"""Tests for ClipboardBackend (schema v6 clipboard_history table)."""

import pytest

from backends.clipboard_backend import ClipboardBackend


# ── Schema ────────────────────────────────────────────────────────────────────

def test_table_exists(tmp_path):
    from models.database import open_db
    with open_db(tmp_path / "data.db") as conn:
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
            " AND name='clipboard_history'"
        ).fetchone()
    assert row is not None


def test_schema_version_is_6(tmp_path):
    from models.database import open_db, CURRENT_VERSION
    with open_db(tmp_path / "data.db") as conn:
        uv = conn.execute("PRAGMA user_version").fetchone()[0]
    assert uv == CURRENT_VERSION == 6


# ── add_entry / list_entries ──────────────────────────────────────────────────

def test_add_and_list_round_trip(tmp_path):
    b = ClipboardBackend(tmp_path / "data.db")
    b.add_entry("hello")
    entries = b.list_entries()
    assert len(entries) == 1
    assert entries[0].content == "hello"
    assert not entries[0].pinned


def test_list_entries_newest_first_within_unpinned(tmp_path):
    b = ClipboardBackend(tmp_path / "data.db")
    b.add_entry("first")
    b.add_entry("second")
    b.add_entry("third")
    entries = b.list_entries()
    # unpinned group ordered by id DESC → third, second, first
    assert [e.content for e in entries] == ["third", "second", "first"]


def test_add_entry_respects_max_entries_limit(tmp_path):
    b = ClipboardBackend(tmp_path / "data.db")
    b.max_entries = 3
    for i in range(5):
        b.add_entry(f"entry {i}")
    entries = b.list_entries()
    assert len(entries) == 3
    # newest three survive
    assert {e.content for e in entries} == {"entry 4", "entry 3", "entry 2"}


def test_add_entry_evicts_oldest_not_newest(tmp_path):
    b = ClipboardBackend(tmp_path / "data.db")
    b.max_entries = 2
    b.add_entry("old")
    b.add_entry("newer")
    b.add_entry("newest")
    contents = {e.content for e in b.list_entries()}
    assert "old" not in contents
    assert "newer" in contents
    assert "newest" in contents


# ── Pinned entries survive eviction ──────────────────────────────────────────

def test_pinned_entries_survive_eviction(tmp_path):
    b = ClipboardBackend(tmp_path / "data.db")
    b.max_entries = 2

    b.add_entry("pinned one")
    pinned_id = b.list_entries()[0].id
    b.toggle_pin(pinned_id)

    b.add_entry("unpinned A")
    b.add_entry("unpinned B")
    b.add_entry("unpinned C")  # should evict unpinned A

    entries = b.list_entries()
    contents = {e.content for e in entries}
    assert "pinned one" in contents
    assert "unpinned A" not in contents


def test_pinned_count_does_not_reduce_unpinned_capacity(tmp_path):
    """Pinned rows don't consume slots in the unpinned limit."""
    b = ClipboardBackend(tmp_path / "data.db")
    b.max_entries = 2

    b.add_entry("pin me")
    b.toggle_pin(b.list_entries()[0].id)

    b.add_entry("u1")
    b.add_entry("u2")
    entries = b.list_entries()
    unpinned = [e for e in entries if not e.pinned]
    assert len(unpinned) == 2


# ── delete_entry ──────────────────────────────────────────────────────────────

def test_delete_entry_removes_row(tmp_path):
    b = ClipboardBackend(tmp_path / "data.db")
    b.add_entry("to delete")
    eid = b.list_entries()[0].id
    b.delete_entry(eid)
    assert b.list_entries() == []


def test_delete_nonexistent_is_noop(tmp_path):
    b = ClipboardBackend(tmp_path / "data.db")
    b.delete_entry(9999)  # should not raise


# ── toggle_pin ────────────────────────────────────────────────────────────────

def test_toggle_pin_flips_from_false_to_true(tmp_path):
    b = ClipboardBackend(tmp_path / "data.db")
    b.add_entry("text")
    eid = b.list_entries()[0].id
    b.toggle_pin(eid)
    assert b.list_entries()[0].pinned is True


