"""Dismiss panel: movable (drag header), resizable (size grip), and collapsible
to a one-line toolbar that expands back. Lists captured notifications with a
per-item dismiss and a clear-all. Geometry persists as absolute pixels (it's a
text list -- legibility matters more than scaling), with a max-fraction clamp."""

import html

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QWidget, QLabel, QPushButton, QVBoxLayout,
                               QHBoxLayout, QScrollArea, QSizeGrip, QFrame)

from ... import config
from ...geometry import default_panel_rect
from ...huds import load_huds
from ._context import make_context
from .persistence import QtPersistent
from .settings_panel import SettingsPanel

_STYLE = (
    "#panel{background:rgba(18,20,26,235);}"
    " QLabel{color:#e8e8e8;}"
    " #panelHeader{background:rgba(255,255,255,20);"
    "border-bottom:1px solid rgba(255,255,255,30);}"
    " QPushButton{color:#e8e8e8;background:rgba(255,255,255,18);"
    "border:1px solid rgba(255,255,255,30);border-radius:4px;padding:2px 8px;}"
    " QPushButton:hover{background:rgba(255,255,255,40);}"
    # visible scrollbar on the dark panel; thumb shrinks as the list grows
    " QScrollBar:vertical{background:transparent;width:10px;margin:2px;}"
    " QScrollBar::handle:vertical{background:rgba(255,255,255,70);"
    "min-height:24px;border-radius:5px;}"
    " QScrollBar::handle:vertical:hover{background:rgba(255,255,255,130);}"
    " QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical{height:0;}"
    " QScrollBar::add-page:vertical,QScrollBar::sub-page:vertical{background:transparent;}"
)


