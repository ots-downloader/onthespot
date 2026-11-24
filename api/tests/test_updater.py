import unittest
from unittest.mock import MagicMock, patch

import requests
from _support import TEST_ROOT  # noqa: F401

from onthespot import updater
from onthespot.updater import (
    AUTO_CHECK_INTERVAL_SECONDS,
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
        self.get, self.notify, _ = (p.start() for p in patches)
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

        self.assertEqual(check_for_updates(), status)
        self.get.assert_called_once()

    def test_forced_checks_within_a_minute_reuse_the_stored_status(self):
        first = check_for_updates(force=True)
        second = check_for_updates(force=True)
        self.get.assert_called_once()
        self.assertEqual(first, second)

        self._allow_next_check()
        check_for_updates(force=True)
        self.assertEqual(self.get.call_count, 2)

    def test_network_failure_returns_an_error_status(self):
        self.get.side_effect = requests.ConnectionError("offline")
        status = check_for_updates(force=True)
        self.assertTrue(status["error"])
        self.assertFalse(status["update_available"])
        self.assertIsNotNone(status["checked_at"])
        self.assertEqual(check_for_updates()["error"], status["error"])

    def test_rate_limit_is_named_in_the_error(self):
        for code in (403, 429):
            with self.subTest(code=code):
                updater._last_attempt = None
                self.get.return_value = _response(code, {"message": "API rate limit exceeded"})
                self.assertIn("rate limit", check_for_updates(force=True)["error"])

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


if __name__ == "__main__":
    unittest.main()
