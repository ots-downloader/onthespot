import json
import os
import unittest
from pathlib import Path
from unittest.mock import patch

from _support import TEST_ROOT

from onthespot.otsconfig import Config, cache_dir, config_dir  # noqa: E402


class ConfigPathTests(unittest.TestCase):
    def test_nonexistent_config_override_is_honoured(self):
        override = TEST_ROOT / "new-config-root"
        self.assertFalse(override.exists())
        with patch.dict(os.environ, {"ONTHESPOTDIR": str(override)}):
            self.assertEqual(Path(config_dir()), override.resolve())

    def test_cache_override_is_honoured(self):
        override = TEST_ROOT / "new-cache-root"
        with patch.dict(os.environ, {"ONTHESPOTCACHEDIR": str(override)}):
            self.assertEqual(Path(cache_dir()), override.resolve())

    def test_config_saves_inside_configured_app_data(self):
        config_root = TEST_ROOT / "isolated-config"
        cache_root = TEST_ROOT / "isolated-cache"
        with patch.dict(
            os.environ,
            {
                "ONTHESPOTDIR": str(config_root),
                "ONTHESPOTCACHEDIR": str(cache_root),
            },
        ):
            instance = Config()
            instance.set("release_readiness_probe", "saved")
            instance.save()

        config_file = config_root / "otsconfig.json"
        self.assertTrue(config_file.is_file())
        self.assertEqual(json.loads(config_file.read_text(encoding="utf-8"))["release_readiness_probe"], "saved")
        self.assertTrue(cache_root.is_dir())

    def test_public_snapshot_is_flat_detached_and_redacts_secrets(self):
        config_root = TEST_ROOT / "public-snapshot-config"
        cache_root = TEST_ROOT / "public-snapshot-cache"
        with patch.dict(
            os.environ,
            {
                "ONTHESPOTDIR": str(config_root),
                "ONTHESPOTCACHEDIR": str(cache_root),
            },
        ):
            instance = Config()
            instance.set("spotify_webapi_override_client_secret", "do-not-expose")
            instance.set(
                "accounts",
                [
                    {
                        "uuid": "worker-1",
                        "service": "spotify",
                        "active": True,
                        "login": {"credentials": "also-secret"},
                    }
                ],
            )
            snapshot = instance.as_dict()

        self.assertEqual(snapshot["spotify_webapi_override_client_secret"], "")
        self.assertTrue(snapshot["spotify_webapi_override_client_secret_configured"])
        self.assertEqual(
            snapshot["accounts"],
            [{"uuid": "worker-1", "service": "spotify", "active": True}],
        )
        self.assertNotIn("_Config__config", snapshot)
        snapshot["accounts"][0]["service"] = "changed"
        self.assertEqual(instance.get("accounts")[0]["service"], "spotify")


if __name__ == "__main__":
    unittest.main()
