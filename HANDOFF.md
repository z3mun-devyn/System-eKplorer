# System eKplorer — Handoff Notes

## Current state
- Spec: System_eKplorer_Specification_v02.docx (read this first)
- Git is on main, linear history, all milestones tagged

## Completed milestones
- Column-stretch fix: Name column is ResizeMode.Stretch (absorbs all slack,
  fills window width). Icon stays Fixed at 36px. All other columns
  (Tags/Category/Source/Version/Size/Installed On) are Interactive with
  absolute default widths (120/110/70/90/80/110 px) — user-draggable.
  setStretchLastSection(False) kept. Removed: _COL_FRACTIONS, _widths_set,
  _set_default_column_widths, showEvent width-deferral. Column VISIBILITY
  persistence (settings table) untouched. No pixel-width persistence was
  ever added; nothing removed from settings.

- M7.5: Configurable columns, install date, file-manager navigation seam —
  Schema bumped to v3: settings table (key TEXT PRIMARY KEY, value TEXT NOT NULL)
  added via v2→v3 migration; CURRENT_VERSION=3. Column visibility: right-click
  any column header → menu lists Name (checked+disabled) plus 7 toggleable cols
  (Icon, Tags, Category, Source, Version, Size, Installed On); each toggle
  hides/shows the column and writes JSON to settings["packages.column_visibility"];
  visibility restored before first paint. _VISIBILITY_KEYS and _VISIBILITY_LABELS
  are module-level dicts; _COL_NAME excluded. COL_ICON_MENU_LABEL="Icon" added
  to strings.py (icon col header is blank). Installed On column: _COL_INSTALLED=7,
  _NUM_COLS=8; display via QLocale (locale-aware short date), sort via epoch int
  (_SORT_ROLE); derived at load time in backend threads: apt→mtime of
  /var/lib/dpkg/info/{name}.list (multi-arch fallback), flatpak→mtime of
  {base}/{app_id}/current/active; unresolvable shows empty cell. Install location:
  package_location_resolver.py with resolve_location(name, source)→str|None;
  _pick_apt_dir() is pure (testable); /opt/{x} → /usr/share/{x} → /usr/bin or
  /usr/games; flatpak uses `flatpak info --show-location`. "Open install location"
  context menu action (disabled for multi-select); _LocationWorker runs on QThread
  (strong-ref pattern); toast on failure via self._status 3s auto-hide.
  Navigation seam: PackagesView.open_location_requested signal; PackagesTab exposes
  self.packages_view; MainWindow.navigate_to_directory() currently routes to
  QDesktopServices.openUrl (system file manager) — TODO: swap body to File Manager
  tab when built. SettingsRepository in backends/settings_backend.py (get/set).
  +42 tests (settings 5, install_date 12, location_resolver 13, column_visibility 12).
  Note: package-manager track is feature-complete; File Manager tab is the major
  remaining feature with its navigate_to_directory entry point pre-wired.

- Bug fixes (tag filter reset + tag deletion):
  Bug 1: Category and tag sidebar filters are now mutually exclusive.
  `_on_category_filter` always passes `_ALL_TAGS`; `_on_tag_filter` always
  passes `_ALL_CATEGORIES`. Clicking "All" in either list correctly resets
  that filter. M7 search bar query survives both resets (orthogonal state).
  Bug 2: Right-click a tag in the sidebar Tags section → "Delete tag…" →
  confirmation dialog (names the tag, count of assigned packages) → calls
  `TagRepository.delete_tag()`; FK CASCADE removes package_tags rows. If
  the deleted tag was the active filter, resets to All. Reloads in-memory
  entries and refreshes sidebar. New: `delete_tag()` + `assigned_count()`
  on TagRepository; `tag_delete_requested` signal on `_SidebarWidget`;
  `_on_delete_tag_requested` on `PackagesView`. New strings: ACTION_DELETE_TAG,
  TAG_DELETE_CONFIRM_TITLE, TAG_DELETE_CONFIRM_BODY, TAG_DELETE_YES,
  TAG_DELETE_NO. +11 tests (7 tags_backend, 1 assigned_count, 5 filter_proxy).
- M7: Package icons + search bar — Icon column (_COL_ICON=0, 36px fixed,
  QIcon via PackageIconResolver) inserted left of Name; all column indices
  shifted +1 (_COL_NAME=1…_COL_SIZE=6), _NUM_COLS=7; QLineEdit search bar
  with clear button + QToolButton field-filter dropdown (Tagged/Category/
  Source/Version/Size) pinned above the table; 120ms debounce via QTimer
  singleShot; query parsed by package_query.parse() into frozen PackageQuery
  (name, tag, category, source, version, size); proxy.set_query() ANDs with
  existing sidebar category + tag filters; search query filters on contain
  (case-insensitive); bundled category icons in assets/category-icons/
  (13 keys, SVG+PNG each); three-tier resolution in PackageIconResolver:
  Tier1=user override (~/.local/share/ekplorer/icons/), Tier2=QIcon.fromTheme
  candidate chain (name→lower→flatpak DNS tail→hyphen prefixes, deduped),
  Tier3=bundled asset keyed by CATEGORY_ICON_KEYS, floor=unknown.svg (never
  null); resolver caches per (name,source), invalidate() clears+rescans;
  theme_lookup injected at construction for test isolation; +47 tests
  (22 package_query, 25 package_icon_resolver)
- M6: Flatpak backend — backends/flatpak_backend.py parses
  `flatpak list --columns=application,name,version,size --app`;
  Package.name=app-id (DB key + commands), Package.display_name=
  friendly name (Name column display); dual async load via generic
  _BackendLoader(callable) for both APT and Flatpak; _pending_count
  counter, skeleton visible until both complete; Source column added
  (index 3, "APT"/"Flatpak"), shifting Version→4, Size→5; _NUM_COLS=6;
  _PackageActionWorker takes pkg_entries=[(name,source)], groups by
  source in run(), dispatches to apt or flatpak backend methods; mixed-
  source batch works (apt then flatpak, failures merged); 6 new flatpak
  single-pkg + 6 batch methods on PackageActionBackend (pkexec flatpak
  or pkexec bash -c); freedesktop category mappings added to strings.py;
  sidebar tag color bug fixed: _tag_icon() paints colored QPixmap circle,
  replaces plain "●" text; Flatpak not detected hint in sidebar bottom
- M0: Hello World — window, tabs, icon, strings.py, GPLv3
- M1: Drive tiles — real drives via df, usage pies, responsive 
  grid, Physical Devices header, QThread loader
- M2: Drive labels + persistence — SQLite at 
  ~/.local/share/ekplorer/data.db, label modal with 5×2 color 
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
- M4.5: Columnar layout + tag filter fix — replaced QListView+
  delegate with QAbstractTableModel + QSortFilterProxyModel +
  QTableView; five columns (Name | Tags | Category | Version |
  Size); tag filter inverted predicate bug fixed in
  filterAcceptsRow; sortable by header click, default Name asc,
  Tags col sorts by first tag name; three-dot "⋯" in Size column
  right edge; skeleton shimmer per-cell; pill overflow cap 4+…+N
- M5: Reinstall + Uninstall — four context menu actions with two
  separators (Reinstall / Reinstall Reset Settings / Uninstall /
  Uninstall Keep Settings); QMessageBox confirmation per action
  (Yes/No, default No); PackageActionBackend with reinstall,
  reinstall_reset (single pkexec bash -c "purge && install"),
  uninstall(purge|remove); async _PackageActionWorker on QThread;
  _Action enum; per-row "Working…" via _UNINSTALLING_ROLE; inline
  status bar; error dialog with stderr; auto-reload on success;
  pkexec 126/127 → silent cancellation; orphaned tags kept in DB
- M5+: Multi-select — ExtendedSelection mode (Click/Ctrl+Click/
  Shift+Click); _busy_names frozenset replaces _uninstalling_name;
  _get_selected_entries deduplicates by name; right-click or dots
  click on selection uses whole selection, else single row; menu
  labels plural-aware ("Reinstall vim" vs "Reinstall 4 apps");
  _BatchConfirmDialog with scrollable package list (max 200px);
  single pkexec batch via reinstall_batch/reinstall_reset_batch/
  uninstall_batch (shlex-quoted names, bash -c);
  STATUS_BATCH_WORKING + NOTICE_BATCH_COMPLETE strings;
  batch tag assignment: open_for_batch on TagModal, pill starts
  assigned only if ALL entries have the tag, save applies to all

## M10a: NavigationSidebar + Dashboard integration + File Manager shell
- `views/navigation_sidebar.py` (NEW): single `NavigationSidebar` widget shared by
  DashboardTab and FileManagerTab. Sections: Quick Access (XDG dirs + Recent Files +
  Recent Locations, subsections hidden when empty), Drives (system first, then others,
  unmounted in orange — click to mount via udisksctl), Network (hidden, no shares in M10a).
  Public `set_drives(mounted, unmounted)` for test injection. Threads deferred to
  `showEvent` (same pattern as TerminalView) to prevent GC-during-running-thread SIGABRT.
- `backends/recent_backend.py` (NEW): `RecentPathsBackend` with `record_location`,
  `record_file`, `list_locations(limit)`, `list_files(limit)`. Upsert semantics on path+type.
- Schema v3→v4: `recent_paths(path, type CHECK('file','location'), last_accessed)` table,
  `PRIMARY KEY(path,type)`, non-destructive migration. `CURRENT_VERSION=4`.
- `views/file_manager_view.py` (NEW): `FileManagerView` shell with sidebar + placeholder
  label. `navigate_to(path)` records location in `recent_paths` and refreshes sidebar.
- `views/dashboard_view.py`: `DriveTile` emits `navigate_requested(mount_point)` on
  left-click; `DashboardView` propagates signal upward.
- `main.py`: `DashboardTab` adds `NavigationSidebar` left of `DashboardView` (HBoxLayout,
  1px separator). `FileManagerTab` is now a real shell (not a disabled stub). 
  `navigate_to_directory` routes to FM tab (no QDesktopServices). Both sidebar and
  DashboardView drive-click signals wired to `navigate_to_directory`.
- 29 new tests in `test_m10a_navigation_sidebar.py` and `test_m10a_recent_backend.py`.

## NavigationSidebar drive label resolution (post-M10a fix)
- `set_drives` in `NavigationSidebar` now uses M2 user-assigned labels as
  the primary display name. Priority: `drive.label` (SQLite) → `drive.name`
  (hardware model from by-id) → `drive.mount_point`. Raw device names never
  appear as button text.
- System drive: `drive.label or strings.NAV_SYSTEM_DRIVE`. Tooltip shows
  device path when label is set.
- Other mounted: display = user label or hardware name or mount point; tooltip
  = `{device}  ({mount_point})` for power users.
- Unmounted: `udrive.fs_label or udrive.name or udrive.device`; tooltip = device.
- +6 tests in `test_m10a_navigation_sidebar.py` covering all label priority cases.

## M10b: Dual pane layout + Properties panel shell
- **Terminal embeddability**: `TerminalView` is a plain `QWidget`; PTY/shell
  deferred to `showEvent`. A new independent instance is created for the FM
  right pane (same pattern as Dolphin). The Terminal tab keeps its own instance.
  Terminal embedding fully available.
- `views/file_manager_view.py` rewritten with dual pane layout:
  - Toolbar at top; "Dual Pane" checkable `QPushButton` on the right.
  - Content: `NavigationSidebar` | 1px sep | `QSplitter`
    → left pane placeholder (M10c) + right pane (hidden when dual pane off).
  - Right pane: exclusive `QButtonGroup` (File Browser / Properties / Terminal)
    + `QStackedWidget` (browser placeholder at 0, `PropertiesPanel` at 1,
    `TerminalView` at 2).
  - Splitter shows equal-width panes by default when first enabled; handle
    auto-hides when dual pane is off. Splitter position does NOT persist
    (deferred polish item — spec-acknowledged).
- Settings persistence via `SettingsRepository`:
  - `fm.dual_pane.enabled` → `"0"` / `"1"` (default: off)
  - `fm.dual_pane.right_panel` → `"browser"` / `"properties"` / `"terminal"`
    (default: `"browser"`)
  - State restored from DB in `__init__` (signals blocked during restore to
    avoid spurious writes).
- `views/properties_panel.py` (NEW): `PropertiesPanel` with `QStackedWidget`:
  page 0 = placeholder ("Select a file to view properties"), page 1 =
  `QTabWidget` with five tabs: General / Permissions / Checksums / Details /
  Open With. Populated in M10c/M10d. `show_placeholder()` / `show_file()` API.
- 22 new tests in `tests/test_m10b_dual_pane.py`.
- Known deferred: splitter position persistence (polish, not in M10b scope).

## M10c: File listing + navigation
- `models/file_entry.py` (NEW): `FileEntry` dataclass (name, path, size, modified, mime_type,
  is_dir, is_hidden). `fmt_size(n)` → human-readable string. `mime_label(mime, is_dir)` →
  display string (strips "application/" prefix, returns "Folder" for dirs).
- `backends/directory_backend.py` (NEW): `DirectoryLoader(QObject)` with `ready`/`failed`
  signals. `run()` calls `iterdir()` with per-entry try/except, uses `mimetypes.guess_type`
  for MIME, sets `size=None` for dirs, filters hidden if `show_hidden=False`. Always call
  `run()` on a QThread; for tests call synchronously (QObject signals work without an event loop).
- `backends/recent_backend.py` updated: `record_location` and `record_file` now trim after
  every upsert — locations kept to 5, files kept to 10 (DELETE WHERE path NOT IN last N by
  last_accessed DESC). `_MAX_LOCATIONS=5`, `_MAX_FILES=10`.
- `views/file_view.py` (NEW): `FileView(QWidget)` — reusable per-pane component.
  - `_FileModel`: flat `QAbstractTableModel` with 4 columns (Name/Size/Modified/Type).
    Skeleton mode shows 8 `"  · · ·"` rows in gray while loading. `set_entries()` sorts
    dirs first then alpha (case-insensitive).
  - `_FileProxy`: `QSortFilterProxyModel` with `_SORT_ROLE` for type-safe sort (tuples for
    Name col for dirs-first). `filterAcceptsRow` passes all rows during skeleton mode.
  - `FileView`: two views in `QStackedWidget` — `QTreeView` (details, index 0) and
    `QListView` IconMode (icons, index 1). `_shown` flag defers `_load()` to `showEvent`
    to prevent GC-during-QThread SIGABRT. Navigation history per-instance (`_back_stack`,
    `_forward_stack`). Signals: `path_changed`, `file_opened`, `selection_changed`,
    `hover_changed`. Double-click dirs → `navigate()`; double-click files → `xdg-open` +
    `file_opened`. Hover tracked via viewport `eventFilter` → `hover_changed`.
  - Column widths: Name=Stretch, Size/Modified/Type=Interactive (80/140/120 px). 
    `hdr.setStretchLastSection(False)` — call on header, NOT on tree view.
- `views/breadcrumb_bar.py` (NEW): `BreadcrumbBar(QWidget)` — two-page `QStackedWidget`:
  page 0 = clickable `QPushButton` segments + "›" separators; page 1 = `QLineEdit` edit mode.
  Empty-area click on crumb widget → edit mode. Enter → navigate if dir exists.
  Escape → cancel. Emits `navigate_requested(str)`.
- `views/properties_panel.py` updated: `populate_general(entry: FileEntry)` fills all 7
  General tab fields and switches stack to page 1. `accessed`/`created` from `entry.path.stat()`;
  `OSError` → show "—". `size` shows "—" for directories.
