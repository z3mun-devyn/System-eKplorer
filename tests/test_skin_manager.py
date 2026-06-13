"""M11 P1 — skin_manager palette mechanism.

build_palette is pure (no app needed). The apply/restore round-trip touches a
live QApplication; the GUI side-effects (widgets actually repainting) can't be
unit-asserted here — those are verified manually — but we can assert that
restore_baseline reinstalls the captured palette colors on the app.
"""
import pytest

from PyQt6.QtGui import QColor, QPalette

import skin_manager

_NORMAL = QPalette.ColorGroup.Normal

# A full 9-role dark-red skin, matching the manual confirm snippet.
SKIN = {
    "window": "#0a0a0a",
    "window_text": "#e0e0e0",
    "base": "#0d0d0d",
    "text": "#e0e0e0",
    "alternate_base": "#141414",
    "mid": "#2a2a2a",
    "dark": "#050505",
    "highlight": "#b51a1a",
    "highlighted_text": "#ffffff",
}

_READ_EXPECTATIONS = [
    (QPalette.ColorRole.Window, "#0a0a0a"),
    (QPalette.ColorRole.WindowText, "#e0e0e0"),
    (QPalette.ColorRole.Base, "#0d0d0d"),
    (QPalette.ColorRole.Text, "#e0e0e0"),
    (QPalette.ColorRole.AlternateBase, "#141414"),
    (QPalette.ColorRole.Mid, "#2a2a2a"),
    (QPalette.ColorRole.Dark, "#050505"),
    (QPalette.ColorRole.Highlight, "#b51a1a"),
    (QPalette.ColorRole.HighlightedText, "#ffffff"),
]


_ACTIVE = QPalette.ColorGroup.Active
_INACTIVE = QPalette.ColorGroup.Inactive
_DISABLED = QPalette.ColorGroup.Disabled


@pytest.mark.parametrize("role,hex_", _READ_EXPECTATIONS)
def test_build_palette_sets_nine_read_roles(role, hex_):
    pal = skin_manager.build_palette(SKIN, QPalette())
    assert pal.color(_NORMAL, role).name() == hex_


@pytest.mark.parametrize("role,hex_", _READ_EXPECTATIONS)
def test_build_palette_populates_all_three_groups(role, hex_):
    """Active + Inactive get the full skin colour (so the skin persists on focus
    loss); Disabled is populated too (so it can't fall back to the theme default)."""
    pal = skin_manager.build_palette(SKIN, QPalette())
    assert pal.color(_ACTIVE, role).name() == hex_
    assert pal.color(_INACTIVE, role).name() == hex_
    # Disabled is set (dimmed) — not left at the base/default.
    assert pal.color(_DISABLED, role).name() == _dim_hex(role, hex_)


@pytest.mark.parametrize("role,hex_", _READ_EXPECTATIONS)
def test_build_palette_disabled_differs_from_active(role, hex_):
    pal = skin_manager.build_palette(SKIN, QPalette())
    assert pal.color(_DISABLED, role) != pal.color(_ACTIVE, role)


def _dim_hex(role, hex_):
    """Expected Disabled colour: the module's own dimming of the skin colour."""
    from PyQt6.QtGui import QColor
    return skin_manager._dim(QColor(hex_), QColor(SKIN["mid"])).name()


def test_build_palette_derives_non_read_roles_when_absent():
    """Button/ButtonText/ToolTip*/PlaceholderText/Link/BrightText follow their
    source read role when the skin doesn't name them explicitly."""
    pal = skin_manager.build_palette(SKIN, QPalette())

    derivations = [
        (QPalette.ColorRole.Button,          QPalette.ColorRole.Window),
        (QPalette.ColorRole.ButtonText,      QPalette.ColorRole.WindowText),
        (QPalette.ColorRole.ToolTipBase,     QPalette.ColorRole.AlternateBase),
        (QPalette.ColorRole.ToolTipText,     QPalette.ColorRole.Text),
        (QPalette.ColorRole.PlaceholderText, QPalette.ColorRole.Mid),
        (QPalette.ColorRole.Link,            QPalette.ColorRole.Highlight),
        (QPalette.ColorRole.BrightText,      QPalette.ColorRole.HighlightedText),
    ]
    for target, source in derivations:
        assert pal.color(_NORMAL, target) == pal.color(_NORMAL, source)


def test_build_palette_explicit_derived_role_overrides_derivation():
    """An explicit derived key wins over the source-role derivation."""
    role_map = dict(SKIN, button="#00ff00")
    pal = skin_manager.build_palette(role_map, QPalette())
    assert pal.color(_NORMAL, QPalette.ColorRole.Button).name() == "#00ff00"
    # Window stays its own value, proving the override is independent.
    assert pal.color(_NORMAL, QPalette.ColorRole.Window).name() == "#0a0a0a"


def test_build_palette_copies_base_leaving_unset_roles(qt_app):
    """Roles absent from role_map keep the base palette's color."""
    base = QPalette()
    base.setColor(_NORMAL, QPalette.ColorRole.Window, QColor("#123456"))
    pal = skin_manager.build_palette({"text": "#abcdef"}, base)
    assert pal.color(_NORMAL, QPalette.ColorRole.Window).name() == "#123456"
    assert pal.color(_NORMAL, QPalette.ColorRole.Text).name() == "#abcdef"


def test_restore_baseline_reinstalls_captured_palette(qt_app):
    """capture → apply skin → restore returns the app to the captured colors."""
    if qt_app is None:
        pytest.skip("PyQt6 unavailable")

    skin_manager.capture_baseline(qt_app)
    captured = QPalette(qt_app.palette())

    skin_manager.apply_skin(qt_app, SKIN)
    # Skin took effect on the live app.
    assert qt_app.palette().color(_NORMAL, QPalette.ColorRole.Window).name() == "#0a0a0a"

    skin_manager.restore_baseline(qt_app)
    for role, _ in _READ_EXPECTATIONS:
        assert qt_app.palette().color(_NORMAL, role) == captured.color(_NORMAL, role)
