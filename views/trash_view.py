"""M10d.1: TrashView — listing of items in the Wastebin.

Columns: Name | Original Location | Deletion Date | Size
Default sort: Deletion Date descending (newest first, pre-sorted by backend).
Selection: extended (multi-select supported).
Context menu: Restore | Delete Permanently.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

import strings
from backends.trash_backend import TrashEntry
from models.file_entry import fmt_size
from views.file_view import _chrome_icon

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QFileIconProvider,
    QHeaderView,
    QMenu,
    QStyle,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

_COL_NAME     = 0
_COL_ORIGINAL = 1
_COL_DATE     = 2
_COL_SIZE     = 3

_ENTRY_ROLE = Qt.ItemDataRole.UserRole + 1  # stores index into _entries list


def _trash_icon() -> object:
    return _chrome_icon("user-trash", QStyle.StandardPixmap.SP_TrashIcon)

def _folder_icon() -> object:
    return _chrome_icon("folder", QStyle.StandardPixmap.SP_DirIcon)

def _file_icon() -> object:
    provider = QFileIconProvider()
    return provider.icon(QFileIconProvider.IconType.File)


class TrashView(QWidget):
    """Displays the contents of the Freedesktop Trash as a flat table."""

    action_requested = pyqtSignal(str, list)
    # emits ("restore", [TrashEntry]) or ("delete_permanently", [TrashEntry])

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._tree = QTreeWidget()
        self._tree.setColumnCount(4)
        self._tree.setHeaderLabels([
            strings.TRASH_COL_NAME,
            strings.TRASH_COL_ORIGINAL,
            strings.TRASH_COL_DATE,
            strings.TRASH_COL_SIZE,
        ])
        self._tree.setRootIsDecorated(False)
        self._tree.setSortingEnabled(False)
        self._tree.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection)
        self._tree.setContextMenuPolicy(
            Qt.ContextMenuPolicy.CustomContextMenu)
        self._tree.customContextMenuRequested.connect(self._on_context_menu)
        self._tree.setAlternatingRowColors(False)

        hdr = self._tree.header()
        hdr.setStretchLastSection(False)
        hdr.setSectionResizeMode(_COL_NAME,     QHeaderView.ResizeMode.Interactive)
        hdr.setSectionResizeMode(_COL_ORIGINAL, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(_COL_DATE,     QHeaderView.ResizeMode.Interactive)
        hdr.setSectionResizeMode(_COL_SIZE,     QHeaderView.ResizeMode.Interactive)
        self._tree.setColumnWidth(_COL_NAME,  200)
        self._tree.setColumnWidth(_COL_DATE,  150)
        self._tree.setColumnWidth(_COL_SIZE,   80)

        layout.addWidget(self._tree)

        self._entries: list[TrashEntry] = []

    # ── Public API ─────────────────────────────────────────────────────────────

    def show_loading(self) -> None:
        """Show a transient loading placeholder while the list worker runs."""
        self._tree.clear()
        self._entries = []
        item = QTreeWidgetItem([strings.TRASH_LOADING, "", "", ""])
        item.setFlags(Qt.ItemFlag.NoItemFlags)
        self._tree.addTopLevelItem(item)

    def show_error(self, msg: str) -> None:
        """Replace the loading placeholder with a readable error message."""
        self._tree.clear()
        self._entries = []
        item = QTreeWidgetItem(
            [strings.TRASH_LOAD_ERROR.format(msg=msg), "", "", ""])
        item.setFlags(Qt.ItemFlag.NoItemFlags)
        self._tree.addTopLevelItem(item)

    def load(self, entries: list[TrashEntry]) -> None:
        """Populate the view.  Entries expected newest-first (from backend)."""
        self._tree.clear()
        self._entries = list(entries)

        if not entries:
            placeholder = QTreeWidgetItem([strings.TRASH_EMPTY_VIEW, "", "", ""])
            placeholder.setFlags(Qt.ItemFlag.NoItemFlags)
            self._tree.addTopLevelItem(placeholder)
            return

        file_icon   = _file_icon()
        folder_icon = _folder_icon()

        for i, entry in enumerate(self._entries):
            item = QTreeWidgetItem()
            item.setText(_COL_NAME,     entry.name)
            item.setText(_COL_ORIGINAL, str(entry.original_path.parent))
            item.setText(_COL_DATE,     entry.deletion_date.strftime("%Y-%m-%d  %H:%M"))
            # size == -1 means directory (no recursive sizing); render as "—"
            item.setText(_COL_SIZE,     fmt_size(entry.size) if entry.size >= 0 else "—")
            item.setData(0, _ENTRY_ROLE, i)
            item.setTextAlignment(_COL_SIZE, Qt.AlignmentFlag.AlignRight)
            item.setIcon(_COL_NAME, folder_icon if entry.is_dir else file_icon)
            self._tree.addTopLevelItem(item)

    def all_entries(self) -> list[TrashEntry]:
        """Return the currently displayed entries (from the last load() call)."""
        return list(self._entries)

    def get_selected_entries(self) -> list[TrashEntry]:
        result: list[TrashEntry] = []
        for item in self._tree.selectedItems():
            idx = item.data(0, _ENTRY_ROLE)
            if idx is not None and 0 <= idx < len(self._entries):
                result.append(self._entries[idx])
        return result

    # ── Internal ───────────────────────────────────────────────────────────────

    def _on_context_menu(self, pos) -> None:
        entries = self.get_selected_entries()
        if not entries:
            return
        menu = QMenu(self)
        menu.addAction(strings.TRASH_CTX_RESTORE).triggered.connect(
            lambda: self.action_requested.emit("restore", list(entries)))
        menu.addAction(strings.TRASH_CTX_DELETE).triggered.connect(
            lambda: self.action_requested.emit("delete_permanently", list(entries)))
        menu.exec(self._tree.viewport().mapToGlobal(pos))
