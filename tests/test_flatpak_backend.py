"""Unit tests for backends/flatpak_backend.py.

All subprocess calls are monkeypatched — no real flatpak runs.
"""

import subprocess
from types import SimpleNamespace

import pytest

from backends.flatpak_backend import FlatpakBackend, _parse_line, _parse_size_kb


# ── Size parsing ──────────────────────────────────────────────────────────────

def test_parse_size_kb_megabytes():
    assert _parse_size_kb("293.0 MB") == 293 * 1024


def test_parse_size_kb_gigabytes():
    assert _parse_size_kb("1.0 GB") == 1024 * 1024


def test_parse_size_kb_kilobytes():
    assert _parse_size_kb("512.0 kB") == 512


def test_parse_size_kb_lowercase_mb():
    assert _parse_size_kb("11.1 MB") == int(11.1 * 1024)


def test_parse_size_kb_bad_string_returns_zero():
    assert _parse_size_kb("unknown") == 0


def test_parse_size_kb_empty_returns_zero():
    assert _parse_size_kb("") == 0


# ── Line parsing ──────────────────────────────────────────────────────────────

_SAMPLE_LINE = "org.mozilla.firefox\tFirefox\t120.0\t293.0 MB"


def test_parse_line_returns_package():
    pkg = _parse_line(_SAMPLE_LINE)
    assert pkg is not None


def test_parse_line_name_is_app_id():
    pkg = _parse_line(_SAMPLE_LINE)
    assert pkg.name == "org.mozilla.firefox"


def test_parse_line_display_name_is_friendly():
    pkg = _parse_line(_SAMPLE_LINE)
    assert pkg.display_name == "Firefox"


def test_parse_line_version():
    pkg = _parse_line(_SAMPLE_LINE)
    assert pkg.version == "120.0"


def test_parse_line_size_parsed():
    pkg = _parse_line(_SAMPLE_LINE)
    assert pkg.installed_size_kb == int(293.0 * 1024)


def test_parse_line_source_is_flatpak():
    pkg = _parse_line(_SAMPLE_LINE)
    assert pkg.source == "flatpak"


def test_parse_line_section_is_empty():
    pkg = _parse_line(_SAMPLE_LINE)
    assert pkg.section == ""


def test_parse_line_too_few_fields_returns_none():
    assert _parse_line("org.gnome.Calendar\tGNOME Calendar") is None


def test_parse_line_empty_app_id_returns_none():
    assert _parse_line("\tFriendly\t1.0\t10.0 MB") is None


def test_parse_line_empty_string_returns_none():
    assert _parse_line("") is None


# ── Backend list_installed ────────────────────────────────────────────────────

def _make_result(returncode, stdout="", stderr=""):
    return SimpleNamespace(returncode=returncode, stdout=stdout, stderr=stderr)


SAMPLE_OUTPUT = (
    "org.mozilla.firefox\tFirefox\t120.0\t293.0 MB\n"
    "org.gnome.Calendar\tGNOME Calendar\t43.1\t11.1 MB\n"
)


def test_list_installed_parses_multiple(monkeypatch):
    monkeypatch.setattr(
        "backends.flatpak_backend.subprocess.run",
        lambda *a, **kw: _make_result(0, SAMPLE_OUTPUT),
    )
    monkeypatch.setattr("backends.flatpak_backend.shutil.which",
                        lambda _: "/usr/bin/flatpak")
    pkgs = FlatpakBackend().list_installed()
    assert len(pkgs) == 2


def test_list_installed_names_correct(monkeypatch):
    monkeypatch.setattr(
        "backends.flatpak_backend.subprocess.run",
        lambda *a, **kw: _make_result(0, SAMPLE_OUTPUT),
    )
    monkeypatch.setattr("backends.flatpak_backend.shutil.which",
                        lambda _: "/usr/bin/flatpak")
    pkgs = FlatpakBackend().list_installed()
    names = {p.name for p in pkgs}
    assert "org.mozilla.firefox" in names
    assert "org.gnome.Calendar" in names


def test_list_installed_empty_output(monkeypatch):
    monkeypatch.setattr(
        "backends.flatpak_backend.subprocess.run",
        lambda *a, **kw: _make_result(0, ""),
    )
    monkeypatch.setattr("backends.flatpak_backend.shutil.which",
                        lambda _: "/usr/bin/flatpak")
    assert FlatpakBackend().list_installed() == []


def test_list_installed_not_available_returns_empty(monkeypatch):
    monkeypatch.setattr("backends.flatpak_backend.shutil.which",
                        lambda _: None)
    assert FlatpakBackend().list_installed() == []


def test_list_installed_file_not_found_returns_empty(monkeypatch):
    monkeypatch.setattr("backends.flatpak_backend.shutil.which",
                        lambda _: "/usr/bin/flatpak")

    def _raise(*a, **kw):
        raise FileNotFoundError("flatpak: no such file")

    monkeypatch.setattr("backends.flatpak_backend.subprocess.run", _raise)
    assert FlatpakBackend().list_installed() == []


def test_list_installed_timeout_returns_empty(monkeypatch):
    monkeypatch.setattr("backends.flatpak_backend.shutil.which",
                        lambda _: "/usr/bin/flatpak")

    def _raise(*a, **kw):
        raise subprocess.TimeoutExpired(cmd="flatpak", timeout=30)

    monkeypatch.setattr("backends.flatpak_backend.subprocess.run", _raise)
    assert FlatpakBackend().list_installed() == []


def test_list_installed_skips_blank_lines(monkeypatch):
    output = "\n" + SAMPLE_OUTPUT + "\n"
    monkeypatch.setattr(
        "backends.flatpak_backend.subprocess.run",
        lambda *a, **kw: _make_result(0, output),
    )
    monkeypatch.setattr("backends.flatpak_backend.shutil.which",
                        lambda _: "/usr/bin/flatpak")
    assert len(FlatpakBackend().list_installed()) == 2


def test_is_available_true_when_which_finds_flatpak(monkeypatch):
    monkeypatch.setattr("backends.flatpak_backend.shutil.which",
                        lambda _: "/usr/bin/flatpak")
    assert FlatpakBackend.is_available() is True


def test_is_available_false_when_which_returns_none(monkeypatch):
    monkeypatch.setattr("backends.flatpak_backend.shutil.which",
                        lambda _: None)
    assert FlatpakBackend.is_available() is False
