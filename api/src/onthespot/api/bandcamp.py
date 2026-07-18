from html import unescape
import json
import re
import requests
from urllib.request import Request, urlopen
from ..constants import HTTP_TIMEOUT
from ..otsconfig import config
from ..runtimedata import get_logger, account_pool
from ..utils import conv_list_format, make_call

logger = get_logger("api.bandcamp")

_BANDCAMP_SEARCH_URL = (
    "https://bandcamp.com/api/bcsearch_public_api/1/autocomplete_elastic"
)
_BANDCAMP_SEARCH_TYPES = {
    "track": ("t", "track"),
    "album": ("a", "album"),
    "artist": ("b", "artist"),
}


def _bandcamp_artwork_url(result):
    """Return a public Bandcamp artwork URL from search API image IDs.

    The search endpoint's ``img`` field omits the ``a`` prefix required by
    album artwork URLs and currently returns the retired ``_23`` artist image
    size.  Constructing the URL from the accompanying IDs avoids broken image
    cards while retaining the raw URL as a fallback for future response types.
    """
    art_id = result.get("art_id")
    if art_id not in (None, ""):
        return f"https://f4.bcbits.com/img/a{str(art_id).zfill(10)}_16.jpg"

    image_id = result.get("img_id")
    if image_id not in (None, ""):
        return f"https://f4.bcbits.com/img/{str(image_id).zfill(10)}_10.jpg"

    return result.get("img") or ""


def bandcamp_login_user(account):
    logger.info("Logging into Bandcamp account...")
    try:
        # Ping to verify connectivity
        requests.get("https://bandcamp.com", timeout=HTTP_TIMEOUT)
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
    """Search Bandcamp's JSON catalogue endpoint.

    Bandcamp's former HTML search page now returns a JavaScript client
    challenge to non-browser clients, so scraping ``/search`` produces an
    empty result set.  The site uses this JSON endpoint for its own catalogue
    search and returns stable IDs, URLs, artwork, and artist names directly.
    """
    search_results = []
    max_results = max(1, int(config.get("max_search_results") or 10))
    for requested_type in content_types:
        type_details = _BANDCAMP_SEARCH_TYPES.get(requested_type)
        if type_details is None:
            continue
        search_filter, item_type = type_details
        request = Request(
            _BANDCAMP_SEARCH_URL,
            data=json.dumps(
                {
                    "search_text": search_term,
                    "search_filter": search_filter,
                    "full_page": True,
                    "fan_id": None,
                }
            ).encode("utf-8"),
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
                "User-Agent": "Mozilla/5.0",
            },
            method="POST",
        )
        # Bandcamp's edge challenge currently rejects Python requests' TLS
        # client fingerprint while accepting the standard-library client used
        # here. HTTPError/URLError still bubble up to provider isolation.
        with urlopen(request, timeout=HTTP_TIMEOUT[-1]) as response:  # noqa: S310
            payload = json.loads(response.read().decode("utf-8"))
        results = payload.get("auto", {}).get("results", [])

        for result in results[:max_results]:
            if result.get("type") != search_filter:
                continue
            item_url = str(
                result.get("item_url_path") or result.get("item_url_root") or ""
            ).split("?")[0]
            item_id = str(result.get("id") or item_url)
            title = str(result.get("name") or "").strip()
            if not item_id or not item_url or not title:
                continue
            search_results.append(
                {
                    "item_id": item_id,
                    "item_name": title,
                    "item_by": result.get("band_name") or result.get("location"),
                    "item_type": item_type,
                    "item_service": "bandcamp",
                    "item_url": item_url,
                    "item_thumbnail_url": _bandcamp_artwork_url(result),
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
