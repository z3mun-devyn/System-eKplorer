"""Tests for ConfigureDialog and the app.startup_tab startup behaviour."""

import strings
from backends.settings_backend import SettingsRepository
from views.configure_dialog import ConfigureDialog, _STARTUP_TAB_KEYS


# ── _startup_tab_index (unit tests — no Qt widgets) ──────────────────────────

def test_startup_tab_default_is_dashboard(tmp_path):
    from main import _startup_tab_index
    repo = SettingsRepository(tmp_path / "data.db")
    assert _startup_tab_index(repo) == 0


def test_startup_tab_file_manager_maps_to_1(tmp_path):
    from main import _startup_tab_index
    repo = SettingsRepository(tmp_path / "data.db")
    repo.set("app.startup_tab", "file_manager")
    assert _startup_tab_index(repo) == 1


def test_startup_tab_packages_maps_to_2(tmp_path):
    from main import _startup_tab_index
    repo = SettingsRepository(tmp_path / "data.db")
    repo.set("app.startup_tab", "packages")
    assert _startup_tab_index(repo) == 2


def test_startup_tab_terminal_maps_to_3(tmp_path):
    from main import _startup_tab_index
    repo = SettingsRepository(tmp_path / "data.db")
    repo.set("app.startup_tab", "terminal")
    assert _startup_tab_index(repo) == 3


def test_startup_tab_clipboard_maps_to_4(tmp_path):
    from main import _startup_tab_index
    repo = SettingsRepository(tmp_path / "data.db")
    repo.set("app.startup_tab", "clipboard")
    assert _startup_tab_index(repo) == 4


def test_startup_tab_unknown_defaults_to_0(tmp_path):
    from main import _startup_tab_index
    repo = SettingsRepository(tmp_path / "data.db")
    repo.set("app.startup_tab", "nonexistent_garbage")
    assert _startup_tab_index(repo) == 0


def test_startup_tab_keys_cover_all_map_entries():
    from main import _STARTUP_TAB_MAP
    assert set(_STARTUP_TAB_KEYS) == set(_STARTUP_TAB_MAP.keys())


# ── ConfigureDialog helpers ───────────────────────────────────────────────────

def _make_dialog(tmp_path, monkeypatch, *, default_fm="dolphin.desktop") -> ConfigureDialog:
    """Create a dialog with xdg-mime query mocked to return *default_fm*."""
    monkeypatch.setattr(
        ConfigureDialog,
        "_query_default_fm",
        lambda self: default_fm,
    )
    return ConfigureDialog(db_path=tmp_path / "data.db")


# ── Dialog reads settings into widgets ───────────────────────────────────────

def test_dialog_reads_startup_tab_into_combo(tmp_path, monkeypatch):
    db = tmp_path / "data.db"
    SettingsRepository(db).set("app.startup_tab", "packages")
    dlg = _make_dialog(tmp_path, monkeypatch)
    assert dlg._startup_combo.currentIndex() == 2  # packages
    dlg.reject()


def test_dialog_reads_fm_show_hidden_into_checkbox(tmp_path, monkeypatch):
    db = tmp_path / "data.db"
    SettingsRepository(db).set("fm.show_hidden", "true")
    dlg = _make_dialog(tmp_path, monkeypatch)
    assert dlg._fm_hidden_cb.isChecked()
    dlg.reject()


def test_dialog_fm_hidden_unchecked_when_false(tmp_path, monkeypatch):
    db = tmp_path / "data.db"
    SettingsRepository(db).set("fm.show_hidden", "false")
    dlg = _make_dialog(tmp_path, monkeypatch)
    assert not dlg._fm_hidden_cb.isChecked()
    dlg.reject()


def test_dialog_reads_fm_view_mode_icons(tmp_path, monkeypatch):
    db = tmp_path / "data.db"
    SettingsRepository(db).set("fm.view_mode", "icons")
    dlg = _make_dialog(tmp_path, monkeypatch)
    assert dlg._fm_view_combo.currentIndex() == 1  # Icons
    dlg.reject()


def test_dialog_reads_fm_address_bar_breadcrumb(tmp_path, monkeypatch):
    db = tmp_path / "data.db"
    SettingsRepository(db).set("fm.address_bar.mode", "breadcrumb")
    dlg = _make_dialog(tmp_path, monkeypatch)
    assert dlg._fm_addr_combo.currentIndex() == 1  # Breadcrumb
    dlg.reject()


