import threading
import unittest
from unittest.mock import MagicMock, patch

import requests
from _support import TEST_ROOT  # noqa: F401

from onthespot import updater
from onthespot.updater import (
    AUTO_CHECK_INTERVAL_SECONDS,
    AUTO_RETRY_AFTER_FAILURE_SECONDS,
    MIN_CHECK_INTERVAL_SECONDS,
    _normalise_release,
    check_for_updates,
    is_development_build,
    should_check_now,
)

LATEST = {"tag_name": "v2.0.5", "name": "v2.0.5"}


def _response(status_code=200, payload=None):
    response = MagicMock(status_code=status_code)
    response.json.return_value = LATEST if payload is None else payload
    return response


class UpdaterVersionTests(unittest.TestCase):
    def test_development_builds_are_recognised(self):
        for version in ("dev", "", None, "dev-abc1234"):
            self.assertTrue(is_development_build(version), version)
        # Any other version is checked, even in an unusual format.
        for version in ("v2.0.5", "2.0.5", "v2.0.2 Beta 4", "V2.0.2beta4", "release-2.0.6", "v2.0.5-4-g14eda2c"):
            self.assertFalse(is_development_build(version), version)

    def test_older_release_reports_an_update(self):
        status = _normalise_release(LATEST, "v2.0.4")
        self.assertTrue(status["update_available"])
        self.assertFalse(status["development_build"])

    def test_current_release_reports_no_update(self):
        status = _normalise_release(LATEST, "v2.0.5")
        self.assertFalse(status["update_available"])
        self.assertFalse(status["development_build"])

    def test_edge_build_reports_only_a_newer_release(self):
        # An edge build is ahead of the tag it describes, behind the next one.
        self.assertFalse(_normalise_release(LATEST, "v2.0.5-4-g14eda2c")["update_available"])
        self.assertTrue(_normalise_release(LATEST, "v2.0.4-12-gabc1234")["update_available"])

    def test_development_build_never_reports_an_update(self):
        status = _normalise_release(LATEST, "dev")
        self.assertFalse(status["update_available"])
        self.assertTrue(status["development_build"])
        self.assertEqual(status["latest_version"], "v2.0.5")


