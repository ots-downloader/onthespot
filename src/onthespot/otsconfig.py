import json
import os
import shutil
import uuid


def config_dir():
    if os.path.exists(os.environ.get("ONTHESPOTDIR", "")):
        return os.environ["ONTHESPOTDIR"]
    elif os.name == "nt" and os.path.exists(os.environ.get("APPDATA", "")):
        base_dir = os.environ["APPDATA"]
    elif os.name == "nt" and os.path.exists(os.environ.get("LOCALAPPDATA", "")):
        base_dir = os.environ["LOCALAPPDATA"]
    elif os.path.exists(os.environ.get("XDG_CONFIG_HOME", "")):
        base_dir = os.environ["XDG_CONFIG_HOME"]
    else:
        base_dir = os.path.join(os.path.expanduser("~"), ".config")
    return os.path.join(base_dir, "onthespot")


def cache_dir():
    if os.name == "nt" and os.path.exists(os.environ.get("TEMP", "")):
        base_dir = os.environ["TEMP"]
    elif os.path.exists(os.environ.get("XDG_CACHE_HOME", "")):
        base_dir = os.environ["XDG_CACHE_HOME"]
    else:
        base_dir = os.path.join(os.path.expanduser("~"), ".cache")
    return os.path.join(base_dir, "onthespot")


