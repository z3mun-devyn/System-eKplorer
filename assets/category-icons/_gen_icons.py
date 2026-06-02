"""Generate placeholder category icons (SVG + PNG) for M7."""
import struct, zlib
from pathlib import Path

HERE = Path(__file__).parent

ICONS = {
    "accessibility":           ("#4fc3f7", "A"),
    "development":             ("#ff9800", "{}"),
    "education":               ("#4caf50", "Ed"),
    "games":                   ("#f44336", "G"),
    "graphics":                ("#9c27b0", "Gr"),
    "hardware-drivers":        ("#9e9e9e", "HW"),
    "internet-communications": ("#009688", "Net"),
    "multimedia":              ("#e91e63", "MM"),
    "productivity":            ("#ffc107", "Pr"),
    "science-math":            ("#00bcd4", "Sc"),
    "system-utilities":        ("#1565c0", "Sys"),
    "themes-fonts":            ("#f06292", "Tf"),
    "unknown":                 ("#78909c", "?"),
}

SVG_TMPL = """\
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">
  <rect width="64" height="64" rx="12" ry="12" fill="{fill}"/>
  <text x="32" y="38" font-family="sans-serif" font-size="20"
        font-weight="bold" fill="#ffffff" text-anchor="middle">{label}</text>
</svg>
"""

def make_png(r, g, b):
    """Build a minimal 64×64 solid-colour PNG."""
    def chunk(name, data):
        c = name + data
        return struct.pack(">I", len(data)) + c + struct.pack(">I", zlib.crc32(c) & 0xFFFFFFFF)

    ihdr = chunk(b"IHDR", struct.pack(">IIBBBBB", 64, 64, 8, 2, 0, 0, 0))
    row  = b"\x00" + bytes([r, g, b] * 64)
    idat = chunk(b"IDAT", zlib.compress(row * 64, 9))
    iend = chunk(b"IEND", b"")
    return b"\x89PNG\r\n\x1a\n" + ihdr + idat + iend

def hex_to_rgb(h):
    h = h.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)

for key, (color, label) in ICONS.items():
    svg_path = HERE / f"{key}.svg"
    png_path = HERE / f"{key}.png"
    svg_path.write_text(SVG_TMPL.format(fill=color, label=label), encoding="utf-8")
    png_path.write_bytes(make_png(*hex_to_rgb(color)))

print(f"Generated {len(ICONS)*2} files ({len(ICONS)} SVG + {len(ICONS)} PNG).")
