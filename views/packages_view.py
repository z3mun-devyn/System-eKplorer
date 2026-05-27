from __future__ import annotations

import strings
from backends.packages_backend import PackagesBackend
from backends.tags_backend import TagRepository
from models.package import Package
from models.tag import PackageEntry, Tag
from views.tag_editor_modal import DimOverlay, TagModal

from PyQt6.QtCore import (
    QAbstractListModel,
    QEvent,
    QModelIndex,
    QObject,
    QRect,
    QSize,
    QThread,
    Qt,
    pyqtSignal,
)
from PyQt6.QtGui import QColor, QFontMetrics, QPainter, QPalette
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QLabel,
    QListView,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QVBoxLayout,
    QWidget,
)

_ROW_HEIGHT = 56
_ROW_HEIGHT_TAGGED = 78
_H_PAD = 14
_V_PAD = 9
_LINE_GAP = 4
_PILL_H = 16
_PILL_V_PAD = 6
_PILL_PAD = 12        # horizontal padding inside a pill
_MAX_PILLS = 4        # max visible pills before "…+N" overflow indicator

_ENTRY_ROLE = Qt.ItemDataRole.UserRole
_SKELETON_ROLE = Qt.ItemDataRole.UserRole + 1
_SIDEBAR_W = 200
_SKELETON_COUNT = 24

# Filter sentinels
_ALL_CATEGORIES = ""
_ALL_TAGS = ""


# ── Model ─────────────────────────────────────────────────────────────────────

class _PackageModel(QAbstractListModel):
    def __init__(self) -> None:
        super().__init__()
        self._all: list[PackageEntry] | None = None   # None = skeleton mode
        self._shown: list[PackageEntry] = []
        self._cat_filter: str = _ALL_CATEGORIES
        self._tag_filter: str = _ALL_TAGS

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return _SKELETON_COUNT if self._all is None else len(self._shown)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        if self._all is None:
            return True if role == _SKELETON_ROLE else None
        row = index.row()
        if row >= len(self._shown):
            return None
        entry = self._shown[row]
        if role == _ENTRY_ROLE:
            return entry
        if role == Qt.ItemDataRole.DisplayRole:
            return entry.package.name
        return None

    def set_entries(self, entries: list[PackageEntry]) -> None:
        self.beginResetModel()
        self._all = entries
        self._rebuild_shown()
        self.endResetModel()

    def set_filter(self, category: str = _ALL_CATEGORIES,
                   tag_name: str = _ALL_TAGS) -> None:
        self._cat_filter = category
        self._tag_filter = tag_name
        self.beginResetModel()
        self._rebuild_shown()
        self.endResetModel()

    def current_category(self) -> str:
        return self._cat_filter

    def current_tag(self) -> str:
        return self._tag_filter

    def all_entries(self) -> list[PackageEntry]:
        return list(self._all) if self._all is not None else []

    def is_loading(self) -> bool:
        return self._all is None

    def _rebuild_shown(self) -> None:
        if self._all is None:
            self._shown = []
            return
        result = self._all
        if self._cat_filter:
            result = [e for e in result
                      if strings.package_category(e.package.section) == self._cat_filter]
        if self._tag_filter:
            result = [e for e in result
                      if any(t.name == self._tag_filter for t in e.tags)]
        self._shown = result


# ── Delegate ──────────────────────────────────────────────────────────────────

