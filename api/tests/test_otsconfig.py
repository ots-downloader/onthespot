import json
import os
import unittest
from pathlib import Path
from unittest.mock import patch

from _support import TEST_ROOT

from onthespot import otsconfig  # noqa: E402
from onthespot.otsconfig import Config, cache_dir, config_dir  # noqa: E402


DEFAULT_CONFIG = json.loads(
    Path(otsconfig.__file__)
    .with_name("otsconfig_default.json")
    .read_text(encoding="utf-8")
)


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


class ConfigCoercionTests(unittest.TestCase):
    def setUp(self):
        with patch.dict(
            os.environ,
            {
                "ONTHESPOTDIR": str(TEST_ROOT / "coercion-config"),
                "ONTHESPOTCACHEDIR": str(TEST_ROOT / "coercion-cache"),
            },
        ):
            self.config = Config()

    def test_numeric_text_is_stored_as_a_whole_number(self):
        self.assertEqual(self.config.set("download_chunk_size", "50000"), 50000)
        self.assertIsInstance(self.config.get("download_chunk_size"), int)

    def test_boolean_keys_accept_text_and_real_booleans(self):
        self.assertIs(self.config.set("debug_mode", "false"), False)
        self.assertIs(self.config.set("debug_mode", "True"), True)
        self.assertIs(self.config.set("debug_mode", True), True)

    def test_text_key_keeps_a_value_that_reads_as_a_boolean(self):
        self.assertEqual(self.config.set("search_prefix", "true"), "true")
        self.assertEqual(self.config.get("search_prefix"), "true")

    def test_values_of_the_wrong_type_are_rejected(self):
        with self.assertRaises(ValueError):
            self.config.set("search_prefix", 123)
        with self.assertRaises(ValueError):
            self.config.set("download_chunk_size", True)
        with self.assertRaises(ValueError):
            self.config.set("download_chunk_size", "abc")

    def test_list_key_takes_json_text_that_holds_a_list(self):
        self.assertEqual(
            self.config.set("ffmpeg_args", '["-hide_banner"]'), ["-hide_banner"]
        )
        with self.assertRaises(ValueError):
            self.config.set("ffmpeg_args", '{"loglevel": "quiet"}')

    def test_keys_outside_the_template_are_stored_as_they_arrive(self):
        self.assertEqual(self.config.set("release_readiness_probe", "saved"), "saved")
        self.assertEqual(self.config.get("release_readiness_probe"), "saved")
        self.assertEqual(self.config.set("_cache_dir", "/cache"), "/cache")

    def test_corrupt_config_file_is_healed_on_load(self):
        config_root = TEST_ROOT / "healing-config"
        config_root.mkdir(parents=True, exist_ok=True)
        (config_root / "otsconfig.json").write_text(
            json.dumps(
                {
                    "audio_download_path": str(TEST_ROOT / "healing-audio"),
                    "video_download_path": str(TEST_ROOT / "healing-video"),
                    "download_chunk_size": "50000",
                    "debug_mode": "false",
                    "search_prefix": True,
                    "download_delay": "garbage",
                    "download_profiles": "not-json",
                }
            ),
            encoding="utf-8",
        )
        with patch.dict(
            os.environ,
            {
                "ONTHESPOTDIR": str(config_root),
                "ONTHESPOTCACHEDIR": str(TEST_ROOT / "healing-cache"),
            },
        ):
            instance = Config()

        self.assertEqual(instance.get("download_chunk_size"), 50000)
        self.assertIs(instance.get("debug_mode"), False)
        # A boolean in a text slot keeps the user's choice as text.
        self.assertEqual(instance.get("search_prefix"), "true")
        self.assertEqual(instance.get("download_delay"), DEFAULT_CONFIG["download_delay"])

        healed_profiles = instance.get("download_profiles")
        self.assertEqual(healed_profiles, DEFAULT_CONFIG["download_profiles"])
        self.assertIsNot(
            healed_profiles[0],
            instance._Config__template_data["download_profiles"][0],
        )


if __name__ == "__main__":
    unittest.main()
