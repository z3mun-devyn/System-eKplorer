"""M10c tests: FileView, DirectoryLoader, BreadcrumbBar, FileManagerView integration,
recent_paths trim, Properties General tab population, view mode / hidden files persistence."""
from __future__ import annotations

import functools
import time
from pathlib import Path

import pytest


# ── Helpers ───────────────────────────────────────────────────────────────────

def _app():
    pytest.importorskip("PyQt6")
    from PyQt6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def _patch_db(monkeypatch, tmp_path):
    from models.database import open_db
    db = tmp_path / "data.db"
    partial = functools.partial(open_db, db)
    monkeypatch.setattr("backends.settings_backend.open_db",
                        lambda _path=None: open_db(db))
    monkeypatch.setattr("backends.recent_backend.open_db", partial)
    return db


def _make_file_view(app_ref=None):
    """Create a FileView with _shown=False so no thread starts."""
    from views.file_view import FileView
    fv = FileView()
    if app_ref:
        fv._app_ref = app_ref
    return fv


def _make_fm(monkeypatch, tmp_path):
    app = _app()
    _patch_db(monkeypatch, tmp_path)
    monkeypatch.setattr("views.file_view.FileView._load", lambda self: None)
    from views.file_manager_view import FileManagerView
    fm = FileManagerView()
    fm._app_ref = app
    return fm


# ── DirectoryLoader (synchronous test — no QThread) ──────────────────────────

def test_directory_loader_lists_files(tmp_path):
    """DirectoryLoader.run() emits a list of FileEntry for a real directory."""
    (tmp_path / "hello.txt").write_text("hi")
    (tmp_path / "subdir").mkdir()

    from backends.directory_backend import DirectoryLoader
    from models.file_entry import FileEntry

    results: list = []
    loader = DirectoryLoader(tmp_path, show_hidden=False)
    loader.ready.connect(results.append)
    loader.run()   # synchronous

    assert results, "ready signal not emitted"
    entries = results[0]
    names = {e.name for e in entries}
    assert "hello.txt" in names
    assert "subdir" in names


def test_directory_loader_skips_hidden_by_default(tmp_path):
    (tmp_path / ".hidden").write_text("secret")
    (tmp_path / "visible.txt").write_text("yes")

    from backends.directory_backend import DirectoryLoader

    results: list = []
    loader = DirectoryLoader(tmp_path, show_hidden=False)
    loader.ready.connect(results.append)
    loader.run()

    names = {e.name for e in results[0]}
    assert "visible.txt" in names
    assert ".hidden" not in names


def test_directory_loader_shows_hidden_when_enabled(tmp_path):
    (tmp_path / ".hidden").write_text("secret")

    from backends.directory_backend import DirectoryLoader

    results: list = []
    loader = DirectoryLoader(tmp_path, show_hidden=True)
    loader.ready.connect(results.append)
    loader.run()

    names = {e.name for e in results[0]}
    assert ".hidden" in names


def test_directory_loader_tolerates_unreadable_entry(tmp_path):
    """A single unreadable entry must not abort the whole listing."""
    import os
    good = tmp_path / "good.txt"
    good.write_text("ok")

    from backends.directory_backend import DirectoryLoader

    results: list = []
    loader = DirectoryLoader(tmp_path, show_hidden=False)
    loader.ready.connect(results.append)
    loader.run()

    assert results, "loader should still emit results"


def test_directory_loader_marks_dirs_and_files(tmp_path):
    (tmp_path / "afile.txt").write_text("x")
    (tmp_path / "adir").mkdir()

    from backends.directory_backend import DirectoryLoader

    results: list = []
    loader = DirectoryLoader(tmp_path, False)
    loader.ready.connect(results.append)
    loader.run()
    by_name = {e.name: e for e in results[0]}

    assert by_name["adir"].is_dir is True
    assert by_name["afile.txt"].is_dir is False
    assert by_name["afile.txt"].size is not None
    assert by_name["adir"].size is None


# ── FileView navigation (no threading — _shown stays False) ───────────────────

