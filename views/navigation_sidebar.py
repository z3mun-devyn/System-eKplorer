"""M10a: NavigationSidebar — shared widget used in Dashboard and File Manager.

Single implementation; instantiated in both DashboardTab and FileManagerTab.
Sections (top to bottom):
  - Quick Access: QTreeWidget with XDG dirs (expandable to subdirs, lazy-loaded)
                  + Recent Files + Recent Locations (hidden if empty)
  - Drives: system drive first, then others, then unmounted (orange)
  - Network: hidden if no shares detected (always hidden in M10a)
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

import strings
from backends.recent_backend import RecentPathsBackend
from backends.storage_backend import StorageBackend
from models.storage import Drive, UnmountedDrive

from PyQt6.QtCore import QObject, QSize, QThread, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QIcon
from PyQt6.QtWidgets import (
    QAbstractScrollArea,
    QApplication,
    QFrame,
    QLabel,
    QMenu,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStyle,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)
from views.file_view import _chrome_icon

# UserRole+1 marks a placeholder child (triggers lazy subdir load on expand)
_PLACEHOLDER_ROLE = Qt.ItemDataRole.UserRole + 1
# UserRole+2 stores an UnmountedDrive on unmounted drive tree items
_UNMOUNTED_ROLE = Qt.ItemDataRole.UserRole + 2


# ── Internal helpers ──────────────────────────────────────────────────────────

def _section_header(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("nav_section_header")
    font = label.font()
    font.setBold(True)
    font.setPointSize(max(7, font.pointSize() - 1))
    label.setFont(font)
    label.setStyleSheet(
        "QLabel { color: palette(mid); padding: 8px 8px 2px 8px; }"
    )
    label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
    return label


def _subsection_header(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("nav_subsection_header")
    font = label.font()
    font.setBold(True)
    font.setPointSize(max(7, font.pointSize() - 1))
    label.setFont(font)
    label.setStyleSheet(
        "QLabel { color: palette(mid); padding: 6px 8px 1px 16px; }"
    )
    label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
    return label


class _NavEntry(QPushButton):
    """A single clickable sidebar entry (used for Drives section)."""

    def __init__(
        self,
        text: str,
        *,
        unmounted: bool = False,
        tooltip: str = "",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(text, parent)
        self.setFlat(True)
        color_rule = f"color: {strings.NAV_UNMOUNTED_COLOR};" if unmounted else ""
        self.setStyleSheet(
            f"QPushButton {{ text-align: left; border: none;"
            f" padding: 3px 8px 3px 8px; {color_rule} }}"
            " QPushButton:hover { background: palette(mid);"
            " border-radius: 4px; }"
        )
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        if tooltip:
            self.setToolTip(tooltip)


# ── Background workers ────────────────────────────────────────────────────────

class _SidebarDriveLoader(QObject):
    ready  = pyqtSignal(list, list)   # (mounted, unmounted)
    failed = pyqtSignal(str)

    def run(self) -> None:
        try:
            backend = StorageBackend()
            self.ready.emit(backend.list_drives(), backend.list_unmounted_devices())
        except Exception as exc:
            self.failed.emit(str(exc))


class _SidebarMountWorker(QObject):
    mounted = pyqtSignal(str)   # mount point on success
    failed  = pyqtSignal(str)

    def __init__(self, drive: UnmountedDrive) -> None:
        super().__init__()
        self._drive = drive

    def run(self) -> None:
        try:
            if self._drive.is_encrypted:
                result = subprocess.run(
                    ["udisksctl", "unlock", "-b", self._drive.device],
                    capture_output=True, text=True, timeout=30,
                )
                if result.returncode != 0:
                    self.failed.emit(result.stderr.strip())
                    return
                mapped = result.stdout.strip().split()[-1]
                device = mapped
            else:
                device = self._drive.device

            result = subprocess.run(
                ["udisksctl", "mount", "-b", device],
                capture_output=True, text=True, timeout=30,
            )
            if result.returncode == 0:
                parts = result.stdout.strip().split(" at ")
                mount_point = parts[-1] if len(parts) > 1 else "/"
                self.mounted.emit(mount_point.rstrip("."))
            else:
                self.failed.emit(result.stderr.strip())
        except Exception as exc:
            self.failed.emit(str(exc))


# ── NavigationSidebar ─────────────────────────────────────────────────────────

_XDG_ENTRIES: list[tuple[str, str]] = [
    (strings.NAV_HOME,       "~"),
    (strings.NAV_DESKTOP,    "~/Desktop"),
    (strings.NAV_DOCUMENTS,  "~/Documents"),
    (strings.NAV_DOWNLOADS,  "~/Downloads"),
    (strings.NAV_PICTURES,   "~/Pictures"),
    (strings.NAV_VIDEOS,     "~/Videos"),
    (strings.NAV_MUSIC,      "~/Music"),
]

# Freedesktop theme name for each Quick Access XDG directory
_XDG_ICONS: dict[str, str] = {
    strings.NAV_HOME:       "user-home",
    strings.NAV_DESKTOP:    "user-desktop",
    strings.NAV_DOCUMENTS:  "folder-documents",
    strings.NAV_DOWNLOADS:  "folder-download",
    strings.NAV_PICTURES:   "folder-pictures",
    strings.NAV_VIDEOS:     "folder-videos",
    strings.NAV_MUSIC:      "folder-music",
}


def _nav_icon(
    *theme_names: str,
    fallback_standard: QStyle.StandardPixmap | None = None,
) -> QIcon:
    """Return a sidebar icon using the self-adaptive theme pattern.

    On viable theme systems, tries each name in order and returns the first
    non-null result.  Falls back to a QStyle standard pixmap if given, and
    always floors to SP_DirIcon so the result is never null.
    """
    for name in theme_names:
        icon = _chrome_icon(name)
        if not icon.isNull():
            return icon
    if fallback_standard is not None:
        icon = QApplication.style().standardIcon(fallback_standard)
        if not icon.isNull():
            return icon
    return QApplication.style().standardIcon(QStyle.StandardPixmap.SP_DirIcon)


class NavigationSidebar(QWidget):
    """Shared navigation sidebar — Quick Access (tree), Drives, Network.

    Used verbatim in DashboardTab (left of drive tiles) and FileManagerTab
    (left of the file view).  One implementation, two instances.

    Signals:
        navigate_requested(path): emitted when any interactive entry is clicked.
        drives_updated(mounted, unmounted): emitted whenever drives are (re)loaded.
    """

    navigate_requested       = pyqtSignal(str)
    drives_updated           = pyqtSignal(list, list)
    wastebin_action_requested = pyqtSignal(str)
    # emits "restore_all" | "empty" when user right-clicks the Wastebin node

    def __init__(self, fixed_width: int | None = 220,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        if fixed_width is not None:
            self.setFixedWidth(fixed_width)
        else:
            self.setMinimumWidth(140)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        container = QWidget()
        self._main_layout = QVBoxLayout(container)
        self._main_layout.setContentsMargins(4, 8, 4, 8)
        self._main_layout.setSpacing(0)

        # ── Quick Access ──────────────────────────────────────────────────────
        self._main_layout.addWidget(
            _section_header(strings.NAV_SECTION_QUICK_ACCESS))

        # Expandable tree for XDG directories
        self._quick_tree = QTreeWidget()
        self._quick_tree.setHeaderHidden(True)
        self._quick_tree.setRootIsDecorated(True)
        self._quick_tree.setAnimated(True)
        self._quick_tree.setIndentation(14)
        self._quick_tree.setFrameShape(QFrame.Shape.NoFrame)
        self._quick_tree.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._quick_tree.setSizeAdjustPolicy(
            QAbstractScrollArea.SizeAdjustPolicy.AdjustToContents)
        self._quick_tree.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self._quick_tree.setStyleSheet("""
            QTreeWidget {
                background: transparent;
                border: none;
                outline: 0;
            }
            QTreeWidget::item {
                padding: 3px 4px 3px 2px;
                border-radius: 3px;
            }
            QTreeWidget::item:hover {
                background: palette(mid);
            }
            QTreeWidget::item:selected {
                background: palette(highlight);
                color: palette(highlighted-text);
            }
        """)
        self._quick_tree.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._quick_tree.itemClicked.connect(self._on_tree_item_clicked)
        self._quick_tree.itemExpanded.connect(self._on_tree_item_expanded)
        self._quick_tree.itemExpanded.connect(
            lambda _: self._quick_tree.updateGeometry())
        self._quick_tree.itemCollapsed.connect(
            lambda _: self._quick_tree.updateGeometry())

        for label, tilde_path in _XDG_ENTRIES:
            path = os.path.expanduser(tilde_path)
            if os.path.isdir(path):
                icon = _nav_icon(_XDG_ICONS.get(label, "folder"),
                                 fallback_standard=QStyle.StandardPixmap.SP_DirIcon)
                self._quick_tree.addTopLevelItem(
                    self._make_tree_item(label, path, icon=icon))

        # Wastebin — not expandable (no placeholder child)
        self._wastebin_item = QTreeWidgetItem([strings.NAV_WASTEBIN])
        self._wastebin_item.setData(0, Qt.ItemDataRole.UserRole, strings.TRASH_SENTINEL)
        self._wastebin_item.setIcon(0, _nav_icon("user-trash",
                                                  fallback_standard=QStyle.StandardPixmap.SP_TrashIcon))
        self._quick_tree.addTopLevelItem(self._wastebin_item)

        # Right-click context menu for the Wastebin node
        self._quick_tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._quick_tree.customContextMenuRequested.connect(
            self._on_quick_tree_context_menu)

        self._main_layout.addWidget(self._quick_tree)

        # Recent Files (subsection, hidden until populated)
        self._recent_files_header = _subsection_header(
            strings.NAV_SUBSECTION_RECENT_FILES)
        self._main_layout.addWidget(self._recent_files_header)
        self._recent_files_box = QWidget()
        self._recent_files_layout = QVBoxLayout(self._recent_files_box)
        self._recent_files_layout.setContentsMargins(8, 0, 0, 0)
        self._recent_files_layout.setSpacing(0)
        self._main_layout.addWidget(self._recent_files_box)

        # Recent Locations (subsection, hidden until populated)
        self._recent_locs_header = _subsection_header(
            strings.NAV_SUBSECTION_RECENT_LOCS)
        self._main_layout.addWidget(self._recent_locs_header)
        self._recent_locs_box = QWidget()
        self._recent_locs_layout = QVBoxLayout(self._recent_locs_box)
        self._recent_locs_layout.setContentsMargins(8, 0, 0, 0)
        self._recent_locs_layout.setSpacing(0)
        self._main_layout.addWidget(self._recent_locs_box)

        # ── Drives ────────────────────────────────────────────────────────────
        self._main_layout.addWidget(_section_header(strings.NAV_SECTION_DRIVES))
        self._drives_tree = QTreeWidget()
        self._drives_tree.setHeaderHidden(True)
        self._drives_tree.setRootIsDecorated(True)
        self._drives_tree.setAnimated(True)
        self._drives_tree.setIndentation(14)
        self._drives_tree.setFrameShape(QFrame.Shape.NoFrame)
        self._drives_tree.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._drives_tree.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._drives_tree.setSizeAdjustPolicy(
            QAbstractScrollArea.SizeAdjustPolicy.AdjustToContents)
        self._drives_tree.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self._drives_tree.setStyleSheet("""
            QTreeWidget {
                background: transparent;
                border: none;
                outline: 0;
            }
            QTreeWidget::item {
                padding: 3px 4px 3px 2px;
                border-radius: 3px;
            }
            QTreeWidget::item:hover {
                background: palette(mid);
            }
            QTreeWidget::item:selected {
                background: palette(highlight);
                color: palette(highlighted-text);
            }
        """)
        self._drives_tree.itemClicked.connect(self._on_drives_tree_item_clicked)
        self._drives_tree.itemExpanded.connect(self._on_tree_item_expanded)
        self._drives_tree.itemExpanded.connect(
            lambda _: self._drives_tree.updateGeometry())
        self._drives_tree.itemCollapsed.connect(
            lambda _: self._drives_tree.updateGeometry())
        self._main_layout.addWidget(self._drives_tree)

        # ── Network (hidden) ──────────────────────────────────────────────────
        self._network_header = _section_header(strings.NAV_SECTION_NETWORK)
        self._main_layout.addWidget(self._network_header)
        self._network_box = QWidget()
        self._main_layout.addWidget(self._network_box)
        self._network_header.setVisible(False)
        self._network_box.setVisible(False)

        self._main_layout.addStretch()

        scroll.setWidget(container)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

        self._drive_thread: QThread | None = None
        self._drive_worker: _SidebarDriveLoader | None = None
        self._mount_thread: QThread | None = None
        self._mount_worker: _SidebarMountWorker | None = None
        self._drives_loaded = False

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if not self._drives_loaded:
            self._drives_loaded = True
            self._load_drives()
        self.refresh_recent()

    # ── Public API ────────────────────────────────────────────────────────────

    def set_drives(self, mounted: list[Drive], unmounted: list[UnmountedDrive]) -> None:
        """Populate the Drives section. Called from background thread or tests."""
        self._drives_tree.clear()

        _hd_icon     = _nav_icon("drive-harddisk",
                                  fallback_standard=QStyle.StandardPixmap.SP_DriveHDIcon)
        _root_icon   = _nav_icon("drive-harddisk-root", "drive-harddisk",
                                  fallback_standard=QStyle.StandardPixmap.SP_DriveHDIcon)

        # System drive first
        system = next((d for d in mounted if d.mount_point == "/"), None)
        if system:
            display = system.label or strings.NAV_SYSTEM_DRIVE
            tip = system.device if system.label else ""
            self._drives_tree.addTopLevelItem(
                self._make_tree_item(display, "/", tip=tip, icon=_root_icon))

        # Other mounted drives
        for drive in mounted:
            if drive.mount_point == "/":
                continue
            display = drive.label or drive.name or drive.mount_point
            tip = f"{drive.device}  ({drive.mount_point})"
            self._drives_tree.addTopLevelItem(
                self._make_tree_item(display, drive.mount_point, tip=tip,
                                     icon=_hd_icon))

        # Unmounted drives (orange text; same drive icon, no expand arrow)
        for udrive in unmounted:
            display = udrive.fs_label or udrive.name or udrive.device
            label = f"{display} {strings.NAV_UNMOUNTED}"
            item = QTreeWidgetItem([label])
            item.setIcon(0, _hd_icon)
            item.setToolTip(0, udrive.device)
            item.setData(0, _UNMOUNTED_ROLE, udrive)
            item.setForeground(0, QColor(strings.NAV_UNMOUNTED_COLOR))
            self._drives_tree.addTopLevelItem(item)

        self.drives_updated.emit(mounted, unmounted)

    def refresh_recent(self) -> None:
        """Reload recent files and locations from the database."""
        backend = RecentPathsBackend()

        locs = backend.list_locations(limit=5)
        self._repopulate(
            self._recent_locs_layout,
            [(os.path.basename(p) or p, p) for p in locs],
        )
        self._recent_locs_header.setVisible(bool(locs))
        self._recent_locs_box.setVisible(bool(locs))

        files = backend.list_files(limit=10)
        self._repopulate(
            self._recent_files_layout,
            [(os.path.basename(p) or p, p) for p in files],
        )
        self._recent_files_header.setVisible(bool(files))
        self._recent_files_box.setVisible(bool(files))

    # ── Public: wastebin icon ─────────────────────────────────────────────────

    def update_wastebin_icon(self) -> None:
        """Switch the Wastebin icon between empty and full based on trash count."""
        from backends.trash_backend import TrashBackend
        try:
            count = TrashBackend().trash_count()
        except Exception:
            count = 0
        if count > 0:
            icon = _nav_icon("user-trash-full", "user-trash",
                             fallback_standard=QStyle.StandardPixmap.SP_TrashIcon)
        else:
            icon = _nav_icon("user-trash",
                             fallback_standard=QStyle.StandardPixmap.SP_TrashIcon)
        self._wastebin_item.setIcon(0, icon)

    # ── Public: tree refresh ──────────────────────────────────────────────────

    def refresh_expanded_nodes(self) -> None:
        """Sync expanded tree nodes with the current filesystem state.

        Walks all expanded items in both trees.  For each one whose children
        have been lazy-loaded, re-reads immediate subdirectories from disk,
        adds new ones, removes stale ones, and preserves expansion state of
        surviving children.  Does not collapse anything.
        """
        for tree in (self._quick_tree, self._drives_tree):
            self._sync_expanded(tree.invisibleRootItem())
            tree.updateGeometry()

    # ── Private: tree helpers ─────────────────────────────────────────────────

    def _make_tree_item(
        self,
        label: str,
        path: str,
        tip: str = "",
        icon: QIcon | None = None,
    ) -> QTreeWidgetItem:
        """Create a top-level or child tree item with a lazy-load placeholder."""
        item = QTreeWidgetItem([label])
        if icon is not None and not icon.isNull():
            item.setIcon(0, icon)
        item.setData(0, Qt.ItemDataRole.UserRole, path)
        if tip:
            item.setToolTip(0, tip)
        # Placeholder child forces the expand arrow to appear
        ph = QTreeWidgetItem([""])
        ph.setData(0, _PLACEHOLDER_ROLE, True)
        item.addChild(ph)
        return item

    def _on_quick_tree_context_menu(self, pos) -> None:
        """Show the Wastebin context menu when that node is right-clicked."""
        item = self._quick_tree.itemAt(pos)
        if item is not self._wastebin_item:
            return
        menu = QMenu(self)
        menu.addAction(strings.TRASH_WB_RESTORE_ALL).triggered.connect(
            lambda: self.wastebin_action_requested.emit("restore_all"))
        menu.addSeparator()
        menu.addAction(strings.TRASH_WB_EMPTY).triggered.connect(
            lambda: self.wastebin_action_requested.emit("empty"))
        menu.addSeparator()
        shred_act = menu.addAction(strings.TRASH_WB_SHRED)
        shred_act.setEnabled(False)
        shred_act.setToolTip(strings.TRASH_SHRED_TOOLTIP)
        menu.exec(self._quick_tree.viewport().mapToGlobal(pos))

    def _on_tree_item_clicked(self, item: QTreeWidgetItem, column: int) -> None:
        path = item.data(0, Qt.ItemDataRole.UserRole)
        if path:
            self.navigate_requested.emit(str(path))

    def _on_drives_tree_item_clicked(
        self, item: QTreeWidgetItem, column: int
    ) -> None:
        udrive = item.data(0, _UNMOUNTED_ROLE)
        if udrive is not None:
            self._mount_and_navigate(udrive)
            return
        path = item.data(0, Qt.ItemDataRole.UserRole)
        if path:
            self.navigate_requested.emit(str(path))

    def _on_tree_item_expanded(self, item: QTreeWidgetItem) -> None:
        """Lazy-load subdirectories on first expand."""
        if (item.childCount() == 1
                and item.child(0).data(0, _PLACEHOLDER_ROLE)):
            item.removeChild(item.child(0))
            path_str = item.data(0, Qt.ItemDataRole.UserRole)
            if path_str is None:
                return
            self._populate_subdirs(item, Path(path_str))

    def _populate_subdirs(
        self, parent_item: QTreeWidgetItem, path: Path
    ) -> None:
        """Add immediate non-hidden subdirectories as children."""
        try:
            subdirs = sorted(
                [d for d in path.iterdir()
                 if d.is_dir() and not d.name.startswith(".")],
                key=lambda d: d.name.lower(),
            )
        except PermissionError:
            subdirs = []

        folder_icon = _nav_icon("folder",
                                fallback_standard=QStyle.StandardPixmap.SP_DirIcon)
        for sub in subdirs:
            child = QTreeWidgetItem([sub.name])
            child.setIcon(0, folder_icon)
            child.setData(0, Qt.ItemDataRole.UserRole, str(sub))
            # Show expand arrow only if the subdir itself has sub-subdirs
            try:
                has_subdirs = any(
                    d.is_dir() and not d.name.startswith(".")
                    for d in sub.iterdir()
                )
            except PermissionError:
                has_subdirs = False
            if has_subdirs:
                ph = QTreeWidgetItem([""])
                ph.setData(0, _PLACEHOLDER_ROLE, True)
                child.addChild(ph)
            parent_item.addChild(child)

    def _sync_expanded(self, item: QTreeWidgetItem) -> None:
        """Recursively sync loaded children of expanded items under item."""
        for i in range(item.childCount()):
            child = item.child(i)
            if child is None:
                continue
            if not child.isExpanded():
                continue
            # Item still has its placeholder → never lazy-loaded, skip
            if (child.childCount() == 1
                    and child.child(0).data(0, _PLACEHOLDER_ROLE)):
                continue
            self._sync_node_children(child)
            self._sync_expanded(child)

    def _sync_node_children(self, item: QTreeWidgetItem) -> None:
        """Add new and remove stale immediate subdir children to match disk."""
        path_str = item.data(0, Qt.ItemDataRole.UserRole)
        if not path_str:
            return
        path = Path(path_str)

        try:
            current_subdirs = sorted(
                [d for d in path.iterdir()
                 if d.is_dir() and not d.name.startswith(".")],
                key=lambda d: d.name.lower(),
            )
        except (PermissionError, OSError):
            return

        current_names = {d.name for d in current_subdirs}

        # Build map of existing children; bail if a placeholder is still present
        existing: dict[str, QTreeWidgetItem] = {}
        for i in range(item.childCount()):
            child = item.child(i)
            if child.data(0, _PLACEHOLDER_ROLE):
                return
            child_path = child.data(0, Qt.ItemDataRole.UserRole)
            if child_path:
                existing[Path(child_path).name] = child

        # Remove stale children
        for name in list(existing.keys()):
            if name not in current_names:
                item.removeChild(existing.pop(name))

        # Add new children
        folder_icon = _nav_icon("folder",
                                fallback_standard=QStyle.StandardPixmap.SP_DirIcon)
        for sub in current_subdirs:
            if sub.name in existing:
                continue
            child = QTreeWidgetItem([sub.name])
            child.setIcon(0, folder_icon)
            child.setData(0, Qt.ItemDataRole.UserRole, str(sub))
            try:
                has_subdirs = any(
                    d.is_dir() and not d.name.startswith(".")
                    for d in sub.iterdir()
                )
            except PermissionError:
                has_subdirs = False
            if has_subdirs:
                ph = QTreeWidgetItem([""])
                ph.setData(0, _PLACEHOLDER_ROLE, True)
                child.addChild(ph)
            item.addChild(child)

        # Re-sort to maintain alphabetical order after insertions
        if item.childCount() > 1:
            item.sortChildren(0, Qt.SortOrder.AscendingOrder)

    # ── Private: other helpers ────────────────────────────────────────────────

    def _repopulate(
        self, layout: QVBoxLayout, entries: list[tuple[str, str]]
    ) -> None:
        while layout.count():
            item = layout.takeAt(0)
            if item and item.widget():
                item.widget().deleteLater()
        recent_icon = _nav_icon("folder-recent", "document-open-recent",
                                fallback_standard=QStyle.StandardPixmap.SP_DirIcon)
        for label, path in entries:
            btn = _NavEntry(label, tooltip=path)
            btn.setIcon(recent_icon)
            btn.setIconSize(QSize(16, 16))
            btn.clicked.connect(
                lambda checked=False, p=path: self.navigate_requested.emit(p))
            layout.addWidget(btn)

    def _load_drives(self) -> None:
        if self._drive_thread and self._drive_thread.isRunning():
            return
        self._drive_thread = QThread(parent=self)
        self._drive_worker = _SidebarDriveLoader()
        self._drive_worker.moveToThread(self._drive_thread)
        self._drive_thread.started.connect(self._drive_worker.run)
        self._drive_worker.ready.connect(self.set_drives)
        self._drive_worker.ready.connect(self._drive_thread.quit)
        self._drive_worker.failed.connect(self._drive_thread.quit)
        self._drive_thread.finished.connect(self._drive_worker.deleteLater)
        self._drive_thread.start()

    def _mount_and_navigate(self, drive: UnmountedDrive) -> None:
        if self._mount_thread and self._mount_thread.isRunning():
            return
        self._mount_thread = QThread(parent=self)
        self._mount_worker = _SidebarMountWorker(drive)
        self._mount_worker.moveToThread(self._mount_thread)
        self._mount_thread.started.connect(self._mount_worker.run)
        self._mount_worker.mounted.connect(self._on_mount_success)
        self._mount_worker.mounted.connect(self._mount_thread.quit)
        self._mount_worker.failed.connect(self._mount_thread.quit)
        self._mount_thread.finished.connect(self._mount_worker.deleteLater)
        self._mount_thread.start()

    def _on_mount_success(self, mount_point: str) -> None:
        self.navigate_requested.emit(mount_point)
        self._load_drives()
