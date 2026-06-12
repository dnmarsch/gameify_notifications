"""Best-effort "which apps have a window on screen right now" probe.

Returns a *set* of lowercased identifiers for apps that currently have a window
VISIBLE -- mapped, not minimized, on the active workspace -- so on a
multi-monitor setup an app visible on any monitor counts, not only the focused
one. (The focused window is a subset, so this also covers "focused".)

There is NO single cross-platform API, so the probe is a per-OS strategy
(`FocusProbe`), injected into App (swappable / unit-testable):
  * X11FocusProbe   : _NET_CLIENT_LIST -> per-window WM_CLASS, skipping
                      _NET_WM_STATE_HIDDEN and windows on another
                      _NET_WM_DESKTOP  (via xprop)
  * WindowsFocusProbe : EnumWindows + IsWindowVisible -> process exe names
  * NoFocusProbe    : empty set (Wayland/macOS/unknown -- can't tell, so no
                      suppression)

A FocusProbe is callable (`probe()` -> set) so App treats it as a plain
zero-arg callable; the ABC just gives the concrete probes a shared `visible()`
contract symmetric with the other strategy seams (NotificationSource,
OverlayBackend, TrayCleaner). To support a new desktop, subclass FocusProbe and
add a branch to `select_focus_probe()`.

Rules compare their `focus_class` regex against this set.
"""

import logging
import os
import re
import shutil
import subprocess
import sys
import time
from abc import ABC, abstractmethod

log = logging.getLogger(__name__)

_CACHE_TTL = 0.5
_cache = {"t": -1e9, "val": frozenset()}


def _xprop(args):
    return subprocess.run(["xprop", *args], capture_output=True, text=True,
                          timeout=1).stdout


def _x11_visible_uncached():
    """Set of WM_CLASSes for windows visible on the current workspace."""
    try:
        m = re.search(r"=\s*(\d+)", _xprop(["-root", "_NET_CURRENT_DESKTOP"]))
        current = int(m.group(1)) if m else None
        ids = re.findall(r"0x[0-9a-fA-F]+", _xprop(["-root", "_NET_CLIENT_LIST"]))
        visible = set()
        for wid in ids:
            props = _xprop(["-id", wid, "WM_CLASS", "_NET_WM_STATE", "_NET_WM_DESKTOP"])
            if "_NET_WM_STATE_HIDDEN" in props:
                continue                                       # minimized
            dm = re.search(r"_NET_WM_DESKTOP\([A-Z]+\)\s*=\s*(\d+)", props)
            if dm is not None and current is not None:
                d = int(dm.group(1))
                if d != current and d != 0xFFFFFFFF:           # other workspace
                    continue
            cm = re.search(r'WM_CLASS\([A-Z]+\)\s*=\s*(.+)', props)
            if cm:
                # add BOTH WM_CLASS strings (instance + class). Chrome PWAs put
                # the per-app id in the instance ("crx_<appid>") and a generic
                # "Google-chrome" in the class, so we must keep both to match either.
                for nm in re.findall(r'"([^"]*)"', cm.group(1)):
                    if nm:
                        visible.add(nm.lower())
        return frozenset(visible)
    except Exception:
        return frozenset()


def _x11_visible():
    now = time.monotonic()
    if now - _cache["t"] < _CACHE_TTL:           # cheap during notification bursts
        return _cache["val"]
    _cache["t"] = now
    _cache["val"] = _x11_visible_uncached()
    return _cache["val"]


def _windows_visible_uncached():   # pragma: no cover (Windows-only)
    try:
        import ctypes
        from ctypes import wintypes
        u32, k32 = ctypes.windll.user32, ctypes.windll.kernel32
        out = set()

        @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        def cb(hwnd, _lparam):
            if not u32.IsWindowVisible(hwnd) or u32.GetWindowTextLengthW(hwnd) == 0:
                return True
            pid = wintypes.DWORD()
            u32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            h = k32.OpenProcess(0x1000, False, pid)            # QUERY_LIMITED_INFORMATION
            if h:
                buf = ctypes.create_unicode_buffer(512)
                size = wintypes.DWORD(512)
                k32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size))
                k32.CloseHandle(h)
                if buf.value:
                    out.add(os.path.basename(buf.value).lower())
            return True

        u32.EnumWindows(cb, 0)
        return frozenset(out)
    except Exception:
        return frozenset()


class FocusProbe(ABC):
    """Strategy: identifiers of apps with a window currently on screen.

    Concrete probes implement `visible()`; instances are callable so callers
    (App) can treat any probe as a plain `() -> set[str]`."""

    @abstractmethod
    def visible(self):
        """Return a frozenset of lowercased window identifiers visible now."""

    def __call__(self):
        return self.visible()

    def describe(self):
        return type(self).__name__


class X11FocusProbe(FocusProbe):
    """Reads _NET_CLIENT_LIST via xprop (cached ~0.5s for notification bursts)."""

    def visible(self):
        return _x11_visible()


class WindowsFocusProbe(FocusProbe):   # pragma: no cover (Windows-only)
    def visible(self):
        return _windows_visible_uncached()


class NoFocusProbe(FocusProbe):
    """Can't determine visibility (Wayland/macOS/unknown) -> never suppress."""

    def visible(self):
        return frozenset()


def select_focus_probe():
    """Pick a visibility probe for the current platform (or a no-op)."""
    if sys.platform.startswith("linux"):
        if os.environ.get("WAYLAND_DISPLAY") and not os.environ.get("DISPLAY"):
            log.info("Wayland session: focus/visibility suppression unavailable")
            return NoFocusProbe()
        if shutil.which("xprop"):
            return X11FocusProbe()
        log.info("xprop not found: focus/visibility suppression unavailable")
        return NoFocusProbe()
    if sys.platform.startswith("win"):
        return WindowsFocusProbe()
    return NoFocusProbe()
