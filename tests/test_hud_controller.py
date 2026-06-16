"""HudController: both HUD windows built once, the active one toggled live.
Same-scope swaps are instant; cod<->widget flips visibility and docks/undocks
the panel; the repaint timer wakes on damage."""

import pytest

from gameify_notifications.huds import load_huds
from gameify_notifications.backends.qt.hud_controller import HudController
from gameify_notifications.backends.qt.overlay_window import OverlayWindow
from gameify_notifications.backends.qt.widget_window import WidgetWindow
from gameify_notifications.backends.qt.panel_window import PanelWindow
from gameify_notifications.backends.qt.panel_dock import PanelDock


def _controller(qtbot, make_app, single_monitor, hud="halo", dock=True):
    app = make_app(hud)
    widget = WidgetWindow(app, monitors_provider=single_monitor)
    overlay = OverlayWindow(app)        # overlay wants a bare-list provider; default is fine offscreen
    panel = PanelWindow(app, monitors_provider=single_monitor)
    for w in (widget, overlay, panel):
        qtbot.addWidget(w)
    pd = PanelDock(widget, panel) if dock else None
    panel.show()
    ctl = HudController(app, widget, overlay, panel, load_huds(), pd)
    return app, ctl, widget, overlay, panel, pd


def test_initial_widget_hud_shows_widget_hides_overlay(qtbot, make_app, single_monitor):
    app, ctl, widget, overlay, panel, pd = _controller(qtbot, make_app, single_monitor, "halo")
    assert ctl.active() is widget
    assert widget.isVisible() and not overlay.isVisible()
    assert panel._dock is pd                          # docked under the widget


def test_initial_cod_shows_overlay_floats_panel(qtbot, make_app, single_monitor):
    app, ctl, widget, overlay, panel, pd = _controller(qtbot, make_app, single_monitor, "cod")
    assert ctl.active() is overlay
    assert overlay.isVisible() and not widget.isVisible()
    assert panel._dock is None                        # cod -> panel floats free


def test_switching_hud_updates_widget_min_size(qtbot, make_app, single_monitor):
    # halo's floor is the default 140px; switching to Stardew lowers it to 74px
    app, ctl, widget, overlay, panel, pd = _controller(qtbot, make_app, single_monitor, "halo")
    assert widget.minimumWidth() == 140
    ctl.set_hud("stardew")
    assert widget.minimumWidth() == 74


def test_same_scope_swap_is_instant(qtbot, make_app, single_monitor):
    app, ctl, widget, overlay, panel, pd = _controller(qtbot, make_app, single_monitor, "halo")
    ctl.set_hud("mario")
    assert app.hud.name == "mario"
    assert ctl.active() is widget                     # same window, just new content
    assert widget.isVisible() and not overlay.isVisible()
    assert panel._dock is pd                          # still docked


def test_cross_scope_swap_toggles_windows_and_dock(qtbot, make_app, single_monitor):
    app, ctl, widget, overlay, panel, pd = _controller(qtbot, make_app, single_monitor, "halo")
    ctl.set_hud("cod")                                # widget -> overlay
    assert app.hud.name == "cod" and ctl.active() is overlay
    assert overlay.isVisible() and not widget.isVisible()
    assert panel._dock is None                        # undocked for cod
    ctl.set_hud("goldeneye")                          # overlay -> widget
    assert ctl.active() is widget
    assert widget.isVisible() and not overlay.isVisible()
    assert panel._dock is pd                          # re-docked


def test_unknown_hud_is_ignored(qtbot, make_app, single_monitor):
    app, ctl, *_ = _controller(qtbot, make_app, single_monitor, "halo")
    assert ctl.set_hud("nope") is False and app.hud.name == "halo"


def test_no_dock_when_disabled(qtbot, make_app, single_monitor):
    app, ctl, widget, overlay, panel, pd = _controller(qtbot, make_app, single_monitor,
                                                        "halo", dock=False)
    assert pd is None and panel._dock is None         # widget HUD but docking off


def test_repaint_timer_starts_on_damage(qtbot, make_app, single_monitor):
    app, ctl, *_ = _controller(qtbot, make_app, single_monitor, "cod")
    assert not ctl._timer.isActive()
    app.on_notification("Google Chrome", "Carol", "teams.cloud.microsoft")
    assert ctl._timer.isActive()                      # observer woke the repaint loop
    ctl._timer.stop()


def test_refresh_repaints_and_refreshes_panel(qtbot, make_app, single_monitor):
    app, ctl, widget, overlay, panel, pd = _controller(qtbot, make_app, single_monitor, "halo")
    app.on_notification("Google Chrome", "Carol", "teams.cloud.microsoft")
    ctl.refresh()                                     # must not raise; panel reflects damage
    assert "%" in panel.status.text()
