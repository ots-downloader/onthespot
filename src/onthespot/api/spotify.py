import base64
import json
import os
import re
import requests
import threading
import time
import traceback
import uuid
from librespot.audio.decoders import AudioQuality
from librespot.core import Session
from librespot.zeroconf import ZeroconfServer
from PyQt6.QtCore import QObject
from ..otsconfig import config, cache_dir
from ..runtimedata import get_logger, account_pool, pending, download_queue, pending_lock
from ..utils import make_call, conv_list_format

logger = get_logger("api.spotify")
BASE_URL = "https://api.spotify.com/v1"

# OAuth token cache (for Client Credentials flow)
_oauth_token_cache = {
    'access_token': None,
    'expires_at': 0
}


def spotify_get_oauth_token():
    """
    Get OAuth access token using Client Credentials flow.
    Uses your own Spotify app credentials instead of librespot tokens.
    Recommended for Web API calls to avoid 429 rate limiting.

    Returns OAuth access token string, or None if not configured/failed.
    """
    # Return cached token if still valid
    if _oauth_token_cache['access_token'] and time.time() < _oauth_token_cache['expires_at']:
        logger.debug("Using cached OAuth token")
        return _oauth_token_cache['access_token']

    # Get credentials from config
    client_id = config.get('spotify_webapi_override_client_id', '').strip()
    client_secret = config.get('spotify_webapi_override_client_secret', '').strip()

    if not client_id or not client_secret:
        logger.debug("Web API override credentials not configured, will use librespot token instead")
        return None

    # Encode credentials for Basic Auth
    credentials = f"{client_id}:{client_secret}"
    credentials_b64 = base64.b64encode(credentials.encode()).decode()

    # Request token using Client Credentials flow
    token_url = "https://accounts.spotify.com/api/token"
    headers = {
        "Authorization": f"Basic {credentials_b64}",
        "Content-Type": "application/x-www-form-urlencoded"
    }
    data = {"grant_type": "client_credentials"}

    try:
        logger.info("[OAUTH] Requesting new access token from Spotify")
        response = requests.post(token_url, headers=headers, data=data, timeout=10)

        if response.status_code == 200:
            token_data = response.json()
            access_token = token_data['access_token']
            expires_in = token_data['expires_in']  # Seconds until expiration (usually 3600)

            # Cache token with 5 minute buffer before expiration
            _oauth_token_cache['access_token'] = access_token
            _oauth_token_cache['expires_at'] = time.time() + expires_in - 300

            logger.info(f"[OAUTH] Successfully obtained access token (expires in {expires_in}s)")
            logger.info("[AUTH] Using Web API override credentials (OAuth) for metadata authentication")
            return access_token
        else:
            logger.error(f"[OAUTH] Failed to get access token: {response.status_code} - {response.text}")
            return None

    except Exception as e:
        logger.error(f"[OAUTH] Exception while getting access token: {str(e)}")
        return None


def spotify_get_auth_header():
    """
    Get Authorization header for Spotify Web API calls.

    Auto-detects authentication method:
    - If override credentials configured: Use OAuth token
    - Otherwise: Use librespot session token

    Returns dict with Authorization header, or None if authentication unavailable.
    """
    # Try OAuth first if override credentials are configured
    oauth_token = spotify_get_oauth_token()
    if oauth_token:
        # Success message already logged in spotify_get_oauth_token()
        return {'Authorization': f'Bearer {oauth_token}'}

    # Fall back to librespot session tokens
    logger.info("[AUTH] Using librespot session token for Web API authentication (default behavior)")
    try:
        from ..accounts import get_account_token
        token = get_account_token('spotify')
        if token:
            # This is a librespot Session object
            oauth_token = token.tokens().get('user-read-email')
            if oauth_token:
                return {'Authorization': f'Bearer {oauth_token}'}
            else:
                logger.error("[AUTH] Failed to extract OAuth token from librespot session")
        else:
            logger.error("[AUTH] Failed to get librespot session token")
    except Exception as e:
        logger.error(f"[AUTH] Error accessing librespot token: {str(e)}")

    logger.error("[AUTH] All authentication methods failed - no valid token available")
    return None


