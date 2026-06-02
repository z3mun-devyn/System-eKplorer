"""M10c: FileView — reusable flat-directory-listing widget.

Column layout (6 cols):
    0  Icon          36px fixed   (decoration only, no text)
    1  Name          stretch
    2  Tags          80px         (empty shell — M10e populates)
    3  Category      120px        (MIME description)
    4  Date Modified 140px
    5  Size          80px         (right-aligned; dirs show item count)

View modes: "details" | "icons_small" | "icons_medium" | "icons_large"

Threading discipline:
    _load() starts a QThread only after the widget has been show()n.
    Before first show, navigate() / set_show_hidden() store state but do
    not spawn threads, so tests that never call show() are safe.
"""
from __future__ import annotations

import subprocess
import sys
from datetime import datetime
from pathlib import Path

import strings
from backends.directory_backend import DirectoryLoader
from models.file_entry import FileEntry, fmt_size, mime_label
from models.tag import Tag

from PyQt6.QtCore import (
    QAbstractTableModel,
    QEvent,
    QFileInfo,
    QMimeData,
    QMimeDatabase,
    QModelIndex,
    QSize,
    QSortFilterProxyModel,
    Qt,
    QThread,
    QUrl,
    pyqtSignal,
)
from PyQt6.QtCore import QRect
from PyQt6.QtGui import QColor, QFontMetrics, QIcon, QPainter, QPalette
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QFileIconProvider,
    QHeaderView,
    QLineEdit,
    QListView,
    QMenu,
    QSizePolicy,
    QStackedWidget,
    QStyle,
    QStyledItemDelegate,
    QTreeView,
    QVBoxLayout,
    QWidget,
)

# Custom roles
_SORT_ROLE     = Qt.ItemDataRole.UserRole + 1
_ENTRY_ROLE    = Qt.ItemDataRole.UserRole + 2
_TAG_DATA_ROLE = Qt.ItemDataRole.UserRole + 3   # returns list[Tag] for _COL_TAGS

# Column indices
_COL_ICON          = 0
_COL_NAME          = 1
_COL_TAGS          = 2
_COL_CATEGORY      = 3
_COL_DATE_MODIFIED = 4
_COL_SIZE          = 5

_SKELETON_ROWS = 8
_SKELETON_TEXT = "  · · ·"

# Icon view sizes: (icon_w, icon_h, grid_w, grid_h)
_ICON_SIZES = {
    "icons_small":  (QSize(24, 24), QSize(60,  60)),
    "icons_medium": (QSize(48, 48), QSize(90,  80)),
    "icons_large":  (QSize(96, 96), QSize(130, 120)),
}

# Tag pill rendering constants (same as packages_view)
_PILL_H     = 16
_PILL_H_PAD = 6
_PILL_GAP   = 4
_MAX_PILLS  = 4


# ── Helpers ───────────────────────────────────────────────────────────────────

def _fmt_modified(ts: float) -> str:
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d  %H:%M")


def _fmt_item_count(n: int | None) -> str:
    if n is None:
        return "—"
    if n == 1:
        return strings.FM_SIZE_ITEMS_ONE
    return strings.FM_SIZE_ITEMS_MANY.format(n=n)


# ── FM icon resolver (self-adaptive, cached per MIME name) ────────────────────
# At first use, tests whether theme icons are visually viable on this system.
# Viable  (Plasma 6 / kde platformtheme): 3-tier fromTheme chain.
# Not viable (Plasma 5.27 Qt6, no KDE colour engine): QFileIconProvider only.

_ICON_CACHE: dict[tuple[str, bool], QIcon] = {}
_ICON_CACHE_THEME: str = ""
_FILE_ICON_PROVIDER: QFileIconProvider | None = None
_MIME_DB: QMimeDatabase | None = None
_THEME_VIABLE: bool | None = None   # None = not yet tested


def _chrome_icon(
    theme_name: str,
    fallback_standard: QStyle.StandardPixmap | None = None,
) -> QIcon:
    """Return a chrome/toolbar icon that's always visible.

    Tries fromTheme when the theme is viable (or not yet tested); falls back
    to a QStyle standard pixmap so Bob's Plasma 5.27 system sees an icon.
    """
    if _THEME_VIABLE is not False:
        icon = QIcon.fromTheme(theme_name)
        if not icon.isNull():
            return icon
    if fallback_standard is not None:
        return QApplication.style().standardIcon(fallback_standard)
    return QIcon()


