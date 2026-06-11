"""Tests for the surgical fix pass (6 fixes).

FIX 1 — SMART: devices_for_mount handles ZFS pools via zpool status -P.
FIX 2 — Pie: exactly one Other category (scan's Other merged into other_bytes).
FIX 3 — Tag deletion: delete_tag cascades through file_tags + package_tags.
FIX 4 — Sidebar DnD: dropEvent emits sidebar_drop_requested with correct target.
FIX 5 — Drive rename: custom name persists by device_id, not mount_point.
FIX 6 — Reduce animations: ui.reduce_animations toggles setAnimated on trees.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from backends.smart_backend import SmartBackend, _resolve_zfs_members


# ══════════════════════════════════════════════════════════════════════════════
# FIX 1 — SMART: ZFS pool device resolution
# ══════════════════════════════════════════════════════════════════════════════

_ZPOOL_STATUS_OUTPUT = """\
  pool: tank
 state: ONLINE
config:

\tNAME        STATE     READ WRITE CKSUM
\ttank        ONLINE       0     0     0
\t  /dev/sdb  ONLINE       0     0     0
\t  /dev/sdc  ONLINE       0     0     0

errors: No known data errors
"""

_ZPOOL_STATUS_PARTITIONED = """\
  pool: data
 state: ONLINE
config:
\tNAME        STATE
\tdata        ONLINE
\t  /dev/sda3 ONLINE
"""

_ZPOOL_STATUS_DISK_BY_ID = """\
  pool: tank
 state: ONLINE
config:
\tNAME                                   STATE
\ttank                                   ONLINE
\t  /dev/disk/by-id/ata-WDC_WD20_12345  ONLINE
"""


def _write_mounts(tmp_path: Path, content: str) -> Path:
    p = tmp_path / "mounts"
    p.write_text(content, encoding="utf-8")
    return p


def test_resolve_zfs_members_parses_dev_paths(monkeypatch):
    monkeypatch.setattr("backends.smart_backend.shutil.which", lambda _: "/usr/sbin/zpool")
    mock_result = MagicMock()
    mock_result.stdout = _ZPOOL_STATUS_OUTPUT
    monkeypatch.setattr("backends.smart_backend.subprocess.run", lambda *a, **kw: mock_result)

    devices = _resolve_zfs_members("tank")
    assert "/dev/sdb" in devices
    assert "/dev/sdc" in devices


def test_resolve_zfs_members_strips_partition_suffix(monkeypatch):
    monkeypatch.setattr("backends.smart_backend.shutil.which", lambda _: "/usr/sbin/zpool")
    mock_result = MagicMock()
    mock_result.stdout = _ZPOOL_STATUS_PARTITIONED
    monkeypatch.setattr("backends.smart_backend.subprocess.run", lambda *a, **kw: mock_result)

    devices = _resolve_zfs_members("data")
    assert "/dev/sda" in devices   # sda3 → sda after strip


def test_resolve_zfs_members_handles_disk_by_id(monkeypatch):
    monkeypatch.setattr("backends.smart_backend.shutil.which", lambda _: "/usr/sbin/zpool")
    mock_result = MagicMock()
    mock_result.stdout = _ZPOOL_STATUS_DISK_BY_ID
    monkeypatch.setattr("backends.smart_backend.subprocess.run", lambda *a, **kw: mock_result)

    devices = _resolve_zfs_members("tank")
    assert any("/dev/disk/by-id/" in d for d in devices)


def test_resolve_zfs_members_returns_empty_when_zpool_missing(monkeypatch):
    monkeypatch.setattr("backends.smart_backend.shutil.which", lambda _: None)
    devices = _resolve_zfs_members("tank")
    assert devices == []


def test_devices_for_mount_zfs_pool(tmp_path, monkeypatch):
    mounts = _write_mounts(tmp_path, "tank /tank zfs rw 0 0\n")
    monkeypatch.setattr("backends.smart_backend.shutil.which", lambda _: "/usr/sbin/zpool")
    mock_result = MagicMock()
    mock_result.stdout = _ZPOOL_STATUS_OUTPUT
    monkeypatch.setattr("backends.smart_backend.subprocess.run", lambda *a, **kw: mock_result)

    backend = SmartBackend(mounts_path=mounts)
    devices = backend.devices_for_mount("/tank")
    assert set(devices) == {"/dev/sdb", "/dev/sdc"}


def test_devices_for_mount_non_dev_fstype_treated_as_pool(tmp_path, monkeypatch):
    """A non-/dev device (no leading /dev/) is treated as a pool name."""
    mounts = _write_mounts(tmp_path, "poolname /mnt/pool zfs rw 0 0\n")
    monkeypatch.setattr("backends.smart_backend.shutil.which", lambda _: "/usr/sbin/zpool")
    mock_result = MagicMock()
    mock_result.stdout = _ZPOOL_STATUS_OUTPUT
    monkeypatch.setattr("backends.smart_backend.subprocess.run", lambda *a, **kw: mock_result)
    backend = SmartBackend(mounts_path=mounts)
    devices = backend.devices_for_mount("/mnt/pool")
    assert len(devices) >= 1


def test_devices_for_mount_single_disk(tmp_path):
    mounts = _write_mounts(tmp_path, "/dev/sda1 / ext4 rw 0 0\n")
    backend = SmartBackend(mounts_path=mounts)
    assert backend.devices_for_mount("/") == ["/dev/sda"]


def test_device_for_mount_compat_shim(tmp_path):
    mounts = _write_mounts(tmp_path, "/dev/sdb1 /mnt/data ext4 rw 0 0\n")
    backend = SmartBackend(mounts_path=mounts)
    assert backend.device_for_mount("/mnt/data") == "/dev/sdb"


# ══════════════════════════════════════════════════════════════════════════════
# FIX 2 — Pie: exactly one "Other" in assembled pie data
# ══════════════════════════════════════════════════════════════════════════════

def test_scan_other_does_not_duplicate_in_legend():
    """_on_scan_finished strips scan's 'Other' so legend never has two Other rows."""
    from views.dashboard_view import AdvancedDriveTile
    from models.storage import Drive

    drive = Drive(
        name="Test", device="/dev/sda", mount_point="/", fs_type="ext4",
        total_bytes=1_000_000_000, used_bytes=600_000_000, free_bytes=400_000_000,
    )
    tile = AdvancedDriveTile(drive)

    # Simulate scan result that includes a scan-level "Other" bucket
    scan_data = {
        "Pictures": 200_000_000,
        "Other":    100_000_000,   # scan's uncategorized bucket
    }
    tile._on_scan_finished(scan_data)

    # Collect legend labels
    labels = []
    for i in range(tile._legend_layout.count()):
        item = tile._legend_layout.itemAt(i)
        if item and item.widget():
            # Each row_widget has a QHBoxLayout; find the name QLabel
            row_layout = item.widget().layout()
            if row_layout:
                for j in range(row_layout.count()):
                    child = row_layout.itemAt(j)
                    if child and child.widget():
                        from PyQt6.QtWidgets import QLabel
                        if isinstance(child.widget(), QLabel) and child.widget().text():
                            labels.append(child.widget().text())

    # No plain "Other" — only "Other (uncategorized)"
    assert "Other" not in labels, f"Raw 'Other' found in legend: {labels}"
    # Must appear exactly once under the renamed label
    from strings import DASHBOARD_OTHER_UNCATEGORIZED
    assert labels.count(DASHBOARD_OTHER_UNCATEGORIZED) == 1, (
        f"Expected exactly one '{DASHBOARD_OTHER_UNCATEGORIZED}', got: {labels}"
    )


