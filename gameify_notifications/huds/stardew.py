"""Stardew Valley energy + health HUD: two wood-framed vertical bars that fill
from the bottom, each capped with a round badge -- Health ("H") on the left,
Energy ("E") on the right.

Same "shield drains first" model as Halo / GoldenEye (shared ShieldHealthModel),
but here the SHIELD share is the Energy bar: Energy depletes ENTIRELY before
Health starts dropping. Each bar colours its own fill green -> yellow -> red by
how full IT is, using the same thresholds as the Pokemon HP bar (shared
bar_color). scope='widget' -- movable, resizable, persisted."""

from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QColor, QPen, QFont

from . import Hud, Param, ParamSpec
from . import bar_color
from .shield_health import ShieldHealthModel


class StardewHud(ShieldHealthModel, Hud):
    name = "stardew"
    display = "Stardew Valley"
    label = "Stardew Valley -- energy + health bars"
    scope = "widget"
    BARS_W = 44                # nominal width of the two-bar band itself
    right_gutter = 30          # transparent pad on the RIGHT only (clears the ⊕);
                               # bars stay LEFT-aligned, flush with the docked toolbar
    size = (BARS_W + right_gutter, 107)      # ~1/3 of the prior 320 default height
    min_size = (BARS_W + right_gutter, 60)   # floor below the new shorter default

    # max_alpha only affects Halo's WARNING border; hide it here (no-op).
    HIDDEN_SETTINGS = ("max_alpha",)

    WOOD = (150, 92, 50)       # bar frame
    WOOD_DARK = (92, 54, 30)   # frame outline / shadow
    TRACK = (58, 38, 24)       # empty bar interior
    BADGE = (201, 162, 112)    # the round H/E badge -- light brown
    INK = (74, 42, 24)         # frame / badge ring outline
    HEALTH_LETTER = bar_color.RED      # "H" drawn in red
    ENERGY_LETTER = bar_color.YELLOW   # "E" drawn in yellow

    PARAMS = ParamSpec([
        Param("shield_fraction", 0.5, float, 0.0, 1.0,
              help="Share of capacity given to the Energy bar (which drains first); "
                   "the rest is the Health bar. Energy empties entirely before Health "
                   "begins to drop."),
        Param("green_above", 0.70, float, 0.0, 1.0,
              help="A bar at or above this fill fraction shows green."),
        Param("yellow_above", 0.30, float, 0.0, 1.0,
              help="A bar at or above this fill shows yellow; below it shows red."),
    ])

    # ---- damage model: energy(=shield)-drains-first (shared model) ---------
    def levels(self, ctx):
        """-> (energy_frac, health_frac) remaining in 0..1. Energy is the shield
        share (drains first); Health is the rest (drains once Energy hits 0)."""
        energy_units, health_units, energy_rem, health_rem = self.shield_health(ctx)
        efrac = energy_rem / energy_units if energy_units else 0.0
        hfrac = health_rem / health_units if health_units else 0.0
        return efrac, hfrac

    # ---- rendering --------------------------------------------------------
    def draw(self, p, w, h, ctx):
        t = self.tuned(ctx)
        energy_frac, health_frac = self.levels(ctx)
        green_above, yellow_above = t["green_above"], t["yellow_above"]

        w = self.content_width(w)                # reserve the right gutter for the ⊕
        v_margin = min(w, h) * 0.07
        gap = w * 0.18
        # bars run from a small left margin to the right edge of the (reduced)
        # content -> LEFT-aligned, flush with the docked toolbar's left edge
        bar_w = (w - v_margin - gap) / 2.0
        if bar_w < 4:
            return
        badge_d = bar_w * 1.25                   # < bar pitch -> badges don't overlap
        track_top = v_margin + badge_d * 0.55    # tuck the track under the badge
        track_bottom = h - v_margin
        track_h = track_bottom - track_top
        if track_h < 10:
            return

        left_cx = v_margin + bar_w / 2.0
        right_cx = v_margin + bar_w + gap + bar_w / 2.0
        # Health (H) on the left, Energy (E) on the right -- matches the in-game
        # corner layout; Energy is the shield that drains first.
        self._bar(p, left_cx, track_top, bar_w, track_h, badge_d, health_frac,
                  "H", self.HEALTH_LETTER, green_above, yellow_above)
        self._bar(p, right_cx, track_top, bar_w, track_h, badge_d, energy_frac,
                  "E", self.ENERGY_LETTER, green_above, yellow_above)

    def _bar(self, p, cx, top, bar_w, track_h, badge_d, frac, letter,
             letter_color, green_above, yellow_above):
        x = cx - bar_w / 2.0
        radius = bar_w * 0.32
        outline = max(1.0, bar_w * 0.05)        # fine frame lines

        # wood frame + empty track
        p.setPen(QPen(QColor(*self.WOOD_DARK), outline))
        p.setBrush(QColor(*self.WOOD))
        p.drawRoundedRect(QRectF(x, top, bar_w, track_h), radius, radius)
        inset = outline + bar_w * 0.07          # thin gap -> fill nearly spans the bar
        track = QRectF(x + inset, top + inset,
                       bar_w - 2 * inset, track_h - 2 * inset)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(*self.TRACK))
        p.drawRoundedRect(track, radius * 0.7, radius * 0.7)

        # coloured fill, growing from the BOTTOM up to `frac`
        frac = max(0.0, min(1.0, frac))
        if frac > 0.0:
            fill_h = track.height() * frac
            fill = QRectF(track.x(), track.bottom() - fill_h,
                          track.width(), fill_h)
            p.setBrush(QColor(*bar_color.fill_color(frac, green_above, yellow_above)))
            p.drawRoundedRect(fill, radius * 0.7, radius * 0.7)

        # rounded-square badge with the letter, centred at the top of the bar
        # (bd is square -> equal sides; just round the corners)
        bd = QRectF(cx - badge_d / 2.0, top - badge_d * 0.62, badge_d, badge_d)
        br = badge_d * 0.28          # corner radius
        p.setPen(QPen(QColor(*self.WOOD_DARK), outline))
        p.setBrush(QColor(*self.BADGE))
        p.drawRoundedRect(bd, br, br)
        f = QFont("sans-serif")
        f.setBold(True)
        f.setPixelSize(int(max(8, badge_d * 0.55)))
        p.setFont(f)
        p.setPen(QColor(*letter_color))
        p.drawText(bd, Qt.AlignCenter, letter)

    def is_animating(self, ctx):
        return self.flash(ctx) > 0.0        # static gauges; just the on-damage flash
