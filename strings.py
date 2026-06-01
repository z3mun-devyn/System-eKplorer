# Centralised terminology layer (spec §4).
# All user-facing strings live here so Linux idioms can be revised globally.
# Also home to shared color utilities used across views.

APP_TITLE = "System eKploiter"
APP_VERSION = "0.1-alpha"

# Tab bar
TAB_DASHBOARD = "Dashboard"
TAB_FILE_MANAGER = "File Manager"
TAB_FILE_MANAGER_TOOLTIP = "Coming soon"
TAB_PACKAGES = "Packages"

# §4 terminology translations: Linux term → eKploiter UI
TERM_PACKAGE = "App"                           # "Package" sounds like cardboard box
TERM_PACKAGES_PLURAL = "Apps"
TERM_REPOSITORY = "Source"                     # Plain English
TERM_MOUNT_POINT = "Drive location"            # Cognitive load with no payoff
TERM_DEPENDENCY = "Required by"               # Already English
TERM_DEPENDENCY_OF = "Depends on"
TERM_PURGE = "Uninstall completely (including settings)"
TERM_SNAPSHOT = "Restore point"               # Direct Windows analogue
TERM_DAEMON = "Background service"            # Less jargon-y
TERM_SUDO = "Password prompt"                 # User should not need to know mechanism
TERM_DISTRO = "Linux version"                 # Term exposed only when relevant

# Source labels (shown on package rows, not explained)
SOURCE_APT = "apt"
SOURCE_FLATPAK = "Flatpak"
SOURCE_SNAP = "Snap"
SOURCE_APPIMAGE = "AppImage"
SOURCE_STEAM = "Steam"
SOURCE_WINE = "Wine"
SOURCE_GOG = "GOG"

# Source column labels — short, shown in the Source column
SOURCE_APT_LABEL      = "APT"
SOURCE_FLATPAK_LABEL  = "Flatpak"

# Flatpak sidebar hint
FLATPAK_NOT_DETECTED = "Flatpak not detected"

# Status / health
STATUS_ONLINE = "Online"
STATUS_DEGRADED = "Warning"
STATUS_FAULTED = "Error"

# Drive states
DRIVE_EMPTY = "Empty — ready for use"
DRIVE_MOUNT = "Mount"

# Action labels
ACTION_OPEN = "Open"
ACTION_OPEN_FILE_LOCATION = "Open file location"
ACTION_OPEN_INSTALL_LOCATION = "Open install location"
NOTICE_LOCATION_NOT_FOUND   = "Couldn't locate an install directory for {name}"
ACTION_CHECK_UPDATES = "Check for updates"
ACTION_ASSIGN_TAGS = "Assign tags…"
ACTION_MIGRATE_DRIVE = "Migrate to different drive"
ACTION_REINSTALL = "Reinstall"
ACTION_REINSTALL_RESET = "Reinstall (Reset Settings)"
ACTION_UNINSTALL = "Uninstall"
ACTION_UNINSTALL_KEEP = "Uninstall (Keep Settings)"
ACTION_RENAME_LABEL = "Rename label…"
ACTION_CLEANUP = "Cleanup"
ACTION_PROPERTIES = "Properties"
ACTION_EJECT = "Eject"
ACTION_SCRUB_NOW = "Scrub now"

# Updates banner
UPDATES_BANNER = "{total} updates available · {breakdown}"
UPDATES_REVIEW = "Review"

# Label modal
LABEL_MODAL_TITLE = "Label drive: {name}"
LABEL_MODAL_FIELD = "Label"
LABEL_MODAL_COLOR = "Color"
STUB_COMING_M3 = "Coming in M3"

# Dashboard sections
SECTION_ACTIVE = "Physical Devices"
SECTION_INACTIVE = "Connected — not active"

# Unmounted drive actions
ACTION_CLICK_TO_MOUNT = "Click to mount"
ACTION_CLICK_TO_UNLOCK = "Click to unlock"

