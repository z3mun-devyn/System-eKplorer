"""Resolve a package's install directory for the "Open install location" action.

resolve_location(name, source) → str | None
  Returns an absolute directory path or None when no useful location is found.

The resolution is intentionally lazy (called on user action, not at load time).
Subprocess calls use a short timeout so the UI is never blocked indefinitely.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

_TIMEOUT = 10


def resolve_location(package_name: str, source: str) -> str | None:
    """Return install directory for *package_name* or None."""
    if source == "flatpak":
        return _flatpak_location(package_name)
    return _apt_location(package_name)


# ── Flatpak ───────────────────────────────────────────────────────────────────

def _flatpak_location(app_id: str) -> str | None:
    try:
        result = subprocess.run(
            ["flatpak", "info", "--show-location", app_id],
            capture_output=True,
            text=True,
            timeout=_TIMEOUT,
        )
        path = result.stdout.strip()
        return path if path else None
    except Exception:
        return None


# ── APT ───────────────────────────────────────────────────────────────────────

def _apt_location(package_name: str) -> str | None:
    try:
        result = subprocess.run(
            ["dpkg", "-L", package_name],
            capture_output=True,
            text=True,
            timeout=_TIMEOUT,
        )
        lines = [ln.strip() for ln in result.stdout.splitlines() if ln.strip()]
        return _pick_apt_dir(lines)
    except Exception:
        return None


def _pick_apt_dir(file_list: list[str]) -> str | None:
    """Choose the best install directory from a dpkg -L file list.

    Priority:
      1. /opt/{x}          — self-contained install under /opt
      2. /usr/share/{x}    — dedicated data dir (matches any x with files inside)
      3. /usr/bin or /usr/games — parent dir of the first executable found
      4. None
    """
    # 1. /opt/{x}
    for f in file_list:
        p = Path(f)
        if len(p.parts) >= 3 and p.parts[1] == "opt":
            return str(Path("/") / "opt" / p.parts[2])

    # 2. /usr/share/{x}  — any subpath with at least one level under share,
    #    excluding well-known shared container directories that many packages
    #    write into (doc, man, locale, lintian, games, icons, pixmaps, etc.)
    _SHARED_CONTAINERS = frozenset(
        ("doc", "man", "locale", "lintian", "games",
         "icons", "pixmaps", "applications", "fonts")
    )
    for f in file_list:
        p = Path(f)
        if (len(p.parts) >= 4
                and p.parts[1] == "usr"
                and p.parts[2] == "share"
                and p.parts[3] not in _SHARED_CONTAINERS):
            return str(Path("/") / "usr" / "share" / p.parts[3])

    # 3. Executable directory
    for prefix in ("/usr/bin", "/usr/games"):
        for f in file_list:
            if f.startswith(prefix + "/"):
                return prefix

    return None
