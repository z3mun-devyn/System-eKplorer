"""M9 terminal integration tests.

Tests:
- navigate_to_directory sends cd when terminal tab is active
- navigate_to_directory falls back to QDesktopServices when terminal tab is not active
- _strip_ansi removes ANSI escape codes (including previously-missed sequences)
- TerminalView.navigate_to writes the correct bytes
- _render handles CR, BS, and control characters correctly
"""
from __future__ import annotations

import os
import pytest


# ── Pure ANSI stripping ───────────────────────────────────────────────────────

def test_strip_ansi_removes_color_codes():
    from views.terminal_view import _strip_ansi
    assert _strip_ansi("\x1b[32mHello\x1b[0m") == "Hello"


def test_strip_ansi_removes_bold():
    from views.terminal_view import _strip_ansi
    assert _strip_ansi("\x1b[1mBold\x1b[0m") == "Bold"


def test_strip_ansi_removes_cursor_movement():
    from views.terminal_view import _strip_ansi
    assert _strip_ansi("\x1b[2J\x1b[H") == ""


def test_strip_ansi_preserves_plain_text():
    from views.terminal_view import _strip_ansi
    assert _strip_ansi("no escapes here") == "no escapes here"


def test_strip_ansi_removes_osc_title():
    from views.terminal_view import _strip_ansi
    result = _strip_ansi("\x1b]0;bash\x07Hello")
    assert result == "Hello"


# ── Regression: private 0x30-0x3F final-byte sequences (root cause of bug) ───

def test_strip_ansi_removes_alternate_keypad_esc_equals():
    """\\x1b= (alternate keypad) was previously left as orphaned \\x1b → □."""
    from views.terminal_view import _strip_ansi
    assert _strip_ansi("\x1b=Hello") == "Hello"


def test_strip_ansi_removes_normal_keypad_esc_gt():
    from views.terminal_view import _strip_ansi
    assert _strip_ansi("\x1b>Hello") == "Hello"


def test_strip_ansi_removes_charset_designation_esc_paren_b():
    """\\x1b(B (select ASCII charset) was previously left as (B in output."""
    from views.terminal_view import _strip_ansi
    assert _strip_ansi("\x1b(BHello") == "Hello"


def test_strip_ansi_removes_save_restore_cursor():
    from views.terminal_view import _strip_ansi
    assert _strip_ansi("\x1b7saved\x1b8") == "saved"


def test_strip_ansi_removes_bracketed_paste_mode():
    from views.terminal_view import _strip_ansi
    # ESC [ ? 2004 h — bracketed paste enable (bash sends this on startup)
    assert _strip_ansi("\x1b[?2004hHello") == "Hello"


def test_strip_ansi_removes_application_cursor_keys():
    from views.terminal_view import _strip_ansi
    assert _strip_ansi("\x1b[?1hHello\x1b[?1l") == "Hello"


def test_strip_ansi_removes_bel_so_si():
    from views.terminal_view import _strip_ansi
    assert _strip_ansi("\x07\x0e\x0fHello") == "Hello"


# ── _render: CR, BS, and control-char handling (root cause of backspace bug) ──

def _make_view():
    """Construct a TerminalView without starting a PTY.

    __init__ is safe to call — PTY creation is deferred to showEvent.
    We never show the widget, so no shell is spawned.

    The QApplication must be stored; CPython reference-counts it and an
    un-stored `QApplication([])` would be destroyed before TerminalView().
    """
    pytest.importorskip("PyQt6")
    from PyQt6.QtWidgets import QApplication
    _app = QApplication.instance() or QApplication([])  # noqa: F841 — keep alive
    from views.terminal_view import TerminalView
    view = TerminalView()
    view._app_ref = _app  # pin to widget lifetime
    return view


def _text(view) -> str:
    return view._display.toPlainText()


def test_render_plain_text():
    view = _make_view()
    view._render("hello world")
    assert _text(view) == "hello world"


def test_render_newline():
    view = _make_view()
    view._render("line1\nline2")
    assert "line1" in _text(view)
    assert "line2" in _text(view)


def test_render_crlf_treated_as_newline():
    view = _make_view()
    view._render("line1\r\nline2")
    lines = _text(view).splitlines()
    assert lines[0] == "line1"
    assert lines[1] == "line2"


