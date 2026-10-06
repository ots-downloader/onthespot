"""
runtimedata.py
~~~~~~~~~~~~~~

Application-wide shared state and logging infrastructure.

All mutable global state that must be shared between worker threads lives
here.  Modules import only the symbols they need so it's easy to trace every
access back to this file.
"""

import logging
import re
import sys
import threading
import time
import uuid
from asyncio.log import logger
from collections import deque
from logging.handlers import RotatingFileHandler
from threading import Event, Lock

from .basemodels import QueueItem
from .constants import ItemStatus
from .otsconfig import config
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
    delay=True,
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
    _logger.critical("Uncaught exception", exc_info=(exc_type, exc_value, exc_traceback))


sys.excepthook = _handle_uncaught_exception

# ---------------------------------------------------------------------------
# Shared queues and pools (written to by multiple threads; always access
# under the corresponding lock)
# ---------------------------------------------------------------------------


# Thread Safe Queue Adapter, uses deque with lock
class ThreadSafeDeque:
    def __init__(self, maxsize=100):
        self._deque = deque(maxlen=maxsize)
        self._lock = threading.Lock()

    def put_nowait(self, item):
        with self._lock:
            self._deque.append(item)

    def get_nowait(self):
        with self._lock:
            if not self._deque:
                raise IndexError("pop from an empty deque")
            return self._deque.popleft()

    def get_items(self) -> list:
        with self._lock:
            if not self._deque:
                return []
            return list(self._deque)

    def remove(self, item):
        with self._lock:
            self._deque.remove(item)

    def empty(self):
        queue = self.__len__()
        return not queue > 0

    def qsize(self) -> int:
        """Return the number of queued items using the adapter's lock."""
        return len(self)

    def replace_items(self, items: list) -> None:
        """Replace the queue contents atomically while preserving item order."""
        with self._lock:
            self._deque.clear()
            self._deque.extend(items)

    def __len__(self):
        with self._lock:
            return len(self._deque)

    def __contains__(self, item):
        # Tests membership without copying the whole queue, and stops at the
        # first match. `item in queue.get_items()` builds a full list first.
        with self._lock:
            return item in self._deque

    def __iter__(self):
        # Iterates a snapshot taken under the lock, so another thread adding or
        # removing entries mid-loop cannot invalidate the iterator.
        with self._lock:
            items = list(self._deque)
        return iter(items)


#: Pool of authenticated service accounts added by :class:`AccountPoolLoader`.
account_pool: list = []

#: Temporary download path override (set when user picks a custom location).
temp_download_path: list = []

# Work queues must be unbounded: deque(maxlen=...) silently evicts older work.
#: Items currently being parsed (URL → item dict).
parsing = ThreadSafeDeque(maxsize=None)
#: Items waiting to be moved to the download queue.
pending = ThreadSafeDeque(maxsize=None)

#: Active download queue (local_id → item dict).
download_queue: dict[int, QueueItem] = {}

# Global download pause state. Workers remain alive while paused so a resume
# does not require restarting the server or losing the queue.
download_paused = Event()

# EventSource subscribers.  A single shared ``asyncio.Queue`` caused multiple
# browser tabs to consume each other's events and was unsafe when worker
# threads published into the queue.  Each connection now owns a bounded queue
# on its own event loop.
_websocket_subscribers: dict[str, ThreadSafeDeque] = {}

# LOCK HELPERS
download_queue_lock = Lock()
pause_state_lock = Lock()
websocket_queue_lock = Lock()
rate_limit_lock = Lock()
rate_limit_state = {
    "active": False,
    "host": "",
    "retry_after": 0,
    "until": 0.0,
    "count": 0,
    "last_event": 0.0,
}


def subscribe_websocket(user_id: str) -> tuple[str, ThreadSafeDeque]:
    """Register one SSE connection and return its private event queue."""
    subscription_id = user_id

    with websocket_queue_lock:
        try:
            exists = _websocket_subscribers[subscription_id]
            event_queue = exists
        except (KeyError, IndexError):
            logger.info("No queue for userid %s , creating new one", user_id)
            event_queue: ThreadSafeDeque = ThreadSafeDeque(maxsize=100)
            _websocket_subscribers[subscription_id] = event_queue
    return subscription_id, event_queue


def unsubscribe_websocket(subscription_id: str) -> None:
    """Remove an SSE connection without affecting any other subscriber."""
    with websocket_queue_lock:
        _websocket_subscribers.pop(subscription_id, None)


def _enqueue_websocket_event(event_queue: ThreadSafeDeque, data: dict) -> None:
    """Add an event on the subscriber's loop, dropping only its oldest item."""

    event_queue.put_nowait(data)


# Event callback for EventSource updates
def websocket_event(etype: str, event=""):
    """Publish an event safely to every connected browser."""
    data = {"type": etype, "event": event}
    with websocket_queue_lock:
        subscribers = list(_websocket_subscribers.items())

    stale_subscriptions: list[str] = []
    for subscription_id, event_queue in subscribers:
        try:
            event_queue.put_nowait(data)
        except Exception as e:
            logger.error("Queue Error %s id:%s", e, subscription_id)
            stale_subscriptions.append(subscription_id)

    if stale_subscriptions:
        with websocket_queue_lock:
            for subscription_id in stale_subscriptions:
                _websocket_subscribers.pop(subscription_id, None)


def format_bytes(value: float | None) -> str:
    if not value or value < 0:
        return "—"
    units = ("B", "KB", "MB", "GB")
    amount = float(value)
    unit = 0
    while amount >= 1024 and unit < len(units) - 1:
        amount /= 1024
        unit += 1
    return f"{amount:.1f} {units[unit]}"


