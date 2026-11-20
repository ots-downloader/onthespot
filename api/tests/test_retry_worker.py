"""Regression tests: a failed download must reach the RetryWorker."""

import os
import unittest
from unittest.mock import patch

from _support import TEST_ROOT  # noqa: F401

# librespot ships protobuf files built for the pure-Python runtime.
os.environ.setdefault("PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION", "python")

from onthespot import downloader
from onthespot.basemodels import DownloadProfile, ItemStatus, QueueItem
from onthespot.otsconfig import config
from onthespot.runtimedata import download_queue, download_queue_lock, pending
from onthespot.utils import requeue_item


def make_item(local_id, status, error=""):
    return QueueItem(
        local_id=local_id,
        item_service="deezer",
        item_type="track",
        item_id=f"track-{local_id}",
        item_url=f"https://www.deezer.com/track/{local_id}",
        parent_category="album",
        item_status=status,
        error=error,
        download_profile=DownloadProfile(id="p1", name="test", format="mp3", bitrate=128),
    )


class RetryWorkerTests(unittest.TestCase):
    def setUp(self):
        self.values = values = {"enable_retry_worker": True, "retry_worker_delay": 5}
        real_get = config.get
        patcher = patch.object(
            config,
            "get",
            side_effect=lambda key, default=None: values[key] if key in values else real_get(key, default),
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        while not pending.empty():
            pending.get_nowait()
        with download_queue_lock:
            download_queue.clear()
        self.addCleanup(download_queue.clear)

    def run_retry_worker_once(self):
        worker = downloader.RetryWorker()

        def stop(_seconds):
            worker.is_running = False

        with patch.object(downloader.time, "sleep", side_effect=stop):
            worker.run()

    def fail_item(self, item):
        """Mimic the download worker: mark the item failed, then requeue it."""
        item.error = "RuntimeError during download, see logs."
        item.item_status = ItemStatus.FAILED
        requeue_item(item)

    def test_requeue_keeps_a_failed_item_failed_and_moves_it_last(self):
        first = make_item(1, ItemStatus.DOWNLOADING)
        second = make_item(2, ItemStatus.WAITING)
        with download_queue_lock:
            download_queue[1] = first
            download_queue[2] = second

        self.fail_item(first)

        self.assertEqual(download_queue[1].item_status, ItemStatus.FAILED)
        self.assertEqual(list(download_queue), [2, 1])

    def test_retry_worker_picks_up_a_requeued_failed_item(self):
        item = make_item(1, ItemStatus.DOWNLOADING)
        with download_queue_lock:
            download_queue[1] = item

        self.fail_item(item)
        self.run_retry_worker_once()

        self.assertNotIn(1, download_queue)
        retried = pending.get_items()
        self.assertEqual([entry.local_id for entry in retried], [1])
        self.assertEqual(retried[0].item_status, ItemStatus.WAITING)
        self.assertEqual(retried[0].error, "")
        self.assertEqual(retried[0].retry_count, 1)

    def test_retry_worker_leaves_other_items_alone(self):
        waiting = make_item(1, ItemStatus.WAITING)
        done = make_item(2, ItemStatus.DOWNLOADED)
        unavailable = make_item(3, ItemStatus.UNAVAILABLE, error="unavailable")
        with download_queue_lock:
            download_queue.update({1: waiting, 2: done, 3: unavailable})

        requeue_item(unavailable)
        self.run_retry_worker_once()

        self.assertEqual(pending.get_items(), [])
        self.assertEqual(list(download_queue), [1, 2, 3])
        self.assertEqual(download_queue[3].item_status, ItemStatus.UNAVAILABLE)


if __name__ == "__main__":
    unittest.main()
