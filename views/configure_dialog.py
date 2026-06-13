"""Centralised settings dialog — opened via the gear button in the tab bar."""

from __future__ import annotations

import getpass
import grp
import os
import shutil
import subprocess
from pathlib import Path

import skin_background
import skin_loader
import skin_manager
import strings
from backends.settings_backend import SettingsRepository

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QIcon, QPixmap
from PyQt6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QSpinBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

_XDG_MIME = shutil.which("xdg-mime")

# Ordered list of settings key values matching the startup-tab combo box.
_STARTUP_TAB_KEYS = [
    "dashboard",
    "file_manager",
    "packages",
    "terminal",
    "clipboard",
]

_CAT_GENERAL      = 0
_CAT_FILE_MANAGER = 1
_CAT_DASHBOARD    = 2
_CAT_CLIPBOARD    = 3
_CAT_SYSTEM       = 4
_CAT_APPEARANCE   = 5
_CAT_ABOUT        = 6


class ConfigureDialog(QDialog):
    def __init__(
        self,
        parent: QWidget | None = None,
        db_path: Path | None = None,
    ) -> None:
        super().__init__(parent)
        self._db_path = db_path
        self._settings = SettingsRepository(db_path)

        # ClipboardBackend is optional — gracefully absent if not yet built.
        self._cb_backend = None
        try:
            from backends.clipboard_backend import ClipboardBackend
            self._cb_backend = ClipboardBackend(db_path)
        except ImportError:
            pass

        self.setWindowTitle(strings.CONFIGURE_TITLE)
        self.setModal(True)
        self.setFixedSize(680, 460)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # ── Body: left category list + right stacked pages ────────────────────
        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)

        self._cat_list = QListWidget()
        self._cat_list.setFixedWidth(160)
        self._cat_list.setFrameShape(QFrame.Shape.NoFrame)
        self._cat_list.setStyleSheet(
            "QListWidget { border-right: 1px solid palette(mid); }"
            "QListWidget::item { padding: 8px 12px; }"
            "QListWidget::item:selected {"
            "  background: palette(highlight);"
            "  color: palette(highlighted-text);"
            "}"
        )

        _categories = [
            ("preferences-system",  strings.CONFIGURE_CAT_GENERAL),
            ("folder",              strings.CONFIGURE_CAT_FILE_MANAGER),
            ("utilities-system-monitor", strings.CONFIGURE_CAT_DASHBOARD),
            ("edit-paste",          strings.CONFIGURE_CAT_CLIPBOARD),
            ("preferences-desktop", strings.CONFIGURE_CAT_SYSTEM),
            ("preferences-desktop-theme", strings.CONFIGURE_CAT_APPEARANCE),
            ("help-about",          strings.CONFIGURE_CAT_ABOUT),
        ]
        for icon_name, label in _categories:
            item = QListWidgetItem(QIcon.fromTheme(icon_name), label)
            self._cat_list.addItem(item)

        body.addWidget(self._cat_list)

        self._stack = QStackedWidget()
        self._stack.addWidget(self._build_general_page())
        self._stack.addWidget(self._build_fm_page())
        self._stack.addWidget(self._build_dashboard_page())
        self._stack.addWidget(self._build_clipboard_page())
        self._stack.addWidget(self._build_system_page())
        self._stack.addWidget(self._build_appearance_page())
        self._stack.addWidget(self._build_about_page())
        body.addWidget(self._stack, stretch=1)

        self._cat_list.currentRowChanged.connect(self._stack.setCurrentIndex)
        self._cat_list.setCurrentRow(0)

        outer.addLayout(body, stretch=1)

        # ── Separator ─────────────────────────────────────────────────────────
        sep = QWidget()
        sep.setFixedHeight(1)
        sep.setStyleSheet("QWidget { background: palette(mid); }")
        outer.addWidget(sep)

        # ── OK / Cancel ───────────────────────────────────────────────────────
        btn_row = QWidget()
        btn_layout = QHBoxLayout(btn_row)
        btn_layout.setContentsMargins(8, 8, 8, 8)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._on_ok)
        buttons.rejected.connect(self.reject)
        btn_layout.addWidget(buttons)
        outer.addWidget(btn_row)

        self._load_settings()

    # ── Page builders ─────────────────────────────────────────────────────────

    def _build_general_page(self) -> QWidget:
        page = QWidget()
        layout = QFormLayout(page)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        self._startup_combo = QComboBox()
        self._startup_combo.addItems([
            strings.TAB_DASHBOARD,
            strings.TAB_FILE_MANAGER,
            strings.TAB_PACKAGES,
            strings.TAB_TERMINAL,
            strings.TAB_CLIPBOARD,
        ])
        layout.addRow(strings.CONFIGURE_STARTUP_TAB, self._startup_combo)

        self._reduce_anim_cb = QCheckBox(strings.CONFIGURE_REDUCE_ANIM)
        layout.addRow("", self._reduce_anim_cb)

        return page

    def _build_fm_page(self) -> QWidget:
        page = QWidget()
        layout = QFormLayout(page)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        self._fm_view_combo = QComboBox()
        self._fm_view_combo.addItems(["Details", "Icons"])
        layout.addRow(strings.CONFIGURE_FM_DEFAULT_VIEW, self._fm_view_combo)

        self._fm_hidden_cb = QCheckBox(strings.CONFIGURE_FM_SHOW_HIDDEN)
        layout.addRow("", self._fm_hidden_cb)

        self._fm_addr_combo = QComboBox()
        self._fm_addr_combo.addItems(["Path", "Breadcrumb"])
        layout.addRow(strings.CONFIGURE_FM_ADDRESS_BAR, self._fm_addr_combo)

        return page

    def _build_dashboard_page(self) -> QWidget:
        page = QWidget()
        layout = QFormLayout(page)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        rb_container = QWidget()
        rb_layout = QHBoxLayout(rb_container)
        rb_layout.setContentsMargins(0, 0, 0, 0)
        rb_layout.setSpacing(16)

        self._dash_simple_rb = QRadioButton(strings.CONFIGURE_DASH_SIMPLE)
        self._dash_advanced_rb = QRadioButton(strings.CONFIGURE_DASH_ADVANCED)

        self._dash_rb_group = QButtonGroup(page)
        self._dash_rb_group.addButton(self._dash_simple_rb, 0)
        self._dash_rb_group.addButton(self._dash_advanced_rb, 1)

        rb_layout.addWidget(self._dash_simple_rb)
        rb_layout.addWidget(self._dash_advanced_rb)
        rb_layout.addStretch()

        layout.addRow(strings.CONFIGURE_DASH_VIEW_MODE, rb_container)
        return page

    def _build_clipboard_page(self) -> QWidget:
        page = QWidget()
        layout = QFormLayout(page)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        self._cb_spinbox = QSpinBox()
        self._cb_spinbox.setRange(1, 100)
        self._cb_spinbox.setToolTip(strings.CONFIGURE_CB_MAX_TOOLTIP)
        layout.addRow(strings.CONFIGURE_CB_MAX_ENTRIES, self._cb_spinbox)

        clear_btn = QPushButton(strings.CONFIGURE_CB_CLEAR_ALL)
        if self._cb_backend is None:
            clear_btn.setEnabled(False)
            clear_btn.setToolTip("Available after Clipboard tab is built.")
        else:
            clear_btn.clicked.connect(self._on_clear_clipboard)
        layout.addRow("", clear_btn)

        return page

    def _build_system_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        self._sys_fm_status = QLabel()
        layout.addWidget(self._sys_fm_status)

        self._sys_fm_set_btn = QPushButton(strings.CONFIGURE_SYS_FM_SET_BTN)
        self._sys_fm_set_btn.setFixedWidth(160)
        self._sys_fm_set_btn.clicked.connect(self._on_set_default_fm)
        layout.addWidget(self._sys_fm_set_btn)

        # ── SMART Access section ──────────────────────────────────────────────
        sep = QWidget()
        sep.setFixedHeight(1)
        sep.setStyleSheet("QWidget { background: palette(mid); }")
        layout.addWidget(sep)

        smart_title = QLabel(strings.CONFIGURE_SYS_SMART_TITLE)
        sf = QFont()
        sf.setBold(True)
        smart_title.setFont(sf)
        layout.addWidget(smart_title)

        smart_desc = QLabel(strings.CONFIGURE_SYS_SMART_LABEL)
        smart_desc.setWordWrap(True)
        layout.addWidget(smart_desc)

        cmd_row = QHBoxLayout()
        cmd_label = QLabel(f"<code>{strings.CONFIGURE_SYS_SMART_CMD}</code>")
        cmd_label.setWordWrap(True)
        cmd_row.addWidget(cmd_label, stretch=1)
        copy_btn = QPushButton(strings.CONFIGURE_SYS_SMART_COPY_CMD)
        copy_btn.setFixedWidth(120)
        copy_btn.clicked.connect(self._on_copy_smart_cmd)
        cmd_row.addWidget(copy_btn)
        layout.addLayout(cmd_row)

        self._smart_group_status = QLabel()
        self._refresh_smart_group_status()
        layout.addWidget(self._smart_group_status)

        layout.addStretch()

        self._refresh_default_fm_status()

        return page

    def _build_appearance_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        hint = QLabel(strings.CONFIGURE_APPEARANCE_HINT)
        hint.setWordWrap(True)
        hint.setStyleSheet("color: palette(mid);")
        layout.addWidget(hint)

        row = QHBoxLayout()
        row.setSpacing(16)

        # Left: the list of skins (synthetic "off" first, then bundled/user).
        self._skins = skin_loader.discover_skins()
        self._skin_list = QListWidget()
        self._skin_list.setFixedWidth(180)
        for skin in self._skins:
            item = QListWidgetItem(skin.name)
            item.setData(Qt.ItemDataRole.UserRole, skin.id)
            self._skin_list.addItem(item)
        self._skin_list.currentRowChanged.connect(self._on_skin_row_changed)
        row.addWidget(self._skin_list)

        # Right: live preview panel.
        preview = QVBoxLayout()
        preview.setSpacing(6)

        self._skin_thumb = QLabel(strings.CONFIGURE_APPEARANCE_NO_PREVIEW)
        self._skin_thumb.setFixedSize(260, 150)
        self._skin_thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._skin_thumb.setStyleSheet(
            "QLabel { border: 1px solid palette(mid); color: palette(mid); }"
        )
        preview.addWidget(self._skin_thumb)

        self._skin_name = QLabel()
        nf = QFont()
        nf.setBold(True)
        self._skin_name.setFont(nf)
        preview.addWidget(self._skin_name)

        self._skin_desc = QLabel()
        self._skin_desc.setWordWrap(True)
        preview.addWidget(self._skin_desc)

        self._skin_attrib = QLabel()
        self._skin_attrib.setWordWrap(True)
        self._skin_attrib.setStyleSheet("color: palette(mid); font-size: 10px;")
        preview.addWidget(self._skin_attrib)

        # Background fit picker (per-skin, persisted; disabled for off/palette-only).
        fit_row = QHBoxLayout()
        fit_row.addWidget(QLabel(strings.CONFIGURE_APPEARANCE_FIT_LABEL))
        self._fit_combo = QComboBox()
        self._fit_combo.addItem(strings.CONFIGURE_APPEARANCE_FIT_COVER, "cover")
        self._fit_combo.addItem(strings.CONFIGURE_APPEARANCE_FIT_CONTAIN, "contain")
        self._fit_combo.addItem(strings.CONFIGURE_APPEARANCE_FIT_STRETCH, "stretch")
        self._fit_combo.currentIndexChanged.connect(self._on_fit_changed)
        fit_row.addWidget(self._fit_combo)
        fit_row.addStretch()
        preview.addLayout(fit_row)

        preview.addStretch()
        row.addLayout(preview, stretch=1)
        layout.addLayout(row)
        return page

    # ── Appearance preview helpers ─────────────────────────────────────────────

    def _on_skin_row_changed(self, row: int) -> None:
        if row < 0 or row >= len(self._skins):
            return
        skin = self._skins[row]
        self._apply_skin_preview(skin.id)
        self._update_skin_preview_panel(skin)
        self._update_fit_combo(skin)

    def _apply_skin_preview(self, skin_id: str) -> None:
        """Apply a skin to the whole app for live preview (or restore baseline)."""
        app = QApplication.instance()
        if app is None:
            return
        role_map = skin_loader.resolve_role_map(
            skin_id,
            self._skins,
            override_lookup=lambda role: self._settings.get(
                f"appearance.override.{skin_id}.{role}"),
        )
        if role_map is None:
            skin_manager.restore_baseline(app)
        else:
            skin_manager.apply_skin(app, role_map)

        # Drive the FM-viewport wallpaper live alongside the palette preview,
        # honoring the user's per-skin fit override.
        if skin_id == "off":
            skin_background.set_active(None)
        else:
            skin = next((s for s in self._skins if s.id == skin_id), None)
            fit = self._settings.get(f"appearance.fit.{skin_id}")
            skin_background.set_active(skin, fit)

    def _update_fit_combo(self, skin) -> None:
        """Reflect the resolved fit for ``skin`` and enable only when it has a bg."""
        has_bg = (
            skin is not None and skin.id != "off"
            and bool(getattr(skin, "background", None))
            and bool(skin.background.get("image"))
        )
        self._fit_combo.setEnabled(has_bg)
        override = self._settings.get(f"appearance.fit.{skin.id}") if has_bg else None
        resolved = skin_background.resolve_fit(skin, override)
        idx = self._fit_combo.findData(resolved)
        blocked = self._fit_combo.blockSignals(True)   # don't fire _on_fit_changed
        self._fit_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self._fit_combo.blockSignals(blocked)

    def _on_fit_changed(self, _index: int) -> None:
        row = self._skin_list.currentRow()
        if row < 0 or row >= len(self._skins):
            return
        skin = self._skins[row]
        if skin.id == "off":
            return
        mode = self._fit_combo.currentData()
        # Commit immediately (crash-safe), then re-render the viewport live.
        self._settings.set(f"appearance.fit.{skin.id}", mode)
        skin_background.set_active(skin, mode)

    def _update_skin_preview_panel(self, skin) -> None:
        self._skin_name.setText(skin.name)
        self._skin_desc.setText(skin.description)

        if skin.attribution:
            parts = []
            for entry in skin.attribution:
                author = entry.get("author", "")
                source = entry.get("source", "")
                if author and source:
                    parts.append(f"{author} — {source}")
                elif author or source:
                    parts.append(author or source)
                elif entry.get("text"):          # legacy P2 fallback
                    parts.append(entry["text"])
            self._skin_attrib.setText(" · ".join(p for p in parts if p))
        else:
            self._skin_attrib.clear()

        pixmap = None
        if skin.path is not None and skin.background:
            image = skin.background.get("image")
            if image:
                img_path = Path(skin.path) / image
                if img_path.is_file():
                    pm = QPixmap(str(img_path))
                    if not pm.isNull():
                        pixmap = pm.scaled(
                            self._skin_thumb.width(),
                            self._skin_thumb.height(),
                            Qt.AspectRatioMode.KeepAspectRatio,
                            Qt.TransformationMode.SmoothTransformation,
                        )
        if pixmap is not None:
            self._skin_thumb.setPixmap(pixmap)
        else:
            self._skin_thumb.clear()
            self._skin_thumb.setText(strings.CONFIGURE_APPEARANCE_NO_PREVIEW)

    def _build_about_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(24, 16, 24, 16)
        layout.setSpacing(8)
        layout.addStretch()

        title_lbl = QLabel(strings.APP_TITLE)
        f = QFont()
        f.setBold(True)
        f.setPointSize(title_lbl.font().pointSize() + 4)
        title_lbl.setFont(f)
        title_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title_lbl)

        version_lbl = QLabel(f"Version {strings.APP_VERSION}")
        version_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(version_lbl)

        license_lbl = QLabel(
            f'<a href="https://www.gnu.org/licenses/gpl-3.0.html">'
            f"{strings.CONFIGURE_ABOUT_LICENSE}</a>"
        )
        license_lbl.setOpenExternalLinks(True)
        license_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(license_lbl)

        if strings.APP_REPO_URL:
            repo_lbl = QLabel(
                f'{strings.CONFIGURE_ABOUT_REPO} '
                f'<a href="{strings.APP_REPO_URL}">{strings.APP_REPO_URL}</a>'
            )
            repo_lbl.setOpenExternalLinks(True)
            repo_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(repo_lbl)

        layout.addStretch()
        return page

    # ── Settings I/O ─────────────────────────────────────────────────────────

    def _load_settings(self) -> None:
        # General
        startup = self._settings.get("app.startup_tab") or "dashboard"
        idx = _STARTUP_TAB_KEYS.index(startup) if startup in _STARTUP_TAB_KEYS else 0
        self._startup_combo.setCurrentIndex(idx)
        self._reduce_anim_cb.setChecked(
            self._settings.get("ui.reduce_animations") == "true"
        )

        # File Manager
        view_mode = self._settings.get("fm.view_mode") or "details"
        self._fm_view_combo.setCurrentIndex(0 if view_mode == "details" else 1)

        show_hidden = self._settings.get("fm.show_hidden") == "true"
        self._fm_hidden_cb.setChecked(show_hidden)

        addr_mode = self._settings.get("fm.address_bar.mode") or "path"
        self._fm_addr_combo.setCurrentIndex(0 if addr_mode == "path" else 1)

        # Dashboard
        dash_mode = self._settings.get("dashboard.view_mode") or "simple"
        if dash_mode == "advanced":
            self._dash_advanced_rb.setChecked(True)
        else:
            self._dash_simple_rb.setChecked(True)

        # Clipboard
        max_e = 10
        v = self._settings.get("clipboard.max_entries")
        if v is not None:
            try:
                max_e = max(1, int(v))
            except ValueError:
                pass
        self._cb_spinbox.setValue(max_e)

        # Appearance — select the active skin and remember it for Cancel revert.
        self._original_skin_id = self._settings.get("appearance.active_skin") or "off"
        target_row = next(
            (i for i, s in enumerate(self._skins) if s.id == self._original_skin_id),
            0,
        )
        self._skin_list.setCurrentRow(target_row)

    def _on_ok(self) -> None:
        # General
        startup_key = _STARTUP_TAB_KEYS[self._startup_combo.currentIndex()]
        self._settings.set("app.startup_tab", startup_key)
        self._settings.set(
            "ui.reduce_animations",
            "true" if self._reduce_anim_cb.isChecked() else "false",
        )

        # File Manager
        view_mode = "details" if self._fm_view_combo.currentIndex() == 0 else "icons"
        self._settings.set("fm.view_mode", view_mode)

        show_hidden = "true" if self._fm_hidden_cb.isChecked() else "false"
        self._settings.set("fm.show_hidden", show_hidden)

        addr_mode = "path" if self._fm_addr_combo.currentIndex() == 0 else "breadcrumb"
        self._settings.set("fm.address_bar.mode", addr_mode)

        # Dashboard
        dash_mode = "advanced" if self._dash_advanced_rb.isChecked() else "simple"
        self._settings.set("dashboard.view_mode", dash_mode)

        # Clipboard
        self._settings.set("clipboard.max_entries", str(self._cb_spinbox.value()))

        # Appearance — the selected skin is already applied live; persist the choice.
        selected = self._skin_list.currentItem()
        if selected is not None:
            self._settings.set(
                "appearance.active_skin",
                selected.data(Qt.ItemDataRole.UserRole),
            )

        self.accept()

    def reject(self) -> None:
        # Revert any live skin preview to whatever was active when the dialog opened.
        self._apply_skin_preview(getattr(self, "_original_skin_id", "off"))
        super().reject()

    # ── System page ───────────────────────────────────────────────────────────

    def _query_default_fm(self) -> str | None:
        """Return current default handler for inode/directory, or None."""
        if _XDG_MIME is None:
            return None
        try:
            result = subprocess.run(
                [_XDG_MIME, "query", "default", "inode/directory"],
                capture_output=True, text=True, timeout=2,
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except Exception:
            pass
        return None

    def _refresh_default_fm_status(self) -> None:
        if self._query_default_fm() == "ekplorer.desktop":
            self._sys_fm_status.setText(strings.CONFIGURE_SYS_FM_STATUS_IS)
            self._sys_fm_set_btn.setEnabled(False)
        else:
            self._sys_fm_status.setText(strings.CONFIGURE_SYS_FM_STATUS_NOT)
            self._sys_fm_set_btn.setEnabled(True)

    def _refresh_smart_group_status(self) -> None:
        try:
            disk_group = grp.getgrnam("disk")
            in_group = getpass.getuser() in disk_group.gr_mem
        except (KeyError, OSError):
            in_group = False
        if in_group:
            self._smart_group_status.setText(strings.CONFIGURE_SYS_SMART_IN_GROUP)
            self._smart_group_status.setStyleSheet("color: #27ae60;")
        else:
            self._smart_group_status.setText(strings.CONFIGURE_SYS_SMART_NOT_IN_GROUP)
            self._smart_group_status.setStyleSheet("color: palette(mid);")

    def _on_copy_smart_cmd(self) -> None:
        QApplication.clipboard().setText(strings.CONFIGURE_SYS_SMART_CMD)

    def _on_set_default_fm(self) -> None:
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
        self._refresh_default_fm_status()

    # ── Clipboard page ────────────────────────────────────────────────────────

    def _on_clear_clipboard(self) -> None:
        if self._cb_backend is None:
            return
        reply = QMessageBox.question(
            self,
            strings.CONFIGURE_CB_CLEAR_TITLE,
            strings.CONFIGURE_CB_CLEAR_MSG,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._cb_backend.clear_unpinned()
