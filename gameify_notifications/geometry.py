"""Monitor geometry math: off-screen-safe clamping and fraction-of-monitor
persistence. Pure functions over a tiny `Rect` type (x, y, width, height) so
they're toolkit-independent and trivially unit-testable.
"""


class Rect:
    """Minimal rectangle with attribute access (adapts QRect / Gdk.Rectangle)."""

    __slots__ = ("x", "y", "width", "height")

    def __init__(self, x, y, width, height):
        self.x = x
        self.y = y
        self.width = width
        self.height = height

    def __repr__(self):
        return f"Rect({self.x}, {self.y}, {self.width}, {self.height})"


def monitor_for_point(workareas, x, y):
    """Index of the monitor whose work area contains (x, y), else None."""
    for i, a in enumerate(workareas):
        if a.x <= x < a.x + a.width and a.y <= y < a.y + a.height:
            return i
    return None


def virtual_bounds(geos):
    """Bounding box (x, y, w, h) of all monitor geometries."""
    minx = min(g.x for g in geos)
    miny = min(g.y for g in geos)
    maxx = max(g.x + g.width for g in geos)
    maxy = max(g.y + g.height for g in geos)
    return minx, miny, maxx - minx, maxy - miny


def panel_visible_enough(rect, workareas):
    """The drag handle (top strip) must be substantially reachable on SOME
    monitor, else the window is unreachable -> invalid."""
    HANDLE_H = 36
    MIN_VISIBLE_W = 80
    MIN_VISIBLE_H = HANDLE_H / 2
    x, y, w, h = rect
    for a in workareas:
        ix = max(x, a.x)
        iy = max(y, a.y)
        ax = min(x + w, a.x + a.width)
        ay = min(y + HANDLE_H, a.y + a.height)
        if (ax - ix) >= MIN_VISIBLE_W and (ay - iy) >= MIN_VISIBLE_H:
            return True
    return False


def default_panel_rect(workareas, primary):
    """Top-right of the primary monitor (the dismiss panel's home)."""
    a = workareas[primary] if primary < len(workareas) else workareas[0]
    w, h = 360, 440
    w = min(w, a.width - 20)
    h = min(h, a.height - 20)
    return [a.x + a.width - w - 16, a.y + 16, w, h]


def center_rect(workareas, primary, w, h):
    """A w*h rect centered on the primary monitor."""
    a = workareas[primary] if primary < len(workareas) else workareas[0]
    w = min(w, a.width - 20)
    h = min(h, a.height - 20)
    return [int(a.x + (a.width - w) // 2), int(a.y + (a.height - h) // 2), int(w), int(h)]


def frac_rect_centered(workareas, primary, wf, hf):
    """A rect sized as a fraction (wf, hf) of the primary monitor, centered."""
    a = workareas[primary] if primary < len(workareas) else workareas[0]
    return center_rect(workareas, primary, int(a.width * wf), int(a.height * hf))


def top_center_rect(workareas, primary, w, h, margin=8):
    """A w*h rect centered horizontally, near the TOP of the primary monitor."""
    a = workareas[primary] if primary < len(workareas) else workareas[0]
    w = min(w, a.width - 20)
    h = min(h, a.height - 20)
    return [int(a.x + (a.width - w) // 2), int(a.y + margin), int(w), int(h)]


def frac_top_centered(workareas, primary, wf, hf):
    """A fraction-sized rect, centered horizontally and near the top."""
    a = workareas[primary] if primary < len(workareas) else workareas[0]
    return top_center_rect(workareas, primary, int(a.width * wf), int(a.height * hf))


def rect_to_fractions(rect, workareas, primary):
    """Express an absolute rect as fractions of the monitor under its centre.
    Returns (monitor_index, [fx, fy, fw, fh])."""
    x, y, w, h = rect
    mi = monitor_for_point(workareas, x + w / 2, y + h / 2)
    if mi is None:
        mi = primary
    a = workareas[mi] if mi < len(workareas) else workareas[0]
    # guard against a degenerate (zero-size) workarea -- some compositors briefly
    # report a 0x0 screen during a hotplug/resolution change; treat as 1px so the
    # save can't crash (the next valid geometry event corrects the fraction).
    aw = a.width if a.width else 1
    ah = a.height if a.height else 1
    return mi, [(x - a.x) / aw, (y - a.y) / ah, w / aw, h / ah]


def fractions_to_rect(mi, fr, workareas, primary):
    """Inverse of rect_to_fractions against the *current* monitor sizes, so a
    resolution or orientation change rescales the window proportionally."""
    if mi is None or mi >= len(workareas):
        mi = primary
    a = workareas[mi] if mi < len(workareas) else workareas[0]
    fx, fy, fw, fh = fr
    return [int(a.x + fx * a.width), int(a.y + fy * a.height),
            int(fw * a.width), int(fh * a.height)]


def clamp_rect(rect, workareas, primary, default_fn, max_frac=0.95):
    """Clamp size and snap-back. A window may not exceed `max_frac` of the
    monitor it sits on, and if its drag handle isn't reachable on any monitor it
    snaps to `default_fn(workareas, primary)`. Reused by every persisted window."""
    x, y, w, h = rect
    on = monitor_for_point(workareas, x + w / 2, y + h / 2)
    cap = workareas[on] if on is not None else max(workareas, key=lambda a: a.width * a.height)
    w = min(w, int(cap.width * max_frac))
    h = min(h, int(cap.height * max_frac))
    biggest = max(workareas, key=lambda a: a.width * a.height)
    w = min(w, biggest.width - 20)
    h = min(h, biggest.height - 20)
    rect = [int(x), int(y), int(w), int(h)]
    if not panel_visible_enough(rect, workareas):
        return default_fn(workareas, primary)
    return rect
