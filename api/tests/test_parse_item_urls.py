import os
import unittest

from _support import TEST_ROOT  # noqa: F401

# main.py sets this before it imports librespot; set it here for a direct import.
os.environ.setdefault("PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION", "python")

from onthespot.parse_item import parse_url
from onthespot.runtimedata import parsing


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


if __name__ == "__main__":
    unittest.main()
