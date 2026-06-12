"""Focus/visibility probe. The real probes hit the OS, so we drive the X11
parsing with faked `xprop` output; the suppression *logic* is covered against a
fake probe in test_app.py."""

import subprocess
import sys

from gameify_notifications import focus


class _R:
    def __init__(self, out):
        self.stdout = out


def test_select_focus_probe_returns_callable():
    # every probe is a FocusProbe instance and remains callable () -> set
    probe = focus.select_focus_probe()
    assert isinstance(probe, focus.FocusProbe)
    assert callable(probe)


def test_select_probe_x11_when_xprop_present(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    monkeypatch.setattr(focus.shutil, "which", lambda _n: "/usr/bin/xprop")
    assert isinstance(focus.select_focus_probe(), focus.X11FocusProbe)


def test_select_probe_noop_without_xprop(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    monkeypatch.setattr(focus.shutil, "which", lambda _n: None)
    assert isinstance(focus.select_focus_probe(), focus.NoFocusProbe)


def test_select_probe_noop_on_pure_wayland(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setenv("WAYLAND_DISPLAY", "wayland-0")
    monkeypatch.delenv("DISPLAY", raising=False)
    assert isinstance(focus.select_focus_probe(), focus.NoFocusProbe)


def test_no_probe_yields_empty_set():
    # the call interface (__call__ -> visible()) returns an empty set
    assert focus.NoFocusProbe()() == frozenset()


def test_x11_visible_filters_hidden_and_other_workspace(monkeypatch):
    def fake(cmd, **kw):
        if "_NET_CURRENT_DESKTOP" in cmd:
            return _R("_NET_CURRENT_DESKTOP(CARDINAL) = 0\n")
        if "_NET_CLIENT_LIST" in cmd:
            return _R("_NET_CLIENT_LIST(WINDOW): window id # 0x1, 0x2, 0x3, 0x4\n")
        if cmd[:2] == ["xprop", "-id"]:
            wid = cmd[2]
            if wid == "0x1":   # visible Teams on current desktop
                return _R('WM_CLASS(STRING) = "crx_teamsid", "crx_TeamsID"\n'
                          '_NET_WM_STATE(ATOM) = \n_NET_WM_DESKTOP(CARDINAL) = 0\n')
            if wid == "0x2":   # minimized -> excluded
                return _R('WM_CLASS(STRING) = "crx_outlookid", "crx_outlookid"\n'
                          '_NET_WM_STATE(ATOM) = _NET_WM_STATE_HIDDEN\n'
                          '_NET_WM_DESKTOP(CARDINAL) = 0\n')
            if wid == "0x3":   # other workspace -> excluded
                return _R('WM_CLASS(STRING) = "crx_other", "crx_other"\n'
                          '_NET_WM_STATE(ATOM) = \n_NET_WM_DESKTOP(CARDINAL) = 1\n')
            if wid == "0x4":   # sticky (all desktops) -> visible
                return _R('WM_CLASS(STRING) = "firefox", "firefox"\n'
                          '_NET_WM_STATE(ATOM) = \n_NET_WM_DESKTOP(CARDINAL) = 4294967295\n')
        return _R("")

    monkeypatch.setattr(subprocess, "run", fake)
    assert focus._x11_visible_uncached() == frozenset({"crx_teamsid", "firefox"})


def test_x11_visible_swallows_errors(monkeypatch):
    def boom(cmd, **kw):
        raise OSError("xprop missing")

    monkeypatch.setattr(subprocess, "run", boom)
    assert focus._x11_visible_uncached() == frozenset()


def test_x11_visible_returns_all_on_screen_not_just_focused(monkeypatch):
    # Two windows on the SAME (current) workspace -- e.g. one per monitor. The
    # probe returns BOTH, regardless of which one is focused: that's the
    # multi-monitor "visible anywhere" behavior (it never reads the active window).
    def fake(cmd, **kw):
        if "_NET_CURRENT_DESKTOP" in cmd:
            return _R("_NET_CURRENT_DESKTOP(CARDINAL) = 2\n")
        if "_NET_CLIENT_LIST" in cmd:
            return _R("_NET_CLIENT_LIST(WINDOW): window id # 0xa, 0xb\n")
        if cmd[:2] == ["xprop", "-id"]:
            if cmd[2] == "0xa":      # editor on monitor 1
                return _R('WM_CLASS(STRING) = "code", "code"\n'
                          '_NET_WM_STATE(ATOM) = \n_NET_WM_DESKTOP(CARDINAL) = 2\n')
            if cmd[2] == "0xb":      # Teams on monitor 2 (not focused)
                return _R('WM_CLASS(STRING) = "crx_teamsid", "crx_teamsid"\n'
                          '_NET_WM_STATE(ATOM) = \n_NET_WM_DESKTOP(CARDINAL) = 2\n')
        return _R("")

    monkeypatch.setattr(subprocess, "run", fake)
    visible = focus._x11_visible_uncached()
    assert visible == frozenset({"code", "crx_teamsid"})
    assert "crx_teamsid" in visible          # Teams suppresses even when not focused


def test_x11_visible_keeps_both_instance_and_class(monkeypatch):
    # Chrome PWA: instance is the per-app 'crx_<id>', class is generic 'Google-chrome'.
    # We must keep BOTH so a focus_class of 'crx_<id>' matches.
    def fake(cmd, **kw):
        if "_NET_CURRENT_DESKTOP" in cmd:
            return _R("_NET_CURRENT_DESKTOP(CARDINAL) = 0\n")
        if "_NET_CLIENT_LIST" in cmd:
            return _R("_NET_CLIENT_LIST(WINDOW): window id # 0x1\n")
        if cmd[:2] == ["xprop", "-id"]:
            return _R('WM_CLASS(STRING) = "crx_ompifg", "Google-chrome"\n'
                      '_NET_WM_STATE(ATOM) = \n_NET_WM_DESKTOP(CARDINAL) = 0\n')
        return _R("")

    monkeypatch.setattr(subprocess, "run", fake)
    visible = focus._x11_visible_uncached()
    assert "crx_ompifg" in visible and "google-chrome" in visible
