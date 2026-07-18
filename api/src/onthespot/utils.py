"""
utils.py
~~~~~~~~

Miscellaneous utility functions used across the application.

Sections
--------
* HTTP / caching       — :func:`make_call`
* Queue helpers        — :func:`format_local_id`
* String / path        — :func:`sanitize_data`, :func:`format_item_path`, …
* Audio processing     — :func:`convert_audio_format`, :func:`embed_metadata`, …
* Thumbnail handling   — :func:`set_music_thumbnail`
* M3U playlist         — :func:`add_to_m3u_file`
* Miscellaneous        — :func:`is_latest_release`, :func:`open_item`, …
"""

import json
import os
import random
import platform
import requests
import re
import ssl
import subprocess
import threading
import time
import itertools
import string
from hashlib import md5
from urllib.parse import urlparse
from io import BytesIO
from PIL import Image
from mutagen.id3 import ID3, WOAS, USLT, TCMP, COMM
import music_tag
from .otsconfig import config
from .runtimedata import (
    get_logger,
    download_queue,
    download_queue_lock,
    progress_hook,
    notification_hook,
    pending,
    get_rate_limit_delay,
    record_rate_limit,
)
from .constants import HTTP_TIMEOUT, ItemStatus

logger = get_logger("utils")

# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

# Serialises outbound API requests across all worker threads so that a single
# global rate-limit applies rather than each thread racing independently.
# _api_request_lock = threading.Lock()

# Per-host request locks: serialise dispatch to each API host independently so a
# burst of concurrent calls to one service can't trip its rate limit, while
# unrelated services (Apple Music, Bandcamp, Deezer, ...) keep running concurrently.
_api_host_locks = {}
_api_host_locks_guard = threading.Lock()

local_id_counter = itertools.count(start=1)


def _get_host_lock(url):
    host = urlparse(url).netloc
    with _api_host_locks_guard:
        lock = _api_host_locks.get(host)
        if lock is None:
            lock = threading.Lock()
            _api_host_locks[host] = lock
        return lock


def _cache_ttl_seconds(url, cache_ttl_seconds):
    """Return a safe disk-cache TTL for a public HTTP response.

    Spotify account, library, and playlist responses are deliberately excluded:
    they are user-specific and should never be persisted in the shared request
    cache. Public catalogue metadata and search results are safe to reuse.
    """
    if not bool(config.get("cache_api_calls", True)):
        return 0

    if cache_ttl_seconds is not None:
        return max(0, int(cache_ttl_seconds))

    parsed = urlparse(url)
    if parsed.netloc.casefold() == "api.spotify.com":
        path = parsed.path.rstrip("/")
        if path == "/v1/search":
            return max(0, int(config.get("spotify_search_cache_ttl_seconds", 900)))
        public_catalogue_paths = (
            "/v1/albums",
            "/v1/artists",
            "/v1/audio-features",
            "/v1/audiobooks",
            "/v1/episodes",
            "/v1/markets",
            "/v1/shows",
            "/v1/tracks",
        )
        if path.startswith(public_catalogue_paths):
            return max(0, int(config.get("spotify_metadata_cache_ttl_seconds", 604800)))
        return 0

    return max(0, int(config.get("api_response_cache_ttl_seconds", 86400)))


def _cache_path(url, params, text):
    """Return a deterministic cache path including the complete query string."""
    prepared_url = requests.Request("GET", url, params=params).prepare().url
    cache_key = md5(
        f"v2|{int(bool(text))}|{prepared_url}".encode(), usedforsecurity=False
    ).hexdigest()
    cache_dir = os.path.join(config.get("_cache_dir"), "reqcache")
    os.makedirs(cache_dir, exist_ok=True)
    return cache_key, os.path.join(cache_dir, f"v2-{cache_key}.json")


def _read_cached_response(cache_file, text):
    """Read a v2 cache envelope, returning ``(entry, value)`` or ``(None, None)``."""
    if not cache_file or not os.path.isfile(cache_file):
        return None, None
    try:
        with open(cache_file, "r", encoding="utf-8") as cache_handle:
            entry = json.load(cache_handle)
        if not isinstance(entry, dict) or entry.get("version") != 2:
            return None, None
        payload = entry.get("payload")
        if not isinstance(payload, str):
            return None, None
        if text:
            return entry, payload
        return entry, json.loads(payload)
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        return None, None


def _write_cached_response(cache_file, payload, ttl_seconds, etag=None):
    if not cache_file or ttl_seconds <= 0:
        return
    now = time.time()
    entry = {
        "version": 2,
        "stored_at": now,
        "expires_at": now + ttl_seconds,
        "etag": etag or "",
        "payload": payload,
    }
    try:
        with open(cache_file, "w", encoding="utf-8") as cache_handle:
            json.dump(entry, cache_handle, ensure_ascii=False)
    except OSError as error:
        logger.warning("Could not cache API response at %s: %s", cache_file, error)


def _response_cache_ttl(response, default_ttl):
    """Respect no-store and keep positive provider TTLs from extending ours.

    Spotify marks public catalogue responses ``public, max-age=0`` to force
    browser revalidation.  OnTheSpot's local cache deliberately keeps those
    immutable/public results for its configured short TTL so repeated searches
    do not spend the user's API quota.  ``no-store`` remains authoritative.
    """
    cache_control = str(response.headers.get("Cache-Control") or "").casefold()
    if "no-store" in cache_control:
        return 0
    max_age_match = re.search(r"max-age\s*=\s*(\d+)", cache_control)
    if max_age_match:
        provider_ttl = int(max_age_match.group(1))
        if provider_ttl > 0:
            return min(default_ttl, provider_ttl)
    return default_ttl