class MirrorSpotifyPlayback(QObject):
    def __init__(self):
        super().__init__()
        self.thread = None
        self.is_running = False

    def start(self):
        if self.thread is None:
            logger.info('Starting SpotifyMirrorPlayback')
            self.is_running = True
            self.thread = threading.Thread(target=self.run)
            self.thread.start()
        else:
            logger.warning('SpotifyMirrorPlayback is already running.')

    def stop(self):
        if self.thread is not None:
            logger.info('Stopping SpotifyMirrorPlayback')
            self.is_running = False
            self.thread.join()
            self.thread = None
        else:
            logger.warning('SpotifyMirrorPlayback is not running.')

    def run(self):
        # Circular Import
        from ..accounts import get_account_token
        while self.is_running:
            time.sleep(5)
            try:
                token = get_account_token('spotify').tokens()
            except (AttributeError, IndexError):
                # Account pool hasn't been filled yet
                continue
            url = f"{BASE_URL}/me/player/currently-playing"
            try:
                resp = requests.get(url, headers={"Authorization": f"Bearer {token.get('user-read-currently-playing')}"})
            except:
                logger.info("Session Expired, reinitializing...")
                parsing_index = config.get('active_account_number')
                spotify_re_init_session(account_pool[parsing_index])
                token = account_pool[parsing_index]['login']['session']
                continue
            if resp.status_code == 200:
                data = resp.json()
                if data['currently_playing_type'] == 'track':
                    item_id = data['item']['id']
                    if item_id not in pending and item_id not in download_queue:
                        parent_category = 'track'
                        playlist_name = ''
                        playlist_by = ''
                        if data['context'] is not None:
                            if data['context'].get('type') == 'playlist':
                                match = re.search(r'spotify:playlist:(\w+)', data['context']['uri'])
                                if match:
                                    playlist_id = match.group(1)
                                else:
                                    continue
                                token = get_account_token('spotify')
                                playlist_name, playlist_by = spotify_get_playlist_data(token, playlist_id)
                                parent_category = 'playlist'
                            elif data['context'].get('type') == 'collection':
                                playlist_name = 'Liked Songs'
                                playlist_by = 'me'
                                parent_category = 'playlist'
                            elif data['context'].get('type') in ('album', 'artist'):
                                parent_category = 'album'
                        # Use item id to prevent duplicates
                        #local_id = format_local_id(item_id)
                        with pending_lock:
                            pending[item_id] = {
                                'local_id': item_id,
                                'item_service': 'spotify',
                                'item_type': 'track',
                                'item_id': item_id,
                                'parent_category': parent_category,
                                'playlist_name': playlist_name,
                                'playlist_by': playlist_by,
                                'playlist_number': '?'
                            }
                        logger.info(f'Mirror Spotify Playback added track to download queue: https://open.spotify.com/track/{item_id}')
                        continue
                else:
                    logger.info('Spotify API does not return enough data to parse currently playing episodes.')
                    continue
            else:
                continue


def spotify_new_session():
    os.makedirs(os.path.join(cache_dir(), 'sessions'), exist_ok=True)

    uuid_uniq = str(uuid.uuid4())
    session_json_path = os.path.join(os.path.join(cache_dir(), 'sessions'),
                 f"ots_login_{uuid_uniq}.json")

    CLIENT_ID: str = "65b708073fc0480ea92a077233ca87bd"
    ZeroconfServer._ZeroconfServer__default_get_info_fields['clientID'] = CLIENT_ID
    zs_builder = ZeroconfServer.Builder()
    zs_builder.device_name = 'OnTheSpot'
    zs_builder.conf.stored_credentials_file = session_json_path
    zs = zs_builder.create()
    logger.info("Zeroconf login service started")

    while True:
        time.sleep(1)
        if zs.has_valid_session():
            logger.info(f"Grabbed {zs._ZeroconfServer__session} for {zs._ZeroconfServer__session.username()}")
            if zs._ZeroconfServer__session.username() in config.get('accounts'):
                logger.info("Account already exists")
                return False
            else:
                # I wish there was a way to get credentials without saving to
                # a file and parsing it but not currently sure how.
                try:
                    with open(session_json_path, 'r') as file:
                        zeroconf_login = json.load(file)
                except FileNotFoundError as e:
                    logger.error(f"Error: {str(e)} The file {session_json_path} was not found.\nTraceback: {traceback.format_exc()}")
                except json.JSONDecodeError as e:
                    logger.error(f"Error: {str(e)} Failed to decode JSON from the file.\nTraceback: {traceback.format_exc()}")
                except Exception as e:
                    logger.error(f"Unknown Error: {str(e)}\nTraceback: {traceback.format_exc()}")
                cfg_copy = config.get('accounts').copy()
                new_user = {
                    "uuid": uuid_uniq,
                    "service": "spotify",
                    "active": True,
                    "login": {
                        "username": zeroconf_login["username"],
                        "credentials": zeroconf_login["credentials"],
                        "type": zeroconf_login["type"],
                    }
                }
                zs.close()
                cfg_copy.append(new_user)
                config.set('accounts', cfg_copy)
                config.save()
                logger.info("New account added to config.")
                return True