def test_toggle_pin_flips_from_true_to_false(tmp_path):
    b = ClipboardBackend(tmp_path / "data.db")
    b.add_entry("text")
    eid = b.list_entries()[0].id
    b.toggle_pin(eid)
    b.toggle_pin(eid)
    assert b.list_entries()[0].pinned is False


def test_toggle_pin_twice_restores_original_state(tmp_path):
    b = ClipboardBackend(tmp_path / "data.db")
    b.add_entry("text")
    eid = b.list_entries()[0].id
    original = b.list_entries()[0].pinned
    b.toggle_pin(eid)
    b.toggle_pin(eid)
    assert b.list_entries()[0].pinned == original


# ── clear_unpinned ────────────────────────────────────────────────────────────

def test_clear_unpinned_removes_all_unpinned(tmp_path):
    b = ClipboardBackend(tmp_path / "data.db")
    b.add_entry("a")
    b.add_entry("b")
    b.clear_unpinned()
    assert b.list_entries() == []


def test_clear_unpinned_leaves_pinned_intact(tmp_path):
    b = ClipboardBackend(tmp_path / "data.db")
    b.add_entry("keep me")
    b.toggle_pin(b.list_entries()[0].id)
    b.add_entry("delete me")
    b.clear_unpinned()
    entries = b.list_entries()
    assert len(entries) == 1
    assert entries[0].content == "keep me"
    assert entries[0].pinned is True


def test_clear_unpinned_multiple_pinned_all_survive(tmp_path):
    b = ClipboardBackend(tmp_path / "data.db")
    b.add_entry("pin1")
    b.add_entry("pin2")
    b.add_entry("unpinned")
    for e in b.list_entries():
        if e.pinned is False and e.content != "unpinned":
            b.toggle_pin(e.id)
    # pin both pin1 and pin2
    for e in b.list_entries():
        if e.content in {"pin1", "pin2"}:
            b.toggle_pin(e.id)
    b.clear_unpinned()
    remaining = {e.content for e in b.list_entries()}
    assert "unpinned" not in remaining


# ── max_entries setting ───────────────────────────────────────────────────────

def test_max_entries_default_is_10(tmp_path):
    b = ClipboardBackend(tmp_path / "data.db")
    assert b.max_entries == 10


def test_max_entries_persists_across_instances(tmp_path):
    db = tmp_path / "data.db"
    b1 = ClipboardBackend(db)
    b1.max_entries = 25
    b2 = ClipboardBackend(db)
    assert b2.max_entries == 25


def test_max_entries_minimum_is_1(tmp_path):
    b = ClipboardBackend(tmp_path / "data.db")
    b.max_entries = 0
    assert b.max_entries == 1


# ── list_entries ordering: pinned float to top ────────────────────────────────

def test_pinned_entries_appear_before_unpinned(tmp_path):
    b = ClipboardBackend(tmp_path / "data.db")
    b.add_entry("unpinned first")
    b.add_entry("to pin")
    b.toggle_pin(b.list_entries()[0].id)  # pin "to pin" (newest)
    entries = b.list_entries()
    assert entries[0].content == "to pin"
    assert entries[0].pinned is True
    assert entries[1].content == "unpinned first"
    assert entries[1].pinned is False


# ── enforce_limit ─────────────────────────────────────────────────────────────

def test_enforce_limit_trims_to_new_max(tmp_path):
    b = ClipboardBackend(tmp_path / "data.db")
    b.max_entries = 5
    for i in range(5):
        b.add_entry(f"e{i}")
    b.max_entries = 2
    b.enforce_limit()
    assert len(b.list_entries()) == 2


def test_enforce_limit_preserves_pinned(tmp_path):
    b = ClipboardBackend(tmp_path / "data.db")
    b.max_entries = 5
    b.add_entry("pin me")
    b.toggle_pin(b.list_entries()[0].id)
    for i in range(4):
        b.add_entry(f"u{i}")
    b.max_entries = 1
    b.enforce_limit()
    contents = {e.content for e in b.list_entries()}
    assert "pin me" in contents
