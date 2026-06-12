"""Notification capture abstraction + a registry of named capture strategies.

Different Teams installs deliver notifications differently (direct
org.freedesktop.Notifications, the XDG portal for snap/flatpak, WinRT on
Windows, ...), so capture is pluggable: `select_source()` composes one or more
named strategies, chosen with `--source`. Users can drop a custom source into
the config `sources/` dir (see the example template) without forking."""

import importlib.util
import logging
import sys
from abc import ABC, abstractmethod

from .. import config

log = logging.getLogger(__name__)


class NotificationSource(ABC):
    name = "base"

    @abstractmethod
    def start(self, callback):
        """Begin capturing; call callback(app_name, summary, body, close=None)
        per event, where `close` is an optional zero-arg callable that clears
        the underlying desktop notification (best-effort; None if unsupported).
        May invoke the callback from a background thread."""

    def stop(self):
        pass

    def describe(self):
        return self.name


class CompositeNotificationSource(NotificationSource):
    """Fan-in: run several sources at once into one callback (e.g. freedesktop
    Notify AND the XDG portal, to cover snap/flatpak + native installs)."""

    name = "composite"

    def __init__(self, sources):
        self.sources = list(sources)

    def start(self, callback):
        for s in self.sources:
            try:
                s.start(callback)
            except Exception:
                log.exception("source %s failed to start", s.describe())

    def stop(self):
        for s in self.sources:
            s.stop()

    def describe(self):
        return " + ".join(s.describe() for s in self.sources)


def _builtin_factories(match):
    """Name -> zero-arg factory for the current platform's built-in sources."""
    if sys.platform.startswith("win"):
        from .windows_source import WindowsNotificationSource
        return {"windows": lambda: WindowsNotificationSource(match)}
    if sys.platform.startswith("linux"):
        from .dbus_source import FreedesktopNotifyMonitor, PortalNotifyMonitor, HAVE_GI
        if not HAVE_GI:
            return {}   # gi unavailable -> no built-in Linux sources (plugins still work)
        return {"freedesktop": lambda: FreedesktopNotifyMonitor(match),
                "portal": lambda: PortalNotifyMonitor(match)}
    return {}


def _plugin_factories(match):
    """Name -> factory for user sources dropped into the config sources/ dir."""
    out = {}
    sdir = config.sources_dir()
    if not sdir.is_dir():
        return out
    for path in sorted(sdir.glob("*.py")):
        try:
            spec = importlib.util.spec_from_file_location(f"source_{path.stem}", path)
            module = importlib.util.module_from_spec(spec)
            module.NotificationSource = NotificationSource
            spec.loader.exec_module(module)
            for obj in vars(module).values():
                if (isinstance(obj, type) and issubclass(obj, NotificationSource)
                        and obj is not NotificationSource
                        and getattr(obj, "name", "base") != "base"):
                    out[obj.name] = (lambda cls=obj: cls(match))
        except Exception:
            log.exception("failed to load source plugin %s", path.name)
    return out


def _default_names():
    if sys.platform.startswith("win"):
        return ["windows"]
    if sys.platform.startswith("linux"):
        return ["freedesktop", "portal"]
    raise NotImplementedError(
        f"No notification sources for platform '{sys.platform}' "
        "(macOS has no public API to read other apps' notifications).")


def available_sources(match=""):
    """All selectable source names for this platform (built-ins + plugins)."""
    factories = {}
    try:
        factories.update(_builtin_factories(match))
    except Exception:
        pass
    factories.update(_plugin_factories(match))
    return sorted(factories)


def select_source(match_substr, spec=None):
    """Build a NotificationSource from `spec` ("auto" | comma-separated names).
    'auto' composes the platform defaults (Linux: freedesktop + portal)."""
    spec = (spec or "auto").strip()
    factories = dict(_builtin_factories(match_substr))
    factories.update(_plugin_factories(match_substr))

    names = _default_names() if spec == "auto" else [s.strip() for s in spec.split(",") if s.strip()]
    unknown = [n for n in names if n not in factories]
    if unknown:
        log.warning("unknown source(s): %s. Available: %s",
                    ", ".join(unknown), ", ".join(sorted(factories)) or "(none)")
    chosen = [factories[n]() for n in names if n in factories]
    if not chosen:
        hint = ""
        if sys.platform.startswith("linux"):
            from .dbus_source import HAVE_GI
            if not HAVE_GI:
                hint = (" PyGObject (gi) is unavailable -- apt install python3-gi, "
                        "or recreate the venv with --system-site-packages.")
        raise RuntimeError(f"No usable notification source for spec '{spec}'.{hint}")
    return chosen[0] if len(chosen) == 1 else CompositeNotificationSource(chosen)
