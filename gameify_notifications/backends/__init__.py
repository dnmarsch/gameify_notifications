"""Overlay backend abstraction. A backend owns the windowing toolkit and the UI
event loop; given an App and a NotificationSource it renders the HUD overlay +
dismiss panel and runs until quit. Qt is cross-platform, so it's the only
backend; add another by implementing run() and registering it here."""

from abc import ABC, abstractmethod


class OverlayBackend(ABC):
    @abstractmethod
    def run(self, app, source):
        """Build the UI, start the source, run the event loop; return exit code."""


def select_backend():
    from .qt.backend import QtOverlayBackend
    return QtOverlayBackend()
