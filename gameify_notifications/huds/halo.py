"""Halo shield + health HUD: a continuous shield bar over a segmented health
bar, under a compass strip.

  * Shield bar (top)   -- the first chunk of the damage capacity. Drains as one
    CONTINUOUS cyan fill (no segments).
  * Health bar (below) -- the rest of the capacity. SEGMENTED at a configurable
    resolution (default 2x the health units, so it reads finer when small
    weights change it). Cyan while healthy; turns RED once it drops below the
    `health_red_at` fraction (default 0.5). Flashes WARNING below `warning_at`.

The shield depletes *entirely* before the health bar begins to drop, mirroring
Halo's "shield first, then health" model.

Capacity N = round(full_at) units, split by `shield_fraction` (default 0.5).
The split rounds *toward the shield* (half-up) so it stays an integer even for
odd N: shield = round_half_up(N * shield_fraction), health = N - shield
(e.g. N=11, f=0.5 -> 6 shield / 5 health; N=13 -> 7 / 6; N=10 -> 5 / 5).

All knobs are read from the hot-reloaded [hud.halo] table in rules.toml via
ctx.param(), so they can be tuned at runtime. scope='widget'."""

import math

from PySide6.QtCore import Qt, QRectF, QPointF
from PySide6.QtGui import QColor, QPen, QFont, QPainterPath

from . import Hud, Param, ParamSpec
from .shield_health import ShieldHealthModel


