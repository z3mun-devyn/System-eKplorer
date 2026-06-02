"""Tests for column-visibility constants, settings persistence, and v2→v3 migration."""
from __future__ import annotations

import json
import sqlite3

import pytest

from backends.settings_backend import SettingsRepository
from models.database import CURRENT_VERSION, open_db
from views.packages_view import (
    _COL_ICON,
    _COL_NAME,
    _VISIBILITY_KEYS,
    _VISIBILITY_LABELS,
    _SETTINGS_COL_VIS,
)

# ── Stretch / fixed column invariants ─────────────────────────────────────────

def test_name_col_excluded_from_toggleable_keys():
    # Name is the stretch absorber — always visible, never hideable.
    assert _COL_NAME not in _VISIBILITY_KEYS


def test_icon_col_is_toggleable():
    # Icon is Fixed-width but still user-hideable via the visibility menu.
    assert _COL_ICON in _VISIBILITY_KEYS


def test_name_col_not_in_visibility_labels():
    assert _COL_NAME not in _VISIBILITY_LABELS


# ── All expected toggleable columns are present ───────────────────────────────

def test_all_seven_keys_present():
    expected = {"icon", "tags", "category", "source", "version", "size", "installed"}
    assert set(_VISIBILITY_KEYS.values()) == expected


def test_visibility_labels_match_keys():
    assert set(_VISIBILITY_LABELS.keys()) == set(_VISIBILITY_KEYS.keys())


# ── Column visibility JSON round-trip via SettingsRepository ─────────────────

def test_column_visibility_json_round_trip(tmp_path):
    repo = SettingsRepository(tmp_path / "data.db")
    vis = {key: True for key in _VISIBILITY_KEYS.values()}
    vis["tags"] = False
    vis["installed"] = False
    repo.set(_SETTINGS_COL_VIS, json.dumps(vis))
    raw = repo.get(_SETTINGS_COL_VIS)
    assert raw is not None
    recovered = json.loads(raw)
    assert recovered["tags"] is False
    assert recovered["installed"] is False
    assert recovered["icon"] is True


def test_missing_visibility_setting_returns_none(tmp_path):
    repo = SettingsRepository(tmp_path / "data.db")
    assert repo.get(_SETTINGS_COL_VIS) is None


# ── v2 → v3 migration ────────────────────────────────────────────────────────

def _make_v2_db(path) -> None:
    """Manually create a v2 DB (user_version=2, has tags and package_tags)."""
    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TABLE drive_labels"
        " (device_id TEXT PRIMARY KEY, label TEXT NOT NULL,"
        "  color_hex TEXT, updated_at TEXT NOT NULL)"
    )
    conn.execute("CREATE TABLE tags (name TEXT PRIMARY KEY, color_hex TEXT NOT NULL)")
    conn.execute(
        "CREATE TABLE package_tags"
        " (package_source TEXT NOT NULL, package_name TEXT NOT NULL,"
        "  tag_name TEXT NOT NULL REFERENCES tags(name) ON DELETE CASCADE,"
        "  PRIMARY KEY (package_source, package_name, tag_name))"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_pkg_tags"
        " ON package_tags (package_source, package_name)"
    )
    conn.execute("INSERT INTO tags VALUES ('Work', '#3498db')")
    conn.execute("PRAGMA user_version = 2")
    conn.commit()
    conn.close()


def test_v2_migrates_to_v3(tmp_path):
    db = tmp_path / "data.db"
    _make_v2_db(db)
    with open_db(db) as conn:
        uv = conn.execute("PRAGMA user_version").fetchone()[0]
    assert uv == CURRENT_VERSION


def test_v2_migration_adds_settings_table(tmp_path):
    db = tmp_path / "data.db"
    _make_v2_db(db)
    with open_db(db) as conn:
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='settings'"
        ).fetchone()
    assert row is not None


def test_v2_migration_preserves_tags_data(tmp_path):
    db = tmp_path / "data.db"
    _make_v2_db(db)
    with open_db(db) as conn:
        rows = conn.execute("SELECT name FROM tags").fetchall()
    names = [r["name"] for r in rows]
    assert "Work" in names


def test_v2_migration_does_not_break_drive_labels(tmp_path):
    db = tmp_path / "data.db"
    _make_v2_db(db)
    with open_db(db) as conn:
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='drive_labels'"
        ).fetchone()
    assert row is not None


def test_fresh_v3_db_has_settings_table(tmp_path):
    db = tmp_path / "data.db"
    with open_db(db) as conn:
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='settings'"
        ).fetchone()
    assert row is not None


def test_settings_table_key_is_primary_key(tmp_path):
    db = tmp_path / "data.db"
    with open_db(db) as conn:
        info = conn.execute("PRAGMA table_info(settings)").fetchall()
    cols = {row["name"]: row for row in info}
    assert "key" in cols
    assert cols["key"]["pk"] == 1