# Notifications
NOTICE_BITLOCKER_MISSING = "BitLocker support requires the dislocker package"
NOTICE_MOUNT_SUCCESS = "Mounted {device}"
ERR_MOUNT_FAILED = "Could not mount {device}: {error}"
ERR_UNLOCK_FAILED = "Could not unlock {device}: {error}"

# Placeholder text for stub views
PLACEHOLDER_FILES = "Files — coming in Milestone 1"
PLACEHOLDER_PACKAGES = "Packages — coming in Milestone 3"

# Error / warning messages
ERR_BACKEND_UNAVAILABLE = "{backend} is not available on this system."
ERR_PARSE_FAILURE = "Could not read {source} data. The view may be incomplete."
ERR_TIMEOUT = "{command} took too long to respond and was cancelled."

# Session recovery
NOTICE_RECOVERED = "Recovered from previous session"

# Confirmation dialogs — per-action question + subtitle
CONFIRM_ACTION_TITLE             = "{action} {name}?"
CONFIRM_REINSTALL_QUESTION       = "Are you sure you want to reinstall {name}?"
CONFIRM_REINSTALL_SUBTITLE       = "The package will be re-downloaded and installed. Your settings will be kept."
CONFIRM_REINSTALL_RESET_QUESTION = "Are you sure you want to reset and reinstall {name}?"
CONFIRM_REINSTALL_RESET_SUBTITLE = "The package will be fully removed then reinstalled fresh. All settings will be reset."
CONFIRM_UNINSTALL_QUESTION       = "Are you sure you want to uninstall {name}?"
CONFIRM_UNINSTALL_SUBTITLE_PURGE = "This will also remove all settings and configuration files."
CONFIRM_UNINSTALL_SUBTITLE_KEEP  = "Settings and configuration files will be kept."

# Multi-select menu labels (n > 1)
ACTION_REINSTALL_N       = "Reinstall {n} apps"
ACTION_REINSTALL_RESET_N = "Reinstall (Reset Settings) {n} apps"
ACTION_UNINSTALL_N       = "Uninstall {n} apps"
ACTION_UNINSTALL_KEEP_N  = "Uninstall (Keep Settings) {n} apps"
ACTION_ASSIGN_TAGS_N     = "Assign tags to {n} apps…"

# Batch confirmation / status
CONFIRM_BATCH_QUESTION   = "Are you sure you want to {action} {n} apps?"
STATUS_BATCH_WORKING     = "{action} in progress… ({n} apps)"
NOTICE_BATCH_COMPLETE    = "{action} complete: {n} apps"

# Package action status / errors
STATUS_WORKING         = "Working…"
NOTICE_ACTION_COMPLETE = "{action} complete: {name}"
NOTICE_ACTION_CANCELLED = "Cancelled"
ERR_ACTION_TITLE       = "Action Failed"
ERR_ACTION_FAILED      = "Could not complete this action on {name}."

# Packages view
PACKAGES_LOADING = "Loading apps…"
PACKAGES_EMPTY = "No apps found."
PACKAGES_COUNT = "{n} apps installed"