class SSLAdapter(requests.adapters.HTTPAdapter):
    """HTTPAdapter that injects a custom :class:`ssl.SSLContext`."""

    def __init__(self, ssl_context, *args, **kwargs):
        self.ssl_context = ssl_context
        super().__init__(*args, **kwargs)

    def init_poolmanager(self, *args, **kwargs):
        context = self.ssl_context
        return super().init_poolmanager(*args, ssl_context=context, **kwargs)


def make_call(
    url,
    params=None,
    headers=None,
    session=None,
    skip_cache=False,
    text=False,
    use_ssl=False,
    cache_ttl_seconds=None,
):
    """Perform a GET request with caching and automatic retry / back-off.

    Public responses are cached on disk using a URL-and-query-aware key unless
    *skip_cache* is ``True``. Spotify private/account data is never persisted.
    Rate-limited (429) and server-error (5xx) responses are retried with
    exponential back-off up to ``api_retry_max_attempts`` times.

    Parameters
    ----------
    url:
        Target URL.
    params:
        Optional query-string parameters dict.
    headers:
        Optional HTTP headers dict.
    session:
        Optional :class:`requests.Session` to reuse.  A new one is created
        when ``None``.
    skip_cache:
        When ``True`` the response is never read from or written to the disk
        cache.
    text:
        When ``True`` return the raw response text instead of parsed JSON.
    use_ssl:
        When ``True`` attach an :class:`SSLAdapter` with certificate
        verification enabled.
    cache_ttl_seconds:
        Optional response cache lifetime. ``None`` applies the safe service
        defaults; ``0`` disables caching for this request.
    """
    cache_ttl = 0 if skip_cache else _cache_ttl_seconds(url, cache_ttl_seconds)
    parsed_url = urlparse(url)
    # A third-party response authenticated with a cookie or bearer token can
    # belong to one account only. Keep those out of the disk cache unless a
    # caller deliberately opts in. Spotify has its own public-path allowlist
    # above, so catalogue results can still be reused safely.
    if (
        parsed_url.netloc.casefold() != "api.spotify.com"
        and cache_ttl_seconds is None
        and any(key.casefold() in {"authorization", "cookie"} for key in (headers or {}))
    ):
        cache_ttl = 0
    request_key = None
    req_cache_file = None
    cached_entry = None
    cached_value = None
    if cache_ttl > 0:
        request_key, req_cache_file = _cache_path(url, params, text)
        cached_entry, cached_value = _read_cached_response(req_cache_file, text)
        if cached_entry and float(cached_entry.get("expires_at", 0) or 0) > time.time():
            logger.debug("[CACHE HIT] %s | %s", url, request_key)
            return cached_value
        logger.debug("[CACHE MISS] %s | %s", url, request_key)

    request_headers = dict(headers or {})
    if cached_entry and cached_entry.get("etag"):
        request_headers.setdefault("If-None-Match", cached_entry["etag"])

    if session is None:
        session = requests.Session()

    if use_ssl:
        ctx = ssl.create_default_context()
        ctx.verify_mode = ssl.CERT_REQUIRED
        session.mount("https://", SSLAdapter(ssl_context=ctx))

    # Retry logic with exponential backoff for transient failures (rate limits,
    # server errors, timeouts). Permanent client errors (e.g. 401/403/404) are
    # returned as None without retrying.
    max_retries = config.get("api_retry_max_attempts", 3)
    base_delay = config.get("api_retry_base_delay", 2)
    max_delay = config.get("api_retry_max_delay", 60)

    for attempt in range(max_retries):
        # The lock serialises request dispatch per host. It also keeps a shared
        # cooldown together with the next request so workers cannot stampede a
        # provider the moment a Retry-After window ends.
        try:
            with _get_host_lock(url):
                # Recheck after waiting for this host lock. A concurrent caller
                # may already have fetched the exact same response.
                if cache_ttl > 0:
                    refreshed_entry, refreshed_value = _read_cached_response(req_cache_file, text)
                    if refreshed_entry and float(refreshed_entry.get("expires_at", 0) or 0) > time.time():
                        return refreshed_value

                cooldown = get_rate_limit_delay(urlparse(url).netloc)
                if cooldown > 0:
                    logger.info("Waiting %.1fs for shared API cooldown on %s", cooldown, urlparse(url).netloc)
                    time.sleep(cooldown)
                response = session.get(
                    url,
                    headers=request_headers,
                    params=params,
                    timeout=HTTP_TIMEOUT,
                )
        except requests.exceptions.Timeout:
            time.sleep(min((2**attempt) * base_delay, max_delay))
            logger.warning(
                f"Timeout on {url}, retrying (attempt {attempt + 1}/{max_retries})"
            )
            continue
        except requests.exceptions.RequestException as e:
            logger.error(f"Request exception on {url}: {str(e)}")
            return None

        if response.status_code == 304 and cached_entry:
            response_ttl = _response_cache_ttl(response, cache_ttl)
            _write_cached_response(
                req_cache_file,
                cached_entry["payload"],
                response_ttl,
                response.headers.get("ETag") or cached_entry.get("etag"),
            )
            return cached_value

        # Rate limited - honour Retry-After if present (capped at max_delay), else back off.
        if response.status_code == 429:
            retry_after = response.headers.get("Retry-After")
            if retry_after and retry_after.isdigit():
                delay = min(int(retry_after) + 1, max_delay)  # 1s buffer, capped
                logger.warning(
                    f"Rate limited (429) on {url}. Retry-After honoured, waiting {delay}s (attempt {attempt + 1}/{max_retries})"
                )
            else:
                delay = min((2**attempt) * base_delay, max_delay)
                logger.warning(
                    f"Rate limited (429) on {url}. No Retry-After header, backing off {delay}s (attempt {attempt + 1}/{max_retries})"
                )
            record_rate_limit(
                urlparse(url).netloc,
                int(retry_after) if retry_after and retry_after.isdigit() else delay,
                delay,
            )
            time.sleep(delay)
            continue

        # Transient errors (request timeout + server errors) - retry with backoff.
        elif response.status_code in (408, 500, 502, 503, 504):
            delay = min((2**attempt) * base_delay, max_delay)
            logger.warning(
                f"Transient error ({response.status_code}) on {url}. Retrying in {delay}s (attempt {attempt + 1}/{max_retries})"
            )
            time.sleep(delay)
            continue

        # Success - cache and return.
        elif response.status_code == 200:
            if text:
                _write_cached_response(
                    req_cache_file,
                    response.text,
                    _response_cache_ttl(response, cache_ttl),
                    response.headers.get("ETag"),
                )
                return response.text
            # Guard against a 200 with a non-JSON body (e.g. an HTML error/captive
            # portal page) so we return None instead of raising into callers.
            try:
                data = json.loads(response.text)
            except json.JSONDecodeError:
                logger.error(f"Invalid JSON in 200 response from {url}")
                return None
            _write_cached_response(
                req_cache_file,
                response.text,
                _response_cache_ttl(response, cache_ttl),
                response.headers.get("ETag"),
            )
            return data

        # Permanent client errors - don't retry.
        else:
            logger.error(f"Request status error {response.status_code}: {url}")
            return None

    # Retries exhausted - raise so the caller marks the item Failed (and the
    # retry worker can pick it up later) instead of crashing on a None result.
    error_msg = f"Max retries ({max_retries}) exhausted for {url}"
    logger.error(error_msg)
    raise requests.exceptions.RequestException(error_msg)


