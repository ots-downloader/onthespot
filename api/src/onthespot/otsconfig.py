import copy
import json
import logging
import os
import shutil
import uuid


logger = logging.getLogger(__name__)


def _expanded_path(value: str) -> str:
    """Return an absolute path after expanding user and environment markers."""
    return os.path.abspath(os.path.expandvars(os.path.expanduser(value)))


def config_dir():
    """
    Returns the configuration directory path based on environment variables and operating system.

    :return: The configuration directory path as a string.
    """
    override = os.environ.get("ONTHESPOTDIR", "").strip()
    if override:
        return _expanded_path(override)
    if os.name == "nt" and os.environ.get("APPDATA"):
        base_dir = os.environ["APPDATA"]
    elif os.name == "nt" and os.environ.get("LOCALAPPDATA"):
        base_dir = os.environ["LOCALAPPDATA"]
    elif os.environ.get("XDG_CONFIG_HOME"):
        base_dir = os.environ["XDG_CONFIG_HOME"]
    else:
        base_dir = os.path.join(os.path.expanduser("~"), ".config")
    return _expanded_path(os.path.join(base_dir, "onthespot"))


def cache_dir():
    """
    Returns the cache directory path based on environment variables and operating system.

    :return: The cache directory path as a string.
    """
    override = os.environ.get("ONTHESPOTCACHEDIR", "").strip()
    if override:
        return _expanded_path(override)
    # Cache-backed state includes Spotify sessions, statistics, playlist
    # automation state, and uploaded YouTube cookies. Keep it beside the main
    # configuration so Docker/Unraid's config volume persists it.
    return os.path.join(config_dir(), "cache")


def _legacy_config_root() -> str | None:
    """Return the accidental Windows config root used by older FastAPI builds."""
    if os.name != "nt" or os.environ.get("ONTHESPOTDIR"):
        return None
    return os.path.dirname(_expanded_path("/root/.config/onthespot/otsconfig.json"))


def _legacy_cache_roots() -> list[str]:
    """Return cache locations used before persistent app-data storage."""
    roots: list[str] = []
    if os.name == "nt" and os.environ.get("TEMP"):
        roots.append(_expanded_path(os.path.join(os.environ["TEMP"], "onthespot")))
    elif os.environ.get("XDG_CACHE_HOME"):
        roots.append(_expanded_path(os.path.join(os.environ["XDG_CACHE_HOME"], "onthespot")))
    else:
        roots.append(_expanded_path(os.path.join(os.path.expanduser("~"), ".cache", "onthespot")))
    return roots


def _copy_newer_tree(source: str, destination: str) -> None:
    """Copy missing or newer files without deleting destination state."""
    if not os.path.isdir(source) or os.path.abspath(source) == os.path.abspath(destination):
        return
    for root, _, files in os.walk(source):
        relative = os.path.relpath(root, source)
        target_root = destination if relative == "." else os.path.join(destination, relative)
        os.makedirs(target_root, exist_ok=True)
        for filename in files:
            source_file = os.path.join(root, filename)
            target_file = os.path.join(target_root, filename)
            if not os.path.exists(target_file) or os.path.getmtime(source_file) > os.path.getmtime(target_file):
                shutil.copy2(source_file, target_file)


def _migrate_legacy_state(config_root: str) -> None:
    """Move state from legacy roots while preserving any existing destination."""
    os.makedirs(config_root, exist_ok=True)
    destination_config = os.path.join(config_root, "otsconfig.json")
    legacy_root = _legacy_config_root()
    if legacy_root:
        legacy_config = os.path.join(legacy_root, "otsconfig.json")
        if os.path.isfile(legacy_config) and (
            not os.path.isfile(destination_config)
            or os.path.getmtime(legacy_config) > os.path.getmtime(destination_config)
        ):
            if os.path.isfile(destination_config):
                backup = destination_config + ".pre-migration.bak"
                if not os.path.exists(backup):
                    shutil.copy2(destination_config, backup)
            shutil.copy2(legacy_config, destination_config)
            logger.info("Migrated OnTheSpot configuration from the legacy Windows path")
        _copy_newer_tree(os.path.join(legacy_root, "cache"), cache_dir())

    for legacy_cache in _legacy_cache_roots():
        _copy_newer_tree(legacy_cache, cache_dir())