def spotify_login_user(account):
    try:
        # I'd prefer to use 'Session.Builder().stored(credentials).create but
        # I can't get it to work, loading from credentials file instead.
        uuid = account['uuid']
        username = account['login']['username']

        session_dir = os.path.join(cache_dir(), "sessions")
        os.makedirs(session_dir, exist_ok=True)
        session_json_path = os.path.join(session_dir, f"ots_login_{uuid}.json")
        try:
            with open(session_json_path, 'w') as file:
                json.dump(account['login'], file)
            logger.info(f"Login information for '{username[:4]}*******' written to {session_json_path}")
        except IOError as e:
            logger.error(f"Error writing to file {session_json_path}: {str(e)}\nTraceback: {traceback.format_exc()}")

        config = Session.Configuration.Builder().set_stored_credential_file(session_json_path).build()
        # For some reason initialising session as None prevents premature application exit
        session = None
        try:
            session = Session.Builder(conf=config).stored_file(session_json_path).create()
        except Exception:
            time.sleep(3)
            session = Session.Builder(conf=config).stored_file(session_json_path).create()
        logger.debug("Session created")
        logger.info(f"Login successful for user '{username[:4]}*******'")
        account_type = session.get_user_attribute("type")
        bitrate = "160k"
        if account_type == "premium":
            bitrate = "320k"
        account_pool.append({
            "uuid": uuid,
            "username": username,
            "service": "spotify",
            "status": "active",
            "account_type": account_type,
            "bitrate": bitrate,
            "login": {
                "session": session,
                "session_path": session_json_path,
            }
        })
        return True
    except Exception as e:
        logger.error(f"Unknown Exception: {str(e)}\nTraceback: {traceback.format_exc()}")
        account_pool.append({
            "uuid": uuid,
            "username": username,
            "service": "spotify",
            "status": "error",
            "account_type": "N/A",
            "bitrate": "N/A",
            "login": {
                "session": "",
                "session_path": "",
            }
        })
        return False


def spotify_re_init_session(account):
    session_json_path = os.path.join(cache_dir(), "sessions", f"ots_login_{account['uuid']}.json")
    try:
        config = Session.Configuration.Builder().set_stored_credential_file(session_json_path).build()
        logger.debug("Session config created")
        session = Session.Builder(conf=config).stored_file(session_json_path).create()
        logger.debug("Session re init done")
        account['login']['session_path'] = session_json_path
        account['login']['session'] = session
        account['status'] = 'active'
        account['account_type'] = session.get_user_attribute("type")
        bitrate = "160k"
        account_type = session.get_user_attribute("type")
        if account_type == "premium":
            bitrate = "320k"
        account['bitrate'] = bitrate
    except:
        logger.error('Failed to re init session !')


def spotify_get_token(parsing_index):
    try:
        token = account_pool[parsing_index]['login']['session']
    except (OSError, AttributeError):
        logger.info(f'Failed to retreive token for {account_pool[parsing_index]["username"]}, attempting to reinit session.')
        spotify_re_init_session(account_pool[parsing_index])
        token = account_pool[parsing_index]['login']['session']
    return token


def spotify_get_artist_album_ids(token, artist_id):
    logger.info(f"Getting album ids for artist: '{artist_id}'")
    items = []
    offset = 0
    limit = 50
    while True:
        # Use new auth method (OAuth or librespot)
        auth_header = spotify_get_auth_header()
        if not auth_header:
            logger.error("Failed to get authentication header")
            return []
        headers = auth_header

        url = f'{BASE_URL}/artists/{artist_id}/albums?include_groups=album%2Csingle&limit={limit}&offset={offset}' #%2Cappears_on%2Ccompilation
        artist_data = make_call(url, headers=headers)

        offset += limit
        items.extend(artist_data['items'])

        if artist_data['total'] <= offset:
            break

    item_ids = []
    for album in items:
        item_ids.append(album['id'])
    return item_ids


def spotify_get_playlist_data(token, playlist_id):
    logger.info(f"Get playlist data for playlist: {playlist_id}")
    # Use new auth method (OAuth or librespot)
    auth_header = spotify_get_auth_header()
    if not auth_header:
        logger.error("Failed to get authentication header")
        return "Unknown", "Unknown"
    headers = auth_header
    resp = make_call(f'{BASE_URL}/playlists/{playlist_id}', headers=headers, skip_cache=True)
    return resp['name'], resp['owner']['display_name']


