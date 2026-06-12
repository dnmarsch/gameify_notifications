"""Notification classification (uses the shipped default rules in the isolated
config dir)."""

import pytest

from gameify_notifications.rules import RuleSet


@pytest.fixture
def rules():
    return RuleSet()


@pytest.mark.parametrize("app,summary,body,expected", [
    # Chrome delivers Teams/Outlook with the site origin in the body
    ("Google Chrome", "Collin Kessinger", "teams.cloud.microsoft", ("Teams message", 1.5)),
    ("Google Chrome", "Collin Kessinger", "teams.microsoft.com", ("Teams message", 1.5)),
    ("Google Chrome", "Derek Marsch", "outlook.cloud.microsoft", ("Outlook email", 0.5)),
    ("Google Chrome", "Inbox", "outlook.office.com", ("Outlook email", 0.5)),
    ("Slack", "general", "hello there", None),               # no rule -> ignored
    ("Google Chrome", "Some site", "example.com", None),     # other web notif -> ignored
])
def test_classify(rules, app, summary, body, expected):
    assert rules.classify(app, summary, body) == expected


def test_unmatched_is_ignored(rules):
    # a notification with no origin/app match returns None (dropped)
    assert rules.classify("Discord", "friend", "hello") is None


def test_defaults_loaded(rules):
    assert rules.full_at == 10.0
    assert 0 < rules.max_alpha <= 1.0


def test_default_hud_params_loaded(rules):
    # the shipped rules.toml documents [hud.halo] / [hud.cod] tuning tables
    assert rules.params_for("halo")["shield_fraction"] == 0.5
    assert rules.params_for("cod")["intensity"] == 0.5
    assert rules.params_for("nope") == {}          # unknown HUD -> empty


def test_hud_params_parsed_and_non_table_ignored():
    _write_rules("""
[hud.halo]
shield_fraction = 0.8
warning_at = 0.4

[hud]
cod = "oops not a table"

[[rule]]
name = "Ok"
app = "teams"
weight = 1.0
""")
    rs = RuleSet()
    assert rs.params_for("halo") == {"shield_fraction": 0.8, "warning_at": 0.4}
    assert rs.params_for("cod") == {}              # non-table entry dropped, no crash
    assert [r.name for r in rs.rules] == ["Ok"]    # rules still load


# --- robustness: a bad rule is logged and skipped, never crashes the rest ---
def _write_rules(text):
    from gameify_notifications import config
    config.rules_file().write_text(text)


def test_invalid_regex_rule_skipped_others_load(caplog):
    import logging
    _write_rules("""
[[rule]]
name = "Bad regex"
app = "teams"
match = "(unclosed"
weight = 3.0

[[rule]]
name = "Good"
app = "teams"
weight = 1.0
""")
    with caplog.at_level(logging.WARNING, logger="gameify_notifications.rules"):
        rs = RuleSet()
    names = [r.name for r in rs.rules]
    assert names == ["Good"]
    assert rs.classify("Microsoft Teams", "x", "y") == ("Good", 1.0)
    assert any("skipping invalid rule" in r.getMessage() for r in caplog.records)


def test_missing_name_rule_skipped():
    _write_rules("""
[[rule]]
app = "teams"
weight = 2.0

[[rule]]
name = "Ok"
app = "teams"
weight = 1.0
""")
    assert [r.name for r in RuleSet().rules] == ["Ok"]


def test_non_numeric_weight_rule_skipped():
    _write_rules("""
[[rule]]
name = "Bad weight"
app = "teams"
weight = "high"

[[rule]]
name = "Ok"
app = "teams"
weight = 1.0
""")
    assert [r.name for r in RuleSet().rules] == ["Ok"]


def test_bad_full_at_falls_back_to_default():
    _write_rules("""
full_at = "lots"

[[rule]]
name = "Ok"
app = "teams"
weight = 1.0
""")
    rs = RuleSet()
    assert rs.full_at == 6.0
    assert [r.name for r in rs.rules] == ["Ok"]


def test_malformed_toml_keeps_previous_rules():
    _write_rules("""
[[rule]]
name = "First"
app = "teams"
weight = 1.0
""")
    rs = RuleSet()
    assert [r.name for r in rs.rules] == ["First"]
    _write_rules("this is { not valid toml")
    changed = rs.reload(force=True)        # parse fails mid-edit
    assert changed is False
    assert [r.name for r in rs.rules] == ["First"]   # last-known-good kept


def test_malformed_toml_on_first_load_uses_defaults():
    _write_rules("not valid toml {{{")
    rs = RuleSet()                          # nothing loaded yet -> built-in defaults
    assert any(r.name == "Teams message" for r in rs.rules)


def test_rule_is_not_a_table_skipped():
    _write_rules("""
rule = "oops not a list of tables"
""")
    # 'rule' wrong type -> ignored, no rules, no crash
    assert RuleSet().rules == []


def test_focus_class_is_parsed_and_exposed_via_match():
    _write_rules("""
[[rule]]
name = "X"
app = "teams"
focus_class = 'crx_abc'
weight = 1.0
""")
    rule = RuleSet().match("Microsoft Teams", "s", "b")
    assert rule is not None and rule.name == "X"
    assert rule.focus_regex is not None and rule.focus_regex.search("CRX_ABC")  # case-insensitive
