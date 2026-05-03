import json
import logging
import os
import re
import subprocess
from pathlib import Path

import config
from models.storage import Drive, UnmountedDrive

log = logging.getLogger(__name__)

PSEUDO_FS: frozenset[str] = frozenset({
    "tmpfs", "devtmpfs", "proc", "sysfs", "cgroup", "cgroup2",
    "squashfs", "overlay", "efivarfs", "securityfs", "fusectl",
    "hugetlbfs", "mqueue", "pstore", "debugfs", "tracefs",
    "bpf", "autofs", "devpts", "ramfs", "configfs", "binfmt_misc",
    "nsfs", "rpc_pipefs",
})

_BOOT_MOUNTS: frozenset[str] = frozenset({"/boot", "/boot/efi"})
_FAT_FS: frozenset[str] = frozenset({"vfat", "fat32", "msdos"})
_SKIP_FSTYPES: frozenset[str] = frozenset({"swap"})
_ENCRYPTED_FSTYPES: frozenset[str] = frozenset({"crypto_LUKS", "BitLocker"})

_BY_ID = Path("/dev/disk/by-id")

# Serial suffixes: 8+ uppercase alphanum chars at the end of a by-id name
_SERIAL_RE = re.compile(r"_[A-Z0-9]{8,}$")
# NVMe partition suffix: p followed by digits at end
_NVME_PART_RE = re.compile(r"(n\d+)p\d+$")


def _is_system_partition(d: Drive) -> bool:
    """True when the partition should be hidden from the user-facing drive list."""
    if config.SHOW_SYSTEM_PARTITIONS:
        return False
    if d.mount_point in _BOOT_MOUNTS:
        return True
    if d.total_bytes < config.MIN_USER_BYTES:
        return True
    return False


