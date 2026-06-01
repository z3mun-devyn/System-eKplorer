"""M10a tests: v3→v4 schema migration and RecentPathsBackend."""
from __future__ import annotations

import sqlite3
import time
from pathlib import Path

import pytest


# ── Schema migration: v3 → v4 ────────────────────────────────────────────────

def _make_v3_db(path: Path) -> None:
    """Create a v3 database with representative data in all existing tables."""
    conn = sqlite3.connect(path)
    conn.executescript("""
        CREATE TABLE drive_labels (
            device_id TEXT PRIMARY KEY, label TEXT NOT NULL,
            color_hex TEXT, updated_at TEXT NOT NULL
        );
        CREATE TABLE tags (name TEXT PRIMARY KEY, color_hex TEXT NOT NULL);
        CREATE TABLE package_tags (
            package_source TEXT NOT NULL, package_name TEXT NOT NULL,
            tag_name TEXT NOT NULL REFERENCES tags(name) ON DELETE CASCADE,
            PRIMARY KEY (package_source, package_name, tag_name)
        );
        CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        INSERT INTO drive_labels VALUES ('ata-SAMSUNG', 'Work SSD', '#3498db', '2026-01-01');
        INSERT INTO tags VALUES ('important', '#e74c3c');
        INSERT INTO package_tags VALUES ('apt', 'vim', 'important');
        INSERT INTO settings VALUES ('packages.column_visibility', '{}');
        PRAGMA user_version = 3;
    """)
    conn.commit()
    conn.close()


