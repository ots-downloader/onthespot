import queue
import os

import json as _json
import requests
from librespot.audio.decoders import AudioQuality, VorbisOnlyAudioQuality
from librespot.metadata import EpisodeId, TrackId
from yt_dlp import YoutubeDL

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
from .api.tidal import tidal_get_mpd_data
from .api.spotify import reinit_spotify_session


from .accounts import get_account_token
from .constants import ItemStatus
from .runtimedata import get_logger, progress_hook, wait_for_download_resume, yt_dlp_progress_hook
from .resources.exceptions import TrackUnavailableError, DownloadCancelled
from .otsconfig import config
from .utils import requeue_item, run_ffmpeg
from .youtube_auth import is_youtube_url, youtube_ydl_options


logger = get_logger("services_middleware")


def _download_http_with_resume(item, url, temp_path, headers=None):
    """Stream a URL into *temp_path*, continuing a partial file when possible."""
    headers = dict(headers or {})
    existing = os.path.getsize(temp_path) if os.path.isfile(temp_path) else 0
    if existing:
        headers["Range"] = f"bytes={existing}-"

    response = requests.get(url, headers=headers, stream=True, timeout=60)
    response.raise_for_status()
    can_append = existing > 0 and response.status_code == 206
    if not can_append:
        existing = 0
    total_size = int(response.headers.get("Content-Length", 0) or 0) + existing
    downloaded = existing

    with open(temp_path, "ab" if can_append else "wb") as audio_file:
        for chunk in response.iter_content(chunk_size=config.get("download_chunk_size", 65536)):
            if not chunk:
                continue
            if item.get("item_status") == ItemStatus.CANCELLED:
                raise DownloadCancelled("Download cancelled by user.")
            wait_for_download_resume(item)
            downloaded += len(chunk)
            audio_file.write(chunk)
            progress_hook(
                item,
                int((downloaded / total_size) * 100) if total_size else item.get("progress", 0),
                ItemStatus.DOWNLOADING,
                downloaded_bytes=downloaded,
                total_bytes=total_size or None,
            )
    return downloaded


def download_spotify(item, item_id, item_type, token, temp_path):
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
        reinit_spotify_session(token)
        raise RuntimeError(f"Spotify session connection lost: {exc}") from exc
    except queue.Empty as exc:
        reinit_spotify_session(token)
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
                progress_hook(
                    item,
                    int((downloaded / total_size) * 100),
                    ItemStatus.DOWNLOADING,
                    downloaded_bytes=downloaded,
                    total_bytes=total_size,
                )
            if not chunk:
                break

    stream.input_stream.stream().close()
    del stream.input_stream

    return default_format, bitrate

def download_deezer(item, item_id, token, temp_path):
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
            "Unable to select Deezer quality %s for track %s , defaulting to 128k MP3. Error: %s",
            song_quality,
            song["SNG_ID"],
            str(exc),
        )
        song_quality = 1
        song_format = "MP3_128"
        bitrate = "128k"
        default_format = ".mp3"
        url_key = genurlkey(
            song["SNG_ID"], song["MD5_ORIGIN"], song["MEDIA_VERSION"], song_quality
        )
        url = f"https://e-cdns-proxy-{song['MD5_ORIGIN'][0]}.dzcdn.net/mobile/1/{url_key.decode()}"

    response = requests.get(url, stream=True, timeout=60)
    if response.status_code != 200:
        logger.info(
            "Deezer download failed %s", response.status_code
        )
        item["item_status"] = ItemStatus.FAILED
        requeue_item(item)
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
            progress_hook(
                item,
                int((downloaded / total_size) * 100),
                ItemStatus.DOWNLOADING,
                downloaded_bytes=downloaded,
                total_bytes=total_size,
            )

    bf_key = calcbfkey(song["SNG_ID"])
    progress_hook(item, 99, ItemStatus.DECRYPTING)
    with open(temp_path, "wb") as out_file:
        decryptfile(data_chunks, bf_key, out_file)

    return default_format, bitrate

