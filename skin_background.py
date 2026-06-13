"""Coordinates which skin background the FM content viewports paint.

Decouples the Appearance dialog and startup autoload (which call ``set_active``)
from the FileView instances (which ``register`` themselves and react). This is
about the optional wallpaper PNG only — the palette is handled by skin_manager.
A painter is any object exposing ``apply_skin_background(skin_or_none)``.
"""
from __future__ import annotations

import logging
import weakref

logger = logging.getLogger(__name__)

VALID_FITS = ("cover", "contain", "stretch")

_active = None            # current Skin | None ("off" / none = no wallpaper)
_active_fit = None        # per-skin user fit override (or None → use TOML/default)
_painters: list = []      # weakrefs to registered painters (FileViews)


def set_active(skin, fit=None) -> None:
    """Set the active background skin (None = off) + optional user fit override."""
    global _active, _active_fit
    _active = skin
    _active_fit = fit
    for ref in list(_painters):
        painter = ref()
        if painter is None:
            _painters.remove(ref)
        else:
            painter.apply_skin_background(skin, fit)


def register(painter) -> None:
    """Register a painter and immediately apply the current active background."""
    _painters.append(weakref.ref(painter))
    painter.apply_skin_background(_active, _active_fit)


def active():
    return _active


def resolve_fit(skin, user_override=None) -> str:
    """Effective background fit mode. Order: user override → skin.toml → 'cover'."""
    if isinstance(user_override, str) and user_override.lower() in VALID_FITS:
        return user_override.lower()
    background = getattr(skin, "background", None) if skin is not None else None
    toml_value = background.get("scaling") if isinstance(background, dict) else None
    if isinstance(toml_value, str) and toml_value.lower() in VALID_FITS:
        return toml_value.lower()
    return "cover"
