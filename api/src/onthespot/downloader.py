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
import threading
import time


from .accounts import get_account_token

from .api.registry import (
    SERVICE_LYRICS_FUNCTIONS,
    get_metadata_function,
)
from .services_middleware import (
    download_spotify,
    download_deezer,
    download_via_ytdlp_audio,
    download_http_stream,
    download_apple_music,
    download_crunchyroll,
    download_generic_v2a,
    download_generic
)

from .constants import ItemStatus
from .library import remember_item, verify_file
from .otsconfig import config
from .runtimedata import (
    pending,
    download_paused,
    download_queue,
    download_queue_lock,
    get_logger,
    temp_download_path,
    progress_hook,
    wait_for_download_resume,
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
    requeue_item,
    retry_single_item,
    jittered_delay,
)
from .resources.exceptions import DownloadCancelled, TrackUnavailableError


logger = get_logger("downloader")

# Maximum total file path length (Windows limit; used on all platforms for safety).
_MAX_PATH_LENGTH = 260



class RetryWorker:
    """Periodically resets failed download-queue items back to *Waiting*.

    The worker sleeps for ``retry_worker_delay`` minutes between scans so
    it does not busy-poll the queue.
    """

    def __init__(self) -> None:
        super().__init__()
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
                    found_items = []
                    for local_id, item in download_queue.items():
                        if item["available"] is False:
                            continue
                        # Only retry items that actually need a retry. Waiting,
                        # downloading, and completed playlist entries must stay
                        # in the visible batch queue.
                        retryable_statuses = {
                            ItemStatus.CANCELLED,
                            ItemStatus.FAILED,
                            ItemStatus.UNAVAILABLE,
                        }
                        if item["item_status"] not in retryable_statuses:
                            continue
                        # A user cancellation must stay cancelled until the
                        # user explicitly retries it.  Without this marker the
                        # retry worker treats every cancellation as a transient
                        # failure and starts it again shortly afterwards.
                        if item.get("_manual_cancelled"):
                            continue
                        item["available"] = True
                        item["item_status"] = ItemStatus.WAITING
                        item["error"] = ""
                        item["_stats_recorded"] = False
                        item["retry_count"] = int(item.get("retry_count", 0) or 0) + 1
                        found_items.append(item)

                    for item in found_items:
                        del download_queue[item["local_id"]]
                        pending.put_nowait(item)


            delay_minutes = config.get("retry_worker_delay")
            if delay_minutes > 0:
                time.sleep(delay_minutes * 60)


