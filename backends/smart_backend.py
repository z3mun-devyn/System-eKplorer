"""SMART health data via smartctl."""

from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class SmartData:
    health: str
    power_on_hours: int | None = None
    temperature_c: int | None = None
    reallocated_sectors: int | None = None


def _resolve_zfs_members(pool_name: str) -> list[str]:
    """Run `zpool status -P <pool>` and extract unique member device paths."""
    if shutil.which("zpool") is None:
        return []
    try:
        result = subprocess.run(
            ["zpool", "status", "-P", pool_name],
            capture_output=True, text=True, timeout=10,
        )
    except Exception:
        return []
    seen: list[str] = []
    for match in re.finditer(r"^\s+(/dev/\S+)", result.stdout, re.MULTILINE):
        raw = match.group(1)
        parent = Path(raw).parent
        name = Path(raw).name
        stripped = _strip_partition(name)
        # Preserve full path for by-id/by-path symlinks; just strip the basename.
        dev = str(parent / stripped)
        if dev not in seen:
            seen.append(dev)
    return seen


def _strip_partition(name: str) -> str:
    if re.search(r"(nvme|mmcblk)", name):
        return re.sub(r"p\d+$", "", name)
    return re.sub(r"\d+$", "", name)


def _parse_smart_output(text: str) -> SmartData:
    health = "UNKNOWN"
    power_on_hours: int | None = None
    temperature_c: int | None = None
    reallocated_sectors: int | None = None

    for line in text.splitlines():
        try:
            if "SMART overall-health self-assessment test result:" in line:
                parts = line.split(":")
                if len(parts) >= 2:
                    health = parts[-1].strip().split()[0]

            elif "Power_On_Hours" in line:
                raw = line.split()[-1]
                power_on_hours = int(raw.replace(",", ""))

            elif re.match(r"Power On Hours:\s+", line):
                m = re.search(r"Power On Hours:\s+([\d,]+)", line)
                if m:
                    power_on_hours = int(m.group(1).replace(",", ""))

            elif "Temperature_Celsius" in line or "Airflow_Temp" in line:
                raw = line.split()[-1]
                temperature_c = int(raw.split()[0])

            elif re.match(r"Temperature:\s+\d+", line):
                m = re.search(r"Temperature:\s+(\d+)", line)
                if m:
                    temperature_c = int(m.group(1))

            elif "Reallocated_Sector_Ct" in line:
                raw = line.split()[-1]
                reallocated_sectors = int(raw.replace(",", ""))

        except (ValueError, IndexError):
            continue

    return SmartData(
        health=health,
        power_on_hours=power_on_hours,
        temperature_c=temperature_c,
        reallocated_sectors=reallocated_sectors,
    )


class SmartBackend:
    def __init__(self, mounts_path: str | Path | None = None) -> None:
        self._mounts_path = Path(mounts_path) if mounts_path else Path("/proc/mounts")

    def is_available(self) -> bool:
        return shutil.which("smartctl") is not None

    def devices_for_mount(self, mount_point: str) -> list[str]:
        """Return disk device(s) backing mount_point.

        Single-disk mounts → 1-element list.
        ZFS pools → all member vdev disk paths via `zpool status -P`.
        Returns [] when the mount is unknown or not mappable to /dev.
        """
        try:
            text = self._mounts_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return []

        for line in text.splitlines():
            fields = line.split()
            if len(fields) < 3:
                continue
            if fields[1] != mount_point:
                continue
            device, fstype = fields[0], fields[2]
            if fstype == "zfs" or not device.startswith("/dev/"):
                pool = device.split("/")[0]
                members = _resolve_zfs_members(pool)
                return members
            name = Path(device).name
            return [f"/dev/{_strip_partition(name)}"]
        return []

    def device_for_mount(self, mount_point: str) -> str | None:
        """Compat shim — returns first device or None. Prefer devices_for_mount."""
        devices = self.devices_for_mount(mount_point)
        return devices[0] if devices else None

    def check_runnable(self) -> bool:
        """Return True if smartctl --version exits successfully."""
        try:
            r = subprocess.run(
                ["smartctl", "--version"],
                capture_output=True, text=True, timeout=5,
            )
            return r.returncode == 0
        except Exception:
            return False

    def get_data(self, device: str) -> SmartData | None:
        if shutil.which("smartctl") is None:
            return None
        try:
            result = subprocess.run(
                ["smartctl", "-iHA", device],
                capture_output=True, text=True, timeout=10,
            )
        except Exception:
            return None

        if result.returncode not in (0, 4):
            if (
                result.returncode in (1, 2)
                or "Permission denied" in result.stderr
                or "Permission denied" in result.stdout
            ):
                return SmartData(health="permission_denied")
            return None

        return _parse_smart_output(result.stdout)
