import os
import threading
import time
import json
import uuid
import re
import shutil
from urllib.parse import quote
from pathlib import Path
from typing import Any
from contextlib import asynccontextmanager
import mimetypes


import uvicorn
from pydantic import BaseModel
from fastapi import FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles

# dev env flag for protobufs
# os.environ["PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION"] = "python"


from .api.generic import generic_add_account
from .api.apple_music import apple_music_add_account
from .api.bandcamp import bandcamp_add_account
from .api.deezer import deezer_add_account
from .api.qobuz import qobuz_add_account
from .api.soundcloud import soundcloud_add_account
from .api.crunchyroll import crunchyroll_add_account
from .api.spotify import spotify_get_search_results, spotify_new_session
from .api.tidal import tidal_add_account_pt1, tidal_add_account_pt2

from .accounts import FillAccountPool, get_account_token
from .parsingworker import ParsingWorker
from .otsconfig import config
from .parse_item import get_search_results
from .runtimedata import (
    get_logger,
    pending,
    download_queue,
    download_queue_lock,
    download_paused,
    pending_lock,
    parsing,
    websocket_queue,
    account_pool,
    notification_hook,
    progress_hook,
    get_rate_limit_state,
)
from .downloader import DownloadWorker, RetryWorker
from .constants import ItemStatus
from .library import (
    is_allowed_path,
    missing_items,
    remove_missing_items,
    read_cover,
    rename_file,
    scan_library,
    export_index,
    import_index,
    verify_file,
    update_cover,
    update_metadata,
    write_m3u,
)
from .utils import format_local_id, open_item, retry_single_item
from .statistics import clear_history, export_history, get_statistics, import_history
from .updater import check_for_updates, install_update, start_update_checker, stop_update_checker
from .playlist_automation import PlaylistAutomationError, playlist_automation
from .export_locations import default_export_directory, playlist_backup_directory, set_default_export_directory, set_playlist_backup_directory, write_export_file


log_level = int(os.environ.get("LOG_LEVEL", 20))
logger = get_logger("gui")
# ---------------------------------------------------------------------------
# ONTHESPOT BOOTSTRAP
# ---------------------------------------------------------------------------

# define workers here to allow app to access them
# but start/stop them on lifespan events
parsing_worker = ParsingWorker()
downloadworker = DownloadWorker()
# spotifymirrorworker = MirrorSpotifyPlayback()
retryworker = RetryWorker()
fillaccountpool = FillAccountPool()


##ONTHESPOT BRIDGE FUNCTIONS
def add_spotify_account():
    """
    Initiates the process to add a Spotify account.
    """
    logger.info("Add spotify account clicked")
    login_worker = threading.Thread(target=add_spotify_account_worker)
    login_worker.daemon = True
    login_worker.start()


def add_spotify_account_worker():
    """
    Worker function to add a Spotify account.
    """
    if spotify_new_session():
        config.set("active_account_number", len(account_pool))
        config.save()
    else:
        logger.info("Account Already Exists")


def add_tidal_account():
    """
    Initiates the process to add a Tidal account.
    """
    logger.info("Add Tidal account clicked")
    device_code, verification_url = tidal_add_account_pt1()
    logger.info(
        "Login Service Started head to <a style='color: #6495ed;' href='https://%s'>https://%s</a> to continue.",
        verification_url,
        verification_url,
    )
    notification_hook(
        title="Continue Login - Go to the URL", url=f"https://{verification_url}"
    )
    login_worker = threading.Thread(
        target=add_tidal_account_worker, args=(device_code,)
    )
    login_worker.daemon = True
    login_worker.start()


def add_tidal_account_worker(device_code):
    """
    Worker function to complete the Tidal account addition.

    :param device_code: Device code required for Tidal login.
    """
    if tidal_add_account_pt2(device_code):
        config.set("active_account_number", len(account_pool))
        config.save()
        fillaccountpool.stop()
        time.sleep(1)
        relogin()
        notification_hook("Login Complete", "Refresh the page")
    else:
        logger.info("Account Already Exists")


def search(search_term, search_filters: dict | None = None) -> None:
    """
    Parse the url and add the item to the pending queue.
    """

    results = get_search_results(search_term)
    return results


def relogin():
    """
    Reloads the account pool to refresh accounts.
    """
    time.sleep(1)
    global fillaccountpool
    previous_worker = fillaccountpool
    if previous_worker is not None and previous_worker.is_running:
        previous_worker.stop()
    fillaccountpool = FillAccountPool()
    account_pool.clear()
    fillaccountpool.start()


# ---------------------------------------------------------------------------
# FASTAPI INIT
# ---------------------------------------------------------------------------


