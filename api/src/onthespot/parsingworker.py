# ---------------------------------------------------------------------------
# Parsing worker
# ---------------------------------------------------------------------------
import queue
import threading
import time

from .accounts import get_account_token
from .api.registry import (
    SERVICE_ALBUM_TRACK_ID_FUNCTIONS,
    SERVICE_ARTIST_ALBUM_ID_FUNCTIONS,
    SERVICE_CHANNEL_TRACK_ID_FUNCTIONS,
    SERVICE_EPISODE_ID_FUNCTIONS,
    SERVICE_LABEL_ALBUM_ID_FUNCTIONS,
    SERVICE_MIX_DATA_FUNCTIONS,
    SERVICE_PLAYLIST_DATA_FUNCTIONS,
    SERVICE_PODCAST_EPISODE_ID_FUNCTIONS,
)
from .api.spotify import reinit_spotify_session, spotify_get_playlist
from .basemodels import DownloadProfile, QueueItem
from .constants import (
    ARTIST_TYPES,
    COLLECTION_TYPES,
    PODCAST_TYPES,
    SHOW_TYPES,
    SINGLE_ITEM_TYPES,
    ItemStatus,
)
from .resources.exceptions import UnsupportedItemError
from .runtimedata import config, download_queue, download_queue_lock, get_logger, parsing, pending
from .utils import format_local_id

logger = get_logger("ParsingWorker")

# Errors that mean the librespot session died. RuntimeError and queue.Empty
# match services_middleware; OSError also covers ConnectionError and requests'
# connection errors.
_DEAD_SESSION_ERRORS = (OSError, RuntimeError, queue.Empty)


