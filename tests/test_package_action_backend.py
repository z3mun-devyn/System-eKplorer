"""Unit tests for backends/package_action_backend.py.

All subprocess calls are monkeypatched — no real apt or pkexec runs.
"""

import subprocess

import pytest

from backends.package_action_backend import ActionResult, PackageActionBackend


# ── Fake Popen helpers ────────────────────────────────────────────────────────

class _FakePopen:
    """Minimal Popen context-manager stub for testing."""
    def __init__(self, returncode=0, stdout_text=""):
        self.returncode = returncode
        self.stdout = iter(stdout_text.splitlines(keepends=True) if stdout_text else [])
    def __enter__(self): return self
    def __exit__(self, *args): pass


def _patch(monkeypatch, returncode: int, stdout_text: str = ""):
    monkeypatch.setattr(
        "backends.package_action_backend.subprocess.Popen",
        lambda *a, **kw: _FakePopen(returncode, stdout_text),
    )


def _capture_popen(monkeypatch, captured: dict, returncode: int = 0):
    def _fake(cmd, **kw):
        captured["cmd"] = cmd
        return _FakePopen(returncode)
    monkeypatch.setattr("backends.package_action_backend.subprocess.Popen", _fake)


# ── Success ───────────────────────────────────────────────────────────────────

def test_uninstall_success(monkeypatch):
    _patch(monkeypatch, 0)
    r = PackageActionBackend().uninstall("vim", purge=True)
    assert r == ActionResult(success=True, cancelled=False, stderr="")


def test_reinstall_success(monkeypatch):
    _patch(monkeypatch, 0)
    r = PackageActionBackend().reinstall("vim")
    assert r == ActionResult(success=True, cancelled=False, stderr="")


def test_reinstall_reset_success(monkeypatch):
    _patch(monkeypatch, 0)
    r = PackageActionBackend().reinstall_reset("vim")
    assert r == ActionResult(success=True, cancelled=False, stderr="")


# ── Cancellation (pkexec auth rejected) ──────────────────────────────────────

def test_exit_126_is_cancelled(monkeypatch):
    _patch(monkeypatch, 126)
    r = PackageActionBackend().uninstall("vim", purge=True)
    assert r.cancelled is True
    assert r.success is False


def test_exit_127_is_cancelled(monkeypatch):
    _patch(monkeypatch, 127)
    r = PackageActionBackend().uninstall("vim", purge=True)
    assert r.cancelled is True
    assert r.success is False


# ── Failure ───────────────────────────────────────────────────────────────────

def test_nonzero_returncode_is_failure(monkeypatch):
    _patch(monkeypatch, 1, stdout_text="E: Unable to locate package vim")
    r = PackageActionBackend().uninstall("vim", purge=True)
    assert r.success is False
    assert r.cancelled is False
    assert "Unable to locate" in r.stderr


def test_output_captured_as_error_on_failure(monkeypatch):
    _patch(monkeypatch, 100, stdout_text="some apt output")
    r = PackageActionBackend().uninstall("vim", purge=True)
    assert r.stderr == "some apt output"


def test_timeout_is_failure(monkeypatch):
    def _raise(*a, **kw):
        raise subprocess.TimeoutExpired(cmd="pkexec", timeout=120)
    monkeypatch.setattr("backends.package_action_backend.subprocess.Popen", _raise)
    r = PackageActionBackend().uninstall("vim", purge=True)
    assert r.success is False
    assert r.cancelled is False
    assert "timed out" in r.stderr.lower()


def test_file_not_found_is_failure(monkeypatch):
    def _raise(*a, **kw):
        raise FileNotFoundError("pkexec: no such file")
    monkeypatch.setattr("backends.package_action_backend.subprocess.Popen", _raise)
    r = PackageActionBackend().uninstall("vim", purge=True)
    assert r.success is False
    assert "pkexec" in r.stderr.lower()


# ── Streaming line_cb ─────────────────────────────────────────────────────────

def test_line_cb_receives_stdout_lines(monkeypatch):
    _patch(monkeypatch, 0, stdout_text="line one\nline two\n")
    lines: list[str] = []
    PackageActionBackend().reinstall("vim", line_cb=lines.append)
    assert lines == ["line one", "line two"]


