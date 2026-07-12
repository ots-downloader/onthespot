"""Release checking and safe application update helpers.

The web UI can run against a source checkout, Docker, or a packaged desktop
build.  Checking releases is useful in all three modes, while replacing the
running executable is intentionally limited to packaged Windows builds.  In
source/Docker mode the updater exposes the matching release asset so the user
can update through the deployment method they chose.
"""

from __future__ import annotations

import json
import logging
import os
import platform
import re
import subprocess
import sys
import tempfile
import threading
import time
import shutil
import zipfile
from pathlib import Path
from typing import Any, Callable

import requests

from .otsconfig import config


logger = logging.getLogger("onthespot.updater")
_check_lock = threading.Lock()
_update_thread: threading.Thread | None = None
_stop_event = threading.Event()

DEFAULT_REPOSITORY = "ots-downloader/onthespot"
GITHUB_API = "https://api.github.com"
CACHE_FILENAME = "update-status.json"
CACHE_MAX_AGE_SECONDS = 60 * 60


def _repository() -> str:
    """Return the configured GitHub ``owner/repository`` identifier."""
    configured = (
        os.environ.get("ONTHESPOT_UPDATE_REPOSITORY")
        or config.get("update_repository")
        or DEFAULT_REPOSITORY
    )
    value = str(configured).strip().rstrip("/")
    value = re.sub(r"^https?://github\.com/", "", value, flags=re.IGNORECASE)
    value = value.removesuffix(".git").strip("/")
    if re.fullmatch(r"[^/]+/[^/]+", value):
        return value
    return DEFAULT_REPOSITORY