def wait_for_download_resume(item: dict) -> None:
    """Block an active worker while global or per-item pause is enabled."""
    was_paused = False
    while download_paused.is_set() or item.get("_pause_requested"):
        if item.get("item_status") == ItemStatus.CANCELLED:
            raise DownloadCancelled("Download cancelled while paused.")
        if not was_paused:
            item["item_status"] = ItemStatus.PAUSED
            websocket_event("STATUS_CHANGE", item)
            was_paused = True
        time.sleep(0.2)
    if was_paused and item.get("item_status") != ItemStatus.CANCELLED:
        item["item_status"] = ItemStatus.DOWNLOADING
        websocket_event("STATUS_CHANGE", item)


def update_download_telemetry(
    item: dict,
    downloaded_bytes: float | None = None,
    total_bytes: float | None = None,
    speed_bps: float | None = None,
) -> None:
    """Attach portable progress, speed, and ETA data to a queue item."""
    now = time.monotonic()
    if downloaded_bytes is not None:
        item["downloaded_bytes"] = max(0, int(downloaded_bytes))
    if total_bytes is not None and total_bytes:
        item["total_bytes"] = max(0, int(total_bytes))

    if speed_bps is None:
        previous_bytes = item.get("_telemetry_bytes")
        previous_time = item.get("_telemetry_time")
        if previous_bytes is not None and previous_time is not None:
            elapsed = now - previous_time
            delta = item.get("downloaded_bytes", 0) - previous_bytes
            if elapsed > 0 and delta >= 0:
                speed_bps = delta / elapsed
    if speed_bps is not None and speed_bps >= 0:
        item["download_speed_bps"] = float(speed_bps)
        item["download_speed"] = f"{format_bytes(speed_bps)}/s"

    if item.get("total_bytes") and item.get("download_speed_bps", 0) > 0:
        remaining = max(0, item["total_bytes"] - item.get("downloaded_bytes", 0))
        item["eta_seconds"] = int(remaining / item["download_speed_bps"])
    else:
        item["eta_seconds"] = None

    if item.get("downloaded_bytes") is not None:
        item["_telemetry_bytes"] = item["downloaded_bytes"]
        item["_telemetry_time"] = now


def record_rate_limit(host: str, retry_after: float, delay: float) -> bool:
    """Record the latest API rate-limit window for the diagnostics UI."""
    now = time.time()
    with rate_limit_lock:
        was_active_for_host = (
            float(rate_limit_state.get("until", 0) or 0) > now and str(rate_limit_state.get("host") or "") == host
        )
        rate_limit_state.update(
            {
                "active": True,
                "host": host,
                "retry_after": max(0, int(retry_after or 0)),
                "until": now + max(0, float(delay or 0)),
                "count": int(rate_limit_state.get("count", 0)) + 1,
                "last_event": now,
            }
        )
    is_new_limit = not was_active_for_host
    if is_new_limit and "spotify" in host.casefold():
        notification_hook(
            "Spotify API rate limited",
            f"Spotify asked OnTheSpot to wait {max(0, int(delay or 0))} second(s) before retrying.",
        )
    return is_new_limit


def get_rate_limit_delay(host: str) -> float:
    """Return the remaining shared cooldown for *host*, if one is active.

    Network workers use this before dispatching a request so a 429 received by
    one worker prevents the other workers from immediately repeating it.
    """
    now = time.time()
    with rate_limit_lock:
        if str(rate_limit_state.get("host") or "") != host:
            return 0.0
        return max(0.0, float(rate_limit_state.get("until", 0) or 0) - now)


def get_rate_limit_state() -> dict:
    """Return a JSON-safe rate-limit snapshot with a live countdown."""
    with rate_limit_lock:
        snapshot = dict(rate_limit_state)
    remaining = max(0, int(float(snapshot.get("until", 0)) - time.time()))
    snapshot["seconds_remaining"] = remaining
    snapshot["active"] = remaining > 0
    return snapshot


def progress_hook(
    item: QueueItem,
    progress: int,
    status: ItemStatus | None = None,
    downloaded_bytes: float | None = None,
    total_bytes: float | None = None,
    speed_bps: float | None = None,
):
    # update_download_telemetry(item, downloaded_bytes, total_bytes, speed_bps)
    item.progress = progress
    if status:
        item.item_status = status

    websocket_event("STATUS_CHANGE", item.model_dump())


def yt_dlp_progress_hook(item: QueueItem, progress_info: dict) -> None:
    """Hook passed to yt-dlp to forward download progress to the GUI."""
    # yt-dlp can emit callbacks without a percentage while probing formats or
    # waiting for a fragment. Check cancellation before returning from those
    # callbacks so a cancelled item cannot continue silently.
    if item.item_status == ItemStatus.CANCELLED:
        raise DownloadCancelled("Download cancelled by user.")
    current = item.progress
    percent_text = progress_info.get("_percent_str", "")
    match = re.search(r"(\d+\.\d+)%", percent_text)
    downloaded = progress_info.get("downloaded_bytes")
    total = progress_info.get("total_bytes") or progress_info.get("total_bytes_estimate")
    speed = progress_info.get("speed")
    if not match:
        return
    new_value = round(float(match.group(1))) - 1
    if new_value >= current + 20:  # offset to avoid locking queue every 2 ms
        progress_hook(
            item,
            new_value,
            ItemStatus.DOWNLOADING,
            downloaded_bytes=downloaded,
            total_bytes=total,
            speed_bps=speed,
        )
    else:
        # update_download_telemetry(item, downloaded, total, speed)
        pass


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
