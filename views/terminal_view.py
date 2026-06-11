"""M9: Embedded PTY terminal tab.

Uses Python stdlib pty + QSocketNotifier for async reads.  Output is displayed
in a QTextEdit with ANSI/VT100 escape codes stripped.  Keyboard events write to
the master PTY fd so the shell receives input in real time.

Full-screen TUI apps (vim, htop) will not render correctly because there is no
full VT100 state machine — only escape stripping.  Common commands (ls, git,
apt, etc.) work fine.

QTermWidget has no Qt6 Python bindings on Ubuntu 24.04; this is the alternative.

Initialization fixes applied here (analogous to QTermWidget.setTerminalFont /
setKeyBindings / setScrollbarPosition):
  - TERM=xterm-256color set in shell environment
  - COLORTERM=truecolor for true-colour prompts
  - Slave PTY VERASE=0x7F (DEL) configured to match Backspace key binding
  - ANSI regex covers all VT100 2-byte sequences including private 0x30-0x3F finals
    (fixes \x1b= alternate-keypad and \x1b(B charset sequences escaping as boxes)
  - \r (CR without LF) clears the current display line before reprint, enabling
    readline's in-place line-editing redraws
  - \x08 (BS) deletes the previous display character (canonical-mode erase echo)
  - Buffered UTF-8 decode to avoid split-sequence replacement boxes

Focus / cursor polish (this bug fix):
  - QTextEdit (not TerminalView) holds Qt focus — its cursor is visible and
    blinks naturally.  TerminalView.setFocusProxy(_display) routes tab-focus
    and programmatic focus directly to the display widget.
  - Event filter on _display + _display.viewport() intercepts ALL KeyPress
    events before QTextEdit processes them, preventing scroll-on-space and
    other read-only key handling.  Events are forwarded to keyPressEvent.
  - setCursorWidth(char_width) in showEvent makes the I-beam cursor as wide
    as one monospace character — a block-style cursor that blinks via Qt's
    standard cursor-blink timer.
  - _display.setFocus() is called in showEvent so the cursor is immediately
    visible after the terminal tab is switched to.
"""
from __future__ import annotations

import fcntl
import os
import re
import shlex
import struct
import subprocess
import termios

from PyQt6.QtCore import QEvent, Qt, QSocketNotifier
from PyQt6.QtGui import QColor, QFont, QFontDatabase, QKeyEvent, QPalette, QTextCharFormat, QTextCursor
from PyQt6.QtWidgets import QApplication, QMenu, QVBoxLayout, QWidget, QTextEdit


# ── ANSI / VT100 escape stripping ────────────────────────────────────────────
#
# Ordering of alternatives matters — OSC before single-char because ']' (0x5D)
# falls inside the \\-_ range (0x5C-0x5F) and would short-circuit otherwise.
#
# Key extension over the previous version: the `[0-?]` alternative covers
# private-use final bytes 0x30-0x3F.  This strips sequences that were
# previously left as orphaned \x1b chars in the display:
#   \x1b=   (0x3D) — alternate keypad mode
#   \x1b>   (0x3E) — normal keypad mode
#   \x1b<   (0x3C) — exit VT52 mode
#   \x1b7 / \x1b8 — save/restore cursor (xterm private)
#
# The `[ -/]*` prefix handles character-set designation intermediates:
#   \x1b(B  — select ASCII charset  (( = 0x28, intermediate; B = final 0x42)
#   \x1b)0  — select graphics charset
#   \x1b#8  — screen alignment test
#
_ANSI_RE = re.compile(
    r"\x1b(?:"
    r"\[[0-?]*[ -/]*[@-~]"                   # CSI:  ESC [ params... final(0x40-0x7E)
    r"|\][^\x07\x1b]*(?:\x07|\x1b\\)"        # OSC:  ESC ] ... BEL|ST
    r"|[PX_^][^\x1b]*(?:\x1b\\|$)"           # DCS/SOS/PM/APC: ESC P|X|_|^ ... ST
    r"|[ -/]*[@-~]"                           # Fe/Fs: ESC (intermediates)* final(0x40-0x7E)
    r"|[ -/]*[0-?]"                           # Fp:    ESC (intermediates)* final(0x30-0x3F)
    r")"
    r"|\x07|\x0e|\x0f"                       # Standalone BEL, SO (^N), SI (^O)
)


