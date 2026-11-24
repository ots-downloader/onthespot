import json
import os
import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch

from _support import TEST_ROOT

from onthespot import otsconfig
from onthespot.basemodels import AppSettings
from onthespot.otsconfig import Config, cache_dir, config_dir  # noqa: E402

DEFAULT_CONFIG = json.loads(
    Path(otsconfig.__file__)
    .with_name("otsconfig_default.json")
    .read_text(encoding="utf-8")
)


class ConfigPathTests(unittest.TestCase):
    def test_automatic_itunes_enrichment_flags_are_removed(self):
        for flag in ("enable_itunes_metadata", "itunes_metadata_overwrite"):
            self.assertNotIn(flag, DEFAULT_CONFIG)
            self.assertNotIn(flag, AppSettings.model_fields)
        self.assertIn("itunes_metadata_country", DEFAULT_CONFIG)
        self.assertIn("itunes_metadata_country", AppSettings.model_fields)

    def test_update_repository_setting_is_removed(self):
        self.assertNotIn("update_repository", DEFAULT_CONFIG)
        self.assertNotIn("update_repository", AppSettings.model_fields)
        self.assertIn("check_for_updates", DEFAULT_CONFIG)

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
            instance.set("search_prefix", "saved")
            instance.save()

        config_file = config_root / "otsconfig.json"
        self.assertTrue(config_file.is_file())
        self.assertEqual(json.loads(config_file.read_text(encoding="utf-8"))["search_prefix"], "saved")
        self.assertTrue(cache_root.is_dir())

    def test_build_version_replaces_the_saved_version(self):
        config_root = TEST_ROOT / "build-version-config"
        config_root.mkdir(parents=True, exist_ok=True)
        (config_root / "otsconfig.json").write_text(json.dumps({"version": "v2.0.2 Beta 4"}), encoding="utf-8")
        env = {"ONTHESPOTDIR": str(config_root), "ONTHESPOTCACHEDIR": str(TEST_ROOT / "build-version-cache")}

        with patch.dict(os.environ, {**env, "ONTHESPOT_VERSION": "v2.0.6"}):
            instance = Config()
            self.assertEqual(instance.get("version"), "v2.0.6")
            instance.reset()
            self.assertEqual(instance.get("version"), "v2.0.6")
        # A checkout would answer with git describe output, so stub git out.
        with patch.object(otsconfig, "_source_version", return_value=None):
            with patch.dict(os.environ, {**env, "ONTHESPOT_VERSION": "  "}):
                self.assertEqual(Config().get("version"), DEFAULT_CONFIG["version"])
            with patch.dict(os.environ, env):
                os.environ.pop("ONTHESPOT_VERSION", None)
                self.assertEqual(Config().get("version"), DEFAULT_CONFIG["version"])

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


class SourceVersionTests(unittest.TestCase):
    def setUp(self):
        # A stand-in checkout, so no test depends on the real one's git state.
        self.checkout = TEST_ROOT / "source-checkout"
        (self.checkout / ".git").mkdir(parents=True, exist_ok=True)
        root = patch.object(otsconfig, "_REPOSITORY_ROOT", str(self.checkout))
        root.start()
        self.addCleanup(root.stop)

    @staticmethod
    def _git_output(stdout):
        return subprocess.CompletedProcess(args=["git"], returncode=0, stdout=stdout, stderr="")

    def test_source_run_reports_git_describe(self):
        with patch.object(otsconfig.subprocess, "run", return_value=self._git_output("v2.0.5-4-g14eda2c\n")) as run:
            self.assertEqual(otsconfig._source_version(), "v2.0.5-4-g14eda2c")
        command = run.call_args.args[0]
        self.assertEqual(command[:4], ["git", "-C", str(self.checkout), "describe"])
        self.assertIn("v[0-9]*", command)
        # Without check=True a failed describe would return "" and skip dev-<sha>.
        self.assertTrue(run.call_args.kwargs["check"])

    def test_clone_without_version_tags_reports_dev_and_the_commit(self):
        no_tags = subprocess.CalledProcessError(128, ["git", "describe"])
        with patch.object(otsconfig.subprocess, "run", side_effect=[no_tags, self._git_output("abc1234\n")]):
            self.assertEqual(otsconfig._source_version(), "dev-abc1234")

    def test_missing_git_or_checkout_reports_no_version(self):
        failures = (FileNotFoundError("git"), subprocess.TimeoutExpired(["git"], 5))
        for failure in failures:
            with patch.object(otsconfig.subprocess, "run", side_effect=failure):
                self.assertIsNone(otsconfig._source_version(), failure)
        with patch.object(otsconfig, "_REPOSITORY_ROOT", str(TEST_ROOT / "zip-download")):
            with patch.object(otsconfig.subprocess, "run") as run:
                self.assertIsNone(otsconfig._source_version())
            run.assert_not_called()

    def test_build_version_wins_without_asking_git(self):
        env = {
            "ONTHESPOTDIR": str(TEST_ROOT / "build-wins-config"),
            "ONTHESPOTCACHEDIR": str(TEST_ROOT / "build-wins-cache"),
            "ONTHESPOT_VERSION": "v2.0.6",
        }
        with patch.dict(os.environ, env), patch.object(otsconfig, "_source_version") as source_version:
            self.assertEqual(Config().get("version"), "v2.0.6")
        source_version.assert_not_called()

    def test_source_version_replaces_the_template_dev(self):
        env = {
            "ONTHESPOTDIR": str(TEST_ROOT / "source-run-config"),
            "ONTHESPOTCACHEDIR": str(TEST_ROOT / "source-run-cache"),
        }
        with patch.dict(os.environ, env), patch.object(
            otsconfig.subprocess, "run", return_value=self._git_output("v2.0.5-4-g14eda2c\n")
        ):
            os.environ.pop("ONTHESPOT_VERSION", None)
            self.assertEqual(Config().get("version"), "v2.0.5-4-g14eda2c")


