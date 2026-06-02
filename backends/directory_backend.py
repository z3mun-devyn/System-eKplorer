"""Async directory listing worker for the File Manager."""
from __future__ import annotations

import mimetypes
import stat
from pathlib import Path

from models.file_entry import FileEntry

from PyQt6.QtCore import QObject, pyqtSignal


class DirectoryLoader(QObject):
    """QObject worker — run on a QThread.

    Emits ready(list[FileEntry]) on success or failed(str) on fatal error.
    Per-entry OSError is silently skipped so one bad symlink cannot abort
    the whole listing.
    """

    ready  = pyqtSignal(list)   # list[FileEntry]
    failed = pyqtSignal(str)

    def __init__(self, path: Path, show_hidden: bool) -> None:
        super().__init__()
        self._path = path
        self._show_hidden = show_hidden

    def run(self) -> None:
        try:
            try:
                items = list(self._path.iterdir())
            except PermissionError as exc:
                self.failed.emit(str(exc))
                return

            entries: list[FileEntry] = []
            for item in items:
                try:
                    is_hidden = item.name.startswith(".")
                    if is_hidden and not self._show_hidden:
                        continue
                    st = item.stat(follow_symlinks=True)
                    is_dir = stat.S_ISDIR(st.st_mode)
                    size = None if is_dir else st.st_size
                    item_count: int | None = None
                    if is_dir:
                        mime_type = "inode/directory"
                        try:
                            item_count = sum(1 for _ in item.iterdir())
                        except PermissionError:
                            item_count = None
                    else:
                        guessed, _ = mimetypes.guess_type(item.name)
                        mime_type = guessed or "application/octet-stream"
                    entries.append(FileEntry(
                        name=item.name,
                        path=item,
                        size=size,
                        modified=st.st_mtime,
                        mime_type=mime_type,
                        is_dir=is_dir,
                        is_hidden=is_hidden,
                        item_count=item_count,
                    ))
                except OSError:
                    continue

            self.ready.emit(entries)
        except Exception as exc:
            self.failed.emit(str(exc))