def format_local_id(item_id):
    """Return a unique local ID for *item_id* that does not clash with any
    existing entry in the download queue or pending dict."""
    local_id = next(local_id_counter)
    logger.debug("NEW ID: %s for item %s", local_id, item_id)
    return str(local_id)


# ---------------------------------------------------------------------------
# Application helpers
# ---------------------------------------------------------------------------
def requeue_item(item: dict) -> None:
    """Move *item* to the back of the queue and mark it available for RetryWorker to re-add to the pending queue."""
    with download_queue_lock:
        try:
            local_id = item["local_id"]
            del download_queue[local_id]
            download_queue[local_id] = item
            download_queue[local_id]["available"] = True
            download_queue[local_id]["_active_download"] = False
            raw_progress = item.get("progress", item.get("item_progress", 0))
            try:
                current_progress = int(float(raw_progress or 0))
            except (TypeError, ValueError):
                current_progress = 0
            progress_hook(
                download_queue[local_id],
                current_progress,
                item["item_status"],
            )
        except KeyError:
            # Item was cleared from the queue while we were processing it.
            pass


def retry_single_item(item: dict) -> None:
    """Move *item* back to the pending queue for download and removes from downloadqueue
    FREE THE DownloadQueue LOCK BEFORE CALLING"""
    with download_queue_lock:
        try:
            item["available"] = True
            item.pop("_manual_cancelled", None)
            item["item_status"] = ItemStatus.WAITING
            item["error"] = ""
            item["_stats_recorded"] = False
            item["retry_count"] = int(item.get("retry_count", 0) or 0) + 1
            if item.get("queue_preloaded"):
                download_queue[item["local_id"]] = item
            else:
                del download_queue[item["local_id"]]
            pending.put_nowait(item)
        except KeyError as e:
            logger.error("Error retrying item %s, error: %s", item, str(e))


def _version_to_int(version):
    try:
        match = re.findall(r"\d+\.\d+\.\d+", version)
        digits = match[0].replace(".", "") if match else 0
        return int(digits) if digits else 0
    except Exception:
        logger.error("Error during version extraction %s", version)
        return 0


def is_latest_release():
    """Return ``True`` if the running version is the latest GitHub release.

    This compatibility wrapper is retained for callers from the desktop
    application.  The structured updater lives in :mod:`onthespot.updater`.
    """
    from .updater import check_for_updates

    status = check_for_updates(force=True)
    if status.get("update_available"):
        latest = status.get("latest_version")
        notification_hook(
            "Update available",
            f"OnTheSpot {latest} is ready to download.",
            status.get("release_url", ""),
        )
        logger.info("Update Available: %s", latest)
        return False
    return True


def open_item(item):
    """Open *item* (a file path or URL) with the OS default application."""
    if platform.system() == "Windows":
        os.startfile(item)
    elif platform.system() == "Darwin":  # For MacOS
        subprocess.Popen(["open", item])
    else:  # For Linux and other Unix-like systems
        subprocess.Popen(["xdg-open", item])


def jittered_delay() -> float:
    """Return the configured download delay with optional random variance."""
    variance = int(config.get("download_delay_variance"))
    return max(
        0, int(config.get("download_delay")) + random.randint(-variance, variance)
    )


# ---------------------------------------------------------------------------
# String / path helpers
# ---------------------------------------------------------------------------


def sanitize_data(value):
    """Replace characters that are illegal in file/directory names.

    On Windows, replaces ``\\ / : * ? " < > |`` and strips trailing dots/spaces.
    On other platforms only ``/`` is replaced.
    Returns an empty string when *value* is ``None``.
    """
    if value is None:
        return ""
    char = config.get("illegal_character_replacement")
    if os.name == "nt":
        illegal_chars = ["\\", "/", ":", "*", "?", '"', "<", ">", "|"]
        for illegal_char in illegal_chars:
            value = value.replace(illegal_char, char)
        while value.endswith(".") or value.endswith(" "):
            value = value[:-1]
    else:
        value = value.replace("/", char)
    return value


def translate(string):
    """Return metadata unchanged.

    The web interface uses bundled language packs.  Metadata is deliberately
    left untouched: translating song and album names would be lossy and would
    require sending a user's library to a third-party translation service.
    """
    return string


