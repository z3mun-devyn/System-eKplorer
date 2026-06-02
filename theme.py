"""Surface color helpers (spec §15 — theme-native design principle).

All colors are derived from the active QPalette.  No hardcoded hex for
surfaces or text anywhere in the codebase.  Pass the current palette to
each helper; callers are responsible for re-querying on paletteChanged.
"""

from PyQt6.QtGui import QColor, QPalette


def toolbar_surface(palette: QPalette) -> QColor:
    """Distinct background for the toolbar/breadcrumb area (AlternateBase tone)."""
    return QColor(palette.color(QPalette.ColorRole.AlternateBase))


def modal_overlay() -> QColor:
    """Semi-transparent backdrop at ~35 % opacity for modal dim effect."""
    c = QColor(0, 0, 0)
    c.setAlpha(90)
    return c


def modal_header_bar(palette: QPalette) -> QColor:
    """Darker structural bar for the modal header (AlternateBase tone)."""
    return QColor(palette.color(QPalette.ColorRole.AlternateBase))


def modal_footer_bar(palette: QPalette) -> QColor:
    """Darker structural bar for the modal footer (same tone as header)."""
    return QColor(palette.color(QPalette.ColorRole.AlternateBase))
