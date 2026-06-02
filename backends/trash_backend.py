"""M10d.1: Trash / Wastebin backend.

Pure synchronous operations — no Qt imports at module level.
Follows the freedesktop.org Trash specification:
  ~/.local/share/Trash/files/   — actual trashed content
  ~/.local/share/Trash/info/    — *.trashinfo metadata files
  <mount>/.Trash-<uid>/         — per-drive trash (checked additionally)

Qt workers are defined in a try: block at the bottom (same pattern as
file_ops_backend.py) so the module is importable without Qt.
"""
from __future__ import annotations

import configparser
import os
import shutil
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable

from backends.file_ops_backend import ConflictStrategy, FileOpResult, _unique_name


# ── TrashEntry ────────────────────────────────────────────────────────────────

@dataclass
class TrashEntry:
    name:          str       # stem of the .trashinfo file (key in files/)
    trash_path:    Path      # full path inside files/
    original_path: Path      # from .trashinfo Path=
    deletion_date: datetime  # from .trashinfo DeletionDate=
    size:          int       # bytes (recursive for dirs)
    is_dir:        bool
    mime_type:     str = ""


# ── TrashBackend ──────────────────────────────────────────────────────────────

class TrashBackend:
    """Synchronous trash operations.  Safe to call from a QThread worker."""

    def __init__(self, trash_dir: Path | None = None) -> None:
        if trash_dir is None:
            self._trash_dir = Path.home() / ".local" / "share" / "Trash"
        else:
            self._trash_dir = trash_dir
        self._files_dir = self._trash_dir / "files"
        self._info_dir  = self._trash_dir / "info"
        try:
            self._uid = os.getuid()
        except AttributeError:
            self._uid = 0

    # ── Public API ────────────────────────────────────────────────────────────

    def list_trash(self) -> list[TrashEntry]:
        """Return all trash entries, newest first."""
        entries: list[TrashEntry] = []
        for info_dir in self._all_info_dirs():
            files_dir = info_dir.parent / "files"
            for trashinfo in _safe_glob(info_dir, "*.trashinfo"):
                try:
                    entry = self._parse_trashinfo(trashinfo, files_dir)
                    if entry is not None:
                        entries.append(entry)
                except Exception:
                    continue
        entries.sort(key=lambda e: e.deletion_date, reverse=True)
        return entries

    def restore(
        self,
        entries: list[TrashEntry],
        conflict_strategy: str = ConflictStrategy.RENAME,
        line_cb: Callable[[str], None] | None = None,
    ) -> FileOpResult:
        """Move entries back to their original locations."""
        errors: list[str] = []
        for entry in entries:
            try:
                dst = entry.original_path
                if dst.exists():
                    if conflict_strategy == ConflictStrategy.SKIP:
                        if line_cb:
                            line_cb(f"Skipped: {entry.name}")
                        continue
                    elif conflict_strategy == ConflictStrategy.REPLACE:
                        if dst.is_dir():
                            shutil.rmtree(dst)
                        else:
                            dst.unlink()
                    else:  # RENAME
                        dst = _unique_name(dst)
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(entry.trash_path), str(dst))
                trashinfo = entry.trash_path.parent.parent / "info" / (entry.name + ".trashinfo")
                if trashinfo.exists():
                    trashinfo.unlink()
                if line_cb:
                    line_cb(f"Restored: {entry.name}")
            except Exception as exc:
                errors.append(f"{entry.name}: {exc}")
                if line_cb:
                    line_cb(f"Error: {entry.name}: {exc}")
        n_ok = len(entries) - len(errors)
        if errors:
            return FileOpResult(ok=False, errors=errors,
                                message=f"{len(errors)} error(s)")
        return FileOpResult(ok=True, message=f"Restored {n_ok} item(s)")

    def empty_trash(
        self,
        line_cb: Callable[[str], None] | None = None,
    ) -> FileOpResult:
        """Permanently delete all content from files/ and info/."""
        errors: list[str] = []
        for directory in (self._files_dir, self._info_dir):
            if not directory.exists():
                continue
            for item in list(directory.iterdir()):
                try:
                    if item.is_dir():
                        shutil.rmtree(item)
                    else:
                        item.unlink()
                    if line_cb:
                        line_cb(f"Deleted: {item.name}")
                except Exception as exc:
                    errors.append(f"{item.name}: {exc}")
                    if line_cb:
                        line_cb(f"Error: {item.name}: {exc}")
        if errors:
            return FileOpResult(ok=False, errors=errors,
                                message=f"{len(errors)} error(s)")
        return FileOpResult(ok=True, message="Wastebin emptied")

    def delete_permanently(
        self,
        entries: list[TrashEntry],
        line_cb: Callable[[str], None] | None = None,
    ) -> FileOpResult:
        """Permanently delete specific items from the Wastebin."""
        errors: list[str] = []
        for entry in entries:
            try:
                if entry.trash_path.is_dir():
                    shutil.rmtree(entry.trash_path)
                elif entry.trash_path.exists():
                    entry.trash_path.unlink()
                trashinfo = entry.trash_path.parent.parent / "info" / (entry.name + ".trashinfo")
                if trashinfo.exists():
                    trashinfo.unlink()
                if line_cb:
                    line_cb(f"Deleted: {entry.name}")
            except Exception as exc:
                errors.append(f"{entry.name}: {exc}")
                if line_cb:
                    line_cb(f"Error: {entry.name}: {exc}")
        if errors:
            return FileOpResult(ok=False, errors=errors,
                                message=f"{len(errors)} error(s)")
        return FileOpResult(ok=True, message=f"Deleted {len(entries)} item(s) permanently")

    def trash_count(self) -> int:
        """Fast count of items in the main Trash info directory."""
        try:
            if not self._info_dir.exists():
                return 0
            return len(list(self._info_dir.glob("*.trashinfo")))
        except (PermissionError, OSError):
            return 0

    def shred(
        self,
        entries: list[TrashEntry],
        line_cb: Callable[[str], None] | None = None,
    ) -> FileOpResult:
        """Stub — shred not implemented until M10f."""
        raise NotImplementedError("Shred not implemented — M10f")

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _all_info_dirs(self) -> list[Path]:
        """Return all trash info directories to scan (main + per-mount)."""
        dirs: list[Path] = []
        if self._info_dir.exists():
            dirs.append(self._info_dir)
        for mp in self._mount_points():
            td = mp / f".Trash-{self._uid}" / "info"
            if td.exists():
                dirs.append(td)
        return dirs

    def _mount_points(self) -> list[Path]:
        """Read real mount points from /proc/mounts, skipping pseudo-filesystems."""
        _SKIP_FS = frozenset({
            "proc", "sysfs", "devtmpfs", "tmpfs", "cgroup", "cgroup2",
            "pstore", "bpf", "tracefs", "debugfs", "mqueue", "hugetlbfs",
            "devpts", "securityfs", "fusectl", "efivarfs", "autofs",
            "configfs", "squashfs",
        })
        try:
            mounts: list[Path] = []
            with open("/proc/mounts") as f:
                for line in f:
                    parts = line.split()
                    if len(parts) < 3:
                        continue
                    fs_type = parts[2]
                    if fs_type in _SKIP_FS:
                        continue
                    mp = Path(parts[1])
                    if mp != Path("/"):
                        mounts.append(mp)
            return mounts
        except Exception:
            return []

    def _parse_trashinfo(self, trashinfo: Path, files_dir: Path) -> TrashEntry | None:
        cp = configparser.ConfigParser(strict=False)
        cp.read(trashinfo, encoding="utf-8")
        if not cp.has_section("Trash Info"):
            return None
        path_str = cp.get("Trash Info", "Path", fallback=None)
        date_str  = cp.get("Trash Info", "DeletionDate", fallback=None)
        if not path_str:
            return None

        original_path = Path(path_str)
        if date_str:
            try:
                deletion_date = datetime.strptime(date_str, "%Y-%m-%dT%H:%M:%S")
            except ValueError:
                deletion_date = datetime.fromtimestamp(0)
        else:
            deletion_date = datetime.fromtimestamp(0)

        name = trashinfo.stem
        trash_path = files_dir / name
        if not trash_path.exists():
            return None  # orphaned .trashinfo

        is_dir = trash_path.is_dir()
        size   = _entry_size(trash_path)

        return TrashEntry(
            name=name,
            trash_path=trash_path,
            original_path=original_path,
            deletion_date=deletion_date,
            size=size,
            is_dir=is_dir,
        )


