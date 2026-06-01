"""M10d.1 follow-up 2: system clipboard interop + pane auto-refresh."""
from __future__ import annotations

from pathlib import Path

import pytest

from PyQt6.QtCore import QMimeData, QUrl
from PyQt6.QtWidgets import QApplication


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_fmv():
    from views.file_manager_view import FileManagerView
    return FileManagerView()


# ── Part 1: system clipboard — _set_system_clipboard ─────────────────────────

def test_copy_writes_uri_list_to_system_clipboard(tmp_path):
    """_set_system_clipboard('copy', ...) puts file:// URLs in QApplication.clipboard()."""
    f = tmp_path / "hello.txt"
    f.write_text("hi")

    fmv = _make_fmv()
    fmv._set_system_clipboard("copy", [f])

    mime = QApplication.clipboard().mimeData()
    assert mime is not None
    assert mime.hasUrls()
    urls = [u.toLocalFile() for u in mime.urls()]
    assert str(f) in urls


def test_copy_writes_plain_text_to_system_clipboard(tmp_path):
    """_set_system_clipboard sets text/plain with newline-joined paths."""
    f = tmp_path / "doc.txt"
    f.write_text("x")

    fmv = _make_fmv()
    fmv._set_system_clipboard("copy", [f])

    mime = QApplication.clipboard().mimeData()
    assert mime.hasText()
    assert str(f) in mime.text()


def test_copy_sets_gnome_copy_marker(tmp_path):
    """_set_system_clipboard('copy', ...) sets the 'copy\\n' GNOME marker."""
    f = tmp_path / "doc.pdf"
    f.write_bytes(b"data")

    fmv = _make_fmv()
    fmv._set_system_clipboard("copy", [f])

    mime = QApplication.clipboard().mimeData()
    assert mime.hasFormat("x-special/gnome-copied-files")
    data = bytes(mime.data("x-special/gnome-copied-files")).decode()
    assert data.startswith("copy\n")
    # copy must NOT set the KDE cut marker
    assert not mime.hasFormat("application/x-kde-cutselection")


def test_cut_sets_kde_cut_marker(tmp_path):
    """_set_system_clipboard('cut', ...) sets application/x-kde-cutselection=1."""
    f = tmp_path / "secret.txt"
    f.write_text("x")

    fmv = _make_fmv()
    fmv._set_system_clipboard("cut", [f])

    mime = QApplication.clipboard().mimeData()
    assert mime.hasFormat("application/x-kde-cutselection")
    val = bytes(mime.data("application/x-kde-cutselection")).decode()
    assert val == "1"


def test_cut_sets_gnome_cut_marker(tmp_path):
    """_set_system_clipboard('cut', ...) sets the 'cut\\n' GNOME marker."""
    f = tmp_path / "file.txt"
    f.write_text("y")

    fmv = _make_fmv()
    fmv._set_system_clipboard("cut", [f])

    mime = QApplication.clipboard().mimeData()
    assert mime.hasFormat("x-special/gnome-copied-files")
    data = bytes(mime.data("x-special/gnome-copied-files")).decode()
    assert data.startswith("cut\n")


def test_cut_url_in_gnome_marker(tmp_path):
    """The GNOME cut marker contains the file:// URL of the cut file."""
    f = tmp_path / "thing.txt"
    f.write_text("z")

    fmv = _make_fmv()
    fmv._set_system_clipboard("cut", [f])

    mime = QApplication.clipboard().mimeData()
    data = bytes(mime.data("x-special/gnome-copied-files")).decode()
    expected_url = QUrl.fromLocalFile(str(f)).toString()
    assert expected_url in data


# ── Part 1: paste reads from system clipboard ─────────────────────────────────

def test_paste_reads_urls_and_treats_no_marker_as_copy(tmp_path, monkeypatch):
    """Plain URLs on system clipboard (no cut marker) → copy operation."""
    src = tmp_path / "src.txt"
    src.write_text("content")
    dst_dir = tmp_path / "dst"
    dst_dir.mkdir()

    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(src))])
    QApplication.clipboard().setMimeData(mime)

    fmv = _make_fmv()
    fmv._current_path = dst_dir

    ops_called = []
    monkeypatch.setattr(fmv, "_start_file_op",
                        lambda op, srcs, **kw: ops_called.append((op, srcs)))

    fmv._do_paste()
    assert len(ops_called) == 1
    assert ops_called[0][0] == "copy"
    assert any(str(src) == str(p) for p in ops_called[0][1])