class DownloadWorker:
    """Worker that downloads, converts, and tags one queue item at a time.

    Each instance runs in its own daemon thread.  Multiple instances may
    run concurrently (controlled by ``maximum_download_workers`` in config).
    """

    def __init__(self) -> None:
        super().__init__()
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
    # Main loop
    # ------------------------------------------------------------------

    @staticmethod
    def _retry_or_fail(item, error: str) -> bool:
        """Retry transient download failures while preserving partial files."""
        max_retries = max(0, int(config.get("api_retry_max_attempts", 3) or 3))
        retry_count = int(item.get("retry_count", 0) or 0)
        if retry_count < max_retries and not item.get("_discarded"):
            item["retry_count"] = retry_count + 1
            item["error"] = f"{error} (automatic retry {retry_count + 1}/{max_retries})"
            item["_stats_recorded"] = False
            item["_active_download"] = False
            item["item_status"] = ItemStatus.WAITING
            retry_single_item(item)
            return True

        item["error"] = error
        item["item_status"] = ItemStatus.FAILED
        progress_hook(item, 0, item["item_status"])
        requeue_item(item)
        return False

    @staticmethod
    def _raise_if_cancelled(item) -> None:
        """Stop processing as soon as a user cancellation is observed."""
        if item.get("item_status") == ItemStatus.CANCELLED:
            raise DownloadCancelled("Download cancelled by user.")

    @classmethod
    def _mark_cancelled(cls, item, error: str = "Download cancelled by user.") -> None:
        """Finalize cancellation and notify the UI without retrying the item."""
        item["_active_download"] = False
        item["_pause_requested"] = False
        item["item_status"] = ItemStatus.CANCELLED
        item["error"] = error
        raw_progress = item.get("progress", item.get("item_progress", 0))
        try:
            current_progress = int(float(raw_progress or 0))
        except (TypeError, ValueError):
            current_progress = 0
        progress_hook(item, current_progress, ItemStatus.CANCELLED)

    def run(self) -> None:
        """Process download queue items until stopped."""
        while self.is_running:
            item = None
            temp_path = ""
            file_path = ""

            try:
                if download_paused.is_set():
                    time.sleep(0.2)
                    continue
                # ---- Fetch next item from download queue ----------------------
                try:
                    if not pending.empty():
                        item = pending.get_nowait()
                        if item is None:
                            time.sleep(0.2)
                            continue
                        if item.get("_discarded"):
                            continue
                        with download_queue_lock:
                            # Playlist items are registered before they reach
                            # pending so the UI can show the full batch. If a
                            # user cleared one in the meantime, do not
                            # resurrect it when the pending item is consumed.
                            if item.get("queue_preloaded") and item["local_id"] not in download_queue:
                                continue
                            if item["local_id"] not in download_queue:
                                item["queue_position"] = max(
                                    [entry.get("queue_position", -1) for entry in download_queue.values()],
                                    default=-1,
                                ) + 1
                                item.setdefault("priority", 0)
                            download_queue[item["local_id"]] = item
                    else:
                        time.sleep(0.2)
                        continue
                except (RuntimeError, OSError, StopIteration) as e:
                    logger.error("error fetching next item from download queue %s", str(e), exc_info=True)
                    time.sleep(0.2)
                    continue

                service = item["item_service"]
                item_type = item["item_type"]
                item_id = item["item_id"]

                self._apply_download_profile(item)
                item["_active_download"] = True
                wait_for_download_resume(item)
                self._raise_if_cancelled(item)
                item["item_status"] = ItemStatus.DOWNLOADING
                progress_hook(item, 1, item["item_status"])


                token = get_account_token(
                    service,
                    rotate=config.get("rotate_active_account_number"),
                )
                # If no token is available, mark the item as failed and continue to the next item.
                if token is False:
                    logger.error("No token available for service '%s'", service)
                    item["error"] = f"No active account is available for {service}."
                    item["item_status"] = ItemStatus.FAILED
                    progress_hook(item, 0, item["item_status"])
                    requeue_item(item)
                    continue

                self._raise_if_cancelled(item)
                
                # ---- Fetch metadata -------------------------------------------
                try:
                    metadata_fn = get_metadata_function(service, item_type)
                    if service == "youtube_music":
                        # passing item for YouTube Music album number shim
                        item_metadata = metadata_fn(token, item_id, item)
                    else:
                        item_metadata = metadata_fn(token, item_id)

                    # ---- Emit progress metadata ------------------------------------
                    try:
                        progress_item = item
                        progress_item["name"] = item_metadata.get("title")
                        progress_item["artist"] = item_metadata.get("artists")
                        progress_item["thumbnail"] = item_metadata.get("image_url")
                        progress_item["album"] = item_metadata.get("album_name")

                        progress_hook(progress_item, 25)
                    except Exception as e:
                        logger.error("error emitting progress metadata %s", str(e), exc_info=True)
                except DownloadCancelled:
                    raise
                except (Exception, KeyError) as exc:
                    error_msg = (
                        f"Failed to fetch metadata for '{item_id}', Error: {exc}"
                    )
                    if "Max retries" in str(exc) or "exhausted" in str(exc):
                        error_msg += " (Rate limit exceeded - please try again later or reduce concurrent downloads)"
                    logger.error(error_msg, exc_info=exc)
                    item["error"] = error_msg
                    item["item_status"] = ItemStatus.FAILED
                    
                    requeue_item(item)
                    continue

                # --- Format item path ------------------------------------------
                item_path = format_item_path(item, item_metadata)

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
                    item["error"] = "The service marked this item as unavailable."
                    item["item_status"] = ItemStatus.UNAVAILABLE
                    progress_hook(item, 0, item["item_status"])
                    requeue_item(item)
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
                    item["error"] = "The service marked this item as unavailable."
                    item["item_status"] = ItemStatus.UNAVAILABLE
                    
                    requeue_item(item)
                    continue
                except RuntimeError as exc:
                    logger.error(
                        "Download failed", extra={"item": item, "error": str(exc)}
                    )
                    self._retry_or_fail(item, str(exc))
                    continue

                self._raise_if_cancelled(item)

                # ---- Post-processing (convert, tag, thumbnail, lyrics, ecc) ------------------------------------------
                if service != "generic":
                    progress_hook(item, 50)
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

                self._raise_if_cancelled(item)

                if service != "generic" and item_type in ("track", "podcast_episode"):
                    verification = verify_file(item.get("file_path", ""))
                    if not verification.get("valid"):
                        raise RuntimeError(
                            f"Final file verification failed: {verification.get('reason', 'invalid audio')}"
                        )

                # ---- Mark downloaded ------------------------------------------
                item["item_status"] = ItemStatus.DOWNLOADED
                item["_active_download"] = False
                item["error"] = ""
                logger.info("Item Successfully Downloaded")
                item["progress"] = 100
                # --- Emit final progress metadata --------------------------------
                try:
                    item_progress = item
                    item_progress["bitrate"] = str(bitrate)
                    item_progress["format"] = default_format
                    item_progress["length"] = item_metadata.get("length")
                    if os.path.isfile(item["file_path"]):
                        item_progress["file_size"] = str(
                            os.path.getsize(item["file_path"])
                        )
                        remember_item(item, item["file_path"])
                    progress_hook(item_progress, 100, item["item_status"])
                except Exception as e:
                    logger.error("error emitting progress metadata", exc_info=e)
                
                delay = jittered_delay()
                logger.info("Waiting %s seconds", delay)
                requeue_item(item)
                time.sleep(delay)
                

            except DownloadCancelled as exc:
                if item is not None:
                    logger.info("Download cancelled: %s", item.get("name", item.get("local_id", "unknown")))
                    self._mark_cancelled(item, str(exc))
                continue
            except Exception as exc:
                logger.error(
                    "Unknown Exception: %s",
                    str(exc),
                )
                if item is not None:
                    item["_active_download"] = False
                    if item["item_status"] != ItemStatus.CANCELLED:
                        self._retry_or_fail(item, str(exc))
                    delay = jittered_delay()
                    time.sleep(delay)
                    # remove possible trash files
                    for path in (temp_path, file_path, item.get("file_path", "")):
                        # Keep the temporary download so the next retry can
                        # continue it when the underlying service supports
                        # ranged/continued downloads.
                        if path == temp_path:
                            continue
                        if isinstance(path, str) and path and os.path.exists(path):
                            os.remove(path)

    # ------------------------------------------------------------------
    # Path helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _apply_download_profile(item):
        profiles = config.get("download_profiles", []) or []
        active_id = item.get("profile_id") or config.get("active_download_profile")
        profile = next((entry for entry in profiles if entry.get("id") == active_id), None)
        if profile is None and profiles:
            profile = profiles[0]
        if not profile:
            return
        item["profile_id"] = profile.get("id")
        item["profile_name"] = profile.get("name", profile.get("id", "Default"))
        item["profile_format"] = str(profile.get("format", config.get("track_file_format"))).lstrip(".")
        item["profile_bitrate"] = profile.get("bitrate", config.get("file_bitrate"))
        item["profile_download_path"] = profile.get("download_path", "")

    def _resolve_paths(self, item, item_type, item_path):
        """Return ``(temp_file_path, file_path)`` for *item*."""
        if item_type in ("track", "podcast_episode"):
            dl_root = config.get("audio_download_path")
        else:
            dl_root = config.get("video_download_path")

        if temp_download_path:
            dl_root = temp_download_path[0]
        elif item_type in ("track", "podcast_episode") and item.get("profile_download_path"):
            dl_root = item["profile_download_path"]

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
        try:
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
                    progress_hook(item, 99, ItemStatus.ADDING_TO_M3U)
                    add_to_m3u_file(item, item_metadata)

                item["item_status"] = ItemStatus.ALREADY_EXISTS

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
                    progress_hook(progress_item, 100, ItemStatus.ALREADY_EXISTS)
                except Exception as e:
                    logger.error("error emitting progress metadata", exc_info=e)

                logger.info("File already exists", extra={"track_id": item_id})
                item["progress"] = 100
                time.sleep(0.2)
                # requeue_item(item)
                return True  # caller should continue

            return False  # file not found; proceed with download
        except Exception as e:
            logger.error("Error checking for existing file %s, exception: %s", item_id, str(e))
            raise

    def _overwrite_metadata(
        self, item, item_metadata, service, item_id, item_type, token, file_path
    ):
        """Re-embed lyrics, metadata, and thumbnail on an existing file."""
        # Lyrics
        lyrics_fn = SERVICE_LYRICS_FUNCTIONS.get(service)
        if lyrics_fn and config.get("download_lyrics"):
            progress_hook(item, 60, ItemStatus.GETTING_LYRICS)
            extra = lyrics_fn(token, item_id, item_type, item_metadata, file_path)
            if isinstance(extra, dict):
                item_metadata.update(extra)

        if not config.get("raw_media_download"):
            strip_metadata(item)
            embed_metadata(item, item_metadata)
            if config.get("save_album_cover") or config.get("embed_cover"):
                progress_hook(item, 70, ItemStatus.SETTING_THUMBNAIL)
                set_music_thumbnail(item["file_path"], item_metadata)
            if os.path.splitext(item["file_path"])[1] == ".mp3":
                fix_mp3_metadata(item["file_path"])
        elif config.get("save_album_cover"):
            progress_hook(item, 70, ItemStatus.SETTING_THUMBNAIL)
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
            default_format, bitrate = download_spotify(
                item,
                item_id,
                item_type,
                token,
                temp_path,
            )
            return default_format, bitrate, []

        if service == "deezer":
            default_format, bitrate = download_deezer(
                item,
                item_id,
                token,
                temp_path,
            )
            return default_format, bitrate, []

        if service in ("soundcloud", "tidal", "youtube_music"):
            default_format, bitrate = download_via_ytdlp_audio(
                item, item_metadata, service, item_id, token, temp_path, item_type
            )
            return default_format, bitrate, []

        if service in ("bandcamp", "qobuz"):
            default_format, bitrate = download_http_stream(
                item,
                item_metadata,
                service,
                item_id,
                token,
                temp_path,
            )
            return default_format, bitrate, []

        if service == "apple_music":
            default_format, bitrate = download_apple_music(
                item,
                item_id,
                token,
                temp_path,
            )
            return default_format, bitrate, []

        if service == "crunchyroll":
            video_files = download_crunchyroll(
                item,
                item_metadata,
                item_id,
                token,
                temp_path,
            )
            return "", "", video_files

        if service == "generic":
            if config.get("v2a_enable", False) is True:
                item_codec, item_bitrate = download_generic_v2a(
                    item, item_id, temp_path
                )
                return item_codec, str(item_bitrate), []
            download_generic(item, item_id, temp_path)
            return "", "", []

        raise ValueError(f"No download handler for service '{service}'")


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
            progress_hook(item, 60, ItemStatus.GETTING_LYRICS)
            extra = lyrics_fn(token, item_id, item_type, item_metadata, file_path)
            if isinstance(extra, dict):
                item_metadata.update(extra)

        # Rename temp file to final path with correct extension
        target_format = item.get("profile_format") or config.get("track_file_format")
        target_bitrate = item.get("profile_bitrate") or config.get("file_bitrate")
        if config.get("raw_media_download") or config.get("use_source_format"):
            final_path = file_path + default_format
        elif item_type == "track":
            final_path = file_path + "." + target_format
        else:
            final_path = file_path + "." + config.get("podcast_file_format")

        os.rename(temp_path, final_path)
        item["file_path"] = final_path

        if not config.get("raw_media_download"):
            progress_hook(item, 70, ItemStatus.CONVERTING)
            if item.get("profile_bitrate") or config.get("use_custom_file_bitrate"):
                bitrate = target_bitrate
            convert_audio_format(
                final_path,
                bitrate,
                default_format,
                force_bitrate=bool(item.get("profile_bitrate")),
            )
            embed_metadata(item, item_metadata)

            if config.get("save_album_cover") or config.get("embed_cover"):
                progress_hook(item, 80, ItemStatus.SETTING_THUMBNAIL)
                set_music_thumbnail(final_path, item_metadata)

            if os.path.splitext(final_path)[1] == ".mp3":
                fix_mp3_metadata(final_path)

        elif config.get("save_album_cover"):
            progress_hook(item, 80, ItemStatus.SETTING_THUMBNAIL)
            set_music_thumbnail(final_path, item_metadata)

        # M3U
        if config.get("create_m3u_file") and item.get("parent_category") == "playlist":
            progress_hook(item, 90, ItemStatus.ADDING_TO_M3U)
            add_to_m3u_file(item, item_metadata)

    def _finalize_video(self, item, item_metadata, item_type, file_path, video_files):
        """Rename temp video files and mux them together."""
        for vf in video_files:
            final_path = vf["path"].replace("~", "")
            os.rename(vf["path"], final_path)
            vf["path"] = final_path

        if not config.get("raw_media_download"):
            progress_hook(item, 70, ItemStatus.CONVERTING)
            output_format = config.get(
                "show_file_format" if item_type == "episode" else "movie_file_format"
            )
            convert_video_format(
                item, file_path, output_format, video_files, item_metadata
            )
            item["file_path"] = file_path + "." + output_format
        else:
            item["file_path"] = file_path + ".mp4"

