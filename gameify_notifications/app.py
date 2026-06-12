"""Platform-agnostic application context. Holds the damage state, the rule set,
the active HUD, and the notification->state classification. No GUI toolkit and
no notification transport here -- backends present it; sources feed it."""

import logging

from .rules import RuleSet
from .state import DamageState

log = logging.getLogger(__name__)


class App:
    def __init__(self, hud, match_substr, test_mode=False, focus_probe=None):
        self.rules = RuleSet()
        self.state = DamageState()
        self.hud = hud
        self.match = match_substr
        self.test_mode = test_mode
        # zero-arg callable -> focused app/window id (or None); enables the
        # per-rule `focus_class` suppression. None disables it entirely.
        self.focus_probe = focus_probe

    def on_notification(self, app_name, summary, body, close=None):
        """Classify an incoming notification and add it to the damage state.
        `close` (optional) is a source-provided callable to clear the desktop
        notification when this item is dismissed. Safe to call from the UI
        thread (backends marshal onto it)."""
        self.rules.reload()  # pick up live edits to rules.toml
        rule = self.rules.match(app_name, summary, body)
        if rule is None:
            log.debug("ignored notification app=%r summary=%r (no matching rule)",
                      app_name, summary)
            return False
        # don't add damage for an app that's already on screen (any monitor)
        if rule.focus_regex is not None and self.focus_probe is not None:
            onscreen = self.focus_probe() or ()
            if isinstance(onscreen, str):
                onscreen = (onscreen,)
            hit = next((c for c in onscreen if rule.focus_regex.search(c)), None)
            if hit:
                log.debug("suppressed app=%r summary=%r: on-screen window %r matches "
                          "rule '%s'", app_name, summary, hit, rule.name)
                return False
        log.debug("notification app=%r summary=%r -> category=%s weight=%s",
                  app_name, summary, rule.name, rule.weight)
        self.state.add(summary, body, rule.name, rule.weight, close=close)
        return False  # convenient for GLib.idle_add / Qt slot
