# System eKplorer

> The unified and customizable File and Package Manager, Terminal, Clipboard and
> Drive Monitoring software for Windows migrants to Linux. Formerly and internally known as "ekploiter."

**1.0 — Proof of Concept.** A working exhibition for an idea that neurodivergents like myself within the Linux community have neglected to do. It runs end-to-end and is largely feature-complete judging by the milestones reached. I will improve it over time as I'm still aware of minor bugs and adjustments that need to be made, but I can't promise rock-solid reliability or support. However, the source is open for anyone that downloaded System eKplorer to fork it and make it better. Maybe this kind of software is what Linux migrants like myself need rather than certain "regressions" from a modern computing standpoint.

![File Manager](docs/twmaf.png)
![Dashboard](docs/dashboard.png)

## What it is
One app: file manager + package manager + terminal + clipboard + drive dashboard.
PyQt6, Linux. Fully skinnable.

## Skins
Copy `assets/skins/_template/`, rename it, edit `skin.toml` (colors + background) and
drop in a `bg.png`. It appears in Configure → Appearance. Colors come from `[palette]`,
NOT the image — edit both.

## Requirements
- Python 3.11+, PyQt6
- `smartmontools` for drive health
  (NVMe SMART needs: `sudo setcap cap_sys_rawio,cap_sys_admin+ep "$(command -v smartctl)"`)

## Run