def test_scan_other_merged_into_other_bytes():
    """When scan returns 'Other', it's absorbed into other_bytes (no named 'Other' key)."""
    from views.dashboard_view import AdvancedDriveTile
    from models.storage import Drive

    drive = Drive(
        name="Test", device="/dev/sda", mount_point="/", fs_type="ext4",
        total_bytes=1_000_000_000, used_bytes=600_000_000, free_bytes=400_000_000,
    )
    tile = AdvancedDriveTile(drive)

    scan_data = {"Pictures": 100_000_000, "Other": 50_000_000}
    tile._on_scan_finished(scan_data)

    # The pie widget's _named dict must not contain "Other"
    assert "Other" not in tile._pie_widget._named, (
        "Pie widget's _named should not contain 'Other' after _on_scan_finished"
    )


# ══════════════════════════════════════════════════════════════════════════════
# FIX 3 — Tag deletion cascades through file_tags AND package_tags
# ══════════════════════════════════════════════════════════════════════════════

def test_delete_tag_cascades_to_file_tags(tmp_path):
    from backends.tags_backend import TagRepository
    from backends.file_tags_backend import FileTagRepository

    db = tmp_path / "test.db"
    tr = TagRepository(db)
    fr = FileTagRepository(db)

    tr.create_tag("work", "#e74c3c")
    fr.set_assignments("/home/user/doc.txt", {"work"})
    assert len(fr.tags_for_path("/home/user/doc.txt")) == 1

    tr.delete_tag("work")
    assert fr.tags_for_path("/home/user/doc.txt") == []


