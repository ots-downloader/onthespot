from __future__ import annotations

import unittest
from unittest.mock import MagicMock, Mock, call, patch
import json

from _support import TEST_ROOT  # noqa: F401

from onthespot.api.bandcamp import bandcamp_get_search_results  # noqa: E402
from onthespot.api.youtube_music import youtube_music_get_search_results  # noqa: E402


class BandcampSearchTests(unittest.TestCase):
    def test_search_uses_json_catalogue_and_maps_requested_types(self):
        track_payload = {
            "auto": {
                "results": [
                    {
                        "type": "t",
                        "id": 123,
                        "art_id": 123456789,
                        "name": "Example Track",
                        "band_name": "Example Artist",
                        "item_url_path": "https://artist.bandcamp.com/track/example",
                        "img": "https://example.test/track.jpg",
                    }
                ]
            }
        }
        artist_payload = {
            "auto": {
                "results": [
                    {
                        "type": "b",
                        "id": 456,
                        "img_id": 33347730,
                        "name": "Example Artist",
                        "location": "London, UK",
                        "item_url_root": "https://artist.bandcamp.com",
                        "img": "https://example.test/artist.jpg",
                    }
                ]
            }
        }
        track_response = Mock()
        track_response.read.return_value = json.dumps(track_payload).encode("utf-8")
        artist_response = Mock()
        artist_response.read.return_value = json.dumps(artist_payload).encode("utf-8")
        track_context = MagicMock()
        track_context.__enter__.return_value = track_response
        artist_context = MagicMock()
        artist_context.__enter__.return_value = artist_response

        with (
            patch(
                "onthespot.api.bandcamp.urlopen",
                side_effect=[track_context, artist_context],
            ) as open_url,
            patch("onthespot.api.bandcamp.config.get", return_value=10),
        ):
            results = bandcamp_get_search_results(
                None,
                "Example",
                ["track", "artist"],
            )

        self.assertEqual(
            [result["item_type"] for result in results],
            ["track", "artist"],
        )
        self.assertEqual(results[0]["item_id"], "123")
        self.assertEqual(results[0]["item_by"], "Example Artist")
        self.assertEqual(
            results[0]["item_thumbnail_url"],
            "https://f4.bcbits.com/img/a0123456789_16.jpg",
        )
        self.assertEqual(results[1]["item_url"], "https://artist.bandcamp.com")
        self.assertEqual(
            results[1]["item_thumbnail_url"],
            "https://f4.bcbits.com/img/0033347730_10.jpg",
        )
        self.assertEqual(open_url.call_count, 2)
        self.assertEqual(
            [
                json.loads(entry.args[0].data.decode("utf-8"))["search_filter"]
                for entry in open_url.call_args_list
            ],
            ["t", "b"],
        )


class YouTubeSearchTests(unittest.TestCase):
    def test_locked_browser_session_falls_back_to_public_catalogue_search(self):
        public_entries = [
            {
                "id": "video-1",
                "title": "Example Video",
                "channel": "Example Channel",
            }
        ]
        with (
            patch(
                "onthespot.api.youtube_music.youtube_ydl_options",
                return_value={"cookiesfrombrowser": ("chrome",)},
            ),
            patch(
                "onthespot.api.youtube_music._youtube_search",
                side_effect=[RuntimeError("Chrome cookie database is locked"), public_entries],
            ) as search,
        ):
            results = youtube_music_get_search_results(None, "Example", ["track"])

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["item_service"], "youtube_music")
        self.assertEqual(results[0]["item_id"], "video-1")
        self.assertEqual(
            search.call_args_list,
            [
                call(
                    "Example",
                    {
                        "quiet": True,
                        "no_warnings": True,
                        "extract_flat": True,
                        "skip_download": True,
                        "cookiesfrombrowser": ("chrome",),
                    },
                ),
                call(
                    "Example",
                    {
                        "quiet": True,
                        "no_warnings": True,
                        "extract_flat": True,
                        "skip_download": True,
                    },
                ),
            ],
        )

    def test_public_search_failure_is_not_hidden(self):
        with (
            patch("onthespot.api.youtube_music.youtube_ydl_options", return_value={}),
            patch(
                "onthespot.api.youtube_music._youtube_search",
                side_effect=RuntimeError("provider unavailable"),
            ),
        ):
            with self.assertRaisesRegex(RuntimeError, "provider unavailable"):
                youtube_music_get_search_results(None, "Example", ["track"])


if __name__ == "__main__":
    unittest.main()
