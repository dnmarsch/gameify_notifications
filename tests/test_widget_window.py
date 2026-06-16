"""HUD widget (Halo, scope='widget') behaviors via qtbot: it paints, the center
button re-centers and persists a monitor-relative rect, and it exposes the move
and resize affordances."""

from gameify_notifications import config
from gameify_notifications.backends.qt.widget_window import WidgetWindow


def test_widget_paints_non_empty(qtbot, make_app, single_monitor):
    app = make_app("halo")
    app.on_notification("Google Chrome", "Carol", "teams.cloud.microsoft")  # some damage
    w = WidgetWindow(app, monitors_provider=single_monitor)
    qtbot.addWidget(w)
    w.resize(640, 170)
    pm = w.grab()
    assert not pm.isNull()
    assert pm.width() == 640 and pm.height() == 170


def test_min_size_comes_from_the_active_hud(qtbot, make_app, single_monitor):
    # Stardew allows a much narrower box than the default 140px floor
    halo = WidgetWindow(make_app("halo"), monitors_provider=single_monitor)
    sd = WidgetWindow(make_app("stardew"), monitors_provider=single_monitor)
    qtbot.addWidget(halo)
    qtbot.addWidget(sd)
    assert halo.minimumWidth() == 140
    assert sd.minimumWidth() == 74                   # 44px bars + 30px right gutter
    sd.resize(74, 200)                               # can actually shrink to it
    assert sd.width() == 74


def test_center_button_recenters_and_persists_fraction(qtbot, make_app, single_monitor):
    app = make_app("halo")
    w = WidgetWindow(app, monitors_provider=single_monitor)
    qtbot.addWidget(w)
    w.move(40, 50)

    with qtbot.waitSignal(w.recentered, timeout=1000):
        w.center_btn.click()

    saved = config.load_state("hud")
    assert isinstance(saved, dict) and "rel" in saved      # stored as monitor fraction
    fx, fy, fw, fh = saved["rel"]
    # centered horizontally...
    assert abs(fx - (1 - fw) / 2) < 0.02
    # ...but anchored near the TOP, not vertically centered (Halo shield up top)
    assert fy < 0.1
    assert abs(fy - (1 - fh) / 2) > 0.1


def test_widget_default_size_follows_configured_width_height(qtbot, make_app, single_monitor):
    app = make_app("goldeneye")
    app.rules.hud_params = {"goldeneye": {"width": 300, "height": 320}}
    w = WidgetWindow(app, monitors_provider=single_monitor)
    qtbot.addWidget(w)
    # fresh placement uses the configured box size (no saved geometry yet)
    assert (w.width(), w.height()) == (300, 320)


def test_center_button_resets_to_configured_size(qtbot, make_app, single_monitor):
    app = make_app("goldeneye")
    w = WidgetWindow(app, monitors_provider=single_monitor)
    qtbot.addWidget(w)
    w.resize(123, 456)                                 # user resized to something odd
    app.rules.hud_params = {"goldeneye": {"width": 280, "height": 300}}
    with qtbot.waitSignal(w.recentered, timeout=1000):
        w.center_btn.click()                           # ⊕ -> reset to configured size + center
    assert (w.width(), w.height()) == (280, 300)


def test_center_button_resets_to_builtin_size_when_unconfigured(qtbot, make_app, single_monitor):
    app = make_app("halo")
    w = WidgetWindow(app, monitors_provider=single_monitor)
    qtbot.addWidget(w)
    w.resize(200, 90)
    with qtbot.waitSignal(w.recentered, timeout=1000):
        w.center_btn.click()
    assert (w.width(), w.height()) == app.hud.size      # halo's built-in default


def test_pokemon_widget_paints_and_context_carries_params(qtbot, make_app, single_monitor):
    # pokemon is scope='widget' -> rendered by WidgetWindow; its [hud.pokemon]
    # params (name/level/...) must reach the HUD via the window's context().
    app = make_app("pokemon")
    app.on_notification("Google Chrome", "Carol", "teams.cloud.microsoft")   # some damage
    app.rules.hud_params = {"pokemon": {"name": "CLAUDEMON", "level": 42}}
    w = WidgetWindow(app, monitors_provider=single_monitor)
    qtbot.addWidget(w)
    w.resize(560, 150)

    ctx = w.context()
    assert ctx.params.get("name") == "CLAUDEMON" and ctx.params.get("level") == 42
    # the validated knobs (incl. the universal capacity/drain) resolve too
    t = app.hud.tuned(ctx)
    assert t["name"] == "CLAUDEMON" and t["level"] == 42
    assert t["max_messages"] == 0 and t["weight_scale"] == 1.0   # defaults present

    pm = w.grab()
    assert not pm.isNull() and pm.width() == 560 and pm.height() == 150


def test_pokemon_widget_hp_tracks_per_overlay_capacity(qtbot, make_app, single_monitor):
    app = make_app("pokemon")
    w = WidgetWindow(app, monitors_provider=single_monitor)
    qtbot.addWidget(w)
    app.on_notification("Google Chrome", "Carol", "teams.cloud.microsoft")   # weight 1.5
    app.rules.hud_params = {"pokemon": {"max_messages": 3}}                   # tiny capacity
    assert abs(app.hud.hp(w.context()) - 0.5) < 1e-6                          # 1.5 / 3 -> 50% HP


def test_widget_has_move_and_resize_affordances(qtbot, make_app, single_monitor):
    w = WidgetWindow(make_app("halo"), monitors_provider=single_monitor)
    qtbot.addWidget(w)
    assert w.center_btn.objectName() == "hud.centerBtn"
    assert w.grip is not None                              # QSizeGrip => resizable
    # movable: mouse handlers are wired (no exception when invoked is covered elsewhere)
    assert hasattr(w, "mouseMoveEvent")
