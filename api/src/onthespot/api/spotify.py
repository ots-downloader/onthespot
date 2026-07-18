import base64
import concurrent.futures
import inspect
import json
import os
import re
import socket
import threading
import textwrap
import time
import traceback
import uuid

import requests
import librespot.zeroconf as librespot_zeroconf
from librespot.core import Session
from librespot.zeroconf import ZeroconfServer
from ..otsconfig import config, cache_dir
from ..runtimedata import (
    get_logger,
    account_pool,
    pending,
    download_queue,
    pending_lock,
)
from ..utils import make_call, conv_list_format, get_primary_composer
from ..resources.exceptions import (
    SpotifyPlaylistUnavailableError,
    SpotifyAPIUnavailableError,
)

logger = get_logger("api.spotify")
BASE_URL = "https://api.spotify.com/v1"

# Cache for the Client-Credentials OAuth token (keyed by client id + expiry so
# changing the credentials in Settings takes effect immediately).
_oauth_token_cache = {"access_token": None, "expires_at": 0, "client_id": None}
_oauth_token_lock = threading.Lock()

_session_reinit_lock = threading.Lock()
_SESSION_REINIT_TIMEOUT = 30

# Spotify Connect discovery is a long-lived service.  The old sign-in flow
# created this listener only while adding an account and then closed it once
# credentials had been captured, which meant an existing installation could
# never appear in Spotify's device picker after a restart.
_spotify_connect_server = None
_spotify_connect_lock = threading.RLock()
_SPOTIFY_CONNECT_LOGIN_FILENAME = "spotify_connect_login.json"


def _patch_librespot_zeroconf_runner() -> bool:
    """Repair shutdown support in the bundled librespot HTTP runner.

    The current librespot-python ``HttpRunner.close`` implementation is an
    empty method.  Its listening socket and non-daemon thread therefore keep
    the Python process alive after Uvicorn has completed shutdown.  Keep this
    compatibility patch narrowly version-gated so a future upstream lifecycle
    implementation takes precedence automatically.
    """
    runner_type = ZeroconfServer.HttpRunner
    if getattr(runner_type, "_onthespot_lifecycle_patch", False):
        return True

    try:
        close_source = textwrap.dedent(inspect.getsource(runner_type.close)).strip()
    except (OSError, TypeError):
        close_source = ""
    if not close_source.endswith("pass"):
        return False

    original_init = runner_type.__init__

    def patched_init(self, zeroconf_server, port):
        original_init(self, zeroconf_server, port)
        # Upstream currently stores these on the class, which would make
        # shutting down one service poison every later reconnect.  Give each
        # discovery server its own state and request pool instead.
        self._HttpRunner__should_stop = False
        self._HttpRunner__worker = concurrent.futures.ThreadPoolExecutor(
            thread_name_prefix="spotify-connect-request"
        )

    def patched_run(self):
        self._onthespot_runner_thread = threading.current_thread()
        try:
            while not self._HttpRunner__should_stop:
                try:
                    client_socket, _address = self._HttpRunner__socket.accept()
                except OSError:
                    if self._HttpRunner__should_stop:
                        break
                    raise

                def handle_client(sock=client_socket):
                    try:
                        self._HttpRunner__handle(sock)
                    except OSError:
                        if not self._HttpRunner__should_stop:
                            logger.debug(
                                "Spotify Connect request ended unexpectedly",
                                exc_info=True,
                            )
                    finally:
                        try:
                            sock.close()
                        except OSError:
                            pass

                try:
                    self._HttpRunner__worker.submit(handle_client)
                except RuntimeError:
                    # The pool can only reject work while shutdown is racing an
                    # accepted connection.  Close that connection explicitly.
                    client_socket.close()
                    if not self._HttpRunner__should_stop:
                        raise
        finally:
            self._onthespot_runner_thread = None

    def patched_close(self):
        if self._HttpRunner__should_stop:
            return
        self._HttpRunner__should_stop = True
        try:
            self._HttpRunner__socket.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        try:
            self._HttpRunner__socket.close()
        except OSError:
            pass
        self._HttpRunner__worker.shutdown(wait=True, cancel_futures=True)
        runner_thread = getattr(self, "_onthespot_runner_thread", None)
        if runner_thread is not None and runner_thread is not threading.current_thread():
            runner_thread.join(timeout=2)
            if runner_thread.is_alive():
                logger.warning("Spotify Connect listener did not stop within two seconds")

    runner_type.__init__ = patched_init
    runner_type.run = patched_run
    runner_type.close = patched_close
    runner_type._onthespot_lifecycle_patch = True
    logger.info("Applied Spotify Connect shutdown compatibility patch")
    return True


def _spotify_connect_port() -> int:
    try:
        return int(
            os.environ.get(
                "ONTHESPOT_SPOTIFY_CONNECT_PORT",
                str(config.get("spotify_connect_port", 6768) or 0),
            )
            or 0
        )
    except (TypeError, ValueError):
        return 0


def _spotify_connect_interface() -> str | None:
    """Choose the host interface Spotify clients can actually reach.

    Hostnames on machines with VPN, Hyper-V, or Tailscale adapters often
    resolve to the wrong address.  Spotify Connect needs the LAN address in
    the mDNS record.  An explicit environment value wins; otherwise the
    default-route address is selected without sending any traffic.
    """
    configured = str(os.environ.get("ONTHESPOT_SPOTIFY_CONNECT_INTERFACE", "") or "").strip()
    if configured:
        return configured

    # Prefer a normal home/LAN address when one is available.  This avoids
    # advertising a Hyper-V, VPN, or Tailscale address on Windows while still
    # leaving ONTHESPOT_SPOTIFY_CONNECT_INTERFACE available for multi-NIC
    # servers.
    try:
        candidates = socket.gethostbyname_ex(socket.gethostname())[2]
        lan_candidates = [
            address
            for address in candidates
            if address.startswith("192.168.") and not address.startswith("192.168.56.")
        ]
        if lan_candidates:
            return lan_candidates[0]
    except OSError:
        pass

    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.connect(("8.8.8.8", 80))
        return probe.getsockname()[0]
    except OSError:
        return None
    finally:
        probe.close()


