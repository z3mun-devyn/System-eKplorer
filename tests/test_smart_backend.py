"""Tests for SmartBackend device detection and SMART output parsing."""

from pathlib import Path
from unittest.mock import MagicMock

from backends.smart_backend import SmartBackend, _parse_smart_output, _strip_partition


# ── _strip_partition unit tests ───────────────────────────────────────────────

def test_strip_partition_sda1_to_sda():
    assert _strip_partition("sda1") == "sda"


def test_strip_partition_sdb2_to_sdb():
    assert _strip_partition("sdb2") == "sdb"


def test_strip_partition_nvme_p_suffix():
    assert _strip_partition("nvme0n1p1") == "nvme0n1"


def test_strip_partition_mmcblk_p_suffix():
    assert _strip_partition("mmcblk0p2") == "mmcblk0"


def test_strip_partition_no_suffix_unchanged():
    assert _strip_partition("sda") == "sda"


# ── device_for_mount tests ────────────────────────────────────────────────────

def _write_mounts(tmp_path: Path, content: str) -> Path:
    p = tmp_path / "mounts"
    p.write_text(content, encoding="utf-8")
    return p


def test_device_for_mount_sdb1_strips_to_sdb(tmp_path):
    mounts = _write_mounts(tmp_path, "/dev/sdb1 /mnt/data ext4 rw 0 0\n")
    backend = SmartBackend(mounts_path=mounts)
    assert backend.device_for_mount("/mnt/data") == "/dev/sdb"


def test_device_for_mount_nvme_strips_p_suffix(tmp_path):
    mounts = _write_mounts(tmp_path, "/dev/nvme0n1p1 / ext4 rw 0 0\n")
    backend = SmartBackend(mounts_path=mounts)
    assert backend.device_for_mount("/") == "/dev/nvme0n1"


def test_device_for_mount_mmcblk_strips_p_suffix(tmp_path):
    mounts = _write_mounts(tmp_path, "/dev/mmcblk0p1 /boot/efi vfat rw 0 0\n")
    backend = SmartBackend(mounts_path=mounts)
    assert backend.device_for_mount("/boot/efi") == "/dev/mmcblk0"


def test_device_for_mount_returns_none_when_not_found(tmp_path):
    mounts = _write_mounts(tmp_path, "/dev/sda1 / ext4 rw 0 0\n")
    backend = SmartBackend(mounts_path=mounts)
    assert backend.device_for_mount("/nonexistent") is None


def test_device_for_mount_ignores_non_dev_devices(tmp_path):
    mounts = _write_mounts(tmp_path, "tmpfs /tmp tmpfs rw 0 0\n")
    backend = SmartBackend(mounts_path=mounts)
    assert backend.device_for_mount("/tmp") is None


def test_device_for_mount_missing_file(tmp_path):
    backend = SmartBackend(mounts_path=tmp_path / "nonexistent")
    assert backend.device_for_mount("/") is None


# ── _parse_smart_output unit tests ────────────────────────────────────────────

_SATA_OUTPUT = """\
smartctl 7.3 2022-02-28 r5338
Device Model:     SAMSUNG MZNLN256HAJQ
SMART overall-health self-assessment test result: PASSED

ID# ATTRIBUTE_NAME          FLAG  VALUE WORST THRESH TYPE  RAW_VALUE
  9 Power_On_Hours          0x0032  097  097  000   Old  12345
190 Airflow_Temp_Cel        0x0022  063  042  045   Old  37
"""

_NVME_OUTPUT = """\
smartctl 7.3 NVMe
SMART overall-health self-assessment test result: PASSED
Power On Hours:          8,760
Temperature:             42 Celsius
"""

_FAILED_OUTPUT = """\
SMART overall-health self-assessment test result: FAILED!
"""


def test_parse_health_passed_sata():
    data = _parse_smart_output(_SATA_OUTPUT)
    assert data.health == "PASSED"


def test_parse_health_passed_nvme():
    data = _parse_smart_output(_NVME_OUTPUT)
    assert data.health == "PASSED"


def test_parse_health_failed():
    data = _parse_smart_output(_FAILED_OUTPUT)
    assert data.health == "FAILED!"


def test_parse_power_on_hours_sata():
    data = _parse_smart_output(_SATA_OUTPUT)
    assert data.power_on_hours == 12345


def test_parse_power_on_hours_nvme():
    data = _parse_smart_output(_NVME_OUTPUT)
    assert data.power_on_hours == 8760


def test_parse_temperature_sata():
    data = _parse_smart_output(_SATA_OUTPUT)
    assert data.temperature_c == 37


def test_parse_temperature_nvme():
    data = _parse_smart_output(_NVME_OUTPUT)
    assert data.temperature_c == 42


