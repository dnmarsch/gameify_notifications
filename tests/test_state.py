"""DamageState: accumulation, dismissal (healing), clear, and observer events."""

from gameify_notifications.state import DamageState


def test_add_accumulates_weight():
    s = DamageState()
    s.add("a", "b", "Call", 4.0)
    s.add("c", "d", "DM", 0.0)
    assert len(s.items) == 2
    assert s.total_weight() == 4.0


def test_dismiss_heals():
    s = DamageState()
    n = s.add("a", "b", "Call", 4.0)
    s.add("c", "d", "Meeting", 3.0)
    s.dismiss(n.id)
    assert s.total_weight() == 3.0
    assert len(s.items) == 1


def test_clear():
    s = DamageState()
    s.add("a", "b", "Call", 4.0)
    s.clear()
    assert s.items == []
    assert s.total_weight() == 0.0


def test_observer_fires_on_change():
    s = DamageState()
    events = []
    s.subscribe(lambda kind: events.append(kind))
    n = s.add("a", "b", "Call", 4.0)
    s.dismiss(n.id)
    s.clear()  # nothing to clear -> no event
    assert events == ["add", "change"]


def test_unique_ids():
    s = DamageState()
    a = s.add("a", "", "x", 1.0)
    b = s.add("b", "", "x", 1.0)
    assert a.id != b.id


def test_dismiss_fires_close():
    s = DamageState()
    fired = []
    n = s.add("a", "b", "Call", 1.0, close=lambda: fired.append("x"))
    s.dismiss(n.id)
    assert fired == ["x"]
    assert s.items == []


def test_clear_fires_close_on_all():
    s = DamageState()
    fired = []
    s.add("a", "", "x", 1.0, close=lambda: fired.append("a"))
    s.add("b", "", "y", 1.0, close=lambda: fired.append("b"))
    s.clear()
    assert sorted(fired) == ["a", "b"]


def test_close_errors_are_swallowed():
    s = DamageState()
    def boom():
        raise RuntimeError("nope")
    n = s.add("a", "b", "x", 1.0, close=boom)
    s.dismiss(n.id)              # must not raise
    assert s.items == []
