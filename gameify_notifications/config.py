"""Paths, default rules, state persistence, and autostart.

Stdlib-only and cross-platform: no Qt, no GLib. The user config directory
follows each OS's convention, and can be overridden with the
GAMEIFY_NOTIFICATIONS_CONFIG_DIR environment variable (used by the test suite for
isolation).
"""

import json
import logging
import os
import sys
from pathlib import Path

log = logging.getLogger(__name__)

APP_ID = "gameify_notifications_overlay"
APP_NAME = "Gameify Notifications"

# D-Bus interfaces the Linux source watches.
NOTIFY_IFACE = "org.freedesktop.Notifications"
PORTAL_IFACE = "org.freedesktop.impl.portal.Notification"


def _user_config_base():
    if sys.platform.startswith("win"):
        return Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming")
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support"
    return Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")


def config_dir():
    override = os.environ.get("GAMEIFY_NOTIFICATIONS_CONFIG_DIR")
    return Path(override) if override else _user_config_base() / APP_ID


def rules_file():
    return config_dir() / "rules.toml"


def state_file():
    return config_dir() / "state.json"


def huds_dir():
    return config_dir() / "huds"


def sources_dir():
    return config_dir() / "sources"


def assets_dir():
    """Bundled, read-only assets shipped inside the package (e.g. HUD icons)."""
    return Path(__file__).resolve().parent / "assets"


def autostart_file():
    return _user_config_base() / "autostart" / f"{APP_ID}.desktop"


# --------------------------------------------------------------------------
# Default rules (TOML). Patterns are BEST GUESSES -- confirm with `--inspect`.
# --------------------------------------------------------------------------
DEFAULT_RULES = """\
# gameify_notifications_overlay rules
# ------------------------
# Each rule matches on the notifying app name (`app`, regex) and/or the
# notification text (`match`, regex over "summary | body"). Both are optional;
# an absent one is not a constraint. Rules are tested TOP-TO-BOTTOM and the
# FIRST match wins. A notification matching NO rule is IGNORED (allowlist).
#
#   weight = how much "damage" it adds. 0 = captured & listed in the panel, but
#            no redness (for noisy stuff you still want to see).
#
# Confirm what YOUR setup emits with `gameify_notifications --inspect`. How each install
# (Chrome vs snap vs Firefox) reports Teams/Outlook is documented in
# docs/notification-capture-ubuntu.md. These defaults target the recommended
# setup -- Teams + Outlook running in Chrome -- where the site origin shows up
# in the notification body (e.g. body == "teams.cloud.microsoft").

max_messages   = 10.0    # total weight at which the HUD is maxed (full red / empty shield);
                    # i.e. the unread-message budget. Raise it to make damage build slower.
max_alpha = 0.7     # opacity ceiling so the screen never goes fully opaque
dock_panel = true   # dock the dismiss panel under widget HUDs (halo/mario/pokemon/
                    # goldeneye): width follows the HUD, one move handle. false = a
                    # separate floating panel. (cod always uses a free panel.) Restart to apply.

# --- Per-HUD tuning (hot-reloaded; edits apply live while the HUD is shown) ---
# EVERY [hud.*] block also accepts these optional universal knobs (omit them to
# use the defaults shown); they let each overlay set its own capacity, drain, and
# default widget box size:
#   max_messages = 0     # this HUD's damage capacity; 0 = inherit global max_messages
#   weight_scale = 1.0   # drain-rate multiplier on notification weights (2.0 = 2x)
#   width  = 0           # default widget box width  px (0 = the HUD's built-in size)
#   height = 0           # default widget box height px (0 = the HUD's built-in size)
# (width/height apply to widget HUDs; the ⊕ button resets the box to this size.)
#
# Halo (shield + health bars):
[hud.halo]
shield_fraction  = 0.5    # share of `max_messages` allotted to the shield (rest = health)
health_red_at    = 0.5    # health turns red once it drops below this fraction
warning_at       = 0.25   # health fraction below which "WARNING" flashes
health_resolution = 2     # health-bar segments per health unit (higher = finer)

# Call of Duty (damage vignette):
[hud.cod]
clear_at_rest    = 0.85   # inner clear radius at 0 damage (1.0 = red only at the edge)
max_encroachment = 0.18   # inner clear radius at full damage (smaller = red creeps further in)
intensity        = 0.6    # peripheral-red opacity at full damage (cod ignores max_alpha)

# Mario (mushroom lives -- one mushroom per unit of max_messages, lost per damage):
[hud.mario]
# icon_path   = "/path/to/icon.png"   # default: bundled mushroom (transparent bg)
lost_opacity = 0.18   # opacity of a lost mushroom (0 = hide it entirely)
gap          = 0.12   # spacing between mushrooms (fraction of icon width)

# Pokemon (sprite + classic HP bar; HP = remaining health, green->yellow->red):
[hud.pokemon]
name         = "BULBASAUR"   # the name shown above the level
level        = 50            # 1-100
# icon_path  = "/path/to/sprite.png"   # default: bundled Bulbasaur (transparent bg)
green_above  = 0.70   # HP at/above this fraction -> green
yellow_above = 0.30   # HP at/above this -> yellow, below -> red

# GoldenEye (two facing arcs: left = health red->yellow, right = shield blue->cyan):
[hud.goldeneye]
shield_fraction = 0.5   # share of capacity given to the shield (drains first)
segments        = 9     # ticks per arc

# Stardew Valley (two vertical wood-framed bars: Energy "E" drains first, then
# Health "H"; each bar fills green->yellow->red by how full it is):
[hud.stardew]
shield_fraction = 0.5   # share of capacity given to the Energy bar (drains first)
green_above     = 0.70  # a bar at/above this fill -> green
yellow_above    = 0.30  # at/above this -> yellow, below -> red

# --- Microsoft Teams (Chrome: site origin appears in the body) ---
# Optional `focus_class`: a regex on the active window's WM_CLASS; when it
# matches, the notification is dropped (you're already looking at that app).
# Find yours with `xprop WM_CLASS` (Chrome PWAs are 'crx_<app-id>'), e.g.:
#   focus_class = 'crx_ompifgpmddkgmclendfeacglnodjjndh'
[[rule]]
name   = "Teams message"
match  = 'teams\\.cloud\\.microsoft|teams\\.microsoft\\.com'
weight = 1.5

# --- Microsoft Outlook (Chrome: site origin appears in the body) ---
[[rule]]
name   = "Outlook email"
match  = 'outlook\\.(cloud\\.microsoft|office\\.com|office365\\.com)'
weight = 0.5        # mild -- a few unread emails become noticeable

# --- Alternatives for other installs (uncomment if you use them) ---
# snap teams-for-linux reports app name "teams-for-linux" (real message in body):
# [[rule]]
# name   = "Teams message"
# app    = "teams-for-linux"
# weight = 1.5
#
# Firefox-delivered Outlook uses summary "Outlook":
# [[rule]]
# name   = "Outlook email"
# match  = '^Outlook\\b'
# weight = 0.5
"""

