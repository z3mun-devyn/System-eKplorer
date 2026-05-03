from datetime import datetime, timezone

import strings
from backends.storage_backend import StorageBackend
from models.database import open_db
from models.storage import Drive

from PyQt6.QtCore import QObject, QThread, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QPainter, QPalette, QPen
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

_PIE_SIZE = 80
_PEN_WIDTH = 12
_PIE_MARGIN = _PEN_WIDTH // 2 + 2

_TILE_MIN_WIDTH = 360
_MAX_TRACKED_COLS = 6

# 5×2 palette for drive labels (tag-editor spec §12)
_LABEL_PALETTE: list[str] = [
    "#e74c3c", "#e67e22", "#f1c40f", "#2ecc71", "#1abc9c",
    "#3498db", "#9b59b6", "#e91e63", "#795548", "#607d8b",
]
_PALETTE_COLS = 5


def _contrast_color(hex_color: str) -> str:
    """Return #000000 or #ffffff for best contrast against hex_color."""
    r = int(hex_color[1:3], 16) / 255
    g = int(hex_color[3:5], 16) / 255
    b = int(hex_color[5:7], 16) / 255

    def lin(c: float) -> float:
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    luminance = 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b)
    return "#000000" if luminance > 0.179 else "#ffffff"


class UsagePie(QWidget):
    """Ring indicator: free arc + used arc drawn as two complementary arcs."""

    def __init__(self, used_pct: float, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._used_pct = max(0.0, min(1.0, used_pct))
        self.setFixedSize(_PIE_SIZE, _PIE_SIZE)

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(Qt.BrushStyle.NoBrush)

        rect = self.rect().adjusted(_PIE_MARGIN, _PIE_MARGIN, -_PIE_MARGIN, -_PIE_MARGIN)
        palette = self.palette()

        free_color = QColor(palette.color(QPalette.ColorRole.WindowText))
        free_color.setAlphaF(0.30)
        free_pen = QPen(free_color)
        free_pen.setWidth(_PEN_WIDTH)
        free_pen.setCapStyle(Qt.PenCapStyle.FlatCap)
        painter.setPen(free_pen)
        painter.drawArc(rect, 0, 360 * 16)

        if self._used_pct > 0:
            used_pen = QPen(palette.color(QPalette.ColorRole.Highlight))
            used_pen.setWidth(_PEN_WIDTH)
            used_pen.setCapStyle(Qt.PenCapStyle.FlatCap)
            painter.setPen(used_pen)
            span = -int(self._used_pct * 360 * 16)
            painter.drawArc(rect, 90 * 16, span)


class LabelModal(QDialog):
    """Small modal for setting a drive label and color."""

    def __init__(
        self,
        drive: Drive,
        parent: QWidget | None = None,
        db_path=None,
    ) -> None:
        super().__init__(parent)
        self._drive = drive
        self._db_path = db_path
        self._selected_color: str = drive.color_hex or _LABEL_PALETTE[0]

        self.setWindowTitle(strings.LABEL_MODAL_TITLE.format(name=drive.name))
        self.setWindowModality(Qt.WindowModality.WindowModal)
        self.setFixedWidth(320)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(16, 16, 16, 16)

        # Label field
        layout.addWidget(QLabel(strings.LABEL_MODAL_FIELD + ":"))
        self._label_edit = QLineEdit(drive.label or "")
        self._label_edit.setPlaceholderText("e.g. Work, Backup, Media…")
        layout.addWidget(self._label_edit)

        # Color picker
        layout.addWidget(QLabel(strings.LABEL_MODAL_COLOR + ":"))
        color_container = QWidget()
        color_grid = QGridLayout(color_container)
        color_grid.setSpacing(6)
        color_grid.setContentsMargins(0, 0, 0, 0)

        self._swatch_buttons: list[QPushButton] = []
        for i, color in enumerate(_LABEL_PALETTE):
            btn = QPushButton()
            btn.setFixedSize(32, 32)
            btn.setCheckable(True)
            btn.setProperty("swatch_color", color)
            btn.clicked.connect(lambda _checked, c=color: self._select_color(c))
            row, col = divmod(i, _PALETTE_COLS)
            color_grid.addWidget(btn, row, col)
            self._swatch_buttons.append(btn)

        layout.addWidget(color_container)
        self._refresh_swatches()

        # Footer buttons
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel
            | QDialogButtonBox.StandardButton.Save
        )
        button_box.accepted.connect(self._save)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def _select_color(self, color: str) -> None:
        self._selected_color = color
        self._refresh_swatches()

    def _refresh_swatches(self) -> None:
        for btn in self._swatch_buttons:
            color = btn.property("swatch_color")
            selected = color == self._selected_color
            border = "3px solid #ffffff" if selected else "2px solid transparent"
            outline = "2px solid #000000" if selected else "none"
            btn.setStyleSheet(
                f"QPushButton {{"
                f"  background-color: {color};"
                f"  border: {border};"
                f"  border-radius: 4px;"
                f"  outline: {outline};"
                f"}}"
            )
            btn.setChecked(selected)

    def _save(self) -> None:
        label = self._label_edit.text().strip()
        now = datetime.now(tz=timezone.utc).isoformat()
        try:
            with open_db(self._db_path) as conn:
                if label:
                    conn.execute(
                        "INSERT OR REPLACE INTO drive_labels"
                        " (device_id, label, color_hex, updated_at)"
                        " VALUES (?, ?, ?, ?)",
                        (self._drive.device_id, label, self._selected_color, now),
                    )
                    self._drive.label = label
                    self._drive.color_hex = self._selected_color
                else:
                    conn.execute(
                        "DELETE FROM drive_labels WHERE device_id = ?",
                        (self._drive.device_id,),
                    )
                    self._drive.label = None
                    self._drive.color_hex = None
        except Exception:
            pass
        self.accept()


