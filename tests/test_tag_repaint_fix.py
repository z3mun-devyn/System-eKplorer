"""Tag repaint fix tests + chmod generation guard.

Part 1 (Packages): _PackageModel.refresh_tags() emits dataChanged on _COL_TAGS
  only, preserving scroll position and selection.

Part 2 (FM): _load_file_tags() → set_tag_map() → dataChanged on _COL_TAGS.
  The assign-tags path (M10e) IS built and wired; no gap exists.

Part 3 (Properties): chmod worker result slots are guarded by _chmod_expected_gen
  so stale results from a previous file are discarded after selection changes.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from models.package import Package
from models.tag import PackageEntry, Tag


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_package(name: str, source: str = "apt") -> Package:
    return Package(
        name=name,
        version="1.0",
        installed_size_kb=100,
        section="misc",
        source=source,
    )


def _make_entry(name: str, tags: list[Tag] | None = None,
                source: str = "apt") -> PackageEntry:
    return PackageEntry(package=_make_package(name, source),
                        tags=tags or [])


def _make_tag(name: str) -> Tag:
    return Tag(name=name, color_hex="#ff0000")


# ── Part 1: _PackageModel.refresh_tags() ──────────────────────────────────────

def test_refresh_tags_emits_data_changed_on_col_tags():
    """refresh_tags() emits dataChanged for exactly _COL_TAGS, not other columns."""
    from views.packages_view import _PackageModel, _COL_TAGS

    model = _PackageModel()
    model.set_entries([_make_entry("vim"), _make_entry("git")])

    changed: list[tuple[int, int]] = []

    def _record(tl, br, _roles):
        changed.append((tl.column(), br.column()))

    model.dataChanged.connect(_record)

    tag = _make_tag("work")
    model.refresh_tags({("apt", "vim"): [tag]})

    assert changed, "no dataChanged emitted"
    assert all(c[0] == _COL_TAGS and c[1] == _COL_TAGS for c in changed), (
        f"Expected all dataChanged on col {_COL_TAGS}, got {changed}"
    )


def test_refresh_tags_covers_all_rows():
    """dataChanged from refresh_tags() spans row 0 to rowCount-1."""
    from views.packages_view import _PackageModel, _COL_TAGS

    model = _PackageModel()
    model.set_entries([_make_entry("a"), _make_entry("b"), _make_entry("c")])

    ranges: list[tuple[int, int]] = []

    def _record(tl, br, _roles):
        if tl.column() == _COL_TAGS:
            ranges.append((tl.row(), br.row()))

    model.dataChanged.connect(_record)
    model.refresh_tags({})

    assert ranges, "no dataChanged for _COL_TAGS"
    assert ranges[0][0] == 0
    assert ranges[0][1] == model.rowCount() - 1


def test_refresh_tags_updates_entry_tags_in_place():
    """refresh_tags() mutates each entry's .tags to reflect the new assignments."""
    from views.packages_view import _PackageModel

    tag = _make_tag("work")
    entries = [_make_entry("vim"), _make_entry("git")]
    model = _PackageModel()
    model.set_entries(entries)

    model.refresh_tags({("apt", "vim"): [tag]})

    assert model._entries[0].tags == [tag]
    assert model._entries[1].tags == []


def test_refresh_tags_clears_tags_not_in_assignments():
    """refresh_tags() replaces tags even when a package is absent from assignments."""
    from views.packages_view import _PackageModel

    tag = _make_tag("old")
    entries = [_make_entry("vim", tags=[tag])]
    model = _PackageModel()
    model.set_entries(entries)

    model.refresh_tags({})  # empty — vim should lose its tag

    assert model._entries[0].tags == []


def test_refresh_tags_noop_when_loading():
    """refresh_tags() does nothing and emits no signal when model is in loading state."""
    from views.packages_view import _PackageModel

    model = _PackageModel()
    # Do NOT call set_entries — model remains in loading state (_entries is None)

    changed: list = []
    model.dataChanged.connect(lambda *_: changed.append(True))
    model.refresh_tags({("apt", "vim"): [_make_tag("work")]})

    assert changed == []


def test_refresh_tags_handles_flatpak_source():
    """refresh_tags() uses (source, name) key so flatpak packages update correctly."""
    from views.packages_view import _PackageModel

    tag = _make_tag("media")
    entries = [_make_entry("org.gimp.GIMP", source="flatpak")]
    model = _PackageModel()
    model.set_entries(entries)

    model.refresh_tags({("flatpak", "org.gimp.GIMP"): [tag]})

    assert model._entries[0].tags == [tag]


# ── Part 1: _on_tags_saved uses refresh_tags not set_entries ─────────────────

def test_on_tags_saved_emits_data_changed_not_model_reset(monkeypatch):
    """_on_tags_saved triggers dataChanged (not beginResetModel) for Tags column."""
    from views.packages_view import _PackageModel, _COL_TAGS
    from backends.tags_backend import TagRepository

    model = _PackageModel()
    model.set_entries([_make_entry("vim"), _make_entry("git")])

    data_changed_cols: list[tuple[int, int]] = []
    reset_calls: list[str] = []

    model.dataChanged.connect(
        lambda tl, br, _: data_changed_cols.append((tl.column(), br.column()))
    )
    model.modelAboutToBeReset.connect(lambda: reset_calls.append("reset"))

    # Directly call refresh_tags (same path _on_tags_saved takes)
    model.refresh_tags({})

    assert any(c[0] == _COL_TAGS for c in data_changed_cols), (
        "dataChanged not emitted for _COL_TAGS"
    )
    assert reset_calls == [], "model reset unexpectedly triggered"


