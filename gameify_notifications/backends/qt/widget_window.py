"""Movable, resizable, persisted HUD widget on the primary monitor (Halo scope).
Drag anywhere to move; drag the size grip to resize; the ⊕ button re-centers.
Geometry is persisted as a fraction of the monitor (rescales on resolution /
orientation change)."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPainter, QColor
from PySide6.QtWidgets import QWidget, QPushButton, QSizeGrip

from ...geometry import frac_top_centered, top_center_rect
from ._context import make_context
from .persistence import QtPersistent

REF_W, REF_H = 1920.0, 1080.0


class WidgetWindow(QWidget):
    recentered = Signal()
    geometryChanged = Signal()        # emitted on move/resize so a docked panel can follow

    def __init__(self, app, monitors_provider=None):
        super().__init__()
        self.app = app
        self._drag = None
        self.setObjectName("hudWidget")
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setMinimumSize(140, 60)

        self.center_btn = QPushButton("⊕", self)        # circled plus
        self.center_btn.setObjectName("hud.centerBtn")
        self.center_btn.setToolTip("Reset size & center on primary monitor")
        self.center_btn.setStyleSheet(
            "QPushButton{background:rgba(0,0,0,110);color:#cdeefe;border:none;"
            "border-radius:11px;} QPushButton:hover{background:rgba(0,0,0,170);}")
        self.center_btn.resize(22, 22)
        self.grip = QSizeGrip(self)
        self.grip.setObjectName("hud.grip")

        self.persist = QtPersistent(
            self, "hud", self._default_geom,
            relative=True, monitors_provider=monitors_provider,
            center_fn=top_center_rect)          # ⊕ snaps to top-centre (Halo-style)
        self.center_btn.clicked.connect(self._do_center)
        self._reposition_controls()

    def _configured_size(self):
        """The HUD's box size: [hud.<name>] width/height if set, else its default."""
        return self.app.hud.configured_size(self.app.rules.params_for(self.app.hud.name))

    def _default_geom(self, wa, pr):
        w, h = self._configured_size()             # read live so ⊕ picks up config edits
        return frac_top_centered(wa, pr, w / REF_W, h / REF_H)

    def _do_center(self):
        self.persist.center(self._configured_size())   # reset to the configured size + center
        self.recentered.emit()

    def context(self):
        return make_context(self.app, [(0, 0, self.width(), self.height())], 0)

    def paintEvent(self, ev):
        p = QPainter(self)
        # clear the backing store to fully transparent first -- otherwise a
        # brighter previous frame (e.g. a pulsing WARNING border) can linger
        # under the new one when damage drops, since a translucent top-level
        # window's buffer isn't reliably auto-cleared across compositors.
        p.setCompositionMode(QPainter.CompositionMode_Source)
        p.fillRect(self.rect(), QColor(0, 0, 0, 0))
        p.setCompositionMode(QPainter.CompositionMode_SourceOver)
        p.setRenderHint(QPainter.Antialiasing, True)
        self.app.hud.draw(p, self.width(), self.height(), self.context())
        p.end()

    def _reposition_controls(self):
        self.center_btn.move(self.width() - self.center_btn.width() - 6, 6)
        self.grip.move(self.width() - self.grip.width(), self.height() - self.grip.height())

    def resizeEvent(self, ev):
        self._reposition_controls()
        self.persist.schedule_save()
        self.geometryChanged.emit()
        super().resizeEvent(ev)

    def moveEvent(self, ev):
        self.persist.schedule_save()
        self.geometryChanged.emit()
        super().moveEvent(ev)

    def mousePressEvent(self, ev):
        if ev.button() == Qt.LeftButton:
            self._drag = ev.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, ev):
        if self._drag is not None and (ev.buttons() & Qt.LeftButton):
            self.move(ev.globalPosition().toPoint() - self._drag)

    def mouseReleaseEvent(self, ev):
        self._drag = None