def conv_list_format(items):
    """Join *items* with the configured metadata separator string."""
    try:
        if len(items) == 0:
            return ""
        return (config.get("metadata_separator")).join(items)
    except TypeError:
        logger.error(
            f"Error converting items list for items: {items}, separator: {config.get('metadata_separator')}"
        )
        return ""


def get_primary_composer(composer_full):
    if not composer_full:
        return ""
    return re.split(r" [,&;] | & |,|;", composer_full)[0].strip()


def format_item_path(item, item_metadata):
    """Build the relative file path for *item* using the configured formatter.

    Uses the playlist path formatter when *item* belongs to a playlist and the
    option is enabled; otherwise selects the track, podcast, movie, or show
    formatter based on ``item_type``.
    """
    if config.get("translate_file_path"):
        name = translate(item_metadata.get("title"))
        album = translate(item_metadata.get("album_name"))
    else:
        name = item_metadata.get("title")
        album = item_metadata.get("album_name")

    if item["parent_category"] == "playlist" and config.get("use_playlist_path"):
        path = config.get("playlist_path_formatter")
    elif item["item_type"] == "track":
        path = config.get("track_path_formatter")
    elif item["item_type"] == "podcast_episode":
        path = config.get("podcast_path_formatter")
    elif item["item_type"] == "movie":
        path = config.get("movie_path_formatter")
    elif item["item_type"] == "episode":
        path = config.get("show_path_formatter")

    # A stray closing brace in a user-edited formatter otherwise aborts every
    # item in a playlist before the download starts. Repair the common typo
    # and let the formatter continue; the saved setting is corrected by the
    # UI/API separately.
    try:
        list(string.Formatter().parse(path))
    except ValueError as exc:
        repaired_path = path.replace("}}", "}")
        if repaired_path == path:
            raise
        logger.warning("Repairing malformed path formatter %r: %s", path, exc)
        path = repaired_path

    # Split composer
    composer_full = item_metadata.get("composer", "")
    primary_composer = get_primary_composer(composer_full)

    try:
        safe_artist = sanitize_data(item_metadata.get("artists"))
        safe_composer = sanitize_data(primary_composer)
    except KeyError as e:
        logger.error(f"No {e} found in metadata, leaving blank")
        safe_artist = ""
        safe_composer = ""

    item_path = path.format(
        # Universal
        service=sanitize_data(item.get("item_service")).title(),
        service_id=str(item_metadata.get("item_id")),
        name=sanitize_data(name),
        year=sanitize_data(item_metadata.get("release_year")),
        explicit=sanitize_data(
            str(config.get("explicit_label")) if item_metadata.get("explicit") else ""
        ),
        # Audio
        artist=safe_artist,
        composer=safe_composer,
        album=sanitize_data(album),
        album_artist=sanitize_data(item_metadata.get("album_artists")),
        album_type=item_metadata.get("album_type", "single").title(),
        disc_number=item_metadata.get("disc_number", 1)
        if not config.get("use_double_digit_path_numbers")
        else str(item_metadata.get("disc_number", 1)).zfill(2),
        track_number=item_metadata.get("track_number", 1)
        if not config.get("use_double_digit_path_numbers")
        else str(item_metadata.get("track_number", 1)).zfill(2),
        genre=sanitize_data(item_metadata.get("genre")),
        label=sanitize_data(item_metadata.get("label")),
        trackcount=item_metadata.get("total_tracks", 1)
        if not config.get("use_double_digit_path_numbers")
        else str(item_metadata.get("total_tracks", 1)).zfill(2),
        disccount=item_metadata.get("total_discs", 1)
        if not config.get("use_double_digit_path_numbers")
        else str(item_metadata.get("total_discs", 1)).zfill(2),
        isrc=str(item_metadata.get("isrc")),
        playlist_name=sanitize_data(item.get("playlist_name")),
        playlist_owner=sanitize_data(item.get("playlist_by")),
        playlist_number=sanitize_data(item.get("playlist_number")),
        # Show
        show_name=sanitize_data(item_metadata.get("show_name")),
        season_number=item_metadata.get("season_number", 1)
        if not config.get("use_double_digit_path_numbers")
        else str(item_metadata.get("season_number", 1)).zfill(2),
        episode_number=item_metadata.get("episode_number", 1)
        if not config.get("use_double_digit_path_numbers")
        else str(item_metadata.get("episode_number", 1)).zfill(2),
    )
    # Clean up any duplicate consecutive slashes from empty fields
    item_path = re.sub(r"/+", "/", item_path)

    return item_path


# ---------------------------------------------------------------------------
# Audio / video processing
# ---------------------------------------------------------------------------
def run_ffmpeg(command: list) -> None:
    """Run an ffmpeg command, suppressing the console window on Windows."""
    if os.name == "nt":
        subprocess.check_call(
            command, shell=False, creationflags=subprocess.CREATE_NO_WINDOW
        )
    else:
        subprocess.check_call(command, shell=False)


