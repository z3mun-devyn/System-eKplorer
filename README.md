<img width="256" height="256" alt="production_ekplorer_icon" src="https://github.com/user-attachments/assets/89b24e64-189d-4994-ad21-83781459b77a" />

# System eKplorer (V1.0 POC)
A unified File and Software manager, with a drive dashboard, clipboard and terminal tab, made by a Windows user. Formerly known by it's internal codename as "ekplorer," (born out of a joke)


## Vision:
Linux gets constantly recommended to Windows users looking to switch, but the problem always was I feel, that seemingly no effort was being put in making modern GUIs actually mature / respect muscle memory amassed from years-worth of Windows or MacOSX usage / anything but customizable, certainly not stable (random arbitrary crashes on Ubuntu being one.) On top of also the community's insistence of pulling a new comer into multiple directions that is generally unhelpful, I decided to make this as one step in the direction that Linux is going to.

Anyhow, I have no coding experience and this was made by Claude Code, just for disclosure. 

System eKplorer, heavily inspired by Konqueror, like mentioned before, is a customizable and unified File-Software manager that attempts to address my personal grievances when using vanilla File Managers on Linux; ergo discovery issues, clunky navigation, feature sets that make no sense, lack of cohesive metrics to immediately solve system storage, but with my own twist on it. It is also supposed to address my grievances I have on Windows, from sluggish performance, fonts disappearing when multiple drives are connected, you get the picture. I wanted to blend very-much Windows-like GUI design but honor Linux's nature with customizability. 

Unlike Konqueror that failed because it tried to do everything at once, I wanted a clearer focus on anything-software management. The source has been however opened for anyone to fork it and make it better, and potentially, this software could facilitate future spins like for GNOME (eGplorer), XFCE (eXCplorer) or whichever DE there is.

# For The Nerds  
Under the hood, it’s a Python application built on PyQt6. Supposed to support APT and Flatpack, It uses SQLite to persist settings, labels, and a tagging system for both files and packages. All heavy operations run on background threads so the interface stays responsive... hopefully; the icon system reads whichever theme the user has set (Breeze, Adwaita, or anything else, though for KDE 5.2.7 Breeze is kinda scuffed for me) and adapts automatically.

Target distros: **Kubuntu** (primary), Bazzite, Arch/SteamOS. In my case, it was made partly on Kubuntu, but also Ubuntu 5.2.7 as a backup.

## Requirements

- Python 3.11+
- PyQt6
- KDE Plasma 6 (for full theme integration)

## Quick start

```bash
python -m venv .venv
source .venv/bin/activate
pip install PyQt6
python main.py
```

## Project structure

```
ekplorer/
├── main.py              # Entry point
├── strings.py           # Centralised terminology layer (§4 of spec)
├── assets/
│   ├── icons/
│   │   └── ekplorer.png   # App icon — Adwaita folder + magnifying glass + clamp (§15)
│   └── ekplorer.desktop   # KDE app-menu integration
├── views/               # Per-tab view models and UI logic
├── backends/            # Pluggable backends (apt, flatpak, snap, zfs, …)
├── models/              # Data classes shared across views and backends
└── tests/               # pytest test suite (parsers tested first)
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
