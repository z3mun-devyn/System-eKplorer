import re
import shutil
import subprocess
from datetime import datetime, timezone

import strings
from backends.disk_scan_backend import DISK_CATEGORIES, DISK_FREE_COLOR, DiskScanWorker
from backends.settings_backend import SettingsRepository
from backends.smart_backend import SmartBackend, SmartData
from backends.storage_backend import StorageBackend
from backends.udisks_watcher import UDisks2Watcher
from models.database import open_db
from models.storage import Drive, UnmountedDrive

from PyQt6.QtCore import QObject, QRectF, QSize, QThread, QTimer, Qt, pyqtSignal
from PyQt6.QtGui import QBrush, QColor, QIcon, QPainter, QPalette, QPen
from PyQt6.QtWidgets import (
    QButtonGroup,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QGraphicsOpacityEffect,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

_XDG_MIME = shutil.which("xdg-mime")

_PIE_SIZE = 80
_PEN_WIDTH = 12
_PIE_MARGIN = _PEN_WIDTH // 2 + 2

_TILE_MIN_WIDTH = 360
_MAX_TRACKED_COLS = 6
_CARD_RADIUS = 7

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


def _paint_card(widget: QWidget, hovered: bool) -> None:
    """Shared card-background painter for drive tiles."""
    painter = QPainter(widget)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    rect = widget.rect().adjusted(1, 1, -1, -1)
    palette = widget.palette()

    painter.setBrush(palette.color(QPalette.ColorRole.Base))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawRoundedRect(rect, _CARD_RADIUS, _CARD_RADIUS)

    if hovered:
        hl = QColor(palette.color(QPalette.ColorRole.Highlight))
        hl.setAlphaF(0.08)
        painter.setBrush(hl)
        painter.drawRoundedRect(rect, _CARD_RADIUS, _CARD_RADIUS)

    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.setPen(QPen(palette.color(QPalette.ColorRole.Mid), 1))
    painter.drawRoundedRect(rect, _CARD_RADIUS, _CARD_RADIUS)


class UsagePie(QWidget):
    """Solid-fill ring: free arc muted + used arc in highlight color."""

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


class DashedRing(QWidget):
    """Dashed ring outline for unmounted drives (usage unknown)."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(_PIE_SIZE, _PIE_SIZE)

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(Qt.BrushStyle.NoBrush)

        rect = self.rect().adjusted(_PIE_MARGIN, _PIE_MARGIN, -_PIE_MARGIN, -_PIE_MARGIN)
        color = QColor(self.palette().color(QPalette.ColorRole.WindowText))
        color.setAlphaF(0.30)
        pen = QPen(color)
        pen.setWidth(_PEN_WIDTH)
        pen.setCapStyle(Qt.PenCapStyle.FlatCap)
        pen.setStyle(Qt.PenStyle.DashLine)
        painter.setPen(pen)
        painter.drawArc(rect, 0, 360 * 16)


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

        layout.addWidget(QLabel(strings.LABEL_MODAL_FIELD + ":"))
        self._label_edit = QLineEdit(drive.label or "")
        self._label_edit.setPlaceholderText("e.g. Work, Backup, Media…")
        layout.addWidget(self._label_edit)

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
    navigate_requested = pyqtSignal(str)

    def __init__(self, drive: Drive, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._drive = drive
        self._hovered = False

        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setAutoFillBackground(False)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setMinimumHeight(160)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)

        layout = QVBoxLayout(self)
        layout.setSpacing(8)
        layout.setContentsMargins(16, 16, 16, 16)

        # Header row: name on left, label badge on right
        header = QHBoxLayout()
        header.setSpacing(8)

        name_label = QLabel(drive.name)
        font = name_label.font()
        font.setBold(True)
        font.setPointSize(font.pointSize() + 1)
        name_label.setFont(font)
        name_label.setWordWrap(True)
        header.addWidget(name_label, stretch=1)

        rename_btn = QPushButton(strings.ACTION_RENAME_DRIVE)
        rename_btn.setFlat(True)
        rename_btn.setFixedSize(22, 22)
        rename_btn.setToolTip(strings.ACTION_RENAME_LABEL)
        rename_btn.clicked.connect(self._open_label_modal)
        header.addWidget(rename_btn, stretch=0)

        # Badge always allocated (fixed height) — empty+transparent when no label
        self._badge = QLabel()
        self._badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._badge.setFixedHeight(20)
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

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.navigate_requested.emit(self._drive.mount_point)
        super().mousePressEvent(event)

    def paintEvent(self, event) -> None:
        _paint_card(self, self._hovered)

    def enterEvent(self, event) -> None:
        self._hovered = True
        self.update()

    def leaveEvent(self, event) -> None:
        self._hovered = False
        self.update()

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
        else:
            self._badge.setText("")
            self._badge.setStyleSheet("QLabel { background: transparent; }")

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


class _MountWorker(QObject):
    success = pyqtSignal(str)    # device path
    error = pyqtSignal(str, str) # device path, error message

    def __init__(self, drive: UnmountedDrive) -> None:
        super().__init__()
        self._drive = drive

    def run(self) -> None:
        try:
            if self._drive.is_encrypted:
                self._unlock_and_mount()
            else:
                self._plain_mount(self._drive.device)
        except Exception as exc:
            self.error.emit(self._drive.device, str(exc))

    def _plain_mount(self, device: str) -> None:
        result = subprocess.run(
            ["udisksctl", "mount", "-b", device],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode != 0:
            msg = (result.stderr.strip() or result.stdout.strip()
                   or "unknown error")
            self.error.emit(self._drive.device, msg)
        else:
            self.success.emit(self._drive.device)

    def _unlock_and_mount(self) -> None:
        if self._drive.fs_type == "BitLocker" and not shutil.which("dislocker"):
            self.error.emit(self._drive.device, strings.NOTICE_BITLOCKER_MISSING)
            return

        result = subprocess.run(
            ["udisksctl", "unlock", "-b", self._drive.device],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode != 0:
            msg = result.stderr.strip() or result.stdout.strip() or "unknown error"
            self.error.emit(self._drive.device, msg)
            return

        mapped = self._parse_unlock_output(result.stdout)
        if not mapped:
            self.error.emit(
                self._drive.device,
                f"Could not determine mapped device after unlock",
            )
            return

        self._plain_mount(mapped)

    @staticmethod
    def _parse_unlock_output(output: str) -> str | None:
        m = re.search(r"as (/dev/\S+?)\.?\s*$", output, re.MULTILINE)
        return m.group(1) if m else None


class UnmountedDriveTile(QFrame):
    mount_success = pyqtSignal()
    mount_error = pyqtSignal(str)

    def __init__(self, drive: UnmountedDrive, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._drive = drive
        self._hovered = False

        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setAutoFillBackground(False)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setMinimumHeight(160)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        opacity = QGraphicsOpacityEffect(self)
        opacity.setOpacity(0.6)
        self.setGraphicsEffect(opacity)

        layout = QVBoxLayout(self)
        layout.setSpacing(8)
        layout.setContentsMargins(16, 16, 16, 16)

        # Header row: name on left, status icon on right
        header = QHBoxLayout()
        header.setSpacing(8)

        name_label = QLabel(drive.name)
        font = name_label.font()
        font.setBold(True)
        font.setPointSize(font.pointSize() + 1)
        name_label.setFont(font)
        name_label.setWordWrap(True)
        header.addWidget(name_label, stretch=1)

        icon_label = QLabel()
        icon_label.setFixedHeight(20)
        if drive.is_encrypted:
            icon = QIcon.fromTheme("security-high")
            if not icon.isNull():
                icon_label.setPixmap(icon.pixmap(16, 16))
            else:
                icon_label.setText("🔒")
        else:
            icon = QIcon.fromTheme("drive-harddisk")
            if not icon.isNull():
                icon_label.setPixmap(icon.pixmap(16, 16))
            else:
                icon_label.setText("⏏")
        header.addWidget(icon_label, stretch=0)

        layout.addLayout(header)

        info_label = QLabel(f"{drive.device}  ·  {drive.fs_type}")
        info_label.setStyleSheet("color: palette(mid);")
        layout.addWidget(info_label)

        body_row = QHBoxLayout()
        body_row.setSpacing(16)
        body_row.addWidget(DashedRing())

        body_detail = QVBoxLayout()
        body_detail.setSpacing(2)
        body_detail.addStretch()
        action_text = (
            strings.ACTION_CLICK_TO_UNLOCK if drive.is_encrypted
            else strings.ACTION_CLICK_TO_MOUNT
        )
        body_detail.addWidget(QLabel(action_text))
        size_label = QLabel(drive.size_str)
        size_label.setStyleSheet("color: palette(mid);")
        body_detail.addWidget(size_label)
        body_detail.addStretch()

        body_row.addLayout(body_detail)
        body_row.addStretch()
        layout.addLayout(body_row)

    def paintEvent(self, event) -> None:
        _paint_card(self, self._hovered)

    def enterEvent(self, event) -> None:
        self._hovered = True
        self.update()

    def leaveEvent(self, event) -> None:
        self._hovered = False
        self.update()

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._start_mount()

    def _start_mount(self) -> None:
        self._thread = QThread(parent=self)
        self._worker = _MountWorker(self._drive)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.success.connect(lambda _dev: self.mount_success.emit())
        self._worker.error.connect(lambda _dev, msg: self.mount_error.emit(msg))
        self._worker.success.connect(self._thread.quit)
        self._worker.error.connect(lambda _dev, _msg: self._thread.quit())
        self._thread.finished.connect(self._worker.deleteLater)
        self._thread.start()


class _SegmentedPieWidget(QWidget):
    """Donut chart showing disk usage by category."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._named: dict[str, int] = {}
        self._other: int = 0    # used but not covered by named scan categories
        self._free: int = 0     # drive.free_bytes
        self._total: int = 0    # drive.total_bytes
        self._basis: str = "used"

    def set_basis(self, basis: str) -> None:
        self._basis = basis
        self.update()

    def sizeHint(self) -> QSize:
        return QSize(160, 160)

    def set_data(
        self,
        category_bytes: dict[str, int],
        other_bytes: int,
        free_bytes: int,
        total_bytes: int,
    ) -> None:
        self._named = category_bytes
        self._other = other_bytes
        self._free = free_bytes
        self._total = total_bytes
        self.update()

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        cx, cy = self.width() // 2, self.height() // 2
        outer_r = min(cx, cy) - 4
        inner_r = outer_r * 5 // 10
        outer_rect = QRectF(cx - outer_r, cy - outer_r, outer_r * 2, outer_r * 2)

        if not self._named and self._other == 0 and self._total <= 0:
            painter.setPen(QPen(self.palette().color(QPalette.ColorRole.Mid), 1))
            painter.setBrush(QBrush(self.palette().color(QPalette.ColorRole.Mid)))
            painter.drawEllipse(outer_rect)
            inner_rect = QRectF(cx - inner_r, cy - inner_r, inner_r * 2, inner_r * 2)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(self.palette().color(QPalette.ColorRole.Base)))
            painter.drawEllipse(inner_rect)
            return

        painter.setPen(QPen(self.palette().color(QPalette.ColorRole.Dark), 1))

        # Named categories largest-first, then Other (uncategorized), then Free Space
        segments: list[tuple[str, int]] = sorted(
            self._named.items(), key=lambda x: x[1], reverse=True,
        )
        if self._other > 0:
            segments.append(("Other", self._other))
        segments.append(("_free", self._free))

        if self._basis == "used":
            used_total = self._total - self._free
            denom = used_total if used_total > 0 else 1
            draw_segments = [(c, v) for c, v in segments if c != "_free"]
        else:
            denom = self._total
            draw_segments = segments

        start = 90 * 16
        for cat, val in draw_segments:
            if denom == 0 or val <= 0:
                continue
            span = int(val / denom * 360 * 16)
            if span == 0:
                continue
            color = (
                QColor(DISK_FREE_COLOR) if cat == "_free"
                else QColor(DISK_CATEGORIES.get(cat, "#566573"))
            )
            painter.setBrush(QBrush(color))
            painter.drawPie(outer_rect, start, span)
            start -= span

        inner_rect = QRectF(cx - inner_r, cy - inner_r, inner_r * 2, inner_r * 2)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(self.palette().color(QPalette.ColorRole.Base)))
        painter.drawEllipse(inner_rect)

        used_bytes = self._total - self._free
        used_pct = int(used_bytes / self._total * 100) if self._total else 0
        painter.setPen(QPen(self.palette().color(QPalette.ColorRole.WindowText)))
        painter.drawText(inner_rect, Qt.AlignmentFlag.AlignCenter, f"{used_pct}%")