# START ONTHESPOT WORKERS HERE
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Context manager for FastAPI application lifecycle events.

    :param app: The FastAPI application instance.
    """
    logger.info("OnTheSpot Version: %s", config.get("version"))
    parsing_worker.start()
    downloadworker.start()
    if config.get("enable_retry_worker"):
        retryworker.start()
    fillaccountpool.start()
    start_update_checker(
        lambda title, message, url: notification_hook(title, message, url)
    )
    playlist_automation.start_scheduler()
    logger.info("Initializing...")

    yield

    parsing_worker.stop()
    downloadworker.stop()
    fillaccountpool.stop()
    stop_update_checker()
    playlist_automation.stop_scheduler()
    logger.info("Application shutdown")


app = FastAPI(lifespan=lifespan)

# Define allowed origins
origins = [
    "http://localhost:3000",
    "https://example.com",
]

# Register correct MIME types for frontend files
mimetypes.add_type("application/javascript", ".js")
mimetypes.add_type("application/wasm", ".wasm")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# Enabled Self-serving static frontend files from FastAPI. This could work for single binary deployment
# but we need to implement better path handling and a separate composer file
# app.frontend("/", directory="dist")


# Pydantic schemas of body data
class AccountData(BaseModel):
    username: str | None = None
    token: str | None = None


class YouTubeAuthentication(BaseModel):
    mode: str = "none"
    browser: str | None = None
    cookie_file: str | None = None


class QueueOrder(BaseModel):
    local_ids: list[str]


class QueueBatch(BaseModel):
    local_ids: list[str]
    action: str
    priority: int | None = None
    profile_id: str | None = None


class QueueVerify(BaseModel):
    local_ids: list[str] = []
    retry: bool = True


class DownloadProfile(BaseModel):
    id: str
    name: str
    format: str = "mp3"
    bitrate: str = "320k"
    download_path: str = ""


class ActiveProfile(BaseModel):
    profile_id: str


class LibraryPath(BaseModel):
    path: str


class LibraryPaths(BaseModel):
    paths: list[str] = []


class LibraryVerify(BaseModel):
    paths: list[str] = []


class LibraryRename(BaseModel):
    path: str
    new_name: str


class LibraryMetadata(BaseModel):
    path: str
    title: str | None = None
    artist: str | None = None
    album: str | None = None
    album_artist: str | None = None
    genre: str | None = None
    year: str | int | None = None
    release_date: str | None = None
    track_number: str | int | None = None
    disc_number: str | int | None = None
    lyrics: str | None = None


class LibraryM3U(BaseModel):
    name: str
    paths: list[str]


class LibraryOpen(BaseModel):
    path: str
    action: str = "folder"


# ---------------------------------------------------------------------------
# API ENDPOINTS
# ---------------------------------------------------------------------------


##QUERY ENDPOINTS


@app.get("/profiles")
async def get_download_profiles():
    return {
        "active": config.get("active_download_profile", ""),
        "profiles": config.get("download_profiles", []) or [],
    }


@app.post("/profiles")
async def save_download_profile(profile: DownloadProfile):
    profiles = list(config.get("download_profiles", []) or [])
    clean_id = re.sub(r"[^a-z0-9_-]+", "-", profile.id.lower()).strip("-")
    if not clean_id:
        clean_id = f"profile-{uuid.uuid4().hex[:8]}"
    value = profile.model_dump()
    value["id"] = clean_id
    value["format"] = profile.format.lstrip(".").lower()
    if value["format"] not in {"mp3", "flac", "m4a", "opus", "ogg", "wav"}:
        return {"success": False, "error": "Unsupported audio format"}
    value["bitrate"] = str(profile.bitrate or "320k")
    value["download_path"] = os.path.abspath(profile.download_path) if profile.download_path else ""
    profiles = [entry for entry in profiles if entry.get("id") != clean_id]
    profiles.append(value)
    config.set("download_profiles", profiles)
    if not config.get("active_download_profile"):
        config.set("active_download_profile", clean_id)
    config.save()
    return value


@app.post("/profiles/active")
async def set_active_download_profile(profile: ActiveProfile):
    profiles = config.get("download_profiles", []) or []
    if not any(entry.get("id") == profile.profile_id for entry in profiles):
        return {"success": False, "error": "Unknown profile"}
    config.set("active_download_profile", profile.profile_id)
    config.save()
    return {"success": True, "active": profile.profile_id}


@app.delete("/profiles/{profile_id}")
async def delete_download_profile(profile_id: str):
    profiles = [entry for entry in (config.get("download_profiles", []) or []) if entry.get("id") != profile_id]
    if not profiles:
        return {"success": False, "error": "At least one profile is required"}
    config.set("download_profiles", profiles)
    if config.get("active_download_profile") == profile_id:
        config.set("active_download_profile", profiles[0].get("id"))
    config.save()
    return {"success": True}


## LOCAL LIBRARY ENDPOINTS
@app.get("/library")
async def get_library(
    q: str = "",
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
):
    return scan_library(
        q,
        sort,
        sort_descending,
        duplicates_only,
        missing_artwork,
        failed_metadata,
        file_format,
        artist,
        genre,
        date_from,
        date_to,
    )


@app.post("/library/scan")
async def scan_local_library(
    q: str = "",
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
):
    return scan_library(
        q,
        sort,
        sort_descending,
        duplicates_only,
        missing_artwork,
        failed_metadata,
        file_format,
        artist,
        genre,
        date_from,
        date_to,
    )


@app.get("/library/missing")
async def get_missing_library_items(q: str = ""):
    return {"items": missing_items(q)}


@app.post("/library/verify")
async def verify_library_files(request: LibraryVerify):
    targets = request.paths
    if not targets:
        snapshot = scan_library()
        targets = [item.get("path", "") for item in snapshot.get("items", [])]
    results = []
    for path in targets:
        try:
            results.append(verify_file(path))
        except ValueError as exc:
            results.append({"path": path, "valid": False, "reason": str(exc), "size": 0})
    corrupt = [item for item in results if not item.get("valid")]
    return {
        "checked": len(results),
        "healthy": len(results) - len(corrupt),
        "corrupt": len(corrupt),
        "items": results,
    }


@app.get("/library/file")
async def get_library_file(path: str):
    if not is_allowed_path(path):
        raise HTTPException(status_code=404, detail="Library file not found")
    media_type = mimetypes.guess_type(path)[0] or "application/octet-stream"
    return FileResponse(path, media_type=media_type, filename=os.path.basename(path))


@app.post("/library/open")
async def open_library_item(request: LibraryOpen):
    if not is_allowed_path(request.path):
        raise HTTPException(status_code=404, detail="Library file not found")
    try:
        if request.action == "play":
            open_item(request.path)
        else:
            open_item(os.path.dirname(os.path.abspath(request.path)))
    except OSError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"success": True}


@app.post("/library/rename")
async def rename_library_item(request: LibraryRename):
    try:
        return {"success": True, "item": rename_file(request.path, request.new_name)}
    except FileExistsError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except OSError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/library/metadata")
async def update_library_metadata(request: LibraryMetadata):
    try:
        changes = request.model_dump(exclude={"path"}, exclude_none=True)
        return {"success": True, "item": update_metadata(request.path, changes)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except OSError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/library/cover")
async def update_library_cover(path: str = Form(...), cover: UploadFile = File(...)):
    try:
        data = await cover.read()
        return {"success": True, "item": update_cover(path, data)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except OSError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/library/cover")
async def get_library_cover(path: str):
    try:
        data, mime = read_cover(path)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except OSError as exc:
        raise HTTPException(status_code=404, detail="Cover art is unavailable") from exc
    return Response(content=data, media_type=mime, headers={"Cache-Control": "public, max-age=3600"})


@app.post("/library/m3u")
async def create_library_m3u(request: LibraryM3U):
    try:
        path = write_m3u(request.name, request.paths)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except OSError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"success": True, "path": path}


@app.post("/library/requeue")
async def requeue_missing_library_item(request: LibraryPath):
    target = os.path.normcase(os.path.abspath(os.path.expanduser(request.path)))
    record = next(
        (item for item in missing_items() if os.path.normcase(os.path.abspath(item.get("path", ""))) == target),
        None,
    )
    if record is None:
        raise HTTPException(status_code=404, detail="No missing indexed download matches that file")
    source_url = record.get("source_url")
    if not source_url:
        raise HTTPException(status_code=400, detail="This library entry has no source URL to re-download")

    local_id = format_local_id(record.get("source_id") or source_url)
    item = {
        "local_id": local_id,
        "item_url": source_url,
        "item_service": record.get("source_service", "generic"),
        "item_type": record.get("source_type", "track"),
        "item_id": record.get("source_id") or source_url,
        "parent_category": "library",
        "available": True,
        "item_status": ItemStatus.WAITING,
        "name": record.get("title", ""),
        "artist": record.get("artist", ""),
        "album": record.get("album", ""),
        "playlist_name": record.get("playlist_name", ""),
        "playlist_by": record.get("playlist_by", ""),
        "playlist_number": record.get("playlist_number", ""),
        "queue_position": 0,
        "priority": 0,
    }
    with download_queue_lock:
        item["queue_position"] = max(
            [entry.get("queue_position", -1) for entry in download_queue.values()],
            default=-1,
        ) + 1
        download_queue[local_id] = item
    pending.put_nowait(item)
    notification_hook("Added missing file", f"Queued {item['name'] or source_url} for re-download.")
    return {"success": True, "local_id": local_id, "item": item}


@app.delete("/library/missing")
async def remove_missing_library_items(request: LibraryPaths):
    removed = remove_missing_items(request.paths)
    if request.paths and not removed:
        raise HTTPException(status_code=404, detail="No missing indexed downloads match the selected entries")
    if removed:
        notification_hook("Library entries removed", f"Removed {removed} missing file entr{'y' if removed == 1 else 'ies'} from the library index.")
    return {"success": True, "removed": removed}


@app.post("/query/url")
async def query_url(q: str | None = None, filters: dict | None = None):
    """
    Endpoint to perform a URL-based search.

    :param q: The search term.
    :param filters: Optional dictionary of filters for the search.
    :return: Search results.
    """
    result = None
    if q:
        result = search(q, filters)
    return result


@app.get("/catalog/spotify")
async def search_spotify_catalog(q: str, types: str = "track"):
    """Search the Spotify public catalogue for the browse view."""
    content_types = [
        value
        for value in types.split(",")
        if value in {"track", "album", "artist", "playlist", "show", "episode"}
    ]
    if not content_types:
        content_types = ["track"]

    token = None
    try:
        if account_pool:
            token = get_account_token("spotify")
    except (IndexError, KeyError, TypeError):
        token = None

    # Client-credentials catalog searches do not need the paired user session,
    # but a paired session remains the fallback when no override is configured.
    if token is False and not config.get("spotify_webapi_override_client_id"):
        return []

    raw_results = spotify_get_search_results(
        token,
        q.strip(),
        content_types,
        search_prefix="",
    )
    return [
        {
            "id": item.get("item_id", ""),
            "item_id": item.get("item_id", ""),
            "item_service": item.get("item_service", "spotify"),
            "item_type": item.get("item_type", "track"),
            "name": item.get("item_name", ""),
            "artist": item.get("item_by", ""),
            "thumbnail": item.get("item_thumbnail_url", ""),
            "url": item.get("item_url", ""),
            "item_url": item.get("item_url", ""),
        }
        for item in raw_results
        if item.get("item_id") and item.get("item_url")
    ]


## @app.post("/spotify/mirror")
## async def mirror_spotify(state: bool = False):
##     """
##     Endpoint to control Spotify mirroring.
##
##     :param state: Boolean indicating whether to start or stop mirroring.
##     """
##     if state:
##         spotifymirrorworker.start()
##     else:
##         spotifymirrorworker.stop()