- `views/file_manager_view.py` rewritten (M10c): full toolbar (←/→/↑ nav buttons,
  `BreadcrumbBar`, search `QLineEdit`, Details/Icons view-mode toggle, Hidden toggle,
  Dual-Pane toggle). Left pane = `FileView`. Right browser pane = `FileView`. Status bar
  (MIME on hover left, selection summary left, free space right).
  - Nav button connections must be wired AFTER `_left_view = FileView()` — do NOT connect
    in `_build_toolbar()` since the view doesn't exist yet at that point.
  - `navigate_to(path)` records the location FIRST (via `RecentPathsBackend().record_location`)
    before delegating to `_left_view.navigate()`. This ensures locations are recorded even
    for paths that no longer exist on disk (sidebar recent clicks for stale paths).
  - `_on_left_path_changed` also records on every navigation (internal double-clicks); the
    upsert is idempotent, so double-recording for valid paths is harmless.
  - Settings: `fm.view_mode` (`"details"`/`"icons"`), `fm.show_hidden` (`"0"`/`"1"`),
    `fm.dual_pane.enabled`, `fm.dual_pane.right_panel` (all four restored in `__init__`
    with signals blocked to avoid spurious DB writes).
  - `Ctrl+H` shortcut → `_toggle_hidden`.
  - Free space: `shutil.disk_usage(path).free` formatted with `fmt_size`.
- 36 new tests in `tests/test_m10c_file_view.py`.

## M10c Polish pass (visual + UX)

### Alternating rows
- `setAlternatingRowColors(False)` on both QTreeViews (default was True).
- `FileView.set_alternating_rows(enabled)` public method; `FileManagerView._restore_state`
  reads `fm.alternating_rows` setting (default "0" = off). No UI yet — key pre-wired for
  Configure eKplorer option.

### Toolbar visual separation
- Toolbar widget has NO custom background — it inherits app chrome color naturally.
  `theme.toolbar_surface()` remains in `theme.py` but is no longer applied to the toolbar.
- Breadcrumb bar and search QLineEdit share matching inset styling:
  `background: palette(base); border: 1px solid palette(mid); border-radius: 4px`.
  Applied via object-name CSS selector `QWidget#breadcrumbBar` (prevents cascading to
  child buttons inside BreadcrumbBar) and direct `QLineEdit` stylesheet on `_search_bar`.

### Nav buttons
- All three (←→↑) enlarged to 40×32 for easy clicking.

### View mode slider
- Replaced Details/Icons toggle buttons + Hidden button with a 4-stop `QSlider`:
  stop 0 = `"details"`, 1 = `"icons_small"`, 2 = `"icons_medium"`, 3 = `"icons_large"`.
- Compound widget: `QSlider` (range 0–3, integer snapping) + row of 4 equal-width icon
  labels below the track (≡ ⊞ ⊡ ◻). `strings.FM_VIEWSLIDER_ICONS` tuple.
- Dual Pane toggle kept as separate button, visually distinct from slider group.
- `Ctrl+H` shortcut remains; `fm.show_hidden` still persists. Hidden button removed from toolbar.
- `FileView.set_view_mode()` handles all 4 modes; icon sizes: small=24px/60×60 grid,
  medium=48px/90×80, large=96px/130×120.
- `FileView.zoom_requested = pyqtSignal(int)`: emitted on Ctrl+Scroll on either viewport
  (+1 = zoom in, -1 = zoom out). `FileManagerView._on_zoom_requested` steps slider ±1.
- `fm.view_mode` now stores "details"/"icons_small"/"icons_medium"/"icons_large".

### Free space status bar
- Format updated to `"{name}: {free} free of {total}"` where `{name}` = drive label
  (SQLite M2 user label) or mount point as fallback.
- `FileManagerView._mounted_drives` caches drives from `sidebar.drives_updated` signal
  (new signal added to `NavigationSidebar`, emitted from `set_drives()`).
- `_update_free_space(path)` finds best-match drive via longest-prefix mount point match.
  Falls back to `shutil.disk_usage` without label if drives not yet loaded.

### Address bar (post-M10c redesign — `views/address_bar.py`)
- **Default mode: path edit.** `AddressBar` replaces `BreadcrumbBar` in the FM toolbar
  and in the right pane nav bar.
- Permanently dark: `QWidget#addressBar { background: palette(base); border: 1px solid
  palette(mid); border-radius: 4px; }` — looks like an input field at all times.
- **Path mode (default)**: `QLineEdit` always visible, text = canonical POSIX path
  (`/home/user/dir`). Click / focus → select-all for instant clipboard copy.
- **Ctrl+L** shortcut on `FileManagerView` → `_address_bar.focus_edit()` — switches to
  path mode if in breadcrumb mode, focuses, selects-all.
- **Enter** navigates if path is a valid directory; invalid path silently reverts.
- **Escape** reverts text to current directory path — never blank, never breadcrumbs.
- **Breadcrumb mode (opt-in)**: toggle via small "/" button at left of bar; switches
  inner stack to the existing `BreadcrumbBar` widget. Mode persisted in SQLite key
  `fm.address_bar.mode` (default `"path"`).
- Both left (toolbar) and right (dual-pane nav bar) panes each have their own
  `AddressBar`. Right pane address bar replaces the old `_right_path_label` QLabel.
- `navigate_requested` signal — same interface as `BreadcrumbBar`; wired to
  `_left_view.navigate` / `_right_view.navigate` in `FileManagerView`.
- New strings: `FM_SETTING_ADDRESS_BAR_MODE`, `FM_ADDRESS_TOGGLE_ICON`,
  `FM_ADDRESS_TOGGLE_TOOLTIP`.

### File/folder icons
- **Primary**: `QFileIconProvider().icon(QFileInfo(path))` — delegates to the system's
  native icon provider (KIO on KDE). Returns colored system icons, not monochrome symbolics.
- Module-level singleton `_FILE_ICON_PROVIDER` created lazily on first call.
- **Fallback** (only if QFileIconProvider returns null): `QIcon.fromTheme` chain —
  exact MIME theme name (`image-png`, `text-plain`), category fallbacks
  (`image-x-generic`, etc.), then `"unknown"`, then `"application-x-generic"`.
- Applied to both Details and Icons view modes (single `_entry_icon()` function).

### Column order + names
- Old: 4 cols — Name(icon+text) | Size | Modified | Type
- New: 6 cols — Icon(36px,blank header) | Name(stretch) | Tags(80px,empty shell) |
  Category(120px) | Date Modified(140px) | Size(80px,right-aligned)
- Tags column: present but empty until M10e.
- Category: MIME description (was "Type"). `strings.FM_COL_CATEGORY`.
- Date Modified: (was "Modified"). `strings.FM_COL_DATE_MODIFIED`.
- Size: right-aligned. Folders show "N items" / "1 item" (item count from
  `FileEntry.item_count`; counted in `DirectoryLoader.run()` via `iterdir()` count with
  PermissionError guard). `strings.FM_SIZE_ITEMS_ONE`, `FM_SIZE_ITEMS_MANY`.
- `_ENTRY_ROLE` stays on column 0 (icon col) — all `siblingAtColumn(0)` calls unchanged.
- Filter key column updated to 1 (Name).

### Sidebar tree navigation (Quick Access + Drives)
- XDG flat `_NavEntry` buttons replaced with `_quick_tree: QTreeWidget`.
- **Drives section** flat `_NavEntry` buttons replaced with `_drives_tree: QTreeWidget`
  (same style as `_quick_tree`). Mounted drives get a lazy-load placeholder child
  (expand arrow + subdir expansion, same `_on_tree_item_expanded` handler). Unmounted
  drives: plain `QTreeWidgetItem` with orange foreground + `_UNMOUNTED_ROLE` data; no
  expand arrow. Click handler `_on_drives_tree_item_clicked` dispatches to mount or
  navigate based on `_UNMOUNTED_ROLE`.
- **Push-down expansion** (no internal scroll): both trees have
  `setVerticalScrollBarPolicy(ScrollBarAlwaysOff)` +
  `setSizeAdjustPolicy(AdjustToContents)` so tree grows to content. `itemExpanded`/
  `itemCollapsed` connected to `updateGeometry()` lambdas to push content below
  downward. Outer `QScrollArea` handles overall sidebar scrolling.
- Each XDG/drive entry = top-level item with a placeholder child (forces expand arrow).
- `itemExpanded` → lazy-load non-hidden immediate subdirs; `_on_tree_item_expanded`
  guards for `None` path_str before constructing `Path`.
- Subsection headers (Recent Files, Recent Locations) now use bold/non-italic to
  match section header styling.
- `drives_updated = pyqtSignal(list, list)` added to `NavigationSidebar`.

### Right pane navigation bar
- Compact 30px-tall nav bar added above right `FileView` (inside the browser wrapper
  widget at `_right_stack` index 0, so it's automatically hidden when Properties or
  Terminal is active).
- Contains ←→↑ buttons (28×24) + path label (`QLabel`, palette(mid), 11px).
- `_on_right_path_changed`: updates path label to last path segment, enables/disables buttons.
- Right pane ← → ↑ buttons wired to `self._right_view.navigate_back/forward/up`.

### Deferred: Sorting table / file staging area
- The "hotbar" concept (temporarily collecting files before moving them) is a good UX idea.
  **Deferred to a future milestone.** Note here so it's not forgotten.

### Ctrl+H
- Hidden files toggle keyboard shortcut retained (`QShortcut` on `FileManagerView`).
- `_toggle_hidden()` reads `fm.show_hidden` setting directly (no longer references a button).

## M10d: File operations

### Backend (`backends/file_ops_backend.py`)
- **`FmClipboard(operation, paths)`** — FM clipboard dataclass; `operation` is `"copy"` or `"cut"`;
  `is_empty()` guard. Lives in FM-wide state on `FileManagerView._clipboard`.
- **`ConflictStrategy`** — SKIP / REPLACE / RENAME constants.
- **`FileOpResult(ok, message, errors)`** — uniform return from every operation.
- **`FileOpsBackend`** — pure synchronous class, safe on QThread:
  - `copy_files(srcs, dst, conflict, line_cb)` — `shutil.copy2` (files) / `shutil.copytree` (dirs)
  - `move_files(srcs, dst, conflict, line_cb)` — `shutil.move`
  - `delete_to_trash(paths, line_cb)` — `send2trash.send2trash`; graceful fallback to
    `delete_permanently` + log line if `send2trash` is not importable
  - `delete_permanently(paths, line_cb)` — `shutil.rmtree` / `Path.unlink`
  - `rename_path(src, new_name)` — `Path.rename`; returns `ok=False` for empty/same/collision
  - `create_folder(parent, name)` — `Path.mkdir`; returns `ok=False` on duplicate
  - `create_file(parent, name)` — `Path.touch`; returns `ok=False` on duplicate
  - `find_conflicts(srcs, dst_dir)` — pre-flight scan; returns list of colliding names
  - `get_stat_info(path)` — `stat()` dict: mode/octal/owner/group/inode/links/block_size/blocks
  - `set_chmod(path, octal_mode)` — `pkexec chmod` via `subprocess.run`
  - `compute_checksums(path)` — MD5/SHA-1/SHA-256 via `hashlib`, 64 KB chunks
  - `get_open_with_apps(mime)` — `xdg-mime query` + `gio mime` output
  - `set_default_app(mime, desktop)` — `xdg-mime default`
  - `find_admin_file_manager()` — `shutil.which` chain: dolphin → nautilus → nemo → thunar
  - `open_as_admin(path)` — `pkexec <found_fm> <path>` via `subprocess.Popen`
- **Workers** (QObject, move to QThread): `_FileOpsWorker` (copy/move/trash/delete),
  `_ChecksumWorker`, `_ChmodWorker`, `_OpenWithLoader`. All guarded by `try: from PyQt6`
  so the module is importable for pure unit tests without Qt.

### Context menu (`views/file_view.py`)
- `action_requested = pyqtSignal(str, list)` signal on `FileView`.
- `set_paste_enabled(bool)` — called by `FileManagerView` after cut/copy; enables Paste item.
- Context menu on both `_tree` and `_list` viewports via `CustomContextMenu` policy.
- Single-item menu: Open / Open With / Open as Administrator / — / Cut / Copy / Copy Path /
  Copy Name / Paste / — / Rename / Move to Trash / Delete Permanently / — / New Folder /
  New File / — / Assign Tags / Properties.
- Multi-select: Open/Open With/Rename/Open as Admin/Properties removed.
- Empty-area click: shows Paste / New Folder / New File only.
- `_get_selected_entries()` helper deduplicates by `id(entry)`; now also used by
  `_on_selection_changed` (no duplicate logic).

### Inline rename (`views/file_view.py`)
- `_NameEditDelegate(QStyledItemDelegate)` installed on `_COL_NAME` column of `_tree`.
  - `setEditorData` → fills `QLineEdit` from `_ENTRY_ROLE`.
  - `setModelData` → emits `action_requested("rename", [path_str, new_name])` instead of
    writing to model. Actual rename + refresh happens in `FileManagerView`.
- `_FileModel.flags()` override returns `ItemIsEditable` for `_COL_NAME` when not loading.
- Edit triggers: `SelectedClicked | EditKeyPressed` (F2 or slow-double-click).

### FileManagerView (`views/file_manager_view.py`)
- `_FmActionPanel` inner class (160px, hidden until op starts) — same pattern as M8
  `_ActionPanel`: `start_action(desc)`, `append_line(str)`, `mark_complete(str)`,
  `mark_failed(str)`, `dismissed` signal. Log toggle, Dismiss button enabled on completion.
- `_clipboard: FmClipboard | None` — set on cut/copy; consumed (cleared) on cut-paste.
- `_on_action_requested(action, entries)` dispatcher handles all 15 context menu actions.
- `_do_paste()` — pre-flight conflict scan → `_ask_conflict_strategy` dialog (Skip/Replace/Rename)
  → `_start_file_op`. Cut-paste clears clipboard and disables Paste after.
- `_confirm_and_delete(paths)` — `QMessageBox` warning with destructive-role Yes + default Cancel.
- `_start_file_op(op, srcs, dst_dir, conflict, desc)` — spins up `QThread` +
  `_FileOpsWorker`; streams `output_line` to action panel; on done calls `_refresh_left()`.
- `_refresh_left()` — calls `_left_view._load()` if shown, so listing updates after ops.
- Keyboard shortcuts on `FileManagerView`: Ctrl+X (cut), Ctrl+C (copy), Ctrl+V (paste),
  Delete (trash), Shift+Delete (permanent delete), Ctrl+Shift+N (new folder), F2 (rename inline).

### Properties panel (`views/properties_panel.py`)
- **Permissions tab**: owner/group/mode/octal from `get_stat_info()`; "Change permissions…"
  button opens `QInputDialog` for octal string, spawns `_ChmodWorker` on QThread. Refreshes
  mode labels on success.
- **Checksums tab**: MD5/SHA-1/SHA-256 rows start "—"; "Compute" button (disabled for dirs)
  spawns `_ChecksumWorker` on QThread; fills rows on completion; button re-enabled.
- **Details tab**: inode/hard-links/block-size/blocks from `get_stat_info()`.
- **Open With tab**: default app label + QListWidget for alternatives; populated via
  `_OpenWithLoader` worker on `populate_general()`; "Set as default" button writes via
  `xdg-mime default`. All thread refs stored as attrs to prevent GC SIGABRT.

### Open as Administrator
- Detection chain: dolphin → nautilus → nemo → thunar via `shutil.which`.
- If found: `subprocess.Popen(["pkexec", fm, path])`.
- If none found: `QMessageBox.warning` with explanatory message.

### Deps
- `send2trash` added to venv (`pip install send2trash`). No requirements.txt in repo.

### Test count
- 557/557 passing at M10d completion (+38 new in `tests/test_m10d_file_ops.py`)

## FM icon resolver fix (post-M10d)

### Problem
On KDE with Qt6, `QIcon.themeName()` was empty and `QIcon.themeSearchPaths()` contained
only `[':/icons']` when running outside the Plasma session integration. This caused
`QIcon.fromTheme()` to return null icons everywhere in the File Manager view, falling
back to monochrome system-style generics instead of the Breeze colored icons Dolphin shows.

### Fix: startup bootstrap (`main.py`)
`_bootstrap_icon_theme()` runs right after `QApplication(sys.argv)`:
- If `/usr/share/icons` is not in `themeSearchPaths()`, adds it.
- If `themeName()` is empty or `"hicolor"`, sets it to `"breeze"`.
Requires `breeze-icon-theme` and `plasma-integration` as runtime deps (already installed).

