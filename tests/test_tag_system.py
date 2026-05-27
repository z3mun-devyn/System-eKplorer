"""Tests for models/tag.py (dataclasses) and strings.contrast_color.

Schema migration and TagRepository CRUD live in tests/test_tags_backend.py.
"""

import pytest

from models.package import Package
from models.tag import PackageEntry, Tag
import strings


# ── Tag dataclass ─────────────────────────────────────────────────────────────

def test_tag_has_name_and_color():
    tag = Tag(name="Work", color_hex="#3498db")
    assert tag.name == "Work"
    assert tag.color_hex == "#3498db"


def test_tag_has_no_id_field():
    tag = Tag(name="Gaming", color_hex="#e74c3c")
    assert not hasattr(tag, "id")


# ── PackageEntry dataclass ────────────────────────────────────────────────────

def test_package_entry_defaults_to_no_tags():
    pkg = Package("vim", "2:8.2", 3584, "editors")
    entry = PackageEntry(package=pkg)
    assert entry.tags == []


def test_package_entry_stores_tags():
    pkg = Package("vim", "2:8.2", 3584, "editors")
    tag = Tag(name="Work", color_hex="#3498db")
    entry = PackageEntry(package=pkg, tags=[tag])
    assert len(entry.tags) == 1
    assert entry.tags[0].name == "Work"


def test_package_source_defaults_to_apt():
    pkg = Package("bash", "5.1", 6608, "shells")
    assert pkg.source == "apt"


# ── contrast_color ────────────────────────────────────────────────────────────

@pytest.mark.parametrize("color,expected", [
    ("#ffffff", "#000000"),
    ("#000000", "#ffffff"),
    ("#3498db", "#000000"),
    ("#f1c40f", "#000000"),
    ("#1abc9c", "#000000"),
    ("#9b59b6", "#ffffff"),
])
def test_contrast_color(color, expected):
    assert strings.contrast_color(color) == expected
