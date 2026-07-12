"""Regression guard for the AUTH-03 console-link dev fallback.

The email-verification link is emitted via the `assayingest.auth` logger. Under
a real `uvicorn assayingest.api.app:app` run, uvicorn configures only its own
loggers and Python's root logger defaults to WARNING with no INFO handler, so a
bare `logger.info(...)` from an `assayingest.*` logger was silently dropped --
the link never reached the console the dev fallback promises. pytest's `caplog`
captured records regardless of handlers, which masked the gap. `app.py`'s
`_configure_console_logging()` attaches a stdout INFO handler to the top-level
`assayingest` logger at import; this test proves an INFO record actually reaches
stdout, not just a caplog buffer.
"""
from __future__ import annotations

import logging
import sys

# Importing the app module runs _configure_console_logging() at import time.
import assayingest.api.app  # noqa: F401


def _console_handlers():
    return [
        handler
        for handler in logging.getLogger("assayingest").handlers
        if getattr(handler, "_assayingest_console", False)
    ]


def test_assayingest_logger_is_configured_at_info_with_a_console_handler():
    # Before the fix there was NO handler here, so an INFO record from
    # `assayingest.auth` was dropped under uvicorn (root defaults to WARNING).
    app_logger = logging.getLogger("assayingest")
    assert app_logger.getEffectiveLevel() <= logging.INFO
    assert _console_handlers(), "no stdout console handler on the 'assayingest' logger"


def test_the_console_handler_targets_stdout_at_info():
    handler = _console_handlers()[0]
    assert isinstance(handler, logging.StreamHandler)
    assert handler.stream is sys.stdout  # the real server console, not stderr
    assert handler.level <= logging.INFO


def test_an_assayingest_info_record_reaches_the_console_handler():
    # Prove an emit actually flows THROUGH the configured console handler (the
    # exact path that was silently broken) by swapping in a buffer stream on
    # that same handler and confirming the record lands -- avoids pytest's
    # fd/stream capture racing the import-time stream binding.
    import io

    handler = _console_handlers()[0]
    original = handler.stream
    buffer = io.StringIO()
    handler.setStream(buffer)
    try:
        logging.getLogger("assayingest.auth").info("Email verification link for %s: %s", "a@b.c", "/verify?token=T")
        handler.flush()
    finally:
        handler.setStream(original)
    emitted = buffer.getvalue()
    assert "Email verification link" in emitted and "/verify?token=T" in emitted
