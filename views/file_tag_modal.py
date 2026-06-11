"""File tag assignment dialog.

Reuses the shared `tags` table for tag definitions and `FileTagRepository`
for path-level assignments.  Shown as a modal QDialog (not an overlay widget)
since FileManagerView's layout doesn't require the overlay pattern.
"""
from __future__ import annotations

from pathlib import Path

import strings
from backends.file_tags_backend import FileTagRepository
from backends.tags_backend import TagRepository
from models.file_entry import FileEntry
from models.tag import Tag
from views.tag_pill import TagPill

from PyQt6.QtCore import QPoint, QRect, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QPainter, QPalette
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QLayout,
    QMenu,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)


# ── Flow layout (same as tag_editor_modal.py) ─────────────────────────────────

class _FlowLayout(QLayout):
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


# ── File tag modal dialog ─────────────────────────────────────────────────────

class FileTagModal(QDialog):
    """Modal dialog for assigning tags to one or more file paths."""

    saved = pyqtSignal()  # emitted after successful save

    def __init__(
        self,
        entries: list[FileEntry],
        parent: QWidget | None = None,
        db_path: Path | None = None,
    ) -> None:
        super().__init__(parent)
        self._entries = entries
        self._tag_repo = TagRepository(db_path)
        self._file_tag_repo = FileTagRepository(db_path)
        self._selected_color: str = strings.TAG_PALETTE[2]
        self._pills: list[TagPill] = []

        self.setWindowTitle(
            strings.FT_MODAL_TITLE.format(name=entries[0].name)
            if len(entries) == 1
            else strings.FT_MODAL_TITLE_BATCH.format(n=len(entries))
        )
        self.setMinimumWidth(380)
        self.setModal(True)

        outer = QVBoxLayout(self)
        outer.setSpacing(8)

        # Subtitle
        subtitle = QLabel(strings.FT_MODAL_SUBTITLE)
        subtitle.setStyleSheet("color: palette(text); font-size: 10px;")
        outer.addWidget(subtitle)

        # ── Assign section ───────────────────────────────────────────────────
        assign_lbl = QLabel(strings.FT_ASSIGN_HEADER)
        assign_lbl.setStyleSheet("color: palette(text); font-size: 10px;")
        outer.addWidget(assign_lbl)

        self._no_tags_label = QLabel(strings.FT_NO_TAGS_MSG)
        self._no_tags_label.setStyleSheet(
            "color: palette(mid); font-style: italic;")
        outer.addWidget(self._no_tags_label)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setMinimumHeight(60)
        scroll.setMaximumHeight(120)

        self._pill_widget = QWidget()
        self._pill_widget.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
        self._pill_layout = _FlowLayout(self._pill_widget, h_gap=6, v_gap=6)
        self._pill_widget.setLayout(self._pill_layout)
        scroll.setWidget(self._pill_widget)
        outer.addWidget(scroll)

        divider = QFrame()
        divider.setFrameShape(QFrame.Shape.HLine)
        divider.setFrameShadow(QFrame.Shadow.Sunken)
        outer.addWidget(divider)

        # ── Create section ───────────────────────────────────────────────────
        create_lbl = QLabel(strings.FT_CREATE_HEADER)
        create_lbl.setStyleSheet("color: palette(text); font-size: 10px;")
        outer.addWidget(create_lbl)

        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText(strings.TAG_EDITOR_NAME_PLACEHOLDER)
        self._name_edit.setStyleSheet("QLineEdit { color: palette(text); }")
        outer.addWidget(self._name_edit)

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
        outer.addWidget(color_container)

        # ── Buttons ──────────────────────────────────────────────────────────
        buttons = QDialogButtonBox()
        self._save_btn = buttons.addButton(
            strings.FT_SAVE_BTN, QDialogButtonBox.ButtonRole.AcceptRole)
        buttons.addButton(
            strings.FT_CANCEL_BTN, QDialogButtonBox.ButtonRole.RejectRole)
        buttons.accepted.connect(self._on_save)
        buttons.rejected.connect(self.reject)
        outer.addWidget(buttons)

        self._rebuild_pills()

    # ── Internals ─────────────────────────────────────────────────────────────

    def _rebuild_pills(self) -> None:
        for pill in self._pills:
            pill.setParent(None)
        self._pills.clear()
        while self._pill_layout.count():
            self._pill_layout.takeAt(0)

        all_tags = self._tag_repo.all_tags()
        if not all_tags:
            self._no_tags_label.setVisible(True)
            return
        self._no_tags_label.setVisible(False)

        # For multiple entries, a tag starts assigned only if ALL have it
        paths = [str(e.path) for e in self._entries]
        tag_map = self._file_tag_repo.bulk_load(paths)
        if len(self._entries) == 1:
            assigned_names = {t.name for t in tag_map.get(paths[0], [])}
        else:
            sets = [frozenset(t.name for t in tag_map.get(p, [])) for p in paths]
            assigned_names = set(sets[0].intersection(*sets[1:])) if sets else set()

        for tag in all_tags:
            pill = TagPill(tag, tag.name in assigned_names)
            pill.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            pill.customContextMenuRequested.connect(
                lambda pos, t=tag, p=pill: self._on_pill_context_menu(t, p, pos)
            )
            self._pill_layout.addWidget(pill)
            self._pills.append(pill)

    def _on_pill_context_menu(self, tag: Tag, pill, pos) -> None:
        menu = QMenu(self)
        delete_act = menu.addAction(strings.FT_DELETE_TAG_CTX)
        if menu.exec(pill.mapToGlobal(pos)) is not delete_act:
            return
        msg = QMessageBox(self)
        msg.setWindowTitle(strings.FT_DELETE_TAG_TITLE.format(name=tag.name))
        msg.setText(strings.FT_DELETE_TAG_TITLE.format(name=tag.name))
        msg.setInformativeText(strings.FT_DELETE_TAG_BODY)
        msg.setStandardButtons(
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        msg.button(QMessageBox.StandardButton.Yes).setText(strings.TAG_DELETE_YES)
        msg.button(QMessageBox.StandardButton.No).setText(strings.TAG_DELETE_NO)
        msg.setDefaultButton(QMessageBox.StandardButton.No)
        if msg.exec() != QMessageBox.StandardButton.Yes:
            return
        try:
            self._tag_repo.delete_tag(tag.name)
        except Exception:
            pass
        self._rebuild_pills()
        self.saved.emit()

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
                self._tag_repo.create_tag(name, self._selected_color)
            except Exception:
                pass  # duplicate name — pill assignment still proceeds

        assigned: set[str] = {p.tag.name for p in self._pills if p.is_assigned()}
        if name:
            assigned.add(name)

        for entry in self._entries:
            self._file_tag_repo.set_assignments(str(entry.path), assigned)

        self.saved.emit()
        self.accept()