class PanelWindow(QWidget):
    dismissed = Signal(int)
    cleared = Signal()
    collapsedChanged = Signal(bool)

    def __init__(self, app, monitors_provider=None):
        super().__init__()
        self.app = app
        self._drag = None
        self._dock = None          # PanelDock when docked under a widget HUD, else None
        self._collapsed = False
        self.setObjectName("panel")
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setStyleSheet(_STYLE)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # header / drag handle (also the toolbar when collapsed)
        self.header = QWidget()
        self.header.setObjectName("panelHeader")
        self.header.setCursor(Qt.SizeAllCursor)   # 4-arrow "move" cursor on hover
        self.header.setToolTip("Drag to move")
        hb = QHBoxLayout(self.header)
        hb.setContentsMargins(8, 6, 8, 6)
        self.settings_btn = QPushButton("⚙")   # the old ☰ grip is now a settings gear
        self.settings_btn.setObjectName("panel.settingsBtn")
        self.settings_btn.setFixedWidth(28)
        self.settings_btn.setToolTip("Settings: theme + live tuning")
        self.title = QLabel("<b>INCOMING FIRE</b>")
        self.title.setTextFormat(Qt.RichText)
        # let clicks on the title fall through to the header so the WHOLE bar drags
        self.title.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.clear_btn = QPushButton("Clear all")
        self.clear_btn.setObjectName("panel.clearBtn")
        self.collapse_btn = QPushButton("▾")
        self.collapse_btn.setObjectName("panel.collapseBtn")
        self.collapse_btn.setFixedWidth(28)
        self.collapse_btn.setToolTip("Collapse to toolbar")
        hb.addWidget(self.settings_btn)
        hb.addWidget(self.title, 1)
        hb.addWidget(self.clear_btn)
        hb.addWidget(self.collapse_btn)
        root.addWidget(self.header)

        # Settings is a SEPARATE window (so it isn't squeezed by the panel's
        # height); the gear toggles + positions it. Parented to the panel so it's
        # cleaned up with it.
        self.settings = SettingsPanel(app, load_huds(), parent=self)
        self.settings_btn.clicked.connect(self._toggle_settings)

        self.status = QLabel()
        self.status.setObjectName("panel.status")
        self.status.setTextFormat(Qt.RichText)
        self.status.setContentsMargins(8, 4, 8, 4)
        root.addWidget(self.status)

        self.scroll = QScrollArea()
        self.scroll.setObjectName("panel.scroll")
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.listw = QWidget()
        self.listv = QVBoxLayout(self.listw)
        self.listv.setContentsMargins(4, 4, 4, 4)
        self.listv.setSpacing(4)
        self.listv.addStretch(1)
        self.scroll.setWidget(self.listw)
        root.addWidget(self.scroll, 1)

        # resize grip, anchored flush in the bottom-right via the layout
        grip_row = QHBoxLayout()
        grip_row.setContentsMargins(0, 0, 2, 2)
        grip_row.addStretch(1)
        self.grip = QSizeGrip(self)
        self.grip.setObjectName("panel.grip")
        grip_row.addWidget(self.grip, 0, Qt.AlignRight | Qt.AlignBottom)
        root.addLayout(grip_row)

        self.clear_btn.clicked.connect(self._clear)
        self.collapse_btn.clicked.connect(lambda: self.set_collapsed(not self._collapsed))
        self.header.mousePressEvent = self._hdr_press
        self.header.mouseMoveEvent = self._hdr_move
        self.header.mouseReleaseEvent = self._hdr_release

        self.persist = QtPersistent(self, "panel", default_panel_rect,
                                    relative=False, monitors_provider=monitors_provider)
        self.refresh()
        # refresh whenever the damage state changes (add/dismiss/clear)
        app.state.subscribe(lambda _kind: self.refresh())
        if config.load_state("panel_collapsed"):
            self.set_collapsed(True, persist=False)

    # ---- notifications list ---------------------------------------------
    def rows(self):
        """Notification row widgets (excludes the trailing stretch)."""
        return [self.listv.itemAt(i).widget() for i in range(self.listv.count() - 1)]

    def damage_percent(self):
        """Damage as a percentage of the ACTIVE overlay's capacity:
        (weight_scale x total weight) / max_messages, where max_messages is that
        HUD's optional capacity knob (else the global max_messages). So the panel
        reads the same damage the overlay shows -- not a raw count."""
        ctx = make_context(self.app, [(0, 0, 1, 1)])
        return self.app.hud.fraction(ctx) * 100.0

    def refresh(self):
        while self.listv.count() > 1:
            item = self.listv.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        self.status.setText(
            f"DAMAGE: <b>{self.damage_percent():.0f}%</b>&#160;&#160; "
            f"unread: <b>{len(self.app.state.items)}</b>")
        for n in reversed(self.app.state.items):
            row = QWidget()
            row.setProperty("nid", n.id)
            rl = QHBoxLayout(row)
            rl.setContentsMargins(6, 4, 6, 4)
            tag = "noise" if n.weight == 0 else f"+{n.weight:.1f}"
            body = (n.body[:120] + "…") if len(n.body) > 120 else n.body
            txt = QLabel(
                f"<small><b>{html.escape(n.category)}</b> <tt>[{tag}]</tt></small><br>"
                f"{html.escape(n.summary or '(no title)')}<br>"
                f"<small>{html.escape(body)}</small>")
            txt.setTextFormat(Qt.RichText)
            txt.setWordWrap(True)
            btn = QPushButton("✕")
            btn.setObjectName("panel.dismissBtn")
            btn.setFixedWidth(28)
            btn.clicked.connect(lambda _=False, nid=n.id: self._dismiss(nid))
            rl.addWidget(txt, 1)
            rl.addWidget(btn, 0, Qt.AlignTop)
            self.listv.insertWidget(self.listv.count() - 1, row)

    def _dismiss(self, nid):
        self.app.state.dismiss(nid)
        self.dismissed.emit(nid)

    def _clear(self):
        self.app.state.clear()
        self.cleared.emit()

    # ---- settings --------------------------------------------------------
    def _toggle_settings(self):
        # use isHidden() (explicit state), not isVisible() -- the latter is False
        # whenever an ancestor is hidden, which would break the toggle.
        if self.settings.isHidden():
            self.settings.build()                  # open with current values
            g = self.frameGeometry()
            scr = self.screen().availableGeometry() if self.screen() else None
            x = g.x() + g.width() + 8              # to the right of the panel...
            if scr is not None and x + self.settings.width() > scr.right():
                x = max(scr.left(), g.x() - self.settings.width() - 8)   # ...else to the left
            self.settings.move(x, g.y())
            self.settings.show()
            self.settings.raise_()
        else:
            self.settings.hide()

    # ---- collapse / expand ----------------------------------------------
    def is_collapsed(self):
        return self._collapsed

    def set_collapsed(self, collapsed, persist=True):
        self._collapsed = collapsed
        if collapsed:
            g = self.geometry()
            config.save_rect("panel", [g.x(), g.y(), g.width(), g.height()])
            self.persist.save_size = False
            self.status.hide()
            self.scroll.hide()
            self.grip.hide()
            self.settings.hide()         # collapsing also closes the settings section
            self.collapse_btn.setText("▸")
            self.collapse_btn.setToolTip("Expand")
            self.setFixedHeight(self.header.sizeHint().height())
        else:
            self.setMinimumHeight(0)
            self.setMaximumHeight(16777215)
            self.status.show()
            self.scroll.show()
            self.grip.show()
            self.collapse_btn.setText("▾")
            self.collapse_btn.setToolTip("Collapse to toolbar")
            self.persist.save_size = True
            saved = config.load_rect("panel")
            if saved:
                self.resize(saved[2], saved[3])
        if persist:
            config.save_state("panel_collapsed", collapsed)
        self.collapsedChanged.emit(collapsed)

    # ---- docking ---------------------------------------------------------
    def set_dock(self, dock):
        """Attach a PanelDock so this panel follows a widget HUD (or None to
        float freely). While docked, width is HUD-driven and the header drags
        the pair via the HUD."""
        self._dock = dock

    # ---- move / resize ---------------------------------------------------
    def resizeEvent(self, ev):
        self.persist.schedule_save()   # grip is layout-anchored now; no manual move
        if self._dock is not None:
            self._dock.reassert_width()   # keep width HUD-synced; only height drags stick
        super().resizeEvent(ev)

    def moveEvent(self, ev):
        self.persist.schedule_save()
        super().moveEvent(ev)

    def _hdr_press(self, ev):
        if ev.button() != Qt.LeftButton:
            return
        if self._dock is not None:                 # docked: drag moves the HUD (pair follows)
            self._drag = ev.globalPosition().toPoint()
            self._drag_hud_origin = self._dock.hud.frameGeometry().topLeft()
        else:
            self._drag = ev.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def _hdr_move(self, ev):
        if self._drag is None or not (ev.buttons() & Qt.LeftButton):
            return
        if self._dock is not None:
            delta = ev.globalPosition().toPoint() - self._drag
            self._dock.move_hud(self._drag_hud_origin + delta)
        else:
            self.move(ev.globalPosition().toPoint() - self._drag)

    def _hdr_release(self, ev):
        self._drag = None