# Custom-HUD template dropped into huds/ on first run (QPainter-based).
EXAMPLE_HUD = '''\
"""Example custom HUD (QPainter). Rename this file to *.py to enable it.

The loader injects Hud, HudContext, math, and the Qt drawing types
(QPainter, QColor, QPen, QBrush, QFont, QRadialGradient, Qt, QRectF, QPointF)
into this module, so you do not need to import them.
"""


class PulseHud(Hud):
    name = "pulse"
    label = "Simple pulsing border"
    scope = "all"           # "all" (every monitor, click-through) or "widget" (movable)
    size = (640, 160)

    def draw(self, p, w, h, ctx):
        frac = self.fraction(ctx)
        if frac <= 0.0:
            return
        pulse = 0.5 + 0.5 * math.sin(ctx.now * 3.0)
        alpha = int(min(ctx.max_alpha, frac * ctx.max_alpha * (0.6 + 0.4 * pulse)) * 255)
        pen = QPen(QColor(255, 115, 0, alpha))
        pen.setWidth(24)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        p.drawRect(12, 12, w - 24, h - 24)

    def is_animating(self, ctx):
        return self.fraction(ctx) > 0.0
'''


# Custom-source template dropped into sources/ on first run.
EXAMPLE_SOURCE = '''\
"""Example custom notification source. Rename this file to *.py to enable it,
then run: `gameify_notifications --source mysource`. The loader injects NotificationSource
into this module, so you don't need to import it.

A source captures notifications however it likes (D-Bus, a log file, a socket,
a browser-extension bridge, ...) and calls callback(app_name, summary, body)
for each one. It may run on a background thread.
"""

import threading
import time


class MySource(NotificationSource):
    name = "mysource"

    def __init__(self, match):
        self.match = match
        self._stop = False

    def start(self, callback):
        def run():
            while not self._stop:
                # ... detect a notification, then:
                # callback("Microsoft Teams", "Summary", "Body text")
                time.sleep(1)
        threading.Thread(target=run, daemon=True).start()

    def stop(self):
        self._stop = True

    def describe(self):
        return "my custom source"
'''