## QUEUES ENDPOINTS
@app.get("/queue/downloads")
async def query_download_queue():
    """
    Endpoint to get the current download queue.

    :return: Sorted dictionary of items in the download queue.
    """
    def sort_key(entry):
        local_id, item = entry
        position = item.get("queue_position", 10**9)
        priority = item.get("priority", 0)
        try:
            numeric_id = int(local_id)
        except (TypeError, ValueError):
            numeric_id = 10**9
        return (position, -priority, numeric_id)

    with download_queue_lock:
        return dict(sorted(download_queue.items(), key=sort_key))


@app.get("/queue/downloads/state")
async def query_download_state():
    with download_queue_lock:
        active = [
            item for item in download_queue.values()
            if item.get("item_status") in (ItemStatus.DOWNLOADING, ItemStatus.PAUSED)
        ]
        return {
            "paused": download_paused.is_set(),
            "active": len(active),
            "speed": sum(float(item.get("download_speed_bps", 0) or 0) for item in active),
            "eta_seconds": max(
                [item.get("eta_seconds") or 0 for item in active],
                default=0,
            ),
        }


@app.post("/queue/downloads/pause")
async def set_download_pause(paused: bool = True):
    if paused:
        download_paused.set()
        with download_queue_lock:
            for item in download_queue.values():
                if item.get("item_status") == ItemStatus.DOWNLOADING:
                    item["item_status"] = ItemStatus.PAUSED
                    notification_hook("Downloads paused", "The current track will resume from the queue.")
    else:
        download_paused.clear()
        with download_queue_lock:
            for item in download_queue.values():
                if item.get("item_status") == ItemStatus.PAUSED:
                    if item.get("_active_download"):
                        item["item_status"] = ItemStatus.DOWNLOADING
                    else:
                        item["item_status"] = ItemStatus.WAITING
        notification_hook("Downloads resumed", "The download queue is running again.")
    return {"paused": download_paused.is_set()}


@app.post("/queue/downloads/reorder")
async def reorder_download_queue(order: QueueOrder):
    requested = [str(local_id) for local_id in order.local_ids]
    with download_queue_lock:
        for position, local_id in enumerate(requested):
            if local_id in download_queue:
                download_queue[local_id]["queue_position"] = position
                download_queue[local_id]["priority"] = len(requested) - position

    # asyncio.Queue exposes its deque internally; the queue is only touched
    # while holding the same lock used by the parsing worker.
    with pending_lock:
        pending_items = list(pending._queue)
        pending_by_id = {str(item.get("local_id")): item for item in pending_items}
        ordered_pending = [pending_by_id[local_id] for local_id in requested if local_id in pending_by_id]
        ordered_ids = {str(item.get("local_id")) for item in ordered_pending}
        ordered_pending.extend(item for item in pending_items if str(item.get("local_id")) not in ordered_ids)
        pending._queue.clear()
        pending._queue.extend(ordered_pending)
    return {"success": True, "order": requested}