def _fmt_bytes(b: int) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if b < 1024:
            return f"{b:.1f} {unit}" if unit != "B" else f"{b} B"
        b //= 1024
    return f"{b} PB"


class AdvancedDriveTile(QFrame):
    navigate_requested = pyqtSignal(str)

    def __init__(self, drive: Drive, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._drive = drive
        self._hovered = False
        self._scan_started = False
        self._scan_thread: QThread | None = None
        self._scan_worker = None
        self._smart_thread: QThread | None = None
        self._smart_worker = None

        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setAutoFillBackground(False)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setMinimumHeight(320)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)

        layout = QVBoxLayout(self)
        layout.setSpacing(8)
        layout.setContentsMargins(16, 16, 16, 16)

        # ── Header (same as DriveTile) ────────────────────────────────────────
        header_row = QHBoxLayout()
        header_row.setSpacing(8)

        name_label = QLabel(drive.name)
        font = name_label.font()
        font.setBold(True)
        font.setPointSize(font.pointSize() + 1)
        name_label.setFont(font)
        name_label.setWordWrap(True)
        header_row.addWidget(name_label, stretch=1)

        self._badge = QLabel()
        self._badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._badge.setFixedHeight(20)
        header_row.addWidget(self._badge, stretch=0)

        adv_rename_btn = QPushButton(strings.ACTION_RENAME_DRIVE)
        adv_rename_btn.setFlat(True)
        adv_rename_btn.setFixedSize(22, 22)
        adv_rename_btn.setToolTip(strings.ACTION_RENAME_LABEL)
        adv_rename_btn.clicked.connect(self._open_label_modal)
        header_row.addWidget(adv_rename_btn)

        rescan_btn = QPushButton(strings.DASHBOARD_RESCAN)
        rescan_btn.setFlat(True)
        rescan_btn.clicked.connect(self._start_scan)
        header_row.addWidget(rescan_btn)

        layout.addLayout(header_row)

        info_label = QLabel(f"{drive.device}  ·  {drive.fs_type}")
        info_label.setStyleSheet("color: palette(mid);")
        layout.addWidget(info_label)

        stats_row = QHBoxLayout()
        stats_row.setSpacing(12)
        stats_row.addWidget(QLabel(f"{drive.used_str} used"))
        stats_row.addWidget(QLabel(f"{drive.free_str} free"))
        total_lbl = QLabel(f"of {drive.total_str}")
        total_lbl.setStyleSheet("color: palette(mid);")
        stats_row.addWidget(total_lbl)
        stats_row.addStretch()
        layout.addLayout(stats_row)

        # ── Scan area ─────────────────────────────────────────────────────────
        self._scan_stack = QStackedWidget()

        scanning_page = QWidget()
        sp_layout = QVBoxLayout(scanning_page)
        sp_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._progress_bar = QProgressBar()
        self._progress_bar.setRange(0, 0)
        sp_layout.addWidget(self._progress_bar)
        sp_layout.addWidget(QLabel(strings.DASHBOARD_SCANNING))
        self._scan_stack.addWidget(scanning_page)

        self._results_page = QWidget()
        self._results_layout = QHBoxLayout(self._results_page)

        pie_col = QWidget()
        pie_col_layout = QVBoxLayout(pie_col)
        pie_col_layout.setContentsMargins(0, 0, 0, 0)
        pie_col_layout.setSpacing(4)

        toggle_row = QHBoxLayout()
        toggle_row.setSpacing(2)
        self._pie_total_btn = QPushButton("Total")
        self._pie_total_btn.setCheckable(True)
        self._pie_total_btn.setFlat(True)
        self._pie_total_btn.setFixedHeight(20)
        self._pie_used_btn = QPushButton("Used")
        self._pie_used_btn.setCheckable(True)
        self._pie_used_btn.setFlat(True)
        self._pie_used_btn.setFixedHeight(20)
        self._pie_toggle_group = QButtonGroup(self)
        self._pie_toggle_group.addButton(self._pie_total_btn, 0)
        self._pie_toggle_group.addButton(self._pie_used_btn, 1)
        self._pie_toggle_group.setExclusive(True)
        toggle_row.addWidget(self._pie_total_btn)
        toggle_row.addWidget(self._pie_used_btn)
        toggle_row.addStretch()
        pie_col_layout.addLayout(toggle_row)

        self._pie_widget = _SegmentedPieWidget()
        pie_col_layout.addWidget(self._pie_widget)
        self._results_layout.addWidget(pie_col)

        self._legend_widget = QWidget()
        self._legend_layout = QVBoxLayout(self._legend_widget)
        self._legend_layout.setSpacing(3)
        self._legend_layout.setContentsMargins(8, 0, 0, 0)
        self._results_layout.addWidget(self._legend_widget, stretch=1)
        self._scan_stack.addWidget(self._results_page)

        _pie_basis = SettingsRepository().get("dashboard.pie_basis") or "used"
        self._pie_widget.set_basis(_pie_basis)
        (self._pie_total_btn if _pie_basis == "total" else self._pie_used_btn).setChecked(True)
        self._pie_toggle_group.idToggled.connect(self._on_pie_basis_toggled)

        layout.addWidget(self._scan_stack)

        # ── SMART area ────────────────────────────────────────────────────────
        smart_title = QLabel(strings.DASHBOARD_SMART_TITLE)
        tf = smart_title.font()
        tf.setBold(True)
        smart_title.setFont(tf)
        layout.addWidget(smart_title)

        self._smart_container = QWidget()
        self._smart_layout = QVBoxLayout(self._smart_container)
        self._smart_layout.setSpacing(3)
        self._smart_layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._smart_container)

        layout.addStretch()
        self._refresh_badge()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if not self._scan_started:
            self._scan_started = True
            self._start_scan()
            self._start_smart()

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.navigate_requested.emit(self._drive.mount_point)
        super().mousePressEvent(event)

    def paintEvent(self, event) -> None:
        _paint_card(self, self._hovered)

    def enterEvent(self, event) -> None:
        self._hovered = True
        self.update()

    def leaveEvent(self, event) -> None:
        self._hovered = False
        self.update()

    def _refresh_badge(self) -> None:
        label = self._drive.label
        color = self._drive.color_hex
        if label:
            bg = color or _LABEL_PALETTE[-1]
            fg = _contrast_color(bg)
            self._badge.setText(label)
            self._badge.setStyleSheet(
                f"QLabel {{"
                f"  background-color: {bg}; color: {fg};"
                f"  border-radius: 8px; padding: 2px 8px; font-size: 11px;"
                f"}}"
            )
        else:
            self._badge.setText("")
            self._badge.setStyleSheet("QLabel { background: transparent; }")

    def cancel_scan(self) -> None:
        """Drain _scan_thread and _smart_thread; safe to call before setParent(None)."""
        if self._scan_worker is not None:
            self._scan_worker.cancel()
        for t in (self._scan_thread, self._smart_thread):
            if t is not None:
                try:
                    if t.isRunning():
                        t.quit()
                        if not t.wait(3000):
                            t.terminate()
                            t.wait()
                except RuntimeError:
                    pass
        self._scan_thread = None
        self._scan_worker = None
        self._smart_thread = None
        self._smart_worker = None

    def _on_pie_basis_toggled(self, btn_id: int, checked: bool) -> None:
        if not checked:
            return
        basis = "total" if btn_id == 0 else "used"
        self._pie_widget.set_basis(basis)
        SettingsRepository().set("dashboard.pie_basis", basis)

    def _show_smart_howto(self) -> None:
        QMessageBox.information(
            self,
            strings.DASHBOARD_SMART_HOWTO_TITLE,
            strings.DASHBOARD_SMART_HOWTO_MSG,
        )

    def _show_context_menu(self, pos) -> None:
        menu = QMenu(self)
        rename_action = menu.addAction(strings.ACTION_RENAME_LABEL)
        rename_action.triggered.connect(self._open_label_modal)
        menu.exec(self.mapToGlobal(pos))

    def _open_label_modal(self) -> None:
        modal = LabelModal(self._drive, parent=self)
        modal.accepted.connect(self._refresh_badge)
        modal.open()

    # ── Disk scan ─────────────────────────────────────────────────────────────

    def _start_scan(self) -> None:
        self._scan_stack.setCurrentIndex(0)
        self._scan_thread = QThread(parent=self)
        self._scan_worker = DiskScanWorker(self._drive.mount_point)
        self._scan_worker.moveToThread(self._scan_thread)
        self._scan_thread.started.connect(self._scan_worker.run)
        self._scan_worker.finished.connect(self._on_scan_finished)
        self._scan_worker.failed.connect(self._on_scan_failed)
        self._scan_worker.finished.connect(self._scan_thread.quit)
        self._scan_worker.failed.connect(self._scan_thread.quit)
        self._scan_thread.finished.connect(self._scan_worker.deleteLater)
        self._scan_thread.finished.connect(self._scan_thread.deleteLater)
        self._scan_thread.start()

    def _on_scan_finished(self, data: dict) -> None:
        total_bytes = self._drive.total_bytes or sum(data.values())
        free_bytes = max(0, self._drive.free_bytes)

        # Separate named categories from the scan's own "Other" bucket so there
        # is never a duplicate "Other" entry in the legend.  The scan's "Other"
        # (uncategorized files) merges into other_bytes via the arithmetic below.
        named = {k: v for k, v in data.items() if k != "Other"}
        named_total = sum(named.values())

        # other_bytes = used space not accounted for by named categories
        # (naturally absorbs the scan's "Other" bucket + filesystem metadata).
        used_bytes = total_bytes - free_bytes
        other_bytes = max(0, used_bytes - named_total)

        self._pie_widget.set_data(named, other_bytes, free_bytes, total_bytes)
        self._build_legend(named, other_bytes, free_bytes)
        self._scan_stack.setCurrentIndex(1)

    def _on_scan_failed(self, error: str) -> None:
        self._scan_stack.setCurrentIndex(1)

    def _build_legend(
        self, named: dict[str, int], other_bytes: int, free_bytes: int
    ) -> None:
        while self._legend_layout.count():
            item = self._legend_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        segments = sorted(named.items(), key=lambda x: x[1], reverse=True)

        # Other (uncategorized) second-to-last, Free Space always last
        if other_bytes > 0:
            segments.append((strings.DASHBOARD_OTHER_UNCATEGORIZED, other_bytes))
        segments.append((strings.DASHBOARD_FREE_SPACE, free_bytes))

        for cat, val in segments:
            row_widget = QWidget()
            row = QHBoxLayout(row_widget)
            row.setContentsMargins(0, 0, 0, 0)
            row.setSpacing(6)

            swatch = QLabel()
            swatch.setFixedSize(12, 12)
            if cat == strings.DASHBOARD_FREE_SPACE:
                color = DISK_FREE_COLOR
            elif cat == strings.DASHBOARD_OTHER_UNCATEGORIZED:
                color = DISK_CATEGORIES.get("Other", "#7F8C8D")
            else:
                color = DISK_CATEGORIES.get(cat, "#7F8C8D")
            swatch.setStyleSheet(
                f"QLabel {{ background: {color}; border-radius: 2px; }}"
            )
            row.addWidget(swatch)

            name_lbl = QLabel(cat)
            row.addWidget(name_lbl, stretch=1)

            size_lbl = QLabel(_fmt_bytes(val))
            size_lbl.setStyleSheet("color: palette(mid);")
            row.addWidget(size_lbl)

            self._legend_layout.addWidget(row_widget)

        self._legend_layout.addStretch()

    # ── SMART ─────────────────────────────────────────────────────────────────

    def _start_smart(self) -> None:
        self._smart_thread = QThread(parent=self)
        self._smart_worker = _SmartWorker(self._drive.mount_point)
        self._smart_worker.moveToThread(self._smart_thread)
        self._smart_thread.started.connect(self._smart_worker.run)
        self._smart_worker.finished.connect(self._on_smart_finished)
        self._smart_worker.unavailable.connect(self._on_smart_unavailable)
        self._smart_worker.finished.connect(self._smart_thread.quit)
        self._smart_worker.unavailable.connect(self._smart_thread.quit)
        self._smart_thread.finished.connect(self._smart_worker.deleteLater)
        self._smart_thread.finished.connect(self._smart_thread.deleteLater)
        self._smart_thread.start()

    def _on_smart_unavailable(self, reason: str) -> None:
        while self._smart_layout.count():
            item = self._smart_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        lbl = QLabel(reason)
        lbl.setStyleSheet("color: palette(mid);")
        self._smart_layout.addWidget(lbl)

    def _on_smart_finished(self, results: list) -> None:
        while self._smart_layout.count():
            item = self._smart_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        for device, data in results:
            self._add_smart_device_rows(device, data, multi=(len(results) > 1))

    def _add_smart_device_rows(
        self, device: str, data: SmartData, multi: bool
    ) -> None:
        dev_label = Path(device).name if multi else None

        if data.health == "permission_denied":
            lbl = QLabel(strings.DASHBOARD_SMART_NO_PERM)
            lbl.setStyleSheet("color: palette(mid);")
            self._smart_layout.addWidget(lbl)
            howto_btn = QPushButton(strings.DASHBOARD_SMART_HOWTO_BTN)
            howto_btn.setFlat(True)
            howto_btn.clicked.connect(self._show_smart_howto)
            self._smart_layout.addWidget(howto_btn)
            return

        prefix = f"{dev_label}: " if dev_label else ""
        health_lbl = QLabel(f"{prefix}{strings.DASHBOARD_SMART_TITLE}: {data.health}")
        if data.health == strings.DASHBOARD_SMART_PASSED:
            health_lbl.setStyleSheet("color: #27ae60;")
        elif data.health == strings.DASHBOARD_SMART_FAILED:
            health_lbl.setStyleSheet("color: #e74c3c;")
        self._smart_layout.addWidget(health_lbl)

        if not multi:
            if data.power_on_hours is not None:
                h = data.power_on_hours
                y, rem = divmod(h, 8760)
                m = rem // 730
                poh_lbl = QLabel(
                    f"{strings.DASHBOARD_SMART_POH}: {h:,} hrs"
                    + (f" (≈ {y} yrs {m} months)" if y or m else "")
                )
                self._smart_layout.addWidget(poh_lbl)

            if data.temperature_c is not None:
                t = data.temperature_c
                temp_lbl = QLabel(f"{strings.DASHBOARD_SMART_TEMP}: {t} °C")
                if t > 60:
                    temp_lbl.setStyleSheet("color: #e74c3c;")
                elif t > 50:
                    temp_lbl.setStyleSheet("color: #e67e22;")
                self._smart_layout.addWidget(temp_lbl)

            if data.reallocated_sectors and data.reallocated_sectors > 0:
                realloc_lbl = QLabel(
                    strings.DASHBOARD_SMART_REALLOC.format(n=data.reallocated_sectors)
                )
                realloc_lbl.setStyleSheet("color: #e74c3c;")
                self._smart_layout.addWidget(realloc_lbl)


