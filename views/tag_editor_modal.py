"""Tag editor modal — embedded overlay widget (not an OS dialog).

The modal is a child QWidget of PackagesView.  A sibling DimOverlay covers
the rest of the view so the tab bar remains fully accessible at all times,
per spec §12.
"""

from __future__ import annotations

from pathlib import Path

import strings
import theme
from backends.tags_backend import TagRepository
from models.tag import PackageEntry, Tag
from views.tag_pill import TagPill

from PyQt6.QtCore import QPoint, QRect, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QPainter, QPalette
from PyQt6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QLayout,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)


# ── Flow layout ───────────────────────────────────────────────────────────────

class _FlowLayout(QLayout):
    """Wrapping horizontal layout for the existing-tag pill row."""

    def __init__(self, parent: QWidget | None = None,
                 h_gap: int = 6, v_gap: int = 6) -> None:
        super().__init__(parent)
        self._items: list = []
        self._h_gap = h_gap
        self._v_gap = v_gap

    def addItem(self, item) -> None:  # type: ignore[override]
        self._items.append(item)

    def count(self) -> int:
        return len(self._items)

    def itemAt(self, index: int):
        return self._items[index] if 0 <= index < len(self._items) else None

    def takeAt(self, index: int):
        return self._items.pop(index) if 0 <= index < len(self._items) else None

    def hasHeightForWidth(self) -> bool:
        return True

    def heightForWidth(self, width: int) -> int:
        return self._arrange(QRect(0, 0, width, 0), dry_run=True)

    def setGeometry(self, rect: QRect) -> None:
        super().setGeometry(rect)
        self._arrange(rect, dry_run=False)

    def sizeHint(self) -> QSize:
        return self.minimumSize()

    def minimumSize(self) -> QSize:
        size = QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        m = self.contentsMargins()
        return size + QSize(m.left() + m.right(), m.top() + m.bottom())

    def _arrange(self, rect: QRect, dry_run: bool) -> int:
        x, y, line_h = rect.x(), rect.y(), 0
        for item in self._items:
            w = item.sizeHint().width()
            h = item.sizeHint().height()
            if x + w > rect.right() and line_h > 0:
                x = rect.x()
                y += line_h + self._v_gap
                line_h = 0
            if not dry_run:
                item.setGeometry(QRect(QPoint(x, y), item.sizeHint()))
            x += w + self._h_gap
            line_h = max(line_h, h)
        return y + line_h - rect.y()


# ── Dim overlay ───────────────────────────────────────────────────────────────

class DimOverlay(QWidget):
    """Semi-transparent backdrop. Covers PackagesView but never the tab bar."""

    clicked = pyqtSignal()

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setVisible(False)

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), theme.modal_overlay())

    def mousePressEvent(self, _event) -> None:
        self.clicked.emit()


# ── Color swatch button ───────────────────────────────────────────────────────