def _icon_theme_fallback(*names: str) -> QIcon:
    for name in names:
        icon = QIcon.fromTheme(name)
        if not icon.isNull():
            return icon
    return QIcon()


def _check_theme_icons_viable() -> bool:
    """Return True if QIcon.fromTheme produces visible (non-black) icons here."""
    icon = QIcon.fromTheme("folder")
    if icon.isNull():
        return False
    pm = icon.pixmap(16, 16)
    if pm.isNull():
        return False
    img = pm.toImage()
    for y in range(img.height()):
        for x in range(img.width()):
            c = img.pixelColor(x, y)
            if c.alpha() > 128:
                lum = 0.299 * c.red() + 0.587 * c.green() + 0.114 * c.blue()
                if lum > 40:
                    return True
    return False


def _entry_icon(entry: FileEntry) -> QIcon:
    global _ICON_CACHE, _ICON_CACHE_THEME, _FILE_ICON_PROVIDER, _MIME_DB, _THEME_VIABLE

    # One-time visibility probe (lazy — QApplication must already exist)
    if _THEME_VIABLE is None:
        _THEME_VIABLE = _check_theme_icons_viable()
        print(
            f"eKplorer: icon theme viable = {_THEME_VIABLE}"
            f" (theme: {QIcon.themeName() or 'none'})",
            file=sys.stderr,
        )

    # Invalidate cache on theme change (live KDE theme switch)
    theme = QIcon.themeName()
    if theme != _ICON_CACHE_THEME:
        _ICON_CACHE.clear()
        _ICON_CACHE_THEME = theme

    if not _THEME_VIABLE:
        # Fast path: QFileIconProvider only — always renders visibly on Bob's system
        if entry.is_dir:
            key = ("inode/directory", True)
        else:
            if _MIME_DB is None:
                _MIME_DB = QMimeDatabase()
            key = (_MIME_DB.mimeTypeForFile(str(entry.path)).name(), False)
        if key in _ICON_CACHE:
            return _ICON_CACHE[key]
        if _FILE_ICON_PROVIDER is None:
            _FILE_ICON_PROVIDER = QFileIconProvider()
        icon = _FILE_ICON_PROVIDER.icon(QFileInfo(str(entry.path)))
        if icon.isNull():
            icon = _icon_theme_fallback("unknown", "application-x-generic")
        _ICON_CACHE[key] = icon
        return icon

    # Viable path: full 3-tier fromTheme chain
    if entry.is_dir:
        key = ("inode/directory", True)
        if key not in _ICON_CACHE:
            _ICON_CACHE[key] = _icon_theme_fallback("inode-directory", "folder")
        return _ICON_CACHE[key]

    if _MIME_DB is None:
        _MIME_DB = QMimeDatabase()
    mime = _MIME_DB.mimeTypeForFile(str(entry.path))
    key = (mime.name(), False)
    if key in _ICON_CACHE:
        return _ICON_CACHE[key]

    # Tier 2: MIME icon chain
    icon = QIcon.fromTheme(mime.iconName())
    if icon.isNull():
        for parent_name in mime.parentMimeTypes():
            parent_mime = _MIME_DB.mimeTypeForName(parent_name)
            icon = QIcon.fromTheme(parent_mime.iconName())
            if not icon.isNull():
                break
    if icon.isNull():
        icon = QIcon.fromTheme(mime.genericIconName())

    # Tier 3: QFileIconProvider
    if icon.isNull():
        if _FILE_ICON_PROVIDER is None:
            _FILE_ICON_PROVIDER = QFileIconProvider()
        icon = _FILE_ICON_PROVIDER.icon(QFileInfo(str(entry.path)))

    # Floor: never null
    if icon.isNull():
        icon = _icon_theme_fallback("unknown", "application-x-generic")

    _ICON_CACHE[key] = icon
    return icon


# ── Model ─────────────────────────────────────────────────────────────────────

