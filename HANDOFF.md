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
- Test count: 67/67 passing as of M2

## Pending before M3 starts
- Prep commit: rename 'Files' tab to 'Dashboard', add greyed 
  'File Manager' stub tab between Dashboard and Packages

## M3 goal
Package list (apt only, read-only). See Appendix B of spec 
for the exact opening prompt.

## Setup specifics on this machine
- Kubuntu 26.04 LTS on T-Force 240GB SSD (the test drive)
- Python venv at ~/ekploiter/.venv — always activate before 
  running or testing
- drives: T-Force (Main/root), WD Black SN8100 (eui.xxx — 
  labelled WD_Black SN8100), Lexar NM970 (dm-name-bitlk-xxx 
  — BitLocker container, labelled Lexar NM970), Crucial T705 
  (Realtek RTL9210B bridge — labelled Crucial T705)
- BitLocker container shows as unmounted tile — expected, 
  fix requires Windows-side BitLocker-off procedure

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

## How to run
cd ~/ekploiter && source .venv/bin/activate && python main.py

## How to test
cd ~/ekploiter && source .venv/bin/activate && pytest -v

## How to start Claude Code
cd ~/ekploiter && source .venv/bin/activate && claude