def spotify_get_lyrics(token, item_id, item_type, metadata, filepath):
    if config.get('download_lyrics'):
        lyrics = []
        try:
            if item_type == "track":
                url = f'https://spclient.wg.spotify.com/color-lyrics/v2/track/{item_id}?format=json&market=from_token'
            elif item_type == "episode":
                url = f"https://spclient.wg.spotify.com/transcript-read-along/v2/episode/{item_id}?format=json&market=from_token"

            headers = {}
            headers['app-platform'] = 'WebPlayer'
            headers['Authorization'] = f'Bearer {token.tokens().get("user-read-email")}'
            headers['user-agent'] = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/77.0.3865.90 Safari/537.36'

            resp = make_call(url, headers=headers)
            if resp == None:
                logger.info(f"Failed to find lyrics for {item_type}: {item_id}")
                return None

            if not config.get('only_download_plain_lyrics'):
                if config.get("embed_branding"):
                    lyrics.append('[re:OnTheSpot]')

                for key in metadata.keys():
                    value = metadata[key]
                    if key in ['title', 'track_title', 'tracktitle'] and config.get("embed_name"):
                        title = value
                        lyrics.append(f'[ti:{title}]')
                    elif key == 'artists' and config.get("embed_artist"):
                        artist = value
                        lyrics.append(f'[ar:{artist}]')
                    elif key in ['album_name', 'album'] and config.get("embed_album"):
                        album = value
                        lyrics.append(f'[al:{album}]')
                    elif key in ['writers'] and config.get("embed_writers"):
                        author = value
                        lyrics.append(f'[au:{author}]')

                if item_type == "track":
                    lyrics.append(f'[by:{resp["lyrics"]["provider"]}]')

                if config.get("embed_length"):
                    l_ms = int(metadata['length'])
                    if round((l_ms/1000)/60) < 10:
                        digit="0"
                    else:
                        digit=""
                    lyrics.append(f'[length:{digit}{round((l_ms/1000)/60)}:{round((l_ms/1000)%60)}]\n')

            default_length = len(lyrics)

            if item_type == "track":
                if resp["lyrics"]["syncType"] == "LINE_SYNCED":
                    for line in resp["lyrics"]["lines"]:
                        minutes, seconds = divmod(int(line['startTimeMs']) / 1000, 60)
                        if not config.get('only_download_plain_lyrics'):
                            lyrics.append(f'[{minutes:0>2.0f}:{seconds:05.2f}] {line["words"]}')
                        else:
                            lyrics.append(line["words"])
                elif resp["lyrics"]["syncType"] == "UNSYNCED" and not config.get("only_download_synced_lyrics"):
                    lyrics = [line['words'] for line in resp['lyrics']['lines']]

            elif item_type == "episode":
                if resp["timeSyncedStatus"] == "SYLLABLE_SYNCED":
                    for line in resp["section"]:
                        try:
                            minutes, seconds = divmod(int(line['startMs']) / 1000, 60)
                            lyrics.append(f'[{minutes:0>2.0f}:{seconds:05.2f}] {line["text"]["sentence"]["text"]}')
                        except KeyError as e:
                            logger.debug(f"Invalid line: {str(e)} likely title, skipping..")
                else:
                    logger.info("Unsynced episode lyrics, please open a bug report.")

        except requests.exceptions.RequestException as e:
            # Lyrics are optional - a 404 (or any request error) just means no
            # lyrics are available, so log it and continue the download without them.
            logger.info(f'No lyrics available for {item_type} {item_id}: {str(e)}')
            return None
        except (KeyError, IndexError) as e:
            logger.error(f'KeyError/Index Error. Failed to get lyrics for {item_id}: {str(e)}\nTraceback: {traceback.format_exc()}')

        merged_lyrics = '\n'.join(lyrics)

        if lyrics:
            logger.debug(lyrics)
            if len(lyrics) <= default_length:
                return False
            if config.get('save_lrc_file'):
                with open(filepath + '.lrc', 'w', encoding='utf-8') as f:
                    f.write(merged_lyrics)
            if config.get('embed_lyrics'):
                if item_type == "track":
                    return {"lyrics": merged_lyrics, "language": resp['lyrics']['language']}
                if item_type == "episode":
                    return {"lyrics": merged_lyrics}
            else:
                return True
    else:
        return False


def spotify_get_playlist_items(token, playlist_id):
    logger.info(f"Getting items in playlist: '{playlist_id}'")
    items = []
    offset = 0
    limit = 100

    while True:
        url = f'{BASE_URL}/playlists/{playlist_id}/tracks?additional_types=track%2Cepisode&offset={offset}&limit={limit}'
        # Use new auth method (OAuth or librespot)
        auth_header = spotify_get_auth_header()
        if not auth_header:
            logger.error("Failed to get authentication header")
            return []
        headers = auth_header
        try:
            resp = make_call(url, headers=headers, skip_cache=True)
        except Exception as e:
            raise e

        offset += limit
        items.extend(resp['items'])

        if resp['total'] <= offset:
            break
    return items


def spotify_get_liked_songs(token):
    logger.info("Getting liked songs")
    items = []
    offset = 0
    limit = 50

    while True:
        url = f'{BASE_URL}/me/tracks?offset={offset}&limit={limit}'
        headers = {}
        headers['Authorization'] = f"Bearer {token.tokens().get('user-library-read')}"

        resp = make_call(url, headers=headers, skip_cache=True)

        offset += limit
        items.extend(resp['items'])

        if resp['total'] <= offset:
            break
    return items


