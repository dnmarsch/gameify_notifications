"""Pluggable notification sources: pure parsers, composite fan-in, name
registry / selection, and user drop-in plugins."""

import sys
import textwrap

import pytest

from gameify_notifications.sources import (NotificationSource, CompositeNotificationSource,
                                 select_source, available_sources)
from gameify_notifications.sources.dbus_source import HAVE_GI

_linux_gi = sys.platform.startswith("linux") and HAVE_GI


# ---- pure D-Bus parsers (no bus needed) ----------------------------------
def test_parse_notify_and_portal():
    from gameify_notifications.sources.dbus_source import parse_notify, parse_portal
    # Notify(app, replaces_id, icon, summary, body, actions, hints, timeout)
    assert parse_notify(["Teams", 0, "", "Carol", "is calling you", [], {}, -1]) == \
        ("Teams", "Carol", "is calling you")
    assert parse_notify(["x"]) is None
    # portal AddNotification("id", {title, body})
    assert parse_portal(["id", {"title": "Carol", "body": "is calling you"}]) == \
        ("", "Carol", "is calling you")
    assert parse_portal([]) is None


# ---- composite fan-in -----------------------------------------------------
class _Fake(NotificationSource):
    def __init__(self, name):
        self.name = name
        self.started = False

    def start(self, callback):
        self.started = True
        callback(self.name, "summary", "body")

    def describe(self):
        return self.name


def test_composite_fans_in():
    got = []
    comp = CompositeNotificationSource([_Fake("a"), _Fake("b")])
    comp.start(lambda app, s, t: got.append(app))
    assert sorted(got) == ["a", "b"]
    assert "a" in comp.describe() and "b" in comp.describe()


# ---- selection & registry -------------------------------------------------
@pytest.mark.skipif(not _linux_gi, reason="needs Linux + PyGObject")
def test_auto_composes_freedesktop_and_portal():
    src = select_source("teams", "auto")
    assert isinstance(src, CompositeNotificationSource)
    names = {s.name for s in src.sources}
    assert names == {"freedesktop", "portal"}


@pytest.mark.skipif(not _linux_gi, reason="needs Linux + PyGObject")
def test_single_named_source_is_not_composite():
    src = select_source("teams", "portal")
    assert src.name == "portal"


@pytest.mark.skipif(not _linux_gi, reason="needs Linux + PyGObject")
def test_unknown_source_warns_and_falls_back(caplog):
    import logging
    # 'bogus' unknown; 'freedesktop' valid -> still get a usable source
    with caplog.at_level(logging.WARNING, logger="gameify_notifications.sources"):
        src = select_source("teams", "freedesktop,bogus")
    assert src.name == "freedesktop"
    assert any("unknown source" in r.getMessage() for r in caplog.records)


# ---- capture prefilter ----------------------------------------------------
def test_empty_match_forwards_everything():
    from gameify_notifications.sources.dbus_source import FreedesktopNotifyMonitor
    m = FreedesktopNotifyMonitor("")        # default: no prefilter
    assert m._matches("Slack", "x", "y") is True
    assert m._matches("Microsoft Outlook", "Inbox", "mail") is True


def test_nonempty_match_still_prefilters():
    from gameify_notifications.sources.dbus_source import FreedesktopNotifyMonitor
    m = FreedesktopNotifyMonitor("teams")
    assert m._matches("Microsoft Teams", "x", "y") is True
    assert m._matches("Slack", "x", "y") is False


# ---- user drop-in plugin --------------------------------------------------
def test_plugin_source_is_discoverable(tmp_path, monkeypatch):
    from gameify_notifications import config
    plugin = config.sources_dir() / "myplugin.py"
    plugin.write_text(textwrap.dedent('''
        class PluginSource(NotificationSource):
            name = "myplugin"
            def __init__(self, match): self.match = match
            def start(self, callback): pass
    '''))
    assert "myplugin" in available_sources("teams")
    src = select_source("teams", "myplugin")
    assert src.name == "myplugin"


# ---- D-Bus closer propagation, id correlation, dedup, best-effort close ----
# Fakes for Gio D-Bus message/connection objects, so we can drive the monitor's
# message handler without a live bus.
class _FakeBody:
    def __init__(self, vals):
        self._vals = vals

    def unpack(self):
        return self._vals


