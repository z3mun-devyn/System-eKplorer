"""File Manager — dual pane + live file listing.

Toolbar:    [←][→][↑]  AddressBar  [Search]  [view-mode slider]  [Dual Pane]
            Toolbar background = theme.toolbar_surface (AlternateBase).
Content:    NavigationSidebar | left FileView | (splitter) | right pane
Status bar: hover MIME / selection count+size  |  drive-label free-of-total

Right pane stack:
    [0] Browser wrapper  (right nav bar + right FileView)
    [1] PropertiesPanel
    [2] TerminalView

Settings persisted:
    fm.dual_pane.enabled      → "0"/"1"
    fm.dual_pane.right_panel  → "browser"/"properties"/"terminal"
    fm.view_mode              → "details"/"icons_small"/"icons_medium"/"icons_large"
    fm.show_hidden            → "0"/"1"
    fm.alternating_rows       → "0"/"1"   (default "0" — off)
"""
from __future__ import annotations

import subprocess
import shutil
from pathlib import Path

import strings
import theme
from backends.file_ops_backend import (
    ConflictStrategy, FileOpsBackend, FmClipboard,
    _FileOpsWorker,
)
from backends.file_tags_backend import FileTagRepository
from backends.recent_backend import RecentPathsBackend
from backends.settings_backend import SettingsRepository
from backends.trash_backend import TrashBackend, _TrashListWorker, _TrashWorker
from models.file_entry import FileEntry, fmt_size
from models.storage import Drive
from views.address_bar import AddressBar
from views.file_view import FileView
from views.navigation_sidebar import NavigationSidebar
from views.properties_panel import PropertiesPanel
from views.terminal_view import TerminalView
from views.trash_view import TrashView

from PyQt6.QtCore import Qt, QMimeData, QUrl, pyqtSignal
from PyQt6.QtGui import QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QSlider,
    QSplitter,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)
from PyQt6.QtCore import QThread

_RIGHT_BROWSER    = 0
_RIGHT_PROPERTIES = 1
_RIGHT_TERMINAL   = 2

_PANEL_TO_IDX: dict[str, int] = {
    "browser":    _RIGHT_BROWSER,
    "properties": _RIGHT_PROPERTIES,
    "terminal":   _RIGHT_TERMINAL,
}
_IDX_TO_PANEL: dict[int, str] = {v: k for k, v in _PANEL_TO_IDX.items()}

# View mode slider: position 0-3 maps to these mode strings
_SLIDER_MODES = ["details", "icons_small", "icons_medium", "icons_large"]
_MODE_TO_SLIDER: dict[str, int] = {m: i for i, m in enumerate(_SLIDER_MODES)}


# ── FM action panel ───────────────────────────────────────────────────────────

class _FmActionPanel(QWidget):
    """Bottom-docked progress/log panel for file operations.

    Pattern mirrors _ActionPanel from PackagesView (M8).
    Hidden by default; shown when an operation starts.
    """

    dismissed = pyqtSignal()

    _HEIGHT_COLLAPSED = 40
    _HEIGHT_EXPANDED  = 200

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(self._HEIGHT_COLLAPSED)
        self.setVisible(False)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(4)

        top_row = QHBoxLayout()
        self._status_label = QLabel("")
        self._status_label.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        top_row.addWidget(self._status_label)

        self._toggle_btn = QPushButton(strings.ACTION_LOG_SHOW)
        self._toggle_btn.setFixedHeight(24)
        self._toggle_btn.clicked.connect(self._toggle_log)
        top_row.addWidget(self._toggle_btn)

        self._dismiss_btn = QPushButton(strings.FM_OP_DISMISS)
        self._dismiss_btn.setFixedHeight(24)
        self._dismiss_btn.setEnabled(False)
        self._dismiss_btn.clicked.connect(self._on_dismiss)
        top_row.addWidget(self._dismiss_btn)

        layout.addLayout(top_row)

        self._log = QPlainTextEdit()
        self._log.setReadOnly(True)
        self._log.setVisible(False)
        layout.addWidget(self._log)

    def start_action(self, description: str) -> None:
        self._log.clear()
        self._status_label.setText(description)
        self._dismiss_btn.setEnabled(False)
        self.setVisible(True)

    def append_line(self, line: str) -> None:
        self._log.appendPlainText(line)

    def mark_complete(self, message: str) -> None:
        self._status_label.setText(
            f"{strings.FM_OP_DONE}  —  {message}" if message else strings.FM_OP_DONE)
        self._dismiss_btn.setEnabled(True)

    def mark_failed(self, message: str) -> None:
        self._status_label.setText(
            f"{strings.FM_OP_FAILED}  —  {message}")
        if not self._log.isVisible():
            self._toggle_log()
        self._dismiss_btn.setEnabled(True)

    def _toggle_log(self) -> None:
        expand = not self._log.isVisible()
        self._log.setVisible(expand)
        self._toggle_btn.setText(
            strings.ACTION_LOG_HIDE if expand else strings.ACTION_LOG_SHOW)
        self.setFixedHeight(
            self._HEIGHT_EXPANDED if expand else self._HEIGHT_COLLAPSED)

    def _on_dismiss(self) -> None:
        self.setVisible(False)
        self._log.clear()
        self.dismissed.emit()


