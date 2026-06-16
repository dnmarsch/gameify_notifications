"""HUD rendering layer (Qt/QPainter).

A HUD is a strategy that paints the current "damage" onto a surface. The
HudContext carries everything a HUD needs; HUDs draw with QPainter so no extra
2D library (cairo) is required -- Qt's painter is itself cross-platform.

`render_to_image()` renders a HUD to an offscreen QImage, which the test suite
uses to assert deterministically that redness/shield scales from 0% to 100%.
"""

import importlib.util
import logging
import math

from PySide6.QtCore import Qt, QRectF, QPointF
from PySide6.QtGui import (QColor, QPainter, QPen, QBrush, QFont,
                           QRadialGradient, QImage)

from .. import config
from .params import Param, ParamSpec

log = logging.getLogger(__name__)


class HudContext:
    __slots__ = ("total_weight", "max_messages", "max_alpha", "count",
                 "now", "last_event", "monitors", "primary", "params")

    def __init__(self, total_weight, max_messages, max_alpha, count, now,
                 last_event, monitors, primary, params=None):
        self.total_weight = total_weight
        self.max_messages = max_messages
        self.max_alpha = max_alpha
        self.count = count
        self.now = now
        self.last_event = last_event
        self.monitors = monitors
        self.primary = primary
        # raw per-HUD tuning knobs from rules.toml's [hud.<name>] table
        # (hot-reloaded). A HUD validates these against its PARAMS spec via
        # self.tuned(ctx) -- never read self.params directly for tunables.
        self.params = params or {}


class Hud:
    name = "base"               # internal id: --hud arg, rules.toml [hud.<name>] / hud key
    display = ""                # friendly label for the Settings dropdown (else name)
    label = "Base HUD"          # verbose label for --list-huds
    # "all"    -> click-through overlay spanning every monitor (peripheral)
    # "widget" -> a movable, resizable, persisted window on the primary monitor
    scope = "all"
    size = (640, 160)   # preferred (default) size of a "widget"-scope HUD
    min_size = (140, 60)  # smallest a "widget"-scope HUD may be resized to
    # px reserved on the RIGHT for the widget's top-right ⊕ control; the HUD
    # draws into the width LEFT of it (transparent gutter). 0 = use full width.
    right_gutter = 0
    # validated tuning knobs from rules.toml's [hud.<name>] table; subclasses
    # override with their own ParamSpec. Read via self.tuned(ctx).
    PARAMS = ParamSpec([])
    # param names to HIDE from the Settings menu for this HUD (they still
    # validate/apply if hand-set; just decluttered when they'd only confuse).
    HIDDEN_SETTINGS = ()
    # Knobs EVERY overlay shares, so each HUD can independently set its own
    # capacity and drain rate. Optional in rules.toml -> these defaults apply.
    COMMON_PARAMS = [
        Param("max_messages", 0, int, 0, 1_000_000, ui_max=50, step=1,
              help="This overlay's own damage capacity (≈ unread messages to max it "
                   "out). 0 = inherit the global max_messages; any value overrides it "
                   "just for this HUD."),
        Param("weight_scale", 1.0, float, 0.0, 1000.0, ui_max=5.0,
              help="Drain-rate multiplier on notification weights for this HUD. "
                   "2.0 = damage builds twice as fast; 0.5 = half."),
        Param("width", 0, int, 0, 10_000, ui_max=1600,
              help="Default widget width in pixels (0 = the HUD's built-in size). "
                   "The ⊕ button resets the box to this."),
        Param("height", 0, int, 0, 10_000, ui_max=1000,
              help="Default widget height in pixels (0 = built-in). "
                   "The ⊕ button resets the box to this."),
    ]

    def draw(self, p, w, h, ctx):
        """Paint onto QPainter `p` over a w*h surface for damage state `ctx`."""
        raise NotImplementedError

    def is_animating(self, ctx):
        return False

    def _spec(self):
        """The HUD's own PARAMS merged with the shared COMMON_PARAMS, cached on
        the instance (so the validator's warn-once dedup persists)."""
        spec = self.__dict__.get("_spec_cache")
        if spec is None:
            spec = self.PARAMS.extend(self.COMMON_PARAMS)
            self._spec_cache = spec
        return spec

    def tuned(self, ctx):
        """Validated tuning knobs for this HUD (its own + the common capacity /
        drain knobs): every key present, typed, in range, missing/invalid
        entries replaced by the author's defaults."""
        return self._spec().validate(ctx.params)

    # ---- shared damage model (honors per-HUD max_messages / weight_scale) ----
    def capacity(self, ctx):
        """Damage needed to max this HUD: per-HUD `max_messages` if set, else
        the global `max_messages`."""
        mm = self.tuned(ctx)["max_messages"]
        if mm and mm > 0:
            return float(mm)
        return float(ctx.max_messages) if ctx.max_messages > 0 else 1.0

    def damage(self, ctx):
        """Accumulated notification weight scaled by this HUD's drain rate."""
        return max(0.0, ctx.total_weight * self.tuned(ctx)["weight_scale"])

    def fraction(self, ctx):
        cap = self.capacity(ctx)
        return min(1.0, self.damage(ctx) / cap) if cap > 0 else 0.0

    def content_width(self, w):
        """Drawable width after reserving `right_gutter` px on the right, so the
        widget's top-right ⊕ control sits over empty space rather than the HUD.
        Content then draws LEFT-aligned within the returned width."""
        return max(1.0, float(w) - self.right_gutter)

    def configured_size(self, params):
        """Preferred widget box size (w, h): the [hud.<name>] width/height knobs
        if set (>0), else this HUD's built-in `size`. Used for the default
        geometry and the ⊕ reset."""
        v = self._spec().validate(params or {})
        return (v["width"] or self.size[0], v["height"] or self.size[1])

    @staticmethod
    def flash(ctx, duration=0.6, peak=0.35):
        dt = ctx.now - ctx.last_event
        if dt < duration:
            return (1.0 - dt / duration) * peak
        return 0.0


