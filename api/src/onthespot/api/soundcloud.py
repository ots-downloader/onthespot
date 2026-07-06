import re
import requests
import json
from uuid import uuid4
from ..otsconfig import config
from ..runtimedata import get_logger, account_pool
from ..utils import make_call, conv_list_format

logger = get_logger("api.soundcloud")
BASE_URL = "https://api-v2.soundcloud.com"
headers = {
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/77.0.3865.90 Safari/537.36"
}


def soundcloud_parse_url(url, token):
    params = {}
    params["client_id"] = token["client_id"]
    params["app_version"] = token["app_version"]
    params["app_locale"] = token["app_locale"]

    resp = make_call(f"{BASE_URL}/resolve?url={url}", headers=headers, params=params)

    item_id = str(resp["id"])
    item_type = resp["kind"]
    if item_type == "user":
        item_type = "artist"
    elif item_type == "playlist" and resp.get("is_album"):
        item_type = "album"
    return item_type, item_id


def soundcloud_login_user(account):
    logger.info("Logging into Soundcloud account...")
    try:
        page_text = requests.get("https://soundcloud.com").text

        app_version_match = re.search(
            r'<script>window\.__sc_version="(\d+)"</script>',
            page_text,
        )
        app_version = app_version_match.group(1)

        client_id_url_match = re.finditer(
            r"<script\s+crossorigin\s+src=\"([^\"]+)\"",
            page_text,
        )
        *_, client_id_url_match = client_id_url_match
        client_id_url = client_id_url_match.group(1)
        client_id_page_text = requests.get(client_id_url).text
        client_id_match = re.search(r'client_id:\s*"(\w+)"', client_id_page_text)
        client_id = client_id_match.group(1)

        cfg_copy = config.get("accounts").copy()
        for _account in cfg_copy:
            if account["uuid"] == _account["uuid"]:
                # Update Client ID and App Version
                account["login"]["client_id"] = client_id
                account["login"]["app_version"] = app_version

                username = account["login"]["client_id"]
                account_type = "public"
                bitrate = "128k"
                oauth_token = account["login"].get("oauth_token")
                if oauth_token:
                    # Check OAuth Token Validity
                    headers["Content-Type"] = "application/json"
                    headers["Authorization"] = f"OAuth {oauth_token}"

                    params = {}
                    params["client_id"] = client_id

                    data = json.dumps({"session": {"access_token": oauth_token}})

                    if (
                        requests.post(
                            "https://api-auth.soundcloud.com/connect/session",
                            headers=headers,
                            data=data,
                            params=params,
                        ).status_code
                        != 200
                    ):
                        raise Exception("OAuth token expired/invalid")
                    username = oauth_token
                    account_type = "premium"
                    bitrate = "256k"

        config.set("accounts", cfg_copy)
        config.save()

        account_pool.append(
            {
                "uuid": account["uuid"],
                "username": username,
                "service": "soundcloud",
                "status": "active",
                "account_type": account_type,
                "bitrate": bitrate,
                "login": {
                    "client_id": client_id,
                    "app_version": app_version,
                    "app_locale": "en",
                    "oauth_token": oauth_token,
                },
            }
        )
        return True
    except Exception as e:
        logger.error(f"Unknown Exception: {str(e)}")
        account_pool.append(
            {
                "uuid": "public_soundcloud",
                "username": "N/A",
                "service": "soundcloud",
                "status": "error",
                "account_type": "N/A",
                "bitrate": "N/A",
                "login": {
                    "client_id": "N/A",
                    "app_version": "N/A",
                    "app_locale": "en",
                },
            }
        )
        return False


def soundcloud_add_account(oauth_token):
    cfg_copy = config.get("accounts").copy()
    new_user = {
        "uuid": str(uuid4()),
        "service": "soundcloud",
        "active": True,
        "login": {
            "client_id": "null",
            "app_version": "null",
            "app_locale": "null",
            "oauth_token": oauth_token,
        },
    }
    cfg_copy.append(new_user)
    config.set("accounts", cfg_copy)
    config.save()


def soundcloud_get_token(parsing_index):
    return account_pool[parsing_index]["login"]