class DriveTile(QFrame):
    def __init__(self, drive: Drive, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._drive = drive

        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setFrameShadow(QFrame.Shadow.Raised)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)

        layout = QVBoxLayout(self)
        layout.setSpacing(8)
        layout.setContentsMargins(12, 12, 12, 12)

        # Header row: name on left, badge on right
        header = QHBoxLayout()
        header.setSpacing(8)

        name_label = QLabel(drive.name)
        font = name_label.font()
        font.setBold(True)
        font.setPointSize(font.pointSize() + 1)
        name_label.setFont(font)
        name_label.setWordWrap(True)
        header.addWidget(name_label, stretch=1)

        self._badge = QLabel()
        self._badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._badge.setVisible(False)
        header.addWidget(self._badge, stretch=0)

        layout.addLayout(header)

        info_label = QLabel(f"{drive.device}  ·  {drive.fs_type}")
        info_label.setStyleSheet("color: palette(mid);")
        layout.addWidget(info_label)

        pie_row = QHBoxLayout()
        pie_row.setSpacing(16)
        pie_row.addWidget(UsagePie(drive.used_pct))

        stats = QVBoxLayout()
        stats.setSpacing(2)
        stats.addStretch()
        stats.addWidget(QLabel(f"{drive.used_str} used"))
        stats.addWidget(QLabel(f"{drive.free_str} free"))
        total_label = QLabel(f"of {drive.total_str}")
        total_label.setStyleSheet("color: palette(mid);")
        stats.addWidget(total_label)
        stats.addStretch()

        pie_row.addLayout(stats)
        pie_row.addStretch()
        layout.addLayout(pie_row)

        self._refresh_badge()

    def _refresh_badge(self) -> None:
        label = self._drive.label
        color = self._drive.color_hex
        if label:
            bg = color or _LABEL_PALETTE[-1]
            fg = _contrast_color(bg)
            self._badge.setText(label)
            self._badge.setStyleSheet(
                f"QLabel {{"
                f"  background-color: {bg};"
                f"  color: {fg};"
                f"  border-radius: 8px;"
                f"  padding: 2px 8px;"
                f"  font-size: 11px;"
                f"}}"
            )
            self._badge.setVisible(True)
        else:
            self._badge.setVisible(False)

    def _show_context_menu(self, pos) -> None:
        menu = QMenu(self)

        rename_action = menu.addAction(strings.ACTION_RENAME_LABEL)
        rename_action.triggered.connect(self._open_label_modal)

        menu.addSeparator()

        open_action = menu.addAction(strings.ACTION_OPEN)
        open_action.setEnabled(False)
        open_action.setToolTip(strings.STUB_COMING_M3)

        props_action = menu.addAction(strings.ACTION_PROPERTIES)
        props_action.setEnabled(False)

        if self._drive.fs_type not in {"ext4", "btrfs", "xfs", "ntfs", "vfat", "exfat"}:
            eject_action = menu.addAction(strings.ACTION_EJECT)
            eject_action.setEnabled(False)

        menu.exec(self.mapToGlobal(pos))

    def _open_label_modal(self) -> None:
        modal = LabelModal(self._drive, parent=self)
        modal.accepted.connect(self._refresh_badge)
        modal.open()