@app.post("/queue/downloads/batch")
async def batch_download_queue_action(batch: QueueBatch):
    """Apply one control to several queue items at once."""
    action = batch.action.strip().lower()
    allowed = {"pause", "resume", "retry", "cancel", "delete", "priority", "profile"}
    if action not in allowed:
        raise HTTPException(status_code=400, detail="Unsupported queue batch action")
    if action == "profile" and not batch.profile_id:
        raise HTTPException(status_code=400, detail="A profile is required")
    if action == "profile" and not any(
        entry.get("id") == batch.profile_id for entry in (config.get("download_profiles", []) or [])
    ):
        raise HTTPException(status_code=400, detail="Unknown download profile")

    selected: list[dict] = []
    retry_items: list[dict] = []
    changed = 0
    with download_queue_lock:
        for local_id in {str(value) for value in batch.local_ids}:
            item = download_queue.get(local_id)
            if item is None:
                continue
            selected.append(item)
            if action == "pause":
                item["_pause_requested"] = True
                item["item_status"] = ItemStatus.PAUSED
            elif action == "resume":
                item["_pause_requested"] = False
                if not item.get("_active_download"):
                    item["item_status"] = ItemStatus.WAITING
            elif action == "cancel":
                item["_pause_requested"] = False
                item["item_status"] = ItemStatus.CANCELLED
                item["error"] = "Cancelled by the user."
            elif action == "delete":
                if item.get("_active_download"):
                    item["_pause_requested"] = False
                    item["item_status"] = ItemStatus.CANCELLED
                    item["error"] = "Deleted by the user."
                else:
                    item["_discarded"] = True
                    download_queue.pop(local_id, None)
            elif action == "retry":
                retry_items.append(item)
            elif action == "priority":
                item["priority"] = int(batch.priority or 0)
            elif action == "profile":
                profile = next(
                    entry for entry in (config.get("download_profiles", []) or [])
                    if entry.get("id") == batch.profile_id
                )
                item["profile_id"] = profile.get("id")
                item["profile_name"] = profile.get("name", profile.get("id", "Default"))
            changed += 1

        if action == "priority":
            waiting = sorted(
                (item for item in download_queue.values() if item.get("item_status") == ItemStatus.WAITING),
                key=lambda item: (-int(item.get("priority", 0) or 0), int(item.get("queue_position", 10**9) or 10**9)),
            )
            for position, item in enumerate(waiting):
                item["queue_position"] = position

    for item in retry_items:
        retry_single_item(item)
    for item in selected:
        if action in {"pause", "resume", "cancel"}:
            progress_hook(item, int(item.get("progress", 0) or 0), item.get("item_status"))

    if action == "resume" and selected:
        notification_hook("Downloads resumed", f"Resumed {len(selected)} selected item(s).")
    return {"success": True, "changed": changed, "action": action}


@app.post("/queue/downloads/verify")
async def verify_download_queue(request: QueueVerify):
    """Check completed queue files and optionally put corrupt ones back in the queue."""
    with download_queue_lock:
        candidates = [
            item for item in download_queue.values()
            if item.get("item_status") in (ItemStatus.DOWNLOADED, ItemStatus.ALREADY_EXISTS)
            and (not request.local_ids or item.get("local_id") in request.local_ids)
        ]

    corrupt: list[dict] = []
    for item in candidates:
        path = item.get("file_path") or ""
        try:
            result = verify_file(path)
        except ValueError as exc:
            result = {"path": path, "valid": False, "reason": str(exc), "size": 0}
        if not result.get("valid"):
            item["item_status"] = ItemStatus.FAILED
            item["progress"] = 0
            item["error"] = f"Verification failed: {result.get('reason', 'invalid file')}"
            item["_stats_recorded"] = False
            corrupt.append(item)

    if request.retry:
        for item in corrupt:
            retry_single_item(item)
    return {
        "checked": len(candidates),
        "healthy": len(candidates) - len(corrupt),
        "corrupt": len(corrupt),
        "retried": len(corrupt) if request.retry else 0,
        "items": [{"local_id": item.get("local_id"), "error": item.get("error", "")} for item in corrupt],
    }


@app.get("/queue/downloads/clear")
async def remove_queue_items(status: str = "Completed"):
    """
    Endpoint to clear items from the download queue based on their status.

    :param status: Status of items to be removed. Defaults to "Completed".
    """
    with download_queue_lock:
        if status.lower() == "all":
            removed_count = len(download_queue)
            download_queue.clear()
            return removed_count

        normalized_status = status.lower()
        completed_status = normalized_status in {"completed", "downloaded"}
        failed_status = normalized_status in {"failed", "errors", "error"}
        failure_values = {ItemStatus.FAILED, ItemStatus.CANCELLED, ItemStatus.UNAVAILABLE}
        keys_to_remove = [
            key
            for key, item in download_queue.items()
            if item["item_status"] == status
            or (completed_status and item["item_status"] == "Already Exists")
            or (failed_status and item["item_status"] in failure_values)
        ]
        for key in keys_to_remove:
            download_queue.pop(key, None)
        return len(keys_to_remove)


@app.post("/queue/downloads/action")
async def queue_action(lid: str, action: str):
    """
    Endpoint to perform actions on a specific item in the download queue.

    :param lid: Local ID of the item.
    :param action: Action to perform (e.g., retry, cancel, delete).
    :return: Boolean indicating success or failure of the action.
    """

    retry_item = None
    with download_queue_lock:
        for key, item in download_queue.items():
            if item["local_id"] == lid:
                match action:
                    case "retry":
                        # need to retry later to free the lock
                        retry_item = item
                    case "cancel":
                        item["_pause_requested"] = False
                        item["item_status"] = ItemStatus.CANCELLED
                        item["error"] = "Cancelled by the user."
                        notification_hook("Download cancelled", item.get("name", "The current track"))
                        return True
                    case "delete":
                        if item.get("_active_download"):
                            item["_pause_requested"] = False
                            item["item_status"] = ItemStatus.CANCELLED
                            item["error"] = "Deleted by the user."
                        else:
                            item["_discarded"] = True
                            download_queue.pop(key)
                        return True
                    case _:
                        return False
    if retry_item is not None:
        retry_single_item(retry_item)
        return True
    return False


@app.get("/queue/downloads/retryfailed")
async def retry_failed_items():
    """
    Endpoint to retry all failed or cancelled items in the download queue.
    """
    retryable_statuses = {
        ItemStatus.CANCELLED,
        ItemStatus.FAILED,
        ItemStatus.UNAVAILABLE,
    }
    with download_queue_lock:
        found_items = [
            item
            for item in download_queue.values()
            if item.get("available", True) and item.get("item_status") in retryable_statuses
        ]
        for item in found_items:
            item["available"] = True
            item["item_status"] = ItemStatus.WAITING
            item["error"] = ""
            item["_stats_recorded"] = False
            item["retry_count"] = int(item.get("retry_count", 0) or 0) + 1
            download_queue.pop(item["local_id"], None)

    for item in found_items:
        pending.put_nowait(item)
    return {"success": True, "count": len(found_items)}