def _spotify_connect_login_path() -> str:
    sessions_dir = os.path.join(cache_dir(), "sessions")
    os.makedirs(sessions_dir, exist_ok=True)
    return os.path.join(sessions_dir, _SPOTIFY_CONNECT_LOGIN_FILENAME)


def start_spotify_connect_service():
    """Start the persistent Spotify Connect discovery/login service.

    Spotify's device picker discovers OnTheSpot through mDNS, so this must run
    for the lifetime of the API process.  It deliberately does not replace
    the account-pool sessions used for downloading; it only provides the local
    Connect pairing endpoint and can be reused when a new account is added.
    """
    global _spotify_connect_server

    with _spotify_connect_lock:
        if _spotify_connect_server is not None:
            return _spotify_connect_server

        _patch_librespot_zeroconf_runner()
        client_id = "65b708073fc0480ea92a077233ca87bd"
        ZeroconfServer._ZeroconfServer__default_get_info_fields["clientID"] = client_id
        builder = ZeroconfServer.Builder()
        builder.device_name = "OnTheSpot"
        port = _spotify_connect_port()
        if port > 0:
            builder.set_listen_port(port)
        builder.conf.stored_credentials_file = _spotify_connect_login_path()

        interface = _spotify_connect_interface()
        original_zeroconf = librespot_zeroconf.zeroconf.Zeroconf
        original_hostname = ZeroconfServer.get_useful_hostname

        # librespot-python currently constructs Zeroconf without an interface
        # argument and advertises the system hostname.  Scope these two small
        # overrides to creation so VPN/virtual adapters cannot make mDNS
        # registration time out or publish an unreachable address.
        if interface:
            librespot_zeroconf.zeroconf.Zeroconf = lambda *args, **kwargs: original_zeroconf(
                *args, interfaces=[interface], **kwargs
            )
            ZeroconfServer.get_useful_hostname = lambda self: interface

        try:
            _spotify_connect_server = builder.create()
        except Exception:
            logger.exception(
                "Could not start Spotify Connect discovery service on port %s",
                port or "auto",
            )
            _spotify_connect_server = None
            return None
        finally:
            librespot_zeroconf.zeroconf.Zeroconf = original_zeroconf
            ZeroconfServer.get_useful_hostname = original_hostname

        logger.info(
            "Spotify Connect discovery service started as OnTheSpot%s%s",
            f" on port {port}" if port > 0 else "",
            f" on {interface}" if interface else "",
        )
        return _spotify_connect_server


def stop_spotify_connect_service() -> None:
    """Stop the persistent Spotify Connect service during API shutdown."""
    global _spotify_connect_server

    with _spotify_connect_lock:
        server = _spotify_connect_server
        _spotify_connect_server = None
        if server is None:
            return
        try:
            server.close_session()
        except Exception:
            logger.debug("Spotify Connect session was already closed", exc_info=True)
        try:
            server.close()
        except Exception:
            logger.debug("Spotify Connect discovery service close failed", exc_info=True)


def spotify_connect_status() -> dict:
    """Return safe discovery-service status for diagnostics/UI health checks."""
    with _spotify_connect_lock:
        return {
            "running": _spotify_connect_server is not None,
            "device_name": "OnTheSpot",
            "port": _spotify_connect_port(),
        }


def add_spotify_zeroconf_login(zeroconf_login: dict, account_uuid: str | None = None) -> bool:
    """Persist a Spotify Connect login received locally or from a companion.

    The companion only forwards the same three fields produced by librespot's
    ZeroConf login file.  Keep the validation and duplicate handling in one
    place so local and remote sign-in create identical account records.
    """
    if not isinstance(zeroconf_login, dict):
        return False
    username = str(zeroconf_login.get("username") or "").strip()
    credentials = zeroconf_login.get("credentials")
    credential_type = str(zeroconf_login.get("type") or "").strip()
    if not username or not isinstance(credentials, str) or not credentials or not credential_type:
        return False
    if any(
        isinstance(account, dict)
        and account.get("service") == "spotify"
        and account.get("login", {}).get("username") == username
        for account in (config.get("accounts", []) or [])
    ):
        logger.info("Spotify account already exists")
        return False

    cfg_copy = list(config.get("accounts", []) or [])
    cfg_copy.append(
        {
            "uuid": account_uuid or str(uuid.uuid4()),
            "service": "spotify",
            "active": True,
            "login": {
                "username": username,
                "credentials": credentials,
                "type": credential_type,
            },
        }
    )
    config.set("accounts", cfg_copy)
    config.save()
    logger.info("New Spotify account added to config for %s", username[:4] + "****")
    return True


