"""Pure geometry: off-screen clamp, fractional rescale, centering, max-fraction."""

from gameify_notifications.geometry import (
    Rect, monitor_for_point, virtual_bounds, panel_visible_enough,
    default_panel_rect, center_rect, frac_rect_centered, rect_to_fractions,
    fractions_to_rect, clamp_rect, top_center_rect, frac_top_centered)

ONE = [Rect(0, 0, 1920, 1080)]
TWO = [Rect(0, 0, 1920, 1080), Rect(1920, 0, 1920, 1080)]


def test_monitor_for_point():
    assert monitor_for_point(TWO, 100, 100) == 0
    assert monitor_for_point(TWO, 2000, 100) == 1
    assert monitor_for_point(TWO, 5000, 5000) is None


def test_virtual_bounds_spans_all():
    assert virtual_bounds(TWO) == (0, 0, 3840, 1080)


def test_visible_enough_and_offscreen():
    assert panel_visible_enough([1800, 20, 360, 440], TWO)
    assert not panel_visible_enough([5000, 5000, 360, 440], TWO)


def test_clamp_snaps_offscreen_to_default():
    snapped = clamp_rect([5000, 5000, 360, 440], TWO, 0, default_panel_rect)
    assert panel_visible_enough(snapped, TWO)


def test_clamp_max_fraction():
    # ask for a window bigger than the monitor -> capped to <=95%
    huge = clamp_rect([0, 0, 5000, 5000], ONE, 0, default_panel_rect, max_frac=0.95)
    assert huge[2] <= int(1920 * 0.95)
    assert huge[3] <= int(1080 * 0.95)


def test_fractional_rescale_on_resolution_change():
    rect = [1920 + 100, 100, 960, 540]            # 50% x 50% of monitor #2
    mi, fr = rect_to_fractions(rect, TWO, 0)
    assert mi == 1
    assert abs(fr[2] - 0.5) < 1e-9 and abs(fr[3] - 0.5) < 1e-9
    shrunk = [Rect(0, 0, 1920, 1080), Rect(1920, 0, 1280, 720)]
    out = fractions_to_rect(mi, fr, shrunk, 0)
    assert out[2] == 640 and out[3] == 360        # still 50% x 50%


def test_rect_to_fractions_survives_zero_size_workarea():
    # a compositor briefly reporting a 0x0 screen during a hotplug must not crash
    mi, fr = rect_to_fractions([0, 0, 100, 50], [Rect(0, 0, 0, 0)], 0)
    assert mi == 0 and all(isinstance(v, float) for v in fr)   # no ZeroDivisionError


def test_center_rect_is_centered():
    r = center_rect(ONE, 0, 640, 160)
    assert r[0] == (1920 - 640) // 2
    assert panel_visible_enough(r, ONE)


def test_frac_rect_centered():
    r = frac_rect_centered(ONE, 0, 1 / 3, 1 / 6)
    assert r[2] == 640 and r[3] == 180


def test_top_center_rect_is_top_and_horizontally_centered():
    r = top_center_rect(ONE, 0, 640, 160, margin=8)
    assert r[0] == (1920 - 640) // 2          # horizontally centered
    assert r[1] == 8                          # at the top (margin), not vertically centered
    assert r[1] != (1080 - 160) // 2


def test_frac_top_centered():
    r = frac_top_centered(ONE, 0, 1 / 3, 1 / 6)
    assert r[0] == (1920 - 640) // 2 and r[1] <= 12
