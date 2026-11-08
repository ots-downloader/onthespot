import os
import unittest
from unittest.mock import MagicMock

from _support import TEST_ROOT  # noqa: F401

# main.py sets this before it imports librespot; set it here for a direct import.
os.environ.setdefault("PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION", "python")

from librespot.core import TokenProvider

from onthespot.api import spotify


class TokenProviderPatchTests(unittest.TestCase):
    def test_providers_do_not_share_tokens(self):
        first = TokenProvider(MagicMock())
        second = TokenProvider(MagicMock())

        first._TokenProvider__tokens.append("token")

        self.assertIsNot(first._TokenProvider__tokens, second._TokenProvider__tokens)
        self.assertEqual(second._TokenProvider__tokens, [])
        self.assertEqual(TokenProvider.__dict__["_TokenProvider__tokens"], [])

    def test_patch_is_idempotent(self):
        patched_init = TokenProvider.__init__

        self.assertTrue(spotify._patch_librespot_token_provider())

        self.assertIs(TokenProvider.__init__, patched_init)


if __name__ == "__main__":
    unittest.main()
