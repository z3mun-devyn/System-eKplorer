from __future__ import annotations

import json
from enum import Enum, auto

import strings
from backends.packages_backend import PackagesBackend
from backends.settings_backend import SettingsRepository
from backends.tags_backend import TagRepository
from models.package import Package
from models.tag import PackageEntry, Tag
from package_icon_resolver import PackageIconResolver
from package_query import PackageQuery, parse as _parse_query
from views.tag_editor_modal import DimOverlay, TagModal

from PyQt6.QtCore import (
    QAbstractTableModel,
    QDate,
    QEvent,
    QLocale,
    QModelIndex,
    QObject,
    QRect,
    QSize,
    QSortFilterProxyModel,
    QThread,
    QTimer,
    Qt,
    pyqtSignal,
)
from PyQt6.QtGui import (
    QColor, QFont, QFontDatabase, QFontMetrics, QIcon, QPainter, QPalette, QPixmap
)
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QTableView,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

# Column indices
_COL_ICON      = 0
_COL_NAME      = 1
_COL_TAGS      = 2
_COL_CATEGORY  = 3
_COL_SOURCE    = 4
_COL_VERSION   = 5
_COL_SIZE      = 6
_COL_INSTALLED = 7
_NUM_COLS      = 8

_ICON_COL_W = 36   # fixed pixel width of the icon column

# Toggleable column keys for settings persistence. _COL_NAME is always visible.
_VISIBILITY_KEYS: dict[int, str] = {
    _COL_ICON:      "icon",
    _COL_TAGS:      "tags",
    _COL_CATEGORY:  "category",
    _COL_SOURCE:    "source",
    _COL_VERSION:   "version",
    _COL_SIZE:      "size",
    _COL_INSTALLED: "installed",
}

_VISIBILITY_LABELS: dict[int, str] = {
    _COL_ICON:      strings.COL_ICON_MENU_LABEL,
    _COL_TAGS:      strings.COL_TAGS,
    _COL_CATEGORY:  strings.COL_CATEGORY,
    _COL_SOURCE:    strings.COL_SOURCE,
    _COL_VERSION:   strings.COL_VERSION,
    _COL_SIZE:      strings.COL_SIZE,
    _COL_INSTALLED: strings.COL_INSTALLED,
}

_SETTINGS_COL_VIS = "packages.column_visibility"

# Item data roles
_ENTRY_ROLE        = Qt.ItemDataRole.UserRole
_SKELETON_ROLE     = Qt.ItemDataRole.UserRole + 1
_SORT_ROLE         = Qt.ItemDataRole.UserRole + 2
_UNINSTALLING_ROLE = Qt.ItemDataRole.UserRole + 3
_UPGRADABLE_ROLE   = Qt.ItemDataRole.UserRole + 4

# Layout
_ROW_HEIGHT    = 32
_PILL_H        = 18
_PILL_H_PAD    = 10
_PILL_GAP      = 4
_MAX_PILLS     = 4
_DOTS_W        = 24

# Sidebar / loading
_SIDEBAR_W     = 200
_SKELETON_COUNT = 24

_ALL_CATEGORIES = ""
_ALL_TAGS       = ""

_HEADERS = [
    strings.COL_ICON,
    strings.COL_NAME,
    strings.COL_TAGS,
    strings.COL_CATEGORY,
    strings.COL_SOURCE,
    strings.COL_VERSION,
    strings.COL_SIZE,
    strings.COL_INSTALLED,
]


# ── Model ─────────────────────────────────────────────────────────────────────

class _PackageModel(QAbstractTableModel):
    def __init__(self) -> None:
        super().__init__()
        self._entries: list[PackageEntry] | None = None  # None = skeleton mode
        self._busy_names: frozenset[str] = frozenset()
        self._resolver = PackageIconResolver()
        self._update_map: dict[tuple[str, str], str] = {}  # (source, name) → new_version

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        if parent.isValid():
            return 0
        return _SKELETON_COUNT if self._entries is None else len(self._entries)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else _NUM_COLS

    def headerData(self, section: int, orientation: Qt.Orientation,
                   role: int = Qt.ItemDataRole.DisplayRole):
        if (orientation == Qt.Orientation.Horizontal
                and role == Qt.ItemDataRole.DisplayRole
                and 0 <= section < _NUM_COLS):
            return _HEADERS[section]
        return None

    def flags(self, index: QModelIndex) -> Qt.ItemFlag:
        return Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        row = index.row()
        col = index.column()

        # Skeleton mode
        if self._entries is None:
            return True if role == _SKELETON_ROLE else None

        if row >= len(self._entries):
            return None
        entry = self._entries[row]
        pkg = entry.package

        if role == _SKELETON_ROLE:
            return False
        if role == _ENTRY_ROLE:
            return entry
        if role == Qt.ItemDataRole.DecorationRole:
            if col == _COL_ICON:
                return self._resolver.resolve(pkg.name, pkg.source, pkg.section)
            return None
        if role == Qt.ItemDataRole.DisplayRole:
            if col == _COL_ICON:
                return None  # icon column shows only the decoration
            if col == _COL_NAME:
                return pkg.display_name if pkg.display_name else pkg.name
            if col == _COL_TAGS:
                return ""   # painted by delegate
            if col == _COL_CATEGORY:
                return strings.package_category(pkg.section)
            if col == _COL_SOURCE:
                return (strings.SOURCE_FLATPAK_LABEL
                        if pkg.source == "flatpak"
                        else strings.SOURCE_APT_LABEL)
            if col == _COL_VERSION:
                new_ver = self._update_map.get((pkg.source, pkg.name))
                if new_ver:
                    return f"{pkg.version} → {new_ver}"
                return pkg.version
            if col == _COL_SIZE:
                return ""   # painted by delegate
            if col == _COL_INSTALLED:
                if pkg.installed_on is None:
                    return ""
                dt = pkg.installed_on
                return QLocale().toString(
                    QDate(dt.year, dt.month, dt.day),
                    QLocale.FormatType.ShortFormat,
                )
            return None
        if role == Qt.ItemDataRole.FontRole:
            if col == _COL_NAME:
                f = QFont()
                f.setBold(True)
                return f
            return None
        if role == Qt.ItemDataRole.TextAlignmentRole:
            if col in (_COL_VERSION, _COL_SIZE):
                return Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            return Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        if role == _SORT_ROLE:
            if col == _COL_NAME:
                return (pkg.display_name if pkg.display_name else pkg.name).lower()
            if col == _COL_TAGS:
                return entry.tags[0].name.lower() if entry.tags else ""
            if col == _COL_CATEGORY:
                return strings.package_category(pkg.section).lower()
            if col == _COL_SOURCE:
                return pkg.source.lower()
            if col == _COL_VERSION:
                return pkg.version.lower()
            if col == _COL_SIZE:
                return pkg.installed_size_kb
            if col == _COL_INSTALLED:
                if pkg.installed_on is None:
                    return 0
                return int(pkg.installed_on.timestamp())
            return None
        if role == _UNINSTALLING_ROLE:
            return pkg.name in self._busy_names
        if role == _UPGRADABLE_ROLE:
            return bool(self._update_map.get((pkg.source, pkg.name)))
        return None

    def set_entries(self, entries: list[PackageEntry]) -> None:
        self.beginResetModel()
        self._entries = entries
        self.endResetModel()

    def reset_to_loading(self) -> None:
        self.beginResetModel()
        self._entries = None
        self._busy_names = frozenset()
        self.endResetModel()

    def set_busy(self, names: list[str] | None) -> None:
        prev = self._busy_names
        self._busy_names = frozenset(names) if names else frozenset()
        changed = prev | self._busy_names
        for row, entry in enumerate(self._entries or []):
            if entry.package.name in changed:
                self.dataChanged.emit(
                    self.index(row, 0), self.index(row, _NUM_COLS - 1)
                )

    def is_busy(self, pkg_name: str) -> bool:
        return pkg_name in self._busy_names

    def all_entries(self) -> list[PackageEntry]:
        return list(self._entries) if self._entries is not None else []

    def is_loading(self) -> bool:
        return self._entries is None

    def set_update_map(self, updates: dict[tuple[str, str], str]) -> None:
        self._update_map = updates
        if self._entries:
            self.dataChanged.emit(
                self.index(0, 0),
                self.index(len(self._entries) - 1, _NUM_COLS - 1),
            )

    def get_update_map(self) -> dict[tuple[str, str], str]:
        return self._update_map

    def refresh_tags(
        self, assignments: dict[tuple[str, str], list[Tag]]
    ) -> None:
        """Update tag assignments in-place and emit dataChanged for _COL_TAGS only.

        Preferred over set_entries() for tag saves: preserves scroll position,
        selection, and sort order while still triggering the proxy to re-filter
        rows whose tag-filter eligibility may have changed.
        """
        if not self._entries:
            return
        for entry in self._entries:
            entry.tags = assignments.get(
                (entry.package.source, entry.package.name), []
            )
        self.dataChanged.emit(
            self.index(0, _COL_TAGS),
            self.index(len(self._entries) - 1, _COL_TAGS),
        )