def spotify_get_oauth_token():
    """Return an OAuth access token via the Client-Credentials flow using the
    user's own Spotify app credentials, or None if they aren't configured.

    The default librespot token rides on Spotify's shared first-party client id,
    which is now hard rate-limited (HTTP 429). Supplying your own client id/secret
    gives Web API calls their own quota. Catalog endpoints only - this token has
    no user context, so it can't read /me/* (liked songs, your episodes)."""
    # str() guards against the CLI / web settings coercing an all-digit value to int.
    client_id = str(config.get("spotify_webapi_override_client_id", "") or "").strip()
    client_secret = str(
        config.get("spotify_webapi_override_client_secret", "") or ""
    ).strip()
    if not client_id or not client_secret:
        return None

    with _oauth_token_lock:
        if (
            _oauth_token_cache["access_token"]
            and _oauth_token_cache["client_id"] == client_id
            and time.time() < _oauth_token_cache["expires_at"]
        ):
            return _oauth_token_cache["access_token"]

        credentials_b64 = base64.b64encode(
            f"{client_id}:{client_secret}".encode()
        ).decode()
        try:
            resp = requests.post(
                "https://accounts.spotify.com/api/token",
                headers={
                    "Authorization": f"Basic {credentials_b64}",
                    "Content-Type": "application/x-www-form-urlencoded",
                },
                data={"grant_type": "client_credentials"},
                timeout=15,
            )
        except requests.exceptions.RequestException as e:
            logger.error("[OAUTH] Token request failed: %s", str(e))
            return None
        if resp.status_code != 200:
            logger.error(
                "Failed to get access token: %d - %s", resp.status_code, resp.text
            )
            return None
        try:
            data = resp.json()
            access_token = data["access_token"]
            expires_in = data.get("expires_in", 3600)
        except (ValueError, KeyError) as e:
            logger.error("[OAUTH] Malformed token response: %s", str(e))
            return None
        _oauth_token_cache["access_token"] = access_token
        _oauth_token_cache["client_id"] = client_id
        # Refresh a little early (5 min buffer) to avoid mid-call expiry.
        _oauth_token_cache["expires_at"] = time.time() + expires_in - 300
        logger.info(
            "[AUTH] Using Web API override credentials (OAuth) for Spotify metadata/search"
        )
        return _oauth_token_cache["access_token"]


def spotify_get_auth_header(token=None):
    """Authorization header for public Spotify Web API (api.spotify.com) calls.

    Prefers the user's OAuth override token when configured (avoids the shared
    librespot client's 429 rate limit); otherwise falls back to the librespot
    session token passed in by the caller."""
    oauth = spotify_get_oauth_token()
    if oauth:
        return {"Authorization": f"Bearer {oauth}"}
    if token is not None:
        return {"Authorization": f"Bearer {token.tokens().get('user-read-email')}"}
    return None


def spotify_playlist_call(token, url):
    """Fetch a playlist endpoint, preferring the OAuth override. Client-credentials
    OAuth can't see private/collaborative playlists (HTTP 404 -> None), so on a
    permanent failure retry once with the user-scoped librespot token."""
    headers = spotify_get_auth_header(token)
    try:
        resp = make_call(url, headers=headers, skip_cache=True)
    except requests.exceptions.RequestException:
        resp = None
    if not resp and token is not None:
        librespot_headers = {
            "Authorization": f"Bearer {token.tokens().get('user-read-email')}"
        }
        if librespot_headers != headers:
            try:
                resp = make_call(url, headers=librespot_headers, skip_cache=True)
            except requests.exceptions.RequestException:
                resp = None
    return resp


class MirrorSpotifyPlayback:
    def __init__(self):
        self.thread: threading.Thread | None = None
        self.is_running = False
        self._stop_event = threading.Event()
        self._lock = threading.Lock()

    def start(self):
        with self._lock:
            if self.thread is not None and self.thread.is_alive():
                logger.debug("SpotifyMirrorPlayback is already running.")
                return
            logger.info("Starting SpotifyMirrorPlayback")
            self._stop_event.clear()
            self.is_running = True
            self.thread = threading.Thread(
                target=self.run,
                name="spotify-playback-mirror",
                daemon=True,
            )
            self.thread.start()

    def stop(self, timeout: float = 15.0):
        with self._lock:
            thread = self.thread
            if thread is None:
                self.is_running = False
                return
            logger.info("Stopping SpotifyMirrorPlayback")
            self.is_running = False
            self._stop_event.set()
        thread.join(timeout=timeout)
        with self._lock:
            if thread.is_alive():
                logger.warning("SpotifyMirrorPlayback did not stop within %.1f seconds", timeout)
            elif self.thread is thread:
                self.thread = None

    def run(self):
        get_account_token = spotify_get_token
        while not self._stop_event.wait(5):
            try:
                token = get_account_token("spotify").tokens()
            except (AttributeError, IndexError, KeyError, TypeError):
                # Account pool hasn't been filled yet
                continue
            url = f"{BASE_URL}/me/player/currently-playing"
            try:
                resp = requests.get(
                    url,
                    headers={
                        "Authorization": f"Bearer {token.get('user-read-currently-playing')}"
                    },
                    timeout=10,
                )
            except requests.RequestException:
                logger.info("Session Expired, reinitializing...")
                parsing_index = config.get("active_account_number")
                try:
                    spotify_re_init_session(account_pool[parsing_index])
                except (IndexError, KeyError, TypeError):
                    logger.debug("No Spotify account is available to refresh mirroring")
                continue
            if resp.status_code == 200:
                try:
                    data = resp.json()
                    item = data.get("item") or {}
                except (ValueError, TypeError):
                    logger.debug("Spotify returned an invalid playback response")
                    continue
                if data.get("currently_playing_type") == "track" and item.get("id"):
                    item_id = item["id"]
                    if item_id not in pending and item_id not in download_queue:
                        parent_category = "track"
                        playlist_name = ""
                        playlist_by = ""
                        if data["context"] is not None:
                            if data["context"].get("type") == "playlist":
                                match = re.search(
                                    r"spotify:playlist:(\w+)", data["context"]["uri"]
                                )
                                if match:
                                    playlist_id = match.group(1)
                                else:
                                    continue
                                token = get_account_token("spotify")
                                playlist_name, playlist_by = spotify_get_playlist_data(
                                    token, playlist_id
                                )
                                parent_category = "playlist"
                            elif data["context"].get("type") == "collection":
                                playlist_name = "Liked Songs"
                                playlist_by = "me"
                                parent_category = "playlist"
                            elif data["context"].get("type") in ("album", "artist"):
                                parent_category = "album"
                        # Use item id to prevent duplicates
                        # local_id = format_local_id(item_id)
                        with pending_lock:
                            pending.put_nowait(
                                item={
                                    "local_id": item_id,
                                    "item_service": "spotify",
                                    "item_type": "track",
                                    "item_id": item_id,
                                    "parent_category": parent_category,
                                    "playlist_name": playlist_name,
                                    "playlist_by": playlist_by,
                                    "playlist_number": "?",
                                }
                            )
                        logger.info(
                            "Mirror Spotify Playback added track to download queue: https://open.spotify.com/track/%s",
                            item_id,
                        )
                        continue
                else:
                    logger.info(
                        "Spotify API does not return enough data to parse currently playing episodes."
                    )
                    continue
            else:
                continue
        self.is_running = False


