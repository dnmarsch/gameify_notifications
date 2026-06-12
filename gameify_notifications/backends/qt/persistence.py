"""Reusable geometry persistence for a Qt window: restore + off-screen-safe
clamp + save-on-move/resize + re-clamp on monitor changes, shared by the panel
and widget HUD.

`relative=True` stores geometry as fractions of the monitor it sits on, so both
position AND size survive resolution / orientation changes (the window rescales
proportionally). The monitor source is injectable (`monitors_provider`) so tests
can simulate a resolution change without touching real hardware."""

from PySide6.QtCore import QTimer
from PySide6.QtGui import QGuiApplication

from ... import config
from ...geometry import (clamp_rect, center_rect, rect_to_fractions,
                         fractions_to_rect)
from .screens import qt_monitors


class QtPersistent:
    def __init__(self, window, key, default_fn, relative=False, monitors_provider=None,
                 center_fn=None):
        self.window = window
        self.key = key
        self.default_fn = default_fn
        self.relative = relative
        self.save_size = True   # when False, persist position but keep stored size
        self.monitors_provider = monitors_provider or qt_monitors
        self.center_fn = center_fn or center_rect   # how the "center" action places it
        self._timer = QTimer(window)
        self._timer.setSingleShot(True)
        self._timer.setInterval(500)
        self._timer.timeout.connect(self._do_save)
        self.restore()
        appins = QGuiApplication.instance()
        if appins is not None:
            for name in ("screenAdded", "screenRemoved", "primaryScreenChanged"):
                sig = getattr(appins, name, None)
                if sig is not None:
                    try:
                        sig.connect(lambda *_: self.on_monitors_changed())
                    except Exception:
                        pass

    def _wa_pr(self):
        return self.monitors_provider()

    def _serialize(self, rect):
        wa, pr = self._wa_pr()
        if self.relative:
            mi, fr = rect_to_fractions(rect, wa, pr)
            config.save_state(self.key, {"rel": fr, "mon": mi})
        else:
            config.save_rect(self.key, rect)

    def _deserialize(self):
        wa, pr = self._wa_pr()
        v = config.load_state(self.key)
        if self.relative:
            if isinstance(v, dict) and isinstance(v.get("rel"), list) and len(v["rel"]) == 4:
                return fractions_to_rect(v.get("mon", pr), v["rel"], wa, pr)
            return None
        if isinstance(v, list) and len(v) == 4:
            return [int(n) for n in v]
        return None

    def restore(self):
        wa, pr = self._wa_pr()
        saved = self._deserialize()
        rect = clamp_rect(saved, wa, pr, self.default_fn) if saved else self.default_fn(wa, pr)
        self.window.setGeometry(rect[0], rect[1], rect[2], rect[3])

    def schedule_save(self):
        self._timer.start()

    def _do_save(self):
        g = self.window.geometry()
        x, y, w, h = g.x(), g.y(), g.width(), g.height()
        if not self.save_size and not self.relative:
            old = config.load_rect(self.key)
            if old:
                w, h = old[2], old[3]   # keep remembered (expanded) size
        self._serialize([x, y, w, h])

    def on_monitors_changed(self):
        wa, pr = self._wa_pr()
        g = self.window.geometry()
        rect = [g.x(), g.y(), g.width(), g.height()]
        target = (self._deserialize() or rect) if self.relative else rect
        fixed = clamp_rect(target, wa, pr, self.default_fn)
        self.window.setGeometry(fixed[0], fixed[1], fixed[2], fixed[3])

    def center(self, size=None):
        """Re-center on the primary monitor. With `size` (w, h) given, also reset
        the window to that size (used by the ⊕ "reset" button); otherwise keep
        the current size."""
        wa, pr = self._wa_pr()
        if size is not None:
            w, h = int(size[0]), int(size[1])
        else:
            g = self.window.geometry()
            w, h = g.width(), g.height()
        rect = self.center_fn(wa, pr, w, h)
        self.window.setGeometry(rect[0], rect[1], rect[2], rect[3])
        self._serialize([rect[0], rect[1], rect[2], rect[3]])
