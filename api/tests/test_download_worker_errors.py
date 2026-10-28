import os
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from _support import TEST_ROOT  # noqa: F401

# librespot ships protobuf files built for the pure-Python runtime.
os.environ.setdefault("PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION", "python")

from onthespot import downloader
from onthespot.basemodels import DownloadProfile, ItemStatus, QueueItem
from onthespot.otsconfig import config
from onthespot.runtimedata import download_queue, download_queue_lock, pending

TRACK_METADATA = {
    "title": "Showdown",
    "artists": "Pendulum",
    "album_name": "Showdown",
}


def queue_item(local_id, service):
    return QueueItem(
        local_id=local_id,
        item_service=service,
        item_type="track",
        item_id=f"id{local_id}",
        item_url=f"https://example.com/{local_id}",
        parent_category="track",
        item_status=ItemStatus.WAITING,
        download_profile=DownloadProfile(id="p1", name="test", format="mp3", bitrate=320),
    )


class FirstItemTests(unittest.TestCase):
    """The first item a worker takes runs before any earlier item has set its values."""

    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="ots-worker-errors-"))
        values = {"audio_download_path": str(self.root)}
        real_get = config.get
        self.worker = downloader.DownloadWorker()
        while not pending.empty():
            pending.get_nowait()
        with download_queue_lock:
            download_queue.clear()
        for patcher in (
            patch.object(config, "get", side_effect=lambda key, default=None: values[key] if key in values else real_get(key, default)),
            patch.object(downloader.time, "sleep"),
            patch.object(downloader, "get_account_token", return_value=object()),
            patch.object(downloader, "get_metadata_function", return_value=lambda *_: TRACK_METADATA),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

    def _run_until_settled(self, items):
        for item in items:
            pending.put_nowait(item)
        thread = threading.Thread(target=self.worker.run, daemon=True)
        thread.start()
        settled = (ItemStatus.FAILED, ItemStatus.DOWNLOADED, ItemStatus.ALREADY_EXISTS)
        deadline = time.monotonic() + 5
        while thread.is_alive() and items[-1].item_status not in settled and time.monotonic() < deadline:
            thread.join(timeout=0.05)
        self.worker.is_running = False
        thread.join(timeout=5)

    def test_worker_survives_a_path_formatter_error_on_its_first_item(self):
        broken = queue_item(1, "spotify")
        with patch.object(downloader, "format_item_path", side_effect=[KeyError("title"), "Pendulum - Showdown"]):
            (self.root / "Pendulum - Showdown.mp3").write_bytes(b"already downloaded")
            nxt = queue_item(2, "spotify")
            self._run_until_settled([broken, nxt])

        self.assertEqual(nxt.item_status, ItemStatus.ALREADY_EXISTS)

    def test_worker_survives_a_cancel_before_metadata_on_its_first_item(self):
        cancelled = queue_item(1, "spotify")
        nxt = queue_item(2, "spotify")
        (self.root / "Pendulum - Showdown.mp3").write_bytes(b"already downloaded")

        def cancel_while_fetching_token(*_, **__):
            cancelled.item_status = ItemStatus.CANCELLED
            return object()

        with (
            patch.object(downloader, "get_account_token", side_effect=cancel_while_fetching_token),
            patch.object(downloader, "format_item_path", return_value="Pendulum - Showdown"),
        ):
            self._run_until_settled([cancelled, nxt])

        self.assertEqual(nxt.item_status, ItemStatus.ALREADY_EXISTS)

    def test_generic_link_downloads_on_a_fresh_worker(self):
        item = queue_item(1, "generic")
        with patch.object(downloader, "download_generic"):
            self._run_until_settled([item])

        self.assertEqual(item.item_status, ItemStatus.DOWNLOADED)


if __name__ == "__main__":
    unittest.main()
