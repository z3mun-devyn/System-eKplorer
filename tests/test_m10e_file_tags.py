"""M10e tests: FileTagRepository + file-view tag integration."""
from __future__ import annotations

import inspect
from pathlib import Path

import pytest

from backends.file_tags_backend import FileTagRepository
from backends.tags_backend import TagRepository


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture()
def db(tmp_path):
    """Fresh in-memory-like DB at a temp path with tags pre-created."""
    db_path = tmp_path / "test.db"
    tag_repo = TagRepository(db_path)
    tag_repo.create_tag("work", "#e74c3c")
    tag_repo.create_tag("personal", "#3498db")
    tag_repo.create_tag("media", "#2ecc71")
    return db_path


@pytest.fixture()
def repo(db):
    return FileTagRepository(db)


@pytest.fixture()
def tag_repo(db):
    return TagRepository(db)


# ── FileTagRepository: basic CRUD ─────────────────────────────────────────────

def test_tags_for_path_empty_initially(repo):
    assert repo.tags_for_path("/home/user/notes.txt") == []


def test_set_and_retrieve_single_tag(repo):
    repo.set_assignments("/home/user/doc.pdf", {"work"})
    tags = repo.tags_for_path("/home/user/doc.pdf")
    assert len(tags) == 1
    assert tags[0].name == "work"
    assert tags[0].color_hex == "#e74c3c"


def test_set_multiple_tags(repo):
    repo.set_assignments("/home/user/photo.jpg", {"personal", "media"})
    tags = repo.tags_for_path("/home/user/photo.jpg")
    names = {t.name for t in tags}
    assert names == {"personal", "media"}


def test_replace_assignments(repo):
    repo.set_assignments("/home/user/file.txt", {"work", "personal"})
    repo.set_assignments("/home/user/file.txt", {"media"})
    tags = repo.tags_for_path("/home/user/file.txt")
    assert len(tags) == 1
    assert tags[0].name == "media"


def test_clear_assignments_with_empty_set(repo):
    repo.set_assignments("/home/user/file.txt", {"work"})
    repo.set_assignments("/home/user/file.txt", set())
    assert repo.tags_for_path("/home/user/file.txt") == []


def test_different_paths_are_independent(repo):
    repo.set_assignments("/home/user/a.txt", {"work"})
    repo.set_assignments("/home/user/b.txt", {"personal"})
    assert repo.tags_for_path("/home/user/a.txt")[0].name == "work"
    assert repo.tags_for_path("/home/user/b.txt")[0].name == "personal"


# ── FileTagRepository: bulk_load ──────────────────────────────────────────────

def test_bulk_load_empty_list(repo):
    assert repo.bulk_load([]) == {}


def test_bulk_load_no_tagged_paths(repo):
    result = repo.bulk_load(["/home/user/x.txt", "/home/user/y.txt"])
    assert result == {}


def test_bulk_load_returns_tagged_paths_only(repo):
    repo.set_assignments("/home/user/a.txt", {"work"})
    result = repo.bulk_load(["/home/user/a.txt", "/home/user/b.txt"])
    assert "/home/user/a.txt" in result
    assert "/home/user/b.txt" not in result


def test_bulk_load_multiple_tags(repo):
    repo.set_assignments("/home/user/a.txt", {"work", "personal"})
    result = repo.bulk_load(["/home/user/a.txt"])
    assert len(result["/home/user/a.txt"]) == 2
    names = {t.name for t in result["/home/user/a.txt"]}
    assert names == {"work", "personal"}


def test_bulk_load_multiple_paths(repo):
    repo.set_assignments("/home/user/a.txt", {"work"})
    repo.set_assignments("/home/user/b.txt", {"media"})
    result = repo.bulk_load(["/home/user/a.txt", "/home/user/b.txt"])
    assert result["/home/user/a.txt"][0].name == "work"
    assert result["/home/user/b.txt"][0].name == "media"


# ── Schema migration: file_tags table exists ──────────────────────────────────

