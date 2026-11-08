import os
import threading
import unittest
from unittest.mock import MagicMock, patch

from _support import TEST_ROOT  # noqa: F401

# main.py sets this before it imports librespot; set it here for a direct import.
os.environ.setdefault("PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION", "python")

from onthespot import accounts, runtimedata
from onthespot.api import spotify


def _account(session):
    return {"uuid": "test-account", "login": {"session": session}, "status": "error"}


class SpotifyReInitSessionTests(unittest.TestCase):
    def setUp(self):
        patcher = patch("onthespot.api.spotify.Session")
        self.session_cls = patcher.start()
        self.addCleanup(patcher.stop)
        self.built = self.session_cls.Builder.return_value.stored_file.return_value.create.return_value
        self.built.get_user_attribute.return_value = "premium"

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

    def test_free_rebuild_is_rejected_and_not_stored(self):
        self.built.get_user_attribute.return_value = "free"
        dead = MagicMock(name="dead")
        account = _account(dead)
        account.update(status="active", account_type="premium", bitrate="320k")

        spotify.spotify_re_init_session(account, dead_session=dead)

        self.session_cls.Builder.assert_called_once()
        self.assertIsNot(account["login"]["session"], self.built)
        self.assertNotIn("session_path", account["login"])
        self.built.close.assert_called_once_with()
        self.assertEqual(account["status"], "error")
        self.assertEqual(account["account_type"], "free")
        self.assertEqual(account["bitrate"], "N/A")
        self.assertEqual(account["rejected"], "not_premium")

    def test_unknown_type_rebuild_is_rejected_and_marked(self):
        self.built.get_user_attribute.return_value = "family_mystery"
        account = _account("")

        spotify.spotify_re_init_session(account)

        self.assertEqual(account["login"]["session"], "")
        self.built.close.assert_called_once_with()
        self.assertEqual(account["status"], "error")
        self.assertEqual(account["account_type"], "family_mystery")
        self.assertEqual(account["rejected"], "not_premium")

    def test_account_rejected_while_waiting_for_the_lock_is_not_rebuilt(self):
        # Another worker rejected the account while this one waited.
        for marker in ({"rejected": "not_premium"}, {"retry_after": float("inf")}):
            with self.subTest(marker=marker):
                account = _account("")
                account.update(marker)

                spotify.spotify_re_init_session(account)

                self.session_cls.Builder.assert_not_called()
                self.assertEqual(account["login"]["session"], "")

    def test_late_type_within_wait_is_accepted(self):
        self.built.get_user_attribute.side_effect = [None, None, "premium"]
        account = _account("")

        with patch("onthespot.api.spotify.time.sleep"):
            spotify.spotify_re_init_session(account)

        self.assertIs(account["login"]["session"], self.built)
        self.assertEqual(account["status"], "active")
        self.built.close.assert_not_called()


class SpotifyGetTokenTests(unittest.TestCase):
    def setUp(self):
        patcher = patch("onthespot.api.spotify.Session")
        self.session_cls = patcher.start()
        self.addCleanup(patcher.stop)
        self.create = self.session_cls.Builder.return_value.stored_file.return_value.create
        self.built = self.create.return_value

        # Use the shared pool so get_account_token sees the same accounts.
        saved = list(runtimedata.account_pool)
        self.addCleanup(runtimedata.account_pool.__setitem__, slice(None), saved)
        self.account = _account("")
        self.account.update(service="spotify", username="someuser")
        runtimedata.account_pool[:] = [self.account]

    def test_free_account_is_skipped_without_a_handshake(self):
        self.built.get_user_attribute.return_value = "free"

        self.assertIs(spotify.spotify_get_token(0), False)
        self.assertEqual(self.account["rejected"], "not_premium")
        self.assertIs(accounts.get_account_token("spotify"), False)
        self.assertIs(spotify.spotify_get_token(0), False)

        self.create.assert_called_once_with()

    def test_unknown_type_is_rejected_without_another_handshake(self):
        self.built.get_user_attribute.return_value = "family_mystery"

        self.assertIs(spotify.spotify_get_token(0), False)
        self.assertEqual(self.account["rejected"], "not_premium")
        self.assertIs(spotify.spotify_get_token(0), False)

        self.create.assert_called_once_with()

    def test_missing_type_waits_out_the_cooldown_before_a_retry(self):
        self.built.get_user_attribute.return_value = None
        delay = spotify._MISSING_TYPE_RETRY_DELAY

        with (
            patch("onthespot.api.spotify._ACCOUNT_TYPE_WAIT", 0),
            patch("onthespot.api.spotify.time.monotonic", return_value=1000.0) as now,
        ):
            self.assertIs(spotify.spotify_get_token(0), False)
            self.assertEqual(self.account["status"], "error")
            self.assertNotIn("rejected", self.account)

            now.return_value = 1000.0 + delay - 1
            self.assertIs(accounts.get_account_token("spotify"), False)
            self.assertEqual(self.create.call_count, 1)

            now.return_value = 1000.0 + delay
            self.built.get_user_attribute.return_value = "premium"
            self.assertIs(accounts.get_account_token("spotify"), self.built)

        self.assertEqual(self.account["status"], "active")
        self.assertNotIn("retry_after", self.account)
        self.assertEqual(self.create.call_count, 2)

    def test_failed_reinit_returns_false(self):
        self.create.side_effect = OSError("network down")

        self.assertIs(spotify.spotify_get_token(0), False)
        self.assertIs(accounts.get_account_token("spotify"), False)

    def test_timed_out_reinit_returns_false(self):
        release = threading.Event()
        self.addCleanup(release.set)
        self.create.side_effect = lambda: release.wait(5)

        with patch("onthespot.api.spotify._SESSION_REINIT_TIMEOUT", 0):
            self.assertIs(spotify.spotify_get_token(0), False)

    def test_premium_account_returns_its_session(self):
        self.built.get_user_attribute.return_value = "premium"

        self.assertIs(spotify.spotify_get_token(0), self.built)
        self.assertIs(spotify.spotify_get_token(0), self.built)

        self.create.assert_called_once_with()