# Package section → Windows-friendly category name
PACKAGE_CATEGORIES: dict[str, str] = {
    "admin":         "System Tools",
    "comm":          "Internet",
    "database":      "Development",
    "debug":         "Development",
    "devel":         "Development",
    "doc":           "Documentation",
    "editors":       "Text Editors",
    "education":     "Education",
    "electronics":   "Science",
    "embedded":      "Development",
    "fonts":         "Fonts",
    "games":         "Games",
    "gnome":         "Desktop",
    "golang":        "Development",
    "graphics":      "Photos & Graphics",
    "hamradio":      "Science",
    "haskell":       "Development",
    "httpd":         "Internet",
    "image":         "Photos & Graphics",
    "interpreters":  "Development",
    "introspection": "System Libraries",
    "java":          "Development",
    "javascript":    "Development",
    "kde":           "Desktop",
    "kernel":        "System Tools",
    "lang":          "Development",
    "libdevel":      "Development",
    "libs":          "System Libraries",
    "lisp":          "Development",
    "localization":  "Language",
    "mail":          "Email & Messaging",
    "math":          "Science",
    "misc":          "Other",
    "multimedia":    "Audio & Video",
    "net":           "Internet",
    "news":          "Email & Messaging",
    "ocaml":         "Development",
    "office":        "Office",
    "oldlibs":       "System Libraries",
    "otherosfs":     "System Tools",
    "perl":          "Development",
    "php":           "Development",
    "python":        "Development",
    "python3":       "Development",
    "ruby":          "Development",
    "science":       "Science",
    "security":      "Security",
    "shells":        "System Tools",
    "sound":         "Audio & Video",
    "tex":           "Office",
    "text":          "Text Editors",
    "utils":         "System Tools",
    "vcs":           "Development",
    "video":         "Audio & Video",
    "web":           "Internet",
    "x11":           "Desktop",
    "xfce":          "Desktop",
    "zope":          "Development",
    # Freedesktop categories (used by Flatpak / AppStream)
    "audiovideo":    "Audio & Video",
    "audio":         "Audio & Video",
    "video":         "Audio & Video",
    "development":   "Development",
    "education":     "Education",
    "game":          "Games",
    "graphics":      "Photos & Graphics",
    "network":       "Internet",
    "office":        "Office",
    "settings":      "System Tools",
    "system":        "System Tools",
    "utility":       "System Tools",
    "accessibility": "System Tools",
}

PACKAGE_CATEGORY_DEFAULT = "Other"


def package_category(section: str) -> str:
    """Map a dpkg section string to a Windows-friendly category name."""
    return PACKAGE_CATEGORIES.get(section or "", PACKAGE_CATEGORY_DEFAULT)


# ── Shared color utilities ────────────────────────────────────────────────────

# 5×2 swatch palette — used for drive labels and tag colors
TAG_PALETTE: list[str] = [
    "#e74c3c", "#e67e22", "#f1c40f", "#2ecc71", "#1abc9c",
    "#3498db", "#9b59b6", "#e91e63", "#795548", "#607d8b",
]
TAG_PALETTE_COLS = 5


def contrast_color(hex_color: str) -> str:
    """Return #000000 or #ffffff for best contrast against hex_color."""
    r = int(hex_color[1:3], 16) / 255
    g = int(hex_color[3:5], 16) / 255
    b = int(hex_color[5:7], 16) / 255

    def _lin(c: float) -> float:
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    lum = 0.2126 * _lin(r) + 0.7152 * _lin(g) + 0.0722 * _lin(b)
    return "#000000" if lum > 0.179 else "#ffffff"


# ── Tag editor modal ─────────────────────────────────────────────────────────

TAG_EDITOR_TITLE           = "Tags for {name}"
TAG_BATCH_TITLE            = "Tags for {n} apps"
TAG_EDITOR_SUBTITLE        = "Apply existing tags or create a new one"
TAG_EDITOR_ASSIGN_HEADER   = "ASSIGN EXISTING"
TAG_EDITOR_NO_TAGS         = "No tags yet — create one below"
TAG_EDITOR_CREATE_HEADER   = "OR CREATE NEW"
TAG_EDITOR_NAME_PLACEHOLDER = "Tag name"
TAG_EDITOR_SAVE_BTN        = "Assign tag"
TAG_EDITOR_CANCEL_BTN      = "Cancel"

# Legacy aliases — used by views/tag_modal.py until it is removed in M4
TAG_MODAL_TITLE            = TAG_EDITOR_TITLE
TAG_MODAL_SUBTITLE         = TAG_EDITOR_SUBTITLE
TAG_MODAL_EXISTING_HEADER  = TAG_EDITOR_ASSIGN_HEADER
TAG_MODAL_NO_TAGS          = TAG_EDITOR_NO_TAGS
TAG_MODAL_CREATE_HEADER    = TAG_EDITOR_CREATE_HEADER
TAG_MODAL_NAME_PLACEHOLDER = TAG_EDITOR_NAME_PLACEHOLDER
TAG_MODAL_SAVE_BTN         = TAG_EDITOR_SAVE_BTN
TAG_MODAL_CANCEL_BTN       = TAG_EDITOR_CANCEL_BTN
TAG_MODAL_CREATE_BTN       = "Create & assign"

