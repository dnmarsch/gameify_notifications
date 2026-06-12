"""Linux notification capture by passively monitoring the session D-Bus
(the mechanism `dbus-monitor` uses), so the desktop's own daemon keeps showing
banners.

Two concrete strategies cover the common routes:
  * FreedesktopNotifyMonitor -- classic org.freedesktop.Notifications.Notify
    (Chrome, Firefox, teams-for-linux, ...). It also captures the daemon's
    method-return so it learns the assigned notification id, and hands the core
    a `close` callable that calls CloseNotification(id) -- best-effort clearing
    of the desktop notification when the user dismisses it in our panel. This is
    the freedesktop standard, so it works on GNOME/KDE/dunst/mako/... .
  * PortalNotifyMonitor -- XDG Desktop Portal AddNotification (snap/flatpak).
    No reliable id to close, so its notifications come with close=None.

Each is self-servicing: it runs its own GLib main loop on a background thread,
so it doesn't depend on any UI toolkit (the Qt backend marshals the callback)."""

import logging
import threading

from .. import config
from . import NotificationSource

log = logging.getLogger(__name__)

try:
    import gi  # noqa: F401
    from gi.repository import Gio, GLib
    HAVE_GI = True
except Exception:   # ImportError or typelib error
    HAVE_GI = False

_MESSAGE_BUS_FLAGS = None
if HAVE_GI:
    _MESSAGE_BUS_FLAGS = (Gio.DBusConnectionFlags.AUTHENTICATION_CLIENT
                          | Gio.DBusConnectionFlags.MESSAGE_BUS_CONNECTION)


# ---- pure parsers (unit-testable without D-Bus) --------------------------
def parse_notify(args):
    """org.freedesktop.Notifications.Notify positional args -> (app, summary, body)."""
    if len(args) >= 5:
        return args[0] or "", args[3] or "", args[4] or ""
    return None


def parse_portal(args):
    """portal AddNotification(..., a{sv} notification) -> (app, summary, body)."""
    note = args[-1] if args else None
    if isinstance(note, dict):
        return "", note.get("title", ""), note.get("body", "")
    return None


class _DBusMonitorSource(NotificationSource):
    """Base: BecomeMonitor on the session bus with `match_rules`, dispatch each
    message through `_parse()` (override), filter by the match substring, emit.
    Notifications carry no `close` from the base (portal); subclasses may add it."""

    match_rules = []

    def __init__(self, match_substr):
        self.match = match_substr
        self._loop = None
        self._thread = None
        self._cb = None

    def _parse(self, message):
        raise NotImplementedError

    def _matches(self, app, summary, body):
        if not self.match:
            return True   # forward everything; rules.toml is the real filter
        needle = self.match.lower()
        return needle in (app or "").lower() or needle in f"{summary} {body}".lower()

    def _emit(self, app, summary, body, close=None):
        if self._matches(app, summary, body) and self._cb:
            log.debug("[%s] captured app=%r summary=%r close=%s",
                      self.name, app, summary, bool(close))
            self._cb(app, summary, body, close)

    def _on_message(self, connection, message, incoming, user_data):
        try:
            parsed = self._parse(message)
            if parsed:
                self._emit(parsed[0], parsed[1], parsed[2], None)
        except Exception:
            log.exception("error handling D-Bus message in %s", self.name)
        return None  # consume (we are a monitor)

    def _pre_monitor(self):
        """Hook on the source's GLib thread, before BecomeMonitor (e.g. open a
        side connection / resolve names). Default: nothing."""

    def start(self, callback):
        self._cb = callback

        def run():
            ctx = GLib.MainContext.new()
            ctx.push_thread_default()
            self._loop = GLib.MainLoop.new(ctx, False)
            try:
                self._pre_monitor()
                address = Gio.dbus_address_get_for_bus_sync(Gio.BusType.SESSION, None)
                conn = Gio.DBusConnection.new_for_address_sync(
                    address, _MESSAGE_BUS_FLAGS, None, None)
                # BecomeMonitor FIRST -- a message filter that consumes incoming
                # messages would otherwise eat this call's own reply and time out.
                conn.call_sync(
                    "org.freedesktop.DBus", "/org/freedesktop/DBus",
                    "org.freedesktop.DBus.Monitoring", "BecomeMonitor",
                    GLib.Variant("(asu)", (list(self.match_rules), 0)),
                    None, Gio.DBusCallFlags.NONE, 10000, None)
                # ...then start observing the monitored traffic.
                conn.add_filter(self._on_message, None)
                log.info("D-Bus monitor attached: %s", self.describe())
            except Exception:
                log.exception("could not attach D-Bus monitor for %s", self.name)
            self._loop.run()

        self._thread = threading.Thread(target=run, name=f"dbus-{self.name}", daemon=True)
        self._thread.start()

    def stop(self):
        if self._loop is not None:
            self._loop.quit()


