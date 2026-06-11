"""Regression: file-tag pills must appear without an app restart.

Reported symptom: after tagging a file, pills only showed after restarting the
app. The hypothesised cause was a commit-ordering race — FileTagModal emitting
`saved` (which triggers _load_file_tags → bulk_load) while the DB write was still
in an open transaction, so the refresh read stale/empty rows.

Diagnosis (see HANDOFF) showed the live path is actually correct:
  - open_db() commits on context-manager exit, so set_assignments is durable
    BEFORE the modal calls saved.emit();
  - _load_file_tags refreshes both panes against the displayed source model.

This test locks in the invariant that made it correct: by the time `saved`
fires, a FRESH FileTagRepository (new DB connection) already sees the new
assignment. If anyone reorders _on_save to emit before the commit, this fails.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from backends.file_tags_backend import FileTagRepository
from models.file_entry import FileEntry


def _qt():
    pytest.importorskip("PyQt6")
    from PyQt6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def _entry(tmp_path: Path, name: str = "doc.txt") -> FileEntry:
    f = tmp_path / name
    f.write_text("x")
    return FileEntry(
        name=name, path=f, size=1, modified=0.0,
        mime_type="text/plain", is_dir=False, is_hidden=False,
    )


def test_modal_commits_before_saved_emits(tmp_path):
    """Inside the saved slot, a fresh repo connection must already see the tag."""
    _qt()
    from views.file_tag_modal import FileTagModal

    db_path = tmp_path / "tags.db"
    entry = _entry(tmp_path)
    modal = FileTagModal([entry], db_path=db_path)
    modal._name_edit.setText("urgent")   # create + assign a brand-new tag

    seen: dict[str, list[str]] = {}

    def on_saved() -> None:
        # A NEW connection (open_db opens fresh each call) — only sees committed rows.
        fresh = FileTagRepository(db_path).bulk_load([str(entry.path)])
        seen["tags"] = [t.name for t in fresh.get(str(entry.path), [])]

    modal.saved.connect(on_saved)
    modal._on_save()

    assert seen.get("tags") == ["urgent"], (
        "saved fired before the DB write was committed/visible to a fresh "
        "connection — pills would require a restart"
    )


def test_modal_untag_visible_to_fresh_connection_at_emit(tmp_path):
    """Removing the last tag is also committed before saved fires (pills vanish)."""
    _qt()
    from views.file_tag_modal import FileTagModal

    db_path = tmp_path / "tags.db"
    entry = _entry(tmp_path)
    # Pre-create the tag (FK: file_tags.tag_name → tags.name) then assign it.
    from backends.tags_backend import TagRepository
    TagRepository(db_path).create_tag("urgent", "#e74c3c")
    FileTagRepository(db_path).set_assignments(str(entry.path), {"urgent"})

    modal = FileTagModal([entry], db_path=db_path)
    # Toggle every pill OFF so the save clears all assignments.
    for pill in modal._pills:
        pill._assigned = False

    seen: dict[str, list[str]] = {}
    modal.saved.connect(
        lambda: seen.__setitem__(
            "tags",
            [t.name for t in
             FileTagRepository(db_path).bulk_load([str(entry.path)]).get(str(entry.path), [])],
        )
    )
    modal._on_save()

    assert seen.get("tags") == [], "untag not committed before saved fired"


def test_modal_emits_saved_exactly_once(tmp_path):
    _qt()
    from views.file_tag_modal import FileTagModal

    db_path = tmp_path / "tags.db"
    modal = FileTagModal([_entry(tmp_path)], db_path=db_path)
    modal._name_edit.setText("alpha")

    calls = []
    modal.saved.connect(lambda: calls.append(1))
    modal._on_save()
    assert len(calls) == 1
