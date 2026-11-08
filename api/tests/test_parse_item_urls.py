import os
import unittest
from contextlib import ExitStack
from unittest.mock import patch

from _support import TEST_ROOT  # noqa: F401

# main.py sets this before it imports librespot; set it here for a direct import.
os.environ.setdefault("PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION", "python")

from fastapi.testclient import TestClient

from onthespot import parse_item
from onthespot.constants import ROUTABLE_ITEM_TYPES
from onthespot.main import app
from onthespot.parse_item import parse_url
from onthespot.parsingworker import ParsingWorker
from onthespot.resources.exceptions import UnsupportedItemError
from onthespot.runtimedata import parsing

SOUNDCLOUD_URL = "https://soundcloud.com/discover/sets/x"
# The real SoundCloud matcher needs an API token, so tests patch its result.
UNROUTABLE = ("soundcloud", "system-playlist", "1")


class AppleMusicUrlTests(unittest.TestCase):
    def setUp(self):
        parsing.replace_items([])
        self.addCleanup(parsing.replace_items, [])

    def assert_queued(self, url, item_type, item_id):
        self.assertTrue(parse_url(url))
        self.assertEqual(
            parsing.get_items(),
            [
                {
                    "item_url": url,
                    "item_service": "apple_music",
                    "item_type": item_type,
                    "item_id": item_id,
                }
            ],
        )

    def test_song_link_is_queued_as_a_track(self):
        self.assert_queued(
            "https://music.apple.com/us/song/some-name/1234567890",
            "track",
            "1234567890",
        )

    def test_album_link_with_track_id_is_queued_as_a_track(self):
        self.assert_queued(
            "https://music.apple.com/us/album/some-album/111?i=222", "track", "222"
        )

    def test_album_link_is_queued_as_an_album(self):
        self.assert_queued(
            "https://music.apple.com/us/album/some-album/111", "album", "111"
        )


class UnroutableItemTests(unittest.TestCase):
    def setUp(self):
        parsing.replace_items([])
        self.addCleanup(parsing.replace_items, [])

    def test_parse_url_refuses_a_type_the_worker_cannot_route(self):
        with (
            patch.object(parse_item._url_matcher, "match", return_value=UNROUTABLE),
            self.assertRaises(UnsupportedItemError),
        ):
            parse_url(SOUNDCLOUD_URL)
        self.assertEqual(parsing.get_items(), [])

    def test_dispatch_raises_for_an_unknown_type(self):
        worker = ParsingWorker()  # builds the thread but does not start it
        with self.assertRaises(UnsupportedItemError):
            worker._dispatch("soundcloud", "bogus", "1", SOUNDCLOUD_URL, None)

    def test_query_url_returns_400_with_reason(self):
        # No context manager: these route tests need no background workers.
        client = TestClient(app)
        with (
            patch("onthespot.parse_item.account_pool", [{"service": "soundcloud"}]),
            patch.object(parse_item._url_matcher, "match", return_value=UNROUTABLE),
        ):
            response = client.post("/query/url", params={"q": SOUNDCLOUD_URL})

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json()["detail"],
            "Soundcloud system-playlist links are not supported.",
        )
        self.assertEqual(parsing.get_items(), [])

    def test_dispatch_routes_every_routable_type(self):
        handlers = [name for name in vars(ParsingWorker) if name.startswith("_expand_")]
        worker = ParsingWorker()
        with ExitStack() as stack:
            for name in [*handlers, "_enqueue_single_item"]:
                stack.enter_context(patch.object(worker, name))
            for item_type in ROUTABLE_ITEM_TYPES:
                with self.subTest(item_type=item_type):
                    worker._dispatch("soundcloud", item_type, "1", SOUNDCLOUD_URL, None)


if __name__ == "__main__":
    unittest.main()
