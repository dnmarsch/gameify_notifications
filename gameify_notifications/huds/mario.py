"""Mario "lives" HUD: a horizontal row of mushrooms, one per unit of the damage
capacity. Each unit of damage removes a mushroom (lost from the RIGHT, so the
remaining lives read from the left); lost ones fade to a dim "ghost" so the row
keeps a stable width. The boundary mushroom fades fractionally for non-integer
weights, and the last surviving life blinks when critically low.

The icon is the bundled assets/mushroom.png (transparent background) by default;
point `icon_path` at any PNG to swap it. scope='widget' -- movable, resizable,
and persisted like the other widget HUDs. All knobs come from the hot-reloaded
[hud.mario] table in rules.toml via the validated PARAMS spec."""

import math
import os

from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QColor, QImage, QFont

from . import Hud, Param, ParamSpec
from .. import config


def _icon_exists(path):
    try:
        return bool(path) and os.path.isfile(path)
    except (TypeError, ValueError):
        return False


class MarioHud(Hud):
    name = "mario"
    label = "Mario -- mushroom lives"
    scope = "widget"
    size = (600, 96)

    MAGENTA = (255, 46, 140)   # critical / WARNING tint

    PARAMS = ParamSpec([
        Param("icon_path", "", str, validate=_icon_exists),  # "" -> bundled mushroom
        Param("lost_opacity", 0.18, float, 0.0, 1.0),        # 0 = hide lost lives
        Param("gap", 0.12, float, 0.0, 1.0),                 # spacing / icon width
        Param("warning_at", 0.25, float, 0.0, 1.0),          # blink the last lives below this
    ])

    def __init__(self):
        self._src = None              # source QImage (lazy)
        self._src_key = None          # which path the source was loaded from
        self._scaled = None           # cached size-scaled QImage
        self._scaled_key = None       # (w, h) the scaled image was made for

    # ---- pure model (unit-testable) --------------------------------------
    def lives(self, ctx):
        """-> (total, remaining) lives. total = the capacity in whole mushrooms;
        remaining drops by one per unit of damage, clamped to [0, total]."""
        total = max(1, int(round(self.capacity(ctx))))
        remaining = max(0.0, total - max(0.0, min(float(total), self.damage(ctx))))
        return total, remaining

    # ---- asset loading (lazy + cached) -----------------------------------
    def _default_icon(self):
        return str(config.assets_dir() / "mushroom.png")

    def _source(self, icon_path):
        path = icon_path or self._default_icon()
        if self._src is None or self._src_key != path:
            img = QImage(path)
            if img.isNull() and path != self._default_icon():
                img = QImage(self._default_icon())     # fall back to bundled icon
            self._src = img
            self._src_key = path
            self._scaled = None                        # invalidate scaled cache
        return self._src

    def _icon_for(self, src, w, h):
        key = (int(w), int(h))
        if self._scaled is None or self._scaled_key != key or self._src_dirty():
            self._scaled = src.scaled(int(w), int(h), Qt.KeepAspectRatio,
                                      Qt.SmoothTransformation)
            self._scaled_key = key
            self._scaled_src = src
        return self._scaled

    def _src_dirty(self):
        return getattr(self, "_scaled_src", None) is not self._src

    # ---- rendering --------------------------------------------------------
    def draw(self, p, w, h, ctx):
        t = self.tuned(ctx)
        total, remaining = self.lives(ctx)
        src = self._source(t["icon_path"])
        if src is None or src.isNull():
            return

        gap_frac = t["gap"]
        # fit `total` icons across the width: slot = icon + gap; icon is square-ish
        slot_w = w / (total + gap_frac * (total - 1)) if total > 0 else w
        gap = slot_w * gap_frac
        icon = min(slot_w, h * 0.92)
        icon_img = self._icon_for(src, icon, icon)
        iw, ih = icon_img.width(), icon_img.height()
        row_w = total * slot_w + gap * (total - 1) if total else 0
        x0 = (w - row_w) / 2.0
        y = (h - ih) / 2.0

        warn = remaining <= t["warning_at"] * total and remaining > 0.0
        blink = 0.5 + 0.5 * math.sin(ctx.now * 9.0)
        for i in range(total):
            cx = x0 + i * (slot_w + gap) + (slot_w - iw) / 2.0
            alive = remaining - i                      # >=1 full, (0,1) fading, <=0 lost
            if alive >= 1.0:
                op = 1.0
            elif alive > 0.0:
                op = t["lost_opacity"] + (1.0 - t["lost_opacity"]) * alive
            else:
                op = t["lost_opacity"]
            if op <= 0.0:
                continue
            # the single last-standing life blinks when critically low
            if warn and 0.0 < alive <= 1.0:
                op = min(1.0, op * (0.5 + 0.5 * blink))
            p.setOpacity(op)
            p.drawImage(QRectF(cx, y, iw, ih), icon_img)
        p.setOpacity(1.0)

        if warn:
            p.setPen(QColor(*self.MAGENTA, int((0.6 + 0.4 * blink) * 255)))
            f = QFont("monospace")
            f.setBold(True)
            f.setPixelSize(int(max(10, h * 0.16)))
            p.setFont(f)
            p.drawText(QRectF(0, 0, w, h * 0.3),
                       Qt.AlignHCenter | Qt.AlignTop, "1-UP?")

    def is_animating(self, ctx):
        total, remaining = self.lives(ctx)
        t = self.tuned(ctx)
        warn = 0.0 < remaining <= t["warning_at"] * total
        return warn or self.flash(ctx) > 0.0
