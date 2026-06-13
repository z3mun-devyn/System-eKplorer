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

_active = None            # current Skin | None ("off" / none = no wallpaper)
_painters: list = []      # weakrefs to registered painters (FileViews)


def set_active(skin) -> None:
    """Set the active background skin (or None for 'off') and push to painters."""
    global _active
    _active = skin
    for ref in list(_painters):
        painter = ref()
        if painter is None:
            _painters.remove(ref)
        else:
            painter.apply_skin_background(skin)


def register(painter) -> None:
    """Register a painter and immediately apply the current active background."""
    _painters.append(weakref.ref(painter))
    painter.apply_skin_background(_active)


def active():
    return _active
