"""Local music-library indexing and file helpers.

The downloader already knows where completed files are written.  This module
adds a small, dependency-light index on top of those folders so the web UI can
search, sort, edit, and open local audio without making the queue the source
of truth for the library.
"""

from __future__ import annotations

import hashlib
import io
import json
import mimetypes
import os
import re
import threading
import time
from pathlib import Path
from typing import Any

import music_tag
from mutagen import File as MutagenFile

from .otsconfig import config


AUDIO_EXTENSIONS = {
    ".aac",
    ".aiff",
    ".alac",
    ".flac",
    ".m4a",
    ".mp3",
    ".oga",
    ".ogg",
    ".opus",
    ".wav",
    ".wma",
}
INDEX_FILENAME = ".onthespot-library.json"
_index_lock = threading.RLock()


def _absolute(path: str | os.PathLike[str]) -> str:
    return os.path.abspath(os.path.expanduser(os.fspath(path)))


def library_roots() -> list[str]:
    """Return the configured audio roots, including profile-specific roots."""
    candidates: list[str] = []
    audio_root = config.get("audio_download_path")
    if audio_root:
        candidates.append(_absolute(audio_root))
    for profile in config.get("download_profiles", []) or []:
        profile_root = profile.get("download_path") if isinstance(profile, dict) else ""
        if profile_root:
            candidates.append(_absolute(profile_root))

    roots: list[str] = []
    for candidate in candidates:
        if candidate not in roots:
            roots.append(candidate)
    return roots


def _within(path: str, root: str) -> bool:
    try:
        return os.path.commonpath([_absolute(path), _absolute(root)]) == _absolute(root)
    except (OSError, ValueError):
        return False


def is_allowed_path(path: str, allow_missing: bool = False) -> bool:
    """Prevent file endpoints from escaping the configured music roots."""
    normalized = _absolute(path)
    if not allow_missing and not os.path.isfile(normalized):
        return False
    return any(_within(normalized, root) for root in library_roots())


def _index_path() -> str:
    roots = library_roots()
    if roots:
        return os.path.join(roots[0], INDEX_FILENAME)
    return os.path.join(os.path.expanduser("~"), INDEX_FILENAME)


def _path_key(path: str) -> str:
    normalized = _absolute(path)
    return os.path.normcase(normalized) if os.name == "nt" else normalized


def _load_index() -> dict[str, dict[str, Any]]:
    try:
        with open(_index_path(), "r", encoding="utf-8") as handle:
            value = json.load(handle)
        return value if isinstance(value, dict) else {}
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return {}


def _save_index(index: dict[str, dict[str, Any]]) -> None:
    target = _index_path()
    try:
        os.makedirs(os.path.dirname(target), exist_ok=True)
        temporary = f"{target}.tmp"
        with open(temporary, "w", encoding="utf-8") as handle:
            json.dump(index, handle, indent=2, ensure_ascii=False)
        os.replace(temporary, target)
    except OSError:
        # Indexing should never make a download or a library read fail.
        return


def _tag_string(tags: Any, names: tuple[str, ...], default: str = "") -> str:
    if tags is None:
        return default
    value = None
    for name in names:
        try:
            if name in tags:
                value = tags[name]
                break
        except (KeyError, TypeError):
            continue
    if hasattr(value, "value"):
        value = value.value
    if isinstance(value, (list, tuple)):
        value = "; ".join(str(item) for item in value if item is not None)
    if value is None:
        return default
    return str(value).strip() or default


def _tag_number(value: str) -> int | None:
    match = re.search(r"\d+", value or "")
    return int(match.group(0)) if match else None


def _normalise(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (value or "").casefold()).strip()


def _duplicate_key(artist: str, title: str, album: str) -> str:
    # A filename-only entry is not useful for duplicate detection because
    # downloads commonly use the same fallback name in different folders.
    if not title or not artist:
        return ""
    return "|".join((_normalise(artist), _normalise(title), _normalise(album)))


