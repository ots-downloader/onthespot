"""
parse_item.py
~~~~~~~~~~~~~

URL parsing and the item-parsing worker thread.

:func:`parse_url` accepts any supported service URL and adds the resolved
item to the ``parsing`` queue.

:class:`ParsingWorker` is a long-running background thread that drains the
``parsing`` queue and fans each item out into ``pending`` (individual tracks /
episodes) ready for the download workers to pick up.
"""

import re
import threading
import time
import traceback

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
from .api.deezer import deezer_parse_url
from .api.generic import generic_get_track_metadata
from .api.soundcloud import soundcloud_parse_url
from .api.spotify import (
    spotify_get_liked_songs,
    spotify_get_playlist_data,
    spotify_get_playlist_items,
    spotify_get_your_episodes,
)
from .otsconfig import config
from .runtimedata import (
    account_pool,
    download_queue,
    get_logger,
    parsing,
    parsing_lock,
    pending,
    pending_lock,
)
from .utils import format_local_id

logger = get_logger("parse_item")

# ---------------------------------------------------------------------------
# Compiled URL regular expressions
# ---------------------------------------------------------------------------

# Audio services
APPLE_MUSIC_URL_REGEX = re.compile(
    r"https?://music.apple.com/([a-z]{2})/(?P<type>album|playlist|artist)"
    r"(?:/(?P<title>[-a-z0-9]+))?/(?P<id>[\w.-]+)"
    r"(?:\?i=(?P<track_id>\d+))?(?:&.*)?$"
)
BANDCAMP_URL_REGEX = re.compile(
    r"https?://[a-z0-9-]+.bandcamp.com(?:/(?P<type>track|album|music)/[a-z0-9-]+)?"
)
DEEZER_URL_REGEX = re.compile(
    r"https?://www.deezer.com/(?:[a-z]{2}/)?(?P<type>album|playlist|track|artist)/(?P<id>\d+)"
)
DEEZER_SHARE_URL_REGEX = re.compile(r"https?://link.deezer.com/s/([-a-z0-9]+)")
QOBUZ_URL_REGEX = re.compile(
    r"https?://(www.|play.|open.)?qobuz.com/(?:[a-z]{2}-[a-z]{2}/)?"
    r"(?P<type>album|playlist|artist|track|label|interpreter)"
    r"(?:/[^/]+)?(?:/[^/]+)?/(?P<id>[-a-z0-9]+)"
)
SOUNDCLOUD_URL_REGEX = re.compile(r"https?://(m.)?soundcloud.com/[-\w:/]+")
SPOTIFY_URL_REGEX = re.compile(
    r"https?://open.spotify.com/(intl-([a-zA-Z]+)/|)"
    r"(?P<type>track|album|artist|playlist|episode|show)/(?P<id>[0-9a-zA-Z]{22})"
    r"(\?si=.+?)?$"
)
TIDAL_URL_REGEX = re.compile(
    r"https?://(www.|listen.)?tidal.com/(browse/)?"
    r"(?P<type>album|track|artist|playlist|mix)/(?P<id>[-a-z0-9]+)"
)
YOUTUBE_MUSIC_URL_REGEX = re.compile(
    r"https?://music.youtube.com/"
    r"(watch\?v=(?P<video_id>[a-zA-Z0-9_-]+)"
    r"|channel/(?P<channel_id>[a-zA-Z0-9_-]+)"
    r"|playlist\?list=(?P<playlist_id>[a-zA-Z0-9_-]+))"
)

# Video services
CRUNCHYROLL_URL_REGEX = re.compile(
    r"https?://(www.)?crunchyroll.com/(?P<type>watch|series)/(musicvideo/)?"
    r"(?P<id>[-A-Z0-9]+)/(?P<title>[-a-z0-9]+)"
)

# ---------------------------------------------------------------------------
# Static Spotify collection URLs (not matched by the main regex)
# ---------------------------------------------------------------------------

_SPOTIFY_LIKED_SONGS_URL = "https://open.spotify.com/collection/tracks"
_SPOTIFY_YOUR_EPISODES_URL = "https://open.spotify.com/collection/your-episodes"


# ---------------------------------------------------------------------------
# UrlMatcher — encapsulates the URL-to-(service, type, id) resolution logic
# ---------------------------------------------------------------------------


