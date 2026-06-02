"""M10d: File operations backend.

Pure synchronous operations called from QThread workers.  No Qt imports
at module level so this can be unit-tested without a QApplication.

Public surface:
    FmClipboard           — clipboard state (cut | copy + paths)
    ConflictStrategy      — SKIP / REPLACE / RENAME constants
    FileOpResult          — uniform return from every operation
    FileOpsBackend        — synchronous operations class
    _FileOpsWorker        — QObject worker for copy/move/trash/delete
    _ChecksumWorker       — QObject worker for checksum computation
    _ChmodWorker          — QObject worker for pkexec chmod
    _OpenWithLoader       — QObject worker for xdg-mime app list
"""
from __future__ import annotations

import grp
import hashlib
import pwd
import shutil
import stat
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable


# ── Clipboard ─────────────────────────────────────────────────────────────────

@dataclass
class FmClipboard:
    """Lightweight FM clipboard — set on cut/copy, consumed on paste."""
    operation: str        # "copy" | "cut"
    paths: list[Path] = field(default_factory=list)

    def is_empty(self) -> bool:
        return not self.paths


# ── Conflict strategy ─────────────────────────────────────────────────────────

class ConflictStrategy:
    SKIP    = "skip"
    REPLACE = "replace"
    RENAME  = "rename"   # appends " (copy)", "(2)", "(3)" …


# ── Result ─────────────────────────────────────────────────────────────────────

@dataclass
class FileOpResult:
    ok: bool
    message: str = ""
    errors: list[str] = field(default_factory=list)


# ── Helpers ────────────────────────────────────────────────────────────────────

def _unique_name(path: Path) -> Path:
    """Return a non-colliding path by appending ' (copy)', then '(2)', '(3)'…"""
    if not path.exists():
        return path
    stem, suffix, parent = path.stem, path.suffix, path.parent
    candidate = parent / f"{stem} (copy){suffix}"
    if not candidate.exists():
        return candidate
    n = 2
    while True:
        candidate = parent / f"{stem} ({n}){suffix}"
        if not candidate.exists():
            return candidate
        n += 1


_ADMIN_FM_CHAIN = ["dolphin", "nautilus", "nemo", "thunar"]


# ── Backend ────────────────────────────────────────────────────────────────────

