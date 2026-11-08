"""Spotify sign-in with a device code (OAuth 2.0 Device Authorization Grant).

The server asks Spotify for a short user code, the user approves it at
spotify.com/pair on any device, and a background thread polls for the token.
The token then opens one librespot session, which writes the same stored
login record that Spotify Connect pairing and the companion produce.
"""

import json
import math
import os
import secrets
import threading
import time
from dataclasses import dataclass, field

import requests
from librespot.core import Session
from librespot.mercury import MercuryRequests
from librespot.proto import Authentication_pb2 as Authentication

from ..constants import HTTP_TIMEOUT, DeviceAuthState
from ..otsconfig import cache_dir
from ..runtimedata import get_logger
from .spotify import _SESSION_REINIT_TIMEOUT, _check_premium, add_spotify_zeroconf_login

logger = get_logger("api.spotify_device_auth")

DEVICE_AUTHORIZE_URL = "https://accounts.spotify.com/oauth2/device/authorize"
TOKEN_URL = "https://accounts.spotify.com/api/token"
GRANT_TYPE = "urn:ietf:params:oauth:grant-type:device_code"
# login5 sends this same client id, so the token must come from it too.
CLIENT_ID = MercuryRequests.keymaster_client_id
DEFAULT_SCOPES = "streaming"
# Spotify's codes last about an hour; this only bounds a bad expires_in.
MAX_WAIT = 60 * 60
LOGIN_TIMEOUT = _SESSION_REINIT_TIMEOUT
DEFAULT_INTERVAL = 5
SLOW_DOWN_STEP = 5

# Keep a reference to the real class so tests that replace ``Session`` with a
# mock cannot break the ``isinstance`` check below.
_AUTH_ERROR = Session.SpotifyAuthenticationException

_TERMINAL_STATES = {
    DeviceAuthState.APPROVED,
    DeviceAuthState.DENIED,
    DeviceAuthState.EXPIRED,
    DeviceAuthState.CANCELLED,
    DeviceAuthState.ERROR,
}

_MESSAGES = {
    DeviceAuthState.DENIED: "The sign-in was declined in Spotify.",
    DeviceAuthState.EXPIRED: "The code expired. Start the sign-in again.",
    DeviceAuthState.CANCELLED: "The sign-in was cancelled.",
    "login_rejected": "Spotify did not accept the sign-in. Try again.",
    "login_timeout": "Spotify did not answer in time. Check the network and try again.",
    "login_failed": "OnTheSpot could not finish the sign-in. Check the logs and try again.",
    "login5_rejected": "Spotify did not issue an access token for this account. Try again.",
    "not_premium": "Spotify Premium is required. This account is not Premium.",
}


class DeviceAuthStartError(Exception):
    """Spotify refused to start a device-code sign-in."""


class DeviceAuthBusyError(Exception):
    """A sign-in Spotify already granted is still being saved."""


@dataclass
class DeviceAuthFlow:
    """One device-code sign-in.  ``device_code`` never leaves the server."""

    device_code: str
    user_code: str
    verification_uri: str
    verification_uri_complete: str
    interval: float
    deadline: float
    expires_at: int
    flow_id: str = field(default_factory=lambda: secrets.token_urlsafe(16))
    state: DeviceAuthState = DeviceAuthState.PENDING
    error_code: str = ""
    message: str = ""
    username: str = ""
    cancel: threading.Event = field(default_factory=threading.Event)

    def public_dict(self) -> dict:
        """Return the fields of ``SpotifyDeviceAuthStatus``; no secrets."""
        return {
            "flow_id": self.flow_id,
            "state": self.state.value,
            "user_code": self.user_code,
            "verification_uri": self.verification_uri,
            "verification_uri_complete": self.verification_uri_complete,
            "expires_at": self.expires_at,
            "interval": max(1, math.ceil(self.interval)),
            "username": self.username,
            "error_code": self.error_code,
            "message": self.message,
        }


def _session_from_access_token(access_token: str, stored_file_path: str) -> Session:
    """Open a librespot session with a Spotify access token.

    On success librespot writes the stored login record to
    ``stored_file_path``.
    """
    conf = (
        Session.Configuration.Builder()
        .set_stored_credential_file(stored_file_path)
        .set_store_credentials(True)
        .build()
    )
    builder = Session.Builder(conf=conf).set_device_name("OnTheSpot")
    builder.login_credentials = Authentication.LoginCredentials(
        typ=Authentication.AuthenticationType.AUTHENTICATION_SPOTIFY_TOKEN,
        auth_data=access_token.encode("utf-8"),
    )
    return builder.create()