def _safe_glob(directory: Path, pattern: str) -> list[Path]:
    try:
        return list(directory.glob(pattern))
    except (PermissionError, OSError):
        return []


def _entry_size(path: Path) -> int:
    try:
        if path.is_dir():
            return sum(f.stat().st_size for f in path.rglob("*") if f.is_file())
        return path.stat().st_size
    except (PermissionError, OSError):
        return 0


# ── QObject worker (Qt optional) ──────────────────────────────────────────────

try:
    from PyQt6.QtCore import QObject, pyqtSignal as _Signal

    class _TrashWorker(QObject):
        """Runs restore / empty / delete_permanently on a QThread."""
        output_line = _Signal(str)
        succeeded   = _Signal(str)
        failed      = _Signal(str)

        def __init__(
            self,
            op: str,
            entries: list,
            *,
            conflict: str = ConflictStrategy.RENAME,
        ) -> None:
            super().__init__()
            self._op       = op
            self._entries  = entries
            self._conflict = conflict

        def run(self) -> None:
            backend = TrashBackend()
            if self._op == "restore":
                result = backend.restore(
                    self._entries, self._conflict, self.output_line.emit)
            elif self._op == "empty":
                result = backend.empty_trash(self.output_line.emit)
            elif self._op == "delete_permanently":
                result = backend.delete_permanently(
                    self._entries, self.output_line.emit)
            else:
                result = FileOpResult(ok=False, message=f"Unknown op: {self._op}")
            if result.ok:
                self.succeeded.emit(result.message)
            else:
                self.failed.emit(result.message or "; ".join(result.errors))

except ImportError:
    pass
