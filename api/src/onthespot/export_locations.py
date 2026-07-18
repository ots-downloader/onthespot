"""Safe local destinations for files exported by the web UI."""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

from .otsconfig import config


def default_export_directory() -> str:
    configured = str(config.get("export_folder_path") or "").strip()
    target = configured or os.path.join("~", "Documents", "OnTheSpot Exports")
    return str(Path(os.path.expandvars(os.path.expanduser(target))).resolve())


def resolve_export_directory(value: str = "") -> str:
    target = str(value or "").strip() or default_export_directory()
    directory = Path(os.path.expandvars(os.path.expanduser(target))).resolve()
    directory.mkdir(parents=True, exist_ok=True)
    if not directory.is_dir():
        raise OSError(f"Export location is not a folder: {directory}")
    return str(directory)


def set_default_export_directory(value: str) -> str:
    directory = resolve_export_directory(value)
    config.set("export_folder_path", directory)
    config.save()
    return directory


def playlist_backup_directory() -> str:
    configured = str(config.get("playlist_backup_folder_path") or "").strip()
    if configured:
        return str(Path(os.path.expandvars(os.path.expanduser(configured))).resolve())
    return str(Path(default_export_directory()) / "Playlist backups")


def set_playlist_backup_directory(value: str) -> str:
    directory = resolve_export_directory(value)
    config.set("playlist_backup_folder_path", directory)
    config.save()
    return directory


def write_export_file(filename_prefix: str, extension: str, content: str, directory: str = "") -> str:
    target = Path(resolve_export_directory(directory))
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    path = target / f"{filename_prefix}-{timestamp}.{extension.lstrip('.')}"
    path.write_text(content, encoding="utf-8", newline="")
    return str(path)
