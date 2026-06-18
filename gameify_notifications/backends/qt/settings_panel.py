"""The Settings window -- a separate frameless popup toggled by the dismiss
panel's header ⚙. Kept out of the panel's fixed-height layout so its controls
never get squeezed; tall param lists scroll inside it.

Auto-generates controls from the param specs -- a HUD dropdown plus a slider /
checkbox / text field per tunable (global knobs + the active HUD's params) --
so adding a HUD or a Param surfaces here automatically. Editing a control writes
the value into rules.toml via config.set_config_value (comment-preserving),
force-reloads, and repaints, so the GUI and hand-edits are the same file.

Rebuilds its controls when opened or when the HUD changes (so it always shows
current values); live mirroring of a concurrent hand-edit while open is not done."""

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
                               QSlider, QCheckBox, QLineEdit, QScrollArea, QFrame,
                               QPushButton, QFileDialog)

from ... import config
from ...huds.params import Param

# Top-level rules.toml knobs (not part of any HUD spec) shown under "All HUDs".
GLOBAL_PARAMS = [
    Param("max_messages", 10, int, 1, 1000, ui_max=50, step=1,
          help="Global damage capacity: total notification weight at which the HUD is "
               "fully maxed (≈ unread messages at weight 1). Each HUD can override it below."),
    Param("max_alpha", 0.7, float, 0.0, 1.0,
          help="Opacity ceiling (0-1): the most opaque the overlay ever gets, so it "
               "never goes fully solid. Lower = more see-through."),
    Param("dock_panel", True, bool,
          help="Dock this dismiss panel under widget HUDs (halo/mario/pokemon/goldeneye). "
               "Off = a separate floating panel. Takes effect on restart."),
]

_STYLE = (
    "#panelSettings{background:rgba(18,20,26,245);"
    "border:1px solid rgba(255,255,255,40);}"
    " QLabel{color:#e8e8e8;}"
    # the ⓘ help tooltips: black text (the dark QLabel color was bleeding in and
    # killing contrast against the pale tooltip background)
    " QToolTip{color:#000000;background:#f5f2dc;border:1px solid #9a8f55;padding:3px;}"
    " #settingsHeader{background:rgba(255,255,255,20);"
    "border-bottom:1px solid rgba(255,255,255,30);}"
    " QComboBox,QLineEdit{color:#e8e8e8;background:rgba(255,255,255,18);"
    "border:1px solid rgba(255,255,255,30);border-radius:4px;padding:1px 4px;}"
    " QScrollBar:vertical{background:transparent;width:10px;margin:2px;}"
    " QScrollBar::handle:vertical{background:rgba(255,255,255,70);"
    "min-height:24px;border-radius:5px;}"
    " QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical{height:0;}"
)


def _fmt(v):
    return f"{v:g}" if isinstance(v, float) else str(v)


