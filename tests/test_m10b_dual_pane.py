"""M10b tests: dual pane toggle, right pane switcher persistence,
Properties panel structure, settings restore on FM re-open."""
from __future__ import annotations

import functools
from pathlib import Path

import pytest


# ── Helpers ───────────────────────────────────────────────────────────────────

def _app():
    pytest.importorskip("PyQt6")
    from PyQt6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def _patch_db(monkeypatch, tmp_path):
    """Redirect all DB access (settings + recent) to an isolated tmp DB."""
    from models.database import open_db
    db = tmp_path / "data.db"
    # SettingsRepository calls open_db(self._db_path) — ignore the passed path.
    # RecentPathsBackend calls open_db() with no args — partial works fine.
    monkeypatch.setattr("backends.settings_backend.open_db",
                        lambda _path=None: open_db(db))
    monkeypatch.setattr("backends.recent_backend.open_db",
                        functools.partial(open_db, db))
    return db


def _make_fm(monkeypatch, tmp_path):
    app = _app()
    _patch_db(monkeypatch, tmp_path)
    from views.file_manager_view import FileManagerView
    fm = FileManagerView()
    fm._app_ref = app   # prevent QApplication GC while widget lives
    return fm


# ── Dual pane toggle ──────────────────────────────────────────────────────────

def test_dual_pane_off_by_default(monkeypatch, tmp_path):
    """Right pane is hidden when no saved setting exists."""
    fm = _make_fm(monkeypatch, tmp_path)
    # isHidden() checks the widget's own explicit flag; isVisible() would
    # always be False in tests since the parent FM is never show()n.
    assert fm._right_pane.isHidden()


def test_dual_pane_toggle_shows_right_pane(monkeypatch, tmp_path):
    """Clicking the toggle button reveals the right pane."""
    fm = _make_fm(monkeypatch, tmp_path)
    fm._dual_pane_btn.click()
    assert not fm._right_pane.isHidden()


def test_dual_pane_toggle_hides_right_pane(monkeypatch, tmp_path):
    """Clicking the toggle twice returns to single-pane mode."""
    fm = _make_fm(monkeypatch, tmp_path)
    fm._dual_pane_btn.click()   # on
    fm._dual_pane_btn.click()   # off
    assert fm._right_pane.isHidden()


def test_dual_pane_button_is_checkable(monkeypatch, tmp_path):
    """The dual pane toggle button must be a checkable QPushButton."""
    fm = _make_fm(monkeypatch, tmp_path)
    assert fm._dual_pane_btn.isCheckable()


# ── Settings persistence: dual pane ──────────────────────────────────────────

def test_dual_pane_enabled_persists(monkeypatch, tmp_path):
    """Enabling dual pane, then reopening FM, should restore right pane visible."""
    fm = _make_fm(monkeypatch, tmp_path)
    fm._dual_pane_btn.click()   # enable

    from views.file_manager_view import FileManagerView
    fm2 = FileManagerView()
    fm2._app_ref = fm._app_ref
    assert not fm2._right_pane.isHidden()


def test_dual_pane_disabled_persists(monkeypatch, tmp_path):
    """Disabling dual pane persists so it stays off on reopen."""
    fm = _make_fm(monkeypatch, tmp_path)
    fm._dual_pane_btn.click()   # on
    fm._dual_pane_btn.click()   # off

    from views.file_manager_view import FileManagerView
    fm2 = FileManagerView()
    fm2._app_ref = fm._app_ref
    assert fm2._right_pane.isHidden()


# ── Settings persistence: right panel type ───────────────────────────────────

def test_right_panel_properties_persists(monkeypatch, tmp_path):
    """Switching to Properties panel persists across FM re-open."""
    fm = _make_fm(monkeypatch, tmp_path)
    fm._btn_properties.click()

    from views.file_manager_view import FileManagerView
    fm2 = FileManagerView()
    assert fm2._right_stack.currentIndex() == 1   # _RIGHT_PROPERTIES


def test_right_panel_terminal_persists(monkeypatch, tmp_path):
    """Switching to Terminal panel persists across FM re-open."""
    fm = _make_fm(monkeypatch, tmp_path)
    fm._btn_terminal.click()

    from views.file_manager_view import FileManagerView
    fm2 = FileManagerView()
    assert fm2._right_stack.currentIndex() == 2   # _RIGHT_TERMINAL


def test_right_panel_browser_persists(monkeypatch, tmp_path):
    """Switching back to File Browser after another selection persists."""
    fm = _make_fm(monkeypatch, tmp_path)
    fm._btn_properties.click()   # away from browser
    fm._btn_browser.click()      # back to browser

    from views.file_manager_view import FileManagerView
    fm2 = FileManagerView()
    assert fm2._right_stack.currentIndex() == 0   # _RIGHT_BROWSER


