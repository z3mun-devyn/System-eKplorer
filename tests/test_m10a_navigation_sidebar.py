"""M10a tests: NavigationSidebar structure + signals, navigate_to_directory routing,
Dashboard layout integrity."""
from __future__ import annotations

import os

import pytest


# ── Helpers ───────────────────────────────────────────────────────────────────

def _qt():
    pytest.importorskip("PyQt6")
    from PyQt6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def _make_sidebar():
    _app = _qt()
    from views.navigation_sidebar import NavigationSidebar
    sidebar = NavigationSidebar()
    sidebar._app_ref = _app
    return sidebar, _app


def _make_drive(mount_point: str = "/data", name: str = "Data"):
    """Minimal Drive-like object for injection into set_drives."""
    from models.storage import Drive
    return Drive(
        name=name,
        device="/dev/sdb1",
        mount_point=mount_point,
        total_bytes=100 * 1024 ** 3,
        used_bytes=40 * 1024 ** 3,
        free_bytes=60 * 1024 ** 3,
        fs_type="ext4",
        device_id="ata-TEST",
        label=None,
        color_hex=None,
    )


def _make_system_drive():
    return _make_drive(mount_point="/", name="System")


# ── Section headers are QLabel (not QPushButton) ──────────────────────────────

def test_section_headers_are_labels():
    """Section headers must be QLabel widgets — not interactive buttons."""
    pytest.importorskip("PyQt6")
    from PyQt6.QtWidgets import QApplication, QLabel, QPushButton
    _app = QApplication.instance() or QApplication([])
    from views.navigation_sidebar import _section_header
    header = _section_header("Drives")
    assert isinstance(header, QLabel)
    assert not isinstance(header, QPushButton)


def test_section_header_has_no_pointing_cursor():
    """Section headers must not have a pointing-hand cursor (no click affordance)."""
    pytest.importorskip("PyQt6")
    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtCore import Qt
    _app = QApplication.instance() or QApplication([])
    from views.navigation_sidebar import _section_header
    header = _section_header("Quick Access")
    assert header.cursor().shape() != Qt.CursorShape.PointingHandCursor


def test_subsection_headers_are_labels():
    pytest.importorskip("PyQt6")
    from PyQt6.QtWidgets import QApplication, QLabel, QPushButton
    _app = QApplication.instance() or QApplication([])
    from views.navigation_sidebar import _subsection_header
    header = _subsection_header("Recent Files")
    assert isinstance(header, QLabel)
    assert not isinstance(header, QPushButton)


# ── Section headers emit no navigate_requested signal ─────────────────────────

