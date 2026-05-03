"""Parser tests for StorageBackend.

All tests feed fixture strings directly to _parse_df() or _parse_lsblk()
— no subprocess, no real filesystem. list_drives() is covered by monkeypatch
tests.
"""

import json
import pytest
from backends.storage_backend import PSEUDO_FS, StorageBackend
import config

_backend = StorageBackend()

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SAMPLE_DF = """\
Filesystem              Mounted on       1B-blocks         Used    Available Fstype
/dev/nvme0n1p2          /           500107862016    123456789  376651073027 ext4
/dev/nvme0n1p3          /home      1000204886016    456789012  543415874004 btrfs
/dev/nvme0n1p1          /boot/efi       536870912     12345678   524525234 vfat
tmpfs                   /run/user/1000   16777216            0    16777216 tmpfs
/dev/loop0              /snap/core       74448896     74448896           0 squashfs
"""

# Two good lines mixed with three bad ones
MALFORMED_DF = """\
Filesystem   Mounted on  1B-blocks  Used  Available Fstype
/dev/sda1    /           500107862016 123456789 376651073027 ext4
this line is total garbage
/dev/sdb1    /data      1000204886016 456789012 543415874004 ext4

not_enough
"""

# Header only — no data
EMPTY_DF = "Filesystem   Mounted on  1B-blocks  Used  Available Fstype\n"

# Completely unrecognisable
GARBAGE_DF = "this is not df output at all\nno columns here\n"

# Mount point with a space in its name
SPACED_MOUNT_DF = """\
Filesystem   Mounted on  1B-blocks  Used  Available Fstype
/dev/sdc1    /my files  500107862016 123456789 376651073027 ext4
"""

# ---------------------------------------------------------------------------
# _parse_df: basic correctness
# ---------------------------------------------------------------------------

def test_parse_sample_count():
    drives = _backend._parse_df(SAMPLE_DF)
    assert len(drives) == 5  # all 5 lines parsed; filtering is list_drives()'s job


def test_parse_correct_bytes():
    drives = _backend._parse_df(SAMPLE_DF)
    root = next(d for d in drives if d.mount_point == "/")
    assert root.total_bytes == 500107862016
    assert root.used_bytes == 123456789
    assert root.free_bytes == 376651073027


def test_parse_correct_device_and_fstype():
    drives = _backend._parse_df(SAMPLE_DF)
    root = next(d for d in drives if d.mount_point == "/")
    assert root.device == "/dev/nvme0n1p2"
    assert root.fs_type == "ext4"


def test_used_pct_accuracy():
    drives = _backend._parse_df(SAMPLE_DF)
    root = next(d for d in drives if d.mount_point == "/")
    expected = 123456789 / 500107862016
    assert abs(root.used_pct - expected) < 1e-9


def test_parse_all_fstypes_present():
    drives = _backend._parse_df(SAMPLE_DF)
    fstypes = {d.fs_type for d in drives}
    assert fstypes == {"ext4", "btrfs", "vfat", "tmpfs", "squashfs"}


# ---------------------------------------------------------------------------
# _parse_df: mount point with a space
# ---------------------------------------------------------------------------

def test_spaced_mount_point():
    drives = _backend._parse_df(SPACED_MOUNT_DF)
    assert len(drives) == 1
    assert drives[0].mount_point == "/my files"
    assert drives[0].total_bytes == 500107862016


# ---------------------------------------------------------------------------
# _parse_df: resilience
# ---------------------------------------------------------------------------

def test_malformed_lines_skipped():
    drives = _backend._parse_df(MALFORMED_DF)
    assert len(drives) == 2
    devices = {d.device for d in drives}
    assert "/dev/sda1" in devices
    assert "/dev/sdb1" in devices


def test_empty_df_output():
    assert _backend._parse_df(EMPTY_DF) == []


def test_empty_string():
    assert _backend._parse_df("") == []


def test_garbage_df_output():
    result = _backend._parse_df(GARBAGE_DF)
    assert isinstance(result, list)
    assert len(result) == 0


# ---------------------------------------------------------------------------
# list_drives: pseudo-filesystem filtering
# ---------------------------------------------------------------------------

def test_pseudo_fs_filtered():
    drives = _backend._parse_df(SAMPLE_DF)
    real = [d for d in drives if d.fs_type not in PSEUDO_FS]
    assert len(real) == 3
    fstypes = {d.fs_type for d in real}
    assert "tmpfs" not in fstypes
    assert "squashfs" not in fstypes


def test_list_drives_returns_empty_on_run_failure(monkeypatch):
    monkeypatch.setattr(StorageBackend, "_run_df", lambda self: None)
    assert StorageBackend().list_drives() == []


