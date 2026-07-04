"""
downloader.py
~~~~~~~~~~~~~

Download workers that pull items from the download queue and fetch, decrypt,
convert, and tag each file.

Classes
-------
RetryWorker
    Periodically resets "Failed" items back to "Waiting" so they are
    retried by a :class:`DownloadWorker`.

DownloadWorker
    Main download loop.  One thread per worker instance.  Picks the next
    available item from the shared download queue, delegates to a
    service-specific download helper, then handles post-processing
    (format conversion, metadata, lyrics, thumbnail, M3U).
"""

import os
import queue
import random
import re
import subprocess
import threading
import time
import traceback
import json as _json

import requests
from librespot.audio.decoders import AudioQuality, VorbisOnlyAudioQuality
from librespot.metadata import EpisodeId, TrackId
from yt_dlp import YoutubeDL

from .accounts import get_account_token
from .api.apple_music import (
    apple_music_get_decryption_key,
    apple_music_get_webplayback_info,
)
from .api.crunchyroll import (
    crunchyroll_close_stream,
    crunchyroll_get_decryption_key,
    crunchyroll_get_mpd_info,
)
from .api.deezer import (
    calcbfkey,
    decryptfile,
    genurlkey,
    get_song_info_from_deezer_website,
)
from .api.qobuz import qobuz_get_file_url
from .api.registry import (
    SERVICE_LYRICS_FUNCTIONS,
    get_metadata_function,
)
from .api.spotify import spotify_re_init_session
from .api.tidal import tidal_get_mpd_data
from .constants import ItemStatus
from .otsconfig import config
from .runtimedata import (
    account_pool,
    download_queue,
    download_queue_lock,
    get_logger,
    temp_download_path,
    websocket_event,
)
from .utils import (
    add_to_m3u_file,
    convert_audio_format,
    convert_video_format,
    embed_metadata,
    fix_mp3_metadata,
    format_item_path,
    set_music_thumbnail,
    strip_metadata,
)

logger = get_logger("downloader")

# Maximum total file path length (Windows limit; used on all platforms for safety).
_MAX_PATH_LENGTH = 260


class TrackUnavailableError(Exception):
    """Raised when a track has no playable version (not a connection issue)."""


class DownloadCancelled(Exception):
    """Raised when user cancels the download"""


class RetryWorker:
    """Periodically resets failed download-queue items back to *Waiting*.

    The worker sleeps for ``retry_worker_delay`` minutes between scans so
    it does not busy-poll the queue.
    """

    def __init__(self, gui: bool = False) -> None:
        super().__init__()
        self.gui = gui
        self.is_running = True
        self.thread = threading.Thread(target=self.run, daemon=True)

    def start(self) -> None:
        logger.info("Starting Retry Worker")
        self.thread.start()

    def stop(self) -> None:
        logger.info("Stopping Retry Worker")
        self.is_running = False
        self.thread.join()

    def run(self) -> None:
        """Scan the queue and reset any *Failed* items to *Waiting*."""
        while self.is_running:
            if download_queue:
                with download_queue_lock:
                    for local_id, item in download_queue.items():
                        logger.debug("Retrying", extra={"local_id": local_id})
                        if item["item_status"] == ItemStatus.FAILED:
                            item["item_status"] = ItemStatus.WAITING

            delay_minutes = config.get("retry_worker_delay")
            if delay_minutes > 0:
                time.sleep(delay_minutes * 60)


