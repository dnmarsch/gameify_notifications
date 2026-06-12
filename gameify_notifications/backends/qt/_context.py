"""Single source of truth for building a HudContext from the App's damage state
+ rules. The dismiss panel and every HUD window go through here so the damage
they show can't drift apart -- they read the same total_weight, full_at, and the
active HUD's validated [hud.*] params; only the monitor geometry differs."""

import time

from ...huds import HudContext


def make_context(app, monitors, primary=0):
    st, r, hud = app.state, app.rules, app.hud
    return HudContext(st.total_weight(), r.full_at, r.max_alpha, len(st.items),
                      time.monotonic(), st.last_event, monitors, primary,
                      params=r.params_for(hud.name))