def download_via_ytdlp_audio(
    item, item_metadata, service, item_id, token, temp_path, item_type
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
        default_format = ".flac"
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
                _download_http_with_resume(item, direct_url, temp_path, headers)
                mime = manifest_json.get("codecs", "audio/mp4")
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
        ydl_opts.update(youtube_ydl_options())

    ydl_opts.update(
        {
            "quiet": False,
            "no_warnings": True,
            "noprogress": True,
            "extract_audio": True,
            "outtmpl": temp_path,
            "continuedl": True,
            "overwrites": False,
            "retries": 3,
            "fragment_retries": 3,
        }
    )
    ydl_opts["progress_hooks"] = [lambda d: yt_dlp_progress_hook(item, d)]

    if is_youtube_url(item_id):
        ydl_opts.update(youtube_ydl_options())

    with YoutubeDL(ydl_opts) as downloader:
        if service == "soundcloud" and token["oauth_token"]:
            info = downloader.extract_info(item_url)
            bitrate = f"{info.get('abr')}k"
            default_format = f".{info.get('audio_ext')}"
        downloader.download(item_url)

    if os.path.exists(mpd_file_path):
        os.remove(mpd_file_path)

    return default_format, bitrate

def download_http_stream(
    item, item_metadata, service, item_id, token, temp_path
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

    _download_http_with_resume(item, file_url, temp_path)

    return default_format, bitrate

def download_apple_music(item, item_id, token, temp_path):
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
        "continuedl": True,
        "overwrites": False,
        "retries": 3,
        "fragment_retries": 3,
    }
    ydl_opts["progress_hooks"] = [lambda d: yt_dlp_progress_hook(item, d)]
    if is_youtube_url(item_id):
        ydl_opts.update(youtube_ydl_options())

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
    run_ffmpeg(ffmpeg_cmd)
    progress_hook(item, 99, ItemStatus.DECRYPTING)

    if os.path.exists(temp_path):
        os.remove(temp_path)
    os.rename(decrypted_path, temp_path)

    return default_format, bitrate

def download_crunchyroll(item, item_metadata, item_id, token, temp_path):
    """Download encrypted Crunchyroll video/audio streams and subtitles."""
    skip_url = "https://static.crunchyroll.com/skip-events/production/"
    ydl_base_opts = {
        "quiet": False,
        "no_warnings": True,
        "allow_unplayable_formats": True,
        "fixup": "never",
        "allowed_extractors": ["generic"],
        "noprogress": True,
        "continuedl": True,
        "overwrites": False,
        "retries": 3,
        "fragment_retries": 3,
    }
    ydl_base_opts["progress_hooks"] = [
        lambda d: yt_dlp_progress_hook(item, d)
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
            f"(bestvideo[height<={config.get('preferred_video_resolution')}][ext=mp4]+bestaudio[ext=m4a])/"
            f"(bestvideo[height<={config.get('preferred_video_resolution')}]+bestaudio)/"
            f"best"
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
                    f"{skip_url}{version['guid']}.json", timeout=20
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
        run_ffmpeg(ffmpeg_cmd)
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
                sub_data = requests.get(sub["url"], timeout=20).text
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

def download_generic(item, item_id, temp_path):
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
        "continuedl": True,
        "overwrites": False,
        "retries": 3,
        "fragment_retries": 3,
    }

    ydl_opts["progress_hooks"] = [lambda d: yt_dlp_progress_hook(item, d)]
    if is_youtube_url(item_id):
        ydl_opts.update(youtube_ydl_options())

    with YoutubeDL(ydl_opts) as downloader:
        info = downloader.extract_info(item_id, download=False)
        item["file_path"] = downloader.prepare_filename(info)
        downloader.download(item_id)

def download_generic_v2a(item, item_id, temp_path):
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
        "continuedl": True,
        "overwrites": False,
        "retries": 3,
        "fragment_retries": 3,
    }

    ydl_opts["progress_hooks"] = [lambda d: yt_dlp_progress_hook(item, d)]
    if is_youtube_url(item_id):
        ydl_opts.update(youtube_ydl_options())

    with YoutubeDL(ydl_opts) as downloader:
        info = downloader.extract_info(item_id, download=False)
        item["file_path"] = downloader.prepare_filename(info)
        downloader.download(item_id)

    return config.get("v2a_preferred_codec"), config.get("v2a_preferred_bitrate")
