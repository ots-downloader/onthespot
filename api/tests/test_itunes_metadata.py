"""Tests for the optional, service-agnostic iTunes metadata provider."""

import unittest
from unittest.mock import patch

from _support import TEST_ROOT  # noqa: F401

from onthespot.api.itunes import itunes_get_metadata  # noqa: E402
from onthespot.api.metadata_enrichment import enrich_metadata  # noqa: E402

ITUNES_SONG = {
    "wrapperType": "track",
    "kind": "song",
    "artistName": "Daft Punk",
    "collectionName": "Discovery",
    "trackName": "Harder Better Faster Stronger",
    "artworkUrl100": "https://example.com/artwork/100x100bb.jpg",
    "releaseDate": "2001-02-26T08:00:00Z",
    "primaryGenreName": "Dance",
    "trackNumber": 4,
    "trackCount": 14,
    "discNumber": 1,
    "discCount": 1,
    "trackTimeMillis": 224693,
}


def _settings(**overrides):
    values = {
        "enable_itunes_metadata": True,
        "itunes_metadata_overwrite": False,
        "itunes_metadata_country": "US",
    }
    values.update(overrides)
    return lambda key, default=None: values.get(key, default)


class ItunesMetadataTests(unittest.TestCase):
    def test_disabled_provider_is_never_called(self):
        original = {"title": "Song", "artists": "Artist"}
        with (
            patch("onthespot.api.metadata_enrichment.config.get", side_effect=_settings(enable_itunes_metadata=False)),
            patch("onthespot.api.itunes.make_call") as mock_call,
        ):
            result = enrich_metadata(original)
        self.assertIs(result, original)
        mock_call.assert_not_called()

    def test_non_track_items_are_skipped(self):
        original = {"title": "Episode", "artists": "Podcast"}
        with (
            patch("onthespot.api.metadata_enrichment.config.get", side_effect=_settings()),
            patch("onthespot.api.itunes.make_call") as mock_call,
        ):
            result = enrich_metadata(original, item_type="podcast_episode")
        self.assertIs(result, original)
        mock_call.assert_not_called()

    def test_missing_title_warns_and_does_not_call_api(self):
        original = {"artists": "Daft Punk"}
        with (
            patch("onthespot.api.itunes.make_call") as mock_call,
            self.assertLogs("api.itunes", level="WARNING") as logs,
        ):
            result = itunes_get_metadata(original)
        self.assertIs(result, original)
        self.assertIn("no usable track title", logs.output[0])
        mock_call.assert_not_called()

    def test_fills_missing_fields_without_overwriting_source(self):
        original = {
            "title": "Harder Better Faster Stronger (Remastered)",
            "artists": "Daft Punk",
            "album_name": "Discovery",
            "genre": "Electronic",
            "length": "224693",
        }
        response = {"resultCount": 1, "results": [ITUNES_SONG]}
        with patch("onthespot.api.itunes.make_call", return_value=response) as mock_call:
            result = itunes_get_metadata(original)

        self.assertEqual(result["genre"], "Electronic")
        self.assertEqual(result["release_year"], "2001")
        self.assertEqual(result["track_number"], 4)
        self.assertEqual(result["total_tracks"], 14)
        self.assertEqual(result["disc_number"], 1)
        self.assertEqual(result["image_url"], "https://example.com/artwork/600x600bb.jpg")
        self.assertEqual(result["length"], "224693")
        self.assertEqual(original["genre"], "Electronic")
        self.assertNotIn("release_year", original)

        params = mock_call.call_args.kwargs["params"]
        self.assertEqual(params["entity"], "song")
        self.assertEqual(params["country"], "US")
        self.assertIn("Daft Punk", params["term"])

    def test_overwrite_setting_replaces_existing_fields(self):
        original = {"title": "Harder Better Faster Stronger", "artists": "Daft Punk", "genre": "Electronic"}
        response = {"resultCount": 1, "results": [ITUNES_SONG]}
        with (
            patch("onthespot.api.metadata_enrichment.config.get", side_effect=_settings(itunes_metadata_overwrite=True)),
            patch("onthespot.api.itunes.make_call", return_value=response),
        ):
            result = enrich_metadata(original)

        self.assertEqual(result["genre"], "Dance")
        self.assertEqual(original["genre"], "Electronic")

    def test_no_results_warns_and_keeps_original(self):
        original = {"title": "Completely Different Song", "artists": "Somebody Else"}
        with (
            patch("onthespot.api.itunes.make_call", return_value={"resultCount": 0, "results": []}),
            self.assertLogs("api.itunes", level="WARNING") as logs,
        ):
            result = itunes_get_metadata(original)
        self.assertIs(result, original)
        self.assertIn("No confident iTunes match", logs.output[0])

    def test_malformed_responses_warn_and_keep_original(self):
        original = {"title": "Song", "artists": "Artist"}
        for payload in (None, {"results": "not-a-list"}, {"results": ["not-a-dict"]}):
            with self.subTest(payload=payload):
                with (
                    patch("onthespot.api.itunes.make_call", return_value=payload),
                    self.assertLogs("api.itunes", level="WARNING"),
                ):
                    result = itunes_get_metadata(original)
                self.assertIs(result, original)

    def test_api_exception_warns_and_keeps_original(self):
        original = {"title": "Song", "artists": "Artist"}
        with (
            patch("onthespot.api.itunes.make_call", side_effect=RuntimeError("offline")),
            self.assertLogs("api.itunes", level="WARNING") as logs,
        ):
            result = itunes_get_metadata(original)
        self.assertIs(result, original)
        self.assertIn("lookup failed", logs.output[0])

    def test_accepts_generic_and_queue_item_shaped_inputs(self):
        result = dict(ITUNES_SONG, trackName="Song Only")
        response = {"resultCount": 1, "results": [result]}
        generic_track = {"title": "Song Only", "artists": "youtube", "image_url": "thumbnail"}
        queue_track = {"name": "Song Only", "artist": "Some Artist", "album": "Album", "item_id": "abc"}

        with patch("onthespot.api.itunes.make_call", return_value=response) as mock_call:
            itunes_get_metadata(generic_track)
            generic_term = mock_call.call_args.kwargs["params"]["term"]

            itunes_get_metadata(queue_track)
            queue_term = mock_call.call_args.kwargs["params"]["term"]

        self.assertNotIn("youtube", generic_term)
        self.assertEqual(queue_term, "Song Only Some Artist Album")

    def test_object_with_model_dump_is_accepted(self):
        class Track:
            def model_dump(self):
                return {"name": "Song Only", "artist": "Some Artist"}

        result = dict(ITUNES_SONG, trackName="Song Only", artistName="Some Artist")
        with patch("onthespot.api.itunes.make_call", return_value={"results": [result]}) as mock_call:
            enriched = itunes_get_metadata(Track())
        self.assertEqual(enriched["release_year"], "2001")
        self.assertIn("Some Artist", mock_call.call_args.kwargs["params"]["term"])

    def test_invalid_storefront_falls_back_with_warning(self):
        original = {"title": "Song Only", "artists": "Daft Punk"}
        with (
            patch("onthespot.api.itunes.make_call", return_value={"results": []}) as mock_call,
            self.assertLogs("api.itunes", level="WARNING") as logs,
        ):
            itunes_get_metadata(original, country="USA")
        self.assertEqual(mock_call.call_args.kwargs["params"]["country"], "US")
        self.assertIn("Invalid iTunes country", logs.output[0])

    def test_unsupported_input_warns_and_returns_unchanged(self):
        with self.assertLogs("api.itunes", level="WARNING"):
            self.assertIsNone(itunes_get_metadata(None))


if __name__ == "__main__":
    unittest.main()