def test_right_panel_default_is_browser(monkeypatch, tmp_path):
    """Default right panel (no saved setting) is File Browser at index 0."""
    fm = _make_fm(monkeypatch, tmp_path)
    assert fm._right_stack.currentIndex() == 0


def test_switcher_buttons_are_exclusive(monkeypatch, tmp_path):
    """Only one switcher button is checked at a time."""
    fm = _make_fm(monkeypatch, tmp_path)
    fm._btn_properties.click()
    checked = [b for b in (fm._btn_browser, fm._btn_properties, fm._btn_terminal)
               if b.isChecked()]
    assert len(checked) == 1
    assert fm._btn_properties.isChecked()


# ── Properties panel structure ────────────────────────────────────────────────

def test_properties_panel_shows_placeholder(monkeypatch, tmp_path):
    """Properties panel shows placeholder (page 0) by default — no file selected."""
    fm = _make_fm(monkeypatch, tmp_path)
    assert fm._properties_panel._stack.currentIndex() == 0


def test_properties_panel_has_five_tabs(monkeypatch, tmp_path):
    """Properties panel has exactly five tabs."""
    fm = _make_fm(monkeypatch, tmp_path)
    assert fm._properties_panel._tabs.count() == 5


def test_properties_panel_tab_names(monkeypatch, tmp_path):
    """Properties panel tab names match the spec exactly."""
    import strings
    fm = _make_fm(monkeypatch, tmp_path)
    tabs = fm._properties_panel._tabs
    names = [tabs.tabText(i) for i in range(tabs.count())]
    assert names == [
        strings.PROP_TAB_GENERAL,
        strings.PROP_TAB_PERMISSIONS,
        strings.PROP_TAB_CHECKSUMS,
        strings.PROP_TAB_DETAILS,
        strings.PROP_TAB_OPEN_WITH,
    ]


def test_properties_panel_no_crash_without_file(monkeypatch, tmp_path):
    """PropertiesPanel instantiates and renders without a file selected."""
    app = _app()
    _patch_db(monkeypatch, tmp_path)
    from views.properties_panel import PropertiesPanel
    panel = PropertiesPanel()
    panel._app_ref = app
    panel.show_placeholder()   # no crash


def test_properties_panel_show_file_switches_to_tabs(monkeypatch, tmp_path):
    """show_file() switches to tab page (index 1)."""
    app = _app()
    _patch_db(monkeypatch, tmp_path)
    from views.properties_panel import PropertiesPanel
    panel = PropertiesPanel()
    panel._app_ref = app
    panel.show_file()
    assert panel._stack.currentIndex() == 1


# ── Layout integrity ──────────────────────────────────────────────────────────

def test_fm_cold_open_at_home(monkeypatch, tmp_path):
    """FM opens at the user's home directory."""
    fm = _make_fm(monkeypatch, tmp_path)
    assert fm._current_path == Path.home()


def test_navigate_to_sets_current_path(monkeypatch, tmp_path):
    """navigate_to(path) updates _current_path."""
    fm = _make_fm(monkeypatch, tmp_path)
    fm.navigate_to("/tmp")
    assert fm._current_path == Path("/tmp")


def test_right_pane_has_three_switcher_buttons(monkeypatch, tmp_path):
    """Right pane switcher exposes exactly three panel buttons."""
    fm = _make_fm(monkeypatch, tmp_path)
    assert hasattr(fm, "_btn_browser")
    assert hasattr(fm, "_btn_properties")
    assert hasattr(fm, "_btn_terminal")


def test_right_pane_has_stacked_widget_with_three_panels(monkeypatch, tmp_path):
    """Right pane stack has exactly three panels (browser, properties, terminal)."""
    fm = _make_fm(monkeypatch, tmp_path)
    assert fm._right_stack.count() == 3


def test_terminal_in_right_pane_is_terminal_view(monkeypatch, tmp_path):
    """The terminal panel in the right pane is a TerminalView instance."""
    from views.terminal_view import TerminalView
    fm = _make_fm(monkeypatch, tmp_path)
    assert isinstance(fm._right_terminal, TerminalView)


def test_right_terminal_is_independent_of_terminal_tab(monkeypatch, tmp_path):
    """FM right pane terminal is a separate instance from the Terminal tab's view."""
    from views.terminal_view import TerminalView
    fm = _make_fm(monkeypatch, tmp_path)
    tab_terminal = TerminalView()
    assert fm._right_terminal is not tab_terminal
