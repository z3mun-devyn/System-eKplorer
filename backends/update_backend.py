"""Detect available package updates (apt + flatpak).

run_apt_update()          → bool  (runs pkexec apt update, streaming)
list_apt_upgradable()     → [(name, new_version), ...]
list_flatpak_updates()    → [(app_id, new_version), ...]
"""
from __future__ import annotations

import subprocess

_TIMEOUT = 60


class UpdateBackend:
    def run_apt_update(self, line_cb=None) -> bool:
        """Refresh the apt package index via `pkexec apt update` (streaming).

        Returns True if the command exited 0, False otherwise.  Never raises —
        pkexec auth denial and FileNotFoundError are silently treated as failure
        so the caller can still read whatever is in the local cache.
        """
        rc = -1
        try:
            with subprocess.Popen(
                ["pkexec", "apt", "update"],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
            ) as proc:
                if proc.stdout:
                    for line in proc.stdout:
                        if line_cb:
                            line_cb(line.rstrip("\n"))
                rc = proc.returncode
        except Exception:
            pass
        return rc == 0

    def list_apt_upgradable(self) -> list[tuple[str, str]]:
        """Return (name, new_version) pairs for apt packages with available updates."""
        try:
            result = subprocess.run(
                ["apt", "list", "--upgradable"],
                capture_output=True, text=True, timeout=_TIMEOUT,
            )
        except Exception:
            return []
        return _parse_apt_upgradable(result.stdout)

    def list_flatpak_updates(self) -> list[tuple[str, str]]:
        """Return (app_id, new_version) pairs for flatpak apps with available updates."""
        try:
            result = subprocess.run(
                ["flatpak", "remote-ls", "--updates",
                 "--columns=application,version"],
                capture_output=True, text=True, timeout=_TIMEOUT,
            )
        except Exception:
            return []
        return _parse_flatpak_updates(result.stdout)


def _parse_apt_upgradable(output: str) -> list[tuple[str, str]]:
    """Parse `apt list --upgradable` stdout into (name, version) pairs.

    Line format: name/repo new_version arch [upgradable from: old_version]
    The "Listing..." header line is skipped.
    """
    results: list[tuple[str, str]] = []
    for line in output.splitlines():
        line = line.strip()
        if not line or line.startswith("Listing"):
            continue
        parts = line.split()
        if len(parts) < 2:
            continue
        name = parts[0].split("/")[0]
        version = parts[1]
        results.append((name, version))
    return results


def _parse_flatpak_updates(output: str) -> list[tuple[str, str]]:
    """Parse `flatpak remote-ls --updates --columns=application,version` stdout."""
    results: list[tuple[str, str]] = []
    for line in output.splitlines():
        parts = line.split()
        if len(parts) >= 2:
            results.append((parts[0], parts[1]))
    return results