class _DriveLoader(QObject):
    drives_ready = pyqtSignal(list)
    load_failed = pyqtSignal(str)

    def run(self) -> None:
        try:
            drives = StorageBackend().list_drives()
            self.drives_ready.emit(drives)
        except Exception as exc:
            self.load_failed.emit(str(exc))


class DashboardView(QWidget):
    """Files-tab landing page: responsive grid of drive tiles."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._tiles: list[DriveTile] = []
        self._col_count: int = 0

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        outer.addWidget(self._scroll)

        container = QWidget()
        clayout = QVBoxLayout(container)
        clayout.setContentsMargins(16, 16, 16, 16)
        clayout.setSpacing(0)

        section_header = QLabel("Physical Devices")
        hfont = section_header.font()
        hfont.setBold(True)
        hfont.setPointSize(hfont.pointSize() + 3)
        section_header.setFont(hfont)
        clayout.addWidget(section_header)
        clayout.addSpacing(12)

        self._status_label = QLabel("Loading drives…")
        self._status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        clayout.addWidget(self._status_label)

        self._grid_widget = QWidget()
        self._grid_widget.setVisible(False)
        self._grid = QGridLayout(self._grid_widget)
        self._grid.setSpacing(12)
        self._grid.setContentsMargins(0, 0, 0, 0)
        clayout.addWidget(self._grid_widget)
        clayout.addStretch()

        self._scroll.setWidget(container)
        self._start_load()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if self._tiles:
            self._relayout()

    def _relayout(self) -> None:
        vp_width = self._scroll.viewport().width()
        if vp_width <= 0:
            return
        spacing = self._grid.spacing()
        available = vp_width
        cols = max(1, (available + spacing) // (_TILE_MIN_WIDTH + spacing))
        if cols == self._col_count:
            return
        self._col_count = cols
        self._rebuild_grid()

    def _rebuild_grid(self) -> None:
        while self._grid.count():
            self._grid.takeAt(0)

        for c in range(_MAX_TRACKED_COLS):
            self._grid.setColumnStretch(c, 0)

        for i, tile in enumerate(self._tiles):
            row, col = divmod(i, self._col_count)
            self._grid.addWidget(tile, row, col)

        for c in range(self._col_count):
            self._grid.setColumnStretch(c, 1)

    def _start_load(self) -> None:
        self._thread = QThread(parent=self)
        self._worker = _DriveLoader()
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.drives_ready.connect(self._on_drives_ready)
        self._worker.load_failed.connect(self._on_load_failed)
        self._worker.drives_ready.connect(self._thread.quit)
        self._worker.load_failed.connect(self._thread.quit)
        self._thread.finished.connect(self._worker.deleteLater)
        self._thread.start()

    def _on_drives_ready(self, drives: list) -> None:
        if not drives:
            self._status_label.setText("No drives found.")
            return

        self._status_label.setVisible(False)
        self._tiles = [DriveTile(drive) for drive in drives]
        self._grid_widget.setVisible(True)
        self._col_count = 0
        self._relayout()

    def _on_load_failed(self, error: str) -> None:
        self._status_label.setText(strings.ERR_PARSE_FAILURE.format(source="storage"))
