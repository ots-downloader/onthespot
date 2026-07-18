"""Secure yt-dlp authentication settings for YouTube."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from .otsconfig import config
from .runtimedata import get_logger

logger = get_logger("youtube_auth")

_MAX_COOKIE_FILE_BYTES = 5 * 1024 * 1024
_COOKIE_HEADERS = {"# HTTP Cookie File", "# Netscape HTTP Cookie File"}


def managed_youtube_cookie_path() -> Path:
    """Return the private, persistent path used for uploaded cookies."""
    cache_root = Path(str(config.get("_cache_dir") or "~/.cache/onthespot")).expanduser()
    return cache_root / "youtube" / "cookies.txt"


def _normalise_cookie_file(contents: bytes, *, youtube_only: bool = False) -> bytes:
    if not contents:
        raise ValueError("The uploaded cookies file is empty")
    if len(contents) > _MAX_COOKIE_FILE_BYTES:
        raise ValueError("The cookies file is larger than 5 MB")

    try:
        text = contents.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError("The cookies file must be UTF-8 text") from exc

    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    if not lines or lines[0].strip() not in _COOKIE_HEADERS:
        raise ValueError(
            "Use a Netscape-format cookies.txt file whose first line is "
            "'# Netscape HTTP Cookie File'"
        )

    cookie_count = 0
    youtube_cookie_count = 0
    youtube_cookie_lines: list[str] = []
    for raw_line in lines[1:]:
        line = raw_line.strip()
        if not line:
            continue
        cookie_line = line.removeprefix("#HttpOnly_")
        if cookie_line.startswith("#"):
            continue
        fields = cookie_line.split("\t")
        if len(fields) < 7:
            continue
        cookie_count += 1
        domain = fields[0].lstrip(".").lower()
        if (
            domain == "youtube.com"
            or domain.endswith(".youtube.com")
            or domain == "google.com"
            or domain.endswith(".google.com")
        ):
            youtube_cookie_count += 1
            youtube_cookie_lines.append(line)

    if cookie_count == 0:
        raise ValueError("The cookies file contains no Netscape cookie entries")
    if youtube_cookie_count == 0:
        raise ValueError("The cookies file contains no YouTube or Google cookies")

    if youtube_only:
        return (
            "# Netscape HTTP Cookie File\n"
            + "\n".join(youtube_cookie_lines)
            + "\n"
        ).encode("utf-8")

    return ("\n".join(lines).rstrip("\n") + "\n").encode("utf-8")


def validate_youtube_cookie_file(path: Path) -> None:
    """Validate a server-side cookies file without exposing its contents."""
    if not path.is_absolute() or not path.is_file():
        raise ValueError("Choose an existing absolute cookies-file path on the OnTheSpot server")
    try:
        contents = path.read_bytes()
    except OSError as exc:
        raise ValueError(f"The cookies file cannot be read: {exc}") from exc
    _normalise_cookie_file(contents)


def store_youtube_cookie_file(contents: bytes) -> Path:
    """Validate and privately store an uploaded Netscape cookies file."""
    # A browser export can contain cookies for every visited site. Keep only
    # the YouTube/Google rows needed by yt-dlp before writing app data.
    normalised = _normalise_cookie_file(contents, youtube_only=True)
    destination = managed_youtube_cookie_path()
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(".tmp")
    temporary.write_bytes(normalised)
    try:
        os.chmod(temporary, 0o600)
    except OSError:
        pass
    os.replace(temporary, destination)
    return destination


def validate_youtube_browser(browser: str) -> None:
    """Confirm that yt-dlp can read the browser profile on this host."""
    from yt_dlp import YoutubeDL

    try:
        with YoutubeDL({"cookiesfrombrowser": (browser,), "quiet": True, "no_warnings": True}) as downloader:
            cookie_jar = downloader.cookiejar
            if not any(
                "youtube.com" in str(cookie.domain).lower() or "google.com" in str(cookie.domain).lower()
                for cookie in cookie_jar
            ):
                raise ValueError(f"No YouTube cookies were found in the {browser} profile on this host")
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError(
            f"The {browser} profile is not available to OnTheSpot on this host. "
            "Docker and Unraid users should upload a cookies.txt file instead."
        ) from exc


def youtube_auth_status() -> dict[str, Any]:
    """Return a cheap status snapshot for the configured session source.

    Browser cookie stores can contain tens of thousands of entries and may be
    locked while the browser is running.  Reading one during every Accounts
    page status request is both expensive and disruptive, so browser profiles
    are validated only when the user explicitly saves the setup (and naturally
    by yt-dlp when a download starts).  Uploaded files remain cheap enough to
    validate here because they are capped at 5 MB.
    """
    mode = str(config.get("youtube_auth_mode") or "none")
    if mode == "none":
        return {"mode": mode, "configured": False, "ready": False, "source": "None", "error": ""}

    try:
        if mode == "browser":
            browser = str(config.get("youtube_cookies_browser") or "").strip()
            if not browser:
                raise ValueError("No browser profile is configured")
            source = f"{browser.title()} on the OnTheSpot host"
        elif mode == "cookie_file":
            cookie_file = Path(str(config.get("youtube_cookies_file") or "")).expanduser()
            validate_youtube_cookie_file(cookie_file)
            source = "Uploaded cookies.txt" if cookie_file == managed_youtube_cookie_path() else cookie_file.name
        else:
            raise ValueError("Unsupported YouTube authentication mode")
    except ValueError as exc:
        return {"mode": mode, "configured": True, "ready": False, "source": "Unavailable", "error": str(exc)}

    return {"mode": mode, "configured": True, "ready": True, "source": source, "error": ""}


def youtube_ydl_options() -> dict:
    """Return yt-dlp options for a user-selected local YouTube session.

    Only a browser profile name or a local cookies-file path is stored in the
    configuration. Cookie values are never sent to the web UI or persisted by
    this helper.
    """
    mode = str(config.get("youtube_auth_mode") or "none")
    if mode == "browser":
        browser = str(config.get("youtube_cookies_browser") or "").strip()
        if browser:
            return {"cookiesfrombrowser": (browser,)}
    elif mode == "cookie_file":
        cookie_file = Path(str(config.get("youtube_cookies_file") or "")).expanduser()
        if cookie_file.is_file():
            return {"cookiefile": str(cookie_file)}
        logger.warning("Configured YouTube cookies file is unavailable: %s", cookie_file)
        raise RuntimeError(
            "The configured YouTube cookies file is unavailable. Reconfigure the YouTube worker in Accounts."
        )
    return {}


def is_youtube_url(value: str) -> bool:
    normalized = (value or "").lower()
    return any(host in normalized for host in ("youtube.com", "youtu.be", "youtube-nocookie.com"))
