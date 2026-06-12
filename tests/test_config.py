"""State persistence (config.save_state/load_state/save_rect) -- the merge
round-trip the panel + widget geometry rely on. Uses the isolated config dir."""

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
