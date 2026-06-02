"""M10c: BreadcrumbBar — clickable path segments with inline edit fallback.

Normal mode: each path component is a flat QPushButton.  Clicking a button
navigates to that prefix.  Clicking the empty space after the last segment
switches to edit mode.

Edit mode: a QLineEdit pre-filled with the current path.  Enter → navigate;
Escape → revert to breadcrumb mode without navigating.
"""
from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QEvent, Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QWidget,
)


class BreadcrumbBar(QWidget):
    """Clickable breadcrumb path display with inline edit on empty-area click."""

    navigate_requested = pyqtSignal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._path: Path = Path.home()

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._stack = QStackedWidget()
        self._stack.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        # Page 0: breadcrumb buttons
        self._crumb_widget = QWidget()
        self._crumb_layout = QHBoxLayout(self._crumb_widget)
        self._crumb_layout.setContentsMargins(4, 0, 4, 0)
        self._crumb_layout.setSpacing(0)
        self._crumb_widget.installEventFilter(self)   # click empty area → edit
        self._stack.addWidget(self._crumb_widget)

        # Page 1: path editor
        self._edit = QLineEdit()
        self._edit.returnPressed.connect(self._commit_edit)
        self._edit.installEventFilter(self)            # Escape → cancel
        self._stack.addWidget(self._edit)

        layout.addWidget(self._stack)
        self._stack.setCurrentIndex(0)

        self._rebuild_crumbs()

    # ── Public API ────────────────────────────────────────────────────────────

    def set_path(self, path: str | Path) -> None:
        self._path = Path(path)
        self._rebuild_crumbs()
        self._stack.setCurrentIndex(0)

    # ── Internal ──────────────────────────────────────────────────────────────

    def _rebuild_crumbs(self) -> None:
        while self._crumb_layout.count():
            item = self._crumb_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        parts = list(self._path.parts)   # ['/', 'home', 'user', 'docs']
        cumulative = Path("/")
        for i, part in enumerate(parts):
            if part == "/":
                cumulative = Path("/")
                label = "/"
            else:
                cumulative = cumulative / part
                label = part

            target = cumulative
            btn = QPushButton(label)
            btn.setFlat(True)
            btn.setStyleSheet("QPushButton { padding: 2px 4px; }")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(
                lambda checked=False, p=target: self.navigate_requested.emit(str(p))
            )
            self._crumb_layout.addWidget(btn)

            if i < len(parts) - 1:
                sep = QLabel("›")
                sep.setStyleSheet("QLabel { color: palette(mid); padding: 0 2px; }")
                self._crumb_layout.addWidget(sep)

        self._crumb_layout.addStretch()

    def _enter_edit(self) -> None:
        self._edit.setText(str(self._path))
        self._edit.selectAll()
        self._stack.setCurrentIndex(1)
        self._edit.setFocus()

    def _cancel_edit(self) -> None:
        self._stack.setCurrentIndex(0)

    def _commit_edit(self) -> None:
        self._stack.setCurrentIndex(0)
        text = self._edit.text().strip()
        if not text:
            return
        path = Path(text).expanduser()
        if path.is_dir():
            self.navigate_requested.emit(str(path))

    def eventFilter(self, obj, event) -> bool:
        if obj is self._crumb_widget:
            if event.type() == QEvent.Type.MouseButtonPress:
                self._enter_edit()
                return True
        elif obj is self._edit:
            if event.type() == QEvent.Type.KeyPress:
                if event.key() == Qt.Key.Key_Escape:
                    self._cancel_edit()
                    return True
        return super().eventFilter(obj, event)
