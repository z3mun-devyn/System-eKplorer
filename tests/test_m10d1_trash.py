"""M10d.1 tests: TrashBackend + view wiring."""
from __future__ import annotations

import inspect
import textwrap
from datetime import datetime
from pathlib import Path

import pytest

from backends.trash_backend import TrashBackend


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_trash(tmp_path: Path) -> Path:
    """Return a ready-to-use trash root with files/ and info/ subdirs."""
    (tmp_path / "files").mkdir()
    (tmp_path / "info").mkdir()
    return tmp_path


def _add_entry(trash_root: Path, name: str, content: str = "data",
               original: str | None = None,
               deletion_date: str = "2024-01-15T10:30:00") -> Path:
    file_path = trash_root / "files" / name
    file_path.write_text(content)
    orig = original or f"/home/user/Documents/{name}"
    info = trash_root / "info" / f"{name}.trashinfo"
    info.write_text(
        f"[Trash Info]\nPath={orig}\nDeletionDate={deletion_date}\n")
    return file_path


# ── Backend tests ─────────────────────────────────────────────────────────────

def test_list_trash_parses_trashinfo(tmp_path):
    root = _make_trash(tmp_path)
    _add_entry(root, "hello.txt", "hi", "/home/user/hello.txt",
               "2024-03-10T08:00:00")

    backend = TrashBackend(trash_dir=root)
    entries = backend.list_trash()

    assert len(entries) == 1
    e = entries[0]
    assert e.name == "hello.txt"
    assert e.original_path == Path("/home/user/hello.txt")
    assert e.deletion_date == datetime(2024, 3, 10, 8, 0, 0)
    assert e.size > 0
    assert not e.is_dir


def test_restore_moves_file_and_removes_trashinfo(tmp_path):
    root = _make_trash(tmp_path)
    dest_dir = tmp_path / "restored"
    dest_dir.mkdir()
    original_path = dest_dir / "note.txt"

    _add_entry(root, "note.txt", "restored content",
               str(original_path), "2024-04-01T12:00:00")

    backend = TrashBackend(trash_dir=root)
    entries = backend.list_trash()
    assert len(entries) == 1

    result = backend.restore(entries)
    assert result.ok
    assert original_path.exists()
    assert original_path.read_text() == "restored content"
    # .trashinfo must be removed
    assert not (root / "info" / "note.txt.trashinfo").exists()
    # file must be gone from trash
    assert not (root / "files" / "note.txt").exists()


def test_empty_trash_clears_both_dirs(tmp_path):
    root = _make_trash(tmp_path)
    _add_entry(root, "a.txt")
    _add_entry(root, "b.txt")

    backend = TrashBackend(trash_dir=root)
    assert len(backend.list_trash()) == 2

    result = backend.empty_trash()
    assert result.ok
    assert list((root / "files").iterdir()) == []
    assert list((root / "info").iterdir()) == []


def test_delete_permanently_removes_specific_items_only(tmp_path):
    root = _make_trash(tmp_path)
    _add_entry(root, "keep.txt")
    _add_entry(root, "gone.txt")

    backend = TrashBackend(trash_dir=root)
    entries = backend.list_trash()
    # pick only "gone.txt"
    to_delete = [e for e in entries if e.name == "gone.txt"]
    assert len(to_delete) == 1

    result = backend.delete_permanently(to_delete)
    assert result.ok
    # keep.txt still in trash
    remaining = backend.list_trash()
    assert len(remaining) == 1
    assert remaining[0].name == "keep.txt"
    # gone.txt fully removed
    assert not (root / "files" / "gone.txt").exists()
    assert not (root / "info" / "gone.txt.trashinfo").exists()


def test_shred_raises_not_implemented(tmp_path):
    root = _make_trash(tmp_path)
    _add_entry(root, "shred_me.txt")
    backend = TrashBackend(trash_dir=root)
    entries = backend.list_trash()
    with pytest.raises(NotImplementedError):
        backend.shred(entries)


def test_trash_count_returns_correct_count(tmp_path):
    root = _make_trash(tmp_path)
    backend = TrashBackend(trash_dir=root)
    assert backend.trash_count() == 0

    _add_entry(root, "one.txt")
    assert backend.trash_count() == 1

    _add_entry(root, "two.txt")
    assert backend.trash_count() == 2


# ── View wiring tests (source inspection) ────────────────────────────────────

def test_context_menu_has_trash_not_delete():
    from views.file_view import FileView
    src = inspect.getsource(FileView._on_context_menu)
    import strings
    assert strings.FM_CTX_TRASH in src or "FM_CTX_TRASH" in src
    assert "FM_CTX_DELETE" not in src


def test_shift_delete_shortcut_wired():
    from views.file_manager_view import FileManagerView
    src = inspect.getsource(FileManagerView.__init__)
    assert "Shift+Delete" in src
    assert '"delete"' in src or "'delete'" in src


