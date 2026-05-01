import strings
from backends.storage_backend import StorageBackend
from models.storage import Drive

from PyQt6.QtCore import QObject, QThread, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QPainter, QPalette, QPen
from PyQt6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

_PIE_SIZE = 80
_PEN_WIDTH = 12
_PIE_MARGIN = _PEN_WIDTH // 2 + 2

_TILE_MIN_WIDTH = 360       # minimum tile width for column-count calculation
_MAX_TRACKED_COLS = 6       # upper bound for resetting column stretches


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

        # Free arc — full 360°, WindowText at 30% opacity (muted ring background)
        free_color = QColor(palette.color(QPalette.ColorRole.WindowText))
        free_color.setAlphaF(0.30)
        free_pen = QPen(free_color)
        free_pen.setWidth(_PEN_WIDTH)
        free_pen.setCapStyle(Qt.PenCapStyle.FlatCap)
        painter.setPen(free_pen)
        painter.drawArc(rect, 0, 360 * 16)

        # Used arc — from 12 o'clock, clockwise, Plasma highlight color
        if self._used_pct > 0:
            used_pen = QPen(palette.color(QPalette.ColorRole.Highlight))
            used_pen.setWidth(_PEN_WIDTH)
            used_pen.setCapStyle(Qt.PenCapStyle.FlatCap)
            painter.setPen(used_pen)
            span = -int(self._used_pct * 360 * 16)  # negative = clockwise
            painter.drawArc(rect, 90 * 16, span)


class DriveTile(QFrame):
    def __init__(self, drive: Drive, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setFrameShadow(QFrame.Shadow.Raised)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        layout = QVBoxLayout(self)
        layout.setSpacing(8)
        layout.setContentsMargins(12, 12, 12, 12)

        name_label = QLabel(drive.name)
        font = name_label.font()
        font.setBold(True)
        font.setPointSize(font.pointSize() + 1)
        name_label.setFont(font)
        name_label.setWordWrap(True)
        layout.addWidget(name_label)

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

        # ── Section header ──────────────────────────────────────────────────
        section_header = QLabel("Physical Devices")
        hfont = section_header.font()
        hfont.setBold(True)
        hfont.setPointSize(hfont.pointSize() + 3)
        section_header.setFont(hfont)
        clayout.addWidget(section_header)
        clayout.addSpacing(12)

        # ── Status label (loading / empty / error) ──────────────────────────
        self._status_label = QLabel("Loading drives…")
        self._status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        clayout.addWidget(self._status_label)

        # ── Tile grid (hidden until tiles arrive) ───────────────────────────
        self._grid_widget = QWidget()
        self._grid_widget.setVisible(False)
        self._grid = QGridLayout(self._grid_widget)
        self._grid.setSpacing(12)
        self._grid.setContentsMargins(0, 0, 0, 0)
        clayout.addWidget(self._grid_widget)
        clayout.addStretch()

        self._scroll.setWidget(container)
        self._start_load()

    # ── Responsive layout ────────────────────────────────────────────────────

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if self._tiles:
            self._relayout()

    def _relayout(self) -> None:
        vp_width = self._scroll.viewport().width()
        if vp_width <= 0:
            return
        spacing = self._grid.spacing()
        available = vp_width  # grid margins are on the container, not the grid itself
        cols = max(1, (available + spacing) // (_TILE_MIN_WIDTH + spacing))
        if cols == self._col_count:
            return
        self._col_count = cols
        self._rebuild_grid()

    def _rebuild_grid(self) -> None:
        while self._grid.count():
            self._grid.takeAt(0)  # detach without deleting

        for c in range(_MAX_TRACKED_COLS):
            self._grid.setColumnStretch(c, 0)

        for i, tile in enumerate(self._tiles):
            row, col = divmod(i, self._col_count)
            self._grid.addWidget(tile, row, col)

        for c in range(self._col_count):
            self._grid.setColumnStretch(c, 1)

    # ── Thread wiring ────────────────────────────────────────────────────────

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
        self._col_count = 0   # force rebuild on next _relayout
        self._relayout()

    def _on_load_failed(self, error: str) -> None:
        self._status_label.setText(strings.ERR_PARSE_FAILURE.format(source="storage"))
