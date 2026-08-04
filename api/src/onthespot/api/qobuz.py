import base64
from collections import OrderedDict
import hashlib
import re
import time
import uuid
import requests
from ..constants import HTTP_TIMEOUT
from ..otsconfig import config
from ..runtimedata import get_logger, account_pool
from ..utils import conv_list_format, make_call

logger = get_logger("api.qobuz")
BASE_URL = "https://www.qobuz.com/api.json/0.2"
QOBUZ_LOGIN_URL = "https://play.qobuz.com/login"


def qobuz_add_account(email, password):
    logger.info("Logging into Qobuz account...")
    try:
        session = requests.Session()
        response = session.get("https://play.qobuz.com/login", timeout=HTTP_TIMEOUT)
        login_page = response.text

        bundle_url_match = re.search(
            r'<script src="(/resources/\d+\.\d+\.\d+-[a-z]\d{3}/bundle\.js)"></script>',
            login_page,
        )
        if not bundle_url_match:
            raise Exception("Could not find bundle URL.")

        bundle_url = bundle_url_match.group(1)

        response = session.get(
            "https://play.qobuz.com" + bundle_url, timeout=HTTP_TIMEOUT
        )
        bundle = response.text

        app_id_regex = r'production:{api:{appId:"(?P<app_id>\d{9})",appSecret:"(\w{32})'
        seed_timezone_regex = (
            r'[a-z]\.initialSeed\("(?P<seed>[\w=]+)",window\.ut'
            r"imezone\.(?P<timezone>[a-z]+)\)"
        )
        info_extras_regex = (
            r'name:"\w+/(?P<timezone>{timezones})",info:"'
            r'(?P<info>[\w=]+)",extras:"(?P<extras>[\w=]+)"'
        )

        app_id_match = re.search(app_id_regex, bundle)
        if app_id_match is None:
            raise Exception("Could not find app id.")

        app_id = str(app_id_match.group("app_id"))

        # Get secrets
        seed_matches = re.finditer(seed_timezone_regex, bundle)
        secrets = OrderedDict()
        for match in seed_matches:
            seed, timezone = match.group("seed", "timezone")
            secrets[timezone] = [seed]

        # Ensure there are enough seeds to manipulate
        if len(secrets) < 2:
            raise Exception("Not enough secrets found.")

        # Modify the order of seeds
        keypairs = list(secrets.items())
        secrets.move_to_end(keypairs[1][0], last=False)

        # Prepare the regex for info and extras
        info_extras_regex_full = info_extras_regex.format(
            timezones="|".join(timezone.capitalize() for timezone in secrets),
        )
        info_extras_matches = re.finditer(info_extras_regex_full, bundle)
        for match in info_extras_matches:
            timezone, info, extras = match.group("timezone", "info", "extras")
            secrets[timezone.lower()] += [info, extras]

        for secret_pair in secrets:
            secrets[secret_pair] = base64.standard_b64decode(
                "".join(secrets[secret_pair])[:-44],
            ).decode("utf-8")

        vals = list(secrets.values())
        if "" in vals:
            vals.remove("")

        app_secrets = vals

        login_url = f"{BASE_URL}/user/login"

        params = {}
        params["email"] = email
        params["password"] = password
        params["app_id"] = app_id

        login_data = requests.get(
            login_url, params=params, timeout=HTTP_TIMEOUT
        ).json()

        cfg_copy = config.get("accounts").copy()
        new_user = {
            "uuid": str(uuid.uuid4()),
            "service": "qobuz",
            "active": True,
            "login": {
                "email": email,
                "password": password,
                "app_id": app_id,
                "app_secrets": app_secrets,
                "user_auth_token": login_data["user_auth_token"],
            },
        }
        cfg_copy.append(new_user)
        config.set("accounts", cfg_copy)
        config.save()

    except Exception as e:
        logger.error(f"Unknown Exception: {str(e)}")
        return False


def qobuz_login_user(account):
    try:
        # Ping to verify connectivity
        requests.get("https://qobuz.com", timeout=HTTP_TIMEOUT)
        account_pool.append(
            {
                "uuid": account["uuid"],
                "username": account["login"]["email"],
                "service": "qobuz",
                "status": "active",
                "account_type": "premium",
                "bitrate": "1411k",
                "login": {
                    "email": account["login"]["email"],
                    "password": account["login"]["password"],
                    "app_id": account["login"]["app_id"],
                    "app_secrets": account["login"]["app_secrets"],
                    "user_auth_token": account["login"]["user_auth_token"],
                },
            }
        )
        return True

    except Exception as e:
        logger.error(f"Unknown Exception: {str(e)}")
        account_pool.append(
            {
                "uuid": account["uuid"],
                "username": account["login"]["email"],
                "service": "qobuz",
                "status": "error",
                "account_type": "N/A",
                "bitrate": "N/A",
                "login": {
                    "arl": "",
                    "license_token": "",
                    "session": "",
                },
            }
        )
        return False