def _read_file(path: str) -> dict[str, Any]:
    stat = os.stat(path)
    extension = Path(path).suffix.lower()
    title = Path(path).stem
    artist = ""
    album_artist = ""
    album = ""
    genre = ""
    year = ""
    lyrics = ""
    metadata_error = ""
    has_artwork = False
    track_number = None
    disc_number = None
    duration = None
    bitrate = None
    sample_rate = None
    channels = None

    try:
        media = MutagenFile(path, easy=True)
        if media is not None:
            tags = media.tags
            title = _tag_string(tags, ("title",), title)
            artist = _tag_string(tags, ("artist", "albumartist"))
            album_artist = _tag_string(tags, ("albumartist", "album_artist", "artist"))
            album = _tag_string(tags, ("album",))
            genre = _tag_string(tags, ("genre",))
            year = _tag_string(tags, ("date", "year"))
            lyrics = _tag_string(tags, ("lyrics", "unsyncedlyrics", "USLT"))
            track_number = _tag_number(_tag_string(tags, ("tracknumber",)))
            disc_number = _tag_number(_tag_string(tags, ("discnumber",)))
            info = getattr(media, "info", None)
            if info is not None:
                duration = round(float(getattr(info, "length", 0) or 0), 3) or None
                bitrate = int(getattr(info, "bitrate", 0) or 0) or None
                sample_rate = int(getattr(info, "sample_rate", 0) or 0) or None
                channels = int(getattr(info, "channels", 0) or 0) or None
            raw_tags = getattr(MutagenFile(path), "tags", None)
            if raw_tags:
                has_artwork = any(
                    any(token in str(key).casefold() for token in ("apic", "covr", "picture", "artwork"))
                    for key in raw_tags.keys()
                )
    except Exception as exc:
        # A corrupt tag must not hide the file from the local library.
        metadata_error = str(exc)

    # music_tag exposes artwork and lyrics consistently across MP3, FLAC,
    # M4A, and OGG, so use it as a second lightweight metadata check.
    try:
        tagged = music_tag.load_file(path)
        if not album_artist:
            album_artist = _tag_string(tagged, ("albumartist", "album_artist", "artist"))
        if not lyrics:
            lyrics = _tag_string(tagged, ("lyrics", "unsyncedlyrics"))
        if not has_artwork and "artwork" in tagged:
            artwork = tagged["artwork"]
            value = getattr(artwork, "value", artwork)
            has_artwork = bool(getattr(value, "data", None) or getattr(value, "raw", None))
    except Exception as exc:
        if not metadata_error:
            metadata_error = str(exc)

    relative_paths = []
    for root in library_roots():
        if _within(path, root):
            relative_paths.append(os.path.relpath(path, root))
            break

    return {
        "id": hashlib.sha1(_path_key(path).encode("utf-8")).hexdigest(),
        "path": _absolute(path),
        "relative_path": relative_paths[0] if relative_paths else os.path.basename(path),
        "filename": os.path.basename(path),
        "format": extension.removeprefix("."),
        "size": int(stat.st_size),
        "modified_at": int(stat.st_mtime),
        "title": title,
        "artist": artist,
        "album_artist": album_artist,
        "album": album,
        "genre": genre,
        "year": year,
        "release_date": year,
        "lyrics": lyrics,
        "has_artwork": has_artwork,
        "metadata_complete": bool(title and artist and album),
        "metadata_error": metadata_error,
        "track_number": track_number,
        "disc_number": disc_number,
        "duration_seconds": duration,
        "bitrate": bitrate,
        "sample_rate": sample_rate,
        "channels": channels,
        "duplicate_key": _duplicate_key(artist, title, album),
    }


def _iter_audio_files() -> list[str]:
    paths: list[str] = []
    for root in library_roots():
        if not os.path.isdir(root):
            continue
        for current, directories, files in os.walk(root):
            directories[:] = [directory for directory in directories if not directory.startswith(".")]
            for filename in files:
                if filename == INDEX_FILENAME or filename.startswith("~"):
                    continue
                path = os.path.join(current, filename)
                if os.path.splitext(filename)[1].lower() in AUDIO_EXTENSIONS and os.path.isfile(path):
                    paths.append(path)
    return paths


