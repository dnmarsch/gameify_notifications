# Gameify Notifications — Tray Purge (GNOME Shell extension)

Optional companion extension. It runs **inside** gnome-shell and exposes a tiny
session D-Bus service (`org.gameify.TrayPurge`) so the overlay can remove a
notification from GNOME's **notification list / calendar tray** when you dismiss
it in the panel.

## Why it's needed

The overlay's D-Bus source already calls `CloseNotification(id)`, which closes an
**active banner**. But once GNOME parks a notification in its **list** (the
calendar dropdown), `CloseNotification` doesn't reliably remove that list entry —
that can only be done from code running inside the shell. This extension does
exactly that: it matches notifications by **title (== the Notify summary) and
body** (what the overlay captured) and calls `notification.destroy()`.

The overlay calls it automatically (best-effort) on dismiss/clear; if the
extension isn't installed, nothing breaks — you just keep the GNOME list entry.

## Install (GNOME 45/46/47)

```bash
# from this directory
./install.sh
# then reload GNOME Shell:  Alt+F2 -> type r -> Enter      (X11)
#   (Wayland: log out and back in)
gnome-extensions enable gameify-tray-purge@gameify.local
```

Verify it's live:

```bash
gnome-extensions info gameify-tray-purge@gameify.local            # State: ENABLED
gdbus call --session --dest org.gameify.TrayPurge \
  --object-path /org/gameify/TrayPurge \
  --method org.gameify.TrayPurge.ClearAll                     # clears all -> returns count
```

## D-Bus API

- `org.gameify.TrayPurge.DismissMatching(s summary, s body) -> i removed`
  — destroys tray notifications whose title == `summary` and body == `body`
  (empty args are wildcards).
- `org.gameify.TrayPurge.ClearAll() -> i removed` — destroys all tray notifications.

## Notes

- The GNOME 46 `Main.messageTray` API is what this targets; `extension.js`
  normalizes the sources/notifications access defensively. If a future GNOME
  changes it, adjust `_notifications()`.
- This is **not** required for the overlay to work; it only improves tray
  clean-up. Uninstall: `gnome-extensions disable gameify-tray-purge@gameify.local` then
  remove `~/.local/share/gnome-shell/extensions/gameify-tray-purge@gameify.local`.