def test_paste_kde_cut_marker_triggers_move(tmp_path, monkeypatch):
    """Paste with application/x-kde-cutselection=1 → move."""
    src = tmp_path / "move_me.txt"
    src.write_text("content")
    dst_dir = tmp_path / "dst"
    dst_dir.mkdir()

    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(src))])
    mime.setData("application/x-kde-cutselection", b"1")
    QApplication.clipboard().setMimeData(mime)

    fmv = _make_fmv()
    fmv._current_path = dst_dir

    ops_called = []
    monkeypatch.setattr(fmv, "_start_file_op",
                        lambda op, srcs, **kw: ops_called.append((op, srcs)))

    fmv._do_paste()
    assert ops_called[0][0] == "move"


def test_paste_gnome_cut_marker_triggers_move(tmp_path, monkeypatch):
    """Paste with GNOME 'cut\\n' prefix → move."""
    src = tmp_path / "cut_me.txt"
    src.write_text("content")
    dst_dir = tmp_path / "dst"
    dst_dir.mkdir()

    url_str = QUrl.fromLocalFile(str(src)).toString()
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(src))])
    mime.setData("x-special/gnome-copied-files", ("cut\n" + url_str).encode())
    QApplication.clipboard().setMimeData(mime)

    fmv = _make_fmv()
    fmv._current_path = dst_dir

    ops_called = []
    monkeypatch.setattr(fmv, "_start_file_op",
                        lambda op, srcs, **kw: ops_called.append((op, srcs)))

    fmv._do_paste()
    assert ops_called[0][0] == "move"


def test_paste_gnome_copy_marker_triggers_copy(tmp_path, monkeypatch):
    """Paste with GNOME 'copy\\n' prefix → copy."""
    src = tmp_path / "copy_me.txt"
    src.write_text("content")
    dst_dir = tmp_path / "dst"
    dst_dir.mkdir()

    url_str = QUrl.fromLocalFile(str(src)).toString()
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(src))])
    mime.setData("x-special/gnome-copied-files", ("copy\n" + url_str).encode())
    QApplication.clipboard().setMimeData(mime)

    fmv = _make_fmv()
    fmv._current_path = dst_dir

    ops_called = []
    monkeypatch.setattr(fmv, "_start_file_op",
                        lambda op, srcs, **kw: ops_called.append((op, srcs)))

    fmv._do_paste()
    assert ops_called[0][0] == "copy"


def test_paste_falls_back_to_internal_clipboard_when_no_system_urls(tmp_path, monkeypatch):
    """Paste uses internal _clipboard when system clipboard has no file URLs."""
    from backends.file_ops_backend import FmClipboard

    # Clear system clipboard
    QApplication.clipboard().setMimeData(QMimeData())  # empty

    src = tmp_path / "internal.txt"
    src.write_text("data")
    dst_dir = tmp_path / "dst"
    dst_dir.mkdir()

    fmv = _make_fmv()
    fmv._clipboard = FmClipboard(operation="copy", paths=[src])
    fmv._current_path = dst_dir

    ops_called = []
    monkeypatch.setattr(fmv, "_start_file_op",
                        lambda op, srcs, **kw: ops_called.append((op, srcs)))

    fmv._do_paste()
    assert len(ops_called) == 1
    assert ops_called[0][0] == "copy"


def test_paste_with_empty_clipboard_does_nothing(monkeypatch):
    """_do_paste is a no-op when system clipboard is empty and no internal clipboard."""
    # Clear system clipboard
    QApplication.clipboard().setMimeData(QMimeData())

    fmv = _make_fmv()
    fmv._clipboard = None

    ops_called = []
    monkeypatch.setattr(fmv, "_start_file_op",
                        lambda op, srcs, **kw: ops_called.append((op, srcs)))

    fmv._do_paste()
    assert ops_called == []


# ── Part 2: pane auto-refresh ─────────────────────────────────────────────────

def test_refresh_panes_for_dir_reloads_matching_left_pane(monkeypatch):
    """_refresh_panes_for_dir reloads left pane when its current_path matches."""
    fmv = _make_fmv()
    target = Path("/some/dir")
    fmv._left_view._current_path = target
    fmv._left_view._shown = True
    fmv._right_view._shown = False

    calls = []
    monkeypatch.setattr(fmv._left_view, "_load", lambda: calls.append("left"))
    monkeypatch.setattr(fmv._right_view, "_load", lambda: calls.append("right"))

    fmv._refresh_panes_for_dir(target)
    assert calls == ["left"]


