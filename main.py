"""System eKploiter — entry point (Milestone 0)."""

import sys
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (
    QApplication,
    QLabel,
    QMainWindow,
    QStatusBar,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

import strings


class FilesTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label = QLabel(strings.PLACEHOLDER_FILES)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(label)


class PackagesTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label = QLabel(strings.PLACEHOLDER_PACKAGES)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(label)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(strings.APP_TITLE)
        self.resize(1100, 700)

        self._tabs = QTabWidget()
        self._files_tab = FilesTab()
        self._packages_tab = PackagesTab()

        self._tabs.addTab(self._files_tab, strings.TAB_FILES)
        self._tabs.addTab(self._packages_tab, strings.TAB_PACKAGES)
        self._tabs.setCurrentIndex(0)  # Files selected by default (spec §7)

        self.setCentralWidget(self._tabs)

        status = QStatusBar()
        status.showMessage(f"{strings.APP_TITLE}  {strings.APP_VERSION}")
        self.setStatusBar(status)


_ICON_PATH = Path(__file__).parent / "assets" / "icons" / "ekploiter.png"


def main() -> None:
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