def _strip_ansi(text: str) -> str:
    return _ANSI_RE.sub("", text)


# ── Terminal colour constants ─────────────────────────────────────────────────
#
# These are VT100/xterm-256color specification values, not UI theme colours.
# The 16-colour palette matches the standard Linux console that ls, grep, and
# git expect when TERM=xterm-256color.
#
_TERM_BG = "#1e1e1e"   # terminal background — near-black
_TERM_FG = "#d4d4d4"   # terminal default foreground — near-white

_XTERM16 = [
    "#2e3436", "#cc0000", "#4e9a06", "#c4a000",
    "#3465a4", "#75507b", "#06989a", "#d3d7cf",
    "#555753", "#ef2929", "#8ae234", "#fce94f",
    "#729fcf", "#ad7fa8", "#34e2e2", "#eeeeec",
]
_SGR_FG_IDX = {30: 0, 31: 1, 32: 2, 33: 3, 34: 4, 35: 5, 36: 6, 37: 7,
               90: 8, 91: 9, 92: 10, 93: 11, 94: 12, 95: 13, 96: 14, 97: 15}
_SGR_BG_IDX = {k + 10: v for k, v in _SGR_FG_IDX.items()}


def _xterm256(n: int) -> QColor:
    """Convert an xterm 256-colour index to QColor."""
    if n < 16:
        return QColor(_XTERM16[n])
    if n < 232:
        n -= 16
        b = n % 6; n //= 6
        g = n % 6; r = n // 6
        def _v(x: int) -> int: return 0 if x == 0 else 55 + 40 * x
        return QColor(_v(r), _v(g), _v(b))
    gray = 8 + 10 * (n - 232)
    return QColor(gray, gray, gray)


def _parse_sgr_params(middle: str) -> list[int]:
    """Parse the parameter string of an SGR sequence ("1;32" → [1, 32])."""
    if not middle:
        return [0]
    try:
        return [int(p) if p else 0 for p in middle.split(";")]
    except ValueError:
        return [0]


def _esc_end(text: str, start: int) -> int:
    """Return the index of the first char AFTER the escape sequence at `start`.

    Returns `start` if the sequence is unrecognized or incomplete (caller
    should skip the ESC character and continue).
    """
    n = len(text)
    if start >= n or text[start] != "\x1b":
        return start
    i = start + 1
    if i >= n:
        return start  # lone ESC at end of buffer

    ch = text[i]

    if ch == "[":
        # CSI: ESC [ params* intermediates* final(0x40-0x7E)
        i += 1
        while i < n and "\x30" <= text[i] <= "\x3f":
            i += 1
        while i < n and "\x20" <= text[i] <= "\x2f":
            i += 1
        if i < n and "\x40" <= text[i] <= "\x7e":
            return i + 1
        return start

    if ch == "]":
        # OSC: ESC ] ... BEL|ST
        i += 1
        while i < n:
            if text[i] == "\x07":
                return i + 1
            if text[i] == "\x1b" and i + 1 < n and text[i + 1] == "\\":
                return i + 2
            i += 1
        return start

    if ch in "PX_^":
        # DCS/SOS/PM/APC: ESC P|X|_|^ ... ST
        i += 1
        while i < n:
            if text[i] == "\x1b" and i + 1 < n and text[i + 1] == "\\":
                return i + 2
            i += 1
        return start

    if "\x20" <= ch <= "\x2f":
        # Intermediates + final (Fe/Fs/Fp with leading intermediates)
        i += 1
        while i < n and "\x20" <= text[i] <= "\x2f":
            i += 1
        if i < n and "\x30" <= text[i] <= "\x7e":
            return i + 1
        return start

    if "\x30" <= ch <= "\x7e":
        # Plain 2-byte sequence (Fp / Fe)
        return i + 1

    return start


