import os
import threading
import time
import json
import uuid
import re
from contextlib import asynccontextmanager
import mimetypes


import uvicorn
from pydantic import BaseModel
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse

# dev env flag for protobufs
# os.environ["PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION"] = "python"


from .api.generic import generic_add_account
from .api.apple_music import apple_music_add_account
from .api.bandcamp import bandcamp_add_account
from .api.deezer import deezer_add_account
from .api.qobuz import qobuz_add_account
from .api.soundcloud import soundcloud_add_account
from .api.crunchyroll import crunchyroll_add_account
from .api.spotify import spotify_new_session
from .api.tidal import tidal_add_account_pt1, tidal_add_account_pt2

from .accounts import FillAccountPool
from .parsingworker import ParsingWorker
from .otsconfig import config
from .parse_item import get_search_results
from .runtimedata import (
    get_logger,
    pending,
    download_queue,
    download_queue_lock,
    parsing,
    websocket_queue,
    account_pool,
    notification_hook,
)
from .downloader import DownloadWorker, RetryWorker
from .constants import ItemStatus
from .utils import retry_single_item, is_latest_release


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
    logger.info("Initializing...")

    yield

    parsing_worker.stop()
    downloadworker.stop()
    fillaccountpool.stop()
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


# ---------------------------------------------------------------------------
# API ENDPOINTS
# ---------------------------------------------------------------------------


##QUERY ENDPOINTS


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
    return dict(sorted(download_queue.items()))


@app.get("/queue/pending")
async def get_pending_queue():
    return pending.get_items()


@app.post("/queue/pending/action")
async def pending_action(lid: str, action: str):
    """
    Endpoint to perform actions on a specific item in the pending queue.

    :param lid: Local ID of the item.
    :param action: Action to perform (e.g., retry, cancel, delete).
    :return: Boolean indicating success or failure of the action.
    """

    for item in pending.get_items():
        if item["local_id"] == lid:
            match action:
                case "cancel":
                    pending.remove(item)
                    return True
                case _:
                    return False


@app.get("/queue/downloads/clear")
async def remove_queue_items(status: str = "Completed"):
    """
    Endpoint to clear items from the download queue based on their status.

    :param status: Status of items to be removed. Defaults to "Completed".
    """
    with download_queue_lock:
        if status != "all":
            for key, item in download_queue.items():
                if (
                    item["item_status"] == status
                    or item["item_status"] == "Already Exists"
                ):
                    download_queue.pop(key)
                    return
        else:
            download_queue.clear()


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
                        item["item_status"] = ItemStatus.CANCELLED
                        return True
                    case "delete":
                        download_queue.pop(key)
                        return True
                    case _:
                        return False
    if retry_item is not None:
        retry_single_item(retry_item)


@app.get("/queue/downloads/retryfailed")
async def retry_failed_items():
    """
    Endpoint to retry all failed or cancelled items in the download queue.
    """
    with download_queue_lock:
        found_items = []
        for local_id, item in download_queue.items():
            if item["available"] is False:
                continue
            # ---- Skip terminal-state items --------------------------------
            terminal_statuses = {
                ItemStatus.CANCELLED,
                ItemStatus.FAILED,
                ItemStatus.DELETED,
            }
            if item["item_status"] in terminal_statuses:
                item["available"] = True
            item["item_status"] = ItemStatus.WAITING
            found_items.append(item)

        for item in found_items:
            del download_queue[item["local_id"]]
            pending.put_nowait(item)


@app.get("/queue/downloads/download")
async def download_file(lid):
    """
    Endpoint to download a file by its local ID.

    :param lid: Local ID of the item to download.
    :return: File response containing the downloaded file.
    """
    # Returns the file with appropriate headers
    for local_id, item in download_queue.items():
        if local_id == lid:
            file_path = item["file_path"]
            directory, file_name = os.path.split(file_path)
            break
    return FileResponse(file_path, media_type="audio/mpeg", filename=file_name)


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


@app.post("/config/reset")
async def reset_config():
    """
    Endpoint to reset the configuration to default settings.

    :return: Result of resetting the configuration.
    """
    return config.reset()


@app.get("/config/version")
async def check_version():
    # the update available notification is pushed directly by the function
    # returns true if new version available
    return is_latest_release()


# ACCOUNTS ENDPOINTS
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
    return account_pool


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


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
