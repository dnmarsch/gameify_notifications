"""Wires the App + NotificationSource to the Qt windows and runs the event loop.

The notification source may fire on a background thread, so it's bridged onto
the Qt UI thread via a queued signal."""

import logging
import signal
import sys

from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtWidgets import QApplication

from ...backends import OverlayBackend
from ...logsetup import install_qt_message_handler

log = logging.getLogger(__name__)
from .overlay_window import OverlayWindow
from .panel_window import PanelWindow
from .widget_window import WidgetWindow

_TEST_SAMPLES = [
    ("Microsoft Teams", "Alice Smith", "hey are you around?"),
    ("Microsoft Teams", "Engineering channel", "posted in the Engineering channel"),
    ("Microsoft Teams", "Bob Jones", "Bob Jones started a meeting"),
    ("Microsoft Teams", "Carol", "Carol is calling you"),
    ("Microsoft Teams", "Dave", "incoming call from Dave"),
]


class _Bridge(QObject):
    received = Signal(str, str, str, object)   # app, summary, body, close-callable|None


class QtOverlayBackend(OverlayBackend):
    def run(self, app, source):
        return run_qt(app, source)


def make_hud_window(app, monitors_provider=None):
    """Build the HUD window for the active HUD's scope (factored out for tests)."""
    if getattr(app.hud, "scope", "all") == "widget":
        return WidgetWindow(app, monitors_provider=monitors_provider)
    return OverlayWindow(app, monitors_provider=monitors_provider)


def _build_windows(app):
    """The HUD window (scope-dependent) and the dismiss panel."""
    return make_hud_window(app), PanelWindow(app)


def _wire_repaint(app, hud_win):
    """A ~30fps timer that repaints the HUD while it wants animation, and a
    state observer that wakes it on every damage change. Returns the timer."""
    timer = QTimer()
    timer.setInterval(33)  # ~30fps

    def tick():
        hud_win.update()
        if not app.hud.is_animating(hud_win.context()):
            timer.stop()

    timer.timeout.connect(tick)

    def on_state(_kind):
        # the panel refreshes itself (it subscribes too); here we drive the HUD
        hud_win.update()
        if not timer.isActive():
            timer.start()

    app.state.subscribe(on_state)
    return timer


def _wire_capture(app, source):
    """Marshal the (possibly background-thread) notification source onto the UI
    thread via a queued signal. Returns the bridge (kept alive by the caller)."""
    bridge = _Bridge()
    bridge.received.connect(app.on_notification)  # cross-thread => Qt.QueuedConnection
    if source is not None and not app.test_mode:
        try:
            source.start(lambda a, s, t, close=None: bridge.received.emit(a, s, t, close))
            log.info("capturing via %s", source.describe())
        except Exception:  # noqa: BLE001
            log.exception("failed to start notification source")
    return bridge


def _wire_screen_changes(hud_win):
    """Re-place the all-monitor overlay when monitors are added/removed."""
    appins = QApplication.instance()
    if not hasattr(hud_win, "place"):
        return
    for name in ("screenAdded", "screenRemoved", "primaryScreenChanged"):
        sig = getattr(appins, name, None)
        if sig is not None:
            try:
                sig.connect(lambda *_: (hud_win.place(), hud_win.update()))
            except Exception:
                pass


def _wire_config_watch(app, hud_win, panel=None):
    """Poll rules.toml ~2x/sec; when it changes on disk, repaint the HUD and
    refresh the panel so live edits to [hud.*] tuning / full_at apply immediately
    to BOTH (e.g. a max_messages change updates the overlay and the damage %).
    Returns the timer (kept alive by the caller)."""
    watch = QTimer()
    watch.setInterval(500)

    def poll():
        if app.rules.reload():        # mtime-gated; True only when the file changed
            hud_win.update()
            if panel is not None:
                panel.refresh()

    watch.timeout.connect(poll)
    watch.start()
    return watch


def _make_test_injector(app):
    """Inject fake notifications every 2s in --test mode (or None otherwise)."""
    if not app.test_mode:
        return None
    seq = {"i": 0}
    injector = QTimer()
    injector.setInterval(2000)

    def inject():
        a, s, t = _TEST_SAMPLES[seq["i"] % len(_TEST_SAMPLES)]
        seq["i"] += 1
        app.on_notification(a, s, t)
        if seq["i"] >= 12:
            injector.stop()

    injector.timeout.connect(inject)
    injector.start()
    log.info("test mode: injecting fake notifications every 2s")
    return injector


def _install_sigint(qapp):
    """Let Python service Ctrl-C during the Qt loop (needs a periodic timer to
    return control to the interpreter). Returns the heartbeat timer."""
    signal.signal(signal.SIGINT, lambda *_: qapp.quit())
    heartbeat = QTimer()
    heartbeat.setInterval(200)
    heartbeat.timeout.connect(lambda: None)
    heartbeat.start()
    return heartbeat


def run_qt(app, source):
    qapp = QApplication.instance() or QApplication(sys.argv[:1])
    install_qt_message_handler()
    scope = getattr(app.hud, "scope", "all")
    log.info("Qt backend starting hud=%s (%s) scope=%s test_mode=%s",
             app.hud.name, app.hud.label, scope, app.test_mode)

    hud_win, panel = _build_windows(app)
    windows = [hud_win, panel]
    timer = _wire_repaint(app, hud_win)
    bridge = _wire_capture(app, source)
    _wire_screen_changes(hud_win)
    watch = _wire_config_watch(app, hud_win, panel)
    injector = _make_test_injector(app)

    for w in windows:
        w.show()

    # keep Python objects alive for the app's lifetime
    heartbeat = _install_sigint(qapp)
    qapp._cod_refs = (windows, timer, bridge, injector, heartbeat, watch)

    return qapp.exec()
