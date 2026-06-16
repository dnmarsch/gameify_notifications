"""The Qt backend's run_qt() helpers. run_qt() itself blocks on the Qt event
loop, so it isn't unit-tested; the extracted single-responsibility helpers are.
(Window toggling / live HUD switch lives in test_hud_controller.py.)"""

import os
import time

from gameify_notifications.backends.qt import backend
from gameify_notifications.backends.qt.overlay_window import OverlayWindow
from gameify_notifications.backends.qt.widget_window import WidgetWindow


def test_make_hud_window_picks_scope(qapp, make_app):
    assert isinstance(backend.make_hud_window(make_app("cod")), OverlayWindow)
    assert isinstance(backend.make_hud_window(make_app("halo")), WidgetWindow)


def test_test_injector_only_in_test_mode(qapp, make_app):
    assert backend._make_test_injector(make_app("cod", test_mode=False)) is None
    inj = backend._make_test_injector(make_app("cod", test_mode=True))
    assert inj is not None and inj.isActive()
    inj.stop()


def _touch_rules():
    from gameify_notifications import config
    path = config.rules_file()
    path.write_text(path.read_text() + "\n# live edit\n")
    os.utime(path, (time.time() + 10, time.time() + 10))   # force a distinct mtime


def test_config_watch_calls_on_change_only_when_file_changes(qapp, make_app):
    app = make_app("cod")
    app.rules.reload(force=True)                      # sync mtime to the file
    calls = []
    watch = backend._wire_config_watch(app, lambda: calls.append(1))
    assert watch.isActive()

    watch.timeout.emit()                              # unchanged file
    assert calls == []                                # -> no callback

    _touch_rules()
    watch.timeout.emit()                              # changed file
    assert calls == [1]                               # -> on_change fired once
    watch.stop()
