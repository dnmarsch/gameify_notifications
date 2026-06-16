"""Declarative validation for per-HUD tuning knobs (the [hud.<name>] tables in
rules.toml).

A ParamSpec turns a raw, user-edited dict into a clean dict where every knob is
present, correctly typed, and within range. Any missing / wrong-type /
out-of-range / unknown entry falls back to the tuned default and is logged once
(deduped, so a steady bad value doesn't spam at frame rate). So a typo in a
live-edited config can never crash a HUD or silently push a nonsense value into
the renderer -- it degrades to the defaults the author tuned."""

import logging

log = logging.getLogger(__name__)


class Param:
    """One tunable: name, default, target type, and an optional [lo, hi] range.

    `validate` is an optional extra predicate (value -> bool) for types a range
    can't express -- e.g. "this path must exist". A value failing it falls back
    to the default like any other rejection.

    UI metadata (`ui_min`/`ui_max`/`step`) describes how a settings slider should
    present the param. They default sensibly from [lo, hi] with a 10%-of-range
    step, and are only set explicitly where the validation range is unsuitable
    for a slider (e.g. max_messages validates up to 1e6 but the slider shows
    0-50). See `slider()` / `control()`."""

    __slots__ = ("name", "default", "kind", "lo", "hi", "validate",
                 "ui_min", "ui_max", "step", "help", "is_file")

    def __init__(self, name, default, kind=float, lo=None, hi=None, validate=None,
                 ui_min=None, ui_max=None, step=None, help="", is_file=False):
        self.name = name
        self.default = default
        self.kind = kind
        self.lo = lo
        self.hi = hi
        self.validate = validate
        self.ui_min = ui_min
        self.ui_max = ui_max
        self.step = step
        self.help = help          # one-line description for the settings ⓘ tooltip
        self.is_file = is_file    # str param that's a file path -> show a Browse button

    def control(self):
        """Which settings control fits this param: 'toggle' (bool), 'text'
        (str), or 'slider' (numeric)."""
        if self.kind is bool:
            return "toggle"
        if self.kind is str:
            return "text"
        return "slider"

    def slider(self):
        """Slider metadata for a numeric param -> (lo, hi, step), or None for
        non-numeric. `lo`/`hi` come from ui_min/ui_max (else the validation
        range); `step` is explicit or 10% of the span (int -> rounded, min 1)."""
        if self.control() != "slider":
            return None
        lo = self.ui_min if self.ui_min is not None else (self.lo if self.lo is not None else 0)
        hi = self.ui_max if self.ui_max is not None else (self.hi if self.hi is not None else lo + 1)
        if self.step is not None:
            step = self.step
        elif self.kind is int:
            step = max(1, round((hi - lo) * 0.10))
        else:
            step = round((hi - lo) * 0.10, 4)
        if self.kind is int:
            return (int(lo), int(hi), int(step))
        return (float(lo), float(hi), float(step))

    def coerce(self, value):
        """-> (ok, value). ok=False means the value was rejected; `value` is then
        the default. Rejects wrong types, NaN, out-of-range numbers, and values
        failing the optional `validate` predicate."""
        if self.kind is bool:
            return (True, value) if isinstance(value, bool) else (False, self.default)
        if self.kind is str:
            # only accept a genuine string (don't stringify numbers/bools)
            if not isinstance(value, str):
                return False, self.default
            if self.validate is not None and not self.validate(value):
                return False, self.default
            return True, value
        # numbers: reject bool sneaking in (True == 1)
        if isinstance(value, bool):
            return False, self.default
        try:
            v = self.kind(value)
        except (TypeError, ValueError):
            return False, self.default
        if isinstance(v, float) and v != v:                 # NaN
            return False, self.default
        if self.lo is not None and v < self.lo:
            return False, self.default
        if self.hi is not None and v > self.hi:
            return False, self.default
        if self.validate is not None and not self.validate(v):
            return False, self.default
        return True, v


class ParamSpec:
    """A set of Params. `validate(raw)` always returns a full dict of every
    declared knob, valid-or-default. Unknown keys are dropped with a warning."""

    def __init__(self, params):
        self._params = {p.name: p for p in params}
        self._warned = set()

    def extend(self, params):
        """Return a new ParamSpec with `params` added first (e.g. the per-HUD
        common knobs every overlay shares). Existing names take precedence."""
        merged = {p.name: p for p in params}
        merged.update(self._params)
        return ParamSpec(merged.values())

    def defaults(self):
        return {name: p.default for name, p in self._params.items()}

    def validate(self, raw):
        raw = raw or {}
        out = {}
        for name, p in self._params.items():
            if name not in raw:
                out[name] = p.default
                continue
            ok, v = p.coerce(raw[name])
            if not ok:
                self._warn(("bad", name, repr(raw[name])),
                           "hud param %r=%r is invalid; using default %r",
                           name, raw[name], p.default)
            out[name] = v
        for key in raw:
            if key not in self._params:
                self._warn(("unknown", key), "unknown hud param %r ignored", key)
        return out

    def _warn(self, token, fmt, *args):
        if token not in self._warned:        # log each distinct problem once
            self._warned.add(token)
            log.warning(fmt, *args)
