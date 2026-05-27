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
ACTION_CHECK_UPDATES = "Check for updates"
ACTION_ASSIGN_TAGS = "Assign tags…"
ACTION_MIGRATE_DRIVE = "Migrate to different drive"
ACTION_REINSTALL = "Reinstall / repair"
ACTION_UNINSTALL = "Uninstall"
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

# Confirmation
CONFIRM_UNINSTALL_TITLE = "Uninstall {name}?"
CONFIRM_UNINSTALL_BODY = (
    "This will remove the following from your system:"
)

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

# ── Sidebar ───────────────────────────────────────────────────────────────────

SIDEBAR_CATEGORIES = "CATEGORIES"
SIDEBAR_TAGS = "TAGS"
SIDEBAR_ALL = "All"
SIDEBAR_NEW_TAG = "+ New tag"