class HaloHud(ShieldHealthModel, Hud):
    name = "halo"
    label = "Halo -- shield + health bars"
    scope = "widget"
    size = (640, 200)

    CYAN = (92, 219, 255)      # shield + healthy health
    RED = (204, 13, 13)        # low health only
    MAGENTA = (255, 46, 140)   # WARNING flash
    DIM = (60, 78, 96)         # empty health segment

    PARAMS = ParamSpec([
        Param("shield_fraction", 0.5, float, 0.0, 1.0),
        Param("health_red_at", 0.5, float, 0.0, 1.0),
        Param("warning_at", 0.25, float, 0.0, 1.0),
        Param("health_resolution", 2, int, 1, 20),
    ])

    # ---- damage model: shield-drains-first (shared ShieldHealthModel) -----
    # `split()` and the (shield_units, health_units, shield_rem, health_rem)
    # computation live in ShieldHealthModel; `levels` is just that, named for
    # this HUD's segment-oriented rendering.
    levels = ShieldHealthModel.shield_health

    def health_segments(self, ctx):
        """Number of chunks drawn in the health bar = health_units x the
        configured resolution (higher = finer)."""
        _su, health_units, _sr, _hr = self.levels(ctx)
        return max(1, health_units * self.tuned(ctx)["health_resolution"])

    # ---- rendering --------------------------------------------------------
    def draw(self, p, w, h, ctx):
        t = self.tuned(ctx)
        frac = self.fraction(ctx)      # 0 = full, 1 = everything depleted
        shield_units, health_units, shield_rem, health_rem = self.levels(ctx)
        warn_at = t["warning_at"]
        critical = (health_units > 0 and health_rem <= warn_at * health_units
                    and frac > 0.0)

        # red WARNING border -- only while critical, so it appears and clears
        # together with the WARNING text (not for ordinary damage).
        if critical:
            blink = 0.5 + 0.5 * math.sin(ctx.now * 9.0)
            a = min(ctx.max_alpha, ctx.max_alpha * (0.5 + 0.35 * blink))
            glow = max(4.0, 14 * (h / float(self.size[1])))
            pen = QPen(QColor(*self.RED, int(a * 0.6 * 255)))
            pen.setWidthF(glow)
            p.setPen(pen)
            p.setBrush(Qt.NoBrush)
            p.drawRect(QRectF(glow / 2, glow / 2, w - glow, h - glow))

        cx = w / 2.0
        bar_w = w * 0.86
        bx = (w - bar_w) / 2.0
        bar_h = h * 0.13

        self._compass(p, cx, h * 0.20, bar_w, h)

        shield_y = h * 0.46
        health_y = shield_y + bar_h * 1.55

        # shield: a single continuous cyan fill; the damaged part is left CLEAR
        # (transparent), not red -- red is reserved for the health bar.
        shield_frac = shield_rem / shield_units if shield_units > 0 else 0.0
        self._continuous_bar(p, bx, shield_y, bar_w, bar_h, shield_frac, self.CYAN)

        # health: segmented at `health_resolution`x units; cyan, red when low
        health_frac = health_rem / health_units if health_units > 0 else 0.0
        red_at = t["health_red_at"]
        health_color = self.RED if (health_frac <= red_at and health_units > 0
                                    and frac > 0.0) else self.CYAN
        segments = self.health_segments(ctx)
        self._segmented_bar(p, bx, health_y, bar_w, bar_h, segments, health_frac,
                            health_color, critical, ctx)

        if critical:
            blink = 0.5 + 0.5 * math.sin(ctx.now * 9.0)
            p.setPen(QColor(*self.MAGENTA, int((0.6 + 0.4 * blink) * 255)))
            f = QFont("monospace")
            f.setBold(True)
            f.setPixelSize(int(max(11, h * 0.11)))
            p.setFont(f)
            p.drawText(QRectF(0, h * 0.30, w, h * 0.14),
                       Qt.AlignHCenter | Qt.AlignVCenter, "WARNING")

    def _frame(self, p, x, y, bar_w, bar_h, color):
        pen = QPen(QColor(*color, 210))
        pen.setWidthF(max(1.0, bar_h * 0.14))
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        m = bar_h * 0.22
        path = QPainterPath()
        path.addRoundedRect(QRectF(x - m, y - m, bar_w + 2 * m, bar_h + 2 * m),
                            bar_h * 0.25, bar_h * 0.25)
        p.drawPath(path)

    def _continuous_bar(self, p, x, y, bar_w, bar_h, fill, color):
        """A continuous bar: a single `fill`-wide color fill from the left; the
        damaged remainder is left CLEAR (transparent), only the frame outlines
        the empty track."""
        self._frame(p, x, y, bar_w, bar_h, color)
        if fill > 0.0:
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(*color, 235))
            p.drawRect(QRectF(x, y, bar_w * max(0.0, min(1.0, fill)), bar_h))

    def _segmented_bar(self, p, x, y, bar_w, bar_h, segments, fill, color,
                       critical, ctx):
        """`segments` chunks separated by invisible gaps; the leftmost
        `fill`-fraction lit in `color`, the rest shown dim/empty."""
        self._frame(p, x, y, bar_w, bar_h, color)
        gap = bar_w * 0.008                             # invisible separator
        seg_w = (bar_w - gap * (segments - 1)) / segments
        lit = fill * segments
        blink = 0.5 + 0.5 * math.sin(ctx.now * 9.0)
        p.setPen(Qt.NoPen)
        for i in range(segments):
            sx = x + i * (seg_w + gap)
            if (i + 0.5) <= lit:                        # lit (rounds the edge)
                if critical:
                    p.setBrush(QColor(*color, int((0.55 + 0.45 * blink) * 255)))
                else:
                    p.setBrush(QColor(*color, 235))
            else:
                p.setBrush(QColor(*self.DIM, 150))      # empty segment
            p.drawRect(QRectF(sx, y, seg_w, bar_h))

    def _compass(self, p, cx, y, width, h):
        pen = QPen(QColor(*self.CYAN, 140))
        pen.setWidthF(max(1.0, h * 0.006))
        p.setPen(pen)
        left = cx - width / 2.0
        ticks = 28
        tall = max(5.0, h * 0.05)
        short = tall * 0.5
        for i in range(ticks + 1):
            tx = left + (width / ticks) * i
            p.drawLine(QPointF(tx, y), QPointF(tx, y - (tall if (i % 7 == 0) else short)))
        f = QFont("monospace")
        f.setPixelSize(int(max(8, h * 0.065)))
        p.setFont(f)
        p.setPen(QColor(*self.CYAN, 160))
        for fx, letter in ((0.0, "N"), (0.25, "E"), (0.5, "S"), (0.75, "W"), (1.0, "N")):
            tx = left + width * fx
            p.drawText(QRectF(tx - 15, y - tall - 20, 30, 16),
                       Qt.AlignHCenter | Qt.AlignBottom, letter)

    def is_animating(self, ctx):
        _su, health_units, _sr, health_rem = self.levels(ctx)
        warn_at = self.tuned(ctx)["warning_at"]
        critical = (health_units > 0 and health_rem <= warn_at * health_units
                    and self.fraction(ctx) > 0.0)
        return critical or self.flash(ctx) > 0.0
