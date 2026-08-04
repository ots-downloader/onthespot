import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from _support import TEST_ROOT  # noqa: F401

from onthespot.constants import HTTP_TIMEOUT  # noqa: E402
from onthespot.utils import _cache_ttl_seconds, make_call  # noqa: E402


class _Response:
    def __init__(self, payload, *, headers=None, status_code=200):
        self.status_code = status_code
        self.text = json.dumps(payload)
        self.headers = headers or {}


class _Session:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return self.response


class ApiResponseCacheTests(unittest.TestCase):
    def test_spotify_cache_allowlist_excludes_private_routes(self):
        with patch("onthespot.utils.config.get") as config_get:
            values = {
                "cache_api_calls": True,
                "spotify_search_cache_ttl_seconds": 900,
                "spotify_metadata_cache_ttl_seconds": 604800,
            }
            config_get.side_effect = lambda key, default=None: values.get(key, default)
            self.assertEqual(
                _cache_ttl_seconds("https://api.spotify.com/v1/search", None),
                900,
            )
            self.assertEqual(
                _cache_ttl_seconds("https://api.spotify.com/v1/tracks/abc", None),
                604800,
            )
            self.assertEqual(
                _cache_ttl_seconds("https://api.spotify.com/v1/me/playlists", None),
                0,
            )

    def test_global_switch_disables_even_explicit_cache_ttl(self):
        with patch("onthespot.utils.config.get", return_value=False):
            self.assertEqual(
                _cache_ttl_seconds("https://public.example/catalog", 3600),
                0,
            )

    def test_public_response_is_reused_from_disk_across_sessions(self):
        with tempfile.TemporaryDirectory(prefix="ots-request-cache-") as cache_root:
            values = {
                "_cache_dir": cache_root,
                "cache_api_calls": True,
                "api_response_cache_ttl_seconds": 3600,
                "api_retry_max_attempts": 1,
                "api_retry_base_delay": 0,
                "api_retry_max_delay": 0,
            }
            first_session = _Session(
                _Response(
                    {"items": [1, 2, 3]},
                    headers={"Cache-Control": "public, max-age=0"},
                )
            )
            second_session = _Session(_Response({"unexpected": True}))
            with patch("onthespot.utils.config.get") as config_get:
                config_get.side_effect = lambda key, default=None: values.get(key, default)
                first = make_call(
                    "https://public.example/catalog",
                    params={"q": "test"},
                    session=first_session,
                )
                second = make_call(
                    "https://public.example/catalog",
                    params={"q": "test"},
                    session=second_session,
                )

            self.assertEqual(first, {"items": [1, 2, 3]})
            self.assertEqual(second, first)
            self.assertEqual(len(first_session.calls), 1)
            self.assertEqual(second_session.calls, [])
            self.assertEqual(first_session.calls[0][1]["timeout"], HTTP_TIMEOUT)
            self.assertEqual(len(list(Path(cache_root, "reqcache").glob("v2-*.json"))), 1)

    def test_concurrent_identical_requests_only_hit_provider_once(self):
        with tempfile.TemporaryDirectory(prefix="ots-request-cache-concurrent-") as cache_root:
            values = {
                "_cache_dir": cache_root,
                "cache_api_calls": True,
                "api_response_cache_ttl_seconds": 3600,
                "api_retry_max_attempts": 1,
                "api_retry_base_delay": 0,
                "api_retry_max_delay": 0,
            }
            session = _Session(_Response({"ok": True}))
            results = []
            with patch("onthespot.utils.config.get") as config_get:
                config_get.side_effect = lambda key, default=None: values.get(key, default)
                threads = [
                    threading.Thread(
                        target=lambda: results.append(
                            make_call("https://public.example/same", session=session)
                        )
                    )
                    for _ in range(4)
                ]
                for thread in threads:
                    thread.start()
                for thread in threads:
                    thread.join()

            self.assertEqual(results, [{"ok": True}] * 4)
            self.assertEqual(len(session.calls), 1)


if __name__ == "__main__":
    unittest.main()