class _FileModel(QAbstractTableModel):
    _HEADERS = [
        strings.FM_COL_ICON,
        strings.FM_COL_NAME,
        strings.FM_COL_TAGS,
        strings.FM_COL_CATEGORY,
        strings.FM_COL_DATE_MODIFIED,
        strings.FM_COL_SIZE,
    ]

    # Emitted by dropMimeData; consumed by FileView → FileManagerView
    drop_requested = pyqtSignal(list, str, bool)  # (source_paths, target_dir, copy)

    def __init__(self) -> None:
        super().__init__()
        self._entries: list[FileEntry] = []
        self._loading = False
        self._icon_mode = False  # True while any icons_* view is active
        self._current_dir: str = str(Path.home())  # updated on every navigate()
        self._tag_map: dict[str, list[Tag]] = {}  # path_str → list[Tag]

    # ── Mutation ──────────────────────────────────────────────────────────────

    def set_loading(self, loading: bool) -> None:
        self.beginResetModel()
        self._loading = loading
        self.endResetModel()

    def set_entries(self, entries: list[FileEntry]) -> None:
        self.beginResetModel()
        self._entries = sorted(
            entries,
            key=lambda e: (0 if e.is_dir else 1, e.name.lower()),
        )
        self._loading = False
        self.endResetModel()

    def set_icon_mode(self, enabled: bool) -> None:
        """Toggle icon-mode: column 0 returns entry name as DisplayRole when on."""
        if self._icon_mode == enabled:
            return
        self._icon_mode = enabled
        if self.rowCount() > 0:
            top_left = self.index(0, _COL_ICON)
            bottom_right = self.index(self.rowCount() - 1, _COL_ICON)
            self.dataChanged.emit(
                top_left, bottom_right, [Qt.ItemDataRole.DisplayRole])

    def set_tag_map(self, tag_map: dict[str, list[Tag]]) -> None:
        """Update path→tags mapping and repaint the Tags column."""
        self._tag_map = tag_map
        if self.rowCount() > 0:
            top_left = self.index(0, _COL_TAGS)
            bottom_right = self.index(self.rowCount() - 1, _COL_TAGS)
            self.dataChanged.emit(top_left, bottom_right, [])

    # ── QAbstractTableModel interface ─────────────────────────────────────────

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return _SKELETON_ROWS if self._loading else len(self._entries)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 6

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        row, col = index.row(), index.column()

        if self._loading:
            if role == Qt.ItemDataRole.DisplayRole and col == _COL_NAME:
                return _SKELETON_TEXT
            if role == Qt.ItemDataRole.ForegroundRole:
                return QColor("gray")
            return None

        if row >= len(self._entries):
            return None
        entry = self._entries[row]

        if role == Qt.ItemDataRole.DisplayRole:
            if col == _COL_ICON:
                return entry.name if self._icon_mode else None
            if col == _COL_NAME:
                return entry.name
            if col == _COL_TAGS:
                tags = self._tag_map.get(str(entry.path), [])
                return ", ".join(t.name for t in tags) if tags else ""
            if col == _COL_CATEGORY:
                return mime_label(entry.mime_type, entry.is_dir)
            if col == _COL_DATE_MODIFIED:
                return _fmt_modified(entry.modified)
            if col == _COL_SIZE:
                if entry.is_dir:
                    return _fmt_item_count(entry.item_count)
                return fmt_size(entry.size)

        elif role == Qt.ItemDataRole.TextAlignmentRole:
            if col == _COL_SIZE:
                return int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        elif role == _SORT_ROLE:
            if col == _COL_ICON:
                return None
            if col == _COL_NAME:
                return (0 if entry.is_dir else 1, entry.name.lower())
            if col == _COL_TAGS:
                tags = self._tag_map.get(str(entry.path), [])
                return tags[0].name.lower() if tags else ""
            if col == _COL_CATEGORY:
                return mime_label(entry.mime_type, entry.is_dir)
            if col == _COL_DATE_MODIFIED:
                return entry.modified
            if col == _COL_SIZE:
                if entry.is_dir:
                    return entry.item_count if entry.item_count is not None else -1
                return entry.size if entry.size is not None else -1

        elif role == _ENTRY_ROLE:
            if col == _COL_ICON:
                return entry

        elif role == _TAG_DATA_ROLE:
            if col == _COL_TAGS:
                return self._tag_map.get(str(entry.path), [])

        elif role == Qt.ItemDataRole.DecorationRole and col == _COL_ICON:
            return _entry_icon(entry)

        return None

    def flags(self, index: QModelIndex) -> Qt.ItemFlag:
        if not index.isValid():
            # Allow dropping on empty space (= current directory)
            return Qt.ItemFlag.ItemIsDropEnabled
        base = super().flags(index)
        if self._loading:
            return base
        base |= Qt.ItemFlag.ItemIsDragEnabled | Qt.ItemFlag.ItemIsDropEnabled
        if index.column() == _COL_NAME:
            base |= Qt.ItemFlag.ItemIsEditable
        return base

    def headerData(
        self, section: int, orientation: Qt.Orientation,
        role: int = Qt.ItemDataRole.DisplayRole,
    ):
        if (orientation == Qt.Orientation.Horizontal
                and role == Qt.ItemDataRole.DisplayRole):
            return self._HEADERS[section]
        return None

    # ── Drag-and-drop ─────────────────────────────────────────────────────────

    def mimeTypes(self) -> list[str]:
        return ["text/uri-list"]

    def supportedDragActions(self) -> Qt.DropAction:
        return Qt.DropAction.CopyAction | Qt.DropAction.MoveAction

    def supportedDropActions(self) -> Qt.DropAction:
        return Qt.DropAction.CopyAction | Qt.DropAction.MoveAction

    def mimeData(self, indexes) -> QMimeData | None:
        """Return QMimeData with file:// URLs for each selected row (deduped)."""
        urls: list[QUrl] = []
        seen: set[str] = set()
        for idx in indexes:
            if idx.column() != _COL_ICON:
                continue
            entry: FileEntry | None = self.data(idx, _ENTRY_ROLE)
            if entry is not None:
                p = str(entry.path)
                if p not in seen:
                    seen.add(p)
                    urls.append(QUrl.fromLocalFile(p))
        if not urls:
            return None
        data = QMimeData()
        data.setUrls(urls)
        return data

    def canDropMimeData(self, data, action, row, column, parent) -> bool:
        if not data.hasUrls():
            return False
        if parent.isValid():
            # Hovering over a specific item — only allow drop onto directories
            entry: FileEntry | None = self.data(
                parent.siblingAtColumn(_COL_ICON), _ENTRY_ROLE)
            return entry is not None and entry.is_dir
        return True  # Empty space or between rows → current directory

    def dropMimeData(self, data, action, row, column, parent) -> bool:
        if not data.hasUrls():
            return False
        source_paths = [u.toLocalFile() for u in data.urls() if u.isLocalFile()]
        if not source_paths:
            return False
        if parent.isValid():
            entry: FileEntry | None = self.data(
                parent.siblingAtColumn(_COL_ICON), _ENTRY_ROLE)
            target_dir = (str(entry.path)
                          if (entry and entry.is_dir) else self._current_dir)
        else:
            target_dir = self._current_dir
        # Ctrl held at drop time → always copy; otherwise respect drop action
        copy = (action == Qt.DropAction.CopyAction) or bool(
            QApplication.keyboardModifiers() & Qt.KeyboardModifier.ControlModifier
        )
        self.drop_requested.emit(source_paths, target_dir, copy)
        return True