def test_line_cb_none_does_not_raise(monkeypatch):
    _patch(monkeypatch, 0, stdout_text="some output\n")
    r = PackageActionBackend().reinstall("vim", line_cb=None)
    assert r.success is True


# ── Correct apt verbs / commands ──────────────────────────────────────────────

def test_purge_uses_purge_verb(monkeypatch):
    captured: dict = {}
    _capture_popen(monkeypatch, captured)
    PackageActionBackend().uninstall("bash", purge=True)
    assert "purge" in captured["cmd"]
    assert "remove" not in captured["cmd"]


def test_remove_uses_remove_verb(monkeypatch):
    captured: dict = {}
    _capture_popen(monkeypatch, captured)
    PackageActionBackend().uninstall("bash", purge=False)
    assert "remove" in captured["cmd"]
    assert "purge" not in captured["cmd"]


def test_package_name_in_uninstall_command(monkeypatch):
    captured: dict = {}
    _capture_popen(monkeypatch, captured)
    PackageActionBackend().uninstall("my-special-pkg", purge=True)
    assert "my-special-pkg" in captured["cmd"]


def test_reinstall_uses_reinstall_flag(monkeypatch):
    captured: dict = {}
    _capture_popen(monkeypatch, captured)
    PackageActionBackend().reinstall("vim")
    assert "--reinstall" in captured["cmd"]
    assert "install" in captured["cmd"]
    assert "vim" in captured["cmd"]


def test_reinstall_reset_invokes_bash_with_both_commands(monkeypatch):
    captured: dict = {}
    _capture_popen(monkeypatch, captured)
    PackageActionBackend().reinstall_reset("vim")
    assert "bash" in captured["cmd"]
    shell_script = " ".join(captured["cmd"])
    assert "purge" in shell_script
    assert "install" in shell_script
    assert "vim" in shell_script


def test_reinstall_reset_uses_and_operator_so_purge_failure_stops_install(monkeypatch):
    captured: dict = {}
    _capture_popen(monkeypatch, captured)
    PackageActionBackend().reinstall_reset("vim")
    shell_script = " ".join(captured["cmd"])
    assert "&&" in shell_script


# ── Batch methods ─────────────────────────────────────────────────────────────

def test_reinstall_batch_success(monkeypatch):
    _patch(monkeypatch, 0)
    r = PackageActionBackend().reinstall_batch(["vim", "nano"])
    assert r == ActionResult(success=True, cancelled=False, stderr="")


def test_reinstall_reset_batch_success(monkeypatch):
    _patch(monkeypatch, 0)
    r = PackageActionBackend().reinstall_reset_batch(["vim", "nano"])
    assert r == ActionResult(success=True, cancelled=False, stderr="")


def test_uninstall_batch_success(monkeypatch):
    _patch(monkeypatch, 0)
    r = PackageActionBackend().uninstall_batch(["vim", "nano"], purge=True)
    assert r == ActionResult(success=True, cancelled=False, stderr="")


def test_batch_exit_126_is_cancelled(monkeypatch):
    _patch(monkeypatch, 126)
    r = PackageActionBackend().uninstall_batch(["vim", "nano"], purge=True)
    assert r.cancelled is True
    assert r.success is False


def test_uninstall_batch_purge_verb(monkeypatch):
    captured: dict = {}
    _capture_popen(monkeypatch, captured)
    PackageActionBackend().uninstall_batch(["vim", "nano"], purge=True)
    shell_script = " ".join(captured["cmd"])
    assert "purge" in shell_script
    assert "remove" not in shell_script


def test_uninstall_batch_remove_verb(monkeypatch):
    captured: dict = {}
    _capture_popen(monkeypatch, captured)
    PackageActionBackend().uninstall_batch(["vim", "nano"], purge=False)
    shell_script = " ".join(captured["cmd"])
    assert "remove" in shell_script
    assert "purge" not in shell_script