def _json_body(response) -> dict:
    try:
        body = response.json()
    except ValueError:
        return {}
    return body if isinstance(body, dict) else {}


def _spotify_error_text(body: dict, status_code: int) -> str:
    error = str(body.get("error") or "").strip()
    description = str(body.get("error_description") or "").strip()
    if error and description:
        return f"{error}: {description}"
    return error or description or f"HTTP {status_code}"


class SpotifyDeviceAuthManager:
    """Run at most one device-code sign-in at a time."""

    def __init__(self, http_post=requests.post, session_factory=None, clock=time.monotonic):
        self._http_post = http_post
        self._session_factory = session_factory or _session_from_access_token
        self._clock = clock
        self._lock = threading.Lock()
        self._flow: DeviceAuthFlow | None = None

    # -- public API -------------------------------------------------------

    def start(self, on_success) -> dict:
        """Ask Spotify for a user code and start polling in the background.

        This blocks on one HTTP request; async callers run it in a thread.
        A pending flow is cancelled; an authorizing one is kept and
        ``DeviceAuthBusyError`` is raised, so a granted sign-in is never lost.
        """
        with self._lock:
            self._raise_if_busy_locked()
        try:
            response = self._http_post(
                DEVICE_AUTHORIZE_URL,
                data={"client_id": CLIENT_ID, "scope": DEFAULT_SCOPES},
                timeout=HTTP_TIMEOUT,
            )
        except requests.RequestException as exc:
            logger.warning("Could not reach Spotify to start sign-in: %s", exc)
            raise DeviceAuthStartError("Could not reach Spotify. Check the network and try again.") from exc
        body = _json_body(response)
        if response.status_code != 200:
            text = _spotify_error_text(body, response.status_code)
            logger.error("Spotify refused to start sign-in: %s", text)
            raise DeviceAuthStartError(f"Spotify refused the sign-in request: {text}")
        flow = self._flow_from_response(body)

        with self._lock:
            # The pending flow may have been approved during the HTTP call.
            self._raise_if_busy_locked()
            if self._flow is not None:
                self._cancel_locked(self._flow)
            self._flow = flow
        threading.Thread(
            name="spotify-device-auth",
            target=self._run,
            args=(flow, on_success),
            daemon=True,
        ).start()
        logger.info("Spotify device sign-in started; waiting for approval")
        return flow.public_dict()

    def status(self, flow_id: str) -> dict | None:
        """Return the public state of ``flow_id``, or None if it is unknown."""
        with self._lock:
            flow = self._flow
            if not _is_flow(flow, flow_id):
                return None
            return flow.public_dict()

    def cancel(self, flow_id: str) -> bool:
        """Stop ``flow_id`` while it waits for approval.

        Return False if it is unknown or no longer pending.  Once Spotify
        has granted the sign-in (authorizing) it runs to the end, so a closed
        dialog does not throw the new account away.
        """
        with self._lock:
            flow = self._flow
            if not _is_flow(flow, flow_id) or flow.state != DeviceAuthState.PENDING:
                return False
            self._cancel_locked(flow)
            return True

    def cancel_all(self) -> None:
        """Stop any running sign-in, also one that is authorizing (shutdown)."""
        with self._lock:
            if self._flow is not None:
                self._cancel_locked(self._flow)

    # -- internals --------------------------------------------------------

    def _flow_from_response(self, body: dict) -> DeviceAuthFlow:
        try:
            device_code = str(body["device_code"])
            user_code = str(body["user_code"])
            verification_uri = str(body["verification_uri"])
        except KeyError as exc:
            raise DeviceAuthStartError("Spotify sent an incomplete sign-in response.") from exc
        try:
            interval = float(body.get("interval") or DEFAULT_INTERVAL)
        except (TypeError, ValueError):
            interval = DEFAULT_INTERVAL
        if interval <= 0:
            interval = DEFAULT_INTERVAL
        try:
            lifetime = min(int(body.get("expires_in") or MAX_WAIT), MAX_WAIT)
        except (TypeError, ValueError):
            lifetime = MAX_WAIT
        complete = str(body.get("verification_uri_complete") or f"{verification_uri}?code={user_code}")
        return DeviceAuthFlow(
            device_code=device_code,
            user_code=user_code,
            verification_uri=verification_uri,
            verification_uri_complete=complete,
            interval=interval,
            deadline=self._clock() + lifetime,
            expires_at=int(time.time() + lifetime),
        )

    def _raise_if_busy_locked(self) -> None:
        if self._flow is not None and self._flow.state == DeviceAuthState.AUTHORIZING:
            raise DeviceAuthBusyError("A Spotify sign-in is finishing. Wait a moment and try again.")

    def _cancel_locked(self, flow: DeviceAuthFlow) -> None:
        flow.cancel.set()
        if flow.state not in _TERMINAL_STATES:
            flow.state = DeviceAuthState.CANCELLED
            flow.message = _MESSAGES[DeviceAuthState.CANCELLED]

    def _finish(self, flow: DeviceAuthFlow, state: DeviceAuthState, error_code: str = "", message: str = "") -> None:
        """Move ``flow`` to a terminal state unless it was cancelled first."""
        with self._lock:
            if flow.state in _TERMINAL_STATES:
                return
            flow.state = state
            flow.error_code = error_code
            flow.message = message or _MESSAGES.get(error_code or state, "")

    def _run(self, flow: DeviceAuthFlow, on_success) -> None:
        try:
            while not flow.cancel.wait(flow.interval):
                if self._clock() >= flow.deadline:
                    self._finish(flow, DeviceAuthState.EXPIRED)
                    return
                if self._poll_once(flow, on_success):
                    return
        except Exception:
            logger.exception("Spotify device sign-in stopped unexpectedly")
            self._finish(flow, DeviceAuthState.ERROR, "login_failed")

    def _poll_once(self, flow: DeviceAuthFlow, on_success) -> bool:
        """Ask Spotify once for the token.  Return True when the flow is over."""
        try:
            response = self._http_post(
                TOKEN_URL,
                data={
                    "client_id": CLIENT_ID,
                    "grant_type": GRANT_TYPE,
                    "device_code": flow.device_code,
                },
                timeout=HTTP_TIMEOUT,
            )
        except requests.RequestException as exc:
            logger.debug("Spotify token poll failed, will retry: %s", type(exc).__name__)
            return False

        body = _json_body(response)
        if response.status_code == 200:
            if not body.get("access_token"):
                self._finish(flow, DeviceAuthState.ERROR, "spotify_error", "Spotify sent no access token.")
                return True
            with self._lock:
                if flow.cancel.is_set():
                    return True
                flow.state = DeviceAuthState.AUTHORIZING
            self._complete(flow, body, on_success)
            return True

        if response.status_code >= 500:
            # A Spotify outage should not end a sign-in the user already approved.
            logger.debug("Spotify token poll got HTTP %s, will retry", response.status_code)
            return False
        error = str(body.get("error") or "")
        if response.status_code == 429 or error == "slow_down":
            flow.interval += SLOW_DOWN_STEP
            return False
        if error == "authorization_pending":
            return False
        if error == "access_denied":
            self._finish(flow, DeviceAuthState.DENIED)
            return True
        if error == "expired_token":
            self._finish(flow, DeviceAuthState.EXPIRED)
            return True
        text = _spotify_error_text(body, response.status_code)
        logger.error("Spotify sign-in failed: %s", text)
        self._finish(flow, DeviceAuthState.ERROR, "spotify_error", f"Spotify returned an error: {text}")
        return True

    def _open_session(self, access_token: str, path: str):
        """Open a session, get a login5 token and check Premium in time.

        All three steps run in one helper thread bounded by LOGIN_TIMEOUT,
        because librespot sends some of these requests with no timeout.
        Return ``(session, error_code)``; on an error the session is closed.
        If the limit passes, the helper closes a session that opens later and
        removes its login file.
        """
        outcome = {"done": False, "abandoned": False}
        lock = threading.Lock()

        def _login():
            session = token = error = None
            accepted = closed = False
            try:
                session = self._session_factory(access_token, path)
                try:
                    token = session.tokens().login5(["playlist-read"])
                except Exception as exc:  # noqa: BLE001 - any failure here means no token
                    logger.error("Spotify login5 request failed: %s", type(exc).__name__)
                if token is not None:
                    accepted, _account_type = _check_premium(session, session.username())
                    # _check_premium closes a session it rejects.
                    closed = not accepted
            except Exception as exc:  # noqa: BLE001 - librespot raises many types; sorted out below
                error = exc
            with lock:
                outcome.update(done=True, session=session, token=token, accepted=accepted, closed=closed, error=error)
                abandoned = outcome["abandoned"]
            if abandoned:
                if session is not None and not closed:
                    _close_quietly(session)
                _remove_quietly(path)

        helper = threading.Thread(target=_login, name="spotify-device-auth-login", daemon=True)
        helper.start()
        helper.join(timeout=LOGIN_TIMEOUT)
        with lock:
            if not outcome["done"]:
                outcome["abandoned"] = True
                logger.error("Spotify sign-in timed out while opening a session")
                return None, "login_timeout"

        session = outcome["session"]
        error = outcome["error"]
        if error is None and outcome["accepted"]:
            return session, ""
        if session is not None and not outcome["closed"]:
            _close_quietly(session)
        if error is None:
            return None, "login5_rejected" if outcome["token"] is None else "not_premium"
        if isinstance(error, _AUTH_ERROR):
            logger.error("Spotify rejected the session login: %s", error)
            return None, "login_rejected"
        logger.error("Could not open a Spotify session: %s", type(error).__name__)
        return None, "login_failed"

    def _complete(self, flow: DeviceAuthFlow, body: dict, on_success) -> None:
        sessions_dir = os.path.join(cache_dir(), "sessions")
        os.makedirs(sessions_dir, exist_ok=True)
        path = os.path.join(sessions_dir, f"device_auth_{flow.flow_id}.json")
        session = None
        try:
            session, error_code = self._open_session(body["access_token"], path)
            if session is None:
                self._finish(flow, DeviceAuthState.ERROR, error_code)
                return
            login = _read_login(path)
            if login is None:
                self._finish(flow, DeviceAuthState.ERROR, "login_failed")
                return
        finally:
            _remove_quietly(path)
            if session is not None:
                _close_quietly(session)

        username = login["username"]
        masked = username[:4] + "****"
        with self._lock:
            if flow.cancel.is_set():
                logger.info("Spotify sign-in for %s was cancelled; nothing saved", masked)
                return
        # Save outside the lock: it writes to disk.
        if not add_spotify_zeroconf_login(login, replace_existing=True):
            self._finish(flow, DeviceAuthState.ERROR, "login_failed")
            return
        with self._lock:
            stopped = flow.cancel.is_set()
            if not stopped:
                flow.username = username
                flow.state = DeviceAuthState.APPROVED
                flow.message = f"Signed in as {username}."
        if stopped:
            logger.info("Spotify sign-in for %s was saved while the server stopped", masked)
            return
        logger.info("Spotify device sign-in approved for %s", masked)
        try:
            on_success(username)
        except Exception:
            logger.exception("Spotify sign-in follow-up failed")


def _is_flow(flow: DeviceAuthFlow | None, flow_id: str) -> bool:
    if flow is None:
        return False
    return secrets.compare_digest(flow.flow_id.encode("utf-8"), str(flow_id).encode("utf-8"))


def _read_login(path: str) -> dict | None:
    """Load the login record librespot wrote, or None if it is incomplete."""
    try:
        with open(path, encoding="utf-8") as file:
            data = json.load(file)
    except (OSError, ValueError):
        logger.error("Spotify session wrote no usable login file")
        return None
    if not isinstance(data, dict):
        return None
    login = {key: data.get(key) for key in ("username", "credentials", "type")}
    if not all(isinstance(value, str) and value for value in login.values()):
        logger.error("Spotify login file is missing fields")
        return None
    return login


def _remove_quietly(path: str) -> None:
    try:
        os.remove(path)
    except FileNotFoundError:
        pass
    except OSError as exc:
        logger.debug("Could not remove %s: %s", path, exc)


def _close_quietly(session) -> None:
    try:
        session.close()
    except Exception as exc:  # noqa: BLE001 - closing is best effort
        logger.debug("Failed to close Spotify session: %s", exc)


device_auth = SpotifyDeviceAuthManager()