def spotify_new_session():
    os.makedirs(os.path.join(cache_dir(), "sessions"), exist_ok=True)

    uuid_uniq = str(uuid.uuid4())
    session_json_path = _spotify_connect_login_path()
    zs = start_spotify_connect_service()
    if zs is None:
        return False

    # A previous device selection may have left a valid Connect session on the
    # discovery service.  Clear it so this sign-in attempt waits for a new
    # account rather than treating the old selection as fresh credentials.
    if zs.has_valid_session():
        zs.close_session()
    try:
        os.remove(session_json_path)
    except FileNotFoundError:
        pass

    while True:
        time.sleep(1)
        if zs.has_valid_session():
            logger.info(
                "Grabbed %s for %s",
                zs._ZeroconfServer__session,
                zs._ZeroconfServer__session.username(),
            )
            try:
                with open(session_json_path, "r", encoding="utf-8") as file:
                    zeroconf_login = json.load(file)
            except FileNotFoundError as e:
                logger.error(
                    "Error: %s The file %s was not found.\nTraceback: %s",
                    str(e),
                    session_json_path,
                    traceback.format_exc(),
                )
                return False
            except json.JSONDecodeError as e:
                logger.error(
                    "Error: %s Failed to decode JSON from the file.\nTraceback: %s",
                    str(e),
                    traceback.format_exc(),
                )
                return False
            except Exception as e:
                logger.error(
                    "Unknown Error: %s\nTraceback: %s", str(e), traceback.format_exc()
                )
                return False
            # Keep the discovery service alive after pairing.  Closing the
            # whole server here was the reason Spotify stopped showing
            # OnTheSpot after the first login.
            zs.close_session()
            return add_spotify_zeroconf_login(zeroconf_login, account_uuid=uuid_uniq)


def spotify_login_user(account):
    try:
        # I'd prefer to use 'Session.Builder().stored(credentials).create but
        # I can't get it to work, loading from credentials file instead.
        luuid = account["uuid"]
        username = account["login"]["username"]

        session_dir = os.path.join(cache_dir(), "sessions")
        os.makedirs(session_dir, exist_ok=True)
        session_json_path = os.path.join(session_dir, f"ots_login_{luuid}.json")
        try:
            with open(session_json_path, "w", encoding="utf-8") as file:
                json.dump(account["login"], file)
            logger.info(
                "Login information for %s written to %s",
                username[:4] + "****" if username else "",
                session_json_path,
            )
        except IOError as e:
            logger.error(
                "Error writing to file %s: %s\nTraceback: %s",
                session_json_path,
                str(e),
                traceback.format_exc(),
            )

        lconfig = (
            Session.Configuration.Builder()
            .set_stored_credential_file(session_json_path)
            .build()
        )
        # For some reason initialising session as None prevents premature application exit
        session = None
        try:
            session = (
                Session.Builder(conf=lconfig).stored_file(session_json_path).create()
            )
        except Exception:
            time.sleep(3)
            session = (
                Session.Builder(conf=lconfig).stored_file(session_json_path).create()
            )
        logger.debug("Session created")
        logger.info(
            "Login successful for user '%s'", username[:4] + "****" if username else ""
        )
        account_type = session.get_user_attribute("type")
        bitrate = "160k"
        if account_type == "premium":
            bitrate = "320k"
        account_pool.append(
            {
                "uuid": luuid,
                "username": username,
                "service": "spotify",
                "status": "active",
                "account_type": account_type,
                "bitrate": bitrate,
                "login": {
                    "session": session,
                    "session_path": session_json_path,
                },
            }
        )
        return True
    except Exception as e:
        logger.error(
            "Unknown Exception: %s\nTraceback: %s", str(e), traceback.format_exc()
        )
        account_pool.append(
            {
                "uuid": luuid,
                "username": username,
                "service": "spotify",
                "status": "error",
                "account_type": "N/A",
                "bitrate": "N/A",
                "login": {
                    "session": "",
                    "session_path": "",
                },
            }
        )
        return False


def spotify_re_init_session(account, dead_session=None):
    session_json_path = os.path.join(
        cache_dir(), "sessions", f"ots_login_{account['uuid']}.json"
    )
    with _session_reinit_lock:
        old_session = account.get("login", {}).get("session")
        if dead_session is not None and old_session is not dead_session:
            return
        if old_session:
            try:
                old_session.close()
            except Exception as e:
                logger.debug("Failed to close old session: %s", str(e))
            account["login"]["session"] = ""
        result = {}

        def _build():
            try:
                cfg = (
                    Session.Configuration.Builder()
                    .set_stored_credential_file(session_json_path)
                    .build()
                )
                session = (
                    Session.Builder(conf=cfg).stored_file(session_json_path).create()
                )
                result["session"] = session
                result["account_type"] = session.get_user_attribute("type")
            except Exception as e:
                result["error"] = e

        builder = threading.Thread(target=_build, daemon=True)
        builder.start()
        builder.join(timeout=_SESSION_REINIT_TIMEOUT)
        if builder.is_alive():
            logger.error(
                "Session re-init timed out, network may be unavailable. Will retry later."
            )
            return
        session = result.get("session")
        if session is None:
            logger.error("Failed to re init session! %s", str(result.get("error")))
            return
        logger.debug("Session re init done")
        account_type = result["account_type"]
        account["login"]["session_path"] = session_json_path
        account["login"]["session"] = session
        account["status"] = "active"
        account["account_type"] = account_type
        account["bitrate"] = "320k" if account_type == "premium" else "160k"


