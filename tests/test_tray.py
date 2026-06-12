"""Tray-cleaner strategy: selection per desktop + no-op/best-effort behavior."""

import sys

import pytest

from gameify_notifications import tray
from gameify_notifications.sources.dbus_source import HAVE_GI


def test_noop_cleaner_does_nothing():
    tray.NoopTrayCleaner().clear("s", "b")        # must not raise


def test_select_non_gnome_is_noop(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setenv("XDG_CURRENT_DESKTOP", "KDE")
    assert isinstance(tray.select_tray_cleaner(), tray.NoopTrayCleaner)


def test_select_non_linux_is_noop(monkeypatch):
    monkeypatch.setattr(sys, "platform", "darwin")
    assert isinstance(tray.select_tray_cleaner(), tray.NoopTrayCleaner)


@pytest.mark.skipif(not HAVE_GI, reason="needs PyGObject")
def test_select_gnome_is_extension_cleaner(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setenv("XDG_CURRENT_DESKTOP", "ubuntu:GNOME")
    assert isinstance(tray.select_tray_cleaner(), tray.GnomeExtensionTrayCleaner)


@pytest.mark.skipif(not HAVE_GI, reason="needs PyGObject")
def test_gnome_cleaner_clear_is_best_effort():
    # whether or not the extension is running, clear() never raises
    tray.GnomeExtensionTrayCleaner().clear("no-such-title", "no-such-body")
