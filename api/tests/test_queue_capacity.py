"""Regression tests: large playlists must not lose tracks in the shared queues."""

import os
import unittest

from _support import TEST_ROOT  # noqa: F401

# librespot ships protobuf files built for the pure-Python runtime.
os.environ.setdefault("PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION", "python")

from onthespot.runtimedata import parsing, pending


class QueueCapacityTests(unittest.TestCase):
    def setUp(self):
        for queue in (parsing, pending):
            queue.replace_items([])
            self.addCleanup(queue.replace_items, [])

    def test_queues_keep_every_track_of_a_large_playlist(self):
        tracks = list(range(1, 1306))  # a playlist with 1305 tracks

        for queue in (parsing, pending):
            for track in tracks:
                queue.put_nowait(track)

            kept = queue.get_items()
            self.assertEqual(len(kept), len(tracks))
            # A bounded deque silently drops the oldest entries, i.e. the first tracks.
            self.assertEqual(kept[0], 1)
            self.assertEqual(kept[-1], 1305)


if __name__ == "__main__":
    unittest.main()
