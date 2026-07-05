import os
import sys
import threading
import time
import logging

import uuid
import re
import asyncio
from contextlib import asynccontextmanager
from logging.handlers import RotatingFileHandler

# os.environ["PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION"] = "python"
from .api.generic import generic_add_account
from .api.apple_music import apple_music_add_account
from .api.bandcamp import bandcamp_add_account
from .api.deezer import deezer_add_account
from .api.qobuz import qobuz_add_account
from .api.soundcloud import soundcloud_add_account
from .api.crunchyroll import crunchyroll_add_account
from .api.spotify import spotify_new_session, MirrorSpotifyPlayback
from .api.tidal import tidal_add_account_pt1, tidal_add_account_pt2

from .accounts import FillAccountPool
from .search import get_search_results
from .otsconfig import config
from .parse_item import ParsingWorker
from .runtimedata import (
    get_logger,
    pending,
    pending_lock,
    download_queue,
    download_queue_lock,
    parsing,
    websocket_queue,
    websocket_queue_lock,
    websocket_event,
    account_pool,
)
from .downloader import DownloadWorker, RetryWorker
from .constants import ItemStatus

import uvicorn
from pydantic import BaseModel
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse


log_level = int(os.environ.get("LOG_LEVEL", 20))
logger = get_logger("gui")
# ---------------------------------------------------------------------------
# ONTHESPOT BOOTSTRAP
# ---------------------------------------------------------------------------


def add_item_to_download_list(item, item_status: str | None = None):
    """
    Adds an item to the download queue with the specified status.

    :param item: Dictionary containing item details.
    :param item_status: Optional status for the item. Defaults to "Waiting" if not provided.
    """
    playlist_name = ""
    playlist_by = ""
    if item["parent_category"] == "playlist":
        item_category = f"Playlist: {item['playlist_name']}"
        playlist_name = item.get("playlist_name")
        playlist_by = item.get("playlist_by")
    elif item["parent_category"] in ("album", "show"):
        item_category = f"{item['parent_category'].title()}"
    else:
        item_category = f"{item['parent_category'].title()}"

    with download_queue_lock:
        download_queue[item["local_id"]] = {
            "local_id": item["local_id"],
            "available": True,
            "item_service": item["item_service"],
            "item_type": item["item_type"],
            "item_id": item["item_id"],
            "item_status": "Waiting" if not item_status else item_status,
            "file_path": None,
            "parent_category": item_category,
            "playlist_name": playlist_name,
            "playlist_by": playlist_by,
            "playlist_number": item.get("playlist_number"),
        }


class QueueWorker:
    """
    A worker class that processes items in the pending queue and adds them to the download list.
    """

    def __init__(self):
        super().__init__()
        self.is_running = True
        self.thread = threading.Thread(target=self.run)

    def start(self):
        """
        Starts the worker thread.
        """
        self.thread.start()

    def run(self):
        """
        Continuously processes items in the pending queue until stopped.
        """
        while self.is_running:
            if pending:
                try:
                    local_id = next(iter(pending))
                    with pending_lock:
                        item = pending.pop(local_id)

                    add_item_to_download_list(item)

                except Exception as e:
                    error_msg = f"Unknown Exception for {item}: {str(e)}"
                    logger.error(f"{error_msg}\nTraceback: {traceback.format_exc()}")

                    # Check if this is a permanent failure (e.g., max retries exhausted)
                    if item is None:
                        logger.warning(
                            f"Permanent failure detected for {item['item_id']}, will not retry. Adding to download list as Failed."
                        )

                        # Create user-friendly error message
                        error_str = str(e)
                        service = item["item_service"].replace("_", " ").title()
                        item_type = item["item_type"]

                        if "404" in error_str or "not found" in error_str.lower():
                            user_msg = f"Track not found: Could not load {item_type} from {service}. The item may have been removed or is unavailable in your region."
                        elif "Max retries" in error_str or "exhausted" in error_str:
                            user_msg = f"Failed to load {item_type} from {service} after multiple retries. The service may be experiencing issues."
                        else:
                            user_msg = f"Failed to load {item_type} from {service}: {error_str}"

                        # log error
                        logger.error(f"{user_msg}")

                        add_item_to_download_list(item, "Failed")
                    continue
            else:
                time.sleep(0.2)

    def stop(self):
        """
        Stops the worker thread and waits for it to finish.
        """
        logger.info("Stopping Queue Worker")
        self.is_running = False
        self.thread.join()


def notification_hook(
    title,
    message="",
    url="",
):
    """
    Sends a notification event through the websocket queue.

    :param title: The title of the notification.
    :param message: Optional message for the notification. Defaults to an empty string.
    :param url: Optional URL associated with the notification. Defaults to an empty string.
    """
    websocket_event(
        etype="Notification",
        event={
            "id": f"{uuid.uuid4()}",
            "url": f"{url}",
            "title": f"{title}",
            "message": f"{message}",
        },
    )


