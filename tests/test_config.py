"""State persistence (config.save_state/load_state/save_rect) -- the merge
round-trip the panel + widget geometry rely on. Uses the isolated config dir."""

import tomllib

from gameify_notifications import config


def test_save_state_merges_keys():
    config.save_state("a", [1, 2, 3])
    config.save_state("b", {"x": 1})         # must not clobber "a"
    assert config.load_state("a") == [1, 2, 3]
    assert config.load_state("b") == {"x": 1}


def test_load_state_missing_is_none():
    assert config.load_state("does-not-exist") is None


def test_rect_roundtrip_and_coercion():
    config.save_rect("panel", [10.0, 20.0, 300.0, 400.0])
    assert config.load_rect("panel") == [10, 20, 300, 400]   # coerced to ints


def test_load_rect_rejects_bad_shape():
    config.save_state("panel", [1, 2, 3])    # wrong length
    assert config.load_rect("panel") is None


# ---- live config writeback (GUI -> rules.toml) ----------------------------
def _toml():
    return tomllib.loads(config.rules_file().read_text())


def test_set_top_level_value_preserves_comments():
    config.rules_file().write_text(
        "# my header\nmax_messages = 10.0   # capacity\n\n[hud.halo]\nshield_fraction = 0.5\n")
    config.set_config_value(["max_messages"], 25)
    text = config.rules_file().read_text()
    assert "# my header" in text and "# capacity" in text   # comments kept
    d = _toml()
    assert d["max_messages"] == 25 and d["hud"]["halo"]["shield_fraction"] == 0.5


def test_set_nested_hud_value_roundtrips():
    config.rules_file().write_text("[hud.halo]\nshield_fraction = 0.5\n")
    config.set_config_value(["hud", "halo", "shield_fraction"], 0.8)
    assert _toml()["hud"]["halo"]["shield_fraction"] == 0.8


def test_set_creates_missing_table_and_key():
    config.rules_file().write_text("max_messages = 10.0\n")
    config.set_config_value(["hud", "pokemon", "level"], 99)
    assert _toml()["hud"]["pokemon"]["level"] == 99


def test_set_writes_atomically_no_tmp_left():
    config.set_config_value(["max_alpha"], 0.4)
    assert _toml()["max_alpha"] == 0.4
    leftovers = list(config.config_dir().glob("*.tmp"))
    assert leftovers == []                                  # tmp replaced, not orphaned


def test_set_value_types_roundtrip():
    config.set_config_value(["dock_panel"], False)
    config.set_config_value(["hud"], "halo")
    d = _toml()
    assert d["dock_panel"] is False and d["hud"] == "halo"