class UrlMatcher:
    """Resolve a URL into ``(service, item_type, item_id)`` tuple.

    Returns ``None`` when the URL is not recognised by any built-in pattern
    (callers should then try the generic yt-dlp fallback).
    Return service as ``__handled__`` when parsed by the matcher itself (deezer share)
    """

    def match(self, url: str):
        """Try each known service pattern in order.

        Returns
        -------
        tuple[str, str, str] | None
            ``(service, item_type, item_id)`` or ``None`` if unrecognised.
        """
        result = (
            self._try_apple_music(url)
            or self._try_bandcamp(url)
            or self._try_deezer(url)
            or self._try_deezer_share(url)
            or self._try_qobuz(url)
            or self._try_soundcloud(url)
            or self._try_spotify_static(url)
            or self._try_spotify(url)
            or self._try_tidal(url)
            or self._try_youtube_music(url)
            or self._try_crunchyroll(url)
        )
        return result

    # ------------------------------------------------------------------
    # Per-service helpers
    # ------------------------------------------------------------------

    def _try_apple_music(self, url):
        match = APPLE_MUSIC_URL_REGEX.search(url)
        if not match:
            return None
        item_id = match.group("id")
        item_type = match.group("type")
        if match.group("track_id"):
            item_id = match.group("track_id")
            item_type = "track"
        return ("apple_music", item_type, item_id)

    def _try_bandcamp(self, url):
        match = BANDCAMP_URL_REGEX.search(url)
        if not match:
            return None
        item_type = match.group("type") or "artist"
        if item_type == "music":
            item_type = "artist"
        return ("bandcamp", item_type, url)

    def _try_deezer(self, url):
        match = DEEZER_URL_REGEX.search(url)
        if not match:
            return None
        return ("deezer", match.group("type"), match.group("id"))

    def _try_deezer_share(self, url):
        if not DEEZER_SHARE_URL_REGEX.search(url):
            return None
        # Delegate resolution to the deezer API layer; signal caller with a
        # sentinel so parse_url knows it was handled.
        deezer_parse_url(url)
        return ("__handled__", "", "")

    def _try_qobuz(self, url):
        match = QOBUZ_URL_REGEX.search(url)
        if not match:
            return None
        item_type = match.group("type")
        if item_type == "interpreter":
            item_type = "artist"
        return ("qobuz", item_type, match.group("id"))

    def _try_soundcloud(self, url):
        if not SOUNDCLOUD_URL_REGEX.search(url):
            return None
        token = get_account_token("soundcloud")
        item_type, item_id = soundcloud_parse_url(url, token)
        return ("soundcloud", item_type, item_id)

    def _try_spotify_static(self, url):
        if url == _SPOTIFY_LIKED_SONGS_URL:
            return ("spotify", "liked_songs", None)
        if url == _SPOTIFY_YOUR_EPISODES_URL:
            return ("spotify", "your_episodes", None)
        return None

    def _try_spotify(self, url):
        match = SPOTIFY_URL_REGEX.search(url)
        if not match:
            return None
        item_id = match.group("id")
        item_type = match.group("type")
        if item_type == "episode":
            item_type = "podcast_episode"
        elif item_type == "show":
            item_type = "podcast"
        return ("spotify", item_type, item_id)

    def _try_tidal(self, url):
        match = TIDAL_URL_REGEX.search(url)
        if not match:
            return None
        return ("tidal", match.group("type"), match.group("id"))

    def _try_youtube_music(self, url):
        match = YOUTUBE_MUSIC_URL_REGEX.search(url)
        if not match:
            return None
        if match.group("video_id"):
            return ("youtube_music", "track", match.group("video_id"))
        if match.group("channel_id"):
            return ("youtube_music", "artist", match.group("channel_id"))
        if match.group("playlist_id"):
            return ("youtube_music", "playlist", match.group("playlist_id"))
        return None

    def _try_crunchyroll(self, url):
        match = CRUNCHYROLL_URL_REGEX.search(url)
        if not match:
            return None
        item_id = match.group("id") + "/" + match.group("title")
        item_type = "episode" if match.group("type") == "watch" else "show"
        return ("crunchyroll", item_type, item_id)


_url_matcher = UrlMatcher()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def parse_url(url: str) -> bool | None:
    """Resolve *url* and add the resulting item to the parsing queue.

    Returns ``True`` if the URL was recognised and enqueued (or immediately
    handled), ``False`` if it was not recognised and there is no generic
    fallback available, or ``None`` for non-URL inputs such as local file
    paths (handled by the search layer).
    """
    resolved = _url_matcher.match(url)

    if resolved is not None:
        service, item_type, item_id = resolved
        if service == "__handled__":
            # URL was handled entirely inside _try_deezer_share
            return True
        with parsing_lock:
            parsing[item_id] = {
                "item_url": url,
                "item_service": service,
                "item_type": item_type,
                "item_id": item_id,
            }
        return None  # enqueued; caller does not need a boolean

    # Unknown URL — fall back to yt-dlp via the generic service
    is_generic_enabled = any(acc["service"] == "generic" for acc in account_pool)
    if not is_generic_enabled:
        logger.info(f"Invalid Url: {url}")
        return False

    try:
        logger.info(f"Unable to parse url falling back to yt-dlp: {url}")
        item_metadata = generic_get_track_metadata("", url)
        if not item_metadata:
            # Playlist handled internally by generic_get_track_metadata
            return True
        with parsing_lock:
            parsing[url] = {
                "item_url": url,
                "item_service": "generic",
                "item_type": "track",
                "item_id": url,
            }
        return None
    except Exception as exc:
        logger.info(f'Error — possibly invalid URL: {url}, "{exc}"')
        return False


