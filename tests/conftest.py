"""Shared pytest fixtures.

Forces Qt's headless 'offscreen' platform, isolates config to a temp dir per
test, and provides app/window factories plus a fake monitor provider so window
tests are deterministic and never touch real hardware.
"""

import os
import sys
import pathlib

# Must be set before any Qt import.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from gameify_notifications.geometry import Rect


@pytest.fixture(autouse=True)
def isolated_config(tmp_path, monkeypatch):
    """Point all config/state at a throwaway dir so tests never touch ~/.config."""
    monkeypatch.setenv("GAMEIFY_NOTIFICATIONS_CONFIG_DIR", str(tmp_path / "cfg"))
    from gameify_notifications import config
    config.ensure_config()
    yield


@pytest.fixture
def single_monitor():
    """A monitors_provider for a single 1920x1080 screen -> (workareas, primary)."""
    return lambda: ([Rect(0, 0, 1920, 1080)], 0)


@pytest.fixture
def two_monitors():
    return lambda: ([Rect(0, 0, 1920, 1080), Rect(1920, 0, 1920, 1080)], 0)


@pytest.fixture
def make_app():
    """Factory: make_app(hud_name='cod', test_mode=True) -> App."""
    from gameify_notifications.app import App
    from gameify_notifications.huds import load_huds
    huds = load_huds()

    def _make(hud_name="cod", test_mode=True):
        return App(huds[hud_name], "teams", test_mode=test_mode)

    return _make


@pytest.fixture
def make_ctx():
    """Factory for a HudContext with controllable damage and no active flash."""
    from gameify_notifications.huds import HudContext

    def _make(total_weight=0.0, max_messages=6.0, max_alpha=0.7, w=640, h=170,
              params=None):
        return HudContext(total_weight=total_weight, max_messages=max_messages,
                          max_alpha=max_alpha, count=int(total_weight),
                          now=100.0, last_event=0.0,
                          monitors=[(0, 0, w, h)], primary=0, params=params)

    return _make