def reinit_spotify_session(token):

    for account in account_pool:
        if (
            account.get("service") == "spotify"
            and account.get("login", {}).get("session") is token
        ):
            logger.info("Spotify session connection lost, re-initializing...")
            spotify_re_init_session(account, dead_session=token)
            return


def spotify_get_token(parsing_index):
    try:
        token = account_pool[parsing_index]["login"]["session"]
    except (OSError, AttributeError, KeyError):
        token = None
    if not token or isinstance(token, str):
        logger.info(
            "No valid session for %s, attempting to reinit session.",
            account_pool[parsing_index]["username"],
        )
        spotify_re_init_session(account_pool[parsing_index])
        token = account_pool[parsing_index]["login"]["session"]
    return token


def spotify_get_artist_album_ids(token, artist_id):
    logger.info("Getting album ids for artist: %s", artist_id)
    items = []
    offset = 0
    limit = 50
    while True:
        headers = spotify_get_auth_header(token)

        url = f"{BASE_URL}/artists/{artist_id}/albums?include_groups=album%2Csingle&limit={limit}&offset={offset}"  # %2Cappears_on%2Ccompilation
        artist_data = make_call(url, headers=headers)

        offset += limit
        items.extend(artist_data["items"])

        if artist_data["total"] <= offset:
            break

    item_ids = []
    for album in items:
        item_ids.append(album["id"])
    return item_ids


def spotify_get_playlist_data(token, playlist_id):
    logger.info("Get playlist data for playlist: %s", playlist_id)
    resp = spotify_playlist_call(token, f"{BASE_URL}/playlists/{playlist_id}")
    if not resp:
        raise SpotifyPlaylistUnavailableError(
            f"Failed to fetch playlist data for '{playlist_id}'"
        )
    return resp["name"], resp["owner"]["display_name"]


def spotify_get_lyrics(token, item_id, item_type, metadata, filepath):
    if config.get("download_lyrics"):
        lyrics = []
        try:
            if item_type == "track":
                url = f"https://spclient.wg.spotify.com/color-lyrics/v2/track/{item_id}?format=json&market=from_token"
            elif item_type == "episode":
                url = f"https://spclient.wg.spotify.com/transcript-read-along/v2/episode/{item_id}?format=json&market=from_token"
            else:
                url = None
            headers = {}
            headers["app-platform"] = "WebPlayer"
            headers["Authorization"] = f"Bearer {token.tokens().get('user-read-email')}"
            headers["user-agent"] = (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/77.0.3865.90 Safari/537.36"
            )
            if url is None:
                logger.error("No lyrics URL for %s: %s", item_type, item_id)
                return None
            resp = make_call(url, headers=headers)
            if resp is None:
                logger.info("Failed to find lyrics for %s: %s", item_type, item_id)
                return None

            if not config.get("only_download_plain_lyrics"):
                if config.get("embed_branding"):
                    lyrics.append("[re:OnTheSpot]")

                for key in metadata.keys():
                    value = metadata[key]
                    if key in ["title", "track_title", "tracktitle"] and config.get(
                        "embed_name"
                    ):
                        title = value
                        lyrics.append(f"[ti:{title}]")
                    elif key == "artists" and config.get("embed_artist"):
                        artist = value
                        lyrics.append(f"[ar:{artist}]")
                    elif key in ["album_name", "album"] and config.get("embed_album"):
                        album = value
                        lyrics.append(f"[al:{album}]")
                    elif key in ["writers"] and config.get("embed_writers"):
                        author = value
                        lyrics.append(f"[au:{author}]")

                if item_type == "track":
                    lyrics.append(f"[by:{resp['lyrics']['provider']}]")

                if config.get("embed_length"):
                    l_ms = int(metadata["length"])
                    if round((l_ms / 1000) / 60) < 10:
                        digit = "0"
                    else:
                        digit = ""
                    lyrics.append(
                        f"[length:{digit}{round((l_ms / 1000) / 60)}:{round((l_ms / 1000) % 60)}]\n"
                    )

            default_length = len(lyrics)

            if item_type == "track":
                if resp["lyrics"]["syncType"] == "LINE_SYNCED":
                    for line in resp["lyrics"]["lines"]:
                        minutes, seconds = divmod(int(line["startTimeMs"]) / 1000, 60)
                        if not config.get("only_download_plain_lyrics"):
                            lyrics.append(
                                f"[{minutes:0>2.0f}:{seconds:05.2f}] {line['words']}"
                            )
                        else:
                            lyrics.append(line["words"])
                elif resp["lyrics"]["syncType"] == "UNSYNCED" and not config.get(
                    "only_download_synced_lyrics"
                ):
                    lyrics = [line["words"] for line in resp["lyrics"]["lines"]]

            elif item_type == "episode":
                if resp["timeSyncedStatus"] == "SYLLABLE_SYNCED":
                    for line in resp["section"]:
                        try:
                            minutes, seconds = divmod(int(line["startMs"]) / 1000, 60)
                            lyrics.append(
                                f"[{minutes:0>2.0f}:{seconds:05.2f}] {line['text']['sentence']['text']}"
                            )
                        except KeyError as e:
                            logger.debug("Invalid line: %s", str(e))
                else:
                    logger.info("Unsynced episode lyrics, please open a bug report.")

        except requests.exceptions.RequestException as e:
            # Lyrics are optional - a 404 (or any request error) just means no
            # lyrics are available, so log it and continue the download without them.
            logger.info("No lyrics available for %s %s: %s", item_type, item_id, str(e))
            return None
        except (KeyError, IndexError) as e:
            logger.error(
                "Failed to get lyrics for %s: %s\nTraceback: %s",
                item_id,
                str(e),
                traceback.format_exc(),
            )

        merged_lyrics = "\n".join(lyrics)

        if lyrics:
            logger.debug(lyrics)
            if len(lyrics) <= default_length:
                return False
            if config.get("save_lrc_file"):
                with open(filepath + ".lrc", "w", encoding="utf-8") as f:
                    f.write(merged_lyrics)
            if config.get("embed_lyrics"):
                if item_type == "track":
                    return {
                        "lyrics": merged_lyrics,
                        "language": resp["lyrics"]["language"],
                    }
                if item_type == "episode":
                    return {"lyrics": merged_lyrics}
            else:
                return True
    else:
        return False


