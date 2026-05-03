import logging

from PyQt6.QtCore import QObject, QTimer, pyqtSignal, pyqtSlot
from PyQt6.QtDBus import QDBusConnection

log = logging.getLogger(__name__)

_UDISKS2_SERVICE = "org.freedesktop.UDisks2"
_UDISKS2_PATH = "/org/freedesktop/UDisks2"
_OBJ_MANAGER_IFACE = "org.freedesktop.DBus.ObjectManager"
_PROPS_IFACE = "org.freedesktop.DBus.Properties"
_DEBOUNCE_MS = 250


class UDisks2Watcher(QObject):
    """Watches UDisks2 D-Bus signals and emits storage_changed (debounced).

    Falls back silently to polling-only mode if D-Bus is unavailable.
    """

    storage_changed = pyqtSignal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._dbus_available: bool = False

        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(_DEBOUNCE_MS)
        self._debounce.timeout.connect(self.storage_changed)

        self._connect_dbus()

    def _connect_dbus(self) -> None:
        try:
            bus = QDBusConnection.systemBus()
            if not bus.isConnected():
                log.warning(
                    "D-Bus system bus not available; falling back to polling-only mode"
                )
                return

            ok: list[bool] = []
            ok.append(bus.connect(
                _UDISKS2_SERVICE, _UDISKS2_PATH,
                _OBJ_MANAGER_IFACE, "InterfacesAdded",
                self._on_dbus_event,
            ))
            ok.append(bus.connect(
                _UDISKS2_SERVICE, _UDISKS2_PATH,
                _OBJ_MANAGER_IFACE, "InterfacesRemoved",
                self._on_dbus_event,
            ))
            # path="" subscribes to PropertiesChanged on every UDisks2 object
            ok.append(bus.connect(
                _UDISKS2_SERVICE, "",
                _PROPS_IFACE, "PropertiesChanged",
                self._on_dbus_event,
            ))

            self._dbus_available = any(ok)
            if not self._dbus_available:
                log.warning(
                    "Could not subscribe to UDisks2 D-Bus signals; "
                    "falling back to polling-only mode"
                )
        except Exception as exc:
            log.warning("D-Bus setup failed: %s; falling back to polling-only mode", exc)

    @pyqtSlot()
    def _on_dbus_event(self) -> None:
        try:
            self._debounce.start()
        except Exception as exc:
            log.warning("UDisks2 signal handler error: %s", exc)

    @property
    def dbus_available(self) -> bool:
        return self._dbus_available
