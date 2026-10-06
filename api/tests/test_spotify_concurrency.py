"""Concurrent stream setup must not mix librespot audio-key callbacks."""

import threading
import time
import unittest
import queue
from types import SimpleNamespace
from unittest.mock import Mock, patch

from _support import TEST_ROOT
from test_download_recovery import make_item

from onthespot.api import spotify
from onthespot.services_middleware import download_spotify
from onthespot.spotify_transport import bound_spotify_requests


class SpotifyConcurrencyTests(unittest.TestCase):
    def test_content_errors_and_timeouts_do_not_close_shared_session(self):
        for failure in (RuntimeError("Failed fetching audio key!"), queue.Empty()):
            with self.subTest(failure=type(failure).__name__):
                token = Mock()
                token.content_feeder.return_value.load.side_effect = failure
                item = make_item()
                with patch("onthespot.services_middleware.reinit_spotify_session") as reinit:
                    with self.assertRaises((RuntimeError, TimeoutError)):
                        download_spotify(item, item.item_id, "track", token, str(TEST_ROOT / "failed-setup"))
                    reinit.assert_not_called()
                    token.close.assert_not_called()

    def test_unauthenticated_session_still_reconnects(self):
        token = Mock()
        token.content_feeder.return_value.load.side_effect = RuntimeError("Session isn't authenticated!")
        item = make_item()
        with patch("onthespot.services_middleware.reinit_spotify_session") as reinit:
            with self.assertRaisesRegex(RuntimeError, "connection lost"):
                download_spotify(item, item.item_id, "track", token, str(TEST_ROOT / "unauthenticated"))
            reinit.assert_called_once_with(token)

    def test_five_stream_setups_are_serial_but_audio_reads_overlap(self):
        reads = threading.Barrier(5)
        guard = threading.Lock()
        active = maximum = 0
        errors = []

        def load(*args):
            nonlocal active, maximum
            with guard:
                active += 1
                maximum = max(maximum, active)
            try:
                time.sleep(0.01)
                source = Mock(closed=False, chunk_exception=None)
                source.available.return_value = 4

                def read(size):
                    reads.wait(timeout=5)
                    return b"data"

                source.read.side_effect = read
                return SimpleNamespace(input_stream=SimpleNamespace(stream=lambda: source))
            finally:
                with guard:
                    active -= 1

        token = Mock()
        token.content_feeder.return_value.load.side_effect = load

        def download(index):
            try:
                item = make_item(index)
                download_spotify(item, item.item_id, "track", token, str(TEST_ROOT / f"parallel-{index}"))
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=download, args=(index,)) for index in range(5)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=10)
        self.assertTrue(all(not thread.is_alive() for thread in threads))
        self.assertEqual(errors, [])
        self.assertEqual(maximum, 1)
        for index in range(5):
            self.assertEqual((TEST_ROOT / f"parallel-{index}.mp3").read_bytes(), b"data")

    def test_concurrent_token_requests_reuse_one_rebuilt_session(self):
        account = {"username": "test", "login": {"session": ""}}
        replacement = Mock()
        start = threading.Barrier(5)
        results = []
        errors = []

        def rebuild(target):
            # Model the actual reinitializer's lock and slow connection setup.
            with spotify._session_reinit_lock:
                time.sleep(0.05)
                target["login"]["session"] = replacement

        def get_token():
            try:
                start.wait(timeout=5)
                results.append(spotify.spotify_get_token(0))
            except Exception as exc:
                errors.append(exc)

        with (
            patch.object(spotify, "account_pool", [account]),
            patch.object(spotify, "spotify_re_init_session", side_effect=rebuild) as reinit,
        ):
            threads = [threading.Thread(target=get_token) for _ in range(5)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=10)
            self.assertTrue(all(not thread.is_alive() for thread in threads))
            self.assertEqual(errors, [])
            self.assertEqual(results, [replacement] * 5)
            reinit.assert_called_once_with(account)

    def test_closed_session_reports_retryable_error(self):
        token = Mock()
        token.client.return_value = None
        with self.assertRaisesRegex(RuntimeError, "session was closed"):
            bound_spotify_requests(token)


if __name__ == "__main__":
    unittest.main()
