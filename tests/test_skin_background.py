"""M11 P4 — skin_background coordinator + FileView wallpaper painter.

The coordinator is pure Python; the FileView tests construct a real widget under
the session QApplication. GUI *painting* itself isn't asserted (can't unit-test
pixels) — we assert the cache/transparency state the painter sets up.
"""
from pathlib import Path

import pytest

import skin_background as sb
import skin_loader


@pytest.fixture
def clean_coordinator():
    """Isolate the module-global coordinator state for each test."""
    saved_active, saved_painters = sb._active, list(sb._painters)
    sb._active = None
    sb._painters = []
    yield
    sb._active, sb._painters = saved_active, saved_painters


class _FakePainter:
    def __init__(self):
        self.received = []

    def apply_skin_background(self, skin, fit=None):
        self.received.append(skin)


# ── coordinator ──────────────────────────────────────────────────────────────

def test_register_applies_current_active(clean_coordinator):
    sb.set_active("SKIN")
    f = _FakePainter()
    sb.register(f)
    assert f.received == ["SKIN"]          # gets active immediately on register


def test_set_active_pushes_to_registered(clean_coordinator):
    f = _FakePainter()
    sb.register(f)                          # receives initial None
    sb.set_active("X")
    assert f.received == [None, "X"]
    assert sb.active() == "X"


def test_off_invalidates(clean_coordinator):
    f = _FakePainter()
    sb.register(f)
    sb.set_active("X")
    sb.set_active(None)                     # "off"
    assert f.received[-1] is None
    assert sb.active() is None


def test_dead_painter_is_pruned(clean_coordinator):
    import gc
    f = _FakePainter()
    sb.register(f)
    del f
    gc.collect()
    sb.set_active("Y")                      # prunes the dead weakref, no error
    assert sb._painters == []


# ── FileView painter ─────────────────────────────────────────────────────────

def test_fileview_applies_and_clears_background(qt_app, clean_coordinator):
    if qt_app is None:
        pytest.skip("PyQt6 unavailable")
    from views.file_view import FileView

    skins = {s.id: s for s in skin_loader.discover_skins(user_dir="/nonexistent")}
    fv = FileView()
    fv.resize(800, 600)

    fv.apply_skin_background(skins["clockwork"])
    assert fv._bg_cache is not None
    assert (fv._bg_cache.width(), fv._bg_cache.height()) == (800, 600)  # cover-cropped
    assert "transparent" in fv._tree.styleSheet()
    assert "transparent" in fv._list.styleSheet()

    fv.apply_skin_background(None)          # off
    assert fv._bg_cache is None
    assert fv._tree.styleSheet() == ""
    assert fv._list.styleSheet() == ""


def test_fileview_missing_bg_falls_back(qt_app, clean_coordinator):
    if qt_app is None:
        pytest.skip("PyQt6 unavailable")
    from views.file_view import FileView

    fv = FileView()
    fv.resize(800, 600)
    bad = skin_loader.Skin(id="bad", name="Bad",
                           background={"image": "nope.png"}, path=Path("/tmp"))
    fv.apply_skin_background(bad)           # must not crash
    assert fv._bg_cache is None
    assert fv._tree.styleSheet() == ""      # no transparency without a real image


def test_fileview_caches_midres_intermediate(qt_app, clean_coordinator):
    """bg.png is decoded once into a mid-res (longest edge <= 1920) source kept in
    memory; the full-res surface is not retained."""
    if qt_app is None:
        pytest.skip("PyQt6 unavailable")
    from views.file_view import FileView

    skins = {s.id: s for s in skin_loader.discover_skins(user_dir="/nonexistent")}
    fv = FileView()
    fv.resize(1000, 700)
    fv.apply_skin_background(skins["twmaf2"])   # 2560x1660 source
    assert fv._bg_source is not None
    assert max(fv._bg_source.width(), fv._bg_source.height()) <= 1920


