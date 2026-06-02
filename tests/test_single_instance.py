"""Tests for Part A/B/C of the single-instance + default-FM milestone."""

import sys
from pathlib import Path
from unittest.mock import MagicMock, call, patch


# ── Part B: _normalize_path_arg ───────────────────────────────────────────────

from main import _normalize_path_arg


def test_normalize_strips_file_scheme():
    assert _normalize_path_arg("file:///home/user/docs") == "/home/user/docs"


def test_normalize_unquotes_spaces():
    assert _normalize_path_arg("file:///home/user/my%20docs") == "/home/user/my docs"


def test_normalize_plain_path_unchanged():
    assert _normalize_path_arg("/home/user/docs") == "/home/user/docs"


def test_normalize_unquotes_without_scheme():
    assert _normalize_path_arg("/home/user/hello%20world") == "/home/user/hello world"


def test_normalize_empty_string():
    assert _normalize_path_arg("") == ""


def test_normalize_file_scheme_with_encoded_chars():
    assert _normalize_path_arg("file:///tmp/foo%2Fbar") == "/tmp/foo/bar"


# ── Part A: _try_become_secondary ────────────────────────────────────────────

from main import _try_become_secondary


def _make_mock_socket(connected: bool):
    sock = MagicMock()
    sock.waitForConnected.return_value = connected
    return sock


def test_try_become_secondary_returns_true_when_connected(monkeypatch):
    mock_sock = _make_mock_socket(connected=True)
    monkeypatch.setattr("main.QLocalSocket", lambda: mock_sock)

    result = _try_become_secondary("test-socket", "/some/path")

    assert result is True


def test_try_become_secondary_sends_path(monkeypatch):
    mock_sock = _make_mock_socket(connected=True)
    monkeypatch.setattr("main.QLocalSocket", lambda: mock_sock)

    _try_become_secondary("test-socket", "/some/path")

    mock_sock.write.assert_called_once_with(b"/some/path\n")


def test_try_become_secondary_sends_empty_string_when_no_path(monkeypatch):
    mock_sock = _make_mock_socket(connected=True)
    monkeypatch.setattr("main.QLocalSocket", lambda: mock_sock)

    _try_become_secondary("test-socket", "")

    mock_sock.write.assert_called_once_with(b"\n")


def test_try_become_secondary_returns_false_when_no_server(monkeypatch):
    mock_sock = _make_mock_socket(connected=False)
    monkeypatch.setattr("main.QLocalSocket", lambda: mock_sock)

    result = _try_become_secondary("test-socket", "")

    assert result is False


def test_try_become_secondary_closes_socket_on_success(monkeypatch):
    mock_sock = _make_mock_socket(connected=True)
    monkeypatch.setattr("main.QLocalSocket", lambda: mock_sock)

    _try_become_secondary("test-socket", "/path")

    mock_sock.close.assert_called_once()


def test_try_become_secondary_does_not_write_when_not_connected(monkeypatch):
    mock_sock = _make_mock_socket(connected=False)
    monkeypatch.setattr("main.QLocalSocket", lambda: mock_sock)

    _try_become_secondary("test-socket", "/path")

    mock_sock.write.assert_not_called()


# ── Part C: _generate_desktop_file ───────────────────────────────────────────

from main import _generate_desktop_file


def test_desktop_file_exec_contains_sys_executable(tmp_path):
    _generate_desktop_file(desktop_dir=tmp_path)
    content = (tmp_path / "ekplorer.desktop").read_text()
    assert sys.executable in content


def test_desktop_file_exec_contains_main_py_path(tmp_path):
    _generate_desktop_file(desktop_dir=tmp_path)
    content = (tmp_path / "ekplorer.desktop").read_text()
    main_py = str(Path(__file__).parent.parent / "main.py")
    assert main_py in content


def test_desktop_file_exec_line_format(tmp_path):
    _generate_desktop_file(desktop_dir=tmp_path)
    main_py = str(Path(__file__).parent.parent / "main.py")
    expected_exec = f"Exec={sys.executable} {main_py} %U"
    content = (tmp_path / "ekplorer.desktop").read_text()
    assert expected_exec in content


def test_desktop_file_created_when_missing(tmp_path):
    _generate_desktop_file(desktop_dir=tmp_path)
    assert (tmp_path / "ekplorer.desktop").exists()


def test_desktop_file_not_rewritten_when_exec_unchanged(tmp_path):
    _generate_desktop_file(desktop_dir=tmp_path)
    mtime_before = (tmp_path / "ekplorer.desktop").stat().st_mtime_ns

    _generate_desktop_file(desktop_dir=tmp_path)
    mtime_after = (tmp_path / "ekplorer.desktop").stat().st_mtime_ns

    assert mtime_before == mtime_after


def test_desktop_file_rewritten_when_exec_changed(tmp_path):
    _generate_desktop_file(desktop_dir=tmp_path)

    # Simulate a stale entry with a different executable path
    stale = (tmp_path / "ekplorer.desktop").read_text().replace(
        sys.executable, "/old/python3"
    )
    (tmp_path / "ekplorer.desktop").write_text(stale)

    _generate_desktop_file(desktop_dir=tmp_path)

    content = (tmp_path / "ekplorer.desktop").read_text()
    assert sys.executable in content
    assert "/old/python3" not in content


def test_desktop_file_mime_types_present(tmp_path):
    _generate_desktop_file(desktop_dir=tmp_path)
    content = (tmp_path / "ekplorer.desktop").read_text()
    assert "inode/directory" in content
    assert "x-scheme-handler/file" in content


def test_desktop_file_startup_wm_class(tmp_path):
    _generate_desktop_file(desktop_dir=tmp_path)
    content = (tmp_path / "ekplorer.desktop").read_text()
    assert "StartupWMClass=ekplorer" in content


def test_desktop_file_creates_directory_if_missing(tmp_path):
    nested = tmp_path / "a" / "b" / "applications"
    _generate_desktop_file(desktop_dir=nested)
    assert (nested / "ekplorer.desktop").exists()
