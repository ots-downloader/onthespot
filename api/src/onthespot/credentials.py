"""Encrypted at-rest storage for account credentials.

Account logins and API secrets used to live in ``otsconfig.json`` as plain
text, which meant a config pasted into a bug report, copied into a backup or
captured in a screenshot leaked reusable credentials.

Those values now live in their own encrypted file next to the config, so the
config itself stays readable and hand-editable while the sensitive half does
not. Splitting by file rather than by field also means nothing has to work out
which keys inside the config are secret.

What this protects: casual disclosure. A config shared for debugging, a backup
copied somewhere, a screenshot.

What it does not protect: anyone who can read the config directory, since the
key sits beside the store. Gating the key behind a passphrase would close that
gap and is deliberately left for a follow-up.
"""

from __future__ import annotations

import json
import logging
import os
import stat
import tempfile
from pathlib import Path
from typing import Any

from cryptography.fernet import Fernet, InvalidToken

logger = logging.getLogger("onthespot.credentials")

#: Config keys held in the encrypted store instead of ``otsconfig.json``.
CREDENTIAL_KEYS = frozenset(
    {
        "accounts",
        "spotify_webapi_override_client_secret",
        "playlist_automation_client_secret",
    }
)

KEY_FILENAME = "credentials.key"
STORE_FILENAME = "credentials.enc"


def _write_private(path: Path, payload: bytes) -> None:
    """Write *payload* to *path* atomically, readable only by this user.

    The temp file is created in the destination directory so the rename cannot
    cross a filesystem boundary, and permissions are set before any content is
    written so the secret is never briefly world-readable.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temp_name = tempfile.mkstemp(dir=str(path.parent), prefix=".tmp-")
    temp_path = Path(temp_name)
    try:
        os.close(handle)
        # mkstemp is already 0600; restate it so intent survives a refactor.
        # On Windows this only clears the read-only bit, and the file inherits
        # the directory ACL instead. Documented rather than silently assumed.
        os.chmod(temp_path, stat.S_IRUSR | stat.S_IWUSR)
        temp_path.write_bytes(payload)
        os.replace(temp_path, path)
    except BaseException:
        temp_path.unlink(missing_ok=True)
        raise


class CredentialStore:
    """Fernet-encrypted key/value store for the credential keys."""

    def __init__(self, directory: str | os.PathLike[str]) -> None:
        self._directory = Path(directory)
        self._key_path = self._directory / KEY_FILENAME
        self._store_path = self._directory / STORE_FILENAME

    @property
    def key_path(self) -> Path:
        return self._key_path

    @property
    def store_path(self) -> Path:
        return self._store_path

    def _load_or_create_key(self) -> bytes:
        try:
            key = self._key_path.read_bytes().strip()
            if key:
                return key
            logger.warning("Credential key at %s is empty; generating a new one.", self._key_path)
        except FileNotFoundError:
            pass
        except OSError as exc:
            raise RuntimeError(f"Could not read the credential key: {exc}") from exc

        key = Fernet.generate_key()
        _write_private(self._key_path, key)
        logger.info("Generated a new credential key at %s", self._key_path)
        return key

    def load(self) -> dict[str, Any]:
        """Return the stored credentials, or an empty dict if unreadable.

        A missing, damaged or undecryptable store is not fatal. The user is
        asked to sign in again, which is recoverable; refusing to start is not.
        """
        try:
            blob = self._store_path.read_bytes()
        except FileNotFoundError:
            return {}
        except OSError as exc:
            logger.error("Could not read %s: %s", self._store_path, exc)
            return {}

        if not blob.strip():
            return {}

        try:
            key = self._load_or_create_key()
        except RuntimeError as exc:
            logger.error("%s Stored accounts cannot be decrypted.", exc)
            return {}

        try:
            plaintext = Fernet(key).decrypt(blob)
        except InvalidToken:
            logger.error(
                "Stored credentials at %s could not be decrypted with %s. The key "
                "was probably replaced or lost; sign in again to rebuild them.",
                self._store_path,
                self._key_path,
            )
            return {}

        try:
            values = json.loads(plaintext.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            logger.error("Stored credentials are not valid JSON: %s", exc)
            return {}

        if not isinstance(values, dict):
            logger.error(
                "Stored credentials are %s, expected an object; ignoring them.",
                type(values).__name__,
            )
            return {}
        return values

    def save(self, values: dict[str, Any]) -> bool:
        """Encrypt and persist *values*. Returns False if it could not be written."""
        if not isinstance(values, dict):
            raise TypeError(f"credentials must be a dict, got {type(values).__name__}")

        try:
            key = self._load_or_create_key()
        except RuntimeError as exc:
            logger.error("%s Credentials were not saved.", exc)
            return False

        payload = json.dumps(values, ensure_ascii=False).encode("utf-8")
        try:
            _write_private(self._store_path, Fernet(key).encrypt(payload))
        except OSError as exc:
            logger.error("Could not write %s: %s", self._store_path, exc)
            return False
        return True

    def clear(self) -> None:
        """Remove the stored credentials, leaving the key in place."""
        self._store_path.unlink(missing_ok=True)