# ---------------------------------------------------------------------------
# Parsing worker
# ---------------------------------------------------------------------------


class ParsingWorker:
    """Background thread that drains the ``parsing`` queue.

    Each item in the queue represents a service collection (album, playlist,
    artist, …) or an individual track.  This worker expands collections into
    their constituent tracks and adds them to ``pending``, where they wait
    for a :class:`~onthespot.downloader.DownloadWorker` to pick them up.

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
        """Process items from the ``parsing`` queue until stopped."""
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

                logger.info(f"Parsing: {item}")

                service = item["item_service"]
                item_type = item["item_type"]
                item_id = item["item_id"]
                item_url = item["item_url"]
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
                self._expand_spotify_playlist(token, item_id)
                return
            if item_type == "liked_songs":
                self._expand_spotify_liked_songs(token)
                return
            if item_type == "your_episodes":
                self._expand_spotify_your_episodes(token)
                return

        # --- YouTube Music artist (channel) ---
        if service == "youtube_music" and item_type == "artist":
            self._expand_youtube_music_channel(token, item_id, service)
            return

        # --- Single downloadable items ---
        if item_type in ("track", "podcast_episode", "movie", "episode"):
            self._enqueue_single_item(service, item_type, item_id)
            return

        # --- Podcast / audiobook (expand to episodes) ---
        if item_type in ("podcast", "audiobook"):
            self._expand_podcast(service, item_type, item_id, token)
            return

        # --- Album / playlist / mix (expand to tracks) ---
        if item_type in ("album", "playlist", "mix"):
            self._expand_collection(service, item_type, item_id, token, item_url)
            return

        # --- Artist / label (expand to albums, then recurse) ---
        if item_type in ("artist", "label"):
            self._expand_artist_or_label(service, item_type, item_id, token)
            return

        # --- Crunchyroll show / season ---
        if item_type in ("show", "season"):
            self._expand_show(service, item_type, item_id, token)
            return

    # ------------------------------------------------------------------
    # Individual expansion handlers
    # ------------------------------------------------------------------

    def _enqueue_single_item(self, service, item_type, item_id):
        local_id = format_local_id(item_id)
        with pending_lock:
            pending[local_id] = {
                "local_id": local_id,
                "item_service": service,
                "item_type": item_type,
                "item_id": item_id,
                "parent_category": item_type,
            }

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
                    f"• The playlist URL is correct\n"
                    f"• The playlist was NOT created by Spotify\n"
                    f"• The playlist is public or you have access\n"
                    f"• You're logged into the correct Spotify account"
                )
            else:
                msg = f"Failed to load Spotify playlist: {error_str}\n\nPlaylist ID: {playlist_id}"
            logger.error(msg)
            logger.error(f"Playlist fetch failed: {traceback.format_exc()}")
            return

        for index, item in enumerate(items):
            try:
                track_id = item["track"]["id"]
                track_type = item["track"]["type"]
                local_id = format_local_id(track_id)
                with pending_lock:
                    pending[local_id] = {
                        "local_id": local_id,
                        "item_service": "spotify",
                        "item_type": track_type,
                        "item_id": track_id,
                        "parent_category": "playlist",
                        "playlist_name": playlist_name,
                        "playlist_by": playlist_by,
                        "playlist_number": str(index + 1),
                    }
            except TypeError:
                logger.error(f"TypeError for {item}")

    def _expand_spotify_liked_songs(self, token):
        for index, track in enumerate(spotify_get_liked_songs(token)):
            track_id = track["track"]["id"]
            local_id = format_local_id(track_id)
            with pending_lock:
                pending[local_id] = {
                    "local_id": local_id,
                    "item_service": "spotify",
                    "item_type": "track",
                    "item_id": track_id,
                    "parent_category": "playlist",
                    "playlist_name": "Liked Songs",
                    "playlist_by": "me",
                    "playlist_number": str(index + 1),
                }

    def _expand_spotify_your_episodes(self, token):
        for index, track in enumerate(spotify_get_your_episodes(token)):
            episode_id = track["episode"]["id"]
            if not episode_id:
                raise NotImplementedError
            local_id = format_local_id(episode_id)
            with pending_lock:
                pending[local_id] = {
                    "local_id": local_id,
                    "item_service": "spotify",
                    "item_type": "podcast_episode",
                    "item_id": episode_id,
                    "parent_category": "playlist",
                    "playlist_name": "Your Episodes",
                    "playlist_by": "me",
                    "playlist_number": str(index + 1),
                }

    def _expand_youtube_music_channel(self, token, channel_id, service):
        get_track_ids = SERVICE_CHANNEL_TRACK_ID_FUNCTIONS.get(service)
        if get_track_ids is None:
            raise NotImplementedError
        for track_id in get_track_ids(token, channel_id):
            local_id = format_local_id(track_id)
            with pending_lock:
                pending[local_id] = {
                    "local_id": local_id,
                    "item_service": service,
                    "item_type": "track",
                    "item_id": track_id,
                    "parent_category": "album",
                }

    def _expand_podcast(self, service, item_type, item_id, token):
        get_episode_ids = SERVICE_PODCAST_EPISODE_ID_FUNCTIONS.get(service)
        if get_episode_ids is None:
            raise NotImplementedError
        for episode_id in get_episode_ids(token, item_id):
            local_id = format_local_id(episode_id)
            with pending_lock:
                pending[local_id] = {
                    "local_id": local_id,
                    "item_service": service,
                    "item_type": "podcast_episode",
                    "item_id": episode_id,
                    "parent_category": item_type,
                }

    def _expand_collection(self, service, item_type, item_id, token, item_url):
        """Expand an album, playlist, or mix into individual track entries."""
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
            with pending_lock:
                pending[local_id] = {
                    "local_id": local_id,
                    "item_service": service,
                    "item_type": "track",
                    "item_id": track_id,
                    "parent_category": effective_category,
                    "playlist_name": playlist_name,
                    "playlist_by": playlist_by,
                    "playlist_number": str(index + 1),
                }

    def _expand_artist_or_label(self, service, item_type, item_id, token):
        """Expand an artist or label into their albums (which are then re-parsed)."""
        if item_type == "label":
            get_album_ids = SERVICE_LABEL_ALBUM_ID_FUNCTIONS.get(service)
        else:
            get_album_ids = SERVICE_ARTIST_ALBUM_ID_FUNCTIONS.get(service)

        if get_album_ids is None:
            raise NotImplementedError

        for album_id in get_album_ids(token, item_id):
            with parsing_lock:
                parsing[album_id] = {
                    "item_url": "",
                    "item_service": service,
                    "item_type": "album",
                    "item_id": album_id,
                }

    def _expand_show(self, service, item_type, item_id, token):
        get_episode_ids = SERVICE_EPISODE_ID_FUNCTIONS.get(service)
        if get_episode_ids is None:
            raise NotImplementedError
        for episode_id in get_episode_ids(token, item_id):
            local_id = format_local_id(episode_id)
            with pending_lock:
                pending[local_id] = {
                    "local_id": local_id,
                    "item_service": service,
                    "item_type": "episode",
                    "item_id": episode_id,
                    "parent_category": item_type,
                }

    # ------------------------------------------------------------------
    # Error helpers
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
                    f"• The {item_type} URL is correct\n"
                    f"• The {item_type} is public or you have access\n"
                    f"• You're logged into the correct {service_name} account"
                )
            else:
                msg = (
                    f"Album not found: The {service_name} album was not found "
                    f"or is unavailable.\n\nAlbum ID: {item_id}"
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
            f"{item_type.title()} fetch failed for {service}: {traceback.format_exc()}"
        )

    def _handle_parsing_error(self, exc, item_type, item_id, item_url, service):
        error_str = str(exc)
        service_name = service.replace("_", " ").title()

        if "404" in error_str or "not found" in error_str.lower():
            if item_type == "playlist":
                msg = (
                    f"Failed to load playlist: The playlist was not found or is private.\n\n"
                    f"Playlist ID: {item_id}\n\nPlease verify:\n"
                    f"• The playlist URL is correct\n"
                    f"• The playlist is public or you have access\n"
                    f"• You're logged into the correct {service_name} account"
                )
            elif item_type == "album":
                msg = f"Failed to load album: The album was not found or is unavailable.\n\nDetails: {item_url}"
            elif item_type == "artist":
                msg = f"Failed to load artist: The artist was not found.\n\nDetails: {item_url}"
            else:
                msg = f"Failed to load {item_type}: Item was not found.\n\nDetails: {item_url}"
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
        logger.error(
            f"Unknown Exception: {str(exc)}\nTraceback: {traceback.format_exc()}"
        )
