"""pytest-qt tests for views/tag_editor_modal.py.

Covers:
  1. Default swatch is the third palette color (TAG_PALETTE[2]).
  2. Saving with an empty name field does not create a tag.
  3. Tab-switch state preservation: hide/show does not reset modal state.
"""

import pytest

import strings
from backends.tags_backend import TagRepository
from models.package import Package
from models.tag import PackageEntry, Tag
from views.tag_editor_modal import TagModal


# ── Fixture ───────────────────────────────────────────────────────────────────

@pytest.fixture
def modal(qtbot, tmp_path):
    db = tmp_path / "data.db"
    widget = TagModal(None, db_path=db)
    qtbot.addWidget(widget)
    return widget, db


# ── 1. Default swatch ─────────────────────────────────────────────────────────

def test_default_selected_color_is_third_palette(modal):
    widget, _ = modal
    assert widget._selected_color == strings.TAG_PALETTE[2]


def test_third_swatch_shown_as_selected_on_fresh_open(modal):
    widget, _ = modal
    widget.open_for(None)
    third = strings.TAG_PALETTE[2]
    selected = [sw for sw in widget._swatches if sw.isChecked()]
    assert len(selected) == 1
    assert selected[0].color == third


# ── 2. Empty name does not create a tag ──────────────────────────────────────

def test_save_with_empty_name_creates_no_tag(modal):
    widget, db = modal
    pkg = Package("vim", "2:8.2", 3584, "editors")
    widget.open_for(PackageEntry(package=pkg))
    widget._name_edit.setText("")
    widget._on_save()
    assert TagRepository(db).all_tags() == []


def test_save_with_whitespace_only_name_creates_no_tag(modal):
    widget, db = modal
    pkg = Package("bash", "5.1", 6608, "shells")
    widget.open_for(PackageEntry(package=pkg))
    widget._name_edit.setText("   ")
    widget._on_save()
    assert TagRepository(db).all_tags() == []


def test_save_with_name_creates_tag(modal):
    widget, db = modal
    pkg = Package("vim", "2:8.2", 3584, "editors")
    widget.open_for(PackageEntry(package=pkg))
    widget._name_edit.setText("Work")
    widget._on_save()
    tags = TagRepository(db).all_tags()
    assert len(tags) == 1
    assert tags[0].name == "Work"


# ── 3. Tab-switch state preservation ─────────────────────────────────────────

def test_hide_show_preserves_name_field(modal, qtbot):
    widget, _ = modal
    widget.open_for(PackageEntry(package=Package("vim", "2:8.2", 3584, "editors")))
    widget._name_edit.setText("MyTag")
    widget.setVisible(False)
    widget.setVisible(True)
    assert widget._name_edit.text() == "MyTag"


def test_hide_show_preserves_selected_swatch(modal, qtbot):
    widget, _ = modal
    widget.open_for(PackageEntry(package=Package("vim", "2:8.2", 3584, "editors")))
    target = strings.TAG_PALETTE[4]
    widget._select_color(target)
    widget.setVisible(False)
    widget.setVisible(True)
    assert widget._selected_color == target


def test_hide_show_preserves_pill_toggle_state(modal, qtbot):
    widget, db = modal
    # Create a tag so there's a pill to toggle
    repo = TagRepository(db)
    repo.create_tag("Gaming", strings.TAG_PALETTE[0])
    pkg = Package("vim", "2:8.2", 3584, "editors")
    widget.open_for(PackageEntry(package=pkg))
    # Toggle the first pill on
    assert len(widget._pills) == 1
    pill = widget._pills[0]
    original_state = pill.is_assigned()
    pill._on_click()  # toggle
    toggled_state = pill.is_assigned()
    assert toggled_state != original_state
    # Hide and show — toggle state must survive
    widget.setVisible(False)
    widget.setVisible(True)
    assert widget._pills[0].is_assigned() == toggled_state
