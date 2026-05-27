# System eKploiter — Handoff Notes

## Current state
- Spec: System_eKploiter_Specification_v02.docx (read this first)
- Git is on main, linear history, all milestones tagged

## Completed milestones
- M0: Hello World — window, tabs, icon, strings.py, GPLv3
- M1: Drive tiles — real drives via df, usage pies, responsive 
  grid, Physical Devices header, QThread loader
- M2: Drive labels + persistence — SQLite at 
  ~/.local/share/ekploiter/data.db, label modal with 5×2 color 
  swatch grid, colored pill badges, theme.py surface system 
  (ratio-based, no hardcoded hex), udisks2 D-Bus auto-refresh 
  with 15s polling fallback, 250ms debounce, unmounted device 
  tiles with lock icon + "Click to unlock," eject affordance 
  for removable drives, EFI/small partition filter
- M3: Package list — dpkg-query backend, QListView + custom 
  delegate, category sidebar, async loading with skeleton rows, 
  three-tab structure (Dashboard | File Manager [stub] | Packages)
- M4: Tag system — schema v2 migration, tag editor modal, sidebar
  Tags section, three-dot menu, pill rendering in delegate,
  AND-combine filter, tag persistence via SQLite

## Test count
- 154/154 passing as of M4

## M5 goal
Uninstall (first destructive action).
Three-dot menu "Uninstall" flow with confirmation modal.
Polkit prompt at action time. Activity log entry on uninstall.
Acceptance: user can uninstall a package; log records it.
Adding Uninstall to the three-dot menu is a one-line change in 
PackagesView._show_menu_for_entry() — the comment marks the spot.

## Setup
- Current dev machine: Ubuntu 24.04 + Plasma 5.27
  (original dev machine was Kubuntu 26.04 + Plasma 6)
- theme.py integration testing deferred to a Plasma 6 machine
- Python venv at ~/ekploiter/.venv — always activate before 
  running or testing

## How to run
cd ~/ekploiter && source .venv/bin/activate && python main.py

## How to test
cd ~/ekploiter && source .venv/bin/activate && pytest -v

## How to start Claude Code
cd ~/ekploiter && source .venv/bin/activate && claude

## Key architectural decisions (not in spec)
- dpkg-query as package data source, NOT apt list --installed
- QListView + custom delegate for package rows, NOT widget-per-row
- PyQt6 (not PySide6)
- All subprocess calls have 5-10s timeouts, per-line try/except 
  in parsers
- theme.py is the single surface authority — no hardcoded colors 
  anywhere
- strings.py is the single string authority — no hardcoded 
  user-facing text anywhere

## M4 architectural decisions
- Schema versioning: PRAGMA user_version (not schema_version table).
  M2 schema retroactively v1; detected by presence of schema_version 
  table (user_version=0 + schema_version table exists → v1 DB).
  schema_version table preserved on v1→v2 migration, not dropped.
- tags table: name TEXT PRIMARY KEY (not id INTEGER). No rename 
  support needed at this stage; name is stable identity.
- package_tags references tag_name → tags.name ON DELETE CASCADE.
  Index idx_pkg_tags(package_source, package_name) for delegate.
- TagRepository lives in backends/tags_backend.py (not models/database.py).
- Tag modal state (name field, swatch, pill toggles) persists across 
  tab switches because modal is a child widget of PackagesView — no 
  re-init on hide/show.
- Delegate does NOT hit SQLite during paint. PackagesView bulk-loads 
  all assignments on startup and on every save via load_all_assignments().
- Three-dot menu: eventFilter on list viewport; left-click within 
  dots_rect(row_rect) triggers menu. Right-click on row also works 
  (customContextMenuRequested fallback).
- Filter: AND-combines category + tag filters. Clicking the active 
  tag again clears it (toggle). Switching category preserves tag filter.
- Pill overflow: delegate shows at most MAX_PILLS=4 pills; "…+N" 
  muted indicator for remaining count.