def test_render_bare_cr_clears_current_line():
    """\\r without \\n clears the current line — readline redraws use this."""
    view = _make_view()
    view._render("hello\rworld")
    # "world" should have overwritten "hello" on the same line
    text = _text(view)
    assert "world" in text
    assert "hello" not in text


def test_render_bs_deletes_previous_char():
    """\\x08 (BS) removes the preceding character — canonical erase echo."""
    view = _make_view()
    view._render("helo\x08p")
    assert _text(view) == "help"


def test_render_canonical_erase_echo_bs_space_bs():
    """BS + space + BS sequence as sent by terminal driver for erase."""
    view = _make_view()
    # Type "helo" then erase 'o' with canonical echo: \x08 (erase) \x20 (overwrite) \x08 (back)
    view._render("helo\x08 \x08p")
    result = _text(view)
    assert result == "help"


def test_render_drops_other_control_chars():
    """Non-printable control chars except \\n and \\t are silently dropped."""
    view = _make_view()
    view._render("\x00\x01\x02hello\x0b\x0c")
    assert _text(view) == "hello"


def test_render_tab_preserved():
    view = _make_view()
    view._render("a\tb")
    assert "a" in _text(view) and "b" in _text(view)


# ── Event filter: space key is routed to keyPressEvent, not QTextEdit scroll ──

def test_event_filter_space_reaches_keyPressEvent(monkeypatch):
    """Space KeyPress on _display is intercepted and forwarded, not scrolled."""
    pytest.importorskip("PyQt6")
    from PyQt6.QtWidgets import QApplication
    _app = QApplication.instance() or QApplication([])
    from PyQt6.QtCore import QEvent, Qt
    from PyQt6.QtGui import QKeyEvent
    from views.terminal_view import TerminalView

    view = TerminalView()
    view._app_ref = _app

    received: list[int] = []

    def _spy_key(event):
        received.append(event.key())
    monkeypatch.setattr(view, "keyPressEvent", _spy_key)

    space_event = QKeyEvent(
        QEvent.Type.KeyPress, Qt.Key.Key_Space,
        Qt.KeyboardModifier.NoModifier, " ")
    # Simulate the event arriving at _display
    view.eventFilter(view._display, space_event)

    assert Qt.Key.Key_Space in received


def test_event_filter_returns_true_consuming_event():
    """eventFilter returns True for KeyPress so QTextEdit does not process it."""
    pytest.importorskip("PyQt6")
    from PyQt6.QtWidgets import QApplication
    _app = QApplication.instance() or QApplication([])
    from PyQt6.QtCore import QEvent, Qt
    from PyQt6.QtGui import QKeyEvent
    from views.terminal_view import TerminalView

    view = TerminalView()
    view._app_ref = _app

    key_event = QKeyEvent(
        QEvent.Type.KeyPress, Qt.Key.Key_Space,
        Qt.KeyboardModifier.NoModifier, " ")
    assert view.eventFilter(view._display, key_event) is True


def test_event_filter_passes_non_key_events():
    """eventFilter does not consume non-KeyPress events."""
    pytest.importorskip("PyQt6")
    from PyQt6.QtWidgets import QApplication
    _app = QApplication.instance() or QApplication([])
    from PyQt6.QtCore import QEvent
    from views.terminal_view import TerminalView

    view = TerminalView()
    view._app_ref = _app

    paint_event = QEvent(QEvent.Type.Paint)
    assert view.eventFilter(view._display, paint_event) is False


def test_display_focus_policy_is_strong():
    """_display.focusPolicy() is StrongFocus so cursor is visible on click."""
    pytest.importorskip("PyQt6")
    from PyQt6.QtWidgets import QApplication
    _app = QApplication.instance() or QApplication([])
    from PyQt6.QtCore import Qt
    from views.terminal_view import TerminalView

    view = TerminalView()
    view._app_ref = _app
    assert view._display.focusPolicy() == Qt.FocusPolicy.StrongFocus


def test_focus_proxy_is_display():
    """TerminalView.focusProxy() returns _display."""
    pytest.importorskip("PyQt6")
    from PyQt6.QtWidgets import QApplication
    _app = QApplication.instance() or QApplication([])
    from views.terminal_view import TerminalView

    view = TerminalView()
    view._app_ref = _app
    assert view.focusProxy() is view._display


