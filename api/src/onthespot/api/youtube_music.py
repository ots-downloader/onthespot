from hashlib import md5
import json
import os
import requests
from yt_dlp import YoutubeDL
from ..otsconfig import config
from ..runtimedata import get_logger, account_pool

logger = get_logger("api.youtube_music")


def youtube_music_login_user(account):
    logger.info("Logging into Youtube account...")
    try:
        # Ping to verify connectivity
        requests.get("https://youtube.com")
        if account["uuid"] == "public_youtube_music":
            account_pool.append(
                {
                    "uuid": "public_youtube",
                    "username": "yt-dlp",
                    "service": "youtube_music",
                    "status": "active",
                    "account_type": "public",
                    "bitrate": "128k",
                }
            )
            return True
    except Exception as e:
        logger.error(f"Unknown Exception: {str(e)}")
        account_pool.append(
            {
                "uuid": account["uuid"],
                "username": "yt-dlp",
                "service": "youtube_music",
                "status": "error",
                "account_type": "N/A",
                "bitrate": "N/A",
            }
        )
        return False


def youtube_music_add_account():
    cfg_copy = config.get("accounts").copy()
    new_user = {
        "uuid": "public_youtube_music",
        "service": "youtube_music",
        "active": True,
    }
    cfg_copy.append(new_user)
    config.set("accounts", cfg_copy)
    config.save()


def youtube_music_get_search_results(_, search_term, content_types):
    ydl_opts = {
        "quiet": True,
        "extract_flat": True,
    }

    search_results = []
    if "track" in content_types:
        with YoutubeDL(ydl_opts) as ytdl:
            result = ytdl.extract_info(
                f"ytsearch{config.get('max_search_results')}:{search_term}",
                download=False,
            )
            for result in result["entries"]:
                search_results.append(
                    {
                        "item_id": result["id"],
                        "item_name": result["title"],
                        "item_by": result["channel"],
                        "item_type": "track",
                        "item_service": "youtube_music",
                        "item_url": f"https://music.youtube.com/watch?v={result['id']}",
                        "item_thumbnail_url": f"https://i.ytimg.com/vi/{result['id']}/hqdefault.jpg",
                    }
                )

    logger.debug(search_results)
    return search_results


def youtube_music_get_track_metadata(_, item_id, item = None):
    url = f"https://music.youtube.com/watch?v={item_id}"
    request_key = md5(f"{url}".encode()).hexdigest()
    cache_dir = os.path.join(config.get("_cache_dir"), "reqcache")
    os.makedirs(cache_dir, exist_ok=True)
    req_cache_file = os.path.join(cache_dir, request_key + ".json")

    if os.path.isfile(req_cache_file):
        logger.debug(f'URL "{url}" cache found ! HASH: {request_key}')
        with open(req_cache_file, "r", encoding="utf-8") as cf:
            info_dict = json.load(cf)

    else:
        info_dict = YoutubeDL({"quiet": True}).extract_info(url, download=False)
        json_output = json.dumps(info_dict, indent=4)
        with open(req_cache_file, "w", encoding="utf-8") as cf:
            cf.write(json_output)

    # Convert length to milliseconds
    timestamp = info_dict.get("duration_string")
    try:
        if timestamp:
            parts = timestamp.split(":")
            if len(parts) == 3:
                hours, minutes, seconds = map(int, parts)
                total_seconds = (hours * 3600) + (minutes * 60) + seconds
            elif len(parts) == 2:
                minutes, seconds = map(int, parts)
                total_seconds = (minutes * 60) + seconds
            elif len(parts) == 1:
                total_seconds = timestamp
            length = total_seconds * 1000
        else:
            length = "0"
    except Exception:
        logger.error(f"Invalid timestamp: {timestamp}")
        length = "0"

    # Get thumbnail url
    thumbnail_url = None
    for thumbnail in info_dict.get("thumbnails", []):
        current_url = thumbnail.get("url")
        # Square thumbnails are stored on googleusercontent.com as
        # opposed to ytimg.com. Select the last (highest quality)
        # square thumbnail.
        if "googleusercontent.com" in current_url:
            thumbnail_url = current_url

    if not thumbnail_url and info_dict.get("thumbnails", []):
        thumbnail_url = info_dict.get("thumbnails", [])[-1].get("url")

    info = {}
    info["title"] = info_dict.get("title")
    album = info_dict.get("album")
    info["album_name"] = album if album else info_dict.get("title")
    info["artists"] = info_dict.get("channel")
    info["album_artists"] = info_dict.get("channel")
    info["description"] = info_dict.get("description")
    # Commented thumbnails are periodically missing
    # info['image_url'] = info_dict.get('thumbnail')
    # info['image_url'] = f'https://i.ytimg.com/vi/{item_id}/maxresdefault.jpg'
    # info['image_url'] = f'https://i.ytimg.com/vi/{item_id}/hqdefault.jpg'
    info["image_url"] = thumbnail_url
    info["language"] = info_dict.get("language")
    info["item_url"] = url
    # Windows takes issue with the following line, not sure why
    # info['release_year'] = info_dict.get('release_date')[:4] #20150504
    release_year = info_dict.get("release_year")
    info["release_year"] = str(
        release_year if release_year else info_dict.get("upload_date")[:4]
    )
    info["length"] = length
    info["is_playable"] = (
        True
        if info_dict.get("availability") == "public" and not info_dict.get("is_live")
        else False
    )
    info["item_id"] = item_id
    if item.get("parent_category", "") == "album":
        info["track_number"] = item.get("playlist_number")
    return info


def youtube_music_get_playlist_data(_, playlist_id):
    url = f"https://music.youtube.com/playlist?list={playlist_id}"
    ydl_opts = {
        "quiet": True,
        "extract_flat": True,
    }

    with YoutubeDL(ydl_opts) as ytdl:
        playlist_data = ytdl.extract_info(url, download=False)

    playlist_name = playlist_data.get("title")
    playlist_by = playlist_data.get("channel")  # If null the item is an album

    track_ids = []
    for entry in playlist_data["entries"]:
        track_ids.append(entry.get("id"))
    return playlist_name, playlist_by, track_ids


def youtube_music_get_channel_track_ids(_, channel_id):
    url = f"https://music.youtube.com/channel/{channel_id}"

    ydl_opts = {
        "quiet": True,
        "extract_flat": True,
        "extractor_args": {"youtube": {"player_client": ["tv"]}},
    }

    with YoutubeDL(ydl_opts) as ytdl:
        channel_data = ytdl.extract_info(url, download=False)

    track_ids = []
    for entry in channel_data["entries"]:
        track_ids.append(entry.get("id"))
    return track_ids
