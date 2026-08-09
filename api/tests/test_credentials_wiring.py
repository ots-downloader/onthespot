import json
import os
import unittest

from _support import TEST_ROOT

from onthespot.credentials import STORE_FILENAME  # noqa: E402
from onthespot.otsconfig import Config  # noqa: E402


class CredentialWiringTests(unittest.TestCase):
    """Credentials must reach the encrypted store and never the config file."""

    def setUp(self):
        self.root = TEST_ROOT / f"wiring-{self.id().rsplit('.', 1)[-1]}"
        self.root.mkdir(parents=True, exist_ok=True)
        self.cfg_path = self.root / "otsconfig.json"
        self._env = os.environ.get("ONTHESPOTDIR")
        os.environ["ONTHESPOTDIR"] = str(self.root)

    def tearDown(self):
        if self._env is None:
            os.environ.pop("ONTHESPOTDIR", None)
        else:
            os.environ["ONTHESPOTDIR"] = self._env

    def raw_config(self):
        return json.loads(self.cfg_path.read_text(encoding="utf-8"))

    def test_accounts_roundtrip_through_a_new_instance(self):
        accounts = [{"uuid": "a1", "service": "spotify", "active": True}]
        config = Config()
        config.set("accounts", accounts)
        config.save()
        self.assertEqual(Config().get("accounts"), accounts)

    def test_accounts_never_land_in_the_config_file(self):
        config = Config()
        config.set("accounts", [{"uuid": "a1", "service": "spotify", "login": {"password": "hunter2"}}])
        config.set("spotify_webapi_override_client_secret", "top-secret")
        config.save()
        raw = self.cfg_path.read_text(encoding="utf-8")
        self.assertNotIn("hunter2", raw)
        self.assertNotIn("top-secret", raw)
        self.assertNotIn("accounts", self.raw_config())

    def test_save_does_not_wipe_credentials_via_template_merge(self):
        """save() merges template defaults for missing keys; accounts is one."""
        accounts = [{"uuid": "a1", "service": "tidal", "active": True}]
        config = Config()
        config.set("accounts", accounts)
        config.save()
        config.save()
        self.assertEqual(Config().get("accounts"), accounts)

    def test_as_dict_still_reports_accounts(self):
        config = Config()
        config.set("accounts", [{"uuid": "a1", "service": "spotify", "active": True}])
        snapshot = config.as_dict()
        self.assertEqual(len(snapshot["accounts"]), 1)
        self.assertEqual(snapshot["accounts"][0]["service"], "spotify")

    def test_as_dict_still_redacts_the_login_payload(self):
        config = Config()
        config.set("accounts", [{"uuid": "a1", "service": "spotify", "login": {"password": "hunter2"}}])
        self.assertNotIn("login", config.as_dict()["accounts"][0])

    def test_as_dict_still_blanks_secrets(self):
        config = Config()
        config.set("spotify_webapi_override_client_secret", "top-secret")
        snapshot = config.as_dict()
        self.assertEqual(snapshot["spotify_webapi_override_client_secret"], "")
        self.assertTrue(snapshot["spotify_webapi_override_client_secret_configured"])

    def test_plaintext_credentials_are_moved_out_of_an_existing_config(self):
        accounts = [{"uuid": "old", "service": "deezer", "active": True}]
        self.cfg_path.write_text(
            json.dumps({"accounts": accounts, "spotify_webapi_override_client_secret": "legacy"}),
            encoding="utf-8",
        )
        config = Config()
        self.assertEqual(config.get("accounts"), accounts)
        self.assertEqual(config.get("spotify_webapi_override_client_secret"), "legacy")
        raw = self.cfg_path.read_text(encoding="utf-8")
        self.assertNotIn("legacy", raw)
        self.assertNotIn("accounts", self.raw_config())
        self.assertTrue((self.root / STORE_FILENAME).is_file())

    def test_fresh_install_still_gets_the_public_accounts(self):
        """The template ships public bandcamp/soundcloud/etc accounts.

        Nothing is stored yet on a fresh install, so get() has to fall through
        to the template or those services stop working out of the box.
        """
        services = {a["service"] for a in Config().get("accounts")}
        self.assertIn("bandcamp", services)
        self.assertIn("youtube_music", services)

    def test_stored_accounts_take_precedence_over_the_template(self):
        mine = [{"uuid": "a1", "service": "spotify", "active": True}]
        config = Config()
        config.set("accounts", mine)
        self.assertEqual(Config().get("accounts"), mine)

    def test_unknown_key_still_uses_the_supplied_default(self):
        self.assertEqual(Config().get("not_a_real_key", "fallback"), "fallback")


if __name__ == "__main__":
    unittest.main()