def spotify_get_your_episodes(token):
    logger.info("Getting your episodes")
    items = []
    offset = 0
    limit = 50

    while True:
        headers = {}
        headers['Authorization'] = f"Bearer {token.tokens().get('user-library-read')}"
        url = f'{BASE_URL}/me/episodes?offset={offset}&limit={limit}'

        resp = make_call(url, headers=headers, skip_cache=True)

        offset += limit
        items.extend(resp['items'])

        if resp['total'] <= offset:
            break
    return items


def spotify_get_album_track_ids(token, album_id):
    logger.info(f"Getting tracks from album: {album_id}")
    tracks = []
    offset = 0
    limit = 50

    while True:
        url=f'{BASE_URL}/albums/{album_id}/tracks?offset={offset}&limit={limit}'
        logger.info(f"  [Sub-API Call] Fetching album tracks: offset={offset}, limit={limit}")
        # Use new auth method (OAuth or librespot)
        auth_header = spotify_get_auth_header()
        if not auth_header:
            logger.error("Failed to get authentication header")
            return []
        headers = auth_header
        resp = make_call(url, headers=headers)

        offset += limit
        tracks.extend(resp['items'])

        if resp['total'] <= offset:
            break

    item_ids = []
    for track in tracks:
        if track:
            item_ids.append(track['id'])
    return item_ids


def spotify_get_search_results(token, search_term, content_types, filter_tracks=True, filter_albums=True, filter_artists=True, filter_playlists=True, search_prefix=""):
    logger.info(f"Get search result for term '{search_term}'")
    logger.info(f"Searching for '{content_types}'")
    # Use new auth method (OAuth or librespot)
    auth_header = spotify_get_auth_header()
    if not auth_header:
        logger.error("Failed to get authentication header")
        return []
    headers = auth_header

    params = {}
    params['limit'] = config.get("max_search_results")
    params['offset'] = '0'
    params['q'] = search_term
    # Changed params[] expression below - it does not need transform! 
    params['type'] = ",".join(content_types)
    
    rejected_albums = 0
    rejected_artists = 0
    rejected_tracks = 0
    rejected_playlists = 0
    # set article (prefix) removed from items for filters ensuring the last character is a space.
    prefix = search_prefix.strip().lower() + " "

    data = requests.get(f"{BASE_URL}/search", params=params, headers=headers).json()   
    search_results = []
    for key, section in (data or {}).items():
        items = (section or {}).get("items", []) or []
        for item in items:
            if not item:
                continue
            item_type = item.get('type')
            if not item_type:
                continue
#TRACKS               
            if item_type == "track":
                if filter_tracks:  
                    # Keep only tracks where title or artist contains search term (ignoring 'the ' prefix)
                    term_normalized = search_term.lower().removeprefix(prefix).strip()
                    title_normalized = item['name'].lower().removeprefix(prefix).strip()
                    artist_normalized = item['artists'][0]['name'].lower().removeprefix(prefix).strip()
                    
                    if term_normalized not in title_normalized and term_normalized not in artist_normalized:
                        logger.info(f"TRACK REJECTED Prefix: {prefix} : Search Term: {term_normalized} : Title: {title_normalized} : Artist: {artist_normalized}") 
                        rejected_tracks += 1
                        continue
                
                item_name = f"{config.get('explicit_label') if item['explicit'] else ''} {item['name']}"
                item_by = f"{config.get('metadata_separator').join([artist['name'] for artist in item['artists']])}"
                item_thumbnail_url = item['album']['images'][-1]["url"] if item['album']['images'] else ""
#ALBUMS                
            elif item_type == "album":                
                if filter_albums:
                    # Keep only albums where artist name OR album name starts with search term (ignoring prefix)
                    term_normalized = search_term.lower().removeprefix(prefix).strip()
                    artist_normalized = item['artists'][0]['name'].lower().removeprefix(prefix).strip()
                    album_normalized = item['name'].lower().removeprefix(prefix).strip()
                    
                    artist_match = artist_normalized.startswith(term_normalized)
                    album_match = album_normalized.startswith(term_normalized)
                    
                    if not artist_match and not album_match:
                        logger.info(f"ALBUM REJECTED Prefix: {prefix} : Search Term: {term_normalized} : Artist: {artist_normalized} : Album: {album_normalized}") 
                        rejected_albums += 1
                        continue
                
                rel_year = re.search(r'(\d{4})', item['release_date']).group(1)
                item_name = f"[Y:{rel_year}] [T:{item['total_tracks']}] {item['name']}"
                item_by = f"{config.get('metadata_separator').join([artist['name'] for artist in item['artists']])}"
                item_thumbnail_url = item['images'][-1]["url"] if item['images'] else ""
                # logger.info(f"Album OK - artist: '{item['artists'][0]['name']}' Album: '{item['name']}'")
