"""Factory coverage: backend selection and HUD-window scope routing."""

from gameify_notifications.backends import select_backend
from gameify_notifications.backends.qt.backend import QtOverlayBackend, make_hud_window
from gameify_notifications.backends.qt.overlay_window import OverlayWindow
from gameify_notifications.backends.qt.widget_window import WidgetWindow


def test_select_backend_returns_qt():
    assert isinstance(select_backend(), QtOverlayBackend)


def test_make_hud_window_routes_by_scope(qtbot, make_app):
    cod = make_hud_window(make_app("cod"))      # scope = "all"
    qtbot.addWidget(cod)
    assert isinstance(cod, OverlayWindow)

    halo = make_hud_window(make_app("halo"))    # scope = "widget"
    qtbot.addWidget(halo)
    assert isinstance(halo, WidgetWindow)
