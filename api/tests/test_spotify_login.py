import os
import unittest
from unittest.mock import patch

from _support import TEST_ROOT  # noqa: F401

# main.py sets this before it imports librespot; set it here for a direct import.
os.environ.setdefault("PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION", "python")

from onthespot.api import spotify


def _account():
    return {"uuid": "test-login", "login": {"username": "someuser", "credentials": "x"}}


class SpotifyLoginUserTests(unittest.TestCase):
    def setUp(self):
        session_patcher = patch("onthespot.api.spotify.Session")
        self.session_cls = session_patcher.start()
        self.addCleanup(session_patcher.stop)
        self.create = self.session_cls.Builder.return_value.stored_file.return_value.create
        self.built = self.create.return_value

        pool_patcher = patch("onthespot.api.spotify.account_pool", new=[])
        self.pool = pool_patcher.start()
        self.addCleanup(pool_patcher.stop)

    def assertRejected(self, shown_type):
        self.assertFalse(spotify.spotify_login_user(_account()))

        self.assertEqual(len(self.pool), 1)
        entry = self.pool[0]
        self.assertEqual(entry["status"], "error")
        self.assertEqual(entry["account_type"], shown_type)
        self.assertEqual(entry["bitrate"], "N/A")
        self.assertEqual(entry["login"]["session"], "")
        self.built.close.assert_called_once_with()
        return entry

    def test_free_account_is_rejected(self):
        for account_type in ("free", "open"):
            with self.subTest(account_type=account_type):
                self.pool.clear()
                self.built.reset_mock()
                self.built.get_user_attribute.return_value = account_type

                entry = self.assertRejected(account_type)

                self.assertEqual(entry["rejected"], "not_premium")

    def test_free_account_is_not_retried_on_next_token_request(self):
        self.built.get_user_attribute.return_value = "free"
        spotify.spotify_login_user(_account())
        self.create.reset_mock()

        self.assertIs(spotify.spotify_get_token(0), False)
        self.assertIs(spotify.spotify_get_token(0), False)

        self.create.assert_not_called()

    def test_unknown_account_type_is_rejected_and_not_retried(self):
        self.built.get_user_attribute.return_value = "family_mystery"

        entry = self.assertRejected("family_mystery")

        self.assertEqual(entry["rejected"], "not_premium")
        self.create.reset_mock()
        self.assertIs(spotify.spotify_get_token(0), False)
        self.create.assert_not_called()

    def test_missing_account_type_is_retried_only_after_the_cooldown(self):
        self.built.get_user_attribute.return_value = None
        delay = spotify._MISSING_TYPE_RETRY_DELAY

        with (
            patch("onthespot.api.spotify._ACCOUNT_TYPE_WAIT", 0),
            patch("onthespot.api.spotify.time.monotonic", return_value=1000.0) as now,
        ):
            entry = self.assertRejected("N/A")
            self.assertNotIn("rejected", entry)
            self.assertEqual(entry["retry_after"], 1000.0 + delay)
            self.create.reset_mock()

            # Within the cooldown: no handshake.
            now.return_value = 1000.0 + delay - 1
            self.assertIs(spotify.spotify_get_token(0), False)
            self.create.assert_not_called()

            # After it the account is tried again and the type has arrived.
            now.return_value = 1000.0 + delay
            self.built.get_user_attribute.return_value = "premium"
            self.assertIs(spotify.spotify_get_token(0), self.built)

        self.create.assert_called_once_with()
        self.assertEqual(entry["status"], "active")
        self.assertEqual(entry["bitrate"], "320k")
        self.assertNotIn("retry_after", entry)

    def test_premium_account_is_active_at_320k(self):
        self.built.get_user_attribute.return_value = "premium"

        self.assertTrue(spotify.spotify_login_user(_account()))

        self.assertEqual(len(self.pool), 1)
        entry = self.pool[0]
        self.assertEqual(entry["status"], "active")
        self.assertEqual(entry["account_type"], "premium")
        self.assertEqual(entry["bitrate"], "320k")
        self.assertIs(entry["login"]["session"], self.built)
        self.assertNotIn("rejected", entry)
        self.built.close.assert_not_called()

    def test_late_account_type_is_waited_for(self):
        # librespot can return from authenticate() before the product-info packet.
        self.built.get_user_attribute.side_effect = [None, None, "premium"]

        with patch("onthespot.api.spotify.time.sleep"):
            self.assertTrue(spotify.spotify_login_user(_account()))

        self.assertEqual(self.pool[0]["status"], "active")
        self.assertIs(self.pool[0]["login"]["session"], self.built)
        self.built.close.assert_not_called()


if __name__ == "__main__":
    unittest.main()
