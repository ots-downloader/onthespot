import base64
import json
import m3u8
from pathlib import Path
import requests
import re
from uuid import uuid4
import xml.etree.ElementTree as ET
from pywidevine import PSSH, Cdm, Device
from pywidevine.license_protocol_pb2 import WidevinePsshData
from ..constants import WVN_KEY
from ..otsconfig import config
from ..runtimedata import account_pool, get_logger
from ..utils import conv_list_format, make_call, get_primary_composer

logger = get_logger("api.apple_music")
BASE_URL = 'https://amp-api.music.apple.com/v1'
WEB_BASE_URL = 'https://music.apple.com'
WVN_LICENSE_URL = "https://play.itunes.apple.com/WebObjects/MZPlay.woa/wa/acquireWebPlaybackLicense"
APPLE_MUSIC_DEVELOPER_TOKEN_REGEX = r'eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+'
APPLE_MUSIC_DEVELOPER_TOKEN_ISSUER = 'AMPWebPlay'
APPLE_MUSIC_DEVELOPER_TOKEN_KEY_ID = 'WebPlayKid'


def _extract_web_player_assets(home_page):
    asset_paths = []
    for asset_path in re.findall(r'/(assets/(?:index|index-legacy)[^/"\'<>]+\.js)', home_page):
        if asset_path not in asset_paths:
            asset_paths.append(asset_path)

    if not asset_paths:
        raise ValueError("Could not find Apple Music web player JavaScript asset.")

    return asset_paths


def _extract_developer_token(index_js_page):
    token_matches = re.findall(APPLE_MUSIC_DEVELOPER_TOKEN_REGEX, index_js_page)
    if not token_matches:
        raise ValueError("Could not find Apple Music developer token in web player asset.")

    for token in token_matches:
        header, payload, _signature = token.split('.')
        try:
            header_data = _decode_jwt_part(header)
            payload_data = _decode_jwt_part(payload)
        except Exception:
            continue

        if (
            header_data.get('kid') == APPLE_MUSIC_DEVELOPER_TOKEN_KEY_ID or
            payload_data.get('iss') == APPLE_MUSIC_DEVELOPER_TOKEN_ISSUER
        ):
            return token

    raise ValueError("Could not identify Apple Music developer token in web player asset.")


def _decode_jwt_part(jwt_part):
    jwt_part += '=' * (-len(jwt_part) % 4)
    return json.loads(base64.urlsafe_b64decode(jwt_part).decode('utf-8'))


def apple_music_add_account(media_user_token):
    cfg_copy = config.get('accounts').copy()
    new_user = {
        "uuid": str(uuid4()),
        "service": "apple_music",
        "active": True,
        "login": {
            "media-user-token": media_user_token
        }
    }
    cfg_copy.append(new_user)
    config.set('accounts', cfg_copy)
    config.save()


def apple_music_login_user(account):
    logger.info('Logging into Apple Music account...')
    try:
        session = requests.Session()
        session.cookies.update({'media-user-token': account['login']['media-user-token']})
        session.headers.update(
            {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:95.0) Gecko/20100101 Firefox/95.0",
                "Accept": "application/json",
                "Accept-Language": 'en-US',
                "Accept-Encoding": "utf-8",
                "content-type": "application/json",
                "Media-User-Token": session.cookies.get_dict().get("media-user-token"),
                "x-apple-renewal": "true",
                "DNT": "1",
                "Connection": "keep-alive",
                "Sec-Fetch-Dest": "empty",
                "Sec-Fetch-Mode": "cors",
                "Sec-Fetch-Site": "same-site",
                "origin": "https://music.apple.com",
            }
        )

        # Retrieve developer token from the web player assets.
        home_page_response = session.get(WEB_BASE_URL)
        home_page_response.raise_for_status()
        asset_paths = _extract_web_player_assets(home_page_response.text)

        token = None
        for asset_path in asset_paths:
            index_js_response = session.get(f"{WEB_BASE_URL}/{asset_path}")
            index_js_response.raise_for_status()
            try:
                token = _extract_developer_token(index_js_response.text)
                break
            except ValueError:
                logger.debug(f"Apple Music developer token not found in {asset_path}")

        if not token:
            raise ValueError("Could not find Apple Music developer token in any web player asset.")

        session.headers.update({"authorization": f"Bearer {token}"})
        session.params = {"l": 'en-US'}

        account_data_response = session.get(f'{BASE_URL}/me/account?meta=subscription')
        account_data_response.raise_for_status()
        account_data = account_data_response.json()
        session.cookies.update({'itua': account_data.get('meta', {}).get('subscription', {}).get('storefront')})

        account_pool.append({
            "uuid": account['uuid'],
            "username": account['login']['media-user-token'],
            "service": "apple_music",
            "status": "active",
            "account_type": "premium" if account_data.get('meta', {}).get('subscription', {}).get('active') else 'free',
            "bitrate": "256k",
            "login": {
                "session": session
            }
        })
        return True
    except Exception as e:
        logger.error(f"Apple Music login failed: {str(e)}")
        account_pool.append({
            "uuid": account['uuid'],
            "username": account['login']['media-user-token'],
            "service": "apple_music",
            "status": "error",
            "account_type": "N/A",
            "bitrate": "N/A",
            "login": {
                "session": ""
            }
        })
        return False


