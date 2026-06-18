import os
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QSpinBox, QComboBox, QWidget
from ..otsconfig import config
from ..utils import format_bytes


class NonScrollableSpinBox(QSpinBox):
    def wheelEvent(self, event):
        event.ignore()


class NonScrollableComboBox(QComboBox):
    def wheelEvent(self, event):
        event.ignore()


def load_config(self):
    self.version.setText(config.get("version"))
    self.statistics.setText(
        self.tr("{0} / {1}").format(
            config.get("total_downloaded_items"),
            format_bytes(config.get("total_downloaded_data")),
        )
    )

    # Dev Tools
    self.settings_scrollarea_value.valueChanged.connect(
        self.settings_scroll_area.verticalScrollBar().setValue
    )
    if not config.get("debug_mode"):
        self.settings_scrollarea_value.hide()

    # Hide Popup Settings
    self.group_search_items.hide()
    self.group_download_items.hide()

    # Icons
    self.toggle_theme_button.setIcon(self.get_icon("light"))
    self.clear_cache.setIcon(self.get_icon("trash"))
    self.export_logs.setIcon(self.get_icon("export_file"))
    self.donate.setIcon(self.get_icon("filled_heart"))

    self.language.insertItem(0, self.get_icon("en_US"), "English")
    self.language.insertItem(1, self.get_icon("de_DE"), "Deutsch")
    self.language.insertItem(2, self.get_icon("ja_JP"), "日本語")
    self.language.insertItem(3, self.get_icon("pt_PT"), "Português")

    self.login_service.insertItem(0, "Audio")
    self.login_service.insertItem(1, self.get_icon("apple_music"), "Apple Music")
    self.login_service.insertItem(2, self.get_icon("bandcamp"), "Bandcamp")
    self.login_service.insertItem(3, self.get_icon("deezer"), "Deezer")
    self.login_service.insertItem(4, self.get_icon("qobuz"), "Qobuz")
    self.login_service.insertItem(5, self.get_icon("soundcloud"), "Soundcloud")
    self.login_service.insertItem(6, self.get_icon("spotify"), "Spotify")
    self.login_service.insertItem(7, self.get_icon("tidal"), "Tidal")
    self.login_service.insertItem(8, self.get_icon("youtube_music"), "Youtube Music")
    self.login_service.insertItem(9, "Video")
    self.login_service.insertItem(10, self.get_icon("crunchyroll"), "Crunchyroll")
    self.login_service.insertItem(11, self.get_icon("generic"), "Generic")
    self.login_service.setCurrentIndex(6)

    # self.btn_reconfig.setIcon(self.get_icon('trash'))
    self.btn_save_config.setIcon(self.get_icon("save"))
    self.btn_audio_download_path_browse.setIcon(self.get_icon("folder"))
    self.btn_video_download_path.setIcon(self.get_icon("folder"))
    self.btn_download_tmp_browse.setIcon(self.get_icon("folder"))
    self.btn_search.setIcon(self.get_icon("search"))
    self.btn_search_filter_toggle.setIcon(self.get_icon("collapse_down"))
    self.btn_download_filter_toggle.setIcon(self.get_icon("collapse_up"))

    # Disable scrolling to change values of QSpinBoxes and QComboBoxes
    do_not_scroll = [
        "login_service",
        "language",
        "max_search_results",
        "thumbnail_size",
        "preferred_video_resolution",
        "retry_worker_delay",
        "file_hertz",
        "download_delay",
        "download_delay_variance",
        "download_chunk_size",
        "maximum_queue_workers",
        "maximum_download_workers",
    ]

    for name in do_not_scroll:
        widget = self.findChild(QWidget, name)
        if isinstance(widget, QSpinBox):
            # Create new NonScrollableSpinBox
            new_widget = NonScrollableSpinBox()
            new_widget.setRange(widget.minimum(), widget.maximum())
            new_widget.setValue(widget.value())
            new_widget.setGeometry(widget.geometry())
            new_widget.setMinimumSize(widget.minimumSize())
            new_widget.setMaximumSize(widget.maximumSize())
        elif isinstance(widget, QComboBox):
            # Create new NonScrollableComboBox
            new_widget = NonScrollableComboBox()
            new_widget.addItems([widget.itemText(i) for i in range(widget.count())])
            new_widget.setCurrentIndex(widget.currentIndex())
            new_widget.setGeometry(widget.geometry())
            new_widget.setMinimumSize(widget.minimumSize())
            new_widget.setMaximumSize(widget.maximumSize())
            # Copy icons
            for i in range(widget.count()):
                icon = widget.itemIcon(i)
                if not icon.isNull():
                    new_widget.setItemIcon(i, icon)
        # Replace the widget in the layout
        widget.parent().layout().replaceWidget(widget, new_widget)
        # Delete the original widget
        widget.deleteLater()
        # Store the newly created widget in the previous instance variable
        setattr(self, name, new_widget)

    # General Settings
    self.language.setCurrentIndex(config.get("language_index"))
    self.explicit_label.setText(config.get("explicit_label"))
    self.download_copy_btn.setChecked(config.get("download_copy_btn"))
    self.download_open_btn.setChecked(config.get("download_open_btn"))
    self.download_locate_btn.setChecked(config.get("download_locate_btn"))
    self.download_delete_btn.setChecked(config.get("download_delete_btn"))
    self.show_search_thumbnails.setChecked(config.get("show_search_thumbnails"))
    self.show_download_thumbnails.setChecked(config.get("show_download_thumbnails"))
    self.thumbnail_size.setValue(config.get("thumbnail_size"))
    self.max_search_results.setValue(config.get("max_search_results"))
    self.disable_download_popups.setChecked(config.get("disable_download_popups"))
    self.windows_10_explorer_thumbnails.setChecked(
        config.get("windows_10_explorer_thumbnails")
    )
    self.mirror_spotify_playback.setChecked(config.get("mirror_spotify_playback"))
    self.close_to_tray.setChecked(config.get("close_to_tray"))
    self.check_for_updates.setChecked(config.get("check_for_updates"))
    self.illegal_character_replacement.setText(
        config.get("illegal_character_replacement")
    )
    self.raw_media_download.setChecked(config.get("raw_media_download"))
    self.rotate_active_account_number.setChecked(
        config.get("rotate_active_account_number")
    )
    self.download_delay.setValue(config.get("download_delay"))
    self.download_delay_variance.setValue(config.get("download_delay_variance"))
    self.download_chunk_size.setValue(config.get("download_chunk_size"))
    self.maximum_queue_workers.setValue(config.get("maximum_queue_workers"))
    self.maximum_download_workers.setValue(config.get("maximum_download_workers"))
    self.enable_retry_worker.setChecked(config.get("enable_retry_worker"))
    self.retry_worker_delay.setValue(config.get("retry_worker_delay"))

    # Search Settings
    self.enable_search_tracks.setChecked(config.get("enable_search_tracks"))
    self.enable_search_albums.setChecked(config.get("enable_search_albums"))
    self.enable_search_artists.setChecked(config.get("enable_search_artists"))
    self.enable_search_playlists.setChecked(config.get("enable_search_playlists"))
    self.enable_search_episodes.setChecked(config.get("enable_search_episodes"))
    self.enable_search_podcasts.setChecked(config.get("enable_search_podcasts"))
    self.enable_search_audiobooks.setChecked(config.get("enable_search_audiobooks"))

    # Search Filter Settings
    self.f_search_tracks.setChecked(config.get("f_search_tracks"))
    self.f_search_albums.setChecked(config.get("f_search_albums"))
    self.f_search_artists.setChecked(config.get("f_search_artists"))
    self.f_search_playlists.setChecked(config.get("f_search_playlists"))

    # Search Filter prefix Settings
    self.search_prefix.setText(config.get("search_prefix", "the "))

    # Download Queue Filter Settings
    self.download_queue_show_waiting.setChecked(
        config.get("download_queue_show_waiting")
    )
    self.download_queue_show_failed.setChecked(config.get("download_queue_show_failed"))
    self.download_queue_show_cancelled.setChecked(
        config.get("download_queue_show_cancelled")
    )
    self.download_queue_show_unavailable.setChecked(
        config.get("download_queue_show_unavailable")
    )
    self.download_queue_show_completed.setChecked(
        config.get("download_queue_show_completed")
    )

    # Audio Download Settings
    self.audio_download_path.setText(config.get("audio_download_path"))
    self.track_file_format.setText(config.get("track_file_format"))
    self.track_path_formatter.setText(config.get("track_path_formatter"))
    self.podcast_file_format.setText(config.get("podcast_file_format"))
    self.podcast_path_formatter.setText(config.get("podcast_path_formatter"))
    self.use_playlist_path.setChecked(config.get("use_playlist_path"))
    self.playlist_path_formatter.setText(config.get("playlist_path_formatter"))
    self.create_m3u_file.setChecked(config.get("create_m3u_file"))
    self.m3u_path_formatter.setText(config.get("m3u_path_formatter"))
    self.extinf_separator.setText(config.get("extinf_separator"))
    self.extinf_label.setText(config.get("extinf_label"))
    self.save_album_cover.setChecked(config.get("save_album_cover"))
    self.album_cover_format.setText(config.get("album_cover_format"))
    self.file_bitrate.setText(config.get("file_bitrate"))
    self.file_hertz.setValue(config.get("file_hertz"))
    self.use_custom_file_bitrate.setChecked(config.get("use_custom_file_bitrate"))
    self.download_lyrics.setChecked(config.get("download_lyrics"))
    self.only_download_synced_lyrics.setChecked(
        config.get("only_download_synced_lyrics")
    )
    self.only_download_plain_lyrics.setChecked(config.get("only_download_plain_lyrics"))
    self.save_lrc_file.setChecked(config.get("save_lrc_file"))
    self.translate_file_path.setChecked(config.get("translate_file_path"))

    # Spotify Web API Override Settings
    if hasattr(self, "spotify_webapi_override_client_id"):
        self.spotify_webapi_override_client_id.setText(
            config.get("spotify_webapi_override_client_id", "")
        )
    if hasattr(self, "spotify_webapi_override_client_secret"):
        self.spotify_webapi_override_client_secret.setText(
            config.get("spotify_webapi_override_client_secret", "")
        )

    # Metadata Fetching Options (API Call Reduction)
    if hasattr(self, "fetch_artist_metadata"):
        self.fetch_artist_metadata.setChecked(config.get("fetch_genre_metadata", True))
    if hasattr(self, "fetch_album_metadata"):
        self.fetch_album_metadata.setChecked(
            config.get("fetch_extended_album_metadata", True)
        )
    if hasattr(self, "fetch_audio_metadata"):
        self.fetch_audio_metadata.setChecked(config.get("fetch_audio_features", True))
    if hasattr(self, "fetch_credits_metadata"):
        self.fetch_credits_metadata.setChecked(config.get("fetch_track_credits", True))

    # Audio Metadata Settings
    self.metadata_separator.setText(config.get("metadata_separator"))
    self.overwrite_existing_metadata.setChecked(
        config.get("overwrite_existing_metadata")
    )
    self.embed_branding.setChecked(config.get("embed_branding"))
    self.embed_cover.setChecked(config.get("embed_cover"))
    self.embed_artist.setChecked(config.get("embed_artist"))
    self.embed_album.setChecked(config.get("embed_album"))
    self.embed_albumartist.setChecked(config.get("embed_albumartist"))
    self.embed_name.setChecked(config.get("embed_name"))
    self.embed_year.setChecked(config.get("embed_year"))
    self.embed_discnumber.setChecked(config.get("embed_discnumber"))
    self.embed_tracknumber.setChecked(config.get("embed_tracknumber"))
    self.embed_genre.setChecked(config.get("embed_genre"))
    self.embed_performers.setChecked(config.get("embed_performers"))
    self.embed_producers.setChecked(config.get("embed_producers"))
    self.embed_writers.setChecked(config.get("embed_writers"))
    self.embed_label.setChecked(config.get("embed_label"))
    self.embed_copyright.setChecked(config.get("embed_copyright"))
    self.embed_description.setChecked(config.get("embed_description"))
    self.embed_language.setChecked(config.get("embed_language"))
    self.embed_isrc.setChecked(config.get("embed_isrc"))
    self.embed_length.setChecked(config.get("embed_length"))
    self.embed_url.setChecked(config.get("embed_url"))
    self.embed_key.setChecked(config.get("embed_key"))
    self.embed_bpm.setChecked(config.get("embed_bpm"))
    self.embed_compilation.setChecked(config.get("embed_compilation"))
    self.embed_lyrics.setChecked(config.get("embed_lyrics"))
    self.embed_explicit.setChecked(config.get("embed_explicit"))
    self.embed_upc.setChecked(config.get("embed_upc"))
    self.embed_service_id.setChecked(config.get("embed_service_id"))
    self.embed_timesignature.setChecked(config.get("embed_timesignature"))
    self.embed_acousticness.setChecked(config.get("embed_acousticness"))
    self.embed_danceability.setChecked(config.get("embed_danceability"))
    self.embed_energy.setChecked(config.get("embed_energy"))
    self.embed_instrumentalness.setChecked(config.get("embed_instrumentalness"))
    self.embed_liveness.setChecked(config.get("embed_liveness"))
    self.embed_loudness.setChecked(config.get("embed_loudness"))
    self.embed_speechiness.setChecked(config.get("embed_speechiness"))
    self.embed_valence.setChecked(config.get("embed_valence"))

    # Video Download Settings
    self.video_download_path.setText(config.get("video_download_path"))
    self.movie_file_format.setText(config.get("movie_file_format"))
    self.movie_path_formatter.setText(config.get("movie_path_formatter"))
    self.show_file_format.setText(config.get("show_file_format"))
    self.show_path_formatter.setText(config.get("show_path_formatter"))
    self.preferred_video_resolution.setValue(config.get("preferred_video_resolution"))
    self.download_subtitles.setChecked(config.get("download_subtitles"))
    self.preferred_audio_language.setText(config.get("preferred_audio_language"))
    self.preferred_subtitle_language.setText(config.get("preferred_subtitle_language"))
    self.download_all_available_audio.setChecked(
        config.get("download_all_available_audio")
    )
    self.download_all_available_subtitles.setChecked(
        config.get("download_all_available_subtitles")
    )


