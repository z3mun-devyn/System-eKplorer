"""Clipboard history tab — captures text clipboard changes, persists locally."""

from __future__ import annotations

import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import strings
from backends.clipboard_backend import ClipboardBackend
from models.clipboard_entry import ClipboardEntry

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFont, QIcon
from PyQt6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

_PREVIEW_LEN = 120


def _fmt_ts(iso: str) -> str:
    try:
        dt = datetime.fromisoformat(iso)
        return dt.astimezone().strftime("%Y-%m-%d %H:%M")
    except (ValueError, OSError):
        return iso[:16]


def _pin_icon(pinned: bool) -> QIcon:
    name = "bookmark" if pinned else "bookmark-new"
    icon = QIcon.fromTheme(name)
    return icon


class _EntryWidget(QFrame):
    def __init__(
        self,
        entry: ClipboardEntry,
        on_copy,
        on_open_editor,
        on_toggle_pin,
        on_delete,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._entry = entry
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setFrameShadow(QFrame.Shadow.Raised)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 6, 8, 6)
        outer.setSpacing(4)

        # ── Top row: pin | content preview | timestamp ────────────────────────
        top = QHBoxLayout()
        top.setSpacing(6)

        pin_btn = QPushButton()
        icon = _pin_icon(entry.pinned)
        if not icon.isNull():
            pin_btn.setIcon(icon)
        else:
            pin_btn.setText("📌" if entry.pinned else "🔖")
        pin_btn.setFixedSize(28, 28)
        pin_btn.setFlat(True)
        pin_btn.setToolTip("Unpin" if entry.pinned else "Pin")
        pin_btn.clicked.connect(on_toggle_pin)
        top.addWidget(pin_btn)

        preview = entry.content[:_PREVIEW_LEN]
        if len(entry.content) > _PREVIEW_LEN:
            preview += "…"
        content_label = QLabel(preview)
        mono = QFont("Monospace")
        mono.setStyleHint(QFont.StyleHint.Monospace)
        content_label.setFont(mono)
        content_label.setWordWrap(False)
        content_label.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )
        top.addWidget(content_label, stretch=1)

        ts_label = QLabel(_fmt_ts(entry.captured_at))
        ts_label.setStyleSheet("color: palette(mid); font-size: 11px;")
        ts_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        top.addWidget(ts_label)

        outer.addLayout(top)

        # ── Bottom row: action buttons ────────────────────────────────────────
        bottom = QHBoxLayout()
        bottom.setSpacing(4)
        bottom.addStretch()

        self._copy_btn = QPushButton(strings.CLIPBOARD_COPY_BTN)
        self._copy_btn.setFixedHeight(24)
        self._copy_btn.clicked.connect(self._on_copy_clicked)
        self._on_copy = on_copy
        bottom.addWidget(self._copy_btn)

        editor_btn = QPushButton(strings.CLIPBOARD_OPEN_EDITOR_BTN)
        editor_btn.setFixedHeight(24)
        editor_btn.clicked.connect(on_open_editor)
        bottom.addWidget(editor_btn)

        del_btn = QPushButton(strings.CLIPBOARD_DELETE_BTN)
        del_btn.setFixedHeight(24)
        del_btn.clicked.connect(on_delete)
        bottom.addWidget(del_btn)

        outer.addLayout(bottom)

    def _on_copy_clicked(self) -> None:
        self._on_copy()
        self._copy_btn.setText(strings.CLIPBOARD_COPIED_FLASH)
        QTimer.singleShot(
            1000, lambda: self._copy_btn.setText(strings.CLIPBOARD_COPY_BTN)
        )


class ClipboardView(QWidget):
    def __init__(self, db_path: Path | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._backend = ClipboardBackend(db_path)
        self._self_writing = False

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # ── Top bar ───────────────────────────────────────────────────────────
        top_bar = QWidget()
        top_bar.setFixedHeight(40)
        top_layout = QHBoxLayout(top_bar)
        top_layout.setContentsMargins(12, 4, 12, 4)
        top_layout.setSpacing(8)

        top_layout.addWidget(QLabel(strings.CLIPBOARD_MAX_ENTRIES))
        self._spinbox = QSpinBox()
        self._spinbox.setRange(1, 100)
        self._spinbox.setValue(self._backend.max_entries)
        self._spinbox.setFixedWidth(60)
        self._spinbox.valueChanged.connect(self._on_max_changed)
        top_layout.addWidget(self._spinbox)

        top_layout.addStretch()

        clear_btn = QPushButton(strings.CLIPBOARD_CLEAR_ALL)
        clear_btn.clicked.connect(self._on_clear_all)
        top_layout.addWidget(clear_btn)

        outer.addWidget(top_bar)

        sep = QWidget()
        sep.setFixedHeight(1)
        sep.setStyleSheet("QWidget { background: palette(mid); }")
        outer.addWidget(sep)

        # ── Scroll area for entry list ────────────────────────────────────────
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        outer.addWidget(self._scroll, stretch=1)

        self._reload()

        # Connect to system clipboard — text-only capture
        QApplication.clipboard().dataChanged.connect(self._on_clipboard_changed)

    # ── Clipboard capture ─────────────────────────────────────────────────────

    def _on_clipboard_changed(self) -> None:
        if self._self_writing:
            return
        cb = QApplication.clipboard()
        # Skip file operations — FM uses MIME data with URLs
        if cb.mimeData().hasUrls():
            return
        text = cb.text()
        if not text:
            return
        # Skip consecutive duplicates (compare against most recently captured id)
        entries = self._backend.list_entries()
        if entries:
            newest = max(entries, key=lambda e: e.id)
            if newest.content == text:
                return
        self._backend.add_entry(text)
        self._reload()

    # ── UI callbacks ──────────────────────────────────────────────────────────

    def _on_max_changed(self, value: int) -> None:
        self._backend.max_entries = value
        self._backend.enforce_limit()
        self._reload()

    def _on_clear_all(self) -> None:
        self._backend.clear_unpinned()
        self._reload()

    def _copy_entry(self, content: str) -> None:
        self._self_writing = True
        try:
            QApplication.clipboard().setText(content)
        finally:
            self._self_writing = False

    def _open_in_editor(self, content: str) -> None:
        try:
            with tempfile.NamedTemporaryFile(
                suffix=".txt", mode="w", encoding="utf-8", delete=False
            ) as f:
                f.write(content)
                tmp_path = f.name
            subprocess.Popen(["xdg-open", tmp_path])
        except Exception:
            pass

    # ── List rendering ────────────────────────────────────────────────────────

    def _reload(self) -> None:
        entries = self._backend.list_entries()

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        if not entries:
            empty = QLabel(strings.CLIPBOARD_EMPTY)
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty.setStyleSheet("color: palette(mid);")
            layout.addWidget(empty)
        else:
            for entry in entries:
                eid = entry.id
                content = entry.content
                widget = _EntryWidget(
                    entry=entry,
                    on_copy=lambda c=content: self._copy_entry(c),
                    on_open_editor=lambda c=content: self._open_in_editor(c),
                    on_toggle_pin=lambda _=None, i=eid: self._toggle_pin(i),
                    on_delete=lambda _=None, i=eid: self._delete_entry(i),
                )
                layout.addWidget(widget)

        layout.addStretch()
        self._scroll.setWidget(container)

    def _toggle_pin(self, entry_id: int) -> None:
        self._backend.toggle_pin(entry_id)
        self._reload()

    def _delete_entry(self, entry_id: int) -> None:
        self._backend.delete_entry(entry_id)
        self._reload()