class StorageBackend:

    # ── df-based mounted drive list ──────────────────────────────────────────

    def _run_df(self) -> str | None:
        try:
            result = subprocess.run(
                ["df", "-B1", "--output=source,target,size,used,avail,fstype"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            return result.stdout
        except subprocess.TimeoutExpired:
            log.warning("df timed out after 5 seconds")
        except FileNotFoundError:
            log.warning("df not found on this system")
        except OSError as e:
            log.warning("df failed: %s", e)
        return None

    def _parse_df(self, output: str) -> list[Drive]:
        drives: list[Drive] = []
        lines = output.splitlines()
        if not lines:
            return drives
        for line in lines[1:]:          # skip header
            if not line.strip():
                continue
            try:
                parts = line.split()
                if len(parts) < 6:
                    log.warning("Skipping short df line: %r", line)
                    continue
                # Parse right-to-left so mount points with spaces are preserved
                source = parts[0]
                fstype = parts[-1]
                avail = int(parts[-2])
                used = int(parts[-3])
                size = int(parts[-4])
                mount_point = " ".join(parts[1:-4])
                device_id, name = self._resolve_drive_info(source)
                drives.append(Drive(
                    name=name,
                    device=source,
                    mount_point=mount_point,
                    total_bytes=size,
                    used_bytes=used,
                    free_bytes=avail,
                    fs_type=fstype,
                    device_id=device_id,
                ))
            except (ValueError, IndexError) as e:
                log.warning("Could not parse df line %r: %s", line, e)
        return drives

    def list_drives(self) -> list[Drive]:
        output = self._run_df()
        if output is None:
            return []
        try:
            all_drives = self._parse_df(output)
        except Exception as e:
            log.warning("Drive list parse failed unexpectedly: %s", e)
            return []

        real: list[Drive] = []
        seen_mounts: set[str] = set()
        for d in all_drives:
            if d.fs_type in PSEUDO_FS:
                continue
            if _is_system_partition(d):
                continue
            if d.mount_point in seen_mounts:
                continue
            seen_mounts.add(d.mount_point)
            real.append(d)

        self._attach_labels(real)
        return real

    def _attach_labels(self, drives: list[Drive]) -> None:
        try:
            from models.database import open_db
            ids = [d.device_id for d in drives if d.device_id]
            if not ids:
                return
            placeholders = ",".join("?" * len(ids))
            with open_db() as conn:
                rows = conn.execute(
                    f"SELECT device_id, label, color_hex FROM drive_labels"
                    f" WHERE device_id IN ({placeholders})",
                    ids,
                ).fetchall()
            label_map = {row["device_id"]: row for row in rows}
            for drive in drives:
                row = label_map.get(drive.device_id)
                if row:
                    drive.label = row["label"]
                    drive.color_hex = row["color_hex"]
        except Exception as e:
            log.warning("Could not load drive labels: %s", e)

    # ── lsblk-based unmounted device list ───────────────────────────────────

    def _run_lsblk(self) -> str | None:
        try:
            result = subprocess.run(
                ["lsblk", "-bpJ", "-o", "NAME,SIZE,FSTYPE,LABEL,MOUNTPOINT,TYPE"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            return result.stdout
        except subprocess.TimeoutExpired:
            log.warning("lsblk timed out after 5 seconds")
        except FileNotFoundError:
            log.warning("lsblk not found on this system")
        except OSError as e:
            log.warning("lsblk failed: %s", e)
        return None

    @staticmethod
    def _flatten_lsblk(devices: list[dict]) -> list[dict]:
        result: list[dict] = []
        for dev in devices:
            result.append(dev)
            children = dev.get("children") or []
            result.extend(StorageBackend._flatten_lsblk(children))
        return result

    @staticmethod
    def _lsblk_mountpoint(dev: dict) -> str:
        # lsblk ≥2.37 emits "mountpoints" (array); older emits "mountpoint" (string)
        mps = dev.get("mountpoints")
        if isinstance(mps, list):
            return next((m for m in mps if m), "")
        return dev.get("mountpoint") or ""

    def _parse_lsblk(self, output: str) -> list[UnmountedDrive]:
        data = json.loads(output)
        all_devs = self._flatten_lsblk(data.get("blockdevices", []))

        result: list[UnmountedDrive] = []
        for dev in all_devs:
            dev_type = dev.get("type", "")
            if dev_type not in ("part", "crypt"):
                continue

            fstype = dev.get("fstype") or ""
            if not fstype or fstype in _SKIP_FSTYPES:
                continue

            # Skip boot/EFI partitions identified by label
            fs_label = dev.get("label") or ""
            if fstype in _FAT_FS and fs_label.upper() in ("EFI", "ESP", "BOOT", "SYSTEM"):
                continue

            mountpoint = self._lsblk_mountpoint(dev)
            if mountpoint:
                continue

            size = int(dev.get("size") or 0)
            if size < config.MIN_USER_BYTES:
                continue

            device_path = dev["name"]
            device_id, display_name = self._resolve_drive_info(device_path)
            is_encrypted = fstype in _ENCRYPTED_FSTYPES or dev_type == "crypt"

            result.append(UnmountedDrive(
                name=display_name,
                device=device_path,
                size_bytes=size,
                fs_type=fstype,
                fs_label=fs_label,
                is_encrypted=is_encrypted,
                device_id=device_id,
            ))
        return result

    def list_unmounted_devices(self) -> list[UnmountedDrive]:
        output = self._run_lsblk()
        if output is None:
            return []
        try:
            return self._parse_lsblk(output)
        except Exception as e:
            log.warning("lsblk parse failed: %s", e)
            return []

    # ── by-id name resolution ────────────────────────────────────────────────

    def _resolve_drive_info(self, device: str) -> tuple[str, str]:
        """Return (device_id, display_name) for device."""
        basename = os.path.basename(device)
        if not _BY_ID.exists():
            return (basename, basename)
        try:
            return self._lookup_by_id(device)
        except OSError as e:
            log.warning("Could not read /dev/disk/by-id: %s", e)
            return (basename, basename)

    def _lookup_by_id(self, device: str) -> tuple[str, str]:
        device_path = Path(device)
        try:
            resolved = device_path.resolve()
        except OSError:
            basename = os.path.basename(device)
            return (basename, basename)

        # Build map: resolved real path → list of by-id names
        candidates: list[str] = []
        for link in _BY_ID.iterdir():
            try:
                link_real = (_BY_ID / link.readlink()).resolve()
            except (OSError, ValueError):
                continue
            if link_real == resolved:
                candidates.append(link.name)

        # Prefer disk-level entries (no -partN suffix); if none, try the parent disk
        disk_level = [c for c in candidates if not re.search(r"-part\d+$", c)]

        if not disk_level:
            # Look up the parent disk device and prefer its disk-level entries
            parent = _NVME_PART_RE.sub(r"\1", device)   # nvme0n1p2 → nvme0n1
            if parent == device:
                parent = re.sub(r"\d+$", "", device)    # sda1 → sda
            if parent != device:
                try:
                    parent_real = Path(parent).resolve()
                    for link in _BY_ID.iterdir():
                        try:
                            link_real = (_BY_ID / link.readlink()).resolve()
                        except (OSError, ValueError):
                            continue
                        if link_real == parent_real:
                            name = link.name
                            if not re.search(r"-part\d+$", name):
                                disk_level.append(name)
                            else:
                                candidates.append(name)
                except OSError:
                    pass

        basename = os.path.basename(device)
        if not disk_level and not candidates:
            return (basename, basename)

        chosen = disk_level[0] if disk_level else candidates[0]
        raw_id = chosen  # stable identifier before prettification

        # Skip wwn- entries — they carry no human-readable name
        if chosen.startswith("wwn-"):
            return (basename, basename)

        # Strip known bus prefixes
        for prefix in ("ata-", "nvme-", "usb-", "mmc-", "virtio-"):
            if chosen.startswith(prefix):
                chosen = chosen[len(prefix):]
                break

        # Strip trailing serial number (_XXXXXXXX, 8+ uppercase alphanum)
        chosen = _SERIAL_RE.sub("", chosen)

        # Replace underscores with spaces and tidy up
        display = chosen.replace("_", " ").strip()
        return (raw_id, display if display else basename)