def test_list_drives_no_duplicates(monkeypatch):
    # Two lines with the same mount point — only the first should survive.
    # Use >1 GiB sizes so system-partition filtering doesn't swallow them.
    df_out = """\
Filesystem  Mounted on  1B-blocks       Used    Available Fstype
/dev/sda1   /           107374182400 50000000 57374182400 ext4
/dev/sda2   /           214748364800 50000000 214698364800 ext4
"""
    monkeypatch.setattr(StorageBackend, "_run_df", lambda self: df_out)
    drives = StorageBackend().list_drives()
    mounts = [d.mount_point for d in drives]
    assert mounts.count("/") == 1


# ---------------------------------------------------------------------------
# _resolve_drive_name: fallback when /dev/disk/by-id absent
# ---------------------------------------------------------------------------

def test_resolve_name_fallback_no_by_id(monkeypatch, tmp_path):
    monkeypatch.setattr("backends.storage_backend._BY_ID", tmp_path / "nonexistent")
    device_id, name = StorageBackend()._resolve_drive_info("/dev/sda99")
    assert name == "sda99"
    assert device_id == "sda99"


def test_resolve_name_returns_string_for_any_input(monkeypatch, tmp_path):
    monkeypatch.setattr("backends.storage_backend._BY_ID", tmp_path / "nonexistent")
    for dev in ("/dev/sda", "/dev/nvme0n1p1", "/dev/mmcblk0p1", "tmpfs"):
        device_id, name = StorageBackend()._resolve_drive_info(dev)
        assert isinstance(name, str) and len(name) > 0
        assert isinstance(device_id, str) and len(device_id) > 0


# ---------------------------------------------------------------------------
# Drive model helpers
# ---------------------------------------------------------------------------

def test_fmt_bytes_gb():
    from models.storage import Drive
    d = Drive("x", "/dev/x", "/", 500_107_862_016, 123_456_789, 376_651_073_027, "ext4")
    assert "GB" in d.total_str


def test_fmt_bytes_zero():
    from models.storage import Drive
    d = Drive("x", "/dev/x", "/", 0, 0, 0, "ext4")
    assert d.used_pct == 0.0
    assert "0.0" in d.used_str


# ---------------------------------------------------------------------------
# ITEM 1: system-partition filtering in list_drives()
# ---------------------------------------------------------------------------

_FILTER_DF = """\
Filesystem  Mounted on   1B-blocks       Used    Available Fstype
/dev/sda1   /boot/efi    536870912   12345678   524525234 vfat
/dev/sda2   /boot        524288000  100000000   424288000 ext4
/dev/sda3   /            500107862016 123456789 376651073027 ext4
/dev/sda4   /home        300000000000 50000000000 250000000000 btrfs
/dev/sda5   /data        524288000   200000000   324288000 ext4
"""


def test_efi_partition_filtered(monkeypatch):
    monkeypatch.setattr(StorageBackend, "_run_df", lambda self: _FILTER_DF)
    drives = StorageBackend().list_drives()
    mounts = {d.mount_point for d in drives}
    assert "/boot/efi" not in mounts


def test_boot_partition_filtered(monkeypatch):
    monkeypatch.setattr(StorageBackend, "_run_df", lambda self: _FILTER_DF)
    drives = StorageBackend().list_drives()
    mounts = {d.mount_point for d in drives}
    assert "/boot" not in mounts


def test_small_ext4_partition_filtered(monkeypatch):
    # /data is 500 MiB — below the 1 GiB threshold
    monkeypatch.setattr(StorageBackend, "_run_df", lambda self: _FILTER_DF)
    drives = StorageBackend().list_drives()
    mounts = {d.mount_point for d in drives}
    assert "/data" not in mounts


def test_normal_user_partition_passes(monkeypatch):
    monkeypatch.setattr(StorageBackend, "_run_df", lambda self: _FILTER_DF)
    drives = StorageBackend().list_drives()
    mounts = {d.mount_point for d in drives}
    assert "/" in mounts
    assert "/home" in mounts


def test_show_system_partitions_flag_bypasses_filter(monkeypatch):
    monkeypatch.setattr(StorageBackend, "_run_df", lambda self: _FILTER_DF)
    monkeypatch.setattr(config, "SHOW_SYSTEM_PARTITIONS", True)
    drives = StorageBackend().list_drives()
    mounts = {d.mount_point for d in drives}
    assert "/boot/efi" in mounts
    assert "/boot" in mounts
    assert "/data" in mounts


# ---------------------------------------------------------------------------
# ITEM 3: list_unmounted_devices() / _parse_lsblk()
# ---------------------------------------------------------------------------

