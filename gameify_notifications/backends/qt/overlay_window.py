"""Click-through, always-on-top overlay spanning every monitor (CoD scope).
Uses Qt.WindowTransparentForInput so clicks pass through to the apps beneath --
cross-platform (X11 + Windows), no per-platform input-shape hacks."""

from PySide6.QtCore import Qt
from PySide6.QtGui import QPainter, QColor
from PySide6.QtWidgets import QWidget

from ...geometry import virtual_bounds
from ._context import make_context
from .screens import qt_geometries, qt_primary


class OverlayWindow(QWidget):
    def __init__(self, app, monitors_provider=None):
        super().__init__()
        self.app = app
        self._geos = monitors_provider or qt_geometries   # () -> list[Rect]
        self.setObjectName("overlay")
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
                            | Qt.Tool | Qt.WindowTransparentForInput)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.place()

    def place(self):
        geos = self._geos()
        vx, vy, vw, vh = virtual_bounds(geos)
        self.setGeometry(vx, vy, vw, vh)

    def local_monitors(self):
        geos = self._geos()
        vx, vy, vw, vh = virtual_bounds(geos)
        local = [(g.x - vx, g.y - vy, g.width, g.height) for g in geos]
        prim = min(qt_primary(), max(0, len(local) - 1))
        return local, prim

    def context(self):
        local, prim = self.local_monitors()
        return make_context(self.app, local, prim)

    def paintEvent(self, ev):
        p = QPainter(self)
        p.setCompositionMode(QPainter.CompositionMode_Source)
        p.fillRect(self.rect(), QColor(0, 0, 0, 0))   # clear to transparent
        p.setCompositionMode(QPainter.CompositionMode_SourceOver)
        p.setRenderHint(QPainter.Antialiasing, True)
        self.app.hud.draw(p, self.width(), self.height(), self.context())
        p.end()