# define workers here to allow app to access them
# but start/stop them on lifespan events
parsing_worker = ParsingWorker()
queueworker = QueueWorker()
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
    Performs a search with optional filters.

    :param search_term: The term to search for.
    :param search_filters: Optional dictionary of content types to filter the search results.
    :return: Search results.
    """
    if not search_filters:
        search_filters = {
            "tracks": True,
            "playlists": True,
            "albums": True,
            "artists": True,
            "podcasts": True,
            "episodes": True,
            "audiobooks": True,
        }

    content_types = []
    for key, value in search_filters.items():
        if value is True:
            content_types.append(key)

    results = get_search_results(search_term, content_types)
    return results


def relogin():
    """
    Reloads the account pool to refresh accounts.
    """
    time.sleep(1)
    global fillaccountpool
    fillaccountpool = FillAccountPool()
    account_pool: list = []
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
    queueworker.start()
    downloadworker.start()
    if config.get("enable_retry_worker"):
        retryworker.start()
    fillaccountpool.start()
    logger.info("Initializing...")

    yield

    queueworker.stop()
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

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Pydantic schemas of body data
class AccountData(BaseModel):
    username: str | None = None
    token: str | None = None


# ---------------------------------------------------------------------------
# API ENDPOINTS
# ---------------------------------------------------------------------------


@app.get("/")
def read_root():
    """
    Root endpoint returning a greeting message.

    :return: A dictionary with a greeting message.
    """
    return {"Hello": "World"}


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
    websocket_event("QUEUE_UPDATE")
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
    with download_queue_lock:
        for key, item in download_queue.items():
            if item["local_id"] == lid:
                match action:
                    case "retry":
                        item["item_status"] = ItemStatus.WAITING
                        return True
                    case "cancel":
                        item["item_status"] = ItemStatus.CANCELLED
                        return True
                    case "delete":
                        download_queue.pop(key)
                        return True
                    case _:
                        return False


@app.get("/queue/downloads/retryfailed")
async def retry_failed_items():
    """
    Endpoint to retry all failed or cancelled items in the download queue.
    """
    with download_queue_lock:
        for key, item in download_queue.items():
            if item["item_status"] in ["Failed", "Cancelled"]:
                download_queue[key]["item_status"] = "Waiting"


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


@app.post("/config/reset")
async def reset_config():
    """
    Endpoint to reset the configuration to default settings.

    :return: Result of resetting the configuration.
    """
    return config.reset()


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
            logger.error("error finding match in log %s", l)
            message = None

        log_info = re.findall(r"\[(.+?) :: (\w+?) :: (.+) :: (\w.+)]", main[0][0])
        try:
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


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """
    Websocket endpoint for real-time communication.

    :param websocket: The websocket connection.
    """
    await websocket.accept()
    logger.info("websocket connected")

    try:
        # Step 1: Send the initial HANDSHAKE with the current queue
        # The frontend accepts either an array or an object (it converts objects to arrays via Object.values)
        with download_queue_lock:
            await websocket.send_json({"type": "HANDSHAKE", "queue": dict(download_queue)})

        while True:
            if len(websocket_queue) > 0:
                with websocket_queue_lock:
                    websocket_event_time, websocket_event_item = (
                        websocket_queue.popleft()
                    )
                    websocket_event_type = websocket_event_item["type"]
                    websocket_payload = websocket_event_item["event"]
                    try:
                        if (
                            websocket_event_type == "STATUS_CHANGE"
                        ):  # progress change on item
                            # Update status of item_1 to 'downloading' and trigger a notification

                            await websocket.send_json(
                                {
                                    "type": "STATUS_CHANGE",
                                    "item": websocket_payload,
                                    "notification": websocket_payload["item_status"],
                                }
                            )

                        elif websocket_event_type == "QUEUE_UPDATE":  # queue update
                            # Add a new item to the queue and send a full QUEUE_UPDATE

                            await websocket.send_json(
                                {"type": "QUEUE_UPDATE", "queue": download_queue}
                            )
                        elif websocket_event_type == "Notification":  # queue update
                            # Add a new item to the queue and send a full QUEUE_UPDATE

                            await websocket.send_json(
                                {
                                    "type": "Notification",
                                    "content": websocket_payload,
                                }
                            )
                        else:
                            # Keep the connection alive with simple heartbeat logs, or break/reset
                            await websocket.send_json(
                                {
                                    "type": "LOG",
                                    "line": f"Unknown websocket event {websocket_event_type}",
                                }
                            )
                    except Exception as e:
                        logger.error(
                            f"Error sending websocket event {websocket_event_type}: {str(e)}"
                        )
                        break
                    await asyncio.sleep(0.5)
            else:
                await asyncio.sleep(2)
                try:
                    await websocket.send_json(
                        {
                            "type": "Keepalive",
                        }
                    )
                except Exception as e:
                    logger.error(f"Failed to send websocket message: {e}")
                    break  
    except WebSocketDisconnect:
        logger.info("Client disconnected")
        


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