#PLAYLISTS                
            elif item_type == "playlist":
                if filter_playlists:
                    # Keep only playlists where name contains search term (ignoring 'the ' prefix)
                    term_normalized = search_term.lower().removeprefix(prefix).strip()
                    playlist_normalized = item['name'].lower().removeprefix(prefix).strip()
                    
                    if term_normalized not in playlist_normalized:
                        rejected_playlists += 1
                        logger.info(f"PLAYLIST REJECTED Prefix: {prefix} : Search Term: {term_normalized} : Playlist Name: {playlist_normalized} : By: {item['owner']['display_name']}")
                        continue
                
                item_name = f"[T:{item['tracks']['total']}] {item['name']}"
                item_by = f"{item['owner']['display_name']}"
                item_thumbnail_url = item['images'][-1]["url"] if item['images'] else ""
                # logger.info(f"Playlist OK: '{item['name']}' - Tracks: {item['tracks']['total']}")
#ARTISTS    
            elif item_type == "artist":
                if filter_artists:
                    # Keep only artists where name starts with search term (ignoring 'the ' prefix)
                    name_normalized = item['name'].lower().removeprefix(prefix).strip()
                    term_normalized = search_term.lower().removeprefix(prefix).strip()
                    
                    if not name_normalized.startswith(term_normalized):
                        logger.info(f"ARTIST REJECTED Prefix: {prefix} : Search Term: {term_normalized} : Artist: {name_normalized}")
                        rejected_artists += 1
                        continue
                
                # Build item name with genres if available
                item_name = item['name']
                try:
                    if item['genres']:
                        item_name = item['name'] + f"  |  GENRES: {'/'.join(item['genres'])}"
                except (KeyError, TypeError):
                    logger.warning("No genre tag found for %s", item['name'])               
                item_by = item['name']
                item_thumbnail_url = item['images'][-1]["url"] if item['images'] else ""
                # logger.info(f"Artist OK - artist_name is : '{item['name']}'")                
#SHOWS                
            elif item_type == "show":
                item_name = f"{config.get('explicit_label') if item['explicit'] else ''} {item['name']}"
                item_by = f"{item['publisher']}"
                item_thumbnail_url = item['images'][-1]["url"] if len(item['images']) > 0 else ""
                item_type = "podcast"
#EPISODES
            elif item_type == "episode":
                item_name = f"{config.get('explicit_label') if item['explicit'] else ''} {item['name']}"
                item_by = ""
                item_thumbnail_url = item['images'][-1]["url"] if len(item['images']) > 0 else ""
                item_type = "podcast_episode"
#AUDIOBOOKS
            elif item_type == "audiobook":
                item_name = f"{config.get('explicit_label') if item['explicit'] else ''} {item['name']}"
                item_by = f"{item['publisher']}"
                item_thumbnail_url = item['images'][-1]["url"] if len(item['images']) > 0 else ""

            search_results.append({
                'item_id': item['id'],
                'item_name': item_name,
                'item_by': item_by,
                'item_type': item_type,
                'item_service': "spotify",
                'item_url': item['external_urls']['spotify'],
                'item_thumbnail_url': item_thumbnail_url
            })
            
#REJECTION LOGGING - logs number of items rejected by filters
    rejections = {
        "Tracks": rejected_tracks,
        "Artists": rejected_artists,
        "Albums": rejected_albums,
        "Playlists": rejected_playlists
    }
    rejection_msg = ' '.join([f"{label}:{count}" for label, count in rejections.items() if count > 0])
    if rejection_msg:
        logger.info(f"TOTAL REJECTED - {rejection_msg}")
    else:
        logger.info("TOTAL REJECTED - None")
        
    return search_results


