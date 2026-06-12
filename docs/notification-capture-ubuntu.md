# Notification capture on Ubuntu — Teams & Outlook (impl notes)

Empirically validated on **Ubuntu 24.04 (noble), GNOME / X11, 2026-06**, by
eavesdropping the session bus (`dbus-monitor` + `gameify_notifications --inspect`).

## How capture works (and its hard limit)

`gameify_notifications_overlay` is a **passive D-Bus monitor** (`BecomeMonitor`) on
`org.freedesktop.Notifications.Notify` (+ the XDG portal `AddNotification`). It
sees a notification only if that notification actually crosses the **session
bus** in a form a monitor is allowed to observe.

Two consequences, both confirmed by testing:

- **AppArmor-confined snaps can be invisible.** A monitor never saw the snap
  **outlook-electron** notifications (its `org.gtk.Notifications` path under snap
  confinement isn't eavesdroppable here), while a `notify-send` and the snap
  **teams-for-linux** *were* captured. So "it's a snap" isn't the whole story —
  it depends on which notification API the app uses and how it's confined.
- **Focus suppression is universal.** Per the Web Notifications spec, a browser
  raises a *system* notification only when the web app is **unfocused**. Focused
  → you get the app's in-app banner, which **never touches D-Bus**. This is why
  testing must be done with the Teams/Outlook window in the background.

## What each install option actually emits

| Install | On the bus? | `app_name` | `desktop-entry` hint | `summary` | `body` |
|---|---|---|---|---|---|
| **teams-for-linux** (snap) | ✅ yes | `teams-for-linux` | `/snap/teams-for-linux/<rev>/teams-for-linux` | sender | **real message text** |
| **outlook-electron** (snap) | ❌ **no** (hidden) | — | — | — | — |
| **Chrome** — Teams (tab/PWA) | ✅ yes | `Google Chrome` | `google-chrome` | sender | **`teams.cloud.microsoft`** (origin) |
| **Chrome** — Outlook (tab/PWA) | ✅ yes | `Google Chrome` | `google-chrome` | sender / title | **`outlook.cloud.microsoft`** (origin) |
| **Firefox** (.deb) — Teams | ✅ yes | `Firefox` | `firefox` | sender | real message text |
| **Firefox** (.deb) — Outlook | ✅ yes | `Firefox` | `firefox` | `Outlook` | "Sender: Subject" |

Notes:
- **Firefox must be the unconfined `.deb`** (the snap Firefox can't be captured
  reliably and also can't run PWAsForFirefox). See
  [`snap-to-deb-firefox.md`](snap-to-deb-firefox.md).
- **PWAsForFirefox does not give a per-app identity** — Firefox reports
  `app_name="Firefox"` / `desktop-entry="firefox"` for everything.
- **Chrome's `desktop-entry` was `google-chrome`** (not a per-PWA `chrome-<id>`)
  in testing; the distinguishing signal is the **origin in the body**.

## Latency (observed)

- **Teams**: near-instant — it uses a live push channel (websocket/signalR).
- **Outlook**: minutes — Enterprise/Exchange mail sync runs on a cadence
  (~1–5 min) **plus** the browser's unfocused background-throttle. This is
  upstream of the notification; the overlay can't change it. Native apps or a
  true Web Push pipeline are the only real fixes.

## Rules implications (what to match on)

Because identity differs per client, `rules.toml` should match on the fields
that client actually fills:

| Client | Reliable match | Granularity |
|---|---|---|
| **Chrome** | the **origin in the body** (`teams.cloud.microsoft`, `outlook.cloud.microsoft`) | **coarse** — body is the origin, so you *cannot* tell a Teams call/meeting/message apart |
| **snap teams-for-linux** | `app` = `teams-for-linux`; body carries the real message | finer, but Teams chat bodies are arbitrary |
| **Firefox** | Outlook → `summary` = `Outlook`; **Teams is *not* identifiable** (looks like any Firefox notification) | n/a |

### Recommended setup (simplest + most robust)

**Use Chrome for both Teams and Outlook**, and run **only one client per app**
(running snap + Firefox + Chrome simultaneously triple-fires every message — each
copy is a separate `Notify`). Then:

```toml
full_at   = 6.0
max_alpha = 0.7

[[rule]]
name   = "Teams message"
match  = "teams\\.cloud\\.microsoft"     # Chrome puts the origin in the body
weight = 1.5

[[rule]]
name   = "Outlook email"
match  = "outlook\\.cloud\\.microsoft"
weight = 0.5
```

(Matching works because `classify()` tests against `"summary | body"`.)

> Per-notification-type damage (call=4 / meeting=3 / message=1.5) is **not
> achievable via web notifications** — only the native/snap client carries the
> real message text. With Chrome it's "any Teams = X, any Outlook = Y."

## Focus suppression — don't damage the app you're looking at

A rule may set `focus_class` (regex). When a matching notification arrives, the
probe returns the apps with a window **visible on any monitor** (mapped, not
minimized, on the current workspace); if `focus_class` matches one, the
notification is **dropped** (no damage, no panel row). Using *visible* rather
than only *focused* means a Teams window open on a second monitor also
suppresses. This kills the "message in another Teams chat while I'm in Teams"
annoyance (browser focus-suppression only covers the chat you're viewing).

- There's **no single cross-platform API**, so the probe is per-OS
  (`gameify_notifications/focus.py`, injected into `App` so it's swappable/testable), and
  returns a *set* of on-screen app ids: **X11** `_NET_CLIENT_LIST` → per-window
  `WM_CLASS`, skipping `_NET_WM_STATE_HIDDEN`/other-workspace (via `xprop`, with
  a 0.5s cache); **Windows** `EnumWindows`+`IsWindowVisible`→exe;
  **Wayland/macOS** → empty (suppression skipped).
- `focus_class`'s *value* is platform-specific: X11 `WM_CLASS` (Chrome PWAs are
  `crx_<app-id>` — `xprop WM_CLASS`), Windows exe name. Cross-OS files use an
  alternation. PID-matching is **not** usable for Chrome (all PWAs share one
  process); `WM_CLASS` is the discriminator. Disable globally: `--no-focus-suppress`.

## Clearing the GNOME notification on dismiss (best-effort, implemented)

Dismissing a row also asks the daemon to clear the desktop notification:

- The D-Bus source captures each notification's daemon-assigned **id** (from the
  `Notify` **method-return**, correlated to its call by `(destination,
  reply_serial)`), and hands the core a `close` callable that runs
  `CloseNotification(id)` on a **separate** connection (the monitor is
  receive-only). The freedesktop standard → works on GNOME/KDE/dunst/etc.
- This **also dedupes**: on this machine the daemon is `org.gnome.Shell.Notifications`
  (a gjs process) which **re-emits** each notification to the main shell, so a
  notification crosses the bus twice; we skip the daemon-as-sender copy by owner.

**Limitation (observed):** `CloseNotification` reliably closes an **active
banner**, but GNOME often keeps the entry in its **calendar notification list**
even after close — a shell behavior, not our bug (`CloseNotification` calls
succeed in the logs). Purging the *list* per-item needs code running **inside**
gnome-shell:
- **[Clear All Notifications](https://extensions.gnome.org/extension/1226/clear-all-notifications/)**
  adds a clear-all button — clears *everything*, not by id.
- No off-the-shelf extension purges a *specific* notification by its freedesktop
  id from an external D-Bus call; the
  [GJS notifications API](https://gjs.guide/extensions/topics/notifications.html)
  works on `Main.messageTray` inside the shell. So this repo **ships a small
  custom extension** at `gnome-extension/cod-tray-purge@cod.local/` that exports
  `org.cod.TrayPurge.DismissMatching(summary, body)` / `ClearAll()` and destroys
  matching `Main.messageTray` notifications. Install it (see
  `gnome-extension/README.md`); the overlay then calls it automatically on
  dismiss/clear (best-effort — matching by title+body, since the freedesktop id
  isn't exposed on tray notifications). No extension installed → CloseNotification
  still closes the banner, the list entry just lingers.
- Also: a chunk of the lingering tray entries are **duplicate snap apps** (e.g.
  `teams-for-linux` snap alongside the Chrome PWA) which we ignore and never
  close — remove the snaps to halve the clutter.
