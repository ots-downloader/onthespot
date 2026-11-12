import os
import unittest
import uuid
from unittest.mock import MagicMock, patch

from _support import TEST_ROOT  # noqa: F401

# main.py sets this before it imports librespot; set it here for a direct import.
os.environ.setdefault("PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION", "python")

from onthespot.parse_item import parse_url
from onthespot.runtimedata import parsing


def flat_entry(url):
    """A playlist entry as yt-dlp gives it with extract_flat: no webpage_url."""
    entry_id = url.rsplit("/", 1)[-1]
    return {
        "_type": "url",
        "ie_key": "Generic",
        "url": url,
        "id": entry_id,
        "title": f"Track {entry_id}",
    }


def inline_entry(playlist_url, n):
    """An inline entry as archive.org gives it: "url" is a direct media link and
    yt-dlp fills "webpage_url" with the playlist URL."""
    return {
        "id": f"file{n}",
        "title": f"File {n}",
        "url": f"{playlist_url}/download/file{n}.mpg",
        "webpage_url": playlist_url,
    }


def fake_youtube_dl(playlists):
    """Build a YoutubeDL stand-in; *playlists* maps a URL to its entry list."""

    def extract_info(url, download=False):
        if url in playlists:
            return {"_type": "playlist", "webpage_url": url, "entries": playlists[url]}
        return {"title": "t", "extractor": "generic", "thumbnail": None}

    ydl = MagicMock()
    ydl.extract_info.side_effect = extract_info
    return MagicMock(return_value=ydl)


class GenericFallbackTests(unittest.TestCase):
    def setUp(self):
        parsing.replace_items([])
        self.addCleanup(parsing.replace_items, [])
        # Unique URLs per test so the on-disk request cache cannot leak.
        self.base = f"https://example.com/{uuid.uuid4().hex}"
        self.playlist_url = f"{self.base}/playlist"
        self.entry_urls = [f"{self.base}/track/{n}" for n in range(3)]
        self.playlists = {self.playlist_url: [flat_entry(u) for u in self.entry_urls]}
        patcher = patch(
            "onthespot.api.generic.YoutubeDL", fake_youtube_dl(self.playlists)
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        account_patcher = patch(
            "onthespot.parse_item.account_pool", [{"service": "generic"}]
        )
        account_patcher.start()
        self.addCleanup(account_patcher.stop)

    def generic_track(self, url):
        return {
            "item_url": url,
            "item_service": "generic",
            "item_type": "track",
            "item_id": url,
        }

    def test_single_link_is_queued_as_a_generic_track(self):
        url = f"{self.base}/single"
        self.assertTrue(parse_url(url))
        self.assertEqual(parsing.get_items(), [self.generic_track(url)])

    def test_flat_playlist_queues_each_entry_with_its_own_url(self):
        self.assertTrue(parse_url(self.playlist_url))
        self.assertEqual(
            parsing.get_items(), [self.generic_track(u) for u in self.entry_urls]
        )

    def test_entries_without_a_url_are_skipped(self):
        no_url = {"_type": "url", "ie_key": "Generic", "id": "x", "title": "No URL"}
        self.playlists[self.playlist_url] = [None, no_url] + [
            flat_entry(u) for u in self.entry_urls
        ]
        self.assertTrue(parse_url(self.playlist_url))
        self.assertEqual(
            parsing.get_items(), [self.generic_track(u) for u in self.entry_urls]
        )

    def test_repeated_entry_is_queued_once(self):
        first, second = self.entry_urls[:2]
        self.playlists[self.playlist_url] = [
            flat_entry(first),
            flat_entry(second),
            flat_entry(first),
        ]
        self.assertTrue(parse_url(self.playlist_url))
        self.assertEqual(
            parsing.get_items(), [self.generic_track(first), self.generic_track(second)]
        )

    def test_playlist_whose_entries_point_at_itself_is_not_handled(self):
        self.playlists[self.playlist_url] = [
            inline_entry(self.playlist_url, n) for n in range(3)
        ]
        self.assertFalse(parse_url(self.playlist_url))
        self.assertEqual(parsing.get_items(), [])

    def test_no_generic_account_queues_nothing(self):
        with patch("onthespot.parse_item.account_pool", []):
            self.assertFalse(parse_url(f"{self.base}/single"))
        self.assertEqual(parsing.get_items(), [])


if __name__ == "__main__":
    unittest.main()
