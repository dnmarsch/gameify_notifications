"""The shared green->yellow->red fill-colour thresholds (Pokemon + Stardew)."""

from gameify_notifications.huds import bar_color, load_huds


def test_thresholds_inclusive_boundaries():
    assert bar_color.fill_color(1.00) == bar_color.GREEN
    assert bar_color.fill_color(0.70) == bar_color.GREEN     # boundary inclusive
    assert bar_color.fill_color(0.69) == bar_color.YELLOW
    assert bar_color.fill_color(0.30) == bar_color.YELLOW    # boundary inclusive
    assert bar_color.fill_color(0.29) == bar_color.RED
    assert bar_color.fill_color(0.00) == bar_color.RED


def test_thresholds_are_configurable():
    assert bar_color.fill_color(0.85, green_above=0.9, yellow_above=0.5) == bar_color.YELLOW
    assert bar_color.fill_color(0.40, green_above=0.9, yellow_above=0.5) == bar_color.RED


def test_pokemon_uses_the_shared_thresholds(qapp):
    # Pokemon delegates to bar_color -> Stardew gets the identical mapping
    poke = load_huds()["pokemon"]
    assert poke.GREEN == bar_color.GREEN
    assert poke.hp_color(1.0) == bar_color.GREEN
    assert poke.hp_color(0.5) == bar_color.YELLOW
    assert poke.hp_color(0.1) == bar_color.RED