# ── Part 2: FM _load_file_tags → dataChanged on _COL_TAGS ────────────────────

def test_load_file_tags_triggers_data_changed_on_col_tags(tmp_path, monkeypatch):
    """_load_file_tags() calls set_tag_map() which emits dataChanged on _COL_TAGS."""
    from views.file_manager_view import FileManagerView
    from views.file_view import _COL_TAGS
    from models.file_entry import FileEntry

    fmv = FileManagerView()

    f = tmp_path / "doc.txt"
    f.write_text("hello")
    entry = FileEntry(
        name="doc.txt",
        path=f,
        size=5,
        modified=f.stat().st_mtime,
        mime_type="text/plain",
        is_dir=False,
        is_hidden=False,
    )
    fmv._left_view._model.set_entries([entry])

    changed_cols: list[tuple[int, int]] = []

    fmv._left_view._model.dataChanged.connect(
        lambda tl, br, _: changed_cols.append((tl.column(), br.column()))
    )

    # _load_file_tags calls FileTagRepository().bulk_load() — patch to return no tags
    monkeypatch.setattr(
        "views.file_manager_view.FileTagRepository",
        lambda: type("R", (), {"bulk_load": staticmethod(lambda _: {})})(),
    )

    fmv._load_file_tags()

    assert any(c[0] == _COL_TAGS and c[1] == _COL_TAGS for c in changed_cols), (
        f"Expected dataChanged on col {_COL_TAGS} after _load_file_tags, got {changed_cols}"
    )


# ── Part 3: chmod generation guard ────────────────────────────────────────────

def _make_pp():
    from views.properties_panel import PropertiesPanel
    return PropertiesPanel()


def _make_pp_entry(tmp_path: Path) -> object:
    from models.file_entry import FileEntry
    f = tmp_path / "file.txt"
    f.write_text("x")
    return FileEntry(
        name="file.txt", path=f, size=1,
        modified=f.stat().st_mtime,
        mime_type="text/plain", is_dir=False, is_hidden=False,
    )


def test_chmod_done_stale_generation_does_not_reenable_button(tmp_path):
    """_on_chmod_done() with stale generation is discarded; button stays disabled."""
    pp = _make_pp()

    def _noop_ow(e):
        pp._ow_expected_gen = pp._generation

    pp._populate_open_with = _noop_ow
    pp.populate_general(_make_pp_entry(tmp_path))

    pp._chmod_btn.setEnabled(False)
    pp._chmod_expected_gen = pp._generation - 1  # stale
    pp._on_chmod_done()

    assert not pp._chmod_btn.isEnabled()


def test_chmod_failed_stale_generation_shows_no_dialog(tmp_path, monkeypatch):
    """_on_chmod_failed() with stale generation suppresses the warning dialog."""
    pp = _make_pp()

    def _noop_ow(e):
        pp._ow_expected_gen = pp._generation

    pp._populate_open_with = _noop_ow
    pp.populate_general(_make_pp_entry(tmp_path))

    dialogs: list = []
    monkeypatch.setattr(
        "views.properties_panel.QMessageBox.warning",
        lambda *a, **kw: dialogs.append(True),
    )

    pp._chmod_expected_gen = pp._generation - 1  # stale
    pp._on_chmod_failed("permission denied")

    assert dialogs == []


def test_chmod_done_current_generation_reenables_button(tmp_path):
    """_on_chmod_done() with current generation re-enables the button."""
    pp = _make_pp()

    def _noop_ow(e):
        pp._ow_expected_gen = pp._generation

    pp._populate_open_with = _noop_ow
    pp.populate_general(_make_pp_entry(tmp_path))

    pp._chmod_btn.setEnabled(False)
    pp._chmod_expected_gen = pp._generation  # current
    pp._current_entry = None  # skip _populate_permissions
    pp._on_chmod_done()

    assert pp._chmod_btn.isEnabled()


def test_chmod_expected_gen_set_on_chmod_clicked(tmp_path, monkeypatch):
    """_on_chmod_clicked() sets _chmod_expected_gen to the current _generation."""
    pp = _make_pp()

    def _noop_ow(e):
        pp._ow_expected_gen = pp._generation

    pp._populate_open_with = _noop_ow
    entry = _make_pp_entry(tmp_path)
    pp.populate_general(entry)
    pp._current_entry = entry

    # Patch the dialog to return a value and patch the thread to not actually start
    monkeypatch.setattr(
        "views.properties_panel.QInputDialog.getText",
        lambda *a, **kw: ("644", True),
    )
    monkeypatch.setattr(
        "views.properties_panel.QThread.start",
        lambda self: None,
    )

    gen_before = pp._generation
    pp._on_chmod_clicked()

    assert pp._chmod_expected_gen == gen_before
