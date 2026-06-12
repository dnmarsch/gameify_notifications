"""Best-effort removal of a notification from the desktop's *persistent
notification list* (the tray/calendar) after CloseNotification has closed the
banner.

There is no freedesktop standard for purging the persistent list, so this is a
per-desktop **strategy** (like sources/ and backends/): GNOME uses our
`cod-tray-purge` shell extension; other desktops (KDE, dunst, ...) can implement
their own `TrayCleaner` and register it in `select_tray_cleaner()`. The default
is a harmless no-op. The cleaner is injected into the D-Bus source, so it's
swappable and unit-testable.
"""

import logging
import os
import sys
from abc import ABC, abstractmethod

log = logging.getLogger(__name__)


class TrayCleaner(ABC):
    @abstractmethod
    def clear(self, summary, body):
        """Best-effort: remove the matching entry from the persistent list."""


class NoopTrayCleaner(TrayCleaner):
    def clear(self, summary, body):
        pass


class GnomeExtensionTrayCleaner(TrayCleaner):
    """Calls `org.cod.TrayPurge.DismissMatching` exposed by the cod-tray-purge
    GNOME Shell extension. Silently no-ops if the extension isn't installed."""

    SERVICE = "org.cod.TrayPurge"
    OBJECT = "/org/cod/TrayPurge"

    def __init__(self):
        self._conn = None

    def clear(self, summary, body):
        try:
            from gi.repository import Gio, GLib
            if self._conn is None:
                self._conn = Gio.bus_get_sync(Gio.BusType.SESSION, None)
            self._conn.call_sync(
                self.SERVICE, self.OBJECT, self.SERVICE, "DismissMatching",
                GLib.Variant("(ss)", (summary or "", body or "")),
                GLib.VariantType("(i)"), Gio.DBusCallFlags.NONE, 1500, None)
            log.debug("TrayPurge.DismissMatching(%r) ok", summary)
        except Exception:
            pass   # extension absent / not GNOME -> CloseNotification already ran


def _is_gnome():
    return "gnome" in os.environ.get("XDG_CURRENT_DESKTOP", "").lower()


def select_tray_cleaner():
    """Pick a tray cleaner for the current desktop (no-op when unsupported)."""
    if sys.platform.startswith("linux") and _is_gnome():
        try:
            import gi  # noqa: F401
            return GnomeExtensionTrayCleaner()
        except Exception:
            return NoopTrayCleaner()
    return NoopTrayCleaner()
