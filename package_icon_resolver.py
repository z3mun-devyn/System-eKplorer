"""Three-tier package icon resolution.

Tier 1 — User override:
  ~/.local/share/ekplorer/icons/{name}.svg else .png
  Directory is scanned once at construction and again on invalidate().

Tier 2 — Desktop theme (QIcon.fromTheme):
  Candidate chain: name as-is → lowercased → flatpak DNS tail (both cases)
  → hyphen-prefix prefixes (each with both cases), deduped first-occurrence.

Tier 3 — Bundled category icon (never returns null):
  assets/category-icons/{key}.svg else .png, where key comes from
  strings.CATEGORY_ICON_KEYS[display_cat]. Falls back to "unknown" when the
  category is empty or unmapped; unknown.svg is always bundled.

Inject theme_lookup (default QIcon.fromTheme) for test isolation.
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable

from PyQt6.QtGui import QIcon

import strings

_ASSET_DIR = Path(__file__).parent / "assets" / "category-icons"
_USER_ICON_DIR = Path.home() / ".local" / "share" / "ekplorer" / "icons"


# ── Candidate chain for Tier 2 ────────────────────────────────────────────────

def _candidate_chain(name: str, source: str) -> list[str]:
    """Build ordered, deduped list of theme icon name candidates."""
    seen: set[str] = set()
    result: list[str] = []

    def add(s: str) -> None:
        if s and s not in seen:
            seen.add(s)
            result.append(s)

    add(name)
    add(name.lower())

    if source == "flatpak" and "." in name:
        tail = name.rsplit(".", 1)[1]
        add(tail)
        add(tail.lower())

    parts = name.split("-")
    for i in range(len(parts) - 1, 0, -1):
        prefix = "-".join(parts[:i])
        add(prefix)
        add(prefix.lower())

    return result


# ── Resolver ──────────────────────────────────────────────────────────────────

class PackageIconResolver:
    def __init__(self,
                 theme_lookup: Callable[[str], QIcon] | None = None) -> None:
        self._theme = theme_lookup if theme_lookup is not None else QIcon.fromTheme
        self._cache: dict[tuple[str, str], QIcon] = {}
        self._user_dir = _USER_ICON_DIR
        self._user_dir.mkdir(parents=True, exist_ok=True)
        self._user_files: set[str] = self._scan_user_dir()
        self._asset_files: set[str] = self._scan_asset_dir()

    # ── Public API ────────────────────────────────────────────────────────────

    def resolve(self, name: str, source: str, section: str = "") -> QIcon:
        key = (name, source)
        if key in self._cache:
            return self._cache[key]
        icon = (self._tier1(name)
                or self._tier2(name, source)
                or self._tier3(section))
        self._cache[key] = icon
        return icon

    def invalidate(self) -> None:
        self._cache.clear()
        self._user_files = self._scan_user_dir()

    # ── Tier 1: user override ─────────────────────────────────────────────────

    def _tier1(self, name: str) -> QIcon | None:
        for ext in (".svg", ".png"):
            filename = name + ext
            if filename in self._user_files:
                icon = QIcon(str(self._user_dir / filename))
                if not icon.isNull():
                    return icon
        return None

    # ── Tier 2: desktop theme ─────────────────────────────────────────────────

    def _tier2(self, name: str, source: str) -> QIcon | None:
        for candidate in _candidate_chain(name, source):
            icon = self._theme(candidate)
            if not icon.isNull():
                return icon
        return None

    # ── Tier 3: bundled category icon ─────────────────────────────────────────

    def _tier3(self, section: str) -> QIcon:
        cat_name = strings.package_category(section)
        icon_key = strings.CATEGORY_ICON_KEYS.get(cat_name, "unknown")
        icon = self._load_asset(icon_key)
        if icon is not None:
            return icon
        # Final floor: always-bundled unknown icon
        icon = self._load_asset("unknown")
        return icon if icon is not None else QIcon()

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _load_asset(self, key: str) -> QIcon | None:
        for ext in (".svg", ".png"):
            filename = key + ext
            if filename in self._asset_files:
                icon = QIcon(str(_ASSET_DIR / filename))
                if not icon.isNull():
                    return icon
        return None

    def _scan_user_dir(self) -> set[str]:
        try:
            return {f.name for f in self._user_dir.iterdir()
                    if f.suffix in (".svg", ".png")}
        except OSError:
            return set()

    def _scan_asset_dir(self) -> set[str]:
        try:
            return {f.name for f in _ASSET_DIR.iterdir()
                    if f.suffix in (".svg", ".png")}
        except OSError:
            return set()