def test_wastebin_icon_switches_on_trash(tmp_path, monkeypatch):
    root = _make_trash(tmp_path)

    from backends.trash_backend import TrashBackend as TB
    # empty trash → user-trash icon path
    monkeypatch.setattr(TB, "trash_count", lambda self: 0)

    from views.navigation_sidebar import NavigationSidebar
    import sys
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication(sys.argv)

    sidebar = NavigationSidebar(fixed_width=None)
    # Should not raise regardless of icon theme availability
    sidebar.update_wastebin_icon()

    # non-empty trash → user-trash-full icon path
    monkeypatch.setattr(TB, "trash_count", lambda self: 3)
    sidebar.update_wastebin_icon()  # also must not raise


# ── _TrashListWorker ─────────────────────────────────────────────────────────

# ── _entry_size non-recursive ────────────────────────────────────────────────

def test_entry_size_returns_minus_one_for_directory(tmp_path):
    """Trashed directories must return -1 (never recursive-walk)."""
    from backends.trash_backend import _entry_size
    d = tmp_path / "big_dir"
    d.mkdir()
    (d / "file.txt").write_text("lots of data" * 1000)
    assert _entry_size(d) == -1


def test_entry_size_returns_stat_size_for_file(tmp_path):
    """Trashed files return the exact stat().st_size byte count."""
    from backends.trash_backend import _entry_size
    f = tmp_path / "data.bin"
    f.write_bytes(b"x" * 512)
    assert _entry_size(f) == 512


def test_list_trash_directory_size_is_minus_one(tmp_path, monkeypatch):
    """list_trash() stores -1 for directory entries, not a recursive byte count."""
    root = _make_trash(tmp_path)
    trashed_dir = root / "files" / "mydir"
    trashed_dir.mkdir()
    (trashed_dir / "big.bin").write_bytes(b"0" * 8192)

    info = root / "info" / "mydir.trashinfo"
    info.write_text("[Trash Info]\nPath=/home/user/mydir\nDeletionDate=2024-01-01T00:00:00\n")

    # Suppress per-mount scan so the snap PermissionError doesn't interfere
    monkeypatch.setattr(TrashBackend, "_mount_points", lambda self: [])
    backend = TrashBackend(trash_dir=root)
    entries = backend.list_trash()

    assert len(entries) == 1
    assert entries[0].is_dir is True
    assert entries[0].size == -1


# ── _mount_points filtering ───────────────────────────────────────────────────

def test_mount_points_excludes_snapd_ns(monkeypatch):
    """/run/snapd/ns/... paths are excluded from _mount_points()."""
    fake_mounts = (
        "sysfs /sys sysfs rw 0 0\n"
        "tmpfs /run tmpfs rw 0 0\n"
        "ext4 /home ext4 rw 0 0\n"                        # should be kept
        "fuse /run/snapd/ns/foo.mnt fuse rw 0 0\n"        # /run prefix → skip
        "ext4 /snap/core20/1234 ext4 ro 0 0\n"            # /snap prefix → skip
        "zfs /tank zfs rw 0 0\n"                          # real pool → keep
    )
    import io
    monkeypatch.setattr("builtins.open",
                        lambda path, *a, **kw: io.StringIO(fake_mounts)
                        if "mounts" in str(path) else open(path, *a, **kw))
    backend = TrashBackend()
    mps = [str(p) for p in backend._mount_points()]
    assert "/home" in mps
    assert "/tank" in mps
    assert not any("/snap" in m or "/run" in m for m in mps)


def test_mount_points_excludes_run_prefix(monkeypatch):
    """Any mount under /run is excluded."""
    fake_mounts = "ext4 /run/user/1000 ext4 rw 0 0\n"
    import io
    monkeypatch.setattr("builtins.open",
                        lambda path, *a, **kw: io.StringIO(fake_mounts)
                        if "mounts" in str(path) else open(path, *a, **kw))
    backend = TrashBackend()
    assert backend._mount_points() == []


# ── list_trash per-dir isolation ──────────────────────────────────────────────

def test_list_trash_continues_after_permission_error(tmp_path, monkeypatch):
    """A PermissionError on one per-mount info dir is skipped; main trash is read."""
    root = _make_trash(tmp_path)
    _add_entry(root, "file.txt", "hi", "/home/user/file.txt",
               "2024-06-01T10:00:00")

    bad_dir = tmp_path / "bad_info"
    bad_dir.mkdir()

    def fake_all_info_dirs(self):
        return [bad_dir, root / "info"]

    monkeypatch.setattr(TrashBackend, "_all_info_dirs", fake_all_info_dirs)

    # Make bad_dir raise on glob
    original_glob = __import__("backends.trash_backend", fromlist=["_safe_glob"])
    import backends.trash_backend as tb_mod
    original_safe_glob = tb_mod._safe_glob

    def patched_safe_glob(directory, pattern):
        if directory == bad_dir:
            raise PermissionError("denied")
        return original_safe_glob(directory, pattern)

    monkeypatch.setattr(tb_mod, "_safe_glob", patched_safe_glob)

    backend = TrashBackend(trash_dir=root)
    entries = backend.list_trash()

    assert len(entries) == 1
    assert entries[0].name == "file.txt"