@app.get("/queue/downloads/download")
async def download_file(lid):
    """
    Endpoint to download a file by its local ID.

    :param lid: Local ID of the item to download.
    :return: File response containing the downloaded file.
    """
    file_path = None
    with download_queue_lock:
        item = download_queue.get(str(lid))
        if item is not None:
            file_path = item.get("file_path")
    if not file_path or not os.path.isfile(file_path):
        raise HTTPException(status_code=404, detail="Downloaded file not found")
    file_name = os.path.basename(file_path)
    media_type = mimetypes.guess_type(file_path)[0] or "application/octet-stream"
    return FileResponse(file_path, media_type=media_type, filename=file_name)


@app.get("/queue/pending")
async def query_pending_queue():
    """
    Endpoint to get the current pending queue.

    :return: Dictionary of items in the pending queue.
    """
    return pending


@app.get("/queue/parsing")
async def query_parsing_queue():
    """
    Endpoint to get the current parsing queue.

    :return: Dictionary of items in the parsing queue.
    """
    return parsing


## CONFIG ENDPOINTS
@app.get("/config/get")
async def get_config():
    """
    Endpoint to get the current configuration.

    :return: Current configuration settings.
    """
    return config


@app.post("/config/set")
async def set_config(nkey, nvalue):
    """
    Endpoint to set a configuration setting.

    :param nkey: Key of the configuration setting.
    :param nvalue: Value for the configuration setting.
    :return: Updated configuration setting.
    """
    if nvalue in ["false", "true"]:
        match nvalue:
            case "false":
                nvalue = False
            case "true":
                nvalue = True
            case _:
                pass
    return config.set(nkey, nvalue)


@app.post("/config/save")
async def save_config():
    """
    Endpoint to save the current configuration.

    :return: Result of saving the configuration.
    """
    return config.save()


@app.get("/exports/location")
async def get_export_location():
    return {"directory": default_export_directory()}


@app.post("/exports/location")
async def update_export_location(payload: dict[str, Any]):
    try:
        return {"directory": set_default_export_directory(str(payload.get("directory") or ""))}
    except OSError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/exports/playlist-backup-location")
async def get_playlist_backup_location():
    return {"directory": playlist_backup_directory()}


@app.post("/exports/playlist-backup-location")
async def update_playlist_backup_location(payload: dict[str, Any]):
    try:
        return {"directory": set_playlist_backup_directory(str(payload.get("directory") or ""))}
    except OSError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/exports/write")
async def write_text_export(payload: dict[str, Any]):
    filename = re.sub(r"[^A-Za-z0-9._-]+", "-", str(payload.get("filename") or "export.txt")).strip(".-") or "export.txt"
    stem, extension = os.path.splitext(filename)
    try:
        path = write_export_file(stem or "export", extension or ".txt", str(payload.get("content") or ""), str(payload.get("directory") or ""))
        return {"success": True, "path": path}
    except OSError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/exports/open-folder")
async def open_export_folder(payload: dict[str, Any]):
    try:
        directory = playlist_backup_directory() if payload.get("playlist_backups") else default_export_directory()
        os.makedirs(directory, exist_ok=True)
        open_item(directory)
        return {"success": True, "path": directory}
    except OSError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/config/reset")
async def reset_config():
    """
    Endpoint to reset the configuration to default settings.

    :return: Result of resetting the configuration.
    """
    return config.reset()


def _exportable_config() -> dict:
    raw = getattr(config, "_Config__config", {})
    exported = dict(raw) if isinstance(raw, dict) else {}
    exported["spotify_webapi_override_client_secret"] = "<redacted>"
    safe_accounts = []
    for account in exported.get("accounts", []) or []:
        if isinstance(account, dict):
            safe_accounts.append(
                {
                    "uuid": account.get("uuid", ""),
                    "service": account.get("service", ""),
                    "active": bool(account.get("active", True)),
                }
            )
    exported["accounts"] = safe_accounts
    return exported


@app.get("/config/export")
async def export_config():
    return JSONResponse(content=_exportable_config())


@app.post("/config/export-file")
async def export_config_file(payload: dict[str, Any]):
    try:
        path = write_export_file("onthespot-config", "json", json.dumps(_exportable_config(), indent=2, ensure_ascii=False), str(payload.get("directory") or ""))
        return {"success": True, "path": path}
    except OSError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/config/import")
async def import_config(payload: dict):
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Configuration must be a JSON object")
    protected = {"_ffmpeg_bin_path", "_log_file", "_cache_dir"}
    for key, value in payload.items():
        if key in protected or key.startswith("_"):
            continue
        if key == "spotify_webapi_override_client_secret" and value in {"", "<redacted>", None}:
            continue
        if key == "accounts" and isinstance(value, list):
            # Accounts contain authentication material and are deliberately
            # not imported from a redacted export.
            continue
        config.set(key, value)
    config.save()
    return {"success": True, "config": _exportable_config()}


def _safe_queue_snapshot() -> list[dict]:
    with download_queue_lock:
        snapshot = []
        for item in download_queue.values():
            safe = {
                key: value
                for key, value in item.items()
                if not key.startswith("_") and key not in {"token", "credentials", "login"}
            }
            snapshot.append(safe)
        return snapshot


@app.get("/statistics")
async def download_statistics():
    stats = get_statistics()
    library_snapshot = scan_library()
    with download_queue_lock:
        queue_counts: dict[str, int] = {}
        for item in download_queue.values():
            status = str(getattr(item.get("item_status", ""), "value", item.get("item_status", "")))
            queue_counts[status] = queue_counts.get(status, 0) + 1
    return {
        **stats,
        "storage_used": int(library_snapshot.get("storage_used", 0) or 0),
        "library_tracks": int(library_snapshot.get("count", 0) or 0),
        "queue_counts": queue_counts,
    }


@app.post("/statistics/clear")
async def clear_download_statistics():
    clear_history()
    return {"success": True}


# ---------------------------------------------------------------------------
# SPOTIFY PLAYLIST AUTOMATION
# ---------------------------------------------------------------------------

async def _playlist_operation(function, *args):
    try:
        return await run_in_threadpool(function, *args)
    except PlaylistAutomationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/playlist-automation/status")
async def playlist_automation_status():
    return playlist_automation.status()


@app.post("/playlist-automation/config")
async def configure_playlist_automation(payload: dict[str, Any]):
    return await _playlist_operation(
        playlist_automation.configure,
        str(payload.get("client_id") or ""),
        str(payload.get("client_secret") or ""),
        str(payload.get("redirect_uri") or ""),
    )


