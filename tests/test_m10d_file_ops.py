"""M10d tests: file operations backend — copy, move, delete, rename, create,
clipboard state, conflict resolution, trash fallback, checksums, chmod."""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from backends.file_ops_backend import (
    ConflictStrategy,
    FileOpResult,
    FileOpsBackend,
    FmClipboard,
    _unique_name,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _backend() -> FileOpsBackend:
    return FileOpsBackend()


# ── Copy ──────────────────────────────────────────────────────────────────────

def test_copy_file(tmp_path):
    src_dir = tmp_path / "src"
    dst_dir = tmp_path / "dst"
    src_dir.mkdir(); dst_dir.mkdir()
    f = src_dir / "hello.txt"
    f.write_text("hi")

    result = _backend().copy_files([f], dst_dir)

    assert result.ok
    assert (dst_dir / "hello.txt").exists()
    assert f.exists(), "source must still exist after copy"


def test_copy_directory(tmp_path):
    src_dir = tmp_path / "src_tree"
    dst_dir = tmp_path / "dst"
    dst_dir.mkdir()
    src_dir.mkdir()
    (src_dir / "a.txt").write_text("a")
    (src_dir / "sub").mkdir()
    (src_dir / "sub" / "b.txt").write_text("b")

    result = _backend().copy_files([src_dir], dst_dir)

    assert result.ok
    assert (dst_dir / "src_tree" / "sub" / "b.txt").exists()


def test_copy_collects_lines(tmp_path):
    src = tmp_path / "x.txt"
    src.write_text("x")
    dst = tmp_path / "dst"
    dst.mkdir()
    lines: list[str] = []

    _backend().copy_files([src], dst, line_cb=lines.append)

    assert any("x.txt" in l for l in lines)


# ── Move ──────────────────────────────────────────────────────────────────────

def test_move_file(tmp_path):
    src_dir = tmp_path / "src"
    dst_dir = tmp_path / "dst"
    src_dir.mkdir(); dst_dir.mkdir()
    f = src_dir / "item.txt"
    f.write_text("data")

    result = _backend().move_files([f], dst_dir)

    assert result.ok
    assert (dst_dir / "item.txt").exists()
    assert not f.exists(), "source must be gone after move"


def test_move_directory(tmp_path):
    src = tmp_path / "tree"
    dst_dir = tmp_path / "dst"
    dst_dir.mkdir()
    src.mkdir()
    (src / "file.txt").write_text("hello")

    result = _backend().move_files([src], dst_dir)

    assert result.ok
    assert (dst_dir / "tree" / "file.txt").exists()
    assert not src.exists()


# ── Delete permanently ────────────────────────────────────────────────────────

def test_delete_permanently_file(tmp_path):
    f = tmp_path / "gone.txt"
    f.write_text("bye")

    result = _backend().delete_permanently([f])

    assert result.ok
    assert not f.exists()


def test_delete_permanently_directory(tmp_path):
    d = tmp_path / "tree"
    d.mkdir()
    (d / "child.txt").write_text("x")

    result = _backend().delete_permanently([d])

    assert result.ok
    assert not d.exists()


def test_delete_permanently_logs_lines(tmp_path):
    f = tmp_path / "f.txt"
    f.write_text("")
    lines: list[str] = []

    _backend().delete_permanently([f], line_cb=lines.append)

    assert any("f.txt" in l for l in lines)


# ── Rename ────────────────────────────────────────────────────────────────────

def test_rename_path(tmp_path):
    f = tmp_path / "old.txt"
    f.write_text("x")

    result = _backend().rename_path(f, "new.txt")

    assert result.ok
    assert (tmp_path / "new.txt").exists()
    assert not f.exists()


def test_rename_empty_name_is_noop(tmp_path):
    f = tmp_path / "file.txt"
    f.write_text("")

    result = _backend().rename_path(f, "")

    assert not result.ok


def test_rename_same_name_is_noop(tmp_path):
    f = tmp_path / "file.txt"
    f.write_text("")

    result = _backend().rename_path(f, "file.txt")

    assert not result.ok


def test_rename_collision_returns_error(tmp_path):
    f = tmp_path / "a.txt"
    f.write_text("")
    (tmp_path / "b.txt").write_text("")

    result = _backend().rename_path(f, "b.txt")

    assert not result.ok
    assert "a.txt" in str(f)  # original unchanged


# ── Create ────────────────────────────────────────────────────────────────────

def test_create_folder(tmp_path):
    result = _backend().create_folder(tmp_path, "myfolder")

    assert result.ok
    assert (tmp_path / "myfolder").is_dir()


def test_create_file(tmp_path):
    result = _backend().create_file(tmp_path, "blank.txt")

    assert result.ok
    assert (tmp_path / "blank.txt").is_file()


def test_create_folder_duplicate_returns_error(tmp_path):
    (tmp_path / "dup").mkdir()

    result = _backend().create_folder(tmp_path, "dup")

    assert not result.ok


def test_create_file_duplicate_returns_error(tmp_path):
    (tmp_path / "dup.txt").write_text("")

    result = _backend().create_file(tmp_path, "dup.txt")

    assert not result.ok


# ── Conflict resolution ───────────────────────────────────────────────────────

def test_conflict_skip(tmp_path):
    src = tmp_path / "src" / "f.txt"
    src.parent.mkdir()
    src.write_text("new")
    dst_dir = tmp_path / "dst"
    dst_dir.mkdir()
    existing = dst_dir / "f.txt"
    existing.write_text("original")

    _backend().copy_files([src], dst_dir, conflict=ConflictStrategy.SKIP)

    assert existing.read_text() == "original", "skip must leave existing file unchanged"


def test_conflict_replace(tmp_path):
    src = tmp_path / "src" / "f.txt"
    src.parent.mkdir()
    src.write_text("new content")
    dst_dir = tmp_path / "dst"
    dst_dir.mkdir()
    (dst_dir / "f.txt").write_text("old content")

    _backend().copy_files([src], dst_dir, conflict=ConflictStrategy.REPLACE)

    assert (dst_dir / "f.txt").read_text() == "new content"


def test_conflict_rename_auto(tmp_path):
    src = tmp_path / "src" / "f.txt"
    src.parent.mkdir()
    src.write_text("new")
    dst_dir = tmp_path / "dst"
    dst_dir.mkdir()
    (dst_dir / "f.txt").write_text("original")

    _backend().copy_files([src], dst_dir, conflict=ConflictStrategy.RENAME)

    assert (dst_dir / "f.txt").read_text() == "original", "original intact"
    assert (dst_dir / "f (copy).txt").exists(), "renamed copy created"


# ── unique_name helper ────────────────────────────────────────────────────────

def test_unique_name_no_collision(tmp_path):
    p = tmp_path / "new.txt"
    assert _unique_name(p) == p


def test_unique_name_copy_suffix(tmp_path):
    f = tmp_path / "f.txt"
    f.write_text("")

    result = _unique_name(f)
    assert result == tmp_path / "f (copy).txt"


def test_unique_name_numbered_suffix(tmp_path):
    (tmp_path / "f.txt").write_text("")
    (tmp_path / "f (copy).txt").write_text("")

    result = _unique_name(tmp_path / "f.txt")
    assert result == tmp_path / "f (2).txt"


def test_unique_name_chain(tmp_path):
    for name in ("f.txt", "f (copy).txt", "f (2).txt"):
        (tmp_path / name).write_text("")

    result = _unique_name(tmp_path / "f.txt")
    assert result == tmp_path / "f (3).txt"


# ── find_conflicts ────────────────────────────────────────────────────────────

def test_find_conflicts_none(tmp_path):
    srcs = [tmp_path / "a.txt", tmp_path / "b.txt"]
    dst = tmp_path / "dst"
    dst.mkdir()

    conflicts = _backend().find_conflicts(srcs, dst)
    assert conflicts == []


def test_find_conflicts_detects_collision(tmp_path):
    srcs = [tmp_path / "a.txt"]
    dst = tmp_path / "dst"
    dst.mkdir()
    (dst / "a.txt").write_text("existing")

    conflicts = _backend().find_conflicts(srcs, dst)
    assert "a.txt" in conflicts


# ── Trash fallback ────────────────────────────────────────────────────────────

def test_trash_fallback_when_send2trash_missing(tmp_path, monkeypatch):
    """When send2trash is not importable, falls back to permanent delete."""
    f = tmp_path / "todelete.txt"
    f.write_text("x")

    # Hide send2trash from the import system
    import importlib
    original = sys.modules.get("send2trash")
    sys.modules["send2trash"] = None  # makes import raise ImportError

    try:
        lines: list[str] = []
        result = _backend().delete_to_trash([f], line_cb=lines.append)
    finally:
        if original is None:
            sys.modules.pop("send2trash", None)
        else:
            sys.modules["send2trash"] = original

    assert result.ok
    assert not f.exists(), "file deleted permanently as fallback"
    assert any("send2trash" in l for l in lines), "fallback logged"


def test_trash_calls_send2trash(tmp_path, monkeypatch):
    """When send2trash IS available, it is called (not permanent delete)."""
    f = tmp_path / "trashed.txt"
    f.write_text("x")

    called_with: list[str] = []
    mock_s2t = MagicMock()
    mock_s2t.send2trash = lambda p: (called_with.append(p), f.unlink())[0]

    import sys as _sys
    original = _sys.modules.get("send2trash")
    _sys.modules["send2trash"] = mock_s2t
    try:
        result = _backend().delete_to_trash([f])
    finally:
        if original is None:
            _sys.modules.pop("send2trash", None)
        else:
            _sys.modules["send2trash"] = original

    assert result.ok
    assert called_with, "send2trash.send2trash must have been called"


# ── Clipboard ─────────────────────────────────────────────────────────────────

def test_clipboard_copy_state():
    cb = FmClipboard(operation="copy", paths=[Path("/a"), Path("/b")])
    assert cb.operation == "copy"
    assert len(cb.paths) == 2
    assert not cb.is_empty()


def test_clipboard_cut_state():
    cb = FmClipboard(operation="cut", paths=[Path("/x")])
    assert cb.operation == "cut"
    assert not cb.is_empty()


def test_clipboard_empty():
    cb = FmClipboard(operation="copy")
    assert cb.is_empty()


# ── Checksums ─────────────────────────────────────────────────────────────────

def test_compute_checksums(tmp_path):
    content = b"hello world\n"
    f = tmp_path / "test.txt"
    f.write_bytes(content)

    sums = _backend().compute_checksums(f)

    assert sums["MD5"]    == hashlib.md5(content).hexdigest()
    assert sums["SHA-1"]  == hashlib.sha1(content).hexdigest()
    assert sums["SHA-256"] == hashlib.sha256(content).hexdigest()


def test_compute_checksums_empty_file(tmp_path):
    f = tmp_path / "empty.bin"
    f.write_bytes(b"")

    sums = _backend().compute_checksums(f)

    assert sums["MD5"] == hashlib.md5(b"").hexdigest()


# ── chmod ─────────────────────────────────────────────────────────────────────

def test_chmod_pkexec_call(tmp_path):
    f = tmp_path / "file.txt"
    f.write_text("")
    run_calls: list = []

    def fake_run(cmd, **_kwargs):
        run_calls.append(cmd)
        r = MagicMock()
        r.returncode = 0
        r.stderr = ""
        return r

    with patch("subprocess.run", fake_run):
        result = _backend().set_chmod(f, 0o644)

    assert result.ok
    assert run_calls, "subprocess.run must be called"
    cmd = run_calls[0]
    assert cmd[0] == "pkexec"
    assert cmd[1] == "chmod"
    assert cmd[2] == "644"
    assert cmd[3] == str(f)


def test_chmod_returns_error_on_nonzero(tmp_path):
    f = tmp_path / "f.txt"
    f.write_text("")

    def fake_run(cmd, **_kwargs):
        r = MagicMock()
        r.returncode = 1
        r.stderr = "permission denied"
        return r

    with patch("subprocess.run", fake_run):
        result = _backend().set_chmod(f, 0o600)

    assert not result.ok
    assert "permission denied" in result.message


# ── stat info ─────────────────────────────────────────────────────────────────

def test_get_stat_info(tmp_path):
    f = tmp_path / "stat_test.txt"
    f.write_text("x")

    info = _backend().get_stat_info(f)

    assert "owner" in info
    assert "group" in info
    assert "mode" in info
    assert "octal" in info
    assert info["octal"].startswith("0o")
    assert isinstance(info["inode"], int)
    assert isinstance(info["links"], int)


# ── QObject worker (requires QApplication) ───────────────────────────────────

def _app():
    pytest.importorskip("PyQt6")
    from PyQt6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def test_worker_copy_emits_lines(tmp_path):
    app = _app()
    from PyQt6.QtCore import QThread
    from backends.file_ops_backend import _FileOpsWorker

    src_dir = tmp_path / "src"
    dst_dir = tmp_path / "dst"
    src_dir.mkdir(); dst_dir.mkdir()
    (src_dir / "file.txt").write_text("data")

    lines: list[str] = []
    succeeded: list[str] = []
    failed: list[str] = []

    worker = _FileOpsWorker(
        "copy", src_paths=[src_dir / "file.txt"], dst_dir=dst_dir)
    worker.output_line.connect(lines.append)
    worker.succeeded.connect(succeeded.append)
    worker.failed.connect(failed.append)
    worker.run()   # call synchronously — no thread needed in test

    assert not failed, f"worker failed: {failed}"
    assert succeeded
    assert any("file.txt" in l for l in lines)
    assert (dst_dir / "file.txt").exists()


def test_worker_delete_emits_lines(tmp_path):
    app = _app()
    from backends.file_ops_backend import _FileOpsWorker

    f = tmp_path / "bye.txt"
    f.write_text("")
    lines: list[str] = []
    succeeded: list[str] = []

    worker = _FileOpsWorker("delete", src_paths=[f])
    worker.output_line.connect(lines.append)
    worker.succeeded.connect(succeeded.append)
    worker.run()

    assert succeeded
    assert not f.exists()
    assert any("bye.txt" in l for l in lines)


def test_worker_unknown_op_emits_failed():
    app = _app()
    from backends.file_ops_backend import _FileOpsWorker

    failed: list[str] = []
    worker = _FileOpsWorker("__unknown__", src_paths=[])
    worker.failed.connect(failed.append)
    worker.run()

    assert failed