def apple_music_get_token(parsing_index):
    return account_pool[parsing_index]['login']['session']


def apple_music_get_search_results(session, search_term, content_types):
    search_types = []
    if 'track' in content_types:
        search_types.append('songs')
    if 'album' in content_types:
        search_types.append('albums')
    if 'artist' in content_types:
        search_types.append('artists')
    if 'playlist' in content_types:
        search_types.append('playlists')

    params = {}
    params['term'] = search_term
    params['limit'] = config.get("max_search_results")
    params['types'] = ",".join(search_types)

    results = make_call(f'{BASE_URL}/catalog/{session.cookies.get("itua")}/search', params=params, session=session, skip_cache=True)

    search_results = []
    for result in results['results']:

        if result == 'songs':
            for track in results['results']['songs']['data']:
                search_results.append({
                    'item_id': track['id'],
                    'item_name': track['attributes']['name'],
                    'item_by': track['attributes']['artistName'],
                    'item_type': "track",
                    'item_service': "apple_music",
                    'item_url': track['attributes']['url'],
                    'item_thumbnail_url': track.get("attributes", {}).get("artwork", {}).get("url").replace("{w}", "160").replace("{h}", "160")
                })

        if result == 'albums':
            for album in results['results']['albums']['data']:
                search_results.append({
                    'item_id': album['id'],
                    'item_name': album['attributes']['name'],
                    'item_by': album['attributes']['artistName'],
                    'item_type': "album",
                    'item_service': "apple_music",
                    'item_url': album['attributes']['url'],
                    'item_thumbnail_url': album.get("attributes", {}).get("artwork", {}).get("url").replace("{w}", "160").replace("{h}", "160")
                })

        if result == 'artists':
            for artist in results['results']['artists']['data']:
                search_results.append({
                    'item_id': artist['id'],
                    'item_name': artist['attributes']['name'],
                    'item_by': artist['attributes']['name'],
                    'item_type': "artist",
                    'item_service': "apple_music",
                    'item_url': artist['attributes']['url'],
                    'item_thumbnail_url': artist.get("attributes", {}).get("artwork", {}).get("url").replace("{w}", "160").replace("{h}", "160")
                })

        if result == 'playlists':
            for playlist in results['results']['playlists']['data']:
                search_results.append({
                    'item_id': playlist['id'],
                    'item_name': playlist['attributes']['name'],
                    'item_by': playlist['attributes'].get('curatorName'),
                    'item_type': "playlist",
                    'item_service': "apple_music",
                    'item_url': playlist['attributes']['url'],
                    'item_thumbnail_url': playlist.get("attributes", {}).get("artwork", {}).get("url").replace("{w}", "160").replace("{h}", "160")
                })

    return search_results


