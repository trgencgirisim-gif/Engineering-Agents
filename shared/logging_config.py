"""shared/logging_config.py — Structured logging with JSON formatter and correlation IDs.

Phase 1.4: Replace ad-hoc print() calls with structured logging that includes:
- JSON-formatted log records for machine parsing
- Per-session correlation IDs (thread-local)
- Standard severity levels: DEBUG, INFO, WARNING, ERROR
"""

import json
import logging
import threading
import time
from typing import Optional

# ── Thread-local correlation ID ──────────────────────────────
_local = threading.local()


def get_correlation_id() -> str:
    """Return the correlation ID for the current thread (session ID)."""
    return getattr(_local, "correlation_id", "-")


def set_correlation_id(cid: str):
    """Set the correlation ID for the current thread."""
    _local.correlation_id = cid


def clear_correlation_id():
    """Clear the correlation ID for the current thread."""
    _local.correlation_id = "-"


# ── JSON formatter ───────────────────────────────────────────

_SKIP_FIELDS = frozenset({
    "msg", "args", "exc_info", "exc_text", "stack_info",
    "levelname", "levelno", "pathname", "filename", "module",
    "funcName", "created", "msecs", "relativeCreated",
    "thread", "threadName", "processName", "process", "name",
    "lineno", "message", "taskName",
})


class JSONFormatter(logging.Formatter):
    """Structured JSON log formatter."""

    def format(self, record: logging.LogRecord) -> str:
        log_entry: dict = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(record.created)),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
            "cid": get_correlation_id(),
        }
        if record.exc_info:
            log_entry["exc"] = self.formatException(record.exc_info)
        if record.stack_info:
            log_entry["stack"] = record.stack_info
        # Carry over any extra fields set via logger.info(..., extra={...})
        for key, val in record.__dict__.items():
            if key not in _SKIP_FIELDS and not key.startswith("_"):
                log_entry[key] = val
        return json.dumps(log_entry, default=str, ensure_ascii=False)


# ── Setup ────────────────────────────────────────────────────

def setup_logging(
    level: str = "INFO",
    json_format: bool = True,
    logger_name: Optional[str] = None,
) -> logging.Logger:
    """
    Configure the root (or named) logger.

    Args:
        level: Logging level string ("DEBUG", "INFO", "WARNING", "ERROR").
        json_format: Use JSONFormatter if True, plain text otherwise.
        logger_name: Configure a specific logger instead of root.

    Returns:
        The configured Logger instance.
    """
    target = logging.getLogger(logger_name)
    target.setLevel(getattr(logging, level.upper(), logging.INFO))

    if not target.handlers:
        handler = logging.StreamHandler()
        if json_format:
            handler.setFormatter(JSONFormatter())
        else:
            handler.setFormatter(
                logging.Formatter("%(asctime)s %(levelname)-8s [%(name)s] [%(cid)s] %(message)s")
            )
        target.addHandler(handler)

    return target


def get_logger(name: str) -> logging.Logger:
    """Get a named logger (standard logging.getLogger wrapper)."""
    return logging.getLogger(name)