def render_to_image(hud, w, h, ctx):
    """Render `hud` to a transparent ARGB QImage (for screenshots / tests)."""
    img = QImage(int(w), int(h), QImage.Format_ARGB32_Premultiplied)
    img.fill(Qt.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing, True)
    try:
        hud.draw(p, int(w), int(h), ctx)
    finally:
        p.end()
    return img


def _builtin_huds():
    from .cod import CodHud
    from .halo import HaloHud
    from .mario import MarioHud
    from .pokemon import PokemonHud
    from .goldeneye import GoldenEyeHud
    from .stardew import StardewHud
    return {CodHud.name: CodHud(), HaloHud.name: HaloHud(),
            MarioHud.name: MarioHud(), PokemonHud.name: PokemonHud(),
            GoldenEyeHud.name: GoldenEyeHud(), StardewHud.name: StardewHud()}


def load_huds():
    """Built-in HUDs plus any user plugins in the config huds/ dir."""
    registry = _builtin_huds()
    hdir = config.huds_dir()
    if hdir.is_dir():
        inject = dict(Hud=Hud, HudContext=HudContext, Param=Param,
                      ParamSpec=ParamSpec, math=math, Qt=Qt,
                      QColor=QColor, QPainter=QPainter, QPen=QPen, QBrush=QBrush,
                      QFont=QFont, QRadialGradient=QRadialGradient,
                      QRectF=QRectF, QPointF=QPointF)
        for path in sorted(hdir.glob("*.py")):
            try:
                spec = importlib.util.spec_from_file_location(f"hud_{path.stem}", path)
                module = importlib.util.module_from_spec(spec)
                module.__dict__.update(inject)
                spec.loader.exec_module(module)
                for obj in vars(module).values():
                    if isinstance(obj, type) and issubclass(obj, Hud) and obj is not Hud:
                        registry[obj.name] = obj()
            except Exception:
                log.exception("failed to load HUD plugin %s", path.name)
    return registry
