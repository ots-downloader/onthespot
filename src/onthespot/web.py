import os

# Required for librespot-python
os.environ["PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION"] = "python"
import argparse
import json
import shutil
import subprocess
import sys
import threading
import time
import traceback
from flask import (
    Flask,
    jsonify,
    render_template,
    redirect,
    request,
    send_file,
    url_for,
    flash,
    Response,
)
from flask_login import (
    LoginManager,
    UserMixin,
    login_user,
    login_required,
    logout_user,
    current_user,
)
from .accounts import FillAccountPool, get_account_token
from .api.apple_music import apple_music_get_track_metadata, apple_music_add_account
from .api.bandcamp import bandcamp_get_track_metadata
from .api.deezer import deezer_get_track_metadata, deezer_add_account
from .api.qobuz import qobuz_get_track_metadata, qobuz_add_account
from .api.soundcloud import soundcloud_get_track_metadata, soundcloud_add_account
from .api.spotify import (
    MirrorSpotifyPlayback,
    spotify_new_session,
    spotify_get_track_metadata,
    spotify_get_podcast_episode_metadata,
)
from .api.tidal import tidal_get_track_metadata
from .api.youtube_music import (
    youtube_music_get_track_metadata,
    youtube_music_add_account,
)
from .api.crunchyroll import crunchyroll_get_episode_metadata, crunchyroll_add_account
from .api.generic import generic_add_account
from .downloader import DownloadWorker, RetryWorker
from .otsconfig import cache_dir, config_dir, config
from .parse_item import ParsingWorker, parse_url
from .runtimedata import (
    get_logger,
    account_pool,
    pending,
    download_queue,
    download_queue_lock,
    pending_lock,
)
from .search import get_search_results
from .utils import format_bytes

logger = get_logger("web")
os.environ["FLASK_ENV"] = "production"
web_resources = os.path.join(config.app_root, "resources", "web")
app = Flask("OnTheSpot", template_folder=web_resources, static_folder=web_resources)
app.secret_key = os.urandom(24)
login_manager = LoginManager()
login_manager.init_app(app)


class QueueWorker(threading.Thread):
    def __init__(self):
        super().__init__()

    def run(self):
        while True:
            try:
                if pending:
                    local_id = next(iter(pending))
                    with pending_lock:
                        item = pending.pop(local_id)
                    token = get_account_token(item["item_service"])
                    item_metadata = globals()[
                        f"{item['item_service']}_get_{item['item_type']}_metadata"
                    ](token, item["item_id"])
                    if item_metadata:
                        with download_queue_lock:
                            download_queue[local_id] = {
                                "local_id": local_id,
                                "available": True,
                                "item_service": item["item_service"],
                                "item_type": item["item_type"],
                                "item_id": item["item_id"],
                                "item_status": "Waiting",
                                "file_path": None,
                                "item_name": item_metadata["title"],
                                "item_by": item_metadata["artists"],
                                "parent_category": item["parent_category"],
                                "playlist_name": item.get("playlist_name"),
                                "playlist_by": item.get("playlist_by"),
                                "playlist_number": item.get("playlist_number"),
                                "item_thumbnail": item_metadata["image_url"],
                                "item_url": item_metadata["item_url"],
                                "progress": 0,
                            }
                else:
                    time.sleep(0.2)
            except Exception as e:
                logger.error(
                    f"Unknown Exception for {item}: {str(e)}\nTraceback: {traceback.format_exc()}"
                )
                with pending_lock:
                    pending[local_id] = item


class User(UserMixin):
    def __init__(self, id):
        self.id = id


@login_manager.user_loader
def load_user(user_id):
    return User(user_id)


login_manager.login_view = "/login"


@app.route("/login", methods=["GET", "POST"])
def login():
    if not config.get("use_webui_login") or not config.get("webui_username"):
        user = User("guest")
        login_user(user)
        return redirect(url_for("download_queue_page"))

    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        if username == config.get("webui_username") and password == config.get(
            "webui_password"
        ):
            user = User(username)
            login_user(user)
            return redirect(url_for("download_queue_page"))
        flash("Invalid credentials, please try again.")
    return render_template("login.html")


