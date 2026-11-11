import json
import os
from hashlib import md5

from yt_dlp import YoutubeDL, extractor

from ..otsconfig import config
from ..runtimedata import account_pool, get_logger
from ..youtube_auth import is_youtube_url, youtube_ydl_options

logger = get_logger("api.generic")


def generic_login_user(_):
    account_pool.append(
        {
            "uuid": "yt-dlp",
            "username": "yt-dlp",
            "service": "generic",
            "status": "active",
            "account_type": "public",
            "bitrate": "N/A",
        }
    )
    return True


def generic_add_account():
    cfg_copy = config.get("accounts").copy()
    new_user = {
        "uuid": "yt-dlp",
        "service": "generic",
        "active": True,
    }
    cfg_copy.append(new_user)
    config.set("accounts", cfg_copy)
    config.save()


def generic_get_track_metadata(_, url, item) -> list | dict | None:
    request_key = md5(f"{url}".encode(), usedforsecurity=False).hexdigest()
    cache_dir = os.path.join(config.get("_cache_dir"), "reqcache")
    os.makedirs(cache_dir, exist_ok=True)
    req_cache_file = os.path.join(cache_dir, request_key + ".json")
    try:
        if os.path.isfile(req_cache_file):
            logger.debug('URL "%s" cache found ! HASH: %s', url, request_key)
            with open(req_cache_file, "r", encoding="utf-8") as cf:
                info_dict = json.load(cf)

        else:
            ydl_opts = {"quiet": True, "extract_flat": True}
            if is_youtube_url(url):
                ydl_opts.update(youtube_ydl_options())
            info_dict = YoutubeDL(ydl_opts).extract_info(url, download=False)
            json_output = json.dumps(info_dict, indent=4)
            with open(req_cache_file, "w", encoding="utf-8") as cf:
                cf.write(json_output)

        if "entries" in info_dict and len(info_dict.get("entries", [])) > 1:
            url_dict = []
            for entry in info_dict.get("entries", []):
                if not entry:
                    continue
                # A flat entry ("_type": "url") keeps its page link in "url".
                # An inline entry's "url" is a direct media link, so read
                # its "webpage_url" instead.
                is_flat = entry.get("_type") in ("url", "url_transparent")
                entry_url = (entry.get("url") if is_flat else None) or entry.get("webpage_url")
                # Skip entries that point back at the playlist itself.
                if not entry_url or entry_url == url or entry_url in url_dict:
                    continue
                logger.debug("Found entry: %s", entry_url)
                url_dict.append(entry_url)
            return url_dict

        info = {}
        info["title"] = info_dict.get("title")
        info["artists"] = info_dict.get("extractor")
        info["image_url"] = info_dict.get("thumbnail")
        info["item_url"] = url
        info["is_playable"] = True
        # info['item_id'] = info_dict.get('id')

        return info
    except Exception as exc:
        logger.error("Error extracting metadata for URL %s: %s", url, str(exc), exc_info=True)
        return None


def generic_list_extractors():
    extractors = extractor.gen_extractors()
    extractor_list = []
    for result in extractors:
        if ":" not in result.IE_NAME:
            extractor_list.append(result.IE_NAME)
    return extractor_list
