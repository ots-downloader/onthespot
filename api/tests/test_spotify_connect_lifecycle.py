import logging
import socket
import threading
import unittest

from _support import TEST_ROOT  # noqa: F401

from librespot.zeroconf import ZeroconfServer  # noqa: E402
from onthespot.api.spotify import (  # noqa: E402
    MirrorSpotifyPlayback,
    _patch_librespot_zeroconf_runner,
)


class _FakeZeroconfServer:
    logger = logging.getLogger("test.spotify-connect")


class SpotifyConnectLifecycleTests(unittest.TestCase):
    def test_playback_mirror_starts_and_stops_without_leaking_a_thread(self):
        worker = MirrorSpotifyPlayback()
        worker.start()
        thread = worker.thread

        self.assertIsNotNone(thread)
        self.assertTrue(thread.is_alive())

        worker.stop(timeout=1)

        self.assertFalse(thread.is_alive())
        self.assertIsNone(worker.thread)
        self.assertFalse(worker.is_running)

    def test_http_runner_close_stops_thread_and_releases_port(self):
        self.assertTrue(_patch_librespot_zeroconf_runner())
        runner = ZeroconfServer.HttpRunner(_FakeZeroconfServer(), 0)
        port = runner._HttpRunner__socket.getsockname()[1]
        thread = threading.Thread(target=runner.run, name="test-spotify-connect")
        thread.start()

        runner.close()
        thread.join(timeout=2)

        self.assertFalse(thread.is_alive())
        replacement = socket.socket()
        try:
            replacement.bind(("0.0.0.0", port))
        finally:
            replacement.close()

    def test_http_runner_close_is_idempotent(self):
        self.assertTrue(_patch_librespot_zeroconf_runner())
        runner = ZeroconfServer.HttpRunner(_FakeZeroconfServer(), 0)
        runner.close()
        runner.close()


if __name__ == "__main__":
    unittest.main()