def apple_music_get_track_metadata(session, item_id):
    params = {}
    params['include'] = 'lyrics'
    track_data = make_call(f'{BASE_URL}/catalog/{session.cookies.get("itua")}/songs/{item_id}', params=params, session=session)
    try:
        album_id = track_data.get('data', [])[0].get('relationships', {}).get('albums', {}).get('data', [])[0].get('id', {})
        album_data = make_call(f'{BASE_URL}/catalog/{session.cookies.get("itua")}/albums/{album_id}', session=session)
    except Exception:
        album_data = ''

    # Artists
    artists = []
    for artist in track_data.get('data', [])[0].get('attributes', {}).get('artistName').replace("&", ",").split(","):
        artists.append(artist.strip())

    info = {}
    info['item_id'] = track_data.get('data', [])[0].get('id')
    info['album_name'] = track_data.get('data', [])[0].get('attributes', {}).get('albumName')
    info['genre'] = conv_list_format(track_data.get('data', [])[0].get('attributes', {}).get('genreNames', []))
    #info['track_number'] = track_data.get('data', [])[0].get('attributes', {}).get('trackNumber')
    try:
        info['release_year'] = track_data.get('data', [])[0].get('attributes', {}).get('releaseDate').split('-')[0]
    except Exception:
        pass
    info['length'] = str(track_data.get('data', [])[0].get('attributes', {}).get('durationInMillis'))
    info['isrc'] = track_data.get('data', [])[0].get('attributes', {}).get('isrc')

    image_url = track_data.get('data', [])[0].get('attributes', {}).get('artwork', {}).get('url')
    max_height = track_data.get('data', [])[0].get('attributes', {}).get('artwork', {}).get('height')
    max_width = track_data.get('data', [])[0].get('attributes', {}).get('artwork', {}).get('width')
    info['image_url'] = image_url.replace("{w}", str(max_width)).replace("{h}", str(max_height))

    info['writer'] = track_data.get('data', [])[0].get('attributes', {}).get('composerName')
    info['composer'] = info['writer']
    info['language'] = track_data.get('data', [])[0].get('attributes', {}).get('audioLocale')
    info['item_url'] = track_data.get('data', [])[0].get('attributes', {}).get('url')
    info['is_playable'] = True if track_data.get('data', [])[0].get('attributes', {}).get('playParams') else False
    info['disc_number'] = track_data.get('data', [])[0].get('attributes', {}).get('discNumber')
    info['title'] = track_data.get('data', [])[0].get('attributes', {}).get('name')
    info['explicit'] = True if track_data.get('data', [])[0].get('attributes', {}).get('contentRating') == 'explicit' else False
    info['artists'] = conv_list_format(artists)

    info['album_artists'] = artists[0]
    if config.get("prefer_composer_as_album_artist") and info['composer']:
        info['album_artists'] = get_primary_composer(info['composer'])

    if album_data:
        info['copyright'] = album_data.get('data', [])[0].get('attributes', {}).get('copyright')
        info['upc'] = album_data.get('data', [])[0].get('attributes', {}).get('upc')
        info['label'] = album_data.get('data', [])[0].get('attributes', {}).get('recordLabel')
        info['total_tracks'] = album_data.get('data', [])[0].get('attributes', {}).get('trackCount')

        album_type = 'album'
        if album_data.get('data', [])[0].get('attributes', {}).get('isSingle'):
            album_type = 'single'
        if album_data.get('data', [])[0].get('attributes', {}).get('isCompilation'):
            album_type = 'compilation'
        info['album_type'] = album_type

        # Track Number
        track_number = None

        for i, track in enumerate(album_data.get('data', [])[0].get('relationships', {}).get('tracks', {}).get('data', [])):
            if track.get('id') == str(item_id):
                track_number = i + 1
                break
        if not track_number:
            track_number = track_data.get('data', [])[0].get('attributes', {}).get('trackNumber')

        # Total Discs
        total_discs = album_data.get('data', [])[0].get('relationships', {}).get('tracks', {}).get('data', [])[-1].get('attributes', {}).get('discNumber')

        info['track_number'] = track_number
        info['total_discs'] = total_discs

    return info


def apple_music_get_lyrics(session, item_id, item_type, metadata, filepath):
    params = {}
    params['include'] = 'lyrics'
    track_data = make_call(f'{BASE_URL}/catalog/{session.cookies.get("itua")}/songs/{item_id}', params=params, session=session)

    time_synced = track_data.get('data', [])[0].get('attributes', {}).get('hasTimeSyncedLyrics')
    if config.get('only_download_synced_lyrics') and not time_synced:
        return False

    if len(track_data.get('data', [])[0].get('relationships', {}).get('lyrics', {}).get('data', [])):
        ttml_data = track_data.get('data', [])[0].get('relationships', {}).get('lyrics', {}).get('data', [])[0].get('attributes', {}).get('ttml')
        lyrics_list = []

        if not config.get('only_download_plain_lyrics'):
            if config.get("embed_branding"):
                lyrics_list.append('[re:OnTheSpot]')

            for key in metadata.keys():
                value = metadata[key]
                if key in ['title', 'track_title', 'tracktitle'] and config.get("embed_name"):
                    lyrics_list.append(f'[ti:{value}]')
                elif key == 'artists' and config.get("embed_artist"):
                    lyrics_list.append(f'[ar:{value}]')
                elif key in ['album_name', 'album'] and config.get("embed_album"):
                    lyrics_list.append(f'[al:{value}]')
                elif key in ['writers'] and config.get("embed_writers"):
                    lyrics_list.append(f'[au:{value}]')

            if config.get("embed_length"):
                l_ms = int(metadata['length'])
                if round((l_ms/1000)/60) < 10:
                    digit="0"
                else:
                    digit=""
                lyrics_list.append(f'[length:{digit}{str((l_ms/1000)/60)[:1]}:{round((l_ms/1000)%60)}]\n')

        default_length = len(lyrics_list)

        for p in ET.fromstring(ttml_data.replace('`', '')).findall('.//{http://www.w3.org/ns/ttml}p'):
            begin_time = p.attrib.get('begin')
            lyric = p.text
            if lyric:
                if time_synced:
                    if ':' in begin_time:
                        time_parts = begin_time.split(':')
                        if len(time_parts) == 3:  # Format: HH:MM:SS.mmm
                            hours, minutes, seconds = time_parts
                            minutes = int(minutes) + (int(hours) * 60)
                        elif len(time_parts) == 2:  # Format: MM:SS.mmm
                            minutes, seconds = time_parts
                    else: # Format: SS.mmm
                        minutes = '0'
                        seconds = begin_time
                    try:
                        seconds, milliseconds = seconds.split('.')
                    except (TypeError, ValueError):
                        milliseconds = '0'
                    formatted_time = f"{int(minutes):02}:{int(seconds):02}.{milliseconds.replace('s', '')[:2]}"
                    if not config.get('only_download_plain_lyrics'):
                        lyric = f'[{formatted_time}] {lyric}'

                lyrics_list.append(lyric)

        merged_lyrics = '\n'.join(lyrics_list)
        if len(merged_lyrics) <= default_length:
            return False

        if config.get('save_lrc_file'):
            with open(filepath + '.lrc', 'w', encoding='utf-8') as f:
                f.write(merged_lyrics)
        if config.get('embed_lyrics'):
            return {"lyrics": merged_lyrics}
        else:
            return False


