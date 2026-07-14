"""Regression tests for shared runtime event delivery."""

import asyncio
import threading
import unittest

from _support import TEST_ROOT  # noqa: F401
from onthespot.runtimedata import (
    subscribe_websocket,
    unsubscribe_websocket,
    websocket_event,
)


class WebsocketEventTests(unittest.IsolatedAsyncioTestCase):
    async def test_event_is_broadcast_to_every_subscriber(self):
        first_id, first_queue = subscribe_websocket("first")
        second_id, second_queue = subscribe_websocket("second")
        try:
            websocket_event("STATUS_CHANGE", {"local_id": "track-1"})
            first = await asyncio.wait_for(first_queue.get(), timeout=1)
            second = await asyncio.wait_for(second_queue.get(), timeout=1)
            self.assertEqual(first, second)
            self.assertEqual(first["type"], "STATUS_CHANGE")
        finally:
            unsubscribe_websocket(first_id)
            unsubscribe_websocket(second_id)

    async def test_worker_thread_can_publish_safely(self):
        subscription_id, event_queue = subscribe_websocket("threaded")
        try:
            publisher = threading.Thread(
                target=websocket_event,
                args=("WORKER_EVENT", {"ok": True}),
            )
            publisher.start()
            publisher.join(timeout=1)
            event = await asyncio.wait_for(event_queue.get(), timeout=1)
            self.assertEqual(event, {"type": "WORKER_EVENT", "event": {"ok": True}})
        finally:
            unsubscribe_websocket(subscription_id)

    async def test_unsubscribe_does_not_drain_other_connections(self):
        first_id, first_queue = subscribe_websocket("first")
        second_id, second_queue = subscribe_websocket("second")
        unsubscribe_websocket(first_id)
        try:
            websocket_event("ONLY_SECOND", "value")
            second = await asyncio.wait_for(second_queue.get(), timeout=1)
            self.assertEqual(second["type"], "ONLY_SECOND")
            with self.assertRaises(TimeoutError):
                await asyncio.wait_for(first_queue.get(), timeout=0.05)
        finally:
            unsubscribe_websocket(second_id)


if __name__ == "__main__":
    unittest.main()