def _headers() -> dict[str, str]:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "OnTheSpot-Updater",
    }
    token = os.environ.get("ONTHESPOT_GITHUB_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _version_key(value: str | None) -> tuple[int, int, int, int, int]:
    """Create a comparable key for tags such as ``v2.0.0alpha1``."""
    text = str(value or "").strip().lower().lstrip("v")
    match = re.search(r"(\d+)(?:\.(\d+))?(?:\.(\d+))?", text)
    if not match:
        return (0, 0, 0, -1, 0)
    major, minor, patch = (int(part or 0) for part in match.groups())
    suffix = text[match.end() :]
    if not suffix:
        return (major, minor, patch, 3, 0)
    prerelease = re.search(r"(alpha|beta|rc|preview|dev)[.-]?(\d*)", suffix)
    if not prerelease:
        return (major, minor, patch, 2, 0)
    rank = {"dev": 0, "alpha": 0, "beta": 1, "preview": 2, "rc": 2}[prerelease.group(1)]
    return (major, minor, patch, rank, int(prerelease.group(2) or 0))


def _cache_path() -> Path:
    configured = config.get("_cache_dir")
    if configured:
        path = Path(str(configured))
    else:
        path = Path(tempfile.gettempdir()) / "onthespot"
    path.mkdir(parents=True, exist_ok=True)
    return path / CACHE_FILENAME


def _read_cache() -> dict[str, Any] | None:
    try:
        with _cache_path().open("r", encoding="utf-8") as handle:
            value = json.load(handle)
        if isinstance(value, dict):
            return value
    except (OSError, TypeError, ValueError):
        return None
    return None


def _write_cache(value: dict[str, Any]) -> None:
    try:
        path = _cache_path()
        temporary = path.with_suffix(".tmp")
        with temporary.open("w", encoding="utf-8") as handle:
            json.dump(value, handle, ensure_ascii=False)
        temporary.replace(path)
    except (OSError, TypeError, ValueError) as exc:
        logger.debug("Could not persist update status: %s", exc)


def _asset_platform(name: str) -> str:
    lowered = name.lower()
    if lowered.endswith(".exe") or lowered.endswith(".exe.zip"):
        return "windows"
    if lowered.endswith(".dmg") or lowered.endswith(".dmg.zip"):
        return "macos"
    if (
        lowered.endswith(".appimage")
        or lowered.endswith(".appimage.zip")
        or lowered.endswith(".tar.gz")
        or lowered.endswith(".tar.gz.zip")
    ):
        return "linux"
    return "other"


def _asset_score(asset_name: str, system: str, machine: str) -> int:
    name = asset_name.lower()
    score = 0
    if system == "windows" and (name.endswith(".exe") or name.endswith(".exe.zip")):
        score += 100
    elif system == "darwin" and (name.endswith(".dmg") or name.endswith(".dmg.zip")):
        score += 100
    elif system == "linux":
        if name.endswith(".appimage") or name.endswith(".appimage.zip"):
            score += 100
        elif name.endswith(".tar.gz") or name.endswith(".tar.gz.zip"):
            score += 80
    if machine in {"amd64", "x86_64"} and any(token in name for token in ("x86_64", "amd64", "64")):
        score += 10
    if machine in {"arm64", "aarch64"} and any(token in name for token in ("arm64", "aarch64")):
        score += 10
    return score


def _select_asset(assets: list[dict[str, Any]]) -> dict[str, Any] | None:
    system = platform.system().lower()
    machine = platform.machine().lower()
    candidates = [asset for asset in assets if _asset_platform(str(asset.get("name", ""))) != "other"]
    if not candidates:
        return None
    ranked = sorted(candidates, key=lambda asset: _asset_score(str(asset.get("name", "")), system, machine), reverse=True)
    best = ranked[0]
    if _asset_score(str(best.get("name", "")), system, machine) < 80:
        return None
    return best


def _normalise_release(payload: dict[str, Any], current_version: str) -> dict[str, Any]:
    raw_assets = payload.get("assets") if isinstance(payload.get("assets"), list) else []
    assets: list[dict[str, Any]] = []
    for raw in raw_assets:
        if not isinstance(raw, dict) or not raw.get("browser_download_url"):
            continue
        assets.append(
            {
                "name": str(raw.get("name") or ""),
                "size": int(raw.get("size") or 0),
                "download_url": str(raw.get("browser_download_url")),
                "platform": _asset_platform(str(raw.get("name") or "")),
            }
        )
    recommended = _select_asset(assets)
    latest_version = str(payload.get("tag_name") or payload.get("name") or "").strip()
    return {
        "repository": _repository(),
        "current_version": current_version,
        "latest_version": latest_version,
        "update_available": _version_key(latest_version) > _version_key(current_version),
        "release_name": str(payload.get("name") or latest_version),
        "release_url": str(payload.get("html_url") or f"https://github.com/{_repository()}/releases/latest"),
        "release_notes": str(payload.get("body") or ""),
        "published_at": payload.get("published_at"),
        "prerelease": bool(payload.get("prerelease")),
        "assets": assets,
        "recommended_asset": recommended,
        "install_supported": bool(getattr(sys, "frozen", False) and platform.system() == "Windows" and recommended),
        "checked_at": time.time(),
        "error": "",
    }


def check_for_updates(force: bool = False) -> dict[str, Any]:
    """Fetch and return structured release information.

    Results are cached for an hour so opening Settings or Diagnostics does not
    repeatedly hit GitHub's unauthenticated API limit.
    """
    with _check_lock:
        cached = _read_cache()
        if not force and cached and time.time() - float(cached.get("checked_at", 0)) < CACHE_MAX_AGE_SECONDS:
            return cached
        current_version = str(config.get("version") or "v0.0.0")
        result: dict[str, Any]
        try:
            response = requests.get(
                f"{GITHUB_API}/repos/{_repository()}/releases/latest",
                headers=_headers(),
                timeout=10,
            )
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict):
                raise ValueError("GitHub returned an invalid release payload")
            result = _normalise_release(payload, current_version)
        except Exception as exc:  # Network failures should never affect downloading.
            logger.info("Update check unavailable: %s", exc)
            result = {
                "repository": _repository(),
                "current_version": current_version,
                "latest_version": "",
                "update_available": False,
                "release_name": "",
                "release_url": f"https://github.com/{_repository()}/releases/latest",
                "release_notes": "",
                "published_at": None,
                "prerelease": False,
                "assets": [],
                "recommended_asset": None,
                "install_supported": False,
                "checked_at": time.time(),
                "error": "Could not check GitHub releases right now.",
            }
        _write_cache(result)
        return result