def test_parse_missing_fields_are_none():
    data = _parse_smart_output("SMART overall-health self-assessment test result: PASSED\n")
    assert data.health == "PASSED"
    assert data.power_on_hours is None
    assert data.temperature_c is None
    assert data.reallocated_sectors is None


# ── get_data tests ────────────────────────────────────────────────────────────

def test_get_data_returns_none_when_smartctl_missing(monkeypatch):
    monkeypatch.setattr("backends.smart_backend.shutil.which", lambda _: None)
    backend = SmartBackend()
    assert backend.get_data("/dev/sda") is None


def test_get_data_returns_none_on_unknown_nonzero_returncode(monkeypatch):
    # returncode 3 (not in (0,1,2,4) and no "Permission denied") → None
    mock_result = MagicMock()
    mock_result.returncode = 3
    mock_result.stderr = ""
    mock_result.stdout = ""
    monkeypatch.setattr("backends.smart_backend.shutil.which", lambda _: "/usr/bin/smartctl")
    monkeypatch.setattr("backends.smart_backend.subprocess.run", lambda *a, **kw: mock_result)
    backend = SmartBackend()
    assert backend.get_data("/dev/sda") is None


def test_get_data_parses_health_passed(monkeypatch):
    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = _SATA_OUTPUT
    monkeypatch.setattr("backends.smart_backend.shutil.which", lambda _: "/usr/bin/smartctl")
    monkeypatch.setattr("backends.smart_backend.subprocess.run", lambda *a, **kw: mock_result)
    backend = SmartBackend()
    data = backend.get_data("/dev/sda")
    assert data is not None
    assert data.health == "PASSED"


def test_get_data_returns_permission_denied_health(monkeypatch):
    mock_result = MagicMock()
    mock_result.returncode = 1
    mock_result.stderr = "Permission denied"
    mock_result.stdout = ""
    monkeypatch.setattr("backends.smart_backend.shutil.which", lambda _: "/usr/bin/smartctl")
    monkeypatch.setattr("backends.smart_backend.subprocess.run", lambda *a, **kw: mock_result)
    backend = SmartBackend()
    data = backend.get_data("/dev/sda")
    assert data is not None
    assert data.health == "permission_denied"


def test_get_data_returncode_2_is_permission_denied(monkeypatch):
    mock_result = MagicMock()
    mock_result.returncode = 2
    mock_result.stderr = ""
    mock_result.stdout = ""
    monkeypatch.setattr("backends.smart_backend.shutil.which", lambda _: "/usr/bin/smartctl")
    monkeypatch.setattr("backends.smart_backend.subprocess.run", lambda *a, **kw: mock_result)
    backend = SmartBackend()
    data = backend.get_data("/dev/sda")
    assert data is not None
    assert data.health == "permission_denied"


def test_get_data_permission_denied_in_stderr_any_returncode(monkeypatch):
    mock_result = MagicMock()
    mock_result.returncode = 5
    mock_result.stderr = "Smartctl open device: /dev/sda failed: Permission denied"
    mock_result.stdout = ""
    monkeypatch.setattr("backends.smart_backend.shutil.which", lambda _: "/usr/bin/smartctl")
    monkeypatch.setattr("backends.smart_backend.subprocess.run", lambda *a, **kw: mock_result)
    backend = SmartBackend()
    data = backend.get_data("/dev/sda")
    assert data is not None
    assert data.health == "permission_denied"


def test_check_runnable_returns_true_on_zero_returncode(monkeypatch):
    mock_result = MagicMock()
    mock_result.returncode = 0
    monkeypatch.setattr("backends.smart_backend.subprocess.run", lambda *a, **kw: mock_result)
    backend = SmartBackend()
    assert backend.check_runnable() is True


def test_check_runnable_returns_false_on_nonzero(monkeypatch):
    mock_result = MagicMock()
    mock_result.returncode = 1
    monkeypatch.setattr("backends.smart_backend.subprocess.run", lambda *a, **kw: mock_result)
    backend = SmartBackend()
    assert backend.check_runnable() is False


def test_check_runnable_returns_false_on_exception(monkeypatch):
    def _raise(*a, **kw):
        raise FileNotFoundError()
    monkeypatch.setattr("backends.smart_backend.subprocess.run", _raise)
    backend = SmartBackend()
    assert backend.check_runnable() is False


def test_get_data_returncode_4_is_ok(monkeypatch):
    mock_result = MagicMock()
    mock_result.returncode = 4
    mock_result.stdout = "SMART overall-health self-assessment test result: PASSED\n"
    monkeypatch.setattr("backends.smart_backend.shutil.which", lambda _: "/usr/bin/smartctl")
    monkeypatch.setattr("backends.smart_backend.subprocess.run", lambda *a, **kw: mock_result)
    backend = SmartBackend()
    data = backend.get_data("/dev/sda")
    assert data is not None
    assert data.health == "PASSED"
