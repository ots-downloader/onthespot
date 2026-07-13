"""Explicit, local-only yt-dlp authentication settings for YouTube."""

from __future__ import annotations

from pathlib import Path

from .otsconfig import config
from .runtimedata import get_logger

logger = get_logger("youtube_auth")


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
    return {}


def is_youtube_url(value: str) -> bool:
    normalized = (value or "").lower()
    return any(host in normalized for host in ("youtube.com", "youtu.be", "youtube-nocookie.com"))
