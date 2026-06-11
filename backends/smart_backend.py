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

    def device_for_mount(self, mount_point: str) -> str | None:
        try:
            text = self._mounts_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return None

        for line in text.splitlines():
            fields = line.split()
            if len(fields) < 2:
                continue
            if fields[1] == mount_point:
                device = fields[0]
                if not device.startswith("/dev/"):
                    return None
                name = Path(device).name
                stripped = _strip_partition(name)
                return f"/dev/{stripped}"
        return None

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
