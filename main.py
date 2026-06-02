"""System eKplorer — entry point."""

import os
import sys
from pathlib import Path

from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QMainWindow,
    QStatusBar,
    QStyle,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

import strings
from views.dashboard_view import DashboardView
from views.file_manager_view import FileManagerView
from views.file_view import _chrome_icon
from views.navigation_sidebar import NavigationSidebar
from views.packages_view import PackagesView
from views.terminal_view import TerminalView


class DashboardTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._sidebar = NavigationSidebar()
        layout.addWidget(self._sidebar, stretch=0)

        sep = QWidget()
        sep.setFixedWidth(1)
        sep.setStyleSheet("QWidget { background: palette(mid); }")
        layout.addWidget(sep)

        self.dashboard_view = DashboardView()
        layout.addWidget(self.dashboard_view, stretch=1)


class FileManagerTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.file_manager_view = FileManagerView()
        layout.addWidget(self.file_manager_view)


class PackagesTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.packages_view = PackagesView()
        layout.addWidget(self.packages_view)


class TerminalTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.terminal_view = TerminalView()
        layout.addWidget(self.terminal_view)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(strings.APP_TITLE)
        self.resize(1100, 700)

        self._tabs = QTabWidget()
        self._dashboard_tab = DashboardTab()
        self._file_manager_tab = FileManagerTab()
        self._packages_tab = PackagesTab()
        self._terminal_tab = TerminalTab()

        self._tabs.addTab(self._dashboard_tab, strings.TAB_DASHBOARD)
        self._fm_index = self._tabs.addTab(
            self._file_manager_tab,
            _chrome_icon("system-file-manager", QStyle.StandardPixmap.SP_DirOpenIcon),
            strings.TAB_FILE_MANAGER,
        )
        self._tabs.addTab(self._packages_tab, strings.TAB_PACKAGES)
        self._terminal_index = self._tabs.addTab(
            self._terminal_tab,
            _chrome_icon("utilities-terminal", QStyle.StandardPixmap.SP_ComputerIcon),
            strings.TAB_TERMINAL,
        )

        self._tabs.setCurrentIndex(0)  # Dashboard selected by default (spec §7)

        self.setCentralWidget(self._tabs)

        status = QStatusBar()
        status.showMessage(f"{strings.APP_TITLE}  {strings.APP_VERSION}")
        self.setStatusBar(status)

        # Navigation seam — all navigate_requested signals route here
        self._packages_tab.packages_view.open_location_requested.connect(
            self.navigate_to_directory
        )
        self._dashboard_tab._sidebar.navigate_requested.connect(
            self.navigate_to_directory
        )
        self._dashboard_tab.dashboard_view.navigate_requested.connect(
            self.navigate_to_directory
        )

    def navigate_to_directory(self, path: str) -> None:
        if self._tabs.currentIndex() == self._terminal_index:
            self._terminal_tab.terminal_view.navigate_to(path)
            return
        # Switch to File Manager tab and navigate there; record in recent_paths
        self._tabs.setCurrentIndex(self._fm_index)
        self._file_manager_tab.file_manager_view.navigate_to(path)


_ICON_PATH = Path(__file__).parent / "assets" / "icons" / "ekplorer.png"

_OLD_DATA_DIR = Path.home() / ".local" / "share" / "ekploiter"
_NEW_DATA_DIR = Path.home() / ".local" / "share" / "ekplorer"


def _migrate_data_dir() -> None:
    """Rename ~/.local/share/ekploiter → ~/.local/share/ekplorer on first launch.

    Only runs when the old directory exists and the new one does not, so it is
    safe to call on every startup with no performance cost after the first run.
    If both directories exist the user has run both versions; leave both alone.
    """
    if _OLD_DATA_DIR.exists() and not _NEW_DATA_DIR.exists():
        _OLD_DATA_DIR.rename(_NEW_DATA_DIR)
        print("Migrated data directory to ~/.local/share/ekplorer/", file=sys.stderr)


def main() -> None:
    _migrate_data_dir()

    # Let the KDE platform plugin load on Plasma 6; silently ignored elsewhere.
    os.environ.setdefault("QT_QPA_PLATFORMTHEME", "kde")

    app = QApplication(sys.argv)
    app.setApplicationName(strings.APP_TITLE)
    if _ICON_PATH.exists():
        app.setWindowIcon(QIcon(str(_ICON_PATH)))
    # Inherit Plasma's active color scheme — no palette override (spec §3)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