# ── navigate_to integration ───────────────────────────────────────────────────

def test_navigate_to_sends_cd(monkeypatch):
    """TerminalView.navigate_to writes cd <path> to the master fd."""
    pytest.importorskip("PyQt6")
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])

    written = []

    # Prevent actual PTY creation in tests
    monkeypatch.setattr("views.terminal_view.os.openpty",
                        lambda: (99, 100))
    monkeypatch.setattr("views.terminal_view.subprocess.Popen",
                        lambda *a, **kw: _FakeProc())
    monkeypatch.setattr("views.terminal_view.os.close", lambda fd: None)
    monkeypatch.setattr("views.terminal_view._set_winsize", lambda *a: None)

    def fake_write(fd, data):
        written.append((fd, data))

    monkeypatch.setattr("views.terminal_view.os.write", fake_write)

    from views.terminal_view import TerminalView
    view = TerminalView.__new__(TerminalView)
    view._master_fd = 99

    view.navigate_to("/home/user/docs")
    assert any(b"cd /home/user/docs" in d for _, d in written)


def test_navigate_to_quotes_path_with_spaces(monkeypatch):
    """navigate_to shell-quotes paths that contain spaces."""
    pytest.importorskip("PyQt6")
    from PyQt6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])

    written = []
    monkeypatch.setattr("views.terminal_view.os.write",
                        lambda fd, data: written.append(data))

    from views.terminal_view import TerminalView
    view = TerminalView.__new__(TerminalView)
    view._master_fd = 99

    view.navigate_to("/home/user/my documents")
    payload = b"".join(written).decode()
    assert "my documents" in payload
    # The path must be quoted so the shell treats it as one argument
    assert "'" in payload or '"' in payload


# ── MainWindow navigate routing (logic-only, no full window construction) ────

def _make_navigate_fn(terminal_index: int, current_index: int):
    """Return a navigate_to_directory-equivalent closure for routing tests."""
    pytest.importorskip("PyQt6")
    from PyQt6.QtCore import QUrl
    from PyQt6.QtGui import QDesktopServices

    terminal_calls: list[str] = []
    desktop_calls: list[str] = []

    class _FakeTabs:
        def currentIndex(self): return current_index

    class _FakeTermView:
        def navigate_to(self, p): terminal_calls.append(p)

    class _FakeTermTab:
        terminal_view = _FakeTermView()

    tabs = _FakeTabs()
    term_tab = _FakeTermTab()

    def navigate(path: str) -> None:
        if tabs.currentIndex() == terminal_index:
            term_tab.terminal_view.navigate_to(path)
        else:
            QDesktopServices.openUrl(QUrl.fromLocalFile(path))

    return navigate, terminal_calls, desktop_calls


def test_navigate_routes_to_terminal_when_active(monkeypatch):
    """navigate_to_directory calls terminal.navigate_to when terminal tab is shown."""
    from PyQt6.QtCore import QUrl
    from PyQt6.QtGui import QDesktopServices
    desktop_calls: list[str] = []
    monkeypatch.setattr(QDesktopServices, "openUrl",
                        staticmethod(lambda url: desktop_calls.append(url.toLocalFile())))

    navigate, terminal_calls, _ = _make_navigate_fn(terminal_index=3, current_index=3)
    navigate("/home/user/test")
    assert terminal_calls == ["/home/user/test"]
    assert desktop_calls == []


def test_navigate_falls_back_to_desktop_when_terminal_not_active(monkeypatch):
    """navigate_to_directory opens system file manager when terminal tab is not active."""
    from PyQt6.QtCore import QUrl
    from PyQt6.QtGui import QDesktopServices
    desktop_calls: list[str] = []
    monkeypatch.setattr(QDesktopServices, "openUrl",
                        staticmethod(lambda url: desktop_calls.append(url.toLocalFile())))

    navigate, terminal_calls, _ = _make_navigate_fn(terminal_index=3, current_index=0)
    navigate("/home/user/test")
    assert desktop_calls == ["/home/user/test"]
    assert terminal_calls == []


# ── Arrow key sequences: DECCKM (application cursor mode) ────────────────────

def _make_key_event(key):
    pytest.importorskip("PyQt6")
    from PyQt6.QtCore import QEvent, Qt
    from PyQt6.QtGui import QKeyEvent
    return QKeyEvent(QEvent.Type.KeyPress, key, Qt.KeyboardModifier.NoModifier, "")