def _set_winsize(fd: int, rows: int, cols: int) -> None:
    try:
        fcntl.ioctl(fd, termios.TIOCSWINSZ,
                    struct.pack("HHHH", rows, cols, 0, 0))
    except OSError:
        pass


def _configure_slave_termios(slave_fd: int) -> None:
    """Ensure slave termios matches what the keyboard event handler sends.

    VERASE must be DEL (0x7F) so that Backspace (which we map to \\x7f) is
    recognized as the erase character in canonical-mode programs and by
    readline's terminal initialization.
    """
    try:
        attrs = termios.tcgetattr(slave_fd)
        attrs[6][termios.VERASE] = 0x7F   # DEL — matches keyPressEvent Backspace
        attrs[6][termios.VINTR]  = 0x03   # Ctrl+C
        attrs[6][termios.VEOF]   = 0x04   # Ctrl+D
        termios.tcsetattr(slave_fd, termios.TCSANOW, attrs)
    except Exception:
        pass


class TerminalView(QWidget):
    """Dumb-terminal widget backed by a real PTY and the user's login shell."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._master_fd: int | None = None
        self._notifier: QSocketNotifier | None = None
        self._proc: subprocess.Popen | None = None
        self._shell_started = False
        # Buffer for incomplete UTF-8 byte sequences across reads
        self._read_buf = bytearray()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._display = QTextEdit()
        self._display.setReadOnly(True)
        # Prefer an explicit "Monospace" family (xterm-style), fall back to
        # the system fixed font.  This mirrors QTermWidget.setTerminalFont().
        mono_font = QFont("Monospace")
        mono_font.setStyleHint(QFont.StyleHint.Monospace)
        if not mono_font.exactMatch():
            mono_font = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
        self._display.setFont(mono_font)
        self._display.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        self._display.setAcceptRichText(False)

        # ── Focus & key-routing fix ───────────────────────────────────────────
        # _display holds Qt focus (not TerminalView) so its cursor is visible
        # and blinks.  setFocusProxy redirects any focus directed at TerminalView
        # (tab-key navigation, programmatic setFocus) to _display.
        self.setFocusProxy(self._display)
        self.setFocusPolicy(Qt.FocusPolicy.TabFocus)  # reachable by Tab key
        # setFocusPolicy propagates to the proxy, so re-set _display to StrongFocus
        # AFTER setting TerminalView's policy — otherwise TabFocus overwrites it.
        self._display.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        # Event filter on the display widget AND its viewport:
        # intercepts QEvent.Type.KeyPress before QTextEdit handles it, so
        # read-only scroll-on-space is suppressed and all keys reach our handler.
        self._display.installEventFilter(self)
        self._display.viewport().installEventFilter(self)

        # Custom context menu so Copy (Ctrl+Shift+C) and Paste (Ctrl+Shift+V)
        # are discoverable; disables the default read-only QTextEdit menu.
        self._display.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._display.customContextMenuRequested.connect(self._on_context_menu)
        # ─────────────────────────────────────────────────────────────────────

        # Dark terminal background so the block cursor is visible and ANSI
        # colours contrast correctly.  These are terminal emulation defaults,
        # not UI theme colours — they live here, not in theme.py.
        pal = QPalette(self._display.palette())
        pal.setColor(QPalette.ColorRole.Base, QColor(_TERM_BG))
        pal.setColor(QPalette.ColorRole.Text, QColor(_TERM_FG))
        self._display.setPalette(pal)

        # Current SGR colour/weight state — updated by ESC[...m sequences in
        # the PTY output stream, reset to default by ESC[0m.
        self._char_fmt = QTextCharFormat()

        # DECCKM (application cursor mode): True when the shell has sent
        # ESC[?1h.  Arrow keys must be sent as SS3 (ESC O A/B/C/D) instead
        # of CSI (ESC [ A/B/C/D) while this flag is set.
        self._app_cursor = False

        layout.addWidget(self._display)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if not self._shell_started:
            self._shell_started = True
            self._start_shell()
        # Ensure _display has focus so the cursor is immediately visible.
        self._display.setFocus()
        # Block-style cursor: setCursorWidth to one monospace character width.
        # The cursor spans the full line height, giving a solid block appearance.
        # Blinking is handled automatically by Qt's standard cursor-blink timer.
        char_w = max(2, self._display.fontMetrics().averageCharWidth())
        self._display.setCursorWidth(char_w)

    # ── Event filter: key routing ─────────────────────────────────────────────

    def eventFilter(self, obj, event) -> bool:
        """Intercept key events from the display before QTextEdit handles them.

        Returning True consumes the event — QTextEdit never sees it.  This
        prevents scroll-on-space (and all other read-only key handling) while
        routing every keystroke to our PTY write logic.
        """
        if event.type() == QEvent.Type.KeyPress and obj in (
                self._display, self._display.viewport()):
            self.keyPressEvent(event)
            return True
        return super().eventFilter(obj, event)

    # ── Shell lifecycle ───────────────────────────────────────────────────────

    def _start_shell(self) -> None:
        try:
            master_fd, slave_fd = os.openpty()
        except OSError:
            self._display.setPlainText(
                "[Terminal] Could not open a pseudo-terminal.\n")
            return

        self._master_fd = master_fd
        _set_winsize(master_fd, 24, 80)

        # Configure VERASE on the slave BEFORE spawning the shell so that
        # readline's initial tcgetattr sees the correct erase character.
        _configure_slave_termios(slave_fd)

        shell = os.environ.get("SHELL", "/bin/bash")
        env = {
            **os.environ,
            "TERM": "xterm-256color",
            "COLORTERM": "truecolor",   # enables 24-bit colour in prompts
        }
        home = os.path.expanduser("~")

        try:
            self._proc = subprocess.Popen(
                [shell],
                stdin=slave_fd,
                stdout=slave_fd,
                stderr=slave_fd,
                start_new_session=True,
                cwd=home,
                env=env,
            )
        except OSError as exc:
            os.close(master_fd)
            os.close(slave_fd)
            self._display.setPlainText(f"[Terminal] Could not start shell: {exc}\n")
            return

        os.close(slave_fd)

        self._notifier = QSocketNotifier(
            master_fd, QSocketNotifier.Type.Read, parent=self)
        self._notifier.activated.connect(self._on_data_ready)

    # ── Output processing ─────────────────────────────────────────────────────

    def _on_data_ready(self) -> None:
        if self._master_fd is None:
            return
        try:
            chunk = os.read(self._master_fd, 4096)
        except OSError:
            if self._notifier:
                self._notifier.setEnabled(False)
            return

        # Accumulate bytes and decode only complete UTF-8 sequences.
        # This prevents U+FFFD replacement boxes from split multi-byte chars.
        self._read_buf += chunk
        text = self._decode_buf()
        self._render(text)

    def _decode_buf(self) -> str:
        """Decode as much of _read_buf as forms complete UTF-8 sequences."""
        buf = self._read_buf
        for trim in range(min(4, len(buf))):
            try:
                text = buf[:len(buf) - trim].decode("utf-8") if trim else buf.decode("utf-8")
                self._read_buf = bytearray(buf[len(buf) - trim:]) if trim else bytearray()
                return text
            except UnicodeDecodeError:
                if trim == min(4, len(buf)) - 1:
                    # Give up, decode with replacement
                    text = buf.decode("utf-8", errors="replace")
                    self._read_buf = bytearray()
                    return text
        return ""

    def _apply_sgr(self, params: list[int]) -> None:
        """Update _char_fmt from a parsed SGR parameter list."""
        i = 0
        while i < len(params):
            p = params[i]
            if p == 0:
                self._char_fmt = QTextCharFormat()
            elif p == 1:
                self._char_fmt.setFontWeight(700)
            elif p in (2, 22):
                self._char_fmt.setFontWeight(400)
            elif p in _SGR_FG_IDX:
                self._char_fmt.setForeground(QColor(_XTERM16[_SGR_FG_IDX[p]]))
            elif p in _SGR_BG_IDX:
                self._char_fmt.setBackground(QColor(_XTERM16[_SGR_BG_IDX[p]]))
            elif p == 39:
                self._char_fmt.clearForeground()
            elif p == 49:
                self._char_fmt.clearBackground()
            elif p == 38 and i + 2 < len(params) and params[i + 1] == 5:
                self._char_fmt.setForeground(_xterm256(params[i + 2]))
                i += 2
            elif p == 48 and i + 2 < len(params) and params[i + 1] == 5:
                self._char_fmt.setBackground(_xterm256(params[i + 2]))
                i += 2
            elif p == 38 and i + 4 < len(params) and params[i + 1] == 2:
                self._char_fmt.setForeground(
                    QColor(params[i + 2], params[i + 3], params[i + 4]))
                i += 4
            elif p == 48 and i + 4 < len(params) and params[i + 1] == 2:
                self._char_fmt.setBackground(
                    QColor(params[i + 2], params[i + 3], params[i + 4]))
                i += 4
            i += 1

    def _render(self, raw: str) -> None:
        """Insert PTY output into the display, applying ANSI colours inline.

        Escape sequences are processed character-by-character:
          - SGR (ESC [ ... m) updates _char_fmt (colour/weight state).
          - All other escape sequences are consumed and discarded.
          - CR (bare \\r) clears the current line for readline redraws.
          - BS (\\x08) deletes the previous character (canonical erase echo).
          - Printable text is inserted with the current _char_fmt.
        """
        cursor = self._display.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)

        i = 0
        while i < len(raw):
            ch = raw[i]

            if ch == "\x1b":
                end = _esc_end(raw, i)
                if end == i:
                    i += 1  # unrecognized / incomplete ESC — skip it
                    continue
                seq = raw[i:end]
                if len(seq) >= 3 and seq[1] == "[" and seq[-1] == "m":
                    # SGR — update colour/weight state
                    self._apply_sgr(_parse_sgr_params(seq[2:-1]))
                elif seq == "\x1b[?1h":
                    # DECCKM set — shell expects SS3 arrow sequences
                    self._app_cursor = True
                elif seq == "\x1b[?1l":
                    # DECCKM reset — shell expects CSI arrow sequences
                    self._app_cursor = False
                i = end

            elif ch in ("\x07", "\x0e", "\x0f"):
                # BEL, SO (^N), SI (^O) — discard
                i += 1

            elif ch == "\r":
                if i + 1 < len(raw) and raw[i + 1] == "\n":
                    # CR+LF — single newline
                    cursor.insertText("\n")
                    i += 2
                else:
                    # Bare CR — clear current line for readline in-place redraw
                    cursor.movePosition(QTextCursor.MoveOperation.StartOfLine)
                    cursor.movePosition(QTextCursor.MoveOperation.EndOfLine,
                                       QTextCursor.MoveMode.KeepAnchor)
                    cursor.removeSelectedText()
                    i += 1

            elif ch == "\x08":
                cursor.deletePreviousChar()
                i += 1

            elif ch == "\x7f":
                cursor.deletePreviousChar()
                i += 1

            elif ch >= " " or ch in ("\n", "\t"):
                cursor.insertText(ch, self._char_fmt)
                i += 1

            else:
                # Drop remaining C0 control characters
                i += 1

        self._display.setTextCursor(cursor)
        self._display.ensureCursorVisible()

    def _write(self, data: bytes) -> None:
        if self._master_fd is not None:
            try:
                os.write(self._master_fd, data)
            except OSError:
                pass

    # ── Keyboard input ────────────────────────────────────────────────────────

    def keyPressEvent(self, event: QKeyEvent) -> None:
        key = event.key()
        mods = event.modifiers()

        if mods & Qt.KeyboardModifier.ControlModifier:
            if mods & Qt.KeyboardModifier.ShiftModifier:
                if key == Qt.Key.Key_C:
                    cursor = self._display.textCursor()
                    if cursor.hasSelection():
                        QApplication.clipboard().setText(cursor.selectedText())
                    return
                if key == Qt.Key.Key_V:
                    text = QApplication.clipboard().text()
                    if text:
                        self._write(text.encode("utf-8", errors="replace"))
                    return
            if Qt.Key.Key_A <= key <= Qt.Key.Key_Z:
                self._write(bytes([key - Qt.Key.Key_A + 1]))
                return

        match key:
            case Qt.Key.Key_Return | Qt.Key.Key_Enter:
                self._write(b"\r")
            case Qt.Key.Key_Backspace:
                # Send DEL (0x7F) — matches slave VERASE configured above.
                # stty erase defaults to ^? (0x7F) on modern Linux.
                self._write(b"\x7f")
            case Qt.Key.Key_Delete:
                self._write(b"\x1b[3~")
            case Qt.Key.Key_Tab:
                self._write(b"\x09")
            case Qt.Key.Key_Escape:
                self._write(b"\x1b")
            case Qt.Key.Key_Up:
                self._write(b"\x1bOA" if self._app_cursor else b"\x1b[A")
            case Qt.Key.Key_Down:
                self._write(b"\x1bOB" if self._app_cursor else b"\x1b[B")
            case Qt.Key.Key_Right:
                self._write(b"\x1bOC" if self._app_cursor else b"\x1b[C")
            case Qt.Key.Key_Left:
                self._write(b"\x1bOD" if self._app_cursor else b"\x1b[D")
            case Qt.Key.Key_Home:
                self._write(b"\x1b[H")
            case Qt.Key.Key_End:
                self._write(b"\x1b[F")
            case Qt.Key.Key_PageUp:
                self._write(b"\x1b[5~")
            case Qt.Key.Key_PageDown:
                self._write(b"\x1b[6~")
            case _:
                text = event.text()
                if text:
                    self._write(text.encode("utf-8", errors="replace"))

    # ── navigate_to integration ───────────────────────────────────────────────

    def navigate_to(self, path: str) -> None:
        """Send `cd <path>` to the running shell."""
        self._write(f"cd {shlex.quote(path)}\n".encode())

    # ── Resize → update PTY window size ──────────────────────────────────────

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if self._master_fd is None:
            return
        font_metrics = self._display.fontMetrics()
        char_w = max(1, font_metrics.averageCharWidth())
        char_h = max(1, font_metrics.height())
        cols = max(1, self._display.width() // char_w)
        rows = max(1, self._display.height() // char_h)
        _set_winsize(self._master_fd, rows, cols)

    # ── Context menu ─────────────────────────────────────────────────────────

    def _on_context_menu(self, pos) -> None:
        menu = QMenu(self)
        cursor = self._display.textCursor()

        copy_act = menu.addAction("Copy\t(Ctrl+Shift+C)")
        copy_act.setEnabled(cursor.hasSelection())

        paste_act = menu.addAction("Paste\t(Ctrl+Shift+V)")
        paste_act.setEnabled(bool(QApplication.clipboard().text()))

        menu.addSeparator()
        select_all_act = menu.addAction("Select All")
        clear_act = menu.addAction("Clear")

        act = menu.exec(self._display.mapToGlobal(pos))
        if act == copy_act:
            cursor = self._display.textCursor()
            if cursor.hasSelection():
                QApplication.clipboard().setText(cursor.selectedText())
        elif act == paste_act:
            text = QApplication.clipboard().text()
            if text:
                self._write(text.encode("utf-8", errors="replace"))
        elif act == select_all_act:
            self._display.selectAll()
        elif act == clear_act:
            self._display.clear()

    # ── Cleanup ───────────────────────────────────────────────────────────────

    def closeEvent(self, event) -> None:
        if self._notifier:
            self._notifier.setEnabled(False)
        if self._proc and self._proc.poll() is None:
            self._proc.terminate()
        if self._master_fd is not None:
            try:
                os.close(self._master_fd)
            except OSError:
                pass
            self._master_fd = None
        super().closeEvent(event)
