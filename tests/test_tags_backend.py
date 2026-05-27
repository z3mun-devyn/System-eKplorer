"""M4 schema migration (3 starting states) and TagRepository CRUD tests."""

import sqlite3

import pytest

from backends.tags_backend import TagRepository
from models.database import CURRENT_VERSION, open_db


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_v1_db(path) -> None:
    """Reproduce a v1 DB as M2 would have created it (schema_version table, no PRAGMA)."""
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE schema_version (version INTEGER NOT NULL)")
    conn.execute("INSERT INTO schema_version VALUES (1)")
    conn.execute(
        "CREATE TABLE drive_labels"
        " (device_id TEXT PRIMARY KEY, label TEXT NOT NULL,"
        "  color_hex TEXT, updated_at TEXT NOT NULL)"
    )
    conn.execute(
        "INSERT INTO drive_labels"
        " VALUES ('disk-0', 'Main', '#3498db', '2026-01-01T00:00:00+00:00')"
    )
    conn.commit()
    conn.close()


# ── Starting state 1: Fresh DB ────────────────────────────────────────────────

def test_fresh_db_user_version(tmp_path):
    db = tmp_path / "data.db"
    with open_db(db) as conn:
        uv = conn.execute("PRAGMA user_version").fetchone()[0]
    assert uv == CURRENT_VERSION == 2


def test_fresh_db_has_drive_labels(tmp_path):
    db = tmp_path / "data.db"
    with open_db(db) as conn:
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='drive_labels'"
        ).fetchone()
    assert row is not None


def test_fresh_db_has_tags(tmp_path):
    db = tmp_path / "data.db"
    with open_db(db) as conn:
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='tags'"
        ).fetchone()
    assert row is not None


def test_fresh_db_has_package_tags(tmp_path):
    db = tmp_path / "data.db"
    with open_db(db) as conn:
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='package_tags'"
        ).fetchone()
    assert row is not None


def test_fresh_db_has_idx_pkg_tags(tmp_path):
    db = tmp_path / "data.db"
    with open_db(db) as conn:
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_pkg_tags'"
        ).fetchone()
    assert row is not None


def test_fresh_db_tags_uses_name_as_pk(tmp_path):
    """Confirm tags PK is the name column, not an integer id."""
    db = tmp_path / "data.db"
    with open_db(db) as conn:
        info = conn.execute("PRAGMA table_info(tags)").fetchall()
    cols = {row["name"]: row for row in info}
    assert "name" in cols
    assert cols["name"]["pk"] == 1
    assert "id" not in cols


# ── Starting state 2: v1 DB from M2 ──────────────────────────────────────────

def test_v1_migrates_user_version_to_2(tmp_path):
    db = tmp_path / "data.db"
    _make_v1_db(db)
    with open_db(db) as conn:
        uv = conn.execute("PRAGMA user_version").fetchone()[0]
    assert uv == 2


def test_v1_drive_label_survives_migration(tmp_path):
    db = tmp_path / "data.db"
    _make_v1_db(db)
    with open_db(db) as conn:
        row = conn.execute(
            "SELECT label FROM drive_labels WHERE device_id = 'disk-0'"
        ).fetchone()
    assert row["label"] == "Main"


def test_v1_tags_table_added_by_migration(tmp_path):
    db = tmp_path / "data.db"
    _make_v1_db(db)
    with open_db(db) as conn:
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='tags'"
        ).fetchone()
    assert row is not None


def test_v1_package_tags_added_by_migration(tmp_path):
    db = tmp_path / "data.db"
    _make_v1_db(db)
    with open_db(db) as conn:
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='package_tags'"
        ).fetchone()
    assert row is not None


def test_v1_legacy_schema_version_table_preserved(tmp_path):
    """Legacy schema_version table is left intact — we do not drop it."""
    db = tmp_path / "data.db"
    _make_v1_db(db)
    with open_db(db) as conn:
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='schema_version'"
        ).fetchone()
    assert row is not None


# ── Starting state 3: v2 DB re-open is a no-op ───────────────────────────────

def test_v2_reopen_does_not_change_user_version(tmp_path):
    db = tmp_path / "data.db"
    with open_db(db):
        pass
    with open_db(db) as conn:
        uv = conn.execute("PRAGMA user_version").fetchone()[0]
    assert uv == 2


def test_v2_reopen_does_not_lose_data(tmp_path):
    db = tmp_path / "data.db"
    repo = TagRepository(db)
    repo.create_tag("Persistent", "#e74c3c")
    with open_db(db):
        pass  # re-open
    assert len(repo.all_tags()) == 1
    assert repo.all_tags()[0].name == "Persistent"


def test_v2_reopen_does_not_duplicate_tables(tmp_path):
    db = tmp_path / "data.db"
    with open_db(db):
        pass
    with open_db(db) as conn:
        count = conn.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='tags'"
        ).fetchone()[0]
    assert count == 1


