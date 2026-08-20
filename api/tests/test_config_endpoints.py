import copy
import unittest

from _support import TEST_ROOT  # noqa: F401

from fastapi.testclient import TestClient  # noqa: E402
from onthespot.main import app, config  # noqa: E402


# Keys any test in this file writes. The configuration singleton is shared by
# the whole suite and ``/config/import`` saves it, so each test restores both
# the in-memory value and the file.
TOUCHED_KEYS = (
    "download_chunk_size",
    "download_delay",
    "debug_mode",
    "search_prefix",
    "accounts",
    "spotify_webapi_override_client_secret",
)


class ConfigEndpointTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def setUp(self):
        self.snapshot = {
            key: copy.deepcopy(config.get(key)) for key in TOUCHED_KEYS
        }

    def tearDown(self):
        for key, value in self.snapshot.items():
            config.set(key, value)
        config.save()

    def test_numeric_setting_is_stored_and_returned_as_a_number(self):
        response = self.client.post(
            "/config/set?nkey=download_chunk_size&nvalue=50000"
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), 50000)
        self.assertEqual(config.get("download_chunk_size"), 50000)

    def test_boolean_setting_is_stored_as_a_boolean(self):
        response = self.client.post("/config/set?nkey=debug_mode&nvalue=false")

        self.assertEqual(response.status_code, 200)
        self.assertIs(response.json(), False)
        self.assertIs(config.get("debug_mode"), False)

    def test_text_setting_keeps_a_value_that_reads_as_a_boolean(self):
        response = self.client.post("/config/set?nkey=search_prefix&nvalue=true")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), "true")
        self.assertEqual(config.get("search_prefix"), "true")

    def test_value_of_the_wrong_type_is_refused_and_changes_nothing(self):
        config.set("download_chunk_size", 4096)

        response = self.client.post(
            "/config/set?nkey=download_chunk_size&nvalue=abc"
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(config.get("download_chunk_size"), 4096)

    def test_key_outside_the_template_is_still_stored_as_it_arrives(self):
        response = self.client.post(
            "/config/set?nkey=release_readiness_probe&nvalue=probe"
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), "probe")
        self.assertEqual(config.get("release_readiness_probe"), "probe")

    def test_import_converts_values_to_the_type_of_the_key(self):
        response = self.client.post(
            "/config/import", json={"download_chunk_size": "123"}
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(config.get("download_chunk_size"), 123)

    def test_import_applies_nothing_when_one_value_is_invalid(self):
        config.set("download_chunk_size", 4096)
        config.set("download_delay", 7)

        response = self.client.post(
            "/config/import",
            json={"download_chunk_size": "123", "download_delay": "garbage"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(config.get("download_chunk_size"), 4096)
        self.assertEqual(config.get("download_delay"), 7)

    def test_import_refuses_an_unhashable_secret_value(self):
        config.set("spotify_webapi_override_client_secret", "keep-me")

        response = self.client.post(
            "/config/import", json={"spotify_webapi_override_client_secret": ["x"]}
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            config.get("spotify_webapi_override_client_secret"), "keep-me"
        )

    def test_import_never_writes_accounts(self):
        original = copy.deepcopy(config.get("accounts"))

        self.client.post(
            "/config/import",
            json={
                "accounts": '[{"uuid": "injected", "service": "spotify", "active": true}]'
            },
        )

        self.assertEqual(config.get("accounts"), original)


if __name__ == "__main__":
    unittest.main()
