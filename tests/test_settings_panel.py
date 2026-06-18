"""Settings panel: auto-generated controls write back to rules.toml (live), the
HUD dropdown switches + persists, and the panel exposes the ⚙ toggle."""

import tomllib

import pytest

from gameify_notifications import config
from gameify_notifications.backends.qt.settings_panel import SettingsPanel, GLOBAL_PARAMS
from gameify_notifications.backends.qt.panel_window import PanelWindow
from PySide6.QtWidgets import QSlider, QCheckBox


def _toml():
    return tomllib.loads(config.rules_file().read_text())


def _settings(qtbot, make_app, hud="halo"):
    app = make_app(hud)
    s = SettingsPanel(app, _huds())
    qtbot.addWidget(s)
    return app, s


def _huds():
    from gameify_notifications.huds import load_huds
    return load_huds()


def test_dropdown_shows_display_names_mapped_to_internal_names(qtbot, make_app):
    _app, s = _settings(qtbot, make_app, "cod")
    items = {s.hud_combo.itemText(i): s.hud_combo.itemData(i)
             for i in range(s.hud_combo.count())}
    # friendly display text -> internal name used by --hud / [hud.<name>]
    assert items["Call Of Duty"] == "cod"
    assert items["Pokémon"] == "pokemon"
    assert items["GoldenEye"] == "goldeneye"
    assert s.hud_combo.currentData() == "cod"        # reflects the active HUD


def test_builds_controls_for_global_and_active_hud(qtbot, make_app):
    _app, s = _settings(qtbot, make_app, "halo")
    # a slider exists for a global knob and for a halo-specific knob
    assert s.findChild(QSlider, "settings.max_messages") is not None
    assert s.findChild(QSlider, "settings.shield_fraction") is not None
    assert s.findChild(QCheckBox, "settings.dock_panel") is not None


def test_cod_hides_inapplicable_settings(qtbot, make_app):
    # cod: width/height meaningless; weight_scale/max_alpha/dock_panel hidden
    # (cod ignores max_alpha and never docks) -> none should appear.
    from PySide6.QtWidgets import QCheckBox
    _app, s = _settings(qtbot, make_app, "cod")
    for hidden in ("width", "height", "weight_scale", "max_alpha"):
        assert s.findChild(QSlider, f"settings.{hidden}") is None
    assert s.findChild(QCheckBox, "settings.dock_panel") is None
    assert s.findChild(QSlider, "settings.intensity") is not None      # cod knobs remain
    assert s.findChild(QSlider, "settings.max_messages") is not None   # global capacity still shown


def test_widget_hud_shows_size_and_weight_scale(qtbot, make_app):
    _app, s = _settings(qtbot, make_app, "halo")
    for shown in ("width", "height", "weight_scale"):
        assert s.findChild(QSlider, f"settings.{shown}") is not None


def test_max_alpha_shown_only_for_halo(qtbot, make_app):
    # max_alpha now only affects Halo's WARNING border -> hidden elsewhere
    _h, halo = _settings(qtbot, make_app, "halo")
    assert halo.findChild(QSlider, "settings.max_alpha") is not None
    for name in ("pokemon", "mario", "goldeneye", "cod"):
        _a, s = _settings(qtbot, make_app, name)
        assert s.findChild(QSlider, "settings.max_alpha") is None


def test_path_param_has_browse_button(qtbot, make_app):
    from PySide6.QtWidgets import QLineEdit, QPushButton
    _app, s = _settings(qtbot, make_app, "pokemon")
    assert s.findChild(QLineEdit, "settings.icon_path") is not None   # still typeable
    assert s.findChild(QPushButton, "settings.browse.icon_path") is not None


def test_reset_button_restores_hud_defaults(qtbot, make_app):
    app = make_app("halo")
    s = SettingsPanel(app, _huds())
    qtbot.addWidget(s)
    s.findChild(QSlider, "settings.shield_fraction").setValue(0)   # change away from default
    assert _toml()["hud"]["halo"]["shield_fraction"] == 0.0
    s.reset_btn.click()
    # the [hud.halo] table is dropped -> reverts to the spec default (0.5)
    assert "halo" not in _toml().get("hud", {})


