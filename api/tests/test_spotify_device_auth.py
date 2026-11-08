import json
import os
import threading
import time
import unittest
from unittest.mock import MagicMock, patch

import requests
from _support import TEST_ROOT  # noqa: F401

# main.py sets this before it imports librespot; set it here for a direct import.
os.environ.setdefault("PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION", "python")

from librespot.core import Session
from librespot.proto import Authentication_pb2 as Authentication
from librespot.proto import Keyexchange_pb2 as Keyexchange

from onthespot.api import spotify, spotify_device_auth
from onthespot.api.spotify_device_auth import (
    DeviceAuthStartError,
    SpotifyDeviceAuthManager,
)
from onthespot.constants import DeviceAuthState
from onthespot.otsconfig import cache_dir, config

DEVICE_CODE = "device-code-secret"
ACCESS_TOKEN = "access-token-secret"
REFRESH_TOKEN = "refresh-token-secret"
LOGIN = {
    "username": "someuser",
    "credentials": "c3RvcmVkLWNyZWRz",
    "type": "AUTHENTICATION_STORED_SPOTIFY_CREDENTIALS",
}


class FakeResponse:
    def __init__(self, status_code, body=None):
        self.status_code = status_code
        self._body = body

    def json(self):
        if self._body is None:
            raise ValueError("no JSON")
        return self._body


def _authorize_body(**overrides):
    body = {
        "device_code": DEVICE_CODE,
        "user_code": "ABCD-EFGH",
        "verification_uri": "https://spotify.com/pair",
        "verification_uri_complete": "https://spotify.com/pair?code=ABCD-EFGH",
        "expires_in": 3599,
        "interval": 5,
    }
    body.update(overrides)
    return body


def _token_body():
    return {
        "access_token": ACCESS_TOKEN,
        "refresh_token": REFRESH_TOKEN,
        "expires_in": 3600,
        "scope": "streaming",
        "token_type": "Bearer",
        "username": "someuser",
    }


def _pending():
    return FakeResponse(400, {"error": "authorization_pending"})


class FakeSpotify:
    """Answers the authorize call, then hands out queued token responses."""

    def __init__(self, authorize=None, tokens=None):
        self.authorize = authorize or FakeResponse(200, _authorize_body())
        self.tokens = list(tokens or [])
        self.calls = []
        self.lock = threading.Lock()

    def __call__(self, url, data=None, timeout=None):
        with self.lock:
            self.calls.append((url, dict(data or {}), timeout))
            if url == spotify_device_auth.DEVICE_AUTHORIZE_URL:
                return self.authorize
            response = self.tokens.pop(0) if self.tokens else _pending()
        if isinstance(response, Exception):
            raise response
        return response

    def token_calls(self):
        return [call for call in self.calls if call[0] == spotify_device_auth.TOKEN_URL]


class FakeClock:
    def __init__(self, now=1000.0):
        self.now = now

    def __call__(self):
        return self.now


_LOGIN5_TOKEN = object()