class FileOpsBackend:
    """Synchronous file operations.  All methods are safe to call from a worker
    thread.  No Qt types used; return FileOpResult for every mutable op."""

    # ── Copy / Move ───────────────────────────────────────────────────────────

    def copy_files(
        self,
        src_paths: list[Path],
        dst_dir: Path,
        *,
        conflict: str = ConflictStrategy.RENAME,
        line_cb: Callable[[str], None] | None = None,
    ) -> FileOpResult:
        errors: list[str] = []
        for src in src_paths:
            dst = dst_dir / src.name
            if dst.exists() and src.resolve() != dst.resolve():
                if conflict == ConflictStrategy.SKIP:
                    if line_cb:
                        line_cb(f"Skipped: {src.name}")
                    continue
                elif conflict == ConflictStrategy.REPLACE:
                    try:
                        if dst.is_dir():
                            shutil.rmtree(dst)
                        else:
                            dst.unlink()
                    except Exception as exc:
                        errors.append(f"{src.name}: {exc}")
                        if line_cb:
                            line_cb(f"Error: {src.name}: {exc}")
                        continue
                else:  # RENAME
                    dst = _unique_name(dst)
            try:
                if src.is_dir():
                    shutil.copytree(src, dst)
                else:
                    shutil.copy2(src, dst)
                if line_cb:
                    line_cb(f"Copied: {src.name}")
            except Exception as exc:
                errors.append(f"{src.name}: {exc}")
                if line_cb:
                    line_cb(f"Error: {src.name}: {exc}")
        if errors:
            return FileOpResult(ok=False, errors=errors,
                                message=f"{len(errors)} error(s)")
        return FileOpResult(ok=True,
                            message=f"Copied {len(src_paths)} item(s)")

    def move_files(
        self,
        src_paths: list[Path],
        dst_dir: Path,
        *,
        conflict: str = ConflictStrategy.RENAME,
        line_cb: Callable[[str], None] | None = None,
    ) -> FileOpResult:
        errors: list[str] = []
        for src in src_paths:
            dst = dst_dir / src.name
            if dst.exists() and src.resolve() != dst.resolve():
                if conflict == ConflictStrategy.SKIP:
                    if line_cb:
                        line_cb(f"Skipped: {src.name}")
                    continue
                elif conflict == ConflictStrategy.REPLACE:
                    try:
                        if dst.is_dir():
                            shutil.rmtree(dst)
                        else:
                            dst.unlink()
                    except Exception as exc:
                        errors.append(f"{src.name}: {exc}")
                        if line_cb:
                            line_cb(f"Error: {src.name}: {exc}")
                        continue
                else:  # RENAME
                    dst = _unique_name(dst)
            try:
                shutil.move(str(src), str(dst))
                if line_cb:
                    line_cb(f"Moved: {src.name}")
            except Exception as exc:
                errors.append(f"{src.name}: {exc}")
                if line_cb:
                    line_cb(f"Error: {src.name}: {exc}")
        if errors:
            return FileOpResult(ok=False, errors=errors,
                                message=f"{len(errors)} error(s)")
        return FileOpResult(ok=True,
                            message=f"Moved {len(src_paths)} item(s)")

    # ── Delete ────────────────────────────────────────────────────────────────

    def delete_to_trash(
        self,
        paths: list[Path],
        *,
        line_cb: Callable[[str], None] | None = None,
    ) -> FileOpResult:
        try:
            import send2trash as _s2t
            trash_fn: Callable[[str], None] = _s2t.send2trash
        except ImportError:
            trash_fn = None

        if trash_fn is None:
            if line_cb:
                line_cb("send2trash not available — deleting permanently")
            return self.delete_permanently(paths, line_cb=line_cb)

        errors: list[str] = []
        for path in paths:
            try:
                trash_fn(str(path))
                if line_cb:
                    line_cb(f"Trashed: {path.name}")
            except Exception as exc:
                errors.append(f"{path.name}: {exc}")
                if line_cb:
                    line_cb(f"Error: {path.name}: {exc}")
        if errors:
            return FileOpResult(ok=False, errors=errors)
        return FileOpResult(ok=True,
                            message=f"Moved {len(paths)} item(s) to trash")

    def delete_permanently(
        self,
        paths: list[Path],
        *,
        line_cb: Callable[[str], None] | None = None,
    ) -> FileOpResult:
        errors: list[str] = []
        for path in paths:
            try:
                if path.is_dir():
                    shutil.rmtree(path)
                else:
                    path.unlink()
                if line_cb:
                    line_cb(f"Deleted: {path.name}")
            except Exception as exc:
                errors.append(f"{path.name}: {exc}")
                if line_cb:
                    line_cb(f"Error: {path.name}: {exc}")
        if errors:
            return FileOpResult(ok=False, errors=errors)
        return FileOpResult(ok=True,
                            message=f"Deleted {len(paths)} item(s)")

    # ── Rename / Create ───────────────────────────────────────────────────────

    def rename_path(self, src: Path, new_name: str) -> FileOpResult:
        new_name = new_name.strip()
        if not new_name or new_name == src.name:
            return FileOpResult(ok=False, message="No change")
        dst = src.parent / new_name
        if dst.exists():
            return FileOpResult(ok=False,
                                message=f'"{new_name}" already exists')
        try:
            src.rename(dst)
            return FileOpResult(ok=True, message=f"Renamed to {new_name}")
        except Exception as exc:
            return FileOpResult(ok=False, message=str(exc))

    def create_folder(self, parent: Path, name: str) -> FileOpResult:
        name = name.strip()
        if not name:
            return FileOpResult(ok=False, message="Name cannot be empty")
        try:
            (parent / name).mkdir(exist_ok=False)
            return FileOpResult(ok=True)
        except FileExistsError:
            return FileOpResult(ok=False, message=f'"{name}" already exists')
        except Exception as exc:
            return FileOpResult(ok=False, message=str(exc))

    def create_file(self, parent: Path, name: str) -> FileOpResult:
        name = name.strip()
        if not name:
            return FileOpResult(ok=False, message="Name cannot be empty")
        target = parent / name
        if target.exists():
            return FileOpResult(ok=False, message=f'"{name}" already exists')
        try:
            target.touch()
            return FileOpResult(ok=True)
        except Exception as exc:
            return FileOpResult(ok=False, message=str(exc))

    # ── Conflict pre-flight ───────────────────────────────────────────────────

    def find_conflicts(
        self, src_paths: list[Path], dst_dir: Path
    ) -> list[str]:
        """Return names of src items that collide with existing dst items."""
        return [
            s.name for s in src_paths
            if (dst_dir / s.name).exists()
            and s.resolve() != (dst_dir / s.name).resolve()
        ]

    # ── Permissions ───────────────────────────────────────────────────────────

    def get_stat_info(self, path: Path) -> dict:
        st = path.stat()
        try:
            owner = pwd.getpwuid(st.st_uid).pw_name
        except (KeyError, ImportError):
            owner = str(st.st_uid)
        try:
            group = grp.getgrgid(st.st_gid).gr_name
        except (KeyError, ImportError):
            group = str(st.st_gid)
        return {
            "mode":       stat.filemode(st.st_mode),
            "octal":      oct(stat.S_IMODE(st.st_mode)),
            "owner":      owner,
            "group":      group,
            "inode":      st.st_ino,
            "links":      st.st_nlink,
            "block_size": getattr(st, "st_blksize", "—"),
            "blocks":     getattr(st, "st_blocks", "—"),
            "uid":        st.st_uid,
            "gid":        st.st_gid,
            "mode_int":   stat.S_IMODE(st.st_mode),
        }

    def set_chmod(self, path: Path, octal_mode: int) -> FileOpResult:
        """Set file permissions via pkexec chmod."""
        mode_str = oct(octal_mode)[2:]
        try:
            result = subprocess.run(
                ["pkexec", "chmod", mode_str, str(path)],
                capture_output=True, text=True, timeout=30,
            )
            if result.returncode == 0:
                return FileOpResult(ok=True)
            return FileOpResult(ok=False, message=result.stderr.strip())
        except Exception as exc:
            return FileOpResult(ok=False, message=str(exc))

    # ── Checksums ─────────────────────────────────────────────────────────────

    def compute_checksums(self, path: Path) -> dict[str, str]:
        md5    = hashlib.md5()
        sha1   = hashlib.sha1()
        sha256 = hashlib.sha256()
        with open(path, "rb") as fh:
            for chunk in iter(lambda: fh.read(65536), b""):
                md5.update(chunk)
                sha1.update(chunk)
                sha256.update(chunk)
        return {
            "MD5":    md5.hexdigest(),
            "SHA-1":  sha1.hexdigest(),
            "SHA-256": sha256.hexdigest(),
        }

    # ── Open With ─────────────────────────────────────────────────────────────

    def get_open_with_apps(self, mime: str) -> list[str]:
        """Return list of .desktop app IDs for this MIME type."""
        apps: list[str] = []
        try:
            r = subprocess.run(
                ["xdg-mime", "query", "default", mime],
                capture_output=True, text=True, timeout=5,
            )
            default = r.stdout.strip()
            if default:
                apps.append(default)
        except Exception:
            pass
        try:
            r2 = subprocess.run(
                ["gio", "mime", mime],
                capture_output=True, text=True, timeout=5,
            )
            for line in r2.stdout.splitlines():
                stripped = line.strip()
                if stripped.endswith(".desktop") and stripped not in apps:
                    apps.append(stripped)
        except Exception:
            pass
        return apps

    def set_default_app(self, mime: str, app_desktop: str) -> None:
        try:
            subprocess.run(
                ["xdg-mime", "default", app_desktop, mime],
                capture_output=True, text=True, timeout=5,
            )
        except Exception:
            pass

    # ── Open as Administrator ─────────────────────────────────────────────────

    def find_admin_file_manager(self) -> str | None:
        """Return first found FM from the detection chain, or None."""
        for fm in _ADMIN_FM_CHAIN:
            if shutil.which(fm):
                return fm
        return None

    def open_as_admin(self, path: Path) -> FileOpResult:
        fm = self.find_admin_file_manager()
        if fm is None:
            return FileOpResult(
                ok=False,
                message="No supported file manager found "
                        f"(tried: {', '.join(_ADMIN_FM_CHAIN)})",
            )
        try:
            subprocess.Popen(["pkexec", fm, str(path)])
            return FileOpResult(ok=True)
        except Exception as exc:
            return FileOpResult(ok=False, message=str(exc))