def spotify_get_track_metadata(token, item_id):
    if item_id is None:
        error_msg = f"Item ID is None, cannot fetch track metadata"
        logger.error(error_msg)
        raise Exception(error_msg)
    # Use new auth method (OAuth or librespot)
    auth_header = spotify_get_auth_header()
    if not auth_header:
        logger.error("Failed to get authentication header")
        return None

    headers = auth_header

    #Calculate number of API calls required
    api_total_calls = 1   
    if config.get('fetch_extended_album_metadata', True):
        api_total_calls += 1
    if config.get('fetch_genre_metadata', True):
        api_total_calls += 1    
    call_num = 1
    logger.info(f"[API Call {call_num}/{api_total_calls}] Fetching track data for track_id={item_id}")
    track_data = make_call(f'{BASE_URL}/tracks?ids={item_id}', headers=headers)
    time.sleep(config.get('api_request_delay', 0.1))
    call_num += 1

    # Use embedded album data (album_type, name, images, total_tracks already available)
    album_data = track_data.get('tracks', [])[0].get('album', {})

    # Only fetch full album if we need label/copyright (optional fields)
    if config.get('fetch_extended_album_metadata', True):
        album_id = track_data.get('tracks', [])[0].get('album', {}).get('id')
        logger.info(f"[API Call {call_num}/{api_total_calls}] Fetching extended album metadata for album_id={album_id}")
        full_album = make_call(f"{BASE_URL}/albums/{album_id}", headers=headers)
        time.sleep(config.get('api_request_delay', 0.1))
        call_num += 1
        album_data = full_album  # Use full data if fetched

    # Fetch artist data only if genre metadata is enabled
    artist_data = {}
    if config.get('fetch_genre_metadata', True):
        artist_id = track_data.get('tracks', [])[0].get('artists', [])[0].get('id')
        logger.info(f"[API Call {call_num}/{api_total_calls}] Fetching artist data for artist_id={artist_id}")
        artist_data = make_call(f"{BASE_URL}/artists/{artist_id}", headers=headers)
        time.sleep(config.get('api_request_delay', 0.1))
        call_num += 1

    # Fetch audio features only if enabled
    track_audio_data = ''
    '''
    if config.get('fetch_audio_features', True):
        try:
            logger.info(f"[API Call 5/6] Fetching audio features for track_id={item_id}")
            track_audio_data = make_call(f'{BASE_URL}/audio-features/{item_id}', headers=headers)
            time.sleep(config.get('api_request_delay', 0.1))
        except Exception:
            track_audio_data = ''
    '''
    # Fetch credits only if enabled
    credits_data = ''
    '''
    if config.get('fetch_track_credits', True):
        try:
            logger.info(f"[API Call 6/6] Fetching track credits for track_id={item_id}")
            credits_data = make_call(f'https://spclient.wg.spotify.com/track-credits-view/v0/experimental/{item_id}/credits', headers=headers)
        except Exception:
            credits_data = ''
    '''
    # Artists
    artists = []
    for data in track_data.get('tracks', [{}])[0].get('artists', []):
        artists.append(data.get('name'))
    artists = conv_list_format(artists)

    # Track Number - use direct value from track data
    track_number = track_data.get('tracks', [{}])[0].get('track_number')

    info = {}
    info['artists'] = artists
    info['album_name'] = track_data.get('tracks', [{}])[0].get('album', {}).get("name", '')
    info['album_type'] = album_data.get('album_type')

    # Album artists - available in both embedded and full album data
    album_artists_data = album_data.get('artists', [])
    if album_artists_data:
        info['album_artists'] = album_artists_data[0].get('name')
    else:
        # Fallback to track's first artist if album artists not available
        info['album_artists'] = track_data.get('tracks', [{}])[0].get('artists', [{}])[0].get('name', '')

    info['title'] = track_data.get('tracks', [{}])[0].get('name')

    try:
        info['image_url'] = track_data.get('tracks', [{}])[0].get('album', {}).get('images', [{}])[0].get('url')
    except IndexError:
        info['image_url'] = ''
        logger.info('Invalid thumbnail')

    info['release_year'] = track_data.get('tracks', [{}])[0].get('album', {}).get('release_date').split("-")[0]
    info['track_number'] = track_number
    info['total_tracks'] = track_data.get('tracks', [{}])[0].get('album', {}).get('total_tracks')
    info['disc_number'] = track_data.get('tracks', [{}])[0].get('disc_number')

    # Total discs - only available from full album data
    if config.get('fetch_extended_album_metadata', True) and 'tracks' in album_data:
        info['total_discs'] = sorted([trk.get('disc_number', 0) for trk in album_data.get('tracks', {}).get('items', [])])[-1]
    else:
        info['total_discs'] = 1  # Default to 1 disc if not fetching extended album data

    # Genre - only available if artist metadata was fetched
    info['genre'] = conv_list_format(artist_data.get('genres', [])) if artist_data else ''

    # Label and copyright - only available from full album data
    info['label'] = album_data.get('label', '')
    info['copyright'] = conv_list_format([holder.get('text') for holder in album_data.get('copyrights', [])])
    info['explicit'] = track_data.get('tracks', [{}])[0].get('explicit', False)
    info['isrc'] = track_data.get('tracks', [{}])[0].get('external_ids', {}).get('isrc')
    info['length'] = str(track_data.get('tracks', [{}])[0].get('duration_ms'))
    info['item_url'] = track_data.get('tracks', [{}])[0].get('external_urls', {}).get('spotify')
    #info['popularity'] = track_data.get('tracks', [{}])[0].get('popularity')
    info['item_id'] = track_data.get('tracks', [{}])[0].get('id')
    info['is_playable'] = track_data.get('tracks', [{}])[0].get('is_playable', True)

    if credits_data:
        credits = {}
        for credit_block in credits_data.get('roleCredits', []):
            role_title = credit_block.get('roleTitle').lower()
            credits[role_title] = [
                artist.get('name') for artist in credit_block.get('artists', [])
            ]
        info['performers'] = conv_list_format([item for item in credits.get('performers', []) if isinstance(item, str)])
        info['producers'] = conv_list_format([item for item in credits.get('producers', []) if isinstance(item, str)])
        info['writers'] = conv_list_format([item for item in credits.get('writers', []) if isinstance(item, str)])

    if track_audio_data:
        key_mapping = {
            0: "C",
            1: "C♯/D♭",
            2: "D",
            3: "D♯/E♭",
            4: "E",
            5: "F",
            6: "F♯/G♭",
            7: "G",
            8: "G♯/A♭",
            9: "A",
            10: "A♯/B♭",
            11: "B"
        }
        info['bpm'] = str(track_audio_data.get('tempo'))
        info['key'] = str(key_mapping.get(track_audio_data.get('key'), ''))
        info['time_signature'] = track_audio_data.get('time_signature')
        info['acousticness'] = track_audio_data.get('acousticness')
        info['danceability'] = track_audio_data.get('danceability')
        info['energy'] = track_audio_data.get('energy')
        info['instrumentalness'] = track_audio_data.get('instrumentalness')
        info['liveness'] = track_audio_data.get('liveness')
        info['loudness'] = track_audio_data.get('loudness')
        info['speechiness'] = track_audio_data.get('speechiness')
        info['valence'] = track_audio_data.get('valence')
    return info