def test_reinstall_batch_all_names_in_command(monkeypatch):
    captured: dict = {}
    _capture_popen(monkeypatch, captured)
    PackageActionBackend().reinstall_batch(["vim", "nano", "curl"])
    shell_script = " ".join(captured["cmd"])
    assert "vim" in shell_script
    assert "nano" in shell_script
    assert "curl" in shell_script


def test_reinstall_batch_uses_bash(monkeypatch):
    captured: dict = {}
    _capture_popen(monkeypatch, captured)
    PackageActionBackend().reinstall_batch(["vim", "nano"])
    assert "bash" in captured["cmd"]


def test_reinstall_reset_batch_uses_and_operator(monkeypatch):
    captured: dict = {}
    _capture_popen(monkeypatch, captured)
    PackageActionBackend().reinstall_reset_batch(["vim", "nano"])
    shell_script = " ".join(captured["cmd"])
    assert "&&" in shell_script
    assert "purge" in shell_script
    assert "install" in shell_script


def test_reinstall_reset_batch_all_names_in_both_commands(monkeypatch):
    captured: dict = {}
    _capture_popen(monkeypatch, captured)
    PackageActionBackend().reinstall_reset_batch(["vim", "nano"])
    script_arg = captured["cmd"][-1]
    assert script_arg.count("vim") >= 2
    assert script_arg.count("nano") >= 2


def test_batch_names_are_shell_quoted(monkeypatch):
    captured: dict = {}
    _capture_popen(monkeypatch, captured)
    PackageActionBackend().uninstall_batch(["my-pkg", "other-pkg"], purge=True)
    script_arg = captured["cmd"][-1]
    assert "my-pkg" in script_arg
    assert "other-pkg" in script_arg


# ── Flatpak single-package actions ────────────────────────────────────────────

def test_reinstall_flatpak_success(monkeypatch):
    _patch(monkeypatch, 0)
    r = PackageActionBackend().reinstall_flatpak("org.mozilla.firefox")
    assert r == ActionResult(success=True, cancelled=False, stderr="")


def test_uninstall_flatpak_delete_data_success(monkeypatch):
    _patch(monkeypatch, 0)
    r = PackageActionBackend().uninstall_flatpak("org.mozilla.firefox", delete_data=True)
    assert r == ActionResult(success=True, cancelled=False, stderr="")


def test_uninstall_flatpak_keep_data_success(monkeypatch):
    _patch(monkeypatch, 0)
    r = PackageActionBackend().uninstall_flatpak("org.mozilla.firefox", delete_data=False)
    assert r == ActionResult(success=True, cancelled=False, stderr="")


def test_reinstall_reset_flatpak_success(monkeypatch):
    _patch(monkeypatch, 0)
    r = PackageActionBackend().reinstall_reset_flatpak("org.mozilla.firefox")
    assert r == ActionResult(success=True, cancelled=False, stderr="")


def test_reinstall_flatpak_uses_reinstall_flag(monkeypatch):
    captured: dict = {}
    _capture_popen(monkeypatch, captured)
    PackageActionBackend().reinstall_flatpak("org.gnome.Calendar")
    assert "--reinstall" in captured["cmd"]
    assert "org.gnome.Calendar" in captured["cmd"]


def test_uninstall_flatpak_with_delete_data_flag(monkeypatch):
    captured: dict = {}
    _capture_popen(monkeypatch, captured)
    PackageActionBackend().uninstall_flatpak("org.gnome.Calendar", delete_data=True)
    assert "--delete-data" in captured["cmd"]


def test_uninstall_flatpak_keep_data_no_delete_flag(monkeypatch):
    captured: dict = {}
    _capture_popen(monkeypatch, captured)
    PackageActionBackend().uninstall_flatpak("org.gnome.Calendar", delete_data=False)
    assert "--delete-data" not in captured["cmd"]
    assert "org.gnome.Calendar" in captured["cmd"]


def test_reinstall_reset_flatpak_uses_and_operator(monkeypatch):
    captured: dict = {}
    _capture_popen(monkeypatch, captured)
    PackageActionBackend().reinstall_reset_flatpak("org.mozilla.firefox")
    shell_script = " ".join(captured["cmd"])
    assert "&&" in shell_script
    assert "uninstall" in shell_script
    assert "install" in shell_script