def test_file_tags_table_created(tmp_path):
    from models.database import open_db
    db_path = tmp_path / "schema_test.db"
    with open_db(db_path) as conn:
        tables = {row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
    assert "file_tags" in tables


def test_cascade_delete_removes_file_tags(db):
    """Deleting a tag from tags table must cascade to file_tags."""
    fr = FileTagRepository(db)
    tr = TagRepository(db)
    fr.set_assignments("/home/user/doc.txt", {"work"})
    assert len(fr.tags_for_path("/home/user/doc.txt")) == 1
    tr.delete_tag("work")
    assert fr.tags_for_path("/home/user/doc.txt") == []


# ── FileView: set_tag_map propagates to Tags column ──────────────────────────

def test_file_model_set_tag_map():
    from models.tag import Tag
    from views.file_view import _FileModel, _TAG_DATA_ROLE, _COL_TAGS
    from models.file_entry import FileEntry

    model = _FileModel()
    entry = FileEntry(
        name="report.pdf",
        path=Path("/home/user/report.pdf"),
        size=1024,
        modified=0.0,
        mime_type="application/pdf",
        is_dir=False,
        is_hidden=False,
    )
    model.set_entries([entry])
    assert model.rowCount() == 1

    # Before tag_map: Tags column returns empty list via _TAG_DATA_ROLE
    idx = model.index(0, _COL_TAGS)
    assert model.data(idx, _TAG_DATA_ROLE) == []

    tag = Tag(name="work", color_hex="#e74c3c")
    model.set_tag_map({str(entry.path): [tag]})
    result = model.data(idx, _TAG_DATA_ROLE)
    assert len(result) == 1
    assert result[0].name == "work"


def test_file_model_tags_display_role():
    from models.tag import Tag
    from views.file_view import _FileModel, _COL_TAGS
    from models.file_entry import FileEntry
    from PyQt6.QtCore import Qt

    model = _FileModel()
    entry = FileEntry(
        name="photo.jpg",
        path=Path("/home/user/photo.jpg"),
        size=512,
        modified=0.0,
        mime_type="image/jpeg",
        is_dir=False,
        is_hidden=False,
    )
    model.set_entries([entry])
    tag = Tag(name="media", color_hex="#2ecc71")
    model.set_tag_map({str(entry.path): [tag]})
    idx = model.index(0, _COL_TAGS)
    assert model.data(idx, Qt.ItemDataRole.DisplayRole) == "media"


def test_file_model_tags_sort_role():
    from models.tag import Tag
    from views.file_view import _FileModel, _COL_TAGS, _SORT_ROLE
    from models.file_entry import FileEntry

    model = _FileModel()
    entry = FileEntry(
        name="x.txt",
        path=Path("/home/user/x.txt"),
        size=10,
        modified=0.0,
        mime_type="text/plain",
        is_dir=False,
        is_hidden=False,
    )
    model.set_entries([entry])
    # No tags → sort key is empty string
    idx = model.index(0, _COL_TAGS)
    assert model.data(idx, _SORT_ROLE) == ""

    tag = Tag(name="Work", color_hex="#e74c3c")
    model.set_tag_map({str(entry.path): [tag]})
    assert model.data(idx, _SORT_ROLE) == "work"


# ── FileView.entries_ready signal ─────────────────────────────────────────────

def test_file_view_has_entries_ready_signal():
    from views.file_view import FileView
    fv = FileView()
    assert hasattr(fv, "entries_ready")


# ── FileManagerView wiring ────────────────────────────────────────────────────

def test_file_manager_view_loads_tags_on_entries_ready(monkeypatch):
    """_load_file_tags is called when entries_ready fires."""
    from views.file_manager_view import FileManagerView
    fmv = FileManagerView()
    called = []
    monkeypatch.setattr(fmv, "_load_file_tags", lambda: called.append(1))
    fmv._left_view.entries_ready.emit()
    assert called == [1]


def test_assign_tags_action_opens_modal(monkeypatch):
    """assign_tags action calls _open_file_tag_modal with the entries list."""
    from views.file_manager_view import FileManagerView
    from models.file_entry import FileEntry

    fmv = FileManagerView()
    opened_with = []

    def fake_open(entries):
        opened_with.extend(entries)

    monkeypatch.setattr(fmv, "_open_file_tag_modal", fake_open)
    entry = FileEntry(
        name="doc.txt",
        path=Path("/home/user/doc.txt"),
        size=100,
        modified=0.0,
        mime_type="text/plain",
        is_dir=False,
        is_hidden=False,
    )
    fmv._on_action_requested("assign_tags", [entry])
    assert len(opened_with) == 1
    assert opened_with[0].name == "doc.txt"
