"""Async logging backend: queue-based (non-blocking), context-rich records,
per-level file routing, idempotent setup."""

import logging
import logging.handlers

from gameify_notifications import logsetup


def test_uses_async_queue_handler(tmp_path):
    logsetup.setup_logging(level="DEBUG", logfile=str(tmp_path / "x.log"),
                           console=False, force=True)
    root = logging.getLogger("gameify_notifications")
    try:
        assert any(isinstance(h, logging.handlers.QueueHandler) for h in root.handlers)
    finally:
        logsetup.shutdown_logging()


def test_record_has_context_and_writes_file(tmp_path):
    logfile = tmp_path / "x.log"
    logsetup.setup_logging(level="DEBUG", logfile=str(logfile), console=False, force=True)
    logging.getLogger("gameify_notifications.test").error("boom-marker")
    logsetup.shutdown_logging()   # stops listener -> flushes the queue

    text = logfile.read_text()
    assert "boom-marker" in text
    assert "ERROR" in text
    assert "test_record_has_context_and_writes_file" in text   # %(funcName)s
    assert "MainThread" in text                                # threadName


def test_below_level_is_suppressed_not_enqueued(tmp_path):
    logfile = tmp_path / "x.log"
    logsetup.setup_logging(level="INFO", logfile=str(logfile), console=False, force=True)
    log = logging.getLogger("gameify_notifications.test")
    assert not log.isEnabledFor(logging.DEBUG)   # dropped at the call site
    log.debug("should-not-appear")
    log.info("should-appear")
    logsetup.shutdown_logging()
    text = logfile.read_text()
    assert "should-appear" in text
    assert "should-not-appear" not in text


def test_env_var_overrides_level(tmp_path, monkeypatch):
    monkeypatch.setenv("GAMEIFY_NOTIFICATIONS_LOG_LEVEL", "ERROR")
    logsetup.setup_logging(level="DEBUG", logfile=str(tmp_path / "x.log"),
                           console=False, force=True)
    try:
        assert logging.getLogger("gameify_notifications").level == logging.ERROR
    finally:
        logsetup.shutdown_logging()


def test_setup_is_idempotent(tmp_path):
    a = logsetup.setup_logging(logfile=str(tmp_path / "a.log"), console=False, force=True)
    b = logsetup.setup_logging(logfile=str(tmp_path / "b.log"), console=False)  # ignored
    try:
        assert a is b
    finally:
        logsetup.shutdown_logging()
