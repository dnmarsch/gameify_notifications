"""gameify_notifications_overlay: turn Teams notifications into a videogame HUD.

Layered for single responsibility and cross-platform portability:

    config    paths, rules file, state persistence, autostart   (stdlib only)
    geometry  monitor math, off-screen clamp, fractional rescale (stdlib only)
    rules     notification -> (category, damage weight)          (stdlib only)
    state     accumulated "damage" + observers                   (stdlib only)
    app       platform-agnostic application context              (stdlib only)
    huds/     QPainter HUD renderers (CoD, Halo) + plugin loader  (needs Qt)
    sources/  NotificationSource ABC + D-Bus (Linux) / WinRT      (needs gi/winrt)
    backends/ OverlayBackend ABC + Qt windows                     (needs Qt)

The core (config/geometry/rules/state/app) imports no GUI toolkit, so it is
unit-testable on its own; only the huds/ and backends/qt/ layers require Qt.
"""

import logging as _logging

# Library best practice: a NullHandler so logging is silent until the app calls
# logsetup.setup_logging(). Child loggers (gameify_notifications.*) propagate up to here.
_logging.getLogger("gameify_notifications").addHandler(_logging.NullHandler())

__version__ = "0.2.0"