# --------------------------------------------------------------------------
# Live config writeback (GUI settings -> rules.toml)
# --------------------------------------------------------------------------
def set_config_value(keys, value):
    """Set rules.toml at the nested `keys` path to `value`, preserving the
    user's comments, ordering, and formatting (round-trip via tomlkit), then
    write atomically so the hot-reloader never sees a half-written file.

    `keys` is a path list: ["max_messages"] for a top-level key, or
    ["hud", "halo", "shield_fraction"] for a nested table. Intermediate tables
    are created as needed. This is how the Settings GUI edits the same file the
    user can hand-edit -- both flow through rules.toml + the existing reload."""
    # `hud` is the table namespace for per-HUD tuning ([hud.<name>]). Writing a
    # scalar to it (the old active-HUD bug) silently overwrites that whole table
    # and wipes every HUD's saved params -- refuse it. Use ["active_hud"] for the
    # launch selection, or ["hud", "<name>", "<knob>"] for a HUD's tuning.
    if keys == ["hud"]:
        raise ValueError(
            "refusing to write a scalar to the 'hud' table namespace (would clobber "
            "all per-HUD tuning); use ['active_hud'] for the launch selection")
    import tomlkit                                   # lazy: only writers need it
    path = rules_file()
    config_dir().mkdir(parents=True, exist_ok=True)
    text = path.read_text() if path.exists() else DEFAULT_RULES
    doc = tomlkit.parse(text)
    node = doc
    for k in keys[:-1]:
        if k not in node or not isinstance(node.get(k), dict):
            node[k] = tomlkit.table()
        node = node[k]
    node[keys[-1]] = value
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(tomlkit.dumps(doc))
    tmp.replace(path)                                # atomic on POSIX


def get_config_value(keys, default=None):
    """Read rules.toml at the nested `keys` path, returning `default` if the file
    is absent, unreadable, or the path doesn't exist. The read-side counterpart
    of set_config_value -- e.g. get_config_value(["active_hud"]) for the
    last-selected HUD remembered across sessions."""
    try:
        import tomllib
    except ModuleNotFoundError:  # pragma: no cover
        return default
    path = rules_file()
    try:
        node = tomllib.loads(path.read_text() if path.exists() else DEFAULT_RULES)
    except Exception:
        return default
    for k in keys:
        if not isinstance(node, dict) or k not in node:
            return default
        node = node[k]
    return node


def reset_hud(name):
    """Remove the [hud.<name>] table from rules.toml so that HUD reverts to its
    built-in defaults (the Settings 'Reset to defaults' button). Preserves the
    rest of the file (other HUDs, rules, comments). No-op if absent."""
    import tomlkit
    path = rules_file()
    if not path.exists():
        return
    doc = tomlkit.parse(path.read_text())
    hud = doc.get("hud")
    if isinstance(hud, dict) and name in hud:
        del hud[name]
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(tomlkit.dumps(doc))
        tmp.replace(path)


# --------------------------------------------------------------------------
# State persistence (window geometry, collapsed flag, ...)
# --------------------------------------------------------------------------
def load_state(key):
    """Load whatever JSON value is stored under `key` in state.json."""
    try:
        data = json.loads(state_file().read_text())
        if isinstance(data, dict):
            return data.get(key)
    except Exception:
        pass
    return None


def save_state(key, value):
    """Persist `value` under `key`, merging with other windows' saved state."""
    try:
        config_dir().mkdir(parents=True, exist_ok=True)
        data = {}
        if state_file().exists():
            try:
                data = json.loads(state_file().read_text())
            except Exception:
                data = {}
        if not isinstance(data, dict):
            data = {}
        data[key] = value
        state_file().write_text(json.dumps(data))
    except OSError:
        log.warning("could not save state key %r", key, exc_info=True)


def load_rect(key):
    """Load an absolute [x, y, w, h] rect stored under `key`."""
    v = load_state(key)
    if isinstance(v, list) and len(v) == 4:
        return [int(n) for n in v]
    return None


def save_rect(key, rect):
    save_state(key, [int(n) for n in rect])


# --------------------------------------------------------------------------
# First-run scaffolding + autostart
# --------------------------------------------------------------------------
def ensure_config():
    config_dir().mkdir(parents=True, exist_ok=True)
    huds_dir().mkdir(parents=True, exist_ok=True)
    sources_dir().mkdir(parents=True, exist_ok=True)
    if not rules_file().exists():
        rules_file().write_text(DEFAULT_RULES)
    hud_example = huds_dir() / "example_pulse.py.txt"
    if not hud_example.exists():
        hud_example.write_text(EXAMPLE_HUD)
    src_example = sources_dir() / "example_source.py.txt"
    if not src_example.exists():
        src_example.write_text(EXAMPLE_SOURCE)


def install_autostart():
    if not sys.platform.startswith("linux"):
        print("Autostart auto-install is implemented for Linux only. On Windows, "
              "add a shortcut to shell:startup; on macOS, use a LaunchAgent.",
              file=sys.stderr)
        return
    path = autostart_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    exec_line = f"{sys.executable} -m gameify_notifications"
    path.write_text(
        "[Desktop Entry]\n"
        "Type=Application\n"
        f"Name={APP_NAME}\n"
        "Comment=Desktop notifications as a videogame HUD\n"
        f"Exec={exec_line}\n"
        "Terminal=false\n"
        "X-GNOME-Autostart-enabled=true\n"
    )
    print(f"Installed autostart entry: {path}\n  Exec={exec_line}")


def uninstall_autostart():
    path = autostart_file()
    if path.exists():
        path.unlink()
        print(f"Removed autostart entry: {path}")
    else:
        print("No autostart entry installed.")