_LSBLK_DATA = {
    "blockdevices": [
        {
            "name": "/dev/sda",
            "size": "500107862016",
            "fstype": None,
            "label": None,
            "mountpoint": None,
            "type": "disk",
            "children": [
                # Mounted — must be excluded
                {
                    "name": "/dev/sda1",
                    "size": "499107862016",
                    "fstype": "ext4",
                    "label": None,
                    "mountpoint": "/",
                    "type": "part",
                },
                # Unmounted ext4 — must appear
                {
                    "name": "/dev/sda2",
                    "size": "2000000000",
                    "fstype": "ext4",
                    "label": "DataVol",
                    "mountpoint": None,
                    "type": "part",
                },
                # Small (< 1 GiB) — must be excluded
                {
                    "name": "/dev/sda3",
                    "size": "536870912",
                    "fstype": "vfat",
                    "label": None,
                    "mountpoint": None,
                    "type": "part",
                },
                # Swap — must be excluded
                {
                    "name": "/dev/sda4",
                    "size": "4294967296",
                    "fstype": "swap",
                    "label": None,
                    "mountpoint": None,
                    "type": "part",
                },
            ],
        },
        # Unmounted LUKS — must appear as encrypted
        {
            "name": "/dev/sdb",
            "size": "1000204886016",
            "fstype": None,
            "label": None,
            "mountpoint": None,
            "type": "disk",
            "children": [
                {
                    "name": "/dev/sdb1",
                    "size": "1000000000000",
                    "fstype": "crypto_LUKS",
                    "label": None,
                    "mountpoint": None,
                    "type": "part",
                }
            ],
        },
    ]
}

_LSBLK_JSON = json.dumps(_LSBLK_DATA)


def test_unmounted_parses_known_device(monkeypatch):
    monkeypatch.setattr(StorageBackend, "_run_lsblk", lambda self: _LSBLK_JSON)
    devices = StorageBackend().list_unmounted_devices()
    device_paths = {d.device for d in devices}
    assert "/dev/sda2" in device_paths


def test_unmounted_excludes_mounted_device(monkeypatch):
    monkeypatch.setattr(StorageBackend, "_run_lsblk", lambda self: _LSBLK_JSON)
    devices = StorageBackend().list_unmounted_devices()
    device_paths = {d.device for d in devices}
    assert "/dev/sda1" not in device_paths


def test_unmounted_excludes_small_device(monkeypatch):
    monkeypatch.setattr(StorageBackend, "_run_lsblk", lambda self: _LSBLK_JSON)
    devices = StorageBackend().list_unmounted_devices()
    device_paths = {d.device for d in devices}
    assert "/dev/sda3" not in device_paths


def test_unmounted_excludes_swap(monkeypatch):
    monkeypatch.setattr(StorageBackend, "_run_lsblk", lambda self: _LSBLK_JSON)
    devices = StorageBackend().list_unmounted_devices()
    device_paths = {d.device for d in devices}
    assert "/dev/sda4" not in device_paths


def test_unmounted_identifies_luks_as_encrypted(monkeypatch):
    monkeypatch.setattr(StorageBackend, "_run_lsblk", lambda self: _LSBLK_JSON)
    devices = StorageBackend().list_unmounted_devices()
    luks = next((d for d in devices if d.device == "/dev/sdb1"), None)
    assert luks is not None
    assert luks.is_encrypted is True


def test_unmounted_plain_not_encrypted(monkeypatch):
    monkeypatch.setattr(StorageBackend, "_run_lsblk", lambda self: _LSBLK_JSON)
    devices = StorageBackend().list_unmounted_devices()
    plain = next((d for d in devices if d.device == "/dev/sda2"), None)
    assert plain is not None
    assert plain.is_encrypted is False


def test_unmounted_fs_label_populated(monkeypatch):
    monkeypatch.setattr(StorageBackend, "_run_lsblk", lambda self: _LSBLK_JSON)
    devices = StorageBackend().list_unmounted_devices()
    vol = next((d for d in devices if d.device == "/dev/sda2"), None)
    assert vol is not None
    assert vol.fs_label == "DataVol"


def test_unmounted_returns_empty_on_run_failure(monkeypatch):
    monkeypatch.setattr(StorageBackend, "_run_lsblk", lambda self: None)
    assert StorageBackend().list_unmounted_devices() == []


def test_unmounted_handles_malformed_json(monkeypatch):
    monkeypatch.setattr(StorageBackend, "_run_lsblk", lambda self: "not json at all")
    result = StorageBackend().list_unmounted_devices()
    assert isinstance(result, list)
    assert result == []


def test_unmounted_handles_lsblk_newer_mountpoints_key(monkeypatch):
    # lsblk ≥2.37 emits "mountpoints" (array) instead of "mountpoint" (string)
    data = {
        "blockdevices": [
            {
                "name": "/dev/sdc1",
                "size": "2000000000",
                "fstype": "ext4",
                "label": None,
                "mountpoints": ["/mnt/usb"],  # newer key — should be seen as mounted
                "type": "part",
            },
            {
                "name": "/dev/sdc2",
                "size": "2000000000",
                "fstype": "ext4",
                "label": None,
                "mountpoints": [None],  # newer key — unmounted
                "type": "part",
            },
        ]
    }
    monkeypatch.setattr(StorageBackend, "_run_lsblk", lambda self: json.dumps(data))
    devices = StorageBackend().list_unmounted_devices()
    device_paths = {d.device for d in devices}
    assert "/dev/sdc1" not in device_paths  # has mountpoint → excluded
    assert "/dev/sdc2" in device_paths       # no mountpoint → included