def test_each_control_has_info_icon_with_help_tooltip(qtbot, make_app):
    from PySide6.QtWidgets import QLabel
    _app, s = _settings(qtbot, make_app, "halo")
    info = s.findChild(QLabel, "settings.info.shield_fraction")
    assert info is not None and info.text() == "ⓘ"
    assert "shield" in info.toolTip().lower()          # help text shows on hover
    assert s.findChild(QLabel, "settings.info.max_alpha").toolTip()  # global knobs too
    # black icon on a light badge -> the tooltip inherits black (readable) text
    ss = info.styleSheet()
    assert "color:#101010" in ss and "background:#cdd9e3" in ss


def test_slider_edit_writes_back_to_toml_and_calls_on_change(qtbot, make_app):
    changed = []
    app = make_app("halo")
    s = SettingsPanel(app, _huds(), on_change=lambda: changed.append(1))
    qtbot.addWidget(s)
    sl = s.findChild(QSlider, "settings.shield_fraction")
    sl.setValue(sl.maximum())                       # drag to 1.0
    assert _toml()["hud"]["halo"]["shield_fraction"] == 1.0
    assert changed                                   # on_change (repaint) fired


def test_text_field_commits_on_each_keystroke(qtbot, make_app):
    # a text param (pokemon name) persists as you type -- no Enter / focus-out
    from PySide6.QtWidgets import QLineEdit
    _app, s = _settings(qtbot, make_app, "pokemon")
    le = s.findChild(QLineEdit, "settings.name")
    le.clear()
    qtbot.keyClicks(le, "Cha")                       # type three keys
    assert _toml()["hud"]["pokemon"]["name"] == "Cha"   # committed mid-typing


def test_global_slider_writes_top_level_key(qtbot, make_app):
    _app, s = _settings(qtbot, make_app, "halo")
    sl = s.findChild(QSlider, "settings.max_messages")
    sl.setValue(sl.maximum())                        # ticks 0..49 over values 1..50
    assert _toml()["max_messages"] == 50


def test_width_slider_triggers_live_resize(qtbot, make_app):
    resized = []
    app = make_app("halo")
    s = SettingsPanel(app, _huds(), on_resize=lambda: resized.append(1))
    qtbot.addWidget(s)
    s.findChild(QSlider, "settings.width").setValue(5)   # any width change
    assert resized                                        # on_resize fired -> live resize
    assert "width" in _toml()["hud"]["halo"]              # and persisted


def test_non_size_slider_does_not_trigger_resize(qtbot, make_app):
    resized = []
    app = make_app("halo")
    s = SettingsPanel(app, _huds(), on_resize=lambda: resized.append(1))
    qtbot.addWidget(s)
    s.findChild(QSlider, "settings.shield_fraction").setValue(3)
    assert resized == []                                  # only width/height resize


def test_controller_apply_size_resizes_widget(qtbot, make_app, single_monitor):
    from gameify_notifications.backends.qt.hud_controller import HudController
    from gameify_notifications.backends.qt.widget_window import WidgetWindow
    from gameify_notifications.backends.qt.overlay_window import OverlayWindow
    from gameify_notifications.backends.qt.panel_window import PanelWindow
    app = make_app("halo")
    widget = WidgetWindow(app, monitors_provider=single_monitor)
    overlay = OverlayWindow(app)
    panel = PanelWindow(app, monitors_provider=single_monitor)
    for w in (widget, overlay, panel):
        qtbot.addWidget(w)
    ctl = HudController(app, widget, overlay, panel, _huds())
    app.rules.hud_params = {"halo": {"width": 500, "height": 300}}
    ctl.apply_size()
    assert (widget.width(), widget.height()) == (500, 300)


def test_toggle_writes_bool(qtbot, make_app):
    _app, s = _settings(qtbot, make_app, "halo")
    cb = s.findChild(QCheckBox, "settings.dock_panel")
    cb.setChecked(False)
    assert _toml()["dock_panel"] is False


