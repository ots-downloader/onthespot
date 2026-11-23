"""Small, self-contained file helpers for manual metadata writes.

This module intentionally does not depend on the legacy library index. It owns
download-root validation and safe copying; the actual tag/artwork writes are
delegated to the existing :mod:`onthespot.utils` helpers so manual identify
behaves the same as a normal download.
"""

from __future__ import annotations

import os
import shutil
from collections.abc import Mapping
from typing import Any

from .otsconfig import config
from .utils import embed_metadata, set_music_thumbnail

# Manual identify uses short, format-agnostic keys. embed_metadata() expects
# the same key names the download worker passes from service metadata.
_EMBED_KEY_MAP = {
    "title": "title",
    "artist": "artists",
    "album": "album",
    "album_artist": "album_artists",
    "genre": "genre",
    "year": "year",
    "track_number": "track_number",
    "disc_number": "disc_number",
    "total_tracks": "total_tracks",
    "total_discs": "total_discs",
}


def _absolute(path: Any) -> str:
    return os.path.realpath(os.path.abspath(os.path.expanduser(str(path))))


def _roots() -> list[str]:
    values: list[Any] = [config.get("audio_download_path"), config.get("video_download_path")]
    profiles = config.get("download_profiles", []) or []
    for profile in profiles:
        if isinstance(profile, Mapping):
            values.append(profile.get("download_path"))
        else:
            values.append(getattr(profile, "download_path", None))

    roots: list[str] = []
    for value in values:
        if not value:
            continue
        root = _absolute(value)
        if root not in roots:
            roots.append(root)
    return roots


def is_allowed_path(path: Any, *, allow_missing: bool = False) -> bool:
    """Return whether *path* is inside a configured download root."""
    normalized = _absolute(path)
    if not allow_missing and not os.path.isfile(normalized):
        return False
    for root in _roots():
        try:
            if os.path.commonpath([normalized, root]) == root:
                return True
        except (OSError, ValueError):
            continue
    return False


def _require_file(path: Any) -> str:
    normalized = _absolute(path)
    if not os.path.isfile(normalized):
        raise FileNotFoundError(f"File not found: {normalized}")
    if not is_allowed_path(normalized):
        raise ValueError("The file is outside the configured download folders")
    return normalized


def copy_file(source: Any, target: Any) -> str:
    """Copy *source* to *target* without overwriting or removing either file."""
    source_path = _require_file(source)
    target_path = _absolute(target)
    if not is_allowed_path(target_path, allow_missing=True):
        raise ValueError("The target is outside the configured download folders")
    if os.path.normcase(source_path) == os.path.normcase(target_path):
        raise ValueError("Source and target paths must be different")
    if os.path.exists(target_path):
        raise FileExistsError("A file with that name already exists")

    os.makedirs(os.path.dirname(target_path), exist_ok=True)
    shutil.copy2(source_path, target_path)
    return target_path


def _embed_metadata_payload(changes: Mapping[str, Any]) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for key, value in changes.items():
        embed_key = _EMBED_KEY_MAP.get(key)
        if not embed_key or value is None or value == "":
            continue
        payload[embed_key] = value

    # embed_metadata() reads total_* directly when writing disc/track numbers.
    if "track_number" in payload or "disc_number" in payload:
        payload.setdefault("total_tracks", 1)
        payload.setdefault("total_discs", 1)
    return payload


def _item_payload(item: Any) -> dict[str, Any]:
    if isinstance(item, Mapping):
        return dict(item)
    model_dump = getattr(item, "model_dump", None)
    if callable(model_dump):
        dumped = model_dump()
        if isinstance(dumped, Mapping):
            return dict(dumped)
    return {}


def _temp_path(path: str) -> str:
    directory, name = os.path.split(path)
    stem, extension = os.path.splitext(name)
    return os.path.join(directory, "~" + stem + extension)


def update_tags(path: Any, changes: Mapping[str, Any], *, item: Any = None) -> dict[str, Any]:
    """Write *changes* to *path* with the shared ``embed_metadata`` helper."""
    normalized = _require_file(path)
    payload = _embed_metadata_payload(changes)
    item_data = _item_payload(item)
    embed_item = {
        "file_path": normalized,
        "item_service": item_data.get("item_service", ""),
        "item_id": item_data.get("item_id", ""),
    }

    try:
        embed_metadata(embed_item, payload)
    except Exception:
        # embed_metadata() renames the file before invoking ffmpeg. Put the
        # copy back if ffmpeg failed so a failed tag write cannot delete it.
        temp = _temp_path(normalized)
        if not os.path.exists(normalized) and os.path.exists(temp):
            os.replace(temp, normalized)
        raise

    return {
        key: value
        for key, value in changes.items()
        if key in _EMBED_KEY_MAP and value is not None and value != ""
    }


def update_artwork(path: Any, image_data: bytes) -> dict[str, bool]:
    """Embed cover *image_data* with the shared thumbnail helper."""
    normalized = _require_file(path)
    set_music_thumbnail(normalized, {"image_url": ""}, image_data=image_data)
    embedded = not config.get("raw_media_download") and bool(config.get("embed_cover"))
    return {"artwork": embedded}