class Config:
    def __init__(self, cfg_path=None):
        if cfg_path is None or not os.path.isfile(cfg_path):
            cfg_path = os.path.join(config_dir(), "otsconfig.json")
        self.__cfg_path = cfg_path
        self.ext_ = ".exe" if os.name == "nt" else ""
        self.session_uuid = str(uuid.uuid4())
        self.__template_data = {
            # System Variables
            "version": "v1.8.0",  # Application version
            "debug_mode": False,  # Enable debug mode
            "language_index": 0,  # Language Index
            "total_downloaded_items": 0,  # Total downloaded items
            "total_downloaded_data": 0,  # Total downloaded data in bytes
            "m3u_format": "m3u8",  # M3U file format
            "use_double_digit_path_numbers": False,  # Append a 0 to single digit path numbers, for instance 1 -> 01
            "ffmpeg_args": [],  # Extra arguments for ffmpeg
            # Accounts
            "active_account_number": 0,  # Serial number of account that will be used to parse and download media
            "accounts": [
                {
                    "uuid": "public_bandcamp",
                    "service": "bandcamp",
                    "active": True,
                },
                {
                    "uuid": "public_soundcloud",
                    "service": "soundcloud",
                    "active": True,
                    "login": {
                        "client_id": "null",
                        "app_version": "null",
                        "app_locale": "null",
                    },
                },
                {
                    "uuid": "public_youtube_music",
                    "service": "youtube_music",
                    "active": True,
                },
                {
                    "uuid": "public_generic",
                    "service": "generic",
                    "active": True,
                },
            ],  # Saved account information
            # Web UI Settings
            "use_webui_login": False,  # Enable Web UI Login Page
            "webui_username": "",  # Web UI Username
            "webui_password": "",  # Web UI Password
            # General Settings
            "language": "en_US",  # Language
            "theme": "background-color: #282828; color: white;",  # Custom stylesheet
            "explicit_label": "🅴",  # Explicit label in app and download path
            "download_copy_btn": False,  # Add copy button to downloads
            "download_open_btn": True,  # Add open button to downloads
            "download_locate_btn": True,  # Add locate button to downloads
            "download_delete_btn": False,  # Add delete button to downloads
            "show_search_thumbnails": True,  # Show thumbnails in search view
            "show_download_thumbnails": False,  # Show thumbnails in download view
            "thumbnail_size": 60,  # Thumbnail height and width in px
            "max_search_results": 10,  # Number of search results to display of each type
            "disable_download_popups": False,  # Hide download popups
            "windows_10_explorer_thumbnails": False,  # Use old id3 format to support windows 10 explorer (not the standard format)
            "mirror_spotify_playback": False,  # Mirror spotify playback
            "close_to_tray": False,  # Close application to tray
            "check_for_updates": True,  # Check for updates
            "illegal_character_replacement": "-",  # Character used to replace illegal characters or values in path
            "raw_media_download": False,  # Skip media conversion and metadata writing
            "rotate_active_account_number": False,  # Rotate active account for parsing and downloading tracks
            "download_delay": 3,  # Seconds to wait before next download attempt
            "download_delay_variance": 0,  # Random ± variance in seconds applied to download delay
            "download_chunk_size": 50000,  # Chunk size in bytes to download in
            "maximum_queue_workers": 1,  # Maximum number of queue workers
            "maximum_download_workers": 1,  # Maximum number of download workers
            "enable_retry_worker": False,  # Enable retry worker, automatically retries failed downloads after a set time
            "retry_worker_delay": 10,  # Amount of time to wait before retrying failed downloads, in minutes
            "api_retry_max_attempts": 3,  # Max retries on rate limit (429)
            "api_retry_base_delay": 2,  # Base delay for exponential backoff (seconds)
            "api_retry_max_delay": 60,  # Max delay between retries (seconds)
            "api_request_delay": 0.1,  # Delay between consecutive API calls (seconds)
            # Spotify Web API Override Credentials (for debugging only)
            # These credentials override the default librespot token authentication for Web API calls.
            # Use when debugging metadata retrieval issues. Create personal tokens for yourself only.
            # WARNING: Overuse can result in Spotify banning your account!
            "spotify_webapi_override_client_id": "",  # Your personal Spotify app client ID
            "spotify_webapi_override_client_secret": "",  # Your personal Spotify app client secret
            # API Call Reduction - Metadata Fetching Options
            "cache_metadata_in_queue": True,  # Pass metadata from QueueWorker to DownloadWorker (50% reduction)
            "fetch_genre_metadata": True,  # Fetch genre from artist endpoint (adds 1 API call per track)
            "fetch_extended_album_metadata": True,  # Fetch label, copyright (adds 1 API call per track)
            "fetch_audio_features": True,  # Fetch BPM, key, danceability (adds 1 API call per track)
            "fetch_track_credits": True,  # Fetch producers, writers (adds 1 API call per track)
            # Search Settings
            "enable_search_tracks": True,  # Enable listed category in search
            "enable_search_albums": True,  # Enable listed category in search
            "enable_search_playlists": True,  # Enable listed category in search
            "enable_search_artists": True,  # Enable listed category in search
            "enable_search_episodes": True,  # Enable listed category in search
            "enable_search_podcasts": True,  # Enable listed category in search
            "enable_search_audiobooks": True,  # Enable listed category in search
            "f_search_tracks": False,  # Enable filtered Tracks search
            "f_search_albums": False,  # Enable filtered Albums search
            "f_search_artists": False,  # Enable filtered Artists search
            "f_search_playlists": False,  # Enable filtered Playlists search
            # Search Prefix Settings
            "search_prefix": "the",
            # Download Queue Filter Settings
            "download_queue_show_waiting": True,  # Enable listed filter in download queue
            "download_queue_show_failed": True,  # Enable listed filter in download queue
            "download_queue_show_cancelled": True,  # Enable listed filter in download queue
            "download_queue_show_unavailable": True,  # Enable listed filter in download queue
            "download_queue_show_completed": True,  # Enable listed filter in download queue
            # Audio Download Settings
            "audio_download_path": os.path.join(
                os.path.expanduser("~"), "Music", "OnTheSpot"
            ),  # Root dir for audio downloads
            "track_file_format": "mp3",  # Song track media format
            "track_path_formatter": "Tracks"
            + os.path.sep
            + "{album_artist}"
            + os.path.sep
            + "[{year}] {album}"
            + os.path.sep
            + "{track_number}. {name}",  # Track path format string
            "podcast_file_format": "mp3",  # Podcast track media format
            "podcast_path_formatter": "Episodes"
            + os.path.sep
            + "{album}"
            + os.path.sep
            + "{name}",  # Episode path format string
            "use_playlist_path": False,  # Use playlist path
            "playlist_path_formatter": "Playlists"
            + os.path.sep
            + "{playlist_name} by {playlist_owner}"
            + os.path.sep
            + "{playlist_number}. {name} - {artist}",  # Playlist path format string
            "create_m3u_file": False,  # Create m3u based playlist
            "m3u_path_formatter": "M3U"
            + os.path.sep
            + "{playlist_name} by {playlist_owner}",  # M3U name format string
            "extinf_separator": "; ",  # M3U EXTINF metadata separator
            "extinf_label": "{playlist_number}. {artist} - {name}",  # M3U EXTINF path
            "save_album_cover": False,  # Save album covers to a file
            "album_cover_format": "png",  # Album cover format
            "file_bitrate": "320k",  # Converted file bitrate
            "file_hertz": 44100,  # Converted file hertz
            "use_custom_file_bitrate": True,  # Use bitrate specified by file bitrate
            "download_lyrics": False,  # Enable lyrics download
            "only_download_synced_lyrics": False,  # Only download synced lyrics
            "only_download_plain_lyrics": False,  # Only download plain lyrics
            "save_lrc_file": False,  # Download .lrc file alongside track
            "translate_file_path": False,  # Translate downloaded file path to application language
            # Audio Metadata Settings
            "metadata_separator": "; ",  # Separator used for metadata fields that have multiple values
            "overwrite_existing_metadata": False,  # Overwrite metadata in files that 'Already Exist'
            "embed_branding": False,
            "embed_cover": True,
            "embed_artist": True,
            "embed_album": True,
            "embed_albumartist": True,
            "embed_name": True,
            "embed_year": True,
            "embed_discnumber": True,
            "embed_tracknumber": True,
            "embed_genre": True,
            "embed_performers": True,
            "embed_producers": True,
            "embed_writers": True,
            "embed_composer": True,
            "embed_label": True,
            "embed_copyright": True,
            "embed_description": True,
            "embed_language": True,
            "embed_isrc": True,
            "embed_length": True,
            "embed_url": True,
            "embed_key": True,
            "embed_bpm": True,
            "embed_compilation": True,
            "embed_lyrics": False,
            "embed_explicit": False,
            "embed_upc": False,
            "embed_service_id": False,
            "embed_timesignature": False,
            "embed_acousticness": False,
            "embed_danceability": False,
            "embed_energy": False,
            "embed_instrumentalness": False,
            "embed_liveness": False,
            "embed_loudness": False,
            "embed_speechiness": False,
            "embed_valence": False,
            # Video Download Settings
            "video_download_path": os.path.join(
                os.path.expanduser("~"), "Videos", "OnTheSpot"
            ),  # Root dir for audio downloads
            "movie_file_format": "mkv",
            "movie_path_formatter": "Movies"
            + os.path.sep
            + "{name} ({release_year})",  # Show path format string
            "show_file_format": "mkv",
            "show_path_formatter": "Shows"
            + os.path.sep
            + "{show_name}"
            + os.path.sep
            + "Season {season_number}"
            + os.path.sep
            + "{episode_number}. {name}",  # Show path format string
            "preferred_video_resolution": 1080,  # Maximum video resolution for Generic Downloader
            "download_subtitles": False,  # Download Subtitles
            "download_chapters": False,  # Download Chapters
            "preferred_audio_language": "en-US",
            "preferred_subtitle_language": "en-US",
            "download_all_available_audio": False,
            "download_all_available_subtitles": False,
        }
        # Load Config
        if os.path.isfile(self.__cfg_path):
            self.__config = json.load(open(cfg_path, "r"))
        else:
            try:
                os.makedirs(os.path.dirname(self.__cfg_path), exist_ok=True)
            except (FileNotFoundError, PermissionError):
                print("Failed to create config dir, attempting fallback path.")
                fallback_path = os.path.abspath(
                    os.path.join(os.path.expanduser("~"), ".config", "otsconfig.json")
                )
                self.__cfg_path = fallback_path
                os.makedirs(os.path.dirname(self.__cfg_path), exist_ok=True)
            with open(self.__cfg_path, "w") as cf:
                cf.write(json.dumps(self.__template_data, indent=4))
            self.__config = self.__template_data
        # Make Download Dirs
        try:
            os.makedirs(self.get("audio_download_path"), exist_ok=True)
            os.makedirs(self.get("video_download_path"), exist_ok=True)
        except (FileNotFoundError, PermissionError):
            print("Failed to create download dir, attempting fallback path.")
            self.set(
                "audio_download_path", self.__template_data.get("audio_download_path")
            )
            self.set(
                "video_download_path", self.__template_data.get("video_download_path")
            )
            os.makedirs(self.get("audio_download_path"), exist_ok=True)
            os.makedirs(self.get("video_download_path"), exist_ok=True)
        # Set FFMPEG Path
        self.app_root = os.path.dirname(os.path.realpath(__file__))
        ffmpeg_path_candidates = [
            os.environ.get("FFMPEG_PATH", ""),  # ENV
            shutil.which("ffmpeg") or "",  # SYSTEM PATH
            "/usr/bin/ffmpeg",  # UNIX
            "/opt/homebrew/bin/ffmpeg",  # MACOS ARM
            "/usr/local/bin/ffmpeg",  # MACOS INTEL
            os.path.join(
                self.app_root, "bin", "ffmpeg", "ffmpeg" + self.ext_
            ),  # BUNDLED
        ]
        ffmpeg_path = ""
        for path in ffmpeg_path_candidates:
            if os.path.isfile(path) and os.access(path, os.X_OK):
                ffmpeg_path = path
                break
        if not ffmpeg_path:
            print(
                "Failed to find ffmpeg binary, please consider installing ffmpeg or defining its path by setting FFMPEG_PATH."
            )

        print(f"FFMPEG Binary: {ffmpeg_path}")
        self.set("_ffmpeg_bin_path", ffmpeg_path)
        self.set(
            "_log_file",
            os.path.join(cache_dir(), "logs", self.session_uuid, "onthespot.log"),
        )
        self.set("_cache_dir", cache_dir())
        try:
            os.makedirs(os.path.dirname(self.get("_log_file")), exist_ok=True)
        except (FileNotFoundError, PermissionError):
            fallback_logdir = os.path.abspath(
                os.path.join(".logs", self.session_uuid, "onthespot.log")
            )
            print(
                'Current logging dir cannot be set up at "',
                self.get("audio_download_path"),
                '"; Falling back to : ',
                fallback_logdir,
            )
            self.set("_log_file", fallback_logdir)
            os.makedirs(os.path.dirname(self.get("_log_file")), exist_ok=True)

    def get(self, key, default=None):
        if key in self.__config:
            return self.__config[key]
        elif key in self.__template_data:
            return self.__template_data[key]
        else:
            return default

    def set(self, key, value):
        if type(value) in [list, dict]:
            self.__config[key] = value.copy()
        else:
            self.__config[key] = value
        return value

    def save(self):
        os.makedirs(os.path.dirname(self.__cfg_path), exist_ok=True)
        for key in list(set(self.__template_data).difference(set(self.__config))):
            if not key.startswith("_"):
                self.set(key, self.__template_data[key])
        with open(self.__cfg_path, "w") as cf:
            cf.write(json.dumps(self.__config, indent=4))

    def reset(self):
        with open(self.__cfg_path, "w") as cf:
            cf.write(json.dumps(self.__template_data, indent=4))
        self.__config = self.__template_data

    def migration(self):
        if int(self.get("version").replace("v", "").replace(".", "")) < int(
            self.__template_data.get("version").replace("v", "").replace(".", "")
        ):
            old_config_path = os.path.join(config_dir(), "config.json")
            if os.path.exists(old_config_path):
                os.remove(old_config_path)

            # Migration (>v1.0.3)
            if isinstance(self.get("file_hertz"), str):
                self.set("file_hertz", int(self.get("file_hertz")))

            # Migration (>v1.0.4)
            if self.get("theme") == "dark":
                self.set("theme", f"background-color: #282828; color: white;")
            elif self.get("theme") == "light":
                self.set("theme", f"background-color: white; color: black;")

            # Migration (>v1.0.5)
            cfg_copy = self.get("accounts").copy()
            for account in cfg_copy:
                if account["uuid"] == "public_youtube":
                    account["uuid"] = "public_youtube_music"
                    account["service"] = "youtube_music"
            self.set("accounts", cfg_copy)

            # Migration (>v1.0.7)
            if int(self.get("version").replace("v", "").replace(".", "")) < 110:
                updated_keys = [
                    ("active_account_number", "parsing_acc_sn"),
                    ("thumbnail_size", "search_thumb_height"),
                    ("disable_download_popups", "disable_bulk_dl_notices"),
                    ("raw_media_download", "force_raw"),
                    ("download_chunk_size", "chunk_size"),
                    ("rotate_active_account_number", "rotate_acc_sn"),
                    ("audio_download_path", "download_root"),
                    ("track_file_format", "media_format"),
                    ("podcast_file_format", "podcast_media_format"),
                    ("video_download_path", "generic_download_root"),
                    ("create_m3u_file", "create_m3u_playlists"),
                    ("m3u_path_formatter", "m3u_name_formatter"),
                    ("enable_search_podcasts", "enable_search_shows"),
                    ("extinf_separator", "ext_seperator"),
                    ("extinf_label", "ext_path"),
                    ("download_lyrics", "inp_enable_lyrics"),
                    ("save_lrc_file", "use_lrc_file"),
                    ("only_download_synced_lyrics", "only_synced_lyrics"),
                    ("preferred_video_resolution", "maximum_generic_resolution"),
                    ("use_custom_file_bitrate", True),
                ]
                for key in updated_keys:
                    value = self.get(key[1])
                    if value:
                        self.set(key[0], value)
                        self.__config.pop(key[1])

            self.set("version", self.__template_data.get("version"))
            self.save()

        # Language
        if self.get("language_index") == 0:
            self.set("language", "en_US")
        elif self.get("language_index") == 1:
            self.set("language", "de_DE")
        elif self.get("language_index") == 2:
            self.set("language", "ja_JP")
        elif self.get("language_index") == 3:
            self.set("language", "pt_PT")
        else:
            print(f"Unknown language index: {self.get('language_index')}")
            self.set("language", "en_US")
        self.save()


config = Config()
