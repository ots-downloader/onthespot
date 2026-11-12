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
    "length": 327706,
}


class ExistingPlaylistTrackTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="ots-existing-m3u-"))
        self.values = values = {
            "audio_download_path": str(self.root),
            "create_m3u_file": True,
        }
        real_get = config.get
        for patcher in (
            patch.object(config, "get", side_effect=lambda key, default=None: values[key] if key in values else real_get(key, default)),
            patch.object(downloader.time, "sleep"),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)
        while not pending.empty():
            pending.get_nowait()
        with download_queue_lock:
            download_queue.clear()

        self.item = QueueItem(
            local_id=1,
            item_service="spotify",
            item_type="track",
            item_id="69d0sDgbueWWHuFjcZd996",
            item_url="https://open.spotify.com/track/69d0sDgbueWWHuFjcZd996",
            parent_category="playlist",
            playlist_name="Road Trip",
            playlist_by="alice",
            playlist_number="7",
            item_status=ItemStatus.DOWNLOADING,
            download_profile=DownloadProfile(id="p1", name="test", format="mp3", bitrate=320),
        )
        self.existing = self.root / "Pendulum - Showdown.mp3"
        self.existing.write_bytes(b"already downloaded")

    def _handle_existing_file(self):
        return downloader.DownloadWorker()._handle_existing_file(
            self.item,
            "spotify",
            "track",
            self.item.item_id,
            TRACK_METADATA,
            object(),
            str(self.root / "Pendulum - Showdown"),
        )

    def test_existing_playlist_track_is_kept_and_added_to_the_m3u(self):
        handled = self._handle_existing_file()

        self.assertTrue(handled)
        self.assertEqual(self.item.item_status, ItemStatus.ALREADY_EXISTS)
        self.assertTrue(self.existing.exists())
        m3u = (self.root / "M3U" / "Road Trip by alice.m3u8").read_text(encoding="utf-8")
        self.assertIn(str(self.existing), m3u)

    def test_metadata_rewrite_gets_the_existing_path(self):
        self.values["overwrite_existing_metadata"] = True

        with patch.object(downloader.DownloadWorker, "_overwrite_metadata") as overwrite:
            self._handle_existing_file()

        overwrite.assert_called_once()
        self.assertEqual(overwrite.call_args.args[0].file_path, str(self.existing))
        self.assertEqual(self.item.file_path, str(self.existing))

    def _run_worker_over_item(self, m3u_error=None):
        """Run one worker pass over self.item; stop once it is found or fails."""
        worker = downloader.DownloadWorker()

        def stop_after_this_item(*_):
            worker.is_running = False

        with (
            patch.object(downloader, "get_account_token", return_value=object()),
            patch.object(downloader, "get_metadata_function", return_value=lambda *_: TRACK_METADATA),
            patch.object(downloader, "format_item_path", return_value="Pendulum - Showdown"),
            patch.object(downloader, "add_to_m3u_file", side_effect=m3u_error),
            patch.object(downloader, "requeue_item", side_effect=stop_after_this_item),
        ):
            pending.put_nowait(self.item)
            thread = threading.Thread(target=worker.run, daemon=True)
            thread.start()
            deadline = time.monotonic() + 5
            while thread.is_alive() and self.item.item_status != ItemStatus.ALREADY_EXISTS and time.monotonic() < deadline:
                thread.join(timeout=0.05)
            worker.is_running = False
            thread.join(timeout=5)

        self.assertFalse(thread.is_alive())

    def test_existing_file_survives_an_error_in_the_existing_file_step(self):
        self._run_worker_over_item(m3u_error=OSError("disk full"))

        self.assertTrue(self.existing.exists())

    def test_existing_file_survives_an_error_when_the_item_is_retried(self):
        self._run_worker_over_item()
        self.assertEqual(self.item.item_status, ItemStatus.ALREADY_EXISTS)

        self.item.item_status = ItemStatus.WAITING
        self._run_worker_over_item(m3u_error=OSError("disk full"))

        self.assertNotEqual(self.item.item_status, ItemStatus.ALREADY_EXISTS)
        self.assertTrue(self.existing.exists())

    def test_existing_file_without_an_extension_survives_an_error(self):
        self.existing.unlink()
        bare = self.root / "Pendulum - Showdown"
        bare.write_bytes(b"already downloaded")

        self._run_worker_over_item(m3u_error=OSError("disk full"))

        self.assertTrue(bare.exists())


if __name__ == "__main__":
    unittest.main()