class Config:
    def __init__(self):
        """
        Initializes a new Config instance, setting up configuration paths,
        loading default and user configurations, and initializing session UUID.
        Also sets up download directories and determines the FFMPEG binary path.

        This method will:
        - Load template data from the external default configuration file.
        - Initialize session UUID.
        - Define file extension for cross-platform compatibility.
        - Load or create a user configuration file.
        - Create necessary download directories.
        - Determine the FFMPEG binary path.

        If any step fails, appropriate fallback mechanisms are used to ensure that the application can still run.
        """
        config_root = config_dir()
        _migrate_legacy_state(config_root)
        self.__cfg_path = os.path.join(config_root, "otsconfig.json")
        self.__default_cfg_path = os.path.join(
            os.path.dirname(__file__), "otsconfig_default.json"
        )
        self.session_uuid = str(uuid.uuid4())

        # Load default config
        try:
            with open(self.__default_cfg_path, "r", encoding="utf-8") as df:
                self.__template_data = json.load(df)
        except (json.JSONDecodeError, FileNotFoundError):
            print(
                f"Failed to load default config file: {self.__default_cfg_path}, using empty template"
            )
            self.__template_data = {}

        # Load or create user config
        if os.path.isfile(self.__cfg_path):
            try:
                with open(self.__cfg_path, "r", encoding="utf-8") as cf:
                    self.__config = json.load(cf)
            except (json.JSONDecodeError, FileNotFoundError):
                print(
                    f"Failed to load user config file: {self.__cfg_path}, using default template"
                )
                self.__config = self.__template_data.copy()
        else:
            try:
                os.makedirs(os.path.dirname(self.__cfg_path), exist_ok=True)
                with open(self.__cfg_path, "w", encoding="utf-8") as cf:
                    json.dump(self.__template_data, cf, indent=4, ensure_ascii=False)
                self.__config = self.__template_data.copy()
            except (FileNotFoundError, PermissionError) as e:
                print(f"Failed to create config dir: {e}, attempting fallback path.")
                fallback_path = os.path.abspath(
                    os.path.join(os.path.expanduser("~"), ".config", "otsconfig.json")
                )
                self.__cfg_path = fallback_path
                os.makedirs(os.path.dirname(self.__cfg_path), exist_ok=True)
                with open(self.__cfg_path, "w", encoding="utf-8") as cf:
                    json.dump(self.__template_data, cf, indent=4, ensure_ascii=False)
                self.__config = self.__template_data

        # Version identifies the bundled application build, not a user setting.
        # Keep existing configuration volumes from pinning the UI to an older
        # release after the Docker image has been upgraded.
        if self.__template_data.get("version"):
            self.__config["version"] = self.__template_data["version"]

        # ``cache_metadata_in_queue`` was the original UI key for the global
        # API-cache switch.  Preserve an existing user's choice while moving
        # to the accurately named setting.
        if "cache_api_calls" not in self.__config:
            self.__config["cache_api_calls"] = bool(
                self.__config.get(
                    "cache_metadata_in_queue",
                    self.__template_data.get("cache_api_calls", True),
                )
            )

        # The bundled defaults are written for the Linux/Docker image. When
        # running the API directly on Windows, translate those container paths
        # to the user's normal Music/Videos folders instead of creating a
        # literal ``C:\\root`` directory.
        if os.name == "nt":
            for path_key in ("audio_download_path", "video_download_path"):
                configured_path = self.__config.get(path_key)
                normalized_path = str(configured_path or "").replace("\\", "/")
                if normalized_path.startswith("/root/"):
                    self.__config[path_key] = os.path.join(
                        os.path.expanduser("~"), normalized_path.removeprefix("/root/")
                    )

        # Make Download Dirs
        try:
            os.makedirs(self.get("audio_download_path"), exist_ok=True)
            os.makedirs(self.get("video_download_path"), exist_ok=True)
        except (FileNotFoundError, PermissionError) as e:
            print(f"Failed to create download dir: {e}, attempting fallback path.")
            self.set(
                "audio_download_path", self.__template_data.get("audio_download_path")
            )
            self.set(
                "video_download_path", self.__template_data.get("video_download_path")
            )
            os.makedirs(self.get("audio_download_path"), exist_ok=True)
            os.makedirs(self.get("video_download_path"), exist_ok=True)

        # Set FFMPEG Path
        ffmpeg_path = os.environ.get("FFMPEG_PATH") or shutil.which("ffmpeg")
        if not ffmpeg_path and os.name != "nt":
            ffmpeg_path = "/usr/bin/ffmpeg"

        if ffmpeg_path and os.path.isfile(ffmpeg_path):
            self._ffmpeg_bin_path = ffmpeg_path
        else:
            print(
                "Failed to find ffmpeg binary, please consider installing ffmpeg or defining its path."
            )
            self._ffmpeg_bin_path = ""

        print(f"FFMPEG Binary: {self._ffmpeg_bin_path}")
        self.set("_ffmpeg_bin_path", self._ffmpeg_bin_path)
        self.set(
            "_log_file",
            os.path.join(
                config_root,
                "logs",
                self.session_uuid,
                "onthespot.log",
            ),
        )
        self.set(
            "_cache_dir",
            cache_dir(),
        )
        try:
            os.makedirs(os.path.dirname(self.get("_log_file")), exist_ok=True)
            os.makedirs(self.get("_cache_dir"), exist_ok=True)
        except (FileNotFoundError, PermissionError):
            fallback_logdir = os.path.abspath(
                os.path.join(".logs", self.session_uuid, "onthespot.log")
            )
            print(
                f'Current logging dir cannot be set up at "{self.get("video_download_path")}"'
                f"; Falling back to: {fallback_logdir}"
            )
            self.set("_log_file", fallback_logdir)
            os.makedirs(os.path.dirname(self.get("_log_file")), exist_ok=True)

    def get(self, key, default=None):
        """
        Retrieves the value of a configuration key.

        :param key: The configuration key to retrieve.
        :param default: The default value to return if the key is not found in either the user or template configurations.
        :return: The value associated with the key, or the default value if the key is not found.
        """
        if key in self.__config:
            return self.__config[key]
        if key in self.__template_data:
            return self.__template_data[key]
        else:
            return default

    def as_dict(self, *, include_runtime=False, include_secrets=False):
        """Return a detached configuration snapshot for API responses.

        Historically FastAPI serialised the ``Config`` instance directly.
        That exposed Python implementation details, runtime filesystem paths,
        account login payloads, and the Spotify client secret.  Keep the
        public response flat and useful to the UI while never returning
        authentication material by default.
        """
        snapshot = copy.deepcopy(self.__template_data)
        snapshot.update(copy.deepcopy(self.__config))

        if not include_runtime:
            snapshot = {
                key: value
                for key, value in snapshot.items()
                if not str(key).startswith("_")
            }

        if include_secrets:
            return snapshot

        accounts = []
        for account in snapshot.get("accounts", []) or []:
            if not isinstance(account, dict):
                continue
            accounts.append(
                {
                    "uuid": str(account.get("uuid") or ""),
                    "service": str(account.get("service") or ""),
                    "active": bool(account.get("active", True)),
                }
            )
        snapshot["accounts"] = accounts

        secret_keys = {
            "spotify_webapi_override_client_secret",
            "playlist_automation_client_secret",
            "webui_password",
        }
        for key in list(snapshot):
            if key in secret_keys or any(
                marker in key.casefold() for marker in ("password", "secret", "token")
            ):
                snapshot[f"{key}_configured"] = bool(snapshot.get(key))
                snapshot[key] = ""

        return snapshot

    def set(self, key, value):
        """
        Sets a configuration key to a given value.

        :param key: The configuration key to set.
        :param value: The value to associate with the key.
        :return: The value that was set.
        """
        if type(value) in [list, dict]:
            self.__config[key] = value.copy()
        else:
            self.__config[key] = value
        return value

    def save(self):
        """
        Saves the current configuration to the user configuration file.

        This method will ensure that all necessary directories are created and then write the current configuration to the JSON file.
        If any step fails, appropriate fallback mechanisms are used to ensure that the application can still run.
        """
        os.makedirs(os.path.dirname(self.__cfg_path), exist_ok=True)
        # Merge template data into config for missing keys
        for key in list(set(self.__template_data).difference(set(self.__config))):
            if not key.startswith("_"):
                self.set(key, self.__template_data[key])
        try:
            with open(self.__cfg_path, "w", encoding="utf-8") as cf:
                json.dump(self.__config, cf, indent=4, ensure_ascii=False)
        except (IOError, OSError) as e:
            print(f"Failed to save config file: {e}")

    def reset(self):
        """
        Resets the configuration to its default values.

        This method will overwrite the user configuration file with the default template data.
        If any step fails, appropriate fallback mechanisms are used to ensure that the application can still run.
        """
        try:
            with open(self.__cfg_path, "w", encoding="utf-8") as cf:
                json.dump(self.__template_data, cf, indent=4, ensure_ascii=False)
        except (IOError, OSError) as e:
            print(f"Failed to reset config file: {e}")
        self.__config = self.__template_data.copy()


config = Config()
