"""M11 P3 — Configure dialog Appearance page (skin picker + live preview).

These drive the live session QApplication: selecting a skin applies it app-wide,
so each test captures + restores the baseline to avoid leaking a palette into
later tests.
"""
import pytest

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPalette

import skin_manager
import strings
from backends.settings_backend import SettingsRepository
from views import configure_dialog
from views.configure_dialog import (
    ConfigureDialog,
    _CAT_ABOUT,
    _CAT_APPEARANCE,
)

_NORMAL = QPalette.ColorGroup.Normal


def _win_hex(app):
    return app.palette().color(_NORMAL, QPalette.ColorRole.Window).name()


def _row_for(dlg, skin_id):
    for i in range(dlg._skin_list.count()):
        if dlg._skin_list.item(i).data(Qt.ItemDataRole.UserRole) == skin_id:
            return i
    raise AssertionError(f"skin {skin_id!r} not in list")


# ── Category insertion (renumber safe per recon) ─────────────────────────────

def test_appearance_category_inserted_before_about(qt_app, tmp_path):
    if qt_app is None:
        pytest.skip("PyQt6 unavailable")
    skin_manager.capture_baseline(qt_app)
    try:
        dlg = ConfigureDialog(db_path=tmp_path / "s.db")
        assert _CAT_APPEARANCE == 5 and _CAT_ABOUT == 6
        # list rows, stack pages, and constants all agree
        assert dlg._cat_list.count() == 7
        assert dlg._stack.count() == 7
        assert dlg._cat_list.item(_CAT_APPEARANCE).text() == strings.CONFIGURE_CAT_APPEARANCE
        assert dlg._cat_list.item(_CAT_ABOUT).text() == strings.CONFIGURE_CAT_ABOUT
    finally:
        skin_manager.restore_baseline(qt_app)


# ── Skin list ────────────────────────────────────────────────────────────────

def test_skin_list_has_off_first_and_bundled(qt_app, tmp_path):
    if qt_app is None:
        pytest.skip("PyQt6 unavailable")
    skin_manager.capture_baseline(qt_app)
    try:
        dlg = ConfigureDialog(db_path=tmp_path / "s.db")
        ids = [dlg._skin_list.item(i).data(Qt.ItemDataRole.UserRole)
               for i in range(dlg._skin_list.count())]
        assert ids[0] == "off"
        assert {"ek-imp", "twmaf1", "twmaf2",
                "ignorance", "clockwork", "backyard"} <= set(ids)
    finally:
        skin_manager.restore_baseline(qt_app)


# ── Live preview + persistence ───────────────────────────────────────────────

def test_selecting_skin_applies_live_and_ok_persists(qt_app, tmp_path):
    if qt_app is None:
        pytest.skip("PyQt6 unavailable")
    db = tmp_path / "s.db"
    skin_manager.capture_baseline(qt_app)
    try:
        dlg = ConfigureDialog(db_path=db)
        dlg._skin_list.setCurrentRow(_row_for(dlg, "twmaf1"))
        assert _win_hex(qt_app) == "#1a2230"          # applied live, no OK yet

        dlg._on_ok()
        assert SettingsRepository(db).get("appearance.active_skin") == "twmaf1"
        assert _win_hex(qt_app) == "#1a2230"          # stays applied after OK
    finally:
        skin_manager.restore_baseline(qt_app)


def test_cancel_reverts_to_original_skin(qt_app, tmp_path):
    if qt_app is None:
        pytest.skip("PyQt6 unavailable")
    db = tmp_path / "s.db"
    SettingsRepository(db).set("appearance.active_skin", "twmaf1")
    skin_manager.capture_baseline(qt_app)
    try:
        dlg = ConfigureDialog(db_path=db)
        assert _win_hex(qt_app) == "#1a2230"          # loaded active skin applied

        dlg._skin_list.setCurrentRow(_row_for(dlg, "backyard"))
        assert _win_hex(qt_app) == "#1c2a1c"          # previewing another

        dlg.reject()
        assert _win_hex(qt_app) == "#1a2230"          # reverted to original
        # Cancel must NOT persist the previewed skin.
        assert SettingsRepository(db).get("appearance.active_skin") == "twmaf1"
    finally:
        skin_manager.restore_baseline(qt_app)


def test_off_selection_restores_baseline(qt_app, tmp_path):
    if qt_app is None:
        pytest.skip("PyQt6 unavailable")
    db = tmp_path / "s.db"
    skin_manager.capture_baseline(qt_app)
    baseline = _win_hex(qt_app)
    try:
        dlg = ConfigureDialog(db_path=db)
        dlg._skin_list.setCurrentRow(_row_for(dlg, "twmaf1"))
        assert _win_hex(qt_app) == "#1a2230"

        dlg._skin_list.setCurrentRow(_row_for(dlg, "off"))
        assert _win_hex(qt_app) == baseline           # off → baseline

        dlg._on_ok()
        assert SettingsRepository(db).get("appearance.active_skin") == "off"
    finally:
        skin_manager.restore_baseline(qt_app)


def test_load_selects_stored_skin_row(qt_app, tmp_path):
    if qt_app is None:
        pytest.skip("PyQt6 unavailable")
    db = tmp_path / "s.db"
    SettingsRepository(db).set("appearance.active_skin", "clockwork")
    skin_manager.capture_baseline(qt_app)
    try:
        dlg = ConfigureDialog(db_path=db)
        sel = dlg._skin_list.currentItem()
        assert sel is not None
        assert sel.data(Qt.ItemDataRole.UserRole) == "clockwork"
        assert dlg._original_skin_id == "clockwork"
    finally:
        skin_manager.restore_baseline(qt_app)