class _SmartWorker(QObject):
    # Emits list[tuple[str, SmartData | None]]: (device_path, data)
    finished = pyqtSignal(list)
    unavailable = pyqtSignal(str)

    def __init__(self, mount_point: str) -> None:
        super().__init__()
        self._mount_point = mount_point

    def run(self) -> None:
        backend = SmartBackend()
        if not backend.is_available():
            self.unavailable.emit(strings.DASHBOARD_SMART_UNAVAILABLE)
            return
        if not backend.check_runnable():
            self.unavailable.emit(strings.DASHBOARD_SMART_UNAVAILABLE)
            return
        devices = backend.devices_for_mount(self._mount_point)
        if not devices:
            self.unavailable.emit(strings.DASHBOARD_SMART_UNAVAILABLE)
            return
        results: list[tuple[str, SmartData | None]] = []
        for device in devices:
            data = backend.get_data(device)
            if data is None:
                data = SmartData(health="permission_denied")
            results.append((device, data))
        self.finished.emit(results)


class _DriveLoader(QObject):
    loads_ready = pyqtSignal(list, list)  # (mounted, unmounted)
    load_failed = pyqtSignal(str)

    def run(self) -> None:
        try:
            backend = StorageBackend()
            mounted = backend.list_drives()
            unmounted = backend.list_unmounted_devices()
            self.loads_ready.emit(mounted, unmounted)
        except Exception as exc:
            self.load_failed.emit(str(exc))