def _sort_value(item: dict[str, Any], sort: str) -> Any:
    if sort == "date":
        return -(item.get("modified_at") or 0)
    if sort == "size":
        return -(item.get("size") or 0)
    return str(item.get(sort, "") or "").casefold()


def scan_library(
    query: str = "",
    sort: str = "artist",
    sort_descending: bool = False,
    duplicates_only: bool = False,
    missing_artwork: bool = False,
    failed_metadata: bool = False,
    file_format: str = "",
    artist: str = "",
    genre: str = "",
    date_from: int = 0,
    date_to: int = 0,
) -> dict[str, Any]:
    """Scan configured roots and return a JSON-safe library response."""
    query_value = (query or "").casefold().strip()
    with _index_lock:
        index = _load_index()
        items: list[dict[str, Any]] = []
        for path in _iter_audio_files():
            try:
                item = _read_file(path)
            except OSError:
                continue
            previous = index.get(_path_key(path), {})
            for key in (
                "source_url",
                "source_service",
                "source_type",
                "source_id",
                "playlist_name",
                "playlist_by",
                "playlist_number",
            ):
                if previous.get(key) is not None:
                    item[key] = previous[key]
            item["last_seen"] = int(time.time())
            index[_path_key(path)] = item
            items.append(item)

        duplicate_counts: dict[str, int] = {}
        for item in items:
            key = item.get("duplicate_key")
            if key:
                duplicate_counts[key] = duplicate_counts.get(key, 0) + 1
        for item in items:
            item["duplicate_count"] = duplicate_counts.get(item.get("duplicate_key", ""), 0)
            item["is_duplicate"] = item["duplicate_count"] > 1

        if query_value:
            items = [
                item
                for item in items
                if query_value in " ".join(
                    str(item.get(field, ""))
                    for field in ("title", "artist", "album", "genre", "filename")
                ).casefold()
            ]
        if duplicates_only:
            items = [item for item in items if item.get("is_duplicate")]
        if missing_artwork:
            items = [item for item in items if not item.get("has_artwork")]
        if failed_metadata:
            items = [item for item in items if not item.get("metadata_complete") or item.get("metadata_error")]
        if file_format:
            wanted_format = file_format.casefold().lstrip(".")
            items = [item for item in items if str(item.get("format", "")).casefold() == wanted_format]
        if artist:
            wanted_artist = artist.casefold().strip()
            items = [item for item in items if wanted_artist in str(item.get("artist", "")).casefold()]
        if genre:
            wanted_genre = genre.casefold().strip()
            items = [item for item in items if wanted_genre in str(item.get("genre", "")).casefold()]
        if date_from:
            items = [item for item in items if int(item.get("modified_at", 0) or 0) >= int(date_from)]
        if date_to:
            items = [item for item in items if int(item.get("modified_at", 0) or 0) <= int(date_to)]

        allowed_sorts = {"title", "artist", "album", "genre", "date", "size"}
        sort_key = sort if sort in allowed_sorts else "artist"
        items.sort(key=lambda item: (_sort_value(item, sort_key), str(item.get("title", "")).casefold()), reverse=sort_descending)
        _save_index(index)

    return {
        "items": items,
        "count": len(items),
        "duplicate_count": sum(1 for item in items if item.get("is_duplicate")),
        "roots": library_roots(),
        "storage_used": sum(int(item.get("size", 0) or 0) for item in items),
        "scanned_at": int(time.time()),
    }


def export_index() -> dict[str, dict[str, Any]]:
    """Return the provenance and metadata index for backup/export."""
    with _index_lock:
        return _load_index()


