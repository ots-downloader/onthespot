import json
import os
import shutil
import uuid


def config_dir():
    """
    Returns the configuration directory path based on environment variables and operating system.

    :return: The configuration directory path as a string.
    """
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
    """
    Returns the cache directory path based on environment variables and operating system.

    :return: The cache directory path as a string.
    """
    if os.name == "nt" and os.path.exists(os.environ.get("TEMP", "")):
        base_dir = os.environ["TEMP"]
    elif os.path.exists(os.environ.get("XDG_CACHE_HOME", "")):
        base_dir = os.environ["XDG_CACHE_HOME"]
    else:
        base_dir = os.path.join(os.path.expanduser("~"), ".cache")
    return os.path.join(base_dir, "onthespot")


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
        self.__cfg_path = "/root/.config/onthespot/otsconfig.json"
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
                "/root/.config/onthespot",
                "logs",
                self.session_uuid,
                "onthespot.log",
            ),
        )
        self.set(
            "_cache_dir",
            os.path.join(
                "/root/.config/onthespot",
                "cache",
            ),
        )
        try:
            os.makedirs(os.path.dirname(self.get("_log_file")), exist_ok=True)
            os.makedirs(os.path.dirname(self.get("_cache_dir")), exist_ok=True)
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