# ── Packages table column headers ────────────────────────────────────────────

COL_ICON     = ""       # icon column — blank header
COL_NAME     = "Name"
COL_TAGS     = "Tags"
COL_CATEGORY = "Category"
COL_SOURCE   = "Source"
COL_VERSION  = "Version"
COL_SIZE     = "Size"
COL_INSTALLED       = "Installed On"
COL_ICON_MENU_LABEL = "Icon"   # visibility menu label (header for icon col is blank)

# ── Search bar ────────────────────────────────────────────────────────────────

SEARCH_PLACEHOLDER   = "Search apps…"
SEARCH_FILTER_TOOLTIP = "Field filter"

# Dropdown menu item labels (capitalized, shown in UI)
SEARCH_FIELD_TAGGED   = "Tagged"
SEARCH_FIELD_CATEGORY = "Category"
SEARCH_FIELD_SOURCE   = "Source"
SEARCH_FIELD_VERSION  = "Version"
SEARCH_FIELD_SIZE     = "Size"

# Query parser modifier tokens (lowercase, what user types before ":")
QUERY_TOKEN_TAGGED   = "tagged"
QUERY_TOKEN_CATEGORY = "category"
QUERY_TOKEN_SOURCE   = "source"
QUERY_TOKEN_VERSION  = "version"
QUERY_TOKEN_SIZE     = "size"

# ── Category → bundled icon file key ─────────────────────────────────────────
# Keys are lowercase-hyphenated filenames under assets/category-icons/.
# Unknown or unmapped categories fall back to "unknown".

CATEGORY_ICON_KEYS: dict[str, str] = {
    "Audio & Video":      "multimedia",
    "Desktop":            "system-utilities",
    "Development":        "development",
    "Documentation":      "system-utilities",
    "Education":          "education",
    "Email & Messaging":  "internet-communications",
    "Fonts":              "themes-fonts",
    "Games":              "games",
    "Internet":           "internet-communications",
    "Language":           "themes-fonts",
    "Office":             "productivity",
    "Other":              "unknown",
    "Photos & Graphics":  "graphics",
    "Science":            "science-math",
    "Security":           "system-utilities",
    "System Libraries":   "system-utilities",
    "System Tools":       "system-utilities",
    "Text Editors":       "productivity",
}

# ── Sidebar ───────────────────────────────────────────────────────────────────

SIDEBAR_CATEGORIES = "CATEGORIES"
SIDEBAR_TAGS = "TAGS"
SIDEBAR_ALL = "All"
SIDEBAR_NEW_TAG = "+ New tag"

# Tag deletion
ACTION_DELETE_TAG         = "Delete tag…"
TAG_DELETE_CONFIRM_TITLE  = 'Delete tag "{name}"?'
TAG_DELETE_CONFIRM_BODY   = "This will remove the tag from {n} app(s). The apps themselves will not be affected."
TAG_DELETE_YES            = "Delete"
TAG_DELETE_NO             = "Cancel"

# ── M8: Action log expander ───────────────────────────────────────────────────
ACTION_LOG_SHOW  = "Show details"
ACTION_LOG_HIDE  = "Hide details"

# ── M8: Update actions ────────────────────────────────────────────────────────
ACTION_UPDATE             = "Update"
ACTION_UPDATE_ALL         = "Update all"
UPDATES_CHECKING          = "Checking for updates…"
UPDATES_AVAILABLE_N       = "{n} update(s) available"
UPDATES_NONE              = "Everything is up to date"
CONFIRM_UPDATE_QUESTION   = "Are you sure you want to update {name}?"
CONFIRM_UPDATE_SUBTITLE   = "This will upgrade the app to the latest available version."
CONFIRM_UPDATE_ALL_QUESTION = "Are you sure you want to update {n} app(s)?"
CONFIRM_UPDATE_ALL_SUBTITLE = "All selected apps will be updated to their latest versions."

