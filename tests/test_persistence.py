"""QtPersistent: off-screen-safe restore, fractional rescale on a (simulated)
resolution change, and the collapse size-freeze. Monitor info is injected so the
tests are deterministic and never touch real screens."""

from PySide6.QtCore import QRect
from PySide6.QtWidgets import QWidget

from gameify_notifications import config
from gameify_notifications.geometry import (Rect, frac_rect_centered, frac_top_centered,
                                  default_panel_rect, top_center_rect)
from gameify_notifications.backends.qt.persistence import QtPersistent

_ONE = [Rect(0, 0, 1920, 1080)]


def test_relative_rescale_on_resolution_change(qtbot, monkeypatch):
    w = QWidget()
    qtbot.addWidget(w)
    mon = {"wa": [Rect(0, 0, 1920, 1080)], "pr": 0}
    provider = lambda: (mon["wa"], mon["pr"])
    p = QtPersistent(w, "hud", lambda wa, pr: frac_rect_centered(wa, pr, 0.5, 0.5),
                     relative=True, monitors_provider=provider)

    # store a 50% x 50% rect on the 1920x1080 monitor
    p._serialize([480, 270, 960, 540])

    # spy on geometry application, then "shrink the monitor"
    applied = []
    monkeypatch.setattr(w, "setGeometry",
                        lambda x, y, ww, hh: applied.append((x, y, ww, hh)))
    mon["wa"] = [Rect(0, 0, 1280, 720)]
    p.on_monitors_changed()

    assert applied, "monitor change should re-apply geometry"
    _, _, ww, hh = applied[-1]
    assert ww == 640 and hh == 360          # still 50% x 50% of the new resolution


def test_offscreen_restore_snaps_back(qtbot):
    w = QWidget()
    qtbot.addWidget(w)
    provider = lambda: ([Rect(0, 0, 1920, 1080)], 0)
    # a saved panel rect way off any screen
    config.save_rect("panel", [9000, 9000, 360, 440])
    QtPersistent(w, "panel", default_panel_rect, relative=False,
                 monitors_provider=provider)
    g = w.geometry()
    # snapped back onto the monitor (top-right default region)
    assert 0 <= g.x() < 1920 and 0 <= g.y() < 1080


def test_center_uses_injected_top_center_fn(qtbot, monkeypatch):
    w = QWidget()
    qtbot.addWidget(w)
    provider = lambda: (_ONE, 0)
    p = QtPersistent(w, "hud",
                     lambda wa, pr: frac_top_centered(wa, pr, 0.33, 0.16),
                     relative=True, monitors_provider=provider,
                     center_fn=top_center_rect)
    monkeypatch.setattr(w, "geometry", lambda: QRect(40, 50, 640, 170))
    placed = []
    monkeypatch.setattr(w, "setGeometry", lambda x, y, ww, hh: placed.append((x, y, ww, hh)))
    p.center()
    assert placed, "center() should reposition the window"
    x, y, ww, hh = placed[-1]
    assert x == (1920 - 640) // 2       # horizontally centered
    assert y <= 12                      # near the TOP, not vertically centered
    assert (ww, hh) == (640, 170)       # size unchanged when no size passed


def test_center_defaults_to_center_center(qtbot, monkeypatch):
    w = QWidget()
    qtbot.addWidget(w)
    provider = lambda: (_ONE, 0)
    # no center_fn -> default is center_rect (vertically centered)
    p = QtPersistent(w, "panel", default_panel_rect, relative=False,
                     monitors_provider=provider)
    monkeypatch.setattr(w, "geometry", lambda: QRect(0, 0, 640, 170))
    placed = []
    monkeypatch.setattr(w, "setGeometry", lambda x, y, ww, hh: placed.append((x, y, ww, hh)))
    p.center()
    x, y, _ww, _hh = placed[-1]
    assert x == (1920 - 640) // 2 and y == (1080 - 170) // 2   # center-center


def test_center_with_size_resets_dimensions(qtbot, monkeypatch):
    w = QWidget()
    qtbot.addWidget(w)
    provider = lambda: (_ONE, 0)
    p = QtPersistent(w, "hud",
                     lambda wa, pr: frac_top_centered(wa, pr, 0.33, 0.16),
                     relative=True, monitors_provider=provider, center_fn=top_center_rect)
    monkeypatch.setattr(w, "geometry", lambda: QRect(40, 50, 123, 456))
    placed = []
    monkeypatch.setattr(w, "setGeometry", lambda x, y, ww, hh: placed.append((x, y, ww, hh)))
    p.center((300, 320))                                  # ⊕ reset to a specific size
    x, y, ww, hh = placed[-1]
    assert (ww, hh) == (300, 320)                         # size reset to the passed box
    assert x == (1920 - 300) // 2                         # re-centered at the new size


def test_collapse_freezes_saved_size(qtbot, monkeypatch):
    w = QWidget()
    qtbot.addWidget(w)
    provider = lambda: ([Rect(0, 0, 1920, 1080)], 0)
    p = QtPersistent(w, "panel", default_panel_rect, relative=False,
                     monitors_provider=provider)
    config.save_rect("panel", [10, 10, 400, 500])     # remembered expanded size

    # simulate collapsed window geometry (short toolbar) + frozen size
    monkeypatch.setattr(w, "geometry", lambda: QRect(10, 10, 100, 40))
    p.save_size = False
    p._do_save()

    assert config.load_rect("panel")[2:] == [400, 500]   # size preserved, not clobbered
