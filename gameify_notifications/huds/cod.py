"""Call of Duty damage vignette. Two independent functions drive it:

  * encroachment(frac) -- how far the red creeps in from the edges toward the
    centre. This is the PRIMARY damage signal: more damage narrows your focal
    area / peripheral vision. A readable clear centre always remains.
  * edge_alpha(frac)  -- the peripheral red's opacity. Deliberately gentle and
    capped, so one or two notifications tint the edges without making anything
    unreadable; plus a brief flash on each new hit.

The vignette is an ellipse (Qt object-bounding gradient) so it auto-fits the
window aspect -- across all monitors in scope='all', the clear region is a wide
ellipse centred on the whole virtual desktop. scope='all' (click-through)."""

import math

from PySide6.QtCore import QRectF
from PySide6.QtGui import QColor, QRadialGradient, QBrush, QGradient

from . import Hud, Param, ParamSpec


class CodHud(Hud):
    name = "cod"
    display = "Call Of Duty"
    label = "Call of Duty -- damage vignette"
    scope = "all"

    RED = (196, 8, 8)

    # The menu focuses on the vignette's shape (clear_at_rest / max_encroachment)
    # and intensity. weight_scale is hidden (stays 1); max_alpha & dock_panel are
    # hidden because cod ignores max_alpha (intensity is the opacity control) and
    # never docks the panel.
    HIDDEN_SETTINGS = ("weight_scale", "max_alpha", "dock_panel")

    PARAMS = ParamSpec([
        Param("clear_at_rest", 0.85, float, 0.0, 1.0,
              help="Inner clear-radius at zero damage (1.0 = red only at the very edge). "
                   "How much of the centre stays clear when there's no damage."),
        Param("max_encroachment", 0.18, float, 0.0, 1.0,
              help="Inner clear-radius at full damage -- how far the red creeps toward "
                   "the centre. Smaller = creeps further in."),
        Param("intensity", 0.6, float, 0.0, 3.0,
              help="Peripheral-red opacity at full damage (cod ignores max_alpha, so "
                   "this is the sole opacity control). Higher = redder."),
    ])

    def encroachment(self, frac, clear_at_rest=0.85, max_encroachment=0.18):
        """Inner CLEAR radius (0..1 toward the edge). `clear_at_rest` = radius at
        0 damage (red only near the edge); it shrinks along a sqrt curve as
        damage rises so red creeps inward, reaching `max_encroachment` at full
        damage. sqrt curve => the first hits move it noticeably; the smaller
        `max_encroachment`, the further toward centre the red reaches at max."""
        frac = max(0.0, min(1.0, frac))
        return clear_at_rest - (clear_at_rest - max_encroachment) * math.sqrt(frac)

    def edge_alpha(self, ctx, frac):
        """Peripheral red opacity -- linear in damage at slope `intensity`, 0 at
        rest, plus a brief 'took a hit' flash on a new notification. cod ignores
        the global max_alpha (uses a 1.0 ceiling), so `intensity` alone sets how
        opaque the edges get at full damage."""
        intensity = self.tuned(ctx)["intensity"]
        a = intensity * frac
        return min(1.0, a + self.flash(ctx, duration=0.5, peak=0.2))

    def draw(self, p, w, h, ctx):
        t = self.tuned(ctx)
        frac = self.fraction(ctx)
        a = self.edge_alpha(ctx, frac)
        if a <= 0.003:
            return                                  # clear at rest
        clear = self.encroachment(frac, t["clear_at_rest"], t["max_encroachment"])
        r, g, b = self.RED
        grad = QRadialGradient(0.5, 0.5, 0.5)       # centre, radius in 0..1 of the rect
        grad.setCoordinateMode(QGradient.ObjectBoundingMode)   # -> ellipse fitting the rect
        grad.setColorAt(0.0, QColor(r, g, b, 0))
        grad.setColorAt(clear, QColor(r, g, b, 0))
        grad.setColorAt(1.0, QColor(r, g, b, int(a * 255)))
        p.fillRect(QRectF(0, 0, w, h), QBrush(grad))

    def is_animating(self, ctx):
        return self.flash(ctx, duration=0.5, peak=0.2) > 0.0