class _FakeMsg:
    def __init__(self, mtype, member=None, interface=None, sender=None, serial=0,
                 destination=None, reply_serial=0, body=None):
        self._t, self._m, self._i, self._s = mtype, member, interface, sender
        self._serial, self._dest, self._rs, self._body = serial, destination, reply_serial, body

    def get_message_type(self): return self._t
    def get_member(self): return self._m
    def get_interface(self): return self._i
    def get_sender(self): return self._s
    def get_serial(self): return self._serial
    def get_destination(self): return self._dest
    def get_reply_serial(self): return self._rs
    def get_body(self): return self._body


class _Call:
    def __init__(self, dest, path, iface, method, params):
        self.dest, self.path, self.iface = dest, path, iface
        self.method, self.params = method, params


class _FakeSide:
    def __init__(self):
        self.calls = []

    def call_sync(self, dest, path, iface, method, params, *rest):
        self.calls.append(_Call(dest, path, iface, method, params))

    def methods(self):
        return [c.method for c in self.calls]

    def by_method(self, method):
        return next(c for c in self.calls if c.method == method)


class _FakeTray:
    def __init__(self):
        self.cleared = []

    def clear(self, summary, body):
        self.cleared.append((summary, body))


@pytest.mark.skipif(not HAVE_GI, reason="needs PyGObject for Gio message types")
def test_freedesktop_propagates_closer_and_correlates_id():
    from gi.repository import Gio
    from gameify_notifications import config
    from gameify_notifications.sources.dbus_source import FreedesktopNotifyMonitor

    tray = _FakeTray()
    m = FreedesktopNotifyMonitor("", tray_cleaner=tray)   # no prefilter
    m._owner = ":1.46"                          # pretend owner resolved
    m._side = _FakeSide()
    emitted = []
    m._cb = lambda app, summary, body, close: emitted.append((app, summary, body, close))

    iface = config.NOTIFY_IFACE
    # 1) a client Notify call (sender != owner) -> emit with a close callable
    call = _FakeMsg(Gio.DBusMessageType.METHOD_CALL, member="Notify", interface=iface,
                    sender=":1.99", serial=42,
                    body=_FakeBody(["Google Chrome", 0, "", "Carol",
                                    "teams.cloud.microsoft", [], {}, -1]))
    m._on_message(None, call, True, None)
    assert len(emitted) == 1
    app, summary, body, close = emitted[0]
    assert (app, summary, body) == ("Google Chrome", "Carol", "teams.cloud.microsoft")
    assert callable(close)

    # 2) the daemon's reply carries the id, correlated by (destination, reply_serial)
    ret = _FakeMsg(Gio.DBusMessageType.METHOD_RETURN, sender=":1.46",
                   destination=":1.99", reply_serial=42, body=_FakeBody([7]))
    m._on_message(None, ret, True, None)

    # 3) invoking the closer issues CloseNotification(7) on the freedesktop object
    close()
    assert "CloseNotification" in m._side.methods()
    cn = m._side.by_method("CloseNotification")
    assert cn.params.unpack()[0] == 7
    assert cn.dest == iface and cn.path == "/org/freedesktop/Notifications" and cn.iface == iface
    # ...and the tray-list purge goes through the injected TrayCleaner strategy
    assert tray.cleared == [("Carol", "teams.cloud.microsoft")]


@pytest.mark.skipif(not HAVE_GI, reason="needs PyGObject for Gio message types")
def test_freedesktop_skips_forwarder_call_for_dedup():
    from gi.repository import Gio
    from gameify_notifications import config
    from gameify_notifications.sources.dbus_source import FreedesktopNotifyMonitor

    m = FreedesktopNotifyMonitor("")
    m._owner = ":1.46"
    emitted = []
    m._cb = lambda *a: emitted.append(a)
    # a Notify whose sender IS the daemon owner == the forward to the shell
    fwd = _FakeMsg(Gio.DBusMessageType.METHOD_CALL, member="Notify",
                   interface=config.NOTIFY_IFACE, sender=":1.46", serial=1,
                   body=_FakeBody(["x", 0, "", "s", "b", [], {}, -1]))
    m._on_message(None, fwd, True, None)
    assert emitted == []                         # forwarder de-duplicated


