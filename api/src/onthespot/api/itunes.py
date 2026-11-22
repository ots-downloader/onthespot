"""
api/itunes.py
~~~~~~~~~~~~~

Optional, service-agnostic metadata enrichment using Apple's free iTunes
Search API (no account or API key required).

This is *not* a download service: it takes the metadata dict produced by any
service (Spotify, Deezer, generic/yt-dlp, ...) and returns a copy enriched with
fields Apple has available (genre, year, artwork, track/disc numbers, ...).
Every failure path logs a warning and returns the original metadata so an
optional lookup can never break a download.
"""

import re
import unicodedata
from collections.abc import Mapping
from typing import Any
from urllib.parse import urlparse

import requests

from ..runtimedata import get_logger
from ..utils import make_call

logger = get_logger("api.itunes")

ITUNES_SEARCH_URL = "https://itunes.apple.com/search"
DEFAULT_COUNTRY = "US"
SEARCH_LIMIT = 5
ARTWORK_SIZE = 600

# yt-dlp's generic extractor uses its own name as the artist when the source
# page has no artist metadata; do not send that to iTunes as a search term.
_WEAK_ARTISTS = {
    "bandcamp",
    "dailymotion",
    "generic",
    "instagram",
    "soundcloud",
    "tiktok",
    "vimeo",
    "youtube",
}

_PUNCTUATION_RE = re.compile(r"[^\w\s]+", re.UNICODE)
_BRACKETED_RE = re.compile(r"[\(\[][^\)\]]*[\)\]]")

# Artwork URLs in iTunes responses are served from Apple's CDN.  Only fetch
# from that host so a client-supplied candidate cannot be used for SSRF.
_TRUSTED_ARTWORK_HOSTS = {"mzstatic.com", "itunes.apple.com"}


def _storefront(country: Any, context: str = "lookup") -> str:
    """Return a usable two-letter storefront, warning and falling back if not."""
    storefront = _text(country).upper()
    if len(storefront) == 2 and storefront.isalpha():
        return storefront
    logger.warning("Invalid iTunes country %r for %s; falling back to %s", country, context, DEFAULT_COUNTRY)
    return DEFAULT_COUNTRY


def _run_itunes_search(query: str, country: str, limit: int) -> list[dict]:
    """Call the search endpoint and return usable song results, never raising."""
    params = {"term": query, "entity": "song", "limit": limit, "country": country}
    try:
        response = make_call(ITUNES_SEARCH_URL, params=params)
    except Exception as exc:
        logger.warning("iTunes metadata lookup failed for query %r: %s", query, exc)
        return []

    if not isinstance(response, Mapping):
        logger.warning("iTunes metadata lookup returned no usable response for query %r", query)
        return []
    results = response.get("results")
    if not isinstance(results, list):
        logger.warning("iTunes metadata lookup returned malformed results for query %r", query)
        return []
    return [result for result in results if isinstance(result, Mapping)]


def itunes_search_candidates(
    title: Any = "",
    artist: Any = "",
    album: Any = "",
    *,
    country: str = DEFAULT_COUNTRY,
    limit: int = SEARCH_LIMIT,
    length: Any = None,
) -> list[dict]:
    """Return ranked iTunes song candidates for manual selection.

    Unlike :func:`itunes_get_metadata`, no confidence cutoff is applied: the
    user decides which result is correct.  Network and response errors are
    logged as warnings and produce an empty list.
    """
    title_text = _text(title)
    artist_text = _primary_name(_text(artist))
    if artist_text.casefold() in _WEAK_ARTISTS:
        artist_text = ""
    album_text = _text(album)

    if not title_text:
        logger.warning("iTunes candidate search skipped: no usable track title")
        return []

    storefront = _storefront(country, "candidate search")
    terms = [title_text]
    if artist_text:
        terms.append(artist_text)
    if album_text:
        terms.append(album_text)
    query = " ".join(terms)
    length_ms = _duration_ms(length)

    results = _run_itunes_search(query, storefront, max(1, min(int(limit or SEARCH_LIMIT), 20)))
    candidates = []
    for result in results:
        if result.get("kind") not in (None, "song"):
            continue
        mapped = _map_result(result)
        candidates.append(
            {
                "track_id": _text(result.get("trackId")),
                "title": mapped.get("title", ""),
                "artist": mapped.get("artists", ""),
                "album": mapped.get("album_name", ""),
                # iTunes often omits collectionArtistName for singles. Fall back
                # to the track artist so path formatters using {album_artist}
                # still produce Artist/Album/... instead of a top-level album.
                "album_artist": mapped.get("album_artists") or mapped.get("artists") or "",
                "genre": mapped.get("genre", ""),
                "release_year": mapped.get("release_year", ""),
                "track_number": mapped.get("track_number"),
                "total_tracks": mapped.get("total_tracks"),
                "disc_number": mapped.get("disc_number"),
                "total_discs": mapped.get("total_discs"),
                "image_url": mapped.get("image_url", ""),
                "length": mapped.get("length", ""),
                "score": round(_score_candidate(result, title_text, artist_text, album_text, length_ms), 2),
            }
        )

    candidates.sort(key=lambda entry: entry["score"], reverse=True)
    return candidates


