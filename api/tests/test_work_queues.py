"""Work queues must retain every item in playlists larger than 1,000."""

import unittest

from _support import TEST_ROOT  # noqa: F401
from onthespot.runtimedata import ThreadSafeDeque, parsing, pending


class WorkQueueTests(unittest.TestCase):
    def tearDown(self):
        parsing.replace_items([])
        pending.replace_items([])

    def test_large_playlist_is_consumed_in_full_and_in_order(self):
        items = list(range(4062))
        for name, queue in (("parsing", parsing), ("pending", pending)):
            with self.subTest(queue=name):
                queue.replace_items([])
                for item in items:
                    queue.put_nowait(item)
                self.assertEqual(queue.qsize(), len(items))
                self.assertEqual([queue.get_nowait() for _ in items], items)
                self.assertTrue(queue.empty())

    def test_replacing_work_queue_retains_large_playlist(self):
        items = list(range(4062))
        for name, queue in (("parsing", parsing), ("pending", pending)):
            with self.subTest(queue=name):
                queue.replace_items(items)
                self.assertEqual(queue.get_items(), items)

    def test_bounded_notification_queue_still_keeps_recent_events(self):
        queue = ThreadSafeDeque(maxsize=3)
        for event in range(5):
            queue.put_nowait(event)
        self.assertEqual(queue.get_items(), [2, 3, 4])


if __name__ == "__main__":
    unittest.main()
