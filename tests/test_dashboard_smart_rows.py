"""Regression: AdvancedDriveTile SMART-finish path must not crash.

Bug: views/dashboard_view.py used `Path(device).name` in
_add_smart_device_rows (the multi-device SMART/ZFS row builder) but never
imported pathlib.Path → NameError → crash on entering Dashboard Advanced mode
(and a crash-loop when Advanced was the persisted view).

The existing suite missed this because it never drove the SMART *finish* path
(_on_smart_finished → _add_smart_device_rows). These tests exercise it directly
with a mock device path + SmartData, in both the multi=True (per-device label,
the regression line) and permission-denied fallback branches.
"""
from __future__ import annotations

import pytest

from backends.smart_backend import SmartData
from models.storage import Drive
from views.dashboard_view import AdvancedDriveTile


def _make_drive() -> Drive:
    return Drive(
        name="Test Drive",
        device="/dev/sda1",
        mount_point="/mnt/test",
        total_bytes=1000,
        used_bytes=400,
        free_bytes=600,
        fs_type="ext4",
    )


def _make_tile() -> AdvancedDriveTile:
    return AdvancedDriveTile(_make_drive())


def test_add_smart_device_rows_multi_does_not_raise():
    """multi=True builds the per-device label via Path(device).name (regression)."""
    tile = _make_tile()
    before = tile._smart_layout.count()

    # Must not raise NameError on Path(...) nor TypeError on the SmartData fields.
    tile._add_smart_device_rows(
        "/dev/sda1",
        SmartData(
            health="PASSED",
            power_on_hours=12_345,
            temperature_c=38,
            reallocated_sectors=0,
        ),
        multi=True,
    )

    # At least the health row was appended.
    assert tile._smart_layout.count() > before


def test_add_smart_device_rows_multi_permission_denied_fallback():
    """permission_denied renders the no-perm label + how-to button without crashing."""
    tile = _make_tile()
    before = tile._smart_layout.count()

    tile._add_smart_device_rows(
        "/dev/sdb1",
        SmartData(health="permission_denied"),
        multi=True,
    )

    # No-perm label + how-to button = two new widgets.
    assert tile._smart_layout.count() == before + 2


def test_on_smart_finished_multi_results_does_not_raise():
    """Full finish path with >1 device (sets multi=True internally)."""
    tile = _make_tile()

    results = [
        ("/dev/sda", SmartData(health="PASSED", temperature_c=40)),
        ("/dev/sdb", SmartData(health="permission_denied")),
    ]
    # _on_smart_finished clears the layout then fans out to _add_smart_device_rows.
    tile._on_smart_finished(results)

    assert tile._smart_layout.count() > 0
