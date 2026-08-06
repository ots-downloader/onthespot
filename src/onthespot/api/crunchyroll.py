import base64
from hashlib import md5
import json
import os
import re
import requests
import time
from uuid import uuid4
from pywidevine.cdm import Cdm
from pywidevine.pssh import PSSH
from pywidevine.device import Device
from yt_dlp import YoutubeDL
from ..constants import WVN_KEY
from ..otsconfig import config
from ..runtimedata import get_logger, account_pool
from ..utils import make_call, conv_list_format

logger = get_logger("api.crunchyroll")
PUBLIC_TOKEN = "ZGsxYndzemRyc3lkeTR1N2xvenE6bDl0SU1BdTlzTGc4ZjA4ajlfQkQ4eWZmQmZTSms0R0o="
APP_VERSION = "3.60.0"
BASE_URL = "https://beta-api.crunchyroll.com"


def crunchyroll_login_user(account):
    try:
        headers = {}
        headers['Content-Type'] = 'application/x-www-form-urlencoded'

        if account['uuid'] == 'public_crunchyroll':
            prod = "cr_web:"
            prod_token = base64.b64encode(prod.encode("iso-8859-1")).decode()
            
            headers['Authorization'] = f'Basic {prod_token}'
            headers['ETP-Anonymous-ID'] = str(uuid4())

            payload = {}
            payload['grant_type'] = 'client_id'
        else:
            headers['Authorization'] = f'Basic {PUBLIC_TOKEN}'
            headers['Connection'] = 'Keep-Alive'
            headers['User-Agent'] = f'Crunchyroll/{APP_VERSION} Android/13 okhttp/4.12.0'

            payload = {}
            payload['username'] = account['login']['email']
            payload['password'] = account['login']['password']
            payload['grant_type'] = 'password'
            payload['scope'] = 'offline_access'
            payload['device_id'] = account['uuid']
            payload['device_name'] = 'OnTheSpot'
            payload['device_type'] = 'OnTheSpot'

        token_data = requests.post(f"{BASE_URL}/auth/v1/token", headers=headers, data=payload).json()
        
        token = token_data.get('access_token')
        refresh_token = token_data.get('refresh_token')
        token_expiry = time.time() + token_data.get('expires_in')

        header_b64, payload_b64, signature_b64 = token.split('.')
        jwt_data = json.loads(base64.urlsafe_b64decode(f'{payload_b64}==='))
        account_type = 'free'
        if jwt_data.get('status') == 'ANONYMOUS':
            account_type = 'public'
        elif 'cr_premium' in jwt_data.get('benefits', {}):
            account_type = 'premium'

        if account['uuid'] == 'public_crunchyroll':
            account_pool.append({
                "uuid": account['uuid'],
                "username": account['uuid'],
                "service": "crunchyroll",
                "status": "active",
                "account_type": account_type,
                "bitrate": "1080p",
                "login": {
                    "token": token,
                    "refresh_token": prod_token,
                    "token_expiry": token_expiry
                }
            })
        else:
            account_pool.append({
                "uuid": account['uuid'],
                "username": account['login']['email'],
                "service": "crunchyroll",
                "status": "active",
                "account_type": account_type,
                "bitrate": "1080p",
                "login": {
                    "email": account['login']['email'],
                    "password": account['login']['password'],
                    "token": token,
                    "refresh_token": refresh_token,
                    "token_expiry": token_expiry
                }
            })
        
        
        return True
    except Exception as e:
        logger.error(f"Unknown Exception: {str(e)}")
        account_pool.append({
            "uuid": account['uuid'],
            "username": account['uuid'],
            "service": "crunchyroll",
            "status": "error",
            "account_type": "N/A",
            "bitrate": "N/A",
            "login": {
                "token": None,
                "refresh_token": None,
                "token_expiry": None
            }
        })
        return False


def crunchyroll_add_account(email, password):
    cfg_copy = config.get('accounts').copy()
    new_user = {
            "uuid": str(uuid4()),
            "service": "crunchyroll",
            "active": True,
            "login": {
                "email": email,
                "password": password
            }
        }
    cfg_copy.append(new_user)
    config.set('accounts', cfg_copy)
    config.save()