def save_config(self):
    # General Settings
    config.set("language_index", self.language.currentIndex())
    config.set("explicit_label", self.explicit_label.text())
    config.set("download_copy_btn", self.download_copy_btn.isChecked())
    config.set("download_open_btn", self.download_open_btn.isChecked())
    config.set("download_locate_btn", self.download_locate_btn.isChecked())
    config.set("download_delete_btn", self.download_delete_btn.isChecked())
    config.set("show_search_thumbnails", self.show_search_thumbnails.isChecked())
    config.set("show_download_thumbnails", self.show_download_thumbnails.isChecked())
    config.set("thumbnail_size", self.thumbnail_size.value())
    config.set("max_search_results", self.max_search_results.value())
    config.set("disable_download_popups", self.disable_download_popups.isChecked())
    config.set(
        "windows_10_explorer_thumbnails",
        self.windows_10_explorer_thumbnails.isChecked(),
    )
    config.set("mirror_spotify_playback", self.mirror_spotify_playback.isChecked())
    config.set("close_to_tray", self.close_to_tray.isChecked())
    config.set("check_for_updates", self.check_for_updates.isChecked())
    config.set(
        "illegal_character_replacement", self.illegal_character_replacement.text()
    )
    config.set("raw_media_download", self.raw_media_download.isChecked())
    config.set(
        "rotate_active_account_number", self.rotate_active_account_number.isChecked()
    )
    config.set("download_delay", self.download_delay.value())
    config.set("download_delay_variance", self.download_delay_variance.value())
    config.set("download_chunk_size", self.download_chunk_size.value())
    config.set("maximum_queue_workers", self.maximum_queue_workers.value())
    config.set("maximum_download_workers", self.maximum_download_workers.value())
    config.set("enable_retry_worker", self.enable_retry_worker.isChecked())
    config.set("retry_worker_delay", self.retry_worker_delay.value())

    # Search Settings
    config.set("enable_search_tracks", self.enable_search_tracks.isChecked())
    config.set("enable_search_albums", self.enable_search_albums.isChecked())
    config.set("enable_search_playlists", self.enable_search_playlists.isChecked())
    config.set("enable_search_artists", self.enable_search_artists.isChecked())
    config.set("enable_search_episodes", self.enable_search_episodes.isChecked())
    config.set("enable_search_podcasts", self.enable_search_podcasts.isChecked())
    config.set("enable_search_audiobooks", self.enable_search_audiobooks.isChecked())

    # Search Filter Settings
    config.set("f_search_tracks", self.f_search_tracks.isChecked())
    config.set("f_search_artists", self.f_search_artists.isChecked())
    config.set("f_search_albums", self.f_search_albums.isChecked())
    config.set("f_search_playlists", self.f_search_playlists.isChecked())

    # Search Filter prefix Settings
    config.set("search_prefix", self.search_prefix.text())

    # Download Queue Filter Settings
    config.set(
        "download_queue_show_waiting", self.download_queue_show_waiting.isChecked()
    )
    config.set(
        "download_queue_show_failed", self.download_queue_show_failed.isChecked()
    )
    config.set(
        "download_queue_show_cancelled", self.download_queue_show_cancelled.isChecked()
    )
    config.set(
        "download_queue_show_unavailable",
        self.download_queue_show_unavailable.isChecked(),
    )
    config.set(
        "download_queue_show_completed", self.download_queue_show_completed.isChecked()
    )

    # Audio Download Settings
    config.set("audio_download_path", self.audio_download_path.text())
    config.set("track_file_format", self.track_file_format.text())
    config.set("track_path_formatter", self.track_path_formatter.text())
    config.set("podcast_file_format", self.podcast_file_format.text())
    config.set("podcast_path_formatter", self.podcast_path_formatter.text())
    config.set("use_playlist_path", self.use_playlist_path.isChecked())
    config.set("playlist_path_formatter", self.playlist_path_formatter.text())
    config.set("create_m3u_file", self.create_m3u_file.isChecked())
    config.set("m3u_path_formatter", self.m3u_path_formatter.text())
    config.set("extinf_separator", self.extinf_separator.text())
    config.set("extinf_label", self.extinf_label.text())
    config.set("save_album_cover", self.save_album_cover.isChecked())
    config.set("album_cover_format", self.album_cover_format.text())
    config.set("file_bitrate", self.file_bitrate.text())
    config.set("file_hertz", self.file_hertz.value())
    config.set("use_custom_file_bitrate", self.use_custom_file_bitrate.isChecked())
    config.set("download_lyrics", self.download_lyrics.isChecked())
    config.set(
        "only_download_synced_lyrics", self.only_download_synced_lyrics.isChecked()
    )
    config.set(
        "only_download_plain_lyrics", self.only_download_plain_lyrics.isChecked()
    )
    config.set("save_lrc_file", self.save_lrc_file.isChecked())
    config.set("translate_file_path", self.translate_file_path.isChecked())

    # Spotify Web API Override Settings
    if hasattr(self, "spotify_webapi_override_client_id"):
        config.set(
            "spotify_webapi_override_client_id",
            self.spotify_webapi_override_client_id.text(),
        )
    if hasattr(self, "spotify_webapi_override_client_secret"):
        config.set(
            "spotify_webapi_override_client_secret",
            self.spotify_webapi_override_client_secret.text(),
        )

    # Metadata Fetching Options (API Call Reduction)
    if hasattr(self, "fetch_artist_metadata"):
        config.set("fetch_genre_metadata", self.fetch_artist_metadata.isChecked())
    if hasattr(self, "fetch_album_metadata"):
        config.set(
            "fetch_extended_album_metadata", self.fetch_album_metadata.isChecked()
        )
    if hasattr(self, "fetch_audio_metadata"):
        config.set("fetch_audio_features", self.fetch_audio_metadata.isChecked())
    if hasattr(self, "fetch_credits_metadata"):
        config.set("fetch_track_credits", self.fetch_credits_metadata.isChecked())

    # Audio Metadata Settings
    config.set("metadata_separator", self.metadata_separator.text())
    config.set(
        "overwrite_existing_metadata", self.overwrite_existing_metadata.isChecked()
    )
    config.set("embed_branding", self.embed_branding.isChecked())
    config.set("embed_cover", self.embed_cover.isChecked())
    config.set("embed_artist", self.embed_artist.isChecked())
    config.set("embed_album", self.embed_album.isChecked())
    config.set("embed_albumartist", self.embed_albumartist.isChecked())
    config.set("embed_name", self.embed_name.isChecked())
    config.set("embed_year", self.embed_year.isChecked())
    config.set("embed_discnumber", self.embed_discnumber.isChecked())
    config.set("embed_tracknumber", self.embed_tracknumber.isChecked())
    config.set("embed_genre", self.embed_genre.isChecked())
    config.set("embed_performers", self.embed_performers.isChecked())
    config.set("embed_producers", self.embed_producers.isChecked())
    config.set("embed_writers", self.embed_writers.isChecked())
    config.set("embed_label", self.embed_label.isChecked())
    config.set("embed_copyright", self.embed_copyright.isChecked())
    config.set("embed_description", self.embed_description.isChecked())
    config.set("embed_language", self.embed_language.isChecked())
    config.set("embed_isrc", self.embed_isrc.isChecked())
    config.set("embed_length", self.embed_length.isChecked())
    config.set("embed_url", self.embed_url.isChecked())
    config.set("embed_key", self.embed_key.isChecked())
    config.set("embed_bpm", self.embed_bpm.isChecked())
    config.set("embed_compilation", self.embed_compilation.isChecked())
    config.set("embed_lyrics", self.embed_lyrics.isChecked())
    config.set("embed_explicit", self.embed_explicit.isChecked())
    config.set("embed_upc", self.embed_upc.isChecked())
    config.set("embed_service_id", self.embed_service_id.isChecked())
    config.set("embed_timesignature", self.embed_timesignature.isChecked())
    config.set("embed_acousticness", self.embed_acousticness.isChecked())
    config.set("embed_danceability", self.embed_danceability.isChecked())
    config.set("embed_energy", self.embed_energy.isChecked())
    config.set("embed_instrumentalness", self.embed_instrumentalness.isChecked())
    config.set("embed_liveness", self.embed_liveness.isChecked())
    config.set("embed_loudness", self.embed_loudness.isChecked())
    config.set("embed_speechiness", self.embed_speechiness.isChecked())
    config.set("embed_valence", self.embed_valence.isChecked())

    # Video Download Settings
    config.set("video_download_path", self.video_download_path.text())
    config.set("movie_file_format", self.movie_file_format.text())
    config.set("movie_path_formatter", self.movie_path_formatter.text())
    config.set("show_file_format", self.show_file_format.text())
    config.set("show_path_formatter", self.show_path_formatter.text())
    config.set("preferred_video_resolution", self.preferred_video_resolution.value())
    config.set("download_subtitles", self.download_subtitles.isChecked())
    config.set("preferred_audio_language", self.preferred_audio_language.text())
    config.set("preferred_subtitle_language", self.preferred_subtitle_language.text())
    config.set(
        "download_all_available_audio", self.download_all_available_audio.isChecked()
    )
    config.set(
        "download_all_available_subtitles",
        self.download_all_available_subtitles.isChecked(),
    )

    config.save()
