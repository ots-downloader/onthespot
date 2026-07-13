"""Spotify playlist automation services for the OnTheSpot web UI.

This module deliberately keeps playlist-management OAuth separate from the
download account pool. Download accounts are service sessions; playlist
automation needs a Spotify user token with playlist modification scopes.
"""

from __future__ import annotations

import csv
import io
import json
import os
import re
import threading
import time
import uuid
from datetime import datetime, timedelta
from typing import Any
from urllib.parse import urlencode

import requests

from .otsconfig import config
from .runtimedata import record_rate_limit
from .export_locations import playlist_backup_directory


BASE_URL = "https://api.spotify.com/v1"
AUTH_URL = "https://accounts.spotify.com/authorize"
TOKEN_URL = "https://accounts.spotify.com/api/token"
SCOPES = "playlist-read-private playlist-read-collaborative playlist-modify-public playlist-modify-private user-library-read"
DEFAULT_SORT_RULES = [
    {"id": "release-date", "field": "release_date", "descending": True},
    {"id": "artist", "field": "artist", "descending": False},
    {"id": "album", "field": "album", "descending": False},
    {"id": "track-name", "field": "name", "descending": False},
]
SORTER_DUPE_PREFERENCES = {
    "Keep Oldest (Release Date)",
    "Keep Newest (Release Date)",
    "Keep Oldest (Playlist Order)",
    "Keep Newest (Playlist Order)",
}
SORTER_VERSION_PREFERENCES = {
    "Artist Only: Oldest Version",
    "Artist Only: Newest Version",
    "Global: Oldest Version",
    "Global: Newest Version",
}


class PlaylistAutomationError(RuntimeError):
    """A user-facing playlist automation failure."""


