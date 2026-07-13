from hashlib import md5
import json
import os
from yt_dlp import YoutubeDL, extractor
from ..otsconfig import config
from ..runtimedata import get_logger, account_pool
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


def generic_get_track_metadata(_, url):
    request_key = md5(f"{url}".encode()).hexdigest()
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
            info_dict = YoutubeDL(ydl_opts).extract_info(
                url, download=False
            )
            json_output = json.dumps(info_dict, indent=4)
            with open(req_cache_file, "w", encoding="utf-8") as cf:
                cf.write(json_output)

        if "entries" in info_dict:
            if len(info_dict.get("entries", [])) > 1:
                # Circular import
                from ..parse_item import parse_url

                for entry in info_dict.get("entries", []):
                    logger.debug("Found entry: %s", entry["webpage_url"])
                    parse_url(entry["webpage_url"])
                return True
    
        info = {}
        info["title"] = info_dict.get("title")
        info["artists"] = info_dict.get("extractor")
        info["image_url"] = info_dict.get("thumbnail")
        info["item_url"] = url
        info["is_playable"] = True
        # info['item_id'] = info_dict.get('id')

        return info
    except Exception as exc:
        logger.error(
            "Error extracting metadata for URL %s: %s", url, str(exc), exc_info=True
        )
        return None

def generic_list_extractors():
    extractors = extractor.gen_extractors()
    extractor_list = []
    for result in extractors:
        if ":" not in result.IE_NAME:
            extractor_list.append(result.IE_NAME)
    return extractor_list