# ── QObject workers ───────────────────────────────────────────────────────────
# Importing Qt here; isolated so the module is still importable without Qt
# for pure unit tests (skip these classes in those tests).

try:
    from PyQt6.QtCore import QObject, pyqtSignal as _Signal

    class _FileOpsWorker(QObject):
        """Runs copy / move / trash / delete on a QThread."""
        output_line = _Signal(str)
        succeeded   = _Signal(str)
        failed      = _Signal(str)

        def __init__(
            self,
            op: str,
            *,
            src_paths: list[Path] | None = None,
            dst_dir: Path | None = None,
            conflict: str = ConflictStrategy.RENAME,
        ) -> None:
            super().__init__()
            self._op        = op
            self._src_paths = src_paths or []
            self._dst_dir   = dst_dir
            self._conflict  = conflict

        def run(self) -> None:
            backend = FileOpsBackend()
            if self._op == "copy":
                result = backend.copy_files(
                    self._src_paths, self._dst_dir,
                    conflict=self._conflict,
                    line_cb=self.output_line.emit,
                )
            elif self._op == "move":
                result = backend.move_files(
                    self._src_paths, self._dst_dir,
                    conflict=self._conflict,
                    line_cb=self.output_line.emit,
                )
            elif self._op == "trash":
                result = backend.delete_to_trash(
                    self._src_paths,
                    line_cb=self.output_line.emit,
                )
            elif self._op == "delete":
                result = backend.delete_permanently(
                    self._src_paths,
                    line_cb=self.output_line.emit,
                )
            else:
                result = FileOpResult(ok=False,
                                      message=f"Unknown op: {self._op}")

            if result.ok:
                self.succeeded.emit(result.message)
            else:
                self.failed.emit(result.message or "; ".join(result.errors))

    class _ChecksumWorker(QObject):
        checksums_ready = _Signal(dict)
        failed          = _Signal(str)

        def __init__(self, path: Path) -> None:
            super().__init__()
            self._path = path

        def run(self) -> None:
            try:
                sums = FileOpsBackend().compute_checksums(self._path)
                self.checksums_ready.emit(sums)
            except Exception as exc:
                self.failed.emit(str(exc))

    class _ChmodWorker(QObject):
        done   = _Signal()
        failed = _Signal(str)

        def __init__(self, path: Path, octal_mode: int) -> None:
            super().__init__()
            self._path = path
            self._mode = octal_mode

        def run(self) -> None:
            result = FileOpsBackend().set_chmod(self._path, self._mode)
            if result.ok:
                self.done.emit()
            else:
                self.failed.emit(result.message)

    class _OpenWithLoader(QObject):
        apps_ready = _Signal(list)

        def __init__(self, mime: str) -> None:
            super().__init__()
            self._mime = mime

        def run(self) -> None:
            apps = FileOpsBackend().get_open_with_apps(self._mime)
            self.apps_ready.emit(apps)

except ImportError:
    pass  # Qt not available — workers are not defined (tests use backend directly)
