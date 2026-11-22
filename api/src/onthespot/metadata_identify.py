"""Manual track identification using iTunes metadata.

The queue detail UI lets a user correct the basic fields of a finished track,
search the iTunes catalog, pick a match, and apply it. Applying a match writes
tags and artwork to a **new copy** of the file: the original download is never
modified, moved, or deleted.
"""

from __future__ import annotations

import os
from collections.abc import Mapping, MutableMapping
from typing import Any

from pydantic import ValidationError

from .api.itunes import fetch_itunes_artwork, itunes_result_to_library_changes, itunes_search_candidates
from .basemodels import IdentifyApplyRequest, IdentifySearchRequest, QueueItem
from .constants import ItemStatus
from .library import copy_library_file, is_allowed_path, remember_item, update_cover, update_metadata
from .otsconfig import config
from .runtimedata import download_queue, download_queue_lock, get_logger, notification_hook
from .utils import format_item_path, sanitize_data

logger = get_logger("metadata_identify")

_FINISHED_STATUSES = {ItemStatus.DOWNLOADED.value, ItemStatus.ALREADY_EXISTS.value}
_AUDIO_ITEM_TYPES = {"track", "podcast_episode"}
_MAX_PATH_LENGTH = 260  # Keep in sync with DownloadWorker._MAX_PATH_LENGTH.


def _text(value: Any) -> str:
    if value is None or isinstance(value, bool):
        return ""
    return str(value).strip()


def _status_value(value: Any) -> str:
    return _text(getattr(value, "value", value))


def _item_snapshot(item: Any) -> dict[str, Any]:
    """Accept both QueueItem models and queue dicts (both exist in practice)."""
    if isinstance(item, Mapping):
        return dict(item)
    model_dump = getattr(item, "model_dump", None)
    if callable(model_dump):
        try:
            dumped = model_dump()
        except Exception:
            dumped = None
        if isinstance(dumped, Mapping):
            return dict(dumped)
    return {}


def _resolve_item(local_id: int) -> tuple[Any, dict[str, Any]]:
    with download_queue_lock:
        item = download_queue.get(local_id)
        if item is None:
            raise LookupError(f"Queue item {local_id} was not found")
        snapshot = _item_snapshot(item)
    return item, snapshot


def _validate_finished(snapshot: dict[str, Any]) -> str:
    status = _status_value(snapshot.get("item_status"))
    if status not in _FINISHED_STATUSES:
        raise ValueError("Identify is only available for finished downloads")
    if _text(snapshot.get("item_type")) not in _AUDIO_ITEM_TYPES:
        raise ValueError("Identify is only available for audio tracks")

    source = os.path.realpath(os.path.expanduser(_text(snapshot.get("file_path"))))
    if not source:
        raise ValueError("This item has no downloaded file path")
    if not os.path.isfile(source):
        raise ValueError("The downloaded file no longer exists")
    if not is_allowed_path(source):
        raise ValueError("The downloaded file is outside the configured music library")
    return source


def _fit_path_length(path: str) -> str:
    path = os.path.realpath(os.path.expanduser(path))
    directory, filename = os.path.split(path)
    name, extension = os.path.splitext(filename)
    available = _MAX_PATH_LENGTH - len(os.path.join(directory, ""))
    if available <= 0 or len(filename) <= available:
        return path
    name = name[: max(0, available - len(extension))]
    return os.path.join(directory, name + extension)


def _same_path(left: str, right: str) -> bool:
    return os.path.normcase(os.path.realpath(left)) == os.path.normcase(os.path.realpath(right))


def _unique_target(source: str, target: str) -> str:
    """Return a free target path, never resolving to *source* or an existing file."""
    target = _fit_path_length(target)
    if _same_path(source, target):
        base, extension = os.path.splitext(target)
        target = _fit_path_length(f"{base} - tagged{extension}")

    base, extension = os.path.splitext(target)
    counter = 2
    while os.path.exists(target):
        target = _fit_path_length(f"{base} ({counter}){extension}")
        counter += 1
    return target


def _profile_download_path(profile: Any) -> str:
    if isinstance(profile, Mapping):
        return _text(profile.get("download_path"))
    return _text(getattr(profile, "download_path", ""))


def _candidate_metadata(snapshot: dict[str, Any], candidate: Mapping) -> dict[str, Any]:
    """Build the metadata dict expected by the configured path formatter."""
    return {
        "title": _text(candidate.get("title")) or _text(snapshot.get("name")),
        "artists": _text(candidate.get("artist")) or _text(snapshot.get("artist")),
        "album_name": _text(candidate.get("album")) or _text(snapshot.get("album")),
        "album_artists": (
            _text(candidate.get("album_artist"))
            or _text(candidate.get("artist"))
            or _text(snapshot.get("artist"))
        ),
        "release_year": _text(candidate.get("release_year")),
        "genre": _text(candidate.get("genre")),
        "track_number": candidate.get("track_number") or 1,
        "disc_number": candidate.get("disc_number") or 1,
        "total_tracks": candidate.get("total_tracks") or "",
        "total_discs": candidate.get("total_discs") or "",
        "item_id": _text(snapshot.get("item_id")),
        "explicit": snapshot.get("explicit", False),
        "composer": _text(snapshot.get("composer")),
        "album_type": _text(snapshot.get("album_type")),
        "label": _text(snapshot.get("label")),
        "isrc": _text(snapshot.get("isrc")),
    }


