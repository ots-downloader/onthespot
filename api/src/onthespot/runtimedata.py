"""
runtimedata.py
~~~~~~~~~~~~~~

Application-wide shared state and logging infrastructure.

All mutable global state that must be shared between worker threads lives
here.  Modules import only the symbols they need so it's easy to trace every
access back to this file.
"""

import linecache
import logging

import re
import sys
import uuid
import tracemalloc

import asyncio
from functools import wraps
from logging.handlers import RotatingFileHandler
from threading import Lock
from .otsconfig import config
from .constants import ItemStatus
from .resources.exceptions import DownloadCancelled
# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

_log_formatter = logging.Formatter(
    "[%(asctime)s :: %(name)s :: %(pathname)s -> %(lineno)s:%(funcName)20s() :: %(levelname)s] -> %(message)s"
)
_file_handler = RotatingFileHandler(
    config.get("_log_file"),
    mode="a",
    maxBytes=(5 * 1024 * 1024),
    backupCount=2,
    encoding="utf-8",
    delay=0,
)
_stdout_handler = logging.StreamHandler(sys.stdout)
_file_handler.setFormatter(_log_formatter)
_stdout_handler.setFormatter(_log_formatter)

log_level = "DEBUG"


def get_logger(name: str) -> logging.Logger:
    """Return a named logger that writes to both the log file and stdout."""
    logger = logging.getLogger(name)
    logger.addHandler(_file_handler)
    logger.addHandler(_stdout_handler)
    logger.setLevel(log_level)
    return logger


_logger = get_logger("runtimedata")

# ---------------------------------------------------------------------------
# Uncaught-exception handler
# ---------------------------------------------------------------------------


def _handle_uncaught_exception(exc_type, exc_value, exc_traceback):
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return
    _logger.critical(
        "Uncaught exception", exc_info=(exc_type, exc_value, exc_traceback)
    )


sys.excepthook = _handle_uncaught_exception

# ---------------------------------------------------------------------------
# Shared queues and pools (written to by multiple threads; always access
# under the corresponding lock)
# ---------------------------------------------------------------------------

#: Pool of authenticated service accounts added by :class:`AccountPoolLoader`.
account_pool: list = []

#: Temporary download path override (set when user picks a custom location).
temp_download_path: list = []

#: Items currently being parsed (URL → item dict).
parsing: dict = {}

#: Items waiting to be moved to the download queue.
pending: asyncio.Queue = asyncio.Queue()

#: Active download queue (local_id → item dict).
download_queue: dict = {}

# Notification queue for EventSource updates.
websocket_queue: asyncio.Queue = asyncio.Queue()

# LOCK HELPERS
parsing_lock = Lock()
pending_lock = Lock()
download_queue_lock = Lock()
websocket_queue_lock = Lock()


# Event callback for EventSource updates
def websocket_event(etype: str, event=""):
    if websocket_queue:
        data = {"type": etype, "event": event}
        websocket_queue.put_nowait(data)

def progress_hook(item: dict, progress: int, status: ItemStatus | None = None):
    item["progress"] = progress
    if status:
        item["item_status"] = status
    websocket_event("STATUS_CHANGE", item)

def yt_dlp_progress_hook(item: dict, progress_info: dict) -> None:
    """Hook passed to yt-dlp to forward download progress to the GUI."""
    current = item.get("progress", 0)
    match = re.search(r"(\d+\.\d+)%", progress_info["_percent_str"])
    if not match:
        return
    new_value = round(float(match.group(1))) - 1
    if new_value >= current + 20:  # offset to avoid locking queue every 2 ms
        item["progress"] = new_value
        progress_hook(item, new_value, ItemStatus.DOWNLOADING)
    if item["item_status"] == ItemStatus.CANCELLED:
        raise DownloadCancelled("Download cancelled by user.")

def notification_hook(
    title,
    message="",
    url="",
):
    """
    Sends a notification event through the websocket queue.

    :param title: The title of the notification.
    :param message: Optional message for the notification. Defaults to an empty string.
    :param url: Optional URL associated with the notification. Defaults to an empty string.
    """
    websocket_event(
        etype="Notification",
        event={
            "id": f"{uuid.uuid4()}",
            "url": f"{url}",
            "title": f"{title}",
            "message": f"{message}",
        },
    )

# ---------------------------------------------------------------------------
# System-tray initialisation flag
# ---------------------------------------------------------------------------

_tray_initialized: bool = False


def set_tray_initialized(value: bool) -> None:
    """Mark whether the system tray has been set up."""
    global _tray_initialized
    _tray_initialized = value


def is_tray_initialized() -> bool:
    """Return ``True`` if the system tray has been initialised."""
    return _tray_initialized


# ---------------------------------------------------------------------------
# Memory-profiling decorator (development / debug use only)
# ---------------------------------------------------------------------------


def log_function_memory(wrap_func):
    """Decorator that logs memory usage before and after *wrap_func* runs.

    Uses :mod:`tracemalloc`.  Enable with::

        @log_function_memory
        def my_expensive_function(...):
            ...
    """
    tracemalloc.start()
    top_limit = 10

    def _display_top(snapshot, prefix, key_type="lineno"):
        snapshot = snapshot.filter_traces(
            (
                tracemalloc.Filter(False, "<frozen importlib._bootstrap>"),
                tracemalloc.Filter(False, "<unknown>"),
            )
        )
        top_stats = snapshot.statistics(key_type)

        _logger.debug(f"{prefix} Top {top_limit} lines")
        for index, stat in enumerate(top_stats[:top_limit], 1):
            frame = stat.traceback[0]
            _logger.debug(
                "#%s: %s:%s: %.1f KiB"
                % (index, frame.filename, frame.lineno, stat.size / 1024)
            )
            line = linecache.getline(frame.filename, frame.lineno).strip()
            if line:
                _logger.debug(f"{prefix} -- {line}")

        other = top_stats[top_limit:]
        if other:
            size = sum(stat.size for stat in other)
            _logger.debug("%s other: %.1f KiB" % (len(other), size / 1024))
        total = sum(stat.size for stat in top_stats)
        _logger.debug("Total allocated size: %.1f KiB" % (total / 1024))

    @wraps(wrap_func)
    def _wrapper(*args, **kwargs):
        prefix = f"{wrap_func.__name__}: "
        snapshot_before = tracemalloc.take_snapshot()
        _logger.debug(f"Snapshotting before {wrap_func.__name__} call")
        result = wrap_func(*args, **kwargs)
        _display_top(snapshot_before, prefix)
        _logger.debug(f"Snapshotting after {wrap_func.__name__} call")
        snapshot_after = tracemalloc.take_snapshot()
        _display_top(snapshot_after, prefix)
        top_stats = snapshot_after.compare_to(snapshot_before, "lineno")
        _logger.debug(f"{prefix} Top {top_limit} differences")
        for stat in top_stats[:10]:
            _logger.debug(f"{prefix}{stat}")
        return result

    return _wrapper


# ---------------------------------------------------------------------------
# Backwards-compatible aliases (avoids breaking any code that imported the
# old names directly)
# ---------------------------------------------------------------------------

#: Deprecated — use :func:`set_tray_initialized`.
set_init_tray = set_tray_initialized
#: Deprecated — use :func:`is_tray_initialized`.
get_init_tray = is_tray_initialized