def crunchyroll_get_token(parsing_index):
    if time.time() >= account_pool[parsing_index]['login']['token_expiry']:
        logger.debug("Refreshing Crunchyroll token")
        headers = {}
        headers['Content-Type'] = 'application/x-www-form-urlencoded'
        if account_pool[parsing_index]['uuid'] == 'public_crunchyroll':
            headers['Authorization'] = f"Basic {account_pool[parsing_index]['login']['refresh_token']}"
            headers['ETP-Anonymous-ID'] = str(uuid4())

            payload = {}
            payload['grant_type'] = 'client_id'

            token_data = requests.post(f"{BASE_URL}/auth/v1/token", headers=headers, data=payload).json()
        else:
            headers['Authorization'] = f'Basic {PUBLIC_TOKEN}'
            headers['Connection'] = 'Keep-Alive'
            headers['User-Agent'] = f'Crunchyroll/{APP_VERSION} Android/13 okhttp/4.12.0'

            payload = {}
            payload['refresh_token'] = account_pool[parsing_index]['login']['refresh_token']
            payload['grant_type'] = 'refresh_token'
            payload['scope'] = 'offline_access'
            payload['device_id'] = account_pool[parsing_index]['uuid']
            payload['device_name'] = 'OnTheSpot'
            payload['device_type'] = 'OnTheSpot'

            token_data = requests.post(f"{BASE_URL}/auth/v1/token", headers=headers, data=payload).json()
            account_pool[parsing_index]['login']['refresh_token'] = token_data.get('refresh_token')

        account_pool[parsing_index]['login']['token'] = token_data.get('access_token')
        account_pool[parsing_index]['login']['token_expiry'] = time.time() + token_data.get('expires_in')
    return account_pool[parsing_index]['login']['token']


def crunchyroll_get_search_results(token, search_term, _):
    headers = {}
    headers['Authorization'] = f'Bearer {token}'
    headers['Connection'] = 'Keep-Alive'
    headers['Content-Type'] = 'application/json'
    headers['User-Agent'] = f'Crunchyroll/{APP_VERSION} Android/13 okhttp/4.12.0'

    params={}
    params['q'] = search_term
    params['n'] = config.get('max_search_results')
    params["locale"] = 'en-US'
    #params["type"] = "top_results,series,movie_listing,episode"

    search_data = requests.get(f'{BASE_URL}/content/v2/discover/search', headers=headers, params=params).json()

    search_results = []
    for category in search_data['data']:
        for item in category['items']:
            if category.get('type') == 'top_results':
                continue
            elif category.get('type') == 'movie_listing':
                item_type = 'movie'
            elif category.get('type') == 'series':
                item_type = 'show'
            elif category.get('type') == 'episode':
                item_type = 'episode'

            try:
                thumbnail_url = item.get('images', {}).get('thumbnail', [])[0][0].get('source')
            except Exception:
                thumbnail_url = item.get('images', {}).get('poster_wide', [])[0][0].get('source')

            if category.get('type') == 'episode':
                item_url = f"https://www.crunchyroll.com/watch/{item.get('id')}/{item.get('slug')}"
            else:
                item_url = f"https://www.crunchyroll.com/series/{item.get('id')}/{item.get('slug')}"

            search_results.append({
                'item_id': f"{item.get('id')}/{item.get('slug')}",
                'item_name': item['title'],
                'item_by': 'Crunchyroll',
                'item_type': item_type,
                'item_service': "crunchyroll",
                'item_url': item_url,
                'item_thumbnail_url': thumbnail_url
            })

    logger.debug(search_results)
    return search_results


def crunchyroll_get_episode_metadata(token, item_id):
    headers = {}
    headers['Authorization'] = f'Bearer {token}'
    headers['Connection'] = 'Keep-Alive'
    headers['Content-Type'] = 'application/json'
    headers['User-Agent'] = f'Crunchyroll/{APP_VERSION} Android/13 okhttp/4.12.0'

    episode_data = make_call(f'{BASE_URL}/content/v2/cms/objects/{item_id.split("/")[0]}?ratings=true&images=true&locale=en-US', headers=headers)
    info_dict = episode_data['data'][0]
    # Doesn't seem to work with android bearer.
    #genre_data = make_call(f'{BASE_URL}/content/v2/discover/categories?guid={item_id.split("/")[0]}&locale=en-US', headers=headers)
    # Headers not required, 403 means data does not exist or more likely crunchyroll owns the rights to the media.
    copyright_data = make_call(f'https://static.crunchyroll.com/copyright/{item_id.split("/")[0]}.json')
    # intro and credit timestamps (done in downloader step)
    #https://static.crunchyroll.com/skip-events/production/G4VUQ588P.json
    # I believe this url gives you the difference in time between different audio formats or skips, if applicable else 403. Not entirely sure.
    #https://static.crunchyroll.com/datalab-intro-v2/G14U4XX4N.json

    #genres = []
    #for genre in genre_data['data']:
    #    genres.append(genre.get('localization', {}).get('title'))

    copyright_string = ''
    if copyright_data:
        copyright_string = copyright_data.get('long_copyright')

    info = {}
    info['title'] = info_dict.get('title')
    info['description'] = info_dict.get('description')
    info['image_url'] = info_dict.get('images', {}).get('thumbnail', [])[0][-1].get('source')
    info['show_name'] = info_dict.get('episode_metadata').get('series_title')
    info['season_number'] = info_dict.get('episode_metadata', {}).get('season_number')
    info['episode_number'] = info_dict.get('episode_metadata', {}).get('episode_number')
    info['item_url'] = f"https://www.crunchyroll.com/watch/{item_id}"
    #info['genre'] = conv_list_format(genres)
    info['copyright'] = copyright_string
    info['versions'] = info_dict.get('episode_metadata', {}).get('versions', {})
    # Not accurate
    #info['release_year'] = info_dict.get('release_year') if info_dict.get('release_year') else info_dict.get('upload_date')[:4]
    info['item_id'] = item_id.split('/')[0]
    info['explicit'] = True if int(info_dict.get('episode_metadata', {}).get('extended_maturity_rating', {}).get('rating')) != 'PG' else False
    info['is_playable'] = True

    return info