class ConfigSetTests(unittest.TestCase):
    def setUp(self):
        with patch.dict(
            os.environ,
            {
                "ONTHESPOTDIR": str(TEST_ROOT / "set-config"),
                "ONTHESPOTCACHEDIR": str(TEST_ROOT / "set-cache"),
            },
        ):
            self.config = Config()

    def test_text_is_converted_to_the_setting_type(self):
        self.config.set("download_chunk_size", "65536")
        self.assertEqual(self.config.get("download_chunk_size"), 65536)
        self.config.set("debug_mode", "True")
        self.assertIs(self.config.get("debug_mode"), True)
        self.config.set("search_prefix", "true")
        self.assertEqual(self.config.get("search_prefix"), "true")

    def test_keys_outside_the_settings_model_are_not_stored(self):
        self.config.set("release_readiness_probe", 7)
        self.assertIsNone(self.config.get("release_readiness_probe"))


class ConfigHealingTests(unittest.TestCase):
    def _load(self, name, stored):
        config_root = TEST_ROOT / name
        config_root.mkdir(parents=True, exist_ok=True)
        payload = {
            "audio_download_path": str(TEST_ROOT / f"{name}-audio"),
            "video_download_path": str(TEST_ROOT / f"{name}-video"),
        }
        payload.update(stored)
        (config_root / "otsconfig.json").write_text(
            json.dumps(payload), encoding="utf-8"
        )
        with patch.dict(
            os.environ,
            {
                "ONTHESPOTDIR": str(config_root),
                "ONTHESPOTCACHEDIR": str(TEST_ROOT / f"{name}-cache"),
            },
        ):
            return Config()

    def test_stored_values_are_validated_on_load(self):
        instance = self._load(
            "healing-config",
            {
                "download_chunk_size": "65536",
                "debug_mode": "true",
                "extinf_separator": 3.5,
                "download_delay": "garbage",
            },
        )

        # Text that reads as the setting's type is converted.
        self.assertEqual(instance.get("download_chunk_size"), 65536)
        self.assertIs(instance.get("debug_mode"), True)
        # A value that cannot be read as the setting's type takes the default.
        self.assertEqual(
            instance.get("extinf_separator"), DEFAULT_CONFIG["extinf_separator"]
        )
        self.assertEqual(
            instance.get("download_delay"), DEFAULT_CONFIG["download_delay"]
        )

    def test_saved_update_repository_is_dropped_on_load(self):
        instance = self._load(
            "removed-update-repository",
            {"update_repository": "someone/fork", "check_for_updates": False},
        )
        self.assertNotIn("update_repository", instance._Config__config)
        self.assertIsNone(instance.get("update_repository"))
        self.assertFalse(instance.get("check_for_updates"))

    def test_profile_bitrate_that_is_already_a_number_is_left_alone(self):
        profiles = [
            {
                "id": "mp3-320",
                "name": "MP3 · 320 kbps",
                "format": "mp3",
                "bitrate": 320,
                "download_path": "",
            },
            {
                "id": "flac",
                "name": "FLAC · lossless",
                "format": "flac",
                "bitrate": 1411,
                "download_path": "",
            },
        ]
        instance = self._load(
            "healing-profile-bitrates-untouched",
            {"download_profiles": profiles},
        )

        self.assertEqual(instance.get("download_profiles"), profiles)


if __name__ == "__main__":
    unittest.main()
