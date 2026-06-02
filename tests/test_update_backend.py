"""Tests for backends/update_backend.py.

All subprocess calls are monkeypatched — no real apt or flatpak runs.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from backends.update_backend import (
    UpdateBackend,
    _parse_apt_upgradable,
    _parse_flatpak_updates,
)


# ── _parse_apt_upgradable (pure) ──────────────────────────────────────────────

def test_parse_apt_upgradable_basic():
    output = (
        "Listing... Done\n"
        "vim/jammy-updates 2:9.0.0749-5ubuntu2 amd64 [upgradable from: 2:9.0.0749-5ubuntu1]\n"
        "curl/jammy-updates 7.81.0-1ubuntu1.15 amd64 [upgradable from: 7.81.0-1ubuntu1.14]\n"
    )
    results = _parse_apt_upgradable(output)
    assert ("vim", "2:9.0.0749-5ubuntu2") in results
    assert ("curl", "7.81.0-1ubuntu1.15") in results


def test_parse_apt_upgradable_listing_header_skipped():
    output = "Listing... Done\nvim/repo 9.1 amd64 [upgradable from: 9.0]\n"
    results = _parse_apt_upgradable(output)
    assert len(results) == 1
    assert results[0][0] == "vim"


def test_parse_apt_upgradable_empty_output():
    assert _parse_apt_upgradable("") == []
    assert _parse_apt_upgradable("Listing... Done\n") == []


def test_parse_apt_upgradable_strips_repo_suffix():
    # Name comes as "name/repo" — only the name part should be returned
    output = "vim/jammy-updates 9.1 amd64\n"
    results = _parse_apt_upgradable(output)
    assert results[0][0] == "vim"
    assert "/" not in results[0][0]


def test_parse_apt_upgradable_multiple_packages():
    output = (
        "Listing...\n"
        "a/repo 1.0 amd64\n"
        "b/repo 2.0 amd64\n"
        "c/repo 3.0 amd64\n"
    )
    results = _parse_apt_upgradable(output)
    names = [r[0] for r in results]
    assert names == ["a", "b", "c"]


# ── _parse_flatpak_updates (pure) ─────────────────────────────────────────────

def test_parse_flatpak_updates_basic():
    output = (
        "org.mozilla.firefox\t128.0\n"
        "org.gnome.Calendar\t45.1\n"
    )
    results = _parse_flatpak_updates(output)
    assert ("org.mozilla.firefox", "128.0") in results
    assert ("org.gnome.Calendar", "45.1") in results


def test_parse_flatpak_updates_empty_output():
    assert _parse_flatpak_updates("") == []


def test_parse_flatpak_updates_skips_blank_lines():
    output = "\norg.test.App\t1.0\n\n"
    results = _parse_flatpak_updates(output)
    assert len(results) == 1
    assert results[0] == ("org.test.App", "1.0")


def test_parse_flatpak_updates_skips_short_lines():
    # Lines with only one token (no version) are ignored
    output = "org.incomplete\norg.test.App 2.0\n"
    results = _parse_flatpak_updates(output)
    assert len(results) == 1
    assert results[0][0] == "org.test.App"


# ── UpdateBackend.run_apt_update (mocked Popen) ───────────────────────────────

class _FakePopen:
    def __init__(self, returncode=0, stdout_lines=None):
        self.returncode = returncode
        self.stdout = iter(stdout_lines or [])
    def __enter__(self): return self
    def __exit__(self, *args): pass


def test_run_apt_update_returns_true_on_success(monkeypatch):
    monkeypatch.setattr(
        "backends.update_backend.subprocess.Popen",
        lambda *a, **kw: _FakePopen(0),
    )
    assert UpdateBackend().run_apt_update() is True


def test_run_apt_update_returns_false_on_failure(monkeypatch):
    monkeypatch.setattr(
        "backends.update_backend.subprocess.Popen",
        lambda *a, **kw: _FakePopen(1),
    )
    assert UpdateBackend().run_apt_update() is False


def test_run_apt_update_returns_false_on_pkexec_denied(monkeypatch):
    # pkexec exit 126 = auth denied
    monkeypatch.setattr(
        "backends.update_backend.subprocess.Popen",
        lambda *a, **kw: _FakePopen(126),
    )
    assert UpdateBackend().run_apt_update() is False


def test_run_apt_update_returns_false_on_exception(monkeypatch):
    monkeypatch.setattr(
        "backends.update_backend.subprocess.Popen",
        lambda *a, **kw: (_ for _ in ()).throw(FileNotFoundError()),
    )
    assert UpdateBackend().run_apt_update() is False


def test_run_apt_update_calls_line_cb(monkeypatch):
    lines = ["Hit:1 http://...\n", "Fetched 12 kB\n"]
    monkeypatch.setattr(
        "backends.update_backend.subprocess.Popen",
        lambda *a, **kw: _FakePopen(0, lines),
    )
    collected: list[str] = []
    UpdateBackend().run_apt_update(line_cb=collected.append)
    assert collected == ["Hit:1 http://...", "Fetched 12 kB"]


def test_run_apt_update_uses_pkexec_apt_update(monkeypatch):
    captured: dict = {}
    def _capture(cmd, **kw):
        captured["cmd"] = cmd
        return _FakePopen(0)
    monkeypatch.setattr("backends.update_backend.subprocess.Popen", _capture)
    UpdateBackend().run_apt_update()
    assert "pkexec" in captured["cmd"]
    assert "apt" in captured["cmd"]
    assert "update" in captured["cmd"]


# ── UpdateBackend.list_apt_upgradable (mocked subprocess) ────────────────────

def _fake_run(stdout="", returncode=0):
    def _run(*args, **kwargs):
        return SimpleNamespace(stdout=stdout, returncode=returncode)
    return _run


def test_list_apt_upgradable_returns_pairs(monkeypatch):
    output = "Listing...\nvim/repo 9.1 amd64\n"
    monkeypatch.setattr("backends.update_backend.subprocess.run", _fake_run(output))
    results = UpdateBackend().list_apt_upgradable()
    assert results == [("vim", "9.1")]


def test_list_apt_upgradable_returns_empty_on_exception(monkeypatch):
    def _raise(*a, **kw):
        raise FileNotFoundError("apt not found")
    monkeypatch.setattr("backends.update_backend.subprocess.run", _raise)
    assert UpdateBackend().list_apt_upgradable() == []


# ── UpdateBackend.list_flatpak_updates (mocked subprocess) ───────────────────

def test_list_flatpak_updates_returns_pairs(monkeypatch):
    output = "org.mozilla.firefox\t128.0\n"
    monkeypatch.setattr("backends.update_backend.subprocess.run", _fake_run(output))
    results = UpdateBackend().list_flatpak_updates()
    assert results == [("org.mozilla.firefox", "128.0")]


def test_list_flatpak_updates_returns_empty_on_exception(monkeypatch):
    def _raise(*a, **kw):
        raise FileNotFoundError("flatpak not found")
    monkeypatch.setattr("backends.update_backend.subprocess.run", _raise)
    assert UpdateBackend().list_flatpak_updates() == []


# ── Upgradable flag correctly set per package ─────────────────────────────────

def test_upgradable_flag_per_package():
    apt_output = "Listing...\nvim/repo 9.1 amd64\n"
    results = _parse_apt_upgradable(apt_output)
    result_map = dict(results)
    # vim has an update
    assert "vim" in result_map
    assert result_map["vim"] == "9.1"
    # nano does not
    assert "nano" not in result_map


def test_upgradable_version_matches_new_version():
    output = "Listing...\nvim/repo 2:9.0.0749-5ubuntu2 amd64 [upgradable from: 2:9.0.0]\n"
    results = _parse_apt_upgradable(output)
    assert results[0] == ("vim", "2:9.0.0749-5ubuntu2")