class AccountPoolSkipsRejectedTests(unittest.TestCase):
    def setUp(self):
        patcher = patch("onthespot.api.spotify.Session")
        self.session_cls = patcher.start()
        self.addCleanup(patcher.stop)
        self.create = self.session_cls.Builder.return_value.stored_file.return_value.create
        self.built = self.create.return_value

        values = {"active_account_number": 0, "rotate_active_account_number": False}
        config_patcher = patch.object(accounts, "config")
        self.config = config_patcher.start()
        self.addCleanup(config_patcher.stop)
        self.config.get.side_effect = lambda key, default=None: values.get(key, default)

        saved = list(runtimedata.account_pool)
        self.addCleanup(runtimedata.account_pool.__setitem__, slice(None), saved)
        self.live = MagicMock(name="premium")
        self.premium = _account(self.live)
        self.premium.update(service="spotify", username="premiumuser", status="active")

    def test_rejected_current_account_is_skipped_for_a_premium_one(self):
        free = _account("")
        free.update(service="spotify", username="freeuser", rejected="not_premium")
        runtimedata.account_pool[:] = [free, self.premium]

        self.assertIs(accounts.get_account_token("spotify"), self.live)

        self.create.assert_not_called()

    def test_account_rejected_on_use_falls_back_to_a_premium_one(self):
        # Premium lapsed: the re-init finds a free account and rejects it.
        self.built.get_user_attribute.return_value = "free"
        lapsed = _account("")
        lapsed.update(service="spotify", username="lapseduser")
        runtimedata.account_pool[:] = [lapsed, self.premium]

        self.assertIs(accounts.get_account_token("spotify"), self.live)
        self.assertEqual(lapsed["rejected"], "not_premium")
        self.assertIs(accounts.get_account_token("spotify"), self.live)

        self.create.assert_called_once_with()

    def test_cooling_down_account_is_skipped_for_a_premium_one(self):
        cooling = _account("")
        cooling.update(service="spotify", username="slowuser", retry_after=float("inf"))
        other = _account(MagicMock(name="other"))
        other.update(service="spotify", username="otheruser", status="active")

        for pool, rotate, expected in (
            ([cooling, self.premium], False, self.live),
            ([other, cooling, self.premium], True, self.live),
        ):
            with self.subTest(rotate=rotate):
                runtimedata.account_pool[:] = pool
                self.assertIs(accounts.get_account_token("spotify", rotate=rotate), expected)

        self.create.assert_not_called()

    def test_account_with_no_type_on_use_falls_back_to_a_premium_one(self):
        self.built.get_user_attribute.return_value = None
        slow = _account("")
        slow.update(service="spotify", username="slowuser")
        runtimedata.account_pool[:] = [slow, self.premium]

        with patch("onthespot.api.spotify._ACCOUNT_TYPE_WAIT", 0):
            self.assertIs(accounts.get_account_token("spotify"), self.live)
            self.assertIn("retry_after", slow)
            self.assertIs(accounts.get_account_token("spotify"), self.live)

        self.create.assert_called_once_with()

    def test_only_rejected_accounts_give_no_token(self):
        free = _account("")
        free.update(service="spotify", username="freeuser", rejected="not_premium")
        runtimedata.account_pool[:] = [free]

        self.assertIs(accounts.get_account_token("spotify"), False)
        self.assertIs(accounts.get_account_token("spotify", rotate=True), False)

        self.create.assert_not_called()


if __name__ == "__main__":
    unittest.main()
