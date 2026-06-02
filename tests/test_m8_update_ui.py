"""M8 update-UI integration tests.

Tests:
- log expander emits lines from subprocess stdout
- "Update all" disabled when nothing upgradable
- "Update all" enabled after updates_found with non-empty map
- post-update list refresh triggered on dialog accept
- update version displayed in model data
- upgradable badge role correctly set
"""
from __future__ import annotations

import pytest

from backends.update_backend import _parse_apt_upgradable, _parse_flatpak_updates


# ── Streaming emits lines ─────────────────────────────────────────────────────

def test_streaming_emits_lines_to_line_cb(monkeypatch):
    """_run_streaming calls line_cb once per stdout line."""
    class _FakePopen:
        returncode = 0
        stdout = iter(["Setting up vim...\n", "Processing triggers...\n"])
        def __enter__(self): return self
        def __exit__(self, *args): pass

    monkeypatch.setattr(
        "backends.package_action_backend.subprocess.Popen",
        lambda *a, **kw: _FakePopen(),
    )

    from backends.package_action_backend import PackageActionBackend
    collected: list[str] = []
    PackageActionBackend().reinstall("vim", line_cb=collected.append)
    assert collected == ["Setting up vim...", "Processing triggers..."]


def test_streaming_no_lines_when_stdout_empty(monkeypatch):
    class _FakePopen:
        returncode = 0
        stdout = iter([])
        def __enter__(self): return self
        def __exit__(self, *args): pass

    monkeypatch.setattr(
        "backends.package_action_backend.subprocess.Popen",
        lambda *a, **kw: _FakePopen(),
    )

    from backends.package_action_backend import PackageActionBackend
    collected: list[str] = []
    PackageActionBackend().reinstall("vim", line_cb=collected.append)
    assert collected == []


# ── Update map / model role tests (no Qt — pure logic) ───────────────────────

def test_update_version_in_apt_upgradable_map():
    output = "Listing...\nvim/repo 9.1 amd64\n"
    results = _parse_apt_upgradable(output)
    result_map = {name: ver for name, ver in results}
    assert result_map.get("vim") == "9.1"


def test_no_update_version_for_absent_package():
    output = "Listing...\nvim/repo 9.1 amd64\n"
    results = _parse_apt_upgradable(output)
    result_map = {name: ver for name, ver in results}
    assert result_map.get("nano") is None


def test_flatpak_update_map():
    output = "org.mozilla.firefox\t128.0\n"
    results = _parse_flatpak_updates(output)
    result_map = {app_id: ver for app_id, ver in results}
    assert result_map.get("org.mozilla.firefox") == "128.0"
    assert result_map.get("org.gnome.Calendar") is None


# ── Update all disabled when map is empty ─────────────────────────────────────

def test_update_all_disabled_on_empty_map(monkeypatch, tmp_path):
    """_on_updates_found({}) → update_all button disabled."""
    pytest.importorskip("PyQt6")
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])

    from views.packages_view import PackagesView
    view = PackagesView.__new__(PackagesView)
    from PyQt6.QtWidgets import QPushButton, QLabel
    view._update_all_btn = QPushButton()
    view._updates_label = QLabel()
    view._check_updates_btn = QPushButton()
    view._update_all_btn.setEnabled(True)  # pre-set enabled

    # Simulate model stub
    class _FakeModel:
        def set_update_map(self, m): self._map = m
        def get_update_map(self): return getattr(self, '_map', {})
    view._model = _FakeModel()

    view._on_updates_found({})
    assert not view._update_all_btn.isEnabled()
    assert view._updates_label.text() != ""  # shows "everything is up to date"


def test_update_all_enabled_when_updates_found(monkeypatch, tmp_path):
    """_on_updates_found with non-empty map → update_all button enabled."""
    pytest.importorskip("PyQt6")
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])

    from views.packages_view import PackagesView
    from PyQt6.QtWidgets import QPushButton, QLabel
    view = PackagesView.__new__(PackagesView)
    view._update_all_btn = QPushButton()
    view._updates_label = QLabel()
    view._check_updates_btn = QPushButton()
    view._update_all_btn.setEnabled(False)

    class _FakeModel:
        def set_update_map(self, m): self._map = m
        def get_update_map(self): return getattr(self, '_map', {})
    view._model = _FakeModel()

    view._on_updates_found({("apt", "vim"): "9.1"})
    assert view._update_all_btn.isEnabled()


# ── _ActionPanel basic behaviour ──────────────────────────────────────────────

def _panel():
    from PyQt6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    from views.packages_view import _ActionPanel
    return _ActionPanel()


def test_action_panel_hidden_by_default():
    p = _panel()
    # isHidden() checks the widget's own flag independent of parent visibility
    assert p.isHidden()


def test_action_panel_visible_after_start_action():
    p = _panel()
    p.start_action("Reinstall: vim")
    assert not p.isHidden()


def test_action_panel_dismiss_btn_disabled_while_running():
    p = _panel()
    p.start_action("Update: curl")
    assert not p._dismiss_btn.isEnabled()


def test_action_panel_dismiss_btn_enabled_after_mark_complete():
    p = _panel()
    p.start_action("Update: curl")
    p.mark_complete("Done")
    assert p._dismiss_btn.isEnabled()


def test_action_panel_dismiss_btn_enabled_after_mark_failed():
    p = _panel()
    p.start_action("Uninstall: vim")
    p.mark_failed("apt error")
    assert p._dismiss_btn.isEnabled()


def test_action_panel_append_line_shows_in_log():
    p = _panel()
    p.start_action("Reinstall: nano")
    p.append_line("Setting up nano...")
    p.append_line("Processing triggers...")
    text = p._log.toPlainText()
    assert "Setting up nano..." in text
    assert "Processing triggers..." in text


def test_action_panel_mark_complete_sets_result():
    p = _panel()
    p.start_action("Reinstall: vim")
    p.mark_complete("Reinstall complete: vim")
    assert p._result.text() == "Reinstall complete: vim"


def test_action_panel_mark_failed_sets_result_and_appends_details():
    p = _panel()
    p.start_action("Update: broken-pkg")
    p.mark_failed("E: Unable to locate package")
    assert p._result.text() == "Action failed"
    assert "Unable to locate" in p._log.toPlainText()


def test_action_panel_dismiss_hides_and_emits():
    p = _panel()
    p.start_action("Uninstall: vim")
    p.mark_complete("Done")
    fired = []
    p.dismissed.connect(lambda: fired.append(1))
    p._on_dismiss()
    assert p.isHidden()
    assert fired == [1]


def test_action_panel_start_action_clears_previous_log():
    p = _panel()
    p.start_action("First action")
    p.append_line("old output")
    p.mark_complete("done")
    p._on_dismiss()
    p.start_action("Second action")
    assert "old output" not in p._log.toPlainText()
