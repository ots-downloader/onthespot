"""Regression checks for blocked audio, worker count and failed retries."""

import asyncio
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from _support import TEST_ROOT
from requests.adapters import HTTPAdapter

from onthespot import main
from onthespot.basemodels import QueueItem
from onthespot.constants import ItemStatus
from onthespot.downloader import DownloadWorker, RetryWorker
from onthespot.runtimedata import download_queue, pending
from onthespot.services_middleware import download_spotify
from onthespot.spotify_transport import SpotifyChunkCondition, SpotifyHTTPAdapter
from onthespot.utils import requeue_item


def make_item(local_id=1, status=ItemStatus.WAITING):
    return QueueItem(
        local_id=local_id, item_service="spotify", item_type="track",
        item_id="0" * 22, item_url="https://example.com/track",
        parent_category="playlist", item_status=status,
        download_profile={"id": "mp3-320", "name": "MP3", "format": "mp3", "bitrate": 320},
    )


class SpotifyTransportTests(unittest.TestCase):
    def test_missing_chunk_times_out(self):
        source = SimpleNamespace(closed=False, chunk_exception=None)
        condition = SpotifyChunkCondition(source, timeout=0.01)
        with condition, self.assertRaisesRegex(TimeoutError, "stalled"):
            condition.wait_for(lambda: False)

    def test_failed_chunk_wakes_reader(self):
        source = SimpleNamespace(closed=False, chunk_exception=OSError("network"))
        condition = SpotifyChunkCondition(source)
        with condition, self.assertRaisesRegex(OSError, "chunk failed"):
            condition.wait_for(lambda: False)

    def test_closed_stream_wakes_reader(self):
        source = SimpleNamespace(closed=True, chunk_exception=None)
        condition = SpotifyChunkCondition(source)
        with condition, self.assertRaisesRegex(OSError, "closed"):
            condition.wait_for(lambda: False)

    def test_arriving_chunk_resumes_reader(self):
        source = SimpleNamespace(closed=False, chunk_exception=None)
        condition = SpotifyChunkCondition(source, timeout=1)
        available = threading.Event()

        def deliver():
            with condition:
                available.set()
                condition.notify_all()

        with condition:
            publisher = threading.Thread(target=deliver)
            publisher.start()
            self.assertTrue(condition.wait_for(available.is_set))
        publisher.join(timeout=1)
        self.assertFalse(publisher.is_alive())

    def test_http_timeout_default_and_explicit_override(self):
        adapter = SpotifyHTTPAdapter()
        with patch.object(HTTPAdapter, "send") as send:
            adapter.send(Mock(), timeout=None)
            self.assertEqual(send.call_args.kwargs["timeout"], (10, 30))
            adapter.send(Mock(), timeout=7)
            self.assertEqual(send.call_args.kwargs["timeout"], 7)

    def download(self, source, name):
        token = Mock()
        token.get_user_attribute.return_value = "premium"
        token.content_feeder.return_value.load.return_value = SimpleNamespace(
            input_stream=SimpleNamespace(stream=lambda: source, size=171)
        )
        return download_spotify(make_item(), make_item().item_id, "track", token, str(TEST_ROOT / name))

    def test_complete_audio_excludes_consumed_header_and_closes(self):
        source = Mock(closed=False, chunk_exception=None)
        source.available.return_value = 4
        source.read.side_effect = [b"abc", b"d"]
        self.assertEqual(self.download(source, "complete"), (".mp3", "320k"))
        self.assertEqual((TEST_ROOT / "complete.mp3").read_bytes(), b"abcd")
        self.assertEqual([call.args[0] for call in source.read.call_args_list], [4, 1])
        source.close.assert_called_once()

    def test_truncated_audio_is_failed_before_conversion(self):
        source = Mock(closed=False, chunk_exception=None)
        source.available.return_value = 4
        source.read.side_effect = [b"abc", b""]
        with self.assertRaisesRegex(OSError, "Incomplete"):
            self.download(source, "truncated")
        source.close.assert_called_once()


class WorkerRecoveryTests(unittest.TestCase):
    def tearDown(self):
        pending.replace_items([])
        download_queue.clear()

    def test_retries_only_failed_and_stops_after_three(self):
        failed = make_item(1, ItemStatus.FAILED)
        exhausted = make_item(2, ItemStatus.FAILED)
        exhausted.retry_count = 3
        completed = make_item(3, ItemStatus.DOWNLOADED)
        active = make_item(4, ItemStatus.DOWNLOADING)
        download_queue.update({item.local_id: item for item in (failed, exhausted, completed, active)})
        with patch("onthespot.utils.config.get", return_value=True):
            requeue_item(failed)
        self.assertEqual(failed.item_status, ItemStatus.FAILED)
        worker = RetryWorker()
        worker.retry_failed()
        worker.retry_failed()
        self.assertEqual(pending.get_items(), [failed])
        self.assertEqual(failed.retry_count, 1)
        self.assertEqual(set(download_queue), {2, 3, 4})

    def test_conversion_error_does_not_remain_active_or_remove_other_file(self):
        item = make_item()
        pending.put_nowait(item)
        worker = DownloadWorker()
        temp = TEST_ROOT / "~conversion.mp3"
        temp.write_bytes(b"test audio")
        preserved = TEST_ROOT / "existing.mp3"
        preserved.write_bytes(b"completed audio")
        with (
            patch("onthespot.downloader.get_account_token", return_value=Mock()),
            patch("onthespot.downloader.get_metadata_function", return_value=lambda *args: {"title": "test"}),
            patch("onthespot.downloader.format_item_path", return_value="conversion"),
            patch.object(worker, "_resolve_paths", return_value=(str(temp)[:-4], str(TEST_ROOT / "conversion"))),
            patch.object(worker, "_handle_existing_file", return_value=False),
            patch.object(worker, "_download", return_value=(".mp3", "320k", [])),
            patch.object(worker, "_finalize_audio", side_effect=RuntimeError("conversion failed")),
            patch("onthespot.downloader.time.sleep", side_effect=lambda _: setattr(worker, "is_running", False)),
        ):
            worker.run()
        self.assertEqual(item.item_status, ItemStatus.FAILED)
        self.assertIn("conversion failed", item.error)
        self.assertEqual(preserved.read_bytes(), b"completed audio")
        self.assertFalse(temp.exists())

    def test_lifespan_starts_configured_worker_count(self):
        async def exercise():
            with (
                patch.object(main, "DownloadWorker") as worker_type,
                patch.object(main.parsing_worker, "start"),
                patch.object(main.parsing_worker, "stop"),
                patch.object(main.fillaccountpool, "start"),
                patch.object(main.fillaccountpool, "stop"),
                patch.object(main.config, "get", side_effect=lambda key, *args: {
                    "maximum_download_workers": 5, "enable_retry_worker": False,
                }.get(key)),
            ):
                workers = [Mock() for _ in range(5)]
                worker_type.side_effect = workers
                async with main.lifespan(main.app):
                    self.assertEqual(worker_type.call_count, 5)
                    for worker in workers:
                        worker.start.assert_called_once()
                for worker in workers:
                    worker.stop.assert_called_once()
            main.downloadworkers.clear()

        asyncio.run(exercise())


if __name__ == "__main__":
    unittest.main()