# ── Filter proxy ──────────────────────────────────────────────────────────────

class _PackageFilterProxy(QSortFilterProxyModel):
    def __init__(self) -> None:
        super().__init__()
        self._cat_filter: str = _ALL_CATEGORIES
        self._tag_filter: str = _ALL_TAGS
        self._query: PackageQuery = PackageQuery()
        self.setDynamicSortFilter(True)

    def set_filter(self, category: str = _ALL_CATEGORIES,
                   tag_name: str = _ALL_TAGS) -> None:
        self._cat_filter = category
        self._tag_filter = tag_name
        self.invalidateFilter()

    def set_query(self, query: PackageQuery) -> None:
        if query != self._query:
            self._query = query
            self.invalidateFilter()

    def current_category(self) -> str:
        return self._cat_filter

    def current_tag(self) -> str:
        return self._tag_filter

    def filterAcceptsRow(self, source_row: int, source_parent: QModelIndex) -> bool:
        idx = self.sourceModel().index(source_row, 0, source_parent)
        if idx.data(_SKELETON_ROLE):
            return True
        entry: PackageEntry | None = idx.data(_ENTRY_ROLE)
        if entry is None:
            return False
        pkg = entry.package
        q = self._query

        if q.name:
            display = (pkg.display_name or pkg.name).lower()
            if q.name not in display:
                return False
        if q.tag:
            if not any(q.tag in t.name.lower() for t in entry.tags):
                return False
        if q.category:
            if q.category not in strings.package_category(pkg.section).lower():
                return False
        if q.source:
            if q.source not in pkg.source.lower():
                return False
        if q.version:
            if q.version not in pkg.version.lower():
                return False
        if q.size:
            if q.size not in pkg.size_str.lower():
                return False

        if self._cat_filter:
            if strings.package_category(pkg.section) != self._cat_filter:
                return False
        if self._tag_filter:
            if not any(t.name == self._tag_filter for t in entry.tags):
                return False
        return True

    def lessThan(self, left: QModelIndex, right: QModelIndex) -> bool:
        lv = left.data(_SORT_ROLE)
        rv = right.data(_SORT_ROLE)
        if isinstance(lv, int) and isinstance(rv, int):
            return lv < rv
        return str(lv or "") < str(rv or "")


# ── Delegate ──────────────────────────────────────────────────────────────────

