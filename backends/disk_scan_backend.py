"""Categorised disk-usage scanner + QThread worker."""

from __future__ import annotations

import mimetypes
import os
from collections import defaultdict
from pathlib import Path

from PyQt6.QtCore import QObject, pyqtSignal

DISK_CATEGORIES: dict[str, str] = {
    "System & OS":           "#5A6B7B",
    "Applications":          "#2D7DD2",
    "Documents":             "#27AE60",
    "Pictures":              "#9B59B6",
    "Videos":                "#E74C3C",
    "Music & Audio":         "#E67E22",
    "Archives":              "#E91E8C",
    "Development":           "#F1C40F",
    "Other":                 "#7F8C8D",  # internal key used by pie widget
}

DISK_FREE_COLOR = "#2C3440"

_SYSTEM_PREFIXES = ("/usr", "/lib", "/lib64", "/bin", "/sbin", "/etc", "/boot", "/snap")
_APP_PREFIXES = ("/opt", "/var/lib/flatpak", str(Path.home() / ".local/share/flatpak"))
_SKIP_UNDER_ROOT = ("/proc", "/sys", "/dev", "/run", "/tmp")

_ARCHIVE_EXTS = {".zip", ".tar", ".gz", ".bz2", ".xz", ".7z", ".rar", ".deb", ".rpm"}
_DEV_EXTS = {
    ".py", ".js", ".ts", ".c", ".cpp", ".h", ".hpp", ".java", ".rs", ".go",
    ".sh", ".rb", ".php", ".css", ".html", ".json", ".yaml", ".toml", ".sql",
    ".md", ".rst",
}
_ARCHIVE_MIMES = {
    "application/zip", "application/x-tar", "application/gzip",
    "application/x-bzip2", "application/x-xz", "application/x-7z-compressed",
    "application/vnd.debian.binary-package", "application/x-rpm",
}


def _categorize(path: str, filename: str) -> str:
    if any(path == p or path.startswith(p + "/") for p in _SYSTEM_PREFIXES):
        return "System & OS"
    if any(path == p or path.startswith(p + "/") for p in _APP_PREFIXES):
        return "Applications"

    suffix = os.path.splitext(filename)[1].lower()

    # Extension check before MIME so dev-file extensions (text/x-python etc.)
    # are not swallowed by the text/* Documents catch-all.
    if suffix in _DEV_EXTS:
        return "Development"
    if suffix in _ARCHIVE_EXTS:
        return "Archives"

    mime, _ = mimetypes.guess_type(filename)
    if mime:
        major = mime.split("/")[0]
        if major == "image":
            return "Pictures"
        if major == "video":
            return "Videos"
        if major == "audio":
            return "Music & Audio"
        if major == "text" or mime in (
            "application/pdf", "application/msword",
        ) or mime.startswith((
            "application/vnd.openxmlformats",
            "application/vnd.oasis",
            "application/vnd.ms-",
        )):
            return "Documents"
        if mime in _ARCHIVE_MIMES:
            return "Archives"

    return "Other"


class DiskScanBackend:
    def scan(
        self,
        mount_point: str,
        progress_cb=None,
        cancel_check=None,
    ) -> dict[str, int]:
        result: dict[str, int] = defaultdict(int)
        count = 0
        try:
            root_dev = os.stat(mount_point).st_dev
        except OSError:
            root_dev = None

        for dirpath, dirnames, filenames in os.walk(
            mount_point, topdown=True, followlinks=False, onerror=lambda e: None
        ):
            if cancel_check and cancel_check():
                return {}
            if mount_point == "/" and any(
                dirpath == p or dirpath.startswith(p + "/")
                for p in _SKIP_UNDER_ROOT
            ):
                dirnames.clear()
                continue

            # Prune subdirectories that belong to a different filesystem so we
            # don't count data from btrfs subvolumes, ZFS pools, or other mounts
            # nested inside this one (root cause of inflated category totals).
            if root_dev is not None:
                kept = []
                for d in dirnames:
                    try:
                        if os.stat(os.path.join(dirpath, d)).st_dev == root_dev:
                            kept.append(d)
                    except OSError:
                        pass
                dirnames[:] = kept

            for fname in filenames:
                fpath = os.path.join(dirpath, fname)
                try:
                    size = os.stat(fpath, follow_symlinks=False).st_size
                except (PermissionError, OSError):
                    continue
                cat = _categorize(dirpath, fname)
                result[cat] += size
                count += 1
                if progress_cb and count % 500 == 0:
                    progress_cb(sum(result.values()))
        return {k: v for k, v in result.items() if v > 0}


class DiskScanWorker(QObject):
    progress = pyqtSignal(int)
    finished = pyqtSignal(dict)
    failed = pyqtSignal(str)

    def __init__(self, mount_point: str) -> None:
        super().__init__()
        self._mount_point = mount_point
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    def run(self) -> None:
        try:
            data = DiskScanBackend().scan(
                self._mount_point,
                self._emit_progress,
                cancel_check=lambda: self._cancelled,
            )
            if not self._cancelled:
                self.finished.emit(data)
        except Exception as exc:
            if not self._cancelled:
                self.failed.emit(str(exc))

    def _emit_progress(self, bytes_done: int) -> None:
        self.progress.emit(bytes_done)
