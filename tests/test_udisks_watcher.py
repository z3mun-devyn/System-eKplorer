"""Tests for UDisks2Watcher and DashboardView auto-refresh integration."""

import pytest
from unittest.mock import MagicMock

from backends.udisks_watcher import UDisks2Watcher
from backends.storage_backend import StorageBackend
from models.storage import Drive, UnmountedDrive


def _drive(device: str, name: str = "Drive", mount: str = "/") -> Drive:
    return Drive(
        name=name,
        device=device,
        mount_point=mount,
        total_bytes=500_000_000_000,
        used_bytes=100_000_000_000,
        free_bytes=400_000_000_000,
        fs_type="ext4",
        device_id=device.lstrip("/").replace("/", "-"),
    )


# ---------------------------------------------------------------------------
# UDisks2Watcher unit tests
# ---------------------------------------------------------------------------

def test_storage_changed_fires_after_dbus_event(qtbot):
    watcher = UDisks2Watcher()
    with qtbot.waitSignal(watcher.storage_changed, timeout=500):
        watcher._on_dbus_event()


def test_debounce_coalesces_rapid_events(qtbot):
    watcher = UDisks2Watcher()
    fired: list[int] = []
    watcher.storage_changed.connect(lambda: fired.append(1))

    for _ in range(8):
        watcher._on_dbus_event()

    qtbot.wait(400)  # longer than 250 ms debounce
    assert len(fired) == 1


def test_debounce_resets_on_each_event(qtbot):
    watcher = UDisks2Watcher()
    fired: list[int] = []
    watcher.storage_changed.connect(lambda: fired.append(1))

    watcher._on_dbus_event()
    qtbot.wait(100)
    watcher._on_dbus_event()   # resets the timer
    qtbot.wait(100)
    assert len(fired) == 0     # hasn't fired yet

    qtbot.wait(300)            # now > 250 ms since last event
    assert len(fired) == 1


def test_dbus_unavailable_no_crash(monkeypatch):
    from PyQt6.QtDBus import QDBusConnection

    class _FakeBus:
        def isConnected(self):
            return False

    monkeypatch.setattr(QDBusConnection, "systemBus", staticmethod(lambda: _FakeBus()))
    watcher = UDisks2Watcher()
    assert watcher.dbus_available is False


def test_dbus_connect_failure_no_crash(monkeypatch):
    from PyQt6.QtDBus import QDBusConnection

    class _FaultyBus:
        def isConnected(self):
            return True

        def connect(self, *args, **kwargs):
            raise RuntimeError("simulated D-Bus error")

    monkeypatch.setattr(QDBusConnection, "systemBus", staticmethod(lambda: _FaultyBus()))
    watcher = UDisks2Watcher()
    assert watcher.dbus_available is False


def test_dbus_event_does_not_raise_on_handler_error(qtbot):
    watcher = UDisks2Watcher()
    # Make debounce.start raise to simulate internal error
    watcher._debounce.start = MagicMock(side_effect=RuntimeError("boom"))
    # Must not propagate
    watcher._on_dbus_event()


# ---------------------------------------------------------------------------
# DashboardView integration tests
# ---------------------------------------------------------------------------

def test_dashboard_shows_initial_tiles(qtbot, monkeypatch):
    from views.dashboard_view import DashboardView

    monkeypatch.setattr(StorageBackend, "list_drives", lambda self: [_drive("/dev/sda1")])
    monkeypatch.setattr(StorageBackend, "list_unmounted_devices", lambda self: [])

    view = DashboardView()
    qtbot.addWidget(view)
    qtbot.waitUntil(lambda: len(view._tiles) == 1, timeout=3000)


