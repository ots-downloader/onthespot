import os
import sys
import threading
import time
import logging
import uvicorn
import uuid
import re
import asyncio
from pydantic import BaseModel
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from logging.handlers import RotatingFileHandler

# Must be set before any protobuf/librespot imports.
os.environ["PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION"] = "python"
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

log_level = int(os.environ.get("LOG_LEVEL", 20))
logger = get_logger("gui")
# ---------------------------------------------------------------------------
# ONTHESPOT BOOTSTRAP
# ---------------------------------------------------------------------------

def add_item_to_download_list(item, item_status: str | None = None):

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
    def __init__(self):
        super().__init__()
        self.is_running = True
        self.thread = threading.Thread(target=self.run)

    def start(self):
        self.thread.start()

    def run(self):
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
        logger.info("Stopping Queue Worker")
        self.is_running = False
        self.thread.join()


# define workers here to allow app to access them
# but start/stop them on lifespan events
parsing_worker = ParsingWorker()
queueworker = QueueWorker()
downloadworker = DownloadWorker(gui=True)
spotifymirrorworker = MirrorSpotifyPlayback()
retryworker = RetryWorker(gui=True)
fillaccountpool = FillAccountPool(gui=True)

# migrate possibly old configurations
config.migration()

##ONTHESPOT BRIDGE FUNCTIONS
def add_spotify_account():
    logger.info("Add spotify account clicked ")
    login_worker = threading.Thread(target=add_spotify_account_worker)
    login_worker.daemon = True
    login_worker.start()


def add_spotify_account_worker():
    if spotify_new_session():
        config.set("active_account_number", len(account_pool))
        config.save()
    else:
        logger.info("Account Already Exists")


def add_tidal_account():
    logger.info("Add Tidal account clicked ")
    device_code, verification_url = tidal_add_account_pt1()
    logger.info(
        f"Login Service Started head to <a style='color: #6495ed;' href='https://{verification_url}'>https://{verification_url}</a> to continue."
    )
    login_worker = threading.Thread(
        target=add_tidal_account_worker, args=(device_code,)
    )
    login_worker.daemon = True
    login_worker.start()


def add_tidal_account_worker(device_code):
    if tidal_add_account_pt2(device_code):
        config.set("active_account_number", len(account_pool))
        config.save()
    else:
        logger.info("Account Already Exists")


def search(search_term, search_filters: dict | None = None) -> None:
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
    fillaccountpool.stop()
    time.sleep(1)
    fillaccountpool.start()    

# ---------------------------------------------------------------------------
# FASTAPI INIT
# ---------------------------------------------------------------------------

#START ONTHESPOT WORKERS HERE
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(f"OnTheSpot Version: {config.get('version')}")  
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
    return {"Hello": "World"}


##QUERY ENDPOINTS

@app.post("/query/url")
async def query_url(q: str | None = None, filters: dict | None = None):
    result = None
    if q:
        result = search(q, filters)
    websocket_event("QUEUE_UPDATE")
    return result

@app.post("/spotify/mirror")
async def mirror_spotify(state: bool = False):
    if state:
        spotifymirrorworker.start()
    else:
        spotifymirrorworker.stop()

## QUEUES ENDPOINTS

@app.get("/queue/downloads")
async def query_download_queue():
    return download_queue

@app.get("/queue/downloads/clear")
async def remove_queue_items(status: str = "Completed"):
    with download_queue_lock:
        if status != "all":
            for key, item in download_queue.items():
                if item["item_status"] == status or item["item_status"] == "Already Exists":
                    download_queue.pop(key)
                    return
        else:
            download_queue.clear()

@app.post("/queue/downloads/action")
async def queue_action(id: str, action: str):
    with download_queue_lock:
        for key, item in download_queue.items():
            if item["local_id"] == id:
                match (action):
                    case "retry":
                        item["item_status"] = ItemStatus.WAITING
                    case "cancel":
                        item["item_status"] = ItemStatus.CANCELLED
                    case "delete":
                        download_queue.pop(key)
                    case (_):
                        pass 
                
                return
        else:
            download_queue.clear()