def test_dialog_reads_clipboard_max_entries(tmp_path, monkeypatch):
    db = tmp_path / "data.db"
    SettingsRepository(db).set("clipboard.max_entries", "42")
    dlg = _make_dialog(tmp_path, monkeypatch)
    assert dlg._cb_spinbox.value() == 42
    dlg.reject()


def test_dialog_defaults_max_entries_to_10_when_missing(tmp_path, monkeypatch):
    dlg = _make_dialog(tmp_path, monkeypatch)
    assert dlg._cb_spinbox.value() == 10
    dlg.reject()


# ── OK writes; Cancel does not ────────────────────────────────────────────────

def test_ok_writes_startup_tab(tmp_path, monkeypatch):
    dlg = _make_dialog(tmp_path, monkeypatch)
    dlg._startup_combo.setCurrentIndex(4)  # clipboard
    dlg._on_ok()
    assert SettingsRepository(tmp_path / "data.db").get("app.startup_tab") == "clipboard"


def test_ok_writes_fm_view_mode(tmp_path, monkeypatch):
    dlg = _make_dialog(tmp_path, monkeypatch)
    dlg._fm_view_combo.setCurrentIndex(1)  # Icons
    dlg._on_ok()
    assert SettingsRepository(tmp_path / "data.db").get("fm.view_mode") == "icons"


def test_ok_writes_fm_show_hidden(tmp_path, monkeypatch):
    dlg = _make_dialog(tmp_path, monkeypatch)
    dlg._fm_hidden_cb.setChecked(True)
    dlg._on_ok()
    assert SettingsRepository(tmp_path / "data.db").get("fm.show_hidden") == "true"


def test_ok_writes_fm_address_bar_mode(tmp_path, monkeypatch):
    dlg = _make_dialog(tmp_path, monkeypatch)
    dlg._fm_addr_combo.setCurrentIndex(1)  # Breadcrumb
    dlg._on_ok()
    assert SettingsRepository(tmp_path / "data.db").get("fm.address_bar.mode") == "breadcrumb"


def test_ok_writes_clipboard_max_entries(tmp_path, monkeypatch):
    dlg = _make_dialog(tmp_path, monkeypatch)
    dlg._cb_spinbox.setValue(33)
    dlg._on_ok()
    assert SettingsRepository(tmp_path / "data.db").get("clipboard.max_entries") == "33"


def test_cancel_does_not_write_fm_view(tmp_path, monkeypatch):
    db = tmp_path / "data.db"
    SettingsRepository(db).set("fm.view_mode", "details")
    dlg = _make_dialog(tmp_path, monkeypatch)
    dlg._fm_view_combo.setCurrentIndex(1)  # change in UI
    dlg.reject()                           # Cancel
    assert SettingsRepository(db).get("fm.view_mode") == "details"


def test_cancel_does_not_write_startup_tab(tmp_path, monkeypatch):
    db = tmp_path / "data.db"
    SettingsRepository(db).set("app.startup_tab", "dashboard")
    dlg = _make_dialog(tmp_path, monkeypatch)
    dlg._startup_combo.setCurrentIndex(3)  # terminal
    dlg.reject()
    assert SettingsRepository(db).get("app.startup_tab") == "dashboard"


# ── System page — status label and button state ───────────────────────────────

def test_system_status_label_when_is_default(tmp_path, monkeypatch):
    dlg = _make_dialog(tmp_path, monkeypatch, default_fm="ekplorer.desktop")
    assert dlg._sys_fm_status.text() == strings.CONFIGURE_SYS_FM_STATUS_IS
    dlg.reject()


def test_system_status_label_when_not_default(tmp_path, monkeypatch):
    dlg = _make_dialog(tmp_path, monkeypatch, default_fm="dolphin.desktop")
    assert dlg._sys_fm_status.text() == strings.CONFIGURE_SYS_FM_STATUS_NOT
    dlg.reject()


def test_system_set_btn_disabled_when_already_default(tmp_path, monkeypatch):
    dlg = _make_dialog(tmp_path, monkeypatch, default_fm="ekplorer.desktop")
    assert not dlg._sys_fm_set_btn.isEnabled()
    dlg.reject()