class SettingsPanel(QWidget):
    def __init__(self, app, huds, on_hud=None, on_change=None, on_resize=None, parent=None):
        super().__init__(parent)
        self.app = app
        self.huds = huds                         # name -> Hud instance
        self.on_hud = on_hud or (lambda name: None)
        self.on_change = on_change or (lambda: None)
        self.on_resize = on_resize or (lambda: None)   # apply width/height live
        self._building = False
        self._drag = None
        self.setObjectName("panelSettings")
        # a separate window so it isn't constrained by the panel's height
        self.setWindowFlags(Qt.Window | Qt.FramelessWindowHint
                            | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setStyleSheet(_STYLE)
        self.setMinimumWidth(340)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.header = QWidget()
        self.header.setObjectName("settingsHeader")
        self.header.setCursor(Qt.SizeAllCursor)
        hh = QHBoxLayout(self.header)
        hh.setContentsMargins(10, 6, 10, 6)
        title = QLabel("⚙  <b>Settings</b>")
        title.setTextFormat(Qt.RichText)
        title.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        hh.addWidget(title, 1)
        # explicit close (✕), inline at the top-right of the header, so the user
        # need not re-toggle the gear or collapse the panel to dismiss settings
        self.close_btn = QPushButton("✕")
        self.close_btn.setObjectName("settings.close")
        self.close_btn.setFixedWidth(26)
        self.close_btn.setToolTip("Close settings")
        self.close_btn.setStyleSheet(
            "QPushButton{color:#e8e8e8;background:transparent;border:none;"
            "font-weight:bold;padding:0 4px;} QPushButton:hover{color:#ff6b6b;}")
        self.close_btn.clicked.connect(self.hide)
        hh.addWidget(self.close_btn, 0)
        self.header.mousePressEvent = self._hdr_press
        self.header.mouseMoveEvent = self._hdr_move
        self.header.mouseReleaseEvent = self._hdr_release
        root.addWidget(self.header)

        self._hud_row = QWidget()
        hr = QHBoxLayout(self._hud_row)
        hr.setContentsMargins(10, 8, 10, 4)
        lbl = QLabel("HUD")
        lbl.setMinimumWidth(120)
        self.hud_combo = QComboBox()
        self.hud_combo.setObjectName("settings.hud")
        # show the friendly display name, carry the internal name as item data
        for hud in sorted(self.huds.values(), key=lambda x: (x.display or x.name).lower()):
            self.hud_combo.addItem(hud.display or hud.name, hud.name)
        self._select_combo(app.hud.name)
        self.hud_combo.activated.connect(self._on_hud_selected)
        hr.addWidget(lbl)
        hr.addWidget(self.hud_combo, 1)
        root.addWidget(self._hud_row)

        # param controls live in a scroll area so any height fits
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self._formw = QWidget()
        self._form = QVBoxLayout(self._formw)
        self._form.setContentsMargins(10, 4, 10, 10)
        self._form.setSpacing(4)
        self._form.addStretch(1)
        self.scroll.setWidget(self._formw)
        root.addWidget(self.scroll, 1)

        # footer: "Reset to defaults" centered below the list (full text, no truncation)
        self._footer = QWidget()
        fr = QHBoxLayout(self._footer)
        fr.setContentsMargins(10, 6, 10, 10)
        self.reset_btn = QPushButton("Reset to defaults")
        self.reset_btn.setObjectName("settings.reset")
        self.reset_btn.setToolTip("Reset this HUD's settings to their built-in defaults")
        self.reset_btn.clicked.connect(self._on_reset)
        fr.addStretch(1)
        fr.addWidget(self.reset_btn)
        fr.addStretch(1)
        root.addWidget(self._footer)
        self.build()

    # ---- (re)build the controls for the active HUD -----------------------
    def _select_combo(self, name):
        i = self.hud_combo.findData(name)
        if i >= 0:
            self.hud_combo.setCurrentIndex(i)

    def build(self):
        self._building = True
        try:
            self._select_combo(self.app.hud.name)
            while self._form.count() > 1:            # keep the trailing stretch
                w = self._form.takeAt(0).widget()
                if w:
                    w.setParent(None)
                    w.deleteLater()
            hud = self.app.hud
            hidden = set(getattr(hud, "HIDDEN_SETTINGS", ()))
            widget_scope = getattr(hud, "scope", "all") == "widget"
            self._add_header("All HUDs")
            for p in GLOBAL_PARAMS:
                if p.name in hidden:
                    continue                              # e.g. cod hides max_alpha/dock_panel
                self._add_control(p, [p.name], self._global_current(p))
            self._add_header(hud.name)
            for p in hud._spec()._params.values():
                if p.name in hidden:
                    continue                              # per-HUD decluttered knob
                if p.name in ("width", "height") and not widget_scope:
                    continue                              # box size is meaningless for cod
                self._add_control(p, ["hud", hud.name, p.name], self._hud_current(p))
            self._add_rules_section()                 # global per-notification weights
        finally:
            self._building = False
        self._fit()                              # best-effort now...
        QTimer.singleShot(0, self._fit)          # ...and again once the new rows are realized

    def _fit(self):
        """Size the window to its content, capped to ~85% of the screen. Activate
        the layout first so the size hint reflects the just-rebuilt controls
        (otherwise switching HUD shrinks and never re-expands)."""
        self._form.activate()
        chrome = (self.header.sizeHint().height() + self._hud_row.sizeHint().height()
                  + self._footer.sizeHint().height())
        want = chrome + self._form.sizeHint().height() + 8
        screen = QGuiApplication.primaryScreen()
        cap = int(screen.availableGeometry().height() * 0.85) if screen else 900
        self.resize(self.width() if self.width() > 340 else 360, min(want, cap))

    # ---- current values --------------------------------------------------
    def _global_current(self, p):
        r = self.app.rules
        if p.name == "dock_panel":
            return r.dock_panel
        if p.name == "max_alpha":
            return r.max_alpha
        return int(round(r.max_messages))

    def _hud_current(self, p):
        raw = self.app.rules.params_for(self.app.hud.name)
        return p.coerce(raw[p.name])[1] if p.name in raw else p.default

    # ---- control rows ----------------------------------------------------
    def _add_header(self, text):
        h = QLabel(f"<b>{text}</b>")
        h.setTextFormat(Qt.RichText)
        self._form.insertWidget(self._form.count() - 1, h)

    def _add_control(self, p, keys, current):
        kind = p.control()
        if kind == "slider":
            self._add_slider(p, keys, current)
        elif kind == "toggle":
            self._add_toggle(p, keys, current)
        else:
            self._add_text(p, keys, current)

    def _row(self, p):
        w = QWidget()
        h = QHBoxLayout(w)
        h.setContentsMargins(0, 0, 0, 0)
        lbl = QLabel(p.name)
        lbl.setMinimumWidth(112)
        h.addWidget(lbl)
        if getattr(p, "help", ""):
            info = QLabel("ⓘ")                 # ⓘ -- hover for help
            info.setObjectName(f"settings.info.{p.name}")
            info.setToolTip(p.help)
            # The tooltip inherits the icon's foreground color, so make the icon
            # BLACK (-> black, readable tooltip text) and put a light badge behind
            # it so the black ⓘ stays visible on the dark panel.
            info.setStyleSheet(
                "color:#101010; background:#cdd9e3; border:1px solid #9aa7b3;"
                " border-radius:7px; padding:0px 4px;")
            h.addWidget(info)
        self._form.insertWidget(self._form.count() - 1, w)
        return h

    def _add_slider(self, p, keys, current):
        lo, hi, step = p.slider()
        ticks = max(1, round((hi - lo) / step))

        def to_val(t):
            v = lo + t * step
            return int(round(v)) if p.kind is int else round(v, 4)

        def to_tick(v):
            return min(ticks, max(0, round((v - lo) / step)))

        h = self._row(p)
        slider = QSlider(Qt.Horizontal)
        slider.setObjectName(f"settings.{p.name}")
        slider.setRange(0, ticks)
        slider.setValue(to_tick(current))
        vlabel = QLabel(_fmt(to_val(slider.value())))
        vlabel.setMinimumWidth(46)
        vlabel.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

        def changed(t):
            v = to_val(t)
            vlabel.setText(_fmt(v))
            self._commit(keys, v)

        slider.valueChanged.connect(changed)
        h.addWidget(slider, 1)
        h.addWidget(vlabel)

    def _add_toggle(self, p, keys, current):
        h = self._row(p)
        cb = QCheckBox()
        cb.setObjectName(f"settings.{p.name}")
        cb.setChecked(bool(current))
        cb.toggled.connect(lambda c: self._commit(keys, bool(c)))
        h.addWidget(cb, 1)

    def _add_text(self, p, keys, current):
        h = self._row(p)
        le = QLineEdit(str(current))
        le.setObjectName(f"settings.{p.name}")
        # textEdited fires on every keystroke (no Enter/focus-out needed) but,
        # unlike textChanged, is NOT emitted for programmatic setText -- so the
        # build path and the Browse button below don't spuriously re-commit.
        le.textEdited.connect(lambda text: self._commit(keys, text))
        h.addWidget(le, 1)
        if getattr(p, "is_file", False):       # path param -> Browse, but typing still works
            browse = QPushButton("Browse…")
            browse.setObjectName(f"settings.browse.{p.name}")
            browse.clicked.connect(lambda: self._browse(le, keys))
            h.addWidget(browse)

    def _browse(self, line_edit, keys):
        import os
        start = os.path.dirname(line_edit.text()) or os.path.expanduser("~")
        path, _ = QFileDialog.getOpenFileName(
            self, "Choose image", start,
            "Images (*.png *.jpg *.jpeg *.gif *.webp);;All files (*)")
        if path:
            line_edit.setText(path)
            self._commit(keys, path)

    # ---- write-through ---------------------------------------------------
    def _commit(self, keys, value):
        if self._building:
            return
        config.set_config_value(keys, value)
        self.app.rules.reload(force=True)      # apply now (the 0.5s watch is the backstop)
        if keys[-1] in ("width", "height"):
            self.on_resize()                   # live-resize the widget HUD box
        self.on_change()

    # ---- global damage-source weights (rules.toml [[rule]]) --------------
    def _add_rules_section(self):
        """A 'Damage sources' section: one weight slider per rule (its matcher
        shown read-only), then a reset-to-default button. Built with the same
        row/slider helpers as the param controls."""
        self._add_header("Damage sources")
        for rule in self.app.rules.rules:
            self._add_rule_weight(rule)
        self._add_rules_reset()

    def _matcher_text(self, rule):
        """Read-only description of what a rule matches (edited only in rules.toml)."""
        parts = []
        if rule.app_regex is not None:
            parts.append(f"app matches  /{rule.app_regex.pattern}/")
        if rule.text_regex is not None:
            parts.append(f"text matches /{rule.text_regex.pattern}/")
        if rule.focus_regex is not None:
            parts.append(f"muted while focused: /{rule.focus_regex.pattern}/")
        if not parts:
            parts.append("matches every notification")
        return "Matcher (read-only -- edit in rules.toml):\n" + "\n".join(parts)

    def _add_rule_weight(self, rule):
        idx = rule.index
        row = QWidget()
        h = QHBoxLayout(row)
        h.setContentsMargins(0, 0, 0, 0)
        lbl = QLabel(rule.name)
        lbl.setMinimumWidth(112)
        h.addWidget(lbl)
        info = QLabel("ⓘ")                            # hover -> read-only matcher
        info.setObjectName(f"settings.rule.info.{idx}")
        info.setToolTip(self._matcher_text(rule))
        info.setStyleSheet(
            "color:#101010; background:#cdd9e3; border:1px solid #9aa7b3;"
            " border-radius:7px; padding:0px 4px;")
        h.addWidget(info)

        lo, hi, step = 0.0, 5.0, 0.5                  # 0 = listed, no redness (re-armable)
        ticks = int(round((hi - lo) / step))
        slider = QSlider(Qt.Horizontal)
        slider.setObjectName(f"settings.rule.weight.{idx}")
        slider.setRange(0, ticks)
        slider.setValue(min(ticks, max(0, round(rule.weight / step))))
        vlabel = QLabel(_fmt(round(slider.value() * step, 2)))
        vlabel.setMinimumWidth(46)
        vlabel.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

        def changed(t):
            val = round(t * step, 2)
            vlabel.setText(_fmt(val))
            self._commit_rule_weight(idx, val)

        slider.valueChanged.connect(changed)
        h.addWidget(slider, 1)
        h.addWidget(vlabel)
        self._form.insertWidget(self._form.count() - 1, row)

    def _commit_rule_weight(self, index, value):
        if self._building or index is None:
            return
        config.set_rule_weight(index, value)
        self.app.rules.reload(force=True)
        self.on_change()

    def _add_rules_reset(self):
        row = QWidget()
        h = QHBoxLayout(row)
        h.setContentsMargins(0, 6, 0, 2)
        self.rules_reset_btn = QPushButton("Reset damage source weights")
        self.rules_reset_btn.setObjectName("settings.rules.reset")
        self.rules_reset_btn.setToolTip(
            "Reset every damage source's weight to the default "
            f"({config.DEFAULT_RULE_WEIGHT:g})")
        self.rules_reset_btn.clicked.connect(self._on_reset_rules)
        h.addStretch(1)
        h.addWidget(self.rules_reset_btn)
        h.addStretch(1)
        self._form.insertWidget(self._form.count() - 1, row)

    def _on_reset_rules(self):
        config.reset_rule_weights()
        self.app.rules.reload(force=True)
        self.on_change()
        self.build()                                  # sliders now show the default weight

    def _on_hud_selected(self, _index):
        name = self.hud_combo.currentData()       # internal name, not the display text
        # NB: a dedicated top-level key -- NOT "hud", which is the table namespace
        # for per-HUD tuning ([hud.<name>]); writing a string there would clobber
        # every HUD's saved params.
        config.set_config_value(["active_hud"], name)
        self.on_hud(name)                      # controller.set_hud -> app.hud updates
        self.build()                           # show the newly-selected HUD's params

    def _on_reset(self):
        """Reset the active HUD's settings to defaults (drop its [hud.*] table)."""
        config.reset_hud(self.app.hud.name)
        self.app.rules.reload(force=True)
        self.on_resize()                       # box size may revert to the built-in default
        self.on_change()                       # repaint with defaults
        self.build()                           # controls now show the defaults

    # ---- drag to move ----------------------------------------------------
    def _hdr_press(self, ev):
        if ev.button() == Qt.LeftButton:
            self._drag = ev.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def _hdr_move(self, ev):
        if self._drag is not None and (ev.buttons() & Qt.LeftButton):
            self.move(ev.globalPosition().toPoint() - self._drag)

    def _hdr_release(self, ev):
        self._drag = None