def itunes_result_to_tag_changes(result: Mapping) -> dict:
    """Map an iTunes result (or candidate dict) to format-agnostic tag keys."""
    raw_keys = {"trackName", "artistName", "collectionName", "artworkUrl100"}
    mapped = _map_result(result) if raw_keys.intersection(result) else dict(result)

    changes: dict[str, Any] = {}
    field_map = {
        "title": ("title",),
        "artist": ("artist", "artists"),
        "album": ("album", "album_name"),
        "album_artist": ("album_artist", "album_artists", "artist", "artists"),
        "genre": ("genre",),
        "year": ("release_year", "year"),
        "track_number": ("track_number",),
        "total_tracks": ("total_tracks",),
        "disc_number": ("disc_number",),
        "total_discs": ("total_discs",),
    }
    for target_key, source_keys in field_map.items():
        for source_key in source_keys:
            value = mapped.get(source_key)
            if not _is_missing(value):
                changes[target_key] = value
                break
    return changes


def fetch_itunes_artwork(url: Any, *, timeout: float = 10.0) -> bytes:
    """Download artwork from Apple's CDN, raising only on unusable responses."""
    artwork_url = _text(url)
    if not artwork_url:
        raise ValueError("The selected match has no artwork URL")

    parsed = urlparse(artwork_url)
    host = (parsed.hostname or "").casefold()
    allowed_host = host in _TRUSTED_ARTWORK_HOSTS or host.endswith(".mzstatic.com")
    if parsed.scheme != "https" or not allowed_host:
        raise ValueError("Refusing to fetch artwork from an untrusted host")

    try:
        # Do not follow redirects: the initial URL is the only host that was
        # validated above, and a redirect could otherwise reach an internal host.
        response = requests.get(artwork_url, timeout=timeout, allow_redirects=False)
        response.raise_for_status()
        data = bytes(response.content or b"")
    except Exception as exc:
        logger.warning("Could not download iTunes artwork from %s: %s", artwork_url, exc)
        raise ValueError("Could not download iTunes artwork") from exc

    if not data:
        raise ValueError("iTunes artwork response was empty")
    return data


def _as_mapping(value: Any, label: str) -> dict | None:
    """Return a plain dict for *value*, or ``None`` if it is not track-like."""
    if isinstance(value, Mapping):
        return dict(value)
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        try:
            dumped = model_dump()
        except Exception:
            dumped = None
        if isinstance(dumped, Mapping):
            return dict(dumped)
    logger.warning("iTunes metadata provider ignored unsupported %s input: %s", label, type(value).__name__)
    return None


def _text(value: Any) -> str:
    if value is None or isinstance(value, bool):
        return ""
    return str(value).strip()


