import html.parser
import json
import random
import re
import requests
import uuid
from binascii import a2b_hex, b2a_hex
from Cryptodome.Cipher import AES, Blowfish
from Cryptodome.Hash import MD5
from ..otsconfig import config
from ..runtimedata import get_logger, account_pool
from ..utils import conv_list_format, make_call

logger = get_logger("api.deezer")
BASE_URL = "https://api.deezer.com/"


class ScriptExtractor(html.parser.HTMLParser):
    """extract <script> tag contents from a html page"""

    def __init__(self):
        html.parser.HTMLParser.__init__(self)
        self.scripts = []
        self.curtag = None

    def handle_starttag(self, tag, attrs):
        self.curtag = tag.lower()

    def handle_data(self, data):
        if self.curtag == "script":
            self.scripts.append(data)

    def handle_endtag(self, tag):
        self.curtag = None


def deezer_add_account(arl):
    cfg_copy = config.get("accounts").copy()
    new_user = {
        "uuid": str(uuid.uuid4()),
        "service": "deezer",
        "active": True,
        "login": {
            "arl": arl,
        },
    }
    cfg_copy.append(new_user)
    config.set("accounts", cfg_copy)
    config.save()


def deezer_get_album_track_ids(_, album_id):
    logger.info(f"Getting tracks from album: {album_id}")
    album_data = make_call(f"{BASE_URL}/album/{album_id}?limit=10000")
    item_ids = []
    for track in album_data.get("tracks", {}).get("data", []):
        item_ids.append(track.get("id"))
    return item_ids


def deezer_get_artist_album_ids(_, artist_id):
    logger.info(f"Getting album ids for artist: '{artist_id}'")
    album_data = make_call(f"{BASE_URL}/artist/{artist_id}/albums?limit=10000")
    item_ids = []
    for album in album_data.get("data", []):
        item_ids.append(album.get("id"))
    return item_ids


def deezer_get_playlist_data(_, playlist_id):
    logger.info(f"Get playlist data for playlist: '{playlist_id}'")
    playlist_data = make_call(f"{BASE_URL}/playlist/{playlist_id}?limit=10000")

    playlist_name = playlist_data.get("title", "")
    playlist_by = playlist_data.get("creator", {}).get("name")

    track_ids = []
    for track in playlist_data.get("tracks", {}).get("data", []):
        track_ids.append(track.get("id"))
    return playlist_name, playlist_by, track_ids


def deezer_get_track_metadata(_, item_id):
    logger.info(f"Get track info for: '{item_id}'")

    track_data = make_call(f"{BASE_URL}/track/{item_id}")
    album_data = make_call(
        f"{BASE_URL}/album/{track_data.get('album', {}).get('id')}?limit=10000"
    )
    album_tracks = make_call(
        f"{BASE_URL}/album/{track_data.get('album', {}).get('id')}/tracks?limit=10000"
    )
    # album_page = make_call(f"https://www.deezer.com/album/{track_data.get('album', {}).get('id')}", text=True)

    # Fetch track_number
    track_number = None
    for i, track in enumerate(album_data.get("tracks", {}).get("data", [])):
        if track.get("id") == int(item_id):
            track_number = i + 1
            break
    if not track_number:
        track_number = track_data.get("track_position")

    # Total Discs
    try:
        total_discs = album_tracks.get("data", [])[-1].get("disk_number")
    except Exception:
        total_discs = track_data.get("disk_number")

    # Artists
    artists = []
    for artist in track_data.get("contributors"):
        artists.append(artist.get("name"))

    info = {}
    info["title"] = track_data.get("title")
    info["isrc"] = track_data.get("isrc")
    info["item_url"] = track_data.get("link")
    info["length"] = str(track_data.get("duration")) + "000"
    # Deezer api does not return total_tracks only position so on a
    # second disc the number will be, for instance, 1/24 instead of 13/24.
    # I opted to iterate through the list instead as seen above.
    # info['track_number'] = track_data.get('track_position')
    info["track_number"] = track_number
    info["total_tracks"] = len(album_data.get("tracks", {}).get("data", []))
    # Deezer returns disc number but not total discs
    # so it is scraped from the album_tracks, can
    # alternatively scrape album page.
    info["disc_number"] = track_data.get("disk_number")
    info["total_discs"] = total_discs
    info["release_year"] = track_data.get("release_date").split("-")[0]
    info["explicit"] = track_data.get("explicit_lyrics")
    info["bpm"] = track_data.get("bpm")
    info["artists"] = conv_list_format(artists)
    info["image_url"] = track_data.get("album", {}).get("cover_xl")
    info["album_artists"] = album_data.get("artist", {}).get("name")
    info["album_name"] = track_data.get("album", {}).get("title")
    info["album_type"] = album_data.get("record_type")
    info["is_playable"] = track_data.get("readable")
    info["item_id"] = track_data.get("id")

    return info


