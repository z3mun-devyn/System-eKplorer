import logging
import subprocess
from datetime import datetime
from pathlib import Path

from models.package import Package

log = logging.getLogger(__name__)

# Fields: name, version, installed-size (KB), status abbrev (ii = installed), section
_DPKG_FORMAT = "${Package}\\t${Version}\\t${Installed-Size}\\t${db:Status-Abbrev}\\t${Section}\\n"

_DPKG_INFO_DIR = Path("/var/lib/dpkg/info")
_MULTIARCH_SUFFIXES = ("amd64", "arm64", "i386", "all")


def _apt_install_date(
    name: str,
    info_dir: Path = _DPKG_INFO_DIR,
) -> datetime | None:
    """Return the install date for an apt package via dpkg info file mtime."""
    primary = info_dir / f"{name}.list"
    if primary.exists():
        try:
            return datetime.fromtimestamp(primary.stat().st_mtime)
        except OSError:
            pass
    for arch in _MULTIARCH_SUFFIXES:
        candidate = info_dir / f"{name}:{arch}.list"
        if candidate.exists():
            try:
                return datetime.fromtimestamp(candidate.stat().st_mtime)
            except OSError:
                pass
    return None


class PackagesBackend:
    def list_installed(self) -> list[Package]:
        try:
            result = subprocess.run(
                ["dpkg-query", "-W", f"-f={_DPKG_FORMAT}"],
                capture_output=True,
                text=True,
                timeout=30,
            )
        except subprocess.TimeoutExpired:
            log.warning("dpkg-query timed out after 30s")
            return []
        except FileNotFoundError:
            log.warning("dpkg-query not found")
            return []

        packages: list[Package] = []
        for line in result.stdout.splitlines():
            pkg = _parse_line(line)
            if pkg is not None:
                try:
                    pkg.installed_on = _apt_install_date(pkg.name)
                except Exception:
                    pass
                packages.append(pkg)
        return packages


def _parse_line(line: str) -> Package | None:
    parts = line.split("\t", 4)
    if len(parts) < 5:
        return None
    name, version, size_str, status, section = parts
    if not status.strip().startswith("ii"):
        return None
    try:
        size_kb = int(size_str.strip())
    except ValueError:
        size_kb = 0
    # Strip area prefix from section (e.g. "non-free/libs" → "libs")
    base_section = section.strip()
    if "/" in base_section:
        base_section = base_section.split("/")[-1]
    return Package(
        name=name.strip(),
        version=version.strip(),
        installed_size_kb=size_kb,
        section=base_section.lower(),
    )
