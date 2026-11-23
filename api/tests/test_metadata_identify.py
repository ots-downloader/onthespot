"""Tests for manual iTunes identification of finished downloads."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from _support import TEST_ROOT  # noqa: F401

from fastapi.testclient import TestClient  # noqa: E402

from onthespot.basemodels import DownloadProfile, IdentifyApplyRequest, IdentifyCandidate, IdentifySearchRequest, QueueItem
from onthespot.constants import ItemStatus
from onthespot.main import app  # noqa: E402
from onthespot.metadata_identify import apply_manual_match, search_manual_matches
from onthespot.otsconfig import config
from onthespot.runtimedata import download_queue, download_queue_lock


class ManualIdentifyTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(dir=TEST_ROOT))
        self.source = self.root / "Wrong Artist - Wrong Title.mp3"
        self.source.write_bytes(b"original-audio")

        real_get = config.get

        def settings(key, default=None):
            overrides = {
                "audio_download_path": str(self.root),
                "download_profiles": [],
                "track_path_formatter": "{artist}/{name}",
                "use_playlist_path": False,
                "translate_file_path": False,
                "use_double_digit_path_numbers": False,
                "illegal_character_replacement": "-",
                "itunes_metadata_country": "GB",
            }
            return overrides[key] if key in overrides else real_get(key, default)

        self.settings = settings
        patchers = [
            patch("onthespot.metadata_files.config.get", side_effect=settings),
            patch("onthespot.metadata_identify.config.get", side_effect=settings),
            patch("onthespot.utils.config.get", side_effect=settings),
        ]
        for patcher in patchers:
            patcher.start()
            self.addCleanup(patcher.stop)

        with download_queue_lock:
            self.saved_queue = dict(download_queue)
            download_queue.clear()
        self.addCleanup(self._restore_queue)

    def _restore_queue(self):
        with download_queue_lock:
            download_queue.clear()
            download_queue.update(self.saved_queue)

    def _candidate(self, **overrides):
        values = {
            "track_id": "123",
            "title": "Correct Title",
            "artist": "Correct Artist",
            "album": "Correct Album",
            "album_artist": "Correct Artist",
            "genre": "Dance",
            "release_year": "2001",
            "track_number": 3,
            "total_tracks": 10,
            "disc_number": 1,
            "total_discs": 1,
            "image_url": "https://is1-ssl.mzstatic.com/image/thumb/art.jpg",
            "length": "200000",
            "score": 8.5,
        }
        values.update(overrides)
        return IdentifyCandidate(**values)

    def _add_item(self, source=None, status=ItemStatus.DOWNLOADED, item_type="track"):
        source = source or self.source
        profile = DownloadProfile(
            id="profile",
            name="Profile",
            format="mp3",
            bitrate=320,
            download_path=str(self.root),
        )
        item = QueueItem(
            local_id=42,
            name="Wrong Title",
            artist="Wrong Artist",
            album="Wrong Album",
            length=200000,
            item_service="spotify",
            item_type=item_type,
            item_id="spotify:track:abc",
            item_url="https://open.spotify.com/track/abc",
            parent_category="track",
            item_status=status,
            file_path=str(source),
            download_profile=profile,
        )
        with download_queue_lock:
            download_queue[item.local_id] = item
        return item

    def _run_apply(self, candidate=None, artwork=b"image-bytes", artwork_error=None):
        candidate = candidate or self._candidate()
        with (
            patch("onthespot.metadata_identify.update_tags", return_value={"title": candidate.title}) as update,
            patch("onthespot.metadata_identify.update_artwork", return_value={"artwork": True}) as cover,
            patch(
                "onthespot.metadata_identify.fetch_itunes_artwork",
                return_value=artwork,
                side_effect=artwork_error,
            ) as fetch,
            patch("onthespot.metadata_identify.notification_hook"),
        ):
            result = apply_manual_match(
                IdentifyApplyRequest(local_id=42, candidate=candidate, embed_artwork=True)
            )
        return result, update, cover, fetch

    def test_search_uses_queue_values_and_configured_country(self):
        self._add_item()
        candidate = self._candidate().model_dump()
        with patch("onthespot.metadata_identify.itunes_search_candidates", return_value=[candidate]) as mock_search:
            result = search_manual_matches(IdentifySearchRequest(local_id=42, limit=5))

        self.assertEqual(result["country"], "GB")
        self.assertEqual(result["candidates"], [candidate])
        self.assertEqual(mock_search.call_args.args, ("Wrong Title", "Wrong Artist", "Wrong Album"))
        self.assertEqual(mock_search.call_args.kwargs["limit"], 5)

    def test_apply_creates_tagged_copy_and_leaves_original_untouched(self):
        self._add_item()
        result, update, cover, fetch = self._run_apply()

        expected = self.root / "Correct Artist" / "Correct Title.mp3"
        self.assertTrue(expected.is_file())
        self.assertEqual(expected.read_bytes(), b"original-audio")
        self.assertEqual(self.source.read_bytes(), b"original-audio")
        self.assertEqual(result["original_path"], str(self.source))
        self.assertEqual(result["file_path"], str(expected))
        self.assertEqual(result["warnings"], [])
        self.assertEqual(result["metadata"]["title"], "Correct Title")
        self.assertTrue(result["metadata"]["artwork"])

        update.assert_called_once()
        self.assertEqual(update.call_args.args[0], str(expected))
        self.assertEqual(update.call_args.kwargs["item"]["item_id"], "spotify:track:abc")
        self.assertEqual(
            update.call_args.args[1],
            {
                "title": "Correct Title",
                "artist": "Correct Artist",
                "album": "Correct Album",
                "album_artist": "Correct Artist",
                "genre": "Dance",
                "year": "2001",
                "track_number": 3,
                "total_tracks": 10,
                "disc_number": 1,
                "total_discs": 1,
            },
        )
        cover.assert_called_once_with(str(expected), b"image-bytes")
        fetch.assert_called_once()
        self.assertEqual(download_queue[42].file_path, str(expected))
        self.assertEqual(download_queue[42].name, "Correct Title")

    def test_default_formatter_nests_album_inside_artist_when_album_artist_missing(self):
        self._add_item()
        candidate = self._candidate(album_artist="")

        def formatter_settings(key, default=None):
            if key == "track_path_formatter":
                return "Tracks/{album_artist}/{year} {album}/{name}"
            return self.settings(key, default)

        with patch("onthespot.utils.config.get", side_effect=formatter_settings):
            result, update, _, _ = self._run_apply(candidate=candidate)

        expected = self.root / "Tracks" / "Correct Artist" / "2001 Correct Album" / "Correct Title.mp3"
        self.assertEqual(result["file_path"], str(expected))
        self.assertTrue(expected.is_file())
        self.assertEqual(update.call_args.args[1]["album_artist"], "Correct Artist")

    def test_extension_is_kept_when_title_contains_a_dot(self):
        self._add_item()
        candidate = self._candidate(title="Song feat. Guest")

        result, _, _, _ = self._run_apply(candidate=candidate)

        expected = self.root / "Correct Artist" / "Song feat. Guest.mp3"
        self.assertEqual(result["file_path"], str(expected))
        self.assertTrue(expected.is_file())

    def test_existing_target_gets_a_numeric_suffix_without_overwrite(self):
        self._add_item()
        existing = self.root / "Correct Artist" / "Correct Title.mp3"
        existing.parent.mkdir(parents=True, exist_ok=True)
        existing.write_bytes(b"already-here")

        result, _, _, _ = self._run_apply()

        expected = self.root / "Correct Artist" / "Correct Title (2).mp3"
        self.assertEqual(result["file_path"], str(expected))
        self.assertEqual(existing.read_bytes(), b"already-here")
        self.assertEqual(expected.read_bytes(), b"original-audio")

    def test_target_equal_to_source_gets_tagged_suffix(self):
        source = self.root / "Correct Artist" / "Correct Title.mp3"
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_bytes(b"original-audio")
        self._add_item(source=source)

        result, _, _, _ = self._run_apply()

        expected = self.root / "Correct Artist" / "Correct Title - tagged.mp3"
        self.assertEqual(result["file_path"], str(expected))
        self.assertEqual(source.read_bytes(), b"original-audio")
        self.assertEqual(expected.read_bytes(), b"original-audio")

    def test_non_finished_items_are_rejected(self):
        self._add_item(status=ItemStatus.DOWNLOADING)
        with self.assertRaisesRegex(ValueError, "finished downloads"):
            apply_manual_match(IdentifyApplyRequest(local_id=42, candidate=self._candidate()))

    def test_files_outside_the_download_folders_are_rejected(self):
        outside = Path(tempfile.mkdtemp()) / "outside.mp3"
        outside.write_bytes(b"outside-audio")
        self._add_item(source=outside)
        with self.assertRaisesRegex(ValueError, "outside the configured download folders"):
            apply_manual_match(IdentifyApplyRequest(local_id=42, candidate=self._candidate()))

    def test_dict_queue_items_are_supported(self):
        with download_queue_lock:
            download_queue[42] = {
                "local_id": 42,
                "name": "Wrong Title",
                "artist": "Wrong Artist",
                "album": "Wrong Album",
                "length": 200000,
                "item_service": "spotify",
                "item_type": "track",
                "item_id": "spotify:track:abc",
                "item_url": "https://open.spotify.com/track/abc",
                "parent_category": "track",
                "item_status": ItemStatus.DOWNLOADED.value,
                "file_path": str(self.source),
                "download_profile": {
                    "id": "profile",
                    "name": "Profile",
                    "format": "mp3",
                    "bitrate": 320,
                    "download_path": str(self.root),
                },
            }

        result, _, _, _ = self._run_apply()

        self.assertEqual(download_queue[42]["file_path"], result["file_path"])
        self.assertEqual(download_queue[42]["name"], "Correct Title")
        self.assertEqual(self.source.read_bytes(), b"original-audio")

    def test_artwork_failure_still_applies_tags(self):
        self._add_item()
        result, update, cover, _ = self._run_apply(artwork_error=ValueError("bad artwork"))

        self.assertTrue(Path(result["file_path"]).is_file())
        self.assertTrue(any("Artwork was not embedded" in warning for warning in result["warnings"]))
        update.assert_called_once()
        cover.assert_not_called()


class ManualIdentifyEndpointTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def test_search_endpoint_returns_candidates(self):
        payload = {"query": {"title": "Song", "artist": "Artist", "album": "Album"}, "country": "US", "candidates": []}
        with patch("onthespot.main.search_manual_matches", return_value=payload) as mock_search:
            response = self.client.post("/metadata/identify/search", json={"local_id": 42, "title": "Song"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), payload)
        self.assertEqual(mock_search.call_args.args[0].local_id, 42)

    def test_apply_endpoint_returns_copy_paths(self):
        payload = {
            "original_path": "/music/old.mp3",
            "file_path": "/music/new.mp3",
            "queue_updated": True,
            "item": {},
            "metadata": {},
            "warnings": [],
        }
        with patch("onthespot.main.apply_manual_match", return_value=payload) as mock_apply:
            response = self.client.post(
                "/metadata/identify/apply",
                json={"local_id": 42, "candidate": {"title": "Song", "artist": "Artist"}},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["file_path"], "/music/new.mp3")
        self.assertEqual(mock_apply.call_args.args[0].candidate.title, "Song")

    def test_missing_queue_item_maps_to_404(self):
        with patch("onthespot.main.search_manual_matches", side_effect=LookupError("missing")):
            response = self.client.post("/metadata/identify/search", json={"local_id": 999})

        self.assertEqual(response.status_code, 404)
        self.assertIn("missing", response.json()["detail"])


if __name__ == "__main__":
    unittest.main()
