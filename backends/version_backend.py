"""Version history and hold/mask backend for M9."""
from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass


@dataclass
class AptVersionEntry:
    version: str
    is_installed: bool    # currently installed version
    is_obtainable: bool   # reachable via apt install pkg=ver


@dataclass
class FlatpakCommit:
    commit: str           # short commit hash
    subject: str          # one-line description
    date: str             # human-readable date string
    is_current: bool


class VersionBackend:
    TIMEOUT = 15

    # ── Apt version history ───────────────────────────────────────────────────

    def get_apt_versions(self, pkg_name: str) -> list[AptVersionEntry]:
        try:
            result = subprocess.run(
                ["apt-cache", "policy", pkg_name],
                capture_output=True, text=True, timeout=self.TIMEOUT,
            )
            return _parse_apt_policy(result.stdout)
        except Exception:
            return []

    def hold_apt(self, pkg_name: str) -> bool:
        try:
            r = subprocess.run(
                ["pkexec", "apt-mark", "hold", pkg_name],
                capture_output=True, timeout=self.TIMEOUT,
            )
            return r.returncode == 0
        except Exception:
            return False

    def unhold_apt(self, pkg_name: str) -> bool:
        try:
            r = subprocess.run(
                ["pkexec", "apt-mark", "unhold", pkg_name],
                capture_output=True, timeout=self.TIMEOUT,
            )
            return r.returncode == 0
        except Exception:
            return False

    def is_apt_held(self, pkg_name: str) -> bool:
        try:
            r = subprocess.run(
                ["apt-mark", "showhold"],
                capture_output=True, text=True, timeout=self.TIMEOUT,
            )
            return _is_in_hold_list(r.stdout, pkg_name)
        except Exception:
            return False

    # ── Flatpak commit history ────────────────────────────────────────────────

    def get_flatpak_history(self, app_id: str) -> list[FlatpakCommit]:
        try:
            result = subprocess.run(
                ["flatpak", "remote-info", "--log", app_id],
                capture_output=True, text=True, timeout=self.TIMEOUT,
            )
            current = _get_flatpak_current_commit(app_id)
            return _parse_flatpak_log(result.stdout, current)
        except Exception:
            return []

    def mask_flatpak(self, app_id: str) -> bool:
        try:
            r = subprocess.run(
                ["flatpak", "mask", app_id],
                capture_output=True, timeout=self.TIMEOUT,
            )
            return r.returncode == 0
        except Exception:
            return False

    def unmask_flatpak(self, app_id: str) -> bool:
        try:
            r = subprocess.run(
                ["flatpak", "mask", "--remove", app_id],
                capture_output=True, timeout=self.TIMEOUT,
            )
            return r.returncode == 0
        except Exception:
            return False

    def is_flatpak_masked(self, app_id: str) -> bool:
        try:
            r = subprocess.run(
                ["flatpak", "mask"],
                capture_output=True, text=True, timeout=self.TIMEOUT,
            )
            return _is_in_mask_list(r.stdout, app_id)
        except Exception:
            return False


# ── Pure parsing helpers ──────────────────────────────────────────────────────

def _parse_apt_policy(output: str) -> list[AptVersionEntry]:
    """Parse `apt-cache policy` output into AptVersionEntry list.

    Example output::

        vim:
          Installed: 2:9.0.1672-1ubuntu4
          Candidate: 2:9.0.1672-1ubuntu4
          Version table:
         *** 2:9.0.1672-1ubuntu4 500
                500 http://archive.ubuntu.com/... Packages
                100 /var/lib/dpkg/status
             2:9.0.1678-2 500
                500 http://archive.ubuntu.com/... Packages
    """
    installed_ver: str | None = None
    entries: list[AptVersionEntry] = []

    in_table = False
    current_ver: str | None = None
    current_obtainable = False

    for line in output.splitlines():
        stripped = line.strip()

        m = re.match(r"Installed:\s+(.+)", stripped)
        if m:
            v = m.group(1).strip()
            installed_ver = None if v == "(none)" else v
            continue

        if stripped == "Version table:":
            in_table = True
            continue

        if not in_table:
            continue

        # New version block — starts with optional *** and then version + priority
        m = re.match(r"\*?\*?\*?\s*(\S+)\s+\d+", stripped)
        if m and not stripped.startswith("500") and not stripped.startswith("100"):
            if current_ver is not None:
                entries.append(AptVersionEntry(
                    version=current_ver,
                    is_installed=(current_ver == installed_ver),
                    is_obtainable=current_obtainable,
                ))
            current_ver = m.group(1)
            current_obtainable = False
            continue

        # Source line within a version block
        if current_ver and re.match(r"\d+\s+", stripped):
            if "/var/lib/dpkg/status" not in stripped:
                current_obtainable = True

    if current_ver is not None:
        entries.append(AptVersionEntry(
            version=current_ver,
            is_installed=(current_ver == installed_ver),
            is_obtainable=current_obtainable,
        ))

    return entries


def _is_in_hold_list(output: str, pkg_name: str) -> bool:
    return any(line.strip() == pkg_name for line in output.splitlines())


def _parse_flatpak_log(output: str, current_commit: str | None) -> list[FlatpakCommit]:
    """Parse `flatpak remote-info --log` output.

    Example commit block::

        Commit: abc123def456...
        Subject: Update to 1.2.3
        Date: 2024-01-15 12:00:00 +0000
    """
    commits: list[FlatpakCommit] = []
    commit = subject = date = ""

    for line in output.splitlines():
        stripped = line.strip()
        m = re.match(r"Commit:\s+(\S+)", stripped)
        if m:
            if commit:
                commits.append(FlatpakCommit(
                    commit=commit, subject=subject, date=date,
                    is_current=(current_commit is not None
                                and commit.startswith(current_commit[:8])),
                ))
            commit = m.group(1)[:12]
            subject = date = ""
            continue
        m = re.match(r"Subject:\s+(.+)", stripped)
        if m:
            subject = m.group(1)
            continue
        m = re.match(r"Date:\s+(.+)", stripped)
        if m:
            date = m.group(1)

    if commit:
        commits.append(FlatpakCommit(
            commit=commit, subject=subject, date=date,
            is_current=(current_commit is not None
                        and commit.startswith(current_commit[:8])),
        ))

    return commits


def _get_flatpak_current_commit(app_id: str) -> str | None:
    try:
        r = subprocess.run(
            ["flatpak", "info", "--show-commit", app_id],
            capture_output=True, text=True, timeout=10,
        )
        return r.stdout.strip() or None
    except Exception:
        return None


def _is_in_mask_list(output: str, app_id: str) -> bool:
    return any(line.strip() == app_id for line in output.splitlines())
