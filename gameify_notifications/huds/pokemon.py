"""Pokemon HUD: a sprite to the left of a classic battle box (name, level, and
an HP bar). HP = remaining health (1 - damage); the bar starts green and
transitions green -> yellow -> red as damage accumulates.

The sprite (bundled Bulbasaur by default, swap via icon_path), the trainer-given
`name`, and the `level` are all configurable from the hot-reloaded [hud.pokemon]
table. scope='widget' -- movable, resizable, persisted like the other widgets."""

import os

from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QColor, QImage, QPen, QFont

from . import Hud, Param, ParamSpec
from .. import config


def _icon_exists(path):
    try:
        return bool(path) and os.path.isfile(path)
    except (TypeError, ValueError):
        return False


class PokemonHud(Hud):
    name = "pokemon"
    label = "Pokemon -- HP bar + sprite"
    scope = "widget"
    size = (560, 150)

    GREEN = (88, 208, 120)     # HP 70-100%
    YELLOW = (240, 200, 48)    # HP 30-70%
    RED = (216, 64, 48)        # HP 0-30%
    BOX = (248, 248, 224)      # cream battle box
    INK = (56, 56, 64)         # dark text / border
    HP_LABEL = (216, 152, 40)  # the orange "HP" tag

    PARAMS = ParamSpec([
        Param("name", "BULBASAUR", str),                      # trainer-given name
        Param("level", 50, int, 1, 100),
        Param("icon_path", "", str, validate=_icon_exists),   # "" -> bundled sprite
        Param("green_above", 0.70, float, 0.0, 1.0),          # >= this HP -> green
        Param("yellow_above", 0.30, float, 0.0, 1.0),         # >= this HP -> yellow, else red
    ])

    def __init__(self):
        self._src = {}        # path -> source QImage
        self._scaled = {}     # (path, w, h) -> scaled QImage

    # ---- pure model (unit-testable) --------------------------------------
    def hp(self, ctx):
        """Remaining HP as a fraction (1.0 = full, 0.0 = fainted)."""
        return max(0.0, min(1.0, 1.0 - self.fraction(ctx)))

    def hp_color(self, hp, green_above=0.70, yellow_above=0.30):
        if hp >= green_above:
            return self.GREEN
        if hp >= yellow_above:
            return self.YELLOW
        return self.RED

    # ---- asset loading (lazy + size-cached) ------------------------------
    def _sprite_path(self, icon_path):
        return icon_path or str(config.assets_dir() / "bulbasaur.png")

    def _male_path(self):
        return str(config.assets_dir() / "male.png")

    def _image(self, path, w, h):
        if path not in self._src:
            self._src[path] = QImage(path)
        src = self._src[path]
        if src.isNull():
            return src
        key = (path, int(w), int(h))
        if key not in self._scaled:
            if len(self._scaled) > 24:            # bound the cache across resizes
                self._scaled.clear()
            self._scaled[key] = src.scaled(int(w), int(h), Qt.KeepAspectRatio,
                                           Qt.SmoothTransformation)
        return self._scaled[key]

    # ---- rendering --------------------------------------------------------
    def draw(self, p, w, h, ctx):
        t = self.tuned(ctx)
        hp = self.hp(ctx)
        pad = h * 0.07

        # one box spanning the widget; everything lives INSIDE it
        box_x, box_y = pad, pad
        box_w, box_h = w - 2 * pad, h - 2 * pad
        if box_w < 40 or box_h < 20:
            return
        self._box(p, box_x, box_y, box_w, box_h)
        inset = box_h * 0.12

        # sprite fits inside the box on the left (scales with the box on resize)
        sprite_sz = box_h - 2 * inset
        sprite = self._image(self._sprite_path(t["icon_path"]), sprite_sz, sprite_sz)
        sprite_x = box_x + inset
        if not sprite.isNull():
            p.drawImage(QRectF(sprite_x, box_y + (box_h - sprite.height()) / 2.0,
                               sprite.width(), sprite.height()), sprite)
            text_x = sprite_x + sprite.width() + box_w * 0.04
        else:
            text_x = sprite_x

        text_right = box_x + box_w - inset
        text_w = max(10.0, text_right - text_x)

        # row 1: NAME + gender symbol (left-aligned at text_x)
        name_h = box_h * 0.30
        f = QFont("sans-serif")
        f.setBold(True)
        f.setPixelSize(int(max(10, name_h)))
        p.setFont(f)
        p.setPen(QColor(*self.INK))
        ny = box_y + inset
        p.drawText(QRectF(text_x, ny, text_w, name_h * 1.2),
                   Qt.AlignLeft | Qt.AlignVCenter, t["name"])
        # The gender icon is hard-coded MALE -- I didn't want to source a matching
        # female sprite, so: the patriarchy, in action. (Swap-in left as an exercise.)
        adv = p.fontMetrics().horizontalAdvance(t["name"])
        sym = self._image(self._male_path(), name_h, name_h)
        if not sym.isNull():
            p.drawImage(QRectF(text_x + adv + name_h * 0.3,
                               ny + (name_h * 1.2 - sym.height()) / 2.0,
                               sym.width(), sym.height()), sym)

        # row 2: level (left-aligned at text_x, under the name)
        lv_h = box_h * 0.22
        lf = QFont("sans-serif")
        lf.setBold(True)
        lf.setPixelSize(int(max(9, lv_h)))
        p.setFont(lf)
        p.setPen(QColor(*self.INK))
        p.drawText(QRectF(text_x, box_y + box_h * 0.42, text_w, lv_h * 1.2),
                   Qt.AlignLeft | Qt.AlignVCenter, f"Lv{t['level']}")

        # row 3: "HP" hugs the bar; the bar fills to the box's right edge
        bar_y = box_y + box_h * 0.70
        bar_h = box_h * 0.20
        hf = QFont("sans-serif")
        hf.setBold(True)
        hf.setPixelSize(int(max(8, bar_h * 1.05)))
        p.setFont(hf)
        p.setPen(QColor(*self.HP_LABEL))
        hp_w = p.fontMetrics().horizontalAdvance("HP")
        p.drawText(QRectF(text_x, bar_y - bar_h * 0.25, hp_w, bar_h * 1.5),
                   Qt.AlignLeft | Qt.AlignVCenter, "HP")
        bx = text_x + hp_w + bar_h * 0.35              # bar starts right after "HP"
        bw = text_right - bx
        if bw < 8:
            return
        # bar frame + empty track
        p.setPen(QPen(QColor(*self.INK), max(1.0, bar_h * 0.2)))
        p.setBrush(QColor(40, 40, 40, 180))
        p.drawRoundedRect(QRectF(bx, bar_y, bw, bar_h), bar_h * 0.4, bar_h * 0.4)
        # colored fill, proportional to HP
        fi = max(1.0, bar_h * 0.2)
        fill_w = (bw - 2 * fi) * hp
        if fill_w > 0:
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(*self.hp_color(hp, t["green_above"], t["yellow_above"]), 240))
            p.drawRoundedRect(QRectF(bx + fi, bar_y + fi, fill_w, bar_h - 2 * fi),
                              bar_h * 0.3, bar_h * 0.3)

    def _box(self, p, x, y, w, h):
        p.setPen(QPen(QColor(*self.INK), max(1.5, h * 0.04)))
        p.setBrush(QColor(*self.BOX, 235))
        p.drawRoundedRect(QRectF(x, y, w, h), h * 0.12, h * 0.12)

    def is_animating(self, ctx):
        return self.flash(ctx) > 0.0
