"""Dismiss panel widget behaviors via qtbot: collapse/expand, dismiss, clear,
and collapsed-state persistence."""

from PySide6.QtWidgets import QPushButton

from gameify_notifications.backends.qt.panel_window import PanelWindow


def test_collapse_to_toolbar_and_expand(qtbot, make_app):
    p = PanelWindow(make_app("cod"))
    qtbot.addWidget(p)
    assert not p.is_collapsed()

    with qtbot.waitSignal(p.collapsedChanged, timeout=1000):
        p.collapse_btn.click()
    assert p.is_collapsed()
    assert p.scroll.isHidden() and p.status.isHidden()   # body hidden -> toolbar

    with qtbot.waitSignal(p.collapsedChanged, timeout=1000):
        p.collapse_btn.click()
    assert not p.is_collapsed()
    assert not p.scroll.isHidden()                        # expanded back


def test_dismiss_removes_row_and_heals(qtbot, make_app):
    app = make_app("cod")
    app.on_notification("Google Chrome", "Carol", "teams.cloud.microsoft")
    p = PanelWindow(app)
    qtbot.addWidget(p)
    assert len(p.rows()) == 1

    with qtbot.waitSignal(p.dismissed, timeout=1000):
        p.rows()[0].findChild(QPushButton, "panel.dismissBtn").click()

    assert len(p.rows()) == 0
    assert app.state.total_weight() == 0.0


def test_clear_all(qtbot, make_app):
    app = make_app("cod")
    app.on_notification("Google Chrome", "Carol", "teams.cloud.microsoft")
    app.on_notification("Google Chrome", "Inbox", "outlook.cloud.microsoft")
    p = PanelWindow(app)
    qtbot.addWidget(p)
    assert len(p.rows()) == 2

    with qtbot.waitSignal(p.cleared, timeout=1000):
        p.clear_btn.click()
    assert len(p.rows()) == 0
    assert app.state.items == []


def test_new_notification_appears_live(qtbot, make_app):
    app = make_app("cod")
    p = PanelWindow(app)
    qtbot.addWidget(p)
    assert len(p.rows()) == 0
    app.on_notification("Google Chrome", "Carol", "teams.cloud.microsoft")  # state -> observer -> refresh
    assert len(p.rows()) == 1


def test_panel_lists_all_and_scrolls(qtbot, make_app):
    app = make_app("cod")
    p = PanelWindow(app)
    qtbot.addWidget(p)
    p.resize(360, 300)
    p.show()
    for i in range(20):
        app.on_notification("Google Chrome", f"Sender {i}", "teams.cloud.microsoft")
    assert len(p.rows()) == 20                    # no cap -- every notification listed
    # content exceeds the viewport -> the list scrolls
    qtbot.waitUntil(lambda: p.scroll.verticalScrollBar().maximum() > 0, timeout=2000)


def _teams(app, n):
    for i in range(n):
        app.on_notification("Google Chrome", f"S{i}", "teams.cloud.microsoft")  # weight 1.5


def test_damage_shown_as_percentage_not_raw_count(qtbot, make_app):
    app = make_app("cod")                         # max_messages 10, Teams weight 1.5
    p = PanelWindow(app)
    qtbot.addWidget(p)
    _teams(app, 2)                                # total weight 3.0 -> 3/10 = 30%
    assert "30%" in p.status.text()
    assert "/ 10" not in p.status.text()          # no more raw "x / 10" count


def test_damage_percent_uses_per_overlay_max_messages(qtbot, make_app):
    app = make_app("cod")
    p = PanelWindow(app)
    qtbot.addWidget(p)
    _teams(app, 2)                                # weight 3.0
    # the denominator is THIS overlay's max_messages, not the global max_messages
    app.rules.hud_params = {"cod": {"max_messages": 30}}
    p.refresh()
    assert "10%" in p.status.text()               # 3 / 30
    assert abs(p.damage_percent() - 10.0) < 1e-6


def test_damage_percent_uses_per_overlay_weight_scale(qtbot, make_app):
    app = make_app("cod")
    p = PanelWindow(app)
    qtbot.addWidget(p)
    _teams(app, 2)                                # weight 3.0
    app.rules.hud_params = {"cod": {"weight_scale": 2.0}}
    p.refresh()
    assert "60%" in p.status.text()               # (3 * 2) / 10
    assert abs(p.damage_percent() - 60.0) < 1e-6


def test_halo_panel_percent_is_shield_plus_health_total(qtbot, make_app):
    # For Halo the panel % must reflect the WHOLE pool (shield + health), not one
    # bar -- damage% + combined-remaining% == 100 (levels() only splits it 50/50
    # for rendering).
    from gameify_notifications.backends.qt._context import make_context
    app = make_app("halo")
    p = PanelWindow(app)
    qtbot.addWidget(p)
    _teams(app, 3)                                # weight 4.5 / 10 -> 45%
    assert abs(p.damage_percent() - 45.0) < 0.5
    ctx = make_context(app, [(0, 0, 1, 1)])
    su, hu, sr, hr = app.hud.levels(ctx)
    combined_remaining = (sr + hr) / (su + hu) * 100.0
    assert abs(p.damage_percent() + combined_remaining - 100.0) < 0.5


def test_panel_and_hud_share_one_context_builder(qtbot, make_app, single_monitor):
    # the panel's damage and the HUD's damage come from the same make_context()
    # source, so they can't drift.
    from gameify_notifications.backends.qt._context import make_context
    from gameify_notifications.backends.qt.widget_window import WidgetWindow
    app = make_app("halo")
    p = PanelWindow(app)
    qtbot.addWidget(p)
    w = WidgetWindow(app, monitors_provider=single_monitor)
    qtbot.addWidget(w)
    _teams(app, 2)
    # the window builds its context via make_context too; same params + fraction
    assert w.context().params == make_context(app, [(0, 0, 1, 1)]).params
    assert abs(app.hud.fraction(w.context()) * 100 - p.damage_percent()) < 1e-6


def test_damage_percent_clamps_at_100(qtbot, make_app):
    app = make_app("cod")
    p = PanelWindow(app)
    qtbot.addWidget(p)
    _teams(app, 20)                               # weight 30 >> max_messages 10
    assert p.damage_percent() == 100.0
    assert "100%" in p.status.text()


def test_collapsed_state_persists_across_instances(qtbot, make_app):
    p = PanelWindow(make_app("cod"))
    qtbot.addWidget(p)
    p.set_collapsed(True)
    p2 = PanelWindow(make_app("cod"))
    qtbot.addWidget(p2)
    assert p2.is_collapsed()
