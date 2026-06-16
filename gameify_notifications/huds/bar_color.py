"""Shared green -> yellow -> red fill color for HP/energy-style bars.

Both the Pokemon HP bar and the Stardew energy/health bars colour their fill by
how FULL the bar is: full reads green, mid reads yellow, low reads red. The two
cut-points are configurable per HUD (the same `green_above` / `yellow_above`
defaults are used by each) so the mapping lives in exactly one place."""

GREEN = (88, 208, 120)     # full         (>= green_above)
YELLOW = (240, 200, 48)    # getting low  (>= yellow_above)
RED = (216, 64, 48)        # critical     (< yellow_above)


def fill_color(frac, green_above=0.70, yellow_above=0.30):
    """Bar colour for a fill fraction in 0..1: green at/above `green_above`,
    yellow at/above `yellow_above`, otherwise red. Both boundaries are inclusive."""
    if frac >= green_above:
        return GREEN
    if frac >= yellow_above:
        return YELLOW
    return RED