### Fix: three-tier `_entry_icon()` resolver (`views/file_view.py`)
Replaced the old `QFileIconProvider`-primary resolver with a proper MIME-aware chain:
1. **Tier 1 (directories)**: `QIcon.fromTheme("inode-directory")` → `"folder"` fallback.
2. **Tier 2 (files)**: `QMimeDatabase.mimeTypeForFile()` (magic + extension) →
   `mime.iconName()` → walk `mime.parentMimeTypes()` chain → `mime.genericIconName()`.
   Covers the full Breeze icon hierarchy (e.g. `.docx` → `"x-office-document"`).
3. **Tier 3**: `QFileIconProvider.icon(QFileInfo)` — Qt's native fallback.
4. **Floor**: `"unknown"` / `"application-x-generic"` — never returns null.

Cache keyed by `(mime_name, is_dir)`. Cache is invalidated on theme-name change
(handles live KDE theme switches). `_MIME_DB` singleton created lazily at first file
icon lookup.

### Tests (+5 in `tests/test_m10c_file_view.py`)
- `test_icon_resolver_folder_non_null` — tier 1 path returns non-null
- `test_icon_resolver_docx_non_null` — tier 2 genericIconName path returns non-null
- `test_icon_resolver_unknown_extension_non_null` — tier 3 provider floor returns non-null
- `test_icon_resolver_cache_reuse` — same MIME type → same `QIcon` object
- `test_icon_resolver_cache_invalidated_on_theme_change` — theme change clears cache

All use `QApplication.style().standardIcon()` (not QPixmap) for a non-null stub icon
since the offscreen Qt platform used in tests does not support QPixmap creation reliably.

### Test count
- 562/562 at icon-resolver completion; **574/574 after AddressBar** (+12 new in `tests/test_m10c_file_view.py`)

## FIX PASS (address bar surface + icon theme + sidebar resize)

### Part 1 — Address bar dark surface (`views/address_bar.py`)
**Problem**: outer `QWidget#addressBar { background: palette(base) }` was painted over by
`QStackedWidget`'s own background, so the inner `_path_edit` with `background: transparent`
showed `palette(window)` (light) instead of `palette(base)` (dark).

**Fix**: removed the outer container QSS entirely; applied the search-bar-identical QSS
directly to `_path_edit`:
```python
self._path_edit.setStyleSheet(
    "QLineEdit { background: palette(base); border: 1px solid palette(mid);"
    " border-radius: 4px; padding: 2px 4px; }"
)
```
The `_crumb_bar` (breadcrumb mode, opt-in) is now wrapped in a `QWidget` with the same dark
QSS + `setAutoFillBackground(True)` so breadcrumb mode also looks right.
Height changed from 32 → 28 in `FileManagerView._build_toolbar()` to match the search bar.

### Part 2 — Icon theme auto-follow (`main.py`)
**Problem**: `_bootstrap_icon_theme()` hardcoded `"breeze"` regardless of system theme.
Actual system theme is `"breeze-dark"` (detected via GTK3 `~/.config/gtk-3.0/settings.ini`).

**Fix**: added `_detect_icon_theme()` reading in priority order:
1. `~/.config/kdeglobals` `[Icons]` `Theme=`
2. `~/.config/gtk-3.0/settings.ini` `gtk-icon-theme-name=`
3. `gsettings get org.gnome.desktop.interface icon-theme` (2s timeout)
4. `"breeze"` fallback

`_bootstrap_icon_theme()` now: adds both `/usr/share/icons` and
`~/.local/share/icons` to `themeSearchPaths`, then calls `_detect_icon_theme()`.

`--icon-debug` flag prints `themeName`, `fallbackThemeName`, `themeSearchPaths`, detected
theme, and `isNull` for four common icon names.

Note: plasma-integration or qt6ct is required for Qt to inherit the system theme
automatically at startup (without the explicit bootstrap). Our bootstrap is the reliable path
for running outside a full Plasma session.

### Part 3 — Resizable sidebar (`views/navigation_sidebar.py`, `views/file_manager_view.py`)
**Problem**: `NavigationSidebar` had `setFixedWidth(220)`, preventing resize.

**Fix**:
- `NavigationSidebar.__init__` now takes `fixed_width: int | None = 220` parameter.
  - Dashboard tab uses the default `fixed_width=220` (unchanged behavior).
  - FM uses `fixed_width=None` → `setMinimumWidth(140)`.
- `FileManagerView` content area now uses an outer `QSplitter(Horizontal)`:
  - Index 0 = `NavigationSidebar(fixed_width=None)`, `setStretchFactor(0, 0)`
  - Index 1 = existing `_splitter` (left+right panes), `setStretchFactor(1, 1)`
  - Handle width = 2px for a subtle but functional drag handle
  - Removed the old 1px `sep_v` separator widget (splitter handle replaces it)
- Persistence: `_on_sidebar_resized(pos, index)` → writes `fm.sidebar.width` to SQLite.
  `_restore_state()` reads it back and calls `self._outer_splitter.setSizes([w, 1])`.

### Tests (576/576)
- `test_address_bar_path_edit_qss_matches_search_bar` — `_path_edit.styleSheet()` contains
  `palette(base)`, `border`, and `border-radius`
- `test_fm_sidebar_width_persists` — calling `_on_sidebar_resized` writes a digit string to
  `fm.sidebar.width` in settings

## CRITICAL FIX PASS: drag-and-drop + self-adaptive icons

### Part 1 — Drag and drop (`views/file_view.py`, `views/file_manager_view.py`)

**`_FileModel`** (source model):
- `drop_requested = pyqtSignal(list, str, bool)` — emitted by `dropMimeData`; propagated
  by `FileView.drop_requested` to `FileManagerView._on_drop_requested`.
- `_current_dir: str` — set to `str(Path.home())` initially; synced on every `FileView.navigate()`.
- `mimeTypes()` → `["text/uri-list"]`
- `mimeData(indexes)` — deduped by path (only processes `_COL_ICON` column per row),
  returns `QMimeData` with `file://` URLs.
- `supportedDragActions()` / `supportedDropActions()` → `CopyAction | MoveAction`
- `canDropMimeData()` — accepts URLs; if dropping ON a specific item, requires it to be
  a directory; empty space / between rows always accepted.
- `dropMimeData()` — extracts `toLocalFile()` paths, determines target dir (item's path
  or `_current_dir`), checks `QApplication.keyboardModifiers()` for Ctrl→copy override,
  emits `drop_requested`.
- `flags()` — adds `ItemIsDragEnabled | ItemIsDropEnabled` for valid non-loading indexes;
  invalid index (empty space) → `ItemIsDropEnabled` only.

**`FileView`**:
- Both `_tree` (QTreeView) and `_list` (QListView):
  `setDragEnabled(True)`, `setAcceptDrops(True)`, `setDropIndicatorShown(True)`,
  `setDragDropMode(DragDrop)`, `setDefaultDropAction(MoveAction)`.
- `drop_requested = pyqtSignal(list, str, bool)` — wired to `_model.drop_requested`.
- `navigate()` now also sets `self._model._current_dir = str(path)`.
- `eventFilter`: on `DragMove` with URLs, if Ctrl held → `event.setDropAction(CopyAction)`;
  returns `False` so Qt's own `dragMoveEvent` also runs (drop indicator preserved).

**`FileManagerView`**:
- `_left_view.drop_requested` and `_right_view.drop_requested` both connected to
  `_on_drop_requested(source_paths, target_dir, copy)`.
- `_on_drop_requested`: filters existing sources, checks target is a dir, runs conflict
  check, calls `_start_file_op("copy" or "move", ...)`.
- `_refresh_right()` added; `_on_ops_succeeded` and `_on_ops_failed` now call both
  `_refresh_left()` and `_refresh_right()` so both panes update after any operation.

**Drop semantics**:
- Plain drag = Move (`setDefaultDropAction(MoveAction)`).
- Ctrl held at any point during drag = Copy (detected in `eventFilter` for cursor
  feedback; confirmed in `dropMimeData` via `QApplication.keyboardModifiers()`).
- External DnD OUT (to Dolphin/desktop): automatic via `text/uri-list` MIME.
- External DnD IN (from Dolphin/desktop): same handler; action follows what Dolphin
  proposes (Ctrl override still works).

### Part 2 — Self-adaptive icon resolver (`views/file_view.py`, `main.py`)

**`main.py`**:
- Removed `_detect_icon_theme()`, `_bootstrap_icon_theme()`, `_print_icon_debug()`,
  and all related imports (`configparser`, `subprocess`, `Qt`).
- Added `os.environ.setdefault("QT_QPA_PLATFORMTHEME", "kde")` in `main()` BEFORE
  `QApplication(sys.argv)`. On Plasma 6 this loads the KDE platform plugin; on Bob's
  Plasma 5.27 it silently falls back.

**`views/file_view.py`** — `_THEME_VIABLE` probe:
- `_THEME_VIABLE: bool | None = None` (module level, `None` = not yet tested).
- `_check_theme_icons_viable()` — lazy, called at first `_entry_icon()` invocation:
  requests `QIcon.fromTheme("folder")`, renders to a 16×16 pixmap, converts to image,
  scans for any non-transparent pixel with luminance > 40. Returns `True` if found.
- Result cached in `_THEME_VIABLE`; one line printed to stderr:
  `eKplorer: icon theme viable = True/False (theme: ...)`

**`_entry_icon()` — two paths**:
- `_THEME_VIABLE = False` (Bob's system): uses only `QFileIconProvider.icon(QFileInfo(path))`.
  Always renders a visible icon (some colored, some generic monochrome). Falls back to
  `_icon_theme_fallback("unknown", "application-x-generic")` if the provider returns null.
- `_THEME_VIABLE = True` (Plasma 6): full 3-tier fromTheme chain (unchanged logic).

Cache invalidation on theme name change and MIME-keyed cache apply to both paths.

### Tests (580/580)
Existing 5 icon resolver tests updated: all now use `_reset_icon_state(fv_mod, monkeypatch,
viable=False)` helper to force the non-viable path (consistent with offscreen Qt platform).
4 new tests:
- `test_dnd_mime_types` — `_FileModel().mimeTypes() == ["text/uri-list"]`
- `test_dnd_mime_data_has_file_urls` — `mimeData(indexes)` URLs match selected entry paths
- `test_icon_viable_check_returns_bool` — `_check_theme_icons_viable()` returns `bool`
- `test_icon_provider_fallback_non_null` — non-viable path returns non-null icon

## M10c bug fix: icon-mode label display
- **Problem**: Icons view (all three sizes) showed icons with no filename label because
  `QListView` uses `modelColumn() = 0` (the Icon column), and column 0 returned
  `None` for `DisplayRole`.
- **Fix**: `_FileModel.set_icon_mode(enabled: bool)` flag. When enabled, column 0
  returns `entry.name` for `DisplayRole` in addition to the QIcon for `DecorationRole`.
  When disabled (details), column 0 returns `None` for DisplayRole — name stays only
  in column 1, no duplication.
- `FileView.set_view_mode()` calls `self._model.set_icon_mode(mode != "details")` so
  the flag tracks the active view. `dataChanged` emitted on col 0 for all rows to
  repaint without resetting selection.
- `QListView` remains at `modelColumn() = 0` (default). No changes to column indices,
  proxy, or `QTreeView` behavior.
- +2 tests: `test_file_model_col0_display_role_icon_mode`,
  `test_set_view_mode_toggles_icon_mode_flag`.

## Terminal arrow key fix (post-M9, fourth pass)
Root cause of "left arrow triggers delete / arrow keys misbehave":

DECCKM (application cursor mode, ANSI private mode 1). bash/readline sends
`\x1b[?1h` during startup to enable application cursor mode, after which it
expects arrow keys as SS3 sequences (`\x1bOA/OB/OC/OD`) rather than CSI
sequences (`\x1b[A/B/C/D`). We always sent the CSI form, which readline in
application cursor mode did not recognise as arrow keys, causing it to
interpret them as literal escape-bracket sequences and triggering unexpected
actions (readline may forward the raw chars to the shell as text or commands).

Fix:
- `_app_cursor: bool` flag added to `__init__` (default False = normal mode).
- `_render` detects `\x1b[?1h` (DECCKM set) → `_app_cursor = True` and
  `\x1b[?1l` (DECCKM reset) → `_app_cursor = False`.
- `keyPressEvent` sends `\x1bOA/OB/OC/OD` when `_app_cursor` is True, and
  `\x1b[A/B/C/D` otherwise. All four arrow keys corrected.
- Backspace and space confirmed unaffected (regression tests added).

+9 tests in test_m9_terminal.py (CSI mode, SS3 mode, DECCKM toggle, regressions).

## Known issue: terminal cursor blink (cosmetic, deferred)
QTextEdit's cursor blink is controlled by `QApplication.cursorFlashTime()` (system
default, typically 1000 ms). The cursor is visible and positioned correctly — blink
cadence is system-controlled and cannot be overridden per-widget in this Qt build
without subclassing QTextEdit and overriding the paint event. Cosmetic only; terminal
is fully functional. Revisit if a custom cursor-blink approach becomes worth the
complexity, or if a full VT100 widget with Python/Qt6 bindings becomes available.

## Terminal colour rendering + cursor visibility fix (post-M9, third pass)
Root cause of "ls shows no colours" and "cursor hard to see":

1. ANSI sequences were stripped before rendering — the pipeline called `_strip_ansi`
   before `_render`, so all SGR colour codes were discarded. Fix: removed the
   `_strip_ansi` call from `_on_data_ready`. `_render` now processes escape sequences
   inline using `_esc_end` to consume non-SGR sequences and `_apply_sgr` to apply
   SGR colour/weight changes to `_char_fmt`.

