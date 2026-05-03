# Centralised terminology layer (spec §4).
# All user-facing strings live here so Linux idioms can be revised globally.

APP_TITLE = "System eKploiter"
APP_VERSION = "0.1-alpha"

# Tab bar
TAB_FILES = "Files"
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
