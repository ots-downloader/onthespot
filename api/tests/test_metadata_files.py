"""Tests for the standalone metadata file helpers."""

import io
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from _support import TEST_ROOT  # noqa: F401

import music_tag  # noqa: E402
from PIL import Image  # noqa: E402

from onthespot.metadata_files import copy_file, update_artwork, update_tags  # noqa: E402


@unittest.skipUnless(shutil.which("ffmpeg"), "ffmpeg is required to create a test audio file")
class MetadataFileTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(dir=TEST_ROOT))
        self.source = self.root / "source.mp3"
        subprocess.run(
            [
                "ffmpeg", "-v", "error", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono",
                "-t", "0.2", "-q:a", "9", "-y", str(self.source),
            ],
            check=True,
        )

        overrides = {
            "audio_download_path": str(self.root),
            "download_profiles": [],
            "_ffmpeg_bin_path": shutil.which("ffmpeg"),
            "album_cover_format": "png",
            "raw_media_download": False,
            "embed_artist": True,
            "embed_album": True,
            "embed_albumartist": True,
            "embed_name": True,
            "embed_year": True,
            "embed_discnumber": True,
            "embed_tracknumber": True,
            "embed_genre": True,
            "embed_cover": True,
            "save_album_cover": False,
            "windows_10_explorer_thumbnails": False,
            "embed_branding": False,
            "embed_service_id": False,
        }

        def settings(key, default=None):
            return overrides.get(key, default)

        patcher = patch("onthespot.metadata_files.config.get", side_effect=settings)
        patcher.start()
        self.addCleanup(patcher.stop)

    def _artwork(self) -> bytes:
        buffer = io.BytesIO()
        Image.new("RGB", (16, 16), (180, 40, 80)).save(buffer, format="PNG")
        return buffer.getvalue()

    def test_copy_file_never_overwrites_and_refuses_same_path(self):
        target = self.root / "copy.mp3"
        original = self.source.read_bytes()

        self.assertEqual(copy_file(self.source, target), str(target))
        self.assertEqual(target.read_bytes(), original)
        self.assertEqual(self.source.read_bytes(), original)

        with self.assertRaises(FileExistsError):
            copy_file(self.source, target)
        with self.assertRaises(ValueError):
            copy_file(self.source, self.source)

    def test_tags_and_artwork_are_written_to_the_copy_only(self):
        target = self.root / "tagged.mp3"
        copy_file(self.source, target)
        original = self.source.read_bytes()

        applied = update_tags(
            target,
            {
                "title": "Tagged Title",
                "artist": "Good Artist",
                "album": "Tagged Album",
                "album_artist": "Good Artist",
                "genre": "Dance",
                "year": "2001",
                "track_number": 3,
                "total_tracks": 10,
                "disc_number": 1,
                "total_discs": 1,
            },
            item={"item_service": "spotify", "item_id": "spotify:track:abc"},
        )
        self.assertEqual(update_artwork(target, self._artwork()), {"artwork": True})

        loaded = music_tag.load_file(str(target))
        self.assertEqual(loaded["title"].first, "Tagged Title")
        self.assertEqual(loaded["artist"].first, "Good Artist")
        self.assertEqual(loaded["album"].first, "Tagged Album")
        self.assertEqual(loaded["albumartist"].first, "Good Artist")
        self.assertEqual(loaded["genre"].first, "Dance")
        self.assertEqual(loaded["year"].first, 2001)
        self.assertEqual(loaded["tracknumber"].first, 3)
        self.assertEqual(loaded["discnumber"].first, 1)
        self.assertTrue(loaded["artwork"].first.raw.startswith(b"\x89PNG"))
        self.assertEqual(
            set(applied),
            {
                "title", "artist", "album", "album_artist", "genre",
                "year", "track_number", "total_tracks", "disc_number", "total_discs",
            },
        )
        self.assertEqual(self.source.read_bytes(), original)


if __name__ == "__main__":
    unittest.main()