def crunchyroll_get_show_episode_ids(token, show_id):
    headers = {}
    headers['Authorization'] = f'Bearer {token}'
    headers['Connection'] = 'Keep-Alive'
    headers['Content-Type'] = 'application/json'
    headers['User-Agent'] = f'Crunchyroll/{APP_VERSION} Android/13 okhttp/4.12.0'

    url = f"{BASE_URL}/content/v2/cms/series/{show_id.split('/')[0]}/seasons"
    season_data = make_call(url, headers=headers)

    episode_ids = []
    for season in season_data.get('data', []):
        url = f"{BASE_URL}/content/v2/cms/seasons/{season.get('id')}/episodes"
        episode_data = make_call(url, headers=headers)
        for episode in episode_data.get('data', []):
            episode_ids.append(f"{episode.get('id')}/{episode.get('slug_title')}")

    return episode_ids


def crunchyroll_get_mpd_info(token, episode_id):
    headers = {}
    headers['Authorization'] = f'Bearer {token}'
    headers['Connection'] = 'Keep-Alive'
    headers['Content-Type'] = 'application/json'
    headers['User-Agent'] = f'Crunchyroll/{APP_VERSION} Android/13 okhttp/4.12.0'

    params={}
    params['queue'] = False
    params["locale"] = 'en-US'

    # Ensure you properly delete session otherwise app will lockup
    url = f"https://cr-play-service.prd.crunchyrollsvc.com/v1/{episode_id.split('/')[0]}/android/phone/play"
    resp = requests.get(url, headers=headers, params=params)
    if resp.status_code != 200:
        raise Exception(f'mpd_info_req: {resp.status_code} Response: {resp.text}')
    stream_data = resp.json()
    mpd_url = stream_data.get('url')
    stream_token = stream_data.get('token')
    audio_locale = stream_data.get('audioLocale')
    # For additional audio sources you need to restream each item in this list
    versions = stream_data.get('versions')

    subtitle_formats = []
    for key in stream_data.get('subtitles').keys():
        if key != 'none':
            subtitle_formats.append({
                "language": stream_data.get('subtitles').get(key).get("language"),
                "url": stream_data.get('subtitles').get(key).get("url"),
                "extension": stream_data.get('subtitles').get(key).get("format")
            })

    return mpd_url, stream_token, audio_locale, headers, versions, subtitle_formats


def crunchyroll_get_decryption_key(token, item_id, mpd_url, stream_token):
    headers = {}
    headers['Authorization'] = f'Bearer {token}'
    headers['Connection'] = 'Keep-Alive'
    headers['Content-Type'] = 'application/json'
    headers['User-Agent'] = f'Crunchyroll/{APP_VERSION} Android/13 okhttp/4.12.0'

    mpd_content = requests.get(mpd_url, headers=headers).text
    match = re.search(r'<cenc:pssh>(.*?)</cenc:pssh>', mpd_content)
    if match:
        pssh_match = match.group(1)
        pssh = PSSH(pssh_match)
    else:
        raise KeyError
    cdm = Cdm.from_device(Device.loads(WVN_KEY))
    session_id = cdm.open()
    challenge = cdm.get_license_challenge(session_id, pssh)
    headers['Content-Type'] = 'application/octet-stream'
    headers['X-Cr-Content-Id'] = item_id.split("/")[0]
    headers['X-Cr-Video-Token'] = stream_token
    url = 'https://cr-license-proxy.prd.crunchyrollsvc.com/v1/license/widevine'
    license_data = base64.b64decode(requests.post(url, headers=headers, params={"specConform": True}, data=challenge).content)
    cdm.parse_license(session_id, license_data)
    for key in cdm.get_keys(session_id, "CONTENT"):
        decryption_key = key.key.hex()
    cdm.close(session_id)

    return decryption_key


def crunchyroll_close_stream(token, episode_id, stream_token):
    headers = {}
    headers['Authorization'] = f'Bearer {token}'
    headers['Connection'] = 'Keep-Alive'
    headers['Content-Type'] = 'application/json'
    headers['User-Agent'] = f'Crunchyroll/{APP_VERSION} Android/13 okhttp/4.12.0'

    url = f'https://cr-play-service.prd.crunchyrollsvc.com/v1/token/{episode_id.split("/")[0]}/{stream_token}'
    resp = requests.delete(url, headers=headers)
