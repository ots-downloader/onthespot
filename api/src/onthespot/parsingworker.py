# ---------------------------------------------------------------------------
# Parsing worker
# ---------------------------------------------------------------------------
import threading
import time


from .accounts import get_account_token
from .runtimedata import (
    download_queue,
    download_queue_lock,
    get_logger,
    parsing,
    parsing_lock,
    pending,
    pending_lock,
)
from .utils import format_local_id
from .constants import ItemStatus
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
from .api.spotify import (
    spotify_get_liked_songs,
    spotify_get_playlist_data,
    spotify_get_playlist_items,
    spotify_get_your_episodes,
)

logger = get_logger("ParsingWorker")


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
            if not parsing:
                time.sleep(0.2)
                continue

            try:
                # Pop the next item outside the lock (pop is atomic for dicts
                # in CPython but we use the lock for cross-platform safety).
                with parsing_lock:
                    item_id = next(iter(parsing))
                    item = parsing.pop(item_id)

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

        # --- Spotify special collections ---
        if service == "spotify":
            if item_type == "playlist":
                self._expand_spotify_playlist(
                    token, item_url, item_id
                )  # URL Passed down
                return
            if item_type == "liked_songs":
                self._expand_spotify_liked_songs(token, item_url)  # URL Passed down
                return
            if item_type == "your_episodes":
                self._expand_spotify_your_episodes(token, item_url)  # URL Passed down
                return

        # --- YouTube Music artist (channel) ---
        if service == "youtube_music" and item_type == "artist":
            self._expand_youtube_music_channel(
                token, item_id, service, item_url
            )  # URL Passed down
            return

        # --- Single downloadable items ---
        if item_type in ("track", "podcast_episode", "movie", "episode"):
            self._enqueue_single_item(service, item_type, item_id, item_url)
            return

        # --- Podcast / audiobook (expand to episodes) ---
        if item_type in ("podcast", "audiobook"):
            self._expand_podcast(
                service, item_type, item_id, token, item_url
            )  # URL Passed down
            return

        # --- Album / playlist / mix (expand to tracks) ---
        if item_type in ("album", "playlist", "mix"):
            self._expand_collection(service, item_type, item_id, token, item_url)
            return

        # --- Artist / label (expand to albums, then recurse) ---
        if item_type in ("artist", "label"):
            self._expand_artist_or_label(
                service, item_type, item_id, token, item_url
            )  # URL Passed down
            return

        # --- Crunchyroll show / season ---
        if item_type in ("show", "season"):
            self._expand_show(
                service, item_type, item_id, token, item_url
            )  # URL Passed down
            return

    # ------------------------------------------------------------------
    # Individual expansion handlers
    # ------------------------------------------------------------------

    def _enqueue_single_item(self, service, item_type, item_id, item_url=""):
        local_id = format_local_id(item_id)
        pending.put_nowait(
            {
                "local_id": local_id,
                "item_service": service,
                "item_type": item_type,
                "item_id": item_id,
                "item_url": item_url,
                "parent_category": item_type,
                "available": True,
                "item_status": ItemStatus.WAITING,
                "item_url": item_url,  # Already included here
            }
        )

    def _enqueue_playlist_item(self, item):
        """Expose the whole playlist in the UI before downloading starts."""
        item["queue_preloaded"] = True
        with download_queue_lock:
            item["queue_position"] = max(
                [entry.get("queue_position", -1) for entry in download_queue.values()],
                default=-1,
            ) + 1
            item["priority"] = 0
            download_queue[item["local_id"]] = item
        pending.put_nowait(item)

    def _expand_spotify_playlist(self, token, playlist_id):
        try:
            items = spotify_get_playlist_items(token, playlist_id)
            playlist_name, playlist_by = spotify_get_playlist_data(token, playlist_id)
        except Exception as exc:
            error_str = str(exc)
            if "404" in error_str or "not found" in error_str.lower():
                msg = (
                    f"Playlist not found: The Spotify playlist was not found, "
                    f"was created by Spotify (unavailable in the Web API) or is private.\n\n"
                    f"Playlist ID: {playlist_id}\n\n"
                    f"Please verify:\n"
                    f"• The playlist URL is correct\n"  # Now has access to item_url context
                    f"• The playlist was NOT created by Spotify\n"
                    f"• The playlist is public or you have access\n"
                    f"• You're logged into the correct Spotify account"
                )
            else:
                msg = f"Failed to load Spotify playlist: {error_str}\n\nPlaylist ID: {playlist_id}"
            logger.error(msg)
            logger.error("Playlist fetch failed: %s", exc)
            return

        for index, item in enumerate(items):
            try:
                track_id = item["track"]["id"]
                track_type = item["track"]["type"]
                local_id = format_local_id(track_id)

                self._enqueue_playlist_item({
                    "local_id": local_id,
                    "item_service": "spotify",
                    "item_type": track_type,
                    "item_id": track_id,
                    "parent_category": "playlist",
                    "playlist_name": playlist_name,
                    "playlist_by": playlist_by,
                    "playlist_number": str(index + 1),
                    "available": True,
                    "item_status": ItemStatus.WAITING
                })
            except TypeError:
                logger.error("TypeError for %s", item)

    def _expand_spotify_liked_songs(self, token, item_url):  # Added item_url
        for index, track in enumerate(spotify_get_liked_songs(token)):
            track_id = track["track"]["id"]
            local_id = format_local_id(track_id)
            self._enqueue_playlist_item({
                "local_id": local_id,
                "item_service": "spotify",
                "item_type": "track",
                "item_id": track_id,
                "parent_category": "playlist",
                "playlist_name": "Liked Songs",
                "playlist_by": "me",
                "playlist_number": str(index + 1),
                "available": True,
                "item_status": ItemStatus.WAITING
            })

    def _expand_spotify_your_episodes(self, token, item_url):  # Added item_url
        for index, track in enumerate(spotify_get_your_episodes(token)):
            episode_id = track["episode"]["id"]
            if not episode_id:
                raise NotImplementedError
            local_id = format_local_id(episode_id)

            pending.put_nowait(
                {
                    "local_id": local_id,
                    "item_service": "spotify",
                    "item_type": "podcast_episode",
                    "item_id": episode_id,
                    "parent_category": "playlist",
                    "playlist_name": "Your Episodes",
                    "playlist_by": "me",
                    "playlist_number": str(index + 1),
                    "available": True,
                    "item_status": ItemStatus.WAITING,
                    "item_url": item_url,  # Added to queue item
                }
            )

    def _expand_youtube_music_channel(
        self, token, item_id, service, item_url
    ):  # Added item_url (using item_id as channel_id for consistency with original logic)
        get_track_ids = SERVICE_CHANNEL_TRACK_ID_FUNCTIONS.get(service)
        if get_track_ids is None:
            raise NotImplementedError
        for track_id in get_track_ids(
            token, item_id
        ):  # item_id used as channel ID here
            local_id = format_local_id(track_id)
            pending.put_nowait(
                {
                    "local_id": local_id,
                    "item_service": service,
                    "item_type": "track",
                    "item_id": track_id,
                    "parent_category": "album",
                    "available": True,
                    "item_status": ItemStatus.WAITING,
                    "item_url": item_url,  # Added to queue item
                }
            )

    def _expand_podcast(
        self, service, item_type, item_id, token, item_url
    ):  # Added item_url
        get_episode_ids = SERVICE_PODCAST_EPISODE_ID_FUNCTIONS.get(service)
        if get_episode_ids is None:
            raise NotImplementedError
        for episode_id in get_episode_ids(token, item_id):
            local_id = format_local_id(episode_id)

            pending.put_nowait(
                {
                    "local_id": local_id,
                    "item_service": service,
                    "item_type": "podcast_episode",
                    "item_id": episode_id,
                    "parent_category": item_type,
                    "available": True,
                    "item_status": ItemStatus.WAITING,
                    "item_url": item_url,  # Added to queue item
                }
            )

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
            queued_item = {
                "local_id": local_id,
                "item_service": service,
                "item_type": "track",
                "item_id": track_id,
                "parent_category": effective_category,
                "playlist_name": playlist_name,
                "playlist_by": playlist_by,
                "playlist_number": str(index + 1),
                "available": True,
                "item_status": ItemStatus.WAITING
            }
            if effective_category == "playlist":
                self._enqueue_playlist_item(queued_item)
            else:
                pending.put_nowait(queued_item)

    def _expand_artist_or_label(
        self, service, item_type, item_id, token, item_url
    ):  # Added item_url
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
            with parsing_lock:
                parsing[album_id] = new_item

    def _expand_show(
        self, service, item_type, item_id, token, item_url
    ):  # Added item_url
        get_episode_ids = SERVICE_EPISODE_ID_FUNCTIONS.get(service)
        if get_episode_ids is None:
            raise NotImplementedError
        for episode_id in get_episode_ids(token, item_id):
            local_id = format_local_id(episode_id)
            with pending_lock:
                pending.put_nowait(
                    {
                        "local_id": local_id,
                        "item_service": service,
                        "item_type": "episode",
                        "item_id": episode_id,
                        "parent_category": item_type,
                        "available": True,
                        "item_status": ItemStatus.WAITING,
                        "item_url": item_url,  # Added to queue item
                    }
                )

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
            msg = (
                f"Failed to load {service_name} {item_type}: {error_str}\n\n"
                f"{item_type.title()} ID: {item_id}"
            )

        logger.error(msg)
        logger.error(
            "Error in _emit_collection_error for %s, info: %s", item_type, str(exc)
        )

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