_POLL_INTERVAL_MS = 15_000


class DashboardView(QWidget):
    """Files-tab landing page: responsive grid of drive tiles."""

    navigate_requested = pyqtSignal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._tiles: list[DriveTile | AdvancedDriveTile] = []
        self._inactive_tiles: list[UnmountedDriveTile] = []
        self._col_count: int = 0
        self._initial_load_done: bool = False

        self._settings = SettingsRepository()
        self._view_mode = self._settings.get("dashboard.view_mode") or "simple"

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        outer.addWidget(self._build_toolbar())

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        outer.addWidget(self._scroll, stretch=1)

        # "Set as default file manager" footer — hidden once already default
        self._default_fm_bar = QWidget()
        _dfm_layout = QHBoxLayout(self._default_fm_bar)
        _dfm_layout.setContentsMargins(16, 4, 16, 4)
        self._default_fm_btn = QPushButton(strings.ACTION_SET_DEFAULT_FM)
        self._default_fm_btn.setMaximumWidth(260)
        self._default_fm_btn.clicked.connect(self._set_as_default_fm)
        _dfm_layout.addWidget(self._default_fm_btn)
        _dfm_layout.addStretch()
        outer.addWidget(self._default_fm_bar)
        self._check_default_fm()

        # Toast bar at the very bottom of the view
        self._toast = QLabel()
        self._toast.setVisible(False)
        self._toast.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._toast.setStyleSheet(
            "QLabel { background: palette(mid); color: palette(window-text);"
            " padding: 8px 16px; border-top: 1px solid palette(dark); }"
        )
        outer.addWidget(self._toast)

        container = QWidget()
        clayout = QVBoxLayout(container)
        clayout.setContentsMargins(16, 16, 16, 16)
        clayout.setSpacing(0)

        # ── Active section ──────────────────────────────────────────────────
        section_header = QLabel(strings.SECTION_ACTIVE)
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

        # ── Inactive section (shown only when unmounted devices exist) ───────
        self._inactive_section = QWidget()
        self._inactive_section.setVisible(False)
        inactive_layout = QVBoxLayout(self._inactive_section)
        inactive_layout.setContentsMargins(0, 24, 0, 0)
        inactive_layout.setSpacing(12)

        inactive_header = QLabel(strings.SECTION_INACTIVE)
        ifont = inactive_header.font()
        ifont.setBold(True)
        ifont.setPointSize(ifont.pointSize() + 3)
        inactive_header.setFont(ifont)
        inactive_layout.addWidget(inactive_header)

        self._inactive_grid_widget = QWidget()
        self._inactive_grid = QGridLayout(self._inactive_grid_widget)
        self._inactive_grid.setSpacing(12)
        self._inactive_grid.setContentsMargins(0, 0, 0, 0)
        inactive_layout.addWidget(self._inactive_grid_widget)

        clayout.addWidget(self._inactive_section)
        clayout.addStretch()

        self._scroll.setWidget(container)

        # ── Event-driven refresh via udisks2 D-Bus + 15-second poll fallback ──
        self._watcher = UDisks2Watcher(parent=self)
        self._watcher.storage_changed.connect(self._on_storage_changed)

        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(_POLL_INTERVAL_MS)
        self._poll_timer.timeout.connect(self._on_storage_changed)
        self._poll_timer.start()

        self._start_load()

    # ── Toolbar ───────────────────────────────────────────────────────────────

    def _build_toolbar(self) -> QWidget:
        toolbar = QWidget()
        toolbar.setFixedHeight(36)
        row = QHBoxLayout(toolbar)
        row.setContentsMargins(12, 4, 12, 4)
        row.setSpacing(4)

        simple_btn = QPushButton(strings.DASHBOARD_TOGGLE_SIMPLE)
        simple_btn.setCheckable(True)
        advanced_btn = QPushButton(strings.DASHBOARD_TOGGLE_ADVANCED)
        advanced_btn.setCheckable(True)

        self._mode_group = QButtonGroup(toolbar)
        self._mode_group.addButton(simple_btn, 0)
        self._mode_group.addButton(advanced_btn, 1)
        self._mode_group.setExclusive(True)

        if self._view_mode == "advanced":
            advanced_btn.setChecked(True)
        else:
            simple_btn.setChecked(True)

        self._mode_group.idToggled.connect(self._on_mode_toggled)

        row.addWidget(simple_btn)
        row.addWidget(advanced_btn)
        row.addStretch()
        return toolbar

    def _on_mode_toggled(self, btn_id: int, checked: bool) -> None:
        if not checked:
            return
        mode = "simple" if btn_id == 0 else "advanced"
        if mode == self._view_mode:
            return
        self._view_mode = mode
        self._settings.set("dashboard.view_mode", mode)
        self._reload()

    # ── Responsive layout ────────────────────────────────────────────────────

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if self._tiles or self._inactive_tiles:
            self._relayout()

    def _relayout(self) -> None:
        vp_width = self._scroll.viewport().width()
        if vp_width <= 0:
            return
        spacing = self._grid.spacing()
        cols = max(1, (vp_width + spacing) // (_TILE_MIN_WIDTH + spacing))
        if cols == self._col_count:
            return
        self._col_count = cols
        self._rebuild_grid(self._grid, self._tiles, cols)
        self._rebuild_grid(self._inactive_grid, self._inactive_tiles, cols)

    @staticmethod
    def _rebuild_grid(grid: QGridLayout, tiles: list, col_count: int) -> None:
        while grid.count():
            grid.takeAt(0)
        for c in range(_MAX_TRACKED_COLS):
            grid.setColumnStretch(c, 0)
        if not tiles:
            return
        for i, tile in enumerate(tiles):
            row, col = divmod(i, col_count)
            grid.addWidget(tile, row, col)
        for c in range(col_count):
            grid.setColumnStretch(c, 1)

    # ── Thread wiring ────────────────────────────────────────────────────────

    def _start_load(self) -> None:
        if hasattr(self, "_thread") and self._thread.isRunning():
            return
        self._thread = QThread(parent=self)
        self._worker = _DriveLoader()
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.loads_ready.connect(self._on_loads_ready)
        self._worker.load_failed.connect(self._on_load_failed)
        self._worker.loads_ready.connect(self._thread.quit)
        self._worker.load_failed.connect(self._thread.quit)
        self._thread.finished.connect(self._worker.deleteLater)
        self._thread.start()

    def _on_storage_changed(self) -> None:
        """Called by D-Bus watcher or polling timer; triggers a diff refresh."""
        self._start_load()

    def _reload(self) -> None:
        """Full teardown + re-load; called after a mount/unmount completes."""
        for tile in self._tiles:
            if isinstance(tile, AdvancedDriveTile):
                tile.cancel_scan()
            tile.setParent(None)
        for tile in self._inactive_tiles:
            tile.setParent(None)
        self._tiles = []
        self._inactive_tiles = []
        self._col_count = 0
        self._initial_load_done = False
        self._grid_widget.setVisible(False)
        self._inactive_section.setVisible(False)
        self._status_label.setText("Loading drives…")
        self._status_label.setVisible(True)
        self._start_load()

    def _on_loads_ready(self, mounted: list, unmounted: list) -> None:
        if not self._initial_load_done:
            self._initial_load_done = True
            self._build_initial(mounted, unmounted)
        else:
            self._apply_diff(mounted, unmounted)

    def _new_drive_tile(self, drive: Drive) -> DriveTile | AdvancedDriveTile:
        if self._view_mode == "advanced":
            tile = AdvancedDriveTile(drive)
        else:
            tile = DriveTile(drive)
        tile.navigate_requested.connect(self.navigate_requested)
        return tile

    def _build_initial(self, mounted: list, unmounted: list) -> None:
        if not mounted:
            self._status_label.setText("No drives found.")
        else:
            self._status_label.setVisible(False)
            self._tiles = [self._new_drive_tile(drive) for drive in mounted]
            self._grid_widget.setVisible(True)

        if unmounted:
            for drive in unmounted:
                tile = UnmountedDriveTile(drive)
                tile.mount_success.connect(self._reload)
                tile.mount_error.connect(self._show_toast)
                self._inactive_tiles.append(tile)
            self._inactive_section.setVisible(True)

        self._col_count = 0
        self._relayout()

    def _apply_diff(self, mounted: list, unmounted: list) -> None:
        """Update tiles in-place; rebuild only what changed. No-op if unchanged."""
        current_active = {t._drive.device: t for t in self._tiles}
        current_inactive = {t._drive.device: t for t in self._inactive_tiles}

        new_active = {d.device: d for d in mounted}
        new_inactive = {d.device: d for d in unmounted}

        if set(current_active) == set(new_active) and \
                set(current_inactive) == set(new_inactive):
            # Device sets identical — update labels on existing tiles only
            for dev, drive in new_active.items():
                if dev in current_active:
                    current_active[dev]._drive = drive
                    current_active[dev]._refresh_badge()
            return

        scrollbar = self._scroll.verticalScrollBar()
        saved_pos = scrollbar.value()

        # Reconcile active tiles
        new_tiles: list[DriveTile] = []
        for dev, drive in new_active.items():
            if dev in current_active:
                tile = current_active.pop(dev)
                tile._drive = drive
                tile._refresh_badge()
            else:
                tile = self._new_drive_tile(drive)
            new_tiles.append(tile)
        for tile in current_active.values():
            if isinstance(tile, AdvancedDriveTile):
                tile.cancel_scan()
            tile.setParent(None)

        # Reconcile inactive tiles
        new_inactive_tiles: list[UnmountedDriveTile] = []
        for dev, drive in new_inactive.items():
            if dev in current_inactive:
                new_inactive_tiles.append(current_inactive.pop(dev))
            else:
                tile = UnmountedDriveTile(drive)
                tile.mount_success.connect(self._reload)
                tile.mount_error.connect(self._show_toast)
                new_inactive_tiles.append(tile)
        for tile in current_inactive.values():
            tile.setParent(None)

        self._tiles = new_tiles
        self._inactive_tiles = new_inactive_tiles

        if self._tiles:
            self._status_label.setVisible(False)
            self._grid_widget.setVisible(True)
        else:
            self._grid_widget.setVisible(False)
            self._status_label.setText("No drives found.")
            self._status_label.setVisible(True)

        self._inactive_section.setVisible(bool(self._inactive_tiles))

        self._col_count = 0
        self._relayout()

        QTimer.singleShot(0, lambda: scrollbar.setValue(saved_pos))

    def _on_load_failed(self, error: str) -> None:
        self._status_label.setText(strings.ERR_PARSE_FAILURE.format(source="storage"))

    def _show_toast(self, message: str) -> None:
        self._toast.setText(message)
        self._toast.setVisible(True)
        QTimer.singleShot(5000, self._toast.hide)

    # ── Default file manager ──────────────────────────────────────────────────

    def _check_default_fm(self) -> None:
        """Hide the button if ekplorer is already the default file manager."""
        if _XDG_MIME is None:
            return
        try:
            result = subprocess.run(
                [_XDG_MIME, "query", "default", "inode/directory"],
                capture_output=True, text=True, timeout=2,
            )
            if result.returncode == 0 and result.stdout.strip() == "ekplorer.desktop":
                self._default_fm_bar.setVisible(False)
        except Exception:
            pass

    def _set_as_default_fm(self) -> None:
        if _XDG_MIME is not None:
            try:
                subprocess.run(
                    [_XDG_MIME, "default", "ekplorer.desktop", "inode/directory"],
                    check=False, capture_output=True, timeout=5,
                )
                subprocess.run(
                    [_XDG_MIME, "default", "ekplorer.desktop", "x-scheme-handler/file"],
                    check=False, capture_output=True, timeout=5,
                )
            except Exception:
                pass
        self._default_fm_bar.setVisible(False)
        self._show_toast(strings.NOTICE_SET_DEFAULT_FM_DONE)