class FreedesktopNotifyMonitor(_DBusMonitorSource):
    """org.freedesktop.Notifications. Also tracks the daemon's reply to learn the
    notification id, so dismissing in our panel can CloseNotification(id)."""

    name = "freedesktop"
    match_rules = [
        f"interface='{config.NOTIFY_IFACE}',member='Notify'",
        # replies from the notifications daemon (carry the assigned id)
        f"sender='{config.NOTIFY_IFACE}',type='method_return'",
    ]

    def __init__(self, match_substr, tray_cleaner=None):
        super().__init__(match_substr)
        self._side = None      # normal connection used for GetNameOwner + CloseNotification
        self._owner = None     # unique name owning org.freedesktop.Notifications
        self._pending = {}     # (client_unique, call_serial) -> {"id": int|None}
        # strategy for purging the persistent notification list (per desktop)
        if tray_cleaner is None:
            from ..tray import select_tray_cleaner
            tray_cleaner = select_tray_cleaner()
        self._tray = tray_cleaner

    def _pre_monitor(self):
        # a separate, normal connection (the monitor connection is receive-only)
        address = Gio.dbus_address_get_for_bus_sync(Gio.BusType.SESSION, None)
        self._side = Gio.DBusConnection.new_for_address_sync(
            address, _MESSAGE_BUS_FLAGS, None, None)
        try:
            owner = self._side.call_sync(
                "org.freedesktop.DBus", "/org/freedesktop/DBus",
                "org.freedesktop.DBus", "GetNameOwner",
                GLib.Variant("(s)", (config.NOTIFY_IFACE,)),
                GLib.VariantType("(s)"), Gio.DBusCallFlags.NONE, 2000, None)
            self._owner = owner.unpack()[0]
            log.debug("notifications daemon owner = %s", self._owner)
        except Exception:
            log.warning("could not resolve notifications daemon owner; "
                        "clearing/dedup may be degraded", exc_info=True)

    def _on_message(self, connection, message, incoming, user_data):
        try:
            mtype = message.get_message_type()
            if (mtype == Gio.DBusMessageType.METHOD_CALL
                    and message.get_member() == "Notify"
                    and message.get_interface() == config.NOTIFY_IFACE):
                sender = message.get_sender()
                if self._owner and sender == self._owner:
                    return None     # the daemon forwarding to the shell -> skip (dedup)
                body = message.get_body()
                if body is not None:
                    parsed = parse_notify(body.unpack())
                    if parsed:
                        box = {"id": None}
                        self._pending[(sender, message.get_serial())] = box
                        if len(self._pending) > 256:
                            self._pending.pop(next(iter(self._pending)))
                        closer = (lambda b=box, s=parsed[1], bd=parsed[2]:
                                  self._close(b["id"], s, bd))
                        self._emit(parsed[0], parsed[1], parsed[2], closer)
            elif (mtype == Gio.DBusMessageType.METHOD_RETURN
                    and self._owner and message.get_sender() == self._owner):
                key = (message.get_destination(), message.get_reply_serial())
                box = self._pending.pop(key, None)
                if box is not None:
                    rb = message.get_body()
                    if rb is not None:
                        vals = rb.unpack()
                        if vals:
                            box["id"] = vals[0]     # daemon-assigned notification id
        except Exception:
            log.exception("error handling notify message")
        return None

    def _close(self, notif_id, summary="", body=""):
        """Best-effort clearing: close the desktop notification, and -- if the
        optional cod-tray-purge GNOME extension is installed -- also remove the
        lingering entry from GNOME's notification list/tray."""
        if self._side is None:
            return
        if notif_id is not None:
            try:
                self._side.call_sync(
                    config.NOTIFY_IFACE, "/org/freedesktop/Notifications",
                    config.NOTIFY_IFACE, "CloseNotification",
                    GLib.Variant("(u)", (int(notif_id),)),
                    None, Gio.DBusCallFlags.NONE, 2000, None)
                log.debug("CloseNotification(%s) sent", notif_id)
            except Exception:
                log.debug("CloseNotification(%s) failed", notif_id, exc_info=True)
        # purge the persistent list entry via the per-desktop tray cleaner strategy
        try:
            self._tray.clear(summary, body)
        except Exception:
            log.debug("tray cleaner failed", exc_info=True)

    def describe(self):
        return f"freedesktop Notify (match '{self.match}')"


class PortalNotifyMonitor(_DBusMonitorSource):
    name = "portal"
    match_rules = ["member='AddNotification'"]

    def _parse(self, message):
        if message.get_member() == "AddNotification" and "ortal" in (message.get_interface() or ""):
            body = message.get_body()
            if body is not None:
                return parse_portal(body.unpack())
        return None

    def describe(self):
        return f"XDG portal AddNotification (match '{self.match}')"