@pytest.mark.skipif(not HAVE_GI, reason="needs PyGObject")
def test_freedesktop_close_is_best_effort():
    from gameify_notifications.sources.dbus_source import FreedesktopNotifyMonitor

    tray = _FakeTray()
    m = FreedesktopNotifyMonitor("", tray_cleaner=tray)
    m._side = _FakeSide()
    m._close(None, "S", "B")                     # no id -> no CloseNotification...
    assert "CloseNotification" not in m._side.methods()
    assert tray.cleared == [("S", "B")]          # ...but the tray cleaner still runs

    class _Boom:
        def call_sync(self, *a, **k):
            raise RuntimeError("nope")
    m._side = _Boom()
    m._close(5, "S", "B")                         # CloseNotification raises -> swallowed


@pytest.mark.skipif(not HAVE_GI, reason="needs PyGObject for Gio message types")
def test_portal_emits_without_close():
    from gi.repository import Gio
    from gameify_notifications.sources.dbus_source import PortalNotifyMonitor

    m = PortalNotifyMonitor("")
    emitted = []
    m._cb = lambda app, summary, body, close: emitted.append((summary, body, close))
    call = _FakeMsg(Gio.DBusMessageType.METHOD_CALL, member="AddNotification",
                    interface="org.freedesktop.portal.Notification",
                    body=_FakeBody(["some-id", {"title": "T", "body": "B"}]))
    m._on_message(None, call, True, None)
    assert emitted == [("T", "B", None)]         # portal has no close handle


@pytest.mark.skipif(not HAVE_GI, reason="needs PyGObject for Gio message types")
def test_freedesktop_return_from_non_owner_is_ignored():
    from gi.repository import Gio
    from gameify_notifications import config
    from gameify_notifications.sources.dbus_source import FreedesktopNotifyMonitor

    tray = _FakeTray()
    m = FreedesktopNotifyMonitor("", tray_cleaner=tray)
    m._owner = ":1.46"
    m._side = _FakeSide()
    emitted = []
    m._cb = lambda a, s, b, close: emitted.append(close)
    call = _FakeMsg(Gio.DBusMessageType.METHOD_CALL, member="Notify",
                    interface=config.NOTIFY_IFACE, sender=":1.99", serial=42,
                    body=_FakeBody(["Chrome", 0, "", "Carol", "teams.cloud.microsoft", [], {}, -1]))
    m._on_message(None, call, True, None)
    # a method-return from someone OTHER than the daemon owner must not fill the id
    bogus = _FakeMsg(Gio.DBusMessageType.METHOD_RETURN, sender=":1.77",
                     destination=":1.99", reply_serial=42, body=_FakeBody([99]))
    m._on_message(None, bogus, True, None)
    emitted[0]()                                          # close()
    assert "CloseNotification" not in m._side.methods()   # id never learned
    assert tray.cleared == [("Carol", "teams.cloud.microsoft")]  # tray purge still attempted


@pytest.mark.skipif(not HAVE_GI, reason="needs PyGObject for Gio message types")
def test_freedesktop_no_reply_means_no_close_notification():
    from gi.repository import Gio
    from gameify_notifications import config
    from gameify_notifications.sources.dbus_source import FreedesktopNotifyMonitor

    m = FreedesktopNotifyMonitor("")
    m._owner = ":1.46"
    m._side = _FakeSide()
    emitted = []
    m._cb = lambda a, s, b, close: emitted.append(close)
    call = _FakeMsg(Gio.DBusMessageType.METHOD_CALL, member="Notify",
                    interface=config.NOTIFY_IFACE, sender=":1.99", serial=7,
                    body=_FakeBody(["Chrome", 0, "", "Carol", "teams.cloud.microsoft", [], {}, -1]))
    m._on_message(None, call, True, None)
    emitted[0]()                                          # no daemon reply ever arrived
    assert "CloseNotification" not in m._side.methods()   # id stayed None