class UpdateCheckTests(unittest.TestCase):
    def setUp(self):
        updater._status = None
        updater._last_attempt = None
        updater._notified_versions.clear()
        patches = (
            patch("onthespot.updater.requests.get"),
            patch("onthespot.updater.notification_hook"),
            patch("onthespot.updater._current_version", return_value="v2.0.4"),
        )
        self.get, self.notify, self.version = (p.start() for p in patches)
        for p in patches:
            self.addCleanup(p.stop)
        self.get.return_value = _response()

    def _allow_next_check(self):
        updater._last_attempt -= MIN_CHECK_INTERVAL_SECONDS + 1

    def test_read_before_any_check_makes_no_request(self):
        status = check_for_updates()
        self.get.assert_not_called()
        self.assertIsNone(status["checked_at"])
        self.assertFalse(status["update_available"])
        self.assertEqual(status["latest_version"], "")
        self.assertEqual(status["error"], "")
        self.assertEqual(status["repository"], "ots-downloader/onthespot")

    def test_forced_check_asks_github_and_a_read_returns_the_result(self):
        status = check_for_updates(force=True)
        self.get.assert_called_once()
        self.assertTrue(status["update_available"])
        self.assertEqual(status["latest_version"], "v2.0.5")
        self.assertIsNotNone(status["checked_at"])
        self.assertNotIn("assets", status)
        self.assertNotIn("reused_recent_check", status)

        self.assertEqual(check_for_updates(), status)
        self.get.assert_called_once()

    def test_forced_checks_within_a_minute_reuse_the_stored_status(self):
        first = check_for_updates(force=True)
        second = check_for_updates(force=True)
        self.get.assert_called_once()
        # Only the reused copy is marked; the stored status and reads are not.
        self.assertIs(second.pop("reused_recent_check"), True)
        self.assertEqual(first, second)
        self.assertNotIn("reused_recent_check", check_for_updates())

        self._allow_next_check()
        check_for_updates(force=True)
        self.assertEqual(self.get.call_count, 2)

    def test_forced_check_on_a_development_build_reports_the_latest_release(self):
        self.version.return_value = "dev"
        status = check_for_updates(force=True)
        self.get.assert_called_once()
        self.assertTrue(status["development_build"])
        self.assertFalse(status["update_available"])
        self.assertEqual(status["latest_version"], "v2.0.5")
        self.notify.assert_not_called()

    def test_network_failure_returns_an_error_status(self):
        self.get.side_effect = requests.ConnectionError("offline")
        status = check_for_updates(force=True)
        self.assertTrue(status["error"])
        self.assertFalse(status["update_available"])
        self.assertIsNotNone(status["checked_at"])
        self.assertEqual(check_for_updates()["error"], status["error"])

    def test_rate_limit_is_named_in_the_error(self):
        self.get.return_value = _response(429, {"message": "API rate limit exceeded"})
        self.assertEqual(check_for_updates(force=True)["error"], "GitHub rate limit reached. Try again later.")

    def test_forbidden_names_both_causes(self):
        # GitHub sends 403 for a rate limit and for a refused token alike.
        self.get.return_value = _response(403, {"message": "Bad credentials"})
        error = check_for_updates(force=True)["error"]
        self.assertIn("refused", error)
        self.assertIn("rate limit or token", error)

    def test_other_http_errors_return_an_error_status(self):
        self.get.return_value = _response(500, {})
        status = check_for_updates(force=True)
        self.assertIn("500", status["error"])
        self.assertFalse(status["update_available"])

    def test_payload_that_is_not_a_release_returns_an_error_status(self):
        for payload in ({"message": "Not Found"}, [], {"name": "no tag"}):
            with self.subTest(payload=payload):
                updater._last_attempt = None
                self.get.return_value = _response(200, payload)
                status = check_for_updates(force=True)
                self.assertTrue(status["error"])
                self.assertEqual(status["latest_version"], "")

    def test_failed_check_keeps_a_known_update(self):
        good = check_for_updates(force=True)
        self._allow_next_check()
        self.get.side_effect = requests.Timeout("slow")
        failed = check_for_updates(force=True)
        self.assertTrue(failed["error"])
        self.assertTrue(failed["update_available"])
        self.assertEqual(failed["latest_version"], good["latest_version"])
        self.assertEqual(failed["release_url"], good["release_url"])

    def test_good_check_after_a_failure_clears_the_error(self):
        self.get.side_effect = requests.ConnectionError("offline")
        check_for_updates(force=True)
        self._allow_next_check()
        self.get.side_effect = None
        self.assertEqual(check_for_updates(force=True)["error"], "")

    def test_unexpected_exception_returns_an_error_status(self):
        self.get.side_effect = RuntimeError("unexpected")
        status = check_for_updates(force=True)
        self.assertTrue(status["error"])
        self.assertEqual(check_for_updates()["error"], status["error"])

    def test_failed_check_sends_no_notification(self):
        # Not even when the kept status still says an update is out.
        check_for_updates(force=True)
        self.notify.assert_called_once()
        updater._notified_versions.clear()
        self._allow_next_check()
        self.get.side_effect = requests.Timeout("slow")
        failed = check_for_updates(force=True)
        self.assertTrue(failed["update_available"])
        self.notify.assert_called_once()

    def test_notification_is_sent_once_per_version(self):
        check_for_updates(force=True)
        self._allow_next_check()
        check_for_updates(force=True)
        self.notify.assert_called_once()
        title, message, url = self.notify.call_args.args
        self.assertIn("v2.0.5", message)
        self.assertEqual(url, "#diagnostics")

        self._allow_next_check()
        self.get.return_value = _response(200, {"tag_name": "v2.0.6"})
        check_for_updates(force=True)
        self.assertEqual(self.notify.call_count, 2)

    def test_no_notification_when_up_to_date(self):
        self.get.return_value = _response(200, {"tag_name": "v2.0.4"})
        status = check_for_updates(force=True)
        self.assertFalse(status["update_available"])
        self.notify.assert_not_called()


