# gameify_notifications_overlay

Turn desktop notifications into a videogame HUD. Notifications pile up as
"damage" — the screen edges go bloody (Call of Duty), your shield/health drains
(Halo), or your mushroom lives disappear one by one (Mario) — until you read and
dismiss them in a panel. Built because notification banners vanish after 5–10s
and are easy to miss.

It's **not Teams-only**: `rules.toml` decides which apps matter and how much each
adds. It ships with Teams (calls/meetings/channels) and Outlook email rules; add
any other app by adding a rule.

GUI is **PySide6 (Qt Widgets)** — cross-platform. Notification capture is
per-OS: **D-Bus on Linux** (any freedesktop desktop), **WinRT on Windows**.

## Install & run

```bash
python -m venv .venv && . .venv/bin/activate
pip install -e .                      # PySide6 + the app
# Linux capture also needs PyGObject:  sudo apt install python3-gi

gameify_notifications --test                    # demo: CoD vignette, all monitors
gameify_notifications --hud halo --test         # demo: Halo shield + health bars, primary monitor
gameify_notifications --hud mario --test        # demo: Mario mushroom lives, primary monitor
gameify_notifications --hud pokemon --test      # demo: Pokemon sprite + HP bar, primary monitor
gameify_notifications --hud goldeneye --test    # demo: GoldenEye health/armor arcs, primary monitor
gameify_notifications                           # real: capture notifications (default --hud cod)
gameify_notifications --inspect                 # print raw notifications to map message types
gameify_notifications --list-huds
gameify_notifications --list-sources            # capture strategies for your install
gameify_notifications --source freedesktop      # or: portal / freedesktop,portal / a plugin name
gameify_notifications --install-autostart       # / --uninstall-autostart  (Linux .desktop)
```

(or `python -m gameify_notifications ...`)

## Options

| Flag | Default | Description |
|------|---------|-------------|
| `--hud NAME` | `cod` | HUD to render (`cod`, `halo`, `mario`, or a custom plugin). |
| `--match SUBSTR` | *(empty)* | Optional capture prefilter (substring of app name/text). Empty = forward all notifications and let `rules.toml` decide. |
| `--source SPEC` | `auto` | Capture strategy. `auto` = platform default (Linux composes `freedesktop`+`portal`); or a comma list of names; or a plugin name. |
| `--test` | off | Inject fake notifications to demo the HUD (no capture). |
| `--inspect` | off | Print raw captured notifications and exit (no GUI) — use to map message types. |
| `--list-huds` | — | List available HUDs and exit. |
| `--list-sources` | — | List available capture strategies and exit. |
| `--log-level LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR`. Gates records at the source. |
| `--debug` | off | Shortcut for `--log-level DEBUG`. |
| `--log-file PATH` | `<config>/logs/gameify_notifications.log` | Override the log file path. |
| `--no-focus-suppress` | off | Disable per-rule `focus_class` suppression (always add damage, even for the focused app). |
| `--install-autostart` | — | Install a desktop autostart entry and exit (Linux `.desktop`). |
| `--uninstall-autostart` | — | Remove the autostart entry and exit. |

Environment: `GAMEIFY_NOTIFICATIONS_LOG_LEVEL` overrides the level (e.g. for autostart);
`GAMEIFY_NOTIFICATIONS_CONFIG_DIR` relocates config/state/logs (used by the tests).

## Rules — which notifications count

`~/.config/gameify_notifications_overlay/rules.toml` is the filter (hot-reloaded, so edits
apply live). Each rule matches on the notifying **app name** (`app`, regex)
and/or the **text** (`match`, regex over `"summary | body"`); both are optional.
Rules are tested top-to-bottom, **first match wins**, and a notification
matching **no rule is ignored** (allowlist — no surprise redness from Slack,
system updates, etc.). `weight` is the damage it adds; `0` = listed in the panel
but no redness.

```toml
[[rule]]
name = "Incoming call"
app  = "teams"
match = "calling you|incoming call|is calling"
weight = 4.0

[[rule]]
name = "Outlook email"
app  = "outlook"          # matches the snap/Electron Outlook too (via D-Bus)
weight = 0.5

# add any app: run `gameify_notifications --inspect` to see its real app_name + text
```

