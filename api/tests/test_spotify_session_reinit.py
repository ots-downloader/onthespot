import os
import unittest
from unittest.mock import MagicMock, patch

from _support import TEST_ROOT  # noqa: F401

# main.py sets this before it imports librespot; set it here for a direct import.
os.environ.setdefault("PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION", "python")

from onthespot.api import spotify


def _account(session):
    return {"uuid": "test-account", "login": {"session": session}, "status": "error"}


class SpotifyReInitSessionTests(unittest.TestCase):
    def setUp(self):
        patcher = patch("onthespot.api.spotify.Session")
        self.session_cls = patcher.start()
        self.addCleanup(patcher.stop)
        self.built = self.session_cls.Builder.return_value.stored_file.return_value.create.return_value

    def test_empty_slot_is_rebuilt(self):
        account = _account("")

        spotify.spotify_re_init_session(account)

        self.assertIs(account["login"]["session"], self.built)
        self.assertEqual(account["status"], "active")

    def test_live_session_is_kept_when_no_dead_session_is_named(self):
        live = MagicMock(name="live")
        account = _account(live)

        spotify.spotify_re_init_session(account)

        self.assertIs(account["login"]["session"], live)
        live.close.assert_not_called()
        self.session_cls.Builder.assert_not_called()

    def test_named_dead_session_is_replaced(self):
        dead = MagicMock(name="dead")
        account = _account(dead)

        spotify.spotify_re_init_session(account, dead_session=dead)

        dead.close.assert_called_once_with()
        self.assertIs(account["login"]["session"], self.built)

    def test_named_dead_session_already_replaced_is_left_alone(self):
        dead = MagicMock(name="dead")
        fresh = MagicMock(name="fresh")
        account = _account(fresh)

        spotify.spotify_re_init_session(account, dead_session=dead)

        self.assertIs(account["login"]["session"], fresh)
        fresh.close.assert_not_called()
        self.session_cls.Builder.assert_not_called()


if __name__ == "__main__":
    unittest.main()
