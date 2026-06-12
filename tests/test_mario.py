"""Mario "lives" HUD: the lives model, the icon-path fallback / validation, and
that the row visibly empties as damage rises."""

import pytest

from gameify_notifications import config
from gameify_notifications.huds import load_huds, render_to_image


@pytest.fixture
def mario(qapp):
    return load_huds()["mario"]


def _opaque(img, thresh=200):
    """Count clearly-opaque pixels (sampled) -- proxy for 'lit mushrooms'."""
    n = 0
    for y in range(0, img.height(), 3):
        for x in range(0, img.width(), 3):
            if img.pixelColor(x, y).alpha() > thresh:
                n += 1
    return n


# ---- registration ---------------------------------------------------------
def test_mario_is_registered(qapp):
    assert "mario" in load_huds()


# ---- pure lives model -----------------------------------------------------
def test_lives_total_remaining_and_clamp(mario, make_ctx):
    assert mario.lives(make_ctx(total_weight=0.0, full_at=10.0)) == (10, 10.0)
    assert mario.lives(make_ctx(total_weight=3.0, full_at=10.0)) == (10, 7.0)
    assert mario.lives(make_ctx(total_weight=10.0, full_at=10.0)) == (10, 0.0)
    assert mario.lives(make_ctx(total_weight=15.0, full_at=10.0)) == (10, 0.0)  # clamp
    assert mario.lives(make_ctx(total_weight=2.5, full_at=10.0)) == (10, 7.5)   # fractional


def test_lives_total_rounds_full_at(mario, make_ctx):
    assert mario.lives(make_ctx(full_at=11.0))[0] == 11
    assert mario.lives(make_ctx(full_at=0.0))[0] == 1        # never zero slots


# ---- icon_path validation / fallback --------------------------------------
def test_icon_path_validation(mario, make_ctx):
    bad = mario.tuned(make_ctx(params={"icon_path": "/no/such/file.png",
                                       "lost_opacity": 2.0}))
    assert bad["icon_path"] == ""              # nonexistent path -> default (bundled)
    assert bad["lost_opacity"] == 0.18         # out of range -> default
    real = str(config.assets_dir() / "mushroom.png")
    assert mario.tuned(make_ctx(params={"icon_path": real}))["icon_path"] == real


def test_missing_icon_path_still_renders_bundled(mario, make_ctx):
    img = render_to_image(mario, 600, 96,
                          make_ctx(total_weight=0.0, full_at=5.0,
                                   params={"icon_path": "/no/such.png"}))
    assert _opaque(img) > 0                    # fell back to the bundled mushroom


# ---- rendering: the row empties as damage rises ---------------------------
_MP = {"lost_opacity": 0.18, "gap": 0.12, "warning_at": 0.25}


def test_full_lives_more_opaque_than_fewer(mario, make_ctx):
    w, h = 600, 96
    full = render_to_image(mario, w, h, make_ctx(total_weight=0.0, full_at=10.0, w=w, h=h, params=_MP))
    half = render_to_image(mario, w, h, make_ctx(total_weight=5.0, full_at=10.0, w=w, h=h, params=_MP))
    empty = render_to_image(mario, w, h, make_ctx(total_weight=10.0, full_at=10.0, w=w, h=h, params=_MP))
    assert _opaque(full) > _opaque(half) > _opaque(empty)


def test_lost_opacity_zero_hides_lost_lives(mario, make_ctx):
    w, h = 600, 96
    hidden = {"lost_opacity": 0.0, "gap": 0.12, "warning_at": 0.25}
    # 5 of 10 lost; with lost_opacity 0 the lost half draws nothing
    img = render_to_image(mario, w, h,
                          make_ctx(total_weight=5.0, full_at=10.0, w=w, h=h, params=hidden))
    full = render_to_image(mario, w, h,
                           make_ctx(total_weight=0.0, full_at=10.0, w=w, h=h, params=hidden))
    assert 0 < _opaque(img) < _opaque(full)