def test_hud_dropdown_switches_persists_and_rebuilds(qtbot, make_app):
    picked = []
    app = make_app("halo")
    huds = _huds()
    # on_hud mirrors the real controller.set_hud: it updates app.hud
    def on_hud(n):
        picked.append(n)
        app.hud = huds[n]
    s = SettingsPanel(app, huds, on_hud=on_hud)
    qtbot.addWidget(s)
    s._select_combo("pokemon")                       # select by internal name (shows "Pokémon")
    s._on_hud_selected(0)
    assert picked == ["pokemon"]                     # controller.set_hud got the internal name
    assert _toml()["active_hud"] == "pokemon"        # persisted under its own key (not "hud")
    # rebuilt for pokemon -> a pokemon-only control is present
    from PySide6.QtWidgets import QLineEdit
    assert s.findChild(QLineEdit, "settings.name") is not None


def test_building_guard_blocks_spurious_writes(qtbot, make_app):
    # building the controls sets slider values; that must NOT write to the file
    app = make_app("halo")
    config.rules_file().write_text("max_messages = 10.0\n[hud.halo]\nshield_fraction = 0.5\n")
    SettingsPanel(app, _huds())                      # builds in __init__
    assert _toml()["hud"]["halo"]["shield_fraction"] == 0.5   # untouched by build


# ---- panel integration ----------------------------------------------------
def test_rebuild_recomputes_form_size_for_new_hud(qtbot, make_app):
    # switching to a HUD with more controls must yield a taller form hint (the
    # window then re-fits) -- guards the "shrinks and never re-expands" bug.
    app = make_app("cod")
    huds = _huds()
    s = SettingsPanel(app, huds)
    qtbot.addWidget(s)
    cod_h = s._form.sizeHint().height()
    app.hud = huds["pokemon"]                          # more params than cod
    s.build()
    assert s._form.sizeHint().height() > cod_h
    assert s.height() > s.header.sizeHint().height()   # window didn't collapse to the header


def test_all_settings_params_have_help(qtbot, make_app):
    # every knob the settings menu shows must document itself (constitution)
    from gameify_notifications.backends.qt.settings_panel import GLOBAL_PARAMS
    for p in GLOBAL_PARAMS:
        assert p.help, f"global param {p.name} missing help"
    for hud in _huds().values():
        for p in hud._spec()._params.values():
            assert p.help, f"{hud.name}.{p.name} missing help"


def test_damage_source_weight_slider_writes_back(qtbot, make_app):
    # the shipped default rules give Teams (idx 0) + Outlook (idx 1)
    _app, s = _settings(qtbot, make_app, "halo")
    sl = s.findChild(QSlider, "settings.rule.weight.0")
    assert sl is not None
    sl.setValue(sl.maximum())                        # 0..10 ticks over 0..5 weight
    assert _toml()["rule"][0]["weight"] == 5.0


def test_damage_source_matcher_is_read_only_tooltip(qtbot, make_app):
    from PySide6.QtWidgets import QLabel
    _app, s = _settings(qtbot, make_app, "halo")
    info = s.findChild(QLabel, "settings.rule.info.0")
    assert info is not None and "read-only" in info.toolTip().lower()


def test_reset_damage_source_weights_button(qtbot, make_app):
    _app, s = _settings(qtbot, make_app, "halo")
    s.findChild(QSlider, "settings.rule.weight.0").setValue(0)   # mute Teams (idx 0)
    assert _toml()["rule"][0]["weight"] == 0.0
    s.rules_reset_btn.click()
    assert _toml()["rule"][0]["weight"] == 1.5        # restored to Teams' shipped default


def test_close_button_hides_settings(qtbot, make_app):
    _app, s = _settings(qtbot, make_app, "halo")
    s.show()
    assert not s.isHidden()
    s.close_btn.click()
    assert s.isHidden()                              # ✕ dismisses without the gear/collapse dance


def test_panel_gear_toggles_settings(qtbot, make_app):
    p = PanelWindow(make_app("halo"))
    qtbot.addWidget(p)
    # isHidden() reflects the explicit show/hide state without needing the
    # top-level panel itself to be shown.
    assert p.settings.isHidden()
    p.settings_btn.click()
    assert not p.settings.isHidden()
    p.settings_btn.click()
    assert p.settings.isHidden()