class _PackageTableDelegate(QStyledItemDelegate):
    def paint(self, painter: QPainter, option: QStyleOptionViewItem,
              index: QModelIndex) -> None:
        if index.data(_SKELETON_ROLE):
            self._paint_skeleton_cell(painter, option, index)
            return

        col = index.column()
        entry: PackageEntry | None = index.data(_ENTRY_ROLE)

        if index.data(_UNINSTALLING_ROLE) and col == _COL_NAME:
            opt = QStyleOptionViewItem(option)
            self.initStyleOption(opt, index)
            opt.text = ""
            super().paint(painter, opt, index)
            painter.save()
            f = painter.font()
            f.setItalic(True)
            painter.setFont(f)
            muted = QColor(option.palette.color(QPalette.ColorRole.Mid))
            painter.setPen(muted)
            painter.drawText(
                option.rect,
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                f"  {strings.STATUS_WORKING}",
            )
            painter.restore()
            return

        if col == _COL_ICON:
            opt = QStyleOptionViewItem(option)
            self.initStyleOption(opt, index)
            super().paint(painter, opt, index)
            if index.data(_UPGRADABLE_ROLE):
                self._paint_update_badge(painter, option.rect)
            return

        if col == _COL_TAGS:
            opt = QStyleOptionViewItem(option)
            self.initStyleOption(opt, index)
            opt.text = ""
            super().paint(painter, opt, index)
            if entry and entry.tags:
                self._paint_tag_pills(painter, entry.tags, option.rect, option.palette,
                                      option)
            return

        if col == _COL_SIZE:
            opt = QStyleOptionViewItem(option)
            self.initStyleOption(opt, index)
            opt.text = ""
            super().paint(painter, opt, index)
            if entry:
                self._paint_size_with_dots(painter, entry.package.size_str,
                                           option.rect, option.palette, option)
            return

        super().paint(painter, option, index)

    def _paint_skeleton_cell(self, painter: QPainter, option: QStyleOptionViewItem,
                             index: QModelIndex) -> None:
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        opt.text = ""
        super().paint(painter, opt, index)

        painter.save()
        skel = QColor(option.palette.color(QPalette.ColorRole.Mid))
        skel.setAlphaF(0.25)
        painter.setBrush(skel)
        painter.setPen(Qt.PenStyle.NoPen)
        rect = option.rect
        col = index.column()
        cx = rect.left() + 8
        cy = rect.top() + (rect.height() - 12) // 2
        col_widths = {
            _COL_ICON: 0,
            _COL_NAME: 160, _COL_TAGS: 90, _COL_CATEGORY: 80,
            _COL_SOURCE: 55, _COL_VERSION: 70, _COL_SIZE: 50,
            _COL_INSTALLED: 80,
        }
        w = min(col_widths.get(col, 60), rect.width() - 16)
        if w > 0:
            painter.drawRoundedRect(cx, cy, w, 12, 3, 3)
        painter.restore()

    def _paint_tag_pills(self, painter: QPainter, tags: list[Tag],
                         rect: QRect, palette: QPalette,
                         option: QStyleOptionViewItem) -> None:
        painter.save()
        small_font = painter.font()
        small_font.setPointSize(max(7, small_font.pointSize() - 1))
        painter.setFont(small_font)
        sfm = QFontMetrics(small_font)

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
                ov_bg = QColor(palette.color(QPalette.ColorRole.Mid))
                ov_bg.setAlphaF(0.3)
                painter.setBrush(ov_bg)
                painter.setPen(Qt.PenStyle.NoPen)
                painter.drawRoundedRect(ov_rect, _PILL_H // 2, _PILL_H // 2)
                ov_fg = QColor(palette.color(QPalette.ColorRole.WindowText))
                ov_fg.setAlphaF(0.7)
                painter.setPen(ov_fg)
                painter.drawText(ov_rect, Qt.AlignmentFlag.AlignCenter, ot)

        painter.restore()

    def _paint_size_with_dots(self, painter: QPainter, size_str: str,
                              rect: QRect, palette: QPalette,
                              option: QStyleOptionViewItem) -> None:
        painter.save()
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        fg = palette.color(
            QPalette.ColorRole.HighlightedText if selected
            else QPalette.ColorRole.WindowText
        )
        text_rect = QRect(rect.left(), rect.top(), rect.width() - _DOTS_W, rect.height())
        dots_zone = QRect(rect.right() - _DOTS_W, rect.top(), _DOTS_W, rect.height())

        painter.setPen(fg)
        painter.drawText(text_rect,
                         Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                         size_str)

        muted = QColor(palette.color(QPalette.ColorRole.Mid))
        muted.setAlphaF(0.5)
        painter.setPen(muted)
        painter.drawText(dots_zone, Qt.AlignmentFlag.AlignCenter, "⋯")
        painter.restore()

    def _paint_update_badge(self, painter: QPainter, rect: QRect) -> None:
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        bs = 10
        bx = rect.right() - bs - 1
        by = rect.top() + 1
        painter.setBrush(QColor("#27ae60"))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(bx, by, bs, bs)
        f = QFont()
        f.setPixelSize(8)
        f.setBold(True)
        painter.setFont(f)
        painter.setPen(QColor("#ffffff"))
        painter.drawText(QRect(bx, by, bs, bs), Qt.AlignmentFlag.AlignCenter, "↑")
        painter.restore()

    @staticmethod
    def dots_rect(size_cell_rect: QRect) -> QRect:
        return QRect(size_cell_rect.right() - _DOTS_W, size_cell_rect.top(),
                     _DOTS_W, size_cell_rect.height())


# ── Helpers ───────────────────────────────────────────────────────────────────

def _tag_icon(color_hex: str, size: int = 12) -> QIcon:
    """Return a small filled-circle icon in the tag's color for sidebar use."""
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setBrush(QColor(color_hex))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawEllipse(0, 0, size, size)
    painter.end()
    return QIcon(pixmap)


# ── Sidebar ────────────────────────────────────────────────────────────────────

class _SidebarWidget(QWidget):
    category_selected = pyqtSignal(str)   # "" = all
    tag_selected = pyqtSignal(str)        # "" = all (name-based)
    new_tag_requested = pyqtSignal()
    tag_delete_requested = pyqtSignal(str)  # tag name

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumWidth(140)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        outer.addWidget(scroll)

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 8, 0, 8)
        layout.setSpacing(0)

        cat_header = self._section_label(strings.SIDEBAR_CATEGORIES)
        layout.addWidget(cat_header)

        self._cat_list = QListWidget()
        self._cat_list.setFrameShape(QFrame.Shape.NoFrame)
        self._cat_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._cat_list.itemClicked.connect(self._on_cat_click)
        layout.addWidget(self._cat_list)

        tag_header = self._section_label(strings.SIDEBAR_TAGS)
        layout.addWidget(tag_header)

        self._tag_list = QListWidget()
        self._tag_list.setFrameShape(QFrame.Shape.NoFrame)
        self._tag_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._tag_list.itemClicked.connect(self._on_tag_click)
        self._tag_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._tag_list.customContextMenuRequested.connect(self._on_tag_context_menu)
        layout.addWidget(self._tag_list)

        self._flatpak_hint = QLabel(strings.FLATPAK_NOT_DETECTED)
        self._flatpak_hint.setStyleSheet(
            "QLabel { color: palette(mid); font-size: 9px; padding: 4px 12px 4px 12px; }"
        )
        self._flatpak_hint.setVisible(False)
        layout.addWidget(self._flatpak_hint)

        layout.addStretch()
        scroll.setWidget(container)

    @staticmethod
    def _section_label(text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet(
            "QLabel { color: palette(mid); font-size: 10px; font-weight: bold;"
            "  padding: 8px 12px 4px 12px; }"
        )
        return lbl

    def update_categories(self, categories: list[tuple[str, int]]) -> None:
        self._cat_list.clear()
        all_item = QListWidgetItem(f"  {strings.SIDEBAR_ALL}")
        all_item.setData(Qt.ItemDataRole.UserRole, _ALL_CATEGORIES)
        self._cat_list.addItem(all_item)
        self._cat_list.setCurrentItem(all_item)
        for name, count in sorted(categories):
            item = QListWidgetItem(f"  {name}  ({count})")
            item.setData(Qt.ItemDataRole.UserRole, name)
            self._cat_list.addItem(item)
        self._resize_list(self._cat_list)

    def set_flatpak_available(self, available: bool) -> None:
        self._flatpak_hint.setVisible(not available)

    def update_tags(self, tags: list[Tag], counts: dict[str, int]) -> None:
        self._tag_list.clear()
        all_item = QListWidgetItem(f"  {strings.SIDEBAR_ALL}")
        all_item.setData(Qt.ItemDataRole.UserRole, _ALL_TAGS)
        self._tag_list.addItem(all_item)
        for tag in tags:
            cnt = counts.get(tag.name, 0)
            item = QListWidgetItem(f"  {tag.name}  ({cnt})")
            item.setData(Qt.ItemDataRole.UserRole, tag.name)
            item.setIcon(_tag_icon(tag.color_hex))
            self._tag_list.addItem(item)
        new_item = QListWidgetItem(f"  {strings.SIDEBAR_NEW_TAG}")
        new_item.setData(Qt.ItemDataRole.UserRole, None)
        new_item.setForeground(
            self._tag_list.palette().color(QPalette.ColorRole.Highlight)
        )
        self._tag_list.addItem(new_item)
        self._resize_list(self._tag_list)

    @staticmethod
    def _resize_list(lw: QListWidget) -> None:
        total = sum(lw.sizeHintForRow(i) for i in range(lw.count()))
        lw.setFixedHeight(total + 4)

    def _on_cat_click(self, item: QListWidgetItem) -> None:
        self._tag_list.clearSelection()
        val = item.data(Qt.ItemDataRole.UserRole)
        self.category_selected.emit(val if val is not None else _ALL_CATEGORIES)

    def _on_tag_click(self, item: QListWidgetItem) -> None:
        val = item.data(Qt.ItemDataRole.UserRole)
        if val is None:
            self._tag_list.clearSelection()
            self.new_tag_requested.emit()
        else:
            self._cat_list.clearSelection()
            self.tag_selected.emit(val)

    def _on_tag_context_menu(self, pos) -> None:
        item = self._tag_list.itemAt(pos)
        if item is None:
            return
        tag_name = item.data(Qt.ItemDataRole.UserRole)
        # Only show delete for real tags (not "All" or "+ New tag")
        if not tag_name:
            return
        menu = QMenu(self)
        delete_act = menu.addAction(strings.ACTION_DELETE_TAG)
        chosen = menu.exec(self._tag_list.viewport().mapToGlobal(pos))
        if chosen is delete_act:
            self.tag_delete_requested.emit(tag_name)


# ── Package action ────────────────────────────────────────────────────────────

class _Action(Enum):
    REINSTALL       = auto()
    REINSTALL_RESET = auto()
    UNINSTALL_PURGE = auto()
    UNINSTALL_KEEP  = auto()
    UPDATE          = auto()


# ── Bottom-docked action panel ────────────────────────────────────────────────

class _ActionPanel(QWidget):
    """Persistent bottom panel for action progress; replaces the modal dialog.

    Hidden when no action is running.  Slides into view (simple show/hide)
    when _start_action() calls start_action().  Stays visible after the action
    completes so the user can read the log, then dismissed manually.
    """
    dismissed = pyqtSignal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 4, 8, 6)
        outer.setSpacing(4)

        # Thin top border
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFrameShadow(QFrame.Shadow.Plain)
        outer.addWidget(sep)

        # Top row: bold description + dismiss button (disabled while running)
        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        self._desc = QLabel(strings.STATUS_WORKING)
        f = self._desc.font()
        f.setBold(True)
        self._desc.setFont(f)
        top.addWidget(self._desc, stretch=1)
        self._dismiss_btn = QPushButton("Dismiss")
        self._dismiss_btn.setFixedWidth(80)
        self._dismiss_btn.setEnabled(False)
        self._dismiss_btn.clicked.connect(self._on_dismiss)
        top.addWidget(self._dismiss_btn)
        outer.addLayout(top)

        # Live log — monospace, read-only
        self._log = QPlainTextEdit()
        self._log.setReadOnly(True)
        self._log.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont))
        self._log.setMaximumBlockCount(2000)
        outer.addWidget(self._log, stretch=1)

        # Result / status line below the log
        self._result = QLabel("")
        outer.addWidget(self._result)

        self.setFixedHeight(200)
        self.setVisible(False)

    def start_action(self, description: str) -> None:
        self._desc.setText(description)
        self._log.clear()
        self._result.setText("")
        self._dismiss_btn.setEnabled(False)
        self.setVisible(True)

    def append_line(self, line: str) -> None:
        self._log.appendPlainText(line)

    def mark_complete(self, message: str) -> None:
        self._result.setText(message)
        self._dismiss_btn.setEnabled(True)

    def mark_failed(self, details: str) -> None:
        self._result.setText("Action failed")
        if details:
            self._log.appendPlainText("")
            self._log.appendPlainText(details)
        self._dismiss_btn.setEnabled(True)

    def _on_dismiss(self) -> None:
        self.setVisible(False)
        self._log.clear()
        self._result.setText("")
        self.dismissed.emit()