@app.get("/playlist-automation/login")
async def playlist_automation_login():
    try:
        return RedirectResponse(await _playlist_operation(playlist_automation.login_url))
    except HTTPException:
        raise


@app.get("/playlist-automation/callback")
async def playlist_automation_callback(code: str = "", state: str | None = None):
    try:
        await _playlist_operation(playlist_automation.callback, code, state)
        return RedirectResponse(f"{playlist_automation.application_url()}?tab=playlist-automation&playlist-automation=connected")
    except HTTPException as exc:
        message = quote(str(exc.detail))
        return RedirectResponse(f"{playlist_automation.application_url()}?tab=playlist-automation&playlist-automation=error&message={message}")


@app.post("/playlist-automation/logout")
async def playlist_automation_logout():
    return await _playlist_operation(playlist_automation.logout)


@app.get("/playlist-automation/playlists")
async def playlist_automation_playlists():
    return {"playlists": await _playlist_operation(playlist_automation.playlists)}


@app.post("/playlist-automation/scan")
async def playlist_automation_scan(payload: dict[str, Any]):
    return await _playlist_operation(playlist_automation.scan, payload)


@app.post("/playlist-automation/apply")
async def playlist_automation_apply(payload: dict[str, Any]):
    return await _playlist_operation(playlist_automation.apply, payload)


@app.post("/playlist-automation/sort/scan")
async def scan_selected_playlists_for_sorting(payload: dict[str, Any]):
    return {"playlists": await _playlist_operation(playlist_automation.sort_scan, payload)}


@app.post("/playlist-automation/sort/apply")
async def apply_selected_playlist_sorting(payload: dict[str, Any]):
    return await _playlist_operation(playlist_automation.sort_apply, payload)


@app.get("/playlist-automation/history")
async def playlist_automation_history():
    return {"history": playlist_automation.history()}


@app.delete("/playlist-automation/history")
async def clear_playlist_automation_history():
    playlist_automation.clear_history()
    return {"success": True}


@app.delete("/playlist-automation/history/{history_id}")
async def delete_playlist_automation_history(history_id: str):
    await _playlist_operation(playlist_automation.delete_history, history_id)
    return {"success": True}


@app.post("/playlist-automation/history/{history_id}/restore")
async def restore_playlist_automation_history(history_id: str):
    return await _playlist_operation(playlist_automation.restore_history, history_id)


@app.post("/playlist-automation/compare")
async def compare_playlist_automation(payload: dict[str, Any]):
    return await _playlist_operation(playlist_automation.compare, [str(value) for value in payload.get("playlist_ids", []) if value])


@app.post("/playlist-automation/remove-track")
async def remove_playlist_automation_track(payload: dict[str, Any]):
    return await _playlist_operation(playlist_automation.remove_track, str(payload.get("playlist_id") or ""), str(payload.get("track_uri") or ""))


@app.get("/playlist-automation/ignored")
async def get_ignored_playlist_tracks():
    return {"items": playlist_automation.ignored()}


@app.post("/playlist-automation/ignored")
async def add_ignored_playlist_track(payload: dict[str, Any]):
    return await _playlist_operation(playlist_automation.ignore, payload)


@app.delete("/playlist-automation/ignored")
async def remove_ignored_playlist_tracks(payload: dict[str, Any]):
    playlist_automation.remove_ignored([str(value) for value in payload.get("track_ids", []) if value])
    return {"success": True}


@app.get("/playlist-automation/configs")
async def get_playlist_automation_configs():
    return {"configs": playlist_automation.configs()}


@app.post("/playlist-automation/configs")
async def save_playlist_automation_config(payload: dict[str, Any]):
    return await _playlist_operation(playlist_automation.save_config, payload, str(payload.get("id") or "") or None)


@app.post("/playlist-automation/configs/reorder")
async def reorder_playlist_automation_configs(payload: dict[str, Any]):
    return {"configs": playlist_automation.reorder_configs([str(value) for value in payload.get("config_ids", []) if value])}


@app.delete("/playlist-automation/configs/{config_id}")
async def delete_playlist_automation_config(config_id: str):
    playlist_automation.delete_config(config_id)
    return {"success": True}


@app.post("/playlist-automation/configs/{config_id}/run")
async def run_playlist_automation_config(config_id: str):
    return await _playlist_operation(playlist_automation.run_config, config_id)


@app.post("/playlist-automation/configs/run-all")
async def run_all_playlist_automation_configs():
    return await _playlist_operation(playlist_automation.run_all_configs)


@app.get("/playlist-automation/export/config")
async def export_playlist_automation_config():
    return playlist_automation.export_config()


@app.post("/playlist-automation/export/config-file")
async def export_playlist_automation_config_file(payload: dict[str, Any]):
    try:
        path = write_export_file("playlist-automation-config", "json", json.dumps(playlist_automation.export_config(), indent=2, ensure_ascii=False), str(payload.get("directory") or ""))
        return {"success": True, "path": path}
    except OSError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/playlist-automation/import/config")
async def import_playlist_automation_config(payload: dict[str, Any]):
    playlist_automation.import_config(payload)
    return {"success": True}


@app.post("/playlist-automation/export/csv")
async def export_playlist_automation_csv(payload: dict[str, Any]):
    content = playlist_automation.export_csv(payload.get("tracks", []) if isinstance(payload.get("tracks", []), list) else [])
    return Response(
        content=content,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=playlist-automation.csv"},
    )


@app.post("/playlist-automation/export/playlists-csv")
async def export_selected_playlists_csv(payload: dict[str, Any]):
    content = await _playlist_operation(playlist_automation.export_playlists_csv, [str(value) for value in payload.get("playlist_ids", []) if value])
    return Response(
        content=content,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=spotify-playlists.csv"},
    )


@app.post("/playlist-automation/export/playlists-csv-file")
async def export_selected_playlists_csv_file(payload: dict[str, Any]):
    content = await _playlist_operation(playlist_automation.export_playlists_csv, [str(value) for value in payload.get("playlist_ids", []) if value])
    try:
        path = write_export_file("spotify-playlists", "csv", content, str(payload.get("directory") or ""))
        return {"success": True, "path": path}
    except OSError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/playlist-automation/export/playlists-csv")
async def download_selected_playlists_csv(playlist_ids: str = Query("")):
    identifiers = [value.strip() for value in playlist_ids.split(",") if value.strip()]
    content = await _playlist_operation(playlist_automation.export_playlists_csv, identifiers)
    return Response(
        content=content,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=spotify-playlists.csv"},
    )


@app.get("/playlist-automation/backups")
async def get_playlist_automation_backups():
    return {"backups": playlist_automation.backups()}


