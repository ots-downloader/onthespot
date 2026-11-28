import unittest
from unittest.mock import patch

from _support import TEST_ROOT  # noqa: F401

from fastapi.testclient import TestClient  # noqa: E402
from onthespot.basemodels import AppSettings  # noqa: E402
from onthespot.main import app  # noqa: E402


class ThemeSettingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def test_default_follows_the_system(self):
        self.assertEqual(AppSettings().theme, "system")

    def test_each_appearance_is_accepted(self):
        for value in ("system", "dark", "light"):
            with self.subTest(value=value), patch("onthespot.main.config.set") as config_set:
                config_set.return_value = True
                response = self.client.patch("/config/set", json={"theme": value})

                self.assertEqual(response.status_code, 200)
                config_set.assert_called_once_with("theme", value)

    def test_an_unknown_appearance_is_refused_and_not_stored(self):
        with patch("onthespot.main.config.set") as config_set:
            response = self.client.patch("/config/set", json={"theme": "blue"})

        self.assertEqual(response.status_code, 422)
        config_set.assert_not_called()


if __name__ == "__main__":
    unittest.main()
