"""The Qt backend's run_qt() helpers. run_qt() itself blocks on the Qt event
loop, so it isn't unit-tested; the extracted single-responsibility helpers are.
Uses pytest-qt's `qapp` + the offscreen platform."""

import os
import time

import pytest

from gameify_notifications.backends.qt import backend
from gameify_notifications.backends.qt.overlay_window import OverlayWindow
from gameify_notifications.backends.qt.widget_window import WidgetWindow


def test_make_hud_window_picks_scope(qapp, make_app):
    # NB: overlay + widget take different monitors_provider contracts, so let
    # each use its default; the offscreen platform supplies one screen.
    cod_app = make_app("cod")        # scope "all"   -> overlay
    halo_app = make_app("halo")      # scope "widget" -> movable widget
    assert isinstance(backend.make_hud_window(cod_app), OverlayWindow)
    assert isinstance(backend.make_hud_window(halo_app), WidgetWindow)


def test_build_windows_returns_hud_and_panel(qapp, make_app):
    from gameify_notifications.backends.qt.panel_window import PanelWindow
    hud_win, panel = backend._build_windows(make_app("halo"))
    assert isinstance(hud_win, WidgetWindow)          # halo -> widget
    assert isinstance(panel, PanelWindow)


def test_dock_created_for_widget_hud_when_enabled(qapp, make_app):
    from gameify_notifications.backends.qt.panel_dock import PanelDock
    app = make_app("halo")                          # widget scope
    hud_win, panel = backend._build_windows(app)
    assert app.rules.dock_panel is True             # shipped default
    assert isinstance(backend._wire_dock(app, hud_win, panel), PanelDock)


def test_no_dock_for_cod_or_when_disabled(qapp, make_app):
    cod_app = make_app("cod")                        # all-monitor overlay -> never docks
    cod_hud, cod_panel = backend._build_windows(cod_app)
    assert backend._wire_dock(cod_app, cod_hud, cod_panel) is None

    halo = make_app("halo")
    halo.rules.dock_panel = False                    # toggled off
    h_hud, h_panel = backend._build_windows(halo)
    assert backend._wire_dock(halo, h_hud, h_panel) is None


def test_test_injector_only_in_test_mode(qapp, make_app):
    assert backend._make_test_injector(make_app("cod", test_mode=False)) is None
    inj = backend._make_test_injector(make_app("cod", test_mode=True))
    assert inj is not None and inj.isActive()
    inj.stop()


def test_repaint_timer_starts_on_damage(qapp, make_app):
    app = make_app("cod", test_mode=True)
    _hud, _panel = backend._build_windows(app)
    timer = backend._wire_repaint(app, _hud)
    assert not timer.isActive()                       # idle until damage
    # body carries the site origin the shipped Teams rule matches on
    app.on_notification("Google Chrome", "Carol", "teams.cloud.microsoft")
    assert timer.isActive()                           # state observer woke it
    timer.stop()


class _FakeWin:
    def __init__(self):
        self.updates = 0

    def update(self):
        self.updates += 1


class _FakePanel:
    def __init__(self):
        self.refreshes = 0

    def refresh(self):
        self.refreshes += 1


def _touch_rules():
    from gameify_notifications import config
    path = config.rules_file()
    path.write_text(path.read_text() + "\n# live edit\n")
    os.utime(path, (time.time() + 10, time.time() + 10))   # force a distinct mtime


def test_config_watch_updates_hud_and_panel_only_when_file_changes(qapp, make_app):
    app = make_app("cod")
    app.rules.reload(force=True)                      # sync mtime to the file
    win, panel = _FakeWin(), _FakePanel()
    watch = backend._wire_config_watch(app, win, panel)
    assert watch.isActive()

    watch.timeout.emit()                              # unchanged file
    assert win.updates == 0 and panel.refreshes == 0  # -> nothing

    _touch_rules()
    watch.timeout.emit()                              # changed file
    assert win.updates == 1 and panel.refreshes == 1  # -> HUD repaints AND panel refreshes
    watch.stop()


def test_config_watch_panel_is_optional(qapp, make_app):
    # the helper still works HUD-only (no panel) -- used by other call paths/tests
    app = make_app("cod")
    app.rules.reload(force=True)
    win = _FakeWin()
    watch = backend._wire_config_watch(app, win)      # no panel arg
    _touch_rules()
    watch.timeout.emit()
    assert win.updates == 1                           # no crash without a panel
    watch.stop()
