#!/usr/bin/env python3
"""THROWAWAY preview tool (NOT wired into the app — safe to delete).

Renders cover-crop (fill + center-crop) previews of every assets/skins/*/bg.png at
the real P4 target shapes, so we can eyeball which skins lose their subject to a
center crop and therefore need an anchor field. Uses the same Qt scaling path P4
would (KeepAspectRatioByExpanding → center copy).

Run:  QT_QPA_PLATFORM=offscreen .venv/bin/python scripts/bg_preview.py
Out:  /tmp/bg_preview/<id>_<WxH>.png
"""
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QGuiApplication, QPixmap

TARGETS = [
    (1280, 800),    # 16:10 main window
    (680, 460),     # Configure dialog
    (320, 720),     # tall sidebar-ish
    (2560, 1080),   # 21:9 maximized
]

SKINS_DIR = Path(__file__).resolve().parent.parent / "assets" / "skins"
OUT_DIR = Path("/tmp/bg_preview")


def cover_crop(src: QPixmap, w: int, h: int) -> QPixmap:
    scaled = src.scaled(
        w, h,
        Qt.AspectRatioMode.KeepAspectRatioByExpanding,
        Qt.TransformationMode.SmoothTransformation,
    )
    x = (scaled.width() - w) // 2
    y = (scaled.height() - h) // 2
    return scaled.copy(x, y, w, h)


def main() -> int:
    _app = QGuiApplication(sys.argv)  # noqa: F841 — keep alive for QPixmap
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    bgs = sorted(SKINS_DIR.glob("*/bg.png"))
    if not bgs:
        print(f"no bg.png found under {SKINS_DIR}", file=sys.stderr)
        return 1

    for bg in bgs:
        skin_id = bg.parent.name
        src = QPixmap(str(bg))
        if src.isNull():
            print(f"  ! {skin_id}: could not load {bg}", file=sys.stderr)
            continue
        sw, sh = src.width(), src.height()
        print(f"{skin_id:12} src {sw}x{sh} (aspect {sw / sh:.2f})")
        for w, h in TARGETS:
            out = OUT_DIR / f"{skin_id}_{w}x{h}.png"
            cover_crop(src, w, h).save(str(out), "PNG")
            print(f"   -> {out.name}")

    print(f"\nDone. Open {OUT_DIR}/ to eyeball the crops.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
