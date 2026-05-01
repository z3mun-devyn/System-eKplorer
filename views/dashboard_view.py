import strings
from backends.storage_backend import StorageBackend
from models.storage import Drive

from PyQt6.QtCore import QObject, QThread, Qt, pyqtSignal
from PyQt6.QtGui import QPainter, QPalette, QPen
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


class UsagePie(QWidget):
    """Ring-style usage indicator: background full circle + used-% arc."""

    def __init__(self, used_pct: float, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._used_pct = max(0.0, min(1.0, used_pct))
        self.setFixedSize(_PIE_SIZE, _PIE_SIZE)

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = self.rect().adjusted(_PIE_MARGIN, _PIE_MARGIN, -_PIE_MARGIN, -_PIE_MARGIN)
        palette = self.palette()

        bg_pen = QPen(palette.color(QPalette.ColorRole.Mid))
        bg_pen.setWidth(_PEN_WIDTH)
        bg_pen.setCapStyle(Qt.PenCapStyle.FlatCap)
        painter.setPen(bg_pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(rect)

        if self._used_pct > 0:
            fg_pen = QPen(palette.color(QPalette.ColorRole.Highlight))
            fg_pen.setWidth(_PEN_WIDTH)
            fg_pen.setCapStyle(Qt.PenCapStyle.FlatCap)
            painter.setPen(fg_pen)
            span = -int(self._used_pct * 360 * 16)   # negative = clockwise
            painter.drawArc(rect, 90 * 16, span)      # start at 12 o'clock


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
    """Files-tab landing page: 2-column grid of drive tiles."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        outer.addWidget(scroll)

        self._container = QWidget()
        self._grid = QGridLayout(self._container)
        self._grid.setSpacing(12)
        self._grid.setContentsMargins(16, 16, 16, 16)
        self._grid.setColumnStretch(0, 1)
        self._grid.setColumnStretch(1, 1)
        scroll.setWidget(self._container)

        self._loading_label = QLabel("Loading drives…")
        self._loading_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._grid.addWidget(self._loading_label, 0, 0, 1, 2)

        self._start_load()

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

    def _clear_grid(self) -> None:
        while self._grid.count():
            item = self._grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _on_drives_ready(self, drives: list) -> None:
        self._clear_grid()
        if not drives:
            label = QLabel("No drives found.")
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._grid.addWidget(label, 0, 0, 1, 2)
            return
        for i, drive in enumerate(drives):
            row, col = divmod(i, 2)
            self._grid.addWidget(DriveTile(drive), row, col)

    def _on_load_failed(self, error: str) -> None:
        self._clear_grid()
        label = QLabel(strings.ERR_PARSE_FAILURE.format(source="storage"))
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._grid.addWidget(label, 0, 0, 1, 2)
