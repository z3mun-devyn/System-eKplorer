"""AddressBar — permanently dark path edit with optional breadcrumb toggle.

Default mode ("path"): a QLineEdit that always shows the canonical POSIX path.
  - Styled identically to the Search field (palette(base) fill, border, radius).
  - Focus / click: selects all text so the path is instantly copyable.
  - Enter: navigate to the typed path (expanduser; must be a directory).
  - Escape: revert to the current directory path — never blank, never breadcrumbs.

Breadcrumb mode (opt-in): shows the existing BreadcrumbBar inside a dark wrapper.
  - Toggle via the small "/" button at the left of the bar.
  - Mode persisted in SQLite via SettingsRepository (fm.address_bar.mode).
"""
from __future__ import annotations

from pathlib import Path

import strings
from backends.settings_backend import SettingsRepository
from views.breadcrumb_bar import BreadcrumbBar

from PyQt6.QtCore import QEvent, Qt, QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

_PATH_MODE  = "path"
_CRUMB_MODE = "breadcrumb"


class AddressBar(QWidget):
    """Permanently dark address bar: POSIX path edit (default) or breadcrumbs (opt-in)."""

    navigate_requested = pyqtSignal(str)

    def __init__(
        self,
        settings: SettingsRepository,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._settings = settings
        self._path = Path.home()
        self._mode = settings.get(strings.FM_SETTING_ADDRESS_BAR_MODE) or _PATH_MODE

        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 0, 4, 0)
        layout.setSpacing(2)

        # Mode toggle: small flat "/" button at left edge
        self._toggle_btn = QPushButton(strings.FM_ADDRESS_TOGGLE_ICON)
        self._toggle_btn.setFlat(True)
        self._toggle_btn.setFixedSize(18, 22)
        self._toggle_btn.setToolTip(strings.FM_ADDRESS_TOGGLE_TOOLTIP)
        self._toggle_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._toggle_btn.setStyleSheet(
            "QPushButton { background: transparent; border: none;"
            " color: palette(mid); font-weight: bold; }"
            "QPushButton:hover { color: palette(text); }"
        )
        self._toggle_btn.clicked.connect(self._on_toggle)
        layout.addWidget(self._toggle_btn)

        # Inner stack: [0] path QLineEdit | [1] BreadcrumbBar
        self._stack = QStackedWidget()
        self._stack.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        # Page 0 — POSIX path edit, styled identically to the Search field
        self._path_edit = QLineEdit()
        self._path_edit.setStyleSheet(
            "QLineEdit { background: palette(base);"
            " border: 1px solid palette(mid); border-radius: 4px;"
            " padding: 2px 4px; }"
        )
        self._path_edit.returnPressed.connect(self._commit)
        self._path_edit.installEventFilter(self)
        self._stack.addWidget(self._path_edit)     # index 0

        # Page 1 — BreadcrumbBar wrapped in a dark-filled container
        _crumb_wrapper = QWidget()
        _crumb_wrapper.setStyleSheet(
            "QWidget { background: palette(base);"
            " border: 1px solid palette(mid); border-radius: 4px; }"
        )
        _crumb_wrapper.setAutoFillBackground(True)
        _cwl = QHBoxLayout(_crumb_wrapper)
        _cwl.setContentsMargins(4, 0, 4, 0)
        _cwl.setSpacing(0)
        self._crumb_bar = BreadcrumbBar()
        self._crumb_bar.navigate_requested.connect(self.navigate_requested)
        _cwl.addWidget(self._crumb_bar)
        self._stack.addWidget(_crumb_wrapper)      # index 1

        layout.addWidget(self._stack, stretch=1)

        self._apply_mode(save=False)
        self._sync_display()

    # ── Public API ────────────────────────────────────────────────────────────

    def set_path(self, path: str | Path) -> None:
        """Update the displayed path (called on every navigation event)."""
        self._path = Path(path)
        self._sync_display()

    def focus_edit(self) -> None:
        """Switch to path mode and select-all (Ctrl+L target)."""
        if self._mode != _PATH_MODE:
            self._mode = _PATH_MODE
            self._apply_mode()
            self._sync_display()
        self._path_edit.setFocus()
        QTimer.singleShot(0, self._path_edit.selectAll)

    # ── Internal ──────────────────────────────────────────────────────────────

    def _sync_display(self) -> None:
        self._path_edit.setText(str(self._path))
        self._crumb_bar.set_path(self._path)

    def _apply_mode(self, *, save: bool = True) -> None:
        self._stack.setCurrentIndex(0 if self._mode == _PATH_MODE else 1)
        if save:
            self._settings.set(strings.FM_SETTING_ADDRESS_BAR_MODE, self._mode)

    def _on_toggle(self) -> None:
        self._mode = _CRUMB_MODE if self._mode == _PATH_MODE else _PATH_MODE
        self._apply_mode()
        self._sync_display()

    def _commit(self) -> None:
        """Enter pressed in path edit — navigate if valid, else revert."""
        text = self._path_edit.text().strip()
        if not text:
            self._path_edit.setText(str(self._path))
            return
        path = Path(text).expanduser()
        if path.is_dir():
            self.navigate_requested.emit(str(path.resolve()))
        else:
            self._path_edit.setText(str(self._path))

    def eventFilter(self, obj, event) -> bool:  # type: ignore[override]
        if obj is self._path_edit:
            etype = event.type()
            if etype == QEvent.Type.KeyPress and event.key() == Qt.Key.Key_Escape:
                # Revert to current path — never blank, never switches to breadcrumbs
                self._path_edit.setText(str(self._path))
                self._path_edit.clearFocus()
                return True
            if etype == QEvent.Type.FocusIn:
                # Delay selectAll so Qt finishes the focus change first
                QTimer.singleShot(0, self._path_edit.selectAll)
        return super().eventFilter(obj, event)
