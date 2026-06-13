"""System eKplorer — entry point."""

import logging
import os
import subprocess
import sys
import urllib.parse
from pathlib import Path

logger = logging.getLogger(__name__)

from PyQt6.QtGui import QIcon
from PyQt6.QtNetwork import QLocalServer, QLocalSocket
from PyQt6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QMainWindow,
    QPushButton,
    QStatusBar,
    QStyle,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

import skin_background
import skin_loader
import skin_manager
import strings
from backends.settings_backend import SettingsRepository
from views.clipboard_view import ClipboardView
from views.configure_dialog import ConfigureDialog
from views.dashboard_view import DashboardView
from views.file_manager_view import FileManagerView
from views.file_view import _chrome_icon
from views.navigation_sidebar import NavigationSidebar
from views.packages_view import PackagesView
from views.terminal_view import TerminalView


# ── Single-instance socket name ───────────────────────────────────────────────
_SOCKET_NAME = f"ekplorer-{os.getuid()}"

# ── Startup tab mapping ───────────────────────────────────────────────────────
_STARTUP_TAB_MAP: dict[str, int] = {
    "dashboard":    0,
    "file_manager": 1,
    "packages":     2,
    "terminal":     3,
    "clipboard":    4,
}


def _startup_tab_index(settings: SettingsRepository) -> int:
    """Map the app.startup_tab setting to a tab index (default 0 = Dashboard)."""
    key = settings.get("app.startup_tab") or "dashboard"
    return _STARTUP_TAB_MAP.get(key, 0)

# ── Desktop file paths ────────────────────────────────────────────────────────
_DESKTOP_DIR = Path.home() / ".local" / "share" / "applications"
_DESKTOP_FILE = _DESKTOP_DIR / "ekplorer.desktop"


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


class ClipboardTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.clipboard_view = ClipboardView()
        layout.addWidget(self.clipboard_view)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(strings.APP_TITLE)
        self.resize(1100, 700)

        self._local_server: QLocalServer | None = None

        self._tabs = QTabWidget()
        self._dashboard_tab = DashboardTab()
        self._file_manager_tab = FileManagerTab()
        self._packages_tab = PackagesTab()
        self._terminal_tab = TerminalTab()
        self._clipboard_tab = ClipboardTab()

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
        self._tabs.addTab(
            self._clipboard_tab,
            _chrome_icon("edit-paste", QStyle.StandardPixmap.SP_FileIcon),
            strings.TAB_CLIPBOARD,
        )

        # Startup tab from settings (defaults to Dashboard)
        self._tabs.setCurrentIndex(_startup_tab_index(SettingsRepository()))

        # Gear button in the top-right corner of the tab bar
        gear_btn = QPushButton()
        gear_btn.setIcon(
            _chrome_icon(
                "configure",
                QStyle.StandardPixmap.SP_FileDialogDetailedView,
            )
        )
        gear_btn.setToolTip(strings.CONFIGURE_TOOLTIP)
        gear_btn.setFlat(True)
        gear_btn.setFixedSize(28, 28)
        gear_btn.clicked.connect(self._open_configure)
        self._tabs.setCornerWidget(gear_btn)

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

    # ── Configure dialog ──────────────────────────────────────────────────────

    def _open_configure(self) -> None:
        dlg = ConfigureDialog(parent=self)
        if dlg.exec():
            self._dashboard_tab._sidebar.apply_animation_setting()
            self._file_manager_tab.file_manager_view._sidebar.apply_animation_setting()

    # ── Single-instance server ────────────────────────────────────────────────

    def start_server(self, socket_name: str) -> None:
        QLocalServer.removeServer(socket_name)
        self._local_server = QLocalServer(self)
        self._local_server.newConnection.connect(self._on_new_instance_connection)
        self._local_server.listen(socket_name)

    def _on_new_instance_connection(self) -> None:
        if self._local_server is None:
            return
        conn = self._local_server.nextPendingConnection()
        if conn is None:
            return
        conn.waitForReadyRead(500)
        raw = bytes(conn.readAll()).decode("utf-8").strip()
        conn.close()
        self.raise_()
        self.activateWindow()
        if raw:
            p = Path(raw)
            if p.is_dir():
                self.navigate_to_directory(raw)

    # ── Navigation ────────────────────────────────────────────────────────────

    def navigate_to_directory(self, path: str) -> None:
        if self._tabs.currentIndex() == self._terminal_index:
            self._terminal_tab.terminal_view.navigate_to(path)
            return
        # Switch to File Manager tab and navigate there; record in recent_paths
        self._tabs.setCurrentIndex(self._fm_index)
        self._file_manager_tab.file_manager_view.navigate_to(path)


# ── App paths & migration ─────────────────────────────────────────────────────

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


# ── Desktop file generation ───────────────────────────────────────────────────

