# System eKploiter

A unified file manager and software manager for KDE Plasma, designed for Windows users migrating to Linux.

**Status: Milestone 0 — Hello World (pre-alpha)**

## Vision

eKploiter brings together two tasks Windows users do in one place — browsing files and managing installed software — into a single, familiar application. It speaks Windows idioms where Linux terminology would create confusion, and stays read-only by default.

Target distros: **Kubuntu** (primary), Bazzite, Arch/SteamOS.

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
ekploiter/
├── main.py          # Entry point
├── strings.py       # Centralised terminology layer (§4 of spec)
├── views/           # Per-tab view models and UI logic
├── backends/        # Pluggable backends (apt, flatpak, snap, zfs, …)
├── models/          # Data classes shared across views and backends
└── tests/           # pytest test suite (parsers tested first)
```

## Milestones

| # | Name | Status |
|---|------|--------|
| 0 | Hello World | ✅ Done |
| 1 | Drive tiles (read-only) | Pending |
| 2 | Drive labels & persistence | Pending |
| 3 | Package list (apt, read-only) | Pending |
| 4 | Tag system | Pending |
| 5 | Uninstall (first destructive action) | Pending |
| 6 | Flatpak backend | Pending |

## Licence

GNU General Public License v3.0 — see [LICENSE](LICENSE).
