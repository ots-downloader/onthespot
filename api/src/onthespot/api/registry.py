"""
api/registry.py
~~~~~~~~~~~~~~~

Central registry of per-service callable functions.

Previously, modules used ``globals()[f"{service}_get_..."]`` to dynamically
look up service functions at runtime.  That pattern is opaque to static
analysis tools and IDEs and makes the code hard to follow.

This module replaces every such lookup with a plain dictionary whose keys are
service name strings (matching the values stored in ``account_pool`` entries)
and whose values are the actual function objects.  Consumers import only the
specific dict they need, e.g.::

    from .api.registry import SERVICE_METADATA_FUNCTIONS
    metadata = SERVICE_METADATA_FUNCTIONS[item_service](token, item_id)

Adding support for a new service is a matter of importing its functions and
adding entries to the appropriate dicts below.
"""

# ---------------------------------------------------------------------------
# Login / session initialisation
# ---------------------------------------------------------------------------
from .apple_music import apple_music_login_user
from .bandcamp import bandcamp_login_user
from .crunchyroll import crunchyroll_login_user
from .deezer import deezer_login_user
from .generic import generic_login_user
from .qobuz import qobuz_login_user
from .soundcloud import soundcloud_login_user
from .spotify import spotify_login_user
from .tidal import tidal_login_user
from .youtube_music import youtube_music_login_user

SERVICE_LOGIN_FUNCTIONS = {
    "apple_music": apple_music_login_user,
    "bandcamp": bandcamp_login_user,
    "crunchyroll": crunchyroll_login_user,
    "deezer": deezer_login_user,
    "generic": generic_login_user,
    "qobuz": qobuz_login_user,
    "soundcloud": soundcloud_login_user,
    "spotify": spotify_login_user,
    "tidal": tidal_login_user,
    "youtube_music": youtube_music_login_user,
}

# ---------------------------------------------------------------------------
# Token retrieval (returns an auth token / session object for a given account
# pool index)
# ---------------------------------------------------------------------------
from .apple_music import apple_music_get_token
from .crunchyroll import crunchyroll_get_token
from .deezer import deezer_get_token
from .qobuz import qobuz_get_token
from .soundcloud import soundcloud_get_token
from .spotify import spotify_get_token
from .tidal import tidal_get_token

SERVICE_TOKEN_FUNCTIONS = {
    "apple_music": apple_music_get_token,
    "crunchyroll": crunchyroll_get_token,
    "deezer": deezer_get_token,
    "qobuz": qobuz_get_token,
    "soundcloud": soundcloud_get_token,
    "spotify": spotify_get_token,
    "tidal": tidal_get_token,
}

# ---------------------------------------------------------------------------
# Track / episode metadata retrieval
# ---------------------------------------------------------------------------
from .apple_music import apple_music_get_track_metadata
from .bandcamp import bandcamp_get_track_metadata
from .crunchyroll import crunchyroll_get_episode_metadata
from .deezer import deezer_get_track_metadata
from .generic import generic_get_track_metadata
from .qobuz import qobuz_get_track_metadata
from .soundcloud import soundcloud_get_track_metadata
from .spotify import spotify_get_track_metadata, spotify_get_podcast_episode_metadata
from .tidal import tidal_get_track_metadata
from .youtube_music import youtube_music_get_track_metadata

SERVICE_METADATA_FUNCTIONS = {
    "apple_music": {"track": apple_music_get_track_metadata},
    "bandcamp": {"track": bandcamp_get_track_metadata},
    "crunchyroll": {"episode": crunchyroll_get_episode_metadata},
    "deezer": {"track": deezer_get_track_metadata},
    "generic": {"track": generic_get_track_metadata},
    "qobuz": {"track": qobuz_get_track_metadata},
    "soundcloud": {"track": soundcloud_get_track_metadata},
    "spotify": {
        "track": spotify_get_track_metadata,
        "podcast_episode": spotify_get_podcast_episode_metadata,
    },
    "tidal": {"track": tidal_get_track_metadata},
    "youtube_music": {"track": youtube_music_get_track_metadata},
}


def get_metadata_function(service: str, item_type: str):
    """Return the metadata function for *service* / *item_type*.

    Raises ``KeyError`` if the combination is not registered.
    """
    return SERVICE_METADATA_FUNCTIONS[service][item_type]


# ---------------------------------------------------------------------------
# Lyrics retrieval (only a subset of services support this)
# ---------------------------------------------------------------------------
from .apple_music import apple_music_get_lyrics
from .spotify import spotify_get_lyrics
from .tidal import tidal_get_lyrics

SERVICE_LYRICS_FUNCTIONS = {
    "apple_music": apple_music_get_lyrics,
    "spotify": spotify_get_lyrics,
    "tidal": tidal_get_lyrics,
}

# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------
from .apple_music import apple_music_get_search_results
from .bandcamp import bandcamp_get_search_results
from .crunchyroll import crunchyroll_get_search_results
from .deezer import deezer_get_search_results
from .qobuz import qobuz_get_search_results
from .soundcloud import soundcloud_get_search_results
from .spotify import spotify_get_search_results
from .tidal import tidal_get_search_results
from .youtube_music import youtube_music_get_search_results

SERVICE_SEARCH_FUNCTIONS = {
    "apple_music": apple_music_get_search_results,
    "bandcamp": bandcamp_get_search_results,
    "crunchyroll": crunchyroll_get_search_results,
    "deezer": deezer_get_search_results,
    "qobuz": qobuz_get_search_results,
    "soundcloud": soundcloud_get_search_results,
    "spotify": spotify_get_search_results,
    "tidal": tidal_get_search_results,
    "youtube_music": youtube_music_get_search_results,
}

# ---------------------------------------------------------------------------
# Collection helpers — album track IDs, artist album IDs, playlist data, etc.
# ---------------------------------------------------------------------------
from .apple_music import (
    apple_music_get_album_track_ids,
    apple_music_get_artist_album_ids,
    apple_music_get_playlist_data,
)
from .bandcamp import bandcamp_get_album_track_ids, bandcamp_get_artist_album_ids
from .crunchyroll import crunchyroll_get_show_episode_ids
from .deezer import (
    deezer_get_album_track_ids,
    deezer_get_artist_album_ids,
    deezer_get_playlist_data,
)
from .qobuz import (
    qobuz_get_album_track_ids,
    qobuz_get_artist_album_ids,
    qobuz_get_label_album_ids,
    qobuz_get_playlist_data,
)
from .soundcloud import (
    soundcloud_get_album_track_ids,
    soundcloud_get_artist_album_ids,
    soundcloud_get_playlist_data,
)
from .spotify import (
    spotify_get_album_track_ids,
    spotify_get_artist_album_ids,
    spotify_get_playlist_data,
    spotify_get_podcast_episode_ids,
)
from .tidal import (
    tidal_get_album_track_ids,
    tidal_get_artist_album_ids,
    tidal_get_playlist_data,
    tidal_get_mix_data,
)
from .youtube_music import (
    youtube_music_get_channel_track_ids,
    youtube_music_get_playlist_data,
)

# Maps service → album_type → function(token, collection_id) → list[track_id]
SERVICE_ALBUM_TRACK_ID_FUNCTIONS = {
    "apple_music": apple_music_get_album_track_ids,
    "bandcamp": bandcamp_get_album_track_ids,
    "deezer": deezer_get_album_track_ids,
    "qobuz": qobuz_get_album_track_ids,
    "soundcloud": soundcloud_get_album_track_ids,
    "spotify": spotify_get_album_track_ids,
    "tidal": tidal_get_album_track_ids,
}

# Maps service → function(token, artist_id) → list[album_id]
SERVICE_ARTIST_ALBUM_ID_FUNCTIONS = {
    "apple_music": apple_music_get_artist_album_ids,
    "bandcamp": bandcamp_get_artist_album_ids,
    "deezer": deezer_get_artist_album_ids,
    "qobuz": qobuz_get_artist_album_ids,
    "soundcloud": soundcloud_get_artist_album_ids,
    "spotify": spotify_get_artist_album_ids,
    "tidal": tidal_get_artist_album_ids,
}

# Maps service → function(token, label_id) → list[album_id]
SERVICE_LABEL_ALBUM_ID_FUNCTIONS = {
    "qobuz": qobuz_get_label_album_ids,
}

# Maps service → function(token, playlist_id) → (name, by, list[track_id])
SERVICE_PLAYLIST_DATA_FUNCTIONS = {
    "apple_music": apple_music_get_playlist_data,
    "deezer": deezer_get_playlist_data,
    "qobuz": qobuz_get_playlist_data,
    "soundcloud": soundcloud_get_playlist_data,
    "spotify": spotify_get_playlist_data,
    "tidal": tidal_get_playlist_data,
    "youtube_music": youtube_music_get_playlist_data,
}

# Maps service → function(token, mix_id) → (name, by, list[track_id])
SERVICE_MIX_DATA_FUNCTIONS = {
    "tidal": tidal_get_mix_data,
}

# Maps service → function(token, show_id/season_id) → list[episode_id]
SERVICE_EPISODE_ID_FUNCTIONS = {
    "spotify": spotify_get_podcast_episode_ids,
    "crunchyroll": crunchyroll_get_show_episode_ids,
}

# Maps service → function(token, channel_id) → list[track_id]
SERVICE_CHANNEL_TRACK_ID_FUNCTIONS = {
    "youtube_music": youtube_music_get_channel_track_ids,
}

# Podcast episode IDs (reuses the same crunchyroll/spotify functions)
SERVICE_PODCAST_EPISODE_ID_FUNCTIONS = {
    "spotify": spotify_get_podcast_episode_ids,
}
