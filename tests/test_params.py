"""Validation of per-HUD tuning params: every knob ends up present, typed, and
in range; missing/invalid/unknown entries fall back to the author's defaults
(and are logged once). Pure, no Qt."""

import logging

import pytest

from gameify_notifications.huds.params import Param, ParamSpec


def spec():
    return ParamSpec([
        Param("frac", 0.5, float, 0.0, 1.0),
        Param("count", 2, int, 1, 10),
        Param("flag", True, bool),
    ])


# ---- valid ----------------------------------------------------------------
def test_empty_or_none_yields_all_defaults():
    expected = {"frac": 0.5, "count": 2, "flag": True}
    assert spec().validate({}) == expected
    assert spec().validate(None) == expected


def test_valid_values_pass_and_coerce_type():
    out = spec().validate({"frac": "0.8", "count": 4.0, "flag": False})
    assert out == {"frac": 0.8, "count": 4, "flag": False}   # str/float coerced


def test_boundaries_inclusive():
    out = spec().validate({"frac": 0.0, "count": 10})
    assert out["frac"] == 0.0 and out["count"] == 10
    out = spec().validate({"frac": 1.0, "count": 1})
    assert out["frac"] == 1.0 and out["count"] == 1


def test_defaults_method():
    assert spec().defaults() == {"frac": 0.5, "count": 2, "flag": True}


# ---- invalid -> fall back to the tuned default ----------------------------
def test_out_of_range_falls_back():
    out = spec().validate({"frac": 1.5, "count": 0})
    assert out["frac"] == 0.5 and out["count"] == 2


def test_wrong_type_falls_back():
    out = spec().validate({"frac": "abc", "count": "x"})
    assert out["frac"] == 0.5 and out["count"] == 2


def test_nan_falls_back():
    assert spec().validate({"frac": float("nan")})["frac"] == 0.5


def test_bool_rejected_where_number_expected():
    # True == 1 would silently pass int()/float(); we reject it explicitly
    out = spec().validate({"frac": True, "count": True})
    assert out["frac"] == 0.5 and out["count"] == 2


def test_number_rejected_where_bool_expected():
    assert spec().validate({"flag": 1})["flag"] is True       # 1 is not a bool
    assert spec().validate({"flag": False})["flag"] is False  # genuine bool kept


def test_unknown_key_dropped_with_warning(caplog):
    s = spec()
    with caplog.at_level(logging.WARNING, logger="gameify_notifications.huds.params"):
        out = s.validate({"bogus": 3, "frac": 0.7})
    assert "bogus" not in out and out["frac"] == 0.7
    assert any("unknown hud param" in r.getMessage() for r in caplog.records)


def test_each_problem_warns_once(caplog):
    s = spec()
    with caplog.at_level(logging.WARNING, logger="gameify_notifications.huds.params"):
        s.validate({"frac": 1.5})
        s.validate({"frac": 1.5})        # same bad value again -> not re-logged
    bad = [r for r in caplog.records if "frac" in r.getMessage()]
    assert len(bad) == 1


def test_int_param_truncates_float_in_range():
    # 3.9 -> int 3 (in [1,10]); documents the int() truncation behavior
    assert spec().validate({"count": 3.9})["count"] == 3


def test_extend_merges_and_keeps_specific_on_collision():
    common = [Param("max_messages", 0, int, 0, 100), Param("weight_scale", 1.0, float, 0.0, 10.0)]
    merged = spec().extend(common)
    d = merged.defaults()
    # both the common knobs and the spec's own knobs are present
    assert d["max_messages"] == 0 and d["weight_scale"] == 1.0
    assert d["frac"] == 0.5 and d["count"] == 2
    # a HUD-specific param of the same name would win over a common one
    clash = ParamSpec([Param("max_messages", 7, int, 0, 100)]).extend(common)
    assert clash.defaults()["max_messages"] == 7


# ---- the shared capacity / drain knobs every overlay gets ----------------
def _common_spec():
    from gameify_notifications.huds import Hud
    return ParamSpec([]).extend(Hud.COMMON_PARAMS)


def test_common_params_default_when_absent():
    out = _common_spec().validate({})
    assert out["max_messages"] == 0      # 0 -> inherit global max_messages
    assert out["weight_scale"] == 1.0    # 1.0 -> unscaled drain
    assert out["width"] == 0             # 0 -> use the HUD's built-in size
    assert out["height"] == 0


def test_common_params_accept_valid():
    out = _common_spec().validate({"max_messages": 25, "weight_scale": 2.5,
                                   "width": 400, "height": 220})
    assert out["max_messages"] == 25 and out["weight_scale"] == 2.5
    assert out["width"] == 400 and out["height"] == 220


def test_width_height_validation():
    s = _common_spec()
    assert s.validate({"width": 300, "height": 320}) == {
        "max_messages": 0, "weight_scale": 1.0, "width": 300, "height": 320}
    assert s.validate({"width": "wide"})["width"] == 0        # non-int -> default
    assert s.validate({"height": -10})["height"] == 0         # negative -> default
    assert s.validate({"width": 10_000})["width"] == 10_000   # upper bound ok
    assert s.validate({"width": 10_001})["width"] == 0        # over max -> default
    assert s.validate({"height": 250.0})["height"] == 250     # float coerced to int
    assert s.validate({"width": True})["width"] == 0          # bool rejected


def test_common_params_reject_invalid_and_fall_back():
    out = _common_spec().validate({"max_messages": -5, "weight_scale": "fast"})
    assert out["max_messages"] == 0      # negative out of range -> default
    assert out["weight_scale"] == 1.0    # non-number -> default


def test_common_params_boundaries():
    s = _common_spec()
    assert s.validate({"weight_scale": 0.0})["weight_scale"] == 0.0       # 0 allowed (no drain)
    assert s.validate({"max_messages": 1_000_000})["max_messages"] == 1_000_000
    assert s.validate({"max_messages": 1_000_001})["max_messages"] == 0   # over max -> default
    assert s.validate({"weight_scale": 1000.0})["weight_scale"] == 1000.0
    assert s.validate({"weight_scale": 1000.1})["weight_scale"] == 1.0    # over max -> default


def test_common_params_bool_rejected():
    # True must not slip through as 1 for either numeric knob
    out = _common_spec().validate({"max_messages": True, "weight_scale": True})
    assert out["max_messages"] == 0 and out["weight_scale"] == 1.0
