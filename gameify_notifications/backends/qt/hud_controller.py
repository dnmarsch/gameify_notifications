"""Owns both HUD windows and switches the active HUD live.

Both window types are built once: the all-monitor click-through `OverlayWindow`
(for scope='all' HUDs like cod) and the movable `WidgetWindow` (for the widget
HUDs). Switching HUD just toggles which one is shown -- no teardown/rebuild:
widget<->widget is an instant repaint; cod<->widget flips visibility and
docks/undocks the panel. The repaint timer and damage observer always act on
whichever window is currently active."""

from PySide6.QtCore import QTimer


class HudController:
    def __init__(self, app, widget_win, overlay_win, panel, huds, dock=None):
        self.app = app
        self.widget_win = widget_win
        self.overlay_win = overlay_win
        self.panel = panel
        self.huds = huds              # name -> Hud instance (the switchable registry)
        self.dock = dock              # PanelDock(widget_win, panel), or None if disabled
        # parent the timer to the panel so it dies with the windows (no orphan
        # timer ticking update() on a deleted window after teardown)
        self._timer = QTimer(panel)
        self._timer.setInterval(33)   # ~30fps; only ticks while the HUD animates
        self._timer.timeout.connect(self._tick)
        app.state.subscribe(self._on_state)
        self.set_hud(app.hud.name)    # place the initial window

    def active(self):
        """The currently-visible HUD window for the active HUD's scope."""
        scope = getattr(self.app.hud, "scope", "all")
        return self.overlay_win if scope == "all" else self.widget_win

    def set_hud(self, name):
        """Switch the active HUD live. Shows the matching window, hides the other,
        and docks/undocks the panel. Returns True if `name` is a known HUD."""
        hud = self.huds.get(name)
        if hud is None:
            return False
        self.app.hud = hud
        if getattr(hud, "scope", "all") == "widget":
            self.widget_win.apply_min_size()         # the new HUD may allow a smaller box
            self.overlay_win.hide()
            if self.dock is not None:
                self.panel.set_dock(self.dock)   # re-dock under the widget
                self.dock.sync()
            self.widget_win.show()
        else:
            self.widget_win.hide()
            if self.dock is not None:
                self.panel.set_dock(None)        # cod: the panel floats free
            self.overlay_win.show()
        self.active().update()
        return True

    def refresh(self):
        """Repaint the active HUD + refresh the panel (e.g. after a config edit)."""
        self.active().update()
        self.panel.refresh()

    def apply_size(self):
        """Resize the widget HUD to its configured width/height now (live effect
        when those sliders move); re-syncs the dock. No-op visually for cod."""
        w, h = self.app.hud.configured_size(self.app.rules.params_for(self.app.hud.name))
        self.widget_win.resize(int(w), int(h))
        if self.dock is not None:
            self.dock.sync()

    # ---- repaint loop (always drives the active window) ------------------
    def _tick(self):
        win = self.active()
        win.update()
        if not self.app.hud.is_animating(win.context()):
            self._timer.stop()

    def _on_state(self, _kind):
        self.active().update()
        if not self._timer.isActive():
            self._timer.start()