def apple_music_get_webplayback_info(session, item_id):
    json = {}
    json['salableAdamId'] = item_id  # Corrected variable name from track_id to item_id
    webplayback_info = session.post('https://play.itunes.apple.com/WebObjects/MZPlay.woa/wa/webPlayback', json=json).json()
    return webplayback_info.get("songList")[0]


def apple_music_get_decryption_key(session, stream_url, item_id):
    # Extract the PSSH (Protection System Specific Header) from the m3u8 object
    m3u8_obj = m3u8.load(stream_url)
    pssh = m3u8_obj.keys[0].uri if m3u8_obj.keys else None

    try:
        widevine_pssh_data = WidevinePsshData()
        widevine_pssh_data.algorithm = 1
        widevine_pssh_data.key_ids.append(base64.b64decode(pssh.split(",")[1]))

        pssh_obj = PSSH(widevine_pssh_data.SerializeToString())
        cdm = Cdm.from_device(Device.loads(WVN_KEY))

        cdm_session = cdm.open()
        challenge = base64.b64encode(
            cdm.get_license_challenge(cdm_session, pssh_obj)
        ).decode()

        json = {}
        json['challenge'] = challenge
        json['key-system'] = 'com.widevine.alpha'
        json['uri'] = pssh
        json['adamId'] = item_id
        json['isLibrary'] = False
        json['user-initiated'] = True

        license_data = session.post(WVN_LICENSE_URL, json=json).json()

        wvn_license = license_data.get('license')

        cdm.parse_license(cdm_session, wvn_license)
        decryption_key = next(
            key for key in cdm.get_keys(cdm_session) if key.type == "CONTENT"
        ).key.hex()

    finally:
        cdm.close(cdm_session)

    return decryption_key


def apple_music_get_album_track_ids(session, album_id):
    logger.info(f"Getting tracks from album: {album_id}")
    album_data = make_call(f'{BASE_URL}/catalog/{session.cookies.get("itua")}/albums/{album_id}', session=session)
    item_ids = []
    for track in album_data.get('data', [])[0].get('relationships', {}).get('tracks', {}).get('data', []):
        if track['type'] == 'songs':
            item_ids.append(track['id'])
    return item_ids


def apple_music_get_artist_album_ids(session, artist_id):
    logger.info(f"Getting album ids for artist: '{artist_id}'")

    params = {}
    params['include'] = 'albums'
    params['views'] = 'full-albums,singles,live-albums'

    album_data = make_call(f'{BASE_URL}/catalog/{session.cookies.get("itua")}/artists/{artist_id}', params=params, session=session)

    item_ids = []
    for album in album_data.get('data', [])[0].get('relationships', {}).get('albums', {}).get('data', []):
        item_ids.append(album.get('id'))
    return item_ids


def apple_music_get_playlist_data(session, playlist_id):
    logger.info(f"Get playlist data for playlist: {playlist_id}")
    playlist_data = make_call(f"{BASE_URL}/catalog/{session.cookies.get('itua')}/playlists/{playlist_id}", session=session, skip_cache=True)
    playlist_name = playlist_data.get('data', [])[0].get('attributes', {}).get('name')
    playlist_by =  playlist_data.get('data', [])[0].get('attributes', {}).get('curatorName')

    track_ids = []
    offset = 0
    while True:
        url = f'{BASE_URL}/catalog/{session.cookies.get("itua")}/playlists/{playlist_id}/tracks?offset={offset}'
        playlist_track_data = make_call(url, session=session, skip_cache=True)
        for track in playlist_track_data.get('data'):
            track_ids.append(track.get('id'))
        if 'next' in playlist_track_data:
            offset += 100
        else:
            break

    return playlist_name, playlist_by, track_ids