@app.post("/playlist-automation/backups")
async def create_playlist_automation_backup(payload: dict[str, Any]):
    return await _playlist_operation(playlist_automation.create_backup, [str(value) for value in payload.get("playlist_ids", []) if value])


@app.post("/playlist-automation/backups/restore")
async def restore_playlist_automation_backup(payload: dict[str, Any]):
    return await _playlist_operation(playlist_automation.restore_backup, str(payload.get("filename") or ""), str(payload.get("target_playlist_id") or ""))


@app.get("/playlist-automation/schedules")
async def get_playlist_automation_schedules():
    return {"schedules": playlist_automation.schedules()}


@app.post("/playlist-automation/schedules")
async def save_playlist_automation_schedule(payload: dict[str, Any]):
    return await _playlist_operation(playlist_automation.save_schedule, payload)


@app.delete("/playlist-automation/schedules/{schedule_id}")
async def delete_playlist_automation_schedule(schedule_id: str):
    playlist_automation.delete_schedule(schedule_id)
    return {"success": True}


@app.get("/backup/export")
async def export_backup():
    return JSONResponse(
        content={
            "version": 1,
            "created_at": int(time.time()),
            "settings": _exportable_config(),
            "download_profiles": config.get("download_profiles", []) or [],
            "queue": _safe_queue_snapshot(),
            "queue_history": export_history(),
            "library_metadata": export_index(),
        }
    )


@app.post("/backup/export-file")
async def export_backup_file(payload: dict[str, Any]):
    backup = payload.get("backup") if isinstance(payload.get("backup"), dict) else payload
    try:
        path = write_export_file("onthespot-backup", "json", json.dumps(backup, indent=2, ensure_ascii=False), str(payload.get("directory") or ""))
        return {"success": True, "path": path}
    except OSError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/backup/import")
async def import_backup(payload: dict):
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Backup must be a JSON object")
    settings = payload.get("settings") if isinstance(payload.get("settings"), dict) else payload
    protected = {"_ffmpeg_bin_path", "_log_file", "_cache_dir"}
    for key, value in settings.items():
        if key in protected or str(key).startswith("_"):
            continue
        if key in {"accounts", "spotify_webapi_override_client_secret"}:
            continue
        config.set(key, value)
    config.save()
    history_restored = import_history(payload.get("queue_history")) if payload.get("queue_history") is not None else False
    library_restored = import_index(payload.get("library_metadata")) if payload.get("library_metadata") is not None else False
    return {
        "success": True,
        "history_restored": history_restored,
        "library_restored": library_restored,
        "config": _exportable_config(),
    }


@app.get("/config/version")
async def check_version():
    # Keep this legacy boolean endpoint for the existing diagnostics view.
    status = await run_in_threadpool(check_for_updates)
    return not bool(status.get("update_available"))


@app.get("/updates/check")
async def updates_check(force: bool = False):
    """Return release metadata and the best asset for this platform."""
    return await run_in_threadpool(check_for_updates, force)


@app.post("/updates/install")
async def updates_install():
    """Download and stage an update where the current build supports it."""
    result = await run_in_threadpool(install_update)
    return JSONResponse(status_code=200, content=result)


# ACCOUNTS ENDPOINTS
@app.post("/accounts/youtube-auth")
async def configure_youtube_auth(authentication: YouTubeAuthentication):
    """Save explicit local-only yt-dlp authentication settings for YouTube."""
    allowed_browsers = {"chrome", "chromium", "edge", "firefox", "brave", "opera", "vivaldi"}
    mode = authentication.mode.strip().lower()
    if mode not in {"none", "browser", "cookie_file"}:
        raise HTTPException(status_code=400, detail="Unsupported YouTube authentication mode")

    browser = (authentication.browser or "").strip().lower()
    cookie_file = (authentication.cookie_file or "").strip()
    if mode == "browser" and browser not in allowed_browsers:
        raise HTTPException(status_code=400, detail="Choose a supported browser profile")
    if mode == "cookie_file":
        path = Path(cookie_file).expanduser()
        if not path.is_absolute() or not path.is_file():
            raise HTTPException(status_code=400, detail="Choose an existing absolute cookies-file path")
        cookie_file = str(path)

    config.set("youtube_auth_mode", mode)
    config.set("youtube_cookies_browser", browser if mode == "browser" else "")
    config.set("youtube_cookies_file", cookie_file if mode == "cookie_file" else "")
    config.save()
    status = "disabled" if mode == "none" else "configured"
    notification_hook("YouTube authentication updated", f"YouTube session authentication is {status}.")
    return {"success": True, "mode": mode, "browser": browser if mode == "browser" else "", "cookie_file": cookie_file if mode == "cookie_file" else ""}


@app.post("/accounts/add")
async def add_account(service: str, item: AccountData | None = None):
    """
    Endpoint to add an account for a specific service.

    :param service: The name of the service (e.g., "spotify", "tidal").
    :param item: Optional data required for adding the account.
    :return: Boolean indicating success or failure of account addition.
    """
    found = False
    match service:
        case "generic":
            generic_add_account()
            found = True
        case "spotify":
            add_spotify_account()
            # found = True
        case "tidal":
            add_tidal_account()
            # found = True
        case "applemusic":
            apple_music_add_account(item.token)
            found = True
        case "youtube":
            generic_add_account()
            found = True
        case "bandcamp":
            bandcamp_add_account()
            found = True
        case "qobuz":
            qobuz_add_account(item.username, item.token)
            found = True
        case "deezer":
            deezer_add_account(item.token)
            found = True
        case "soundcloud":
            soundcloud_add_account(oauth_token=item.token)
            found = True
        case "crunchyroll":
            crunchyroll_add_account(item.username, item.token)
            # found = True
        case _:
            raise NotImplementedError
    if found:
        relogin()
    notification_hook(title="Logging in...")
    return found


@app.post("/accounts/remove")
async def remove_account(luuid: str):
    """
    Endpoint to remove an account by its UUID.

    :param luuid: UUID of the account to be removed.
    :return: Boolean indicating success or failure of account removal.
    """
    index = None
    for idx, item in enumerate(account_pool):
        if item["uuid"] == luuid:
            index = idx
    if index is None:
        return None
    del account_pool[index]
    accounts = config.get("accounts").copy()
    del accounts[index]
    config.set("accounts", accounts)
    config.save()
    return True


