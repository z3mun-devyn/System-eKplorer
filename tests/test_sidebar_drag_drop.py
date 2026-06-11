"""Regression: NavigationSidebar drag-drop handlers must use the PyQt6 event API.

Bug: _on_drag_enter / _on_drag_move / _on_drop called event.pos() on
QDragEnterEvent/QDragMoveEvent/QDropEvent. PyQt6/Qt6 REMOVED .pos() from drag
events — it is now .position() returning a QPointF. Every sidebar drag handler
hit AttributeError mid-drag, which froze the cursor ("freeze dead in tracks").

The suite missed this because no test drove the drag handlers at all. These
tests exercise each handler with a fake event that exposes ONLY .position()
(no .pos()), so any regression back to event.pos() raises AttributeError and is
caught by the graceful-failure wrapper — which the assertions detect.
"""
from __future__ import annotations

import pytest

from PyQt6.QtCore import QMimeData, QPointF, QUrl, Qt


def _qt():
    pytest.importorskip("PyQt6")
    from PyQt6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def _make_sidebar():
    _app = _qt()
    from views.navigation_sidebar import NavigationSidebar
    sidebar = NavigationSidebar()
    sidebar._app_ref = _app
    return sidebar


class _FakeDragEvent:
    """Mimics a PyQt6 drag/drop event: .position() (QPointF), no .pos()."""

    def __init__(self, urls=None, *, has_urls=True, ctrl=False,
                 position=QPointF(5.0, 5.0)):
        self._mime = QMimeData()
        if urls:
            self._mime.setUrls([QUrl.fromLocalFile(u) for u in urls])
        self._has_urls = has_urls
        self._position = position
        self._ctrl = ctrl
        self.accepted = False
        self.ignored = False

    # PyQt6 API surface (deliberately NO .pos()).
    def position(self):
        return self._position

    def mimeData(self):
        return self._mime

    def acceptProposedAction(self):
        self.accepted = True

    def ignore(self):
        self.ignored = True

    def modifiers(self):
        # Qt6 drop events expose .modifiers(), NOT .keyboardModifiers().
        return (Qt.KeyboardModifier.ControlModifier if self._ctrl
                else Qt.KeyboardModifier.NoModifier)


def _viewport(sidebar):
    return sidebar._quick_tree.viewport()


# ── Drag-enter ────────────────────────────────────────────────────────────────

def test_drag_enter_uses_position_accepts_valid_target(monkeypatch):
    """Valid target → acceptProposedAction; resolver receives a QPoint from .toPoint()."""
    sidebar = _make_sidebar()
    seen = {}

    def _fake_resolve(tree, pos):
        seen["pos"] = pos
        return "/tmp"

    monkeypatch.setattr(sidebar, "_resolve_drop_target", _fake_resolve)

    event = _FakeDragEvent(urls=["/tmp/a.txt"])
    result = sidebar._on_drag_enter(_viewport(sidebar), event)

    assert result is True
    assert event.accepted is True          # would be False if .pos() regressed
    assert event.ignored is False
    # Confirms we reached _resolve_drop_target via .position().toPoint() (a QPoint).
    from PyQt6.QtCore import QPoint
    assert isinstance(seen["pos"], QPoint)


def test_drag_enter_invalid_target_ignores(monkeypatch):
    sidebar = _make_sidebar()
    monkeypatch.setattr(sidebar, "_resolve_drop_target", lambda t, p: None)

    event = _FakeDragEvent(urls=["/tmp/a.txt"])
    result = sidebar._on_drag_enter(_viewport(sidebar), event)

    assert result is True
    assert event.ignored is True
    assert event.accepted is False


def test_drag_enter_no_urls_ignores():
    sidebar = _make_sidebar()
    event = _FakeDragEvent(urls=None)   # empty mime → hasUrls() False
    result = sidebar._on_drag_enter(_viewport(sidebar), event)
    assert result is True
    assert event.ignored is True


def test_drag_enter_graceful_on_exception(monkeypatch):
    """A handler that blows up must ignore() and return True, never raise/hang."""
    sidebar = _make_sidebar()

    def _boom(tree, pos):
        raise RuntimeError("kaboom")

    monkeypatch.setattr(sidebar, "_resolve_drop_target", _boom)
    event = _FakeDragEvent(urls=["/tmp/a.txt"])

    result = sidebar._on_drag_enter(_viewport(sidebar), event)   # must not raise
    assert result is True
    assert event.ignored is True


# ── Drag-move ─────────────────────────────────────────────────────────────────

def test_drag_move_uses_position_accepts_valid_target(monkeypatch):
    sidebar = _make_sidebar()
    monkeypatch.setattr(sidebar, "_resolve_drop_target", lambda t, p: "/tmp")
    event = _FakeDragEvent(urls=["/tmp/a.txt"])

    result = sidebar._on_drag_move(_viewport(sidebar), event)
    assert result is True
    assert event.accepted is True


# ── Drop ──────────────────────────────────────────────────────────────────────

