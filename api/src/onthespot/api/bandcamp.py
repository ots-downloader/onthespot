from html import unescape
import json
import re
import requests
from ..otsconfig import config
from ..runtimedata import get_logger, account_pool
from ..utils import conv_list_format, make_call

logger = get_logger("api.bandcamp")


def bandcamp_login_user(account):
    logger.info("Logging into Bandcamp account...")
    try:
        # Ping to verify connectivity
        requests.get("https://bandcamp.com")
        if account["uuid"] == "public_bandcamp":
            account_pool.append(
                {
                    "uuid": "public_bandcamp",
                    "username": "bandcamp",
                    "service": "bandcamp",
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
                "username": "bandcamp",
                "service": "bandcamp",
                "status": "error",
                "account_type": "N/A",
                "bitrate": "N/A",
            }
        )
        return False


def bandcamp_add_account():
    cfg_copy = config.get("accounts").copy()
    new_user = {
        "uuid": "public_bandcamp",
        "service": "bandcamp",
        "active": True,
    }
    cfg_copy.append(new_user)
    config.set("accounts", cfg_copy)
    config.save()


def bandcamp_get_search_results(_, search_term, content_types):
    search_results = []
    urls = []
    if "track" in content_types:
        urls.append(f"https://bandcamp.com/search?q={search_term}&item_type=t")
    if "album" in content_types:
        urls.append(f"https://bandcamp.com/search?q={search_term}&item_type=a")
    if "artist" in content_types:
        urls.append(f"https://bandcamp.com/search?q={search_term}&item_type=b")

    result_pattern = r'<li class="searchresult data-search"[^>]*>.*?</li>'
    artwork_pattern = r'<a class="artcont" href=".*?">\s*<div class="art">\s*<img src="(?P<artwork_url>.*?)"\s*.*?>'
    item_type_pattern = r'<div class="itemtype">\s*(?P<item_type>.*?)\s*</div>'
    heading_pattern = (
        r'<div class="heading">\s*<a href="(?P<url>.*?)".*?>(?P<title>.*?)</a>'
    )

    for url in urls:
        data = make_call(url, skip_cache=True, text=True, use_ssl=True)

        results = re.findall(result_pattern, data, re.DOTALL)
        for result in results:
            artwork_match = re.search(artwork_pattern, result, re.DOTALL)
            artwork_url = artwork_match.group("artwork_url") if artwork_match else None

            item_type_match = re.search(item_type_pattern, result, re.DOTALL)
            item_type = (
                item_type_match.group("item_type").strip().lower()
                if item_type_match
                else None
            )

            heading_match = re.search(heading_pattern, result, re.DOTALL)
            url = heading_match.group("url") if heading_match else None
            title = heading_match.group("title").strip() if heading_match else None

            if artwork_url and item_type and url and title:
                search_results.append(
                    {
                        "item_id": url.split("?")[0],
                        "item_name": title,
                        "item_by": None,
                        "item_type": item_type,
                        "item_service": "bandcamp",
                        "item_url": url.split("?")[0],  # Clean url
                        "item_thumbnail_url": artwork_url,
                    }
                )

    return search_results


def bandcamp_get_album_track_ids(_, url):
    logger.info(f"Getting tracks from album: {url}")
    album_webpage = make_call(url, text=True, use_ssl=True)

    matches = re.findall(
        r'<script type="application/ld\+json">\s*(\{.*?\})\s*</script>',
        album_webpage,
        re.DOTALL,
    )
    for match in matches:
        json_data_str = match
        json_data_str = re.sub(r",\s*}", "}", json_data_str)  # Remove trailing commas
        album_data = json.loads(json_data_str)

        item_ids = []
        for track in album_data.get("track", {}).get("itemListElement", []):
            item_ids.append(track["item"].get("@id"))
        return item_ids


def bandcamp_get_track_metadata(_, url):
    track_webpage = make_call(url, text=True, use_ssl=True)
    track_data = {}
    matches = re.findall(r'data-(\w+)="(.*?)"', track_webpage)
    for match in matches:
        attribute_name, attribute_value = match
        # Decode HTML entities (like &quot; to " and &amp; to &)
        decoded_value = unescape(attribute_value)
        try:
            decoded_value_json = json.loads(decoded_value)
            track_data[attribute_name] = decoded_value_json
        except json.JSONDecodeError:
            track_data[attribute_name] = decoded_value

    # Year
    year = ""
    match = re.search(
        r"\d{1,2} \w+ (\d{4})",
        track_data.get("tralbum", {}).get("current", {}).get("publish_date"),
    )
    if match:
        year = match.group(1)

    # Thumbnail Url
    thumbnail_url = ""
    match = re.search(
        r'<a class="popupImage" href="https://f4\.bcbits\.com/img/(\w+)_\d+\.jpg">',
        track_webpage,
    )
    if match:
        key = match.group(1)
        thumbnail_url = f"https://f4.bcbits.com/img/{key}_0.jpg"

    info = {}
    info["title"] = track_data.get("tralbum", {}).get("current", {}).get("title")
    info["artists"] = track_data.get("embed", {}).get("artist")
    info["album_artists"] = track_data.get("embed", {}).get("artist")
    info["item_url"] = track_data.get("embed", {}).get("linkback")
    info["album_name"] = (
        track_data.get("embed", {}).get("album_embed_data", {}).get("album_title")
    )
    info["release_year"] = year
    info["track_number"] = (
        track_data.get("tralbum", {}).get("current", {}).get("track_number")
    )
    isrc = track_data.get("tralbum", {}).get("current", {}).get("isrc")
    info["isrc"] = isrc if isrc else ""
    info["is_playable"] = True
    try:
        info["file_url"] = (
            track_data.get("tralbum", {})
            .get("trackinfo", [{}])[0]
            .get("file", {})
            .get("mp3-128")
        )
    except AttributeError:
        info["is_playable"] = False
    info["item_id"] = track_data.get("tralbum", {}).get("current", {}).get("id")
    lyrics = track_data.get("tralbum", {}).get("current", {}).get("lyrics")
    info["lyrics"] = (
        lyrics if lyrics and not config.get("only_download_synced_lyrics") else ""
    )
    info["image_url"] = thumbnail_url

    try:
        album_webpage = make_call(
            track_data["embed"]["album_embed_data"]["linkback"], text=True, use_ssl=True
        )
        matches = re.findall(
            r'<script type="application/ld\+json">\s*(\{.*?\})\s*</script>',
            album_webpage,
            re.DOTALL,
        )
        for match in matches:
            json_data_str = match
            json_data_str = re.sub(
                r",\s*}", "}", json_data_str
            )  # Remove trailing commas
            album_data = json.loads(json_data_str)
        info["total_tracks"] = album_data.get("numTracks")
        info["description"] = album_data.get("description")
        info["copyright"] = album_data.get("creditText")
        info["genre"] = conv_list_format(album_data.get("keywords", []))
    except Exception:
        info["track_number"] = 1
        info["total_tracks"] = 1
        info["album_name"] = info["title"]
        album_data = {}

    return info


def bandcamp_get_artist_album_ids(_, url):
    logger.info(f"Getting album ids for artist: '{url}'")
    root_url = re.match(r"^(https?://[^/]+)", url).group(1)
    artist_webpage = make_call(url, text=True, use_ssl=True)

    album_urls = []
    matches = re.findall(r'<a\s+href=["\'](\/album[^"\']*)["\']', artist_webpage)
    for href in matches:
        full_url = f"{root_url}{href}"
        album_urls.append(full_url)

    return album_urls
