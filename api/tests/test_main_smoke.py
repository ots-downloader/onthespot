import unittest
from unittest.mock import patch

from _support import TEST_ROOT  # noqa: F401

from fastapi.testclient import TestClient  # noqa: E402
from onthespot.main import app, search_service_catalogs  # noqa: E402
from onthespot.playlist_automation import (  # noqa: E402
    PlaylistAutomationError,
    normalize_playlist_redirect_uri,
)


class ApiSmokeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Deliberately avoid the context-manager form: these route tests do not
        # need background download, scheduler, or Spotify discovery workers.
        cls.client = TestClient(app)

    def test_openapi_identifies_onthespot(self):
        response = self.client.get("/openapi.json")
        self.assertEqual(response.status_code, 200)
        document = response.json()
        self.assertEqual(document["info"]["title"], "OnTheSpot API")
        self.assertIn("2.0.0", document["info"]["version"])
        self.assertGreaterEqual(len(document["paths"]), 80)

    def test_core_read_endpoints_respond(self):
        for route in (
            "/config/version",
            "/profiles",
            "/queue/downloads",
            "/queue/downloads/state",
            "/library",
            "/statistics",
            "/accounts/health",
            "/system/diagnostics",
        ):
            with self.subTest(route=route):
                self.assertEqual(self.client.get(route).status_code, 200)

    def test_config_response_is_flat_and_does_not_expose_secrets(self):
        with patch("onthespot.main.config.get") as config_get:
            config_get.return_value = None
            response = self.client.get("/config/get")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("version", payload)
        self.assertNotIn("_Config__config", payload)
        self.assertNotIn("_Config__template_data", payload)
        self.assertEqual(payload["spotify_webapi_override_client_secret"], "")

    def test_pending_and_parsing_endpoints_do_not_leak_queue_internals(self):
        for route in ("/queue/pending", "/queue/parsing"):
            with self.subTest(route=route):
                response = self.client.get(route)
                self.assertEqual(response.status_code, 200)
                payload = response.json()
                self.assertEqual(set(payload), {"items", "count"})
                self.assertIsInstance(payload["items"], list)
                self.assertEqual(payload["count"], len(payload["items"]))
                self.assertNotIn("_queue", payload)

    def test_spotify_playback_mirror_endpoint_controls_worker(self):
        with patch("onthespot.main.spotifymirrorworker") as worker:
            enabled = self.client.post("/spotify/mirror?state=true")
            disabled = self.client.post("/spotify/mirror?state=false")

        self.assertEqual(enabled.status_code, 200)
        self.assertEqual(enabled.json(), {"enabled": True})
        self.assertEqual(disabled.status_code, 200)
        self.assertEqual(disabled.json(), {"enabled": False})
        worker.start.assert_called_once_with()
        worker.stop.assert_called_once_with()

    def test_cross_service_search_returns_results_without_enqueueing(self):
        provider_result = {
            "item_id": "track-1",
            "item_name": "Example Track",
            "item_by": "Example Artist",
            "item_type": "track",
            "item_service": "bandcamp",
            "item_url": "https://example.test/track-1",
            "item_thumbnail_url": "https://example.test/cover.jpg",
        }
        with (
            patch("onthespot.main.account_pool", [{"service": "bandcamp"}]),
            patch.dict(
                "onthespot.main.SERVICE_SEARCH_FUNCTIONS",
                {"bandcamp": lambda _token, _query, _types: [provider_result]},
                clear=True,
            ),
        ):
            results = search_service_catalogs("Example", {"tracks": True})

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["id"], "bandcamp:track:track-1")
        self.assertEqual(results[0]["name"], "Example Track")
        self.assertEqual(results[0]["item_url"], "https://example.test/track-1")

    def test_cross_service_search_honours_selected_services(self):
        def provider(service):
            return lambda _token, _query, _types: [
                {
                    "item_id": f"{service}-track",
                    "item_name": f"{service} Track",
                    "item_by": "Artist",
                    "item_type": "track",
                    "item_service": service,
                    "item_url": f"https://example.test/{service}-track",
                }
            ]

        with (
            patch(
                "onthespot.main.account_pool",
                [{"service": "bandcamp"}, {"service": "youtube_music"}],
            ),
            patch.dict(
                "onthespot.main.SERVICE_SEARCH_FUNCTIONS",
                {
                    "bandcamp": provider("bandcamp"),
                    "youtube_music": provider("youtube_music"),
                },
                clear=True,
            ),
        ):
            results = search_service_catalogs(
                "Example",
                {"tracks": True, "services": ["youtube_music"]},
            )

        self.assertEqual([item["item_service"] for item in results], ["youtube_music"])

    def test_cross_service_search_interleaves_provider_results(self):
        def provider(service, count):
            return lambda _token, _query, _types: [
                {
                    "item_id": f"{service}-track-{index}",
                    "item_name": f"{service} Track {index}",
                    "item_by": "Artist",
                    "item_type": "track",
                    "item_service": service,
                    "item_url": f"https://example.test/{service}-track-{index}",
                }
                for index in range(count)
            ]

        with (
            patch(
                "onthespot.main.account_pool",
                [{"service": "soundcloud"}, {"service": "spotify"}],
            ),
            patch(
                "onthespot.main.get_account_token",
                side_effect=lambda service: f"{service}-token",
            ),
            patch.dict(
                "onthespot.main.SERVICE_SEARCH_FUNCTIONS",
                {
                    "soundcloud": provider("soundcloud", 3),
                    "spotify": provider("spotify", 2),
                },
                clear=True,
            ),
        ):
            results = search_service_catalogs(
                "Example",
                {"tracks": True, "services": ["soundcloud", "spotify"]},
            )

        self.assertEqual(
            [item["item_service"] for item in results],
            ["soundcloud", "spotify", "soundcloud", "spotify", "soundcloud"],
        )

    def test_cross_service_search_with_no_selected_services_returns_nothing(self):
        with patch("onthespot.main.account_pool", [{"service": "bandcamp"}]):
            results = search_service_catalogs(
                "Example",
                {"tracks": True, "services": []},
            )

        self.assertEqual(results, [])

    def test_cross_service_search_only_sends_supported_types_to_each_provider(self):
        received_types = {}

        def provider(service):
            def search_provider(_token, _query, content_types):
                received_types[service] = content_types
                return []

            return search_provider

        with (
            patch(
                "onthespot.main.account_pool",
                [{"service": "spotify"}, {"service": "crunchyroll"}],
            ),
            patch(
                "onthespot.main.get_account_token",
                side_effect=lambda service: f"{service}-token",
            ),
            patch.dict(
                "onthespot.main.SERVICE_SEARCH_FUNCTIONS",
                {
                    "spotify": provider("spotify"),
                    "crunchyroll": provider("crunchyroll"),
                },
                clear=True,
            ),
        ):
            search_service_catalogs(
                "Example",
                {
                    "tracks": True,
                    "albums": True,
                    "playlists": True,
                    "artists": True,
                    "podcasts": True,
                    "movies": True,
                },
            )

        self.assertEqual(
            set(received_types["spotify"]),
            {"track", "album", "playlist", "artist", "show", "episode"},
        )
        self.assertNotIn("movie", received_types["spotify"])
        self.assertEqual(
            set(received_types["crunchyroll"]),
            {"movie", "show", "episode"},
        )

    def test_playlist_redirect_normalizes_localhost_to_loopback(self):
        self.assertEqual(
            normalize_playlist_redirect_uri(
                "http://localhost:4321/playlist-automation/callback"
            ),
            "http://127.0.0.1:4321/playlist-automation/callback",
        )

    def test_playlist_redirect_rejects_insecure_lan_address(self):
        with self.assertRaises(PlaylistAutomationError):
            normalize_playlist_redirect_uri(
                "http://192.168.1.3:6767/playlist-automation/callback"
            )

    def test_cors_allows_local_vite_but_not_arbitrary_origins(self):
        headers = {
            "Access-Control-Request-Method": "GET",
            "Origin": "http://localhost:3000",
        }
        allowed = self.client.options("/config/version", headers=headers)
        self.assertEqual(allowed.status_code, 200)
        self.assertEqual(
            allowed.headers.get("access-control-allow-origin"),
            "http://localhost:3000",
        )

        headers["Origin"] = "https://untrusted.example"
        blocked = self.client.options("/config/version", headers=headers)
        self.assertNotIn("access-control-allow-origin", blocked.headers)


if __name__ == "__main__":
    unittest.main()