Use `gameify_notifications --inspect` (now unfiltered — prints **every** app's
notifications) to find the exact `app_name`/text, then write rules for it. The
optional `--match` flag is just a coarse capture prefilter; the rules do the real
filtering.

Editing is safe and live on every platform (TOML hot-reload via stdlib
`tomllib`, Windows included). A single bad rule — missing `name`, broken regex,
non-numeric `weight` — is **logged and skipped**, not fatal; the other rules keep
working. If the whole file is mid-edit-broken, the last good rules are kept.

### Don't damage me for the app I'm looking at (`focus_class`)

A rule may add an optional **`focus_class`** (regex). When a matching notification
arrives, the overlay checks whether that app has a window **visible on any
monitor** (mapped, not minimized, on the current workspace — not just the
*focused* window); if so, the notification is **dropped** (no damage, no panel
row) — you can already see it. Disable globally with `--no-focus-suppress`.

```toml
[[rule]]
name = "Teams message"
match = 'teams\.cloud\.microsoft'
focus_class = 'crx_ompifgpmddkgmclendfeacglnodjjndh'   # Teams PWA visible on a monitor -> no damage
weight = 1.5
```

The *mechanism* is OS-generic (a regex matched against the focused-app id from a
per-OS probe); the *value* is platform-specific — on **X11** it's the window's
`WM_CLASS` (Chrome PWAs are `crx_<app-id>`; find it with `xprop WM_CLASS`), on
**Windows** the process exe (e.g. `chrome.exe`). For a cross-OS file, use an
alternation (`crx_…|chrome.exe`). There's no single cross-platform focus API, so
the probe is per-OS: **X11** (`xprop`), **Windows** (`GetForegroundWindow`),
**Wayland/macOS** → unsupported, so suppression is simply skipped there.

### Tuning the HUDs (`full_at`, `[hud.*]`)

The same hot-reloaded `rules.toml` carries the HUD tuning knobs, so edits apply
**live while the HUD is on screen** (a 2×/sec watch repaints on change):

Per-rule `weight` is the **damage** each notification adds, and it feeds **every**
overlay. On top of that, **every `[hud.*]` block accepts two optional universal
knobs** so each overlay can set its own capacity and drain independently (omit
them to use the defaults):

```toml
max_messages = 0     # this HUD's damage capacity; 0 = inherit the global full_at
weight_scale = 1.0   # drain-rate multiplier on notification weights (2.0 = 2x as fast)
```

```toml
full_at   = 10.0    # global damage / unread-message budget (HUDs inherit unless they
                    # set their own max_messages)
max_alpha = 0.7     # opacity ceiling

[hud.halo]          # shield + health bars (also accepts max_messages / weight_scale)
shield_fraction   = 0.5    # share of full_at given to the shield (rest = health);
                           # the odd unit rounds toward the shield (e.g. 11 -> 6/5)
health_red_at     = 0.5    # health turns red once it drops below this fraction
warning_at        = 0.25   # health fraction below which "WARNING" flashes
health_resolution = 2      # health-bar segments per health unit (higher = finer)

[hud.cod]           # damage vignette
clear_at_rest    = 0.85    # inner clear radius at 0 damage (1.0 = red only at edge)
max_encroachment = 0.18    # inner clear radius at full damage (smaller = red creeps further in)
intensity        = 0.5     # peripheral-red opacity slope (× damage × max_alpha)

[hud.mario]         # mushroom lives (one mushroom per unit of full_at)
# icon_path   = "/path/to/icon.png"   # default: bundled mushroom (transparent bg)
lost_opacity = 0.18    # opacity of a lost mushroom (0 = hide it entirely)
gap          = 0.12    # spacing between mushrooms (fraction of icon width)
warning_at   = 0.25    # blink the last life/lives once lives drop below this fraction

[hud.pokemon]       # sprite + classic HP bar (HP = remaining health)
name         = "BULBASAUR"   # shown above the level
level        = 50            # 1-100
# icon_path  = "/path/to/sprite.png"   # default: bundled Bulbasaur (transparent bg)
green_above  = 0.70    # HP at/above this fraction -> green
yellow_above = 0.30    # HP at/above this -> yellow, below -> red

[hud.goldeneye]     # two facing arcs: left health (red->yellow), right shield (blue->cyan)
shield_fraction = 0.5    # share of capacity given to the shield (drains first)
segments        = 9      # ticks per arc
```