def test_dashboard_adds_tile_on_storage_changed(qtbot, monkeypatch):
    from views.dashboard_view import DashboardView

    call_count = [0]

    def fake_list_drives(self):
        call_count[0] += 1
        if call_count[0] == 1:
            return [_drive("/dev/sda1", "Primary")]
        return [
            _drive("/dev/sda1", "Primary"),
            _drive("/dev/sdb1", "USB Drive", "/mnt/usb"),
        ]

    monkeypatch.setattr(StorageBackend, "list_drives", fake_list_drives)
    monkeypatch.setattr(StorageBackend, "list_unmounted_devices", lambda self: [])

    view = DashboardView()
    qtbot.addWidget(view)
    qtbot.waitUntil(lambda: len(view._tiles) == 1, timeout=3000)

    view._watcher.storage_changed.emit()
    qtbot.waitUntil(lambda: len(view._tiles) == 2, timeout=3000)

    devices = {t._drive.device for t in view._tiles}
    assert "/dev/sdb1" in devices


def test_dashboard_removes_tile_on_storage_changed(qtbot, monkeypatch):
    from views.dashboard_view import DashboardView

    call_count = [0]

    def fake_list_drives(self):
        call_count[0] += 1
        if call_count[0] == 1:
            return [_drive("/dev/sda1"), _drive("/dev/sdb1", "USB", "/mnt/usb")]
        return [_drive("/dev/sda1")]

    monkeypatch.setattr(StorageBackend, "list_drives", fake_list_drives)
    monkeypatch.setattr(StorageBackend, "list_unmounted_devices", lambda self: [])

    view = DashboardView()
    qtbot.addWidget(view)
    qtbot.waitUntil(lambda: len(view._tiles) == 2, timeout=3000)

    view._watcher.storage_changed.emit()
    qtbot.waitUntil(lambda: len(view._tiles) == 1, timeout=3000)

    devices = {t._drive.device for t in view._tiles}
    assert "/dev/sdb1" not in devices


def test_diff_no_op_preserves_tile_identity(qtbot, monkeypatch):
    """If the device set doesn't change, the same tile objects stay in place."""
    from views.dashboard_view import DashboardView

    monkeypatch.setattr(StorageBackend, "list_drives", lambda self: [_drive("/dev/sda1")])
    monkeypatch.setattr(StorageBackend, "list_unmounted_devices", lambda self: [])

    view = DashboardView()
    qtbot.addWidget(view)
    qtbot.waitUntil(lambda: len(view._tiles) == 1, timeout=3000)

    tile_before = view._tiles[0]
    view._watcher.storage_changed.emit()
    qtbot.wait(400)  # let a refresh cycle complete

    assert view._tiles[0] is tile_before


def test_unmounted_device_appears_in_inactive_section(qtbot, monkeypatch):
    from views.dashboard_view import DashboardView, UnmountedDriveTile

    inactive = UnmountedDrive(
        name="External",
        device="/dev/sdc1",
        size_bytes=2_000_000_000,
        fs_type="ntfs",
        fs_label="",
        is_encrypted=False,
        device_id="sdc1",
    )
    monkeypatch.setattr(StorageBackend, "list_drives", lambda self: [_drive("/dev/sda1")])
    monkeypatch.setattr(StorageBackend, "list_unmounted_devices", lambda self: [inactive])

    view = DashboardView()
    qtbot.addWidget(view)
    qtbot.waitUntil(lambda: len(view._inactive_tiles) == 1, timeout=3000)

    # isVisible() requires the whole parent chain to be shown; isHidden() is
    # the reliable check when the view hasn't been window.show()'d in tests.
    assert not view._inactive_section.isHidden()
    assert isinstance(view._inactive_tiles[0], UnmountedDriveTile)


def test_inactive_section_hidden_when_no_unmounted(qtbot, monkeypatch):
    from views.dashboard_view import DashboardView

    monkeypatch.setattr(StorageBackend, "list_drives", lambda self: [_drive("/dev/sda1")])
    monkeypatch.setattr(StorageBackend, "list_unmounted_devices", lambda self: [])

    view = DashboardView()
    qtbot.addWidget(view)
    qtbot.waitUntil(lambda: view._initial_load_done, timeout=3000)

    assert not view._inactive_section.isVisible()