2. QTextEdit had a light background — colours like dark-blue directory names were
   invisible against the default light background. Fix: QPalette applied to `_display`
   sets background to `_TERM_BG` (#1e1e1e, near-black) and default text to `_TERM_FG`
   (#d4d4d4, near-white). The block cursor (white on black) is now clearly visible.

3. Colour support implemented: SGR 0 (reset), SGR 1/2/22 (bold/dim/normal weight),
   SGR 30-37/90-97 (standard 16-colour fg), SGR 40-47/100-107 (standard 16-colour bg),
   SGR 39/49 (default fg/bg), SGR 38;5;N / 48;5;N (256-colour), SGR 38;2;R;G;B /
   48;2;R;G;B (24-bit truecolor). Palette uses standard Linux console / xterm colours.

4. Note: `_ANSI_RE` and `_strip_ansi` are kept (exported, tested in test_m9_terminal.py)
   but are no longer called in the live rendering path. They remain available for
   any utility that wants stripped plain-text output.

5. Colour constants live in terminal_view.py (not theme.py) — they are terminal
   emulation specification values, not UI theme colours.

## Terminal space key + cursor bug fix (post-M9, second pass)
Root causes of "space bar consumed by parent" and "cursor invisible":

1. Space consumed by QTextEdit scroll-on-space — `QTextEdit` in read-only mode
   intercepts Space keypress to scroll the view, before `TerminalView.keyPressEvent`
   ever sees it. Fix: `installEventFilter(self)` on both `_display` and
   `_display.viewport()`. `eventFilter()` intercepts `QEvent.Type.KeyPress` from
   either object, calls `self.keyPressEvent(event)`, and returns `True` (consuming
   the event so QTextEdit never processes it).

2. Cursor invisible because TerminalView held Qt focus — the text cursor in
   `_display` is only visible when `_display` itself has Qt focus. Since
   `TerminalView` (the container) held focus, `_display`'s cursor was hidden.
   Fix: `self.setFocusProxy(self._display)` — any focus directed at TerminalView
   (programmatic, tab-key navigation) is automatically routed to `_display`.
   `self.setFocusPolicy(TabFocus)` keeps TerminalView reachable via Tab.
   `_display.setFocus()` in `showEvent` gives focus immediately when the tab is shown.

3. PyQt6 focus policy propagation — calling `self.setFocusPolicy(TabFocus)` on
   TerminalView after `setFocusProxy(_display)` causes Qt to propagate TabFocus
   to the proxy widget, overwriting the StrongFocus we set on `_display`.
   Fix: re-set `_display.setFocusPolicy(StrongFocus)` AFTER `self.setFocusPolicy(TabFocus)`.

4. Block cursor — `_display.setCursorWidth(char_w)` in `showEvent` makes the
   I-beam as wide as one monospace character. Qt's standard cursor-blink timer
   handles the blink automatically.

+5 regression tests in test_m9_terminal.py (event filter, focus policy, focus proxy).

## Terminal keyboard bug fix (post-M9)
Root causes of "space produces replacement boxes" and "backspace produces garbage":

1. ANSI regex too narrow — missed private 0x30-0x3F final-byte sequences:
   - `\x1b=` (0x3D, alternate keypad mode) — sent by bash/readline on startup
   - `\x1b>` (0x3E, normal keypad mode)
   - `\x1b(B` (charset select, '(' is intermediate at 0x28, 'B' is final)
   These left orphaned `\x1b` bytes in the output, which Qt rendered as U+FFFD
   replacement boxes. Fix: added `[ -/]*[0-?]` alternative to cover all private
   sequences, and `[ -/]*[@-~]` already covers Fe/Fs sequences with intermediates.

2. Bare CR not handled — readline uses `\r` + reprint to redraw the current line
   in-place after backspace/cursor movement. We previously deleted standalone `\r`
   entirely (`.replace("\r", "")`), leaving a stray space from the re-print.
   Fix: bare `\r` now clears the current display line (select StartOfLine→EndOfLine,
   removeSelectedText) then reprints from the PTY buffer. This makes backspace look
   correct at a readline prompt.

3. `\x08` (BS) not handled in output — canonical-mode erase echo sends
   `\x08 \x20 \x08`. The BS chars were passed to insertPlainText as garbage.
   Fix: `\x08` now calls `cursor.deletePreviousChar()`.

4. Buffered UTF-8 decode — partial multi-byte sequences split across reads now
   accumulate in `_read_buf` instead of producing U+FFFD from `errors="replace"`.

5. Slave termios configured before Popen — `_configure_slave_termios(slave_fd)`
   sets VERASE=0x7F so readline's initial tcgetattr sees the correct erase char.

6. Font: explicit `QFont("Monospace")` with `StyleHint.Monospace` fallback to
   `QFontDatabase.systemFont(FixedFont)`.

7. Added `COLORTERM=truecolor` to shell environment for 24-bit colour prompts.

+15 regression tests in test_m9_terminal.py (ANSI regex coverage + _render logic).

## M9 architectural decisions
- QTermWidget has no Python/Qt6 bindings on Ubuntu 24.04 (only libqtermwidget5-1
  for Qt5 C++; no pip package). Terminal tab implemented via Python stdlib `pty`
  module + `QSocketNotifier` for async reads + `QTextEdit` with ANSI stripping.
  Full-screen TUI apps (vim, htop) won't render; common commands (ls, git, etc.) work.
- TerminalView defers PTY creation to showEvent (not __init__) — avoids crash in
  tests and avoids spawning a shell before the tab is ever viewed.
- ANSI regex handles CSI (ESC [... final), OSC (ESC ]...BEL|ST), and 2-byte
  sequences. OSC alternative must precede single-char alternative ('\\-_' range
  includes ']' at 0x5D, so ordering matters).
- navigate_to_directory in MainWindow routes to terminal.navigate_to(path) when
  terminal tab is current index; otherwise falls back to QDesktopServices. The
  terminal.navigate_to() sends "cd <shlex.quoted path>\n" to master PTY fd.
- VersionHistoryDialog: async _HistoryLoader worker loads apt-cache policy or
  flatpak remote-info --log on a QThread. Install button enabled only for
  obtainable+non-current versions. "Prevent automatic updates" checkbox applies
  apt-mark hold / flatpak mask synchronously on the GUI thread (quick, pkexec
  prompt appears immediately when toggled).
- _VersionInstallWorker mirrors _PackageActionWorker: runs install_apt_version
  or install_flatpak_commit, emits succeeded/failed/cancelled, streams output_line.
  PackagesView._start_version_install reuses _action_panel (same bottom dock).
- VersionBackend._parse_apt_policy: parses "Version table:" block; a version is
  obtainable if any source line doesn't contain "/var/lib/dpkg/status" (i.e., it's
  from a real repo). dpkg-status-only entries are historical-only (greyed out).
- New methods on PackageActionBackend: install_apt_version(pkg, ver, line_cb),
  install_flatpak_commit(app_id, commit, line_cb).
- New strings: ACTION_VERSION_HISTORY, VERSION_HISTORY_* family, TAB_TERMINAL.
- New files: backends/version_backend.py, views/version_history_dialog.py,
  views/terminal_view.py. Tests: test_version_backend.py (24), test_m9_terminal.py (29).

## M8 bug fix: "Check for updates" button did nothing
Two root causes:
1. Missing `apt update` step — `_UpdateCheckWorker.run()` called only
   `apt list --upgradable` (no root needed, reads stale cache, no pkexec prompt).
   Fix: `UpdateBackend.run_apt_update(line_cb=None)` added — runs
   `pkexec apt update` via `subprocess.Popen` (streaming), calls `line_cb` per
   line. Worker now calls `run_apt_update` FIRST (triggering the pkexec prompt),
   then proceeds to `list_apt_upgradable`/`list_flatpak_updates` regardless of
   whether `apt update` succeeded (shows stale cache on auth denial).
2. Label invisible — `palette(mid)` stylesheet on `_updates_label` made it
   near-invisible in most themes. Fix: removed the stylesheet; label uses default
   window text color.
   Additionally: button text changes to `UPDATES_CHECKING` ("Checking for
   updates…") while the check runs and is restored to `ACTION_CHECK_UPDATES`
   in both `_on_updates_found` and `_on_update_check_failed`.
+6 tests in `test_update_backend.py` covering `run_apt_update`.

## M8 architectural decisions
- `PackageActionBackend._run()` replaced by `_run_streaming(cmd, line_cb=None)`.
  Uses `subprocess.Popen` with `stdout=PIPE, stderr=STDOUT, text=True`; iterates
  stdout lines, calls `line_cb(stripped_line)` per line, collects output; returns
  `ActionResult`. All 15+ public methods now accept `line_cb=None` and pass it
  through. Tests mock `subprocess.Popen` instead of `subprocess.run` (FakePopen
  context manager with `stdout` iterator and `returncode` attribute).
- `backends/update_backend.py` (new): `UpdateBackend.list_apt_upgradable()` →
  `apt list --upgradable` parsed by `_parse_apt_upgradable()`; returns
  `[(name, new_version), ...]`. `list_flatpak_updates()` → `flatpak remote-ls
  --updates --columns=application,version` parsed by `_parse_flatpak_updates()`.
  Both are pure functions (testable without mocking).
- `Package.update_version: str | None` added to models/package.py.
- `_PackageModel` gains `_update_map: dict[(source,name), new_version]`.
  `set_update_map()` stores the map and emits dataChanged for all rows.
  Version column display: shows "cur → new" when upgradable. `_UPGRADABLE_ROLE`
  returns bool from the map — drives the badge in the delegate.
- Update badge: `_PackageTableDelegate` paints a green 10px dot with "↑" in
  the icon column top-right corner when `_UPGRADABLE_ROLE` is True.
- `_ActionProgressDialog(QDialog)`: shown via `.open()` (non-blocking modal).
  Status label, "Show details" toggle QPushButton (QPlainTextEdit initially
  hidden, auto-expands on `mark_failed`), OK button (disabled until
  `mark_complete`/`mark_failed`). Connected to worker `output_line` signal.
  On success: `accepted` connected to `_do_reload()` (clears update map, reloads list).
  On failure: details shown in log, OK dismisses. On cancel: OK dismisses.
- `_PackageActionWorker` gains `output_line = pyqtSignal(str)`. `run()` passes
  `self.output_line.emit` as `line_cb` to all backend calls. `_run_apt` and
  `_run_flatpak` updated to handle `_Action.UPDATE` → `update_apt/update_flatpak`.
- `_UpdateCheckWorker(QObject)`: runs `UpdateBackend` on a QThread; emits
  `updates_found(dict)` or `check_failed(str)`.
- Update toolbar: "Check for updates" QPushButton + "Update all" QPushButton
  (disabled until updates found) + status QLabel. Placed between search bar
  and status toast in the right panel layout.
- Context menu: for single-app selection, if `_update_map` has an entry,
  "Update {name} ({new_ver})" appears above the separator before Reinstall.
- `_start_update_all()`: builds entries list from all upgradable packages
  (excluding busy ones) → calls `_start_action(entries, _Action.UPDATE)`.
- `_do_reload()`: clears update map, disables "Update all", clears label,
  then `reset_to_loading()` + `_start_load()`.
- Bottom-docked action panel (`_ActionPanel`) replaced `_ActionProgressDialog`.
  Panel is a 200px-fixed-height QWidget at the bottom of the right layout, hidden
  by default. `start_action(desc)` shows it; Dismiss button hidden until action
  completes. `output_line` signal wired directly to `panel.append_line`. Result
  label updated on `mark_complete`/`mark_failed`. `dismissed` signal drives
  `_on_panel_dismissed` which reloads the list iff `_reload_on_dismiss` flag was
  set True by `_on_action_success`. Buttons re-enable on completion (not dismiss),
  so user can queue next check while reading the log. Confirmation dialog retained.
- New strings: `ACTION_UPDATE`, `ACTION_UPDATE_ALL`, `UPDATES_CHECKING`,
  `UPDATES_AVAILABLE_N`, `UPDATES_NONE`, `CONFIRM_UPDATE_QUESTION`,
  `CONFIRM_UPDATE_SUBTITLE`, `CONFIRM_UPDATE_ALL_QUESTION`,
  `CONFIRM_UPDATE_ALL_SUBTITLE`, `ACTION_LOG_SHOW`, `ACTION_LOG_HIDE`.
- New tests: `test_update_backend.py` (18), `test_package_action_backend.py`
  +9 (streaming + update methods), `test_m8_update_ui.py` (12: streaming
  line_cb, update map, dialog states).

## Setup
- Current dev machine: Ubuntu 24.04 + Plasma 5.27
  (original dev machine was Kubuntu 26.04 + Plasma 6)
- theme.py integration testing deferred to a Plasma 6 machine
- Python venv at ~/ekplorer/.venv — always activate before 
  running or testing

## How to run
cd ~/ekplorer && source .venv/bin/activate && python main.py

## How to test
cd ~/ekplorer && source .venv/bin/activate && pytest -v

## How to start Claude Code
cd ~/ekplorer && source .venv/bin/activate && claude

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

## M7 architectural decisions
- Column index 0 is _COL_ICON (36px fixed, ResizeMode.Fixed, blank header).
  All prior column indices shifted +1. Named constants eliminate hardcoded
  column numbers everywhere.
- PackageIconResolver(theme_lookup) lives in package_icon_resolver.py.
  theme_lookup defaults to QIcon.fromTheme; inject a stub in tests.
  Tier 1: scans ~/.local/share/ekplorer/icons/ ONCE at construction (and
  on invalidate()); checks name.svg then name.png.
  Tier 2: _candidate_chain() yields: name, name.lower(), flatpak DNS tail
  (both cases), hyphen-prefix prefixes (both cases), deduped.
  Tier 3: loads assets/category-icons/{CATEGORY_ICON_KEYS[display_cat]}.svg
  else .png; floor is unknown.svg — always bundled, never null.
  Results are cached per (name, source) tuple.
- PackageQuery is a frozen dataclass with fields name/tag/category/source/
  version/size (all strings, default ""). parse() in package_query.py
  tokenises by whitespace; "modifier:value" or "modifier: value" (pending
  field) fills the field; unknown modifiers fall to name free-text.
- _PackageFilterProxy.set_query(PackageQuery) calls invalidateFilter() only
  when the query actually changed (dataclass equality). Search query ANDs
  with existing _cat_filter and _tag_filter.
- 13 bundled category SVGs (+13 PNGs) in assets/category-icons/. Keys in
  strings.CATEGORY_ICON_KEYS map display category names to icon filenames.
  Generator script at assets/category-icons/_gen_icons.py.
- QIcon(png_path) SIGABRT inside pytest/xcb (PyQt6 6.11); works fine at
  runtime. PNG-loading tests replaced with logic-only assertions.

## M6 architectural decisions
- Package.name = apt package name OR flatpak app-id (e.g. org.mozilla.firefox).
  This is the stable DB key and the literal string passed to commands.
  Package.display_name = flatpak friendly name ("Firefox"); "" for apt.
  Name column uses display_name if set, else name. Sort also uses display_name.
- _BackendLoader(fn: callable) is a generic QObject worker. One instance
  wraps PackagesBackend().list_installed, another FlatpakBackend().list_installed.
  Both are started in _start_load(); _pending_count decrements on each completion;
  _finalize_load() merges results once _pending_count == 0.
- _PackageActionWorker now takes pkg_entries: list[tuple[str,str]] = [(name, source)].
  run() groups by source, calls _run_apt() or _run_flatpak() for each group.
  Mixed-source batches run apt first then flatpak; failures merged into one stderr.
  Signals still emit list[str] (names) for UI handlers — source is internal.
- Flatpak actions use pkexec flatpak ... (single) or pkexec bash -c "..." (batch/reset).
  UNINSTALL_PURGE → --delete-data; UNINSTALL_KEEP → no flag. Same confirmation
  dialog text as apt (subtitles already describe the semantics correctly).
- _tag_icon() creates a 12×12 QPixmap filled circle in the tag's color_hex,
  returned as QIcon and set on each tag sidebar item. Replaces "●" plain text.
- FlatpakBackend.is_available() uses shutil.which("flatpak"). Called once at
  PackagesView init; result drives _sidebar.set_flatpak_available(bool).

## M5+ architectural decisions (multi-select)
- _uninstalling_name: str | None replaced by _busy_names: frozenset[str]
  so any number of packages can be marked busy simultaneously.
- set_busy(names: list[str] | None) / is_busy(pkg_name: str) replace
  set_uninstalling / uninstalling_name property.
- _PackageActionWorker signals changed to pyqtSignal(object, str) /
  pyqtSignal(object) to carry list[str] through Qt signal machinery.
- Worker dispatches to single-pkg or batch backend methods depending
  on len(pkg_names); batch methods use shlex.quote for shell safety.
- _BatchConfirmDialog(QDialog) lives in packages_view.py; contains a
  QListWidget (max height 200px) so 200-package lists don't blow out.
- _entries_for_action(clicked_entry): if the clicked row is in the
  current selection the whole selection is used; otherwise just that row.
  This matches Windows Explorer right-click semantics exactly.
- _get_selected_entries() deduplicates via a seen set (selectedIndexes
  returns one index per column; selectedRows is per-row).
- open_for_batch on TagModal: pill starts "assigned" only when ALL
  batch entries already have that tag; save writes final pill state to
  every entry in the batch (no per-entry delta — clean replacement).

## M5 architectural decisions
- backends/package_action_backend.py replaces uninstall_backend.py.
  PackageActionBackend has three public methods; all share _run().
- reinstall_reset uses a single pkexec bash -c invocation so the
  user sees one auth prompt. The && short-circuit means install
  never runs if purge fails — no special error-path needed.
- _Action enum in packages_view.py drives worker dispatch and the
  _ACTION_CONFIRM/_ACTION_LABEL class-level dicts, avoiding any
  if/elif chains outside of _PackageActionWorker.run().
- _UNINSTALLING_ROLE name kept (not renamed) — it marks "row is
  busy", regardless of which action is running.
- _on_action_success calls reset_to_loading() before _start_load()
  so the package list snaps to skeleton immediately; avoids the
  uninstalled/old-version package flickering for reload duration.

## M4.5 architectural decisions
- QAbstractTableModel (_PackageModel) holds the flat list; no
  filtering — that's entirely the proxy's job.
- QSortFilterProxyModel (_PackageFilterProxy) owns cat+tag filter
  AND numeric Size sort (lessThan uses _SORT_ROLE int for Size,
  str for all other cols). filterAcceptsRow returns True for
  skeleton rows so shimmer is visible while loading.
- Tag filter bug was an inverted predicate: old list model's
  _rebuild_shown used `any(...)` (keep if tag present), but the
  proxy convention needs `not any(...)` → return False.
- Three-dot "⋯" is in the Size column's last _DOTS_W=24 px.
  eventFilter computes size-cell visualRect then checks .contains.
- Row height fixed at 32px via verticalHeader setDefaultSectionSize
  + ResizeMode.Fixed; delegate sizeHint not overridden.
- Header: Name=Stretch, Tags/Category/Version/Size=Interactive.
  Default sort: Name ascending via proxy.sort() at init.
- Tags column sorts by first tag name (lowercase); no-tag rows
  sort before "a" (empty string).
- Delegate calls super().paint() with opt.text="" for Tags and Size
  columns so selection/alternating-row background is handled by Qt;
  then paints pills or size+dots on top.

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

## POLISH PASS: chrome icons + action panel

### Part 1 — Chrome icons always visible (`views/file_view.py`, `views/file_manager_view.py`, `main.py`)

**`views/file_view.py`**:
- Added `QStyle` to `PyQt6.QtWidgets` imports.
- Added `_chrome_icon(theme_name, fallback_standard=None) -> QIcon` (module-level,
  after the icon-cache globals). Logic: if `_THEME_VIABLE is not False`, tries
  `QIcon.fromTheme(theme_name)` first; if null or on non-viable system, falls back to
  `QApplication.style().standardIcon(fallback_standard)`. Returns `QIcon()` if no
  fallback given.

**`views/file_manager_view.py`** — slider tick labels:
- `_build_view_slider()` tick labels: changed from `"font-size: 8px; color: palette(mid);"`
  to `"font-size: 9px; color: palette(windowText);"`. `palette(mid)` ≈ `#474b50` on
  Breeze Dark — invisible against dark toolbar. `palette(windowText)` is always the
  theme's foreground text color.

**`main.py`**:
- Added `QStyle` to `PyQt6.QtWidgets` imports.
- Added `from views.file_view import _chrome_icon`.
- Replaced both `QIcon.fromTheme` tab icon calls:
  - `"system-file-manager"` → `_chrome_icon("system-file-manager", SP_DirOpenIcon)`
  - `"utilities-terminal"` → `_chrome_icon("utilities-terminal", SP_ComputerIcon)`

### Part 2 — Action panel height (`views/file_manager_view.py`)

`_FmActionPanel` now has two heights:
- `_HEIGHT_COLLAPSED = 40` — default; single row: status label + two buttons, vertically
  centered within the 40px panel.
- `_HEIGHT_EXPANDED = 200` — after "Show details" toggle; log QPlainTextEdit becomes
  visible and fills remaining space.

Changes vs. prior state:
- `setFixedHeight(160)` → `setFixedHeight(self._HEIGHT_COLLAPSED)` in `__init__`.
- Button `setFixedHeight(22)` → `24` (both `_toggle_btn` and `_dismiss_btn`).
- Removed `self._log.setMaximumHeight(110)` — panel height now governs log size.
- `_toggle_log()` now calls `self.setFixedHeight(HEIGHT_EXPANDED or HEIGHT_COLLAPSED)`
  after toggling log visibility. Snap, no animation.

### Tests: 580/580 (unchanged count — no new tests needed for pure visual fixes)

## POLISH PASS 2: sidebar tree auto-refresh + action panel height

### Part 1 — Sidebar tree auto-refresh (`views/navigation_sidebar.py`, `views/file_manager_view.py`)

**`NavigationSidebar`** — three new methods:

- `refresh_expanded_nodes()` (public): iterates both `_quick_tree` and `_drives_tree`
  calling `_sync_expanded(tree.invisibleRootItem())`, then `tree.updateGeometry()`.

- `_sync_expanded(item)` (private): walks all children of `item`; for each that
  `isExpanded()` AND whose children have been lazy-loaded (no placeholder child),
  calls `_sync_node_children(child)` then recurses into that child.

- `_sync_node_children(item)` (private): reads immediate non-hidden subdirs from disk;
  builds a dict of current child items (bailing out if a placeholder is still present);
  removes stale children (`removeChild`); adds new children with the same
  has-subdirs/placeholder logic as `_populate_subdirs`; re-sorts via `sortChildren`
  when more than one child exists.  Handles `PermissionError` / `OSError` silently.

**`FileManagerView`** — `refresh_expanded_nodes()` called after every successful
directory-modifying operation:
- `_on_ops_succeeded` (move/copy/delete/trash/drop → `_start_file_op` path)
- `_do_rename` (synchronous inline rename)
- `"new_folder"` branch of `_on_action_requested`
- `navigate_to()` (so a freshly created folder is immediately visible in the tree)

NOT called on `_on_ops_failed` (operation didn't complete; sidebar state unchanged).

### Part 2 — Action panel height

Already completed in the previous POLISH PASS session (40/200px snap).
No further changes needed.

### Tests: 583/583 (+3 new in test_m10a_navigation_sidebar.py)
- `test_refresh_expanded_nodes_adds_new_child` — new subdir appears after refresh
- `test_refresh_expanded_nodes_removes_stale_child` — deleted subdir disappears after refresh
- `test_refresh_expanded_nodes_skips_unexpanded` — placeholder-bearing (never-expanded)
  items are left untouched

## POLISH PASS 3: sidebar tree icons

### Implementation (`views/navigation_sidebar.py`)

**New imports**: `QSize` (QtCore), `QIcon` (QtGui), `QApplication`, `QStyle` (QtWidgets),
`from views.file_view import _chrome_icon` — shares the existing viability probe/cache.

**`_XDG_ICONS` dict** (module-level, after `_XDG_ENTRIES`): maps each `strings.NAV_*`
label to its freedesktop theme name.

**`_nav_icon(*theme_names, fallback_standard=None) → QIcon`** (module-level):
- Iterates theme names, calling `_chrome_icon(name)` for each; returns first non-null.
- Falls back to `QApplication.style().standardIcon(fallback_standard)` if given.
- Floors to `SP_DirIcon` so the result is never null.

**Icon assignments at item creation:**
| Location | Theme names tried | QStyle fallback |
|---|---|---|
| XDG Quick Access items | `_XDG_ICONS[label]` (e.g. "user-home") | `SP_DirIcon` |
| `_populate_subdirs` children | `"folder"` | `SP_DirIcon` |
| `_sync_node_children` new children | `"folder"` | `SP_DirIcon` |
| System drive (`/`) | `"drive-harddisk-root"`, `"drive-harddisk"` | `SP_DriveHDIcon` |
| Other mounted drives | `"drive-harddisk"` | `SP_DriveHDIcon` |
| Unmounted drives | `"drive-harddisk"` | `SP_DriveHDIcon` (keep orange text) |
| Recent files/locations buttons | `"folder-recent"`, `"document-open-recent"` | `SP_DirIcon` |

`_make_tree_item` gains an `icon: QIcon | None = None` keyword parameter; applies
`item.setIcon(0, icon)` when non-null.  Recent-entry buttons receive `btn.setIcon()`
+ `btn.setIconSize(QSize(16, 16))` after construction.

No `removable` detection added — `Drive` model has no such field; all non-system
mounted drives use `"drive-harddisk"`.

### Tests: 585/585 (+2 new in test_m10a_navigation_sidebar.py)
- `test_quick_access_items_have_icons` — every XDG Quick Access item has non-null icon
- `test_drives_tree_items_have_icons` — every drive item after `set_drives()` has non-null icon

## M10d.1: Trash / Wastebin entity + permanent-delete relocation

### Part A — "Delete Permanently" removed from file context menu (`views/file_view.py`)
`FM_CTX_DELETE` removed from `_on_context_menu`. **Shift+Delete** keyboard shortcut retained in
`FileManagerView.__init__` as hidden power shortcut (fires `_confirm_and_delete` with confirmation).

### Part B — Wastebin sidebar node (`views/navigation_sidebar.py`)
- `NAV_WASTEBIN = "Wastebin"` and `TRASH_SENTINEL = "trash:///"` added to `strings.py`.
- `self._wastebin_item` (QTreeWidgetItem) added to `_quick_tree` after all XDG entries;
  no placeholder child (not expandable). Path stored via `Qt.ItemDataRole.UserRole`.
- Icon: `_nav_icon("user-trash", fallback_standard=SP_TrashIcon)`.
- `update_wastebin_icon()` public method: calls `TrashBackend().trash_count()` and sets
  icon to `"user-trash-full"` if non-zero, else `"user-trash"`.
- `wastebin_action_requested = pyqtSignal(str)` signal.
- `_quick_tree` gets `CustomContextMenu` policy; `_on_quick_tree_context_menu()` shows
  Wastebin context menu when right-clicking `_wastebin_item`:
  - "Restore All Files" → `wastebin_action_requested.emit("restore_all")`
  - "Empty Wastebin" → `wastebin_action_requested.emit("empty")`
  - "Shred Delete…" → disabled; tooltip = `TRASH_SHRED_TOOLTIP` ("Coming in a future security update")

### Part C — TrashView (`views/trash_view.py`, NEW)
`TrashView(QWidget)` with `action_requested = pyqtSignal(str, list)`.
- `QTreeWidget` with 4 columns: Name (200px interactive) | Original Location (stretch) |
  Deletion Date (150px interactive) | Size (80px interactive).
- `load(entries)` populates from `list[TrashEntry]` (pre-sorted newest-first).
- Icon: folder icon for dirs, `QFileIconProvider.IconType.File` for files.
- Per-item context menu: Restore → `emit("restore", entries)`;
  Delete Permanently → `emit("delete_permanently", entries)`.

### Part D/E — TrashBackend (`backends/trash_backend.py`, NEW)
- `TrashEntry` dataclass: name, trash_path, original_path, deletion_date, size, is_dir, mime_type.
- `TrashBackend(trash_dir=None)` — `trash_dir` param for test injection.
- Follows freedesktop.org Trash spec: `~/.local/share/Trash/{files,info}/` + per-mount `.Trash-<uid>/`.
- `list_trash()` → parses all `.trashinfo` files, returns sorted newest-first.
- `restore(entries, conflict_strategy, line_cb)` → moves to original path, removes `.trashinfo`.
- `empty_trash(line_cb)` → deletes all of `files/` and `info/`.
- `delete_permanently(entries, line_cb)` → removes specific items only.
- `trash_count()` → fast count of `*.trashinfo` files.
- `shred(entries, line_cb)` → raises `NotImplementedError` ("M10f").
- `_TrashWorker(QObject)` defined in `try: from PyQt6` block (Qt-optional pattern);
  ops: `"restore"`, `"empty"`, `"delete_permanently"`.

### Part F — FileManagerView integration (`views/file_manager_view.py`)
- `_left_view` and `_trash_view` wrapped in `_left_stack (QStackedWidget)`:
  index 0 = `FileView`, index 1 = `TrashView`.
- `_in_trash_mode: bool` flag controls Up/Back behavior and address bar label.
- `navigate_to(path)`: if `path == TRASH_SENTINEL` → `_enter_trash_mode()`.
- `_enter_trash_mode()`: switches stack to index 1, shows "Wastebin" in address bar,
  enables Back/Up (disable Forward), calls `_load_trash()` + `update_wastebin_icon()`.
- `_exit_trash_mode()`: switches stack to index 0, restores address bar to current path.
- `_handle_back/forward/up()` replace direct `_left_view.navigate_*` connections
  (nav buttons rewired through these handlers to support trash mode).
- `_on_trash_action(action, entries)`: dispatches to `_start_trash_op` or `_confirm_and_trash_delete`.
- `_on_wastebin_action(action)`: dispatches to `_confirm_and_empty_trash` or `_start_trash_op`.
- `_start_trash_op(op, entries)`: runs `_TrashWorker` on QThread (parallel to `_start_file_op`).
- `_on_trash_succeeded/failed`: refreshes trash view + calls `update_wastebin_icon()`.
- `_on_ops_succeeded` also calls `update_wastebin_icon()` (icon updates after file→trash).
- `_address_bar.navigate_requested` now connects to `navigate_to` (not `_left_view.navigate`),
  so typing "trash:///" in the address bar enters trash mode.

### Test suite fix: PropertiesPanel thread parenting
- **Bug found**: `QThread(parent=self)` in `PropertiesPanel` caused SIGABRT in the full
  test suite when `_OpenWithLoader` (subprocess-based) was still running at GC time.
  Qt's parent-child destructor killed the running thread, corrupting CPython's thread state.
- **Fix**: changed all three thread creations to `QThread(parent=QApplication.instance())`.
  This moves C++ ownership to the long-lived QApplication; thread self-destructs via
  `finished.connect(thread.deleteLater)` when done. Added to all three workers:
  `_ChmodWorker`, `_ChecksumWorker`, `_OpenWithLoader`.
- Added `tests/conftest.py` with session-scoped `qt_app` fixture (one `QApplication` for
  the whole test session) to prevent QApplication create/destroy cycling between tests.

### New strings (all in `strings.py` M10d.1 block)
`NAV_WASTEBIN`, `TRASH_SENTINEL`, `TRASH_ADDRESS_LABEL`, `TRASH_COL_NAME/ORIGINAL/DATE/SIZE`,
`TRASH_CTX_RESTORE/DELETE`, `TRASH_WB_RESTORE_ALL/EMPTY/SHRED`, `TRASH_SHRED_TOOLTIP`,
`TRASH_EMPTY_TITLE/MSG/YES/NO`, `TRASH_DELETE_TITLE/ONE/MANY/YES/NO`, `TRASH_RESTORE_TITLE`,
`TRASH_OP_RESTORING/EMPTYING/DELETING`.

### Tests: 594/594 (+9 new in `tests/test_m10d1_trash.py`)

## M10d.1 Follow-up 2: System clipboard + listing refresh + tag auto-show

### Part 1 — System clipboard interop (`views/file_manager_view.py`)

**`_set_system_clipboard(op, paths)`** (new helper):
- Builds a `QMimeData` object with three MIME types and sets it on `QApplication.clipboard()`:
  - `text/uri-list` → `QUrl.fromLocalFile` URLs of the selected paths.
  - `text/plain` → newline-joined POSIX paths.
  - `x-special/gnome-copied-files` → `b"copy\n"` or `b"cut\n"` prefix + newline-joined file:// URLs (GNOME/Nautilus convention).
  - `application/x-kde-cutselection` → `b"1"` (KDE/Dolphin convention, cut only).
- `QMimeData` and `QUrl` added to `PyQt6.QtCore` imports.

**`_do_paste()`** rewritten to read from the system clipboard:
1. `QApplication.clipboard().mimeData()` → if has file URLs, decode them:
   - Check `application/x-kde-cutselection == "1"` → move.
   - OR check `x-special/gnome-copied-files` starts with `"cut\n"` → move.
   - Otherwise → copy.
2. Falls back to internal `_clipboard` if system clipboard has no file URLs.
3. After a move-paste, calls `QApplication.clipboard().clear()` to signal the cut is consumed.
4. Internal `_clipboard` is cleared (`= None`) on move-paste.

**`_on_clipboard_changed()`** (new slot): connected to `QApplication.clipboard().dataChanged`
in `__init__`. Reads system clipboard `hasUrls()` or internal `_clipboard` to set paste-enabled
state on both left and right `FileView`s. Copy/cut action no longer manually calls
`set_paste_enabled(True)` — that's driven by the `dataChanged` signal.

**`FmClipboard`** kept as thin tracker for cut-visual state (dimmed icons, if ever added). 
Source of truth for paste is now the system clipboard.

### Part 2 — Targeted listing refresh (`views/file_manager_view.py`)

**`_last_op_target_dir: Path | None`** (new instance variable): set in `_start_file_op` to
`dst_dir or self._current_path` so completion handlers know which directory changed.

**`_refresh_panes_for_dir(target_dir: Path | None)`** (new helper):
- Reloads left pane if `_shown` and `current_path == target_dir`.
- Reloads right pane if `_shown` and `current_path == target_dir`.
- Falls back to refreshing both panes when `target_dir is None`.

**`_on_ops_succeeded`** / **`_on_ops_failed`**: replaced `_refresh_left()` + `_refresh_right()`
with `_refresh_panes_for_dir(self._last_op_target_dir)`. Only the pane currently showing
the operation's target directory reloads; unaffected panes are left alone.

**`_on_trash_succeeded`** / **`_on_trash_failed`** (bug fix): added `_refresh_left()`,
`_refresh_right()`, and `_sidebar.refresh_expanded_nodes()`. Previously these never called any
pane refresh, so restored files didn't appear until re-navigation.

### Part 3 — FM tag auto-show (already working)
M10e was completed in the session immediately before this follow-up. The `FileTagModal.saved`
signal already connects to `_load_file_tags()` → `_left_view.set_tag_map()` → `dataChanged`
repaint. No additional work needed; tags appear immediately after the modal closes.

### Tests: 633/633 (+20 new in `tests/test_m10d1_followup2.py`)
Clipboard (6): copy writes URI list; copy writes plain text; copy sets GNOME copy marker; cut sets KDE marker; cut sets GNOME cut marker; cut URL appears in GNOME marker.
Paste (6): plain URLs → copy; KDE cut marker → move; GNOME cut prefix → move; GNOME copy prefix → copy; falls back to internal clipboard; empty clipboard is no-op.
Refresh (8): targeted left reload; both panes reload if both match; non-matching skipped; None fallback reloads both; ops_succeeded uses targeted; ops_failed uses targeted; trash_succeeded refreshes left; trash_succeeded refreshes right.
1. `test_list_trash_parses_trashinfo` — parses name, original_path, deletion_date, size
2. `test_restore_moves_file_and_removes_trashinfo` — file moves to original location, .trashinfo deleted
3. `test_empty_trash_clears_both_dirs` — files/ and info/ both empty after empty_trash()
4. `test_delete_permanently_removes_specific_items_only` — only named items removed, others kept
5. `test_shred_raises_not_implemented` — raises NotImplementedError
6. `test_trash_count_returns_correct_count` — 0/1/2 count tracking
7. `test_context_menu_has_trash_not_delete` — FM_CTX_DELETE absent, FM_CTX_TRASH present
8. `test_shift_delete_shortcut_wired` — "Shift+Delete" and "delete" still in FileManagerView.__init__
9. `test_wastebin_icon_switches_on_trash` — update_wastebin_icon() runs without error on empty/full trash

## M10e: File Tags

### Schema
- Schema bumped to v5. `CURRENT_VERSION=5`.
- New table: `file_tags(path TEXT, tag_name TEXT NOT NULL REFERENCES tags(name) ON DELETE CASCADE, PRIMARY KEY(path, tag_name))`.
- Index `idx_file_tags_path` on `path` for fast per-file lookups.
- Reuses the shared `tags` table (same color-named tags as packages). File tags and package tags are the same tag objects but in separate junction tables.
- `ON DELETE CASCADE` ensures deleting a tag from the `tags` table removes all file_tag assignments.

### Backend (`backends/file_tags_backend.py`, NEW)
- `FileTagRepository(db_path=None)` — stateless CRUD helper.
  - `tags_for_path(path: str) -> list[Tag]` — all tags for one file path, alphabetical.
  - `bulk_load(paths: list[str]) -> dict[str, list[Tag]]` — single SQL query with IN clause; returns only paths that have at least one tag.
  - `set_assignments(path: str, assigned_names: set[str]) -> None` — replaces all assignments for a path (DELETE then INSERT).

### `views/file_view.py` changes
- `_TAG_DATA_ROLE = Qt.ItemDataRole.UserRole + 3` — returns `list[Tag]` for `_COL_TAGS`.
- `_FileModel._tag_map: dict[str, list[Tag]]` — path_str → tag list, empty by default.
- `_FileModel.set_tag_map(tag_map)` — replaces the map, emits `dataChanged` on `_COL_TAGS` for all rows.
- `_FileModel.data()` updated:
  - `DisplayRole` for `_COL_TAGS`: comma-joined tag names (or empty string).
  - `_SORT_ROLE` for `_COL_TAGS`: first tag name lowercased (or empty string for untagged).
  - `_TAG_DATA_ROLE` for `_COL_TAGS`: `list[Tag]` (for pill rendering).
- `_FilePillDelegate(QStyledItemDelegate)` — new class; installed on `_COL_TAGS` of `_tree`. Paints colored rounded-rect pills using the same constants (`_PILL_H`, `_PILL_H_PAD`, `_PILL_GAP`, `_MAX_PILLS`) and overflow `…+N` indicator as `_PackageTableDelegate` in packages_view.
- `FileView.entries_ready = pyqtSignal()` — fired after each successful directory load (via `_worker.ready` → `lambda _: self.entries_ready.emit()`). Lets FileManagerView react without coupling to internal model state.
- `FileView.set_tag_map(tag_map)` — public proxy to `_model.set_tag_map()`.
- `models.tag.Tag` imported into `file_view.py`.

### `views/file_tag_modal.py` (NEW)
- `FileTagModal(QDialog)` — modal dialog for assigning tags to one or more `FileEntry` objects.
- Uses `TagRepository` for tag definitions (create + all_tags) and `FileTagRepository` for path assignments.
- Multi-file: pill starts assigned only if ALL selected paths have the tag.
- Flow layout for pills (copy of `_FlowLayout` from `tag_editor_modal.py`).
- Color swatches from `strings.TAG_PALETTE` for creating new tags.
- `saved = pyqtSignal()` emitted before `accept()`.

### `views/file_manager_view.py` changes
- Imports `FileTagRepository` from `backends.file_tags_backend`.
- `entries_ready` connection: `self._left_view.entries_ready.connect(lambda: self._load_file_tags())` — uses lambda so monkeypatching `_load_file_tags` works in tests.
- `_load_file_tags()` — reads `_left_view._model._entries`, bulk-loads tags via `FileTagRepository`, calls `_left_view.set_tag_map()`.
- `_open_file_tag_modal(entries)` — lazy-imports `FileTagModal`, opens it with `exec()`, connects `saved` → `_load_file_tags`.
- `assign_tags` branch in `_on_action_requested` now calls `_open_file_tag_modal(entries)` (replaces placeholder `QMessageBox`).
- `FileTagModal` import is local (lazy) to avoid circular import risk.

### New strings (all in `strings.py` M10e block)
`FT_MODAL_TITLE`, `FT_MODAL_TITLE_BATCH`, `FT_MODAL_SUBTITLE`, `FT_NO_TAGS_MSG`,
`FT_CREATE_HEADER`, `FT_ASSIGN_HEADER`, `FT_SAVE_BTN`, `FT_CANCEL_BTN`.

### Tests: 613/613 (+19 new in `tests/test_m10e_file_tags.py`)
Backend (6): tags_for_path empty; set/retrieve single; multiple tags; replace assignments; clear with empty set; independent paths.
Bulk load (5): empty list; no tagged paths; tagged vs untagged; multiple tags on one path; multiple paths.
Schema (2): file_tags table created; cascade delete removes file_tags.
Model (3): set_tag_map propagates; DisplayRole shows joined names; _SORT_ROLE returns first tag lowercase.
Integration (3): FileView has entries_ready signal; FileManagerView._load_file_tags called on signal; assign_tags action calls _open_file_tag_modal.
Also: fixed `test_v4_migration_sets_user_version` to use `== CURRENT_VERSION` (not hardcoded 4).

## PropertiesPanel crash fix + FM tag dataChanged (post-M10e)

### Part 1 — PropertiesPanel crash in dual-pane mode (`views/properties_panel.py`)

**Root cause**: In dual-pane mode, rapidly selecting different files triggers `populate_general()` before
the previous `_OpenWithLoader` worker has finished. `_OpenWithLoader` runs a subprocess (`xdg-mime query`),
so `QThread.quit()` does not stop it mid-run. When the old worker's `apps_ready` signal fires after the
new `populate_general()` has started, it overwrites the new UI state and can cause GC-SIGABRT if Python's
garbage collector finalizes the stale wrapper while Qt's thread is still alive.

**Fix: `_cancel_workers()` method**:
- Disconnects `apps_ready` from `_on_apps_ready` on the OW worker.
- Disconnects `checksums_ready` / `failed` from their slots on the CS worker.
- Disconnects `done` / `failed` from their slots on the chmod worker.
- Calls `quit()` + `wait(100)` on any running thread.
- Sets all `_*_thread` / `_*_worker` attrs to `None`.
- Threads are parented to `QApplication.instance()` (set previously) — they self-destruct via
  `finished.connect(deleteLater)` when they eventually finish. Signal disconnection prevents stale
  callbacks from touching UI during the overlap window.

**Fix: generation counter**:
- `self._generation: int` — incremented at the start of every `populate_general()` and `show_placeholder()`.
- `self._ow_expected_gen: int` — captured inside `_populate_open_with()` at thread-start time.
- `self._cs_expected_gen: int` — captured inside `_on_compute_checksums()` at thread-start time.
- `_on_apps_ready()`: returns immediately if `_ow_expected_gen != _generation`.
- `_on_checksums_ready()` / `_on_checksums_failed()`: return immediately if `_cs_expected_gen != _generation`.

**Call sites updated**:
- `populate_general()`: calls `_cancel_workers()` + increments `_generation` before any other work.
- `show_placeholder()`: calls `_cancel_workers()` + increments `_generation`.
- `_populate_open_with()`: removed redundant `if isRunning(): quit()` guard (handled by `_cancel_workers()`);
  added `self._ow_expected_gen = self._generation`.
- `_on_compute_checksums()`: added `self._cs_expected_gen = self._generation`.

### Part 2 — FM tag dataChanged (already working, confirmed by test)
M10e is complete and the tag-assign flow is fully wired:
`FileTagModal.saved → _load_file_tags() → _left_view.set_tag_map() → _FileModel.set_tag_map() → dataChanged`
Tags appear in the Tags column immediately after the modal closes, with no reload needed.
No code changes needed; confirmed by `test_load_file_tags_triggers_data_changed_on_col_tags`.

### Tests: 665/665 (20 in `tests/test_properties_panel_crash_fix.py`, 12 in `tests/test_tag_repaint_fix.py`)
Cancel workers (6): safe when no workers; clears refs on mocked threads; disconnects OW signal; disconnects CS signals; disconnects chmod signals; calls quit+wait on running thread.
Generation counter (8): increments on populate_general; increments on show_placeholder; _ow_expected_gen matches after populate; stale apps_ready discarded; current apps_ready applied; stale checksums_ready discarded; current checksums_ready applied; stale checksums_failed suppresses dialog.
Crash resilience (4): populate_general twice doesn't crash; show_placeholder after populate clears workers; populate switches stack to tabs; show_placeholder switches to placeholder.
FM tags (2): set_tag_map emits dataChanged on _COL_TAGS; dataChanged covers all rows.

## Tag repaint fix + chmod generation guard (post-M10e fix pass)

### Part 1 — Packages Tags column repaint (`views/packages_view.py`)

**Root cause**: `_on_tags_saved()` called `self._model.set_entries(updated)` which uses
`beginResetModel/endResetModel`. This reset the entire model, losing scroll position, selection,
and sort order. Functionally correct, but disruptive to UX and not targeted.

**Fix: `_PackageModel.refresh_tags(assignments)` (new method)**:
- Iterates `_entries` in-place, replacing each entry's `.tags` list from `assignments` dict.
- Emits `dataChanged` for `_COL_TAGS` only (row 0 to rowCount-1).
- No-op when `_entries is None` (loading state).
- `QSortFilterProxyModel` automatically re-evaluates `filterAcceptsRow` for changed rows when
  `dataChanged` fires, so tag-filter visibility updates without manual `invalidateFilter()`.
- Key is `(source, name)` tuple — works for both APT and Flatpak packages.

**`_on_tags_saved()` simplified**:
```python
def _on_tags_saved(self) -> None:
    self._dim.setVisible(False)
    assignments = self._repo.load_all_assignments()
    self._model.refresh_tags(assignments)
    self._refresh_sidebar()
```

### Part 2 — FM Tags column (scope verdict)
**M10e IS built.** The tag-assign flow exists and is wired:
`_on_action_requested("assign_tags") → _open_file_tag_modal() → FileTagModal.saved → _load_file_tags() → set_tag_map() → dataChanged on _COL_TAGS`
No code change needed; confirmed by test.

### Part 3 — Chmod generation guard (`views/properties_panel.py`)
Added `self._chmod_expected_gen: int = -1` to `__init__`. Set in `_on_chmod_clicked()`.
Generation guard added to `_on_chmod_done()` and `_on_chmod_failed()` — stale chmod results
from a previous file are discarded if the selection has moved on.

### Tests: 665/665 (+12 new in `tests/test_tag_repaint_fix.py`)
Packages refresh_tags (6): emits dataChanged on _COL_TAGS; covers all rows; updates entries in-place; clears absent tags; no-op when loading; handles flatpak source key.
_on_tags_saved (1): triggers dataChanged not modelReset.
FM (1): _load_file_tags → dataChanged on _COL_TAGS.
Chmod guard (4): stale done doesn't re-enable button; stale failed suppresses dialog; current done re-enables; expected gen set on click.

## Global rename: eKploiter → eKplorer (tag: v0.1-alpha-ekplorer)

**Commit:** `fb38662 rename: eKploiter → eKplorer`  
**Tag:** `v0.1-alpha-ekplorer`

Pure string/path rename — no logic changes. Three substitution patterns applied to all `.py`, `.md`, `.desktop`, `.toml` files:
- `"System eKploiter"` → `"System eKplorer"`
- `"eKploiter"` → `"eKplorer"`
- `"ekploiter"` → `"ekplorer"`

Asset files renamed: `assets/ekploiter.desktop` → `assets/ekplorer.desktop`, `assets/icons/ekploiter.png` → `assets/icons/ekplorer.png`.

**Data directory migration** (`main.py`, `_migrate_data_dir()`):  
Called at startup before the database opens. If `~/.local/share/ekploiter/` exists **and** `~/.local/share/ekplorer/` does not, the old directory is renamed in-place via `Path.rename()`, preserving all user data (DB, icons, settings) transparently. Logs one line to stderr. If both directories exist (user has run both versions), `ekplorer/` is used and `ekploiter/` is left untouched — no merge, no delete.

**Intentional "ekploiter" occurrences kept in `main.py`** (lines 129 and 134): `_OLD_DATA_DIR` constant and its docstring reference the *old* directory path by design — these must not be renamed or the migration breaks.

**DB path** (`models/database.py`): `DB_PATH = Path.home() / ".local" / "share" / "ekplorer" / "data.db"`

Tests: 665/665 (no new tests; no test assertions checked the old name string).

## Single instance + default file manager registration

### Part A — Single instance (`main.py`)

**Socket name:** `f"ekplorer-{os.getuid()}"` — per-user, no collision with other users.

**Startup flow:**
1. `_generate_desktop_file()` runs (Part C) before `QApplication` is created.
2. `QApplication` is created so `QLocalSocket` is usable.
3. `_try_become_secondary(socket_name, path_arg)` tries `QLocalSocket.connectToServer(name)` + `waitForConnected(500ms)`.
   - Connected → send `path_arg + "\n"` as UTF-8, close socket, `sys.exit(0)`.
   - Not connected → we are the primary instance, continue.
4. `MainWindow.start_server(socket_name)` calls `QLocalServer.removeServer()` (clears stale socket) then `QLocalServer.listen()`.
5. `newConnection → _on_new_instance_connection()`: reads the path from the socket, calls `raise_()` + `activateWindow()`, navigates to the path if it's a directory.

**`_local_server`** is stored on `MainWindow` as `QLocalServer | None` (parented to the window, cleaned up on close).

### Part B — CLI argument handling (`main.py`)

`_normalize_path_arg(arg)`: strips `"file://"` prefix then `urllib.parse.unquote()`. Pure function, no Qt.

After `window.show()`, if `path_arg` is non-empty:
- `Path(path_arg).is_dir()` → `navigate_to_directory(path_arg)` (switch to FM tab)
- `Path(path_arg).is_file()` → `navigate_to_directory(str(p.parent))` (navigate to parent, file not selected — no FM selection API yet)

Normal launch (no args) → Dashboard as before.

### Part C — Desktop file generation (`main.py`)

`_generate_desktop_file(desktop_dir=None)`:
- `desktop_dir` defaults to `~/.local/share/applications/`; overridable for tests.
- Builds Exec line: `f"Exec={sys.executable} {Path(__file__).resolve()} %U"` — always correct for the active venv.
- If `ekplorer.desktop` exists and its `Exec=` line matches → skip (no-op, no filesystem write).
- Otherwise writes the file, then calls `subprocess.run(["update-desktop-database", ...], check=False)` (silently ignored if not installed).
- Called at startup before QApplication so it's always current before the single-instance check fires.

### Part D — "Set as default file manager" button (`views/dashboard_view.py`)

`_XDG_MIME = shutil.which("xdg-mime")` at module level — None if tool absent.

`_check_default_fm()` (called in `__init__`):
- Runs `xdg-mime query default inode/directory`; if output == `"ekplorer.desktop"`, hides `_default_fm_bar` immediately.
- Wrapped in `try/except` — safe if xdg-mime absent.

`_set_as_default_fm()` (button click):
- `xdg-mime default ekplorer.desktop inode/directory`
- `xdg-mime default ekplorer.desktop x-scheme-handler/file`
- Hides `_default_fm_bar`, shows toast `strings.NOTICE_SET_DEFAULT_FM_DONE`.

Layout: `_default_fm_bar` (QWidget with QHBoxLayout) sits between the scroll area and the toast bar in the outer QVBoxLayout — always visible without scrolling.

### Tests: 686/686 (+21 in `tests/test_single_instance.py`)
normalize_path_arg (6): strips file:// scheme; URL-decodes spaces; plain path unchanged; decodes without scheme; empty string; encoded slash.
_try_become_secondary (6): returns True when connected; sends path as UTF-8 line; sends empty string + newline; returns False when no server; closes socket on success; does not write when not connected.
_generate_desktop_file (9): exec contains sys.executable; exec contains main.py path; full exec line format; creates file when missing; not rewritten when exec unchanged (mtime stable); rewritten when exec changed; mime types present; StartupWMClass correct; creates nested directories.

## Clipboard tab (text history, local, persistent)

**Schema:** `CURRENT_VERSION` bumped to 6. `_V6_DDL` adds `clipboard_history(id INTEGER PK AUTOINCREMENT, content TEXT NOT NULL, captured_at TEXT NOT NULL, pinned INTEGER DEFAULT 0)`.

**New files:**
- `models/clipboard_entry.py` — `ClipboardEntry(id, content, captured_at, pinned)` dataclass.
- `backends/clipboard_backend.py` — `ClipboardBackend`: `add_entry`, `list_entries`, `delete_entry`, `toggle_pin`, `clear_unpinned`, `enforce_limit`, `max_entries` property (r/w, reads/writes settings key `clipboard.max_entries`, default 10, min 1).
- `views/clipboard_view.py` — `ClipboardView(QWidget)`.

**Capture guard (`_self_writing`):** Set True before any `clipboard.setText()` inside the tab, cleared in a `try/finally`. Prevents our own Copy button from adding a duplicate. File operations are also guarded: `cb.mimeData().hasUrls()` → skip. Consecutive duplicate detection: compares incoming text to `max(entries, key=lambda e: e.id).content`.

**Eviction:** `add_entry()` inserts first, then runs `DELETE ... LIMIT -1 OFFSET max_entries` targeting unpinned rows ordered by `id DESC` — pinned rows are never touched. `enforce_limit()` runs the same DELETE on demand (called when spinbox changes).

**List ordering:** `ORDER BY pinned DESC, id DESC` — pinned entries float to the top; within each group newest-first.

**`_EntryWidget`:** Two-row layout (pin button + content preview + timestamp / action buttons). Pin uses `QIcon.fromTheme("bookmark"/"bookmark-new")`. Copy button flashes "Copied!" for 1 second. Open in Editor: `NamedTemporaryFile(suffix=".txt", delete=False)` + `subprocess.Popen(["xdg-open", tmp])`. Delete: calls backend + reload.

**Tab:** 5th tab, `_chrome_icon("edit-paste", SP_FileIcon)`. `ClipboardTab` wrapper in `main.py`. `ClipboardView` connects to `QApplication.clipboard().dataChanged` in its `__init__` — this is additive alongside the FM's existing `_on_clipboard_changed` connection (both handlers coexist safely).

**FM clipboard not disrupted:** FM uses `setMimeData()` with `hasUrls()`-triggering MIME. The clipboard view's handler returns immediately on `hasUrls()`, leaving FM clipboard behavior untouched.

### Tests: 708/708 (+22 in `tests/test_clipboard_backend.py`)
Schema (2): clipboard_history table exists; CURRENT_VERSION == 6.
add_entry/list (4): round trip; newest-first within unpinned; respects max_entries limit; evicts oldest not newest.
Pinned survives eviction (2): pinned entries survive; pinned doesn't reduce unpinned capacity.
delete_entry (2): removes row; nonexistent is noop.
toggle_pin (3): false→true; true→false; double toggle restores original state.
clear_unpinned (3): removes all unpinned; leaves pinned intact; multiple pinned all survive.
max_entries setting (3): default 10; persists across instances; minimum clamped to 1.
list ordering (1): pinned appear before unpinned.
enforce_limit (2): trims to new max; preserves pinned.

## Configure dialog (centralised settings)

**Entry point:** `QPushButton` in the top-right corner of the tab bar via `QTabWidget.setCornerWidget()`. Icon: `_chrome_icon("configure", SP_FileDialogDetailedView)`. Tooltip: `strings.CONFIGURE_TOOLTIP`. Opens `ConfigureDialog(parent=self)` via `MainWindow._open_configure()`.

**Startup tab:** `_STARTUP_TAB_MAP` dict and `_startup_tab_index(repo)` function in `main.py`. Setting key: `app.startup_tab` (values: "dashboard", "file_manager", "packages", "terminal", "clipboard"). `MainWindow.__init__` calls `_startup_tab_index(SettingsRepository())` to select the initial tab instead of hardcoded 0.

**`ConfigureDialog`** (`views/configure_dialog.py`): fixed size 680×460. Left `QListWidget` (160px) + right `QStackedWidget`. Category switch via `currentRowChanged → setCurrentIndex`. OK calls `_on_ok()` → writes all settings → `accept()`. Cancel → `reject()` with no writes.

**5 pages:**
- **General**: startup tab `QComboBox` → `app.startup_tab`.
- **File Manager**: view mode combo (details/icons) → `fm.view_mode`; show hidden checkbox → `fm.show_hidden`; address bar mode combo (path/breadcrumb) → `fm.address_bar.mode`.
- **Clipboard**: max entries spinbox 1–100 → `clipboard.max_entries` (tooltip explains pinned immunity); Clear history button calls `ClipboardBackend.clear_unpinned()` after `QMessageBox.question` confirmation. Button disabled (with tooltip) if backend absent.
- **System**: `_query_default_fm()` method calls xdg-mime — mockable separately from subprocess. Status label + Set as Default button (disabled when already default). `_refresh_default_fm_status()` updates both after click.
- **About**: app title (bold, +4pt), version, license link (`openExternalLinks=True`), repo URL (hidden when `strings.APP_REPO_URL` is empty).

**`strings.py` additions:** `APP_REPO_URL = ""`, all `CONFIGURE_*` strings.

### Tests: 734/734 (+26 in `tests/test_configure_dialog.py`)
_startup_tab_index (7): all 5 tabs map correctly; unknown key defaults to 0; _STARTUP_TAB_KEYS covers all map entries.
Dialog reads settings (7): startup tab combo; fm show_hidden checkbox true/false; fm view mode icons; fm address bar breadcrumb; clipboard max entries; default 10 when missing.
OK writes / Cancel does not (7): startup tab; fm view mode; fm show_hidden; fm address bar; clipboard max entries; cancel doesn't write fm view; cancel doesn't write startup tab.
System page (5): label "is default"; label "not default"; set btn disabled when default; set btn enabled when not; not default when query returns None.

## Dashboard Advanced Mode

**Toggle:** Simple/Advanced `QPushButton` (checkable) in a `QButtonGroup` above the scroll area. `idToggled` writes `dashboard.view_mode` ("simple"/"advanced") to settings and calls `_reload()`. Mode persists across launches.

**`AdvancedDriveTile`** (`views/dashboard_view.py`): same header as `DriveTile` (name, badge, device/fs_type, used/free/total) plus a rescan button. Body is a `QStackedWidget`: page 0 = indeterminate `QProgressBar` + "Scanning…"; page 1 = `_SegmentedPieWidget` + legend. SMART section below. `showEvent` + `_scan_started` guard prevents double-start.

**`_SegmentedPieWidget`**: custom `QWidget`, 160×160. `paintEvent` draws pie slices via `drawPie`, then punches a 50% donut hole with `drawEllipse`. Centre shows used %. Unaccounted space shown as grey `_free` slice. Segments sorted largest-first, "Other" always last.

**Legend:** `QVBoxLayout` of rows per category (colored swatch + name + size). Built by `_build_legend()`, cleared and rebuilt on each scan result.

**`DiskScanBackend`** (`backends/disk_scan_backend.py`): `DISK_CATEGORIES` dict (9 categories with hex colors — data-viz constants, NOT theme.py). `_categorize(path, filename)`: extension check runs BEFORE MIME so `.py`/`.js` (MIME `text/x-python` etc.) aren't swallowed by the `text/*` Documents catch-all. Path prefix → extension → MIME → "Other". Skips `/proc` etc. under root. Progress callback every 500 files.

**`SmartBackend`** (`backends/smart_backend.py`): `SmartData` dataclass (health, power_on_hours, temperature_c, reallocated_sectors). `device_for_mount()` parses `/proc/mounts` (injectable via `mounts_path=` for tests), strips partition suffix with `_strip_partition()` (`nvme`/`mmcblk` → `p\d+$`, else `\d+$`). `get_data()` calls `smartctl -iHA`; returncode 0 or 4 = OK; returncode 1 + "Permission denied" in stderr → `SmartData(health="Permission denied")`; other non-zero → None.

**Configure dialog:** Dashboard page added at index 2 (Clipboard→3, System→4, About→5). Two `QRadioButton` (`_dash_simple_rb` / `_dash_advanced_rb`) in a `QButtonGroup`. Setting key: `dashboard.view_mode`.

### Tests: 786/786 (+52: +24 disk_scan, +23 smart, +5 configure_dialog dashboard page)

## BUG FIX: FileView context menu on right-click (post-Dashboard milestone)

**Root cause:** `contextMenuRequested` fires before Qt updates `selectedIndexes()` from the right-click, so `_get_selected_entries()` returned empty and the code fell through to the empty-area menu branch.

**Fix** (`views/file_view.py`, `_on_context_menu`): call `sender.indexAt(pos)` to get the item directly from mouse position. If valid and not already selected (`sel_model.isSelected(idx)` is False), force-select with `sel_model.select(idx, ClearAndSelect | Rows)` before calling `_get_selected_entries()`. Multi-selections where the right-clicked item is already selected are preserved unchanged. `QItemSelectionModel` added to imports.

### Tests: 786/786 (no change — fix is a pure event-ordering correction)

## Dashboard Advanced: three visual fixes

### Part 1 — System & OS color
`DISK_CATEGORIES["System & OS"]` changed from `#7F8C8D` (grey, indistinguishable from "Other") to `#1ABC9C` (teal/cyan). Change is in `backends/disk_scan_backend.py`.

### Part 2 — Free Space / Other separation
`_SegmentedPieWidget.set_data()` now takes four args: `category_bytes, other_bytes, free_bytes, total_bytes`. The old single-dict + total interface is gone.

`_on_scan_finished` computes the correct values from drive data (authoritative, not from scan totals):
- `free_bytes = drive.free_bytes` (from df — no scan needed)
- `other_bytes = max(0, used_bytes - sum(all scanned bytes))` — unscanned used space (permissions, metadata, filesystem overhead)
- Named categories are all scan output passed as-is

Pie renders: named categories (sorted largest-first) → "Other" (if > 0) → "Free Space" (always last, color `#2C3E50` very dark near-black). "Other" color stays `#566573`. Center % text derives from `total - free / total`.

Legend mirrors pie order. "Free Space" always last; "Other" shown only if > 0.

`DASHBOARD_FREE_SPACE = "Free Space"` added to `strings.py`.

### Part 3 — SMART permission detection
`SmartBackend.check_runnable()` added: runs `smartctl --version`, returns True only if returncode == 0. `_SmartWorker.run()` calls this after `is_available()` — if `--version` fails the tile shows "Install smartmontools…"; if it passes but `get_data()` returns None the tile shows the permissions message (via `SmartData(health="permission_denied")`).

`get_data()` permission detection widened: returncode in (1, 2) OR "Permission denied" in stderr/stdout → `SmartData(health="permission_denied")`. Other non-(0,4) returncodes → None. Health sentinel changed from `"Permission denied"` to `"permission_denied"` (lowercase, avoids accidental match against display strings).

`_on_smart_finished` checks `health == "permission_denied"` (was `"Permission denied"`).

### Tests: 791/791 (+5 smart: returncode-2→permission_denied, stderr-any-code→permission_denied, check_runnable ×3)

## BUG FIX (second pass): file context menu — Cause C confirmed, coordinate space

**Diagnosis:** Two compounding bugs were diagnosed via code analysis of Qt6 internals:

1. **Cause A (previously known):** `QAbstractItemView::mousePressEvent` returns immediately for `event->button() != Qt::LeftButton`, so a right-click never commits a selection. At the moment `customContextMenuRequested` fires, `selectedRows()` is always `[]`.

2. **Cause C (root cause of persistent failure):** `customContextMenuRequested(pos)` provides `pos` in **widget** coordinates, not viewport coordinates. This is because `QAbstractScrollArea::viewportEvent` converts the `QContextMenuEvent` from viewport→widget coordinates before forwarding it to `QAbstractItemView::contextMenuEvent`, which then emits the signal with `event->pos()` (widget coords). But `QAbstractItemView::indexAt(point)` expects **viewport** coordinates. For `QTreeView` the header bar (≈28 px) creates the gap: `indexAt(widget_pos)` looks 28 px below the actual click. For clicks near the bottom of a directory listing, `widget_y + 0` exceeds the last visible viewport row → `indexAt` returns **invalid** → `entries = []` → empty-area menu every time.

**First-pass fix failed because:** it force-selected via `indexAt(pos)` which still used the wrong (widget) coordinates. The force-select went to the wrong row (or was skipped entirely on invalid), so the symptom persisted.

**Fix** (`views/file_view.py`, `_on_context_menu`):
- Compute `viewport_pos = sender.viewport().mapFrom(sender, pos)` — converts widget coords → viewport coords.
- Use `idx = sender.indexAt(viewport_pos)` for both the empty-area branch decision and the force-select.
- Change `menu.exec(sender.viewport().mapToGlobal(pos))` → `menu.exec(sender.mapToGlobal(pos))` — `pos` is widget-relative, so `sender.mapToGlobal` is the correct conversion (the previous call was also offset by the header).

**Diagnostic predicted output** (right-clicking row 0 with 28 px header):
```
idx_widget valid=True row=1    # off by one — looked 28 px below cursor
idx_viewport valid=True row=0  # correct item
selectedRows=[]                # right-click never updates selection
```
For a click near the bottom: `idx_widget` would be **invalid** (past last row) → empty menu.

### Tests: 791/791 (no change in count — fix is a coordinate mapping correction)

## FINAL FIX PASS (4 parts)

### Part 1 — Context menu: DnD eventFilter pass-through (third pass)

**Root cause (confirmed):** The DnD milestone installed an `eventFilter` on both `_tree.viewport()` and `_list.viewport()` to intercept drag/scroll events. This filter was consuming `QEvent.Type.ContextMenu` before Qt could route it through `viewportEvent()` → `contextMenuEvent()` → `customContextMenuRequested`. Result: context menu never fired in the Advanced/Drag-ready code path.

**Fix — `eventFilter()` (`views/file_view.py`):**
```python
if event.type() == QEvent.Type.ContextMenu:
    return False  # never consume — let Qt route normally
```
Added at the very top of `eventFilter`, before all other checks.

**Fix — `_on_context_menu()` (`views/file_view.py`):**
`customContextMenuRequested(pos)` emits `pos` in **viewport** coordinates for `QAbstractScrollArea` subclasses. The previous two passes mapped to widget coords and then back; this pass removes all `mapFrom` calls:
- `idx = sender.indexAt(pos)` — direct viewport coords, correct.
- Added `entry = self._model.data(src, _ENTRY_ROLE)` validity check (guards against index with no backing entry).
- `menu.exec(sender.viewport().mapToGlobal(pos))` — viewport pos → global screen coords.

**Note:** Cause C (widget vs viewport coordinate mismatch, diagnosed in the second pass) was fixed in that pass via `viewport().mapFrom(sender, pos)`. This pass supersedes it: since the eventFilter now passes ContextMenu through, Qt routes the event via `QContextMenuEvent` with viewport coordinates natively — no `mapFrom` needed at all.

### Part 2 — SMART without elevation + Configure → System SMART Access section

**Problem:** When smartctl fails with a permissions error, the tile showed a static label with no actionable guidance. Users on standard desktop installs are not in the `disk` group and have no path forward.

**Dashboard fix (`views/dashboard_view.py`):**
`_on_smart_finished()` permission_denied branch now adds a "How to enable" flat `QPushButton` below the label. Clicking it calls `_show_smart_howto()` which opens a `QMessageBox.information` explaining `sudo usermod -a -G disk $USER` and pointing to Configure → System.

**Configure → System SMART Access section (`views/configure_dialog.py`):**
`_build_system_page()` extended with a new "SMART Drive Access" group below the default FM section:
- Description label (`CONFIGURE_SYS_SMART_LABEL`).
- Read-only command row with a "Copy command" button that calls `QApplication.clipboard().setText(strings.CONFIGURE_SYS_SMART_CMD)`.
- `self._smart_group_status` QLabel, populated by `_refresh_smart_group_status()`.
- `_refresh_smart_group_status()` checks `grp.getgrnam("disk").gr_mem` against `os.getlogin()`:
  - In group → green `✓` label (`color: #27ae60`).
  - Not in group → muted `✗` label (`color: palette(mid)`).
  - `KeyError`/`OSError` → treated as not in group.

**New strings (`strings.py`):**
`CONFIGURE_SYS_SMART_TITLE`, `CONFIGURE_SYS_SMART_LABEL`, `CONFIGURE_SYS_SMART_CMD`,
`CONFIGURE_SYS_SMART_COPY_CMD`, `CONFIGURE_SYS_SMART_IN_GROUP`, `CONFIGURE_SYS_SMART_NOT_IN_GROUP`,
`DASHBOARD_SMART_NO_PERM` (replaces previous inline string), `DASHBOARD_SMART_HOWTO_BTN`,
`DASHBOARD_SMART_HOWTO_TITLE`, `DASHBOARD_SMART_HOWTO_MSG`.

### Part 3 — Properties panel crash: GC-safe ref store (definitive fix)

**Root cause recap:** GC collecting a `QThread` wrapper while the thread is still running causes `SIGABRT`. The individual `_ow_thread` / `_cs_thread` / `_chmod_thread` attrs were set to `None` too early (by `_cancel_workers()` clearing them before `wait()` confirmed the thread had stopped), allowing GC to collect the Python wrapper while the C++ thread was still alive.

**Three-layer fix (`views/properties_panel.py`):**

Layer 1 — unified GC-safe ref store:
```python
self._workers: list[tuple[QThread, QObject]] = []
```
Every worker spawn (OW, CS, chmod) appends `(thread, worker)` to this list immediately after `moveToThread`.

Layer 2 — `_cancel_workers()` iterates the list:
```python
for thread, _worker in self._workers:
    thread.quit()
    thread.wait(200)   # 200ms — don't block UI, enough for subprocess
self._workers.clear()  # clear AFTER all wait() calls — GC cannot collect until here
```
Signal disconnection (try/except RuntimeError) runs BEFORE the loop so stale callbacks never fire during the overlap window. All `_*_thread` / `_*_worker` attrs set to `None` after `_workers.clear()`.

Layer 3 — generation counter (already implemented; wait increased from 100ms → 200ms to match subprocess characteristics of `_OpenWithLoader`).

**Note on `show_file()`:** The spec said to also call `_cancel_workers()` at the top of `show_file()`, but `populate_general()` starts workers and then calls `show_file()`. Adding cancel there would kill workers that were just started. Resolution: `_cancel_workers()` is called only at the top of `populate_general()` and `show_placeholder()`.

### Part 4 — Pie scan cross-mount fix + color palette

**Sub-part A — Root cause of inflated category totals:**

`os.walk()` naturally descends into ALL subdirectories including those on different filesystems (btrfs subvolumes, ZFS pools, bind mounts). A user with a 24 GB drive could see "Archives: 230 GB" because the walk descended into a large mounted volume nested inside the mount point.

**Fix (`backends/disk_scan_backend.py`):**
```python
root_dev = os.stat(mount_point).st_dev
# In os.walk topdown=True loop:
kept = []
for d in dirnames:
    try:
        if os.stat(os.path.join(dirpath, d)).st_dev == root_dev:
            kept.append(d)
    except OSError:
        pass
dirnames[:] = kept   # in-place mutation — os.walk respects this in topdown=True mode
```
`root_dev` is captured once before the walk. `OSError` on a subdir → silently skip it (broken symlinks, PermissionError).

**Sub-part B — Color palette:**
- `Archives`: `#16A085` → `#FF1493` (hot pink — visually distinct from Documents and System & OS)
- `Free Space` (both `_on_scan_finished` occurrences): `#2C3E50` → `#1C2833` (very dark near-black — communicates "empty" visually)

### Tests: 798/798 (+7 new)

New tests:
- `tests/test_m10c_file_view.py`: `test_event_filter_passes_context_menu_events` (eventFilter returns False for ContextMenu); `test_event_filter_consumes_ctrl_scroll` (returns True for Ctrl+Wheel).
- `tests/test_disk_scan_backend.py`: `test_scan_prunes_dirs_on_different_device` (foreign dir with `st_dev = root_dev + 999` yields 0 Videos, only local .py counted); fixed `test_scan_skips_proc_under_root` (added `st_dev = 1` to fake_stat's `S` class — needed by new `root_dev = os.stat(mount_point).st_dev` call).
- `tests/test_properties_panel_crash_fix.py`: `test_cancel_workers_calls_quit_on_running_thread` updated (now appends to `_workers` list, `wait(200)`); `test_cancel_workers_clears_workers_list`; `test_workers_list_populated_after_populate`; `test_generation_counter_discards_stale_chmod_result`.

---

---

## QThread teardown — shared pattern (applied everywhere)

```
if thread is not None:
    try:
        if thread.isRunning():
            thread.quit()
            if not thread.wait(3000):
                thread.terminate()
                thread.wait()
    except RuntimeError:
        pass   # C++ object already gone
```
Always connect BOTH `thread.finished → worker.deleteLater` AND
`thread.finished → thread.deleteLater`. Keep a Python ref until `wait()` returns.

### Fix 1 — Wastebin random crash (file_manager_view.py `_start_trash_op`)
**Root cause:** Old `_trash_thread` was `quit()`-ed without `wait()` and
reassigned immediately, orphaning a possibly-running C++ thread. Also
`thread.deleteLater` was never connected, so the C++ thread object leaked.
**Fix:** Added `_drain_trash_thread()` using the shared pattern. Added
`thread.finished → thread.deleteLater`. Added `closeEvent` on `FileManagerView`
that drains both `_trash_thread` and `_trash_list_thread`.

### Wastebin failed on unreadable per-mount trash dirs (trash_backend.py)
**Root cause:** `_mount_points()` included snapd/runtime mounts like `/run/snapd/ns/snapd-desktop-integration.mnt`. `list_trash()` then tried to stat `.Trash-1000/info` on those paths, hit `PermissionError`, and aborted the entire listing — the user's real `~/.local/share/Trash` was never read.

**Three-layer fix:**
1. `_mount_points()` now skips any mount whose path starts with `/run`, `/proc`, `/sys`, `/dev`, `/snap`, `/var/lib/snapd`, `/var/lib/docker`, or contains `/snapd/ns/` or `/.mnt`. These paths never hold user trash.
2. `_all_info_dirs()` wraps each per-mount `td.exists()` check in `try/except (PermissionError, OSError)` — a single bad mount can't abort the loop.
3. `list_trash()` wraps each `info_dir` iteration in its own `try/except (PermissionError, OSError)` — one unreadable directory is skipped, not fatal. Main `~/.local/share/Trash` is always first in the list and therefore always read.

**Side effect:** The path-prefix filter eliminated the `/run/snapd/...` check that was causing 5 pre-existing test failures — all 829 tests now pass.

---

### Wastebin error path left "Loading…" stuck (file_manager_view.py + trash_view.py)
**Root cause:** `_TrashListWorker.failed` was connected only to `thread.quit`. No UI slot cleared the loading state, so any exception in `list_trash()` left TrashView permanently stuck showing "Loading…".
**Fix:** Added `_on_trash_list_failed(msg)` slot that clears thread/worker refs and calls `trash_view.show_error(msg)`. Connected `failed → _on_trash_list_failed` (alongside the existing `failed → thread.quit`). Added `TrashView.show_error(str)` that replaces the spinner with "Couldn't read the Wastebin: \<msg\>".

---

### Wastebin infinite "Loading…" — diagnosed and fixed

**Diagnosis:**
- `_load_trash` was already async (routed through `_TrashListWorker`). The threading was correct.
- **Primary hang:** `_entry_size()` in `trash_backend.py` called `path.rglob("*")` to recursively stat every file in every trashed directory. Called per entry inside the worker — on a ZFS pool with large trashed directories this takes minutes to hours, keeping "Loading…" forever.
- **Secondary:** `load([])` left a blank tree instead of "Wastebin is empty". Two synchronous `list_trash()` calls survived on the UI thread in `_on_wastebin_action` and `_confirm_and_empty_trash`.

**Fixes:**
- `_entry_size()` now returns `-1` for directories (no rglob). Files keep `stat().st_size`.
- `TrashEntry.size == -1` renders as "—" in TrashView. `load([])` shows "Wastebin is empty" placeholder.
- `_on_wastebin_action("restore_all")` and `_confirm_and_empty_trash` now use `self._trash_view.all_entries()` (cached from last load) instead of calling `list_trash()` synchronously.

---

### Fix 2 — Wastebin click freeze (file_manager_view.py `_load_trash`)
**Root cause:** `list_trash()` ran synchronously on the UI thread — on large/slow
trash directories this stalled the compositor enough to kill the app.
**Fix:** Added `_TrashListWorker` in `backends/trash_backend.py`. `_load_trash()`
now starts a thread, shows a "Loading…" state in `TrashView`, and delivers entries
via `_on_trash_list_ready()`. Re-entrancy guard prevents double-starts.

### Fix 3 — Simple-during-scan crash (dashboard_view.py `_reload` + AdvancedDriveTile)
**Root cause:** `_reload()` called `tile.setParent(None)` while `_scan_thread` was
still walking the filesystem → orphaned running QThread → SIGABRT.
**Fix:** Added cooperative `_cancelled` flag + `cancel_check` parameter to
`DiskScanBackend.scan()` and `DiskScanWorker` (checks per directory in os.walk).
Added `cancel_scan()` to `AdvancedDriveTile` that cancels the worker and drains
both `_scan_thread` and `_smart_thread` via the shared pattern. `_reload()` and
`_apply_diff()` now call `cancel_scan()` before `setParent(None)`. Added
`thread.deleteLater` connections that were missing from `_start_scan()`/`_start_smart()`.

### Fix 4 — Properties crash on navigation (properties_panel.py + file_manager_view.py)
**Root cause:** `_cancel_workers()` was only called from `populate_general()` and
`show_placeholder()`, not when the FM tore down or replaced the right pane.
Properties workers survived pane switches and got orphaned.
**Fix:** Added `PropertiesPanel.shutdown()` (public wrapper around `_cancel_workers()`).
Called on: entering trash mode (`_enter_trash_mode`), switching away from Properties
(`_on_panel_selected`), disabling dual pane (`_on_dual_pane_toggled`), and on
`FileManagerView.closeEvent`.

### Fix 5 — Terminal copy/paste (terminal_view.py)
**Root cause:** No copy/paste bindings existed; no context menu. Ctrl+C correctly
sends \\x03 (SIGINT) and must not be remapped.
**Fix:** In `keyPressEvent`, Ctrl+Shift+C copies selection to clipboard; Ctrl+Shift+V
pastes clipboard text to the PTY. Both are checked BEFORE the Ctrl+letter → \\x03
block so Ctrl+C is unaffected. Added right-click context menu (Copy, Paste, Select All,
Clear) with copy/paste enabled only when there is a selection / clipboard content.

---

## Surgical fix pass — root causes documented

### Fix 1 — Context menu empty on files (views/file_view.py)
**Root cause:** `QTreeView` defaults to `SelectItems`, so right-click selects a single
cell. `_get_selected_entries()` calls `selectedRows()`, which returns nothing when only
a cell is selected → menu falls through to the empty-area branch.
**Fix:** `setSelectionBehavior(SelectRows)` added immediately after `setSelectionMode`.
`_on_context_menu` selection guard switched from `isSelected(idx)` (cell-level) to
comparing source-model row indexes via `selectedRows()` so any column click works.

### Fix 2 — Properties crash on rapid file clicks (views/properties_panel.py)
**Root cause A:** `deleteLater` fires when a worker thread finishes normally, destroying
the C++ `QThread` object, but the tuple stays in `self._workers`. The next call to
`_cancel_workers` calls `thread.quit()` on a dead object → `RuntimeError` → crash.
**Root cause B:** `thread.wait(200)` is too short for `_OpenWithLoader` which shells out
to `xdg-mime/gio`. Wait times out, `_workers.clear()` drops the last reference, GC
destroys a still-running C++ QThread → SIGABRT.
**Fix:** `_cancel_workers` now checks `thread.isRunning()` under a `RuntimeError` guard,
uses `wait(3000)` with a `terminate()+wait()` fallback. Redundant pre-quit blocks in
`_on_chmod_clicked` and `_on_compute_checksums` removed (double-quit on possibly-dead objects).

### Fix 3 — SMART permission guidance (strings.py, views/configure_dialog.py)
**Root cause:** Dashboard showed a bare message with a how-to popup; Configure → System
already has the SMART disk-group UI but was never pointed to from the dashboard.
Also, `os.getlogin()` in `_refresh_smart_group_status` can raise `OSError` in
non-terminal environments.
**Fix:** `DASHBOARD_SMART_NO_PERM` string updated to direct users to Configure → System.
`os.getlogin()` replaced with `getpass.getuser()` (safe in all launch contexts).

### Fix 4 — Pie "only Archives" on near-empty drives (views/dashboard_view.py)
**Root cause:** On near-empty multi-TB drives (~88% free), the free wedge is painted in
`#1C2833` which is near-invisible on dark themes, making tiny category segments look like
"only one color". Segments are mathematically present but visually swamped by the free wedge.
**Fix:** Added "Total | Used" toggle (persisted as `dashboard.pie_basis`; default "used").
In "used" mode `_SegmentedPieWidget` divides by `total - free` and omits the free wedge
entirely — category proportions fill the full ring. In "total" mode free-space color
changed from `#1C2833` to `DISK_FREE_COLOR = "#34495E"` (visible slate).
`DISK_FREE_COLOR` defined in `disk_scan_backend.py` as the single source of truth.
