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
import platform
import requests
import re
import ssl
import subprocess
import threading
import time
import itertools
from hashlib import md5
from urllib.parse import urlparse
from io import BytesIO
from PIL import Image
from mutagen.id3 import ID3, ID3NoHeaderError, WOAS, USLT, TCMP, COMM
import music_tag
from .otsconfig import config
from .runtimedata import get_logger, pending, download_queue

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

counter = itertools.count(start=1)


def _get_host_lock(url):
    host = urlparse(url).netloc
    with _api_host_locks_guard:
        lock = _api_host_locks.get(host)
        if lock is None:
            lock = threading.Lock()
            _api_host_locks[host] = lock
        return lock


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
):
    """Perform a GET request with caching and automatic retry / back-off.

    Responses are cached on disk (keyed by URL MD5) unless *skip_cache* is
    ``True``.  Rate-limited (429) and server-error (5xx) responses are
    retried with exponential back-off up to ``api_retry_max_attempts`` times.

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
    """
    if not skip_cache:
        request_key = md5(f"{url}".encode()).hexdigest()
        req_cache_file = os.path.join(
            config.get("_cache_dir"), "reqcache", request_key + ".json"
        )
        os.makedirs(os.path.dirname(req_cache_file), exist_ok=True)
        if os.path.isfile(req_cache_file):
            logger.info(
                f"[CACHE HIT] Retrieved from cache | URL: {url} | MD5: {request_key} | File: {req_cache_file}"
            )
            try:
                with open(req_cache_file, "r", encoding="utf-8") as cf:
                    if text:
                        return cf.read()
                    json_data = json.load(cf)
                return json_data
            except json.JSONDecodeError:
                logger.error(
                    f"[CACHE ERROR] Invalid JSON data | URL: {url} | MD5: {request_key} | File: {req_cache_file}"
                )
                return None
        logger.info(
            f"[CACHE MISS] Not found in cache, fetching from API | URL: {url} | MD5: {request_key} | File: {req_cache_file}"
        )

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
        # The lock serialises only the request dispatch, so a burst of workers
        # can't hit the rate limit simultaneously. The backoff sleep below happens
        # OUTSIDE the lock so a single backing-off call doesn't stall every other
        # worker (and a long Retry-After can't freeze the whole app).
        try:
            with _get_host_lock(url):
                response = session.get(url, headers=headers, params=params, timeout=30)
        except requests.exceptions.Timeout:
            time.sleep(min((2**attempt) * base_delay, max_delay))
            logger.warning(
                f"Timeout on {url}, retrying (attempt {attempt + 1}/{max_retries})"
            )
            continue
        except requests.exceptions.RequestException as e:
            logger.error(f"Request exception on {url}: {str(e)}")
            return None

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
                if not skip_cache:
                    with open(req_cache_file, "w", encoding="utf-8") as cf:
                        cf.write(response.text)
                return response.text
            # Guard against a 200 with a non-JSON body (e.g. an HTML error/captive
            # portal page) so we return None instead of raising into callers.
            try:
                data = json.loads(response.text)
            except json.JSONDecodeError:
                logger.error(f"Invalid JSON in 200 response from {url}")
                return None
            if not skip_cache:
                with open(req_cache_file, "w", encoding="utf-8") as cf:
                    cf.write(response.text)
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
    local_id = next(counter)
    logger.debug(f"NEW ID: {local_id}")
    return str(local_id)


# ---------------------------------------------------------------------------
# Application helpers
# ---------------------------------------------------------------------------


def _version_to_int(version):
    match = re.match(r"[\d.]+", str(version).lower().lstrip("v"))
    digits = match.group(0).replace(".", "") if match else ""
    return int(digits) if digits else 0


def is_latest_release():
    """Return ``True`` if the running version is the latest GitHub release."""
    url = "https://api.github.com/repos/justin025/onthespot/releases/latest"
    response = requests.get(url)
    if response.status_code == 200:
        current_version = _version_to_int(config.get("version"))
        latest_version = _version_to_int(response.json()["name"])
        if latest_version > current_version:
            logger.info(f"Update Available: {latest_version} > {current_version}")
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
    """Translate *string* to the configured app language via Google Translate.

    Returns the original string unchanged if the request fails.
    """
    try:
        response = requests.get(
            f"https://translate.googleapis.com/translate_a/single?dj=1&dt=t&dt=sp&dt=ld&dt=bd&client=dict-chrome-ex&sl=auto&tl={config.get('language')}&q={string}"
        )
        return response.json()["sentences"][0]["trans"]
    except (requests.exceptions.RequestException, KeyError, IndexError):
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


def convert_audio_format(filename, bitrate, default_format):
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

        if filetype == default_format and config.get("use_custom_file_bitrate"):
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
                language = file.get("language")
                format_map += [
                    f"-metadata:s:{current_type[:1]}:{i}",
                    f"title={file.get('language')}",
                ]
                format_map += [
                    f"-metadata:s:{current_type[:1]}:{i}",
                    f"language={file.get('language')[:2]}",
                ]

        i += 1

    format_map += [f"-metadata", f"title={item_metadata.get('title')}"]
    # format_map += [f'-metadata', f'genre={item_metadata.get("genre")}']
    format_map += [f"-metadata", f"copyright={item_metadata.get('copyright')}"]
    format_map += [f"-metadata", f"description={item_metadata.get('description')}"]
    # format_map += [f'-metadata', f'year={item_metadata.get("release_year")}']
    # TV Show Specific Tags
    if item["item_type"] == "episode":
        format_map += [f"-metadata", f"show={item_metadata.get('show_name')}"]
        format_map += [
            f"-metadata",
            f"episode_id={item_metadata.get('episode_number')}",
        ]
        format_map += [f"-metadata", f"tvsn={item_metadata.get('season_number')}"]

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
        img = Image.open(BytesIO(requests.get(metadata["image_url"]).content))
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
    dl_root = config.get("audio_download_path")
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
