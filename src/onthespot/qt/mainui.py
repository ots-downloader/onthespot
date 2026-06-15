import os
import shutil
import threading
import time
import traceback
from urllib3.exceptions import MaxRetryError, NewConnectionError
from PyQt6 import uic, QtGui
from PyQt6.QtCore import QThread, QDir, Qt, pyqtSignal, QObject, QTimer
from PyQt6.QtGui import QIcon, QColor
from PyQt6.QtWidgets import QApplication, QMainWindow, QHeaderView, QLabel, QPushButton, QProgressBar, QTableWidgetItem, QFileDialog, QRadioButton, QHBoxLayout, QWidget, QColorDialog, QGroupBox, QVBoxLayout, QLineEdit
from ..accounts import get_account_token, FillAccountPool
from ..api.apple_music import apple_music_add_account, apple_music_get_track_metadata
from ..api.bandcamp import bandcamp_add_account, bandcamp_get_track_metadata
from ..api.deezer import deezer_add_account, deezer_get_track_metadata
from ..api.qobuz import qobuz_add_account, qobuz_get_track_metadata
from ..api.soundcloud import soundcloud_add_account, soundcloud_get_token, soundcloud_get_track_metadata
from ..api.spotify import MirrorSpotifyPlayback, spotify_get_token, spotify_get_track_metadata, spotify_get_podcast_episode_metadata, spotify_new_session
from ..api.tidal import tidal_add_account_pt1, tidal_add_account_pt2, tidal_get_track_metadata
from ..api.youtube_music import youtube_music_add_account, youtube_music_get_track_metadata
from ..api.generic import generic_add_account, generic_get_track_metadata, generic_list_extractors
from ..api.crunchyroll import crunchyroll_add_account, crunchyroll_get_episode_metadata
from ..downloader import DownloadWorker, RetryWorker
from ..otsconfig import config, cache_dir
from ..runtimedata import account_pool, download_queue, download_queue_lock, get_init_tray, parsing, parsing_lock, pending, pending_lock, get_logger, temp_download_path
from .dl_progressbtn import DownloadActionsButtons
from .settings import load_config, save_config
from .thumb_listitem import LabelWithThumb
from ..utils import is_latest_release, open_item, format_bytes
from ..search import get_search_results

logger = get_logger('gui.main_ui')


class QueueWorker(QObject):
    add_item_to_download_list = pyqtSignal(dict, dict)

    def __init__(self):
        super().__init__()
        self.is_running = True
        self.thread = threading.Thread(target=self.run)


    def start(self):
        self.thread.start()


    def run(self):
        while self.is_running:
            if pending:
                try:
                    local_id = next(iter(pending))
                    with pending_lock:
                        item = pending.pop(local_id)
                    token = get_account_token(item['item_service'])
                    item_metadata = globals()[f"{item['item_service']}_get_{item['item_type']}_metadata"](token, item['item_id'])
                    if item_metadata:
                        self.add_item_to_download_list.emit(item, item_metadata)
                        # Padding for 'GLib-ERROR : Creating pipes for GWakeup: Too many open files Trace/breakpoint trap'
                        # when mass downloading cached responses with download queue thumbnails enabled.
                        if config.get('show_download_thumbnails'):
                            time.sleep(0.1)
                    continue
                except Exception as e:
                    logger.error(f"Unknown Exception for {item}: {str(e)}\nTraceback: {traceback.format_exc()}")
                    with pending_lock:
                        pending[local_id] = item
            else:
                time.sleep(0.2)


    def stop(self):
        logger.info('Stopping Queue Worker')
        self.is_running = False
        self.thread.join()