The shield drains entirely before the health bar starts; the shield renders as a
continuous fill while the health bar is segmented (at `health_resolution`× its
units) so small-weight changes still read. Mario shows `full_at` mushrooms and
removes one per unit of damage (from the right); lost ones fade to a ghost (or
vanish at `lost_opacity = 0`). Unknown keys / bad values fall back to the
defaults above, so a typo while live-editing never crashes the HUD.

> Upgrading from a Teams-only version? Your existing `rules.toml` is kept as-is
> (not overwritten). Delete it to regenerate the new app-aware defaults (now
> including the `[hud.*]` tuning tables), or add `app = "..."` lines, an Outlook
> rule, and the `[hud.*]` blocks yourself.

## Architecture

Single-responsibility modules; the core is GUI-free and unit-testable on its own:

```
gameify_notifications/
  config.py        paths, default rules, state persistence, autostart   (stdlib)
  geometry.py      monitor math, off-screen clamp, fractional rescale    (stdlib)
  rules.py         notification -> (category, damage weight)             (stdlib)
  state.py         accumulated damage + observers                        (stdlib)
  app.py           platform-agnostic App context                         (stdlib)
  huds/            QPainter HUD renderers + plugin loader + render_to_image (Qt)
    cod.py  halo.py  mario.py  pokemon.py  goldeneye.py   params.py (validated [hud.*] tuning)
  sources/         NotificationSource ABC + select_source                (per-OS)
    dbus_source.py      Linux: eavesdrop org.freedesktop.Notifications + portal
    windows_source.py   Windows: WinRT UserNotificationListener
  backends/        OverlayBackend ABC + select_backend
    qt/  backend.py persistence.py overlay_window.py widget_window.py panel_window.py
  __main__.py      CLI entry
```

Two seams make it portable: **`NotificationSource`** (capture) and
**`OverlayBackend`** (windowing). HUDs draw with `QPainter` — no cairo — so the
2D drawing is already cross-platform. Add a platform by implementing the two
ABCs and registering them in `select_source()` / `select_backend()`.

## HUDs

| name | scope | window |
|------|-------|--------|
| `cod` | all monitors | click-through red vignette (`Qt.WindowTransparentForInput`); flashes on each hit |
| `halo` | primary monitor | **movable + resizable** shield + health bars; shield drains first (damage clears, not red), health turns red below 50% with a WARNING pulse; ⊕ re-centers |
| `mario` | primary monitor | **movable + resizable** row of mushroom lives; one lost per unit of damage (faded ghosts), last life blinks when low; icon swappable via `[hud.mario].icon_path` |
| `pokemon` | primary monitor | **movable + resizable** sprite + classic battle box (name, level, HP bar); HP = remaining health, green→yellow→red as damage lands; name/level/sprite configurable |
| `goldeneye` | primary monitor | **movable + resizable** two facing gradient arcs — left = health (red→yellow), right = shield (blue→cyan); shield drains first, ticks drain from the top |

Custom HUDs: drop a `*.py` into `~/.config/gameify_notifications_overlay/huds/` defining a
`Hud` subclass (template `example_pulse.py.txt` is written there on first run).

## The dismiss panel

Movable (drag the header), **resizable** (size grip), and **collapsible** — ▾
shrinks it to a one-line toolbar, ▸ expands it back to your last size. Position,
size, and collapsed state persist. Dismissing an item heals the damage.

## Persistence & multi-monitor safety

`state.json` stores window geometry. The **panel** stores absolute pixels (a text
list — legibility over scaling) with a 95% max-fraction clamp. The **HUD widget**
stores geometry as a **fraction of its monitor**, so it rescales proportionally
when resolution or orientation changes. Both validate against the current monitor
layout on start and on monitor hotplug, snapping back if a window would land
off-screen.

## Tests

```bash
pip install -e ".[dev]"               # pytest + pytest-qt
QT_QPA_PLATFORM=offscreen pytest      # headless; env var also set in conftest
```

Pure-logic unit tests (geometry/rules/state/app) + `pytest-qt` tests for HUD
rendering and widget behavior. See [`tests/TEST_PLAN.md`](tests/TEST_PLAN.md) for
the full widget×behavior matrix and how resizing / resolution-change is tested
(injectable monitor provider; render-to-`QImage` pixel assertions).

## Capture strategies (`--source`)