def soundcloud_get_search_results(token, search_term, content_types):
    params = {}
    params["client_id"] = token["client_id"]
    params["app_version"] = token["app_version"]
    params["app_locale"] = token["app_locale"]
    params["q"] = search_term
    params["limit"] = config.get("max_search_results")

    search_results = []

    if "track" in content_types:
        track_search = requests.get(
            f"{BASE_URL}/search/tracks", headers=headers, params=params
        ).json()
        for track in track_search["collection"]:
            search_results.append(
                {
                    "item_id": track["id"],
                    "item_name": track["title"],
                    "item_by": track["user"]["username"],
                    "item_type": "track",
                    "item_service": "soundcloud",
                    "item_url": track["permalink_url"],
                    "item_thumbnail_url": track["artwork_url"],
                }
            )

    if "album" in content_types:
        playlist_search = requests.get(
            f"{BASE_URL}/search/albums", headers=headers, params=params
        ).json()
        for playlist in playlist_search["collection"]:
            search_results.append(
                {
                    "item_id": playlist["id"],
                    "item_name": playlist["title"],
                    "item_by": playlist["user"]["username"],
                    "item_type": "album",
                    "item_service": "soundcloud",
                    "item_url": playlist["permalink_url"],
                    "item_thumbnail_url": playlist["artwork_url"],
                }
            )

    if "artist" in content_types:
        playlist_search = requests.get(
            f"{BASE_URL}/search/users", headers=headers, params=params
        ).json()
        for playlist in playlist_search["collection"]:
            search_results.append(
                {
                    "item_id": playlist["id"],
                    "item_name": playlist["username"],
                    "item_by": playlist["username"],
                    "item_type": "artist",
                    "item_service": "soundcloud",
                    "item_url": playlist["permalink_url"],
                    "item_thumbnail_url": playlist["avatar_url"],
                }
            )

    if "playlist" in content_types:
        playlist_search = requests.get(
            f"{BASE_URL}/search/playlists_without_albums",
            headers=headers,
            params=params,
        ).json()
        for playlist in playlist_search["collection"]:
            search_results.append(
                {
                    "item_id": playlist["id"],
                    "item_name": playlist["title"],
                    "item_by": playlist["user"]["username"],
                    "item_type": "playlist",
                    "item_service": "soundcloud",
                    "item_url": playlist["permalink_url"],
                    "item_thumbnail_url": playlist["artwork_url"],
                }
            )

    logger.debug(search_results)
    return search_results


def soundcloud_get_artist_album_ids(token, item_id):
    logger.info(f"Getting albums for {item_id}")
    params = {}
    params["client_id"] = token["client_id"]
    params["app_version"] = token["app_version"]
    params["app_locale"] = token["app_locale"]
    params["limit"] = 10000

    artist_data = make_call(
        f"{BASE_URL}/users/{item_id}/albums", headers=headers, params=params
    )

    album_ids = []
    for album in artist_data.get("collection", []):
        album_ids.append(album.get("id"))
    return album_ids


def soundcloud_get_album_track_ids(token, item_id):
    logger.info(f"Getting tracks for {item_id}")
    params = {}
    params["client_id"] = token["client_id"]
    params["app_version"] = token["app_version"]
    params["app_locale"] = token["app_locale"]
    params["limit"] = 10000

    album_data = make_call(
        f"{BASE_URL}/playlists/{item_id}", headers=headers, params=params
    )

    track_ids = []
    for track in album_data.get("tracks", []):
        track_ids.append(track.get("id"))
    return track_ids


def soundcloud_get_playlist_data(token, item_id):
    logger.info(f"Getting playlist data for {item_id}")
    params = {}
    params["client_id"] = token["client_id"]
    params["app_version"] = token["app_version"]
    params["app_locale"] = token["app_locale"]
    params["limit"] = 10000

    playlist_data = make_call(
        f"{BASE_URL}/playlists/{item_id}", headers=headers, params=params
    )

    playlist_name = playlist_data.get("title", "")
    playlist_by = playlist_data.get("user", {}).get("username")

    track_ids = []
    for track in playlist_data.get("tracks", []):
        track_ids.append(track.get("id"))
    return playlist_name, playlist_by, track_ids