def spotify_get_playlist_items(token, playlist_id):
    logger.info("Getting items in playlist: %s", playlist_id)
    items = []
    offset = 0
    limit = 100

    while True:
        url = f"{BASE_URL}/playlists/{playlist_id}/tracks?additional_types=track%2Cepisode&offset={offset}&limit={limit}"
        resp = spotify_playlist_call(token, url)
        if not resp:
            raise Exception(f"Failed to fetch playlist items for '{playlist_id}'")

        offset += limit
        items.extend(resp["items"])

        if resp["total"] <= offset:
            break
    return items


def spotify_get_liked_songs(token):
    logger.info("Getting liked songs")
    items = []
    offset = 0
    limit = 50

    while True:
        url = f"{BASE_URL}/me/tracks?offset={offset}&limit={limit}"
        headers = {}
        headers["Authorization"] = f"Bearer {token.tokens().get('user-library-read')}"

        resp = make_call(url, headers=headers, skip_cache=True)

        offset += limit
        items.extend(resp["items"])

        if resp["total"] <= offset:
            break
    return items


def spotify_get_your_episodes(token):
    logger.info("Getting your episodes")
    items = []
    offset = 0
    limit = 50

    while True:
        headers = {}
        headers["Authorization"] = f"Bearer {token.tokens().get('user-library-read')}"
        url = f"{BASE_URL}/me/episodes?offset={offset}&limit={limit}"

        resp = make_call(url, headers=headers, skip_cache=True)

        offset += limit
        items.extend(resp["items"])

        if resp["total"] <= offset:
            break
    return items


def spotify_get_album_track_ids(token, album_id):
    logger.info("Getting tracks from album: %s", album_id)
    tracks = []
    offset = 0
    limit = 50

    while True:
        url = f"{BASE_URL}/albums/{album_id}/tracks?offset={offset}&limit={limit}"
        headers = spotify_get_auth_header(token)
        resp = make_call(url, headers=headers)

        offset += limit
        tracks.extend(resp["items"])

        if resp["total"] <= offset:
            break

    item_ids = []
    for track in tracks:
        if track:
            item_ids.append(track["id"])
    return item_ids


def spotify_get_search_results(
    token,
    search_term,
    content_types,
    filter_tracks=True,
    filter_albums=True,
    filter_artists=True,
    filter_playlists=True,
    search_prefix="",
):
    logger.info("Get search result for term '%s'", search_term)

    headers = spotify_get_auth_header(token)

    params = {}
    params["limit"] = config.get("max_search_results")
    params["offset"] = "0"
    params["q"] = search_term
    # Changed params[] expression below - it does not need transform!
    params["type"] = ",".join(content_types)

    # Route through make_call so search shares the central 429/Retry-After/backoff
    # and per-host serialisation. It raises on exhausted retries and returns None
    # on a permanent error; treat both as "no results" rather than crashing.
    try:
        data = make_call(
            f"{BASE_URL}/search", params=params, headers=headers
        )
    except requests.exceptions.RequestException as e:
        logger.error("Spotify search failed for '%s': %s", search_term, str(e))
        return []

    # None/non-dict (permanent error) or an API error payload (e.g. {'error': ...}).
    if not isinstance(data, dict) or "error" in data:
        logger.error(
            "Spotify search did not return results for '%s': %s", search_term, str(data)
        )
        return []

    search_results = []
    for key, section in data.items():
        if not isinstance(section, dict):
            continue
        for item in section.get("items", []) or []:
            if not item:
                continue
            item_type = item.get("type")
            if not item_type:
                continue
            # Field shapes differ between librespot and OAuth tokens (e.g. OAuth
            # omits 'genres' on artists and 'publisher' on shows/audiobooks), so
            # access every field defensively and skip any single malformed item
            # rather than letting it blank out the whole result set.
            try:
                explicit = config.get("explicit_label") if item.get("explicit") else ""
                images = item.get("images") or []
                if item_type == "track":
                    item_name = f"{explicit} {item['name']}"
                    item_by = config.get("metadata_separator").join(
                        [a.get("name", "") for a in item.get("artists", [])]
                    )
                    album_images = (item.get("album") or {}).get("images") or []
                    item_thumbnail_url = album_images[-1]["url"] if album_images else ""
                elif item_type == "album":
                    rel_match = re.search(
                        r"(\d{4})", item.get("release_date", "") or ""
                    )
                    rel_year = rel_match.group(1) if rel_match else "?"
                    item_name = f"[Y:{rel_year}] [T:{item.get('total_tracks', '?')}] {item['name']}"
                    item_by = config.get("metadata_separator").join(
                        [a.get("name", "") for a in item.get("artists", [])]
                    )
                    item_thumbnail_url = images[-1]["url"] if images else ""
                elif item_type == "playlist":
                    item_name = f"{item['name']}"
                    item_by = (item.get("owner") or {}).get("display_name", "")
                    item_thumbnail_url = images[-1]["url"] if images else ""
                elif item_type == "artist":
                    item_name = item["name"]
                    # 'genres' is present with librespot tokens but omitted under
                    # the OAuth override, so treat it as optional.
                    genres = item.get("genres") or []
                    if genres:
                        item_name = item["name"] + f"  |  GENRES: {'/'.join(genres)}"
                    item_by = item["name"]
                    item_thumbnail_url = images[-1]["url"] if images else ""
                elif item_type == "show":
                    item_name = f"{explicit} {item['name']}"
                    item_by = item.get("publisher", "")
                    item_thumbnail_url = images[-1]["url"] if images else ""
                    item_type = "podcast"
                elif item_type == "episode":
                    item_name = f"{explicit} {item['name']}"
                    item_by = ""
                    item_thumbnail_url = images[-1]["url"] if images else ""
                    item_type = "podcast_episode"
                elif item_type == "audiobook":
                    item_name = f"{explicit} {item['name']}"
                    item_by = item.get("publisher", "")
                    item_thumbnail_url = images[-1]["url"] if images else ""
                else:
                    continue

                search_results.append(
                    {
                        "item_id": item["id"],
                        "item_name": item_name,
                        "item_by": item_by,
                        "item_type": item_type,
                        "item_service": "spotify",
                        "item_url": item.get("external_urls", {}).get("spotify", ""),
                        "item_thumbnail_url": item_thumbnail_url,
                    }
                )
            except (KeyError, IndexError, TypeError) as e:
                logger.warning(
                    "Skipping malformed '%s' search result: %s", item_type, str(e)
                )
                continue
    return search_results


