import unittest

from _support import TEST_ROOT  # noqa: F401

from onthespot.updater import _normalise_release, is_development_build

LATEST = {"tag_name": "v2.0.5", "name": "v2.0.5", "assets": []}


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

    def test_source_run_without_version_tags_never_reports_an_update(self):
        status = _normalise_release(LATEST, "dev-abc1234")
        self.assertFalse(status["update_available"])
        self.assertTrue(status["development_build"])


if __name__ == "__main__":
    unittest.main()
