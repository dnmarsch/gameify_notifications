"""GoldenEye HUD: shield-drains-first model + that both gradient arcs render
(red/yellow health on the left, blue/cyan shield on the right)."""

import pytest

from gameify_notifications.huds import load_huds, render_to_image


@pytest.fixture
def ge(qapp):
    return load_huds()["goldeneye"]


def _counts(img):
    """(warm, blue) pixel counts -- health arc is warm (red/yellow, low blue),
    shield arc is blue (high blue, low red)."""
    warm = blue = 0
    for y in range(0, img.height(), 3):
        for x in range(0, img.width(), 3):
            c = img.pixelColor(x, y)
            if c.alpha() < 80:
                continue
            if c.red() > 180 and c.blue() < 100:
                warm += 1
            elif c.blue() > 180 and c.red() < 160:
                blue += 1
    return warm, blue


# ---- registration ---------------------------------------------------------
def test_goldeneye_is_registered(qapp):
    assert "goldeneye" in load_huds()


# ---- shield-drains-first model --------------------------------------------
def test_shield_depletes_before_health(ge, make_ctx):
    # capacity 10 -> shield 5 / health 5
    def lv(d):
        return ge.levels(make_ctx(total_weight=d, full_at=10.0))

    assert lv(0.0) == (1.0, 1.0)        # both full
    assert lv(2.5) == (0.5, 1.0)        # shield half, health untouched
    assert lv(5.0) == (0.0, 1.0)        # shield empty, health still full
    assert lv(7.5) == (0.0, 0.5)        # now health drains
    assert lv(10.0) == (0.0, 0.0)       # both gone
    assert lv(99.0) == (0.0, 0.0)       # clamped


def test_shares_shield_health_model_with_halo(ge, make_ctx):
    # both HUDs use the same ShieldHealthModel -> identical shield/health split
    # and drain order; GoldenEye just expresses it as fractions.
    from gameify_notifications.huds.shield_health import ShieldHealthModel
    halo = load_huds()["halo"]
    assert isinstance(ge, ShieldHealthModel) and isinstance(halo, ShieldHealthModel)
    for d in (0.0, 2.5, 5.0, 7.5, 10.0):
        ctx = make_ctx(total_weight=d, full_at=10.0)
        su, hu, sr, hr = halo.shield_health(ctx)        # units form (Halo)
        sfrac, hfrac = ge.levels(ctx)                   # fraction form (GoldenEye)
        assert sfrac == (sr / su if su else 0.0)
        assert hfrac == (hr / hu if hu else 0.0)


def test_levels_honor_shield_fraction(ge, make_ctx):
    s, h = ge.levels(make_ctx(total_weight=0.0, full_at=10.0,
                              params={"shield_fraction": 0.8}))
    assert (s, h) == (1.0, 1.0)
    # 8 shield / 2 health: 8 damage empties shield exactly, health full
    s, h = ge.levels(make_ctx(total_weight=8.0, full_at=10.0,
                              params={"shield_fraction": 0.8}))
    assert s == 0.0 and h == 1.0


# ---- rendering: both arcs draw, and the right arc empties first -----------
def test_both_arcs_render_when_full(ge, make_ctx):
    img = render_to_image(ge, 260, 230, make_ctx(total_weight=0.0, full_at=10.0,
                                                 w=260, h=230))
    warm, blue = _counts(img)
    assert warm > 0 and blue > 0        # health (warm) AND shield (blue) visible


def test_shield_arc_empties_before_health_arc(ge, make_ctx):
    # damage = shield allotment -> shield ticks all dim, health ticks all lit
    img = render_to_image(ge, 260, 230, make_ctx(total_weight=5.0, full_at=10.0,
                                                 w=260, h=230))
    warm, blue = _counts(img)
    assert warm > 0 and blue == 0       # health remains, shield gone