def _generate_desktop_file(desktop_dir: Path | None = None) -> None:
    """Write ~/.local/share/applications/ekplorer.desktop if missing or stale.

    Regenerates whenever the Exec line changes (e.g. venv moved), so the
    entry always points at the live Python interpreter and main.py.
    """
    dest = desktop_dir or _DESKTOP_DIR
    desktop_file = dest / "ekplorer.desktop"
    main_py = str(Path(__file__).resolve())
    exec_line = f"Exec={sys.executable} {main_py} %U"

    content = "\n".join([
        "[Desktop Entry]",
        "Version=1.0",
        "Type=Application",
        "Name=System eKplorer",
        "Comment=File manager, package manager and terminal in one",
        exec_line,
        "Icon=system-file-manager",
        "Terminal=false",
        "Categories=System;FileManager;",
        "MimeType=inode/directory;x-scheme-handler/file;",
        "StartupNotify=true",
        "StartupWMClass=ekplorer",
        "",
    ])

    dest.mkdir(parents=True, exist_ok=True)

    if desktop_file.exists():
        for line in desktop_file.read_text(encoding="utf-8").splitlines():
            if line.startswith("Exec="):
                if line == exec_line:
                    return  # Exec unchanged — skip write
                break

    desktop_file.write_text(content, encoding="utf-8")
    subprocess.run(
        ["update-desktop-database", str(dest)],
        check=False,
        capture_output=True,
        timeout=5,
    )


# ── Single-instance helpers ───────────────────────────────────────────────────

def _normalize_path_arg(arg: str) -> str:
    """Strip file:// scheme and URL-decode a CLI path argument."""
    if arg.startswith("file://"):
        arg = arg[len("file://"):]
    return urllib.parse.unquote(arg)


def _try_become_secondary(socket_name: str, path_arg: str) -> bool:
    """Return True and forward *path_arg* to the running instance, or False."""
    sock = QLocalSocket()
    sock.connectToServer(socket_name)
    if sock.waitForConnected(500):
        sock.write((path_arg + "\n").encode("utf-8"))
        sock.flush()
        sock.waitForBytesWritten(500)
        sock.close()
        return True
    return False


# ── Skin autoload ─────────────────────────────────────────────────────────────

def _autoload_active_skin(app, settings: SettingsRepository | None = None) -> None:
    """Apply the persisted ``appearance.active_skin`` at startup, if set.

    Leaves the captured baseline untouched when the setting is unset, "off",
    points at a skin no longer on disk, or names a palette-less skin (each logged,
    never crashes). Per-skin ``appearance.override.<id>.<role>`` keys are layered
    on top of the skin's palette. No settings are written here — that's P3.
    """
    settings = settings or SettingsRepository()
    active = settings.get("appearance.active_skin")
    skins = skin_loader.discover_skins()
    role_map = skin_loader.resolve_role_map(
        active,
        skins,
        override_lookup=lambda role: settings.get(
            f"appearance.override.{active}.{role}"),
    )
    if role_map is not None:
        skin_manager.apply_skin(app, role_map)

    # FM-viewport background: the active skin (None for off/unset/missing id),
    # plus the user's per-skin fit override (appearance.fit.<id>) if set.
    skin = None
    fit = None
    if active and active != "off":
        skin = next((s for s in skins if s.id == active), None)
        fit = settings.get(f"appearance.fit.{active}")
    skin_background.set_active(skin, fit)


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    _migrate_data_dir()
    _generate_desktop_file()

    # Let the KDE platform plugin load on Plasma 6; silently ignored elsewhere.
    os.environ.setdefault("QT_QPA_PLATFORMTHEME", "kde")

    # Parse CLI path argument before QApplication so we can forward it to a
    # running instance immediately after the app object is created.
    path_arg = ""
    if len(sys.argv) > 1:
        path_arg = _normalize_path_arg(sys.argv[1])

    app = QApplication(sys.argv)
    app.setApplicationName(strings.APP_TITLE)

    # Snapshot the theme-native style + palette before any skin can override it,
    # so "Off" can restore the exact launch appearance.
    skin_manager.capture_baseline(app)

    # Auto-apply the persisted skin (if any) before the window shows (M11 P2).
    _autoload_active_skin(app)

    # Single-instance guard: if another eKplorer is running, hand off and exit.
    if _try_become_secondary(_SOCKET_NAME, path_arg):
        sys.exit(0)

    if _ICON_PATH.exists():
        app.setWindowIcon(QIcon(str(_ICON_PATH)))
    # Inherit Plasma's active color scheme — no palette override (spec §3)
    window = MainWindow()
    window.start_server(_SOCKET_NAME)
    window.show()

    # Navigate to initial path if one was supplied on the command line.
    if path_arg:
        p = Path(path_arg)
        if p.is_dir():
            window.navigate_to_directory(path_arg)
        elif p.is_file():
            window.navigate_to_directory(str(p.parent))

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
