"""Pokemon HUD: HP model, the green->yellow->red color thresholds, param
validation (name/level/icon_path), and that the bar renders the right color."""

import pytest

from gameify_notifications import config
from gameify_notifications.huds import load_huds, render_to_image


@pytest.fixture
def poke(qapp):
    return load_huds()["pokemon"]


def _band_colors(img):
    """Count green / yellow / red pixels in the HP-bar band (right side, past
    the sprite + 'HP' label so the only colored thing is the bar fill)."""
    g = y = r = 0
    x0, x1 = int(img.width() * 0.40), int(img.width() * 0.97)
    y0, y1 = int(img.height() * 0.72), int(img.height() * 0.81)
    for py in range(y0, y1, 2):
        for px in range(x0, x1, 2):
            c = img.pixelColor(px, py)
            if c.alpha() < 60:
                continue
            R, G, B = c.red(), c.green(), c.blue()
            if R > 180 and G > 150 and B < 110:
                y += 1
            elif G > 150 and R < 150 and B < 170:
                g += 1
            elif R > 150 and G < 90:
                r += 1
    return g, y, r


# ---- registration ---------------------------------------------------------
def test_pokemon_is_registered(qapp):
    assert "pokemon" in load_huds()


# ---- HP model + color thresholds ------------------------------------------
def test_hp_is_remaining_health(poke, make_ctx):
    assert poke.hp(make_ctx(total_weight=0.0, max_messages=10.0)) == 1.0
    assert poke.hp(make_ctx(total_weight=5.0, max_messages=10.0)) == 0.5
    assert poke.hp(make_ctx(total_weight=10.0, max_messages=10.0)) == 0.0
    assert poke.hp(make_ctx(total_weight=15.0, max_messages=10.0)) == 0.0   # clamp


def test_hp_color_thresholds(poke):
    assert poke.hp_color(1.00) == poke.GREEN
    assert poke.hp_color(0.70) == poke.GREEN     # boundary inclusive
    assert poke.hp_color(0.69) == poke.YELLOW
    assert poke.hp_color(0.30) == poke.YELLOW    # boundary inclusive
    assert poke.hp_color(0.29) == poke.RED
    assert poke.hp_color(0.00) == poke.RED


def test_hp_color_thresholds_are_configurable(poke, make_ctx):
    # the green/yellow cut-points come from the validated params
    t = poke.tuned(make_ctx(params={"green_above": 0.9, "yellow_above": 0.5}))
    assert poke.hp_color(0.85, t["green_above"], t["yellow_above"]) == poke.YELLOW
    assert poke.hp_color(0.40, t["green_above"], t["yellow_above"]) == poke.RED


def test_hp_honors_max_messages_and_weight_scale(poke, make_ctx):
    # capacity override: 15 damage out of a 30 max -> 50% HP (not fainted)
    assert poke.hp(make_ctx(total_weight=15.0, max_messages=10.0, params={"max_messages": 30})) == 0.5
    # drain multiplier: 5 weight x2 = 10 -> 0 HP against max_messages 10
    assert poke.hp(make_ctx(total_weight=5.0, max_messages=10.0, params={"weight_scale": 2.0})) == 0.0
    # absent -> defaults (inherit max_messages, unscaled)
    assert poke.hp(make_ctx(total_weight=5.0, max_messages=10.0)) == 0.5


# ---- param validation ------------------------------------------------------
def test_param_validation(poke, make_ctx):
    bad = poke.tuned(make_ctx(params={"level": 0, "icon_path": "/no/such.png"}))
    assert bad["level"] == 50            # out of [1,100] -> default
    assert bad["icon_path"] == ""        # missing file -> default (bundled sprite)
    good = poke.tuned(make_ctx(params={"name": "CLAUDEMON", "level": 73}))
    assert good["name"] == "CLAUDEMON" and good["level"] == 73


# ---- rendering: the bar color tracks HP -----------------------------------
def test_bar_is_green_at_full_red_when_low(poke, make_ctx):
    w, h = 560, 150
    full = render_to_image(poke, w, h, make_ctx(total_weight=0.0, max_messages=10.0, w=w, h=h))
    g, _yel, r = _band_colors(full)
    assert g > 0 and r == 0                       # full HP -> green, no red

    low = render_to_image(poke, w, h, make_ctx(total_weight=9.0, max_messages=10.0, w=w, h=h))
    g2, _y2, r2 = _band_colors(low)
    assert r2 > 0 and g2 == 0                      # 10% HP -> red, no green


def test_bar_is_yellow_at_mid(poke, make_ctx):
    w, h = 560, 150
    mid = render_to_image(poke, w, h, make_ctx(total_weight=5.0, max_messages=10.0, w=w, h=h))
    g, yel, r = _band_colors(mid)
    assert yel > 0 and yel >= g and yel >= r       # 50% HP -> yellow dominates


def test_missing_sprite_falls_back_to_bundled(poke, make_ctx):
    # a bad icon_path must not blank the sprite -- it falls back to the bundled
    # one. The box is cream, so assert the sprite region has non-cream ink pixels.
    w, h = 560, 150
    img = render_to_image(poke, w, h,
                          make_ctx(total_weight=0.0, max_messages=10.0, w=w, h=h,
                                   params={"icon_path": "/no/such.png"}))
    cream = (248, 248, 224)
    ink = 0
    for yy in range(int(h * 0.2), int(h * 0.8), 3):
        for xx in range(int(w * 0.04), int(w * 0.20), 3):
            c = img.pixelColor(xx, yy)
            if c.alpha() > 200 and (abs(c.red() - cream[0]) + abs(c.green() - cream[1])
                                    + abs(c.blue() - cream[2])) > 90:
                ink += 1
    assert ink > 0     # the bundled Bulbasaur drew over the cream box