def _run_windows_install(downloaded: Path, target: Path) -> dict[str, Any]:
    """Schedule replacement of a packaged Windows executable after exit."""
    script = downloaded.with_suffix(".update.ps1")
    script.write_text(
        "param([int]$ParentPid, [string]$Downloaded, [string]$Target, [string]$Script)\n"
        "while (Get-Process -Id $ParentPid -ErrorAction SilentlyContinue) { Start-Sleep -Milliseconds 500 }\n"
        "Copy-Item -LiteralPath $Downloaded -Destination $Target -Force\n"
        "Start-Process -FilePath $Target\n"
        "Remove-Item -LiteralPath $Downloaded -Force -ErrorAction SilentlyContinue\n"
        "Remove-Item -LiteralPath $Script -Force -ErrorAction SilentlyContinue\n",
        encoding="utf-8",
    )
    creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(subprocess, "DETACHED_PROCESS", 0)
    subprocess.Popen(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script),
            "-ParentPid",
            str(os.getpid()),
            "-Downloaded",
            str(downloaded),
            "-Target",
            str(target),
            "-Script",
            str(script),
        ],
        creationflags=creation_flags,
        close_fds=True,
    )
    return {"success": True, "restart_required": True, "message": "Update downloaded. The application will restart."}


def install_update() -> dict[str, Any]:
    """Download and stage the matching release for supported packaged builds."""
    status = check_for_updates(force=True)
    asset = status.get("recommended_asset")
    result_base = {
        "success": False,
        "supported": bool(status.get("install_supported")),
        "latest_version": status.get("latest_version", ""),
        "download_url": (asset or {}).get("download_url") or status.get("release_url", ""),
    }
    if not status.get("update_available"):
        return {**result_base, "message": "The application is already up to date."}
    if not status.get("install_supported") or not asset:
        return {**result_base, "message": "Automatic installation is available only for packaged Windows builds."}

    cache_dir = _cache_path().parent / "updates"
    cache_dir.mkdir(parents=True, exist_ok=True)
    archive_suffix = ".zip" if str(asset.get("name", "")).lower().endswith(".zip") else ".exe"
    downloaded = cache_dir / f"OnTheSpot-{status['latest_version']}.update{archive_suffix}"
    temporary = downloaded.with_suffix(".part")
    try:
        with requests.get(asset["download_url"], headers=_headers(), stream=True, timeout=30) as response:
            response.raise_for_status()
            with temporary.open("wb") as handle:
                for chunk in response.iter_content(chunk_size=1024 * 1024):
                    if chunk:
                        handle.write(chunk)
        temporary.replace(downloaded)
        if downloaded.suffix.lower() == ".zip":
            executable = cache_dir / f"OnTheSpot-{status['latest_version']}.update.exe"
            with zipfile.ZipFile(downloaded) as archive:
                member = next((name for name in archive.namelist() if name.lower().endswith(".exe")), None)
                if not member:
                    raise ValueError("The update archive does not contain a Windows executable")
                with archive.open(member) as source, executable.open("wb") as target:
                    shutil.copyfileobj(source, target)
            downloaded.unlink(missing_ok=True)
            downloaded = executable
        target = Path(sys.executable).resolve()
        return _run_windows_install(downloaded, target)
    except Exception as exc:
        logger.warning("Could not stage application update: %s", exc)
        temporary.unlink(missing_ok=True)
        downloaded.unlink(missing_ok=True)
        return {**result_base, "message": "The update could not be downloaded."}


def start_update_checker(callback: Callable[[str, str, str], None] | None = None) -> None:
    """Start a low-noise background checker when automatic checks are enabled."""
    global _update_thread
    if _update_thread and _update_thread.is_alive():
        return
    _stop_event.clear()

    def worker() -> None:
        announced = ""
        while not _stop_event.is_set():
            if config.get("check_for_updates", True):
                status = check_for_updates()
                latest = str(status.get("latest_version") or "")
                if status.get("update_available") and latest and latest != announced:
                    announced = latest
                    if callback:
                        callback(
                            "Update available",
                            f"OnTheSpot {latest} is ready to download.",
                            str(status.get("release_url") or ""),
                        )
            interval_hours = max(1, int(config.get("update_check_interval_hours", 12) or 12))
            _stop_event.wait(interval_hours * 60 * 60)

    _update_thread = threading.Thread(target=worker, name="update-checker", daemon=True)
    _update_thread.start()


def stop_update_checker() -> None:
    _stop_event.set()