# ── TagRepository: create_tag ─────────────────────────────────────────────────

def test_create_tag_persists(tmp_path):
    repo = TagRepository(tmp_path / "data.db")
    repo.create_tag("Gaming", "#e74c3c")
    tags = repo.all_tags()
    assert len(tags) == 1
    assert tags[0].name == "Gaming"
    assert tags[0].color_hex == "#e74c3c"


def test_all_tags_sorted_by_name(tmp_path):
    repo = TagRepository(tmp_path / "data.db")
    repo.create_tag("Zebra", "#e74c3c")
    repo.create_tag("Alpha", "#3498db")
    repo.create_tag("Mango", "#f1c40f")
    names = [t.name for t in repo.all_tags()]
    assert names == sorted(names)


def test_create_tag_duplicate_name_raises(tmp_path):
    repo = TagRepository(tmp_path / "data.db")
    repo.create_tag("Dup", "#e74c3c")
    with pytest.raises(Exception):
        repo.create_tag("Dup", "#3498db")


# ── TagRepository: set_assignments ───────────────────────────────────────────

def test_assign_tag_to_package(tmp_path):
    repo = TagRepository(tmp_path / "data.db")
    repo.create_tag("Work", "#3498db")
    repo.set_assignments("apt", "vim", {"Work"})
    tags = repo.tags_for_package("apt", "vim")
    assert len(tags) == 1
    assert tags[0].name == "Work"


def test_unassign_tag_from_package(tmp_path):
    repo = TagRepository(tmp_path / "data.db")
    repo.create_tag("A", "#e74c3c")
    repo.create_tag("B", "#3498db")
    repo.set_assignments("apt", "vim", {"A", "B"})
    repo.set_assignments("apt", "vim", {"A"})
    tags = repo.tags_for_package("apt", "vim")
    assert len(tags) == 1
    assert tags[0].name == "A"


def test_set_assignments_empty_clears_all(tmp_path):
    repo = TagRepository(tmp_path / "data.db")
    repo.create_tag("Work", "#3498db")
    repo.set_assignments("apt", "bash", {"Work"})
    repo.set_assignments("apt", "bash", set())
    assert repo.tags_for_package("apt", "bash") == []


def test_assignments_for_different_packages_are_independent(tmp_path):
    repo = TagRepository(tmp_path / "data.db")
    repo.create_tag("Work", "#3498db")
    repo.set_assignments("apt", "vim", {"Work"})
    repo.set_assignments("apt", "emacs", set())
    assert repo.tags_for_package("apt", "vim") != []
    assert repo.tags_for_package("apt", "emacs") == []


# ── TagRepository: tag_counts ─────────────────────────────────────────────────

def test_tag_counts_empty_when_no_assignments(tmp_path):
    repo = TagRepository(tmp_path / "data.db")
    repo.create_tag("Unused", "#e74c3c")
    assert repo.tag_counts() == {}


def test_tag_counts_correct(tmp_path):
    repo = TagRepository(tmp_path / "data.db")
    repo.create_tag("A", "#e74c3c")
    repo.create_tag("B", "#3498db")
    repo.set_assignments("apt", "vim",  {"A", "B"})
    repo.set_assignments("apt", "bash", {"A"})
    counts = repo.tag_counts()
    assert counts["A"] == 2
    assert counts["B"] == 1


# ── TagRepository: load_all_assignments ──────────────────────────────────────

def test_load_all_assignments_empty(tmp_path):
    repo = TagRepository(tmp_path / "data.db")
    assert repo.load_all_assignments() == {}


def test_load_all_assignments_bulk(tmp_path):
    repo = TagRepository(tmp_path / "data.db")
    repo.create_tag("Work",   "#3498db")
    repo.create_tag("Gaming", "#e74c3c")
    repo.set_assignments("apt", "vim",  {"Work"})
    repo.set_assignments("apt", "bash", {"Work", "Gaming"})

    result = repo.load_all_assignments()
    vim_names  = {t.name for t in result.get(("apt", "vim"),  [])}
    bash_names = {t.name for t in result.get(("apt", "bash"), [])}

    assert vim_names  == {"Work"}
    assert bash_names == {"Work", "Gaming"}


# ── Foreign key cascade ───────────────────────────────────────────────────────

def test_deleting_tag_cascades_to_package_tags(tmp_path):
    db = tmp_path / "data.db"
    repo = TagRepository(db)
    repo.create_tag("Temp", "#e74c3c")
    repo.set_assignments("apt", "vim", {"Temp"})

    with open_db(db) as conn:
        conn.execute("DELETE FROM tags WHERE name = 'Temp'")

    with open_db(db) as conn:
        rows = conn.execute(
            "SELECT * FROM package_tags WHERE tag_name = 'Temp'"
        ).fetchall()
    assert rows == []