def test_drop_emits_signal_with_matching_args(monkeypatch):
    """Drop on a valid target emits sidebar_drop_requested(paths, target, copy)."""
    sidebar = _make_sidebar()
    monkeypatch.setattr(sidebar, "_resolve_drop_target", lambda t, p: "/tmp")

    captured = {}
    sidebar.sidebar_drop_requested.connect(
        lambda paths, target, copy: captured.update(
            paths=paths, target=target, copy=copy))

    event = _FakeDragEvent(urls=["/tmp/a.txt"], ctrl=True)
    result = sidebar._on_drop(_viewport(sidebar), event)

    assert result is True
    assert event.accepted is True
    assert captured["paths"] == ["/tmp/a.txt"]
    assert captured["target"] == "/tmp"
    assert captured["copy"] is True       # Ctrl held → copy


def test_drop_no_modifier_is_move(monkeypatch):
    sidebar = _make_sidebar()
    monkeypatch.setattr(sidebar, "_resolve_drop_target", lambda t, p: "/tmp")
    captured = {}
    sidebar.sidebar_drop_requested.connect(
        lambda paths, target, copy: captured.update(copy=copy))

    event = _FakeDragEvent(urls=["/tmp/a.txt"], ctrl=False)
    sidebar._on_drop(_viewport(sidebar), event)
    assert captured["copy"] is False


def test_drop_invalid_target_ignores_no_emit(monkeypatch):
    sidebar = _make_sidebar()
    monkeypatch.setattr(sidebar, "_resolve_drop_target", lambda t, p: None)
    fired = []
    sidebar.sidebar_drop_requested.connect(lambda *a: fired.append(a))

    event = _FakeDragEvent(urls=["/tmp/a.txt"])
    result = sidebar._on_drop(_viewport(sidebar), event)

    assert result is True
    assert event.ignored is True
    assert fired == []


def test_drop_graceful_on_exception_releases_cursor(monkeypatch):
    """A drop that raises must acceptProposedAction (release cursor), not hang."""
    sidebar = _make_sidebar()

    def _boom(tree, pos):
        raise RuntimeError("kaboom")

    monkeypatch.setattr(sidebar, "_resolve_drop_target", _boom)
    event = _FakeDragEvent(urls=["/tmp/a.txt"])

    result = sidebar._on_drop(_viewport(sidebar), event)   # must not raise
    assert result is True
    assert event.accepted is True         # cursor released cleanly


# ── Real Qt6 events through the full eventFilter (strongest guard) ─────────────
#
# These build genuine QDragEnterEvent/QDropEvent objects and dispatch them via
# eventFilter, so they catch ANY use of a removed-in-Qt6 event method — both the
# .pos()→.position() and the .keyboardModifiers()→.modifiers() migrations.

def _real_tree_item(sidebar, path: str):
    from PyQt6.QtWidgets import QTreeWidgetItem
    item = QTreeWidgetItem([path])
    item.setData(0, Qt.ItemDataRole.UserRole, path)
    sidebar._quick_tree.addTopLevelItem(item)
    return item


def test_real_qt6_drag_enter_and_drop(tmp_path):
    from PyQt6.QtCore import QPoint, QPointF
    from PyQt6.QtGui import QDragEnterEvent, QDropEvent

    sidebar = _make_sidebar()
    target = str(tmp_path)
    item = _real_tree_item(sidebar, target)
    src = tmp_path / "f.txt"
    src.write_text("x")

    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(src))])
    center = sidebar._quick_tree.visualItemRect(item).center()  # QPoint
    actions = Qt.DropAction.MoveAction | Qt.DropAction.CopyAction
    btn = Qt.MouseButton.LeftButton
    nomod = Qt.KeyboardModifier.NoModifier

    emitted = []
    sidebar.sidebar_drop_requested.connect(
        lambda s, t, c: emitted.append((s, t, c)))

    vp = _viewport(sidebar)

    # Real QDragEnterEvent (constructor takes QPoint) over a valid dir → accepted.
    enter = QDragEnterEvent(center, actions, mime, btn, nomod)
    assert sidebar.eventFilter(vp, enter) is True
    assert enter.isAccepted() is True

    # Real QDropEvent (constructor takes QPointF), plain move.
    drop = QDropEvent(QPointF(center), actions, mime, btn, nomod)
    assert sidebar.eventFilter(vp, drop) is True
    assert emitted[-1] == ([str(src)], target, False)

    # Real QDropEvent with Ctrl held → copy=True (exercises .modifiers()).
    ctrl_drop = QDropEvent(QPointF(center), actions, mime, btn,
                           Qt.KeyboardModifier.ControlModifier)
    sidebar.eventFilter(vp, ctrl_drop)
    assert emitted[-1] == ([str(src)], target, True)

    # Off-tree point → no item → rejected, never emits, never hangs.
    bad = QDragEnterEvent(QPoint(9999, 9999), actions, mime, btn, nomod)
    sidebar.eventFilter(vp, bad)
    assert bad.isAccepted() is False