def test_delete_tag_cascades_to_package_tags(tmp_path):
    from backends.tags_backend import TagRepository

    db = tmp_path / "test.db"
    tr = TagRepository(db)
    tr.create_tag("media", "#2ecc71")
    tr.set_assignments("apt", "vlc", {"media"})
    assert len(tr.tags_for_package("apt", "vlc")) == 1

    tr.delete_tag("media")
    assert tr.tags_for_package("apt", "vlc") == []


def test_delete_tag_removes_both_junctions(tmp_path):
    """Deleting a tag removes it from BOTH file_tags and package_tags in one call."""
    from backends.tags_backend import TagRepository
    from backends.file_tags_backend import FileTagRepository

    db = tmp_path / "test.db"
    tr = TagRepository(db)
    fr = FileTagRepository(db)

    tr.create_tag("shared", "#9b59b6")
    fr.set_assignments("/home/user/photo.jpg", {"shared"})
    tr.set_assignments("apt", "gimp", {"shared"})

    tr.delete_tag("shared")

    assert fr.tags_for_path("/home/user/photo.jpg") == []
    assert tr.tags_for_package("apt", "gimp") == []


# ══════════════════════════════════════════════════════════════════════════════
# FIX 4 — Sidebar DnD: sidebar_drop_requested emitted with correct target_dir
# ══════════════════════════════════════════════════════════════════════════════

def test_sidebar_drop_emits_correct_target_dir(tmp_path):
    """dropEvent on a tree item resolves to its UserRole path."""
    from views.navigation_sidebar import NavigationSidebar
    from PyQt6.QtCore import QMimeData, QPointF, QUrl, Qt
    from PyQt6.QtWidgets import QTreeWidgetItem

    sidebar = NavigationSidebar()

    # Inject a tree item with a known dir path
    target_dir = str(tmp_path)
    item = QTreeWidgetItem([target_dir])
    item.setData(0, Qt.ItemDataRole.UserRole, target_dir)
    sidebar._quick_tree.addTopLevelItem(item)

    emitted: list = []
    sidebar.sidebar_drop_requested.connect(lambda s, t, c: emitted.append((s, t, c)))

    # Simulate the drop by calling _on_drop directly (viewport event filter)
    src_file = tmp_path / "file.txt"
    src_file.write_text("x")

    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(src_file))])

    # Fake event — PyQt6 drag events expose .position() (QPointF), NOT .pos().
    event = MagicMock()
    event.type.return_value = None
    event.mimeData.return_value = mime
    event.position.return_value = QPointF(
        sidebar._quick_tree.visualItemRect(item).center())
    event.modifiers.return_value = Qt.KeyboardModifier.NoModifier

    # Directly test _on_drop
    sidebar._on_drop(sidebar._quick_tree.viewport(), event)

    assert len(emitted) == 1
    sources, tgt, copy = emitted[0]
    assert tgt == target_dir
    assert str(src_file) in sources
    assert copy is False


def test_sidebar_drop_wastebin_emits_trash_sentinel(tmp_path):
    """Dropping onto Wastebin emits TRASH_SENTINEL as target_dir."""
    import strings
    from views.navigation_sidebar import NavigationSidebar
    from PyQt6.QtCore import QMimeData, QPointF, QUrl, Qt

    sidebar = NavigationSidebar()

    emitted: list = []
    sidebar.sidebar_drop_requested.connect(lambda s, t, c: emitted.append((s, t, c)))

    src_file = tmp_path / "file.txt"
    src_file.write_text("x")

    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(src_file))])

    event = MagicMock()
    event.mimeData.return_value = mime
    event.position.return_value = QPointF(sidebar._quick_tree.visualItemRect(
        sidebar._wastebin_item
    ).center())
    event.modifiers.return_value = Qt.KeyboardModifier.NoModifier

    sidebar._on_drop(sidebar._quick_tree.viewport(), event)

    assert len(emitted) == 1
    _, tgt, _ = emitted[0]
    assert tgt == strings.TRASH_SENTINEL


def test_sidebar_drop_ctrl_sets_copy_flag(tmp_path):
    """Ctrl held during drop → copy=True."""
    from views.navigation_sidebar import NavigationSidebar
    from PyQt6.QtCore import QMimeData, QPointF, QUrl, Qt
    from PyQt6.QtWidgets import QTreeWidgetItem

    sidebar = NavigationSidebar()
    target_dir = str(tmp_path)
    item = QTreeWidgetItem([target_dir])
    item.setData(0, Qt.ItemDataRole.UserRole, target_dir)
    sidebar._quick_tree.addTopLevelItem(item)

    emitted: list = []
    sidebar.sidebar_drop_requested.connect(lambda s, t, c: emitted.append((s, t, c)))

    src_file = tmp_path / "a.txt"
    src_file.write_text("x")
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(src_file))])

    event = MagicMock()
    event.mimeData.return_value = mime
    event.position.return_value = QPointF(
        sidebar._quick_tree.visualItemRect(item).center())
    event.modifiers.return_value = Qt.KeyboardModifier.ControlModifier

    sidebar._on_drop(sidebar._quick_tree.viewport(), event)

    assert emitted[0][2] is True  # copy flag