class MainWindow(QMainWindow):
    def closeEvent(self, event):
        if config.get('close_to_tray') and get_init_tray():
            event.ignore()
            self.hide()


    def __init__(self, _dialog, start_url=''):
        super(MainWindow, self).__init__()
        self.path = os.path.dirname(os.path.realpath(__file__))
        self.icon_cache = {}
        QApplication.setStyle("fusion")
        uic.loadUi(os.path.join(self.path, "qtui", "main.ui"), self)
        self.setWindowIcon(self.get_icon('onthespot'))
        self.centralwidget.setStyleSheet(config.get('theme'))

        # Inject the Spotify Web API override credential fields into the settings page
        self.setup_spotify_oauth_override()

        self.start_url = start_url
        logger.info(f"Initialising main window, logging session : {config.session_uuid}")

        # Fill the value from configs
        logger.info("Loading configurations..")
        load_config(self)

        self.__splash_dialog = _dialog

        # Start/create session builder and queue processor
        fillaccountpool = FillAccountPool(gui=True)
        fillaccountpool.finished.connect(self.session_load_done)
        fillaccountpool.progress.connect(self.show_popup_dialog)
        fillaccountpool.start()

        for i in range(config.get('maximum_queue_workers')):
            queueworker = QueueWorker()
            queueworker.add_item_to_download_list.connect(self.add_item_to_download_list)
            queueworker.start()

        for i in range(config.get('maximum_download_workers')):
            downloadworker = DownloadWorker(gui=True)
            downloadworker.progress.connect(self.update_item_in_download_list)
            downloadworker.start()

        if config.get('enable_retry_worker'):
            retryworker = RetryWorker(gui=True)
            retryworker.start()

        self.mirrorplayback = MirrorSpotifyPlayback()
        if config.get('mirror_spotify_playback'):
            self.mirrorplayback.start()

        # Bind button click
        self.bind_button_inputs()

        # Set the table header properties
        self.set_table_props()
        logger.info("Main window init completed !")


    def get_icon(self, name):
        if name not in self.icon_cache:
            icon_path = os.path.join(config.app_root, 'resources', 'icons', f'{name}.png')
            self.icon_cache[name] = QIcon(icon_path)
        return self.icon_cache[name]


    def open_theme_dialog(self):
        colorpicker = QColorDialog(self)
        colorpicker.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        colorpicker.setWindowFlag(Qt.WindowType.Dialog, True)
        colorpicker.setWindowTitle("OnTheSpot - Color Picker")
        colorpicker.setStyleSheet(config.get('theme'))

        if colorpicker.exec() == QColorDialog.DialogCode.Accepted:
            color = colorpicker.selectedColor()

            if color.isValid():
                r, g, b = color.red(), color.green(), color.blue()
                luminance = (0.299 * r + 0.587 * g + 0.114 * b)

                if luminance < 128:
                    # Dark color, set light font and progress bar
                    stylesheet = f'background-color: {color.name()}; color: white;'
                else:
                    # Light color, set dark font and progress bar
                    stylesheet = f'background-color: {color.name()}; color: black;'
                config.set('theme', stylesheet)
                config.save()
                self.centralwidget.setStyleSheet(stylesheet)
                self.__splash_dialog.update_theme(stylesheet)


    def setup_spotify_oauth_override(self):
        """Inject the optional Spotify Web API override credential fields into
        the settings page, above the gb2 group box. Spotify hard rate-limits the
        shared librespot client, so supplying your own Spotify app credentials
        (their own quota) is the reliable way to keep search/metadata working."""
        if not hasattr(self, 'gb2'):
            logger.warning("Settings anchor 'gb2' not found; skipping OAuth override UI")
            return
        parent_layout = self.gb2.parent().layout()
        gb2_index = None
        for i in range(parent_layout.count()):
            item = parent_layout.itemAt(i)
            if item and item.widget() == self.gb2:
                gb2_index = i
                break
        if gb2_index is None:
            return

        gb = QGroupBox(self.tr("Spotify Web API Credentials (recommended)"))
        gb.setStyleSheet("QGroupBox { font-weight: bold; }")
        layout = QVBoxLayout()

        explanation = QLabel(self.tr(
            "Spotify rate-limits OnTheSpot's shared login, which breaks search and "
            "downloads. To fix it, create your own free Spotify app and paste its "
            "credentials below - Web API calls then use your own quota.\n\n"
            "1. Open the Spotify Developer Dashboard and create an app (Web API).\n"
            "2. Set any Redirect URI, e.g. http://127.0.0.1:8888/callback.\n"
            "3. Copy the Client ID and Client Secret into the fields below, then Save.\n\n"
            "Note: a Spotify Premium account is required to create an app, and these "
            "credentials are personal - do not share them."
        ))
        explanation.setWordWrap(True)
        explanation.setStyleSheet("color: #888; margin-bottom: 8px; font-weight: normal;")
        layout.addWidget(explanation)

        dashboard_link = QLabel('<a href="https://developer.spotify.com/dashboard">'
                                + self.tr("Open the Spotify Developer Dashboard") + '</a>')
        dashboard_link.setOpenExternalLinks(True)
        dashboard_link.setStyleSheet("font-weight: normal;")
        layout.addWidget(dashboard_link)

        id_row = QHBoxLayout()
        id_label = QLabel(self.tr("Client ID:"))
        id_label.setMinimumWidth(110)
        self.spotify_webapi_override_client_id = QLineEdit()
        self.spotify_webapi_override_client_id.setText(config.get('spotify_webapi_override_client_id', ''))
        self.spotify_webapi_override_client_id.setPlaceholderText(self.tr("Leave empty to use the default librespot login"))
        id_row.addWidget(id_label)
        id_row.addWidget(self.spotify_webapi_override_client_id)
        layout.addLayout(id_row)

        secret_row = QHBoxLayout()
        secret_label = QLabel(self.tr("Client Secret:"))
        secret_label.setMinimumWidth(110)
        self.spotify_webapi_override_client_secret = QLineEdit()
        self.spotify_webapi_override_client_secret.setText(config.get('spotify_webapi_override_client_secret', ''))
        self.spotify_webapi_override_client_secret.setPlaceholderText(self.tr("Leave empty to use the default librespot login"))
        self.spotify_webapi_override_client_secret.setEchoMode(QLineEdit.EchoMode.Password)
        secret_row.addWidget(secret_label)
        secret_row.addWidget(self.spotify_webapi_override_client_secret)
        layout.addLayout(secret_row)

        gb.setLayout(layout)
        parent_layout.insertWidget(gb2_index, gb)


    def bind_button_inputs(self):
        # Connect button click signals
        self.btn_search.clicked.connect(self.fill_search_table)

        self.login_service.currentIndexChanged.connect(self.set_login_fields)
        self.language.currentIndexChanged.connect(self.language_change)

        self.btn_save_config.clicked.connect(self.update_config)
        self.btn_reset_config.clicked.connect(self.reset_app_config)

        self.toggle_theme_button.clicked.connect(self.open_theme_dialog)

        self.btn_progress_retry_all.clicked.connect(self.retry_cancelled_and_failed_downloads)
        self.btn_progress_cancel_all.clicked.connect(self.cancel_all_downloads)
        self.btn_audio_download_path_browse.clicked.connect(lambda: self.select_dir(self.audio_download_path))
        self.btn_video_download_path.clicked.connect(lambda: self.select_dir(self.video_download_path))

        self.btn_download_tmp_browse.clicked.connect(lambda: self.select_dir(self.tmp_dl_root))
        self.tmp_dl_root.textChanged.connect(self.update_tmp_dir)
        self.search_term.returnPressed.connect(self.fill_search_table)
        self.btn_progress_clear_complete.clicked.connect(self.remove_completed_from_download_list)

        self.btn_search_filter_toggle.clicked.connect(lambda toggle: self.group_search_items.show() if self.group_search_items.isHidden() else self.group_search_items.hide())
        self.btn_search_filter_toggle.clicked.connect(lambda switch: self.btn_search_filter_toggle.setIcon(self.get_icon('collapse_down')) if self.group_search_items.isHidden() else self.btn_search_filter_toggle.setIcon(self.get_icon('collapse_up')))
        self.btn_download_filter_toggle.clicked.connect(lambda toggle: self.group_download_items.show() if self.group_download_items.isHidden() else self.group_download_items.hide())
        self.btn_download_filter_toggle.clicked.connect(lambda switch: self.btn_download_filter_toggle.setIcon(self.get_icon('collapse_up')) if self.group_download_items.isHidden() else self.btn_download_filter_toggle.setIcon(self.get_icon('collapse_down')))

        self.download_queue_show_waiting.stateChanged.connect(self.update_table_visibility)
        self.download_queue_show_failed.stateChanged.connect(self.update_table_visibility)
        self.download_queue_show_unavailable.stateChanged.connect(self.update_table_visibility)
        self.download_queue_show_cancelled.stateChanged.connect(self.update_table_visibility)
        self.download_queue_show_completed.stateChanged.connect(self.update_table_visibility)

        self.download_queue_show_waiting.stateChanged.connect(self.update_table_visibility)
        self.download_queue_show_failed.stateChanged.connect(self.update_table_visibility)
        self.download_queue_show_cancelled.stateChanged.connect(self.update_table_visibility)
        self.download_queue_show_unavailable.stateChanged.connect(self.update_table_visibility)
        self.download_queue_show_completed.stateChanged.connect(self.update_table_visibility)

        self.mirror_spotify_playback.stateChanged.connect(self.manage_mirror_spotify_playback)

        self.settings_bookmark_accounts.clicked.connect(lambda: self.settings_scroll_area.verticalScrollBar().setValue(0))
        self.settings_bookmark_general.clicked.connect(lambda: self.settings_scroll_area.verticalScrollBar().setValue(328))
        self.settings_bookmark_audio_downloads.clicked.connect(lambda: self.settings_scroll_area.verticalScrollBar().setValue(1176))
        self.settings_bookmark_audio_metadata.clicked.connect(lambda: self.settings_scroll_area.verticalScrollBar().setValue(2019))
        self.settings_bookmark_video_downloads.clicked.connect(lambda: self.settings_scroll_area.verticalScrollBar().setValue(9999))


        self.clear_cache.clicked.connect(lambda:
            shutil.rmtree(os.path.join(cache_dir(), "reqcache")) and
            shutil.rmtree(os.path.join(cache_dir(), "logs")) and
            self.show_popup_dialog(self.tr("Cache Cleared"))
            )
        self.export_logs.clicked.connect(lambda: shutil.copy(
            os.path.join(cache_dir(), "logs", config.session_uuid, "onthespot.log"),
            os.path.join(os.path.expanduser("~"), "Downloads", "onthespot.log")) and
            self.show_popup_dialog(self.tr("Logs exported to '{0}'").format(os.path.join(os.path.expanduser("~"), "Downloads", "onthespot.log") or True))
            )
        self.donate.clicked.connect(lambda: open_item('https://justin025.github.io/about.html'))


    def set_table_props(self):
        # Sessions table
        #self.tbl_sessions.setSortingEnabled(True)
        self.tbl_sessions.horizontalHeader().setSectionsMovable(True)
        self.tbl_sessions.horizontalHeader().setSectionsClickable(True)
        self.tbl_sessions.horizontalHeader().resizeSection(0, 16)
        for i in range(1, 7):
            self.tbl_sessions.horizontalHeader().setSectionResizeMode(i, QHeaderView.ResizeMode.Stretch)
        self.set_login_fields()

        # Search results table
        #self.tbl_search_results.setSortingEnabled(True)
        self.tbl_search_results.horizontalHeader().setSectionsMovable(True)
        self.tbl_search_results.horizontalHeader().setSectionsClickable(True)
        self.tbl_search_results.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for i in range(1,5):
            self.tbl_search_results.horizontalHeader().setSectionResizeMode(i, QHeaderView.ResizeMode.Interactive)

        # Download progress table
        #self.tbl_dl_progress.setSortingEnabled(True)
        self.tbl_dl_progress.horizontalHeader().setSectionsMovable(True)
        self.tbl_dl_progress.horizontalHeader().setSectionsClickable(True)
        if not config.get("debug_mode"):
            self.tbl_dl_progress.setColumnWidth(0, 0)
        self.tbl_dl_progress.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        for i in range(2,7):
            self.tbl_dl_progress.horizontalHeader().setSectionResizeMode(i, QHeaderView.ResizeMode.Interactive)

        return True


    def language_change(self):
        config.save()
        self.show_popup_dialog(self.tr("The application's language has been changed, please restart the app."))


    def reset_app_config(self):
        config.reset()
        self.show_popup_dialog(self.tr("The application setting was cleared successfully !\n Please restart the application."))


    def select_dir(self, output):
        self.setStyleSheet(config.get('theme'))
        path = QFileDialog.getExistingDirectory(self, 'OnTheSpot - Select Directory', os.path.expanduser("~"))
        if path.strip() != '':
            output.setText(QDir.toNativeSeparators(path))


    def update_tmp_dir(self):
        temp_download_path.clear()
        new_path = self.tmp_dl_root.text()
        if new_path:
            temp_download_path.append(new_path)

    def show_popup_dialog(self, txt, btn_hide=False, download=False):
        if download and config.get('disable_download_popups'):
            return
        self.__splash_dialog.lb_main.setText(str(txt))
        if btn_hide:
            self.__splash_dialog.btn_close.hide()
        else:
            self.__splash_dialog.btn_close.show()
        self.__splash_dialog.show()


    def session_load_done(self):
        self.__splash_dialog.hide()
        self.__splash_dialog.btn_close.show()
        self.fill_account_table()
        self.show()
        if self.start_url.strip() != '':
            logger.info(f'Session was started with query of {self.start_url}')
            self.tabview.setCurrentIndex(1)
            self.search_term.setText(self.start_url.strip())
            self.fill_search_table()
        self.start_url = ''
        # Update Checker
        if config.get("check_for_updates"):
            if not is_latest_release():
                self.show_popup_dialog(self.tr("<p>An update is available at the link below,<p><a style='color: #6495ed;' href='https://github.com/justin025/onthespot/releases/latest'>https://github.com/justin025/onthespot/releases/latest</a>"))


    def fill_account_table(self):
        # Clear the table
        while self.tbl_sessions.rowCount() > 0:
            self.tbl_sessions.removeRow(0)
        sn = 0
        for account in account_pool:
            sn = sn + 1
            rows = self.tbl_sessions.rowCount()

            radiobutton = QRadioButton()
            radiobutton.clicked.connect(lambda: config.set('active_account_number', self.tbl_sessions.currentRow()))
            if sn == config.get("active_account_number") + 1:
                radiobutton.setChecked(True)

            remove_btn = QPushButton(self.tbl_sessions)
            remove_btn.setIcon(self.get_icon('trash'))
            remove_btn.clicked.connect(self.user_table_remove_click)

            status = QTableWidgetItem(str(account["status"]).title())
            status.setIcon(self.get_icon(account["status"]))

            service = QTableWidgetItem(str(account["service"]).replace('_', ' ').title())
            service.setIcon(self.get_icon(account["service"]))

            self.tbl_sessions.insertRow(rows)
            self.tbl_sessions.setCellWidget(rows, 0, radiobutton)
            self.tbl_sessions.setItem(rows, 1, QTableWidgetItem(account["username"][:22]))
            self.tbl_sessions.setItem(rows, 2, QTableWidgetItem(service))
            self.tbl_sessions.setItem(rows, 3, QTableWidgetItem(str(account["account_type"]).title()))
            self.tbl_sessions.setItem(rows, 4, QTableWidgetItem(account["bitrate"]))
            self.tbl_sessions.setItem(rows, 5, QTableWidgetItem(status))
            self.tbl_sessions.setCellWidget(rows, 6, remove_btn)
        logger.info("Accounts table was populated !")


    def add_item_to_download_list(self, item, item_metadata):
        # Skip rendering QButtons if they are not in use
        copy_btn = None
        open_btn = None
        locate_btn = None
        delete_btn = None

        # Items
        pbar = QProgressBar()
        pbar.setStyleSheet("""
            QProgressBar {
                text-align: center;
            }
            QProgressBar::chunk {
                background-color: #2596BE;
                color: white;
            }
        """)
        pbar.setValue(0)
        pbar.setMinimumHeight(30)
        if config.get("download_copy_btn"):
            copy_btn = QPushButton()
            #copy_btn.setText('Copy')
            copy_btn.setIcon(self.get_icon('link'))
            copy_btn.setToolTip(self.tr('Copy'))
            copy_btn.setMinimumHeight(30)
            copy_btn.hide()
        cancel_btn = QPushButton()
        # cancel_btn.setText('Cancel')
        cancel_btn.setIcon(self.get_icon('stop'))
        cancel_btn.setToolTip(self.tr('Cancel'))
        cancel_btn.setMinimumHeight(30)
        cancel_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        retry_btn = QPushButton()
        #retry_btn.setText('Retry')
        retry_btn.setIcon(self.get_icon('retry'))
        retry_btn.setToolTip(self.tr('Retry'))
        retry_btn.setMinimumHeight(30)
        retry_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        retry_btn.hide()
        if config.get("download_open_btn"):
            open_btn = QPushButton()
            #open_btn.setText('Open')
            open_btn.setIcon(self.get_icon('file'))
            open_btn.setToolTip(self.tr('Open'))
            open_btn.setMinimumHeight(30)
            open_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            open_btn.hide()
        if config.get("download_locate_btn"):
            locate_btn = QPushButton()
            #locate_btn.setText('Locate')
            locate_btn.setIcon(self.get_icon('folder'))
            locate_btn.setToolTip(self.tr('Locate'))
            locate_btn.setMinimumHeight(30)
            locate_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            locate_btn.hide()
        if config.get("download_delete_btn"):
            delete_btn = QPushButton()
            #delete_btn.setText('Delete')
            delete_btn.setIcon(self.get_icon('trash'))
            delete_btn.setToolTip(self.tr('Delete'))
            delete_btn.setMinimumHeight(30)
            delete_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            delete_btn.hide()

        item_by = item_metadata.get('artists') if item_metadata.get('artists') else item_metadata.get('show_name')

        playlist_name = ''
        playlist_by = ''
        if item['parent_category'] == 'playlist':
            item_category = f'Playlist: {item["playlist_name"]}'
            playlist_name = item.get('playlist_name')
            playlist_by = item.get('playlist_by')
        elif item['parent_category'] in ('album', 'show'):
            parent_name = item_metadata.get("album_name") if item_metadata.get("album_name") else item_metadata.get("show_name")
            item_category = f'{item["parent_category"].title()}: {parent_name}'
        else:
            item_category = f'{item["parent_category"].title()}: {item_metadata["title"]}'

        item_service = item["item_service"]
        service_label = QTableWidgetItem(str(item_service).replace('_', ' ').title())
        service_label.setIcon(self.get_icon(item_service))
        service_label.setBackground(QColor(0, 0, 0, 0))

        status_label = QLabel(self.tbl_dl_progress)
        status_label.setText(self.tr("Waiting"))
        status_label.setStyleSheet("background-color: transparent;")
        actions = DownloadActionsButtons(item['local_id'], item_metadata, pbar, copy_btn, cancel_btn, retry_btn, open_btn, locate_btn, delete_btn)

        rows = self.tbl_dl_progress.rowCount()
        self.tbl_dl_progress.insertRow(rows)
        if item_metadata.get('explicit'):
            title = config.get('explicit_label') + ' ' + item_metadata.get('title')
        else:
            title = item_metadata.get('title')
        if config.get('show_download_thumbnails') and item_metadata.get('image_url'):
            self.tbl_dl_progress.setRowHeight(rows, config.get("thumbnail_size"))
            item_label = LabelWithThumb(title, item_metadata.get('image_url'))
        else:
            item_label = QLabel(self.tbl_dl_progress)
            item_label.setText(title)
            item_label.setAlignment(Qt.AlignmentFlag.AlignLeft)
            item_label.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        item_label.setStyleSheet("background-color: transparent;")

        # Add To List
        self.tbl_dl_progress.setItem(rows, 0, QTableWidgetItem(str(item['local_id'])))
        self.tbl_dl_progress.setCellWidget(rows, 1, item_label)
        self.tbl_dl_progress.setItem(rows, 2, QTableWidgetItem(item_by))
        self.tbl_dl_progress.setItem(rows, 3, QTableWidgetItem(item_category))
        self.tbl_dl_progress.setItem(rows, 4, service_label)
        self.tbl_dl_progress.setCellWidget(rows, 5, status_label)
        self.tbl_dl_progress.setCellWidget(rows, 6, actions)

        # Hide if filter is applied
        self.update_table_visibility()

        with download_queue_lock:
            download_queue[item['local_id']] = {
                'local_id': item['local_id'],
                'available': True,
                "item_service": item["item_service"],
                "item_type": item["item_type"],
                'item_id': item['item_id'],
                'item_status': 'Waiting',
                "file_path": None,
                'parent_category': item['parent_category'],
                'playlist_name': playlist_name,
                'playlist_by': playlist_by,
                'playlist_number': item.get('playlist_number'),
                "gui": {
                    "item_label": item_label,
                    "status_label": status_label,
                    "progress_bar": pbar,
                    "btn": {
                        'actions': actions,
                        "copy": copy_btn,
                        "cancel": cancel_btn,
                        "retry": retry_btn,
                        "open": open_btn,
                        "locate": locate_btn,
                        "delete": delete_btn
                        }
                    }
                }


    def update_item_in_download_list(self, item, status, progress):
        self.statistics.setText(self.tr("{0} / {1}").format(config.get('total_downloaded_items'), format_bytes(config.get('total_downloaded_data'))))
        with download_queue_lock:
            item['gui']['status_label'].setText(status)
            item['gui']['progress_bar'].setValue(progress)
            self.update_table_visibility()
            if item['item_status'] == 'Unavailable':
                item['gui']["btn"]['cancel'].hide()
                if config.get("download_copy_btn"):
                    item['gui']['btn']['copy'].show()
                item['gui']["btn"]['retry'].hide()
                return
            elif progress == 0:
                item['gui']["btn"]['cancel'].hide()
                if config.get("download_copy_btn"):
                    item['gui']['btn']['copy'].show()
                item['gui']["btn"]['retry'].show()
                return
            elif progress == 100:
                item['gui']['btn']['cancel'].hide()
                item['gui']['btn']['retry'].hide()
                if config.get("download_copy_btn"):
                    item['gui']['btn']['copy'].show()
                if config.get("download_open_btn"):
                    item['gui']['btn']['open'].show()
                if config.get("download_locate_btn"):
                    item['gui']['btn']['locate'].show()
                if config.get("download_delete_btn"):
                    item['gui']['btn']['delete'].show()
                return
            elif progress != 0:
                item['gui']["btn"]['retry'].hide()
                if config.get("download_copy_btn"):
                    item['gui']['btn']['copy'].show()
                item['gui']["btn"]['cancel'].show()
                return


    def remove_completed_from_download_list(self):
        with download_queue_lock:
            check_row = 0
            while check_row < self.tbl_dl_progress.rowCount():
                local_id = self.tbl_dl_progress.item(check_row, 0).text()
                logger.debug(f'Removing Row: {check_row} and mediaid: {local_id}')
                if local_id in download_queue:
                    if download_queue[local_id]['item_status'] in (
                                "Cancelled",
                                "Deleted",
                                "Downloaded",
                                "Already Exists"
                            ):
                        logger.debug(f'Removing Row: {check_row} and mediaid: {local_id}')
                        self.tbl_dl_progress.removeRow(check_row)
                        download_queue.pop(local_id)
                    else:
                        check_row += 1
                else:
                    check_row += 1


    def cancel_all_downloads(self):
        with parsing_lock:
            parsing.clear()
        with pending_lock:
            pending.clear()
        with download_queue_lock:
            row_count = self.tbl_dl_progress.rowCount()
            while row_count > 0:
                for local_id in download_queue.keys():
                    logger.debug(f'Trying to cancel : {local_id}')
                    if download_queue[local_id]['item_status'] == "Waiting":
                        download_queue[local_id]['item_status'] = "Cancelled"
                        download_queue[local_id]['gui']['status_label'].setText(self.tr("Cancelled"))
                        download_queue[local_id]['gui']['status_label'].setText(self.tr("Cancelled"))
                        download_queue[local_id]['gui']['progress_bar'].setValue(0)
                        download_queue[local_id]['gui']["btn"]['cancel'].hide()
                        download_queue[local_id]['gui']["btn"]['retry'].show()
                    row_count -= 1
                self.update_table_visibility()


    def retry_cancelled_and_failed_downloads(self):
        with download_queue_lock:
            row_count = self.tbl_dl_progress.rowCount()
            while row_count > 0:
                for local_id in download_queue.keys():
                    logger.debug(f'Retrying : {local_id}')
                    if download_queue[local_id]['item_status'] in ("Failed", "Cancelled"):
                        download_queue[local_id]['item_status'] = "Waiting"
                        download_queue[local_id]['gui']['status_label'].setText(self.tr("Waiting"))
                        download_queue[local_id]['gui']["btn"]['cancel'].show()
                        download_queue[local_id]['gui']["btn"]['retry'].hide()
                    row_count -= 1
                self.update_table_visibility()


    def user_table_remove_click(self):
        button = self.sender()
        button_position = button.pos()
        index = self.tbl_sessions.indexAt(button_position).row()

        del account_pool[index]
        accounts = config.get('accounts').copy()
        del accounts[index]
        config.set('accounts', accounts)
        config.save()

        self.tbl_sessions.removeRow(index)
        if config.get('active_account_number') == index or config.get('active_account_number') >= len(account_pool):
            config.set('active_account_number', 0)
            config.save()
            try:
                self.tbl_sessions.cellWidget(0, 0).setChecked(True)
            except AttributeError:
                # Account Table is empty
                pass
        self.show_popup_dialog(self.tr("Account was removed successfully."))


    def update_config(self):
        save_config(self)


    def set_login_fields(self):
        self.lb_generic_extractors.hide()

        # Apple Music
        if self.login_service.currentIndex() == 1:
            self.login_username_label.hide()
            self.login_username.hide()
            self.login_password_label.show()
            self.login_password.setPlaceholderText("Enter your media-user-token")
            self.login_password_label.setText(self.tr("Media User Token"))
            self.login_password.show()
            self.btn_login_add.clicked.disconnect()
            self.btn_login_add.show()
            self.btn_login_add.setIcon(QIcon())
            self.btn_login_add.setText(self.tr("Add Account"))
            self.btn_login_add.clicked.connect(lambda:
                (self.show_popup_dialog(self.tr("Account added, please restart the app.")) or True) and
                apple_music_add_account(self.login_password.text()) and
                self.login_password.clear()
                )

        # Bandcamp
        elif self.login_service.currentIndex() == 2:
            self.login_username_label.hide()
            self.login_username.hide()
            self.login_password_label.hide()
            self.login_password.hide()
            self.btn_login_add.clicked.disconnect()
            self.btn_login_add.show()
            self.btn_login_add.setIcon(QIcon())
            self.btn_login_add.setText(self.tr("Add Bandcamp Account"))
            self.btn_login_add.clicked.connect(lambda:
                (self.show_popup_dialog(self.tr("Public account added, please restart the app.\nLogging into personal accounts is currently unsupported, if you have any premium purchases please consider lending it to the dev team.")) or True) and
                bandcamp_add_account()
                )

        # Deezer
        elif self.login_service.currentIndex() == 3:
            self.login_username_label.hide()
            self.login_username.hide()
            self.login_password_label.show()
            self.login_password.setPlaceholderText("Enter your arl")
            self.login_password_label.setText(self.tr("ARL"))
            self.login_password.show()
            self.btn_login_add.clicked.disconnect()
            self.btn_login_add.show()
            self.btn_login_add.setIcon(QIcon())
            self.btn_login_add.setText(self.tr("Add Account"))
            self.btn_login_add.clicked.connect(lambda:
                (self.show_popup_dialog(self.tr("Account added, please restart the app.")) or True) and
                deezer_add_account(self.login_password.text()) and
                self.login_password.clear()
                )

        # Qobuz
        elif self.login_service.currentIndex() == 4:
            self.login_username_label.show()
            self.login_username_label.setText(self.tr("Email"))
            self.login_username.show()
            self.login_username.setPlaceholderText("Enter your email")
            self.login_password_label.show()
            self.login_password_label.setText(self.tr("Password"))
            self.login_password.show()
            self.login_password.setPlaceholderText("Enter your password")
            self.btn_login_add.clicked.disconnect()
            self.btn_login_add.show()
            self.btn_login_add.setIcon(QIcon())
            self.btn_login_add.setText(self.tr("Add Account"))
            self.btn_login_add.clicked.connect(lambda:
                qobuz_add_account(self.login_username.text(), self.login_password.text()) and
                (self.show_popup_dialog(self.tr("Account added, please restart the app.")) or True) and
                self.login_username.clear() and
                self.login_password.clear()
                )

        # Soundcloud
        elif self.login_service.currentIndex() == 5:
            self.login_username_label.hide()
            self.login_username.hide()
            self.login_password_label.show()
            self.login_password_label.setText(self.tr("OAuth Token"))
            self.login_password.show()
            self.login_password.setPlaceholderText("Enter your oauth_token")
            self.btn_login_add.clicked.disconnect()
            self.btn_login_add.show()
            self.btn_login_add.setIcon(QIcon())
            self.btn_login_add.setText(self.tr("Add Account"))
            self.btn_login_add.clicked.connect(lambda:
                (self.show_popup_dialog(self.tr("Account added, please restart the app.")) or True) and
                soundcloud_add_account(oauth_token=self.login_password.text()) and
                self.login_password.clear()
                )

        # Spotify
        elif self.login_service.currentIndex() == 6:
            self.login_username_label.hide()
            self.login_username.hide()
            self.login_password_label.hide()
            self.login_password.hide()
            try:
                self.btn_login_add.clicked.disconnect()
            except TypeError:
                # Default value does not have disconnect
                pass
            self.btn_login_add.show()
            self.btn_login_add.setIcon(QIcon())
            self.btn_login_add.setText(self.tr("Add Spotify Account"))
            self.btn_login_add.clicked.connect(self.add_spotify_account)

        # Tidal
        elif self.login_service.currentIndex() == 7:
            self.login_username_label.hide()
            self.login_username.hide()
            self.login_password_label.hide()
            self.login_password.hide()
            self.btn_login_add.clicked.disconnect()
            self.btn_login_add.show()
            self.btn_login_add.setIcon(QIcon())
            self.btn_login_add.setText(self.tr("Add Tidal Account"))
            self.btn_login_add.clicked.connect(self.add_tidal_account)

        # Youtube Music
        elif self.login_service.currentIndex() == 8:
            self.login_username_label.hide()
            self.login_username.hide()
            self.login_password_label.hide()
            self.login_password.hide()
            self.btn_login_add.clicked.disconnect()
            self.btn_login_add.show()
            self.btn_login_add.setIcon(QIcon())
            self.btn_login_add.setText(self.tr("Add Youtube Music Account"))
            self.btn_login_add.clicked.connect(lambda:
                (self.show_popup_dialog(self.tr("Public account added, please restart the app.")) or True) and
                youtube_music_add_account()
                )

        # Crunchyroll
        elif self.login_service.currentIndex() == 10:
            self.login_username_label.show()
            self.login_username_label.setText(self.tr("Email"))
            self.login_username.show()
            self.login_username.setPlaceholderText("Enter your email")
            self.login_password_label.show()
            self.login_password_label.setText(self.tr("Password"))
            self.login_password.show()
            self.login_password.setPlaceholderText("Enter your password")
            self.btn_login_add.clicked.disconnect()
            self.btn_login_add.show()
            self.btn_login_add.setIcon(QIcon())
            self.btn_login_add.setText(self.tr("Add Account"))
            self.btn_login_add.clicked.connect(lambda:
                (self.show_popup_dialog(self.tr("Account added, please restart the app.")) or True) and
                crunchyroll_add_account(self.login_username.text(), self.login_password.text()) and
                self.login_username.clear() and
                self.login_password.clear()
                )

        # Generic (yt-dlp)
        elif self.login_service.currentIndex() == 11:
            self.groupbox_generic_audio_download_path.show()
            self.lb_generic_extractors.show()
            self.lb_generic_extractors.setText(self.tr("<strong>The following services are officially supported by the Generic Downloader. Even if your website is not officially supported, generic downloader may be able to download media off it anyway.</strong><br>{0}").format('<br>'.join(generic_list_extractors())))
            self.login_username_label.hide()
            self.login_username.hide()
            self.login_password_label.hide()
            self.login_password.hide()
            self.btn_login_add.clicked.disconnect()
            self.btn_login_add.show()
            self.btn_login_add.setIcon(QIcon())
            self.btn_login_add.setText(self.tr("Add Generic Downloader"))
            self.btn_login_add.clicked.connect(lambda:
                (self.show_popup_dialog(self.tr("Generic Downloader added, please restart the app.")) or True) and
                generic_add_account()
                )

    def add_spotify_account(self):
        logger.info('Add spotify account clicked ')
        self.btn_login_add.setText(self.tr("Waiting..."))
        self.btn_login_add.setDisabled(True)
        self.login_service.setDisabled(True)
        self.show_popup_dialog(self.tr("Login Service Started...\nSelect 'OnTheSpot' under devices in the Spotify Desktop App."))
        login_worker = threading.Thread(target=self.add_spotify_account_worker)
        login_worker.daemon = True
        login_worker.start()


    def add_spotify_account_worker(self):
        if spotify_new_session():
            self.show_popup_dialog(self.tr("Account added, please restart the app."))
            self.btn_login_add.setText(self.tr("Please Restart The App"))
            config.set('active_account_number', len(account_pool))
            config.save()
        else:
            self.show_popup_dialog(self.tr("Account already exists."))
            self.btn_login_add.setText(self.tr("Add Account"))
        self.login_service.setDisabled(False)
        self.btn_login_add.setDisabled(False)


    def add_tidal_account(self):
        logger.info('Add spotify account clicked ')
        self.btn_login_add.setText(self.tr("Waiting..."))
        self.btn_login_add.setDisabled(True)
        self.login_service.setDisabled(True)
        device_code, verification_url = tidal_add_account_pt1()
        self.show_popup_dialog(self.tr(f"Login Service Started head to <a style='color: #6495ed;' href='https://{verification_url}'>https://{verification_url}</a> to continue."))
        login_worker = threading.Thread(target=self.add_tidal_account_worker, args=(device_code,))
        login_worker.daemon = True
        login_worker.start()


    def add_tidal_account_worker(self, device_code):
        if tidal_add_account_pt2(device_code):
            self.show_popup_dialog(self.tr("Account added, please restart the app."))
            self.btn_login_add.setText(self.tr("Please Restart The App"))
            config.set('active_account_number', len(account_pool))
            config.save()
        else:
            self.show_popup_dialog(self.tr("Account already exists."))
            self.btn_login_add.setText(self.tr("Add Account"))
        self.login_service.setDisabled(False)
        self.btn_login_add.setDisabled(False)


    def fill_search_table(self):
        while self.tbl_search_results.rowCount() > 0:
            self.tbl_search_results.removeRow(0)
        search_term = self.search_term.text().strip()
        content_types = []
        if self.enable_search_tracks.isChecked():
            content_types.append('track')
        if self.enable_search_playlists.isChecked():
            content_types.append('playlist')
        if self.enable_search_albums.isChecked():
            content_types.append('album')
        if self.enable_search_artists.isChecked():
            content_types.append('artist')
        if self.enable_search_podcasts.isChecked():
            content_types.append('show')
        if self.enable_search_episodes.isChecked():
            content_types.append('episode')
        if self.enable_search_audiobooks.isChecked():
            content_types.append('audiobook')

        results = get_search_results(search_term, content_types)
        if results is None:
            self.show_popup_dialog(self.tr("You need to login to at least one account to use this feature."))
            self.search_term.setText('')
            return
        elif results is True:
            self.show_popup_dialog(self.tr("Item is being parsed and will be added to the download queue shortly."))
            self.search_term.setText('')
            return
        elif results is False and account_pool[config.get('active_account_number')]['service'] == 'generic':
            self.show_popup_dialog(self.tr("Generic Downloader does not support search, please enter a supported url."))
            self.search_term.setText('')
            return
        elif results is False:
            self.show_popup_dialog(self.tr("Invalid item, please check your query or account settings"))
            self.search_term.setText('')
            return

        def download_btn_clicked(item_name, item_url, item_service, item_type, item_id):
            parsing[item_id] = {
                'item_url': item_url,
                'item_service': item_service,
                'item_type': item_type,
                'item_id': item_id
            }
            self.show_popup_dialog(self.tr("{0} is being parsed and will be added to the download queue shortly.").format(f"{item_type.title()}: {item_name}"), download=True)

        def copy_btn_clicked(item_url):
            QApplication.clipboard().setText(item_url)
            self.show_popup_dialog(self.tr("The URL has been copied to the clipboard."), download=True)

        for result in results:
            download_btn = QPushButton(self.tbl_search_results)
            download_btn.setIcon(self.get_icon('download'))
            download_btn.setMinimumHeight(30)
            download_btn.setStyleSheet(config.get('theme'))
            download_btn.clicked.connect(lambda x,
                                    item_name=result['item_name'],
                                    item_url=result['item_url'],
                                    item_type=result['item_type'],
                                    item_id=result['item_id'],
                                    item_service=result['item_service']:
                                    download_btn_clicked(item_name, item_url, item_service, item_type, item_id)
                                    )

            copy_btn = QPushButton(self.tbl_search_results)
            copy_btn.setIcon(self.get_icon('link'))
            copy_btn.setMinimumHeight(30)
            copy_btn.setStyleSheet(config.get('theme'))
            copy_btn.clicked.connect(lambda x, item_url=result['item_url']: copy_btn_clicked(item_url))

            btn_layout = QHBoxLayout()
            btn_layout.setContentsMargins(2, 2, 2, 2)
            btn_layout.setSpacing(4)
            btn_layout.addWidget(copy_btn)
            btn_layout.addWidget(download_btn)

            btn_widget = QWidget()
            btn_widget.setStyleSheet("QWidget { background-color: transparent !important; }")
            btn_widget.setLayout(btn_layout)

            service = QTableWidgetItem(result['item_service'].replace('_', ' ').title())
            service.setIcon(self.get_icon(result["item_service"]))

            rows = self.tbl_search_results.rowCount()
            self.tbl_search_results.insertRow(rows)

            if config.get('show_search_thumbnails'):
                self.tbl_search_results.setRowHeight(rows, config.get("thumbnail_size"))
                item_label = LabelWithThumb(result['item_name'], result['item_thumbnail_url'])
            else:
                item_label = QLabel(self.tbl_dl_progress)
                item_label.setText(result['item_name'])
            item_label.setStyleSheet("background-color: transparent;")

            self.tbl_search_results.setCellWidget(rows, 0, item_label)
            self.tbl_search_results.setItem(rows, 1, QTableWidgetItem(str(result['item_by'])))
            self.tbl_search_results.setItem(rows, 2, QTableWidgetItem(result['item_type'].replace('podcast_', '').title()))
            self.tbl_search_results.setItem(rows, 3, service)
            self.tbl_search_results.setCellWidget(rows, 4, btn_widget)
            self.tbl_search_results.horizontalHeader().resizeSection(0, 450)
            self.tbl_search_results.horizontalHeader().resizeSection(4, 100)

            self.search_term.setText('')


    def update_table_visibility(self):
        show_waiting = self.download_queue_show_waiting.isChecked()
        show_failed = self.download_queue_show_failed.isChecked()
        show_unavailable = self.download_queue_show_unavailable.isChecked()
        show_cancelled = self.download_queue_show_cancelled.isChecked()
        show_completed = self.download_queue_show_completed.isChecked()

        for row in range(self.tbl_dl_progress.rowCount()):
            label = self.tbl_dl_progress.cellWidget(row, 5)  # Check the Status column
            if label:
                status = label.text()
                # Determine visibility based on checkboxes
                if (status == self.tr("Waiting") and not show_waiting) or \
                   (status == self.tr("Failed") and not show_failed) or \
                   (status == self.tr("Unavailable") and not show_unavailable) or \
                   (status == self.tr("Cancelled") and not show_cancelled) or \
                   (status == self.tr("Already Exists") and not show_completed) or \
                   (status == self.tr("Downloaded") and not show_completed):
                    self.tbl_dl_progress.hideRow(row)  # Hide the row
                else:
                    self.tbl_dl_progress.showRow(row)  # Show the row if the status is allowed


    def manage_mirror_spotify_playback(self):
        if self.mirror_spotify_playback.isChecked():
            self.mirrorplayback.start()
        else:
            self.mirrorplayback.stop()