class _PackageDelegate(QStyledItemDelegate):
    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex) -> QSize:
        if index.data(_SKELETON_ROLE):
            return QSize(max(option.rect.width(), 100), _ROW_HEIGHT)
        entry: PackageEntry | None = index.data(_ENTRY_ROLE)
        h = _ROW_HEIGHT_TAGGED if (entry and entry.tags) else _ROW_HEIGHT
        return QSize(max(option.rect.width(), 100), h)

    def paint(self, painter: QPainter, option: QStyleOptionViewItem,
              index: QModelIndex) -> None:
        painter.save()

        rect = option.rect
        palette = option.palette
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        hovered = bool(option.state & QStyle.StateFlag.State_MouseOver)

        if selected:
            painter.fillRect(rect, palette.color(QPalette.ColorRole.Highlight))
        elif hovered:
            hc = QColor(palette.color(QPalette.ColorRole.Highlight))
            hc.setAlphaF(0.08)
            painter.fillRect(rect, hc)

        if index.data(_SKELETON_ROLE):
            self._paint_skeleton(painter, rect, palette)
        else:
            entry: PackageEntry | None = index.data(_ENTRY_ROLE)
            if entry:
                self._paint_row(painter, rect, palette, entry, selected)

        sep = QColor(palette.color(QPalette.ColorRole.Mid))
        sep.setAlphaF(0.25)
        painter.setPen(sep)
        painter.drawLine(rect.left() + _H_PAD, rect.bottom(),
                         rect.right() - _H_PAD, rect.bottom())

        # Three-dot affordance — painted in dots_rect so the click target is clear
        muted = QColor(palette.color(QPalette.ColorRole.Mid))
        muted.setAlphaF(0.5)
        painter.setPen(muted)
        painter.drawText(self.dots_rect(rect), Qt.AlignmentFlag.AlignCenter, "⋯")

        painter.restore()

    @staticmethod
    def dots_rect(row_rect: QRect) -> QRect:
        return QRect(row_rect.right() - 28, row_rect.top(),
                     24, row_rect.height())

    def _paint_row(self, painter: QPainter, rect: QRect, palette: QPalette,
                   entry: PackageEntry, selected: bool) -> None:
        cg = QPalette.ColorGroup.Normal
        fg = palette.color(
            cg,
            QPalette.ColorRole.HighlightedText if selected else QPalette.ColorRole.WindowText,
        )
        muted = QColor(fg)
        muted.setAlphaF(0.55)

        pkg = entry.package
        fm = QFontMetrics(painter.font())
        line_h = fm.height()

        x = rect.left() + _H_PAD
        right = rect.right() - _H_PAD - 28  # leave room for "⋯"
        y1 = rect.top() + _V_PAD
        y2 = y1 + line_h + _LINE_GAP

        ver_w = fm.horizontalAdvance(pkg.version) + 2
        size_w = fm.horizontalAdvance(pkg.size_str) + 2
        right_w = max(ver_w, size_w)
        name_w = right - x - right_w - 8

        bold_font = painter.font()
        bold_font.setBold(True)
        painter.setFont(bold_font)
        painter.setPen(fg)
        painter.drawText(QRect(x, y1, name_w, line_h),
                         Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                         pkg.name)

        plain_font = painter.font()
        plain_font.setBold(False)
        painter.setFont(plain_font)
        painter.setPen(muted)
        painter.drawText(QRect(right - right_w, y1, right_w, line_h),
                         Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                         pkg.version)

        cat = strings.package_category(pkg.section)
        painter.drawText(QRect(x, y2, right - x - right_w - 8, line_h),
                         Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                         cat)
        painter.drawText(QRect(right - right_w, y2, right_w, line_h),
                         Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                         pkg.size_str)

        if entry.tags:
            self._paint_pills(painter, entry.tags, x, right, y2 + line_h + _PILL_V_PAD,
                              palette)

    def _paint_pills(self, painter: QPainter, tags: list[Tag],
                     x: int, right: int, y: int, palette: QPalette) -> None:
        small_font = painter.font()
        small_font.setPointSize(max(7, small_font.pointSize() - 1))
        painter.setFont(small_font)
        sfm = QFontMetrics(small_font)

        visible = tags[:_MAX_PILLS]
        hidden_count = len(tags) - len(visible)  # beyond the cap

        pill_x = x
        rendered = 0
        for tag in visible:
            pw = sfm.horizontalAdvance(tag.name) + _PILL_PAD
            if pill_x + pw > right:
                # horizontal overflow — count remaining visible as hidden too
                hidden_count += len(visible) - rendered
                break
            pill_rect = QRect(pill_x, y, pw, _PILL_H)
            bg = QColor(tag.color_hex)
            painter.setBrush(bg)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(pill_rect, _PILL_H // 2, _PILL_H // 2)
            pill_fg = QColor(strings.contrast_color(tag.color_hex))
            painter.setPen(pill_fg)
            painter.drawText(pill_rect, Qt.AlignmentFlag.AlignCenter, tag.name)
            pill_x += pw + 4
            rendered += 1

        if hidden_count > 0:
            ot = f"…+{hidden_count}"
            ow = sfm.horizontalAdvance(ot) + _PILL_PAD
            if pill_x + ow <= right:
                ov_rect = QRect(pill_x, y, ow, _PILL_H)
                ov_bg = QColor(palette.color(QPalette.ColorRole.Mid))
                ov_bg.setAlphaF(0.3)
                painter.setBrush(ov_bg)
                painter.setPen(Qt.PenStyle.NoPen)
                painter.drawRoundedRect(ov_rect, _PILL_H // 2, _PILL_H // 2)
                ov_fg = QColor(palette.color(QPalette.ColorRole.WindowText))
                ov_fg.setAlphaF(0.7)
                painter.setPen(ov_fg)
                painter.drawText(ov_rect, Qt.AlignmentFlag.AlignCenter, ot)

    def _paint_skeleton(self, painter: QPainter, rect: QRect,
                        palette: QPalette) -> None:
        skel = QColor(palette.color(QPalette.ColorRole.Mid))
        skel.setAlphaF(0.25)
        painter.setBrush(skel)
        painter.setPen(Qt.PenStyle.NoPen)

        x = rect.left() + _H_PAD
        right = rect.right() - _H_PAD - 28
        y1 = rect.top() + _V_PAD
        y2 = y1 + 14 + _LINE_GAP

        painter.drawRoundedRect(x, y1, 180, 12, 3, 3)
        painter.drawRoundedRect(right - 90, y1, 90, 12, 3, 3)
        painter.drawRoundedRect(x, y2, 110, 10, 3, 3)
        painter.drawRoundedRect(right - 60, y2, 60, 10, 3, 3)


# ── Sidebar ────────────────────────────────────────────────────────────────────

class _SidebarWidget(QWidget):
    category_selected = pyqtSignal(str)   # "" = all
    tag_selected = pyqtSignal(str)        # "" = all (name-based)
    new_tag_requested = pyqtSignal()

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
        layout.addWidget(self._tag_list)

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

    def update_tags(self, tags: list[Tag], counts: dict[str, int]) -> None:
        self._tag_list.clear()
        all_item = QListWidgetItem(f"  {strings.SIDEBAR_ALL}")
        all_item.setData(Qt.ItemDataRole.UserRole, _ALL_TAGS)
        self._tag_list.addItem(all_item)
        for tag in tags:
            cnt = counts.get(tag.name, 0)
            item = QListWidgetItem(f"  ● {tag.name}  ({cnt})")
            item.setData(Qt.ItemDataRole.UserRole, tag.name)
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
            self.tag_selected.emit(val)   # str tag name


# ── Background loader ─────────────────────────────────────────────────────────

class _PackageLoader(QObject):
    packages_ready = pyqtSignal(list)
    load_failed = pyqtSignal(str)

    def run(self) -> None:
        try:
            pkgs = PackagesBackend().list_installed()
            self.packages_ready.emit(pkgs)
        except Exception as exc:
            self.load_failed.emit(str(exc))


# ── View ──────────────────────────────────────────────────────────────────────

class PackagesView(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._repo = TagRepository()

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
        splitter.addWidget(self._sidebar)

        # Right panel: status + list
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)

        self._status = QLabel(strings.PACKAGES_LOADING)
        self._status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._status.setStyleSheet("QLabel { color: palette(mid); padding: 8px; }")
        self._status.setVisible(False)
        right_layout.addWidget(self._status)

        self._model = _PackageModel()
        self._delegate = _PackageDelegate()
        self._list = QListView()
        self._list.setModel(self._model)
        self._list.setItemDelegate(self._delegate)
        self._list.setUniformItemSizes(False)
        self._list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._list.setFrameShape(QFrame.Shape.NoFrame)
        self._list.setMouseTracking(True)
        self._list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._list.customContextMenuRequested.connect(self._show_context_menu)
        self._list.viewport().installEventFilter(self)
        right_layout.addWidget(self._list, stretch=1)

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

        self._start_load()

    # ── Event filter (three-dot left-click) ──────────────────────────────────

    def eventFilter(self, obj, event) -> bool:
        if (obj is self._list.viewport() and
                event.type() == QEvent.Type.MouseButtonPress and
                event.button() == Qt.MouseButton.LeftButton):
            pos = event.pos()
            index = self._list.indexAt(pos)
            if index.isValid():
                entry: PackageEntry | None = index.data(_ENTRY_ROLE)
                if entry is not None:
                    row_rect = self._list.visualRect(index)
                    if _PackageDelegate.dots_rect(row_rect).contains(pos):
                        self._show_menu_for_entry(
                            entry, self._list.viewport().mapToGlobal(pos)
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
        self._thread = QThread(parent=self)
        self._worker = _PackageLoader()
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.packages_ready.connect(self._on_packages_ready)
        self._worker.load_failed.connect(self._on_load_failed)
        self._worker.packages_ready.connect(self._thread.quit)
        self._worker.load_failed.connect(self._thread.quit)
        self._thread.finished.connect(self._worker.deleteLater)
        self._thread.start()

    def _on_packages_ready(self, packages: list[Package]) -> None:
        assignments = self._repo.load_all_assignments()
        entries = [
            PackageEntry(
                package=pkg,
                tags=assignments.get((pkg.source, pkg.name), []),
            )
            for pkg in packages
        ]
        self._model.set_entries(entries)

        if packages:
            self._status.setVisible(False)
            self._refresh_sidebar()
        else:
            self._status.setText(strings.PACKAGES_EMPTY)
            self._status.setVisible(True)

    def _on_load_failed(self, _error: str) -> None:
        self._model.set_entries([])
        self._status.setText(strings.ERR_PARSE_FAILURE.format(source="dpkg"))
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
        counts = self._repo.tag_counts()   # {tag_name: count}
        self._sidebar.update_tags(all_tags, counts)

    # ── Filtering — AND-combines category and tag ─────────────────────────────

    def _on_category_filter(self, category: str) -> None:
        self._model.set_filter(category=category,
                               tag_name=self._model.current_tag())

    def _on_tag_filter(self, tag_name: str) -> None:
        # Toggle: clicking the active tag clears it
        current = self._model.current_tag()
        new_tag = _ALL_TAGS if tag_name == current else tag_name
        self._model.set_filter(category=self._model.current_category(),
                               tag_name=new_tag)

    # ── Context menu ──────────────────────────────────────────────────────────

    def _show_context_menu(self, pos) -> None:
        """Called from customContextMenuRequested (right-click / keyboard)."""
        index = self._list.indexAt(pos)
        if not index.isValid():
            return
        entry: PackageEntry | None = index.data(_ENTRY_ROLE)
        if entry is None:
            return
        self._show_menu_for_entry(entry, self._list.viewport().mapToGlobal(pos))

    def _show_menu_for_entry(self, entry: PackageEntry, global_pos) -> None:
        menu = QMenu(self)
        assign_action = menu.addAction(strings.ACTION_ASSIGN_TAGS)
        # M5: add uninstall action here (one line)
        action = menu.exec(global_pos)
        if action is assign_action:
            self._open_tag_modal_for(entry)

    # ── Tag modal ─────────────────────────────────────────────────────────────

    def _open_tag_modal_for(self, entry: PackageEntry) -> None:
        self._dim.setVisible(True)
        self._dim.raise_()
        self._modal.open_for(entry)
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