def test_refresh_panes_for_dir_reloads_both_when_both_match(monkeypatch):
    """_refresh_panes_for_dir reloads both panes if both show target_dir."""
    fmv = _make_fmv()
    target = Path("/shared/dir")
    fmv._left_view._current_path = target
    fmv._left_view._shown = True
    fmv._right_view._current_path = target
    fmv._right_view._shown = True

    calls = []
    monkeypatch.setattr(fmv._left_view, "_load", lambda: calls.append("left"))
    monkeypatch.setattr(fmv._right_view, "_load", lambda: calls.append("right"))

    fmv._refresh_panes_for_dir(target)
    assert set(calls) == {"left", "right"}


def test_refresh_panes_for_dir_skips_non_matching_pane(monkeypatch):
    """_refresh_panes_for_dir does not reload panes showing a different dir."""
    fmv = _make_fmv()
    target = Path("/some/dir")
    other = Path("/other/dir")
    fmv._left_view._current_path = other
    fmv._left_view._shown = True
    fmv._right_view._current_path = other
    fmv._right_view._shown = True

    calls = []
    monkeypatch.setattr(fmv._left_view, "_load", lambda: calls.append("left"))
    monkeypatch.setattr(fmv._right_view, "_load", lambda: calls.append("right"))

    fmv._refresh_panes_for_dir(target)
    assert calls == []


def test_refresh_panes_for_dir_none_reloads_both(monkeypatch):
    """_refresh_panes_for_dir(None) reloads both panes (unknown target fallback)."""
    fmv = _make_fmv()
    fmv._left_view._shown = True
    fmv._right_view._shown = True

    calls = []
    monkeypatch.setattr(fmv._left_view, "_load", lambda: calls.append("left"))
    monkeypatch.setattr(fmv._right_view, "_load", lambda: calls.append("right"))

    fmv._refresh_panes_for_dir(None)
    assert set(calls) == {"left", "right"}


def test_on_ops_succeeded_calls_refresh_panes_for_dir(monkeypatch):
    """_on_ops_succeeded uses _refresh_panes_for_dir with the stored target dir."""
    fmv = _make_fmv()
    target = Path("/op/target")
    fmv._last_op_target_dir = target

    refresh_calls = []
    monkeypatch.setattr(fmv, "_refresh_panes_for_dir",
                        lambda d: refresh_calls.append(d))
    monkeypatch.setattr(fmv._sidebar, "refresh_expanded_nodes", lambda: None)
    monkeypatch.setattr(fmv._sidebar, "update_wastebin_icon", lambda: None)
    monkeypatch.setattr(fmv._action_panel, "mark_complete", lambda m: None)

    fmv._on_ops_succeeded("done")
    assert refresh_calls == [target]


def test_on_ops_failed_calls_refresh_panes_for_dir(monkeypatch):
    """_on_ops_failed uses _refresh_panes_for_dir (partial completion cleanup)."""
    fmv = _make_fmv()
    target = Path("/fail/target")
    fmv._last_op_target_dir = target

    refresh_calls = []
    monkeypatch.setattr(fmv, "_refresh_panes_for_dir",
                        lambda d: refresh_calls.append(d))
    monkeypatch.setattr(fmv._action_panel, "mark_failed", lambda m: None)

    fmv._on_ops_failed("error")
    assert refresh_calls == [target]


def test_on_trash_succeeded_refreshes_left_pane(monkeypatch):
    """_on_trash_succeeded calls _refresh_left so restored files appear immediately."""
    fmv = _make_fmv()

    calls = []
    monkeypatch.setattr(fmv, "_refresh_left", lambda: calls.append("left"))
    monkeypatch.setattr(fmv, "_refresh_right", lambda: calls.append("right"))
    monkeypatch.setattr(fmv._sidebar, "refresh_expanded_nodes", lambda: None)
    monkeypatch.setattr(fmv._sidebar, "update_wastebin_icon", lambda: None)
    monkeypatch.setattr(fmv._action_panel, "mark_complete", lambda m: None)

    fmv._on_trash_succeeded("done")
    assert "left" in calls


def test_on_trash_succeeded_refreshes_right_pane(monkeypatch):
    """_on_trash_succeeded also refreshes the right pane."""
    fmv = _make_fmv()

    calls = []
    monkeypatch.setattr(fmv, "_refresh_left", lambda: calls.append("left"))
    monkeypatch.setattr(fmv, "_refresh_right", lambda: calls.append("right"))
    monkeypatch.setattr(fmv._sidebar, "refresh_expanded_nodes", lambda: None)
    monkeypatch.setattr(fmv._sidebar, "update_wastebin_icon", lambda: None)
    monkeypatch.setattr(fmv._action_panel, "mark_complete", lambda m: None)

    fmv._on_trash_succeeded("done")
    assert "right" in calls