def spotify_get_track_metadata(token, item_id):
    # Public catalog calls (api.spotify.com) use the OAuth override when
    # configured, else the librespot token. The internal spclient.wg endpoint
    # (credits) only accepts the librespot token, so keep a separate header.
    # Calculate number of API calls required
    api_total_calls = 1
    if config.get("fetch_extended_album_metadata", True):
        api_total_calls += 1
    if config.get("fetch_genre_metadata", True):
        api_total_calls += 1
    call_num = 1
    logger.info(
        "Fetching track data for track_id=%s (Call %d/%d)",
        item_id,
        call_num,
        api_total_calls,
    )

    headers = spotify_get_auth_header(token)
    librespot_headers = {
        "Authorization": f"Bearer {token.tokens().get('user-read-email')}"
    }

    delay = config.get("api_request_delay", 0.1)

    # Use the single-track endpoint /tracks/{id}. The multi-get /tracks?ids= is
    # removed for dev-mode (OAuth) apps and returns 403. Wrap the single object
    # so the parsing below (which expects {'tracks': [..]}) stays unchanged.
    track = make_call(f"{BASE_URL}/tracks/{item_id}", headers=headers)
    # A None result means a permanent (non-retryable) error such as 401/403/404.
    # Bail out with a clear message rather than crashing on track_data.get(...).
    if not track or not track.get("id"):
        raise SpotifyAPIUnavailableError(
            f"No track data returned for '{item_id}' (rate limited or unavailable)"
        )
    track_data = {"tracks": [track]}
    time.sleep(delay)

    # The album and artist lookups only enrich the metadata (label, copyright,
    # total discs, genre). If they fail - None on a permanent error, or a raise
    # on exhausted retries - fall back to the data embedded in the track response
    # so the track is still downloadable.
    if config.get("fetch_extended_album_metadata", True):
        try:
            album_data = (
                make_call(
                    f"{BASE_URL}/albums/{track_data.get('tracks', [])[0].get('album', {}).get('id')}",
                    headers=headers,
                )
                or {}
            )
        except Exception:
            album_data = {}
    else:
        album_data = {}
    time.sleep(delay)
    if config.get("fetch_genre_metadata", True):
        try:
            artist_data = (
                make_call(
                    f"{BASE_URL}/artists/{track_data.get('tracks', [])[0].get('artists', [])[0].get('id')}",
                    headers=headers,
                )
                or {}
            )
        except Exception:
            artist_data = {}
    else:
        artist_data = {}
    time.sleep(delay)
    if config.get("fetch_audio_features", True):
        try:
            track_audio_data = make_call(
                f"{BASE_URL}/audio-features/{item_id}", headers=headers
            )
            time.sleep(delay)
        except Exception:
            track_audio_data = ""
    else:
        track_audio_data = ""
    if config.get("fetch_track_credits", True):
        try:
            credits_data = make_call(
                f"https://spclient.wg.spotify.com/track-credits-view/v0/experimental/{item_id}/credits",
                headers=librespot_headers,
            )
        except Exception:
            credits_data = ""
    else:
        credits_data = ""

    time.sleep(config.get("api_request_delay", 0.1))
    call_num += 1

    # Use embedded album data (album_type, name, images, total_tracks already available)

    album_data = track_data.get("tracks", [])[0].get("album", {})

    # Artists
    artists = []
    for data in track_data.get("tracks", [{}])[0].get("artists", []):
        artists.append(data.get("name"))
    artists = conv_list_format(artists)

    # Track Number - use direct value from track data
    track_number = track_data.get("tracks", [{}])[0].get("track_number")

    info = {}
    info["artists"] = artists
    info["album_name"] = (
        track_data.get("tracks", [{}])[0].get("album", {}).get("name", "")
    )
    info["album_type"] = album_data.get("album_type")

    # Album artists - available in both embedded and full album data
    album_artists_data = album_data.get("artists", [])
    if album_artists_data:
        info["album_artists"] = album_artists_data[0].get("name")
    else:
        # Fallback to track's first artist if album artists not available
        info["album_artists"] = (
            track_data.get("tracks", [{}])[0].get("artists", [{}])[0].get("name", "")
        )

    info["title"] = track_data.get("tracks", [{}])[0].get("name")

    try:
        info["image_url"] = (
            track_data.get("tracks", [{}])[0]
            .get("album", {})
            .get("images", [{}])[0]
            .get("url")
        )
    except IndexError:
        info["image_url"] = ""
        logger.info("Invalid thumbnail")

    info["release_year"] = (
        track_data.get("tracks", [{}])[0]
        .get("album", {})
        .get("release_date")
        .split("-")[0]
    )
    info["track_number"] = track_number
    info["total_tracks"] = (
        track_data.get("tracks", [{}])[0].get("album", {}).get("total_tracks")
    )
    info["disc_number"] = track_data.get("tracks", [{}])[0].get("disc_number")

    # Total discs - only available from full album data
    if config.get("fetch_extended_album_metadata", True) and "tracks" in album_data:
        info["total_discs"] = sorted(
            [
                trk.get("disc_number", 0)
                for trk in album_data.get("tracks", {}).get("items", [])
            ]
        )[-1]
    else:
        info["total_discs"] = 1  # Default to 1 disc if not fetching extended album data

    # Genre - only available if artist metadata was fetched
    info["genre"] = (
        conv_list_format(artist_data.get("genres", [])) if artist_data else ""
    )

    # Label and copyright - only available from full album data
    info["label"] = album_data.get("label", "")
    info["copyright"] = conv_list_format(
        [holder.get("text") for holder in album_data.get("copyrights", [])]
    )
    info["explicit"] = track_data.get("tracks", [{}])[0].get("explicit", False)
    info["isrc"] = track_data.get("tracks", [{}])[0].get("external_ids", {}).get("isrc")
    info["length"] = str(track_data.get("tracks", [{}])[0].get("duration_ms"))
    info["item_url"] = (
        track_data.get("tracks", [{}])[0].get("external_urls", {}).get("spotify")
    )
    # info['popularity'] = track_data.get('tracks', [{}])[0].get('popularity')
    info["item_id"] = track_data.get("tracks", [{}])[0].get("id")
    info["is_playable"] = track_data.get("tracks", [{}])[0].get("is_playable", True)

    if credits_data:
        local_credits = {}
        for credit_block in credits_data.get("roleCredits", []):
            role_title = credit_block.get("roleTitle").lower()
            local_credits[role_title] = [
                artist.get("name") for artist in credit_block.get("artists", [])
            ]
        info["performers"] = conv_list_format(
            [
                item
                for item in local_credits.get("performers", [])
                if isinstance(item, str)
            ]
        )
        info["producers"] = conv_list_format(
            [
                item
                for item in local_credits.get("producers", [])
                if isinstance(item, str)
            ]
        )
        info["writers"] = conv_list_format(
            [item for item in local_credits.get("writers", []) if isinstance(item, str)]
        )
        info["composer"] = info["writers"]
        if config.get("prefer_composer_as_album_artist") and info["composer"]:
            info["album_artists"] = get_primary_composer(info["composer"])

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
            11: "B",
        }
        info["bpm"] = str(track_audio_data.get("tempo"))
        info["key"] = str(key_mapping.get(track_audio_data.get("key"), ""))
        info["time_signature"] = track_audio_data.get("time_signature")
        info["acousticness"] = track_audio_data.get("acousticness")
        info["danceability"] = track_audio_data.get("danceability")
        info["energy"] = track_audio_data.get("energy")
        info["instrumentalness"] = track_audio_data.get("instrumentalness")
        info["liveness"] = track_audio_data.get("liveness")
        info["loudness"] = track_audio_data.get("loudness")
        info["speechiness"] = track_audio_data.get("speechiness")
        info["valence"] = track_audio_data.get("valence")
    return info