# ── Batch confirmation dialog ─────────────────────────────────────────────────

class _BatchConfirmDialog(QDialog):
    def __init__(self, action_label: str, pkg_names: list[str],
                 parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(strings.CONFIRM_BATCH_QUESTION.format(
            action=action_label, n=len(pkg_names)))
        self.setMinimumWidth(320)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        question = QLabel(strings.CONFIRM_BATCH_QUESTION.format(
            action=action_label, n=len(pkg_names)))
        question.setWordWrap(True)
        layout.addWidget(question)

        pkg_list = QListWidget()
        pkg_list.setMaximumHeight(200)
        pkg_list.setFrameShape(QFrame.Shape.StyledPanel)
        for name in sorted(pkg_names):
            pkg_list.addItem(name)
        layout.addWidget(pkg_list)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Yes | QDialogButtonBox.StandardButton.No)
        buttons.button(QDialogButtonBox.StandardButton.No).setDefault(True)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)


# ── Background loaders ────────────────────────────────────────────────────────

class _BackendLoader(QObject):
    """Generic single-backend async loader — wraps any callable returning list[Package]."""
    packages_ready = pyqtSignal(list)
    load_failed    = pyqtSignal(str)

    def __init__(self, fn) -> None:
        super().__init__()
        self._fn = fn

    def run(self) -> None:
        try:
            pkgs = self._fn()
            print(f"[loader] {self._fn.__self__.__class__.__name__}: "
                  f"{len(pkgs)} packages")
            self.packages_ready.emit(pkgs)
        except Exception as exc:
            print(f"[loader] {getattr(self._fn, '__self__', self._fn)}: failed: {exc}")
            self.load_failed.emit(str(exc))
        finally:
            # Quit the thread's event loop from within the thread — reliable
            # and avoids a queued cross-thread connection for the same purpose.
            QThread.currentThread().quit()


class _PackageActionWorker(QObject):
    succeeded   = pyqtSignal(object, str)  # list[str] pkg_names, action_label
    failed      = pyqtSignal(object, str)  # list[str] pkg_names, stderr
    cancelled   = pyqtSignal(object)       # list[str] pkg_names (pkexec auth rejected)
    output_line = pyqtSignal(str)          # one line from subprocess stdout

    def __init__(self, pkg_entries: list[tuple[str, str]], action: _Action,
                 action_label: str) -> None:
        super().__init__()
        self._pkg_entries = pkg_entries   # [(name, source), ...]
        self._action = action
        self._action_label = action_label

    def run(self) -> None:
        from backends.package_action_backend import PackageActionBackend
        backend = PackageActionBackend()

        apt_names     = [n for n, s in self._pkg_entries if s == "apt"]
        flatpak_names = [n for n, s in self._pkg_entries if s == "flatpak"]
        all_names     = [n for n, _ in self._pkg_entries]
        line_cb       = self.output_line.emit  # cross-thread queued connection

        results = []
        if apt_names:
            results.append(self._run_apt(backend, apt_names, line_cb))
        if flatpak_names:
            results.append(self._run_flatpak(backend, flatpak_names, line_cb))

        if any(r.cancelled for r in results):
            self.cancelled.emit(all_names)
        elif any(not r.success for r in results):
            stderr = "\n".join(r.stderr for r in results if not r.success)
            self.failed.emit(all_names, stderr)
        else:
            self.succeeded.emit(all_names, self._action_label)

    def _run_apt(self, backend, names: list[str], line_cb=None):
        if len(names) == 1:
            n = names[0]
            if self._action == _Action.REINSTALL:
                return backend.reinstall(n, line_cb=line_cb)
            if self._action == _Action.REINSTALL_RESET:
                return backend.reinstall_reset(n, line_cb=line_cb)
            if self._action == _Action.UNINSTALL_PURGE:
                return backend.uninstall(n, purge=True, line_cb=line_cb)
            if self._action == _Action.UNINSTALL_KEEP:
                return backend.uninstall(n, purge=False, line_cb=line_cb)
            if self._action == _Action.UPDATE:
                return backend.update_apt(n, line_cb=line_cb)
        if self._action == _Action.REINSTALL:
            return backend.reinstall_batch(names, line_cb=line_cb)
        if self._action == _Action.REINSTALL_RESET:
            return backend.reinstall_reset_batch(names, line_cb=line_cb)
        if self._action == _Action.UNINSTALL_PURGE:
            return backend.uninstall_batch(names, purge=True, line_cb=line_cb)
        if self._action == _Action.UNINSTALL_KEEP:
            return backend.uninstall_batch(names, purge=False, line_cb=line_cb)
        return backend.update_all_apt(names, line_cb=line_cb)

    def _run_flatpak(self, backend, ids: list[str], line_cb=None):
        if len(ids) == 1:
            i = ids[0]
            if self._action == _Action.REINSTALL:
                return backend.reinstall_flatpak(i, line_cb=line_cb)
            if self._action == _Action.REINSTALL_RESET:
                return backend.reinstall_reset_flatpak(i, line_cb=line_cb)
            if self._action == _Action.UNINSTALL_PURGE:
                return backend.uninstall_flatpak(i, delete_data=True, line_cb=line_cb)
            if self._action == _Action.UNINSTALL_KEEP:
                return backend.uninstall_flatpak(i, delete_data=False, line_cb=line_cb)
            if self._action == _Action.UPDATE:
                return backend.update_flatpak(i, line_cb=line_cb)
        if self._action == _Action.REINSTALL:
            return backend.reinstall_flatpak_batch(ids, line_cb=line_cb)
        if self._action == _Action.REINSTALL_RESET:
            return backend.reinstall_reset_flatpak_batch(ids, line_cb=line_cb)
        if self._action == _Action.UNINSTALL_PURGE:
            return backend.uninstall_flatpak_batch(ids, delete_data=True, line_cb=line_cb)
        if self._action == _Action.UNINSTALL_KEEP:
            return backend.uninstall_flatpak_batch(ids, delete_data=False, line_cb=line_cb)
        return backend.update_all_flatpak(ids, line_cb=line_cb)


# ── Version install worker ────────────────────────────────────────────────────

class _VersionInstallWorker(QObject):
    succeeded   = pyqtSignal(str)        # pkg_name
    failed      = pyqtSignal(str, str)   # pkg_name, stderr
    cancelled   = pyqtSignal(str)        # pkg_name
    output_line = pyqtSignal(str)

    def __init__(self, pkg: Package, key: str) -> None:
        super().__init__()
        self._pkg = pkg
        self._key = key  # version string (apt) or commit hash (flatpak)

    def run(self) -> None:
        from backends.package_action_backend import PackageActionBackend
        backend = PackageActionBackend()
        pkg = self._pkg
        line_cb = self.output_line.emit
        if pkg.source == "flatpak":
            result = backend.install_flatpak_commit(pkg.name, self._key, line_cb)
        else:
            result = backend.install_apt_version(pkg.name, self._key, line_cb)
        if result.cancelled:
            self.cancelled.emit(pkg.name)
        elif not result.success:
            self.failed.emit(pkg.name, result.stderr)
        else:
            self.succeeded.emit(pkg.name)
        QThread.currentThread().quit()


# ── Location resolver worker ──────────────────────────────────────────────────

class _LocationWorker(QObject):
    """Async wrapper for resolve_location(); runs on a QThread."""
    resolved = pyqtSignal(str)   # install directory path
    failed   = pyqtSignal(str)   # package name (for toast)

    def __init__(self, pkg_name: str, source: str) -> None:
        super().__init__()
        self._pkg_name = pkg_name
        self._source   = source

    def run(self) -> None:
        from package_location_resolver import resolve_location
        path = resolve_location(self._pkg_name, self._source)
        if path:
            self.resolved.emit(path)
        else:
            self.failed.emit(self._pkg_name)
        QThread.currentThread().quit()


# ── Update check worker ───────────────────────────────────────────────────────