class BackgroundCheckDecisionTests(unittest.TestCase):
    NOW = 1_000_000.0

    def test_first_wake_checks(self):
        self.assertTrue(should_check_now(self.NOW, None, True, "v2.0.4"))

    def test_setting_off_skips_the_check(self):
        self.assertFalse(should_check_now(self.NOW, None, False, "v2.0.4"))

    def test_development_build_skips_the_check(self):
        for version in ("dev", "dev-abc1234", ""):
            with self.subTest(version=version):
                self.assertFalse(should_check_now(self.NOW, None, True, version))

    def test_recent_attempt_skips_the_check(self):
        last = self.NOW - AUTO_CHECK_INTERVAL_SECONDS + 60
        self.assertFalse(should_check_now(self.NOW, last, True, "v2.0.4"))

    def test_a_day_after_the_last_attempt_checks_again(self):
        last = self.NOW - AUTO_CHECK_INTERVAL_SECONDS
        self.assertTrue(should_check_now(self.NOW, last, True, "v2.0.4"))

    def test_failed_attempt_retries_after_an_hour(self):
        too_soon = self.NOW - AUTO_RETRY_AFTER_FAILURE_SECONDS + 60
        self.assertFalse(should_check_now(self.NOW, too_soon, True, "v2.0.4", last_check_failed=True))
        an_hour_ago = self.NOW - AUTO_RETRY_AFTER_FAILURE_SECONDS
        self.assertTrue(should_check_now(self.NOW, an_hour_ago, True, "v2.0.4", last_check_failed=True))

    def test_good_attempt_still_waits_a_day(self):
        an_hour_ago = self.NOW - AUTO_RETRY_AFTER_FAILURE_SECONDS
        self.assertFalse(should_check_now(self.NOW, an_hour_ago, True, "v2.0.4", last_check_failed=False))

    def test_failed_attempt_still_respects_the_setting_and_development_builds(self):
        long_ago = self.NOW - AUTO_CHECK_INTERVAL_SECONDS
        self.assertFalse(should_check_now(self.NOW, long_ago, False, "v2.0.4", last_check_failed=True))
        self.assertFalse(should_check_now(self.NOW, long_ago, True, "dev", last_check_failed=True))


class BackgroundCheckerThreadTests(unittest.TestCase):
    def setUp(self):
        # The thread wakes, decides not to check, and waits on its stop event,
        # so it makes no request and stops as soon as it is told to.
        decide = patch("onthespot.updater.should_check_now", return_value=False)
        decide.start()
        self.addCleanup(decide.stop)
        self.addCleanup(self._stop_all)

    def _stop_all(self):
        updater.stop_update_checker()
        for thread in self._live_checker_threads():
            thread.join(timeout=5)

    def _live_checker_threads(self):
        return [t for t in threading.enumerate() if t.name == "update-checker" and t.is_alive()]

    def _stop_and_join(self, thread):
        updater.stop_update_checker()
        thread.join(timeout=5)
        self.assertFalse(thread.is_alive())

    def test_starting_twice_keeps_one_thread(self):
        updater.start_update_checker()
        first = updater._update_thread
        updater.start_update_checker()
        self.assertIs(updater._update_thread, first)
        self.assertEqual(self._live_checker_threads(), [first])
        self._stop_and_join(first)

    def test_stop_then_start_runs_a_new_thread(self):
        updater.start_update_checker()
        first = updater._update_thread
        self._stop_and_join(first)

        updater.start_update_checker()
        second = updater._update_thread
        self.assertIsNot(second, first)
        self.assertEqual(self._live_checker_threads(), [second])
        self._stop_and_join(second)


if __name__ == "__main__":
    unittest.main()