@app.route("/api/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("login"))


@app.route("/icons/<path:filename>")
def serve_icons(filename):
    icon_path = os.path.join(config.app_root, "resources", "icons", filename)
    return send_file(icon_path)


@app.route("/")
@login_required
def index():
    return redirect(url_for("download_queue_page"))


@app.route("/search")
@login_required
def search():
    config_path = os.path.join(config_dir(), "otsconfig.json")
    with open(config_path, "r") as config_file:
        config_data = json.load(config_file)
    return render_template("search.html", config=config_data)


@app.route("/download_queue")
@login_required
def download_queue_page():
    config_path = os.path.join(config_dir(), "otsconfig.json")
    with open(config_path, "r") as config_file:
        config_data = json.load(config_file)
    return render_template("download_queue.html", config=config_data)


@app.route("/settings")
@login_required
def settings():
    config_path = os.path.join(config_dir(), "otsconfig.json")
    with open(config_path, "r") as config_file:
        config_data = json.load(config_file)
    return render_template(
        "settings.html", config=config_data, account_pool=account_pool
    )


@app.route("/about")
@login_required
def about():
    return render_template(
        "about.html",
        version=config.get("version"),
        statistics=f"{config.get('total_downloaded_items')} / {format_bytes(config.get('total_downloaded_data'))}",
    )


@app.route("/api/search_results")
@login_required
def search_results():
    query = request.args.get("q")

    content_types = []
    if config.get("enable_search_tracks"):
        content_types.append("track")
    if config.get("enable_search_playlists"):
        content_types.append("playlist")
    if config.get("enable_search_albums"):
        content_types.append("album")
    if config.get("enable_search_artists"):
        content_types.append("artist")
    if config.get("enable_search_podcasts"):
        content_types.append("show")
    if config.get("enable_search_episodes"):
        content_types.append("episode")
    if config.get("enable_search_audiobooks"):
        content_types.append("audiobook")

    results = get_search_results(query, content_types=content_types)
    return jsonify(results)


@app.route("/api/clear_items", methods=["POST"])
@login_required
def clear_items():
    keys_to_delete = []
    for local_id, item in download_queue.items():
        if item["item_status"] in (
            "Downloaded",
            "Already Exists",
            "Cancelled",
            "Unavailable",
            "Deleted",
        ):
            keys_to_delete.append(local_id)
    for key in keys_to_delete:
        del download_queue[key]
    return jsonify(success=True)


@app.route("/api/cancel_items", methods=["POST"])
@login_required
def cancel_items():
    with parsing_lock:
        parsing.clear()
    with pending_lock:
        pending.clear()
    for local_id, item in download_queue.items():
        if item["item_status"] == "Waiting":
            with download_queue_lock:
                download_queue[local_id]["item_status"] = "Cancelled"
    return jsonify(success=True)


@app.route("/api/retry_items", methods=["POST"])
@login_required
def retry_items():
    for local_id, item in download_queue.items():
        if item["item_status"] in ("Failed", "Cancelled"):
            with download_queue_lock:
                download_queue[local_id]["item_status"] = "Waiting"
    return jsonify(success=True)


@app.route("/api/restart", methods=["POST"])
@login_required
def restart():
    logger.info("Caching Download Queue...")
    with open(os.path.join(cache_dir(), "cached_download_queue.txt"), "w") as file:
        for local_id, item in download_queue.items():
            file.write(item["item_url"] + "\n")
    logger.info("Restarting...")
    subprocess.Popen([sys.executable, "-m", "onthespot.web"] + (sys.argv[1:]))
    os._exit(0)


@app.route("/api/download_queue")
@login_required
def get_items():
    with download_queue_lock:
        return Response(
            json.dumps(download_queue, sort_keys=True), mimetype="application/json"
        )


@app.route("/api/cancel/<path:local_id>", methods=["POST"])
@login_required
def cancel_item(local_id):
    download_queue[local_id]["item_status"] = "Cancelled"
    return jsonify(success=True)


@app.route("/api/retry/<path:local_id>", methods=["POST"])
@login_required
def retry_item(local_id):
    download_queue[local_id]["item_status"] = "Waiting"
    return jsonify(success=True)


@app.route("/api/download/<path:local_id>")
@login_required
def download_media(local_id):
    if local_id != "logs":
        return send_file(download_queue[local_id]["file_path"], as_attachment=True)
    else:
        return send_file(
            os.path.join(cache_dir(), "logs", config.session_uuid, "onthespot.log"),
            as_attachment=True,
        )


@app.route("/api/parse_url/<path:url>", methods=["POST"])
@login_required
def parse_download(url):
    parse_url(url)
    return jsonify(success=True)


@app.route("/api/delete/<path:local_id>", methods=["DELETE"])
@login_required
def delete_media(local_id):
    os.remove(download_queue[local_id]["file_path"])
    download_queue[local_id]["item_status"] = "Deleted"
    return jsonify(success=True)


@app.route("/api/update_settings", methods=["POST"])
@login_required
def update_settings():
    data = request.json
    for key, value in data.items():
        if isinstance(value, str) and value.isdigit():
            value = int(value)
        config.set(key, value)
        config.save()
    return jsonify(success=True)


@app.route("/api/add_account", methods=["POST"])
@login_required
def add_account():
    account = request.get_json()
    if account["service"] == "apple_music":
        apple_music_add_account(account["password"])
    elif account["service"] == "bandcamp":
        bandcamp_add_account()
    elif account["service"] == "deezer":
        deezer_add_account(account["password"])
    elif account["service"] == "qobuz":
        qobuz_add_account(account["email"], account["password"])
    elif account["service"] == "soundcloud":
        soundcloud_add_account(account["password"])
    elif account["service"] == "youtube_music":
        youtube_music_add_account()
    elif account["service"] == "crunchyroll":
        crunchyroll_add_account(account["email"], account["password"])
    elif account["service"] == "generic":
        generic_add_account()
    config.set("active_account_number", config.get("active_account_number") + 1)
    config.save()
    return jsonify(success=True)


@app.route("/api/remove_account/<path:uuid>", methods=["DELETE"])
@login_required
def remove_account(uuid):
    accounts = config.get("accounts").copy()
    for i, account in enumerate(accounts):
        if account["uuid"] == uuid:
            account_number = i
    del account_pool[account_number]
    del accounts[account_number]
    config.set("accounts", accounts)
    config.set("active_account_number", 0)
    config.save()
    return jsonify(success=True)


@app.route("/api/clear_cache", methods=["DELETE"])
@login_required
def clear_cache():
    shutil.rmtree(os.path.join(cache_dir(), "reqcache"))
    shutil.rmtree(os.path.join(cache_dir(), "logs"))
    return jsonify(success=True)


def main():
    config.migration()
    print(f"OnTheSpot Version: {config.get('version')}")
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", type=str, default="127.0.0.1", help="Host IP address")
    parser.add_argument("--port", type=int, default=5000, help="Port number")
    parser.add_argument("--debug", action="store_true", help="Enable debug mode")
    args = parser.parse_args()

    fill_account_pool = FillAccountPool()

    fill_account_pool.finished.connect(
        lambda: logger.info("Finished filling account pool.")
    )
    fill_account_pool.progress.connect(
        lambda message, status: logger.info(
            f"{message} {'Success' if status else 'Failed'}"
        )
    )

    fill_account_pool.start()

    parsing_worker = ParsingWorker()
    parsing_worker.start()

    for _ in range(config.get("maximum_queue_workers")):
        queue_worker = QueueWorker()
        queue_worker.start()

    for _ in range(config.get("maximum_download_workers")):
        download_worker = DownloadWorker()
        download_worker.start()

    if config.get("enable_retry_worker"):
        retryworker = RetryWorker()
        retryworker.start()

    fill_account_pool.wait()

    if config.get("mirror_spotify_playback"):
        mirrorplayback = MirrorSpotifyPlayback()
        mirrorplayback.start()

    cached_file_path = os.path.join(cache_dir(), "cached_download_queue.txt")
    if os.path.isfile(cached_file_path):
        logger.info(
            f"Found cached download queue at {cached_file_path}, appending items to download queue..."
        )
        get_search_results(cached_file_path)
        os.remove(cached_file_path)

    app.run(host=args.host, port=args.port, debug=args.debug)


if __name__ == "__main__":
    main()
