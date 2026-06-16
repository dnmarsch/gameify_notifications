"""Stardew HUD: energy(=shield)-drains-first model (shared with Halo/GoldenEye)
and that each vertical bar renders green -> yellow -> red by its OWN fill."""

import pytest

from gameify_notifications.huds import load_huds, render_to_image, bar_color


@pytest.fixture
def sd(qapp):
    return load_huds()["stardew"]


def _fill_present(img, side, target, tol=40):
    """Is `target` RGB present in the LOWER (track/fill) area of the given bar
    -- side 'L' = Health, 'R' = Energy -- sampled below the top badges so the
    red "H" / yellow "E" letters don't confound the fill-colour check."""
    w, h = img.width(), img.height()
    x0, x1 = (0, w // 2) if side == "L" else (w // 2, w)
    for y in range(int(h * 0.45), h, 2):            # below the badges
        for x in range(x0, x1, 2):
            c = img.pixelColor(x, y)
            if c.alpha() < 80:
                continue
            if (abs(c.red() - target[0]) + abs(c.green() - target[1])
                    + abs(c.blue() - target[2])) < tol:
                return True
    return False


# ---- registration ---------------------------------------------------------
def test_stardew_is_registered(qapp):
    assert "stardew" in load_huds()


def test_display_name(sd):
    assert sd.display == "Stardew Valley"


def test_default_is_the_narrow_floor_with_right_gutter(sd):
    from gameify_notifications.huds import Hud
    # default width == min width -> it opens at the compact floor
    assert sd.size[0] == sd.min_size[0]
    # narrow bar band + a transparent RIGHT-only gutter for the ⊕ control
    assert sd.BARS_W <= 60
    assert sd.right_gutter >= 28                      # clears the 22px ⊕ + margin
    assert sd.size[0] == sd.BARS_W + sd.right_gutter
    assert sd.size[1] == 107                         # ~1/3 of the prior 320 default
    assert sd.min_size[1] <= sd.size[1]              # floor not above the default
    assert sd.min_size[0] < Hud.min_size[0]          # narrower than the 140 base floor


# ---- energy-drains-first model --------------------------------------------
def test_energy_depletes_before_health(sd, make_ctx):
    # capacity 10 -> energy 5 / health 5 (energy is the shield share)
    def lv(d):
        return sd.levels(make_ctx(total_weight=d, max_messages=10.0))

    assert lv(0.0) == (1.0, 1.0)        # both full
    assert lv(2.5) == (0.5, 1.0)        # energy half, health untouched
    assert lv(5.0) == (0.0, 1.0)        # energy empty, health still full
    assert lv(7.5) == (0.0, 0.5)        # now health drains
    assert lv(10.0) == (0.0, 0.0)       # both gone
    assert lv(99.0) == (0.0, 0.0)       # clamped


def test_shares_shield_health_model_with_halo(sd, make_ctx):
    from gameify_notifications.huds.shield_health import ShieldHealthModel
    halo = load_huds()["halo"]
    assert isinstance(sd, ShieldHealthModel)
    for d in (0.0, 2.5, 5.0, 7.5, 10.0):
        ctx = make_ctx(total_weight=d, max_messages=10.0)
        su, hu, sr, hr = halo.shield_health(ctx)        # units form (Halo)
        efrac, hfrac = sd.levels(ctx)                   # fraction form (Stardew)
        assert efrac == (sr / su if su else 0.0)
        assert hfrac == (hr / hu if hu else 0.0)


def test_levels_honor_shield_fraction(sd, make_ctx):
    # 8 energy / 2 health: 8 damage empties energy exactly, health untouched
    e, h = sd.levels(make_ctx(total_weight=8.0, max_messages=10.0,
                              params={"shield_fraction": 0.8}))
    assert e == 0.0 and h == 1.0


# ---- rendering: each bar colours green->yellow->red by its own fill --------
def test_full_bars_render_green_no_red(sd, make_ctx):
    img = render_to_image(sd, 170, 320,
                          make_ctx(total_weight=0.0, max_messages=10.0, w=170, h=320))
    assert _fill_present(img, "L", bar_color.GREEN)        # health full -> green
    assert _fill_present(img, "R", bar_color.GREEN)        # energy full -> green
    assert not _fill_present(img, "L", bar_color.RED)      # no red fill anywhere
    assert not _fill_present(img, "R", bar_color.RED)


def test_low_energy_bar_turns_red_while_health_stays_green(sd, make_ctx):
    # 5 energy / 5 health; 4 damage -> energy frac 0.2 (red), health full (green)
    img = render_to_image(sd, 170, 320,
                          make_ctx(total_weight=4.0, max_messages=10.0, w=170, h=320))
    assert _fill_present(img, "R", bar_color.RED)          # energy bar critical
    assert _fill_present(img, "L", bar_color.GREEN)        # health bar still full


def test_mid_energy_bar_is_yellow(sd, make_ctx):
    # 3 damage off 5 energy = frac 0.4 -> yellow; health untouched (green)
    img = render_to_image(sd, 170, 320,
                          make_ctx(total_weight=3.0, max_messages=10.0, w=170, h=320))
    assert _fill_present(img, "R", bar_color.YELLOW)       # energy mid
    assert _fill_present(img, "L", bar_color.GREEN)        # health still full
