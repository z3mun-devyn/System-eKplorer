from __future__ import annotations

import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from models.package import Package

if TYPE_CHECKING:
    pass

_TIMEOUT = 30
_COLUMNS = "application,name,version,size"

_FLATPAK_SEARCH_DIRS = [
    Path("/var/lib/flatpak/app"),
    Path.home() / ".local" / "share" / "flatpak" / "app",
]


def _flatpak_install_date(
    app_id: str,
    search_dirs: list[Path] | None = None,
) -> datetime | None:
    """Return the install date for a flatpak app via its deploy-dir mtime."""
    dirs = search_dirs if search_dirs is not None else _FLATPAK_SEARCH_DIRS
    for base in dirs:
        active = base / app_id / "current" / "active"
        if active.exists():
            try:
                return datetime.fromtimestamp(active.stat().st_mtime)
            except OSError:
                pass
    return None


def _parse_size_kb(size_str: str) -> int:
    """Convert flatpak size string ('293.0 MB', '11.1 MB', '1.2 GB', '512.0 kB') to KB."""
    try:
        parts = size_str.strip().split()
        value = float(parts[0])
        unit = parts[1].upper()
        if unit in ("KB", "KIB"):
            return int(value)
        if unit in ("MB", "MIB"):
            return int(value * 1024)
        if unit in ("GB", "GIB"):
            return int(value * 1024 * 1024)
    except (ValueError, IndexError):
        pass
    return 0


def _parse_line(line: str) -> Package | None:
    """Parse one tab-delimited flatpak list line; return None on malformed input."""
    try:
        parts = line.rstrip("\n").split("\t")
        if len(parts) < 4:
            return None
        app_id, friendly, version, size_str = parts[0], parts[1], parts[2], parts[3]
        if not app_id:
            return None
        return Package(
            name=app_id,
            version=version,
            installed_size_kb=_parse_size_kb(size_str),
            section="",
            source="flatpak",
            display_name=friendly,
        )
    except Exception:
        return None


class FlatpakBackend:
    @staticmethod
    def is_available() -> bool:
        return shutil.which("flatpak") is not None

    def list_installed(self) -> list[Package]:
        if not self.is_available():
            return []
        try:
            result = subprocess.run(
                ["flatpak", "list", f"--columns={_COLUMNS}", "--app"],
                capture_output=True,
                text=True,
                timeout=_TIMEOUT,
            )
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            return []
        except Exception:
            return []

        packages: list[Package] = []
        for line in result.stdout.splitlines():
            if not line.strip():
                continue
            try:
                pkg = _parse_line(line)
                if pkg is not None:
                    try:
                        pkg.installed_on = _flatpak_install_date(pkg.name)
                    except Exception:
                        pass
                    packages.append(pkg)
            except Exception:
                continue
        return packages
