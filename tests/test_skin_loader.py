"""M11 P2 — skin_loader parsing/discovery + main.py autoload.

parse_skin / discover_skins / resolve_role_map are pure (no Qt). The autoload
test drives main._autoload_active_skin against the live session QApplication with
an injected temp settings repo; it restores the baseline afterwards.
"""
import textwrap

import pytest

from PyQt6.QtGui import QPalette

import skin_loader

_NORMAL = QPalette.ColorGroup.Normal

GOOD_TOML = """\
[meta]
schema = 1
id = "demo"
name = "Demo"
description = "A demo skin."
version = "0.2.0"
author = "tester"

[palette]
window = "#101010"
window_text = "#eeeeee"
base = "#0a0a0a"
text = "#eeeeee"
alternate_base = "#181818"
mid = "#404040"
dark = "#050505"
highlight = "#cc2222"
highlighted_text = "#ffffff"

[background]
image = "bg.png"
mode = "cover"

[[attribution]]
text = "Original artwork."
note = "in-house"
"""


def _write_skin(folder, toml_text):
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "skin.toml").write_text(textwrap.dedent(toml_text))
    return folder


# ── parse_skin ────────────────────────────────────────────────────────────────

def test_parse_skin_good(tmp_path):
    skin = skin_loader.parse_skin(_write_skin(tmp_path / "demo", GOOD_TOML))
    assert skin is not None
    assert skin.id == "demo"
    assert skin.name == "Demo"
    assert skin.version == "0.2.0"
    assert skin.palette is not None and len(skin.palette) == 9
    assert skin.palette["highlight"] == "#cc2222"
    assert skin.background == {"image": "bg.png", "mode": "cover"}
    assert skin.attribution == [{"text": "Original artwork.", "note": "in-house"}]


def test_parse_skin_missing_palette_is_none(tmp_path):
    skin = skin_loader.parse_skin(_write_skin(
        tmp_path / "np", '[meta]\nschema=1\nid="np"\nname="No Palette"\n'))
    assert skin is not None
    assert skin.palette is None


def test_parse_skin_bad_hex_drops_role_keeps_rest(tmp_path, caplog):
    toml = (
        '[meta]\nschema=1\nid="bh"\nname="Bad Hex"\n'
        '[palette]\nwindow="#123456"\ntext="nope"\nbase="#222222"\n'
    )
    with caplog.at_level("WARNING"):
        skin = skin_loader.parse_skin(_write_skin(tmp_path / "bh", toml))
    assert skin.palette == {"window": "#123456", "base": "#222222"}
    assert "text" in caplog.text and "invalid hex" in caplog.text


def test_parse_skin_future_schema_refused(tmp_path):
    skin = skin_loader.parse_skin(_write_skin(
        tmp_path / "fut", '[meta]\nschema=99\nid="fut"\nname="Future"\n'))
    assert skin is None


def test_parse_skin_missing_toml_returns_none(tmp_path):
    (tmp_path / "empty").mkdir()
    assert skin_loader.parse_skin(tmp_path / "empty") is None


def test_parse_skin_malformed_toml_returns_none(tmp_path):
    folder = tmp_path / "broken"
    folder.mkdir()
    (folder / "skin.toml").write_text("this is = = not toml [[[")
    assert skin_loader.parse_skin(folder) is None


def test_parse_skin_unknown_block_ignored(tmp_path):
    toml = (
        '[meta]\nschema=1\nid="snd"\nname="Sound"\n'
        '[palette]\nwindow="#111111"\n'
        '[sounds]\nclick="boop.wav"\n'
    )
    skin = skin_loader.parse_skin(_write_skin(tmp_path / "snd", toml))
    assert skin is not None and skin.palette == {"window": "#111111"}


# ── discover_skins ──────────────────────────────────────────────────────────────

def test_discover_off_is_synthetic_and_first(tmp_path):
    skins = skin_loader.discover_skins(bundled_dir=tmp_path / "none",
                                       user_dir=tmp_path / "alsonone")
    assert skins[0].id == "off"
    assert skins[0].palette is None