# ══════════════════════════════════════════════════════════════════════════════
# FIX 5 — Drive custom name persists by device_id
# ══════════════════════════════════════════════════════════════════════════════

def test_drive_label_saved_by_device_id(tmp_path):
    """LabelModal._save() writes device_id, not mount_point, as the key."""
    from models.database import open_db
    from models.storage import Drive
    from views.dashboard_view import LabelModal

    drive = Drive(
        name="External SSD", device="/dev/sdb1", mount_point="/mnt/ext",
        fs_type="ext4", total_bytes=1_000_000_000,
        used_bytes=500_000_000, free_bytes=500_000_000,
        device_id="wwn-0x12345",
    )
    db = tmp_path / "test.db"
    modal = LabelModal(drive, db_path=db)
    modal._label_edit.setText("My Backup Drive")
    modal._save()

    with open_db(db) as conn:
        row = conn.execute(
            "SELECT label, device_id FROM drive_labels WHERE device_id = ?",
            ("wwn-0x12345",),
        ).fetchone()

    assert row is not None, "No row saved"
    assert row["label"] == "My Backup Drive"
    assert row["device_id"] == "wwn-0x12345"


def test_drive_label_not_keyed_by_mount_point(tmp_path):
    """The drive_labels table has no mount_point column — keyed by device_id."""
    from models.database import open_db

    db = tmp_path / "schema.db"
    with open_db(db) as conn:
        cols = {
            row[1]
            for row in conn.execute(
                "PRAGMA table_info(drive_labels)"
            ).fetchall()
        }
    assert "device_id" in cols
    assert "mount_point" not in cols


# ══════════════════════════════════════════════════════════════════════════════
# FIX 6 — Reduce animations toggles setAnimated on the sidebar trees
# ══════════════════════════════════════════════════════════════════════════════

def test_reduce_animations_off_trees_are_animated(tmp_path, monkeypatch):
    """When ui.reduce_animations=false, both trees stay animated (default)."""
    from views.navigation_sidebar import NavigationSidebar
    from backends.settings_backend import SettingsRepository

    db = tmp_path / "s.db"
    SettingsRepository(db).set("ui.reduce_animations", "false")
    monkeypatch.setattr(
        "views.navigation_sidebar.SettingsRepository",
        lambda _db=None: SettingsRepository(db),
    )

    sidebar = NavigationSidebar()
    sidebar.apply_animation_setting()

    assert sidebar._quick_tree.isAnimated() is True
    assert sidebar._drives_tree.isAnimated() is True


def test_reduce_animations_on_trees_not_animated(tmp_path, monkeypatch):
    """When ui.reduce_animations=true, both trees have animation disabled."""
    from views.navigation_sidebar import NavigationSidebar
    from backends.settings_backend import SettingsRepository

    db = tmp_path / "s.db"
    SettingsRepository(db).set("ui.reduce_animations", "true")
    monkeypatch.setattr(
        "views.navigation_sidebar.SettingsRepository",
        lambda _db=None: SettingsRepository(db),
    )

    sidebar = NavigationSidebar()
    sidebar.apply_animation_setting()

    assert sidebar._quick_tree.isAnimated() is False
    assert sidebar._drives_tree.isAnimated() is False


def test_configure_dialog_reads_reduce_anim_setting(tmp_path):
    """ConfigureDialog reads ui.reduce_animations and initialises checkbox."""
    from views.configure_dialog import ConfigureDialog
    from backends.settings_backend import SettingsRepository

    db = tmp_path / "s.db"
    SettingsRepository(db).set("ui.reduce_animations", "true")

    dlg = ConfigureDialog(db_path=db)
    assert dlg._reduce_anim_cb.isChecked() is True


def test_configure_dialog_writes_reduce_anim_setting(tmp_path):
    """ConfigureDialog._on_ok() writes ui.reduce_animations."""
    from views.configure_dialog import ConfigureDialog
    from backends.settings_backend import SettingsRepository

    db = tmp_path / "s.db"
    dlg = ConfigureDialog(db_path=db)
    dlg._reduce_anim_cb.setChecked(True)
    dlg._on_ok()

    assert SettingsRepository(db).get("ui.reduce_animations") == "true"