# ── Flatpak batch actions ─────────────────────────────────────────────────────

def test_reinstall_flatpak_batch_success(monkeypatch):
    _patch(monkeypatch, 0)
    r = PackageActionBackend().reinstall_flatpak_batch(
        ["org.mozilla.firefox", "org.gnome.Calendar"])
    assert r == ActionResult(success=True, cancelled=False, stderr="")


def test_reinstall_flatpak_batch_uses_bash(monkeypatch):
    captured: dict = {}
    _capture_popen(monkeypatch, captured)
    PackageActionBackend().reinstall_flatpak_batch(
        ["org.mozilla.firefox", "org.gnome.Calendar"])
    assert "bash" in captured["cmd"]


def test_uninstall_flatpak_batch_delete_data(monkeypatch):
    captured: dict = {}
    _capture_popen(monkeypatch, captured)
    PackageActionBackend().uninstall_flatpak_batch(
        ["org.mozilla.firefox", "org.gnome.Calendar"], delete_data=True)
    script_arg = captured["cmd"][-1]
    assert "--delete-data" in script_arg
    assert "org.mozilla.firefox" in script_arg


def test_uninstall_flatpak_batch_keep_data(monkeypatch):
    captured: dict = {}
    _capture_popen(monkeypatch, captured)
    PackageActionBackend().uninstall_flatpak_batch(
        ["org.mozilla.firefox", "org.gnome.Calendar"], delete_data=False)
    script_arg = captured["cmd"][-1]
    assert "--delete-data" not in script_arg
    assert "org.mozilla.firefox" in script_arg


def test_reinstall_reset_flatpak_batch_uses_and_operator(monkeypatch):
    captured: dict = {}
    _capture_popen(monkeypatch, captured)
    PackageActionBackend().reinstall_reset_flatpak_batch(
        ["org.mozilla.firefox", "org.gnome.Calendar"])
    script_arg = captured["cmd"][-1]
    assert "&&" in script_arg
    assert "uninstall" in script_arg
    assert "install" in script_arg


# ── Update methods ────────────────────────────────────────────────────────────

def test_update_apt_success(monkeypatch):
    _patch(monkeypatch, 0)
    r = PackageActionBackend().update_apt("vim")
    assert r == ActionResult(success=True, cancelled=False, stderr="")


def test_update_apt_uses_only_upgrade_flag(monkeypatch):
    captured: dict = {}
    _capture_popen(monkeypatch, captured)
    PackageActionBackend().update_apt("vim")
    assert "--only-upgrade" in captured["cmd"]
    assert "vim" in captured["cmd"]


def test_update_all_apt_uses_bash(monkeypatch):
    captured: dict = {}
    _capture_popen(monkeypatch, captured)
    PackageActionBackend().update_all_apt(["vim", "nano"])
    assert "bash" in captured["cmd"]
    script = " ".join(captured["cmd"])
    assert "--only-upgrade" in script
    assert "vim" in script
    assert "nano" in script


def test_update_flatpak_success(monkeypatch):
    _patch(monkeypatch, 0)
    r = PackageActionBackend().update_flatpak("org.mozilla.firefox")
    assert r == ActionResult(success=True, cancelled=False, stderr="")


def test_update_flatpak_uses_update_command(monkeypatch):
    captured: dict = {}
    _capture_popen(monkeypatch, captured)
    PackageActionBackend().update_flatpak("org.gnome.Calendar")
    assert "update" in captured["cmd"]
    assert "--noninteractive" in captured["cmd"]
    assert "org.gnome.Calendar" in captured["cmd"]


def test_update_all_flatpak_uses_bash(monkeypatch):
    captured: dict = {}
    _capture_popen(monkeypatch, captured)
    PackageActionBackend().update_all_flatpak(["org.mozilla.firefox", "org.gnome.Calendar"])
    assert "bash" in captured["cmd"]
    script = " ".join(captured["cmd"])
    assert "update" in script
    assert "org.mozilla.firefox" in script
