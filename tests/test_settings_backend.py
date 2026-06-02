"""Unit tests for SettingsRepository (schema v3 settings table)."""
import json

import pytest

from backends.settings_backend import SettingsRepository


def test_get_missing_returns_none(tmp_path):
    repo = SettingsRepository(tmp_path / "data.db")
    assert repo.get("nonexistent.key") is None


def test_set_and_get_round_trip(tmp_path):
    repo = SettingsRepository(tmp_path / "data.db")
    repo.set("my.key", "hello")
    assert repo.get("my.key") == "hello"


def test_set_overwrites_existing(tmp_path):
    repo = SettingsRepository(tmp_path / "data.db")
    repo.set("key", "first")
    repo.set("key", "second")
    assert repo.get("key") == "second"


def test_different_keys_are_independent(tmp_path):
    repo = SettingsRepository(tmp_path / "data.db")
    repo.set("a", "1")
    repo.set("b", "2")
    assert repo.get("a") == "1"
    assert repo.get("b") == "2"


def test_column_visibility_json_round_trip(tmp_path):
    repo = SettingsRepository(tmp_path / "data.db")
    vis = {"icon": True, "tags": False, "category": True,
           "source": True, "version": False, "size": True, "installed": True}
    repo.set("packages.column_visibility", json.dumps(vis))
    raw = repo.get("packages.column_visibility")
    assert raw is not None
    recovered = json.loads(raw)
    assert recovered == vis
    assert recovered["tags"] is False
    assert recovered["icon"] is True
