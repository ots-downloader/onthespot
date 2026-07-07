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


from .accounts import get_account_token

from .api.deezer import deezer_parse_url
from .api.generic import generic_get_track_metadata
from .api.soundcloud import soundcloud_parse_url
from .resources.regexes import (
    APPLE_MUSIC_URL_REGEX,
    BANDCAMP_URL_REGEX,
    DEEZER_URL_REGEX,
    DEEZER_SHARE_URL_REGEX,
    QOBUZ_URL_REGEX,
    SOUNDCLOUD_URL_REGEX,
    SPOTIFY_URL_REGEX,
    TIDAL_URL_REGEX,
    YOUTUBE_MUSIC_URL_REGEX,
    CRUNCHYROLL_URL_REGEX
)

from .runtimedata import (
    account_pool,
    get_logger,
    parsing,
    parsing_lock,
)


logger = get_logger("parse_item")



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
# Uses UrlMatcher to parse results, add basic item information and enqueue the item for parsingWorker
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
        return True  # enqueued; caller does not need a boolean

    # Unknown URL — fall back to yt-dlp via the generic service
    is_generic_enabled = any(acc["service"] == "generic" for acc in account_pool)
    if not is_generic_enabled:
        logger.info("Invalid Url: %s", url)
        return False

    try:
        logger.info("Unable to parse url falling back to yt-dlp: %s", url)
        item_metadata = generic_get_track_metadata("", url)
        if item_metadata is True:
            # Playlist handled internally by generic_get_track_metadata
            return True
        if item_metadata is None:
            logger.info("Unable to parse url: %s", url)
            return False
        with parsing_lock:
            parsing[url] = {
                "item_url": url,
                "item_service": "generic",
                "item_type": "track",
                "item_id": url,
            }
        return None
    except Exception as exc:
        logger.info('Error — possibly invalid URL: %s, "%s"', url, exc)
        return False


def get_search_results(
    search_term: str
):
    """Checks the search term and delegates to the appropriate search function.

    Parameters
    ----------
    search_term: str
        A URL, a local file path containing one URL per line, or a plain
        search query string.
    """
    if not account_pool:
        logger.error("No Accounts configured")
        return False

    if not search_term:
        logger.warning("Returning empty data — search query is empty.")
        return False

    # --- URL input -----------------------------------------------------------
    if search_term.startswith("https://") or search_term.startswith("http://"):
        logger.info("Search term is a URL: %s", search_term)
        result = parse_url(search_term)
        return result

    return False