class ParsingWorker:
    """Background thread that drains the ``parsing`` queue.

    Each item in the queue represents a service collection (album, playlist,
    artist, …) or an individual track.  This worker expands collections into
    their constituent tracks and adds them to ``pending``, where they wait
    for a :class:`~onthespot.main.QueueWorker` to pick them up.

    Emits :attr:`error` with a human-readable message whenever a collection
    cannot be fetched (e.g. 404 or rate limit).  The GUI can connect to this
    signal to show an error dialog.
    """

    def __init__(self) -> None:
        super().__init__()
        self.is_running = True
        self.thread = threading.Thread(target=self.run, daemon=True)

    def start(self) -> None:
        """Start the background thread."""
        self.thread.start()

    def stop(self) -> None:
        """Signal the worker to stop and wait for the thread to finish."""
        logger.info("Stopping Parsing Worker")
        self.is_running = False
        self.thread.join()

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    def run(self) -> None:
        """Process items from the `parsing` queue until stopped."""
        while self.is_running:
            if parsing.empty():
                time.sleep(1)
                continue

            try:
                item = parsing.get_nowait()

                logger.info("Parsing: %s", item)

                service = item["item_service"]
                item_type = item["item_type"]
                item_id = item["item_id"]
                item_url = item["item_url"]  # Captured here and passed down
                token = get_account_token(service)

                self._dispatch(service, item_type, item_id, item_url, token)

            except Exception as exc:
                self._handle_parsing_error(exc, item_type, item_id, item_url, service)

    # ------------------------------------------------------------------
    # Dispatch helpers
    # ------------------------------------------------------------------

    def _dispatch(self, service, item_type, item_id, item_url, token):
        """Route the parsed item to the correct expansion handler."""

        # --- Spotify playlist (read through librespot, not the Web API) ---
        if service == "spotify" and item_type == "playlist":
            self._expand_spotify_playlist(token, item_id, item_url)
            return

        # --- YouTube Music artist (channel) ---
        if service == "youtube_music" and item_type == "artist":
            self._expand_youtube_music_channel(token, item_id, service, item_url)  # URL Passed down
            return

        # --- Single downloadable items ---
        if item_type in SINGLE_ITEM_TYPES:
            self._enqueue_single_item(service, item_type, item_id, item_url)
            return

        # --- Podcast / audiobook (expand to episodes) ---
        if item_type in PODCAST_TYPES:
            self._expand_podcast(service, item_type, item_id, token, item_url)  # URL Passed down
            return

        # --- Album / playlist / mix (expand to tracks) ---
        if item_type in COLLECTION_TYPES:
            self._expand_collection(service, item_type, item_id, token, item_url)
            return

        # --- Artist / label (expand to albums, then recurse) ---
        if item_type in ARTIST_TYPES:
            self._expand_artist_or_label(service, item_type, item_id, token, item_url)  # URL Passed down
            return

        # --- Crunchyroll show / season ---
        if item_type in SHOW_TYPES:
            self._expand_show(service, item_type, item_id, token, item_url)  # URL Passed down
            return

        raise UnsupportedItemError(f"No handler for {service} {item_type}")

    # ------------------------------------------------------------------
    # Individual expansion handlers
    # ------------------------------------------------------------------
    def _get_active_profile(self):
        profiles = config.get("download_profiles", []) or []
        active_id = config.get("active_download_profile", "mp3-320")
        profile = next((entry for entry in profiles if entry.get("id") == active_id), None)
        if profile is None and profiles:
            profile = profiles[0]
        if not profile:
            return
        download_profile = DownloadProfile(
            id=profile.get("id"),
            name=profile.get("name", profile.get("id", "mp3-320")),
            format=profile.get("format", "mp3"),
            bitrate=profile.get("bitrate", 320),
        )
        return download_profile

    def _enqueue_single_item(self, service, item_type, item_id, item_url=""):
        local_id = format_local_id(item_id)
        item = QueueItem(
            local_id=local_id,
            item_service=service,
            item_type=item_type,
            item_id=item_id,
            item_url=item_url,
            parent_category=item_type,
            item_status=ItemStatus.WAITING,
            download_profile=self._get_active_profile(),
        )
        pending.put_nowait(item)

    def _expand_spotify_playlist(self, token, playlist_id, item_url):
        try:
            try:
                playlist_name, playlist_by, entries = spotify_get_playlist(token, playlist_id)
            except _DEAD_SESSION_ERRORS:
                reinit_spotify_session(token)
                playlist_name, playlist_by, entries = spotify_get_playlist(get_account_token("spotify"), playlist_id)
        except Exception as exc:
            self._emit_collection_error(exc, "spotify", "playlist", playlist_id, item_url)
            return

        if not entries:
            logger.warning(
                "Spotify playlist %s has no tracks or episodes to download (local files are skipped).",
                playlist_id,
            )
            return

        profile = self._get_active_profile()
        for position, item_type, item_id in entries:
            kind = "episode" if item_type == "podcast_episode" else "track"
            pending.put_nowait(
                QueueItem(
                    local_id=format_local_id(item_id),
                    item_service="spotify",
                    item_type=item_type,
                    item_id=item_id,
                    item_url=f"https://open.spotify.com/{kind}/{item_id}",
                    parent_category="playlist",
                    playlist_name=playlist_name,
                    playlist_by=playlist_by,
                    playlist_number=str(position),
                    item_status=ItemStatus.WAITING,
                    download_profile=profile,
                )
            )

    def _expand_youtube_music_channel(
        self, token, item_id, service, item_url
    ):  # Added item_url (using item_id as channel_id for consistency with original logic)
        get_track_ids = SERVICE_CHANNEL_TRACK_ID_FUNCTIONS.get(service)
        if get_track_ids is None:
            raise NotImplementedError
        for track_id in get_track_ids(token, item_id):  # item_id used as channel ID here
            local_id = format_local_id(track_id)
            item = QueueItem(
                local_id=local_id,
                item_service=service,
                item_type="track",
                item_id=track_id,
                item_url=item_url,
                parent_category="album",
                item_status=ItemStatus.WAITING,
                download_profile=self._get_active_profile(),
            )
            pending.put_nowait(item)

    def _expand_podcast(self, service, item_type, item_id, token, item_url):  # Added item_url
        get_episode_ids = SERVICE_PODCAST_EPISODE_ID_FUNCTIONS.get(service)
        if get_episode_ids is None:
            raise NotImplementedError
        for episode_id in get_episode_ids(token, item_id):
            local_id = format_local_id(episode_id)
            item = QueueItem(
                local_id=local_id,
                item_service=service,
                item_type="podcast_episode",
                item_id=episode_id,
                item_url=item_url,
                parent_category=item_type,
                item_status=ItemStatus.WAITING,
                download_profile=self._get_active_profile(),
            )
            pending.put_nowait(item)

    def _expand_collection(self, service, item_type, item_id, token, item_url):
        """Expand an album, playlist, or mix into individual track entries. (No change needed as URL was already passed in)."""
        playlist_name = ""
        playlist_by = ""
        try:
            if item_type == "album":
                get_track_ids = SERVICE_ALBUM_TRACK_ID_FUNCTIONS.get(service)
                if get_track_ids is None:
                    raise NotImplementedError
                track_ids = get_track_ids(token, item_id)
            elif item_type == "mix":
                get_mix = SERVICE_MIX_DATA_FUNCTIONS.get(service)
                if get_mix is None:
                    raise NotImplementedError
                playlist_name, playlist_by, track_ids = get_mix(token, item_id)
            else:
                get_playlist = SERVICE_PLAYLIST_DATA_FUNCTIONS.get(service)
                if get_playlist is None:
                    raise NotImplementedError
                playlist_name, playlist_by, track_ids = get_playlist(token, item_id)

        except Exception as exc:
            self._emit_collection_error(exc, service, item_type, item_id, item_url)
            return

        # Normalise mix to playlist for the category label
        effective_category = "playlist" if item_type == "mix" else item_type

        for index, track_id in enumerate(track_ids):
            local_id = format_local_id(track_id)
            item = QueueItem(
                local_id=local_id,
                item_service=service,
                item_type="track",
                item_id=track_id,
                item_url=item_url,
                parent_category=effective_category,
                playlist_name=playlist_name,
                playlist_by=playlist_by,
                playlist_number=str(index + 1),
                item_status=ItemStatus.WAITING,
                download_profile=self._get_active_profile(),
            )
            pending.put_nowait(item)

    def _expand_artist_or_label(self, service, item_type, item_id, token, item_url):  # Added item_url
        """Expand an artist or label into their albums (which are then re-parsed)."""
        if item_type == "label":
            get_album_ids = SERVICE_LABEL_ALBUM_ID_FUNCTIONS.get(service)
        else:
            get_album_ids = SERVICE_ARTIST_ALBUM_ID_FUNCTIONS.get(service)

        if get_album_ids is None:
            raise NotImplementedError

        for album_id in get_album_ids(token, item_id):
            # When recursively parsing, we use the original URL of the parent entity
            # as context for all its children.
            new_item = {
                "item_url": item_url,  # Pass down existing url
                "item_service": service,
                "item_type": "album",
                "item_id": album_id,
            }
            parsing.put_nowait(new_item)

    def _expand_show(self, service, item_type, item_id, token, item_url):  # Added item_url
        get_episode_ids = SERVICE_EPISODE_ID_FUNCTIONS.get(service)
        if get_episode_ids is None:
            raise NotImplementedError
        for episode_id in get_episode_ids(token, item_id):
            local_id = format_local_id(episode_id)
            item = QueueItem(
                local_id=local_id,
                item_service=service,
                item_type="episode",
                item_id=episode_id,
                item_url=item_url,
                parent_category=item_type,
                item_status=ItemStatus.WAITING,
                download_profile=self._get_active_profile(),
            )
            pending.put_nowait(item)

    # ------------------------------------------------------------------
    # Error helpers (No changes required here as they don't dispatch further items)
    # ------------------------------------------------------------------

    def _emit_collection_error(self, exc, service, item_type, item_id, item_url):
        error_str = str(exc)
        service_name = service.replace("_", " ").title()

        if "404" in error_str or "not found" in error_str.lower():
            if item_type in ("playlist", "mix"):
                msg = (
                    f"{item_type.title()} not found: The {service_name} {item_type} "
                    f"was not found or is private.\n\n{item_type.title()} ID: {item_id}\n\n"
                    f"Please verify:\n"
                    f"• The {item_type} URL is correct\n"  # Now has access to item_url context if needed here too
                    f"• The {item_type} is public or you have access\n"
                    f"• You're logged into the correct {service_name} account"
                )
            else:
                msg = (
                    f"Album not found: The {service_name} album was not found "
                    f"or is unavailable.\n\nAlbum ID: {item_id}\n"
                )
        elif "429" in error_str or "rate limit" in error_str.lower():
            msg = (
                f"Rate limit exceeded for {service_name}. Too many requests — "
                f"please wait before adding more items.\n\n"
                f"Tip: Try disabling metadata options in Settings to reduce API calls."
            )
        elif "Max retries" in error_str or "exhausted" in error_str:
            msg = (
                f"Failed to load {item_type} after multiple retries. "
                f"The service may be unavailable.\n\nDetails: {error_str}"
            )
        else:
            msg = f"Failed to load {service_name} {item_type}: {error_str}\n\n{item_type.title()} ID: {item_id}"

        logger.error(msg)
        logger.error("Error in _emit_collection_error for %s, info: %s", item_type, str(exc))

    def _handle_parsing_error(self, exc, item_type, item_id, item_url, service):
        # ... (This function remains functionally similar and already receives all necessary context)
        error_str = str(exc)
        service_name = service.replace("_", " ").title()

        if "404" in error_str or "not found" in error_str.lower():
            msg = f"{item_type.title()} not found: The {service_name} {item_type} was not found.\n\nDetails: {item_url}"
        elif "429" in error_str or "rate limit" in error_str.lower():
            msg = (
                f"Rate limit exceeded for {service_name}. Too many requests — "
                f"please wait before adding more items.\n\n"
                f"Tip: Try disabling metadata options in Settings to reduce API calls."
            )
        elif "Max retries" in error_str or "exhausted" in error_str:
            msg = (
                f"Failed to load {item_type} after multiple retries. "
                f"The service may be unavailable.\n\nDetails: {error_str}"
            )
        else:
            msg = f"Error parsing {item_type}: {error_str}\n\nURL: {item_url}"

        logger.error(msg)
        logger.error("Unknown Exception: %s", str(exc))