# ── M9: Version history ───────────────────────────────────────────────────────
ACTION_VERSION_HISTORY        = "Version history…"
VERSION_HISTORY_TITLE         = "Version history: {name}"
VERSION_HISTORY_SUBTITLE      = "Select a version of {name} to install."
VERSION_HISTORY_LOADING       = "Loading version history…"
VERSION_HISTORY_INSTALL       = "Install this version"
VERSION_HISTORY_CLOSE         = "Close"
VERSION_HISTORY_HOLD          = "Prevent automatic updates (hold/pin)"
VERSION_HISTORY_CURRENT       = "(current)"
VERSION_HISTORY_COLOR_OK      = "#27ae60"   # green — installable
VERSION_HISTORY_COLOR_GREY    = "#808080"   # grey  — historical only
VERSION_HISTORY_LOAD_FAILED   = "Could not load version history: {error}"

# ── M9: Terminal tab ──────────────────────────────────────────────────────────
TAB_TERMINAL                  = "Terminal"

# ── M10a: NavigationSidebar ───────────────────────────────────────────────────
NAV_SECTION_QUICK_ACCESS   = "Quick Access"
NAV_SECTION_DRIVES         = "Drives"
NAV_SECTION_NETWORK        = "Network"
NAV_SUBSECTION_RECENT_FILES = "Recent Files"
NAV_SUBSECTION_RECENT_LOCS  = "Recent Locations"

NAV_HOME       = "Home"
NAV_DESKTOP    = "Desktop"
NAV_DOCUMENTS  = "Documents"
NAV_DOWNLOADS  = "Downloads"
NAV_PICTURES   = "Pictures"
NAV_VIDEOS     = "Videos"
NAV_MUSIC      = "Music"

NAV_SYSTEM_DRIVE   = "System (/)"
NAV_UNMOUNTED      = "(unmounted)"
# Orange for unmounted drives — semantic status colour, follows VERSION_HISTORY_COLOR_* precedent
NAV_UNMOUNTED_COLOR = "#e67e22"

NAV_WASTEBIN        = "Wastebin"

# Sentinel "path" used to detect Wastebin navigation (not a real filesystem path)
TRASH_SENTINEL = "trash:///"

# ── M10d.1: Trash / Wastebin ─────────────────────────────────────────────────

TRASH_ADDRESS_LABEL   = "Wastebin"

TRASH_COL_NAME        = "Name"
TRASH_COL_ORIGINAL    = "Original Location"
TRASH_COL_DATE        = "Deletion Date"
TRASH_COL_SIZE        = "Size"

TRASH_CTX_RESTORE     = "Restore"
TRASH_CTX_DELETE      = "Delete Permanently"

TRASH_WB_RESTORE_ALL  = "Restore All Files"
TRASH_WB_EMPTY        = "Empty Wastebin"
TRASH_WB_SHRED        = "Shred Delete…"
TRASH_SHRED_TOOLTIP   = "Coming in a future security update"

TRASH_EMPTY_TITLE     = "Empty Wastebin"
TRASH_EMPTY_MSG       = "Permanently delete all {n} item(s) in the Wastebin? This cannot be undone."
TRASH_EMPTY_YES       = "Empty Wastebin"
TRASH_EMPTY_NO        = "Cancel"

TRASH_DELETE_TITLE    = "Delete Permanently?"
TRASH_DELETE_ONE      = "Permanently delete \"{name}\" from the Wastebin?"
TRASH_DELETE_MANY     = "Permanently delete {n} items from the Wastebin?"
TRASH_DELETE_YES      = "Delete"
TRASH_DELETE_NO       = "Cancel"

