"""
gui.py
~~~~~~

Application entry point for the GUI mode.

Sets up the Qt application, loads translations, starts the
:class:`~onthespot.parse_item.ParsingWorker` background thread, and
optionally enables the system-tray icon.
"""

import argparse
import os

# Must be set before any protobuf/librespot imports.
os.environ["PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION"] = "python"

import sys

from PyQt6.QtCore import QTranslator
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from .otsconfig import config
from .parse_item import ParsingWorker
from .qt.mainui import MainWindow
from .qt.minidialog import MiniDialog
from .runtimedata import get_logger, set_tray_initialized

logger = get_logger("gui")


class TrayApp:
    """System-tray integration for the main window.

    Creates a tray icon with *Show* and *Quit* actions.  Single-clicking
    the icon brings the main window to the front.
    """

    def __init__(self, main_window: MainWindow) -> None:
        self.main_window = main_window

        icon_path = os.path.join(config.app_root, "resources", "icons", "onthespot.png")
        self.tray_icon = QSystemTrayIcon(self.main_window)
        self.tray_icon.setIcon(QIcon(icon_path))
        self.tray_icon.setVisible(True)

        tray_menu = QMenu()
        tray_menu.addAction("Show", self.show_window)
        tray_menu.addAction("Quit", self.quit_application)
        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.activated.connect(self._on_tray_icon_activated)

    def _on_tray_icon_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.show_window()

    def show_window(self) -> None:
        """Raise and focus the main window."""
        self.main_window.show()
        self.main_window.raise_()
        self.main_window.activateWindow()

    def quit_application(self) -> None:
        """Quit the Qt application."""
        QApplication.quit()


def _parse_args() -> argparse.Namespace:
    """Parse command-line arguments for the GUI entry point."""
    parser = argparse.ArgumentParser(
        prog="onthespot",
        description="OnTheSpot — music downloader",
    )
    parser.add_argument(
        "-u",
        "--url",
        metavar="URL",
        default="",
        help="Open the application with this URL pre-loaded.",
    )
    # Parse only known args so Qt's own argv handling is not disrupted.
    args, _ = parser.parse_known_args()
    return args


def main() -> None:
    """Initialise and run the OnTheSpot GUI application."""
    config.migration()
    logger.info(f"OnTheSpot Version: {config.get('version')}")

    app = QApplication(sys.argv)

    # Load translation file
    translation_path = os.path.join(
        config.app_root, "resources", "translations", f"{config.get('language')}.qm"
    )
    translator = QTranslator()
    translator.load(translation_path)
    app.installTranslator(translator)

    # Start the background parsing worker
    parsing_worker = ParsingWorker()
    parsing_worker.start()

    # Resolve any start URL passed on the command line
    args = _parse_args()
    start_url = args.url

    dialog = MiniDialog()
    window = MainWindow(dialog, start_url, parsing_worker)

    if config.get("close_to_tray"):
        set_tray_initialized(True)
        _tray_app = TrayApp(window)  # noqa: F841 — kept alive via reference

    app.setDesktopFileName("org.onthespot.OnTheSpot")
    app.exec()

    logger.info("Good bye ..")
    os._exit(0)


if __name__ == "__main__":
    main()
