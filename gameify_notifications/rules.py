"""Classify a notification into (category, damage weight) using user-editable,
hot-reloaded regex rules from rules.toml. Stdlib-only."""

import logging
import re

try:
    import tomllib  # py3.11+
except ModuleNotFoundError:  # pragma: no cover
    tomllib = None

from . import config

log = logging.getLogger(__name__)


def _as_float(value, default, field):
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        log.warning("rules.toml: %s=%r is not a number; using %s", field, value, default)
        return default


class Rule:
    """Matches on the notifying app name (`app`, regex) and/or the notification
    text (`pattern`, regex over "summary | body"). A regex that's absent is not
    a constraint; a rule with neither is a catch-all."""

    def __init__(self, name, weight, pattern=None, app=None, focus_class=None):
        self.name = name
        self.weight = float(weight)
        self.text_regex = re.compile(pattern, re.IGNORECASE) if pattern else None
        self.app_regex = re.compile(app, re.IGNORECASE) if app else None
        # if the active window's WM_CLASS/app matches this, suppress the damage
        self.focus_regex = re.compile(focus_class, re.IGNORECASE) if focus_class else None

    def matches(self, app_name, text):
        if self.app_regex is not None and not self.app_regex.search(app_name):
            return False
        if self.text_regex is not None and not self.text_regex.search(text):
            return False
        return True


class RuleSet:
    """Loads rules.toml and hot-reloads it when the file changes on disk."""

    def __init__(self):
        self.rules = []
        self.full_at = 6.0
        self.max_alpha = 0.7
        self.hud_params = {}          # {hud_name: {knob: value}} from [hud.<name>]
        self._mtime = None
        self.reload(force=True)

    def reload(self, force=False):
        path = config.rules_file()
        try:
            mtime = path.stat().st_mtime if path.exists() else 0
        except OSError:
            mtime = 0
        if not force and mtime == self._mtime:
            return False
        self._mtime = mtime
        text = path.read_text() if path.exists() else config.DEFAULT_RULES

        # Whole-file parse: if it's broken mid-edit, keep the last good rules
        # rather than silently reverting behavior; only fall back to defaults
        # when we have nothing loaded yet.
        try:
            data = tomllib.loads(text)
        except Exception:
            if self.rules:
                log.warning("rules.toml is not valid TOML; keeping the previously "
                            "loaded rules", exc_info=True)
                return False
            log.warning("rules.toml is not valid TOML; using built-in defaults",
                        exc_info=True)
            data = tomllib.loads(config.DEFAULT_RULES)

        self.full_at = _as_float(data.get("full_at"), 6.0, "full_at") or 6.0
        self.max_alpha = _as_float(data.get("max_alpha"), 0.7, "max_alpha")

        hud = data.get("hud", {})
        self.hud_params = {k: v for k, v in hud.items()
                           if isinstance(v, dict)} if isinstance(hud, dict) else {}

        raw = data.get("rule", [])
        if not isinstance(raw, list):
            log.warning("rules.toml: 'rule' must be a list of tables; ignoring it")
            raw = []

        # Per-rule: a single bad entry (missing name, bad regex, non-numeric
        # weight, wrong type) is logged and skipped -- it never breaks the rest.
        rules = []
        for i, r in enumerate(raw, start=1):
            try:
                if not isinstance(r, dict):
                    raise TypeError("rule entry is not a table")
                rule = Rule(r["name"], r.get("weight", 0.0),
                            r.get("match"), r.get("app"), r.get("focus_class"))
            except Exception as exc:
                log.warning("skipping invalid rule #%d (%r): %s", i, r, exc)
                continue
            rules.append(rule)
        self.rules = rules
        return True

    def match(self, app_name, summary, body):
        """Return the first matching Rule, or None (notification then ignored)."""
        text = f"{summary} | {body}"
        app = app_name or ""
        for rule in self.rules:
            if rule.matches(app, text):
                return rule
        return None

    def classify(self, app_name, summary, body):
        """Return (category, weight) for the first matching rule, else None."""
        rule = self.match(app_name, summary, body)
        return (rule.name, rule.weight) if rule else None

    def params_for(self, hud_name):
        """The [hud.<hud_name>] tuning table (or {} if absent)."""
        p = self.hud_params.get(hud_name)
        return p if isinstance(p, dict) else {}
