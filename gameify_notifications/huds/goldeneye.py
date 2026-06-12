"""GoldenEye 007 health + armor gauge: two facing segmented arcs.

  * LEFT "C"  -> health, a red->yellow gradient (top -> bottom).
  * RIGHT "Ɔ" -> shield/armor, a blue->cyan gradient (top -> bottom).

Shield depletes entirely before health (armor-absorbs-first), mirroring Halo's
model. Each arc is a fixed ring of ticks; the lit count tracks the remaining
fraction and ticks drain from the top. Honors the universal max_messages /
weight_scale knobs. scope='widget' -- movable, resizable, persisted."""

from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QColor, QPen

from . import Hud, Param, ParamSpec
from .shield_health import ShieldHealthModel


def _lerp(c0, c1, f):
    """Linear blend between two RGB tuples -- the per-tick gradient step."""
    f = max(0.0, min(1.0, f))
    return tuple(int(round(c0[k] + (c1[k] - c0[k]) * f)) for k in range(3))


class GoldenEyeHud(ShieldHealthModel, Hud):
    name = "goldeneye"
    label = "GoldenEye -- health + armor arcs"
    scope = "widget"
    size = (240, 240)          # square -> the ring centers with even margins

    HEALTH_TOP = (224, 36, 24)     # red (top of the left arc)
    HEALTH_BOT = (250, 214, 44)    # yellow (bottom)
    SHIELD_TOP = (40, 84, 232)     # blue (top of the right arc)
    SHIELD_BOT = (120, 206, 255)   # cyan (bottom)
    DIM = (54, 60, 74)             # depleted tick

    PARAMS = ParamSpec([
        Param("shield_fraction", 0.5, float, 0.0, 1.0),   # share of capacity = shield
        Param("segments", 9, int, 3, 40),                 # ticks per arc
    ])

    # ---- damage model: shield-drains-first (shared ShieldHealthModel) -----
    def levels(self, ctx):
        """-> (shield_frac, health_frac) remaining in 0..1; shield drains first.
        Same model as Halo (ShieldHealthModel), expressed as arc-fill fractions."""
        shield_units, health_units, shield_rem, health_rem = self.shield_health(ctx)
        sfrac = shield_rem / shield_units if shield_units else 0.0
        hfrac = health_rem / health_units if health_units else 0.0
        return sfrac, hfrac

    # ---- rendering --------------------------------------------------------
    def draw(self, p, w, h, ctx):
        shield_frac, health_frac = self.levels(ctx)
        segs = self.tuned(ctx)["segments"]
        cx, cy = w / 2.0, h / 2.0
        radius = min(w, h) * 0.42      # fill the box -> smaller empty margin
        thickness = radius * 0.30
        # left arc = health: 110deg (upper-left) sweeping +140deg down to lower-left
        self._arc(p, cx, cy, radius, 110.0, 140.0, segs, health_frac,
                  self.HEALTH_TOP, self.HEALTH_BOT, thickness)
        # right arc = shield: 70deg (upper-right) sweeping -140deg down to lower-right
        self._arc(p, cx, cy, radius, 70.0, -140.0, segs, shield_frac,
                  self.SHIELD_TOP, self.SHIELD_BOT, thickness)

    def _arc(self, p, cx, cy, radius, a_start, sweep, units, frac,
             top_color, bottom_color, thickness):
        rect = QRectF(cx - radius, cy - radius, 2 * radius, 2 * radius)
        seg = sweep / units
        gap = 0.22                                  # blank fraction of each tick slot
        lit_threshold = units * (1.0 - frac)        # drain from the top end
        p.setBrush(Qt.NoBrush)
        for i in range(units):
            f = (i + 0.5) / units
            lit = (i + 0.5) >= lit_threshold
            col = _lerp(top_color, bottom_color, f) if lit else self.DIM
            pen = QPen(QColor(*col, 235 if lit else 120))
            pen.setWidthF(thickness)
            pen.setCapStyle(Qt.FlatCap)
            p.setPen(pen)
            s0 = a_start + seg * i
            p.drawArc(rect, int(round(s0 * 16)), int(round(seg * (1.0 - gap) * 16)))

    def is_animating(self, ctx):
        return False        # static gauge -- no pulse/flash; it repaints on damage change