def soundcloud_get_track_metadata(token, item_id):
    params = {}
    params["client_id"] = token["client_id"]
    params["app_version"] = token["app_version"]
    params["app_locale"] = token["app_locale"]

    track_data = make_call(
        f"{BASE_URL}/tracks/{item_id}", headers=headers, params=params
    )
    # Some tracks fail with a drm error, disabling this in favour of yt-dlp's file parser
    # track_file = requests.get(track_data["media"]["transcodings"][0]["url"], headers=headers, params=params).json()
    track_webpage = make_call(f"{track_data.get('permalink_url')}/albums", text=True)
    # Parse album webpage
    start_index = track_webpage.find("<h2>Appears in albums</h2>")
    if start_index != -1:
        album_href = re.search(r'href="([^"]*)"', track_webpage[start_index:])
        if album_href:
            album_data = make_call(
                f"{BASE_URL}/resolve?url=https://soundcloud.com{album_href.group(1)}",
                headers=headers,
                params=params,
            )

    # Many soundcloud songs are missing publisher metadata, parse if exists.

    # Artists
    artists = []
    try:
        for item in track_data.get("publisher_metadata", {}).get("artist").split(","):
            artists.append(item.strip())
    except AttributeError:
        pass
    artists = conv_list_format(artists)
    if not artists:
        artists = track_data.get("user", {}).get("username")
    # Track Number
    try:
        total_tracks = album_data["track_count"]
        track_number = 0
        for track in album_data["tracks"]:
            track_number = track_number + 1
            if track["id"] == track_data["id"]:
                break
        album_type = "album"
    except (KeyError, TypeError):
        total_tracks = "1"
        track_number = "1"
        album_type = "single"
    # Album Name
    try:
        album_name = track_data["publisher_metadata"]["album_name"]
    except (KeyError, TypeError):
        start_index = track_webpage.find("<h2>Appears in albums</h2>")
        if start_index != -1:
            a_tag_match = re.search(r"<a[^>]*>(.*?)</a>", track_webpage[start_index:])
            if a_tag_match:
                album_name = a_tag_match.group(1)
        if album_name.startswith("Users who like"):
            album_name = track_data["title"]
    # Copyright
    explicit = ""
    copyright_list = ""
    try:
        publisher_metadata = track_data.get("publisher_metadata", {})
        explicit = publisher_metadata.get("explicit")
        if publisher_metadata.get("c_line"):
            copyright_list = [
                item.strip() for item in publisher_metadata.get("c_line").split(",")
            ]
    except Exception:
        pass
    copyright_data = conv_list_format(copyright_list)
    # Image Url
    # TODO: Incorporate header checks into the make_call function for caching
    try:
        image_url = track_data.get("artwork_url")
        if not image_url:
            image_url = track_data.get("user", {}).get("avatar_url")
        # It seems 't500x500' is more accessible than 'original'
        image_url = image_url.replace("large", "t500x500")
        resp = requests.head(image_url)
        resp.raise_for_status()
    except Exception as e:
        logger.info(
            f"Failed to fetch artwork url, neither album or artist image exists. image_url: {image_url} Error: {e}"
        )
        image_url = ""

    info = {}
    info["image_url"] = image_url
    info["description"] = str(track_data.get("description"))
    info["genre"] = track_data.get("genre")

    label = track_data.get("label_name")
    if label:
        info["label"] = label
    info["item_url"] = track_data.get("permalink_url")

    release_date = track_data.get("release_date")
    last_modified = track_data.get("last_modified")
    info["release_year"] = (
        release_date.split("-")[0] if release_date else last_modified.split("-")[0]
    )

    info["title"] = track_data.get("title")
    info["track_number"] = track_number
    info["total_tracks"] = total_tracks
    # info['file_url'] = track_file.get("url")
    info["length"] = str(
        track_data.get("media", {}).get("transcodings", [{}])[0].get("duration", 0)
    )
    info["artists"] = artists
    info["album_name"] = album_name
    info["album_type"] = album_type
    info["album_artists"] = track_data.get("user", {}).get("username")
    info["explicit"] = explicit
    info["copyright"] = copyright_data
    info["is_playable"] = track_data.get("streamable")
    info["item_id"] = track_data.get("id")

    return info