def _wait_for(predicate, timeout=2.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return predicate()


def _session(account_type="premium", login5_token=_LOGIN5_TOKEN):
    session = MagicMock(name="session")
    session.tokens.return_value.login5.return_value = login5_token
    session.username.return_value = "someuser"
    session.get_user_attribute.return_value = account_type
    return session


class SessionFactory:
    """Writes the login file like librespot does and returns a fake session."""

    def __init__(self, session=None, write=True, hook=None):
        self.session = session or _session()
        self.write = write
        self.hook = hook
        self.calls = []

    def __call__(self, access_token, path):
        self.calls.append((access_token, path))
        if self.write:
            with open(path, "w", encoding="utf-8") as file:
                json.dump(LOGIN, file)
        if self.hook is not None:
            self.hook()
        return self.session


class DeviceAuthTestCase(unittest.TestCase):
    def setUp(self):
        self.add_login = self._patch("onthespot.api.spotify_device_auth.add_spotify_zeroconf_login", return_value=True)
        self._patch("onthespot.api.spotify._ACCOUNT_TYPE_WAIT", 0)
        self.http = FakeSpotify()
        self.clock = FakeClock()
        self.factory = SessionFactory()
        self.on_success = MagicMock()
        self.manager = SpotifyDeviceAuthManager(
            http_post=self.http, session_factory=self.factory, clock=self.clock
        )
        self.addCleanup(self.manager.cancel_all)

    def _patch(self, target, *args, **kwargs):
        patcher = patch(target, *args, **kwargs)
        mocked = patcher.start()
        self.addCleanup(patcher.stop)
        return mocked

    def flow(self, **overrides):
        flow = self.manager._flow_from_response(_authorize_body(**overrides))
        self.manager._flow = flow
        return flow

    def poll(self, flow, *responses):
        self.http.tokens.extend(responses)
        return self.manager._poll_once(flow, self.on_success)


class StartTests(DeviceAuthTestCase):
    def test_start_returns_a_pending_flow_without_secrets(self):
        before = int(time.time())
        public = self.manager.start(self.on_success)

        self.assertEqual(public["state"], "pending")
        self.assertEqual(public["user_code"], "ABCD-EFGH")
        self.assertEqual(public["verification_uri"], "https://spotify.com/pair")
        self.assertEqual(public["verification_uri_complete"], "https://spotify.com/pair?code=ABCD-EFGH")
        self.assertEqual(public["interval"], 5)
        # Spotify's full 3599 s code lifetime is kept.
        self.assertGreaterEqual(public["expires_at"], before + 3599)
        self.assertLessEqual(public["expires_at"], int(time.time()) + 3599)
        self.assertEqual(self.manager._flow.deadline, self.clock.now + 3599)
        text = json.dumps(public)
        for secret in (DEVICE_CODE, ACCESS_TOKEN, REFRESH_TOKEN):
            self.assertNotIn(secret, text)

        url, data, timeout = self.http.calls[0]
        self.assertEqual(url, spotify_device_auth.DEVICE_AUTHORIZE_URL)
        self.assertEqual(data, {"client_id": spotify_device_auth.CLIENT_ID, "scope": "streaming"})
        self.assertIsNotNone(timeout)
        self.assertEqual(spotify_device_auth.CLIENT_ID, "65b708073fc0480ea92a077233ca87bd")

    def test_missing_complete_uri_is_built_from_the_code(self):
        self.http.authorize = FakeResponse(200, _authorize_body(verification_uri_complete=None))

        public = self.manager.start(self.on_success)

        self.assertEqual(public["verification_uri_complete"], "https://spotify.com/pair?code=ABCD-EFGH")

    def test_short_expiry_is_kept(self):
        self.http.authorize = FakeResponse(200, _authorize_body(expires_in=60))

        public = self.manager.start(self.on_success)

        self.assertLessEqual(public["expires_at"], int(time.time()) + 60)
        self.assertEqual(self.manager._flow.deadline, self.clock.now + 60)

    def test_long_expiry_is_capped(self):
        self.http.authorize = FakeResponse(200, _authorize_body(expires_in=10 * 60 * 60))

        self.manager.start(self.on_success)

        self.assertEqual(self.manager._flow.deadline, self.clock.now + spotify_device_auth.MAX_WAIT)

    def test_authorize_error_raises_with_spotify_error(self):
        self.http.authorize = FakeResponse(400, {"error": "invalid_client"})

        with self.assertRaises(DeviceAuthStartError) as raised:
            self.manager.start(self.on_success)

        self.assertIn("invalid_client", str(raised.exception))
        self.assertIsNone(self.manager._flow)

    def test_authorize_network_error_raises_start_error(self):

        def broken(url, data=None, timeout=None):
            raise requests.ConnectionError("down")

        self.manager._http_post = broken
        with self.assertRaises(DeviceAuthStartError):
            self.manager.start(self.on_success)


class PollTests(DeviceAuthTestCase):
    def test_pending_stays_pending(self):
        flow = self.flow()

        self.assertFalse(self.poll(flow, _pending()))

        self.assertEqual(flow.state, DeviceAuthState.PENDING)
        _, data, timeout = self.http.token_calls()[0]
        self.assertEqual(data["grant_type"], spotify_device_auth.GRANT_TYPE)
        self.assertEqual(data["device_code"], DEVICE_CODE)
        self.assertEqual(data["client_id"], spotify_device_auth.CLIENT_ID)
        self.assertIsNotNone(timeout)

    def test_slow_down_and_429_add_five_seconds(self):
        flow = self.flow()

        self.assertFalse(self.poll(flow, FakeResponse(400, {"error": "slow_down"})))
        self.assertEqual(flow.interval, 10)
        self.assertFalse(self.poll(flow, FakeResponse(429, None)))
        self.assertEqual(flow.interval, 15)
        self.assertEqual(flow.state, DeviceAuthState.PENDING)

    def test_access_denied_is_denied(self):
        flow = self.flow()

        self.assertTrue(self.poll(flow, FakeResponse(400, {"error": "access_denied"})))

        self.assertEqual(flow.state, DeviceAuthState.DENIED)
        self.assertTrue(flow.message)
        self.assertEqual(self.factory.calls, [])
        self.on_success.assert_not_called()

    def test_expired_token_is_expired(self):
        flow = self.flow()

        self.assertTrue(self.poll(flow, FakeResponse(400, {"error": "expired_token"})))

        self.assertEqual(flow.state, DeviceAuthState.EXPIRED)

    def test_deadline_expires_without_a_request(self):
        flow = self.flow(interval=0.001)
        self.clock.now = flow.deadline

        self.manager._run(flow, self.on_success)

        self.assertEqual(flow.state, DeviceAuthState.EXPIRED)
        self.assertEqual(self.http.token_calls(), [])

    def test_unexpected_poll_error_is_login_failed(self):
        flow = self.flow(interval=0.001)
        self.manager._poll_once = MagicMock(side_effect=RuntimeError("boom"))

        with self.assertLogs(spotify_device_auth.logger, level="ERROR"):
            self.manager._run(flow, self.on_success)

        self.assertEqual(flow.state, DeviceAuthState.ERROR)
        self.assertEqual(flow.error_code, "login_failed")

    def test_network_error_keeps_polling(self):
        flow = self.flow()

        self.assertFalse(self.poll(flow, requests.ConnectionError("down")))

        self.assertEqual(flow.state, DeviceAuthState.PENDING)

    def test_server_error_keeps_polling(self):
        flow = self.flow()

        self.assertFalse(self.poll(flow, FakeResponse(503, None)))

        self.assertEqual(flow.state, DeviceAuthState.PENDING)

    def test_other_spotify_error_ends_the_flow(self):
        flow = self.flow()

        self.assertTrue(self.poll(flow, FakeResponse(400, {"error": "invalid_grant", "error_description": "bad"})))

        self.assertEqual(flow.state, DeviceAuthState.ERROR)
        self.assertEqual(flow.error_code, "spotify_error")
        self.assertIn("invalid_grant", flow.message)


class CompleteTests(DeviceAuthTestCase):
    def test_success_saves_the_login_and_reports_the_user(self):
        flow = self.flow()

        with self.assertLogs(spotify_device_auth.logger, level="DEBUG") as logs:
            self.assertTrue(self.poll(flow, FakeResponse(200, _token_body())))

        self.assertEqual(len(self.factory.calls), 1)
        access_token, path = self.factory.calls[0]
        self.assertEqual(access_token, ACCESS_TOKEN)
        sessions_dir = os.path.join(cache_dir(), "sessions")
        self.assertEqual(os.path.dirname(path), sessions_dir)
        self.assertFalse(os.path.exists(path))
        self.add_login.assert_called_once_with(LOGIN, replace_existing=True)
        self.on_success.assert_called_once_with("someuser")
        self.assertEqual(flow.state, DeviceAuthState.APPROVED)
        self.assertEqual(flow.username, "someuser")
        self.factory.session.close.assert_called_once_with()
        self.factory.session.tokens.return_value.login5.assert_called_once_with(["playlist-read"])
        text = "\n".join(logs.output)
        for secret in (DEVICE_CODE, ACCESS_TOKEN, REFRESH_TOKEN, LOGIN["credentials"]):
            self.assertNotIn(secret, text)

    def test_login5_failure_saves_nothing(self):
        self.factory.session = _session(login5_token=None)
        flow = self.flow()

        self.assertTrue(self.poll(flow, FakeResponse(200, _token_body())))

        self.assertEqual(flow.state, DeviceAuthState.ERROR)
        self.assertEqual(flow.error_code, "login5_rejected")
        self.add_login.assert_not_called()
        self.on_success.assert_not_called()
        self.factory.session.close.assert_called_once_with()
        self.assertFalse(os.path.exists(self.factory.calls[0][1]))

    def test_free_account_is_rejected(self):
        self.factory.session = _session(account_type="free")
        flow = self.flow()

        self.assertTrue(self.poll(flow, FakeResponse(200, _token_body())))

        self.assertEqual(flow.state, DeviceAuthState.ERROR)
        self.assertEqual(flow.error_code, "not_premium")
        self.assertTrue(flow.message)
        self.add_login.assert_not_called()
        self.on_success.assert_not_called()
        # _check_premium closes it; it must not be closed twice.
        self.factory.session.close.assert_called_once_with()

    def test_rejected_session_login_is_login_rejected(self):
        failure = Keyexchange.APLoginFailed(error_code=Keyexchange.ErrorCode.BadCredentials)

        def factory(access_token, path):
            raise Session.SpotifyAuthenticationException(failure)

        self.manager._session_factory = factory
        flow = self.flow()

        self.assertTrue(self.poll(flow, FakeResponse(200, _token_body())))

        self.assertEqual(flow.error_code, "login_rejected")
        self.add_login.assert_not_called()

    def test_slow_session_login_times_out(self):
        release = threading.Event()
        session = _session()

        def factory(access_token, path):
            release.wait(5)
            return session

        self.manager._session_factory = factory
        self._patch("onthespot.api.spotify_device_auth.LOGIN_TIMEOUT", 0.05)
        flow = self.flow()

        self.assertTrue(self.poll(flow, FakeResponse(200, _token_body())))
        self.assertEqual(flow.error_code, "login_timeout")
        self.add_login.assert_not_called()

        # A session that opens after the time limit is closed, not kept.
        release.set()
        self.assertTrue(_wait_for(lambda: session.close.called))
        session.close.assert_called_once_with()

    def test_stalled_login5_times_out(self):
        release = threading.Event()
        session = _session()
        session.tokens.return_value.login5.side_effect = lambda scopes: release.wait(5) and _LOGIN5_TOKEN
        self.factory.session = session
        self._patch("onthespot.api.spotify_device_auth.LOGIN_TIMEOUT", 0.05)
        flow = self.flow()

        self.assertTrue(self.poll(flow, FakeResponse(200, _token_body())))
        self.assertEqual(flow.state, DeviceAuthState.ERROR)
        self.assertEqual(flow.error_code, "login_timeout")
        self.add_login.assert_not_called()
        session.close.assert_not_called()

        # Once login5 returns, the abandoned helper closes the session. The
        # login file is already gone: _complete removed it at the timeout.
        release.set()
        path = self.factory.calls[0][1]
        self.assertTrue(_wait_for(lambda: session.close.called and not os.path.exists(path)))
        session.close.assert_called_once_with()

    def test_missing_login_file_is_login_failed(self):
        self.factory.write = False
        flow = self.flow()

        self.assertTrue(self.poll(flow, FakeResponse(200, _token_body())))

        self.assertEqual(flow.error_code, "login_failed")
        self.add_login.assert_not_called()
        self.factory.session.close.assert_called_once_with()

    def test_save_failure_is_login_failed(self):
        self.add_login.return_value = False
        flow = self.flow()

        self.assertTrue(self.poll(flow, FakeResponse(200, _token_body())))

        self.assertEqual(flow.state, DeviceAuthState.ERROR)
        self.assertEqual(flow.error_code, "login_failed")
        self.on_success.assert_not_called()

    def test_follow_up_error_keeps_the_flow_approved(self):
        self.on_success.side_effect = RuntimeError("relogin broke")
        flow = self.flow()

        with self.assertLogs(spotify_device_auth.logger, level="ERROR") as logs:
            self.assertTrue(self.poll(flow, FakeResponse(200, _token_body())))

        self.assertEqual(flow.state, DeviceAuthState.APPROVED)
        self.assertIn("follow-up failed", "\n".join(logs.output))

    def test_cancel_during_authorizing_keeps_the_sign_in(self):
        flow = self.flow()
        answers = []

        def cancel_now():
            answers.append((flow.state, self.manager.cancel(flow.flow_id)))

        self.factory.hook = cancel_now

        self.assertTrue(self.poll(flow, FakeResponse(200, _token_body())))

        self.assertEqual(answers, [(DeviceAuthState.AUTHORIZING, False)])
        self.assertFalse(flow.cancel.is_set())
        self.assertEqual(flow.state, DeviceAuthState.APPROVED)
        self.add_login.assert_called_once_with(LOGIN, replace_existing=True)
        self.on_success.assert_called_once_with("someuser")

    def test_start_during_authorizing_is_refused_and_keeps_the_sign_in(self):
        flow = self.flow()
        self.http.authorize = FakeResponse(200, _authorize_body())
        answers = []

        def start_now():
            with self.assertRaises(spotify_device_auth.DeviceAuthBusyError):
                self.manager.start(self.on_success)
            answers.append(self.manager._flow is flow)

        self.factory.hook = start_now

        self.assertTrue(self.poll(flow, FakeResponse(200, _token_body())))

        self.assertEqual(answers, [True])
        self.assertEqual(flow.state, DeviceAuthState.APPROVED)
        self.add_login.assert_called_once_with(LOGIN, replace_existing=True)

    def test_shutdown_during_authorizing_saves_nothing(self):
        flow = self.flow()
        self.factory.hook = self.manager.cancel_all

        self.assertTrue(self.poll(flow, FakeResponse(200, _token_body())))

        self.assertEqual(flow.state, DeviceAuthState.CANCELLED)
        self.add_login.assert_not_called()
        self.on_success.assert_not_called()
        self.factory.session.close.assert_called_once_with()
        self.assertFalse(os.path.exists(self.factory.calls[0][1]))

    def test_shutdown_during_save_keeps_the_account_but_not_the_follow_up(self):
        flow = self.flow()

        def save(login, replace_existing):
            self.manager.cancel_all()
            return True

        self.add_login.side_effect = save

        self.assertTrue(self.poll(flow, FakeResponse(200, _token_body())))

        self.add_login.assert_called_once_with(LOGIN, replace_existing=True)
        self.assertEqual(flow.state, DeviceAuthState.CANCELLED)
        self.on_success.assert_not_called()

    def test_cancel_after_the_end_changes_nothing(self):
        flow = self.flow()
        self.assertTrue(self.poll(flow, FakeResponse(200, _token_body())))
        self.assertEqual(flow.state, DeviceAuthState.APPROVED)

        self.assertFalse(self.manager.cancel(flow.flow_id))

        self.assertEqual(flow.state, DeviceAuthState.APPROVED)
        self.assertEqual(flow.message, "Signed in as someuser.")


class ReadLoginTests(unittest.TestCase):
    def test_non_string_field_is_refused(self):
        path = os.path.join(cache_dir(), "read_login_test.json")
        self.addCleanup(spotify_device_auth._remove_quietly, path)
        with open(path, "w", encoding="utf-8") as file:
            json.dump(dict(LOGIN, credentials=12345), file)

        with self.assertLogs(spotify_device_auth.logger, level="ERROR"):
            self.assertIsNone(spotify_device_auth._read_login(path))


class ThreadedRunTests(DeviceAuthTestCase):
    def _poll_threads(self):
        return {t for t in threading.enumerate() if t.name == "spotify-device-auth"}

    def test_flow_moves_from_pending_to_approved(self):
        self.manager._clock = time.monotonic
        self.http.authorize = FakeResponse(200, _authorize_body(interval=0.01))
        self.http.tokens.extend([_pending(), _pending(), FakeResponse(200, _token_body())])
        done = threading.Event()
        self.on_success.side_effect = lambda username: done.set()

        public = self.manager.start(self.on_success)
        self.assertEqual(public["state"], "pending")

        self.assertTrue(done.wait(2))
        status = self.manager.status(public["flow_id"])
        self.assertEqual(status["state"], "approved")
        self.assertEqual(status["username"], "someuser")
        self.assertEqual(len(self.http.token_calls()), 3)

    def test_cancel_stops_the_thread(self):
        self.manager._clock = time.monotonic
        self.http.authorize = FakeResponse(200, _authorize_body(interval=0.01))
        before = self._poll_threads()

        public = self.manager.start(self.on_success)
        started = self._poll_threads() - before
        self.assertEqual(len(started), 1)
        self.assertTrue(self.manager.cancel(public["flow_id"]))

        thread = started.pop()
        thread.join(1)
        self.assertFalse(thread.is_alive())
        self.assertEqual(self.manager.status(public["flow_id"])["state"], "cancelled")

    def test_second_start_cancels_the_first(self):
        self.manager._clock = time.monotonic
        self.http.authorize = FakeResponse(200, _authorize_body(interval=0.01))

        first = self.manager.start(self.on_success)
        first_flow = self.manager._flow
        second = self.manager.start(self.on_success)

        self.assertNotEqual(first["flow_id"], second["flow_id"])
        self.assertTrue(first_flow.cancel.is_set())
        self.assertEqual(first_flow.state, DeviceAuthState.CANCELLED)
        self.assertIsNone(self.manager.status(first["flow_id"]))
        self.assertEqual(self.manager.status(second["flow_id"])["state"], "pending")

    def test_unknown_flow_id(self):
        self.assertIsNone(self.manager.status("nope"))
        self.assertFalse(self.manager.cancel("nope"))
        self.manager.start(self.on_success)
        self.assertIsNone(self.manager.status("nöpe"))


class AddZeroconfLoginTests(unittest.TestCase):
    def setUp(self):
        self.store = {
            "accounts": [
                {"uuid": "keep-me", "service": "spotify", "active": False, "login": {"username": "someuser", "credentials": "old", "type": "OLD"}},
                {"uuid": "other", "service": "tidal", "active": True, "login": {"username": "someuser"}},
            ]
        }
        for name, impl in (
            ("get", lambda key, default=None: self.store.get(key, default)),
            ("set", lambda key, value: self.store.__setitem__(key, value)),
            ("save", lambda: None),
        ):
            patcher = patch.object(config, name, side_effect=impl)
            setattr(self, name, patcher.start())
            self.addCleanup(patcher.stop)

    def test_replace_existing_keeps_the_uuid(self):
        self.assertTrue(spotify.add_spotify_zeroconf_login(dict(LOGIN), replace_existing=True))

        accounts = self.store["accounts"]
        self.assertEqual(len(accounts), 2)
        self.assertEqual(accounts[0]["uuid"], "keep-me")
        self.assertTrue(accounts[0]["active"])
        self.assertEqual(accounts[0]["login"], LOGIN)
        self.assertEqual(accounts[1]["service"], "tidal")
        self.save.assert_called_once_with()

    def test_default_refuses_a_duplicate(self):
        self.assertFalse(spotify.add_spotify_zeroconf_login(dict(LOGIN)))

        self.assertEqual(self.store["accounts"][0]["login"]["credentials"], "old")
        self.set.assert_not_called()

    def test_new_account_is_added(self):
        login = dict(LOGIN, username="newuser")

        self.assertTrue(spotify.add_spotify_zeroconf_login(login, replace_existing=True))

        self.assertEqual(len(self.store["accounts"]), 3)
        self.assertEqual(self.store["accounts"][2]["login"], login)

    def test_bad_payload_is_refused(self):
        for payload in (None, {}, dict(LOGIN, credentials=""), dict(LOGIN, type=None)):
            with self.subTest(payload=payload):
                self.assertFalse(spotify.add_spotify_zeroconf_login(payload, replace_existing=True))
        self.set.assert_not_called()


class SessionFromAccessTokenTests(unittest.TestCase):
    def test_builds_a_token_login_without_network(self):
        with patch("onthespot.api.spotify_device_auth.Session") as session_cls:
            builder = session_cls.Builder.return_value.set_device_name.return_value

            result = spotify_device_auth._session_from_access_token("tok", "/tmp/login.json")

        conf_builder = session_cls.Configuration.Builder.return_value
        conf_builder.set_stored_credential_file.assert_called_once_with("/tmp/login.json")
        conf_builder.set_stored_credential_file.return_value.set_store_credentials.assert_called_once_with(True)
        session_cls.Builder.return_value.set_device_name.assert_called_once_with("OnTheSpot")
        credentials = builder.login_credentials
        self.assertEqual(credentials.typ, Authentication.AuthenticationType.AUTHENTICATION_SPOTIFY_TOKEN)
        self.assertEqual(credentials.auth_data, b"tok")
        builder.create.assert_called_once_with()
        self.assertIs(result, builder.create.return_value)


class DeviceAuthEndpointTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from fastapi.testclient import TestClient

        from onthespot.main import app

        # No context manager: these tests need no background workers.
        cls.client = TestClient(app)

    def setUp(self):
        patcher = patch("onthespot.main.device_auth")
        self.device_auth = patcher.start()
        self.addCleanup(patcher.stop)
        flow = spotify_device_auth.SpotifyDeviceAuthManager(clock=FakeClock())._flow_from_response(_authorize_body())
        self.public = flow.public_dict()

    def test_start_returns_the_status_model(self):
        self.device_auth.start.return_value = self.public

        response = self.client.post("/accounts/spotify/device-auth/start")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(set(response.json()), set(self.public))
        self.assertEqual(response.json()["state"], "pending")
        self.assertNotIn(DEVICE_CODE, response.text)

    def test_start_error_is_502(self):
        self.device_auth.start.side_effect = DeviceAuthStartError("Spotify refused the sign-in request: invalid_client")

        response = self.client.post("/accounts/spotify/device-auth/start")

        self.assertEqual(response.status_code, 502)
        self.assertIn("invalid_client", response.json()["detail"])

    def test_start_while_busy_is_409(self):
        self.device_auth.start.side_effect = spotify_device_auth.DeviceAuthBusyError("finishing")

        response = self.client.post("/accounts/spotify/device-auth/start")

        self.assertEqual(response.status_code, 409)
        self.assertIn("finishing", response.json()["detail"])

    def test_status(self):
        self.device_auth.status.return_value = self.public
        response = self.client.get("/accounts/spotify/device-auth/status", params={"flow_id": "abc"})
        self.assertEqual(response.status_code, 200)
        self.device_auth.status.assert_called_once_with("abc")

        self.device_auth.status.return_value = None
        response = self.client.get("/accounts/spotify/device-auth/status", params={"flow_id": "nope"})
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["detail"], "Unknown or expired sign-in")

    def test_cancel(self):
        self.device_auth.cancel.return_value = True

        response = self.client.post("/accounts/spotify/device-auth/cancel", params={"flow_id": "abc"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"success": True})
        self.device_auth.cancel.assert_called_once_with("abc")

    def test_companion_routes_are_deprecated(self):
        paths = self.client.get("/openapi.json").json()["paths"]

        for path in ("/accounts/spotify/companion/pair", "/accounts/spotify/companion/complete"):
            with self.subTest(path=path):
                self.assertIs(paths[path]["post"].get("deprecated"), True)
        self.assertNotIn("deprecated", paths["/accounts/spotify/device-auth/start"]["post"])


if __name__ == "__main__":
    unittest.main()
