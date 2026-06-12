"""Runtime palette controller for the M11 skin engine.

Skinning works by overriding the active ``QApplication`` palette: ``theme.py``
and every ``palette(...)`` QSS reference follow whatever palette is installed.
This module is the pure mechanism for that — it builds a ``QPalette`` from a
flat ``{role_name: "#hex"}`` map, applies it under the Fusion style (which
honours ``setPalette`` for all roles), and restores the exact startup baseline
when a skin is turned off.

No settings/TOML/UI dependencies live here on purpose: this is the controller,
callers own persistence and presentation.
"""

from PyQt6.QtGui import QColor, QPalette

# ── Module state: the startup baseline, captured once before any skin ────────
_baseline_palette: QPalette | None = None
_baseline_style: str | None = None

# The 9 read roles confirmed by recon, keyed by their flat role-map name.
_READ_ROLES: dict[str, QPalette.ColorRole] = {
    "window":           QPalette.ColorRole.Window,
    "window_text":      QPalette.ColorRole.WindowText,
    "base":             QPalette.ColorRole.Base,
    "text":             QPalette.ColorRole.Text,
    "alternate_base":   QPalette.ColorRole.AlternateBase,
    "mid":              QPalette.ColorRole.Mid,
    "dark":             QPalette.ColorRole.Dark,
    "highlight":        QPalette.ColorRole.Highlight,
    "highlighted_text": QPalette.ColorRole.HighlightedText,
}

# Non-read roles that native Fusion widgets still paint with. We derive each
# from a read role so buttons/tooltips/links don't clash with the skin, unless
# the caller overrides it explicitly via the matching key. Format:
#   derived_key -> (target role, source role to copy from)
_DERIVED_ROLES: dict[str, tuple[QPalette.ColorRole, QPalette.ColorRole]] = {
    "button":           (QPalette.ColorRole.Button,        QPalette.ColorRole.Window),
    "button_text":      (QPalette.ColorRole.ButtonText,    QPalette.ColorRole.WindowText),
    "tooltip_base":     (QPalette.ColorRole.ToolTipBase,   QPalette.ColorRole.AlternateBase),
    "tooltip_text":     (QPalette.ColorRole.ToolTipText,   QPalette.ColorRole.Text),
    "placeholder_text": (QPalette.ColorRole.PlaceholderText, QPalette.ColorRole.Mid),
    "link":             (QPalette.ColorRole.Link,          QPalette.ColorRole.Highlight),
    "bright_text":      (QPalette.ColorRole.BrightText,    QPalette.ColorRole.HighlightedText),
}

_NORMAL = QPalette.ColorGroup.Normal


def capture_baseline(app) -> None:
    """Snapshot the theme-native style + palette before any skin is applied.

    Call ONCE at startup, before the first ``apply_skin``. This is what
    ``restore_baseline`` ("Off"/theme-native) replays.
    """
    global _baseline_palette, _baseline_style
    _baseline_style = app.style().objectName()
    _baseline_palette = QPalette(app.palette())  # detached copy


def build_palette(role_map: dict[str, str], base: QPalette) -> QPalette:
    """Return a copy of ``base`` with the skin's colors applied (Normal group).

    Sets any of the 9 read roles present in ``role_map``, then derives the
    non-read roles (Button/ButtonText/ToolTip*/PlaceholderText/Link/BrightText)
    from their source role so native widgets stay coherent — unless the caller
    supplied the derived role explicitly. The Disabled group is left to
    Fusion's automatic dimming for v1.
    """
    pal = QPalette(base)

    for key, role in _READ_ROLES.items():
        if key in role_map:
            pal.setColor(_NORMAL, role, QColor(role_map[key]))

    for key, (target, source) in _DERIVED_ROLES.items():
        if key in role_map:
            pal.setColor(_NORMAL, target, QColor(role_map[key]))
        else:
            pal.setColor(_NORMAL, target, pal.color(_NORMAL, source))

    return pal


def apply_skin(app, role_map: dict[str, str]) -> None:
    """Install a skin: force Fusion (full palette fidelity) and set the palette.

    Always builds from the captured baseline so successive applies don't stack.
    """
    if _baseline_palette is None:
        capture_baseline(app)
    app.setStyle("Fusion")
    app.setPalette(build_palette(role_map, _baseline_palette))


def restore_baseline(app) -> None:
    """Return the app to the exact style + palette captured at startup ("Off")."""
    if _baseline_style is not None:
        app.setStyle(_baseline_style)
    if _baseline_palette is not None:
        app.setPalette(QPalette(_baseline_palette))