def import_index(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    clean = {str(key): item for key, item in value.items() if isinstance(item, dict)}
    with _index_lock:
        _save_index(clean)
    return True


def verify_file(path: str) -> dict[str, Any]:
    """Validate that a library audio file exists and can be parsed."""
    normalized = _absolute(path)
    if not is_allowed_path(normalized):
        raise ValueError("File is outside the configured music library")
    size = os.path.getsize(normalized)
    if size < 4096:
        return {"path": normalized, "valid": False, "reason": "File is incomplete or too small", "size": size}
    try:
        media = MutagenFile(normalized)
        info = getattr(media, "info", None) if media is not None else None
        valid = media is not None and info is not None
        return {"path": normalized, "valid": valid, "reason": "" if valid else "Audio metadata could not be read", "size": size}
    except Exception as exc:
        return {"path": normalized, "valid": False, "reason": str(exc), "size": size}


def remember_item(item: dict[str, Any], file_path: str) -> None:
    """Persist download provenance so a missing file can be re-downloaded."""
    if not file_path or not is_allowed_path(file_path, allow_missing=False):
        return
    try:
        record = _read_file(_absolute(file_path))
    except (OSError, ValueError):
        return
    record.update(
        {
            "source_url": item.get("item_url") or _source_url(item),
            "source_service": item.get("item_service", ""),
            "source_type": item.get("item_type", "track"),
            "source_id": item.get("item_id", ""),
            "playlist_name": item.get("playlist_name", ""),
            "playlist_by": item.get("playlist_by", ""),
            "playlist_number": item.get("playlist_number", ""),
            "last_seen": int(time.time()),
        }
    )
    with _index_lock:
        index = _load_index()
        index[_path_key(file_path)] = record
        _save_index(index)


def _source_url(item: dict[str, Any]) -> str:
    service = item.get("item_service")
    item_type = item.get("item_type", "track")
    item_id = item.get("item_id", "")
    if service == "spotify" and item_type == "track" and item_id:
        return f"https://open.spotify.com/track/{item_id}"
    if service == "spotify" and item_type == "album" and item_id:
        return f"https://open.spotify.com/album/{item_id}"
    if service == "spotify" and item_type == "playlist" and item_id:
        return f"https://open.spotify.com/playlist/{item_id}"
    return ""


def missing_items(query: str = "") -> list[dict[str, Any]]:
    """Return indexed downloads whose file no longer exists."""
    query_value = (query or "").casefold().strip()
    with _index_lock:
        index = _load_index()
        result = []
        for item in index.values():
            path = item.get("path", "")
            if os.path.isfile(path) or not item.get("source_url"):
                continue
            if query_value and query_value not in json.dumps(item, ensure_ascii=False).casefold():
                continue
            result.append(item)
    result.sort(key=lambda item: str(item.get("title", "")).casefold())
    return result


def remove_missing_items(paths: list[str] | None = None) -> int:
    """Forget missing entries from the provenance index without touching files.

    The library index may outlive a file that was moved or deleted outside
    OnTheSpot.  Removing one of these records only clears its saved metadata;
    it never deletes a file from the music folder.
    """
    requested = {
        _path_key(path)
        for path in (paths or [])
        if path and is_allowed_path(path, allow_missing=True)
    }
    if paths and not requested:
        return 0

    with _index_lock:
        index = _load_index()
        removed = 0
        for key, item in list(index.items()):
            path = str(item.get("path", ""))
            if not path or os.path.isfile(path) or not item.get("source_url"):
                continue
            if requested and _path_key(path) not in requested:
                continue
            index.pop(key, None)
            removed += 1
        if removed:
            _save_index(index)
    return removed


def rename_file(path: str, new_name: str) -> dict[str, Any]:
    normalized = _absolute(path)
    if not is_allowed_path(normalized):
        raise ValueError("File is outside the configured music library")
    clean_name = os.path.basename((new_name or "").strip())
    if not clean_name or clean_name in {".", ".."} or clean_name != (new_name or "").strip():
        raise ValueError("New name must be a file name in the same folder")
    if not os.path.splitext(clean_name)[1]:
        clean_name += os.path.splitext(normalized)[1]
    target = os.path.join(os.path.dirname(normalized), clean_name)
    if _path_key(target) != _path_key(normalized) and os.path.exists(target):
        raise FileExistsError("A file with that name already exists")
    os.replace(normalized, target)
    with _index_lock:
        index = _load_index()
        previous = index.pop(_path_key(normalized), {})
        index[_path_key(target)] = {**previous, **_read_file(target)}
        _save_index(index)
    return _read_file(target)


def update_metadata(path: str, changes: dict[str, Any]) -> dict[str, Any]:
    normalized = _absolute(path)
    if not is_allowed_path(normalized):
        raise ValueError("File is outside the configured music library")
    tags = music_tag.load_file(normalized)
    field_map = {
        "title": "title",
        "artist": "artist",
        "album": "album",
        "album_artist": "albumartist",
        "genre": "genre",
        "year": "year",
        "release_date": "year",
        "track_number": "tracknumber",
        "disc_number": "discnumber",
        "lyrics": "lyrics",
    }
    for field, tag_name in field_map.items():
        if field in changes and changes[field] is not None:
            tags[tag_name] = str(changes[field])
    tags.save()
    return _read_file(normalized)


def update_cover(path: str, image_data: bytes) -> dict[str, Any]:
    normalized = _absolute(path)
    if not is_allowed_path(normalized):
        raise ValueError("File is outside the configured music library")
    if not image_data:
        raise ValueError("Cover art is empty")
    # Validate the image before writing it into the audio container.
    try:
        from PIL import Image

        with Image.open(io.BytesIO(image_data)) as image:
            image.verify()
    except Exception as exc:
        raise ValueError("Cover art must be a valid image") from exc
    tags = music_tag.load_file(normalized)
    tags["artwork"] = image_data
    tags.save()
    return _read_file(normalized)


def read_cover(path: str) -> tuple[bytes, str]:
    """Return embedded or nearby cover art for a library file."""
    normalized = _absolute(path)
    if not is_allowed_path(normalized):
        raise ValueError("File is outside the configured music library")

    try:
        tags = music_tag.load_file(normalized)
        artwork_item = tags["artwork"]
        artwork = getattr(artwork_item, "value", artwork_item)
        data = getattr(artwork, "data", None) or getattr(artwork, "raw", None)
        mime = getattr(artwork, "mime", None) or "image/jpeg"
        if data:
            return bytes(data), str(mime)
    except (KeyError, OSError, ValueError, TypeError):
        pass

    # Downloads can also leave a sidecar cover beside the audio file.
    directory = os.path.dirname(normalized)
    for stem in ("cover", "folder", "front", "album"):
        for extension in (".jpg", ".jpeg", ".png", ".webp"):
            candidate = os.path.join(directory, stem + extension)
            if os.path.isfile(candidate):
                with open(candidate, "rb") as handle:
                    data = handle.read()
                mime = mimetypes.guess_type(candidate)[0] or "image/jpeg"
                if data:
                    return data, mime

    raise ValueError("No cover art found")


def write_m3u(name: str, paths: list[str]) -> str:
    """Write a safe M3U/M3U8 playlist from library paths."""
    roots = library_roots()
    if not roots:
        raise ValueError("No music library root is configured")
    clean_name = os.path.basename((name or "").strip())
    if not clean_name or clean_name != (name or "").strip():
        raise ValueError("Playlist name must be a simple file name")
    extension = ".m3u8" if config.get("m3u_format") == "m3u8" else ".m3u"
    if not clean_name.lower().endswith((".m3u", ".m3u8")):
        clean_name += extension
    target = os.path.join(roots[0], clean_name)
    valid_paths = [_absolute(path) for path in paths if is_allowed_path(path)]
    if not valid_paths:
        raise ValueError("No valid library files were supplied")
    with open(target, "w", encoding="utf-8") as handle:
        handle.write("#EXTM3U\n")
        for path in valid_paths:
            handle.write(f"{path}\n")
    return target
