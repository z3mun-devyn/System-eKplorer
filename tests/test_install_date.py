"""Tests for apt and flatpak install-date derivation helpers."""
from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path

import pytest

from backends.packages_backend import _apt_install_date
from backends.flatpak_backend import _flatpak_install_date


# ── apt install date ──────────────────────────────────────────────────────────

def test_apt_install_date_from_primary_file(tmp_path):
    (tmp_path / "bash.list").touch()
    dt = _apt_install_date("bash", info_dir=tmp_path)
    assert dt is not None
    assert isinstance(dt, datetime)


def test_apt_install_date_none_on_missing(tmp_path):
    dt = _apt_install_date("no-such-pkg", info_dir=tmp_path)
    assert dt is None


def test_apt_install_date_multiarch_fallback_amd64(tmp_path):
    (tmp_path / "libfoo:amd64.list").touch()
    dt = _apt_install_date("libfoo", info_dir=tmp_path)
    assert dt is not None


def test_apt_install_date_multiarch_fallback_arm64(tmp_path):
    (tmp_path / "libbar:arm64.list").touch()
    dt = _apt_install_date("libbar", info_dir=tmp_path)
    assert dt is not None


def test_apt_install_date_primary_takes_priority_over_arch(tmp_path):
    primary = tmp_path / "vim.list"
    primary.touch()
    # Set a known mtime on the primary file
    t0 = 1_700_000_000
    import os
    os.utime(primary, (t0, t0))
    (tmp_path / "vim:amd64.list").touch()
    dt = _apt_install_date("vim", info_dir=tmp_path)
    assert dt is not None
    assert int(dt.timestamp()) == t0


def test_apt_install_date_reflects_file_mtime(tmp_path):
    f = tmp_path / "curl.list"
    f.touch()
    import os
    expected_ts = 1_600_000_000
    os.utime(f, (expected_ts, expected_ts))
    dt = _apt_install_date("curl", info_dir=tmp_path)
    assert dt is not None
    assert int(dt.timestamp()) == expected_ts


# ── flatpak install date ──────────────────────────────────────────────────────

def test_flatpak_install_date_from_deploy_dir(tmp_path):
    active = tmp_path / "org.test.App" / "current" / "active"
    active.mkdir(parents=True)
    dt = _flatpak_install_date("org.test.App", search_dirs=[tmp_path])
    assert dt is not None
    assert isinstance(dt, datetime)


def test_flatpak_install_date_none_on_missing(tmp_path):
    dt = _flatpak_install_date("org.missing.App", search_dirs=[tmp_path])
    assert dt is None


def test_flatpak_install_date_reflects_dir_mtime(tmp_path):
    active = tmp_path / "org.test.App" / "current" / "active"
    active.mkdir(parents=True)
    import os
    expected_ts = 1_650_000_000
    os.utime(active, (expected_ts, expected_ts))
    dt = _flatpak_install_date("org.test.App", search_dirs=[tmp_path])
    assert dt is not None
    assert int(dt.timestamp()) == expected_ts


def test_flatpak_install_date_checks_multiple_search_dirs(tmp_path):
    dir_a = tmp_path / "system"
    dir_b = tmp_path / "user"
    dir_a.mkdir()
    dir_b.mkdir()
    # App only in dir_b
    active = dir_b / "org.user.App" / "current" / "active"
    active.mkdir(parents=True)
    dt = _flatpak_install_date("org.user.App", search_dirs=[dir_a, dir_b])
    assert dt is not None


# ── Sort role must be epoch int, not string ───────────────────────────────────

def test_install_date_sort_role_is_epoch_int(tmp_path):
    f = tmp_path / "bash.list"
    f.touch()
    import os
    ts = 1_700_000_000
    os.utime(f, (ts, ts))
    dt = _apt_install_date("bash", info_dir=tmp_path)
    assert dt is not None
    # epoch int, not a string — ensures numeric sort works correctly
    assert isinstance(int(dt.timestamp()), int)
    assert int(dt.timestamp()) == ts