@app.get("/accounts/get")
async def get_accounts():
    """
    Endpoint to get the list of all accounts.

    :return: List of accounts.
    """
    # librespot sessions and HTTP clients are present in the in-memory account
    # objects but are not JSON serializable (and should never be exposed to the
    # browser). Return only the account identity/status fields the UI needs.
    safe_accounts = []
    for account in account_pool:
        if not isinstance(account, dict):
            continue
        safe_accounts.append(
            {
                "uuid": account.get("uuid", ""),
                "service": account.get("service", ""),
                "active": bool(account.get("active", True)),
                # Never expose token/cookie-like login fields to the browser.
                # A Spotify/Tidal account name is safe to display; service
                # tokens are intentionally omitted.
                "username": account.get("username", "")
                if account.get("service") in {"spotify", "tidal", "qobuz"}
                else "",
            }
        )
    return safe_accounts


@app.get("/accounts/health")
async def get_account_health():
    configured = [
        account
        for account in (config.get("accounts", []) or [])
        if isinstance(account, dict) and account.get("active", True)
    ]
    authenticated_services = {
        account.get("service")
        for account in account_pool
        if isinstance(account, dict) and account.get("active", True)
    }
    configured_services = {account.get("service") for account in configured}
    missing_services = sorted(service for service in configured_services if service not in authenticated_services)
    spotify_online = "spotify" in authenticated_services
    return {
        "healthy": bool(configured) and not missing_services,
        "spotify": {
            "configured": "spotify" in configured_services,
            "connected": spotify_online,
            "status": "Connected" if spotify_online else ("Not configured" if "spotify" not in configured_services else "Needs reconnect"),
        },
        "configured_accounts": len(configured),
        "authenticated_accounts": len(account_pool),
        "missing_services": missing_services,
        "checked_at": time.time(),
    }


@app.post("/accounts/reconnect")
async def reconnect_accounts():
    relogin()
    notification_hook("Reconnecting accounts", "The account pool is refreshing in the background.")
    return {"success": True}


@app.get("/system/rate-limit")
async def get_system_rate_limit():
    return get_rate_limit_state()


@app.get("/system/diagnostics")
async def get_system_diagnostics():
    with download_queue_lock:
        status_counts: dict[str, int] = {}
        for item in download_queue.values():
            status = str(item.get("item_status", "Unknown"))
            status_counts[status] = status_counts.get(status, 0) + 1
    root = config.get("audio_download_path") or os.getcwd()
    try:
        usage = shutil.disk_usage(root)
        disk = {"total": usage.total, "free": usage.free, "used": usage.used}
    except OSError:
        disk = {"total": 0, "free": 0, "used": 0}
    rate_limit = get_rate_limit_state()
    spotify_status = playlist_automation.status()
    spotify_rate_limited = bool(rate_limit.get("active")) and "spotify" in str(rate_limit.get("host") or "").casefold()
    spotify_api_status = "Rate limited" if spotify_rate_limited else ("Connected" if spotify_status.get("authenticated") else ("Needs sign-in" if spotify_status.get("configured") else "Not configured"))
    return {
        "backend": {"status": "online", "version": config.get("version")},
        "workers": {
            "parsing": parsing_worker.thread.is_alive(),
            "downloads": downloadworker.thread.is_alive(),
            "accounts": bool(account_pool),
            "retry": retryworker.thread.is_alive() if config.get("enable_retry_worker") else False,
        },
        "queue": {
            "pending": pending.qsize(),
            "parsing": len(parsing),
            "downloads": len(download_queue),
            "statuses": status_counts,
            "paused": download_paused.is_set(),
        },
        "ffmpeg": {"path": config.get("_ffmpeg_bin_path", ""), "available": bool(config.get("_ffmpeg_bin_path"))},
        "disk": disk,
        "rate_limit": rate_limit,
        "spotify_api": {
            "configured": bool(spotify_status.get("configured")),
            "connected": bool(spotify_status.get("authenticated")),
            "status": spotify_api_status,
            "rate_limited": spotify_rate_limited,
            "seconds_remaining": int(rate_limit.get("seconds_remaining") or 0) if spotify_rate_limited else 0,
        },
    }


# LOGS ENDPOINTS
@app.get("/logs")
async def get_logs():
    """
    Endpoint to retrieve logs from the log file.

    :return: List of log entries.
    """
    log_path = config.get("_log_file")
    lines = None
    data = []
    with open(log_path, "r") as f:
        lines = f.readlines()
    for l in lines:
        main = re.findall(r"(\[*.+\])( -> *.+)", l)
        try:
            message = main[0][1]
        except IndexError:
            message = None
            data.append(
                {
                    "id": uuid.uuid4(),
                    "timestamp": "",
                    "level": "ERROR",
                    "message": l,
                }
            )
            continue

        try:
            log_info = re.findall(r"\[(.+?) :: (\w+?) :: (.+) :: (\w.+)]", main[0][0])
            date = log_info[0][0][:-4]
            source = log_info[0][2]
            level = log_info[0][3]
            formatted_message = main if message is None else source + message

        except IndexError:
            date = ""
            source = ""
            level = ""
            formatted_message = main if message is None else message
        data.append(
            {
                "id": uuid.uuid4(),
                "timestamp": date,
                "level": level,
                "message": formatted_message,
            }
        )
    return data


@app.get("/logs/download")
async def download_logs():
    """
    Returns the log file

    :return: List of log entries.
    """
    log_path = config.get("_log_file")
    directory, file_name = os.path.split(log_path)
    return FileResponse(log_path, media_type="text/plain", filename=file_name)


# SSE Methods and endpoint
async def event_generator(user_id: str, request: Request):
    """Listens for items in the user's queue and pushes them to the frontend."""
    # 1. Create a queue for this specific user connection

    try:
        while True:
            # 2. If the client disconnects, stop the generator
            if await request.is_disconnected():
                break

            # 3. Wait indefinitely for an event to be put in the queue
            # This does NOT use CPU. It just sleeps until data arrives.
            data = await websocket_queue.get()

            # 4. Push the data to the Vite frontend!
            yield f"data: {json.dumps(data, skipkeys=True)}\n\n"

    finally:
        # Cleanup when user closes the browser tab
        while not websocket_queue.empty():
            websocket_queue.get_nowait()


@app.get("/api/sse/{user_id}")
async def sse_endpoint(user_id: str, request: Request):
    """The Vite frontend connects here exactly ONCE."""
    return StreamingResponse(
        event_generator(user_id, request), media_type="text/event-stream"
    )


# The production UI is built by Vite into ui/dist and served by this same
# FastAPI process. Set ONTHESPOT_WEBUI_DIST when the files live elsewhere.
_workspace_root = Path(__file__).resolve().parents[3]
_ui_dist = Path(os.environ.get("ONTHESPOT_WEBUI_DIST") or _workspace_root / "ui" / "dist")
if _ui_dist.is_dir():
    app.mount("/", StaticFiles(directory=str(_ui_dist), html=True), name="web-ui")


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
