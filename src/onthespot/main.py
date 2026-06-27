import os
import sys
import threading
import time
import logging
import uvicorn
from fastapi import FastAPI
from logging.handlers import RotatingFileHandler

# Must be set before any protobuf/librespot imports.
os.environ["PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION"] = "python"

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
)
from .downloader import DownloadWorker, RetryWorker

log_level = int(os.environ.get("LOG_LEVEL", 20))
logger = get_logger("gui")

app = FastAPI()

config.migration()


logger.info(f"OnTheSpot Version: {config.get('version')}")


def add_item_to_download_list(item):

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
            "item_status": "Waiting",
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
                    # Padding for 'GLib-ERROR : Creating pipes for GWakeup: Too many open files Trace/breakpoint trap'
                    # when mass downloading cached responses with download queue thumbnails enabled.
                    if config.get("show_download_thumbnails"):
                        time.sleep(0.1)

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

                        # Emit error to UI
                        self.error.emit(user_msg)

                        # Create minimal metadata so item can be added to UI with "Failed" status
                        failed_metadata = create_failed_metadata(item, str(e))
                        self.add_item_to_download_list.emit(item, failed_metadata)
                    continue
            else:
                time.sleep(0.2)

    def stop(self):
        logger.info("Stopping Queue Worker")
        self.is_running = False
        self.thread.join()


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


@app.get("/")
def read_root():
    return {"Hello": "World"}


##QUERY URL
@app.post("/query/url")
async def query_url(q: str | None = None, filters: dict | None = None):
    result = None
    if q:
        result = search(q, filters)
    return result


## QUEUES STATE
@app.get("/query/downloads/queue")
async def query_download_queue():
    return download_queue


@app.get("/query/pending/queue")
async def query_pending_queue():
    return pending


@app.get("/query/parsing/queue")
async def query_parsing_queue():
    return parsing


## CONFIG
@app.get("/config/get")
async def get_config():
    return config


@app.post("/config/set")
async def set_config(nkey, nvalue):
    return config.set(nkey, nvalue)


@app.post("/config/save")
async def save_config():
    return config.save()


fillaccountpool = FillAccountPool(gui=True)
fillaccountpool.start()

parsing_worker = ParsingWorker()
parsing_worker.start()
queueworker = QueueWorker()
queueworker.start()
downloadworker = DownloadWorker(gui=True)
downloadworker.start()


@app.on_event("shutdown")
def shutdown_event():
    queueworker.stop()
    parsing_worker.stop()
    downloadworker.stop()
    logger.info("Application shutdown")


logger.info("Init completed !")
if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
