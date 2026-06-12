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
    to the default like any other rejection."""

    __slots__ = ("name", "default", "kind", "lo", "hi", "validate")

    def __init__(self, name, default, kind=float, lo=None, hi=None, validate=None):
        self.name = name
        self.default = default
        self.kind = kind
        self.lo = lo
        self.hi = hi
        self.validate = validate

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