# ── Proxy (search + sort) ─────────────────────────────────────────────────────

class _FileProxy(QSortFilterProxyModel):
    def __init__(self) -> None:
        super().__init__()
        self.setSortRole(_SORT_ROLE)
        self.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.setFilterKeyColumn(_COL_NAME)   # filter by Name col

    def filterAcceptsRow(self, source_row: int, source_parent: QModelIndex) -> bool:
        if self.sourceModel()._loading:
            return True
        return super().filterAcceptsRow(source_row, source_parent)

    def lessThan(self, left: QModelIndex, right: QModelIndex) -> bool:
        lv = left.data(_SORT_ROLE)
        rv = right.data(_SORT_ROLE)
        if lv is None or rv is None:
            return False
        try:
            return lv < rv
        except TypeError:
            return str(lv) < str(rv)


# ── Rename delegate ───────────────────────────────────────────────────────────

class _NameEditDelegate(QStyledItemDelegate):
    """Inline editor for the Name column.  On commit, emits rename_committed
    instead of writing to the model; the model is refreshed after the rename."""

    rename_committed = pyqtSignal(str, str)  # (old_path_str, new_name)

    def __init__(
        self,
        proxy: QSortFilterProxyModel,
        source_model: "_FileModel",
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._proxy  = proxy
        self._source = source_model

    def createEditor(self, parent, option, index):
        editor = QLineEdit(parent)
        return editor

    def setEditorData(self, editor: QLineEdit, index: QModelIndex) -> None:
        src = self._proxy.mapToSource(index.siblingAtColumn(_COL_ICON))
        entry: FileEntry | None = self._source.data(src, _ENTRY_ROLE)
        if entry:
            editor.setText(entry.name)
            editor.selectAll()

    def setModelData(self, editor: QLineEdit, model, index: QModelIndex) -> None:
        new_name = editor.text().strip()
        src = self._proxy.mapToSource(index.siblingAtColumn(_COL_ICON))
        entry: FileEntry | None = self._source.data(src, _ENTRY_ROLE)
        if entry and new_name and new_name != entry.name:
            self.rename_committed.emit(str(entry.path), new_name)
        # Do NOT write to the model — actual rename + refresh happens in FileManagerView


# ── Tag pill delegate for _COL_TAGS ──────────────────────────────────────────

class _FilePillDelegate(QStyledItemDelegate):
    """Paints colored tag pills in the Tags column of the file tree view."""

    def paint(self, painter: QPainter, option, index) -> None:
        super().paint(painter, option, index)   # selection / hover background
        tags: list[Tag] = index.data(_TAG_DATA_ROLE) or []
        if not tags:
            return
        painter.save()
        small_font = painter.font()
        small_font.setPointSize(max(7, small_font.pointSize() - 1))
        painter.setFont(small_font)
        sfm = QFontMetrics(small_font)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = option.rect
        x = rect.left() + _PILL_GAP
        y = rect.top() + (rect.height() - _PILL_H) // 2
        right = rect.right() - _PILL_GAP

        visible = tags[:_MAX_PILLS]
        hidden_count = len(tags) - len(visible)
        rendered = 0

        for tag in visible:
            pw = sfm.horizontalAdvance(tag.name) + _PILL_H_PAD * 2
            if x + pw > right:
                hidden_count += len(visible) - rendered
                break
            pill_rect = QRect(x, y, pw, _PILL_H)
            bg = QColor(tag.color_hex)
            painter.setBrush(bg)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(pill_rect, _PILL_H // 2, _PILL_H // 2)
            pill_fg = QColor(strings.contrast_color(tag.color_hex))
            painter.setPen(pill_fg)
            painter.drawText(pill_rect, Qt.AlignmentFlag.AlignCenter, tag.name)
            x += pw + _PILL_GAP
            rendered += 1

        if hidden_count > 0:
            ot = f"…+{hidden_count}"
            ow = sfm.horizontalAdvance(ot) + _PILL_H_PAD * 2
            if x + ow <= right:
                ov_rect = QRect(x, y, ow, _PILL_H)
                pal = option.palette
                ov_bg = QColor(pal.color(QPalette.ColorRole.Mid))
                ov_bg.setAlphaF(0.3)
                painter.setBrush(ov_bg)
                painter.setPen(Qt.PenStyle.NoPen)
                painter.drawRoundedRect(ov_rect, _PILL_H // 2, _PILL_H // 2)
                painter.setPen(pal.color(QPalette.ColorRole.WindowText))
                painter.drawText(ov_rect, Qt.AlignmentFlag.AlignCenter, ot)

        painter.restore()


# ── FileView ──────────────────────────────────────────────────────────────────

class FileView(QWidget):
    """Reusable flat directory-listing widget.

    Instantiate once for the left pane and once for the right browser pane.
    State (path, history, selection) is completely independent per instance.

    Signals
    -------
    path_changed(str)          — emitted on every successful navigate()
    file_opened(str)           — emitted when a file is opened via xdg-open
    selection_changed(list)    — list[FileEntry] of currently selected rows
    hover_changed(object)      — FileEntry under mouse, or None
    zoom_requested(int)        — +1 (zoom in) or -1 (zoom out) from Ctrl+Scroll
    """

    path_changed       = pyqtSignal(str)
    file_opened        = pyqtSignal(str)
    selection_changed  = pyqtSignal(list)
    hover_changed      = pyqtSignal(object)
    zoom_requested     = pyqtSignal(int)
    entries_ready      = pyqtSignal()     # fired after each successful directory load
    # (action_name, payload_list) — consumed by FileManagerView
    # payload items are FileEntry objects except for rename: [path_str, new_name]
    action_requested   = pyqtSignal(str, list)
    # DnD: (source_paths, target_dir, copy) — consumed by FileManagerView
    drop_requested     = pyqtSignal(list, str, bool)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self._current_path: Path = Path.home()
        self._back_stack:    list[Path] = []
        self._forward_stack: list[Path] = []
        self._show_hidden    = False
        self._view_mode      = "details"
        self._shown          = False   # set True on first showEvent
        self._paste_enabled  = False   # toggled by FileManagerView on cut/copy

        self._thread: QThread | None = None
        self._worker: DirectoryLoader | None = None

        self._model = _FileModel()
        self._proxy = _FileProxy()
        self._proxy.setSourceModel(self._model)
        self._model.drop_requested.connect(self.drop_requested)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._view_stack = QStackedWidget()

        # ── Details view (QTreeView) ──────────────────────────────────────────
        self._tree = QTreeView()
        self._tree.setModel(self._proxy)
        self._tree.setRootIsDecorated(False)
        self._tree.setAlternatingRowColors(False)
        self._tree.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection)
        self._tree.setSortingEnabled(True)
        self._tree.sortByColumn(_COL_NAME, Qt.SortOrder.AscendingOrder)
        self._tree.setMouseTracking(True)

        hdr = self._tree.header()
        hdr.setSectionResizeMode(_COL_ICON, QHeaderView.ResizeMode.Fixed)
        hdr.resizeSection(_COL_ICON, 36)
        hdr.setSectionResizeMode(_COL_NAME, QHeaderView.ResizeMode.Stretch)
        for col, width in (
            (_COL_TAGS,          80),
            (_COL_CATEGORY,     120),
            (_COL_DATE_MODIFIED, 140),
            (_COL_SIZE,          80),
        ):
            hdr.setSectionResizeMode(col, QHeaderView.ResizeMode.Interactive)
            hdr.resizeSection(col, width)
        hdr.setStretchLastSection(False)

        self._tree.setDragEnabled(True)
        self._tree.setAcceptDrops(True)
        self._tree.setDropIndicatorShown(True)
        self._tree.setDragDropMode(QAbstractItemView.DragDropMode.DragDrop)
        self._tree.setDefaultDropAction(Qt.DropAction.MoveAction)

        self._tree.doubleClicked.connect(self._on_double_click)
        self._tree.selectionModel().selectionChanged.connect(
            self._on_selection_changed)
        self._tree.viewport().setMouseTracking(True)
        self._tree.viewport().installEventFilter(self)

        # Inline rename delegate on Name column
        self._name_delegate = _NameEditDelegate(self._proxy, self._model, self)
        self._name_delegate.rename_committed.connect(
            lambda p, n: self.action_requested.emit("rename", [p, n]))
        self._tree.setItemDelegateForColumn(_COL_NAME, self._name_delegate)

        # Tag pill delegate on Tags column
        self._pill_delegate = _FilePillDelegate(self._tree)
        self._tree.setItemDelegateForColumn(_COL_TAGS, self._pill_delegate)
        self._tree.setEditTriggers(
            QAbstractItemView.EditTrigger.SelectedClicked
            | QAbstractItemView.EditTrigger.EditKeyPressed)

        # Context menu
        self._tree.setContextMenuPolicy(
            Qt.ContextMenuPolicy.CustomContextMenu)
        self._tree.customContextMenuRequested.connect(
            self._on_context_menu)

        # ── Icons view (QListView) ────────────────────────────────────────────
        self._list = QListView()
        self._list.setModel(self._proxy)
        self._list.setViewMode(QListView.ViewMode.IconMode)
        self._list.setIconSize(QSize(48, 48))
        self._list.setGridSize(QSize(90, 80))
        self._list.setResizeMode(QListView.ResizeMode.Adjust)
        self._list.setWordWrap(True)
        self._list.setUniformItemSizes(True)
        self._list.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection)
        self._list.setDragEnabled(True)
        self._list.setAcceptDrops(True)
        self._list.setDropIndicatorShown(True)
        self._list.setDragDropMode(QAbstractItemView.DragDropMode.DragDrop)
        self._list.setDefaultDropAction(Qt.DropAction.MoveAction)
        self._list.doubleClicked.connect(self._on_double_click)
        self._list.selectionModel().selectionChanged.connect(
            self._on_selection_changed)
        self._list.viewport().installEventFilter(self)
        self._list.setContextMenuPolicy(
            Qt.ContextMenuPolicy.CustomContextMenu)
        self._list.customContextMenuRequested.connect(
            self._on_context_menu)

        self._view_stack.addWidget(self._tree)   # index 0 — details
        self._view_stack.addWidget(self._list)   # index 1 — icons
        layout.addWidget(self._view_stack)

    # ── Qt lifecycle ──────────────────────────────────────────────────────────

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if not self._shown:
            self._shown = True
            self._load()
            self.path_changed.emit(str(self._current_path))

    # ── Navigation API ────────────────────────────────────────────────────────

    def navigate(self, path: Path | str, *, record_history: bool = True) -> None:
        """Navigate to a directory.  No-op if path is not a directory."""
        path = Path(path)
        if not path.is_dir():
            return
        if record_history and self._current_path != path:
            self._back_stack.append(self._current_path)
            self._forward_stack.clear()
        self._current_path = path
        self._model._current_dir = str(path)  # keep model in sync for DnD
        self.path_changed.emit(str(path))
        if self._shown:
            self._load()

    def navigate_back(self) -> None:
        if not self._back_stack:
            return
        self._forward_stack.append(self._current_path)
        self.navigate(self._back_stack.pop(), record_history=False)

    def navigate_forward(self) -> None:
        if not self._forward_stack:
            return
        self._back_stack.append(self._current_path)
        self.navigate(self._forward_stack.pop(), record_history=False)

    def navigate_up(self) -> None:
        parent = self._current_path.parent
        if parent != self._current_path:
            self.navigate(parent)

    # ── State setters ─────────────────────────────────────────────────────────

    def set_search(self, text: str) -> None:
        self._proxy.setFilterFixedString(text)

    def set_show_hidden(self, show: bool) -> None:
        self._show_hidden = show
        if self._shown:
            self._load()

    def set_view_mode(self, mode: str) -> None:
        self._view_mode = mode
        self._model.set_icon_mode(mode != "details")
        if mode == "details":
            self._view_stack.setCurrentIndex(0)
        else:
            self._view_stack.setCurrentIndex(1)
            icon_size, grid_size = _ICON_SIZES.get(
                mode, _ICON_SIZES["icons_medium"])
            self._list.setIconSize(icon_size)
            self._list.setGridSize(grid_size)

    def set_tag_map(self, tag_map: dict[str, list[Tag]]) -> None:
        """Update path→tags mapping so the Tags column repopulates."""
        self._model.set_tag_map(tag_map)

    def set_alternating_rows(self, enabled: bool) -> None:
        self._tree.setAlternatingRowColors(enabled)

    def set_paste_enabled(self, enabled: bool) -> None:
        self._paste_enabled = enabled

    # ── State queries ─────────────────────────────────────────────────────────

    @property
    def current_path(self) -> Path:
        return self._current_path

    def can_go_back(self) -> bool:
        return bool(self._back_stack)

    def can_go_forward(self) -> bool:
        return bool(self._forward_stack)

    def can_go_up(self) -> bool:
        return self._current_path.parent != self._current_path

    # ── Private: loading ──────────────────────────────────────────────────────

    def _load(self) -> None:
        if self._thread and self._thread.isRunning():
            self._thread.quit()

        self._model.set_loading(True)
        self._thread = QThread()
        self._worker = DirectoryLoader(self._current_path, self._show_hidden)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.ready.connect(self._model.set_entries)
        self._worker.ready.connect(lambda _: self.entries_ready.emit())
        self._worker.ready.connect(self._thread.quit)
        self._worker.failed.connect(self._thread.quit)
        self._thread.finished.connect(self._worker.deleteLater)
        self._thread.start()

    # ── Private: interaction ──────────────────────────────────────────────────

    def _get_selected_entries(self) -> list[FileEntry]:
        active = self._tree if self._view_mode == "details" else self._list
        indexes = active.selectionModel().selectedRows()
        entries = []
        seen = set()
        for idx in indexes:
            src = self._proxy.mapToSource(idx.siblingAtColumn(_COL_ICON))
            entry = self._model.data(src, _ENTRY_ROLE)
            if entry and id(entry) not in seen:
                seen.add(id(entry))
                entries.append(entry)
        return entries

    def _on_context_menu(self, pos) -> None:
        sender = self.sender()
        idx = sender.indexAt(pos)
        entries = self._get_selected_entries()
        # If clicking outside any item, treat as empty-area click
        if not idx.isValid():
            entries = []

        single = len(entries) == 1
        multi  = len(entries) > 1
        is_dir = single and entries[0].is_dir

        menu = QMenu(self)

        if single:
            menu.addAction(strings.FM_CTX_OPEN).triggered.connect(
                lambda: self.action_requested.emit("open", list(entries)))
            menu.addAction(strings.FM_CTX_OPEN_WITH).triggered.connect(
                lambda: self.action_requested.emit("open_with", list(entries)))
            admin_act = menu.addAction(strings.FM_CTX_OPEN_ADMIN)
            admin_act.triggered.connect(
                lambda: self.action_requested.emit("open_admin", list(entries)))
            menu.addSeparator()

        if entries:
            menu.addAction(strings.FM_CTX_CUT).triggered.connect(
                lambda: self.action_requested.emit("cut", list(entries)))
            menu.addAction(strings.FM_CTX_COPY).triggered.connect(
                lambda: self.action_requested.emit("copy", list(entries)))
            if single:
                menu.addAction(strings.FM_CTX_COPY_PATH).triggered.connect(
                    lambda: self.action_requested.emit("copy_path", list(entries)))
                menu.addAction(strings.FM_CTX_COPY_NAME).triggered.connect(
                    lambda: self.action_requested.emit("copy_name", list(entries)))

        paste_act = menu.addAction(strings.FM_CTX_PASTE)
        paste_act.setEnabled(self._paste_enabled)
        paste_act.triggered.connect(
            lambda: self.action_requested.emit("paste", []))
        menu.addSeparator()

        if single:
            menu.addAction(strings.FM_CTX_RENAME).triggered.connect(
                lambda: self.action_requested.emit("rename_inline", list(entries)))
        if entries:
            menu.addAction(strings.FM_CTX_TRASH).triggered.connect(
                lambda: self.action_requested.emit("trash", list(entries)))
        menu.addSeparator()

        menu.addAction(strings.FM_CTX_NEW_FOLDER).triggered.connect(
            lambda: self.action_requested.emit("new_folder", []))
        menu.addAction(strings.FM_CTX_NEW_FILE).triggered.connect(
            lambda: self.action_requested.emit("new_file", []))

        if entries:
            menu.addSeparator()
            menu.addAction(strings.FM_CTX_ASSIGN_TAGS).triggered.connect(
                lambda: self.action_requested.emit("assign_tags", list(entries)))
            if single:
                menu.addAction(strings.ACTION_PROPERTIES).triggered.connect(
                    lambda: self.action_requested.emit("properties", list(entries)))

        menu.exec(sender.viewport().mapToGlobal(pos))

    def _on_double_click(self, proxy_index: QModelIndex) -> None:
        src = self._proxy.mapToSource(proxy_index.siblingAtColumn(_COL_ICON))
        entry: FileEntry | None = self._model.data(src, _ENTRY_ROLE)
        if entry is None:
            return
        if entry.is_dir:
            self.navigate(entry.path)
        else:
            subprocess.Popen(["xdg-open", str(entry.path)])
            self.file_opened.emit(str(entry.path))

    def _on_selection_changed(self, *_) -> None:
        self.selection_changed.emit(self._get_selected_entries())

    def eventFilter(self, obj, event) -> bool:
        # Ctrl+Scroll on either viewport → zoom_requested signal
        if event.type() == QEvent.Type.Wheel:
            if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
                delta = event.angleDelta().y()
                self.zoom_requested.emit(1 if delta > 0 else -1)
                return True

        # Ctrl+drag: switch default MoveAction to CopyAction.
        # Return False so Qt's dragMoveEvent also runs (for the drop indicator).
        if event.type() == QEvent.Type.DragMove and event.mimeData().hasUrls():
            if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
                event.setDropAction(Qt.DropAction.CopyAction)
            # fall through (return False below) so Qt updates the drop indicator

        tree_vp = self._tree.viewport()
        if obj is tree_vp:
            if event.type() == QEvent.Type.MouseMove:
                idx = self._tree.indexAt(event.pos())
                if idx.isValid():
                    src = self._proxy.mapToSource(idx.siblingAtColumn(_COL_ICON))
                    self.hover_changed.emit(self._model.data(src, _ENTRY_ROLE))
                else:
                    self.hover_changed.emit(None)
            elif event.type() == QEvent.Type.Leave:
                self.hover_changed.emit(None)
        return super().eventFilter(obj, event)