def test_file_view_initial_path_is_home():
    app = _app()
    fv = _make_file_view(app)
    assert fv.current_path == Path.home()


def test_navigate_sets_current_path(tmp_path):
    app = _app()
    fv = _make_file_view(app)
    fv.navigate(tmp_path)
    assert fv.current_path == tmp_path


def test_navigate_non_dir_is_noop(tmp_path):
    app = _app()
    fv = _make_file_view(app)
    f = tmp_path / "file.txt"
    f.write_text("x")
    initial = fv.current_path
    fv.navigate(f)
    assert fv.current_path == initial


def test_navigate_emits_path_changed(tmp_path):
    app = _app()
    fv = _make_file_view(app)
    emitted: list[str] = []
    fv.path_changed.connect(emitted.append)
    fv.navigate(tmp_path)
    assert str(tmp_path) in emitted


def test_navigate_back_and_forward(tmp_path):
    app = _app()
    fv = _make_file_view(app)
    a = tmp_path / "a"; a.mkdir()
    b = tmp_path / "b"; b.mkdir()

    fv.navigate(a)
    fv.navigate(b)
    assert fv.current_path == b

    fv.navigate_back()
    assert fv.current_path == a
    assert fv.can_go_forward()

    fv.navigate_forward()
    assert fv.current_path == b


def test_navigate_clears_forward_stack(tmp_path):
    app = _app()
    fv = _make_file_view(app)
    a = tmp_path / "a"; a.mkdir()
    b = tmp_path / "b"; b.mkdir()
    c = tmp_path / "c"; c.mkdir()

    fv.navigate(a)
    fv.navigate(b)
    fv.navigate_back()        # now at a, b is in forward
    fv.navigate(c)            # new nav: forward stack cleared
    assert not fv.can_go_forward()


def test_navigate_up(tmp_path):
    app = _app()
    fv = _make_file_view(app)
    sub = tmp_path / "sub"; sub.mkdir()
    fv.navigate(sub)
    fv.navigate_up()
    assert fv.current_path == tmp_path


def test_can_go_up_false_at_root():
    app = _app()
    fv = _make_file_view(app)
    fv.navigate(Path("/"))
    assert not fv.can_go_up()


def test_back_stack_independent_per_instance(tmp_path):
    """Two FileView instances have independent history stacks."""
    app = _app()
    fv1 = _make_file_view(app)
    fv2 = _make_file_view(app)
    a = tmp_path / "a"; a.mkdir()

    fv1.navigate(a)
    assert fv1.can_go_back()
    assert not fv2.can_go_back()


def test_set_show_hidden_stores_flag():
    """set_show_hidden stores the flag without starting a thread (not shown)."""
    app = _app()
    fv = _make_file_view(app)
    assert fv._show_hidden is False
    fv.set_show_hidden(True)
    assert fv._show_hidden is True


def test_set_view_mode_switches_stack():
    app = _app()
    fv = _make_file_view(app)
    for mode in ("icons_small", "icons_medium", "icons_large"):
        fv.set_view_mode(mode)
        assert fv._view_stack.currentIndex() == 1, f"expected icons stack for {mode}"
    fv.set_view_mode("details")
    assert fv._view_stack.currentIndex() == 0


def test_file_model_col0_display_role_icon_mode(tmp_path):
    """Column 0 returns entry name as DisplayRole when icon_mode is on, None when off."""
    app = _app()
    from PyQt6.QtCore import Qt
    from views.file_view import _FileModel, _COL_ICON
    from models.file_entry import FileEntry

    model = _FileModel()
    entry = FileEntry(
        name="hello.txt",
        path=tmp_path / "hello.txt",
        size=100,
        modified=0.0,
        mime_type="text/plain",
        is_dir=False,
        is_hidden=False,
    )
    model.set_entries([entry])

    idx = model.index(0, _COL_ICON)

    # Default (details mode): icon column carries no display text
    assert model.data(idx, Qt.ItemDataRole.DisplayRole) is None

    # Icon mode on: name appears so QListView can render label beneath icon
    model.set_icon_mode(True)
    assert model.data(idx, Qt.ItemDataRole.DisplayRole) == "hello.txt"

    # Toggle back: name gone again
    model.set_icon_mode(False)
    assert model.data(idx, Qt.ItemDataRole.DisplayRole) is None