TRASH_RESTORE_TITLE   = "Restore"
TRASH_OP_RESTORING    = "Restoring…"
TRASH_OP_EMPTYING     = "Emptying Wastebin…"
TRASH_OP_DELETING     = "Deleting permanently…"

# ── M10b: Dual pane + Properties panel ───────────────────────────────────────
FM_DUAL_PANE_TOGGLE    = "Dual Pane"
FM_DUAL_PANE_TOOLTIP   = "Toggle dual-pane view"

FM_RIGHT_PANE_BROWSER    = "File Browser"
FM_RIGHT_PANE_PROPERTIES = "Properties"
FM_RIGHT_PANE_TERMINAL   = "Terminal"

FM_SETTING_DUAL_PANE   = "fm.dual_pane.enabled"
FM_SETTING_RIGHT_PANEL = "fm.dual_pane.right_panel"

PROP_NO_SELECTION  = "Select a file to view properties"
PROP_TAB_GENERAL     = "General"
PROP_TAB_PERMISSIONS = "Permissions"
PROP_TAB_CHECKSUMS   = "Checksums"
PROP_TAB_DETAILS     = "Details"
PROP_TAB_OPEN_WITH   = "Open With"

PROP_GENERAL_NAME     = "Name"
PROP_GENERAL_TYPE     = "Type"
PROP_GENERAL_SIZE     = "Size"
PROP_GENERAL_LOCATION = "Location"
PROP_GENERAL_MODIFIED = "Modified"
PROP_GENERAL_ACCESSED = "Accessed"
PROP_GENERAL_CREATED  = "Created"

# ── M10c: File view ───────────────────────────────────────────────────────────
# Column headers — Icon(blank) | Name | Tags | Category | Date Modified | Size
FM_COL_ICON          = ""
FM_COL_NAME          = "Name"
FM_COL_TAGS          = "Tags"
FM_COL_CATEGORY      = "Category"
FM_COL_DATE_MODIFIED = "Date Modified"
FM_COL_SIZE          = "Size"

FM_SIZE_ITEMS_ONE    = "1 item"
FM_SIZE_ITEMS_MANY   = "{n} items"

FM_TOOLBAR_BACK              = "←"
FM_TOOLBAR_FORWARD           = "→"
FM_TOOLBAR_UP                = "↑"
FM_TOOLBAR_SEARCH_HINT       = "Search…"

# Address bar
FM_SETTING_ADDRESS_BAR_MODE  = "fm.address_bar.mode"   # "path" | "breadcrumb"
FM_ADDRESS_TOGGLE_ICON        = "/"
FM_ADDRESS_TOGGLE_TOOLTIP     = "Toggle path / breadcrumb mode"

# View mode slider stop icons (shown below slider track)
FM_VIEWSLIDER_ICONS = ("≡", "⊞", "⊡", "◻")

FM_SETTING_VIEW_MODE     = "fm.view_mode"
FM_SETTING_SHOW_HIDDEN   = "fm.show_hidden"
FM_SETTING_ALT_ROWS      = "fm.alternating_rows"
FM_SETTING_SIDEBAR_WIDTH = "fm.sidebar.width"

# Status bar — {name} = drive label or mount point; {free}/{total} = sizes
FM_STATUS_FREE             = "{name}: {free} free of {total}"
FM_STATUS_SELECTED_ONE     = "1 item selected,  {size}"
FM_STATUS_SELECTED_MANY    = "{count} items selected,  {size}"
FM_STATUS_HOVER_MIME       = "{mime}"

FM_LEFT_PANE_PLACEHOLDER    = "File listing coming in M10c"
FM_RIGHT_BROWSER_PLACEHOLDER = "File Browser — coming in M10c"

# ── M10d: File operations ─────────────────────────────────────────────────────