class PlaylistAutomation:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._oauth_state = ""
        self._token: dict[str, Any] = {}
        self._scheduler_stop = threading.Event()
        self._scheduler_thread: threading.Thread | None = None
        self._state_path = os.path.join(
            str(config.get("_cache_dir") or os.path.join(os.path.expanduser("~"), ".onthespot")),
            "playlist-automation.json",
        )

    def _backup_directory(self) -> str:
        return playlist_backup_directory()

    def _load_state(self) -> dict[str, Any]:
        try:
            with open(self._state_path, "r", encoding="utf-8") as handle:
                value = json.load(handle)
            if isinstance(value, dict):
                value.setdefault("configs", [])
                value.setdefault("history", [])
                value.setdefault("ignored_tracks", [])
                value.setdefault("schedules", [])
                return value
        except (OSError, json.JSONDecodeError):
            pass
        return {"configs": [], "history": [], "ignored_tracks": [], "schedules": []}

    def _save_state(self, value: dict[str, Any]) -> None:
        try:
            os.makedirs(os.path.dirname(self._state_path), exist_ok=True)
            temporary = f"{self._state_path}.tmp"
            with open(temporary, "w", encoding="utf-8") as handle:
                json.dump(value, handle, indent=2, ensure_ascii=False)
            os.replace(temporary, self._state_path)
        except OSError as exc:
            raise PlaylistAutomationError(f"Could not save playlist automation state: {exc}") from exc

    def _client_id(self) -> str:
        return str(config.get("playlist_automation_client_id") or config.get("spotify_webapi_override_client_id") or "").strip()

    def _client_secret(self) -> str:
        return str(config.get("playlist_automation_client_secret") or config.get("spotify_webapi_override_client_secret") or "").strip()

    def credentials_source(self) -> str:
        if config.get("playlist_automation_client_id") and config.get("playlist_automation_client_secret"):
            return "Playlist automation settings"
        if config.get("spotify_webapi_override_client_id") and config.get("spotify_webapi_override_client_secret"):
            return "API config"
        return "Not configured"

    def redirect_uri(self) -> str:
        configured = str(config.get("playlist_automation_redirect_uri") or "").strip()
        return configured or "http://localhost:6767/playlist-automation/callback"

    def status(self) -> dict[str, Any]:
        with self._lock:
            token = self._token
            authenticated = bool(token.get("access_token") and float(token.get("expires_at", 0)) > time.time())
            return {
                "configured": bool(self._client_id() and self._client_secret()),
                "authenticated": authenticated or bool(token.get("refresh_token")),
                "redirect_uri": self.redirect_uri(),
                "scope": SCOPES,
                "credentials_source": self.credentials_source(),
                "user": token.get("user"),
            }

    def configure(self, client_id: str, client_secret: str, redirect_uri: str = "") -> dict[str, Any]:
        client_id = client_id.strip()
        client_secret = client_secret.strip()
        if bool(client_id) != bool(client_secret):
            raise PlaylistAutomationError("Enter both the Spotify Client ID and Client Secret")
        if client_id and client_secret:
            config.set("playlist_automation_client_id", client_id)
            config.set("playlist_automation_client_secret", client_secret)
        elif not self._client_id() or not self._client_secret():
            raise PlaylistAutomationError("Configure Spotify Client ID and Client Secret in Settings → API config first")
        if redirect_uri.strip():
            config.set("playlist_automation_redirect_uri", redirect_uri.strip())
        config.save()
        return self.status()

    def login_url(self) -> str:
        if not self._client_id() or not self._client_secret():
            raise PlaylistAutomationError("Configure Spotify Client ID and Client Secret first")
        with self._lock:
            self._oauth_state = uuid.uuid4().hex
        return f"{AUTH_URL}?{urlencode({'client_id': self._client_id(), 'response_type': 'code', 'redirect_uri': self.redirect_uri(), 'scope': SCOPES, 'state': self._oauth_state, 'show_dialog': 'false'})}"

    def callback(self, code: str, state: str | None) -> None:
        with self._lock:
            if not state or state != self._oauth_state:
                raise PlaylistAutomationError("Spotify OAuth state validation failed")
        response = requests.post(
            TOKEN_URL,
            data={"grant_type": "authorization_code", "code": code, "redirect_uri": self.redirect_uri()},
            auth=(self._client_id(), self._client_secret()),
            timeout=20,
        )
        if not response.ok:
            raise PlaylistAutomationError(f"Spotify token exchange failed ({response.status_code})")
        payload = response.json()
        with self._lock:
            self._token = {
                "access_token": payload.get("access_token", ""),
                "refresh_token": payload.get("refresh_token", ""),
                "expires_at": time.time() + int(payload.get("expires_in", 3600)) - 60,
                "scope": payload.get("scope", SCOPES),
            }
            self._save_token()

    def _save_token(self) -> None:
        state = self._load_state()
        state["oauth"] = {key: self._token.get(key) for key in ("access_token", "refresh_token", "expires_at", "scope", "user")}
        self._save_state(state)

    def _restore_token(self) -> None:
        if self._token:
            return
        state = self._load_state()
        oauth = state.get("oauth") if isinstance(state.get("oauth"), dict) else {}
        self._token = dict(oauth)

    def _access_token(self) -> str:
        with self._lock:
            self._restore_token()
            if self._token.get("access_token") and float(self._token.get("expires_at", 0)) > time.time():
                return str(self._token["access_token"])
            refresh_token = str(self._token.get("refresh_token") or "")
        if not refresh_token:
            raise PlaylistAutomationError("Connect your Spotify account before using playlist automation")
        response = requests.post(
            TOKEN_URL,
            data={"grant_type": "refresh_token", "refresh_token": refresh_token},
            auth=(self._client_id(), self._client_secret()),
            timeout=20,
        )
        if not response.ok:
            raise PlaylistAutomationError("Spotify session expired; connect again")
        payload = response.json()
        with self._lock:
            self._token["access_token"] = payload.get("access_token", "")
            self._token["expires_at"] = time.time() + int(payload.get("expires_in", 3600)) - 60
            if payload.get("refresh_token"):
                self._token["refresh_token"] = payload["refresh_token"]
            self._save_token()
            return str(self._token["access_token"])

    def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        token = self._access_token()
        headers = dict(kwargs.pop("headers", {}) or {})
        headers["Authorization"] = f"Bearer {token}"
        headers.setdefault("Content-Type", "application/json")
        response = requests.request(method, f"{BASE_URL}{path}", headers=headers, timeout=30, **kwargs)
        if response.status_code == 401:
            with self._lock:
                self._token["expires_at"] = 0
            token = self._access_token()
            headers["Authorization"] = f"Bearer {token}"
            response = requests.request(method, f"{BASE_URL}{path}", headers=headers, timeout=30, **kwargs)
        if response.status_code == 429:
            try:
                retry_after = max(0, int(float(response.headers.get("Retry-After", "0") or 0)))
            except ValueError:
                retry_after = 0
            record_rate_limit("api.spotify.com", retry_after, retry_after)
        if not response.ok:
            detail = ""
            try:
                detail = str(response.json().get("error", {}).get("message", ""))
            except (ValueError, AttributeError):
                detail = response.text[:200]
            raise PlaylistAutomationError(f"Spotify API error ({response.status_code}){': ' + detail if detail else ''}")
        if response.status_code == 204 or not response.content:
            return {}
        return response.json()

    def _remember_user(self) -> None:
        if self._token.get("user"):
            return
        try:
            self._token["user"] = self._request("GET", "/me")
            self._save_token()
        except PlaylistAutomationError:
            return

    def logout(self) -> None:
        with self._lock:
            self._token = {}
            state = self._load_state()
            state.pop("oauth", None)
            self._save_state(state)

    def playlists(self) -> list[dict[str, Any]]:
        self._remember_user()
        rows: list[dict[str, Any]] = []
        offset = 0
        while True:
            payload = self._request("GET", "/me/playlists", params={"limit": 50, "offset": offset})
            for item in payload.get("items", []) or []:
                owner = (item.get("owner") or {}).get("display_name") or (item.get("owner") or {}).get("id") or ""
                rows.append({
                    "id": item.get("id", ""),
                    "name": item.get("name", ""),
                    "owner": owner,
                    "editable": bool(item.get("collaborative") or owner == (self._token.get("user") or {}).get("display_name") or owner == (self._token.get("user") or {}).get("id")),
                    "collaborative": bool(item.get("collaborative")),
                    "public": bool(item.get("public")),
                    "tracks": int((item.get("tracks") or {}).get("total", 0) or 0),
                    "image": ((item.get("images") or [{}])[0] or {}).get("url", ""),
                })
            if not payload.get("next"):
                break
            offset += len(payload.get("items", []) or [])
        return rows

    @staticmethod
    def _track_from_payload(track: dict[str, Any], added_at: str = "") -> dict[str, Any]:
        album = track.get("album") or {}
        artists = track.get("artists") or []
        return {
            "id": track.get("id", ""),
            "uri": track.get("uri", ""),
            "name": track.get("name", ""),
            "artist": ", ".join(str(artist.get("name", "")) for artist in artists),
            "album": album.get("name", ""),
            "album_artist": ", ".join(str(artist.get("name", "")) for artist in (album.get("artists") or [])),
            "album_type": album.get("album_type", ""),
            "release_date": album.get("release_date") or "",
            "track_number": track.get("track_number", 0),
            "disc_number": track.get("disc_number", 0),
            "duration_ms": track.get("duration_ms", 0),
            "explicit": bool(track.get("explicit")),
            "popularity": int(track.get("popularity", 0) or 0),
            "added_at": added_at,
        }

    def _add_audio_features(self, tracks: list[dict[str, Any]]) -> None:
        ids = [str(track.get("id")) for track in tracks if track.get("id")]
        for start in range(0, len(ids), 100):
            try:
                payload = self._request("GET", "/audio-features", params={"ids": ",".join(ids[start:start + 100])})
            except PlaylistAutomationError:
                return
            by_id = {str(item.get("id")): item for item in payload.get("audio_features", []) or [] if item}
            for track in tracks[start:start + 100]:
                feature = by_id.get(str(track.get("id")))
                if not feature:
                    continue
                track["bpm"] = float(feature.get("tempo", 0) or 0)
                track["energy"] = float(feature.get("energy", 0) or 0)
                track["danceability"] = float(feature.get("danceability", 0) or 0)
                track["valence"] = float(feature.get("valence", 0) or 0)

    def playlist_tracks(self, playlist_id: str) -> list[dict[str, Any]]:
        tracks: list[dict[str, Any]] = []
        offset = 0
        while True:
            payload = self._request("GET", f"/playlists/{playlist_id}/items", params={"limit": 100, "offset": offset, "fields": "items(added_at,track(id,uri,name,duration_ms,explicit,popularity,track_number,disc_number,artists,album)),next,total"})
            for item in payload.get("items", []) or []:
                track = item.get("track") or {}
                if not track.get("uri") or track.get("is_local"):
                    continue
                tracks.append(self._track_from_payload(track, item.get("added_at", "")))
            if not payload.get("next"):
                break
            offset += len(payload.get("items", []) or [])
        self._add_audio_features(tracks)
        return tracks

    @staticmethod
    def _version_key(track: dict[str, Any]) -> str:
        value = f"{track.get('artist', '')} {track.get('name', '')}".casefold()
        value = re.sub(r"[\[(](?:\d{4}\s*)?(?:\d{2,4}\s*)?(?:remaster(?:ed)?|deluxe(?: edition)?|anniversary edition|radio edit|explicit version|album version)[^\])]*[\])", "", value)
        value = re.sub(r"\s[-–]\s*(?:\d{4}\s*)?(?:remaster(?:ed)?|deluxe(?: edition)?|anniversary edition|radio edit|explicit version|album version)\b.*$", "", value)
        return re.sub(r"\s+", " ", value).strip()

    @staticmethod
    def _sort_value(track: dict[str, Any], field: str) -> Any:
        if field in {"artist", "primary_artist"}:
            return str(track.get("artist", "")).casefold()
        if field in {"album", "album_name"}:
            return str(track.get("album", "")).casefold()
        if field in {"name", "track_name", "title"}:
            return str(track.get("name", "")).casefold()
        if field in {"release_date", "date", "release"}:
            raw = str(track.get("release_date", ""))
            try:
                return datetime.fromisoformat(raw).date().toordinal()
            except ValueError:
                return 0
        if field in {"duration", "duration_ms"}:
            return int(track.get("duration_ms", 0) or 0)
        if field == "popularity":
            return int(track.get("popularity", 0) or 0)
        if field == "explicit":
            return int(bool(track.get("explicit")))
        if field in {"bpm", "tempo"}:
            return float(track.get("bpm", 0) or 0)
        if field in {"energy", "danceability", "valence"}:
            return float(track.get(field, 0) or 0)
        return str(track.get(field, "")).casefold()

    def _sort_tracks(self, tracks: list[dict[str, Any]], rules: list[dict[str, Any]]) -> list[dict[str, Any]]:
        result = list(tracks)
        normalized = [rule for rule in rules if isinstance(rule, dict) and rule.get("field")]
        for rule in reversed(normalized):
            result.sort(key=lambda track, field=str(rule.get("field")): self._sort_value(track, field), reverse=bool(rule.get("descending")))
        return result

    def scan(self, body: dict[str, Any]) -> dict[str, Any]:
        playlist_ids = [str(value) for value in body.get("playlist_ids", []) if value]
        if not playlist_ids:
            raise PlaylistAutomationError("Select at least one source playlist")
        playlists = {row["id"]: row for row in self.playlists()}
        tracks: list[dict[str, Any]] = []
        source_names: dict[str, list[str]] = {}
        for playlist_id in playlist_ids:
            if playlist_id not in playlists:
                continue
            source_name = playlists[playlist_id]["name"]
            source_tracks = self.playlist_tracks(playlist_id)
            sample_per_source = body.get("sample_per_source")
            if sample_per_source:
                try:
                    source_tracks = source_tracks[:max(1, int(sample_per_source))]
                except (TypeError, ValueError):
                    pass
            for track in source_tracks:
                track["source_playlist_id"] = playlist_id
                track["source_playlist"] = source_name
                source_names.setdefault(track["id"], []).append(source_name)
                tracks.append(track)
        if body.get("include_liked_songs"):
            offset = 0
            while True:
                payload = self._request("GET", "/me/tracks", params={"limit": 50, "offset": offset})
                items = payload.get("items", []) or []
                for item in items:
                    track = item.get("track") or {}
                    if not track.get("uri") or track.get("is_local"):
                        continue
                    normalised = self._track_from_payload(track, item.get("added_at", ""))
                    normalised["source_playlist_id"] = "liked-songs"
                    normalised["source_playlist"] = "Liked Songs"
                    source_names.setdefault(normalised["id"], []).append("Liked Songs")
                    tracks.append(normalised)
                if not payload.get("next"):
                    break
                offset += len(items)
        state = self._load_state()
        ignored = {str(item.get("track_id")) for item in state.get("ignored_tracks", []) if isinstance(item, dict)}
        if ignored:
            tracks = [track for track in tracks if track.get("id") not in ignored]
        if body.get("exclude_liked_songs"):
            liked_ids: set[str] = set()
            offset = 0
            while True:
                payload = self._request("GET", "/me/tracks", params={"limit": 50, "offset": offset, "fields": "items(track(id)),next"})
                items = payload.get("items", []) or []
                liked_ids.update(str((item.get("track") or {}).get("id")) for item in items if (item.get("track") or {}).get("id"))
                if not payload.get("next"):
                    break
                offset += len(items)
            tracks = [track for track in tracks if str(track.get("id")) not in liked_ids]
        original_count = len(tracks)
        duplicates_removed = 0
        if body.get("deduplicate"):
            preference = str(body.get("dupe_preference") or "Keep Oldest (Release Date)")
            groups: dict[str, list[tuple[int, dict[str, Any]]]] = {}
            for index, track in enumerate(tracks):
                groups.setdefault(self._duplicate_key(track), []).append((index, track))
            unique: list[dict[str, Any]] = []
            for items in groups.values():
                if preference == "Keep Newest (Playlist Order)":
                    chosen = items[-1]
                elif preference == "Keep Newest (Release Date)":
                    chosen = max(items, key=lambda item: self._release_key(str(item[1].get("release_date", ""))))
                elif preference == "Keep Oldest (Playlist Order)":
                    chosen = items[0]
                else:
                    chosen = min(items, key=lambda item: self._release_key(str(item[1].get("release_date", ""))))
                unique.append(chosen[1])
                duplicates_removed += len(items) - 1
            tracks = unique
        versions_replaced = 0
        if body.get("version_replacer"):
            best: dict[str, dict[str, Any]] = {}
            for track in tracks:
                key = self._version_key(track)
                current = best.get(key)
                newest = "Newest" in str(body.get("version_preference") or "")
                release_score = self._release_key(str(track.get("release_date", "")))
                score = (release_score, int(track.get("popularity", 0) or 0), int(track.get("duration_ms", 0) or 0)) if newest else tuple(-part for part in release_score) + (int(track.get("popularity", 0) or 0), int(track.get("duration_ms", 0) or 0))
                old_score = ((self._release_key(str(current.get("release_date", ""))), int(current.get("popularity", 0) or 0), int(current.get("duration_ms", 0) or 0)) if newest else tuple(-part for part in self._release_key(str(current.get("release_date", "")))) + (int(current.get("popularity", 0) or 0), int(current.get("duration_ms", 0) or 0))) if current else (None,)
                if current and score > old_score:
                    versions_replaced += 1
                if current is None or score > old_score:
                    best[key] = track
            tracks = list(best.values())
        exclusions = [str(value).casefold().strip() for value in body.get("exclude_keywords", []) if str(value).strip()]
        if exclusions:
            tracks = [track for track in tracks if not any(keyword in f"{track.get('name', '')} {track.get('artist', '')}".casefold() for keyword in exclusions)]
        if body.get("sort_enabled", True):
            tracks = self._sort_tracks(tracks, body.get("sort_rules") or DEFAULT_SORT_RULES)
        for track in tracks:
            track["source_playlists"] = source_names.get(track.get("id", ""), [])
        return {
            "source_playlist_count": len(playlist_ids),
            "original_count": original_count,
            "track_count": len(tracks),
            "duplicates_removed": duplicates_removed,
            "versions_replaced": versions_replaced,
            "tracks": tracks,
            "uris": [track["uri"] for track in tracks if track.get("uri")],
        }

    @staticmethod
    def _release_key(value: str) -> tuple[int, int, int]:
        parts = str(value or "").split("-")
        try:
            return (int(parts[0]), int(parts[1]) if len(parts) > 1 else 1, int(parts[2]) if len(parts) > 2 else 1)
        except (ValueError, IndexError):
            return (0, 1, 1)

    @staticmethod
    def _normalise_title(value: str) -> str:
        return re.sub(r"[^\w\s]", "", str(value or "").casefold()).strip()

    @classmethod
    def _version_title_key(cls, value: str) -> str:
        value = str(value or "").casefold()
        value = re.sub(r"[\[(](?:\d{4}\s*)?(?:\d{2,4}\s*)?(?:remaster(?:ed)?|deluxe(?: edition)?|anniversary edition|radio edit|single version|explicit version|album version)[^\])]*[\])]", "", value)
        value = re.sub(r"\s[-–]\s*(?:\d{4}\s*)?(?:\d{2,4}\s*)?(?:remaster(?:ed)?|deluxe(?: edition)?|anniversary edition|radio edit|single version|explicit version|album version)\b.*$", "", value)
        return cls._normalise_title(value)

    @classmethod
    def _primary_artist(cls, track: dict[str, Any]) -> str:
        return str(track.get("artist", "")).split(",", 1)[0].strip().casefold()

    @classmethod
    def _duplicate_key(cls, track: dict[str, Any]) -> str:
        return f"{cls._normalise_title(str(track.get('name', '')))}|{cls._primary_artist(track)}"

    def _version_ignored(self, track: dict[str, Any]) -> bool:
        title_key = self._version_title_key(str(track.get("name", "")))
        artist_key = self._primary_artist(track)
        for item in self._load_state().get("ignored_tracks", []):
            if not isinstance(item, dict):
                continue
            if str(item.get("track_id") or item.get("id") or "") == str(track.get("id") or ""):
                return True
            if self._version_title_key(str(item.get("name") or item.get("title") or "")) == title_key and str(item.get("artist") or "").split(",", 1)[0].strip().casefold() == artist_key:
                return True
        return False

    def _version_candidates(self, track: dict[str, Any], preference: str) -> list[dict[str, Any]]:
        global_search = preference.startswith("Global:")
        query = f"track:{track.get('name', '')}"
        if not global_search:
            query += f" artist:{self._primary_artist(track)}"
        payload = self._request("GET", "/search", params={"q": query, "type": "track", "limit": 20})
        title_key = self._version_title_key(str(track.get("name", "")))
        artist_key = self._primary_artist(track)
        candidates: list[dict[str, Any]] = []
        for raw in ((payload.get("tracks") or {}).get("items") or []):
            candidate = self._track_from_payload(raw)
            if candidate.get("id") == track.get("id"):
                continue
            if self._version_title_key(str(candidate.get("name", ""))) != title_key or self._primary_artist(candidate) != artist_key:
                continue
            candidates.append(candidate)
        return candidates

    def sort_scan(self, body: dict[str, Any]) -> list[dict[str, Any]]:
        playlist_ids = [str(value) for value in body.get("playlist_ids", []) if value]
        if not playlist_ids:
            raise PlaylistAutomationError("Select at least one playlist to sort")
        playlists = {row["id"]: row for row in self.playlists()}
        sort_enabled = bool(body.get("sort_enabled", True))
        rules = body.get("sort_rules") or DEFAULT_SORT_RULES
        dupe_enabled = bool(body.get("dupes_enabled", body.get("deduplicate", False)))
        dupe_preference = str(body.get("dupe_preference") or "Keep Oldest (Release Date)")
        if dupe_preference not in SORTER_DUPE_PREFERENCES:
            dupe_preference = "Keep Oldest (Release Date)"
        version_enabled = bool(body.get("version_enabled", body.get("version_replacer", False)))
        version_preference = str(body.get("version_preference") or "Artist Only: Oldest Version")
        if version_preference not in SORTER_VERSION_PREFERENCES:
            version_preference = "Artist Only: Oldest Version"
        results: list[dict[str, Any]] = []
        for playlist_id in playlist_ids:
            playlist = playlists.get(playlist_id)
            if not playlist:
                continue
            original = self.playlist_tracks(playlist_id)
            working = list(original)
            changes: list[dict[str, Any]] = []
            duplicates_removed = 0
            if dupe_enabled:
                groups: dict[str, list[tuple[int, dict[str, Any]]]] = {}
                for index, track in enumerate(working):
                    groups.setdefault(self._duplicate_key(track), []).append((index, track))
                keep_indices: set[int] = set()
                for items in groups.values():
                    if len(items) == 1:
                        keep_indices.add(items[0][0])
                        continue
                    if dupe_preference == "Keep Oldest (Playlist Order)":
                        chosen = items[0]
                    elif dupe_preference == "Keep Newest (Playlist Order)":
                        chosen = items[-1]
                    elif dupe_preference == "Keep Newest (Release Date)":
                        chosen = max(items, key=lambda item: self._release_key(str(item[1].get("release_date", ""))))
                    else:
                        chosen = min(items, key=lambda item: self._release_key(str(item[1].get("release_date", ""))))
                    keep_indices.add(chosen[0])
                    for index, track in items:
                        if index == chosen[0]:
                            continue
                        duplicates_removed += 1
                        changes.append({"id": uuid.uuid4().hex, "type": "duplicate", "track_uri": track.get("uri"), "original_uri": track.get("uri"), "original_index": index, "remTitle": track.get("name"), "remArtist": track.get("artist"), "remAlbum": track.get("album"), "remDate": track.get("release_date"), "track_id": track.get("id")})
                working = [track for index, track in enumerate(working) if index in keep_indices]
            versions_replaced = 0
            if version_enabled:
                for index, track in enumerate(list(working)):
                    if self._version_ignored(track):
                        continue
                    try:
                        candidates = self._version_candidates(track, version_preference)
                    except PlaylistAutomationError:
                        candidates = []
                    if not candidates:
                        continue
                    newest = "Newest" in version_preference
                    current_date = self._release_key(str(track.get("release_date", "")))
                    eligible = [candidate for candidate in candidates if (self._release_key(str(candidate.get("release_date", ""))) > current_date if newest else self._release_key(str(candidate.get("release_date", ""))) < current_date)]
                    if not eligible:
                        continue
                    target_date = (max if newest else min)(self._release_key(str(candidate.get("release_date", ""))) for candidate in eligible)
                    best = next(candidate for candidate in eligible if self._release_key(str(candidate.get("release_date", ""))) == target_date)
                    changes.append({"id": uuid.uuid4().hex, "type": "replace", "track_uri": best.get("uri"), "original_uri": track.get("uri"), "original_index": index, "track_id": best.get("id"), "newTitle": best.get("name"), "newArtist": best.get("artist"), "newAlbum": best.get("album"), "newDate": best.get("release_date"), "remTitle": track.get("name"), "remArtist": track.get("artist"), "remAlbum": track.get("album"), "remDate": track.get("release_date")})
                    working[index] = best
                    versions_replaced += 1
            sorted_tracks = self._sort_tracks(working, rules) if sort_enabled else working
            results.append({"playlist_id": playlist_id, "name": playlist.get("name", playlist_id), "changes": changes, "stats": {"original_count": len(original), "duplicates_removed": duplicates_removed, "versions_replaced": versions_replaced, "sorted": bool(sort_enabled and [track.get("uri") for track in sorted_tracks] != [track.get("uri") for track in working])}, "preview_uris": [track.get("uri") for track in sorted_tracks if track.get("uri")]})
        return results

    def sort_apply(self, body: dict[str, Any]) -> dict[str, Any]:
        playlist_id = str(body.get("playlist_id") or "")
        if not playlist_id:
            raise PlaylistAutomationError("A playlist is required")
        original = self.playlist_tracks(playlist_id)
        approved = body.get("approved_changes") or []
        rejected = body.get("rejected_changes") or []
        removals: dict[str, int] = {}
        replacements: dict[str, dict[str, Any]] = {}
        for change in approved:
            original_uri = str(change.get("original_uri") or change.get("originalUri") or "")
            if change.get("type") == "duplicate" and original_uri:
                removals[original_uri] = removals.get(original_uri, 0) + 1
            elif change.get("type") == "replace" and original_uri:
                replacements[original_uri] = change
        working: list[dict[str, Any]] = []
        for track in original:
            uri = str(track.get("uri") or "")
            if removals.get(uri, 0):
                removals[uri] -= 1
                continue
            change = replacements.get(uri)
            if change:
                track = {**track, "id": change.get("track_id") or track.get("id"), "uri": change.get("track_uri") or uri, "name": change.get("newTitle") or track.get("name"), "artist": change.get("newArtist") or track.get("artist"), "album": change.get("newAlbum") or track.get("album"), "release_date": change.get("newDate") or track.get("release_date")}
            working.append(track)
        if bool(body.get("sort_enabled", True)):
            working = self._sort_tracks(working, body.get("sort_rules") or DEFAULT_SORT_RULES)
        before = [track.get("uri") for track in original if track.get("uri")]
        after = [track.get("uri") for track in working if track.get("uri")]
        self._request("PUT", f"/playlists/{playlist_id}/items", json={"uris": after[:100]})
        for start in range(100, len(after), 100):
            self._request("POST", f"/playlists/{playlist_id}/items", json={"uris": after[start:start + 100]})
        state = self._load_state()
        for change in rejected:
            entry = {"track_id": str(change.get("track_id") or ""), "name": str(change.get("remTitle") or ""), "artist": str(change.get("remArtist") or ""), "album": str(change.get("remAlbum") or ""), "context": "Version replacement" if change.get("type") == "replace" else "Duplicate removal", "source_playlist": playlist_id, "added_at": int(time.time())}
            if entry["track_id"] or entry["name"]:
                state["ignored_tracks"] = [item for item in state.get("ignored_tracks", []) if not (item.get("track_id") == entry["track_id"] and item.get("source_playlist") == playlist_id)]
                state["ignored_tracks"].append(entry)
        playlist_name = next((item.get("name") for item in self.playlists() if item.get("id") == playlist_id), playlist_id)
        record = {"id": uuid.uuid4().hex, "timestamp": int(time.time()), "action": "sort", "playlist_id": playlist_id, "playlist_name": playlist_name, "before": before, "after": after, "tracks_processed": len(after), "changes": approved, "ignored": rejected}
        state["history"] = [record, *state.get("history", [])][:100]
        self._save_state(state)
        return {"success": True, "playlist_name": playlist_name, "tracks_processed": len(after), "history_id": record["id"]}

    def _write_playlist(self, playlist_id: str, uris: list[str], mode: str) -> tuple[list[str], list[str]]:
        current_tracks = self.playlist_tracks(playlist_id)
        before = [track["uri"] for track in current_tracks if track.get("uri")]
        mode = mode if mode in {"replace", "merge", "append"} else "replace"
        if mode == "replace":
            after = list(dict.fromkeys(uris))
            self._request("PUT", f"/playlists/{playlist_id}/items", json={"uris": after})
        elif mode == "merge":
            after = list(dict.fromkeys(before + uris))
            self._request("PUT", f"/playlists/{playlist_id}/items", json={"uris": after})
        else:
            after = before + list(uris)
            for start in range(0, len(uris), 100):
                self._request("POST", f"/playlists/{playlist_id}/items", json={"uris": uris[start:start + 100]})
        return before, after

    def apply(self, body: dict[str, Any]) -> dict[str, Any]:
        target_id = str(body.get("target_playlist_id") or "")
        uris = [str(uri) for uri in body.get("uris", []) if uri]
        if not target_id:
            raise PlaylistAutomationError("Choose a target playlist first")
        before, after = self._write_playlist(target_id, uris, str(body.get("update_mode") or "replace"))
        playlist_name = next((item["name"] for item in self.playlists() if item["id"] == target_id), target_id)
        record = {"id": uuid.uuid4().hex, "timestamp": int(time.time()), "action": "update", "playlist_id": target_id, "playlist_name": playlist_name, "before": before, "after": after, "tracks_processed": len(uris)}
        with self._lock:
            state = self._load_state()
            state["history"] = [record, *state.get("history", [])][:100]
            self._save_state(state)
        return {"success": True, "playlist_name": playlist_name, "tracks_processed": len(uris), "history_id": record["id"]}

    def history(self) -> list[dict[str, Any]]:
        return self._load_state().get("history", [])

    def clear_history(self) -> None:
        with self._lock:
            state = self._load_state()
            state["history"] = []
            self._save_state(state)

    def delete_history(self, history_id: str) -> None:
        with self._lock:
            state = self._load_state()
            state["history"] = [item for item in state.get("history", []) if item.get("id") != history_id]
            self._save_state(state)

    def restore_history(self, history_id: str) -> dict[str, Any]:
        record = next((item for item in self.history() if item.get("id") == history_id), None)
        if not record:
            raise PlaylistAutomationError("History entry not found")
        self._request("PUT", f"/playlists/{record['playlist_id']}/items", json={"uris": record.get("before", [])})
        return {"success": True}

    def compare(self, playlist_ids: list[str]) -> dict[str, Any]:
        playlists = {row["id"]: row for row in self.playlists()}
        occurrences: dict[str, dict[str, Any]] = {}
        for playlist_id in playlist_ids:
            for track in self.playlist_tracks(playlist_id):
                key = self._version_key(track)
                entry = occurrences.setdefault(key, {"key": key, "name": track.get("name", ""), "artist": track.get("artist", ""), "track_id": track.get("id", ""), "found_in_playlists": []})
                name = playlists.get(playlist_id, {}).get("name", playlist_id)
                if name not in entry["found_in_playlists"]:
                    entry["found_in_playlists"].append(name)
        duplicates = [entry for entry in occurrences.values() if len(entry["found_in_playlists"]) > 1]
        return {"playlists_compared": len(playlist_ids), "duplicates": duplicates, "duplicate_count": len(duplicates)}

    def remove_track(self, playlist_id: str, track_uri: str) -> dict[str, Any]:
        self._request("DELETE", f"/playlists/{playlist_id}/items", json={"tracks": [{"uri": track_uri}]})
        return {"success": True}

    def ignored(self) -> list[dict[str, Any]]:
        return self._load_state().get("ignored_tracks", [])

    def ignore(self, track: dict[str, Any]) -> dict[str, Any]:
        entry = {"track_id": str(track.get("track_id") or track.get("id") or ""), "name": str(track.get("name") or ""), "artist": str(track.get("artist") or ""), "added_at": int(time.time())}
        if not entry["track_id"]:
            raise PlaylistAutomationError("A Spotify track id is required")
        with self._lock:
            state = self._load_state()
            state["ignored_tracks"] = [item for item in state.get("ignored_tracks", []) if item.get("track_id") != entry["track_id"]]
            state["ignored_tracks"].append(entry)
            self._save_state(state)
        return entry

    def remove_ignored(self, track_ids: list[str]) -> None:
        with self._lock:
            state = self._load_state()
            wanted = {str(value) for value in track_ids}
            state["ignored_tracks"] = [item for item in state.get("ignored_tracks", []) if item.get("track_id") not in wanted]
            self._save_state(state)

    def configs(self) -> list[dict[str, Any]]:
        return self._load_state().get("configs", [])

    @staticmethod
    def _next_schedule_timestamp(expression: str, base: float | None = None) -> float | None:
        parts = expression.split()
        if len(parts) != 5:
            return None
        minute, hour, day, month, weekday = parts
        current = datetime.fromtimestamp(base or time.time()).replace(second=0, microsecond=0)
        if minute == "0" and hour == "*" and day == "*" and month == "*" and weekday == "*":
            return current.timestamp() + 3600
        if minute == "0" and hour.startswith("*/") and day == "*" and month == "*" and weekday == "*":
            try:
                interval = max(1, int(hour.removeprefix("*/")))
            except ValueError:
                return None
            return current.timestamp() + interval * 3600
        try:
            target_minute = int(minute)
            target_hour = int(hour)
        except ValueError:
            return None
        for offset in range(0, 370):
            candidate = current.replace(hour=target_hour, minute=target_minute) + timedelta(days=offset)
            if candidate.timestamp() <= (base or time.time()) + 30:
                continue
            if month != "*" and candidate.month != int(month):
                continue
            if day != "*" and candidate.day != int(day):
                continue
            if weekday != "*" and candidate.weekday() != (int(weekday) - 1) % 7:
                continue
            return candidate.timestamp()
        return None

    def schedules(self) -> list[dict[str, Any]]:
        state = self._load_state()
        rows = state.get("schedules", []) if isinstance(state.get("schedules", []), list) else []
        changed = False
        for row in rows:
            if not row.get("next_run"):
                row["next_run"] = self._next_schedule_timestamp(str(row.get("cron_expression") or ""))
                changed = True
        if changed:
            self._save_state(state)
        return rows

    def save_schedule(self, value: dict[str, Any]) -> dict[str, Any]:
        cron_expression = str(value.get("cron_expression") or "0 0 * * *").strip()
        if len(cron_expression.split()) != 5:
            raise PlaylistAutomationError("Schedule must use a five-part cron expression")
        row = {"id": str(value.get("id") or uuid.uuid4().hex), "config_id": str(value.get("config_id") or ""), "cron_expression": cron_expression, "enabled": bool(value.get("enabled", True)), "last_run": value.get("last_run"), "next_run": self._next_schedule_timestamp(cron_expression)}
        with self._lock:
            state = self._load_state()
            state["schedules"] = [row, *[item for item in state.get("schedules", []) if item.get("id") != row["id"]]]
            self._save_state(state)
        return row

    def delete_schedule(self, schedule_id: str) -> None:
        with self._lock:
            state = self._load_state()
            state["schedules"] = [item for item in state.get("schedules", []) if item.get("id") != schedule_id]
            self._save_state(state)

    def _scheduler_loop(self) -> None:
        while not self._scheduler_stop.wait(30):
            try:
                now = time.time()
                rows = self.schedules()
                changed = False
                for row in rows:
                    if not row.get("enabled") or not row.get("config_id") or float(row.get("next_run") or 0) > now:
                        continue
                    try:
                        self.run_config(str(row["config_id"]))
                        row["last_run"] = int(time.time())
                    except PlaylistAutomationError:
                        row["last_run"] = int(time.time())
                    row["next_run"] = self._next_schedule_timestamp(str(row.get("cron_expression") or ""), now)
                    changed = True
                if changed:
                    with self._lock:
                        state = self._load_state()
                        state["schedules"] = rows
                        self._save_state(state)
            except Exception:
                continue

    def start_scheduler(self) -> None:
        if self._scheduler_thread and self._scheduler_thread.is_alive():
            return
        self._scheduler_stop.clear()
        self._scheduler_thread = threading.Thread(target=self._scheduler_loop, name="playlist-automation-scheduler", daemon=True)
        self._scheduler_thread.start()

    def stop_scheduler(self) -> None:
        self._scheduler_stop.set()
        if self._scheduler_thread:
            self._scheduler_thread.join(timeout=2)
        self._scheduler_thread = None

    def save_config(self, body: dict[str, Any], config_id: str | None = None) -> dict[str, Any]:
        value = dict(body)
        value["id"] = config_id or str(value.get("id") or uuid.uuid4().hex)
        value["name"] = str(value.get("name") or "Untitled automation").strip()
        value.setdefault("sort_rules", DEFAULT_SORT_RULES)
        value.setdefault("update_mode", "replace")
        with self._lock:
            state = self._load_state()
            existing = [item for item in state.get("configs", []) if item.get("id") != value["id"]]
            state["configs"] = [value, *existing]
            self._save_state(state)
        return value

    def delete_config(self, config_id: str) -> None:
        with self._lock:
            state = self._load_state()
            state["configs"] = [item for item in state.get("configs", []) if item.get("id") != config_id]
            self._save_state(state)

    def reorder_configs(self, config_ids: list[str]) -> list[dict[str, Any]]:
        with self._lock:
            state = self._load_state()
            configs = state.get("configs", []) if isinstance(state.get("configs", []), list) else []
            by_id = {str(item.get("id")): item for item in configs if isinstance(item, dict) and item.get("id")}
            ordered = [by_id.pop(config_id) for config_id in config_ids if config_id in by_id]
            ordered.extend(item for item in configs if str(item.get("id")) in by_id)
            state["configs"] = ordered
            self._save_state(state)
        return ordered

    def run_config(self, config_id: str) -> dict[str, Any]:
        item = next((value for value in self.configs() if value.get("id") == config_id), None)
        if not item:
            raise PlaylistAutomationError("Automation configuration not found")
        preview = self.scan({
            "playlist_ids": item.get("source_playlist_ids") or item.get("playlist_ids") or [],
            "sort_enabled": item.get("sort_enabled", True),
            "sort_rules": item.get("sort_rules") or DEFAULT_SORT_RULES,
            "deduplicate": item.get("deduplicate", False),
            "dupe_preference": item.get("dupe_preference", "Keep Oldest (Release Date)"),
            "version_replacer": item.get("version_replacer", False),
            "version_preference": item.get("version_preference", "Artist Only: Oldest Version"),
            "exclude_keywords": item.get("exclude_keywords") or [],
            "include_liked_songs": item.get("include_liked_songs", False),
            "exclude_liked_songs": item.get("exclude_liked_songs", False),
            "sample_per_source": item.get("sample_per_source"),
        })
        return self.apply({"target_playlist_id": item.get("target_playlist_id"), "uris": preview.get("uris", []), "update_mode": item.get("update_mode", "replace")})

    def run_all_configs(self) -> dict[str, Any]:
        configs = self.configs()
        by_target = {str(item.get("target_playlist_id")): str(item.get("id")) for item in configs if item.get("target_playlist_id") and item.get("id")}
        ordered: list[str] = []
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(config_id: str) -> None:
            if config_id in visited:
                return
            if config_id in visiting:
                raise PlaylistAutomationError("Circular dynamic playlist dependency detected")
            item = next((value for value in configs if str(value.get("id")) == config_id), None)
            if not item:
                return
            visiting.add(config_id)
            for source_id in item.get("source_playlist_ids") or []:
                dependency = by_target.get(str(source_id))
                if dependency:
                    visit(dependency)
            visiting.remove(config_id)
            visited.add(config_id)
            ordered.append(config_id)

        for item in configs:
            visit(str(item.get("id")))
        results = [self.run_config(config_id) for config_id in ordered]
        return {"success": True, "configs_processed": len(results), "results": results}

    def export_config(self) -> dict[str, Any]:
        state = self._load_state()
        return {"version": 1, "exported_at": int(time.time()), "sort_rules": DEFAULT_SORT_RULES, "configs": state.get("configs", []), "ignored_tracks": state.get("ignored_tracks", [])}

    def import_config(self, body: dict[str, Any]) -> None:
        if not isinstance(body, dict):
            raise PlaylistAutomationError("Automation config must be a JSON object")
        with self._lock:
            state = self._load_state()
            state["configs"] = body.get("configs", []) if isinstance(body.get("configs", []), list) else []
            state["ignored_tracks"] = body.get("ignored_tracks", []) if isinstance(body.get("ignored_tracks", []), list) else []
            self._save_state(state)

    def export_csv(self, tracks: list[dict[str, Any]]) -> str:
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["Track", "Artist", "Album", "Release date", "Spotify ID", "URI", "Source playlists"])
        for track in tracks:
            writer.writerow([track.get("name", ""), track.get("artist", ""), track.get("album", ""), track.get("release_date", ""), track.get("id", ""), track.get("uri", ""), "; ".join(track.get("source_playlists", []))])
        return output.getvalue()

    def export_playlists_csv(self, playlist_ids: list[str]) -> str:
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["Playlist", "Track", "Artist", "Album", "Release Date", "Spotify ID", "Spotify URI"])
        playlist_map = {row["id"]: row for row in self.playlists()}
        for playlist_id in playlist_ids:
            playlist = playlist_map.get(str(playlist_id))
            if not playlist:
                continue
            for track in self.playlist_tracks(str(playlist_id)):
                writer.writerow([playlist.get("name", playlist_id), track.get("name", ""), track.get("artist", ""), track.get("album", ""), track.get("release_date", ""), track.get("id", ""), track.get("uri", "")])
        return output.getvalue()

    def backups(self) -> list[dict[str, Any]]:
        try:
            backup_dir = self._backup_directory()
            os.makedirs(backup_dir, exist_ok=True)
            rows = []
            for filename in sorted(os.listdir(backup_dir), reverse=True):
                if not filename.endswith(".json"):
                    continue
                path = os.path.join(backup_dir, filename)
                try:
                    with open(path, "r", encoding="utf-8") as handle:
                        value = json.load(handle)
                    rows.append({"filename": filename, "created_at": value.get("created_at", 0), "playlists": len(value.get("playlists", []))})
                except (OSError, json.JSONDecodeError):
                    continue
            return rows
        except OSError:
            return []

    def create_backup(self, playlist_ids: list[str]) -> dict[str, Any]:
        if not playlist_ids:
            raise PlaylistAutomationError("Select at least one playlist to back up")
        playlist_map = {row["id"]: row for row in self.playlists()}
        value = {"version": 1, "created_at": int(time.time()), "playlists": []}
        for playlist_id in playlist_ids:
            if playlist_id not in playlist_map:
                continue
            value["playlists"].append({"playlist": playlist_map[playlist_id], "tracks": self.playlist_tracks(playlist_id)})
        if not value["playlists"]:
            raise PlaylistAutomationError("No selected playlists could be read")
        backup_dir = self._backup_directory()
        os.makedirs(backup_dir, exist_ok=True)
        filename = f"playlist-backup-{datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
        with open(os.path.join(backup_dir, filename), "w", encoding="utf-8") as handle:
            json.dump(value, handle, indent=2, ensure_ascii=False)
        return {"success": True, "filename": filename, "playlists": len(value["playlists"])}

    def restore_backup(self, filename: str, target_playlist_id: str = "") -> dict[str, Any]:
        safe_name = os.path.basename(filename)
        path = os.path.join(self._backup_directory(), safe_name)
        try:
            with open(path, "r", encoding="utf-8") as handle:
                value = json.load(handle)
        except (OSError, json.JSONDecodeError) as exc:
            raise PlaylistAutomationError("Backup file could not be read") from exc
        restored = 0
        for entry in value.get("playlists", []):
            playlist = entry.get("playlist") or {}
            target = target_playlist_id or str(playlist.get("id") or "")
            uris = [str(track.get("uri")) for track in entry.get("tracks", []) if track.get("uri")]
            if target and uris:
                self._write_playlist(target, uris, "replace")
                restored += 1
        return {"success": True, "playlists": restored}


playlist_automation = PlaylistAutomation()
