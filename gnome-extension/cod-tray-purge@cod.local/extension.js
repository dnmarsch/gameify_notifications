// CoD Overlay — Tray Purge (GNOME Shell 45/46/47, ESM)
//
// Runs inside gnome-shell and exposes a tiny session D-Bus service so the
// overlay can purge notifications from the *notification list* (the calendar
// tray) -- something an external client cannot reliably do via
// CloseNotification once GNOME has parked a notification in the list.
//
// We match by notification title (== the Notify "summary") and body, because
// those are exactly what the overlay captured; the freedesktop id is not
// exposed on Main.messageTray notifications.

import Gio from 'gi://Gio';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';

import {matchesNotification} from './purge.js';

const IFACE = `
<node>
  <interface name="org.cod.TrayPurge">
    <method name="DismissMatching">
      <arg type="s" direction="in" name="summary"/>
      <arg type="s" direction="in" name="body"/>
      <arg type="i" direction="out" name="removed"/>
    </method>
    <method name="ClearAll">
      <arg type="i" direction="out" name="removed"/>
    </method>
  </interface>
</node>`;

export default class CodTrayPurgeExtension {
    enable() {
        this._impl = Gio.DBusExportedObject.wrapJSObject(IFACE, this);
        this._impl.export(Gio.DBus.session, '/org/cod/TrayPurge');
        this._ownerId = Gio.bus_own_name(
            Gio.BusType.SESSION, 'org.cod.TrayPurge',
            Gio.BusNameOwnerFlags.NONE, null, null, null);
    }

    disable() {
        if (this._ownerId) {
            Gio.bus_unown_name(this._ownerId);
            this._ownerId = 0;
        }
        if (this._impl) {
            this._impl.unexport();
            this._impl = null;
        }
    }

    _notifications() {
        const tray = Main.messageTray;
        const sources = tray.getSources ? tray.getSources() : (tray.sources || []);
        const out = [];
        for (const source of sources) {
            const notifs = source.notifications || [];
            // GNOME 46 may expose a Map-like; normalize to an array
            for (const n of (notifs[Symbol.iterator] ? notifs : Object.values(notifs)))
                out.push(n);
        }
        return out;
    }

    DismissMatching(summary, body) {
        let removed = 0;
        for (const n of this._notifications()) {
            if (matchesNotification(n, summary, body)) {
                try { n.destroy(); removed++; } catch (_e) { /* already gone */ }
            }
        }
        return removed;
    }

    ClearAll() {
        let removed = 0;
        for (const n of this._notifications()) {
            try { n.destroy(); removed++; } catch (_e) { /* already gone */ }
        }
        return removed;
    }
}