def test_fileview_resize_rebuild_uses_memory_not_disk(qt_app, clean_coordinator):
    """The post-resize crisp rebuild rescales from the in-memory intermediate —
    it must NOT re-decode the PNG from disk."""
    if qt_app is None:
        pytest.skip("PyQt6 unavailable")
    from unittest import mock
    from views.file_view import FileView

    skins = {s.id: s for s in skin_loader.discover_skins(user_dir="/nonexistent")}
    fv = FileView()
    fv.resize(800, 600)
    fv.apply_skin_background(skins["clockwork"])
    assert (fv._bg_cache.width(), fv._bg_cache.height()) == (800, 600)

    # Resize without rebuilding: stale cache kept (paintEvent stretches it).
    fv.resize(1200, 900)
    assert (fv._bg_cache.width(), fv._bg_cache.height()) == (800, 600)

    # The debounced rebuild produces a crisp cache at the new size, no disk decode.
    with mock.patch("views.file_view.QPixmap") as pixmap_cls:
        fv._rebuild_bg_cache_and_repaint()
        assert not pixmap_cls.called          # no PNG re-decode
    assert (fv._bg_cache.width(), fv._bg_cache.height()) == (1200, 900)


# ── fit modes ────────────────────────────────────────────────────────────────

def test_fit_modes_math(qt_app):
    """cover/stretch → exact viewport; contain → aspect-preserving fit inside."""
    if qt_app is None:
        pytest.skip("PyQt6 unavailable")
    from PyQt6.QtCore import Qt
    from PyQt6.QtGui import QPixmap
    from views.file_view import FileView

    src = QPixmap(200, 100)                    # 2:1 source
    fast = Qt.TransformationMode.FastTransformation

    cover = FileView._fit(src, "cover", 100, 100, fast)
    assert (cover.width(), cover.height()) == (100, 100)          # fills, cropped

    contain = FileView._fit(src, "contain", 100, 100, fast)
    assert (contain.width(), contain.height()) == (100, 50)       # aspect kept, fits

    stretch = FileView._fit(src, "stretch", 100, 100, fast)
    assert (stretch.width(), stretch.height()) == (100, 100)      # exact, distorted

    # contain when height is the binding dimension
    contain_tall = FileView._fit(src, "contain", 50, 100, fast)
    assert (contain_tall.width(), contain_tall.height()) == (50, 25)


def test_resolve_fit_order_user_then_toml_then_cover():
    """Resolution: user override > skin.toml scaling > 'cover'."""
    contain = skin_loader.Skin(id="c", name="c",
                               background={"image": "bg.png", "scaling": "contain"})
    nobg = skin_loader.Skin(id="n", name="n")
    assert sb.resolve_fit(contain, "stretch") == "stretch"   # user wins
    assert sb.resolve_fit(contain, None) == "contain"        # toml default
    assert sb.resolve_fit(contain, "bogus") == "contain"     # bad user → toml
    assert sb.resolve_fit(contain, "STRETCH") == "stretch"   # case-insensitive
    assert sb.resolve_fit(nobg, None) == "cover"             # no toml → cover
    assert sb.resolve_fit(None, None) == "cover"             # off / none → cover


def test_scaling_value_parsed_and_defaulted(qt_app, clean_coordinator):
    if qt_app is None:
        pytest.skip("PyQt6 unavailable")
    from views.file_view import FileView
    from skin_loader import Skin, discover_skins

    cw = next(s for s in discover_skins(user_dir="/nonexistent") if s.id == "clockwork")
    fv = FileView()
    fv.resize(400, 300)
    for value, expected in [("contain", "contain"), ("stretch", "stretch"),
                            ("WeIrD", "cover"), (None, "cover")]:
        bg = {"image": "bg.png"}
        if value is not None:
            bg["scaling"] = value
        fv.apply_skin_background(Skin(id="t", name="t", background=bg, path=cw.path))
        assert fv._bg_scaling == expected