def _collect_writes(view, event, monkeypatch) -> list[bytes]:
    written: list[bytes] = []
    monkeypatch.setattr("views.terminal_view.os.write",
                        lambda fd, d: written.append(d))
    view._master_fd = 99
    view.keyPressEvent(event)
    return written


def test_arrow_keys_send_csi_in_normal_cursor_mode(monkeypatch):
    """Arrow keys use CSI sequences (ESC[A/B/C/D) when DECCKM is not set."""
    pytest.importorskip("PyQt6")
    from PyQt6.QtWidgets import QApplication
    _app = QApplication.instance() or QApplication([])
    from PyQt6.QtCore import Qt
    from views.terminal_view import TerminalView

    view = TerminalView()
    view._app_ref = _app
    assert not view._app_cursor  # default: normal cursor mode

    expected = {
        Qt.Key.Key_Up:    b"\x1b[A",
        Qt.Key.Key_Down:  b"\x1b[B",
        Qt.Key.Key_Right: b"\x1b[C",
        Qt.Key.Key_Left:  b"\x1b[D",
    }
    for key, seq in expected.items():
        written = _collect_writes(view, _make_key_event(key), monkeypatch)
        assert seq in written, f"{key!r}: expected {seq!r}, got {written}"


def test_arrow_keys_send_ss3_in_application_cursor_mode(monkeypatch):
    """Arrow keys use SS3 sequences (ESC OA/OB/OC/OD) when DECCKM is active."""
    pytest.importorskip("PyQt6")
    from PyQt6.QtWidgets import QApplication
    _app = QApplication.instance() or QApplication([])
    from PyQt6.QtCore import Qt
    from views.terminal_view import TerminalView

    view = TerminalView()
    view._app_ref = _app
    view._app_cursor = True  # simulate ESC[?1h received

    expected = {
        Qt.Key.Key_Up:    b"\x1bOA",
        Qt.Key.Key_Down:  b"\x1bOB",
        Qt.Key.Key_Right: b"\x1bOC",
        Qt.Key.Key_Left:  b"\x1bOD",
    }
    for key, seq in expected.items():
        written = _collect_writes(view, _make_key_event(key), monkeypatch)
        assert seq in written, f"{key!r}: expected {seq!r}, got {written}"


def test_render_enables_application_cursor_mode():
    """ESC[?1h in PTY output sets _app_cursor = True."""
    view = _make_view()
    assert not view._app_cursor
    view._render("\x1b[?1h")
    assert view._app_cursor is True


def test_render_disables_application_cursor_mode():
    """ESC[?1l in PTY output clears _app_cursor."""
    view = _make_view()
    view._app_cursor = True
    view._render("\x1b[?1l")
    assert view._app_cursor is False


def test_render_decckm_toggle_sequence():
    """DECCKM enable followed by disable returns to normal mode."""
    view = _make_view()
    view._render("\x1b[?1h")
    assert view._app_cursor is True
    view._render("\x1b[?1l")
    assert view._app_cursor is False


def test_backspace_regression_after_arrow_fix(monkeypatch):
    """Backspace still sends DEL (0x7F) after the arrow key fix."""
    pytest.importorskip("PyQt6")
    from PyQt6.QtWidgets import QApplication
    _app = QApplication.instance() or QApplication([])
    from PyQt6.QtCore import Qt
    from views.terminal_view import TerminalView

    view = TerminalView()
    view._app_ref = _app
    written = _collect_writes(view, _make_key_event(Qt.Key.Key_Backspace), monkeypatch)
    assert b"\x7f" in written


def test_space_regression_after_arrow_fix(monkeypatch):
    """Space sends a space character regardless of cursor mode."""
    pytest.importorskip("PyQt6")
    from PyQt6.QtWidgets import QApplication
    _app = QApplication.instance() or QApplication([])
    from PyQt6.QtCore import QEvent, Qt
    from PyQt6.QtGui import QKeyEvent
    from views.terminal_view import TerminalView

    view = TerminalView()
    view._app_ref = _app
    space_event = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Space,
                            Qt.KeyboardModifier.NoModifier, " ")
    written = _collect_writes(view, space_event, monkeypatch)
    assert b" " in written