def convert_audio_format(filename, bitrate, default_format, force_bitrate=False):
    """Re-encode or copy *filename* to the target format via ffmpeg.

    If the file is already in *default_format* and a custom bitrate is not
    requested, the audio stream is copied without re-encoding.
    """
    if os.path.isfile(os.path.abspath(filename)):
        target_path = os.path.abspath(filename)
        file_stem, filetype = os.path.splitext(os.path.basename(target_path))

        temp_name = os.path.join(
            os.path.dirname(target_path), "~" + file_stem + filetype
        )

        if os.path.isfile(temp_name):
            os.remove(temp_name)

        os.rename(filename, temp_name)
        # Prepare default parameters
        # Existing command initialization
        command = [config.get("_ffmpeg_bin_path"), "-i", temp_name]

        # Set log level based on environment variable
        if int(os.environ.get("SHOW_FFMPEG_OUTPUT", 0)) == 0:
            command += ["-loglevel", "error", "-hide_banner", "-nostats"]

        # Check if media format is service default

        if filetype == default_format and (config.get("use_custom_file_bitrate") or force_bitrate):
            command += ["-b:a", bitrate]
        elif filetype == default_format:
            command += ["-c:a", "copy"]
        else:
            command += [
                #'-f', filetype.split('.')[1],
                "-ac",
                "2",
                "-ar",
                f"{config.get('file_hertz') if filetype != '.opus' else 48000}",
                "-b:a",
                bitrate,
            ]

        # Add user defined parameters
        for param in config.get("ffmpeg_args"):
            command.append(param)

        # Add output parameter at last
        command += [filename]
        logger.debug(f"Converting media with ffmpeg. Built commandline {command}")
        # Run subprocess with CREATE_NO_WINDOW flag on Windows
        if os.name == "nt":
            subprocess.check_call(
                command,
                shell=False,
                stdin=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
        else:
            subprocess.check_call(command, shell=False, stdin=subprocess.DEVNULL)
        os.remove(temp_name)


def convert_video_format(item, output_path, output_format, video_files, item_metadata):
    """Mux *video_files* into a single container file via ffmpeg.

    Subtitle and chapter streams are interleaved when present.  The output is
    written to ``output_path + '.' + output_format``.
    """
    target_path = os.path.abspath(output_path)
    file_stem, filetype = os.path.splitext(os.path.basename(target_path))

    temp_file_path = (
        os.path.join(os.path.dirname(target_path), "~" + file_stem + filetype)
        + "."
        + output_format
    )

    # Prepare default parameters
    # Existing command initialization
    command = [config.get("_ffmpeg_bin_path")]

    current_type = ""
    format_map = []
    for map_index, file in enumerate(video_files):
        if current_type != file["type"]:
            i = 0
            current_type = file["type"]
        command += ["-i", file["path"]]

        if current_type != "chapter":
            format_map += ["-map", f"{map_index}:{current_type[:1]}"]
            if file.get("language"):
                format_map += [
                    f"-metadata:s:{current_type[:1]}:{i}",
                    f"title={file.get('language')}",
                ]
                format_map += [
                    f"-metadata:s:{current_type[:1]}:{i}",
                    f"language={file.get('language')[:2]}",
                ]

        i += 1

    format_map += ["-metadata", f"title={item_metadata.get('title')}"]
    # format_map += [f'-metadata', f'genre={item_metadata.get("genre")}']
    format_map += ["-metadata", f"copyright={item_metadata.get('copyright')}"]
    format_map += ["-metadata", f"description={item_metadata.get('description')}"]
    # format_map += [f'-metadata', f'year={item_metadata.get("release_year")}']
    # TV Show Specific Tags
    if item["item_type"] == "episode":
        format_map += ["-metadata", f"show={item_metadata.get('show_name')}"]
        format_map += [
            "-metadata",
            f"episode_id={item_metadata.get('episode_number')}",
        ]
        format_map += ["-metadata", f"tvsn={item_metadata.get('season_number')}"]

    command += format_map

    # Set log level based on environment variable
    if int(os.environ.get("SHOW_FFMPEG_OUTPUT", 0)) == 0:
        command += ["-loglevel", "error", "-hide_banner", "-nostats"]

    # Add user defined parameters
    for param in config.get("ffmpeg_args"):
        command.append(param)

    command += ["-c", "copy"]
    if output_format == "mp4":
        command += ["-c:s", "mov_text"]

    # Add output parameter at last
    command += [temp_file_path]
    logger.debug(f"Converting media with ffmpeg. Built commandline {command}")
    # Run subprocess with CREATE_NO_WINDOW flag on Windows
    if os.name == "nt":
        subprocess.check_call(
            command,
            shell=False,
            stdin=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
    else:
        subprocess.check_call(command, shell=False, stdin=subprocess.DEVNULL)

    for file in video_files:
        if os.path.exists(file["path"]):
            os.remove(file["path"])

    os.rename(temp_file_path, output_path + "." + output_format)


def embed_metadata(item, metadata):
    """Write ID3 / Vorbis / MP4 tags into ``item['file_path']`` via ffmpeg.

    Each metadata field is embedded only when the corresponding
    ``embed_*`` option is enabled in the configuration.
    """
    if os.path.isfile(os.path.abspath(item["file_path"])):
        target_path = os.path.abspath(item["file_path"])
        file_stem, filetype = os.path.splitext(os.path.basename(target_path))

        temp_name = os.path.join(
            os.path.dirname(target_path), "~" + file_stem + filetype
        )

        if os.path.isfile(temp_name):
            os.remove(temp_name)

        os.rename(item["file_path"], temp_name)
        # Prepare default parameters
        # Existing command initialization
        command = [config.get("_ffmpeg_bin_path"), "-i", temp_name]

        if int(os.environ.get("SHOW_FFMPEG_OUTPUT", 0)) == 0:
            command += ["-loglevel", "error", "-hide_banner", "-nostats"]

        command += ["-c:a", "copy"]

        # Append metadata
        #
        # https://www.jthink.net/jaudiotagger/tagmapping.html
        # https://wiki.multimedia.cx/index.php?title=FFmpeg_Metadata

        if config.get("embed_branding"):
            branding = "Downloaded by OnTheSpot, https://github.com/justin025/onthespot"
            if filetype == ".mp3":
                # Incorrectly embedded to TXXX:TCMP, patch sent upstream
                command += ["-metadata", "COMM={}".format(branding)]
            else:
                command += ["-metadata", "comment={}".format(branding)]

        if config.get("embed_service_id"):
            command += ["-metadata", f"{item['item_service']}id={item['item_id']}"]

        for key in metadata.keys():
            value = metadata[key]

            if key == "artists" and config.get("embed_artist"):
                command += ["-metadata", "artist={}".format(value)]

            elif key in ["album_name", "album"] and config.get("embed_album"):
                command += ["-metadata", "album={}".format(value)]

            elif key in ["album_artists"] and config.get("embed_albumartist"):
                if filetype in [".flac", ".ogg", ".opus"]:
                    command += ["-metadata", "albumartist={}".format(value)]
                else:
                    command += ["-metadata", "album_artist={}".format(value)]

            elif key in ["title", "track_title", "tracktitle"] and config.get(
                "embed_name"
            ):
                command += ["-metadata", "title={}".format(value)]

            elif key in ["year", "release_year"] and config.get("embed_year"):
                command += ["-metadata", "date={}".format(value)]

            elif key in [
                "discnumber",
                "disc_number",
                "disknumber",
                "disk_number",
            ] and config.get("embed_discnumber"):
                if filetype in ["m4a", "mp4", "mov"]:
                    command += [
                        "-metadata",
                        "disk={}/{}".format(value, metadata["total_discs"]),
                    ]
                elif filetype in [".flac", ".ogg", ".opus"]:
                    command += ["-metadata", "discnumber={}".format(value)]
                    command += [
                        "-metadata",
                        "disctotal={}".format(metadata["total_discs"]),
                    ]
                else:
                    command += [
                        "-metadata",
                        "disc={}/{}".format(value, metadata["total_discs"]),
                    ]

            elif key in ["track_number", "tracknumber"] and config.get(
                "embed_tracknumber"
            ):
                if filetype in [".flac", ".ogg", ".opus"]:
                    command += ["-metadata", "tracknumber={}".format(value)]
                    command += [
                        "-metadata",
                        "tracktotal={}".format(metadata.get("total_tracks")),
                    ]
                else:
                    command += [
                        "-metadata",
                        "track={}/{}".format(value, metadata.get("total_tracks")),
                    ]

            elif key == "genre" and config.get("embed_genre"):
                command += ["-metadata", "genre={}".format(value)]

            elif key == "performers" and config.get("embed_performers"):
                if filetype == ".mp3":
                    command += ["-metadata", "TPE1={}".format(value)]
                else:
                    command += ["-metadata", "performer={}".format(value)]

            elif key == "producers" and config.get("embed_producers"):
                if filetype == ".mp3":
                    command += ["-metadata", "TIPL={}".format(value)]
                else:
                    command += ["-metadata", "producer={}".format(value)]

            elif key == "writers" and config.get("embed_writers"):
                if filetype == ".mp3":
                    command += ["-metadata", "TEXT={}".format(value)]
                else:
                    command += ["-metadata", "author={}".format(value)]

            elif key == "composer" and config.get("embed_composer"):
                if config.get("shorten_composer_tag"):
                    value = get_primary_composer(value)
                if filetype == ".mp3":
                    command += ["-metadata", "TCOM={}".format(value)]
                else:
                    command += ["-metadata", "composer={}".format(value)]

            elif key == "label" and config.get("embed_label"):
                if filetype in [".flac", ".ogg", ".opus"]:
                    command += ["-metadata", "label={}".format(value)]
                else:
                    command += ["-metadata", "publisher={}".format(value)]

            elif key == "copyright" and config.get("embed_copyright"):
                command += ["-metadata", "copyright={}".format(value)]

            elif key == "description" and config.get("embed_description"):
                if filetype == ".mp3":
                    # Incorrectly embedded to TXXX:COMM, patch sent upstream
                    command += ["-metadata", "COMM={}".format(value)]
                else:
                    command += ["-metadata", "comment={}".format(value)]

            elif key == "language" and config.get("embed_language"):
                if filetype == ".mp3":
                    command += ["-metadata", "TLAN={}".format(value)]
                else:
                    command += ["-metadata", "language={}".format(value)]

            elif key == "isrc" and config.get("embed_isrc"):
                if filetype == ".mp3":
                    command += ["-metadata", "TSRC={}".format(value)]
                else:
                    command += ["-metadata", "isrc={}".format(value)]

            elif key == "length" and config.get("embed_length"):
                if filetype == ".mp3":
                    command += ["-metadata", "TLEN={}".format(value)]
                else:
                    command += ["-metadata", "length={}".format(value)]

            elif key == "bpm" and config.get("embed_bpm"):
                if filetype == ".mp3":
                    command += ["-metadata", "TBPM={}".format(value)]
                elif filetype in ["m4a", "mp4", "mov"]:
                    command += ["-metadata", "tmpo={}".format(value)]
                else:
                    command += ["-metadata", "bpm={}".format(value)]

            elif key == "key" and config.get("embed_key"):
                if filetype == ".mp3":
                    command += ["-metadata", "TKEY={}".format(value)]
                else:
                    command += ["-metadata", "initialkey={}".format(value)]

            elif key == "album_type" and config.get("embed_compilation"):
                if filetype == ".mp3":
                    # Incorrectly embedded to TXXX:TCMP, patch sent upstream
                    command += [
                        "-metadata",
                        "TCMP={}".format(int(value == "compilation")),
                    ]
                else:
                    command += [
                        "-metadata",
                        "compilation={}".format(int(value == "compilation")),
                    ]

            elif key == "item_url" and config.get("embed_url"):
                if filetype == ".mp3":
                    # Incorrectly embedded to TXXX:WOAS, patch sent upstream
                    command += ["-metadata", "WOAS={}".format(value)]
                else:
                    command += ["-metadata", "website={}".format(value)]

            elif key == "lyrics" and config.get("embed_lyrics"):
                if filetype == ".mp3":
                    # Incorrectly embedded to TXXX:USLT, patch sent upstream
                    command += ["-metadata", "USLT={}".format(value)]
                else:
                    command += ["-metadata", "lyrics={}".format(value)]

            elif key == "explicit" and config.get("embed_explicit"):
                if filetype == ".mp3":
                    command += ["-metadata", "ITUNESADVISORY={}".format(value)]
                else:
                    command += ["-metadata", "explicit={}".format(value)]

            elif key == "upc" and config.get("embed_upc"):
                command += ["-metadata", "upc={}".format(value)]

            elif key == "time_signature" and config.get("embed_timesignature"):
                command += ["-metadata", "timesignature={}".format(value)]

            elif key == "acousticness" and config.get("embed_acousticness"):
                command += ["-metadata", "acousticness={}".format(value)]

            elif key == "danceability" and config.get("embed_danceability"):
                command += ["-metadata", "danceability={}".format(value)]

            elif key == "instrumentalness" and config.get("embed_instrumentalness"):
                command += ["-metadata", "instrumentalness={}".format(value)]

            elif key == "liveness" and config.get("embed_liveness"):
                command += ["-metadata", "liveness={}".format(value)]

            elif key == "loudness" and config.get("embed_loudness"):
                command += ["-metadata", "loudness={}".format(value)]

            elif key == "speechiness" and config.get("embed_speechiness"):
                command += ["-metadata", "speechiness={}".format(value)]

            elif key == "energy" and config.get("embed_energy"):
                command += ["-metadata", "energy={}".format(value)]

            elif key == "valence" and config.get("embed_valence"):
                command += ["-metadata", "valence={}".format(value)]

        # Add output parameter at last
        command += [item["file_path"]]
        logger.debug(f"Embed metadata with ffmpeg. Built commandline {command}")
        # Run subprocess with CREATE_NO_WINDOW flag on Windows
        if os.name == "nt":
            subprocess.check_call(
                command,
                shell=False,
                stdin=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
        else:
            subprocess.check_call(command, shell=False, stdin=subprocess.DEVNULL)
        os.remove(temp_name)


# ---------------------------------------------------------------------------
# Thumbnail helpers
# ---------------------------------------------------------------------------


def set_music_thumbnail(filename, metadata):
    """Download the album artwork and embed or save it alongside *filename*.

    Supports MP3, FLAC, OGG, and most common audio containers.
    Does nothing when ``metadata['image_url']`` is falsy.
    """
    if not metadata.get("image_url"):
        return

    target_path = os.path.abspath(filename)
    dirname = os.path.dirname(target_path)
    file_stem, filetype = os.path.splitext(os.path.basename(target_path))

    temp_name = os.path.join(dirname, "~" + file_stem + filetype)

    format = config.get("album_cover_format")
    image_path = os.path.join(dirname, f"cover.{format}")

    logger.info("Fetching item thumbnail")
    try:
        response = requests.get(metadata["image_url"], timeout=HTTP_TIMEOUT)
        response.raise_for_status()
        img = Image.open(BytesIO(response.content))
    except Exception as e:
        logger.error(f"Failed to download image: {e}")
        return

    _save_image(img, image_path, format)

    if not config.get("raw_media_download"):
        if config.get("embed_cover") and config.get("windows_10_explorer_thumbnails"):
            # music_tag renders covers visible in Windows Explorer; raw
            # mutagen/ffmpeg do not in this mode.
            _embed_with_music_tag(filename, image_path)

        elif config.get("embed_cover") and filetype not in (".wav", ".ogg"):
            if os.path.isfile(temp_name):
                os.remove(temp_name)

            os.rename(filename, temp_name)

            command = [config.get("_ffmpeg_bin_path"), "-i", temp_name]

            # Set log level based on environment variable
            if int(os.environ.get("SHOW_FFMPEG_OUTPUT", 0)) == 0:
                command += ["-loglevel", "error", "-hide_banner", "-nostats"]

            command += [
                "-i",
                image_path,
                "-map",
                "0:a",
                "-map",
                "1:v",
                "-c",
                "copy",
                "-disposition:v:0",
                "attached_pic",
                "-metadata:s:v",
                "title=Cover",
                "-metadata:s:v",
                "comment=Cover (front), -id3v2_version 1",
            ]

            command += [filename]
            logger.debug(f"Setting thumbnail with ffmpeg. Built commandline {command}")
            if os.name == "nt":
                subprocess.check_call(
                    command,
                    shell=False,
                    stdin=subprocess.DEVNULL,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                )
            else:
                subprocess.check_call(command, shell=False, stdin=subprocess.DEVNULL)

        elif config.get("embed_cover") and filetype == ".ogg":
            _embed_with_music_tag(filename, image_path)

        if os.path.exists(temp_name):
            os.remove(temp_name)

    if not config.get("save_album_cover") and os.path.exists(image_path):
        os.remove(image_path)


def _save_image(img, image_path, format):
    """Convert and save image to file."""
    if img.mode != "RGB":
        img = img.convert("RGB")

    # Handle jpg/jpeg format alias
    save_format = "jpeg" if format == "jpg" else format

    buf = BytesIO()
    img.save(buf, format=save_format)
    buf.seek(0)

    with open(image_path, "wb") as cover:
        cover.write(buf.read())


def _embed_with_music_tag(filename, image_path):
    """Embed cover using music_tag (Windows Explorer compatible)."""
    with open(image_path, "rb") as image_file:
        image_data = image_file.read()

    tags = music_tag.load_file(filename)
    tags["artwork"] = image_data
    tags.save()


# ---------------------------------------------------------------------------
# ID3 fix-up
# ---------------------------------------------------------------------------


def fix_mp3_metadata(filename):
    """Correct malformed ID3 frames written by ffmpeg.

    ffmpeg incorrectly embeds certain tags inside ``TXXX:`` frames.  This
    function promotes them to their proper ID3 equivalents (WOAS, USLT,
    COMM, TCMP) so media players display them correctly.
    """
    id3 = ID3(filename)
    if "TXXX:WOAS" in id3:
        id3["WOAS"] = WOAS(url=id3["TXXX:WOAS"].text[0])
        del id3["TXXX:WOAS"]
    if "TXXX:USLT" in id3:
        id3.add(
            USLT(encoding=3, lang="und", desc="desc", text=id3["TXXX:USLT"].text[0])
        )
        del id3["TXXX:USLT"]
    if "TXXX:COMM" in id3:
        id3["COMM"] = COMM(encoding=3, lang="und", text=id3["TXXX:COMM"].text[0])
        del id3["TXXX:COMM"]
    if "TXXX:comment" in id3:
        del id3["TXXX:comment"]
    if "TXXX:TCMP" in id3:
        id3["TCMP"] = TCMP(encoding=3, text=id3["TXXX:TCMP"].text[0])
        del id3["TXXX:TCMP"]
    id3.save()


# ---------------------------------------------------------------------------
# M3U playlist helpers
# ---------------------------------------------------------------------------


def add_to_m3u_file(item, item_metadata):
    """Append *item* to the M3U playlist file for its parent playlist.

    Creates the M3U file (and any intermediate directories) if it does not
    already exist.  Duplicate entries are silently skipped.
    """
    logger.info(f"Adding {item['file_path']} to m3u")

    path = config.get("m3u_path_formatter")

    m3u_file = path.format(
        playlist_name=sanitize_data(item["playlist_name"]),
        playlist_owner=sanitize_data(item["playlist_by"]),
    )

    m3u_file += "." + config.get("m3u_format")
    dl_root = item.get("profile_download_path") or config.get("audio_download_path")
    m3u_path = os.path.join(dl_root, m3u_file)

    os.makedirs(os.path.dirname(m3u_path), exist_ok=True)

    if not os.path.exists(m3u_path):
        with open(m3u_path, "w", encoding="utf-8") as m3u_file:
            m3u_file.write("#EXTM3U\n")

    EXTINF = (
        config.get("extinf_label")
        .format(
            service=item.get("item_service").title(),
            service_id=str(item.get("item_id")),
            artist=item_metadata.get("artists"),
            composer=item_metadata.get("composer"),
            album=item_metadata.get("album_name"),
            album_artist=item_metadata.get("album_artists"),
            album_type=item_metadata.get("album_type", "single").title(),
            name=item_metadata.get("title"),
            year=item_metadata.get("release_year"),
            disc_number=item_metadata.get("disc_number", 1)
            if not config.get("use_double_digit_path_numbers")
            else str(item_metadata.get("disc_number", 1)).zfill(2),
            track_number=item_metadata.get("track_number", 1)
            if not config.get("use_double_digit_path_numbers")
            else str(item_metadata.get("track_number", 1)).zfill(2),
            genre=item_metadata.get("genre"),
            label=item_metadata.get("label"),
            explicit=str(config.get("explicit_label"))
            if item_metadata.get("explicit")
            else "",
            trackcount=item_metadata.get("total_tracks", 1)
            if not config.get("use_double_digit_path_numbers")
            else str(item_metadata.get("total_tracks", 1)).zfill(2),
            disccount=item_metadata.get("total_discs", 1)
            if not config.get("use_double_digit_path_numbers")
            else str(item_metadata.get("total_discs", 1)).zfill(2),
            isrc=str(item_metadata.get("isrc")),
            playlist_name=item.get("playlist_name"),
            playlist_owner=item.get("playlist_by"),
            playlist_number=item.get("playlist_number"),
        )
        .replace(config.get("metadata_separator"), config.get("extinf_separator"))
    )

    # Check if the item_path is already in the M3U file
    with open(m3u_path, "r", encoding="utf-8") as m3u_file:
        try:
            ext_length = round(int(item_metadata["length"]) / 1000)
        except Exception:
            ext_length = "-1"
        m3u_item_header = f"#EXTINF:{ext_length}, {EXTINF}"
        m3u_contents = m3u_file.readlines()
        if m3u_item_header not in [line.strip() for line in m3u_contents]:
            with open(m3u_path, "a", encoding="utf-8") as m3u_file:
                m3u_file.write(f"{m3u_item_header}\n{item['file_path']}\n")
        else:
            logger.info(f"{item['file_path']} already exists in the M3U file.")


def strip_metadata(item):
    """Remove all existing metadata tags from ``item['file_path']`` via ffmpeg.

    Used before re-embedding updated metadata so stale tags are not left
    behind.
    """
    if os.path.isfile(os.path.abspath(item["file_path"])):
        target_path = os.path.abspath(item["file_path"])
        file_stem, filetype = os.path.splitext(os.path.basename(target_path))

        temp_name = os.path.join(
            os.path.dirname(target_path), "~" + file_stem + filetype
        )

        if os.path.isfile(temp_name):
            os.remove(temp_name)

        os.rename(item["file_path"], temp_name)
        # Prepare default parameters
        # Existing command initialization
        command = [config.get("_ffmpeg_bin_path"), "-i", temp_name]

        if int(os.environ.get("SHOW_FFMPEG_OUTPUT", 0)) == 0:
            command += ["-loglevel", "error", "-hide_banner", "-nostats"]

        command += ["-map", "0:a", "-map_metadata", "-1", "-c:a", "copy"]

        # Add output parameter at last
        command += [item["file_path"]]
        logger.debug(f"Strip metadata with ffmpeg. Built commandline {command}")
        # Run subprocess with CREATE_NO_WINDOW flag on Windows
        if os.name == "nt":
            subprocess.check_call(
                command,
                shell=False,
                stdin=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
        else:
            subprocess.check_call(command, shell=False, stdin=subprocess.DEVNULL)
        os.remove(temp_name)


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------


def format_bytes(size):
    units = ["B", "KiB", "MiB", "GiB", "TiB", "PiB"]
    index = 0
    while size >= 1024 and index < len(units) - 1:
        size /= 1024
        index += 1
    return f"{size:.2f} {units[index]}"
