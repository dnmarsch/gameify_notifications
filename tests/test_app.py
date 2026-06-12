"""App wiring: a notification flows through classification into damage state."""

from gameify_notifications.app import App
from gameify_notifications.huds import load_huds


def _app():
    return App(load_huds()["cod"], "teams", test_mode=True)


def test_on_notification_classifies_and_accumulates():
    app = _app()
    # Chrome puts the site origin in the body
    app.on_notification("Google Chrome", "Collin Kessinger", "teams.cloud.microsoft")
    assert len(app.state.items) == 1
    assert app.state.total_weight() == 1.5
    assert app.state.items[0].category == "Teams message"


def test_outlook_email_adds_mild_damage():
    app = _app()
    app.on_notification("Google Chrome", "Inbox", "outlook.cloud.microsoft")
    assert len(app.state.items) == 1
    assert app.state.total_weight() == 0.5
    assert app.state.items[0].category == "Outlook email"


def test_unmatched_app_is_ignored():
    app = _app()
    app.on_notification("Slack", "general", "hi there")
    assert app.state.items == []              # no rule -> dropped, no panel row


def test_close_callable_threaded_through_to_dismiss():
    app = _app()
    fired = []
    app.on_notification("Google Chrome", "Carol", "teams.cloud.microsoft",
                        close=lambda: fired.append(1))
    app.state.dismiss(app.state.items[0].id)
    assert fired == [1]


# ---- focus-based suppression -------------------------------------------------
_FOCUS_RULES = """
full_at = 10.0
max_alpha = 0.7
[[rule]]
name = "Teams message"
match = 'teams\\.cloud\\.microsoft'
focus_class = 'crx_teamsid'
weight = 1.5
"""


def _write_rules(text):
    from gameify_notifications import config
    config.rules_file().write_text(text)


def _app_with_probe(probe):
    from gameify_notifications.huds import load_huds
    return App(load_huds()["cod"], "teams", focus_probe=probe)


def test_focus_suppression_drops_when_focused():
    _write_rules(_FOCUS_RULES)
    app = _app_with_probe(lambda: "crx_teamsid")        # looking at Teams
    app.on_notification("Google Chrome", "Carol", "teams.cloud.microsoft")
    assert app.state.items == []                        # suppressed, no panel row


def test_focus_suppression_allows_when_focused_elsewhere():
    _write_rules(_FOCUS_RULES)
    app = _app_with_probe(lambda: "crx_somethingelse")  # looking at another app
    app.on_notification("Google Chrome", "Carol", "teams.cloud.microsoft")
    assert len(app.state.items) == 1                    # damage as normal


def test_focus_suppression_disabled_without_probe():
    _write_rules(_FOCUS_RULES)
    app = _app_with_probe(None)                         # suppression off
    app.on_notification("Google Chrome", "Carol", "teams.cloud.microsoft")
    assert len(app.state.items) == 1


def test_focus_probe_returning_none_does_not_suppress():
    _write_rules(_FOCUS_RULES)
    app = _app_with_probe(lambda: None)                 # probe can't tell
    app.on_notification("Google Chrome", "Carol", "teams.cloud.microsoft")
    assert len(app.state.items) == 1


def test_rule_without_focus_class_is_never_suppressed():
    _write_rules("""
full_at = 10.0
[[rule]]
name = "Teams message"
match = 'teams\\.cloud\\.microsoft'
weight = 1.5
""")
    app = _app_with_probe(lambda: "crx_anything")       # probe matches nothing relevant
    app.on_notification("Google Chrome", "Carol", "teams.cloud.microsoft")
    assert len(app.state.items) == 1                    # no focus_class -> always damage


def test_focus_suppression_when_visible_among_many():
    # probe returns a SET (multi-monitor): Teams visible somewhere -> suppress
    _write_rules(_FOCUS_RULES)
    app = _app_with_probe(lambda: {"firefox", "crx_teamsid", "code"})
    app.on_notification("Google Chrome", "Carol", "teams.cloud.microsoft")
    assert app.state.items == []


def test_no_suppression_when_app_not_on_screen():
    _write_rules(_FOCUS_RULES)
    app = _app_with_probe(lambda: {"firefox", "code"})  # Teams not visible anywhere
    app.on_notification("Google Chrome", "Carol", "teams.cloud.microsoft")
    assert len(app.state.items) == 1