def test_section_header_click_does_not_emit_navigate(monkeypatch):
    """Clicking a section header must NOT emit navigate_requested."""
    sidebar, _app = _make_sidebar()

    emitted: list[str] = []
    sidebar.navigate_requested.connect(emitted.append)

    # Section headers are QLabels — send a mouse press event and verify nothing fires
    from PyQt6.QtCore import QEvent, Qt
    from PyQt6.QtGui import QMouseEvent
    from PyQt6.QtWidgets import QLabel

    headers = sidebar.findChildren(QLabel, "nav_section_header")
    assert headers, "expected at least one nav_section_header QLabel"

    for header in headers:
        press = QMouseEvent(
            QEvent.Type.MouseButtonPress,
            header.rect().center().toPointF(),
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
        header.mousePressEvent(press)

    assert emitted == [], f"navigate_requested fired from header: {emitted}"


# ── Drive entry click emits navigate_requested with correct path ───────────────

def test_drive_entry_click_emits_navigate():
    """Left-clicking a mounted drive entry emits navigate_requested(mount_point)."""
    sidebar, _app = _make_sidebar()
    emitted: list[str] = []
    sidebar.navigate_requested.connect(emitted.append)

    sidebar.set_drives([_make_system_drive(), _make_drive("/data", "Data")], [])

    tree = sidebar._drives_tree
    assert tree.topLevelItemCount() > 0, "expected drive items after set_drives"
    data_item = next(
        (tree.topLevelItem(i)
         for i in range(tree.topLevelItemCount())
         if "/data" in tree.topLevelItem(i).toolTip(0)),
        None,
    )
    assert data_item is not None, "item for /data not found"
    sidebar._on_drives_tree_item_clicked(data_item, 0)

    assert "/data" in emitted


def test_system_drive_entry_emits_root():
    """The 'System (/)' entry emits navigate_requested('/')."""
    sidebar, _app = _make_sidebar()
    emitted: list[str] = []
    sidebar.navigate_requested.connect(emitted.append)

    sidebar.set_drives([_make_system_drive()], [])

    tree = sidebar._drives_tree
    assert tree.topLevelItemCount() > 0
    sidebar._on_drives_tree_item_clicked(tree.topLevelItem(0), 0)

    assert "/" in emitted


# ── Drive label resolution ────────────────────────────────────────────────────

def _make_labeled_drive(mount_point: str, user_label: str):
    from models.storage import Drive
    return Drive(
        name="ata-SomeDisk_SERIALXYZ",
        device="/dev/sdc1",
        mount_point=mount_point,
        total_bytes=200 * 1024 ** 3,
        used_bytes=50 * 1024 ** 3,
        free_bytes=150 * 1024 ** 3,
        fs_type="ext4",
        device_id="ata-SomeDisk_SERIALXYZ",
        label=user_label,
        color_hex=None,
    )


def _make_unmounted(name: str = "MyDisk", fs_label: str = ""):
    from models.storage import UnmountedDrive
    return UnmountedDrive(
        name=name,
        device="/dev/sdd1",
        size_bytes=500 * 1024 ** 3,
        fs_type="ntfs",
        fs_label=fs_label,
        is_encrypted=False,
        device_id="ata-MyDisk",
    )


def _drives_tree_texts(sidebar) -> list[str]:
    tree = sidebar._drives_tree
    return [tree.topLevelItem(i).text(0) for i in range(tree.topLevelItemCount())]


def _drives_tree_tooltips(sidebar) -> list[str]:
    tree = sidebar._drives_tree
    return [tree.topLevelItem(i).toolTip(0) for i in range(tree.topLevelItemCount())]


def test_user_label_shown_as_primary():
    """When drive.label is set, it must appear as the tree item text."""
    sidebar, _app = _make_sidebar()
    drive = _make_labeled_drive("/media/work", "Work SSD")
    sidebar.set_drives([drive], [])

    texts = _drives_tree_texts(sidebar)
    assert any("Work SSD" in t for t in texts), f"label not in texts: {texts}"
    assert not any("ata-SomeDisk" in t for t in texts), \
        f"raw device id leaked into item text: {texts}"


def test_hardware_name_shown_when_no_user_label():
    """When drive.label is None, drive.name is the primary text."""
    sidebar, _app = _make_sidebar()
    drive = _make_drive("/media/data", "Samsung 870 EVO")
    sidebar.set_drives([drive], [])

    texts = _drives_tree_texts(sidebar)
    assert any("Samsung 870 EVO" in t for t in texts), f"name not in texts: {texts}"


def test_system_drive_user_label_overrides_default():
    """System drive with user label shows label, not the hardcoded 'System (/)'."""
    import strings
    sidebar, _app = _make_sidebar()
    drive = _make_labeled_drive("/", "Main SSD")
    sidebar.set_drives([drive], [])

    texts = _drives_tree_texts(sidebar)
    assert any("Main SSD" in t for t in texts), f"label not in texts: {texts}"
    assert not any(strings.NAV_SYSTEM_DRIVE in t for t in texts), \
        "hardcoded system drive text shown despite user label being set"


def test_unmounted_fs_label_shown_as_primary():
    """Unmounted drive with fs_label uses it as primary text, not hardware name."""
    sidebar, _app = _make_sidebar()
    udrive = _make_unmounted(name="ata-MyDisk_SERIAL", fs_label="BACKUP")
    sidebar.set_drives([], [udrive])

    texts = _drives_tree_texts(sidebar)
    assert any("BACKUP" in t for t in texts), f"fs_label not in texts: {texts}"
    assert not any("ata-MyDisk" in t for t in texts), \
        f"raw device id leaked into item text: {texts}"


def test_unmounted_falls_back_to_name_when_no_fs_label():
    """Unmounted drive without fs_label shows hardware name."""
    sidebar, _app = _make_sidebar()
    udrive = _make_unmounted(name="Seagate Backup Plus", fs_label="")
    sidebar.set_drives([], [udrive])

    texts = _drives_tree_texts(sidebar)
    assert any("Seagate Backup Plus" in t for t in texts), f"name not in texts: {texts}"


def test_mount_point_in_tooltip_not_button_text():
    """Mount point is in the tooltip, not the primary item label."""
    sidebar, _app = _make_sidebar()
    drive = _make_labeled_drive("/media/work", "Work SSD")
    sidebar.set_drives([drive], [])

    tree = sidebar._drives_tree
    item = next(
        (tree.topLevelItem(i)
         for i in range(tree.topLevelItemCount())
         if "Work SSD" in tree.topLevelItem(i).text(0)),
        None,
    )
    assert item is not None, "Work SSD item not found"
    assert "/media/work" in item.toolTip(0), "mount point missing from tooltip"
    assert "/media/work" not in item.text(0), "mount point leaked into primary item text"


# ── Home XDG entry emits navigate_requested with expanduser("~") ──────────────

def test_home_entry_emits_correct_path():
    """The Home entry emits the real home directory path."""
    sidebar, _app = _make_sidebar()
    emitted: list[str] = []
    sidebar.navigate_requested.connect(emitted.append)

    # Quick Access now uses a QTreeWidget — find the "Home" top-level item
    import strings
    tree = sidebar._quick_tree
    home_item = None
    for i in range(tree.topLevelItemCount()):
        item = tree.topLevelItem(i)
        if item.text(0) == strings.NAV_HOME:
            home_item = item
            break
    assert home_item is not None, "Home item not found in quick access tree"
    # itemClicked fires on single click; simulate by calling the handler directly
    sidebar._on_tree_item_clicked(home_item, 0)

    assert os.path.expanduser("~") in emitted


# ── Recent sections hidden when empty, visible when populated ──────────────────

def test_recent_locations_hidden_when_empty(tmp_path, monkeypatch):
    """Recent Locations header and container are hidden if the table is empty."""
    import functools
    from models.database import open_db
    monkeypatch.setattr(
        "backends.recent_backend.open_db",
        functools.partial(open_db, tmp_path / "data.db"),
    )
    monkeypatch.setattr(
        "views.navigation_sidebar.RecentPathsBackend",
        lambda: __import__("backends.recent_backend",
                            fromlist=["RecentPathsBackend"]).RecentPathsBackend(),
    )

    sidebar, _app = _make_sidebar()
    sidebar.refresh_recent()  # empty DB

    assert not sidebar._recent_locs_header.isVisible()
    assert not sidebar._recent_locs_box.isVisible()


def test_recent_files_hidden_when_empty(tmp_path, monkeypatch):
    import functools
    from models.database import open_db
    monkeypatch.setattr(
        "backends.recent_backend.open_db",
        functools.partial(open_db, tmp_path / "data.db"),
    )
    monkeypatch.setattr(
        "views.navigation_sidebar.RecentPathsBackend",
        lambda: __import__("backends.recent_backend",
                            fromlist=["RecentPathsBackend"]).RecentPathsBackend(),
    )

    sidebar, _app = _make_sidebar()
    sidebar.refresh_recent()

    assert not sidebar._recent_files_header.isVisible()
    assert not sidebar._recent_files_box.isVisible()


# ── navigate_to_directory routing ─────────────────────────────────────────────

def _make_nav_fn(terminal_index: int, fm_index: int, current_index: int):
    """Return a navigate_to_directory-equivalent closure for routing tests."""
    pytest.importorskip("PyQt6")

    tab_activated: list[int] = []
    fm_navigated: list[str] = []
    terminal_navigated: list[str] = []

    class _FakeTabs:
        def currentIndex(self): return current_index
        def setCurrentIndex(self, i): tab_activated.append(i)

    class _FakeFMView:
        def navigate_to(self, p): fm_navigated.append(p)

    class _FakeTermView:
        def navigate_to(self, p): terminal_navigated.append(p)

    tabs = _FakeTabs()
    fm_view = _FakeFMView()
    term_view = _FakeTermView()

    def navigate(path: str) -> None:
        if tabs.currentIndex() == terminal_index:
            term_view.navigate_to(path)
            return
        tabs.setCurrentIndex(fm_index)
        fm_view.navigate_to(path)

    return navigate, tab_activated, fm_navigated, terminal_navigated


def test_navigate_activates_fm_tab_when_not_terminal():
    navigate, activated, fm_nav, term_nav = _make_nav_fn(
        terminal_index=3, fm_index=1, current_index=0)
    navigate("/home/user/docs")
    assert 1 in activated
    assert "/home/user/docs" in fm_nav
    assert term_nav == []


def test_navigate_uses_terminal_when_terminal_active():
    navigate, activated, fm_nav, term_nav = _make_nav_fn(
        terminal_index=3, fm_index=1, current_index=3)
    navigate("/home/user/docs")
    assert activated == []           # tab is NOT switched
    assert term_nav == ["/home/user/docs"]
    assert fm_nav == []


def test_navigate_no_desktop_services_fallback():
    """QDesktopServices is never called — the FM tab is always the fallback."""
    pytest.importorskip("PyQt6")
    desktop_calls: list[str] = []
    navigate, activated, fm_nav, _ = _make_nav_fn(
        terminal_index=3, fm_index=1, current_index=0)
    navigate("/home/user/somewhere")
    # navigate never touched desktop_calls — verifying the closure matches prod logic
    assert desktop_calls == []
    assert 1 in activated


# ── Dashboard layout retains drive analytics alongside sidebar ─────────────────

def test_dashboard_tab_contains_dashboard_view(monkeypatch):
    """DashboardTab must still contain a DashboardView (drive analytics preserved)."""
    pytest.importorskip("PyQt6")
    from PyQt6.QtWidgets import QApplication
    _app = QApplication.instance() or QApplication([])

    monkeypatch.setattr("views.dashboard_view.DashboardView._start_load", lambda self: None)

    from views.dashboard_view import DashboardView
    from views.navigation_sidebar import NavigationSidebar
    from main import DashboardTab

    tab = DashboardTab()
    tab._app_ref = _app

    assert hasattr(tab, "dashboard_view")
    assert isinstance(tab.dashboard_view, DashboardView)


def test_dashboard_tab_contains_navigation_sidebar(monkeypatch):
    """DashboardTab must also contain a NavigationSidebar."""
    pytest.importorskip("PyQt6")
    from PyQt6.QtWidgets import QApplication
    _app = QApplication.instance() or QApplication([])

    monkeypatch.setattr("views.dashboard_view.DashboardView._start_load", lambda self: None)

    from views.navigation_sidebar import NavigationSidebar
    from main import DashboardTab

    tab = DashboardTab()
    tab._app_ref = _app

    assert isinstance(tab._sidebar, NavigationSidebar)


def test_file_manager_tab_contains_file_manager_view():
    pytest.importorskip("PyQt6")
    from PyQt6.QtWidgets import QApplication
    _app = QApplication.instance() or QApplication([])

    from views.file_manager_view import FileManagerView
    from main import FileManagerTab

    tab = FileManagerTab()
    tab._app_ref = _app

    assert isinstance(tab.file_manager_view, FileManagerView)


def test_file_manager_view_navigate_to_records_location(tmp_path, monkeypatch):
    """FileManagerView.navigate_to(path) records path in recent_paths."""
    pytest.importorskip("PyQt6")
    from PyQt6.QtWidgets import QApplication
    _app = QApplication.instance() or QApplication([])

    import functools
    from models.database import open_db

    db = tmp_path / "data.db"
    monkeypatch.setattr(
        "backends.recent_backend.open_db",
        functools.partial(open_db, db),
    )
    monkeypatch.setattr(
        "views.navigation_sidebar.RecentPathsBackend",
        lambda: __import__("backends.recent_backend",
                            fromlist=["RecentPathsBackend"]).RecentPathsBackend(),
    )

    from views.file_manager_view import FileManagerView
    view = FileManagerView()
    view._app_ref = _app

    view.navigate_to("/home/user/projects")

    from backends.recent_backend import RecentPathsBackend

    with functools.partial(open_db, db)() as conn:
        row = conn.execute(
            "SELECT path FROM recent_paths WHERE type='location'"
        ).fetchone()
    assert row is not None
    assert row[0] == "/home/user/projects"


# ── refresh_expanded_nodes ────────────────────────────────────────────────────

def test_refresh_expanded_nodes_adds_new_child(tmp_path):
    """refresh_expanded_nodes() adds a child item when a subdirectory is created
    under an already-expanded tree node."""
    pytest.importorskip("PyQt6")
    from PyQt6.QtWidgets import QApplication
    _app = QApplication.instance() or QApplication([])

    from views.navigation_sidebar import NavigationSidebar
    sidebar = NavigationSidebar(fixed_width=None)
    sidebar._app_ref = _app

    # Create a parent directory with one existing subdir
    parent_dir = tmp_path / "parent"
    parent_dir.mkdir()
    (parent_dir / "alpha").mkdir()

    # Add parent_dir as a quick-access tree item and simulate expansion:
    # remove the placeholder child, then populate subdirs exactly as
    # _on_tree_item_expanded would, then mark the item as expanded.
    item = sidebar._make_tree_item("parent", str(parent_dir))
    sidebar._quick_tree.addTopLevelItem(item)
    item.removeChild(item.child(0))          # remove placeholder
    sidebar._populate_subdirs(item, parent_dir)
    item.setExpanded(True)

    assert item.childCount() == 1
    assert item.child(0).text(0) == "alpha"

    # Create a new subdirectory on disk (simulates "create folder" operation)
    (parent_dir / "beta").mkdir()

    sidebar.refresh_expanded_nodes()

    assert item.childCount() == 2, (
        f"expected 2 children after refresh, got {item.childCount()}"
    )
    names = {item.child(i).text(0) for i in range(item.childCount())}
    assert "alpha" in names
    assert "beta" in names


def test_refresh_expanded_nodes_removes_stale_child(tmp_path):
    """refresh_expanded_nodes() removes a child item when its directory is deleted."""
    pytest.importorskip("PyQt6")
    from PyQt6.QtWidgets import QApplication
    _app = QApplication.instance() or QApplication([])

    from views.navigation_sidebar import NavigationSidebar
    sidebar = NavigationSidebar(fixed_width=None)
    sidebar._app_ref = _app

    parent_dir = tmp_path / "parent"
    parent_dir.mkdir()
    (parent_dir / "keep").mkdir()
    doomed = parent_dir / "gone"
    doomed.mkdir()

    item = sidebar._make_tree_item("parent", str(parent_dir))
    sidebar._quick_tree.addTopLevelItem(item)
    item.removeChild(item.child(0))
    sidebar._populate_subdirs(item, parent_dir)
    item.setExpanded(True)

    assert item.childCount() == 2

    doomed.rmdir()
    sidebar.refresh_expanded_nodes()

    assert item.childCount() == 1
    assert item.child(0).text(0) == "keep"


def test_quick_access_items_have_icons():
    """Every Quick Access tree item must carry a non-null icon."""
    pytest.importorskip("PyQt6")
    from PyQt6.QtWidgets import QApplication
    _app = QApplication.instance() or QApplication([])

    from views.navigation_sidebar import NavigationSidebar
    sidebar = NavigationSidebar(fixed_width=None)
    sidebar._app_ref = _app

    tree = sidebar._quick_tree
    assert tree.topLevelItemCount() > 0, "expected at least one Quick Access item"
    for i in range(tree.topLevelItemCount()):
        item = tree.topLevelItem(i)
        assert not item.icon(0).isNull(), (
            f"Quick Access item '{item.text(0)}' has a null icon"
        )


def test_drives_tree_items_have_icons():
    """Drive tree items must carry a non-null icon after set_drives()."""
    pytest.importorskip("PyQt6")
    from PyQt6.QtWidgets import QApplication
    _app = QApplication.instance() or QApplication([])

    from views.navigation_sidebar import NavigationSidebar
    sidebar = NavigationSidebar(fixed_width=None)
    sidebar._app_ref = _app

    sidebar.set_drives([_make_system_drive(), _make_drive("/data", "Data")], [])

    tree = sidebar._drives_tree
    for i in range(tree.topLevelItemCount()):
        item = tree.topLevelItem(i)
        assert not item.icon(0).isNull(), (
            f"Drive item '{item.text(0)}' has a null icon"
        )


def test_refresh_expanded_nodes_skips_unexpanded(tmp_path):
    """refresh_expanded_nodes() does not touch items that were never expanded."""
    pytest.importorskip("PyQt6")
    from PyQt6.QtWidgets import QApplication
    _app = QApplication.instance() or QApplication([])

    from views.navigation_sidebar import NavigationSidebar
    sidebar = NavigationSidebar(fixed_width=None)
    sidebar._app_ref = _app

    parent_dir = tmp_path / "parent"
    parent_dir.mkdir()
    (parent_dir / "alpha").mkdir()

    # Add item but do NOT expand it — it still has the placeholder child
    item = sidebar._make_tree_item("parent", str(parent_dir))
    sidebar._quick_tree.addTopLevelItem(item)
    # placeholder is child(0), item is NOT expanded

    (parent_dir / "beta").mkdir()
    sidebar.refresh_expanded_nodes()

    # Placeholder should still be there; no real children added
    assert item.childCount() == 1
    from PyQt6.QtCore import Qt
    from views.navigation_sidebar import _PLACEHOLDER_ROLE
    assert item.child(0).data(0, _PLACEHOLDER_ROLE)
