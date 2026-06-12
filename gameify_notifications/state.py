"""Accumulated notification "damage" and an observer hook. Stdlib-only, so the
damage model is fully unit-testable without any GUI.

Each notification may carry a `close` callable supplied by its source (e.g. the
D-Bus CloseNotification). Dismissing/clearing invokes it best-effort, so the
desktop notification is cleared too -- but the overlay never depends on it."""

import logging
import time
import traceback

log = logging.getLogger(__name__)


class Notif:
    __slots__ = ("id", "ts", "summary", "body", "category", "weight", "close")

    def __init__(self, nid, summary, body, category, weight, close=None):
        self.id = nid
        self.ts = time.time()
        self.summary = summary
        self.body = body
        self.category = category
        self.weight = weight
        self.close = close          # optional zero-arg callable, source-provided


class DamageState:
    """Holds captured notifications and notifies observers on change. The HUD's
    redness/shield is a pure function of total_weight(); dismissing heals."""

    def __init__(self):
        self.items = []          # oldest first
        self._next_id = 1
        self._observers = []
        # start in the past so the "new hit" flash doesn't fire on launch
        self.last_event = time.monotonic() - 3600.0

    def subscribe(self, fn):
        self._observers.append(fn)

    def _notify(self, kind):
        for fn in self._observers:
            try:
                fn(kind)
            except Exception:
                traceback.print_exc()

    @staticmethod
    def _fire_close(n):
        """Best-effort clear of the underlying desktop notification."""
        if n.close:
            try:
                n.close()
            except Exception:
                log.debug("close() failed for notification %s", n.id, exc_info=True)

    def add(self, summary, body, category, weight, close=None):
        n = Notif(self._next_id, summary, body, category, weight, close)
        self._next_id += 1
        self.items.append(n)
        self.last_event = time.monotonic()
        self._notify("add")
        return n

    def dismiss(self, nid):
        before = len(self.items)
        kept = []
        for n in self.items:
            if n.id == nid:
                self._fire_close(n)
            else:
                kept.append(n)
        self.items = kept
        if len(self.items) != before:
            self._notify("change")

    def clear(self):
        if self.items:
            for n in self.items:
                self._fire_close(n)
            self.items = []
            self._notify("change")

    def total_weight(self):
        return sum(n.weight for n in self.items)