def _target_path(source: str, snapshot: dict[str, Any], metadata: dict[str, Any]) -> str:
    root = _profile_download_path(snapshot.get("download_profile")) or _text(config.get("audio_download_path"))
    if not root:
        root = os.path.dirname(source)

    try:
        queue_item = QueueItem.model_validate(snapshot)
        relative = format_item_path(queue_item, metadata)
        # Download formatters intentionally omit the extension; the downloader
        # appends it after conversion, so mirror that for the tagged copy. Do
        # not use splitext() here: a dot in a title like "Song feat. Guest"
        # would be mistaken for an extension and no real suffix would be added.
        extension = os.path.splitext(source)[1]
        if extension and not relative.lower().endswith(extension.lower()):
            relative = relative + extension
        return os.path.join(os.path.expanduser(root), relative)
    except (ValidationError, TypeError, ValueError, KeyError, AttributeError) as exc:
        logger.warning("Could not apply the configured path formatter; using a simple name: %s", exc)
        artist = sanitize_data(metadata.get("artists") or "Unknown Artist") or "Unknown Artist"
        title = sanitize_data(metadata.get("title") or "Unknown Title") or "Unknown Title"
        extension = os.path.splitext(source)[1]
        return os.path.join(os.path.dirname(source), f"{artist} - {title}{extension}")


def _set_item_field(item: Any, key: str, value: Any) -> None:
    if isinstance(item, MutableMapping):
        item[key] = value
    else:
        setattr(item, key, value)


def search_manual_matches(request: IdentifySearchRequest) -> dict[str, Any]:
    """Search iTunes using queue values plus any user overrides."""
    _, snapshot = _resolve_item(request.local_id)
    _validate_finished(snapshot)

    title = _text(request.title) or _text(snapshot.get("name"))
    artist = _text(request.artist) or _text(snapshot.get("artist"))
    album = _text(request.album) or _text(snapshot.get("album"))
    country = _text(request.country) or _text(config.get("itunes_metadata_country", "US")) or "US"

    candidates = itunes_search_candidates(
        title,
        artist,
        album,
        country=country,
        limit=request.limit,
        length=snapshot.get("length"),
    )
    return {
        "query": {"title": title, "artist": artist, "album": album},
        "country": country,
        "candidates": candidates,
    }


def apply_manual_match(request: IdentifyApplyRequest) -> dict[str, Any]:
    """Write the chosen match to a new tagged copy and leave the original alone."""
    _, snapshot = _resolve_item(request.local_id)
    source = _validate_finished(snapshot)

    candidate = request.candidate.model_dump()
    metadata = _candidate_metadata(snapshot, candidate)
    target = _unique_target(source, _target_path(source, snapshot, metadata))

    # Copy first so every subsequent write touches only the new file.
    copy_library_file(source, target)

    changes = itunes_result_to_library_changes(candidate)
    updated = update_metadata(target, changes)

    warnings: list[str] = []
    if request.embed_artwork:
        try:
            artwork = fetch_itunes_artwork(candidate.get("image_url", ""))
            updated = update_cover(target, artwork)
        except Exception as exc:
            warnings.append(f"Artwork was not embedded: {exc}")
            logger.warning("Could not embed artwork for %s: %s", target, exc)

    try:
        remember_item(snapshot, target)
    except Exception as exc:
        warnings.append(f"Library index was not updated: {exc}")
        logger.warning("Could not index identified copy %s: %s", target, exc)

    applied = dict(snapshot)
    applied.update(
        {
            "file_path": target,
            "name": changes.get("title", applied.get("name", "")),
            "artist": changes.get("artist", applied.get("artist", "")),
            "album": changes.get("album", applied.get("album", "")),
        }
    )
    queue_updated = True
    with download_queue_lock:
        current = download_queue.get(request.local_id)
        if current is None:
            queue_updated = False
        else:
            _set_item_field(current, "file_path", target)
            _set_item_field(current, "name", applied["name"])
            _set_item_field(current, "artist", applied["artist"])
            _set_item_field(current, "album", applied["album"])

    if not queue_updated:
        warnings.append("The queue item disappeared while the tagged copy was being created")

    try:
        notification_hook("Track identified", f"Tagged copy saved to {target}")
    except Exception as exc:
        logger.warning("Could not send identify notification: %s", exc)

    return {
        "original_path": source,
        "file_path": target,
        "queue_updated": queue_updated,
        "item": applied,
        "metadata": updated,
        "warnings": warnings,
    }
