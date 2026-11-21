"""Regression tests: large playlists must not silently lose tracks in the shared queues."""

import os
import unittest
from unittest.mock import patch

from _support import TEST_ROOT  # noqa: F401

# librespot ships protobuf files built for the pure-Python runtime.
os.environ.setdefault("PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION", "python")

from onthespot import parsingworker, runtimedata
from onthespot.basemodels import DownloadProfile
from onthespot.otsconfig import config
from onthespot.runtimedata import (
    DEFAULT_MAX_QUEUE_SIZE,
    MAX_QUEUE_SIZE_SETTING_URL,
    get_max_queue_size,
    parsing,
    pending,
    queue_new_item,
)


class QueueCapacityTests(unittest.TestCase):
    def setUp(self):
        for queue in (parsing, pending):
            queue.replace_items([])
            self.addCleanup(queue.replace_items, [])
        self.values = values = {}
        real_get = config.get
        patcher = patch.object(
            config,
            "get",
            side_effect=lambda key, default=None: values[key] if key in values else real_get(key, default),
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        notify = patch.object(runtimedata, "notification_hook")
        self.notification_hook = notify.start()
        self.addCleanup(notify.stop)
        # Each test starts as if the last add had succeeded.
        runtimedata._queue_limit_notified = False

    def test_queues_never_drop_their_oldest_items(self):
        tracks = list(range(1, 1306))  # a playlist with 1305 tracks

        for queue in (parsing, pending):
            for track in tracks:
                queue.put_nowait(track)

            kept = queue.get_items()
            self.assertEqual(len(kept), len(tracks))
            # A bounded deque silently drops the oldest entries, i.e. the first tracks.
            self.assertEqual(kept[0], 1)
            self.assertEqual(kept[-1], 1305)

    def test_default_limit_is_3000(self):
        self.assertEqual(DEFAULT_MAX_QUEUE_SIZE, 3000)
        self.values["max_queue_size"] = 3000
        self.assertEqual(get_max_queue_size(), 3000)

    def test_invalid_limit_falls_back_to_default(self):
        for value in (0, -5, "abc", None):
            self.values["max_queue_size"] = value
            self.assertEqual(get_max_queue_size(), DEFAULT_MAX_QUEUE_SIZE, value)

    def test_full_queue_refuses_new_items_and_keeps_the_first_ones(self):
        self.values["max_queue_size"] = 10

        for queue in (parsing, pending):
            added = [queue_new_item(queue, track) for track in range(1, 16)]

            self.assertEqual(added, [True] * 10 + [False] * 5)
            self.assertEqual(queue.get_items(), list(range(1, 11)))

    def test_full_queue_sends_one_notification_with_a_link_to_the_setting(self):
        self.values["max_queue_size"] = 2

        for track in range(5):
            queue_new_item(pending, track)

        self.notification_hook.assert_called_once()
        title, message, url = self.notification_hook.call_args.args
        self.assertEqual(title, "Queue limit reached")
        self.assertIn("Max Queue Size", message)
        self.assertEqual(url, MAX_QUEUE_SIZE_SETTING_URL)

    def test_notification_repeats_after_the_queue_had_room_again(self):
        self.values["max_queue_size"] = 1

        queue_new_item(pending, "a")
        queue_new_item(pending, "b")  # refused, notifies
        pending.get_nowait()  # the download worker takes "a"
        queue_new_item(pending, "c")  # fits again
        queue_new_item(pending, "d")  # refused, notifies again

        self.assertEqual(self.notification_hook.call_count, 2)

    def test_requeued_items_ignore_the_limit(self):
        # Retries move items that are already known back into pending; the
        # limit must never make them disappear.
        self.values["max_queue_size"] = 1
        queue_new_item(pending, "new")

        pending.put_nowait("retry")

        self.assertEqual(pending.get_items(), ["new", "retry"])

    def test_parsing_worker_stops_expanding_an_album_at_the_limit(self):
        self.values["max_queue_size"] = 50
        track_ids = [f"track-{n}" for n in range(1, 1306)]
        worker = parsingworker.ParsingWorker()
        profile = DownloadProfile(id="p1", name="test", format="mp3", bitrate=128)

        with (
            patch.dict(parsingworker.SERVICE_ALBUM_TRACK_ID_FUNCTIONS, {"deezer": lambda _token, _id: track_ids}),
            patch.object(parsingworker.ParsingWorker, "_get_active_profile", return_value=profile),
        ):
            worker._expand_collection("deezer", "album", "album-1", None, "https://www.deezer.com/album/1")

        kept = pending.get_items()
        self.assertEqual(len(kept), 50)
        self.assertEqual(kept[0].item_id, "track-1")
        self.assertEqual(kept[-1].item_id, "track-50")
        self.notification_hook.assert_called_once()


if __name__ == "__main__":
    unittest.main()
