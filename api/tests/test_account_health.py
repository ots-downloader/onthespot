import unittest
from unittest.mock import patch

from _support import TEST_ROOT  # noqa: F401

from fastapi.testclient import TestClient  # noqa: E402
from onthespot.main import app, config  # noqa: E402


class AccountHealthTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # No context manager: these tests need no background workers.
        cls.client = TestClient(app)

    def health(self, pool):
        configured = [{"service": "spotify", "active": True}]
        real_get = config.get
        with (
            patch("onthespot.main.account_pool", new=pool),
            patch.object(
                config, "get", side_effect=lambda key, *args: configured if key == "accounts" else real_get(key, *args)
            ),
            patch("onthespot.main.spotify_connect_status", return_value={}),
        ):
            response = self.client.get("/accounts/health")
        self.assertEqual(response.status_code, 200)
        return response.json()

    def test_rejected_spotify_account_is_not_connected(self):
        rejected = {"service": "spotify", "status": "error", "rejected": "not_premium"}

        payload = self.health([rejected])

        self.assertFalse(payload["spotify"]["connected"])
        self.assertEqual(payload["spotify"]["status"], "Needs reconnect")
        self.assertEqual(payload["missing_services"], ["spotify"])
        self.assertEqual(payload["authenticated_accounts"], 0)
        self.assertFalse(payload["healthy"])

    def test_premium_account_beside_a_rejected_one_is_connected(self):
        rejected = {"service": "spotify", "status": "error", "rejected": "not_premium"}
        premium = {"service": "spotify", "status": "active"}

        payload = self.health([rejected, premium])

        self.assertTrue(payload["spotify"]["connected"])
        self.assertEqual(payload["missing_services"], [])
        self.assertEqual(payload["authenticated_accounts"], 1)
        self.assertTrue(payload["healthy"])


if __name__ == "__main__":
    unittest.main()