def qobuz_get_token(parsing_index):
    user_auth_token = account_pool[parsing_index]["login"]["user_auth_token"]
    app_id = account_pool[parsing_index]["login"]["app_id"]
    app_secrets = account_pool[parsing_index]["login"]["app_secrets"]
    return {
        "user_auth_token": user_auth_token,
        "app_id": app_id,
        "app_secrets": app_secrets,
    }


def qobuz_get_search_results(token, search_term, content_types):
    headers = {}
    headers["X-User-Auth-Token"] = token["user_auth_token"]
    headers["X-App-Id"] = token["app_id"]

    params = {}
    params["query"] = search_term
    params["limit"] = config.get("max_search_results")

    search_results = []

    if "track" in content_types:
        track_data = make_call(
            f"{BASE_URL}/track/search", params=params, headers=headers, skip_cache=True
        )
        for track in track_data["tracks"]["items"]:
            if track:
                search_results.append(
                    {
                        "item_id": track["id"],
                        "item_name": track["title"],
                        "item_by": track.get("performer").get("name"),
                        "item_type": "track",
                        "item_service": "qobuz",
                        "item_url": f"https://play.qobuz.com/track/{track['id']}",
                        "item_thumbnail_url": track.get("album", {})
                        .get("image", {})
                        .get("small"),
                    }
                )

    if "album" in content_types:
        album_data = make_call(
            f"{BASE_URL}/album/search", params=params, headers=headers, skip_cache=True
        )
        for album in album_data["albums"]["items"]:
            if album:
                search_results.append(
                    {
                        "item_id": album["id"],
                        "item_name": album["title"],
                        "item_by": album.get("artist").get("name"),
                        "item_type": "album",
                        "item_service": "qobuz",
                        "item_url": f"https://play.qobuz.com/album/{album['id']}",
                        "item_thumbnail_url": album.get("image", {}).get("small", ""),
                    }
                )

    if "artist" in content_types:
        artist_data = make_call(
            f"{BASE_URL}/artist/search", params=params, headers=headers, skip_cache=True
        )
        for artist in artist_data["artists"]["items"]:
            if artist:
                search_results.append(
                    {
                        "item_id": artist["id"],
                        "item_name": artist.get("name"),
                        "item_by": artist.get("name"),
                        "item_type": "artist",
                        "item_service": "qobuz",
                        "item_url": f"https://play.qobuz.com/artist/{artist['id']}",
                        "item_thumbnail_url": artist.get("picture", ""),
                    }
                )

    if "playlist" in content_types:
        playlist_data = make_call(
            f"{BASE_URL}/playlist/search",
            params=params,
            headers=headers,
            skip_cache=True,
        )
        for playlist in playlist_data.get("playlists", {}).get("items", []):
            if playlist:
                try:
                    thumbnail = playlist.get("image_rectangle", [])[0]
                except IndexError:
                    thumbnail = ""
                search_results.append(
                    {
                        "item_id": playlist["id"],
                        "item_name": playlist.get("name"),
                        "item_by": playlist.get("owner").get("name", "Qobuz"),
                        "item_type": "playlist",
                        "item_service": "qobuz",
                        "item_url": f"https://play.qobuz.com/playlist/{playlist['id']}",
                        "item_thumbnail_url": thumbnail,
                    }
                )

    return search_results


def qobuz_get_track_metadata(token, item_id):
    headers = {}
    headers["X-User-Auth-Token"] = token["user_auth_token"]
    headers["X-App-Id"] = token["app_id"]

    try:
        track_data = make_call(
            f"{BASE_URL}/track/get?track_id={item_id}", headers=headers
        )
        album_data = make_call(
            f"{BASE_URL}/album/get?album_id={track_data.get('album', {}).get('id')}",
            headers=headers,
        )
    except Exception:
        return

    # Artists
    artists = []
    for artist in track_data.get("album", {}).get("artists"):
        artists.append(artist.get("name"))
    if not artists:
        artists = [track_data.get("album", {}).get("artist", {}).get("name")]

    # Track Number
    track_number = None
    for i, track in enumerate(album_data.get("tracks").get("items", [])):
        if track.get("id") == track_data.get("id"):
            track_number = i + 1
            break
    if not track_number:
        track_number = track_data.get("album", {}).get("track_number")

    info = {}
    info["copyright"] = track_data.get("copyright")
    info["performers"] = track_data.get("performers")
    info["album_artists"] = track_data.get("album", {}).get("artist", {}).get("name")
    info["artists"] = conv_list_format(artists)

    info["image_url"] = track_data.get("album", {}).get("image", {}).get("large")
    info["upc"] = track_data.get("album", {}).get("upc")
    info["label"] = track_data.get("album", {}).get("label", {}).get("name")
    info["album_name"] = track_data.get("album", {}).get("title")
    info["total_tracks"] = track_data.get("album", {}).get("tracks_count")
    info["genre"] = conv_list_format(
        track_data.get("album", {}).get("genres_list", [])[-1].split("→")
    )
    info["release_year"] = (
        track_data.get("album", {}).get("release_date_original").split("-")[0]
    )
    info["description"] = track_data.get("album", {}).get("description")
    info["total_discs"] = track_data.get("album", {}).get("media_count")

    info["isrc"] = track_data.get("isrc")
    info["title"] = track_data.get("title")
    info["length"] = str(track_data.get("duration")) + "000"
    # info['track_number'] = track_data.get('track_number')
    info["track_number"] = track_number
    info["disc_number"] = track_data.get("media_number")
    info["is_playable"] = track_data.get("streamable")
    info["item_url"] = f"https://play.qobuz.com/track/{item_id}"

    return info