def test_system_set_btn_enabled_when_not_default(tmp_path, monkeypatch):
    dlg = _make_dialog(tmp_path, monkeypatch, default_fm="nautilus.desktop")
    assert dlg._sys_fm_set_btn.isEnabled()
    dlg.reject()


def test_system_status_not_default_when_query_returns_none(tmp_path, monkeypatch):
    dlg = _make_dialog(tmp_path, monkeypatch, default_fm=None)
    assert dlg._sys_fm_status.text() == strings.CONFIGURE_SYS_FM_STATUS_NOT
    dlg.reject()


# ── Dashboard page ────────────────────────────────────────────────────────────

def test_configure_dashboard_defaults_to_simple(tmp_path, monkeypatch):
    dlg = _make_dialog(tmp_path, monkeypatch)
    assert dlg._dash_simple_rb.isChecked()
    assert not dlg._dash_advanced_rb.isChecked()
    dlg.reject()


def test_configure_dashboard_reads_simple_setting(tmp_path, monkeypatch):
    db = tmp_path / "data.db"
    SettingsRepository(db).set("dashboard.view_mode", "simple")
    dlg = _make_dialog(tmp_path, monkeypatch)
    assert dlg._dash_simple_rb.isChecked()
    dlg.reject()


def test_configure_dashboard_reads_advanced_setting(tmp_path, monkeypatch):
    db = tmp_path / "data.db"
    SettingsRepository(db).set("dashboard.view_mode", "advanced")
    dlg = _make_dialog(tmp_path, monkeypatch)
    assert dlg._dash_advanced_rb.isChecked()
    dlg.reject()


def test_configure_dashboard_ok_writes_advanced(tmp_path, monkeypatch):
    dlg = _make_dialog(tmp_path, monkeypatch)
    dlg._dash_advanced_rb.setChecked(True)
    dlg._on_ok()
    assert SettingsRepository(tmp_path / "data.db").get("dashboard.view_mode") == "advanced"


def test_configure_dashboard_ok_writes_simple(tmp_path, monkeypatch):
    db = tmp_path / "data.db"
    SettingsRepository(db).set("dashboard.view_mode", "advanced")
    dlg = _make_dialog(tmp_path, monkeypatch)
    dlg._dash_simple_rb.setChecked(True)
    dlg._on_ok()
    assert SettingsRepository(db).get("dashboard.view_mode") == "simple"


def test_configure_dashboard_cancel_does_not_write(tmp_path, monkeypatch):
    db = tmp_path / "data.db"
    SettingsRepository(db).set("dashboard.view_mode", "simple")
    dlg = _make_dialog(tmp_path, monkeypatch)
    dlg._dash_advanced_rb.setChecked(True)
    dlg.reject()
    assert SettingsRepository(db).get("dashboard.view_mode") == "simple"


# ── SMART disk-group status ───────────────────────────────────────────────────

def test_smart_group_status_in_group(tmp_path, monkeypatch):
    """System page shows green in-group message when user is a member of disk group."""
    import grp
    from unittest.mock import MagicMock
    import views.configure_dialog as cd_mod

    mock_group = MagicMock()
    mock_group.gr_mem = ["testuser"]
    monkeypatch.setattr(grp, "getgrnam", lambda name: mock_group)
    monkeypatch.setattr(cd_mod.getpass, "getuser", lambda: "testuser")

    dlg = _make_dialog(tmp_path, monkeypatch)
    assert "✓" in dlg._smart_group_status.text()
    dlg.reject()


def test_smart_group_status_not_in_group(tmp_path, monkeypatch):
    """System page shows not-in-group message when user is absent from disk group."""
    import grp
    from unittest.mock import MagicMock
    import views.configure_dialog as cd_mod

    mock_group = MagicMock()
    mock_group.gr_mem = ["root", "otheruser"]
    monkeypatch.setattr(grp, "getgrnam", lambda name: mock_group)
    monkeypatch.setattr(cd_mod.getpass, "getuser", lambda: "testuser")

    dlg = _make_dialog(tmp_path, monkeypatch)
    assert "✗" in dlg._smart_group_status.text()
    dlg.reject()