def get_song_info_from_deezer_website(token, track_id):
    url = f"https://www.deezer.com/us/track/{track_id}"
    session = token["session"]
    resp = session.get(url)
    if resp.status_code == 404:
        logger.info(f"Received 404 while fetching MD5_ORIGIN, {url}")
    if "MD5_ORIGIN" not in resp.text:
        logger.info(f"Deezer MD5_ORIGIN missing for {url}")
    parser = ScriptExtractor()
    parser.feed(resp.text)
    parser.close()

    songs = []
    for script in parser.scripts:
        regex = re.search(r'{"DATA":.*', script)
        if regex:
            DZR_APP_STATE = json.loads(regex.group())
            songs.append(DZR_APP_STATE["DATA"])
    return songs[0]


def md5hex(data):
    """return hex string of md5 of the given string"""
    # type(data): bytes
    # returns: bytes
    h = MD5.new()
    h.update(data)
    return b2a_hex(h.digest())


def hexaescrypt(data, key):
    """returns hex string of aes encrypted data"""
    c = AES.new(key.encode(), AES.MODE_ECB)
    return b2a_hex(c.encrypt(data))


def calcbfkey(songid):
    """Calculate the Blowfish decrypt key for a given songid"""
    key = b"g4el58wc0zvf9na1"
    songid_md5 = md5hex(songid.encode())

    xor_op = lambda i: chr(songid_md5[i] ^ songid_md5[i + 16] ^ key[i])
    decrypt_key = "".join([xor_op(i) for i in range(16)])
    return decrypt_key


def blowfishDecrypt(data, key):
    iv = a2b_hex("0001020304050607")
    c = Blowfish.new(key.encode(), Blowfish.MODE_CBC, iv)
    return c.decrypt(data)


def decryptfile(data_chunks, key, fo):
    """
    Decrypt data from bytes <data_chunks>, and write to file <fo>.
    Decrypt using blowfish with <key>.
    Only every third 2048 byte block is encrypted.
    """
    blockSize = 2048
    i = 0
    total_length = len(data_chunks)

    for start in range(0, total_length, blockSize):
        end = min(start + blockSize, total_length)
        data = data_chunks[start:end]

        isEncrypted = (i % 3) == 0
        isWholeBlock = len(data) == blockSize

        if isEncrypted and isWholeBlock:
            data = blowfishDecrypt(data, key)

        fo.write(data)
        i += 1


def genurlkey(songid, md5origin, mediaver=4, fmt=1):
    """Calculate the deezer download url given the songid, origin and media+format"""
    data_concat = b"\xa4".join(
        _
        for _ in [
            md5origin.encode(),
            str(fmt).encode(),
            str(songid).encode(),
            str(mediaver).encode(),
        ]
    )
    data = b"\xa4".join([md5hex(data_concat), data_concat]) + b"\xa4"
    if len(data) % 16 != 0:
        data += b"\0" * (16 - len(data) % 16)
    return hexaescrypt(data, "jo6aey6haid2Teih")