class _Swatch(QPushButton):
    def __init__(self, color: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.color = color
        self.setFixedSize(32, 32)
        self.setCheckable(True)
        self._set_style(False)

    def set_selected(self, selected: bool) -> None:
        self.setChecked(selected)
        self._set_style(selected)

    def _set_style(self, selected: bool) -> None:
        border = "3px solid palette(window-text)" if selected else "2px solid transparent"
        self.setStyleSheet(
            f"QPushButton {{"
            f"  background-color: {self.color};"
            f"  border: {border}; border-radius: 16px;"
            f"}}"
        )


# ── Tag editor modal ──────────────────────────────────────────────────────────

class TagModal(QFrame):
    """Embedded, non-blocking tag editor. Shown as an overlay inside PackagesView."""

    saved = pyqtSignal()  # tag assignments or new tags changed — caller must reload

    _MODAL_WIDTH = 380

    def __init__(self, parent: QWidget | None,
                 db_path: Path | None = None) -> None:
        super().__init__(parent)
        self._repo = TagRepository(db_path)
        self._entry: PackageEntry | None = None
        self._batch_entries: list[PackageEntry] | None = None
        # Default to the third swatch in the curated palette (spec §12)
        self._selected_color: str = strings.TAG_PALETTE[2]
        self._pills: list[TagPill] = []

        self.setFixedWidth(self._MODAL_WIDTH)
        self.setFrameShape(QFrame.Shape.Box)
        self.setFrameShadow(QFrame.Shadow.Raised)
        self.setAutoFillBackground(True)
        self.setVisible(False)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # ── Header ──────────────────────────────────────────────────────────
        self._header_widget = QWidget()
        self._header_widget.setAutoFillBackground(True)
        self._apply_bar_color(self._header_widget)

        hdr_layout = QVBoxLayout(self._header_widget)
        hdr_layout.setContentsMargins(16, 12, 16, 12)
        hdr_layout.setSpacing(2)

        self._title_label = QLabel()
        title_font = self._title_label.font()
        title_font.setBold(True)
        title_font.setPointSize(title_font.pointSize() + 1)
        self._title_label.setFont(title_font)
        hdr_layout.addWidget(self._title_label)

        self._subtitle_label = QLabel(strings.TAG_EDITOR_SUBTITLE)
        sub_font = self._subtitle_label.font()
        sub_font.setPointSize(sub_font.pointSize() - 1)
        self._subtitle_label.setFont(sub_font)
        self._subtitle_label.setStyleSheet("color: palette(mid);")
        hdr_layout.addWidget(self._subtitle_label)

        outer.addWidget(self._header_widget)

        # ── Scrollable body ──────────────────────────────────────────────────
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        body = QWidget()
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(16, 12, 16, 12)
        body_layout.setSpacing(8)

        existing_lbl = QLabel(strings.TAG_EDITOR_ASSIGN_HEADER)
        existing_lbl.setStyleSheet("color: palette(mid); font-size: 10px;")
        body_layout.addWidget(existing_lbl)

        self._no_tags_label = QLabel(strings.TAG_EDITOR_NO_TAGS)
        self._no_tags_label.setStyleSheet("color: palette(mid); font-style: italic;")
        body_layout.addWidget(self._no_tags_label)

        self._pill_container = QWidget()
        self._pill_container.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum
        )
        self._pill_layout = _FlowLayout(self._pill_container, h_gap=6, v_gap=6)
        self._pill_container.setLayout(self._pill_layout)
        body_layout.addWidget(self._pill_container)

        divider = QFrame()
        divider.setFrameShape(QFrame.Shape.HLine)
        divider.setFrameShadow(QFrame.Shadow.Sunken)
        body_layout.addWidget(divider)

        create_lbl = QLabel(strings.TAG_EDITOR_CREATE_HEADER)
        create_lbl.setStyleSheet("color: palette(mid); font-size: 10px;")
        body_layout.addWidget(create_lbl)

        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText(strings.TAG_EDITOR_NAME_PLACEHOLDER)
        body_layout.addWidget(self._name_edit)

        color_container = QWidget()
        color_grid = QGridLayout(color_container)
        color_grid.setSpacing(6)
        color_grid.setContentsMargins(0, 0, 0, 0)

        self._swatches: list[_Swatch] = []
        for i, color in enumerate(strings.TAG_PALETTE):
            sw = _Swatch(color)
            sw.clicked.connect(lambda _checked, c=color: self._select_color(c))
            row, col = divmod(i, strings.TAG_PALETTE_COLS)
            color_grid.addWidget(sw, row, col)
            self._swatches.append(sw)
        self._refresh_swatches()

        body_layout.addWidget(color_container)
        body_layout.addStretch()

        scroll.setWidget(body)
        outer.addWidget(scroll, stretch=1)

        # ── Footer ───────────────────────────────────────────────────────────
        footer = QWidget()
        footer.setAutoFillBackground(True)
        self._apply_bar_color(footer)

        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(12, 10, 12, 10)

        cancel_btn = QPushButton(strings.TAG_EDITOR_CANCEL_BTN)
        cancel_btn.clicked.connect(self._close)
        footer_layout.addWidget(cancel_btn)

        footer_layout.addStretch()

        self._save_btn = QPushButton(strings.TAG_EDITOR_SAVE_BTN)
        self._save_btn.setDefault(True)
        self._save_btn.clicked.connect(self._on_save)
        footer_layout.addWidget(self._save_btn)

        outer.addWidget(footer)

    # ── Public API ────────────────────────────────────────────────────────────

    def open_for(self, entry: PackageEntry | None) -> None:
        """Open for a package entry (assign mode) or None (create-only mode)."""
        self._batch_entries = None
        self._entry = entry
        name = entry.package.name if entry else ""
        self._title_label.setText(strings.TAG_EDITOR_TITLE.format(name=name))
        self._subtitle_label.setVisible(entry is not None)
        self._rebuild_pills()
        self._name_edit.clear()
        self.adjustSize()
        self.setVisible(True)
        self.raise_()

    def open_for_batch(self, entries: list[PackageEntry]) -> None:
        """Open for multiple package entries; tag pills start assigned only if ALL have them."""
        self._entry = None
        self._batch_entries = list(entries)
        self._title_label.setText(strings.TAG_BATCH_TITLE.format(n=len(entries)))
        self._subtitle_label.setVisible(True)
        self._rebuild_pills()
        self._name_edit.clear()
        self.adjustSize()
        self.setVisible(True)
        self.raise_()

    def close_modal(self) -> None:
        self._close()

    # ── Internals ─────────────────────────────────────────────────────────────

    @staticmethod
    def _apply_bar_color(widget: QWidget) -> None:
        """Apply the darker header/footer bar color derived from the palette."""
        p = widget.palette()
        p.setColor(QPalette.ColorRole.Window,
                   theme.modal_header_bar(widget.palette()))
        widget.setPalette(p)

    def _rebuild_pills(self) -> None:
        for pill in self._pills:
            pill.setParent(None)
        self._pills.clear()
        while self._pill_layout.count():
            self._pill_layout.takeAt(0)

        all_tags = self._repo.all_tags()
        if not all_tags:
            self._no_tags_label.setVisible(True)
            self._pill_container.setVisible(False)
            return

        self._no_tags_label.setVisible(False)
        self._pill_container.setVisible(True)

        if self._batch_entries is not None:
            if self._batch_entries:
                sets = [frozenset(t.name for t in e.tags) for e in self._batch_entries]
                assigned_names: set[str] = set(sets[0].intersection(*sets[1:]))
            else:
                assigned_names = set()
        else:
            assigned_names = {t.name for t in self._entry.tags} if self._entry else set()
        for tag in all_tags:
            pill = TagPill(tag, tag.name in assigned_names, self._pill_container)
            self._pill_layout.addWidget(pill)
            self._pills.append(pill)

    def _select_color(self, color: str) -> None:
        self._selected_color = color
        self._refresh_swatches()

    def _refresh_swatches(self) -> None:
        for sw in self._swatches:
            sw.set_selected(sw.color == self._selected_color)

    def _on_save(self) -> None:
        name = self._name_edit.text().strip()
        if name:
            try:
                self._repo.create_tag(name, self._selected_color)
            except Exception:
                pass  # duplicate name — pill toggle still saves

        if self._batch_entries is not None:
            assigned = {p.tag.name for p in self._pills if p.is_assigned()}
            if name:
                assigned.add(name)
            for e in self._batch_entries:
                self._repo.set_assignments(e.package.source, e.package.name, assigned)
        elif self._entry:
            assigned = {p.tag.name for p in self._pills if p.is_assigned()}
            if name:
                assigned.add(name)
            self._repo.set_assignments(
                self._entry.package.source, self._entry.package.name, assigned
            )

        self.saved.emit()
        self._close()

    def _close(self) -> None:
        self.setVisible(False)