def test_discover_merges_user_over_bundled(tmp_path, caplog):
    bundled = tmp_path / "bundled"
    user = tmp_path / "user"
    _write_skin(bundled / "demo", GOOD_TOML)
    _write_skin(bundled / "keep", '[meta]\nschema=1\nid="keep"\nname="Keep"\n')
    # user redefines "demo" (collision → user wins) and adds "extra"
    _write_skin(user / "demo",
                '[meta]\nschema=1\nid="demo"\nname="Demo (user)"\n')
    _write_skin(user / "extra", '[meta]\nschema=1\nid="extra"\nname="Extra"\n')

    with caplog.at_level("INFO"):
        skins = skin_loader.discover_skins(bundled_dir=bundled, user_dir=user)

    by_id = {s.id: s for s in skins}
    assert skins[0].id == "off"
    assert set(by_id) == {"off", "demo", "keep", "extra"}
    assert by_id["demo"].name == "Demo (user)"        # user won
    assert "overrides bundled" in caplog.text


def test_discover_real_bundled_set():
    skins = skin_loader.discover_skins(user_dir="/nonexistent-user-dir")
    ids = {s.id for s in skins}
    assert {"off", "ek-imp", "twmaf1", "twmaf2",
            "ignorance", "clockwork", "backyard"} <= ids


def test_bundled_skins_have_background_and_attribution():
    """P4: every bundled skin parses a [background] (cover/center/opacity) and an
    [attribution] with author + source."""
    skins = [s for s in skin_loader.discover_skins(user_dir="/nonexistent")
             if s.id != "off"]
    assert len(skins) == 6
    for s in skins:
        assert s.background is not None, s.id
        assert s.background.get("scaling") == "cover", s.id
        assert s.background.get("anchor") == "center", s.id
        assert "opacity" in s.background, s.id
        assert s.background.get("image") == "bg.png", s.id
        assert s.attribution, s.id
        assert s.attribution[0].get("author"), s.id
        assert s.attribution[0].get("source"), s.id


# ── resolve_role_map ────────────────────────────────────────────────────────────

@pytest.fixture
def demo_skins():
    return [
        skin_loader.Skin(id="off", name="Off"),
        skin_loader.Skin(id="demo", name="Demo",
                         palette={"window": "#101010", "text": "#eeeeee"}),
        skin_loader.Skin(id="bgonly", name="BG only", palette=None),
    ]


@pytest.mark.parametrize("active", [None, "", "off"])
def test_resolve_baseline_cases_return_none(active, demo_skins):
    assert skin_loader.resolve_role_map(active, demo_skins) is None


def test_resolve_unknown_id_returns_none(demo_skins):
    assert skin_loader.resolve_role_map("ghost", demo_skins) is None


def test_resolve_palette_less_returns_none(demo_skins):
    assert skin_loader.resolve_role_map("bgonly", demo_skins) is None


def test_resolve_known_returns_palette_copy(demo_skins):
    rm = skin_loader.resolve_role_map("demo", demo_skins)
    assert rm == {"window": "#101010", "text": "#eeeeee"}


def test_resolve_overrides_layered_on_top(demo_skins):
    overrides = {"window": "#abcdef"}
    rm = skin_loader.resolve_role_map(
        "demo", demo_skins, override_lookup=lambda role: overrides.get(role))
    assert rm["window"] == "#abcdef"   # override won
    assert rm["text"] == "#eeeeee"     # untouched


# ── main.py autoload (drives the live session QApplication) ──────────────────────

def test_autoload_applies_stored_skin_and_falls_back(qt_app, tmp_path):
    if qt_app is None:
        pytest.skip("PyQt6 unavailable")
    import main
    import skin_manager
    from backends.settings_backend import SettingsRepository

    def win():
        return qt_app.palette().color(_NORMAL, QPalette.ColorRole.Window).name()

    skin_manager.capture_baseline(qt_app)
    baseline = win()
    repo = SettingsRepository(tmp_path / "settings.db")
    # Expected window colour derived from the skin (not hardcoded) so palette
    # tuning in twmaf1/skin.toml doesn't break this test.
    from PyQt6.QtGui import QColor
    twmaf1 = next(s for s in skin_loader.discover_skins(user_dir="/nonexistent")
                  if s.id == "twmaf1")
    expected = QColor(twmaf1.palette["window"]).name()
    try:
        repo.set("appearance.active_skin", "twmaf1")
        main._autoload_active_skin(qt_app, settings=repo)
        assert win() == expected                # autoloaded, no keypress

        skin_manager.restore_baseline(qt_app)
        repo.set("appearance.active_skin", "does-not-exist")
        main._autoload_active_skin(qt_app, settings=repo)
        assert win() == baseline                # missing id → baseline, no crash
    finally:
        skin_manager.restore_baseline(qt_app)