class FileManagerView(QWidget):
    """File Manager tab.

    navigate_to(path) is the public API — called by MainWindow and the sidebar.
    Always navigates the LEFT pane.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._settings           = SettingsRepository()
        self._current_path       = Path.home()
        self._mounted_drives: list[Drive] = []
        self._clipboard: FmClipboard | None = None
        self._ops_thread: QThread | None = None
        self._ops_worker: _FileOpsWorker | None = None
        self._trash_thread: QThread | None = None
        self._trash_worker: _TrashWorker | None = None
        self._trash_list_thread: QThread | None = None
        self._trash_list_worker = None
        self._in_trash_mode      = False
        self._last_op_target_dir: Path | None = None

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # ── Toolbar ──────────────────────────────────────────────────────────
        self._toolbar = self._build_toolbar()
        main_layout.addWidget(self._toolbar)

        sep_top = QWidget()
        sep_top.setFixedHeight(1)
        sep_top.setStyleSheet("QWidget { background: palette(mid); }")
        main_layout.addWidget(sep_top)

        # ── Content: sidebar + splitter ───────────────────────────────────────
        content = QWidget()
        cl = QHBoxLayout(content)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(0)

        # Outer splitter: sidebar (left, resizable) | content (right, grows)
        self._outer_splitter = QSplitter(Qt.Orientation.Horizontal)
        self._outer_splitter.setHandleWidth(2)

        self._sidebar = NavigationSidebar(fixed_width=None)
        self._sidebar.navigate_requested.connect(self.navigate_to)
        self._sidebar.drives_updated.connect(self._on_drives_updated)
        self._outer_splitter.addWidget(self._sidebar)

        self._splitter = QSplitter(Qt.Orientation.Horizontal)
        self._splitter.setHandleWidth(4)
        self._outer_splitter.addWidget(self._splitter)

        self._outer_splitter.setStretchFactor(0, 0)  # sidebar doesn't absorb extra width
        self._outer_splitter.setStretchFactor(1, 1)  # content does
        self._outer_splitter.splitterMoved.connect(self._on_sidebar_resized)

        cl.addWidget(self._outer_splitter, stretch=1)

        # Left pane: file view OR trash view (switched by _left_stack)
        self._left_view  = FileView()
        self._trash_view = TrashView()
        self._left_stack = QStackedWidget()
        self._left_stack.addWidget(self._left_view)   # index 0
        self._left_stack.addWidget(self._trash_view)  # index 1
        self._splitter.addWidget(self._left_stack)

        # Right pane
        self._right_pane = self._build_right_pane()
        self._splitter.addWidget(self._right_pane)

        main_layout.addWidget(content, stretch=1)

        # ── FM status bar ─────────────────────────────────────────────────────
        self._fm_status_bar, self._status_label, self._free_space_label = (
            self._build_status_bar()
        )
        main_layout.addWidget(self._fm_status_bar)

        # ── Action panel (hidden until an operation starts) ───────────────────
        self._action_panel = _FmActionPanel()
        main_layout.addWidget(self._action_panel)

        # ── Wire nav buttons (after _left_view created) ───────────────────────
        self._back_btn.clicked.connect(self._handle_back)
        self._forward_btn.clicked.connect(self._handle_forward)
        self._up_btn.clicked.connect(self._handle_up)

        self._dual_pane_btn.toggled.connect(self._on_dual_pane_toggled)
        self._switcher_group.idClicked.connect(self._on_panel_selected)

        self._left_view.path_changed.connect(self._on_left_path_changed)
        self._left_view.file_opened.connect(self._on_file_opened)
        self._left_view.selection_changed.connect(self._on_left_selection_changed)
        self._left_view.hover_changed.connect(self._on_hover_changed)
        self._left_view.zoom_requested.connect(self._on_zoom_requested)
        self._left_view.action_requested.connect(self._on_action_requested)
        self._left_view.entries_ready.connect(lambda: self._load_file_tags())

        self._right_view.zoom_requested.connect(self._on_zoom_requested)
        self._left_view.drop_requested.connect(self._on_drop_requested)
        self._right_view.drop_requested.connect(self._on_drop_requested)

        self._address_bar.navigate_requested.connect(self.navigate_to)
        self._search_bar.textChanged.connect(self._left_view.set_search)

        self._trash_view.action_requested.connect(self._on_trash_action)
        self._sidebar.wastebin_action_requested.connect(self._on_wastebin_action)

        # ── Keyboard shortcuts ────────────────────────────────────────────────
        QShortcut(QKeySequence("Ctrl+L"), self).activated.connect(
            self._address_bar.focus_edit)
        QShortcut(QKeySequence("Ctrl+H"), self).activated.connect(
            self._toggle_hidden)
        QShortcut(QKeySequence("Ctrl+X"), self).activated.connect(
            lambda: self._on_action_requested(
                "cut", self._left_view._get_selected_entries()))
        QShortcut(QKeySequence("Ctrl+C"), self).activated.connect(
            lambda: self._on_action_requested(
                "copy", self._left_view._get_selected_entries()))
        QShortcut(QKeySequence("Ctrl+V"), self).activated.connect(
            lambda: self._on_action_requested("paste", []))
        QShortcut(QKeySequence("Delete"), self).activated.connect(
            lambda: self._on_action_requested(
                "trash", self._left_view._get_selected_entries()))
        QShortcut(QKeySequence("Shift+Delete"), self).activated.connect(
            lambda: self._on_action_requested(
                "delete", self._left_view._get_selected_entries()))
        QShortcut(QKeySequence("Ctrl+Shift+N"), self).activated.connect(
            lambda: self._on_action_requested("new_folder", []))
        QShortcut(QKeySequence("F2"), self).activated.connect(
            lambda: self._on_action_requested(
                "rename_inline", self._left_view._get_selected_entries()))

        # ── System clipboard → paste-enabled state ────────────────────────────
        QApplication.clipboard().dataChanged.connect(self._on_clipboard_changed)

        # ── Restore persisted state ────────────────────────────────────────────
        self._restore_state()

    # ── Toolbar builder ───────────────────────────────────────────────────────

    def _build_toolbar(self) -> QWidget:
        tb = QWidget()
        tb.setFixedHeight(48)

        tbl = QHBoxLayout(tb)
        tbl.setContentsMargins(8, 6, 8, 6)
        tbl.setSpacing(4)

        # Nav buttons — larger for easy clicking
        self._back_btn    = QPushButton(strings.FM_TOOLBAR_BACK)
        self._forward_btn = QPushButton(strings.FM_TOOLBAR_FORWARD)
        self._up_btn      = QPushButton(strings.FM_TOOLBAR_UP)
        for btn in (self._back_btn, self._forward_btn, self._up_btn):
            btn.setFixedSize(40, 32)
            btn.setEnabled(False)
        # connections wired in __init__ after _left_view created

        tbl.addWidget(self._back_btn)
        tbl.addWidget(self._forward_btn)
        tbl.addWidget(self._up_btn)
        tbl.addSpacing(4)

        # Address bar: permanently dark, always shows editable POSIX path
        self._address_bar = AddressBar(self._settings)
        self._address_bar.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._address_bar.setFixedHeight(28)
        tbl.addWidget(self._address_bar, stretch=1)
        tbl.addSpacing(4)

        # Search bar — matching inset visual treatment
        self._search_bar = QLineEdit()
        self._search_bar.setObjectName("searchBar")
        self._search_bar.setStyleSheet(
            "QLineEdit { background: palette(base);"
            " border: 1px solid palette(mid); border-radius: 4px;"
            " padding: 2px 4px; }"
        )
        self._search_bar.setPlaceholderText(strings.FM_TOOLBAR_SEARCH_HINT)
        self._search_bar.setFixedWidth(180)
        self._search_bar.setFixedHeight(28)
        self._search_bar.setClearButtonEnabled(True)
        tbl.addWidget(self._search_bar)
        tbl.addSpacing(8)

        # View mode slider (4 stops: details / icons_small / icons_medium / icons_large)
        tbl.addWidget(self._build_view_slider())
        tbl.addSpacing(12)

        # Dual pane toggle (separate from slider group)
        self._dual_pane_btn = QPushButton(strings.FM_DUAL_PANE_TOGGLE)
        self._dual_pane_btn.setCheckable(True)
        self._dual_pane_btn.setToolTip(strings.FM_DUAL_PANE_TOOLTIP)
        self._dual_pane_btn.setFixedHeight(28)
        tbl.addWidget(self._dual_pane_btn)

        return tb

    def _build_view_slider(self) -> QWidget:
        """Build the 4-stop view mode compound widget (slider + icon row)."""
        container = QWidget()
        container.setFixedWidth(140)
        sv = QVBoxLayout(container)
        sv.setContentsMargins(2, 0, 2, 0)
        sv.setSpacing(1)

        self._view_slider = QSlider(Qt.Orientation.Horizontal)
        self._view_slider.setRange(0, 3)
        self._view_slider.setSingleStep(1)
        self._view_slider.setPageStep(1)
        self._view_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        self._view_slider.setTickInterval(1)
        self._view_slider.setFixedHeight(18)
        self._view_slider.valueChanged.connect(self._on_slider_changed)
        sv.addWidget(self._view_slider)

        icons_row = QHBoxLayout()
        icons_row.setContentsMargins(0, 0, 0, 0)
        icons_row.setSpacing(0)
        for icon_char in strings.FM_VIEWSLIDER_ICONS:
            lbl = QLabel(icon_char)
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setStyleSheet("font-size: 9px; color: palette(windowText);")
            icons_row.addWidget(lbl, stretch=1)
        sv.addLayout(icons_row)

        return container

    # ── Right pane builder ────────────────────────────────────────────────────

    def _build_right_pane(self) -> QWidget:
        pane = QWidget()
        layout = QVBoxLayout(pane)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Switcher button row
        switcher = QWidget()
        sw_layout = QHBoxLayout(switcher)
        sw_layout.setContentsMargins(4, 4, 4, 4)
        sw_layout.setSpacing(2)

        self._btn_browser    = QPushButton(strings.FM_RIGHT_PANE_BROWSER)
        self._btn_properties = QPushButton(strings.FM_RIGHT_PANE_PROPERTIES)
        self._btn_terminal   = QPushButton(strings.FM_RIGHT_PANE_TERMINAL)

        self._switcher_group = QButtonGroup(self)
        self._switcher_group.setExclusive(True)
        for idx, btn in enumerate(
            (self._btn_browser, self._btn_properties, self._btn_terminal)
        ):
            btn.setCheckable(True)
            btn.setFlat(True)
            btn.setFixedHeight(26)
            btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
            sw_layout.addWidget(btn)
            self._switcher_group.addButton(btn, idx)

        sw_layout.addStretch()
        layout.addWidget(switcher)

        sep = QWidget()
        sep.setFixedHeight(1)
        sep.setStyleSheet("QWidget { background: palette(mid); }")
        layout.addWidget(sep)

        # Stacked panels
        self._right_stack = QStackedWidget()

        # [0] Browser: compact nav bar + FileView
        browser_wrapper = QWidget()
        bw_layout = QVBoxLayout(browser_wrapper)
        bw_layout.setContentsMargins(0, 0, 0, 0)
        bw_layout.setSpacing(0)

        self._right_nav_bar = self._build_right_nav_bar()
        bw_layout.addWidget(self._right_nav_bar)

        nav_sep = QWidget()
        nav_sep.setFixedHeight(1)
        nav_sep.setStyleSheet("QWidget { background: palette(mid); }")
        bw_layout.addWidget(nav_sep)

        self._right_view = FileView()
        bw_layout.addWidget(self._right_view, stretch=1)
        self._right_address_bar.navigate_requested.connect(
            lambda p: self._right_view.navigate(Path(p)))

        self._right_stack.addWidget(browser_wrapper)          # index 0

        # [1] Properties panel
        self._properties_panel = PropertiesPanel()
        self._right_stack.addWidget(self._properties_panel)   # index 1

        # [2] Terminal (independent instance)
        self._right_terminal = TerminalView()
        self._right_stack.addWidget(self._right_terminal)     # index 2

        layout.addWidget(self._right_stack, stretch=1)
        return pane

    def _build_right_nav_bar(self) -> QWidget:
        """Compact ←→↑ + path label for the right browser pane."""
        bar = QWidget()
        bar.setFixedHeight(30)
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(2)

        self._right_back_btn    = QPushButton(strings.FM_TOOLBAR_BACK)
        self._right_forward_btn = QPushButton(strings.FM_TOOLBAR_FORWARD)
        self._right_up_btn      = QPushButton(strings.FM_TOOLBAR_UP)
        for btn in (self._right_back_btn, self._right_forward_btn,
                    self._right_up_btn):
            btn.setFixedSize(28, 24)
            btn.setEnabled(False)

        layout.addWidget(self._right_back_btn)
        layout.addWidget(self._right_forward_btn)
        layout.addWidget(self._right_up_btn)
        layout.addSpacing(4)

        self._right_address_bar = AddressBar(self._settings)
        self._right_address_bar.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        layout.addWidget(self._right_address_bar, stretch=1)

        return bar

    # ── Status bar builder ────────────────────────────────────────────────────

    def _build_status_bar(self) -> tuple[QWidget, QLabel, QLabel]:
        bar = QWidget()
        bar.setFixedHeight(24)
        bar.setStyleSheet(
            "QWidget { background: palette(window);"
            " border-top: 1px solid palette(mid); }"
        )
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(8, 0, 8, 0)

        status = QLabel("")
        status.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        layout.addWidget(status)

        free = QLabel("")
        free.setAlignment(Qt.AlignmentFlag.AlignRight)
        free.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        layout.addWidget(free)

        return bar, status, free

    # ── State persistence ─────────────────────────────────────────────────────

    def _restore_state(self) -> None:
        # Right panel type
        saved_panel = self._settings.get(strings.FM_SETTING_RIGHT_PANEL) or "browser"
        panel_idx = _PANEL_TO_IDX.get(saved_panel, _RIGHT_BROWSER)
        self._right_stack.setCurrentIndex(panel_idx)
        btn = self._switcher_group.button(panel_idx)
        if btn:
            btn.setChecked(True)

        # Dual pane
        enabled = self._settings.get(strings.FM_SETTING_DUAL_PANE) == "1"
        self._dual_pane_btn.blockSignals(True)
        self._dual_pane_btn.setChecked(enabled)
        self._dual_pane_btn.blockSignals(False)
        self._right_pane.setVisible(enabled)

        # View mode (slider)
        view_mode = self._settings.get(strings.FM_SETTING_VIEW_MODE) or "details"
        self._apply_view_mode(view_mode, save=False)

        # Hidden files
        show_hidden = self._settings.get(strings.FM_SETTING_SHOW_HIDDEN) == "1"
        self._set_show_hidden(show_hidden, save=False)

        # Alternating rows (off by default; Configure eKplorer will write this key)
        alt_rows = self._settings.get(strings.FM_SETTING_ALT_ROWS) == "1"
        self._left_view.set_alternating_rows(alt_rows)
        self._right_view.set_alternating_rows(alt_rows)

        # Wire right pane nav (must happen after _right_view created and wired)
        self._right_back_btn.clicked.connect(self._right_view.navigate_back)
        self._right_forward_btn.clicked.connect(self._right_view.navigate_forward)
        self._right_up_btn.clicked.connect(self._right_view.navigate_up)
        self._right_view.path_changed.connect(self._on_right_path_changed)

        # Sidebar width
        saved_w = self._settings.get(strings.FM_SETTING_SIDEBAR_WIDTH)
        try:
            sidebar_w = int(saved_w) if saved_w else 220
        except ValueError:
            sidebar_w = 220
        self._outer_splitter.setSizes([sidebar_w, 1])

        # Initial address bar / nav buttons / free space
        self._address_bar.set_path(self._current_path)
        self._update_nav_buttons()
        self._update_free_space(self._current_path)

    # ── Signal handlers ───────────────────────────────────────────────────────

    def closeEvent(self, event) -> None:
        self._properties_panel.shutdown()
        self._drain_trash_thread()
        self._drain_trash_list_thread()
        super().closeEvent(event)

    def _on_dual_pane_toggled(self, enabled: bool) -> None:
        if not enabled:
            self._properties_panel.shutdown()
        self._right_pane.setVisible(enabled)
        if enabled:
            total = self._splitter.width()
            if total > 0:
                half = total // 2
                self._splitter.setSizes([half, half])
        self._settings.set(strings.FM_SETTING_DUAL_PANE, "1" if enabled else "0")

    def _on_panel_selected(self, idx: int) -> None:
        if idx != _RIGHT_PROPERTIES:
            self._properties_panel.shutdown()
        self._right_stack.setCurrentIndex(idx)
        self._settings.set(
            strings.FM_SETTING_RIGHT_PANEL, _IDX_TO_PANEL.get(idx, "browser"))

    def _on_slider_changed(self, value: int) -> None:
        if 0 <= value < len(_SLIDER_MODES):
            self._apply_view_mode(_SLIDER_MODES[value])

    def _on_left_path_changed(self, path: str) -> None:
        self._current_path = Path(path)
        self._address_bar.set_path(path)
        self._update_nav_buttons()
        self._update_free_space(Path(path))
        RecentPathsBackend().record_location(path)
        self._sidebar.refresh_recent()

    def _on_file_opened(self, path: str) -> None:
        RecentPathsBackend().record_file(path)
        self._sidebar.refresh_recent()

    def _on_left_selection_changed(self, entries: list[FileEntry]) -> None:
        if not entries:
            self._status_label.setText("")
            if self._right_stack.currentIndex() == _RIGHT_PROPERTIES:
                self._properties_panel.show_placeholder()
            return
        if len(entries) == 1:
            total = entries[0].size or 0
            text = strings.FM_STATUS_SELECTED_ONE.format(size=fmt_size(total))
        else:
            total = sum(e.size or 0 for e in entries)
            text = strings.FM_STATUS_SELECTED_MANY.format(
                count=len(entries), size=fmt_size(total))
        self._status_label.setText(text)

        if (self._right_stack.currentIndex() == _RIGHT_PROPERTIES
                and len(entries) == 1):
            self._properties_panel.populate_general(entries[0])

    def _on_hover_changed(self, entry: FileEntry | None) -> None:
        if entry is None:
            self._status_label.setText("")
        else:
            from models.file_entry import mime_label
            self._status_label.setText(
                strings.FM_STATUS_HOVER_MIME.format(
                    mime=mime_label(entry.mime_type, entry.is_dir)))

    def _on_right_path_changed(self, path: str) -> None:
        self._right_address_bar.set_path(path)
        self._right_back_btn.setEnabled(self._right_view.can_go_back())
        self._right_forward_btn.setEnabled(self._right_view.can_go_forward())
        self._right_up_btn.setEnabled(self._right_view.can_go_up())

    def _on_sidebar_resized(self, pos: int, index: int) -> None:
        sizes = self._outer_splitter.sizes()
        if sizes:
            self._settings.set(strings.FM_SETTING_SIDEBAR_WIDTH, str(sizes[0]))

    def _on_drives_updated(self, mounted: list, unmounted: list) -> None:
        self._mounted_drives = mounted
        self._update_free_space(self._current_path)

    def _on_zoom_requested(self, delta: int) -> None:
        new_val = max(0, min(3, self._view_slider.value() + delta))
        if new_val != self._view_slider.value():
            self._view_slider.setValue(new_val)

    # ── File operations dispatcher ────────────────────────────────────────────

    def _on_action_requested(self, action: str, entries: list) -> None:
        """Central dispatcher for all context menu and keyboard actions."""
        from models.file_entry import FileEntry
        path_list = [e.path for e in entries if isinstance(e, FileEntry)]

        if action == "open":
            for e in entries:
                if isinstance(e, FileEntry):
                    subprocess.Popen(["xdg-open", str(e.path)])

        elif action == "open_with":
            if entries and isinstance(entries[0], FileEntry):
                cmd, ok = QInputDialog.getText(
                    self, strings.FM_CTX_OPEN_WITH, "Application command:")
                if ok and cmd.strip():
                    subprocess.Popen(
                        cmd.strip().split() + [str(entries[0].path)])

        elif action == "open_admin":
            if path_list:
                result = FileOpsBackend().open_as_admin(path_list[0])
                if not result.ok:
                    QMessageBox.warning(
                        self, strings.FM_CTX_OPEN_ADMIN, result.message)

        elif action in ("cut", "copy"):
            if path_list:
                self._clipboard = FmClipboard(operation=action, paths=path_list)
                self._set_system_clipboard(action, path_list)
                # paste-enabled state updated by _on_clipboard_changed signal

        elif action == "copy_path":
            if path_list:
                QApplication.clipboard().setText(
                    "\n".join(str(p) for p in path_list))

        elif action == "copy_name":
            if path_list:
                QApplication.clipboard().setText(
                    "\n".join(p.name for p in path_list))

        elif action == "paste":
            self._do_paste()

        elif action == "rename":
            # From delegate: entries = [path_str, new_name]
            if len(entries) == 2 and isinstance(entries[0], str):
                self._do_rename(Path(entries[0]), entries[1])

        elif action == "rename_inline":
            # F2 or context menu → open inline editor on Name column
            if entries and isinstance(entries[0], FileEntry):
                fv = self._left_view
                proxy_idx = None
                for row in range(fv._proxy.rowCount()):
                    src = fv._proxy.mapToSource(
                        fv._proxy.index(row, 0))
                    e = fv._model.data(src, fv._model.UserRole + 2
                                       if hasattr(fv._model, "UserRole") else None)
                    break
                # Simpler: just find the row by entry name
                target_name = entries[0].name
                for row in range(fv._proxy.rowCount()):
                    src = fv._proxy.mapToSource(fv._proxy.index(row, 0))
                    from views.file_view import _ENTRY_ROLE, _COL_NAME
                    e = fv._model.data(src, _ENTRY_ROLE)
                    if e and e.name == target_name:
                        proxy_name_idx = fv._proxy.index(row, _COL_NAME)
                        fv._tree.edit(proxy_name_idx)
                        break

        elif action == "trash":
            if path_list:
                self._start_file_op("trash", path_list)

        elif action == "delete":
            if path_list:
                self._confirm_and_delete(path_list)

        elif action == "new_folder":
            name, ok = QInputDialog.getText(
                self, strings.FM_NEW_FOLDER_TITLE,
                strings.FM_NEW_FOLDER_LABEL)
            if ok and name.strip():
                result = FileOpsBackend().create_folder(
                    self._current_path, name.strip())
                if result.ok:
                    self._refresh_left()
                    self._sidebar.refresh_expanded_nodes()
                else:
                    QMessageBox.warning(
                        self, strings.FM_NEW_FOLDER_TITLE, result.message)

        elif action == "new_file":
            name, ok = QInputDialog.getText(
                self, strings.FM_NEW_FILE_TITLE,
                strings.FM_NEW_FILE_LABEL)
            if ok and name.strip():
                result = FileOpsBackend().create_file(
                    self._current_path, name.strip())
                if result.ok:
                    self._refresh_left()
                else:
                    QMessageBox.warning(
                        self, strings.FM_NEW_FILE_TITLE, result.message)

        elif action == "assign_tags":
            self._open_file_tag_modal(entries)

        elif action == "properties":
            if entries and isinstance(entries[0], FileEntry):
                self._properties_panel.populate_general(entries[0])
                # Switch right pane to properties if dual pane is on
                if self._right_pane.isVisible():
                    self._right_stack.setCurrentIndex(_RIGHT_PROPERTIES)
                    self._btn_properties.setChecked(True)

    def _do_paste(self) -> None:
        # ── Read from system clipboard (primary source of truth) ──────────────
        system_mime = QApplication.clipboard().mimeData()
        if system_mime and system_mime.hasUrls():
            urls = [u for u in system_mime.urls() if u.isLocalFile()]
            src_paths = [p for p in (Path(u.toLocalFile()) for u in urls)
                         if p.exists()]
            # Determine copy vs move from cut markers
            is_cut = False
            if system_mime.hasFormat("application/x-kde-cutselection"):
                is_cut = (bytes(system_mime.data(
                    "application/x-kde-cutselection")).decode(errors="replace")
                    .strip() == "1")
            if not is_cut and system_mime.hasFormat("x-special/gnome-copied-files"):
                gnome = bytes(system_mime.data(
                    "x-special/gnome-copied-files")).decode(errors="replace")
                is_cut = gnome.startswith("cut\n")
            op = "move" if is_cut else "copy"
        elif self._clipboard and not self._clipboard.is_empty():
            # Fall back to internal clipboard (e.g. cut from same session)
            src_paths = [p for p in self._clipboard.paths if p.exists()]
            op = "copy" if self._clipboard.operation == "copy" else "move"
        else:
            return

        if not src_paths:
            return

        dst_dir = self._current_path
        conflicts = FileOpsBackend().find_conflicts(src_paths, dst_dir)
        conflict_strategy = ConflictStrategy.RENAME
        if conflicts:
            conflict_strategy = self._ask_conflict_strategy(conflicts)
            if conflict_strategy is None:
                return  # cancelled
        desc = strings.FM_OP_COPYING if op == "copy" else strings.FM_OP_MOVING
        self._start_file_op(op, src_paths, dst_dir=dst_dir,
                            conflict=conflict_strategy, desc=desc)
        if op == "move":
            # Clear system clipboard so other apps know the cut is consumed
            QApplication.clipboard().clear()
            self._clipboard = None

    def _ask_conflict_strategy(self, conflicts: list[str]) -> str | None:
        dlg = QMessageBox(self)
        dlg.setWindowTitle(strings.FM_CONFLICT_TITLE)
        dlg.setText(strings.FM_CONFLICT_MSG.format(n=len(conflicts)))
        dlg.setInformativeText(", ".join(conflicts[:5])
                               + ("…" if len(conflicts) > 5 else ""))
        skip_btn    = dlg.addButton(strings.FM_CONFLICT_SKIP,
                                    QMessageBox.ButtonRole.AcceptRole)
        replace_btn = dlg.addButton(strings.FM_CONFLICT_REPLACE,
                                    QMessageBox.ButtonRole.AcceptRole)
        rename_btn  = dlg.addButton(strings.FM_CONFLICT_RENAME,
                                    QMessageBox.ButtonRole.AcceptRole)
        dlg.addButton(QMessageBox.StandardButton.Cancel)
        dlg.exec()
        clicked = dlg.clickedButton()
        if clicked is skip_btn:
            return ConflictStrategy.SKIP
        if clicked is replace_btn:
            return ConflictStrategy.REPLACE
        if clicked is rename_btn:
            return ConflictStrategy.RENAME
        return None  # cancelled

    def _confirm_and_delete(self, paths: list[Path]) -> None:
        n = len(paths)
        if n == 1:
            msg = strings.FM_DELETE_ONE.format(name=paths[0].name)
        else:
            msg = strings.FM_DELETE_MANY.format(n=n)
        box = QMessageBox(
            QMessageBox.Icon.Warning, strings.FM_DELETE_TITLE,
            msg, parent=self)
        box.setInformativeText(strings.FM_DELETE_WARNING)
        box.addButton(strings.FM_DELETE_YES,
                      QMessageBox.ButtonRole.DestructiveRole)
        cancel = box.addButton(strings.FM_DELETE_NO,
                               QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(cancel)
        box.exec()
        if box.clickedButton() is not cancel:
            self._start_file_op("delete", paths)

    def _do_rename(self, src: Path, new_name: str) -> None:
        result = FileOpsBackend().rename_path(src, new_name)
        if result.ok:
            self._refresh_left()
            self._sidebar.refresh_expanded_nodes()
        else:
            QMessageBox.warning(self, strings.FM_RENAME_TITLE, result.message)

    def _start_file_op(
        self,
        op: str,
        src_paths: list[Path],
        *,
        dst_dir: Path | None = None,
        conflict: str = ConflictStrategy.RENAME,
        desc: str = "",
    ) -> None:
        if not desc:
            desc = {
                "copy":   strings.FM_OP_COPYING,
                "move":   strings.FM_OP_MOVING,
                "trash":  strings.FM_OP_TRASHING,
                "delete": strings.FM_OP_DELETING,
            }.get(op, op)

        self._action_panel.start_action(desc)
        self._last_op_target_dir = dst_dir or self._current_path

        if self._ops_thread and self._ops_thread.isRunning():
            self._ops_thread.quit()

        self._ops_thread = QThread(parent=self)
        self._ops_worker = _FileOpsWorker(
            op,
            src_paths=src_paths,
            dst_dir=dst_dir or self._current_path,
            conflict=conflict,
        )
        self._ops_worker.moveToThread(self._ops_thread)
        self._ops_thread.started.connect(self._ops_worker.run)
        self._ops_worker.output_line.connect(self._action_panel.append_line)
        self._ops_worker.succeeded.connect(self._on_ops_succeeded)
        self._ops_worker.failed.connect(self._on_ops_failed)
        self._ops_worker.succeeded.connect(self._ops_thread.quit)
        self._ops_worker.failed.connect(self._ops_thread.quit)
        self._ops_thread.finished.connect(self._ops_worker.deleteLater)
        self._ops_thread.start()

    def _on_drop_requested(
        self, source_paths: list, target_dir: str, copy: bool,
    ) -> None:
        srcs = [Path(p) for p in source_paths if Path(p).exists()]
        if not srcs:
            return
        dst = Path(target_dir)
        if not dst.is_dir():
            return
        op = "copy" if copy else "move"
        conflicts = FileOpsBackend().find_conflicts(srcs, dst)
        conflict_strategy = ConflictStrategy.RENAME
        if conflicts:
            conflict_strategy = self._ask_conflict_strategy(conflicts)
            if conflict_strategy is None:
                return
        desc = strings.FM_OP_COPYING if copy else strings.FM_OP_MOVING
        self._start_file_op(op, srcs, dst_dir=dst,
                            conflict=conflict_strategy, desc=desc)

    def _on_ops_succeeded(self, message: str) -> None:
        self._action_panel.mark_complete(message)
        self._refresh_panes_for_dir(self._last_op_target_dir)
        self._sidebar.refresh_expanded_nodes()
        self._sidebar.update_wastebin_icon()

    def _on_ops_failed(self, message: str) -> None:
        self._action_panel.mark_failed(message)
        self._refresh_panes_for_dir(self._last_op_target_dir)

    def _refresh_left(self) -> None:
        if self._left_view._shown:
            self._left_view._load()

    def _refresh_right(self) -> None:
        if self._right_view._shown:
            self._right_view._load()

    def _refresh_panes_for_dir(self, target_dir: Path | None) -> None:
        """Reload any pane whose current directory equals target_dir.

        Falls back to refreshing both panes when target_dir is unknown.
        """
        if target_dir is None:
            self._refresh_left()
            self._refresh_right()
            return
        if self._left_view._shown and self._left_view.current_path == target_dir:
            self._left_view._load()
        if self._right_view._shown and self._right_view.current_path == target_dir:
            self._right_view._load()

    def _set_system_clipboard(self, op: str, paths: list[Path]) -> None:
        """Write file paths to the system clipboard with KDE and GNOME cut markers."""
        urls = [QUrl.fromLocalFile(str(p)) for p in paths]
        url_bytes = "\n".join(u.toString() for u in urls).encode()
        mime = QMimeData()
        mime.setUrls(urls)
        mime.setText("\n".join(str(p) for p in paths))
        if op == "cut":
            mime.setData("application/x-kde-cutselection", b"1")
            mime.setData("x-special/gnome-copied-files", b"cut\n" + url_bytes)
        else:
            mime.setData("x-special/gnome-copied-files", b"copy\n" + url_bytes)
        QApplication.clipboard().setMimeData(mime)

    def _on_clipboard_changed(self) -> None:
        """Enable/disable Paste based on whether the system clipboard has file URLs."""
        mime = QApplication.clipboard().mimeData()
        has_files = mime is not None and mime.hasUrls()
        has_internal = self._clipboard is not None and not self._clipboard.is_empty()
        enabled = has_files or has_internal
        self._left_view.set_paste_enabled(enabled)
        self._right_view.set_paste_enabled(enabled)

    def _load_file_tags(self) -> None:
        """Bulk-load tags for the current directory entries and push to the left view."""
        entries = self._left_view._model._entries
        if not entries:
            return
        paths = [str(e.path) for e in entries]
        tag_map = FileTagRepository().bulk_load(paths)
        self._left_view.set_tag_map(tag_map)

    def _open_file_tag_modal(self, entries: list[FileEntry]) -> None:
        if not entries:
            return
        from views.file_tag_modal import FileTagModal
        modal = FileTagModal(entries, parent=self)
        modal.saved.connect(self._load_file_tags)
        modal.exec()

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _update_nav_buttons(self) -> None:
        if self._in_trash_mode:
            self._back_btn.setEnabled(True)
            self._forward_btn.setEnabled(False)
            self._up_btn.setEnabled(True)
        else:
            self._back_btn.setEnabled(self._left_view.can_go_back())
            self._forward_btn.setEnabled(self._left_view.can_go_forward())
            self._up_btn.setEnabled(self._left_view.can_go_up())

    def _update_free_space(self, path: Path) -> None:
        path_str = str(path)
        best_drive: Drive | None = None
        best_len = 0
        for drive in self._mounted_drives:
            mp = drive.mount_point
            if path_str.startswith(mp) and len(mp) > best_len:
                best_drive = drive
                best_len = len(mp)

        if best_drive:
            label = best_drive.label or best_drive.mount_point
            free  = fmt_size(best_drive.free_bytes)
            total = fmt_size(best_drive.total_bytes)
            self._free_space_label.setText(
                strings.FM_STATUS_FREE.format(name=label, free=free, total=total))
        else:
            try:
                usage = shutil.disk_usage(str(path))
                free  = fmt_size(usage.free)
                total = fmt_size(usage.total)
                self._free_space_label.setText(f"{free} free of {total}")
            except OSError:
                self._free_space_label.setText("")

    def _apply_view_mode(self, mode: str, *, save: bool = True) -> None:
        self._left_view.set_view_mode(mode)
        self._right_view.set_view_mode(mode)
        slider_val = _MODE_TO_SLIDER.get(mode, 0)
        self._view_slider.blockSignals(True)
        self._view_slider.setValue(slider_val)
        self._view_slider.blockSignals(False)
        if save:
            self._settings.set(strings.FM_SETTING_VIEW_MODE, mode)

    def _set_show_hidden(self, show: bool, *, save: bool = True) -> None:
        self._left_view.set_show_hidden(show)
        self._right_view.set_show_hidden(show)
        if save:
            self._settings.set(strings.FM_SETTING_SHOW_HIDDEN, "1" if show else "0")

    def _toggle_hidden(self) -> None:
        current = self._settings.get(strings.FM_SETTING_SHOW_HIDDEN) == "1"
        self._set_show_hidden(not current)

    # ── Public API ────────────────────────────────────────────────────────────

    def navigate_to(self, path: str) -> None:
        """Navigate the left pane to path (called by MainWindow and sidebar)."""
        if path == strings.TRASH_SENTINEL:
            self._enter_trash_mode()
            return
        if self._in_trash_mode:
            self._exit_trash_mode()
        RecentPathsBackend().record_location(path)
        self._sidebar.refresh_recent()
        self._left_view.navigate(Path(path))
        self._sidebar.refresh_expanded_nodes()

    # ── Trash mode ────────────────────────────────────────────────────────────

    def _enter_trash_mode(self) -> None:
        self._properties_panel.shutdown()
        self._in_trash_mode = True
        self._left_stack.setCurrentIndex(1)
        self._address_bar.set_path(strings.TRASH_ADDRESS_LABEL)
        self._back_btn.setEnabled(True)
        self._forward_btn.setEnabled(False)
        self._up_btn.setEnabled(True)
        self._load_trash()
        self._sidebar.update_wastebin_icon()

    def _exit_trash_mode(self) -> None:
        self._in_trash_mode = False
        self._left_stack.setCurrentIndex(0)
        self._address_bar.set_path(self._current_path)
        self._update_nav_buttons()

    def _drain_trash_thread(self) -> None:
        t = self._trash_thread
        if t is not None:
            try:
                if t.isRunning():
                    t.quit()
                    if not t.wait(3000):
                        t.terminate()
                        t.wait()
            except RuntimeError:
                pass
        self._trash_thread = None
        self._trash_worker = None

    def _drain_trash_list_thread(self) -> None:
        t = self._trash_list_thread
        if t is not None:
            try:
                if t.isRunning():
                    t.quit()
                    if not t.wait(3000):
                        t.terminate()
                        t.wait()
            except RuntimeError:
                pass
        self._trash_list_thread = None
        self._trash_list_worker = None

    def _load_trash(self) -> None:
        # Guard re-entrancy: if a list is already in flight, skip
        try:
            if self._trash_list_thread is not None and self._trash_list_thread.isRunning():
                return
        except RuntimeError:
            pass

        self._trash_view.show_loading()

        self._trash_list_thread = QThread(parent=self)
        self._trash_list_worker = _TrashListWorker()
        self._trash_list_worker.moveToThread(self._trash_list_thread)
        self._trash_list_thread.started.connect(self._trash_list_worker.run)
        self._trash_list_worker.ready.connect(self._on_trash_list_ready)
        self._trash_list_worker.ready.connect(self._trash_list_thread.quit)
        self._trash_list_worker.failed.connect(self._on_trash_list_failed)
        self._trash_list_worker.failed.connect(self._trash_list_thread.quit)
        self._trash_list_thread.finished.connect(self._trash_list_worker.deleteLater)
        self._trash_list_thread.finished.connect(self._trash_list_thread.deleteLater)
        self._trash_list_thread.start()

    def _on_trash_list_ready(self, entries: list) -> None:
        self._trash_list_thread = None
        self._trash_list_worker = None
        self._trash_view.load(entries)

    def _on_trash_list_failed(self, msg: str) -> None:
        self._trash_list_thread = None
        self._trash_list_worker = None
        self._trash_view.show_error(msg)

    def _handle_back(self) -> None:
        if self._in_trash_mode:
            self._exit_trash_mode()
        else:
            self._left_view.navigate_back()

    def _handle_forward(self) -> None:
        if not self._in_trash_mode:
            self._left_view.navigate_forward()

    def _handle_up(self) -> None:
        if self._in_trash_mode:
            self._exit_trash_mode()
            self._left_view.navigate(Path.home())
        else:
            self._left_view.navigate_up()

    def _on_trash_action(self, action: str, entries: list) -> None:
        if action == "restore":
            self._start_trash_op("restore", entries)
        elif action == "delete_permanently":
            self._confirm_and_trash_delete(entries)

    def _on_wastebin_action(self, action: str) -> None:
        if action == "restore_all":
            entries = self._trash_view.all_entries()
            if entries:
                self._start_trash_op("restore", entries)
        elif action == "empty":
            self._confirm_and_empty_trash()

    def _confirm_and_empty_trash(self) -> None:
        n = len(self._trash_view.all_entries())
        if n == 0:
            return
        msg = strings.TRASH_EMPTY_MSG.format(n=n)
        box = QMessageBox(
            QMessageBox.Icon.Warning, strings.TRASH_EMPTY_TITLE,
            msg, parent=self)
        yes = box.addButton(strings.TRASH_EMPTY_YES,
                            QMessageBox.ButtonRole.DestructiveRole)
        cancel = box.addButton(strings.TRASH_EMPTY_NO,
                               QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(cancel)
        box.exec()
        if box.clickedButton() is not cancel:
            self._start_trash_op("empty", [])

    def _confirm_and_trash_delete(self, entries: list) -> None:
        n = len(entries)
        if n == 1:
            msg = strings.TRASH_DELETE_ONE.format(name=entries[0].name)
        else:
            msg = strings.TRASH_DELETE_MANY.format(n=n)
        box = QMessageBox(
            QMessageBox.Icon.Warning, strings.TRASH_DELETE_TITLE,
            msg, parent=self)
        yes = box.addButton(strings.TRASH_DELETE_YES,
                            QMessageBox.ButtonRole.DestructiveRole)
        cancel = box.addButton(strings.TRASH_DELETE_NO,
                               QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(cancel)
        box.exec()
        if box.clickedButton() is not cancel:
            self._start_trash_op("delete_permanently", entries)

    def _start_trash_op(self, op: str, entries: list) -> None:
        desc = {
            "restore":            strings.TRASH_OP_RESTORING,
            "empty":              strings.TRASH_OP_EMPTYING,
            "delete_permanently": strings.TRASH_OP_DELETING,
        }.get(op, op)
        self._action_panel.start_action(desc)

        self._drain_trash_thread()

        self._trash_thread = QThread(parent=self)
        self._trash_worker = _TrashWorker(op, entries)
        self._trash_worker.moveToThread(self._trash_thread)
        self._trash_thread.started.connect(self._trash_worker.run)
        self._trash_worker.output_line.connect(self._action_panel.append_line)
        self._trash_worker.succeeded.connect(self._on_trash_succeeded)
        self._trash_worker.failed.connect(self._on_trash_failed)
        self._trash_worker.succeeded.connect(self._trash_thread.quit)
        self._trash_worker.failed.connect(self._trash_thread.quit)
        self._trash_thread.finished.connect(self._trash_worker.deleteLater)
        self._trash_thread.finished.connect(self._trash_thread.deleteLater)
        self._trash_thread.start()

    def _on_trash_succeeded(self, message: str) -> None:
        self._action_panel.mark_complete(message)
        if self._in_trash_mode:
            self._load_trash()
        self._refresh_left()
        self._refresh_right()
        self._sidebar.refresh_expanded_nodes()
        self._sidebar.update_wastebin_icon()

    def _on_trash_failed(self, message: str) -> None:
        self._action_panel.mark_failed(message)
        if self._in_trash_mode:
            self._load_trash()
        self._refresh_left()
        self._refresh_right()
        self._sidebar.update_wastebin_icon()
