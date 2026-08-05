"""Release checking and safe application update helpers.

The web UI can run against a source checkout, Docker, or a packaged desktop
build.  Checking releases is useful in all three modes, while replacing the
running executable is intentionally limited to packaged Windows builds.  In
source/Docker mode the updater exposes the matching release asset so the user
can update through the deployment method they chose.
"""

from __future__ import annotations

import logging
import os
import re
import threading
import time
from typing import Any

import requests

from .otsconfig import config
from .runtimedata import notification_hook

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
    configured = config.get("update_repository") or DEFAULT_REPOSITORY
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
    prerelease = re.search(r"(alpha|beta|rc|preview|dev)[.\-\s]?(\d*)", suffix)
    if not prerelease:
        return (major, minor, patch, 2, 0)
    rank = {"dev": 0, "alpha": 0, "beta": 1, "preview": 2, "rc": 2}[prerelease.group(1)]
    return (major, minor, patch, rank, int(prerelease.group(2) or 0))


def _normalise_release(payload: dict[str, Any], current_version: str) -> dict[str, Any]:
    raw_assets = (
        payload.get("assets") if isinstance(payload.get("assets"), list) else None
    )
    assets: list[dict[str, Any]] = []
    if raw_assets is None:
        logger.error("No Releases unavailable")
        return {}
    for raw in raw_assets:
        if not isinstance(raw, dict) or not raw.get("browser_download_url"):
            continue
        assets.append(
            {
                "name": str(raw.get("name") or ""),
                "size": int(raw.get("size") or 0),
                "download_url": str(raw.get("browser_download_url")),
            }
        )
    latest_version = str(payload.get("tag_name") or payload.get("name") or "").strip()
    return {
        "repository": _repository(),
        "current_version": current_version,
        "latest_version": latest_version,
        "update_available": _version_key(latest_version)
        > _version_key(current_version),
        "release_name": str(payload.get("name") or latest_version),
        "release_url": str(
            payload.get("html_url")
            or f"https://github.com/{_repository()}/releases/latest"
        ),
        "release_notes": str(payload.get("body") or ""),
        "published_at": payload.get("published_at"),
        "prerelease": bool(payload.get("prerelease")),
        "assets": assets,
        "checked_at": time.time(),
        "error": "",
    }


def check_for_updates(force: bool = False) -> dict[str, Any] | bool:
    """Fetch and return structured release information.
    returns None if an error occurs in the request

    """
    with _check_lock:
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
                raise TypeError("GitHub returned an invalid release payload")
            result = _normalise_release(payload, current_version)
            if result.get("update_available", False) is True:
                notification_hook(
                    "New Update Available",
                    "Update Via Docker",
                    result.get("release_url", ""),
                )
        except Exception as exc:  # Network failures should never affect downloading.
            logger.error("Update check unavailable: %s", exc)
            return False

        return result
