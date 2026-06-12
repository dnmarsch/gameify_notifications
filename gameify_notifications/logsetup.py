"""Non-blocking logging backend.

App threads (Qt UI thread, the D-Bus monitor threads, the WinRT poller) only
ever do a fast, lock-light `queue.put` via a `QueueHandler`; a single background
`QueueListener` thread drains the queue and performs the slow file/console I/O,
so logging never blocks the UI or a capture thread.

Every record carries the thread name (so you can tell the UI thread from a
`dbus-freedesktop` / `winrt-notify` source thread), the logger/module name, the
function name and the line number -- which makes AI-assisted debugging much
easier. Per-level routing: everything -> rolling file; ERROR+ -> a separate
errors file; WARNING+ -> the console. Uncaught exceptions on any thread, and Qt's
own messages, are funnelled in too.
"""

import atexit
import logging
import logging.handlers
import os
import queue
import sys
import threading
from pathlib import Path

from . import config

FORMAT = ("%(asctime)s %(levelname)-7s [%(threadName)s] "
          "%(name)s.%(funcName)s:%(lineno)d - %(message)s")

_listener = None
_configured = False
_LOGGER_ROOT = "gameify_notifications"


def log_dir():
    return config.config_dir() / "logs"


def log_file_path():
    return log_dir() / "gameify_notifications.log"


def get_logger(name):
    """Logger for a module; pass __name__ (already under the gameify_notifications tree)."""
    if name == "__main__" or not name.startswith(_LOGGER_ROOT):
        name = f"{_LOGGER_ROOT}.{name.rsplit('.', 1)[-1]}"
    return logging.getLogger(name)


def setup_logging(level="INFO", logfile=None, console=True, force=False):
    """Install the async logging pipeline. Idempotent unless force=True.

    The configured level is set on the logger, so records below it are dropped
    at the call site (never enqueued). Both sinks -- one rolling file and the
    console -- emit everything that passes that level (no per-handler/per-level
    filtering, no separate files). GAMEIFY_NOTIFICATIONS_LOG_LEVEL overrides `level`.
    """
    global _listener, _configured
    if _configured and not force:
        return logging.getLogger(_LOGGER_ROOT)
    if force:
        shutdown_logging()

    level = os.environ.get("GAMEIFY_NOTIFICATIONS_LOG_LEVEL", level)
    lvl = getattr(logging, str(level).upper(), logging.INFO)
    path = Path(logfile) if logfile else log_file_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    fmt = logging.Formatter(FORMAT)

    handlers = []
    file_h = logging.handlers.RotatingFileHandler(
        path, maxBytes=1_000_000, backupCount=3, encoding="utf-8")
    file_h.setFormatter(fmt)
    handlers.append(file_h)
    if console:
        con = logging.StreamHandler(sys.stderr)
        con.setFormatter(fmt)
        handlers.append(con)

    # async: producers -> queue (fast) ; one listener thread -> sinks (slow I/O)
    q = queue.SimpleQueue()
    qh = logging.handlers.QueueHandler(q)
    root = logging.getLogger(_LOGGER_ROOT)
    root.setLevel(lvl)                 # gates enqueue: below this is suppressed at source
    for h in list(root.handlers):
        root.removeHandler(h)
    root.addHandler(qh)
    root.propagate = False

    # handlers carry no level -> they emit whatever the logger let through
    _listener = logging.handlers.QueueListener(q, *handlers, respect_handler_level=False)
    _listener.start()

    _install_excepthooks(root)
    _configured = True
    root.info("logging started level=%s file=%s thread=%s",
              logging.getLevelName(lvl), path, threading.current_thread().name)
    return root


def shutdown_logging():
    global _listener, _configured
    if _listener is not None:
        try:
            _listener.stop()   # flushes the queue
        except Exception:
            pass
        _listener = None
    root = logging.getLogger(_LOGGER_ROOT)
    for h in list(root.handlers):
        root.removeHandler(h)
    root.propagate = True   # restore default (so pytest's caplog can capture)
    _configured = False


def _install_excepthooks(logger):
    def _hook(exc_type, exc, tb):
        logger.error("uncaught exception", exc_info=(exc_type, exc, tb))

    sys.excepthook = _hook

    def _thread_hook(args):
        name = args.thread.name if args.thread else "?"
        logger.error("uncaught exception in thread %s", name,
                     exc_info=(args.exc_type, args.exc_value, args.exc_traceback))

    threading.excepthook = _thread_hook


def install_qt_message_handler():
    """Route Qt's own debug/warning/critical messages into our log."""
    try:
        from PySide6.QtCore import qInstallMessageHandler, QtMsgType
    except Exception:
        return
    log = logging.getLogger(f"{_LOGGER_ROOT}.qt")
    _map = {
        QtMsgType.QtDebugMsg: logging.DEBUG,
        QtMsgType.QtInfoMsg: logging.INFO,
        QtMsgType.QtWarningMsg: logging.WARNING,
        QtMsgType.QtCriticalMsg: logging.ERROR,
        QtMsgType.QtFatalMsg: logging.CRITICAL,
    }

    def handler(mode, ctx, message):
        log.log(_map.get(mode, logging.INFO), "%s", message)

    qInstallMessageHandler(handler)


atexit.register(shutdown_logging)