def test_trash_list_worker_exists():
    """_TrashListWorker is importable from backends.trash_backend."""
    from backends.trash_backend import _TrashListWorker
    assert _TrashListWorker is not None


def test_trash_list_worker_emits_ready(monkeypatch):
    """_TrashListWorker.run() calls list_trash() and emits ready with the result."""
    pytest.importorskip("PyQt6")
    from PyQt6.QtWidgets import QApplication
    import sys
    _app = QApplication.instance() or QApplication(sys.argv)
    from backends.trash_backend import _TrashListWorker, TrashBackend

    fake_entries = ["entry_a", "entry_b"]
    monkeypatch.setattr(TrashBackend, "list_trash", lambda self: fake_entries)

    results: list = []
    worker = _TrashListWorker()
    worker.ready.connect(results.append)
    worker.run()

    assert results == [fake_entries]


# ── _start_trash_op drains prior thread ──────────────────────────────────────

def _make_fm(tmp_path, monkeypatch):
    """Create a FileManagerView with DB patched to use tmp_path."""
    pytest.importorskip("PyQt6")
    from PyQt6.QtWidgets import QApplication
    import sys
    _app = QApplication.instance() or QApplication(sys.argv)
    import functools
    from models.database import open_db

    monkeypatch.setattr("backends.settings_backend.open_db",
                        lambda _path=None: open_db(tmp_path / "data.db"))
    monkeypatch.setattr("backends.recent_backend.open_db",
                        functools.partial(open_db, tmp_path / "data.db"))
    monkeypatch.setattr("backends.file_tags_backend.open_db",
                        lambda _path=None: open_db(tmp_path / "data.db"))
    from views.file_manager_view import FileManagerView
    return FileManagerView()


def test_start_trash_op_drains_prior_thread(tmp_path, monkeypatch):
    """_start_trash_op() uses _drain_trash_thread(), not a bare quit()."""
    from unittest.mock import MagicMock
    fm = _make_fm(tmp_path, monkeypatch)
    from PyQt6.QtCore import QThread

    mock_thread = MagicMock(spec=QThread)
    mock_thread.isRunning.return_value = True
    mock_thread.wait.return_value = True
    mock_worker = MagicMock()

    fm._trash_thread = mock_thread
    fm._trash_worker = mock_worker

    # Prevent actually starting a real thread
    monkeypatch.setattr(QThread, "start", lambda self: None)

    fm._start_trash_op("empty", [])

    # The old thread must have been drained (quit + wait), not just quit()
    mock_thread.quit.assert_called_once()
    mock_thread.wait.assert_called_once_with(3000)


def test_trash_list_failed_shows_error_not_spinner(tmp_path, monkeypatch):
    """When _TrashListWorker emits failed, TrashView shows an error — not 'Loading…'."""
    from backends.trash_backend import TrashBackend
    fm = _make_fm(tmp_path, monkeypatch)

    from PyQt6.QtCore import QThread
    monkeypatch.setattr(QThread, "start", lambda self: None)

    # Make list_trash raise so the worker emits failed
    monkeypatch.setattr(TrashBackend, "list_trash",
                        lambda self: (_ for _ in ()).throw(RuntimeError("disk gone")))

    fm._load_trash()
    # Simulate the worker emitting failed directly (thread never started)
    fm._on_trash_list_failed("disk gone")

    top = fm._trash_view._tree.topLevelItem(0)
    assert top is not None
    text = top.text(0)
    assert "disk gone" in text
    assert "Loading" not in text


def test_load_trash_uses_worker_not_direct_call(tmp_path, monkeypatch):
    """_load_trash() must not call TrashBackend.list_trash() on the UI thread."""
    from backends.trash_backend import TrashBackend
    from unittest.mock import MagicMock

    fm = _make_fm(tmp_path, monkeypatch)

    # Prevent actual thread start
    from PyQt6.QtCore import QThread
    monkeypatch.setattr(QThread, "start", lambda self: None)

    direct_calls: list = []
    original = TrashBackend.list_trash
    monkeypatch.setattr(TrashBackend, "list_trash",
                        lambda self: direct_calls.append(1) or [])

    fm._load_trash()

    assert direct_calls == [], "_load_trash() must not call list_trash() synchronously"