def test_v4_migration_creates_recent_paths(tmp_path):
    db = tmp_path / "data.db"
    _make_v3_db(db)

    from models.database import open_db
    with open_db(db):
        pass  # triggers migration

    conn = sqlite3.connect(db)
    tables = {row[0] for row in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    conn.close()
    assert "recent_paths" in tables


def test_v4_migration_sets_user_version(tmp_path):
    db = tmp_path / "data.db"
    _make_v3_db(db)

    from models.database import open_db, CURRENT_VERSION
    with open_db(db):
        pass

    conn = sqlite3.connect(db)
    uv = conn.execute("PRAGMA user_version").fetchone()[0]
    conn.close()
    assert uv == CURRENT_VERSION


def test_v4_migration_preserves_drive_labels(tmp_path):
    db = tmp_path / "data.db"
    _make_v3_db(db)

    from models.database import open_db
    with open_db(db) as conn:
        row = conn.execute(
            "SELECT label FROM drive_labels WHERE device_id='ata-SAMSUNG'"
        ).fetchone()
    assert row is not None
    assert row[0] == "Work SSD"


def test_v4_migration_preserves_tags(tmp_path):
    db = tmp_path / "data.db"
    _make_v3_db(db)

    from models.database import open_db
    with open_db(db) as conn:
        row = conn.execute("SELECT color_hex FROM tags WHERE name='important'").fetchone()
    assert row is not None
    assert row[0] == "#e74c3c"


def test_v4_migration_preserves_settings(tmp_path):
    db = tmp_path / "data.db"
    _make_v3_db(db)

    from models.database import open_db
    with open_db(db) as conn:
        row = conn.execute(
            "SELECT value FROM settings WHERE key='packages.column_visibility'"
        ).fetchone()
    assert row is not None


def test_fresh_db_has_recent_paths(tmp_path):
    """A brand-new database also gets the recent_paths table."""
    db = tmp_path / "data.db"
    from models.database import open_db
    with open_db(db):
        pass

    conn = sqlite3.connect(db)
    tables = {row[0] for row in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    conn.close()
    assert "recent_paths" in tables


def test_recent_paths_type_constraint(tmp_path):
    """recent_paths.type accepts 'file' and 'location' but not arbitrary values."""
    db = tmp_path / "data.db"
    from models.database import open_db
    with open_db(db) as conn:
        conn.execute(
            "INSERT INTO recent_paths VALUES (?, 'location', ?)", ("/tmp", 1)
        )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO recent_paths VALUES (?, 'invalid', ?)", ("/x", 1)
            )
            conn.commit()


# ── RecentPathsBackend ────────────────────────────────────────────────────────

@pytest.fixture()
def backend(tmp_path, monkeypatch):
    db = tmp_path / "data.db"
    monkeypatch.setattr("backends.recent_backend.open_db",
                        __import__("functools").partial(
                            __import__("models.database", fromlist=["open_db"]).open_db, db))
    from backends.recent_backend import RecentPathsBackend
    return RecentPathsBackend()


def test_record_location_stores_entry(tmp_path):
    db = tmp_path / "data.db"
    from models.database import open_db
    from backends.recent_backend import RecentPathsBackend

    import functools
    import unittest.mock
    with unittest.mock.patch("backends.recent_backend.open_db",
                             functools.partial(open_db, db)):
        b = RecentPathsBackend()
        b.record_location("/home/user/docs")
        locs = b.list_locations()

    assert "/home/user/docs" in locs


def test_list_locations_returns_newest_first(tmp_path):
    db = tmp_path / "data.db"
    from models.database import open_db
    from backends.recent_backend import RecentPathsBackend
    import functools, unittest.mock

    with unittest.mock.patch("backends.recent_backend.open_db",
                             functools.partial(open_db, db)):
        b = RecentPathsBackend()
        # Insert directly with explicit timestamps so ordering is deterministic
        with open_db(db) as conn:
            conn.execute("INSERT INTO recent_paths VALUES ('/old', 'location', 100)")
            conn.execute("INSERT INTO recent_paths VALUES ('/new', 'location', 200)")
        locs = b.list_locations()

    assert locs[0] == "/new"
    assert locs[1] == "/old"


def test_record_location_upserts_timestamp(tmp_path):
    db = tmp_path / "data.db"
    from models.database import open_db
    from backends.recent_backend import RecentPathsBackend
    import functools, unittest.mock

    with unittest.mock.patch("backends.recent_backend.open_db",
                             functools.partial(open_db, db)):
        with open_db(db) as conn:
            conn.execute("INSERT INTO recent_paths VALUES ('/p', 'location', 1)")
        b = RecentPathsBackend()
        b.record_location("/p")
        with open_db(db) as conn:
            ts = conn.execute(
                "SELECT last_accessed FROM recent_paths WHERE path='/p'"
            ).fetchone()[0]

    assert ts > 1  # timestamp was updated


def test_list_locations_respects_limit(tmp_path):
    db = tmp_path / "data.db"
    from models.database import open_db
    from backends.recent_backend import RecentPathsBackend
    import functools, unittest.mock

    with unittest.mock.patch("backends.recent_backend.open_db",
                             functools.partial(open_db, db)):
        with open_db(db) as conn:
            for i in range(10):
                conn.execute(
                    "INSERT INTO recent_paths VALUES (?, 'location', ?)", (f"/p{i}", i))
        b = RecentPathsBackend()
        locs = b.list_locations(limit=3)

    assert len(locs) == 3


def test_record_and_list_files(tmp_path):
    db = tmp_path / "data.db"
    from models.database import open_db
    from backends.recent_backend import RecentPathsBackend
    import functools, unittest.mock

    with unittest.mock.patch("backends.recent_backend.open_db",
                             functools.partial(open_db, db)):
        b = RecentPathsBackend()
        b.record_file("/home/user/report.pdf")
        files = b.list_files()

    assert "/home/user/report.pdf" in files


def test_files_and_locations_are_independent(tmp_path):
    """Entries with the same path but different types are separate rows."""
    db = tmp_path / "data.db"
    from models.database import open_db
    from backends.recent_backend import RecentPathsBackend
    import functools, unittest.mock

    with unittest.mock.patch("backends.recent_backend.open_db",
                             functools.partial(open_db, db)):
        b = RecentPathsBackend()
        b.record_location("/home/user/docs")
        b.record_file("/home/user/docs")
        locs = b.list_locations()
        files = b.list_files()

    assert "/home/user/docs" in locs
    assert "/home/user/docs" in files
