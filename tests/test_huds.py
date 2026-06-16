"""HUD rendering: render to an offscreen QImage and assert the display metric
scales from 0% to 100% damage, and that HUDs scale with surface size."""

import pytest

from gameify_notifications.huds import load_huds, render_to_image


def _alpha_at(img, x, y):
    return img.pixelColor(x, y).alpha()


def _color_counts(img):
    """Count clearly-red vs clearly-cyan pixels (sampled)."""
    red = cyan = 0
    for y in range(0, img.height(), 4):
        for x in range(0, img.width(), 4):
            c = img.pixelColor(x, y)
            if c.alpha() < 40:
                continue
            if c.red() > 150 and c.green() < 90:
                red += 1
            if c.green() > 150 and c.blue() > 150 and c.red() < 150:
                cyan += 1
    return red, cyan


@pytest.fixture
def cod(qapp):
    return load_huds()["cod"]


def test_right_gutter_reserved_for_control_on_named_huds(qapp):
    # stardew/goldeneye/halo reserve a transparent right gutter so the widget's
    # ⊕ control doesn't overlap their content; others use the full width.
    huds = load_huds()
    for name in ("stardew", "goldeneye", "halo"):
        g = huds[name].right_gutter
        assert g >= 28, name                          # clears the 22px ⊕ + margin
        assert huds[name].content_width(300) == 300 - g
    for name in ("cod", "mario", "pokemon"):
        assert huds[name].right_gutter == 0, name
        assert huds[name].content_width(300) == 300


@pytest.fixture
def halo(qapp):
    return load_huds()["halo"]


def test_cod_redness_scales_0_to_100(cod, make_ctx):
    w, h = 640, 360
    a0 = _alpha_at(render_to_image(cod, w, h, make_ctx(total_weight=0.0, w=w, h=h)), 2, 2)
    a50 = _alpha_at(render_to_image(cod, w, h, make_ctx(total_weight=3.0, w=w, h=h)), 2, 2)
    a100 = _alpha_at(render_to_image(cod, w, h, make_ctx(total_weight=6.0, w=w, h=h)), 2, 2)
    assert a0 == 0
    assert a0 < a50 < a100
    assert a100 > 50                # clearly red at max damage (intensity is halved/gentle)