def qobuz_get_album_track_ids(token, album_id):
    logger.info(f"Getting tracks from album: {album_id}")

    headers = {}
    headers["X-User-Auth-Token"] = token["user_auth_token"]
    headers["X-App-Id"] = token["app_id"]

    params = {}
    params["limit"] = "500"

    album_data = make_call(
        f"{BASE_URL}/album/get?album_id={album_id}", headers=headers, params=params
    )

    item_ids = []
    for track in album_data.get("tracks", {}).get("items", []):
        item_ids.append(track["id"])
    return item_ids


def qobuz_get_artist_album_ids(token, artist_id):
    logger.info(f"Getting album ids for artist: '{artist_id}'")

    headers = {}
    headers["X-User-Auth-Token"] = token["user_auth_token"]
    headers["X-App-Id"] = token["app_id"]

    params = {}
    params["release_type"] = "album,epSingle,live"
    params["limit"] = "500"

    album_data = make_call(
        f"{BASE_URL}/artist/getReleasesList?artist_id={artist_id}",
        headers=headers,
        params=params,
    )

    item_ids = []
    for album in album_data.get("items", []):
        item_ids.append(album.get("id"))
    return item_ids


def qobuz_get_label_album_ids(token, label_id):
    logger.info(f"Getting album ids for label: '{label_id}'")

    headers = {}
    headers["X-User-Auth-Token"] = token["user_auth_token"]
    headers["X-App-Id"] = token["app_id"]

    params = {}
    params["extra"] = "albums"
    params["limit"] = "500"
    album_data = make_call(
        f"{BASE_URL}/label/get?label_id={label_id}", headers=headers, params=params
    )

    item_ids = []
    for album in album_data.get("albums", {}).get("items", []):
        item_ids.append(album.get("id"))
    return item_ids


def qobuz_get_playlist_data(token, playlist_id):
    logger.info(f"Get playlist data for playlist: {playlist_id}")

    headers = {}
    headers["X-User-Auth-Token"] = token["user_auth_token"]
    headers["X-App-Id"] = token["app_id"]

    params = {}
    params["limit"] = "500"

    playlist_data = make_call(
        f"{BASE_URL}/playlist/get?playlist_id={playlist_id}&extra=track_ids",
        headers=headers,
        params=params,
        skip_cache=True,
    )

    playlist_name = playlist_data.get("name")
    playlist_by = playlist_data.get("owner", {}).get("name", "Qobuz")
    track_ids = playlist_data.get("track_ids", [])
    return playlist_name, playlist_by, track_ids


def qobuz_get_file_url(token, item_id):
    headers = {}
    headers["X-User-Auth-Token"] = token["user_auth_token"]
    headers["X-App-Id"] = token["app_id"]

    for secret in token["app_secrets"]:
        quality = 27
        intent = "stream"

        # Create the signature for the request
        unix_ts = int(time.time())
        r_sig = f"trackgetFileUrlformat_id{quality}intent{intent}track_id{item_id}{unix_ts}{secret}"  # Replace with your secret
        # Qobuz's request-signing protocol mandates MD5; this is not used for
        # password storage or local integrity checks.
        r_sig_hashed = hashlib.md5(
            r_sig.encode("utf-8"), usedforsecurity=False
        ).hexdigest()

        params = {}
        params["request_ts"] = unix_ts
        params["request_sig"] = r_sig_hashed
        params["track_id"] = item_id
        params["format_id"] = quality
        params["intent"] = intent

        file_response = requests.get(
            f"{BASE_URL}/track/getFileUrl",
            params=params,
            headers=headers,
            timeout=HTTP_TIMEOUT,
        )
        if file_response.status_code == 200:
            file_data = file_response.json()
            return file_data.get("url")