@app.get("/queue/downloads/retryfailed")
async def retry_failed_items():
    with download_queue_lock:
        for key, item in download_queue.items():
            if item["item_status"] in ["Failed", "Cancelled"]:
                download_queue[key]["item_status"] = "Waiting"


@app.get("/queue/pending")
async def query_pending_queue():
    return pending


@app.get("/queue/parsing")
async def query_parsing_queue():
    return parsing


## CONFIG ENDPOINTS

@app.get("/config/get")
async def get_config():
    return config


@app.post("/config/set")
async def set_config(nkey, nvalue):
    if nvalue in ['false', 'true']:
        match nvalue:
            case 'false':
                nvalue = False
            case 'true':
                nvalue = True
            case _:
                pass
    return config.set(nkey, nvalue)


@app.post("/config/save")
async def save_config():
    return config.save()

@app.post("/config/reset")
async def reset_config():
    return config.reset()
 

# ACCOUNTS ENDPOINTS

@app.post("/accounts/add")
async def add_account(service: str, item: AccountData | None = None):
    found = None
    match service:
        case "generic":
            generic_add_account()
            found = True
        case "spotify":
            add_spotify_account()
            found = True
        case "tidal":
            add_tidal_account()
            found = True
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
            found = True
        case _:
            raise NotImplementedError
    if found:
        relogin()


@app.post("/accounts/remove")
async def remove_account(uuid: str):
    index = None
    for idx, item in enumerate(account_pool):
        if item["uuid"] == uuid:
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
    return account_pool

#LOGS ENDPOINTS
@app.get("/logs")
async def get_logs():
    log_path = config.get("_log_file")
    lines = None
    data = []
    with open(log_path, "r") as f:
        lines = f.readlines()
    for l in lines:
        main = re.findall(r"(\[*.+\])( -> *.+)",l)
        try:
            message = main[0][1]
        except IndexError:
            pass
        log_info = re.findall(r"\[( *.+?) :: ( *.+?) :: (\w.+) :: (\w.+)]", main[0][0])
        try:
            date = log_info[0][0][:-4]
            source = log_info[0][2]
            level = log_info[0][3]
        except IndexError:
            date = ""
            source = main
            level = ""
        data.append({
            "id": uuid.uuid4(),
            "timestamp": date,
            "level": level,
            "message": source + message,
        })
    return data

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    logger.info("websocket connected")
    
    try:
        
        # Step 1: Send the initial HANDSHAKE with the current queue
        # The frontend accepts either an array or an object (it converts objects to arrays via Object.values)
        await websocket.send_json({
            "type": "HANDSHAKE",
            "queue": download_queue
        })
        loop = True
        while loop:
            if websocket_queue:
                with websocket_queue_lock:
                    if websocket_queue:
                        websocket_event_time, websocket_event_item = websocket_queue.popitem()
                        websocket_event_type = websocket_event_item["type"]
                        websocket_payload = websocket_event_item["event"]
                        if websocket_event_type == "LOG": #log Entry
                            # Send a LOG message
                            await websocket.send_json({
                                "type": "LOG",
                                "line": websocket_payload
                            })  
                        elif websocket_event_type == "STATUS_CHANGE": #progress change on item
                            # Update status of item_1 to 'downloading' and trigger a notification
                            
                            await websocket.send_json({
                                "type": "STATUS_CHANGE",
                                "item": websocket_payload,
                                "notification": websocket_payload["item_status"]
                            })
                            
                        elif websocket_event_type == "QUEUE_UPDATE": #queue update
                            # Add a new item to the queue and send a full QUEUE_UPDATE
                            
                            await websocket.send_json({
                                "type": "QUEUE_UPDATE",
                                "queue": download_queue
                            })
                        else:
                            # Keep the connection alive with simple heartbeat logs, or break/reset
                            await websocket.send_json({
                                "type": "LOG",
                                "line": f"Unknown websocket event {websocket_event_type}"
                            })
                        await asyncio.sleep(0.5)
            else:
                await asyncio.sleep(2)
                await websocket.send_json({
                                "type": "Keepalive",
                            })
                        

    except WebSocketDisconnect:
        print("Client disconnected")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
