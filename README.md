<img width="256" height="256" alt="production_ekplorer_icon" src="https://github.com/user-attachments/assets/89b24e64-189d-4994-ad21-83781459b77a" />


# System eKplorer (V1.0 POC)
A unified File and Software manager, with a drive dashboard, clipboard and terminal tab, made by a Windows user. Formerly known by it's internal codename as "ekplorer," (born out of a joke.)

<img width="1654" height="580" alt="eKplorer Demo" src="https://github.com/user-attachments/assets/87805cf3-bf1c-41dd-8d99-23122f9a66ff" />

<img width="959" height="711" alt="Screenshot_20260613_073101" src="https://github.com/user-attachments/assets/72ad455f-344b-45aa-b8d5-60a1cda549ee" />








## Vision:
Linux gets constantly recommended to Windows users looking to switch, but the problem always was I feel, that seemingly no effort was being put in making modern GUIs actually mature / respect muscle memory amassed from years-worth of Windows or MacOSX usage / anything but customizable, certainly not stable (random arbitrary crashes on Ubuntu being one.) On top of also the community's insistence of pulling a new comer into multiple directions that is generally unhelpful, I decided to make this as one step in the direction that Linux is going to.

Anyhow, I have no coding experience and this was made by Claude Code, just for disclosure. 

**System eKplorer,** heavily inspired by **Konqueror,** like mentioned before, is a customizable and unified File-Software manager that attempts to address my personal grievances when using vanilla File Managers on Linux; **ergo discovery issues, clunky navigation, feature sets that make no sense, lack of cohesive metrics to immediately solve system storage, but with my own twist on it.** It is also supposed to address my grievances I have on Windows, **from sluggish performance, fonts disappearing when multiple drives are connected**, you get the picture. I wanted to blend very-much **Windows-like GUI design** but honor **Linux's nature with customizability.**

Unlike Konqueror that failed because it tried to do everything at once, I wanted a clearer focus on anything-software management. The source has been however opened for anyone to fork it and make it better, and potentially, this software could facilitate future spins like for GNOME (eGplorer), XFCE (eXCplorer) or whichever DE there is.

## For The Nerds:  
Under the hood it's a Python app on **PyQt6**. Package management speaks **APT,
Flatpak and Snap**; the drive dashboard is **ZFS-aware** (reads pool members, not just
mountpoints) and pulls SMART health via `smartctl`. **SQLite** persists settings plus a
tagging system that works on both files and packages. All the heavy lifting — scans,
package queries, SMART — runs on background threads so the UI stays responsive…
hopefully. The icon layer reads whatever theme you've set (Breeze, Adwaita, anything)
and adapts on the fly — though Breeze on the Qt5-era Plasma 5.27 I tested against is
kinda scuffed. To my recollection, if the app crashes, it freezes for a second and then upon
restart, it brings the user back to where they were last.

**Theming is the party trick.** There are zero hardcoded colors — the whole UI is driven
off the active Qt palette, so a "skin" is just a palette swap that every widget, native
ones included, follows for free. Skins are a **PNG + TOML** bundle (a folder with a
`skin.toml` and a `bg.png`): palette, background image, fit mode, opacity, a readability
scrim, and credits, all per-skin. Drop a folder into `~/.config/ekplorer/skins/` and it
shows up in **Configure → Appearance** — no recompile, no registration. Ships with seven
skins plus a high-contrast accessibility mode, and a commented `assets/skins/_template/`
to copy. Note: colors live in `[palette]`, NOT the image — swap a wallpaper and the tint
won't follow unless you edit both.

**Target distros:** Kubuntu (primary), Bazzite, Arch/SteamOS. Built mostly on Kubuntu,
with a Plasma 5.27 box as backup.

# Requirements:

- Python 3.11+
- PyQt6
- KDE Plasma 6 (for full theme integration)

## Manual quick start / Git Clone:

```bash
git clone https://github.com/z3mun-devyn/System-eKplorer.git
cd System-eKplorer
python -m venv .venv
source .venv/bin/activate
pip install PyQt6
python main.py
```

## Project structure:

```
ekplorer/
System-eKplorer/
├── main.py              # Entry point (captures palette baseline, autoloads active skin)
├── strings.py           # Centralised terminology layer
├── theme.py             # Palette-derived surface helpers (single color authority)
├── skin_manager.py      # Builds + applies QPalette per skin; restore for "Off"
├── skin_loader.py       # Parses skin.toml, enumerates bundled + user skins
├── assets/
│   ├── icons/
│   │   └── ekplorer.png        # App icon
│   ├── ekplorer.desktop        # KDE app-menu integration
│   └── skins/                  # Bundled skins (one folder each)
│       ├── _template/          #   commented starter — copy this to make your own
│       ├── high-contrast/      #   accessibility mode (no wallpaper)
│       ├── twmaf1/  twmaf2/  ek-imp/  ignorance/  clockwork/  backyard/
│       └── …                   #   each: skin.toml + bg.png
├── views/               # Per-tab view models and UI logic (incl. Appearance page)
├── backends/            # Pluggable backends (apt, flatpak, snap, zfs, smart, …)
├── models/              # Data classes shared across views and backends
└── tests/               # pytest suite (parsers + skin loader tested first)
```

### Installing the desktop entry (development)

```bash
# Icon
cp assets/icons/ekplorer.png ~/.local/share/icons/hicolor/512x512/apps/ekplorer.png
gtk-update-icon-cache ~/.local/share/icons/hicolor/ 2>/dev/null || true

# Desktop file (edit Exec= to point at your main.py first)
cp assets/ekplorer.desktop ~/.local/share/applications/
```


## Licence

GNU General Public License v3.0 — see [LICENSE](LICENSE).