def deezer_login_user(account):
    logger.info("Logging into Deezer account...")
    uuid = account["uuid"]
    arl = account["login"]["arl"]

    try:
        if uuid == "public_deezer":
            # I have no idea why rentry 403s every scraping trick I've tried
            ia_url = (
                f"http://archive.org/wayback/available?url=https://rentry.co/firehawk52"
            )
            response = requests.get(ia_url)
            if response.status_code != 200:
                logger.error(
                    f"Unable to fetch public deezer account from Internet Archive, status code: {response.raise_for_status()}"
                )
                raise Exception
            data = response.json()

            # Sometimes returns with info missing
            try:
                url = data["archived_snapshots"]["closest"]["url"]
            except Exception:
                url = "http://web.archive.org/web/20241206020314/https://rentry.co/firehawk52"

            html_content = requests.get(url).text

            table_match = re.search(
                r'<table class="ntable">(.*?)</table>', html_content, re.DOTALL
            )
            if table_match:
                table_content = table_match.group(1)
                rows = re.findall(r"<tr>(.*?)</tr>", table_content, re.DOTALL)

                public_arls = []
                for row in rows[1:]:
                    public_arl = re.search(r"<code>(.*?)</code>", row)
                    public_arls.append(public_arl.group(1))
                arl = random.choice(public_arls)

        headers = {
            "Origin": "https://www.deezer.com",
            "Accept-Encoding": "utf-8",
            "Referer": "https://www.deezer.com/login",
        }
        session = requests.Session()
        session.headers.update(headers)
        session.cookies.update({"arl": arl, "comeback": "1"})

        params = {
            "api_version": "1.0",
            "api_token": "null",
            "input": "3",
            "method": "deezer.getUserData",
        }

        user_data = session.post(
            "http://www.deezer.com/ajax/gw-light.php", params=params, headers=headers
        ).json()

        account_type = "free"
        bitrate = "128k"
        if user_data["results"]["USER"]["OPTIONS"]["web_lossless"]:
            account_type = "premium"
            bitrate = "1411k"
        elif user_data["results"]["USER"]["OPTIONS"]["web_hq"]:
            account_type = "premium"
            bitrate = "320k"

        if uuid == "public_deezer":
            account_type = "public"

        account_pool.append(
            {
                "uuid": uuid,
                "username": arl,
                "service": "deezer",
                "status": "active",
                "account_type": account_type,
                "bitrate": bitrate,
                "login": {
                    "arl": arl,
                    "license_token": user_data["results"]["USER"]["OPTIONS"][
                        "license_token"
                    ],
                    "session": session,
                },
            }
        )
        return True
    except Exception as e:
        logger.error(f"Unknown Exception: {str(e)}")
        account_pool.append(
            {
                "uuid": uuid,
                "username": arl,
                "service": "deezer",
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


def deezer_get_token(parsing_index):
    return account_pool[parsing_index]["login"]


def deezer_get_search_results(_, search_term, content_types):
    params = {}
    params["q"] = search_term
    params["limit"] = config.get("max_search_results")

    album_url = f"{BASE_URL}/search/album"
    artist_url = f"{BASE_URL}/search/artist"
    playlist_url = f"{BASE_URL}/search/playlist"
    track_url = f"{BASE_URL}/search/track"

    search_results = []

    if "track" in content_types:
        track_search = requests.get(track_url, params=params).json()
        for track in track_search["data"]:
            search_results.append(
                {
                    "item_id": track["id"],
                    "item_name": track["title"],
                    "item_by": track["artist"]["name"],
                    "item_type": "track",
                    "item_service": "deezer",
                    "item_url": track["link"],
                    "item_thumbnail_url": track["album"]["cover"],
                }
            )

    if "album" in content_types:
        album_search = requests.get(album_url, params=params).json()
        for album in album_search["data"]:
            search_results.append(
                {
                    "item_id": album["id"],
                    "item_name": album["title"],
                    "item_by": album["artist"]["name"],
                    "item_type": "album",
                    "item_service": "deezer",
                    "item_url": album["link"],
                    "item_thumbnail_url": album["cover"],
                }
            )

    if "artist" in content_types:
        artist_search = requests.get(artist_url, params=params).json()
        for artist in artist_search["data"]:
            search_results.append(
                {
                    "item_id": artist["id"],
                    "item_name": artist["name"],
                    "item_by": artist["name"],
                    "item_type": "artist",
                    "item_service": "deezer",
                    "item_url": artist["link"],
                    "item_thumbnail_url": artist["picture"],
                }
            )

    if "playlist" in content_types:
        playlist_search = requests.get(playlist_url, params=params).json()
        for playlist in playlist_search["data"]:
            search_results.append(
                {
                    "item_id": playlist["id"],
                    "item_name": playlist["title"],
                    "item_by": playlist["user"]["name"],
                    "item_type": "playlist",
                    "item_service": "deezer",
                    "item_url": playlist["link"],
                    "item_thumbnail_url": playlist["picture"],
                }
            )

    logger.info(search_results)
    return search_results


def deezer_parse_url(url):
    # Fix Circular Dependency
    from ..parse_item import parse_url

    redirect_url = requests.get(url).url
    parse_url(redirect_url)
