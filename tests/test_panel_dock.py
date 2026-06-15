"""Docked dismiss panel: the pure HUD-rect -> panel-rect mapping, and the live
PanelDock coupling (panel follows the HUD, width syncs with a readable minimum,
height is preserved, dragging the panel moves the HUD)."""

from PySide6.QtCore import QPoint

from gameify_notifications.backends.qt.panel_dock import dock_rect, PanelDock, MIN_WIDTH
from gameify_notifications.backends.qt.widget_window import WidgetWindow
from gameify_notifications.backends.qt.panel_window import PanelWindow


# ---- pure geometry --------------------------------------------------------
def test_dock_rect_wide_hud_matches_width():
    # HUD wider than the minimum -> panel matches its width, flush underneath
    assert dock_rect([100, 50, 560, 200], 180) == [100, 250, 560, 180]


def test_dock_rect_narrow_hud_uses_min_width_left_aligned():
    # HUD narrower than MIN_WIDTH -> panel widens to the minimum, left-aligned
    x, y, w, h = dock_rect([100, 50, 240, 240], 150)
    assert w == MIN_WIDTH and x == 100 and y == 290 and h == 150


def test_dock_rect_preserves_panel_height():
    assert dock_rect([0, 0, 400, 100], 321)[3] == 321


# ---- live coupling --------------------------------------------------------
def _docked(qtbot, make_app, single_monitor, hud="halo"):
    app = make_app(hud)
    hud_win = WidgetWindow(app, monitors_provider=single_monitor)
    panel = PanelWindow(app, monitors_provider=single_monitor)
    qtbot.addWidget(hud_win)
    qtbot.addWidget(panel)
    hud_win.setGeometry(200, 100, 560, 200)        # geometry() updates synchronously
    panel.resize(560, 150)
    dock = PanelDock(hud_win, panel)               # ctor sync()s the panel under the HUD
    return app, hud_win, panel, dock


def test_panel_starts_docked_under_hud(qtbot, make_app, single_monitor):
    _app, _hud, panel, _dock = _docked(qtbot, make_app, single_monitor)
    g = panel.geometry()
    assert (g.x(), g.y(), g.width()) == (200, 300, 560)   # flush below, width synced


def test_panel_follows_hud_on_geometry_change(qtbot, make_app, single_monitor):
    _app, hud_win, panel, _dock = _docked(qtbot, make_app, single_monitor)
    hud_win.setGeometry(400, 120, 600, 220)
    hud_win.geometryChanged.emit()                 # the signal WidgetWindow fires on move/resize
    g = panel.geometry()
    assert (g.x(), g.y(), g.width()) == (400, 340, 600)


def test_panel_width_floors_at_min_for_narrow_hud(qtbot, make_app, single_monitor):
    _app, hud_win, panel, _dock = _docked(qtbot, make_app, single_monitor, hud="goldeneye")
    hud_win.setGeometry(50, 50, 240, 240)          # narrower than MIN_WIDTH
    hud_win.geometryChanged.emit()
    g = panel.geometry()
    assert g.width() == MIN_WIDTH and g.x() == 50   # readable minimum, left-aligned


def test_reassert_width_snaps_back_keeps_height(qtbot, make_app, single_monitor):
    _app, _hud, panel, dock = _docked(qtbot, make_app, single_monitor)
    panel.setGeometry(panel.x(), panel.y(), 900, 320)   # as if a grip drag widened it
    dock.reassert_width()
    assert panel.width() == 560 and panel.height() == 320  # width snapped, height kept


def test_dragging_panel_moves_the_hud(qtbot, make_app, single_monitor):
    _app, hud_win, _panel, dock = _docked(qtbot, make_app, single_monitor)
    dock.move_hud(hud_win.frameGeometry().topLeft() + QPoint(30, 40))
    assert (hud_win.x(), hud_win.y()) == (230, 140)


def test_widget_emits_geometry_changed_on_resize(qtbot, make_app, single_monitor):
    w = WidgetWindow(make_app("halo"), monitors_provider=single_monitor)
    qtbot.addWidget(w)
    w.show()                                   # hidden widgets don't get resize events
    qtbot.waitExposed(w)
    with qtbot.waitSignal(w.geometryChanged, timeout=1000):
        w.resize(480, 220)
