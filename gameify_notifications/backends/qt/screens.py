"""Qt monitor enumeration, adapted to the toolkit-independent `Rect` type used
by the geometry helpers."""

from PySide6.QtGui import QGuiApplication

from ...geometry import Rect


def _to_rect(qr):
    return Rect(qr.x(), qr.y(), qr.width(), qr.height())


def qt_geometries():
    return [_to_rect(s.geometry()) for s in QGuiApplication.screens()]


def qt_workareas():
    return [_to_rect(s.availableGeometry()) for s in QGuiApplication.screens()]


def qt_primary():
    screens = QGuiApplication.screens()
    p = QGuiApplication.primaryScreen()
    return screens.index(p) if p in screens else 0


def qt_monitors():
    """(work_areas, primary_index) -- what QtPersistent needs."""
    return qt_workareas(), qt_primary()