def _is_missing(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip() or value.strip().casefold() in {"none", "null", "n/a"}
    if isinstance(value, (list, tuple, set, dict)):
        return len(value) == 0
    if isinstance(value, (int, float)):
        return value == 0
    return False


def _first(data: Mapping, *keys: str) -> str:
    """Return the first usable value among *keys*, accepting common aliases."""
    for key in keys:
        value = data.get(key)
        if _is_missing(value):
            continue
        if isinstance(value, (list, tuple)):
            value = ", ".join(_text(entry) for entry in value if not _is_missing(entry))
        text = _text(value)
        if text:
            return text
    return ""


def _normalize(value: Any) -> str:
    text = unicodedata.normalize("NFKD", _text(value))
    text = "".join(character for character in text if not unicodedata.combining(character))
    return " ".join(_PUNCTUATION_RE.sub(" ", text.casefold()).split())


def _normalized_title(value: Any) -> str:
    # Source services often include edition markers iTunes omits (or vice
    # versa), so compare titles without bracketed suffixes.
    return _normalize(_BRACKETED_RE.sub(" ", _text(value)))


def _primary_name(value: str) -> str:
    """First artist name in a possibly multi-valued artist string."""
    for separator in (";", ",", " & ", " / "):
        if separator in value:
            value = value.split(separator, 1)[0]
            break
    return value.strip()


def _duration_ms(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return int(value) if value > 0 else None
    text = _text(value)
    if text.isdigit():
        return int(text) or None
    if ":" in text:
        parts = text.split(":")
        if 2 <= len(parts) <= 3 and all(part.isdigit() for part in parts):
            seconds = 0
            for part in parts:
                seconds = seconds * 60 + int(part)
            return seconds * 1000 if seconds else None
    return None


def _similar(left: str, right: str) -> bool:
    """Substring match, but only for names long enough to be meaningful."""
    return len(left) >= 4 and len(right) >= 4 and (left in right or right in left)


def _score_candidate(result: Mapping, title: str, artist: str, album: str, length_ms: int | None) -> float:
    candidate_title = _normalized_title(result.get("trackName"))
    wanted_title = _normalized_title(title)
    if not candidate_title or not wanted_title:
        return 0.0

    if candidate_title == wanted_title:
        score = 3.0
    elif _similar(candidate_title, wanted_title):
        score = 1.5
    else:
        return 0.0

    candidate_artist = _normalize(result.get("artistName"))
    wanted_artist = _normalize(artist)
    if candidate_artist and wanted_artist:
        if candidate_artist == wanted_artist:
            score += 2.0
        elif _similar(candidate_artist, wanted_artist):
            score += 1.0

    candidate_album = _normalize(result.get("collectionName"))
    wanted_album = _normalize(album)
    if candidate_album and wanted_album:
        if candidate_album == wanted_album:
            score += 1.0
        elif _similar(candidate_album, wanted_album):
            score += 0.5

    candidate_length = _duration_ms(result.get("trackTimeMillis"))
    if candidate_length and length_ms:
        difference = abs(candidate_length - length_ms)
        if difference <= 3000:
            score += 1.0
        elif difference <= 10000:
            score += 0.5

    return score


def _map_result(result: Mapping) -> dict:
    """Translate one iTunes song result into OnTheSpot metadata keys."""
    mapped: dict[str, Any] = {}

    artwork = _text(result.get("artworkUrl100"))
    if artwork:
        mapped["image_url"] = re.sub(
            r"100x100bb(?=\.[a-zA-Z0-9]+$)",
            f"{ARTWORK_SIZE}x{ARTWORK_SIZE}bb",
            artwork,
        )

    release_year = _text(result.get("releaseDate"))[:4]
    mapped["artists"] = _text(result.get("artistName"))
    mapped["album_artists"] = _text(result.get("collectionArtistName"))
    mapped["album_name"] = _text(result.get("collectionName"))
    mapped["title"] = _text(result.get("trackName"))
    mapped["genre"] = _text(result.get("primaryGenreName"))
    mapped["release_year"] = release_year if release_year.isdigit() else ""
    mapped["track_number"] = result.get("trackNumber")
    mapped["total_tracks"] = result.get("trackCount")
    mapped["disc_number"] = result.get("discNumber")
    mapped["total_discs"] = result.get("discCount")
    mapped["length"] = str(_duration_ms(result.get("trackTimeMillis")) or "")

    return {key: value for key, value in mapped.items() if not _is_missing(value)}


def itunes_get_metadata(track, item=None, *, overwrite: bool = False, country: str = DEFAULT_COUNTRY):
    """Enrich a track from any service with free iTunes catalog metadata.

    Parameters
    ----------
    track:
        Metadata dict from any service, a queue-item dict, or an object with
        ``model_dump()`` (e.g. :class:`~onthespot.basemodels.QueueItem`).
    item:
        Optional queue item used as a fallback for title/artist/album.
    overwrite:
        When false (default) only missing/empty fields are filled in.
    country:
        Two-letter iTunes storefront code.

    Returns a copy of *track* with any available iTunes fields merged in. On
    any failure it logs a warning and returns *track* unchanged.
    """
    track_data = _as_mapping(track, "track")
    if track_data is None:
        return track
    item_data = _as_mapping(item, "item") if item is not None else {}

    identifier = _first(track_data, "item_id") or _first(item_data or {}, "item_id")
    context = f"item_id={identifier}" if identifier else "unidentified track"

    title = _first(track_data, "title", "name", "trackName", "track_title") or _first(
        item_data or {}, "name", "title"
    )
    artist = _primary_name(
        _first(track_data, "artists", "artist", "artistName") or _first(item_data or {}, "artist", "artists")
    )
    if artist.casefold() in _WEAK_ARTISTS:
        artist = ""
    album = _first(track_data, "album_name", "album", "collectionName") or _first(item_data or {}, "album")

    if not title:
        logger.warning("iTunes metadata lookup skipped for %s: no usable track title", context)
        return track

    storefront = _storefront(country, context)

    terms = [title]
    if artist:
        terms.append(artist)
    if album:
        terms.append(album)
    query = " ".join(terms)

    results = _run_itunes_search(query, storefront, SEARCH_LIMIT)
    length_ms = _duration_ms(track_data.get("length"))
    best_result = None
    best_score = 0.0
    for candidate in results:
        if not isinstance(candidate, Mapping) or candidate.get("kind") not in (None, "song"):
            continue
        score = _score_candidate(candidate, title, artist, album, length_ms)
        if score > best_score:
            best_result, best_score = candidate, score

    # An exact title alone (score 3) is enough when there is no artist, album
    # or duration to cross-check; otherwise require a corroborating field.
    threshold = 4.0 if (artist or album or length_ms) else 3.0
    if best_result is None or best_score < threshold:
        logger.warning(
            "No confident iTunes match for %s (%s, best score %.1f); keeping original metadata",
            context,
            query,
            best_score,
        )
        return track

    enriched = dict(track_data)
    for key, value in _map_result(best_result).items():
        if overwrite or _is_missing(enriched.get(key)):
            enriched[key] = value

    logger.info("Enriched %s with iTunes metadata (score %.1f)", context, best_score)
    return enriched
