import os
import types
import unittest
from unittest.mock import patch

from _support import TEST_ROOT  # noqa: F401

# main.py sets this before it imports librespot; set it here for a direct import.
os.environ.setdefault("PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION", "python")

from librespot.core import Session

from onthespot.api import spotify


def _product_info(account_type):
    return f"<products><product><type>{account_type}</type></product></products>".encode()


class SessionAttributesPatchTests(unittest.TestCase):
    def setUp(self):
        # Session.__init__ opens a client and an AP connection; stub only those.
        for patcher in (
            patch.object(Session, "create_client"),
            patch.object(Session.ConnectionHolder, "create"),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)
        self.inner = types.SimpleNamespace(conf=None, device_id="test-device")

    def test_sessions_do_not_share_account_attributes(self):
        first = Session(self.inner, "ap.test:4070")
        second = Session(self.inner, "ap.test:4070")

        first.parse_product_info(_product_info("free"))

        self.assertEqual(first.get_user_attribute("type"), "free")
        self.assertIsNone(second.get_user_attribute("type"))
        self.assertEqual(Session.__dict__["_Session__user_attributes"], {})

    def test_patch_is_idempotent(self):
        patched_init = Session.__init__

        self.assertTrue(spotify._patch_librespot_session_attributes())
        self.assertTrue(spotify._patch_librespot_session_attributes())

        self.assertIs(Session.__init__, patched_init)


if __name__ == "__main__":
    unittest.main()
