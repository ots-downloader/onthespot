import os
import unittest
from unittest.mock import patch

from _support import TEST_ROOT  # noqa: F401

from onthespot.youtube_auth import (  # noqa: E402
    _normalise_cookie_file,
    managed_youtube_cookie_path,
    store_youtube_cookie_file,
    youtube_auth_status,
)
from onthespot.otsconfig import config  # noqa: E402


class YouTubeCookieTests(unittest.TestCase):
    def test_uploaded_cookie_file_keeps_only_youtube_and_google(self):
        contents = (
            "# Netscape HTTP Cookie File\n"
            ".youtube.com\tTRUE\t/\tTRUE\t2147483647\tSID\tyoutube-secret\n"
            ".example.com\tTRUE\t/\tTRUE\t2147483647\tSID\tother-secret\n"
            "#HttpOnly_.google.com\tTRUE\t/\tTRUE\t2147483647\tHSID\tgoogle-secret\n"
        ).encode()

        filtered = _normalise_cookie_file(contents, youtube_only=True).decode()

        self.assertIn(".youtube.com", filtered)
        self.assertIn("#HttpOnly_.google.com", filtered)
        self.assertNotIn(".example.com", filtered)
        self.assertNotIn("other-secret", filtered)

    def test_invalid_cookie_export_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "Netscape-format"):
            _normalise_cookie_file(b"not a cookie export")

    def test_managed_cookie_file_is_private_app_state(self):
        contents = (
            "# Netscape HTTP Cookie File\n"
            ".youtube.com\tTRUE\t/\tTRUE\t2147483647\tSID\tsecret\n"
        ).encode()

        destination = store_youtube_cookie_file(contents)

        self.assertEqual(destination, managed_youtube_cookie_path())
        self.assertTrue(destination.is_file())
        self.assertTrue(str(destination).startswith(os.environ["ONTHESPOTCACHEDIR"]))

    def test_browser_status_does_not_scan_cookie_database(self):
        original_mode = config.get("youtube_auth_mode")
        original_browser = config.get("youtube_cookies_browser")
        try:
            config.set("youtube_auth_mode", "browser")
            config.set("youtube_cookies_browser", "chrome")
            with patch(
                "onthespot.youtube_auth.validate_youtube_browser",
                side_effect=AssertionError("status must not read browser cookies"),
            ):
                status = youtube_auth_status()
        finally:
            config.set("youtube_auth_mode", original_mode)
            config.set("youtube_cookies_browser", original_browser)

        self.assertTrue(status["configured"])
        self.assertTrue(status["ready"])
        self.assertEqual(status["source"], "Chrome on the OnTheSpot host")


if __name__ == "__main__":
    unittest.main()