def spotify_get_podcast_episode_metadata(token, episode_id):
    logger.info(f"Get episode info for episode by id '{episode_id}'")
    # Use new auth method (OAuth or librespot)
    auth_header = spotify_get_auth_header()
    if not auth_header:
        logger.error("Failed to get authentication header")
        return None
    headers = auth_header
    episode_data = make_call(f"{BASE_URL}/episodes/{episode_id}", headers=headers)
    show_episode_ids = spotify_get_podcast_episode_ids(token, episode_data.get('show', {}).get('id'))
    # I believe audiobook ids start with a 7 but to verify you can use https://api.spotify.com/v1/audiobooks/{id}
    # the endpoint could possibly be used to mark audiobooks in genre but it doesn't really provide any additional
    # metadata compared to show_data beyond abridged and unabridged.

    track_number = ''
    for index, episode in enumerate(show_episode_ids):
        if episode == episode_id:
            track_number = index + 1
            break

    copyrights = []
    for copyright in episode_data.get('show', {}).get('copyrights', []):
        text = copyright.get('text')
        copyrights.append(text)

    info = {}
    info['album_name'] = episode_data.get('show', {}).get('name')
    info['title'] = episode_data.get('name')
    info['image_url'] = episode_data.get('images', [{}])[0].get('url')
    info['release_year'] = episode_data.get('release_date').split('-')[0]
    info['track_number'] = track_number
    # Not accurate
    #info['total_tracks'] = episode_data.get('show', {}).get('total_episodes', 0)
    info['total_tracks'] = len(show_episode_ids)
    info['artists'] = conv_list_format([episode_data.get('show', {}).get('publisher')])
    info['album_artists'] = conv_list_format([episode_data.get('show', {}).get('publisher')])
    info['language'] = conv_list_format(episode_data.get('languages', []))
    description = episode_data.get('description')
    info['description'] = str(description if description else episode_data.get('show', {}).get('description', ""))
    info['copyright'] = conv_list_format(copyrights)
    info['length'] = str(episode_data.get('duration_ms'))
    info['explicit'] = episode_data.get('explicit')
    info['is_playable'] = episode_data.get('is_playable')
    info['item_url'] = episode_data.get('external_urls', {}).get('spotify')
    info['item_id'] = episode_data.get('id')

    return info


def spotify_get_podcast_episode_ids(token, show_id):
    logger.info(f"Getting show episodes: {show_id}'")
    episodes = []
    offset = 0
    limit = 50

    while True:
        url = f'{BASE_URL}/shows/{show_id}/episodes?offset={offset}&limit={limit}'
        # Use new auth method (OAuth or librespot)
        auth_header = spotify_get_auth_header()
        if not auth_header:
            logger.error("Failed to get authentication header")
            return []
        headers = auth_header
        resp = make_call(url, headers=headers)

        offset += limit
        episodes.extend(resp['items'])

        if resp['total'] <= offset:
            break

    item_ids = []
    for episode in episodes:
        if episode:
            item_ids.append(episode['id'])
    return item_ids