# Context menu actions
FM_CTX_OPEN          = "Open"
FM_CTX_OPEN_WITH     = "Open With…"
FM_CTX_OPEN_ADMIN    = "Open as Administrator"
FM_CTX_OPEN_ADMIN_NA = "Open as Administrator (no supported file manager found)"
FM_CTX_CUT           = "Cut"
FM_CTX_COPY          = "Copy"
FM_CTX_COPY_PATH     = "Copy Path"
FM_CTX_COPY_NAME     = "Copy Name"
FM_CTX_PASTE         = "Paste"
FM_CTX_RENAME        = "Rename"
FM_CTX_TRASH         = "Move to Trash"
FM_CTX_DELETE        = "Delete Permanently"
FM_CTX_NEW_FOLDER    = "Create New Folder"
FM_CTX_NEW_FILE      = "Create New File"
FM_CTX_ASSIGN_TAGS   = "Assign Tags…"

# Rename / create dialogs
FM_RENAME_TITLE      = "Rename"
FM_RENAME_LABEL      = "New name:"
FM_NEW_FOLDER_TITLE  = "New Folder"
FM_NEW_FOLDER_LABEL  = "Folder name:"
FM_NEW_FILE_TITLE    = "New File"
FM_NEW_FILE_LABEL    = "File name:"

# Delete confirmation
FM_DELETE_TITLE      = "Delete Permanently?"
FM_DELETE_ONE        = "Permanently delete \"{name}\"?"
FM_DELETE_MANY       = "Permanently delete {n} items?"
FM_DELETE_WARNING    = "This action cannot be undone."
FM_DELETE_YES        = "Delete"
FM_DELETE_NO         = "Cancel"

# Conflict resolution dialog
FM_CONFLICT_TITLE    = "Name Conflict"
FM_CONFLICT_MSG      = "{n} item(s) already exist in the destination."
FM_CONFLICT_SKIP     = "Skip existing"
FM_CONFLICT_REPLACE  = "Replace existing"
FM_CONFLICT_RENAME   = "Keep both (auto-rename)"

# Action panel
FM_OP_COPYING        = "Copying…"
FM_OP_MOVING         = "Moving…"
FM_OP_DELETING       = "Deleting…"
FM_OP_TRASHING       = "Moving to trash…"
FM_OP_DONE           = "Done"
FM_OP_FAILED         = "Failed"
FM_OP_DISMISS        = "Dismiss"

# Properties — Permissions tab
PROP_PERM_OWNER      = "Owner"
PROP_PERM_GROUP      = "Group"
PROP_PERM_MODE       = "Permissions"
PROP_PERM_OCTAL      = "Octal"
PROP_PERM_CHANGE_BTN = "Change permissions…"
PROP_PERM_CHANGE_LABEL = "New octal mode (e.g. 644):"

# Properties — Checksums tab
PROP_CHECKSUMS_COMPUTE    = "Compute"
PROP_CHECKSUMS_COMPUTING  = "Computing…"

# Properties — Details tab
PROP_DETAILS_INODE      = "Inode"
PROP_DETAILS_LINKS      = "Hard links"
PROP_DETAILS_BLOCK_SIZE = "Block size"
PROP_DETAILS_BLOCKS     = "Blocks"

# Properties — Open With tab
PROP_OPENWITH_DEFAULT     = "Default application"
PROP_OPENWITH_OTHERS      = "Other applications"
PROP_OPENWITH_SET_DEFAULT = "Set as default"
PROP_OPENWITH_LOADING     = "Loading…"
PROP_OPENWITH_NONE        = "(none found)"

# ── M10e: File tags ───────────────────────────────────────────────────────────

FT_MODAL_TITLE       = "Tags — {name}"
FT_MODAL_TITLE_BATCH = "Tags — {n} files"
FT_MODAL_SUBTITLE    = "Click a tag to assign or remove it"
FT_NO_TAGS_MSG       = "No tags yet. Create one below."
FT_CREATE_HEADER     = "CREATE TAG"
FT_ASSIGN_HEADER     = "ASSIGN TAGS"
FT_SAVE_BTN          = "Save"
FT_CANCEL_BTN        = "Cancel"
