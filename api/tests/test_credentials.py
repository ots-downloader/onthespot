import json
import os
import stat
import unittest

from _support import TEST_ROOT

from onthespot.credentials import (  # noqa: E402
    KEY_FILENAME,
    STORE_FILENAME,
    CredentialStore,
)


class CredentialStoreTests(unittest.TestCase):
    def setUp(self):
        self.directory = TEST_ROOT / f"credentials-{self.id().rsplit('.', 1)[-1]}"
        for name in (KEY_FILENAME, STORE_FILENAME):
            (self.directory / name).unlink(missing_ok=True)

    def store(self):
        return CredentialStore(self.directory)

    def test_roundtrip_preserves_values(self):
        store = self.store()
        values = {
            "accounts": [{"service": "spotify", "login": {"password": "hunter2"}}],
            "spotify_webapi_override_client_secret": "s3cr3t",
        }
        self.assertTrue(store.save(values))
        self.assertEqual(self.store().load(), values)

    def test_missing_store_reads_as_empty(self):
        self.assertEqual(self.store().load(), {})

    def test_secrets_are_not_recoverable_from_the_file(self):
        store = self.store()
        store.save({"spotify_webapi_override_client_secret": "totally-secret-value"})
        blob = store.store_path.read_bytes()
        self.assertNotIn(b"totally-secret-value", blob)
        self.assertNotIn(b"spotify_webapi_override_client_secret", blob)

    def test_key_is_created_once_and_reused(self):
        store = self.store()
        store.save({"accounts": []})
        first = store.key_path.read_bytes()
        store.save({"accounts": [{"service": "tidal"}]})
        self.assertEqual(store.key_path.read_bytes(), first)

    @unittest.skipIf(os.name == "nt", "POSIX permission bits only")
    def test_key_and_store_are_private(self):
        store = self.store()
        store.save({"accounts": []})
        for path in (store.key_path, store.store_path):
            mode = stat.S_IMODE(path.stat().st_mode)
            self.assertEqual(mode, 0o600, f"{path.name} is {oct(mode)}, expected 0o600")

    def test_lost_key_does_not_raise(self):
        """Losing the key should cost a re-login, never a crash on startup."""
        store = self.store()
        store.save({"accounts": [{"service": "spotify"}]})
        store.key_path.unlink()
        self.assertEqual(self.store().load(), {})

    def test_wrong_key_does_not_raise(self):
        store = self.store()
        store.save({"accounts": [{"service": "spotify"}]})
        from cryptography.fernet import Fernet

        store.key_path.write_bytes(Fernet.generate_key())
        self.assertEqual(self.store().load(), {})

    def test_corrupt_store_does_not_raise(self):
        store = self.store()
        store.save({"accounts": []})
        store.store_path.write_bytes(b"not a fernet token")
        self.assertEqual(self.store().load(), {})

    def test_empty_store_file_reads_as_empty(self):
        store = self.store()
        store.save({"accounts": []})
        store.store_path.write_bytes(b"")
        self.assertEqual(store.load(), {})

    def test_non_object_payload_is_ignored(self):
        """A store holding a JSON list must not be handed back as credentials."""
        from cryptography.fernet import Fernet

        store = self.store()
        store.save({"accounts": []})
        key = store.key_path.read_bytes()
        store.store_path.write_bytes(Fernet(key).encrypt(json.dumps([1, 2]).encode()))
        self.assertEqual(store.load(), {})

    def test_save_rejects_non_dict(self):
        with self.assertRaises(TypeError):
            self.store().save(["not", "a", "dict"])

    def test_clear_removes_the_store_but_keeps_the_key(self):
        store = self.store()
        store.save({"accounts": [{"service": "deezer"}]})
        store.clear()
        self.assertFalse(store.store_path.exists())
        self.assertTrue(store.key_path.exists())
        self.assertEqual(store.load(), {})

    def test_clear_is_safe_when_nothing_is_stored(self):
        self.store().clear()

    def test_unicode_survives_the_roundtrip(self):
        values = {"accounts": [{"service": "spotify", "display": "Bjork — café"}]}
        store = self.store()
        store.save(values)
        self.assertEqual(self.store().load(), values)

    def test_failed_write_leaves_no_temp_files(self):
        store = self.store()
        store.save({"accounts": []})
        leftovers = [p.name for p in self.directory.glob(".tmp-*")]
        self.assertEqual(leftovers, [])


if __name__ == "__main__":
    unittest.main()