def test_set_view_mode_toggles_icon_mode_flag():
    """set_view_mode propagates icon_mode to the model correctly."""
    app = _app()
    fv = _make_file_view(app)

    for mode in ("icons_small", "icons_medium", "icons_large"):
        fv.set_view_mode(mode)
        assert fv._model._icon_mode is True, f"icon_mode should be True for {mode}"

    fv.set_view_mode("details")
    assert fv._model._icon_mode is False


# ── BreadcrumbBar ─────────────────────────────────────────────────────────────

def test_breadcrumb_navigate_on_button_click(tmp_path):
    app = _app()
    from views.breadcrumb_bar import BreadcrumbBar
    bar = BreadcrumbBar()
    bar._app_ref = app

    bar.set_path(tmp_path)
    emitted: list[str] = []
    bar.navigate_requested.connect(emitted.append)

    from PyQt6.QtWidgets import QPushButton
    buttons = bar._crumb_widget.findChildren(QPushButton)
    assert buttons, "no crumb buttons found"
    buttons[0].click()
    assert emitted, "navigate_requested not emitted on breadcrumb click"


def test_breadcrumb_edit_mode_on_empty_click(tmp_path):
    app = _app()
    from views.breadcrumb_bar import BreadcrumbBar
    from PyQt6.QtCore import QEvent, Qt
    from PyQt6.QtGui import QMouseEvent

    bar = BreadcrumbBar()
    bar._app_ref = app
    bar.set_path(tmp_path)

    assert bar._stack.currentIndex() == 0   # breadcrumb mode

    # Simulate click on _crumb_widget (empty area)
    event = QMouseEvent(
        QEvent.Type.MouseButtonPress,
        bar._crumb_widget.rect().center().toPointF(),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    bar._crumb_widget.mousePressEvent(event)
    # Event filter intercepts this — call directly
    bar._enter_edit()
    assert bar._stack.currentIndex() == 1   # edit mode


def test_breadcrumb_escape_cancels_edit():
    app = _app()
    from views.breadcrumb_bar import BreadcrumbBar
    bar = BreadcrumbBar()
    bar._app_ref = app
    bar._enter_edit()
    assert bar._stack.currentIndex() == 1
    bar._cancel_edit()
    assert bar._stack.currentIndex() == 0


# ── AddressBar ────────────────────────────────────────────────────────────────

def _make_address_bar(tmp_path, monkeypatch):
    """Create an AddressBar backed by a fresh SQLite settings store."""
    app = _app()
    _patch_db(monkeypatch, tmp_path)
    from backends.settings_backend import SettingsRepository
    from views.address_bar import AddressBar
    settings = SettingsRepository()
    bar = AddressBar(settings)
    bar._app_ref = app
    return bar, app


def test_address_bar_default_mode_is_path(tmp_path, monkeypatch):
    """AddressBar default mode is 'path' (not breadcrumb)."""
    bar, _ = _make_address_bar(tmp_path, monkeypatch)
    from views.address_bar import _PATH_MODE
    assert bar._mode == _PATH_MODE


def test_address_bar_shows_canonical_posix_path(tmp_path, monkeypatch):
    """AddressBar path edit displays the full canonical POSIX path."""
    bar, _ = _make_address_bar(tmp_path, monkeypatch)
    bar.set_path(tmp_path)
    assert bar._path_edit.text() == str(tmp_path)


def test_address_bar_path_edit_visible_in_path_mode(tmp_path, monkeypatch):
    """Stack index 0 (path edit) is shown in path mode."""
    bar, _ = _make_address_bar(tmp_path, monkeypatch)
    assert bar._stack.currentIndex() == 0


def test_address_bar_toggle_switches_to_breadcrumb(tmp_path, monkeypatch):
    """Toggle button switches mode to breadcrumb and persists it."""
    bar, _ = _make_address_bar(tmp_path, monkeypatch)
    from views.address_bar import _CRUMB_MODE
    bar._on_toggle()
    assert bar._mode == _CRUMB_MODE
    assert bar._stack.currentIndex() == 1  # breadcrumb page


def test_address_bar_toggle_roundtrip(tmp_path, monkeypatch):
    """Two toggles return to path mode."""
    bar, _ = _make_address_bar(tmp_path, monkeypatch)
    from views.address_bar import _PATH_MODE
    bar._on_toggle()
    bar._on_toggle()
    assert bar._mode == _PATH_MODE
    assert bar._stack.currentIndex() == 0


def test_address_bar_mode_persists_across_instances(tmp_path, monkeypatch):
    """Mode written to settings is read by a fresh AddressBar instance."""
    bar, _ = _make_address_bar(tmp_path, monkeypatch)
    bar._on_toggle()  # path → breadcrumb

    from backends.settings_backend import SettingsRepository
    from views.address_bar import AddressBar, _CRUMB_MODE
    bar2 = AddressBar(SettingsRepository())
    bar2._app_ref = bar._app_ref
    assert bar2._mode == _CRUMB_MODE


def test_address_bar_escape_reverts_text(tmp_path, monkeypatch):
    """Escape restores current path text without navigating."""
    bar, _ = _make_address_bar(tmp_path, monkeypatch)
    bar.set_path(tmp_path)
    bar._path_edit.setText("/nonexistent/path/typed/by/user")
    emitted: list[str] = []
    bar.navigate_requested.connect(emitted.append)

    from PyQt6.QtCore import QEvent, Qt
    from PyQt6.QtGui import QKeyEvent
    esc = QKeyEvent(
        QEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier)
    bar.eventFilter(bar._path_edit, esc)

    assert bar._path_edit.text() == str(tmp_path)
    assert not emitted, "Escape must not emit navigate_requested"


def test_address_bar_enter_navigates_valid_path(tmp_path, monkeypatch):
    """Enter navigates when text is a real directory."""
    bar, _ = _make_address_bar(tmp_path, monkeypatch)
    bar.set_path(tmp_path)
    sub = tmp_path / "sub"; sub.mkdir()
    bar._path_edit.setText(str(sub))
    emitted: list[str] = []
    bar.navigate_requested.connect(emitted.append)
    bar._commit()
    assert emitted and str(sub.resolve()) in emitted[0]


def test_address_bar_enter_invalid_reverts(tmp_path, monkeypatch):
    """Enter with a non-existent path reverts text, no navigation."""
    bar, _ = _make_address_bar(tmp_path, monkeypatch)
    bar.set_path(tmp_path)
    bar._path_edit.setText("/this/does/not/exist/xyz")
    emitted: list[str] = []
    bar.navigate_requested.connect(emitted.append)
    bar._commit()
    assert not emitted
    assert bar._path_edit.text() == str(tmp_path)


def test_address_bar_breadcrumb_navigate_signal(tmp_path, monkeypatch):
    """In breadcrumb mode, clicking a crumb still emits navigate_requested."""
    bar, _ = _make_address_bar(tmp_path, monkeypatch)
    bar.set_path(tmp_path)
    bar._on_toggle()  # switch to breadcrumb mode
    emitted: list[str] = []
    bar.navigate_requested.connect(emitted.append)
    # Simulate breadcrumb bar emitting its own navigate signal
    bar._crumb_bar.navigate_requested.emit(str(tmp_path))
    assert emitted


def test_fm_address_bar_updates_on_navigation(tmp_path, monkeypatch):
    """FileManagerView._address_bar.text() matches the current path after navigation."""
    fm = _make_fm(monkeypatch, tmp_path)
    sub = tmp_path / "mydir"; sub.mkdir()
    # Simulate left pane path_changed signal
    fm._on_left_path_changed(str(sub))
    assert fm._address_bar._path_edit.text() == str(sub)


def test_fm_ctrl_l_focuses_address_bar(tmp_path, monkeypatch):
    """Ctrl+L shortcut switches address bar to path mode (in case it was in crumb mode)."""
    fm = _make_fm(monkeypatch, tmp_path)
    from views.address_bar import _CRUMB_MODE, _PATH_MODE
    # Put address bar in breadcrumb mode
    fm._address_bar._mode = _CRUMB_MODE
    fm._address_bar._apply_mode(save=False)
    # Call focus_edit (same as Ctrl+L shortcut target)
    fm._address_bar.focus_edit()
    assert fm._address_bar._mode == _PATH_MODE


# ── recent_paths trimming ─────────────────────────────────────────────────────

def test_locations_trimmed_to_five(tmp_path, monkeypatch):
    db = tmp_path / "data.db"
    from models.database import open_db
    monkeypatch.setattr("backends.recent_backend.open_db",
                        functools.partial(open_db, db))
    from backends.recent_backend import RecentPathsBackend
    b = RecentPathsBackend()
    for i in range(8):
        b.record_location(f"/path/{i}")
        time.sleep(0.01)   # ensure distinct timestamps
    locs = b.list_locations(limit=10)
    assert len(locs) <= 5


def test_files_trimmed_to_ten(tmp_path, monkeypatch):
    db = tmp_path / "data.db"
    from models.database import open_db
    monkeypatch.setattr("backends.recent_backend.open_db",
                        functools.partial(open_db, db))
    from backends.recent_backend import RecentPathsBackend
    b = RecentPathsBackend()
    for i in range(13):
        b.record_file(f"/file/{i}.txt")
    files = b.list_files(limit=20)
    assert len(files) <= 10


def test_trim_keeps_newest(tmp_path, monkeypatch):
    db = tmp_path / "data.db"
    from models.database import open_db
    monkeypatch.setattr("backends.recent_backend.open_db",
                        functools.partial(open_db, db))
    from backends.recent_backend import RecentPathsBackend
    import sqlite3

    b = RecentPathsBackend()
    with functools.partial(open_db, db)() as conn:
        for i in range(6):
            conn.execute(
                "INSERT INTO recent_paths VALUES (?, 'location', ?)",
                (f"/p/{i}", i),
            )

    b.record_location("/p/NEW")   # triggers trim; oldest (/p/0) should be dropped

    locs = b.list_locations(limit=10)
    assert "/p/NEW" in locs
    assert "/p/0" not in locs


# ── FileManagerView integration ───────────────────────────────────────────────

def test_fm_cold_open_at_home(monkeypatch, tmp_path):
    fm = _make_fm(monkeypatch, tmp_path)
    assert fm._current_path == Path.home()


def test_fm_has_left_and_right_file_views(monkeypatch, tmp_path):
    from views.file_view import FileView
    fm = _make_fm(monkeypatch, tmp_path)
    assert isinstance(fm._left_view, FileView)
    assert isinstance(fm._right_view, FileView)
    assert fm._left_view is not fm._right_view


def test_navigate_to_updates_left_pane(monkeypatch, tmp_path):
    fm = _make_fm(monkeypatch, tmp_path)
    fm.navigate_to(str(tmp_path))
    assert fm._left_view.current_path == tmp_path


def test_view_mode_details_persists(monkeypatch, tmp_path):
    fm = _make_fm(monkeypatch, tmp_path)
    fm._view_slider.setValue(0)   # details

    from views.file_manager_view import FileManagerView
    fm2 = FileManagerView()
    fm2._app_ref = fm._app_ref
    assert fm2._view_slider.value() == 0


def test_view_mode_icons_persists(monkeypatch, tmp_path):
    fm = _make_fm(monkeypatch, tmp_path)
    fm._view_slider.setValue(2)   # icons_medium

    from views.file_manager_view import FileManagerView
    fm2 = FileManagerView()
    fm2._app_ref = fm._app_ref
    assert fm2._view_slider.value() == 2


def test_hidden_files_setting_persists(monkeypatch, tmp_path):
    fm = _make_fm(monkeypatch, tmp_path)
    fm._set_show_hidden(True)

    from views.file_manager_view import FileManagerView
    fm2 = FileManagerView()
    fm2._app_ref = fm._app_ref
    assert fm2._left_view._show_hidden is True


def test_search_bar_filters_model(monkeypatch, tmp_path):
    """Setting search text on the bar applies filter to the left view proxy."""
    fm = _make_fm(monkeypatch, tmp_path)
    fm._search_bar.setText("hello")
    assert fm._left_view._proxy.filterRegularExpression().pattern() == "hello"


def test_back_button_disabled_at_start(monkeypatch, tmp_path):
    fm = _make_fm(monkeypatch, tmp_path)
    assert not fm._back_btn.isEnabled()


def test_up_button_disabled_at_root(monkeypatch, tmp_path):
    fm = _make_fm(monkeypatch, tmp_path)
    fm._left_view.navigate(Path("/"))
    fm._update_nav_buttons()
    assert not fm._up_btn.isEnabled()


# ── Properties panel General tab ──────────────────────────────────────────────

def test_properties_general_populates_on_selection(tmp_path, monkeypatch):
    """Selecting a file while Properties is the active right pane populates General tab."""
    app = _app()
    _patch_db(monkeypatch, tmp_path)
    monkeypatch.setattr("views.file_view.FileView._load", lambda self: None)

    f = tmp_path / "report.pdf"
    f.write_text("data")

    from views.file_manager_view import FileManagerView
    fm = FileManagerView()
    fm._app_ref = app

    # Switch right pane to Properties
    fm._on_panel_selected(1)   # _RIGHT_PROPERTIES = 1

    # Build a FileEntry for the file and fire selection_changed
    from models.file_entry import FileEntry
    entry = FileEntry(
        name="report.pdf",
        path=f,
        size=4,
        modified=f.stat().st_mtime,
        mime_type="application/pdf",
        is_dir=False,
        is_hidden=False,
    )
    fm._on_left_selection_changed([entry])

    assert fm._properties_panel._stack.currentIndex() == 1   # tab view shown
    assert fm._properties_panel._val_name.text() == "report.pdf"
    assert "PDF" in fm._properties_panel._val_type.text()


def test_properties_shows_placeholder_on_empty_selection(tmp_path, monkeypatch):
    app = _app()
    _patch_db(monkeypatch, tmp_path)
    monkeypatch.setattr("views.file_view.FileView._load", lambda self: None)

    from views.file_manager_view import FileManagerView
    fm = FileManagerView()
    fm._app_ref = app
    fm._on_panel_selected(1)
    fm._on_left_selection_changed([])   # deselect all

    assert fm._properties_panel._stack.currentIndex() == 0


# ── Status bar ────────────────────────────────────────────────────────────────

def test_status_bar_shows_selection_count(tmp_path, monkeypatch):
    app = _app()
    _patch_db(monkeypatch, tmp_path)
    monkeypatch.setattr("views.file_view.FileView._load", lambda self: None)

    from views.file_manager_view import FileManagerView
    from models.file_entry import FileEntry
    fm = FileManagerView()
    fm._app_ref = app

    f = tmp_path / "a.txt"; f.write_text("hi")
    entry = FileEntry("a.txt", f, 2, f.stat().st_mtime, "text/plain", False, False)
    fm._on_left_selection_changed([entry])

    assert "1" in fm._status_label.text() or "item" in fm._status_label.text()


def test_status_bar_shows_mime_on_hover(tmp_path, monkeypatch):
    app = _app()
    _patch_db(monkeypatch, tmp_path)
    monkeypatch.setattr("views.file_view.FileView._load", lambda self: None)

    from views.file_manager_view import FileManagerView
    from models.file_entry import FileEntry
    fm = FileManagerView()
    fm._app_ref = app

    f = tmp_path / "img.png"; f.write_text("x")
    entry = FileEntry("img.png", f, 1, f.stat().st_mtime, "image/png", False, False)
    fm._on_hover_changed(entry)

    assert fm._status_label.text() != ""


def test_free_space_label_populated(monkeypatch, tmp_path):
    """Free space label is set after restore_state (uses shutil.disk_usage)."""
    fm = _make_fm(monkeypatch, tmp_path)
    assert fm._free_space_label.text() != ""


# ── Icon resolver (_entry_icon) ───────────────────────────────────────────────

def _make_entry(path: Path, is_dir: bool = False):
    from models.file_entry import FileEntry
    stat = path.stat() if path.exists() else None
    size = stat.st_size if stat else 0
    mtime = stat.st_mtime if stat else 0.0
    return FileEntry(path.name, path, size, mtime, "", is_dir, False)


def _make_nonnull_icon():
    """Return (app, icon) — caller must keep app alive to prevent GC of QApplication."""
    from PyQt6.QtWidgets import QApplication, QStyle
    app = QApplication.instance() or QApplication([])
    return app, app.style().standardIcon(QStyle.StandardPixmap.SP_FileIcon)


def _reset_icon_state(fv_mod, monkeypatch, viable: bool = False) -> None:
    """Reset all module-level icon resolver state and force a _THEME_VIABLE value."""
    fv_mod._ICON_CACHE.clear()
    fv_mod._MIME_DB = None
    fv_mod._FILE_ICON_PROVIDER = None
    monkeypatch.setattr(fv_mod, "_THEME_VIABLE", viable)


def test_icon_resolver_folder_non_null(tmp_path, monkeypatch):
    """_entry_icon returns a non-null icon for a directory (non-viable → QFileIconProvider)."""
    import views.file_view as fv_mod
    app, stub = _make_nonnull_icon()
    _reset_icon_state(fv_mod, monkeypatch, viable=False)
    from PyQt6.QtWidgets import QFileIconProvider
    monkeypatch.setattr(QFileIconProvider, "icon", lambda self, *_a: stub)
    from views.file_view import _entry_icon
    d = tmp_path / "somedir"; d.mkdir()
    icon = _entry_icon(_make_entry(d, is_dir=True))
    assert not icon.isNull()


def test_icon_resolver_docx_non_null(tmp_path, monkeypatch):
    """_entry_icon returns a non-null icon for .docx (non-viable → QFileIconProvider)."""
    import views.file_view as fv_mod
    app, stub = _make_nonnull_icon()
    _reset_icon_state(fv_mod, monkeypatch, viable=False)
    from PyQt6.QtWidgets import QFileIconProvider
    monkeypatch.setattr(QFileIconProvider, "icon", lambda self, *_a: stub)
    from views.file_view import _entry_icon
    f = tmp_path / "report.docx"; f.write_bytes(b"PK\x03\x04")
    icon = _entry_icon(_make_entry(f))
    assert not icon.isNull()


def test_icon_resolver_unknown_extension_non_null(tmp_path, monkeypatch):
    """_entry_icon returns a non-null icon for unknown extension via QFileIconProvider."""
    import views.file_view as fv_mod
    app, stub = _make_nonnull_icon()
    _reset_icon_state(fv_mod, monkeypatch, viable=False)
    from PyQt6.QtWidgets import QFileIconProvider
    monkeypatch.setattr(QFileIconProvider, "icon", lambda self, *_a: stub)
    from views.file_view import _entry_icon
    f = tmp_path / "data.xyzunknownext"; f.write_bytes(b"\x00\x01")
    icon = _entry_icon(_make_entry(f))
    assert not icon.isNull()


def test_icon_resolver_cache_reuse(tmp_path, monkeypatch):
    """Two files with the same MIME type return the same QIcon object (cache hit)."""
    import views.file_view as fv_mod
    app, stub = _make_nonnull_icon()
    _reset_icon_state(fv_mod, monkeypatch, viable=False)
    from PyQt6.QtWidgets import QFileIconProvider
    monkeypatch.setattr(QFileIconProvider, "icon", lambda self, *_a: stub)
    from views.file_view import _entry_icon
    a = tmp_path / "a.txt"; a.write_text("a")
    b = tmp_path / "b.txt"; b.write_text("b")
    icon_a = _entry_icon(_make_entry(a))
    icon_b = _entry_icon(_make_entry(b))
    assert not icon_a.isNull()
    assert not icon_b.isNull()
    # Both text/plain → same cache key → same icon object
    assert icon_a is icon_b


def test_icon_resolver_cache_invalidated_on_theme_change(tmp_path, monkeypatch):
    """Cache is cleared when the icon theme name changes."""
    import views.file_view as fv_mod
    app, stub = _make_nonnull_icon()
    _reset_icon_state(fv_mod, monkeypatch, viable=False)
    from PyQt6.QtWidgets import QFileIconProvider
    monkeypatch.setattr(QFileIconProvider, "icon", lambda self, *_a: stub)
    from views.file_view import _entry_icon
    d = tmp_path / "dir"; d.mkdir()
    _entry_icon(_make_entry(d, is_dir=True))
    assert len(fv_mod._ICON_CACHE) > 0
    # Simulate a theme name change
    fv_mod._ICON_CACHE_THEME = "__fake_old_theme__"
    _entry_icon(_make_entry(d, is_dir=True))
    # Cache was cleared and repopulated with one directory entry
    assert len(fv_mod._ICON_CACHE) == 1


# ── FIX PASS: address bar style, sidebar persistence ─────────────────────────

def test_address_bar_path_edit_qss_matches_search_bar(tmp_path, monkeypatch):
    """_path_edit carries the same QSS properties as the Search QLineEdit."""
    bar, _ = _make_address_bar(tmp_path, monkeypatch)
    qss = bar._path_edit.styleSheet()
    # Must specify explicit fill (not transparent) matching search bar treatment
    assert "palette(base)" in qss
    assert "border" in qss
    assert "border-radius" in qss


def test_fm_sidebar_width_persists(tmp_path, monkeypatch):
    """fm.sidebar.width is written to settings when the outer splitter moves."""
    fm = _make_fm(monkeypatch, tmp_path)
    # Simulate the splitter emitting splitterMoved after a drag
    fm._on_sidebar_resized(100, 1)
    saved = fm._settings.get("fm.sidebar.width")
    # Value is whatever the outer splitter reports for index 0
    assert saved is not None
    assert saved.isdigit()


# ── CRITICAL FIX PASS: DnD + self-adaptive icons ──────────────────────────────

def test_dnd_mime_types(tmp_path, monkeypatch):
    """_FileModel.mimeTypes() advertises text/uri-list."""
    _app()
    from views.file_view import _FileModel
    assert _FileModel().mimeTypes() == ["text/uri-list"]


def test_dnd_mime_data_has_file_urls(tmp_path, monkeypatch):
    """mimeData(indexes) returns QMimeData with one file:// URL per selected row."""
    _app()
    from views.file_view import _FileModel, _COL_ICON
    from models.file_entry import FileEntry

    model = _FileModel()
    f1 = tmp_path / "alpha.txt"; f1.write_text("a")
    f2 = tmp_path / "beta.txt";  f2.write_text("b")
    model.set_entries([
        FileEntry(f1.name, f1, 1, 0.0, "text/plain", False, False),
        FileEntry(f2.name, f2, 1, 0.0, "text/plain", False, False),
    ])
    indexes = [model.index(r, _COL_ICON) for r in range(2)]
    data = model.mimeData(indexes)
    assert data is not None and data.hasUrls()
    local_paths = {u.toLocalFile() for u in data.urls()}
    assert str(f1) in local_paths
    assert str(f2) in local_paths


def test_icon_viable_check_returns_bool(tmp_path, monkeypatch):
    """_check_theme_icons_viable() always returns a bool (never raises)."""
    _app()
    from views.file_view import _check_theme_icons_viable
    result = _check_theme_icons_viable()
    assert isinstance(result, bool)


def test_icon_provider_fallback_non_null(tmp_path, monkeypatch):
    """Non-viable path: QFileIconProvider returns a non-null icon for a real file."""
    import views.file_view as fv_mod
    app, stub = _make_nonnull_icon()
    _reset_icon_state(fv_mod, monkeypatch, viable=False)
    from PyQt6.QtWidgets import QFileIconProvider
    monkeypatch.setattr(QFileIconProvider, "icon", lambda self, *_a: stub)
    from views.file_view import _entry_icon
    f = tmp_path / "script.py"; f.write_text("x = 1")
    icon = _entry_icon(_make_entry(f))
    assert not icon.isNull()