def spotify_get_podcast_episode_metadata(token, episode_id):
    logger.info("Get episode info for episode by id %s", episode_id)

    headers = spotify_get_auth_header(token)
    episode_data = make_call(f"{BASE_URL}/episodes/{episode_id}", headers=headers)
    if not episode_data:
        raise Exception(
            f"No episode data returned for '{episode_id}' (rate limited or unavailable)"
        )
    show_episode_ids = spotify_get_podcast_episode_ids(
        token, episode_data.get("show", {}).get("id")
    )
    # I believe audiobook ids start with a 7 but to verify you can use https://api.spotify.com/v1/audiobooks/{id}
    # the endpoint could possibly be used to mark audiobooks in genre but it doesn't really provide any additional
    # metadata compared to show_data beyond abridged and unabridged.

    track_number = ""
    for index, episode in enumerate(show_episode_ids):
        if episode == episode_id:
            track_number = index + 1
            break

    copyrights = []
    for copyright in episode_data.get("show", {}).get("copyrights", []):
        text = copyright.get("text")
        copyrights.append(text)

    info = {}
    info["album_name"] = episode_data.get("show", {}).get("name")
    info["title"] = episode_data.get("name")
    info["image_url"] = episode_data.get("images", [{}])[0].get("url")
    info["release_year"] = episode_data.get("release_date").split("-")[0]
    info["track_number"] = track_number
    # Not accurate
    # info['total_tracks'] = episode_data.get('show', {}).get('total_episodes', 0)
    info["total_tracks"] = len(show_episode_ids)
    info["artists"] = conv_list_format([episode_data.get("show", {}).get("publisher")])
    info["album_artists"] = conv_list_format(
        [episode_data.get("show", {}).get("publisher")]
    )
    info["language"] = conv_list_format(episode_data.get("languages", []))
    description = episode_data.get("description")
    info["description"] = str(
        description
        if description
        else episode_data.get("show", {}).get("description", "")
    )
    info["copyright"] = conv_list_format(copyrights)
    info["length"] = str(episode_data.get("duration_ms"))
    info["explicit"] = episode_data.get("explicit")
    info["is_playable"] = episode_data.get("is_playable")
    info["item_url"] = episode_data.get("external_urls", {}).get("spotify")
    info["item_id"] = episode_data.get("id")

    return info


def spotify_get_podcast_episode_ids(token, show_id):
    logger.info("Getting show episodes: %s", show_id)

    episodes = []
    offset = 0
    limit = 50

    while True:
        url = f"{BASE_URL}/shows/{show_id}/episodes?offset={offset}&limit={limit}"
        headers = spotify_get_auth_header(token)
        resp = make_call(url, headers=headers)

        offset += limit
        episodes.extend(resp["items"])

        if resp["total"] <= offset:
            break

    item_ids = []
    for episode in episodes:
        if episode:
            item_ids.append(episode["id"])
    return item_ids
