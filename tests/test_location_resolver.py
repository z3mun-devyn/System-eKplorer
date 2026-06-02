"""Tests for package_location_resolver."""
from __future__ import annotations

import pytest

from package_location_resolver import _pick_apt_dir, _flatpak_location, resolve_location


# ── _pick_apt_dir (pure function — no subprocess) ─────────────────────────────

def test_apt_opt_style_returns_opt_subdir():
    files = ["/opt/myapp/bin/myapp", "/opt/myapp/lib/myapp.so"]
    assert _pick_apt_dir(files) == "/opt/myapp"


def test_apt_opt_style_first_match():
    files = ["/usr/share/doc/myapp/README", "/opt/myapp/myapp"]
    # /opt takes priority over /usr/share
    assert _pick_apt_dir(files) == "/opt/myapp"


def test_apt_usr_share_style():
    files = ["/usr/share/myapp/data.dat", "/usr/share/myapp/icons/icon.png",
             "/usr/bin/myapp"]
    assert _pick_apt_dir(files) == "/usr/share/myapp"


def test_apt_usr_share_doc_excluded():
    # /usr/share/doc is filtered out — don't return it as a meaningful dir
    files = ["/usr/share/doc/myapp/copyright", "/usr/bin/myapp"]
    result = _pick_apt_dir(files)
    assert result == "/usr/bin"


def test_apt_usr_share_man_excluded():
    files = ["/usr/share/man/man1/tool.1.gz", "/usr/bin/tool"]
    result = _pick_apt_dir(files)
    assert result == "/usr/bin"


def test_apt_executable_usr_bin():
    files = ["/usr/lib/myapp/myapp.so", "/usr/bin/myapp"]
    assert _pick_apt_dir(files) == "/usr/bin"


def test_apt_executable_usr_games():
    files = ["/usr/share/games/mygame/data", "/usr/games/mygame"]
    assert _pick_apt_dir(files) == "/usr/games"


def test_apt_scattered_returns_none():
    files = ["/usr/lib/myapp/myapp.so", "/etc/myapp/config"]
    assert _pick_apt_dir(files) is None


def test_apt_empty_list_returns_none():
    assert _pick_apt_dir([]) is None


# ── _flatpak_location (mocked subprocess) ────────────────────────────────────

def test_flatpak_location_returns_path(monkeypatch):
    class FakeResult:
        stdout = "/var/lib/flatpak/app/org.test.App/x86_64/stable/abc123\n"
        returncode = 0

    import subprocess
    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: FakeResult())
    result = _flatpak_location("org.test.App")
    assert result == "/var/lib/flatpak/app/org.test.App/x86_64/stable/abc123"


def test_flatpak_location_none_on_empty_output(monkeypatch):
    class FakeResult:
        stdout = "\n"
        returncode = 0

    import subprocess
    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: FakeResult())
    result = _flatpak_location("org.missing.App")
    assert result is None


def test_flatpak_location_none_on_exception(monkeypatch):
    import subprocess
    monkeypatch.setattr(
        subprocess, "run",
        lambda *a, **kw: (_ for _ in ()).throw(FileNotFoundError()),
    )
    result = _flatpak_location("org.test.App")
    assert result is None


# ── resolve_location dispatch ─────────────────────────────────────────────────

def test_resolve_location_routes_flatpak(monkeypatch):
    class FakeResult:
        stdout = "/some/flatpak/deploy\n"
        returncode = 0

    import subprocess
    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: FakeResult())
    result = resolve_location("org.test.App", "flatpak")
    assert result == "/some/flatpak/deploy"


def test_resolve_location_routes_apt(monkeypatch):
    class FakeResult:
        stdout = "/opt/myapp/bin/myapp\n"
        returncode = 0

    import subprocess
    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: FakeResult())
    result = resolve_location("myapp", "apt")
    assert result == "/opt/myapp"
