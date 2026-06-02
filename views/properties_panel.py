"""M10b/M10c/M10d: Properties panel — five-tab container.

M10b: shell.
M10c: General tab populated on selection.
M10d: Permissions / Checksums / Details / Open With tabs populated.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

import strings
from backends.file_ops_backend import (
    FileOpsBackend,
    _ChecksumWorker,
    _ChmodWorker,
    _OpenWithLoader,
)
from models.file_entry import FileEntry, fmt_size, mime_label

from PyQt6.QtCore import Qt, QThread
from PyQt6.QtWidgets import (
    QApplication,
    QFormLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)


class PropertiesPanel(QWidget):
    """Five-tab properties panel.

    Page 0: placeholder.
    Page 1: QTabWidget with General / Permissions / Checksums / Details / Open With.
    """

    _TAB_NAMES = [
        strings.PROP_TAB_GENERAL,
        strings.PROP_TAB_PERMISSIONS,
        strings.PROP_TAB_CHECKSUMS,
        strings.PROP_TAB_DETAILS,
        strings.PROP_TAB_OPEN_WITH,
    ]

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._stack = QStackedWidget()

        # ── Page 0: no-selection placeholder ─────────────────────────────────
        placeholder = QLabel(strings.PROP_NO_SELECTION)
        placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        placeholder.setStyleSheet("QLabel { color: palette(mid); }")
        self._stack.addWidget(placeholder)

        # ── Page 1: tab widget ────────────────────────────────────────────────
        self._tabs = QTabWidget()

        self._tabs.addTab(self._build_general_tab(),     strings.PROP_TAB_GENERAL)
        self._tabs.addTab(self._build_permissions_tab(), strings.PROP_TAB_PERMISSIONS)
        self._tabs.addTab(self._build_checksums_tab(),   strings.PROP_TAB_CHECKSUMS)
        self._tabs.addTab(self._build_details_tab(),     strings.PROP_TAB_DETAILS)
        self._tabs.addTab(self._build_openwith_tab(),    strings.PROP_TAB_OPEN_WITH)

        self._stack.addWidget(self._tabs)
        layout.addWidget(self._stack)

        self._stack.setCurrentIndex(0)
        self._current_entry: FileEntry | None = None

        # Incremented at the start of every populate_general() / show_placeholder().
        # Each worker callback checks its captured expected generation against this
        # value; a mismatch means the result is stale and must be discarded.
        self._generation: int = 0
        self._ow_expected_gen: int = -1
        self._cs_expected_gen: int = -1
        self._chmod_expected_gen: int = -1

        # Thread refs kept as attrs to prevent GC-during-running-thread SIGABRT
        self._cs_thread: QThread | None = None
        self._cs_worker: _ChecksumWorker | None = None
        self._chmod_thread: QThread | None = None
        self._chmod_worker: _ChmodWorker | None = None
        self._ow_thread: QThread | None = None
        self._ow_worker: _OpenWithLoader | None = None

    # ── Tab builders ──────────────────────────────────────────────────────────

    def _build_general_tab(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        body = QWidget()
        form = QFormLayout(body)
        form.setContentsMargins(12, 12, 12, 12)
        form.setVerticalSpacing(8)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        def _val() -> QLabel:
            lbl = QLabel("—")
            lbl.setWordWrap(True)
            lbl.setSizePolicy(
                QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
            return lbl

        self._val_name     = _val()
        self._val_type     = _val()
        self._val_size     = _val()
        self._val_location = _val()
        self._val_modified = _val()
        self._val_accessed = _val()
        self._val_created  = _val()

        for field, widget in [
            (strings.PROP_GENERAL_NAME,     self._val_name),
            (strings.PROP_GENERAL_TYPE,     self._val_type),
            (strings.PROP_GENERAL_SIZE,     self._val_size),
            (strings.PROP_GENERAL_LOCATION, self._val_location),
            (strings.PROP_GENERAL_MODIFIED, self._val_modified),
            (strings.PROP_GENERAL_ACCESSED, self._val_accessed),
            (strings.PROP_GENERAL_CREATED,  self._val_created),
        ]:
            form.addRow(f"{field}:", widget)

        scroll.setWidget(body)
        return scroll

    def _build_permissions_tab(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        body = QWidget()
        form = QFormLayout(body)
        form.setContentsMargins(12, 12, 12, 12)
        form.setVerticalSpacing(8)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        def _val() -> QLabel:
            lbl = QLabel("—")
            lbl.setWordWrap(True)
            return lbl

        self._perm_owner = _val()
        self._perm_group = _val()
        self._perm_mode  = _val()
        self._perm_octal = _val()

        form.addRow(f"{strings.PROP_PERM_OWNER}:", self._perm_owner)
        form.addRow(f"{strings.PROP_PERM_GROUP}:", self._perm_group)
        form.addRow(f"{strings.PROP_PERM_MODE}:",  self._perm_mode)
        form.addRow(f"{strings.PROP_PERM_OCTAL}:", self._perm_octal)

        self._chmod_btn = QPushButton(strings.PROP_PERM_CHANGE_BTN)
        self._chmod_btn.setEnabled(False)
        self._chmod_btn.clicked.connect(self._on_chmod_clicked)
        form.addRow("", self._chmod_btn)

        scroll.setWidget(body)
        return scroll

    def _build_checksums_tab(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        body = QWidget()
        form = QFormLayout(body)
        form.setContentsMargins(12, 12, 12, 12)
        form.setVerticalSpacing(8)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        def _val() -> QLabel:
            lbl = QLabel("—")
            lbl.setWordWrap(True)
            lbl.setSizePolicy(
                QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
            return lbl

        self._cs_md5    = _val()
        self._cs_sha1   = _val()
        self._cs_sha256 = _val()

        form.addRow("MD5:",     self._cs_md5)
        form.addRow("SHA-1:",   self._cs_sha1)
        form.addRow("SHA-256:", self._cs_sha256)

        self._cs_btn = QPushButton(strings.PROP_CHECKSUMS_COMPUTE)
        self._cs_btn.setEnabled(False)
        self._cs_btn.clicked.connect(self._on_compute_checksums)
        form.addRow("", self._cs_btn)

        scroll.setWidget(body)
        return scroll

    def _build_details_tab(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        body = QWidget()
        form = QFormLayout(body)
        form.setContentsMargins(12, 12, 12, 12)
        form.setVerticalSpacing(8)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        def _val() -> QLabel:
            lbl = QLabel("—")
            lbl.setWordWrap(True)
            return lbl

        self._det_inode  = _val()
        self._det_links  = _val()
        self._det_bsize  = _val()
        self._det_blocks = _val()

        form.addRow(f"{strings.PROP_DETAILS_INODE}:",      self._det_inode)
        form.addRow(f"{strings.PROP_DETAILS_LINKS}:",      self._det_links)
        form.addRow(f"{strings.PROP_DETAILS_BLOCK_SIZE}:", self._det_bsize)
        form.addRow(f"{strings.PROP_DETAILS_BLOCKS}:",     self._det_blocks)

        scroll.setWidget(body)
        return scroll

    def _build_openwith_tab(self) -> QWidget:
        widget = QWidget()
        vl = QVBoxLayout(widget)
        vl.setContentsMargins(12, 12, 12, 12)
        vl.setSpacing(8)

        vl.addWidget(QLabel(f"{strings.PROP_OPENWITH_DEFAULT}:"))
        self._ow_default_label = QLabel("—")
        self._ow_default_label.setWordWrap(True)
        vl.addWidget(self._ow_default_label)

        vl.addWidget(QLabel(f"{strings.PROP_OPENWITH_OTHERS}:"))
        self._ow_list = QListWidget()
        self._ow_list.setMaximumHeight(120)
        vl.addWidget(self._ow_list)

        self._ow_set_btn = QPushButton(strings.PROP_OPENWITH_SET_DEFAULT)
        self._ow_set_btn.setEnabled(False)
        self._ow_set_btn.clicked.connect(self._on_set_default_app)
        vl.addWidget(self._ow_set_btn)

        vl.addStretch()
        return widget

    # ── Public API ────────────────────────────────────────────────────────────

    def show_placeholder(self) -> None:
        self._cancel_workers()
        self._generation += 1
        self._stack.setCurrentIndex(0)
        self._current_entry = None

    def show_file(self) -> None:
        self._stack.setCurrentIndex(1)

    def populate_general(self, entry: FileEntry) -> None:
        """Populate all tabs from a FileEntry and switch to tab view."""
        self._cancel_workers()
        self._generation += 1
        self._current_entry = entry
        self._populate_general_fields(entry)
        self._populate_permissions(entry)
        self._populate_details(entry)
        self._reset_checksums(entry)
        self._populate_open_with(entry)
        self.show_file()

    def _cancel_workers(self) -> None:
        """Disconnect in-flight worker signals and release thread refs.

        _OpenWithLoader uses a subprocess so quit() won't stop it mid-run;
        signal disconnection + generation counter guard against stale results.
        """
        if self._ow_worker is not None:
            try:
                self._ow_worker.apps_ready.disconnect(self._on_apps_ready)
            except RuntimeError:
                pass
        if self._ow_thread is not None and self._ow_thread.isRunning():
            self._ow_thread.quit()
            self._ow_thread.wait(100)
        self._ow_thread = None
        self._ow_worker = None

        if self._cs_worker is not None:
            try:
                self._cs_worker.checksums_ready.disconnect(self._on_checksums_ready)
                self._cs_worker.failed.disconnect(self._on_checksums_failed)
            except RuntimeError:
                pass
        if self._cs_thread is not None and self._cs_thread.isRunning():
            self._cs_thread.quit()
            self._cs_thread.wait(100)
        self._cs_thread = None
        self._cs_worker = None

        if self._chmod_worker is not None:
            try:
                self._chmod_worker.done.disconnect(self._on_chmod_done)
                self._chmod_worker.failed.disconnect(self._on_chmod_failed)
            except RuntimeError:
                pass
        if self._chmod_thread is not None and self._chmod_thread.isRunning():
            self._chmod_thread.quit()
            self._chmod_thread.wait(100)
        self._chmod_thread = None
        self._chmod_worker = None

    # ── General tab ───────────────────────────────────────────────────────────

    def _populate_general_fields(self, entry: FileEntry) -> None:
        self._val_name.setText(entry.name)
        self._val_type.setText(mime_label(entry.mime_type, entry.is_dir))
        self._val_size.setText(
            fmt_size(entry.size) if not entry.is_dir else "—")
        self._val_location.setText(str(entry.path.parent))
        self._val_modified.setText(
            datetime.fromtimestamp(entry.modified).strftime("%Y-%m-%d  %H:%M:%S"))
        try:
            st = entry.path.stat()
            self._val_accessed.setText(
                datetime.fromtimestamp(st.st_atime).strftime("%Y-%m-%d  %H:%M:%S"))
            self._val_created.setText(
                datetime.fromtimestamp(st.st_ctime).strftime("%Y-%m-%d  %H:%M:%S"))
        except OSError:
            self._val_accessed.setText("—")
            self._val_created.setText("—")

    # ── Permissions tab ───────────────────────────────────────────────────────

    def _populate_permissions(self, entry: FileEntry) -> None:
        try:
            info = FileOpsBackend().get_stat_info(entry.path)
            self._perm_owner.setText(f"{info['owner']}  (uid {info['uid']})")
            self._perm_group.setText(f"{info['group']}  (gid {info['gid']})")
            self._perm_mode.setText(info["mode"])
            self._perm_octal.setText(info["octal"])
            self._chmod_btn.setEnabled(True)
        except OSError:
            for lbl in (self._perm_owner, self._perm_group,
                        self._perm_mode, self._perm_octal):
                lbl.setText("—")
            self._chmod_btn.setEnabled(False)

    def _on_chmod_clicked(self) -> None:
        if self._current_entry is None:
            return
        try:
            current_octal = FileOpsBackend().get_stat_info(
                self._current_entry.path)["octal"].lstrip("0o") or "0"
        except OSError:
            current_octal = ""
        new_str, ok = QInputDialog.getText(
            self, strings.PROP_PERM_CHANGE_BTN,
            strings.PROP_PERM_CHANGE_LABEL,
            text=current_octal,
        )
        if not ok or not new_str.strip():
            return
        try:
            mode_int = int(new_str.strip(), 8)
        except ValueError:
            QMessageBox.warning(self, strings.PROP_PERM_CHANGE_BTN,
                                "Invalid octal value.")
            return
        self._chmod_btn.setEnabled(False)
        self._chmod_expected_gen = self._generation

        if self._chmod_thread and self._chmod_thread.isRunning():
            self._chmod_thread.quit()

        self._chmod_thread = QThread(parent=QApplication.instance())
        self._chmod_worker = _ChmodWorker(self._current_entry.path, mode_int)
        self._chmod_worker.moveToThread(self._chmod_thread)
        self._chmod_thread.started.connect(self._chmod_worker.run)
        self._chmod_worker.done.connect(self._on_chmod_done)
        self._chmod_worker.failed.connect(self._on_chmod_failed)
        self._chmod_worker.done.connect(self._chmod_thread.quit)
        self._chmod_worker.failed.connect(self._chmod_thread.quit)
        self._chmod_thread.finished.connect(self._chmod_worker.deleteLater)
        self._chmod_thread.finished.connect(self._chmod_thread.deleteLater)
        self._chmod_thread.start()

    def _on_chmod_done(self) -> None:
        if self._chmod_expected_gen != self._generation:
            return
        self._chmod_btn.setEnabled(True)
        if self._current_entry:
            self._populate_permissions(self._current_entry)

    def _on_chmod_failed(self, message: str) -> None:
        if self._chmod_expected_gen != self._generation:
            return
        self._chmod_btn.setEnabled(True)
        QMessageBox.warning(self, strings.PROP_PERM_CHANGE_BTN, message)

    # ── Checksums tab ─────────────────────────────────────────────────────────

    def _reset_checksums(self, entry: FileEntry) -> None:
        for lbl in (self._cs_md5, self._cs_sha1, self._cs_sha256):
            lbl.setText("—")
        self._cs_btn.setEnabled(not entry.is_dir)
        self._cs_btn.setText(strings.PROP_CHECKSUMS_COMPUTE)

    def _on_compute_checksums(self) -> None:
        if self._current_entry is None or self._current_entry.is_dir:
            return
        self._cs_btn.setEnabled(False)
        self._cs_btn.setText(strings.PROP_CHECKSUMS_COMPUTING)
        self._cs_expected_gen = self._generation

        if self._cs_thread and self._cs_thread.isRunning():
            self._cs_thread.quit()

        self._cs_thread = QThread(parent=QApplication.instance())
        self._cs_worker = _ChecksumWorker(self._current_entry.path)
        self._cs_worker.moveToThread(self._cs_thread)
        self._cs_thread.started.connect(self._cs_worker.run)
        self._cs_worker.checksums_ready.connect(self._on_checksums_ready)
        self._cs_worker.failed.connect(self._on_checksums_failed)
        self._cs_worker.checksums_ready.connect(self._cs_thread.quit)
        self._cs_worker.failed.connect(self._cs_thread.quit)
        self._cs_thread.finished.connect(self._cs_worker.deleteLater)
        self._cs_thread.finished.connect(self._cs_thread.deleteLater)
        self._cs_thread.start()

    def _on_checksums_ready(self, sums: dict) -> None:
        if self._cs_expected_gen != self._generation:
            return
        self._cs_md5.setText(sums.get("MD5", "—"))
        self._cs_sha1.setText(sums.get("SHA-1", "—"))
        self._cs_sha256.setText(sums.get("SHA-256", "—"))
        self._cs_btn.setEnabled(True)
        self._cs_btn.setText(strings.PROP_CHECKSUMS_COMPUTE)

    def _on_checksums_failed(self, message: str) -> None:
        if self._cs_expected_gen != self._generation:
            return
        self._cs_btn.setEnabled(True)
        self._cs_btn.setText(strings.PROP_CHECKSUMS_COMPUTE)
        QMessageBox.warning(self, strings.PROP_TAB_CHECKSUMS, message)

    # ── Details tab ───────────────────────────────────────────────────────────

    def _populate_details(self, entry: FileEntry) -> None:
        try:
            info = FileOpsBackend().get_stat_info(entry.path)
            self._det_inode.setText(str(info["inode"]))
            self._det_links.setText(str(info["links"]))
            self._det_bsize.setText(str(info["block_size"]))
            self._det_blocks.setText(str(info["blocks"]))
        except OSError:
            for lbl in (self._det_inode, self._det_links,
                        self._det_bsize, self._det_blocks):
                lbl.setText("—")

    # ── Open With tab ─────────────────────────────────────────────────────────

    def _populate_open_with(self, entry: FileEntry) -> None:
        self._ow_default_label.setText(strings.PROP_OPENWITH_LOADING)
        self._ow_list.clear()
        self._ow_set_btn.setEnabled(False)
        self._ow_expected_gen = self._generation

        self._ow_thread = QThread(parent=QApplication.instance())
        self._ow_worker = _OpenWithLoader(entry.mime_type)
        self._ow_worker.moveToThread(self._ow_thread)
        self._ow_thread.started.connect(self._ow_worker.run)
        self._ow_worker.apps_ready.connect(self._on_apps_ready)
        self._ow_worker.apps_ready.connect(self._ow_thread.quit)
        self._ow_thread.finished.connect(self._ow_worker.deleteLater)
        self._ow_thread.finished.connect(self._ow_thread.deleteLater)
        self._ow_thread.start()

    def _on_apps_ready(self, apps: list) -> None:
        if self._ow_expected_gen != self._generation:
            return
        if not apps:
            self._ow_default_label.setText(strings.PROP_OPENWITH_NONE)
            return
        self._ow_default_label.setText(apps[0])
        self._ow_list.clear()
        for app in apps[1:]:
            self._ow_list.addItem(QListWidgetItem(app))
        self._ow_set_btn.setEnabled(self._ow_list.count() > 0)

    def _on_set_default_app(self) -> None:
        item = self._ow_list.currentItem()
        if item is None or self._current_entry is None:
            return
        FileOpsBackend().set_default_app(
            self._current_entry.mime_type, item.text())
        self._populate_open_with(self._current_entry)
