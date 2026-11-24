"""Release checks for the update panel.

OnTheSpot does not update itself. Docker (``docker compose pull``) or the
user's own source checkout does the update; this module only finds out whether
a newer release exists and tells the user.

The server keeps the last update status in memory:

* :func:`check_for_updates` with ``force=False`` returns the stored status and
  never calls GitHub, so loading or reloading the page costs no request.
* :func:`check_for_updates` with ``force=True`` asks GitHub for the latest
  release, stores the result and returns it. Checks closer together than
  :data:`MIN_CHECK_INTERVAL_SECONDS` return the stored status instead.
* A background thread (:func:`start_update_checker`) checks at startup and then
  once every :data:`AUTO_CHECK_INTERVAL_SECONDS` while the ``check_for_updates``
  setting is on.
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

UPDATE_REPOSITORY = "ots-downloader/onthespot"
GITHUB_API = "https://api.github.com"
#: A forced check this soon after the last attempt returns the stored status.
MIN_CHECK_INTERVAL_SECONDS = 60
#: The background checker asks GitHub at most this often.
AUTO_CHECK_INTERVAL_SECONDS = 24 * 60 * 60
#: How often the background checker wakes to decide whether to check.
CHECKER_WAKE_SECONDS = 15 * 60
#: In-app link to the diagnostics view, which holds the update panel.
DIAGNOSTICS_URL = "#diagnostics"

_check_lock = threading.Lock()
_update_thread: threading.Thread | None = None
_stop_event = threading.Event()
_status: dict[str, Any] | None = None
_last_attempt: float | None = None  # time.monotonic() of the last request to GitHub
_notified_versions: set[str] = set()


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
    # git describe form of an edge build, e.g. v2.0.5-4-g14eda2c: newer than
    # v2.0.5 itself, older than the next release.
    commits_since_tag = re.fullmatch(r"-(\d+)-g[0-9a-f]+", suffix)
    if commits_since_tag:
        return (major, minor, patch, 4, int(commits_since_tag.group(1)))
    prerelease = re.search(r"(alpha|beta|rc|preview|dev)[.\-\s]?(\d*)", suffix)
    if not prerelease:
        return (major, minor, patch, 2, 0)
    rank = {"dev": 0, "alpha": 0, "beta": 1, "preview": 2, "rc": 2}[prerelease.group(1)]
    return (major, minor, patch, rank, int(prerelease.group(2) or 0))


def is_development_build(value: str | None) -> bool:
    """True for ``dev`` and ``dev-<sha>``: builds with no release tag to compare."""
    text = str(value or "").strip().lower()
    return text in ("", "dev") or text.startswith("dev-")


def _current_version() -> str:
    return str(config.get("version") or "dev")


def _empty_status(current_version: str) -> dict[str, Any]:
    """Return the status shown before any check has run."""
    return {
        "repository": UPDATE_REPOSITORY,
        "current_version": current_version,
        "latest_version": "",
        "update_available": False,
        "development_build": is_development_build(current_version),
        "release_name": "",
        "release_url": "",
        "release_notes": "",
        "published_at": None,
        "prerelease": False,
        "checked_at": None,
        "error": "",
    }


def _stored_status(current_version: str) -> dict[str, Any]:
    return dict(_status) if _status is not None else _empty_status(current_version)


def _normalise_release(payload: dict[str, Any], current_version: str) -> dict[str, Any]:
    latest_version = str(payload.get("tag_name") or "").strip()
    development_build = is_development_build(current_version)
    return {
        "repository": UPDATE_REPOSITORY,
        "current_version": current_version,
        "latest_version": latest_version,
        "update_available": not development_build
        and _version_key(latest_version) > _version_key(current_version),
        "development_build": development_build,
        "release_name": str(payload.get("name") or latest_version),
        "release_url": str(payload.get("html_url") or f"https://github.com/{UPDATE_REPOSITORY}/releases/latest"),
        "release_notes": str(payload.get("body") or ""),
        "published_at": payload.get("published_at"),
        "prerelease": bool(payload.get("prerelease")),
        "checked_at": time.time(),
        "error": "",
    }


def _fetch_latest_release() -> tuple[dict[str, Any] | None, str]:
    """Return ``(payload, "")`` for a release, else ``(None, error)``."""
    try:
        response = requests.get(
            f"{GITHUB_API}/repos/{UPDATE_REPOSITORY}/releases/latest",
            headers=_headers(),
            timeout=10,
        )
    except requests.RequestException as exc:
        logger.warning("Update check could not reach GitHub: %s", exc)
        return None, "Could not reach GitHub to check for updates."
    if response.status_code in (403, 429):
        logger.warning("Update check hit the GitHub rate limit (HTTP %s)", response.status_code)
        return None, "GitHub rate limit reached. Try again later."
    if response.status_code != 200:
        logger.warning("Update check got HTTP %s from GitHub", response.status_code)
        return None, f"GitHub answered with HTTP {response.status_code}."
    try:
        payload = response.json()
    except ValueError:
        payload = None
    if not isinstance(payload, dict) or not payload.get("tag_name"):
        logger.warning("Update check got a reply from GitHub that is not a release")
        return None, "GitHub did not return a release."
    return payload, ""


def _notify(status: dict[str, Any]) -> None:
    """Send one notification per process for each newer version found."""
    latest = status.get("latest_version") or ""
    if not status.get("update_available") or not latest or latest in _notified_versions:
        return
    _notified_versions.add(latest)
    notification_hook(
        "New Update Available",
        f"OnTheSpot {latest} is out. Open Diagnostics for the update steps.",
        DIAGNOSTICS_URL,
    )


def check_for_updates(force: bool = False) -> dict[str, Any]:
    """Return the update status.

    ``force=False`` returns the stored status and makes no request.
    ``force=True`` asks GitHub for the latest release and stores the result,
    unless the last attempt was under :data:`MIN_CHECK_INTERVAL_SECONDS` ago.
    A failed check keeps the last good release fields and sets ``error``.
    """
    global _status, _last_attempt
    current_version = _current_version()
    if not force:
        return _stored_status(current_version)

    with _check_lock:
        now = time.monotonic()
        if _last_attempt is not None and now - _last_attempt < MIN_CHECK_INTERVAL_SECONDS:
            return _stored_status(current_version)
        _last_attempt = now

        try:
            payload, error = _fetch_latest_release()
            if payload is not None:
                status = _normalise_release(payload, current_version)
            else:
                status = _stored_status(current_version)
                status.update(checked_at=time.time(), error=error)
        except Exception:  # A failed check must never affect downloads.
            logger.exception("Update check failed")
            status = _stored_status(current_version)
            status.update(checked_at=time.time(), error="The update check failed. See the server log.")

        _status = status
        if not status["error"]:
            _notify(status)
        return dict(status)


def should_check_now(
    now: float,
    last_attempt: float | None,
    enabled: bool,
    current_version: str,
) -> bool:
    """Decide whether the background checker asks GitHub on this wake."""
    if not enabled or is_development_build(current_version):
        return False
    return last_attempt is None or now - last_attempt >= AUTO_CHECK_INTERVAL_SECONDS


def _checker_loop(stop_event: threading.Event) -> None:
    # The first wake is right at startup. Later wakes make no request unless
    # a day has passed since the last attempt.
    while not stop_event.is_set():
        try:
            if should_check_now(
                time.monotonic(),
                _last_attempt,
                bool(config.get("check_for_updates", True)),
                _current_version(),
            ):
                check_for_updates(force=True)
        except Exception:
            logger.exception("Background update check failed")
        stop_event.wait(CHECKER_WAKE_SECONDS)


def start_update_checker() -> None:
    """Start the background checker thread. It never blocks startup."""
    global _update_thread, _stop_event
    if _update_thread is not None and _update_thread.is_alive() and not _stop_event.is_set():
        return
    # A new event per thread, so a thread that was told to stop stays stopped.
    _stop_event = threading.Event()
    _update_thread = threading.Thread(
        target=_checker_loop, args=(_stop_event,), name="update-checker", daemon=True
    )
    _update_thread.start()


def stop_update_checker() -> None:
    """Ask the background checker to stop. Does not wait for a check in flight."""
    global _update_thread
    _stop_event.set()
    _update_thread = None