def test_cod_center_stays_clear_at_max(cod, make_ctx):
    w, h = 640, 360
    img = render_to_image(cod, w, h, make_ctx(total_weight=6.0, w=w, h=h))
    assert _alpha_at(img, w // 2, h // 2) == 0   # vignette: center transparent


def test_cod_encroachment_shrinks_with_damage(cod):
    # more damage -> smaller clear radius (red creeps inward), with a floor
    assert cod.encroachment(0.0) > cod.encroachment(0.5) > cod.encroachment(1.0)
    assert cod.encroachment(1.0) >= 0.12         # a readable centre still remains


def test_cod_edge_alpha_zero_at_rest_and_ignores_max_alpha(cod, make_ctx):
    assert cod.edge_alpha(make_ctx(total_weight=0.0), 0.0) == 0.0
    # cod ignores max_alpha: at full damage the edge opacity == intensity (default
    # 0.6), regardless of the global max_alpha.
    assert abs(cod.edge_alpha(make_ctx(total_weight=6.0, max_alpha=0.3), 1.0) - 0.6) < 1e-9
    assert cod.edge_alpha(make_ctx(total_weight=6.0), 1.0) <= 1.0


def test_halo_shield_full_is_cyan_empty_is_red(halo, make_ctx):
    full = render_to_image(halo, 640, 200, make_ctx(total_weight=0.0))   # full shield
    empty = render_to_image(halo, 640, 200, make_ctx(total_weight=6.0))  # depleted
    r_full, c_full = _color_counts(full)
    r_empty, c_empty = _color_counts(empty)
    assert c_full > c_empty          # more cyan when shielded
    assert r_empty > r_full          # more red when depleted


def test_hud_scales_with_size(halo, make_ctx):
    small = render_to_image(halo, 320, 100, make_ctx(total_weight=0.0, w=320, h=100))
    big = render_to_image(halo, 1280, 400, make_ctx(total_weight=0.0, w=1280, h=400))
    # proportional rendering: bigger surface -> more shield-bar pixels drawn
    assert _color_counts(big)[1] > _color_counts(small)[1]


def test_halo_split_rounds_odd_chunk_to_shield(halo):
    # even capacity splits evenly; odd capacity gives the shield the extra chunk
    assert halo.split(10) == (5, 5)
    assert halo.split(11) == (6, 5)
    assert halo.split(13) == (7, 6)
    assert halo.split(1) == (1, 0)        # degenerate: shield-only, no health


def test_halo_shield_depletes_entirely_before_health(halo, make_ctx):
    # N=10 -> 5 shield / 5 health
    def lv(d):
        return halo.levels(make_ctx(total_weight=d, max_messages=10.0))

    su, hu, sr, hr = lv(0.0)
    assert (su, hu, sr, hr) == (5, 5, 5.0, 5.0)        # both full
    _, _, sr, hr = lv(3.0)
    assert sr == 2.0 and hr == 5.0                     # shield drops, health intact
    _, _, sr, hr = lv(5.0)
    assert sr == 0.0 and hr == 5.0                     # shield exhausted, health full
    _, _, sr, hr = lv(7.0)
    assert sr == 0.0 and hr == 3.0                     # now health drains
    _, _, sr, hr = lv(12.0)
    assert sr == 0.0 and hr == 0.0                     # clamped past capacity


def test_halo_odd_capacity_health_only_drains_after_shield(halo, make_ctx):
    # N=11 -> 6 shield / 5 health; health must stay full through the 6th unit
    _, _, sr, hr = halo.levels(make_ctx(total_weight=6.0, max_messages=11.0))
    assert sr == 0.0 and hr == 5.0
    _, _, sr, hr = halo.levels(make_ctx(total_weight=8.0, max_messages=11.0))
    assert sr == 0.0 and hr == 3.0


# ---- per-HUD capacity (max_messages) + drain rate (weight_scale) ----------
@pytest.mark.parametrize("hud_name", ["cod", "halo", "mario", "pokemon", "goldeneye"])
def test_every_hud_honors_max_messages_and_weight_scale(hud_name, qapp, make_ctx):
    hud = load_huds()[hud_name]
    # defaults when the [hud.*] block omits them: capacity = global max_messages,
    # drain unscaled.
    assert hud.capacity(make_ctx(max_messages=10.0)) == 10.0
    assert hud.damage(make_ctx(total_weight=4.0)) == 4.0
    assert hud.fraction(make_ctx(total_weight=5.0, max_messages=10.0)) == 0.5
    # per-HUD max_messages overrides the global capacity for this overlay
    assert hud.capacity(make_ctx(max_messages=10.0, params={"max_messages": 20})) == 20.0
    assert hud.fraction(make_ctx(total_weight=5.0, max_messages=10.0,
                                 params={"max_messages": 20})) == 0.25
    # weight_scale changes the drain rate
    assert hud.damage(make_ctx(total_weight=3.0, params={"weight_scale": 2.0})) == 6.0
    assert hud.fraction(make_ctx(total_weight=5.0, max_messages=10.0,
                                 params={"weight_scale": 2.0})) == 1.0


@pytest.mark.parametrize("hud_name", ["cod", "halo", "mario", "pokemon", "goldeneye"])
def test_every_hud_falls_back_on_invalid_capacity_drain(hud_name, qapp, make_ctx):
    hud = load_huds()[hud_name]
    # garbage / out-of-range -> defaults (0 inherits global max_messages; scale 1.0)
    assert hud.capacity(make_ctx(max_messages=10.0, params={"max_messages": "lots"})) == 10.0
    assert hud.capacity(make_ctx(max_messages=10.0, params={"max_messages": 0})) == 10.0
    assert hud.damage(make_ctx(total_weight=4.0, params={"weight_scale": -3})) == 4.0


@pytest.mark.parametrize("hud_name", ["halo", "mario", "pokemon", "goldeneye"])
def test_configured_size_defaults_and_overrides(hud_name, qapp):
    hud = load_huds()[hud_name]
    assert hud.configured_size({}) == hud.size                 # no config -> built-in default
    assert hud.configured_size({"width": 400, "height": 220}) == (400, 220)
    assert hud.configured_size({"width": 500}) == (500, hud.size[1])   # one axis only
    # invalid -> 0 -> falls back to the built-in size per axis
    assert hud.configured_size({"width": "big", "height": -5}) == hud.size


# ---- live-configurable tuning (rules.toml [hud.*] -> validated params) ----
def test_shipped_default_params_match_hud_specs(qapp):
    """Every shipped rules.toml [hud.*] value must equal that HUD's PARAMS
    default -- so a missing/invalid knob falls back to exactly what's tuned."""
    from gameify_notifications.rules import RuleSet
    from gameify_notifications.huds import load_huds
    rs = RuleSet()
    huds = load_huds()
    for name in ("cod", "halo", "mario", "pokemon", "goldeneye"):
        shipped = rs.params_for(name)
        defaults = huds[name].PARAMS.defaults()
        assert shipped, f"{name} has no [hud.{name}] defaults shipped"
        for key, value in shipped.items():
            assert key in defaults and defaults[key] == value


def test_halo_split_respects_shield_fraction(halo):
    assert halo.split(10, 0.7) == (7, 3)
    assert halo.split(10, 0.0) == (0, 10)               # all health
    assert halo.split(10, 1.0) == (10, 0)               # all shield


def test_halo_levels_uses_configured_shield_fraction(halo, make_ctx):
    ctx = make_ctx(total_weight=0.0, max_messages=10.0, params={"shield_fraction": 0.8})
    shield_units, health_units, _sr, _hr = halo.levels(ctx)
    assert (shield_units, health_units) == (8, 2)


def test_halo_warning_threshold_is_configurable(halo, make_ctx):
    # N=10 -> 5/5; at damage 7 health_rem=3 (0.6 of health)
    base = dict(total_weight=7.0, max_messages=10.0)
    assert halo.is_animating(make_ctx(**base, params={"warning_at": 0.25})) is False
    assert halo.is_animating(make_ctx(**base, params={"warning_at": 0.75})) is True


def test_cod_encroachment_endpoints_configurable(cod):
    assert cod.encroachment(0.0, clear_at_rest=0.9, max_encroachment=0.3) == 0.9
    assert abs(cod.encroachment(1.0, clear_at_rest=0.9, max_encroachment=0.3) - 0.3) < 1e-9


def test_cod_intensity_configurable(cod, make_ctx):
    gentle = cod.edge_alpha(make_ctx(total_weight=6.0, params={"intensity": 0.25}), 1.0)
    steep = cod.edge_alpha(make_ctx(total_weight=6.0, params={"intensity": 1.0}), 1.0)
    assert steep > gentle


def test_invalid_param_falls_back_to_default_at_render(cod, make_ctx):
    # a garbage value in the live config behaves exactly like the default
    bad = cod.edge_alpha(make_ctx(total_weight=6.0, params={"intensity": "boom"}), 1.0)
    default = cod.edge_alpha(make_ctx(total_weight=6.0), 1.0)
    assert bad == default


def test_halo_health_resolution_param(halo, make_ctx):
    base = dict(total_weight=0.0, max_messages=10.0)          # health_units = 5
    assert halo.health_segments(make_ctx(**base, params={"health_resolution": 1})) == 5
    assert halo.health_segments(make_ctx(**base, params={"health_resolution": 2})) == 10
    assert halo.health_segments(make_ctx(**base, params={"health_resolution": 3})) == 15
    # out-of-range (0) -> default 2 -> 10
    assert halo.health_segments(make_ctx(**base, params={"health_resolution": 0})) == 10


# ---- Halo rendering after the redesign -----------------------------------
_HP = {"shield_fraction": 0.5, "health_red_at": 0.5, "warning_at": 0.25,
       "health_resolution": 2}


def test_halo_shield_damage_is_clear_not_red(halo, make_ctx):
    # N=10 -> shield 5; total_weight=4 leaves the shield 20% full, 80% damaged.
    w, h = 640, 200
    img = render_to_image(halo, w, h,
                          make_ctx(total_weight=4.0, max_messages=10.0, w=w, h=h, params=_HP))
    y = int(h * 0.46 + (h * 0.13) / 2)               # mid-height of the shield bar
    damaged = img.pixelColor(int(w * 0.7), y)        # deep in the damaged region
    assert damaged.alpha() < 20                      # CLEAR (transparent), not filled
    assert damaged.red() < 50                        # and definitely not red
    filled = img.pixelColor(int(w * 0.10), y)        # the remaining shield
    assert filled.alpha() > 150 and filled.blue() > 150 and filled.red() < 150  # cyan


def test_halo_health_red_below_threshold_cyan_above(halo, make_ctx):
    w, h = 640, 200
    y = int(h * 0.46 + (h * 0.13) * 1.55 + (h * 0.13) / 2)   # mid-height of health bar
    x = int(w * 0.10)                                        # first (always-lit) segment
    low = render_to_image(halo, w, h,
                          make_ctx(total_weight=9.0, max_messages=10.0, w=w, h=h, params=_HP))
    c_low = low.pixelColor(x, y)                     # health at 20% -> red
    assert c_low.red() > 150 and c_low.green() < 90
    healthy = render_to_image(halo, w, h,
                              make_ctx(total_weight=6.0, max_messages=10.0, w=w, h=h, params=_HP))
    c_ok = healthy.pixelColor(x, y)                  # health at 80% -> still cyan
    assert c_ok.blue() > 150 and c_ok.red() < 150


def test_halo_warning_border_only_when_critical(halo, make_ctx):
    # The red border must track the WARNING state: present when critical, gone
    # for ordinary damage (so dismissing past the threshold clears it).
    w, h = 640, 200
    border = (w // 2, 4)                              # a point on the top border
    damaged = render_to_image(halo, w, h,            # shield gone, health full -> no WARNING
                              make_ctx(total_weight=5.0, max_messages=10.0, w=w, h=h, params=_HP))
    assert damaged.pixelColor(*border).alpha() < 20  # no red border
    critical = render_to_image(halo, w, h,           # health critically low -> WARNING
                               make_ctx(total_weight=10.0, max_messages=10.0, w=w, h=h, params=_HP))
    c = critical.pixelColor(*border)
    assert c.alpha() > 40 and c.red() > 120          # red border present
