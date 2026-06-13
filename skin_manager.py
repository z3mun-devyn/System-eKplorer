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


def _dim(color: QColor, toward: QColor,
         blend: float = 0.4, value_scale: float = 0.85) -> QColor:
    """Mute ``color`` for the Disabled group: blend toward Mid, then darken.

    Derived entirely from the skin's own colours (no hardcoded grey). The
    value-scale guarantees the dimmed result differs from the source even for
    the Mid role itself (which blends toward itself)."""
    out = QColor(
        round(color.red()   * (1 - blend) + toward.red()   * blend),
        round(color.green() * (1 - blend) + toward.green() * blend),
        round(color.blue()  * (1 - blend) + toward.blue()  * blend),
        color.alpha(),
    )
    h, s, v, a = out.getHsv()
    out.setHsv(h, s, round(v * value_scale), a)
    return out


def build_palette(role_map: dict[str, str], base: QPalette) -> QPalette:
    """Return a copy of ``base`` with the skin's colors applied to ALL groups.

    Sets any of the 9 read roles present in ``role_map``, then derives the
    non-read roles (Button/ButtonText/ToolTip*/PlaceholderText/Link/BrightText)
    from their source role so native widgets stay coherent — unless the caller
    supplied the derived role explicitly. Every role is written to Active AND
    Inactive (so the skin persists when the window loses focus) and to Disabled
    in a dimmed form (so disabled widgets still read as disabled).
    """
    pal = QPalette(base)

    # Resolve the final Active colour for each role we will set.
    resolved: dict[QPalette.ColorRole, QColor] = {}
    for key, role in _READ_ROLES.items():
        if key in role_map:
            resolved[role] = QColor(role_map[key])

    for key, (target, source) in _DERIVED_ROLES.items():
        if key in role_map:
            resolved[target] = QColor(role_map[key])
        elif source in resolved:
            resolved[target] = QColor(resolved[source])
        else:
            resolved[target] = QColor(base.color(_NORMAL, source))

    # Mid reference for dimming the Disabled group — skin's Mid if set, else base.
    mid_ref = resolved.get(QPalette.ColorRole.Mid)
    if mid_ref is None:
        mid_ref = QColor(base.color(_NORMAL, QPalette.ColorRole.Mid))

    for role, color in resolved.items():
        pal.setColor(QPalette.ColorGroup.Active, role, color)
        pal.setColor(QPalette.ColorGroup.Inactive, role, color)
        pal.setColor(QPalette.ColorGroup.Disabled, role, _dim(color, mid_ref))

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
