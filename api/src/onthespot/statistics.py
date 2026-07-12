"""Persistent download history and statistics for the web UI."""

from __future__ import annotations

import json
import os
import threading
import time
from typing import Any

from .otsconfig import config


_lock = threading.RLock()
_MAX_EVENTS = 5000
_SUCCESS_STATUSES = {"Downloaded", "Already Exists"}
_FAILURE_STATUSES = {"Failed", "Cancelled", "Unavailable"}


def _history_path() -> str:
    root = config.get("_cache_dir") or os.path.join(os.path.expanduser("~"), ".onthespot")
    return os.path.join(root, "download-history.json")


def _empty_history() -> dict[str, Any]:
    return {
        "version": 1,
        "events": [],
        "totals": {"downloads": 0, "bytes": 0, "success": 0, "failed": 0},
        "formats": {},
    }


def _load() -> dict[str, Any]:
    try:
        with open(_history_path(), "r", encoding="utf-8") as handle:
            value = json.load(handle)
        if isinstance(value, dict):
            base = _empty_history()
            base.update(value)
            base.setdefault("events", [])
            base.setdefault("totals", _empty_history()["totals"])
            base.setdefault("formats", {})
            return base
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        pass
    return _empty_history()


def _save(value: dict[str, Any]) -> None:
    target = _history_path()
    try:
        os.makedirs(os.path.dirname(target), exist_ok=True)
        temporary = f"{target}.tmp"
        with open(temporary, "w", encoding="utf-8") as handle:
            json.dump(value, handle, indent=2, ensure_ascii=False)
        os.replace(temporary, target)
    except OSError:
        # Statistics must never interrupt a download.
        return


def record_terminal_item(item: dict[str, Any]) -> None:
    """Record a queue item once when it reaches a terminal status."""
    raw_status = item.get("item_status", "")
    status = getattr(raw_status, "value", raw_status)
    status = str(status)
    if status not in _SUCCESS_STATUSES | _FAILURE_STATUSES or item.get("_stats_recorded"):
        return

    item["_stats_recorded"] = True
    success = status in _SUCCESS_STATUSES
    file_path = item.get("file_path") or ""
    byte_count = item.get("file_size") or item.get("total_bytes") or 0
    try:
        if file_path and os.path.isfile(file_path):
            byte_count = os.path.getsize(file_path)
        byte_count = max(0, int(byte_count or 0))
    except (OSError, TypeError, ValueError):
        byte_count = 0

    event = {
        "id": f"{item.get('local_id', '')}-{time.time_ns()}",
        "timestamp": int(time.time()),
        "status": status,
        "success": success,
        "bytes": byte_count,
        "format": str(item.get("format") or item.get("profile_format") or "unknown"),
        "name": str(item.get("name") or ""),
        "artist": str(item.get("artist") or ""),
        "service": str(item.get("item_service") or ""),
        "error": str(item.get("error") or "") if not success else "",
    }
    with _lock:
        history = _load()
        totals = history["totals"]
        totals["downloads"] = int(totals.get("downloads", 0)) + 1
        totals["bytes"] = int(totals.get("bytes", 0)) + byte_count
        totals["success" if success else "failed"] = int(totals.get("success" if success else "failed", 0)) + 1
        fmt = event["format"]
        formats = history["formats"]
        formats[fmt] = int(formats.get(fmt, 0)) + 1
        history["events"] = [event, *history.get("events", [])][:_MAX_EVENTS]
        _save(history)


def export_history() -> dict[str, Any]:
    with _lock:
        return _load()


def import_history(value: Any) -> bool:
    if not isinstance(value, dict) or not isinstance(value.get("events", []), list):
        return False
    history = _empty_history()
    history["events"] = value.get("events", [])[:_MAX_EVENTS]
    history["totals"] = value.get("totals", history["totals"])
    history["formats"] = value.get("formats", {})
    with _lock:
        _save(history)
    return True


def clear_history() -> None:
    """Remove all persisted download statistics and activity events."""
    with _lock:
        _save(_empty_history())


def get_statistics() -> dict[str, Any]:
    with _lock:
        history = _load()
    totals = history.get("totals", {})
    attempts = int(totals.get("success", 0)) + int(totals.get("failed", 0))
    return {
        "totals": {
            "downloads": int(totals.get("downloads", 0)),
            "bytes": int(totals.get("bytes", 0)),
            "success": int(totals.get("success", 0)),
            "failed": int(totals.get("failed", 0)),
            "success_rate": round((int(totals.get("success", 0)) / attempts) * 100, 1) if attempts else 0,
        },
        "formats": history.get("formats", {}),
        "history": history.get("events", [])[:100],
    }