Different installs route notifications differently, so capture is pluggable.
`--source auto` (default) composes the platform built-ins; on Linux that's
**freedesktop + portal** together, so both native (`.deb`/Firefox) and confined
(snap/flatpak via the XDG portal) apps are caught. Pick explicitly with
`--source freedesktop`, `--source portal`, or a comma list, and add your own by
dropping a `NotificationSource` subclass into `~/.config/gameify_notifications_overlay/sources/`
(template `example_source.py.txt` is written there on first run), selectable by
its `name`. Built-ins:

| name | what it watches |
|------|-----------------|
| `freedesktop` | `org.freedesktop.Notifications.Notify` (teams-for-linux deb/rpm/AppImage, Firefox) |
| `portal` | XDG Desktop Portal `AddNotification` (snap / flatpak confined apps) |
| `windows` | WinRT `UserNotificationListener` (Windows) |

Capture is **event-driven**, not polling: the Linux sources plug into GLib's
main loop (reactor) via `BecomeMonitor` + a message filter; events propagate to
the UI through the `DamageState` observer and a queued Qt signal. (The Windows
source polls every 2s, and the HUD repaints at ~30fps only while animating.)

## Logging / debugging

Logging is **non-blocking**: app threads push records onto a queue via a
`QueueHandler`; a single background `QueueListener` thread does the file I/O, so
the UI and capture threads never block. Every record carries the **thread name**
(tells the Qt UI thread from a `dbus-freedesktop` / `winrt-notify` source
thread), the **module**, **function** and **line number** — designed to make
AI-assisted debugging easy:

```
2026-06-11 10:39:20 DEBUG [MainThread] gameify_notifications.app.on_notification:30 - notification app='Microsoft Teams' summary='Carol' -> category=Incoming call weight=4.0
```

There is **one** log file (`~/.config/gameify_notifications_overlay/logs/gameify_notifications.log`,
rotating) and the console (stderr); both emit at the configured level. The level
gates records **at the call site** — anything below it is never enqueued, not
just hidden. Uncaught exceptions on any thread and Qt's own messages are
captured too. There are no duplicate `print` + `log` lines: everything goes
through the logger, and the console shows it live.

```bash
gameify_notifications --debug                       # = --log-level DEBUG
gameify_notifications --log-level WARNING
gameify_notifications --log-file /tmp/gameify.log
GAMEIFY_NOTIFICATIONS_LOG_LEVEL=DEBUG gameify_notifications   # env var also works (e.g. for autostart)
```

## Platform notes

- **Linux**: works on any freedesktop desktop (GNOME/KDE/XFCE). The all-monitor
  click-through overlay relies on X11/`WindowTransparentForInput`.
- **Windows**: implement/enable `windows_source.py` (needs the `winrt` packages
  and user-granted notification access). Click-through overlays are supported.
- **macOS**: no public API to read other apps' notifications — unsupported.

## Docs

- [`docs/notification-capture-ubuntu.md`](docs/notification-capture-ubuntu.md) —
  what Teams/Outlook actually emit per install option (snap vs Chrome vs Firefox),
  capture limits (AppArmor confinement, focus-suppression), latency, the
  match-on-origin rule strategy, and the deferred GNOME-tray-sync design.
- [`docs/snap-to-deb-firefox.md`](docs/snap-to-deb-firefox.md) — switching Firefox
  from snap to the unconfined `.deb` (so its notifications are capturable) + profile recovery.

## Known limitations
- Categorization is text/app-based (D-Bus exposes no semantic "category"); tune
  `rules.toml` against `--inspect` output for each app.
- The Halo widget captures clicks where it sits (so you can drag it) — move it
  aside if it covers something.

## Contributing

Read [`CONSTITUTION.md`](CONSTITUTION.md) first — it's the source of truth for how
changes are made here: tests required for every created/modified implementation,
SRP / Open–Closed, the established patterns (Strategy+DI, Factory, Observer,
validated-param ADTs, mixins), DRY with composition over inheritance, OS-agnostic
additions behind a seam, and `docs/` updated when a new OS/technology lands. The
seams to extend (never edit around): `NotificationSource`, `OverlayBackend`,
`Hud` + `ParamSpec`, `TrayCleaner`, `FocusProbe`.

## License

[MIT](LICENSE) © 2026 Derek Marsch.
