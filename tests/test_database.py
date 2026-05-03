"""Tests for models/database.py: schema creation, directory setup, CRUD, versioning."""

import stat
from datetime import datetime, timezone
from pathlib import Path

import pytest

from models.database import CURRENT_VERSION, open_db


def _now() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Directory and file creation
# ---------------------------------------------------------------------------

def test_creates_db_when_missing(tmp_path):
    db_path = tmp_path / "sub" / "data.db"
    assert not db_path.exists()
    with open_db(db_path):
        pass
    assert db_path.exists()


def test_creates_directory_when_missing(tmp_path):
    db_path = tmp_path / "newdir" / "data.db"
    with open_db(db_path):
        pass
    assert db_path.parent.is_dir()


def test_directory_created_with_mode_0700(tmp_path):
    db_path = tmp_path / "secure" / "data.db"
    with open_db(db_path):
        pass
    mode = stat.S_IMODE(db_path.parent.stat().st_mode)
    assert mode == 0o700


# ---------------------------------------------------------------------------
# Schema versioning
# ---------------------------------------------------------------------------

def test_schema_version_row_inserted(tmp_path):
    db_path = tmp_path / "data.db"
    with open_db(db_path) as conn:
        row = conn.execute("SELECT version FROM schema_version").fetchone()
    assert row is not None
    assert row["version"] == CURRENT_VERSION


def test_schema_version_not_duplicated_on_reopen(tmp_path):
    db_path = tmp_path / "data.db"
    with open_db(db_path):
        pass
    with open_db(db_path) as conn:
        count = conn.execute("SELECT COUNT(*) FROM schema_version").fetchone()[0]
    assert count == 1


def test_drive_labels_table_exists(tmp_path):
    db_path = tmp_path / "data.db"
    with open_db(db_path) as conn:
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='drive_labels'"
        ).fetchone()
    assert row is not None


# ---------------------------------------------------------------------------
# drive_labels CRUD
# ---------------------------------------------------------------------------

def test_insert_drive_label(tmp_path):
    db_path = tmp_path / "data.db"
    with open_db(db_path) as conn:
        conn.execute(
            "INSERT INTO drive_labels (device_id, label, color_hex, updated_at)"
            " VALUES (?, ?, ?, ?)",
            ("ata-Samsung_EVO_500GB", "Work", "#3498db", _now()),
        )
    with open_db(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM drive_labels WHERE device_id = 'ata-Samsung_EVO_500GB'"
        ).fetchone()
    assert row["label"] == "Work"
    assert row["color_hex"] == "#3498db"


def test_update_drive_label_via_replace(tmp_path):
    db_path = tmp_path / "data.db"
    with open_db(db_path) as conn:
        conn.execute(
            "INSERT INTO drive_labels VALUES (?, ?, ?, ?)",
            ("disk-1", "Old", "#e74c3c", _now()),
        )
    with open_db(db_path) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO drive_labels VALUES (?, ?, ?, ?)",
            ("disk-1", "New", "#2ecc71", _now()),
        )
    with open_db(db_path) as conn:
        row = conn.execute(
            "SELECT label, color_hex FROM drive_labels WHERE device_id = 'disk-1'"
        ).fetchone()
    assert row["label"] == "New"
    assert row["color_hex"] == "#2ecc71"


def test_delete_drive_label(tmp_path):
    db_path = tmp_path / "data.db"
    with open_db(db_path) as conn:
        conn.execute(
            "INSERT INTO drive_labels VALUES (?, ?, ?, ?)",
            ("disk-temp", "Temp", "#f1c40f", _now()),
        )
    with open_db(db_path) as conn:
        conn.execute("DELETE FROM drive_labels WHERE device_id = ?", ("disk-temp",))
    with open_db(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM drive_labels WHERE device_id = 'disk-temp'"
        ).fetchone()
    assert row is None


def test_device_id_is_primary_key(tmp_path):
    db_path = tmp_path / "data.db"
    with open_db(db_path) as conn:
        conn.execute(
            "INSERT INTO drive_labels VALUES (?, ?, ?, ?)",
            ("disk-pk", "One", "#3498db", _now()),
        )
    with open_db(db_path) as conn:
        with pytest.raises(Exception):
            conn.execute(
                "INSERT INTO drive_labels VALUES (?, ?, ?, ?)",
                ("disk-pk", "Two", "#e74c3c", _now()),
            )
            conn.commit()


def test_color_hex_nullable(tmp_path):
    db_path = tmp_path / "data.db"
    with open_db(db_path) as conn:
        conn.execute(
            "INSERT INTO drive_labels VALUES (?, ?, ?, ?)",
            ("disk-no-color", "Unnamed", None, _now()),
        )
    with open_db(db_path) as conn:
        row = conn.execute(
            "SELECT color_hex FROM drive_labels WHERE device_id = 'disk-no-color'"
        ).fetchone()
    assert row["color_hex"] is None
