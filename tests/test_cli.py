"""Startup HUD resolution: --hud wins and is remembered; with no --hud the
last-selected HUD (persisted in rules.toml under `active_hud`) is used."""

from gameify_notifications.__main__ import choose_hud

AVAILABLE = {"cod": 1, "halo": 1, "pokemon": 1, "goldeneye": 1, "mario": 1}


def test_explicit_hud_wins_over_persisted():
    assert choose_hud("halo", "pokemon", AVAILABLE) == "halo"


def test_no_arg_uses_persisted():
    assert choose_hud(None, "pokemon", AVAILABLE) == "pokemon"


def test_no_arg_no_persisted_defaults_to_cod():
    assert choose_hud(None, None, AVAILABLE) == "cod"


def test_unknown_name_falls_back_to_default():
    assert choose_hud("nope", None, AVAILABLE) == "cod"
    assert choose_hud(None, "stale", AVAILABLE) == "cod"   # persisted HUD removed/renamed
