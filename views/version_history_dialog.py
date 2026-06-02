"""M9: Version history dialog — shows past versions of a package.

Shows installable versions in green, historical-only (no longer in repos) in grey,
current version marked bold.  "Install this version" triggers the M8 action panel.
"Prevent automatic updates" toggle applies apt-mark hold / flatpak mask.
"""
from __future__ import annotations

from PyQt6.QtCore import QObject, QThread, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont
from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
)

import strings
from models.package import Package


class _HistoryLoader(QObject):
    """Async loader for version history + hold/mask state."""
    apt_ready      = pyqtSignal(list, bool)    # (entries, is_held)
    flatpak_ready  = pyqtSignal(list, bool)    # (commits, is_masked)
    failed         = pyqtSignal(str)

    def __init__(self, pkg: Package) -> None:
        super().__init__()
        self._pkg = pkg

    def run(self) -> None:
        from backends.version_backend import VersionBackend
        try:
            backend = VersionBackend()
            pkg = self._pkg
            if pkg.source == "flatpak":
                commits = backend.get_flatpak_history(pkg.name)
                masked  = backend.is_flatpak_masked(pkg.name)
                self.flatpak_ready.emit(commits, masked)
            else:
                entries = backend.get_apt_versions(pkg.name)
                held    = backend.is_apt_held(pkg.name)
                self.apt_ready.emit(entries, held)
        except Exception as exc:
            self.failed.emit(str(exc))
        finally:
            QThread.currentThread().quit()


class VersionHistoryDialog(QDialog):
    # Emitted when the user requests an install — caller wires this to start_action
    install_requested = pyqtSignal(object, str)  # (pkg, version_or_commit)

    def __init__(self, pkg: Package, parent=None) -> None:
        super().__init__(parent)
        self._pkg = pkg
        self._entries: list = []        # AptVersionEntry | FlatpakCommit list
        self._selected_key: str | None = None   # version string or commit hash
        self._selected_obtainable = False

        display = pkg.display_name if pkg.display_name else pkg.name
        self.setWindowTitle(strings.VERSION_HISTORY_TITLE.format(name=display))
        self.setMinimumWidth(480)
        self.setMinimumHeight(360)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        layout.addWidget(QLabel(
            strings.VERSION_HISTORY_SUBTITLE.format(name=display)))

        self._list = QListWidget()
        self._list.currentRowChanged.connect(self._on_selection_changed)
        layout.addWidget(self._list, stretch=1)

        self._loading_label = QLabel(strings.VERSION_HISTORY_LOADING)
        self._loading_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._loading_label)

        # "Prevent automatic updates" checkbox
        self._hold_check = QCheckBox(strings.VERSION_HISTORY_HOLD)
        self._hold_check.setEnabled(False)
        self._hold_check.stateChanged.connect(self._on_hold_toggled)
        layout.addWidget(self._hold_check)

        # Bottom button row
        btn_row = QHBoxLayout()
        self._install_btn = QPushButton(strings.VERSION_HISTORY_INSTALL)
        self._install_btn.setEnabled(False)
        self._install_btn.clicked.connect(self._on_install)
        btn_row.addWidget(self._install_btn)
        btn_row.addStretch()
        close_btn = QPushButton(strings.VERSION_HISTORY_CLOSE)
        close_btn.clicked.connect(self.reject)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

        self._start_load()

    # ── Loading ───────────────────────────────────────────────────────────────

    def _start_load(self) -> None:
        self._thread = QThread(parent=self)
        self._worker = _HistoryLoader(self._pkg)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.apt_ready.connect(self._on_apt_ready)
        self._worker.flatpak_ready.connect(self._on_flatpak_ready)
        self._worker.failed.connect(self._on_load_failed)
        self._thread.finished.connect(self._worker.deleteLater)
        self._thread.start()

    def _on_apt_ready(self, entries: list, is_held: bool) -> None:
        self._loading_label.setVisible(False)
        self._entries = entries
        self._hold_check.blockSignals(True)
        self._hold_check.setChecked(is_held)
        self._hold_check.setEnabled(True)
        self._hold_check.blockSignals(False)

        for entry in entries:
            item = QListWidgetItem()
            label = entry.version
            if entry.is_installed:
                label += f"  {strings.VERSION_HISTORY_CURRENT}"
                f = item.font()
                f.setBold(True)
                item.setFont(f)
            if entry.is_obtainable:
                item.setForeground(QColor(strings.VERSION_HISTORY_COLOR_OK))
            else:
                item.setForeground(QColor(strings.VERSION_HISTORY_COLOR_GREY))
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsSelectable
                              & ~Qt.ItemFlag.ItemIsEnabled)
            item.setText(label)
            item.setData(Qt.ItemDataRole.UserRole, entry.version)
            item.setData(Qt.ItemDataRole.UserRole + 1, entry.is_obtainable)
            item.setData(Qt.ItemDataRole.UserRole + 2, entry.is_installed)
            self._list.addItem(item)

    def _on_flatpak_ready(self, commits: list, is_masked: bool) -> None:
        self._loading_label.setVisible(False)
        self._entries = commits
        self._hold_check.blockSignals(True)
        self._hold_check.setChecked(is_masked)
        self._hold_check.setEnabled(True)
        self._hold_check.blockSignals(False)

        for commit in commits:
            item = QListWidgetItem()
            label = f"{commit.commit}  {commit.subject}"
            if commit.date:
                label += f"  ({commit.date})"
            if commit.is_current:
                label += f"  {strings.VERSION_HISTORY_CURRENT}"
                f = item.font()
                f.setBold(True)
                item.setFont(f)
            item.setForeground(QColor(strings.VERSION_HISTORY_COLOR_OK))
            item.setText(label)
            item.setData(Qt.ItemDataRole.UserRole, commit.commit)
            item.setData(Qt.ItemDataRole.UserRole + 1, True)   # always obtainable
            item.setData(Qt.ItemDataRole.UserRole + 2, commit.is_current)
            self._list.addItem(item)

    def _on_load_failed(self, error: str) -> None:
        self._loading_label.setText(
            strings.VERSION_HISTORY_LOAD_FAILED.format(error=error))

    # ── Selection ─────────────────────────────────────────────────────────────

    def _on_selection_changed(self, row: int) -> None:
        if row < 0:
            self._install_btn.setEnabled(False)
            return
        item = self._list.item(row)
        key         = item.data(Qt.ItemDataRole.UserRole)
        obtainable  = item.data(Qt.ItemDataRole.UserRole + 1)
        is_current  = item.data(Qt.ItemDataRole.UserRole + 2)
        self._selected_key = key
        self._selected_obtainable = obtainable
        # Enable install only when obtainable AND not the currently installed/active version
        self._install_btn.setEnabled(bool(obtainable) and not is_current)

    # ── Actions ───────────────────────────────────────────────────────────────

    def _on_install(self) -> None:
        if self._selected_key and self._selected_obtainable:
            self.install_requested.emit(self._pkg, self._selected_key)
            self.accept()

    def _on_hold_toggled(self, state: int) -> None:
        from backends.version_backend import VersionBackend
        checked = state == Qt.CheckState.Checked.value
        backend = VersionBackend()
        if self._pkg.source == "flatpak":
            if checked:
                backend.mask_flatpak(self._pkg.name)
            else:
                backend.unmask_flatpak(self._pkg.name)
        else:
            if checked:
                backend.hold_apt(self._pkg.name)
            else:
                backend.unhold_apt(self._pkg.name)
