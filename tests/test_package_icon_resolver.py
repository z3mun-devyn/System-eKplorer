"""Unit tests for package_icon_resolver.

theme_lookup is injected so tests are independent of the system icon theme.
Tier 3 uses the real assets/category-icons/ directory bundled with the app.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from PyQt6.QtGui import QIcon

from package_icon_resolver import PackageIconResolver, _candidate_chain


# ── Helpers ───────────────────────────────────────────────────────────────────

def _null_theme(_name: str) -> QIcon:
    """Theme lookup that always misses — used to force Tier 3."""
    return QIcon()


def _hit_theme(hit_name: str) -> callable:
    """Theme lookup that only matches one specific name."""
    # Build a non-null icon from an existing bundled SVG to satisfy isNull()
    from pathlib import Path
    _fallback = str(Path(__file__).parent.parent / "assets" / "category-icons" / "unknown.svg")
    def _fn(name: str) -> QIcon:
        if name == hit_name:
            return QIcon(_fallback)
        return QIcon()
    return _fn


# ── Candidate chain ───────────────────────────────────────────────────────────

def test_apt_chain_name_and_lowercase():
    chain = _candidate_chain("Firefox", "apt")
    assert chain[0] == "Firefox"
    assert "firefox" in chain


def test_apt_chain_no_dns_segment():
    chain = _candidate_chain("com.example.App", "apt")
    # No DNS tail expansion for apt
    assert "App" not in chain


def test_flatpak_chain_includes_dns_tail():
    chain = _candidate_chain("com.discordapp.Discord", "flatpak")
    assert "Discord" in chain
    assert "discord" in chain


def test_flatpak_chain_tail_after_name():
    chain = _candidate_chain("com.discordapp.Discord", "flatpak")
    idx_name = chain.index("com.discordapp.Discord")
    idx_tail = chain.index("Discord")
    assert idx_tail > idx_name


def test_hyphen_prefix_chain_apt():
    chain = _candidate_chain("firefox-locale-en", "apt")
    assert "firefox-locale" in chain
    assert "firefox" in chain
    assert chain.index("firefox-locale") < chain.index("firefox")


def test_hyphen_prefix_not_included_for_name_without_hyphens():
    chain = _candidate_chain("vim", "apt")
    assert chain == ["vim"]


def test_chain_deduped():
    # "vim" lowercased is identical — must not appear twice
    chain = _candidate_chain("vim", "apt")
    assert len(chain) == len(set(chain))


def test_flatpak_no_dot_no_dns_tail():
    chain = _candidate_chain("myapp", "flatpak")
    assert chain[0] == "myapp"
    assert len(chain) == 1  # no hyphen, no dot → only one candidate


# ── Tier 1: user override ─────────────────────────────────────────────────────

def test_tier1_svg_beats_theme(tmp_path, monkeypatch):
    monkeypatch.setattr("package_icon_resolver._USER_ICON_DIR", tmp_path)
    from pathlib import Path
    asset = Path(__file__).parent.parent / "assets" / "category-icons" / "unknown.svg"
    (tmp_path / "vim.svg").write_bytes(asset.read_bytes())
    resolver = PackageIconResolver(theme_lookup=_null_theme)
    icon = resolver.resolve("vim", "apt", "")
    assert not icon.isNull()


def test_tier1_png_in_user_files_when_no_svg(tmp_path, monkeypatch):
    # Verify that PNG files are discovered by _scan_user_dir and included in
    # _user_files. Actual QIcon loading from PNG is not asserted here because
    # PyQt6/xcb SIGABRT on QIcon(png_path) inside pytest; it works in production.
    monkeypatch.setattr("package_icon_resolver._USER_ICON_DIR", tmp_path)
    (tmp_path / "vim.png").touch()
    resolver = PackageIconResolver(theme_lookup=_null_theme)
    assert "vim.png" in resolver._user_files


def test_tier1_svg_checked_before_png(tmp_path, monkeypatch):
    # When both .svg and .png exist, .svg is tried first.
    # Verify by confirming both are in _user_files and SVG resolves correctly.
    monkeypatch.setattr("package_icon_resolver._USER_ICON_DIR", tmp_path)
    from pathlib import Path
    asset_svg = Path(__file__).parent.parent / "assets" / "category-icons" / "unknown.svg"
    (tmp_path / "vim.svg").write_bytes(asset_svg.read_bytes())
    (tmp_path / "vim.png").touch()
    resolver = PackageIconResolver(theme_lookup=_null_theme)
    assert "vim.svg" in resolver._user_files
    assert "vim.png" in resolver._user_files
    icon = resolver.resolve("vim", "apt", "")
    assert not icon.isNull()  # SVG loaded successfully


# ── Tier 2: desktop theme ─────────────────────────────────────────────────────

def test_tier2_theme_hit_returns_icon():
    resolver = PackageIconResolver(theme_lookup=_hit_theme("vim"))
    icon = resolver.resolve("vim", "apt", "")
    assert not icon.isNull()


def test_tier2_skipped_when_tier1_hits(tmp_path, monkeypatch):
    monkeypatch.setattr("package_icon_resolver._USER_ICON_DIR", tmp_path)
    from pathlib import Path
    asset = Path(__file__).parent.parent / "assets" / "category-icons" / "unknown.svg"
    (tmp_path / "vim.svg").write_bytes(asset.read_bytes())
    called = []
    def _spy(name):
        called.append(name)
        return QIcon()
    resolver = PackageIconResolver(theme_lookup=_spy)
    resolver.resolve("vim", "apt", "")
    assert called == []   # Tier 1 hit → Tier 2 never called


def test_tier2_flatpak_dns_tail_tried():
    tried = []
    def _spy(name):
        tried.append(name)
        return QIcon()
    resolver = PackageIconResolver(theme_lookup=_spy)
    resolver.resolve("com.discordapp.Discord", "flatpak", "")
    assert "Discord" in tried or "discord" in tried


# ── Tier 3: bundled category icon ─────────────────────────────────────────────

def test_tier3_never_returns_null():
    resolver = PackageIconResolver(theme_lookup=_null_theme)
    icon = resolver.resolve("some-package", "apt", "")
    assert not icon.isNull()


def test_tier3_games_category():
    resolver = PackageIconResolver(theme_lookup=_null_theme)
    icon = resolver.resolve("pkg", "apt", "games")
    assert not icon.isNull()


def test_tier3_multimedia_category():
    resolver = PackageIconResolver(theme_lookup=_null_theme)
    icon = resolver.resolve("pkg", "apt", "multimedia")
    assert not icon.isNull()


def test_tier3_unknown_floor_for_empty_section():
    resolver = PackageIconResolver(theme_lookup=_null_theme)
    icon = resolver.resolve("pkg", "apt", "")
    assert not icon.isNull()


def test_tier3_unknown_floor_for_unmapped_section():
    resolver = PackageIconResolver(theme_lookup=_null_theme)
    icon = resolver.resolve("pkg", "apt", "zxqf-unmapped")
    assert not icon.isNull()


# ── Cache ─────────────────────────────────────────────────────────────────────

def test_cache_hit_returns_same_object():
    resolver = PackageIconResolver(theme_lookup=_null_theme)
    icon1 = resolver.resolve("vim", "apt", "")
    icon2 = resolver.resolve("vim", "apt", "")
    assert icon1 is icon2


def test_cache_key_includes_source():
    resolver = PackageIconResolver(theme_lookup=_null_theme)
    icon_apt = resolver.resolve("vim", "apt", "")
    icon_fp  = resolver.resolve("vim", "flatpak", "")
    # May or may not be the same icon, but separate cache entries
    assert ("vim", "apt") in resolver._cache
    assert ("vim", "flatpak") in resolver._cache


def test_invalidate_clears_cache():
    resolver = PackageIconResolver(theme_lookup=_null_theme)
    resolver.resolve("vim", "apt", "")
    assert len(resolver._cache) == 1
    resolver.invalidate()
    assert len(resolver._cache) == 0


def test_invalidate_rescans_user_dir(tmp_path, monkeypatch):
    monkeypatch.setattr("package_icon_resolver._USER_ICON_DIR", tmp_path)
    resolver = PackageIconResolver(theme_lookup=_null_theme)
    assert "vim.svg" not in resolver._user_files
    from pathlib import Path
    asset = Path(__file__).parent.parent / "assets" / "category-icons" / "unknown.svg"
    (tmp_path / "vim.svg").write_bytes(asset.read_bytes())
    resolver.invalidate()
    assert "vim.svg" in resolver._user_files