class DownloadWorker:
    """Worker that downloads, converts, and tags one queue item at a time.

    Each instance runs in its own daemon thread.  Multiple instances may
    run concurrently (controlled by ``maximum_download_workers`` in config).
    """

    def __init__(self, gui: bool = False) -> None:
        super().__init__()
        self.gui = gui
        self.is_running = True
        self.thread = threading.Thread(target=self.run, daemon=True)

    def start(self) -> None:
        logger.info("Starting Download Worker")
        self.thread.start()

    def stop(self) -> None:
        logger.info("Stopping Download Worker")
        self.is_running = False
        self.thread.join()

    # ------------------------------------------------------------------
    # Queue helpers
    # ------------------------------------------------------------------

    def _pop_next_item(self):
        """Return the next available (not locked) item from the queue.

        Returns ``None`` when the queue is empty or all items are locked.
        Raises ``StopIteration`` when the queue has no available items at all.
        """
        with download_queue_lock:
            for local_id, item in download_queue.items():
                if item["available"] is False:
                    continue
                item["available"] = False
                return item
        return None

    def _requeue_item(self, item: dict) -> None:
        """Move *item* to the back of the queue and mark it available."""
        with download_queue_lock:
            try:
                local_id = item["local_id"]
                del download_queue[local_id]
                download_queue[local_id] = item
                download_queue[local_id]["available"] = True
            except KeyError:
                # Item was cleared from the queue while we were processing it.
                pass

    def _yt_dlp_progress_hook(self, item: dict, progress_info: dict) -> None:
        """Hook passed to yt-dlp to forward download progress to the GUI."""
        current = item.get("progress", 0)
        match = re.search(r"(\d+\.\d+)%", progress_info["_percent_str"])
        if not match:
            return
        new_value = round(float(match.group(1))) - 1
        if new_value >= current + 10:  # offset to avoid locking queue every 2 ms
            item["progress"] = new_value
            with download_queue_lock:
                download_queue[item["local_id"]]["progress"] = new_value
        websocket_event("STATUS_CHANGE", item)
        if item["item_status"] == ItemStatus.CANCELLED:
            raise DownloadCancelled("Download cancelled by user.")

    def _progress_hook(
        self, item: dict, progress: int, status: ItemStatus | None = None
    ):
        with download_queue_lock:
            download_queue[item["local_id"]]["progress"] = progress
            item["progress"] = progress
            if status:
                download_queue[item["local_id"]]["item_status"] = status
                item["item_status"] = status
        websocket_event("STATUS_CHANGE", item)

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    def run(self) -> None:
        """Process download queue items until stopped."""
        while self.is_running:
            item = None
            temp_path = ""
            file_path = ""

            try:
                # ---- Fetch next item from download queue ----------------------
                try:
                    if not download_queue:
                        time.sleep(0.2)
                        continue
                    item = self._pop_next_item()
                    if item is None:
                        time.sleep(0.2)
                        continue
                except (RuntimeError, OSError, StopIteration):
                    time.sleep(0.2)
                    continue

                # ---- Skip terminal-state items --------------------------------
                terminal_statuses = {
                    ItemStatus.CANCELLED,
                    ItemStatus.FAILED,
                    ItemStatus.UNAVAILABLE,
                    ItemStatus.DOWNLOADED,
                    ItemStatus.ALREADY_EXISTS,
                    ItemStatus.DELETED,
                }
                if item["item_status"] in terminal_statuses:
                    time.sleep(0.2)
                    self._requeue_item(item)
                    continue

                service = item["item_service"]
                item_type = item["item_type"]
                item_id = item["item_id"]

                item["item_status"] = ItemStatus.DOWNLOADING
                self._progress_hook(item, 1, item["item_status"])

                token = get_account_token(
                    service,
                    rotate=config.get("rotate_active_account_number"),
                )

                # ---- Fetch metadata -------------------------------------------
                try:
                    metadata_fn = get_metadata_function(service, item_type)
                    item_metadata = metadata_fn(token, item_id)
                    item["available"] = True
                    try:
                        progress_item = item
                        progress_item["name"] = item_metadata.get("title")
                        progress_item["artist"] = item_metadata.get("artists")
                        progress_item["thumbnail"] = item_metadata.get("image_url")
                        progress_item["album"] = item_metadata.get("album_name")

                        self._progress_hook(progress_item, 25)
                    except Exception as e:
                        logger.error("error emitting progress metadata", exc_info=e)
                    # YouTube Music album number shim
                    if (
                        service == "youtube_music"
                        and item.get("parent_category") == "album"
                    ):
                        item_metadata.update({"track_number": item["playlist_number"]})

                    item_path = format_item_path(item, item_metadata)

                except (Exception, KeyError) as exc:
                    error_msg = (
                        f"Failed to fetch metadata for '{item_id}', Error: {exc}"
                    )
                    if "Max retries" in str(exc) or "exhausted" in str(exc):
                        error_msg += " (Rate limit exceeded — please try again later or reduce concurrent downloads)"
                    logger.error(error_msg, exc_info=exc)
                    item["item_status"] = ItemStatus.FAILED
                    self._progress_hook(item, 0, item["item_status"])
                    self._requeue_item(item)
                    continue

                # ---- Resolve download paths and check if file exists ----------
                if service != "generic":
                    temp_path, file_path = self._resolve_paths(
                        item, item_type, item_path
                    )

                    if self._handle_existing_file(
                        item,
                        service,
                        item_type,
                        item_id,
                        item_metadata,
                        token,
                        file_path,
                    ):
                        continue

                # ---- Playability check ----------------------------------------
                if not item_metadata.get("is_playable", True):
                    logger.error("Track is unavailable", extra={"track_id": item_id})
                    item["item_status"] = ItemStatus.UNAVAILABLE
                    self._progress_hook(item, 0, item["item_status"])
                    self._requeue_item(item)
                    continue

                # ---- Download -------------------------------------------------
                default_format = ""
                bitrate = ""
                video_files = []

                try:
                    default_format, bitrate, video_files = self._download(
                        item,
                        item_metadata,
                        service,
                        item_type,
                        item_id,
                        token,
                        temp_path,
                        file_path,
                    )
                except TrackUnavailableError:
                    logger.error("Track is unavailable", extra={"track_id": item_id})
                    item["item_status"] = ItemStatus.UNAVAILABLE
                    self._progress_hook(item, 0, item["item_status"])
                    self._requeue_item(item)
                    continue
                except RuntimeError as exc:
                    logger.error(
                        "Download failed", extra={"item": item, "error": str(exc)}
                    )
                    item["item_status"] = ItemStatus.FAILED
                    self._progress_hook(item, 0, item["item_status"])
                    self._requeue_item(item)
                    continue

                # ---- Post-processing ------------------------------------------
                if service != "generic":
                    self._progress_hook(item, 50)
                    item["progress"] = 50
                    if item_type in ("track", "podcast_episode"):
                        self._finalize_audio(
                            item,
                            item_metadata,
                            service,
                            item_type,
                            item_id,
                            token,
                            file_path,
                            temp_path,
                            default_format,
                            bitrate,
                        )
                    elif item_type in ("movie", "episode"):
                        self._finalize_video(
                            item,
                            item_metadata,
                            item_type,
                            file_path,
                            video_files,
                        )

                # ---- Mark downloaded ------------------------------------------
                item["item_status"] = ItemStatus.DOWNLOADED
                logger.info("Item Successfully Downloaded")
                try:
                    item_progress = item
                    item_progress["bitrate"] = str(bitrate)
                    item_progress["format"] = default_format
                    item_progress["length"] = item_metadata.get("length")
                    try:
                        item_progress["file_size"] = str(
                            os.path.getsize(item["file_path"])
                        )
                    except Exception as e:
                        pass
                except Exception as e:
                    logger.error("error emitting progress metadata", exc_info=e)
                self._progress_hook(item_progress, 100, item["item_status"])
                item["progress"] = 100
                try:
                    config.set(
                        "total_downloaded_data",
                        config.get("total_downloaded_data")
                        + os.path.getsize(item["file_path"]),
                    )
                    config.set(
                        "total_downloaded_items",
                        config.get("total_downloaded_items") + 1,
                    )
                    config.save()
                except Exception:
                    pass

                delay = self._jittered_delay()
                logger.info("Waiting", extra={"delay": delay})
                time.sleep(delay)
                self._requeue_item(item)

            except Exception as exc:
                logger.error(
                    "Unknown Exception: %s\nTraceback: %s, ",
                    exc,
                    traceback.format_exc(),
                )
                if item is not None:
                    if item["item_status"] != ItemStatus.CANCELLED:
                        item["item_status"] = ItemStatus.FAILED
                        self._progress_hook(item, 0, item["item_status"])
                    else:
                        self._progress_hook(item, 0, item["item_status"])

                    delay = self._jittered_delay()
                    time.sleep(delay)
                    self._requeue_item(item)
                    # remove possible trash files
                    for path in (temp_path, file_path, item.get("file_path", "")):
                        if isinstance(path, str) and path and os.path.exists(path):
                            os.remove(path)

    # ------------------------------------------------------------------
    # Path helpers
    # ------------------------------------------------------------------

    def _resolve_paths(self, item, item_type, item_path):
        """Return ``(temp_file_path, file_path)`` for *item*."""
        if item_type in ("track", "podcast_episode"):
            dl_root = config.get("audio_download_path")
        else:
            dl_root = config.get("video_download_path")

        if temp_download_path:
            dl_root = temp_download_path[0]

        file_path = os.path.join(dl_root, item_path)
        directory, file_name = os.path.split(file_path)

        # Trim excessively long filenames
        name, ext = os.path.splitext(file_name)
        available_length = _MAX_PATH_LENGTH - len(os.path.join(directory, ""))
        if len(file_name) > available_length:
            name = name[: available_length - len(ext)]
            file_name = name + ext
            file_path = os.path.join(directory, file_name)

        temp_path = os.path.join(directory, "~" + file_name)
        os.makedirs(directory, exist_ok=True)
        return temp_path, file_path

    # ------------------------------------------------------------------
    # Existing-file check
    # ------------------------------------------------------------------

    def _handle_existing_file(
        self, item, service, item_type, item_id, item_metadata, token, file_path
    ):
        """Check if the output file already exists and act accordingly.

        Returns ``True`` if the caller should ``continue`` to the next item.
        """
        file_directory = os.path.dirname(file_path)
        base_stem = os.path.basename(file_path)
        subtitle_exts = {".lrc", ".ass", ".srt", ".vtt"}

        for entry in os.listdir(file_directory):
            entry_stem, entry_ext = os.path.splitext(entry)
            if not os.path.isfile(os.path.join(file_directory, entry)):
                continue
            if entry_stem != base_stem or entry_ext in subtitle_exts:
                continue

            # Existing file found
            item["file_path"] = os.path.join(file_directory, entry)

            if item_type in ("track", "podcast_episode") and config.get(
                "overwrite_existing_metadata"
            ):
                self._overwrite_metadata(
                    item, item_metadata, service, item_id, item_type, token, file_path
                )

            if (
                config.get("create_m3u_file")
                and item.get("parent_category") == "playlist"
            ):
                self._progress_hook(item, 99, ItemStatus.ADDING_TO_M3U)
                add_to_m3u_file(item, item_metadata)

            item["item_status"] = ItemStatus.ALREADY_EXISTS
            item["available"] = True
            progress_item = item
            try:
                try:
                    progress_item["file_size"] = os.path.getsize(item["file_path"])
                except Exception:
                    pass
                progress_item["length"] = item_metadata.get("length")
                progress_item["name"] = item_metadata.get("title")
                progress_item["artist"] = item_metadata.get("artists")
                progress_item["thumbnail"] = item_metadata.get("image_url")
                progress_item["album"] = item_metadata.get("album_name")
                progress_item["available"] = True
            except Exception as e:
                logger.error("error emitting progress metadata", exc_info=e)
            self._progress_hook(progress_item, 100, ItemStatus.ALREADY_EXISTS)
            logger.info("File already exists", extra={"track_id": item_id})
            item["progress"] = 100
            time.sleep(0.2)
            # self._requeue_item(item)
            return True  # caller should continue

        return False  # file not found; proceed with download

    def _overwrite_metadata(
        self, item, item_metadata, service, item_id, item_type, token, file_path
    ):
        """Re-embed lyrics, metadata, and thumbnail on an existing file."""
        # Lyrics
        lyrics_fn = SERVICE_LYRICS_FUNCTIONS.get(service)
        if lyrics_fn and config.get("download_lyrics"):
            self._progress_hook(item, 60, ItemStatus.GETTING_LYRICS)
            extra = lyrics_fn(token, item_id, item_type, item_metadata, file_path)
            if isinstance(extra, dict):
                item_metadata.update(extra)

        if not config.get("raw_media_download"):
            strip_metadata(item)
            embed_metadata(item, item_metadata)
            if config.get("save_album_cover") or config.get("embed_cover"):
                self._progress_hook(item, 70, ItemStatus.SETTING_THUMBNAIL)
                set_music_thumbnail(item["file_path"], item_metadata)
            if os.path.splitext(item["file_path"])[1] == ".mp3":
                fix_mp3_metadata(item["file_path"])
        elif config.get("save_album_cover"):
            self._progress_hook(item, 70, ItemStatus.SETTING_THUMBNAIL)
            set_music_thumbnail(file_path, item_metadata)

    # ------------------------------------------------------------------
    # Service-specific download helpers
    # ------------------------------------------------------------------

    def _download(
        self,
        item,
        item_metadata,
        service,
        item_type,
        item_id,
        token,
        temp_path,
        file_path,
    ):
        """Dispatch to the appropriate service download method.

        Returns ``(default_format, bitrate, video_files)``.
        """
        if service == "spotify":
            default_format, bitrate = self._download_spotify(
                item,
                item_id,
                item_type,
                token,
                temp_path,
            )
            return default_format, bitrate, []

        if service == "deezer":
            default_format, bitrate = self._download_deezer(
                item,
                item_id,
                token,
                temp_path,
            )
            return default_format, bitrate, []

        if service in ("soundcloud", "tidal", "youtube_music"):
            default_format, bitrate = self._download_via_ytdlp_audio(
                item, item_metadata, service, item_id, token, temp_path, item_type
            )
            return default_format, bitrate, []

        if service in ("bandcamp", "qobuz"):
            default_format, bitrate = self._download_http_stream(
                item,
                item_metadata,
                service,
                item_id,
                token,
                temp_path,
            )
            return default_format, bitrate, []

        if service == "apple_music":
            default_format, bitrate = self._download_apple_music(
                item,
                item_id,
                token,
                temp_path,
            )
            return default_format, bitrate, []

        if service == "crunchyroll":
            video_files = self._download_crunchyroll(
                item,
                item_metadata,
                item_id,
                token,
                temp_path,
            )
            return "", "", video_files

        if service == "generic":
            if config.get("v2a_enable", False) is True:
                item_codec, item_bitrate = self._download_generic_v2a(
                    item, item_id, temp_path
                )
                return item_codec, str(item_bitrate), []
            self._download_generic(item, item_id, temp_path)
            return "", "", []

        raise ValueError(f"No download handler for service '{service}'")

    def _reinit_spotify_session(self, token):

        for account in account_pool:
            if (
                account.get("service") == "spotify"
                and account.get("login", {}).get("session") is token
            ):
                logger.info("Spotify session connection lost, re-initializing...")
                spotify_re_init_session(account, dead_session=token)
                return

    def _download_spotify(self, item, item_id, item_type, token, temp_path):
        default_format = ""
        temp_path += default_format

        if item_type == "track":
            audio_key = TrackId.from_base62(item_id)
        else:
            audio_key = EpisodeId.from_base62(item_id)

        quality = AudioQuality.HIGH
        bitrate = "160k"
        if token.get_user_attribute("type") == "premium" and item_type == "track":
            quality = AudioQuality.VERY_HIGH
            bitrate = "320k"

        try:
            stream = token.content_feeder().load(
                audio_key, VorbisOnlyAudioQuality(quality), False, None
            )
        except RuntimeError as exc:
            if "alternative track" in str(exc).lower():
                raise TrackUnavailableError(item_id) from exc
            self._reinit_spotify_session(token)
            raise RuntimeError(f"Spotify session connection lost: {exc}") from exc
        except queue.Empty as exc:
            self._reinit_spotify_session(token)
            raise RuntimeError(f"Spotify session connection lost: {exc}") from exc

        total_size = stream.input_stream.size
        downloaded = 0

        with open(temp_path, "wb") as audio_file:
            while downloaded < total_size:
                if item["item_status"] == ItemStatus.CANCELLED:
                    raise DownloadCancelled("Download cancelled by user.")
                chunk = stream.input_stream.stream().read(
                    config.get("download_chunk_size")
                )
                downloaded += len(chunk)
                if chunk:
                    audio_file.write(chunk)
                    self._progress_hook(
                        item,
                        int((downloaded / total_size) * 100),
                        ItemStatus.DOWNLOADING,
                    )
                if not chunk:
                    break

        stream.input_stream.stream().close()
        del stream.input_stream

        return default_format, bitrate

    def _download_deezer(self, item, item_id, token, temp_path):
        song = get_song_info_from_deezer_website(token, item_id)
        song_quality = 1
        song_format = "MP3_128"
        bitrate = "128k"
        default_format = ".mp3"

        if int(song.get("FILESIZE_FLAC", 0)) > 0:
            song_quality, song_format, bitrate, default_format = (
                9,
                "FLAC",
                "1411k",
                ".flac",
            )
        elif int(song.get("FILESIZE_MP3_320", 0)) > 0:
            song_quality, song_format, bitrate = 3, "MP3_320", "320k"
        elif int(song.get("FILESIZE_MP3_256", 0)) > 0:
            song_quality, song_format, bitrate = 5, "MP3_256", "256k"

        temp_path += default_format

        headers = {
            "Origin": "https://www.deezer.com",
            "Accept-Encoding": "utf-8",
            "Referer": "https://www.deezer.com/login",
        }
        track_data = (
            token["session"]
            .post(
                "https://media.deezer.com/v1/get_url",
                json={
                    "license_token": token["license_token"],
                    "media": [
                        {
                            "type": "FULL",
                            "formats": [
                                {"cipher": "BF_CBC_STRIPE", "format": song_format}
                            ],
                        }
                    ],
                    "track_tokens": [song["TRACK_TOKEN"]],
                },
                headers=headers,
            )
            .json()
        )

        try:
            logger.debug(track_data)
            url = track_data["data"][0]["media"][0]["sources"][0]["url"]
        except KeyError as exc:
            logger.error(
                "Unable to select Deezer quality",
                extra={"error": str(exc), "traceback": traceback.format_exc()},
            )
            song_quality = 1
            song_format = "MP3_128"
            bitrate = "128k"
            default_format = ".mp3"
            url_key = genurlkey(
                song["SNG_ID"], song["MD5_ORIGIN"], song["MEDIA_VERSION"], song_quality
            )
            url = f"https://e-cdns-proxy-{song['MD5_ORIGIN'][0]}.dzcdn.net/mobile/1/{url_key.decode()}"

        response = requests.get(url, stream=True)
        if response.status_code != 200:
            logger.info(
                "Deezer download failed", extra={"status_code": response.status_code}
            )
            item["item_status"] = ItemStatus.FAILED
            self._requeue_item(item)
            return default_format, bitrate

        total_size = int(response.headers.get("content-length", 0))
        downloaded = 0
        data_chunks = b""

        for chunk in response.iter_content(
            chunk_size=config.get("download_chunk_size")
        ):
            downloaded += len(chunk)
            data_chunks += chunk
            if downloaded != total_size:
                if item["item_status"] == ItemStatus.CANCELLED:
                    raise DownloadCancelled("Download cancelled by user.")
                self._progress_hook(
                    item, int((downloaded / total_size) * 100), ItemStatus.DOWNLOADING
                )

        bf_key = calcbfkey(song["SNG_ID"])
        self._progress_hook(item, 99, ItemStatus.DECRYPTING)
        with open(temp_path, "wb") as out_file:
            decryptfile(data_chunks, bf_key, out_file)

        return default_format, bitrate

    def _download_via_ytdlp_audio(
        self, item, item_metadata, service, item_id, token, temp_path, item_type
    ):
        """Download audio via yt-dlp (SoundCloud, Tidal, YouTube Music)."""
        item_url = item_metadata["item_url"]
        default_format = ""
        bitrate = ""
        ydl_opts = {}

        mpd_file_path = temp_path + ".mpd"

        if service == "soundcloud":
            if token["oauth_token"]:
                ydl_opts["format"] = "bestaudio[ext=m4a]/bestaudio[ext=mp3]/bestaudio"
                ydl_opts["username"] = "oauth"
                ydl_opts["password"] = token["oauth_token"]
            else:
                default_format = ".mp3"
                bitrate = "128k"
                ydl_opts["format"] = "bestaudio[ext=mp3]"

        elif service == "tidal":
            defaultformat = ".flac"
            bitrate = "1411k"

            # Get MPD manifest with error handling
            mpd_data = tidal_get_mpd_data(token, item_id)
            if not mpd_data:
                raise RuntimeError(
                    f"Tidal: Failed to get MPD manifest for track {item_id}"
                )

            # Check if manifest is JSON with direct URLs (common for AAC/MP4 tracks)

            try:
                manifest_json = _json.loads(mpd_data)
                if "urls" in manifest_json and manifest_json["urls"]:
                    direct_url = manifest_json["urls"][0]
                    logger.info(
                        "Tidal: Direct URL detected", extra={"url": direct_url[:80]}
                    )
                    headers = {"Authorization": f"Bearer {token['access_token']}"}
                    resp = requests.get(
                        direct_url, headers=headers, stream=True, timeout=60
                    )
                    resp.raise_for_status()
                    with open(temp_path, "wb") as f:
                        for chunk in resp.iter_content(chunk_size=65536):
                            if chunk:
                                f.write(chunk)
                    mime = manifest_json.get("mimeType", "audio/mp4")
                    default_format = ".flac" if "flac" in mime else ".m4a"
                    bitrate = "1411k"
                    return default_format, bitrate
            except (_json.JSONDecodeError, KeyError):
                pass

            # Fallback: Write MPD to temp file for yt-dlp
            with open(mpd_file_path, "wb") as mpd_file:
                mpd_file.write(mpd_data.encode("utf-8"))

            prefix = "file:///" if os.name == "nt" else "file://"
            item_url = f"{prefix}{mpd_file_path}"

            ydl_opts["allowed_extractors"] = ["generic"]
            ydl_opts["fixup"] = "never"
            ydl_opts["enable_file_urls"] = True
            ydl_opts["allow_unplayable_formats"] = True

            ydl_opts["http_headers"] = {
                "Authorization": f"Bearer {token['access_token']}",
                "X-Tidal-Token": token["access_token"],
            }

            ydl_opts["quiet"] = False
            ydl_opts["nowarnings"] = False

        elif service == "youtube_music":
            # metadata_fn = get_metadata_function(service, item_type)
            # item_metadata = metadata_fn(token, item_id)
            # item_url = item_metadata["item_url"]
            default_format = ".m4a"
            bitrate = "128k"
            ydl_opts["format"] = "bestaudio[ext=m4a]"
            # needed for download
            ydl_opts["extractor_args"] = {
                "youtube": {
                    "player_client": ["android_vr"],
                }
            }

        ydl_opts.update(
            {
                "quiet": False,
                "no_warnings": True,
                "noprogress": True,
                "extract_audio": True,
                "outtmpl": temp_path,
            }
        )
        ydl_opts["progress_hooks"] = [lambda d: self._yt_dlp_progress_hook(item, d)]

        with YoutubeDL(ydl_opts) as downloader:
            if service == "soundcloud" and token["oauth_token"]:
                info = downloader.extract_info(item_url)
                bitrate = f"{info.get('abr')}k"
                default_format = f".{info.get('audio_ext')}"
            downloader.download(item_url)

        if os.path.exists(mpd_file_path):
            os.remove(mpd_file_path)

        return default_format, bitrate

    def _download_http_stream(
        self, item, item_metadata, service, item_id, token, temp_path
    ):
        """Download a direct HTTP stream (Bandcamp, Qobuz)."""
        if service == "qobuz":
            default_format = ".flac"
            bitrate = "1411k"
            file_url = qobuz_get_file_url(token, item_id)
        else:  # bandcamp
            default_format = ".mp3"
            bitrate = "128k"
            file_url = item_metadata["file_url"]

        response = requests.get(file_url, stream=True)
        total_size = int(response.headers.get("Content-Length", 0))
        downloaded = 0

        with open(temp_path, "wb") as audio_file:
            for chunk in response.iter_content(
                chunk_size=config.get("download_chunk_size", 1024)
            ):
                if not chunk:
                    continue
                downloaded += len(chunk)
                audio_file.write(chunk)
                if total_size > 0 and downloaded != total_size:
                    if item["item_status"] == ItemStatus.CANCELLED:
                        raise DownloadCancelled("Download cancelled by user.")
                    self._progress_hook(item, int((downloaded / total_size) * 100))

        return default_format, bitrate

    def _download_apple_music(self, item, item_id, token, temp_path):
        default_format = ".m4a"
        bitrate = "256k"

        webplayback_info = apple_music_get_webplayback_info(token, item_id)
        stream_url = next(
            (
                asset["URL"]
                for asset in webplayback_info["assets"]
                if asset["flavor"] == "28:ctrp256"
            ),
            None,
        )
        if not stream_url:
            logger.error(
                "Apple Music playback info invalid",
                extra={"webplayback_info": webplayback_info},
            )
            raise RuntimeError("No valid Apple Music stream URL found.")

        decryption_key = apple_music_get_decryption_key(token, stream_url, item_id)

        ydl_opts = {
            "quiet": False,
            "no_warnings": True,
            "outtmpl": temp_path,
            "allow_unplayable_formats": True,
            "fixup": "never",
            "allowed_extractors": ["generic"],
            "noprogress": True,
        }
        ydl_opts["progress_hooks"] = [lambda d: self._yt_dlp_progress_hook(item, d)]

        with YoutubeDL(ydl_opts) as downloader:
            downloader.download(stream_url)

        decrypted_path = temp_path + ".m4a"
        ffmpeg_cmd = [
            config.get("_ffmpeg_bin_path"),
            "-loglevel",
            "error",
            "-y",
            "-decryption_key",
            decryption_key,
            "-i",
            temp_path,
            "-c",
            "copy",
            "-movflags",
            "+faststart",
            decrypted_path,
        ]
        self._run_ffmpeg(ffmpeg_cmd)
        self._progress_hook(item, 99, ItemStatus.DECRYPTING)

        if os.path.exists(temp_path):
            os.remove(temp_path)
        os.rename(decrypted_path, temp_path)

        return default_format, bitrate

    def _download_crunchyroll(self, item, item_metadata, item_id, token, temp_path):
        """Download encrypted Crunchyroll video/audio streams and subtitles."""
        ydl_base_opts = {
            "quiet": False,
            "no_warnings": True,
            "allow_unplayable_formats": True,
            "fixup": "never",
            "allowed_extractors": ["generic"],
            "noprogress": True,
        }
        if self.gui:
            ydl_base_opts["progress_hooks"] = [
                lambda d: self._yt_dlp_progress_hook(item, d)
            ]

        encrypted_files = []
        video_files = []
        subtitle_formats = []
        preferred_langs = (
            config.get("preferred_audio_language").replace(" ", "").split(",")
        )

        for version in item_metadata["versions"]:
            lang = version["audio_locale"]
            if lang not in preferred_langs and not config.get(
                "download_all_available_audio"
            ):
                continue

            try:
                (
                    mpd_url,
                    stream_token,
                    audio_locale,
                    headers,
                    versions,
                    extra_subtitles,
                ) = crunchyroll_get_mpd_info(token, version["guid"])
                subtitle_formats += extra_subtitles
                decryption_key = crunchyroll_get_decryption_key(
                    token, version["guid"], mpd_url, stream_token
                )
            except Exception as exc:
                logger.error(str(exc), exc_info=exc)
                continue

            token = get_account_token(item_metadata.get("item_service", "crunchyroll"))
            headers["Authorization"] = f"Bearer {token}"

            # Video
            ydl_video_opts = dict(ydl_base_opts)
            ydl_video_opts["http_headers"] = headers
            ydl_video_opts["outtmpl"] = temp_path + f" - {lang}.%(ext)s.%(ext)s"
            ydl_video_opts["format"] = (
                f"(bestvideo[height<={config.get('preferred_video_resolution')}][ext=mp4]/bestvideo)"
            )
            with YoutubeDL(ydl_video_opts) as downloader:
                video_info = downloader.extract_info(mpd_url, download=False)
                encrypted_files.append(
                    {
                        "path": downloader.prepare_filename(video_info),
                        "type": "video",
                        "decryption_key": decryption_key,
                        "language": lang,
                    }
                )
                downloader.download(mpd_url)

            # Audio
            token = get_account_token(item_metadata.get("item_service", "crunchyroll"))
            headers["Authorization"] = f"Bearer {token}"
            ydl_audio_opts = dict(ydl_base_opts)
            ydl_audio_opts["http_headers"] = headers
            ydl_audio_opts["outtmpl"] = temp_path + f" - {lang}.%(ext)s.%(ext)s"
            ydl_audio_opts["format"] = "(bestaudio[ext=m4a]/bestaudio)"
            with YoutubeDL(ydl_audio_opts) as downloader:
                audio_info = downloader.extract_info(mpd_url, download=False)
                encrypted_files.append(
                    {
                        "path": downloader.prepare_filename(audio_info),
                        "type": "audio",
                        "decryption_key": decryption_key,
                        "language": lang,
                    }
                )
                downloader.download(mpd_url)

            crunchyroll_close_stream(token, item_id, stream_token)

            # Chapters
            if not config.get("raw_media_download") and config.get("download_chapters"):
                chapter_file = temp_path + f" - {lang}.txt"
                if not os.path.exists(chapter_file):
                    resp = requests.get(
                        f"https://static.crunchyroll.com/skip-events/production/{version['guid']}.json"
                    )
                    if resp.status_code == 200:
                        chapter_data = resp.json()
                        with open(chapter_file, "w", encoding="utf-8") as cf:
                            cf.write(";FFMETADATA1\n")
                            for entry in ("intro", "credits"):
                                if chapter_data.get(entry):
                                    cf.write(
                                        f"[CHAPTER]\nTIMEBASE=1/1\n"
                                        f"START={chapter_data[entry].get('start')}\n"
                                        f"END={chapter_data[entry].get('end')}\n"
                                        f"title={entry.title()}\nlanguage={lang}\n"
                                    )
                        video_files.append(
                            {
                                "path": chapter_file,
                                "type": "chapter",
                                "format": "txt",
                                "language": lang,
                            }
                        )

        for enc_file in encrypted_files:
            decrypted_path = os.path.splitext(enc_file["path"])[0]
            video_files.append(
                {
                    "path": decrypted_path,
                    "format": os.path.splitext(enc_file["path"])[1],
                    "type": enc_file["type"],
                    "language": enc_file.get("language"),
                }
            )
            ffmpeg_cmd = [
                config.get("_ffmpeg_bin_path"),
                "-loglevel",
                "error",
                "-y",
                "-decryption_key",
                enc_file["decryption_key"],
                "-i",
                enc_file["path"],
                "-c",
                "copy",
                "-movflags",
                "+faststart",
                decrypted_path,
            ]
            self._run_ffmpeg(ffmpeg_cmd)
            if os.path.exists(enc_file["path"]):
                os.remove(enc_file["path"])

        # Subtitles
        if config.get("download_subtitles"):
            item["item_status"] = ItemStatus.DOWNLOADING_SUBTITLES
            preferred_sub_langs = config.get("preferred_subtitle_language").split(",")
            seen_langs = []
            for sub in subtitle_formats:
                lang = sub["language"]
                if lang in seen_langs:
                    continue
                seen_langs.append(lang)
                if lang not in preferred_sub_langs and not config.get(
                    "download_all_available_subtitles"
                ):
                    continue
                sub_file = temp_path + f" - {lang}.{sub['extension']}"
                if not os.path.exists(sub_file):
                    sub_data = requests.get(sub["url"]).text
                    with open(sub_file, "w", encoding="utf-8") as sf:
                        sf.write(sub_data)
                video_files.append(
                    {
                        "path": sub_file,
                        "type": "subtitle",
                        "format": sub["extension"],
                        "language": lang,
                    }
                )

        return video_files

    def _download_generic(self, item, item_id, temp_path):
        """Download using yt-dlp's generic extractor (any URL)."""

        ydl_opts = {
            "format": (
                f"(bestvideo[height<={config.get('preferred_video_resolution')}][ext=mp4]+bestaudio[ext=m4a])/"
                f"(bestvideo[height<={config.get('preferred_video_resolution')}]+bestaudio)/"
                f"best"
            ),
            "quiet": False,
            "no_warnings": True,
            "noprogress": True,
            "outtmpl": config.get("video_download_path") + os.sep + "%(title)s.%(ext)s",
            "ffmpeg_location": config.get("_ffmpeg_bin_path"),
            "postprocessors": [{"key": "FFmpegMetadata"}],
        }

        ydl_opts["progress_hooks"] = [lambda d: self._yt_dlp_progress_hook(item, d)]

        with YoutubeDL(ydl_opts) as downloader:
            info = downloader.extract_info(item_id, download=False)
            item["file_path"] = downloader.prepare_filename(info)
            downloader.download(item_id)

    def _download_generic_v2a(self, item, item_id, temp_path):
        """Download using yt-dlp's generic extractor (any URL) but extracts only audio"""

        ydl_opts = {
            "format": (
                f"(bestvideo[height<={config.get('preferred_video_resolution')}][ext=mp4]+bestaudio[ext=m4a])/"
                f"(bestvideo[height<={config.get('preferred_video_resolution')}]+bestaudio)/"
                f"best"
            ),
            "quiet": True,
            "no_warnings": True,
            "noprogress": True,
            "outtmpl": config.get("video_download_path") + os.sep + "%(title)s.%(ext)s",
            "ffmpeg_location": config.get("_ffmpeg_bin_path"),
            "postprocessors": [
                {"key": "FFmpegMetadata"},
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": config.get("v2a_preferred_codec"),
                    "preferredquality": config.get("v2a_preferred_bitrate"),
                },
            ],
        }

        ydl_opts["progress_hooks"] = [lambda d: self._yt_dlp_progress_hook(item, d)]

        with YoutubeDL(ydl_opts) as downloader:
            info = downloader.extract_info(item_id, download=False)
            item["file_path"] = downloader.prepare_filename(info)
            downloader.download(item_id)

        return config.get("v2a_preferred_codec"), config.get("v2a_preferred_bitrate")

    # ------------------------------------------------------------------
    # Post-processing helpers
    # ------------------------------------------------------------------

    def _finalize_audio(
        self,
        item,
        item_metadata,
        service,
        item_type,
        item_id,
        token,
        file_path,
        temp_path,
        default_format,
        bitrate,
    ):
        """Convert, fetch lyrics, tag, thumbnail, and optionally add to M3U."""
        # Verify temp file is valid before post-processing
        if not os.path.exists(temp_path) or os.path.getsize(temp_path) < 4096:
            size = os.path.getsize(temp_path) if os.path.exists(temp_path) else 0
            logger.error(
                "Downloaded temp file is missing or too small (%s bytes): %s",
                size,
                temp_path,
            )
            if os.path.exists(temp_path):
                os.remove(temp_path)
            raise RuntimeError(
                f"Corrupt or incomplete download detected ({size} bytes)"
            )

        # Lyrics
        lyrics_fn = SERVICE_LYRICS_FUNCTIONS.get(service)
        if lyrics_fn and config.get("download_lyrics"):
            self._progress_hook(item, 60, ItemStatus.GETTING_LYRICS)
            extra = lyrics_fn(token, item_id, item_type, item_metadata, file_path)
            if isinstance(extra, dict):
                item_metadata.update(extra)

        # Rename temp file to final path with correct extension
        if config.get("raw_media_download"):
            final_path = file_path + default_format
        elif item_type == "track":
            final_path = file_path + "." + config.get("track_file_format")
        else:
            final_path = file_path + "." + config.get("podcast_file_format")

        os.rename(temp_path, final_path)
        item["file_path"] = final_path

        if not config.get("raw_media_download"):
            self._progress_hook(item, 70, ItemStatus.CONVERTING)
            if config.get("use_custom_file_bitrate"):
                bitrate = config.get("file_bitrate")
            convert_audio_format(final_path, bitrate, default_format)
            embed_metadata(item, item_metadata)

            if config.get("save_album_cover") or config.get("embed_cover"):
                self._progress_hook(item, 80, ItemStatus.SETTING_THUMBNAIL)
                set_music_thumbnail(final_path, item_metadata)

            if os.path.splitext(final_path)[1] == ".mp3":
                fix_mp3_metadata(final_path)

        elif config.get("save_album_cover"):
            self._progress_hook(item, 80, ItemStatus.SETTING_THUMBNAIL)
            set_music_thumbnail(final_path, item_metadata)

        # M3U
        if config.get("create_m3u_file") and item.get("parent_category") == "playlist":
            self._progress_hook(item, 90, ItemStatus.ADDING_TO_M3U)
            add_to_m3u_file(item, item_metadata)

    def _finalize_video(self, item, item_metadata, item_type, file_path, video_files):
        """Rename temp video files and mux them together."""
        for vf in video_files:
            final_path = vf["path"].replace("~", "")
            os.rename(vf["path"], final_path)
            vf["path"] = final_path

        if not config.get("raw_media_download"):
            self._progress_hook(item, 70, ItemStatus.CONVERTING)
            output_format = config.get(
                "show_file_format" if item_type == "episode" else "movie_file_format"
            )
            convert_video_format(
                item, file_path, output_format, video_files, item_metadata
            )
            item["file_path"] = file_path + "." + output_format
        else:
            item["file_path"] = file_path + ".mp4"

    # ------------------------------------------------------------------
    # Utility helpers
    # ------------------------------------------------------------------

    def _run_ffmpeg(self, command: list) -> None:
        """Run an ffmpeg command, suppressing the console window on Windows."""
        if os.name == "nt":
            subprocess.check_call(
                command, shell=False, creationflags=subprocess.CREATE_NO_WINDOW
            )
        else:
            subprocess.check_call(command, shell=False)

    def _jittered_delay(self) -> float:
        """Return the configured download delay with optional random variance."""
        variance = int(config.get("download_delay_variance"))
        return max(
            0, int(config.get("download_delay")) + random.randint(-variance, variance)
        )