class _UpdateCheckWorker(QObject):
    updates_found = pyqtSignal(dict)   # {(source, name): new_version}
    check_failed  = pyqtSignal(str)
    output_line   = pyqtSignal(str)    # streaming lines from pkexec apt update

    def run(self) -> None:
        from backends.update_backend import UpdateBackend
        try:
            backend = UpdateBackend()
            # Refresh the apt index first (triggers pkexec password prompt).
            # We continue even if this fails so stale-cache results are shown.
            backend.run_apt_update(line_cb=self.output_line.emit)
            result: dict[tuple[str, str], str] = {}
            for name, version in backend.list_apt_upgradable():
                result[("apt", name)] = version
            for app_id, version in backend.list_flatpak_updates():
                result[("flatpak", app_id)] = version
            self.updates_found.emit(result)
        except Exception as exc:
            self.check_failed.emit(str(exc))
        finally:
            QThread.currentThread().quit()


# ── View ──────────────────────────────────────────────────────────────────────

class PackagesView(QWidget):
    open_location_requested = pyqtSignal(str)  # emitted with resolved path

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._repo = TagRepository()
        self._settings = SettingsRepository()
        self._pending_count: int = 0
        self._loaded_packages: list = []
        self._loc_workers: list[_LocationWorker] = []
        self._loc_threads: list[QThread] = []
        self._update_check_thread: QThread | None = None
        self._update_check_worker: _UpdateCheckWorker | None = None
        self._reload_on_dismiss: bool = False

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setHandleWidth(1)

        # Sidebar
        self._sidebar = _SidebarWidget()
        self._sidebar.setStyleSheet(
            "_SidebarWidget { background: palette(alternateBase); }"
        )
        self._sidebar.category_selected.connect(self._on_category_filter)
        self._sidebar.tag_selected.connect(self._on_tag_filter)
        self._sidebar.new_tag_requested.connect(self._open_tag_modal_create)
        self._sidebar.tag_delete_requested.connect(self._on_delete_tag_requested)
        splitter.addWidget(self._sidebar)

        # Right panel: search bar + status label + table
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)

        # ── Search bar ────────────────────────────────────────────────────────
        search_bar = QWidget()
        search_layout = QHBoxLayout(search_bar)
        search_layout.setContentsMargins(6, 6, 6, 4)
        search_layout.setSpacing(4)

        self._filter_btn = QToolButton()
        self._filter_btn.setText("≡")
        self._filter_btn.setToolTip(strings.SEARCH_FILTER_TOOLTIP)
        self._filter_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        filter_menu = QMenu(self._filter_btn)
        _FIELD_ITEMS = [
            (strings.SEARCH_FIELD_TAGGED,   strings.QUERY_TOKEN_TAGGED),
            (strings.SEARCH_FIELD_CATEGORY, strings.QUERY_TOKEN_CATEGORY),
            (strings.SEARCH_FIELD_SOURCE,   strings.QUERY_TOKEN_SOURCE),
            (strings.SEARCH_FIELD_VERSION,  strings.QUERY_TOKEN_VERSION),
            (strings.SEARCH_FIELD_SIZE,     strings.QUERY_TOKEN_SIZE),
        ]
        for label, token in _FIELD_ITEMS:
            act = filter_menu.addAction(label)
            act.triggered.connect(
                lambda _checked, t=token: self._insert_field_token(t))
        self._filter_btn.setMenu(filter_menu)
        search_layout.addWidget(self._filter_btn)

        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText(strings.SEARCH_PLACEHOLDER)
        self._search_input.setClearButtonEnabled(True)
        search_layout.addWidget(self._search_input, stretch=1)

        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(120)
        self._search_timer.timeout.connect(self._apply_search)
        self._search_input.textChanged.connect(
            lambda _text: self._search_timer.start())

        right_layout.addWidget(search_bar)

        # ── Update toolbar ────────────────────────────────────────────────────
        update_bar = QWidget()
        update_layout = QHBoxLayout(update_bar)
        update_layout.setContentsMargins(6, 2, 6, 2)
        update_layout.setSpacing(6)

        self._check_updates_btn = QPushButton(strings.ACTION_CHECK_UPDATES)
        self._check_updates_btn.setFixedHeight(24)
        self._check_updates_btn.clicked.connect(self._start_update_check)
        update_layout.addWidget(self._check_updates_btn)

        self._update_all_btn = QPushButton(strings.ACTION_UPDATE_ALL)
        self._update_all_btn.setFixedHeight(24)
        self._update_all_btn.setEnabled(False)
        self._update_all_btn.clicked.connect(self._start_update_all)
        update_layout.addWidget(self._update_all_btn)

        self._updates_label = QLabel("")
        update_layout.addWidget(self._updates_label)
        update_layout.addStretch()

        right_layout.addWidget(update_bar)
        # ─────────────────────────────────────────────────────────────────────

        self._status = QLabel(strings.PACKAGES_LOADING)
        self._status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._status.setStyleSheet("QLabel { color: palette(mid); padding: 8px; }")
        self._status.setVisible(False)
        right_layout.addWidget(self._status)

        self._model = _PackageModel()
        self._proxy = _PackageFilterProxy()
        self._proxy.setSourceModel(self._model)

        self._delegate = _PackageTableDelegate()

        self._table = QTableView()
        self._table.setModel(self._proxy)
        self._table.setItemDelegate(self._delegate)
        self._table.setIconSize(QSize(20, 20))
        self._table.setSortingEnabled(True)
        self._table.setShowGrid(False)
        self._table.setAlternatingRowColors(True)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self._table.setFrameShape(QFrame.Shape.NoFrame)
        self._table.setMouseTracking(True)
        self._table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._table.customContextMenuRequested.connect(self._show_context_menu)
        self._table.viewport().installEventFilter(self)

        vhdr = self._table.verticalHeader()
        vhdr.setVisible(False)
        vhdr.setDefaultSectionSize(_ROW_HEIGHT)
        vhdr.setSectionResizeMode(QHeaderView.ResizeMode.Fixed)

        hhdr = self._table.horizontalHeader()
        hhdr.setStretchLastSection(False)
        hhdr.setSectionResizeMode(_COL_ICON,      QHeaderView.ResizeMode.Fixed)
        hhdr.setSectionResizeMode(_COL_NAME,      QHeaderView.ResizeMode.Stretch)
        for col in range(_NUM_COLS):
            if col not in (_COL_ICON, _COL_NAME):
                hhdr.setSectionResizeMode(col, QHeaderView.ResizeMode.Interactive)
        hhdr.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        hhdr.customContextMenuRequested.connect(self._show_column_menu)

        # Default widths for interactive columns (Name fills remaining space via Stretch)
        self._table.setColumnWidth(_COL_ICON,      _ICON_COL_W)
        self._table.setColumnWidth(_COL_TAGS,      120)
        self._table.setColumnWidth(_COL_CATEGORY,  110)
        self._table.setColumnWidth(_COL_SOURCE,     70)
        self._table.setColumnWidth(_COL_VERSION,    90)
        self._table.setColumnWidth(_COL_SIZE,       80)
        self._table.setColumnWidth(_COL_INSTALLED, 110)

        # Restore saved column visibility before first paint (no flash)
        self._restore_column_visibility()

        # Default sort: Name ascending
        self._proxy.sort(_COL_NAME, Qt.SortOrder.AscendingOrder)

        right_layout.addWidget(self._table, stretch=1)

        self._action_panel = _ActionPanel()
        self._action_panel.dismissed.connect(self._on_panel_dismissed)
        right_layout.addWidget(self._action_panel)

        splitter.addWidget(right)
        splitter.setSizes([_SIDEBAR_W, 600])
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)

        outer.addWidget(splitter)

        # Overlay + modal (not in layout — positioned manually)
        self._dim = DimOverlay(self)
        self._dim.clicked.connect(self._close_modal)

        self._modal = TagModal(self)
        self._modal.saved.connect(self._on_tags_saved)

        from backends.flatpak_backend import FlatpakBackend
        self._sidebar.set_flatpak_available(FlatpakBackend.is_available())

        self._start_load()

    # ── Event filter (three-dot left-click on Size column) ───────────────────

    def eventFilter(self, obj: QObject, event) -> bool:
        if (obj is self._table.viewport()
                and event.type() == QEvent.Type.MouseButtonPress
                and event.button() == Qt.MouseButton.LeftButton):
            pos = event.pos()
            proxy_index = self._table.indexAt(pos)
            if proxy_index.isValid():
                size_index = proxy_index.siblingAtColumn(_COL_SIZE)
                cell_rect = self._table.visualRect(size_index)
                if _PackageTableDelegate.dots_rect(cell_rect).contains(pos):
                    clicked_entry = self._entry_from_proxy(proxy_index)
                    if clicked_entry is not None:
                        entries = self._entries_for_action(clicked_entry)
                        self._show_menu_for_entries(
                            entries, self._table.viewport().mapToGlobal(pos)
                        )
                        return True
        return super().eventFilter(obj, event)

    # ── Sizing ────────────────────────────────────────────────────────────────

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._dim.setGeometry(self.rect())
        if self._modal.isVisible():
            self._position_modal()

    def _position_modal(self) -> None:
        mw = self._modal.width()
        mh = self._modal.height()
        mx = (self.width() - mw) // 2
        my = max(20, (self.height() - mh) // 2)
        self._modal.move(mx, my)

    # ── Loading ───────────────────────────────────────────────────────────────

    def _start_load(self) -> None:
        from backends.flatpak_backend import FlatpakBackend
        self._pending_count = 2
        self._loaded_packages = []
        self._load_had_error = False
        # Instance-variable lists keep strong Python references to both the
        # thread and the worker.  PyQt6 uses *weak* refs for QObject slot
        # connections (to avoid cycles), so a worker that is only referenced
        # by a local loop variable is eligible for GC before the thread
        # starts — causing started → worker.run to fire into nothing and
        # the pending counter to never reach zero.
        self._loader_threads: list[QThread] = []
        self._loader_workers: list[_BackendLoader] = []

        for fn in (PackagesBackend().list_installed,
                   FlatpakBackend().list_installed):
            thread = QThread(parent=self)
            worker = _BackendLoader(fn)
            self._loader_threads.append(thread)   # hold strong ref
            self._loader_workers.append(worker)   # hold strong ref
            worker.moveToThread(thread)
            thread.started.connect(worker.run)
            worker.packages_ready.connect(self._on_source_ready)
            worker.load_failed.connect(self._on_source_failed)
            # run() calls QThread.currentThread().quit() in its finally block,
            # so no separate quit connection is needed here.
            thread.finished.connect(worker.deleteLater)
            thread.start()

    def _on_source_ready(self, packages: list) -> None:
        print(f"[packages] source ready: {len(packages)} packages "
              f"(pending {self._pending_count} → {self._pending_count - 1})")
        self._loaded_packages.extend(packages)
        self._pending_count -= 1
        if self._pending_count == 0:
            self._finalize_load()

    def _on_source_failed(self, error: str) -> None:
        print(f"[packages] source failed: {error!r} "
              f"(pending {self._pending_count} → {self._pending_count - 1})")
        self._load_had_error = True
        self._pending_count -= 1
        if self._pending_count == 0:
            self._finalize_load()

    def _finalize_load(self) -> None:
        print(f"[packages] finalize: {len(self._loaded_packages)} total packages")
        packages = self._loaded_packages
        assignments = self._repo.load_all_assignments()
        entries = [
            PackageEntry(
                package=pkg,
                tags=assignments.get((pkg.source, pkg.name), []),
            )
            for pkg in packages
        ]
        self._model.set_entries(entries)

        if entries:
            self._status.setVisible(False)
            self._refresh_sidebar()
        else:
            self._status.setText(strings.PACKAGES_EMPTY)
            self._status.setVisible(True)

    # ── Sidebar refresh ───────────────────────────────────────────────────────

    def _refresh_sidebar(self) -> None:
        entries = self._model.all_entries()
        cat_counts: dict[str, int] = {}
        for e in entries:
            cat = strings.package_category(e.package.section)
            cat_counts[cat] = cat_counts.get(cat, 0) + 1
        self._sidebar.update_categories(list(cat_counts.items()))
        all_tags = self._repo.all_tags()
        counts = self._repo.tag_counts()
        self._sidebar.update_tags(all_tags, counts)

    # ── Search bar ────────────────────────────────────────────────────────────

    def _apply_search(self) -> None:
        query = _parse_query(self._search_input.text())
        self._proxy.set_query(query)

    def _insert_field_token(self, token: str) -> None:
        current = self._search_input.text()
        if current and not current.endswith(" "):
            current += " "
        self._search_input.setText(current + token + ":")
        self._search_input.setFocus()
        self._search_input.setCursorPosition(len(self._search_input.text()))

    # ── Column visibility ─────────────────────────────────────────────────────

    def _show_column_menu(self, pos) -> None:
        hhdr = self._table.horizontalHeader()
        menu = QMenu(self)
        # Name — anchor column, always visible
        name_act = menu.addAction(strings.COL_NAME)
        name_act.setCheckable(True)
        name_act.setChecked(True)
        name_act.setEnabled(False)
        menu.addSeparator()
        for col in sorted(_VISIBILITY_KEYS.keys()):
            label = _VISIBILITY_LABELS[col]
            act = menu.addAction(label)
            act.setCheckable(True)
            act.setChecked(not self._table.isColumnHidden(col))
            act.triggered.connect(
                lambda checked, c=col, k=_VISIBILITY_KEYS[col]:
                    self._toggle_column(c, k, checked)
            )
        menu.exec(hhdr.mapToGlobal(pos))

    def _toggle_column(self, col: int, key: str, visible: bool) -> None:
        self._table.setColumnHidden(col, not visible)
        self._persist_column_visibility()

    def _persist_column_visibility(self) -> None:
        vis_map = {
            _VISIBILITY_KEYS[col]: not self._table.isColumnHidden(col)
            for col in _VISIBILITY_KEYS
        }
        self._settings.set(_SETTINGS_COL_VIS, json.dumps(vis_map))

    def _restore_column_visibility(self) -> None:
        raw = self._settings.get(_SETTINGS_COL_VIS)
        if not raw:
            return
        try:
            vis_map = json.loads(raw)
        except Exception:
            return
        for col, key in _VISIBILITY_KEYS.items():
            if key in vis_map:
                self._table.setColumnHidden(col, not vis_map[key])

    # ── Filtering — category and tag are mutually exclusive ───────────────────

    def _on_category_filter(self, category: str) -> None:
        self._proxy.set_filter(category=category, tag_name=_ALL_TAGS)

    def _on_tag_filter(self, tag_name: str) -> None:
        current = self._proxy.current_tag()
        new_tag = _ALL_TAGS if tag_name == current else tag_name
        self._proxy.set_filter(category=_ALL_CATEGORIES, tag_name=new_tag)

    # ── Context menu ──────────────────────────────────────────────────────────

    def _show_context_menu(self, pos) -> None:
        proxy_index = self._table.indexAt(pos)
        if not proxy_index.isValid():
            return
        clicked_entry = self._entry_from_proxy(proxy_index)
        if clicked_entry is None:
            return
        entries = self._entries_for_action(clicked_entry)
        self._show_menu_for_entries(entries, self._table.viewport().mapToGlobal(pos))

    def _show_menu_for_entries(self, entries: list[PackageEntry], global_pos) -> None:
        entries = [e for e in entries if not self._model.is_busy(e.package.name)]
        if not entries:
            return
        n = len(entries)
        menu = QMenu(self)
        update_act = None
        if n == 1:
            name = entries[0].package.name
            pkg = entries[0].package
            new_ver = self._model.get_update_map().get((pkg.source, pkg.name))
            assign_act         = menu.addAction(strings.ACTION_ASSIGN_TAGS)
            loc_act            = menu.addAction(strings.ACTION_OPEN_INSTALL_LOCATION)
            history_act        = menu.addAction(strings.ACTION_VERSION_HISTORY)
            if new_ver:
                menu.addSeparator()
                update_act = menu.addAction(
                    f"{strings.ACTION_UPDATE} {name} ({new_ver})")
            menu.addSeparator()
            reinstall_act      = menu.addAction(f"{strings.ACTION_REINSTALL} {name}")
            reinstall_rst_act  = menu.addAction(f"{strings.ACTION_REINSTALL_RESET} {name}")
            menu.addSeparator()
            uninstall_act      = menu.addAction(f"{strings.ACTION_UNINSTALL} {name}")
            uninstall_keep_act = menu.addAction(f"{strings.ACTION_UNINSTALL_KEEP} {name}")
        else:
            assign_act         = menu.addAction(strings.ACTION_ASSIGN_TAGS_N.format(n=n))
            loc_act            = menu.addAction(strings.ACTION_OPEN_INSTALL_LOCATION)
            loc_act.setEnabled(False)  # single-target action only
            history_act        = None
            menu.addSeparator()
            reinstall_act      = menu.addAction(strings.ACTION_REINSTALL_N.format(n=n))
            reinstall_rst_act  = menu.addAction(strings.ACTION_REINSTALL_RESET_N.format(n=n))
            menu.addSeparator()
            uninstall_act      = menu.addAction(strings.ACTION_UNINSTALL_N.format(n=n))
            uninstall_keep_act = menu.addAction(strings.ACTION_UNINSTALL_KEEP_N.format(n=n))
        chosen = menu.exec(global_pos)
        if chosen is assign_act:
            self._open_tag_modal_for_entries(entries)
        elif chosen is loc_act and n == 1:
            self._open_install_location(entries[0])
        elif history_act is not None and chosen is history_act:
            self._open_version_history(entries[0])
        elif update_act is not None and chosen is update_act:
            self._start_action(entries, _Action.UPDATE)
        elif chosen is reinstall_act:
            self._start_action(entries, _Action.REINSTALL)
        elif chosen is reinstall_rst_act:
            self._start_action(entries, _Action.REINSTALL_RESET)
        elif chosen is uninstall_act:
            self._start_action(entries, _Action.UNINSTALL_PURGE)
        elif chosen is uninstall_keep_act:
            self._start_action(entries, _Action.UNINSTALL_KEEP)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _entry_from_proxy(self, proxy_index: QModelIndex) -> PackageEntry | None:
        source_index = self._proxy.mapToSource(proxy_index)
        return self._model.index(source_index.row(), 0).data(_ENTRY_ROLE)

    def _get_selected_entries(self) -> list[PackageEntry]:
        """Return unique entries for all selected rows (one per package name)."""
        seen: set[str] = set()
        result: list[PackageEntry] = []
        for proxy_index in self._table.selectionModel().selectedRows():
            entry = self._entry_from_proxy(proxy_index)
            if entry is not None and entry.package.name not in seen:
                seen.add(entry.package.name)
                result.append(entry)
        return result

    def _entries_for_action(self, clicked_entry: PackageEntry) -> list[PackageEntry]:
        """If clicked row is in the current selection use the whole selection; else single."""
        selected = self._get_selected_entries()
        if any(e.package.name == clicked_entry.package.name for e in selected):
            return selected
        return [clicked_entry]

    # ── Tag modal ─────────────────────────────────────────────────────────────

    def _open_tag_modal_for_entries(self, entries: list[PackageEntry]) -> None:
        self._dim.setVisible(True)
        self._dim.raise_()
        if len(entries) == 1:
            self._modal.open_for(entries[0])
        else:
            self._modal.open_for_batch(entries)
        self._modal.raise_()
        self._position_modal()

    def _open_tag_modal_create(self) -> None:
        self._dim.setVisible(True)
        self._dim.raise_()
        self._modal.open_for(None)
        self._modal.raise_()
        self._position_modal()

    def _close_modal(self) -> None:
        self._modal.close_modal()
        self._dim.setVisible(False)

    def _on_tags_saved(self) -> None:
        self._dim.setVisible(False)
        assignments = self._repo.load_all_assignments()
        self._model.refresh_tags(assignments)
        self._refresh_sidebar()

    def _show_toast(self, message: str, duration_ms: int = 3000) -> None:
        self._status.setText(message)
        self._status.setVisible(True)
        QTimer.singleShot(duration_ms, lambda: self._status.setVisible(False))

    def _open_install_location(self, entry: PackageEntry) -> None:
        worker = _LocationWorker(entry.package.name, entry.package.source)
        thread = QThread()
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.resolved.connect(self.open_location_requested)
        worker.resolved.connect(thread.quit)
        worker.failed.connect(
            lambda name: self._show_toast(
                strings.NOTICE_LOCATION_NOT_FOUND.format(name=name)))
        worker.failed.connect(thread.quit)
        thread.finished.connect(thread.deleteLater)
        # Keep strong refs so PyQt6 doesn't GC the worker before the thread fires
        self._loc_workers.append(worker)
        self._loc_threads.append(thread)
        thread.finished.connect(
            lambda: (self._loc_workers.remove(worker) if worker in self._loc_workers else None))
        thread.finished.connect(
            lambda: (self._loc_threads.remove(thread) if thread in self._loc_threads else None))
        thread.start()

    def _open_version_history(self, entry: PackageEntry) -> None:
        from views.version_history_dialog import VersionHistoryDialog
        dlg = VersionHistoryDialog(entry.package, parent=self)
        dlg.install_requested.connect(self._on_version_install_requested)
        dlg.exec()

    def _on_version_install_requested(self, pkg: Package, key: str) -> None:
        """Handle install request from VersionHistoryDialog."""
        from backends.package_action_backend import PackageActionBackend
        from models.tag import PackageEntry as PE
        # Find the matching PackageEntry in the model
        for e in self._model.all_entries():
            if e.package.name == pkg.name and e.package.source == pkg.source:
                self._start_version_install(e, key)
                return

    def _start_version_install(self, entry: PackageEntry, key: str) -> None:
        """Run install_apt_version or install_flatpak_commit via the action panel."""
        pkg = entry.package
        display = pkg.display_name if pkg.display_name else pkg.name
        desc = f"{strings.VERSION_HISTORY_INSTALL}: {display} → {key[:12]}"
        self._model.set_busy([pkg.name])
        self._action_panel.start_action(desc)
        self._set_action_buttons_enabled(False)

        self._action_thread = QThread(parent=self)
        self._action_worker = _VersionInstallWorker(pkg, key)
        self._action_worker.moveToThread(self._action_thread)
        self._action_thread.started.connect(self._action_worker.run)
        self._action_worker.output_line.connect(self._action_panel.append_line)
        self._action_worker.succeeded.connect(self._on_version_install_success)
        self._action_worker.failed.connect(self._on_version_install_failed)
        self._action_worker.cancelled.connect(self._on_version_install_cancelled)
        self._action_worker.succeeded.connect(self._action_thread.quit)
        self._action_worker.failed.connect(self._action_thread.quit)
        self._action_worker.cancelled.connect(self._action_thread.quit)
        self._action_thread.finished.connect(self._action_worker.deleteLater)
        self._action_thread.start()

    def _on_version_install_success(self, pkg_name: str) -> None:
        msg = strings.NOTICE_ACTION_COMPLETE.format(
            action=strings.VERSION_HISTORY_INSTALL, name=pkg_name)
        self._action_panel.mark_complete(msg)
        self._set_action_buttons_enabled(True)
        self._reload_on_dismiss = True

    def _on_version_install_failed(self, pkg_name: str, stderr: str) -> None:
        self._model.set_busy(None)
        self._action_panel.mark_failed(stderr)
        self._set_action_buttons_enabled(True)
        self._reload_on_dismiss = False

    def _on_version_install_cancelled(self, pkg_name: str) -> None:
        self._model.set_busy(None)
        self._action_panel.mark_complete(strings.NOTICE_ACTION_CANCELLED)
        self._set_action_buttons_enabled(True)
        self._reload_on_dismiss = False

    def _on_delete_tag_requested(self, tag_name: str) -> None:
        count = self._repo.assigned_count(tag_name)
        msg = QMessageBox(self)
        msg.setWindowTitle(strings.TAG_DELETE_CONFIRM_TITLE.format(name=tag_name))
        msg.setText(strings.TAG_DELETE_CONFIRM_TITLE.format(name=tag_name))
        msg.setInformativeText(
            strings.TAG_DELETE_CONFIRM_BODY.format(n=count))
        msg.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        msg.button(QMessageBox.StandardButton.Yes).setText(strings.TAG_DELETE_YES)
        msg.button(QMessageBox.StandardButton.No).setText(strings.TAG_DELETE_NO)
        msg.setDefaultButton(QMessageBox.StandardButton.No)
        if msg.exec() != QMessageBox.StandardButton.Yes:
            return
        self._repo.delete_tag(tag_name)
        # If the deleted tag was the active filter, reset to All
        if self._proxy.current_tag() == tag_name:
            self._proxy.set_filter(category=_ALL_CATEGORIES, tag_name=_ALL_TAGS)
        # Reload in-memory tag assignments and refresh sidebar
        assignments = self._repo.load_all_assignments()
        entries = self._model.all_entries()
        updated = [
            PackageEntry(
                package=e.package,
                tags=assignments.get((e.package.source, e.package.name), []),
            )
            for e in entries
        ]
        self._model.set_entries(updated)
        self._refresh_sidebar()

    # ── Package actions (reinstall / uninstall) ───────────────────────────────

    _ACTION_CONFIRM: dict[_Action, tuple[str, str]] = {
        _Action.REINSTALL:       (strings.CONFIRM_REINSTALL_QUESTION,
                                  strings.CONFIRM_REINSTALL_SUBTITLE),
        _Action.REINSTALL_RESET: (strings.CONFIRM_REINSTALL_RESET_QUESTION,
                                  strings.CONFIRM_REINSTALL_RESET_SUBTITLE),
        _Action.UNINSTALL_PURGE: (strings.CONFIRM_UNINSTALL_QUESTION,
                                  strings.CONFIRM_UNINSTALL_SUBTITLE_PURGE),
        _Action.UNINSTALL_KEEP:  (strings.CONFIRM_UNINSTALL_QUESTION,
                                  strings.CONFIRM_UNINSTALL_SUBTITLE_KEEP),
        _Action.UPDATE:          (strings.CONFIRM_UPDATE_QUESTION,
                                  strings.CONFIRM_UPDATE_SUBTITLE),
    }

    _ACTION_LABEL: dict[_Action, str] = {
        _Action.REINSTALL:       strings.ACTION_REINSTALL,
        _Action.REINSTALL_RESET: strings.ACTION_REINSTALL_RESET,
        _Action.UNINSTALL_PURGE: strings.ACTION_UNINSTALL,
        _Action.UNINSTALL_KEEP:  strings.ACTION_UNINSTALL_KEEP,
        _Action.UPDATE:          strings.ACTION_UPDATE,
    }

    def _start_action(self, entries: list[PackageEntry], action: _Action) -> None:
        pkg_entries = [(e.package.name, e.package.source) for e in entries]
        pkg_names = [n for n, _ in pkg_entries]
        n = len(pkg_names)
        action_label = self._ACTION_LABEL[action]

        # ── Confirmation dialog (unchanged) ───────────────────────────────────
        if n == 1:
            pkg_name = pkg_names[0]
            question, subtitle = self._ACTION_CONFIRM[action]
            confirm_dlg = QMessageBox(self)
            confirm_dlg.setWindowTitle(strings.CONFIRM_ACTION_TITLE.format(
                action=action_label, name=pkg_name))
            confirm_dlg.setText(question.format(name=pkg_name))
            confirm_dlg.setInformativeText(subtitle)
            confirm_dlg.setStandardButtons(
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            confirm_dlg.setDefaultButton(QMessageBox.StandardButton.No)
            confirm_dlg.setIcon(QMessageBox.Icon.Warning)
            if confirm_dlg.exec() != QMessageBox.StandardButton.Yes:
                return
        else:
            confirm_dlg = _BatchConfirmDialog(action_label, pkg_names, self)
            if confirm_dlg.exec() != QDialog.DialogCode.Accepted:
                return

        # ── Launch action panel + worker ──────────────────────────────────────
        desc = (f"{action_label}: {pkg_names[0]}" if n == 1
                else f"{action_label}: {n} apps")
        self._model.set_busy(pkg_names)
        self._action_panel.start_action(desc)
        self._set_action_buttons_enabled(False)

        self._action_thread = QThread(parent=self)
        self._action_worker = _PackageActionWorker(pkg_entries, action, action_label)
        self._action_worker.moveToThread(self._action_thread)
        self._action_thread.started.connect(self._action_worker.run)

        self._action_worker.output_line.connect(self._action_panel.append_line)
        self._action_worker.succeeded.connect(self._on_action_success)
        self._action_worker.failed.connect(self._on_action_failed)
        self._action_worker.cancelled.connect(self._on_action_cancelled)
        self._action_worker.succeeded.connect(self._action_thread.quit)
        self._action_worker.failed.connect(self._action_thread.quit)
        self._action_worker.cancelled.connect(self._action_thread.quit)
        self._action_thread.finished.connect(self._action_worker.deleteLater)
        self._action_thread.start()

    def _on_action_success(self, pkg_names: object, action_label: str) -> None:
        names: list[str] = list(pkg_names)  # type: ignore[arg-type]
        msg = (strings.NOTICE_ACTION_COMPLETE.format(action=action_label, name=names[0])
               if len(names) == 1
               else strings.NOTICE_BATCH_COMPLETE.format(action=action_label, n=len(names)))
        self._action_panel.mark_complete(msg)
        self._set_action_buttons_enabled(True)
        self._reload_on_dismiss = True

    def _on_action_failed(self, pkg_names: object, stderr: str) -> None:
        self._model.set_busy(None)
        self._action_panel.mark_failed(stderr)
        self._set_action_buttons_enabled(True)
        self._reload_on_dismiss = False

    def _on_action_cancelled(self, _pkg_names: object) -> None:
        self._model.set_busy(None)
        self._action_panel.mark_complete(strings.NOTICE_ACTION_CANCELLED)
        self._set_action_buttons_enabled(True)
        self._reload_on_dismiss = False

    def _on_panel_dismissed(self) -> None:
        if self._reload_on_dismiss:
            self._reload_on_dismiss = False
            self._do_reload()

    def _do_reload(self) -> None:
        self._model.set_update_map({})
        self._update_all_btn.setEnabled(False)
        self._updates_label.setText("")
        self._model.reset_to_loading()
        self._start_load()

    def _set_action_buttons_enabled(self, enabled: bool) -> None:
        self._check_updates_btn.setEnabled(enabled)
        self._update_all_btn.setEnabled(
            enabled and bool(self._model.get_update_map())
        )

    # ── Update check ──────────────────────────────────────────────────────────

    def _start_update_check(self) -> None:
        if self._update_check_thread and self._update_check_thread.isRunning():
            return
        self._check_updates_btn.setEnabled(False)
        self._check_updates_btn.setText(strings.UPDATES_CHECKING)
        self._updates_label.setText("")

        self._update_check_thread = QThread(parent=self)
        self._update_check_worker = _UpdateCheckWorker()
        self._update_check_worker.moveToThread(self._update_check_thread)
        self._update_check_thread.started.connect(self._update_check_worker.run)
        self._update_check_worker.updates_found.connect(self._on_updates_found)
        self._update_check_worker.check_failed.connect(self._on_update_check_failed)
        self._update_check_worker.updates_found.connect(self._update_check_thread.quit)
        self._update_check_worker.check_failed.connect(self._update_check_thread.quit)
        self._update_check_thread.finished.connect(self._update_check_worker.deleteLater)
        self._update_check_thread.start()

    def _on_updates_found(self, updates: dict) -> None:
        self._check_updates_btn.setEnabled(True)
        self._check_updates_btn.setText(strings.ACTION_CHECK_UPDATES)
        n = len(updates)
        if n > 0:
            self._updates_label.setText(strings.UPDATES_AVAILABLE_N.format(n=n))
            self._update_all_btn.setEnabled(True)
        else:
            self._updates_label.setText(strings.UPDATES_NONE)
            self._update_all_btn.setEnabled(False)
        self._model.set_update_map(updates)

    def _on_update_check_failed(self, _error: str) -> None:
        self._check_updates_btn.setEnabled(True)
        self._check_updates_btn.setText(strings.ACTION_CHECK_UPDATES)
        self._updates_label.setText("")

    def _start_update_all(self) -> None:
        update_map = self._model.get_update_map()
        if not update_map:
            return
        entries = [
            e for e in self._model.all_entries()
            if (e.package.source, e.package.name) in update_map
            and not self._model.is_busy(e.package.name)
        ]
        if not entries:
            return
        self._start_action(entries, _Action.UPDATE)
