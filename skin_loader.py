"""Skin discovery + parsing for the M11 skin engine (data layer — no UI, no Qt).

A skin is a folder holding ``skin.toml`` ([meta] + optional [palette] / [background]
/ [[attribution]]) plus optional assets (e.g. ``bg.png``). This module reads those
folders into ``Skin`` dataclasses and merges the bundled set with the user's. It does
NOT touch Qt, settings, or painting: ``skin_manager`` applies palettes, ``main.py``
wires autoload, and background image rendering is deferred to P4 (we parse the
[background] block here but never paint it).
"""
from __future__ import annotations

import logging
import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

SUPPORTED_SCHEMA = 1
OFF_ID = "off"

# Palette keys skin_manager understands: the 9 read roles plus the 7 derived
# overrides. Kept local so this module stays decoupled from skin_manager.
PALETTE_ROLE_KEYS = (
    "window", "window_text", "base", "text", "alternate_base",
    "mid", "dark", "highlight", "highlighted_text",
    "button", "button_text", "tooltip_base", "tooltip_text",
    "placeholder_text", "link", "bright_text",
)

_HEX_RE = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$")

_BUNDLED_SKINS_DIR = Path(__file__).resolve().parent / "assets" / "skins"
_USER_SKINS_DIR = Path.home() / ".config" / "ekplorer" / "skins"


@dataclass(frozen=True)
class Skin:
    id: str
    name: str
    description: str = ""
    version: str = ""
    author: str = ""
    palette: dict[str, str] | None = None
    background: dict | None = None
    attribution: list = field(default_factory=list)
    path: Path | None = None  # source folder, for resolving assets like bg.png


def _off_skin() -> Skin:
    """Synthetic baseline entry — selecting it means 'no skin' (theme-native)."""
    return Skin(
        id=OFF_ID,
        name="Off (theme-native)",
        description="Use the system/Plasma color scheme. No skin applied.",
    )


def _clean_palette(raw: dict, skin_id: str) -> dict[str, str]:
    """Keep entries with a valid hex string; drop + log the rest."""
    palette: dict[str, str] = {}
    for role, value in raw.items():
        if isinstance(value, str) and _HEX_RE.match(value.strip()):
            palette[role] = value.strip()
        else:
            logger.warning("skin %r: dropping role %r — invalid hex %r",
                           skin_id, role, value)
    return palette


def _normalize_attribution(raw) -> list:
    if isinstance(raw, dict):       # single [attribution] table
        return [raw]
    if isinstance(raw, list):       # [[attribution]] array of tables
        return [a for a in raw if isinstance(a, dict)]
    return []


def parse_skin(folder) -> Skin | None:
    """Parse ``folder/skin.toml`` into a Skin, or None if it can't be used.

    Refuses (returns None, logs) on: missing/unreadable/malformed TOML, missing
    [meta], or a schema newer than SUPPORTED_SCHEMA. A missing [palette] yields
    palette=None (allowed). Individual roles with bad hex are dropped (others
    kept). Unknown top-level blocks are ignored silently.
    """
    folder = Path(folder)
    toml_path = folder / "skin.toml"
    if not toml_path.is_file():
        logger.debug("no skin.toml in %s", folder)
        return None
    try:
        with open(toml_path, "rb") as fh:
            data = tomllib.load(fh)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        logger.warning("skin %s: cannot read skin.toml — %s", folder, exc)
        return None

    meta = data.get("meta")
    if not isinstance(meta, dict):
        logger.warning("skin %s: [meta] missing or malformed — refusing", folder)
        return None

    schema = meta.get("schema", 1)
    if not isinstance(schema, int) or isinstance(schema, bool):
        logger.warning("skin %s: non-integer schema %r — refusing", folder, schema)
        return None
    if schema > SUPPORTED_SCHEMA:
        logger.warning("skin %s: schema %d > supported %d — refusing",
                       folder, schema, SUPPORTED_SCHEMA)
        return None

    skin_id = str(meta.get("id") or folder.name)

    raw_palette = data.get("palette")
    if raw_palette is None:
        palette = None
    elif isinstance(raw_palette, dict):
        palette = _clean_palette(raw_palette, skin_id)
    else:
        logger.warning("skin %s: [palette] malformed — treating as none", folder)
        palette = None

    background = data.get("background")
    if not isinstance(background, dict):
        background = None

    return Skin(
        id=skin_id,
        name=str(meta.get("name", skin_id)),
        description=str(meta.get("description", "")),
        version=str(meta.get("version", "")),
        author=str(meta.get("author", "")),
        palette=palette,
        background=background,
        attribution=_normalize_attribution(data.get("attribution")),
        path=folder,
    )


def _scan(directory: Path) -> list[Skin]:
    if not directory.is_dir():
        return []
    out: list[Skin] = []
    for toml_path in sorted(directory.glob("*/skin.toml")):
        if toml_path.parent.name.startswith("_"):
            continue   # reserved (e.g. _template) — never a selectable skin
        skin = parse_skin(toml_path.parent)
        if skin is not None:
            out.append(skin)
    return out


def discover_skins(bundled_dir=None, user_dir=None) -> list[Skin]:
    """All usable skins: synthetic 'off' first, then bundled, then user.

    Scans ``assets/skins/*/skin.toml`` then ``~/.config/ekplorer/skins/*/skin.toml``.
    On an id collision the user skin wins (and we log it); the bundled skin's
    position in the list is preserved.
    """
    bundled_dir = _BUNDLED_SKINS_DIR if bundled_dir is None else Path(bundled_dir)
    user_dir = _USER_SKINS_DIR if user_dir is None else Path(user_dir)

    merged: dict[str, Skin] = {}
    for skin in _scan(bundled_dir):
        merged[skin.id] = skin
    for skin in _scan(user_dir):
        if skin.id in merged:
            logger.info("user skin %r overrides bundled skin", skin.id)
        merged[skin.id] = skin

    return [_off_skin()] + list(merged.values())


def resolve_role_map(active_id, skins, override_lookup=None) -> dict | None:
    """Role map to apply for ``active_id``, or None when the baseline should stand.

    None/"off"/unknown-id/palette-less all return None (caller leaves baseline).
    When a palette is found and ``override_lookup`` is given, per-role override
    values it returns are layered on top of the skin's palette.
    """
    if not active_id or active_id == OFF_ID:
        return None
    skin = {s.id: s for s in skins}.get(active_id)
    if skin is None:
        logger.warning("active skin %r not found on disk — using baseline", active_id)
        return None
    if skin.palette is None:
        logger.warning("active skin %r has no palette — using baseline", active_id)
        return None

    role_map = dict(skin.palette)
    if override_lookup is not None:
        for role in PALETTE_ROLE_KEYS:
            val = override_lookup(role)
            if val:
                role_map[role] = val
    return role_map
