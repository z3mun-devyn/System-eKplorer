"""M9 version backend tests — all pure parsing, no subprocess calls."""
from __future__ import annotations

import pytest
from backends.version_backend import (
    _is_in_hold_list,
    _is_in_mask_list,
    _parse_apt_policy,
    _parse_flatpak_log,
)


# ── apt-cache policy parsing ──────────────────────────────────────────────────

_POLICY_VIM = """\
vim:
  Installed: 2:9.0.1672-1ubuntu4
  Candidate: 2:9.0.1672-1ubuntu4
  Version table:
 *** 2:9.0.1672-1ubuntu4 500
        500 http://archive.ubuntu.com/ubuntu noble-updates/main amd64 Packages
        100 /var/lib/dpkg/status
     2:9.0.1100-1ubuntu4 500
        500 http://archive.ubuntu.com/ubuntu noble/main amd64 Packages
"""

_POLICY_NOT_INSTALLED = """\
curl:
  Installed: (none)
  Candidate: 7.88.1-10+deb12u5
  Version table:
     7.88.1-10+deb12u5 500
        500 http://archive.ubuntu.com/ubuntu noble/main amd64 Packages
"""

_POLICY_HISTORICAL_ONLY = """\
oldpkg:
  Installed: 1.0
  Candidate: 1.0
  Version table:
 *** 1.0 100
        100 /var/lib/dpkg/status
"""


def test_parse_apt_policy_installed_version():
    entries = _parse_apt_policy(_POLICY_VIM)
    installed = [e for e in entries if e.is_installed]
    assert len(installed) == 1
    assert installed[0].version == "2:9.0.1672-1ubuntu4"


def test_parse_apt_policy_all_versions():
    entries = _parse_apt_policy(_POLICY_VIM)
    versions = [e.version for e in entries]
    assert "2:9.0.1672-1ubuntu4" in versions
    assert "2:9.0.1100-1ubuntu4" in versions


def test_parse_apt_policy_obtainability():
    entries = _parse_apt_policy(_POLICY_VIM)
    by_ver = {e.version: e for e in entries}
    assert by_ver["2:9.0.1672-1ubuntu4"].is_obtainable
    assert by_ver["2:9.0.1100-1ubuntu4"].is_obtainable


def test_parse_apt_policy_none_installed():
    entries = _parse_apt_policy(_POLICY_NOT_INSTALLED)
    assert not any(e.is_installed for e in entries)
    assert all(e.is_obtainable for e in entries)


def test_parse_apt_policy_dpkg_status_only_not_obtainable():
    entries = _parse_apt_policy(_POLICY_HISTORICAL_ONLY)
    assert len(entries) == 1
    assert entries[0].is_installed
    assert not entries[0].is_obtainable


def test_parse_apt_policy_empty():
    assert _parse_apt_policy("") == []


# ── Hold list detection ───────────────────────────────────────────────────────

def test_is_in_hold_list_found():
    assert _is_in_hold_list("vim\ncurl\n", "vim")


def test_is_in_hold_list_not_found():
    assert not _is_in_hold_list("vim\ncurl\n", "nano")


def test_is_in_hold_list_empty():
    assert not _is_in_hold_list("", "vim")


def test_is_in_hold_list_partial_name_not_matched():
    # "vim" should not match "libvim"
    assert not _is_in_hold_list("libvim\n", "vim")


# ── flatpak remote-info --log parsing ────────────────────────────────────────

_FLATPAK_LOG = """\
Commit: abc123def456789012
Subject: Update to 1.2.3
Date: 2024-01-15 12:00:00 +0000

Commit: 999888777666555444
Subject: Initial release
Date: 2023-06-01 09:00:00 +0000

"""


def test_parse_flatpak_log_count():
    commits = _parse_flatpak_log(_FLATPAK_LOG, current_commit=None)
    assert len(commits) == 2


def test_parse_flatpak_log_commit_truncated():
    commits = _parse_flatpak_log(_FLATPAK_LOG, current_commit=None)
    # Commit hashes should be truncated to 12 chars
    assert commits[0].commit == "abc123def456"


def test_parse_flatpak_log_subject():
    commits = _parse_flatpak_log(_FLATPAK_LOG, current_commit=None)
    assert commits[0].subject == "Update to 1.2.3"
    assert commits[1].subject == "Initial release"


def test_parse_flatpak_log_date():
    commits = _parse_flatpak_log(_FLATPAK_LOG, current_commit=None)
    assert "2024-01-15" in commits[0].date


def test_parse_flatpak_log_current_marked():
    commits = _parse_flatpak_log(_FLATPAK_LOG, current_commit="abc123def456789012")
    assert commits[0].is_current
    assert not commits[1].is_current


def test_parse_flatpak_log_no_current():
    commits = _parse_flatpak_log(_FLATPAK_LOG, current_commit=None)
    assert not any(c.is_current for c in commits)


def test_parse_flatpak_log_empty():
    assert _parse_flatpak_log("", None) == []


# ── Flatpak mask list detection ───────────────────────────────────────────────

def test_is_in_mask_list_found():
    assert _is_in_mask_list("org.mozilla.firefox\norg.gnome.Calendar\n",
                             "org.mozilla.firefox")


def test_is_in_mask_list_not_found():
    assert not _is_in_mask_list("org.mozilla.firefox\n", "org.gnome.Calendar")


def test_is_in_mask_list_empty():
    assert not _is_in_mask_list("", "org.mozilla.firefox")
