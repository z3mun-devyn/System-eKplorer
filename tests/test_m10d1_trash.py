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
