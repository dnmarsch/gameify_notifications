"""Docks the dismiss panel directly beneath a widget HUD so the two read as one
status display: the panel's width follows the HUD (with a readable minimum,
left-aligned under narrower HUDs), it keeps its own height (drag the grip to grow
the notification list), and dragging either window moves the pair.

Only used for scope='widget' HUDs when `dock_panel` is on; the all-monitor `cod`
overlay has nothing to dock to and keeps a free-floating panel. Reversible: turn
`dock_panel` off (then restart) and both windows float independently again."""

MIN_WIDTH = 320       # px -- below this the list is too cramped to read


def dock_rect(hud_rect, panel_height, min_width=MIN_WIDTH, gap=0):
    """Where the panel sits given the HUD's rect -> [x, y, w, h].

    Width follows the HUD but never narrower than `min_width`; when the HUD is
    narrower than that, the panel left-aligns under it (extends to the right).
    The panel keeps its own height."""
    hx, hy, hw, hh = hud_rect
    w = max(int(hw), int(min_width))
    return [int(hx), int(hy + hh + gap), w, int(panel_height)]


class PanelDock:
    def __init__(self, hud_win, panel):
        self.hud = hud_win
        self.panel = panel
        panel.set_dock(self)                     # let the panel delegate move/width
        hud_win.geometryChanged.connect(self.sync)
        self.sync()

    def sync(self):
        """Re-place the panel under the HUD, preserving the panel's height."""
        g = self.hud.frameGeometry()
        x, y, w, h = dock_rect([g.x(), g.y(), g.width(), g.height()], self.panel.height())
        self.panel.setGeometry(x, y, w, h)

    def reassert_width(self):
        """Called after the user resizes the panel (the height drag) -- snap the
        width back to the HUD-synced value so only height changes stick."""
        g = self.hud.frameGeometry()
        target_w = max(g.width(), MIN_WIDTH)
        if self.panel.width() != target_w:
            self.sync()

    def move_hud(self, top_left):
        """Drag-from-panel moves the HUD; the panel follows via geometryChanged."""
        self.hud.move(top_left)
