"""structlog configuration — single-file, level-based logging with contextvars auto-injection."""

from __future__ import annotations

import logging
import os
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path

import orjson
import structlog

_SENSITIVE_KEYS = frozenset({"api_key", "token", "authorization", "password", "secret"})


def _mask_sensitive(logger, method_name: str, event_dict: dict) -> dict:
    """Mask sensitive fields in log output."""
    for key in _SENSITIVE_KEYS:
        if key in event_dict:
            val = str(event_dict[key])
            event_dict[key] = val[:4] + "***" if len(val) > 4 else "***"
    return event_dict


_SHARED_PROCESSORS = [
    structlog.contextvars.merge_contextvars,
    structlog.stdlib.add_log_level,
    structlog.processors.TimeStamper(fmt="iso"),
    structlog.processors.StackInfoRenderer(),
    structlog.processors.format_exc_info,
    structlog.processors.UnicodeDecoder(),
    _mask_sensitive,
]


def _json_renderer(logger, method_name: str, event_dict: dict) -> str:
    """Render log event as JSON string."""
    return orjson.dumps(event_dict, default=str).decode()


def configure_logging(log_dir: str = "logs", level: str | None = None) -> None:
    """Configure structlog with two files: artipivot.log (all levels) + error.log (errors only).

    Level resolution: explicit *level* param > ARTIPIVOT_LOG_LEVEL env var > "INFO".
    """
    effective_level = level or os.environ.get("ARTIPIVOT_LOG_LEVEL", "INFO")
    numeric_level = getattr(logging, effective_level.upper(), logging.INFO)

    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)

    structlog.configure(
        processors=[
            *_SHARED_PROCESSORS,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            _json_renderer,
        ],
        foreign_pre_chain=_SHARED_PROCESSORS,
    )

    # Main log file — all events, level-filtered
    main_handler = TimedRotatingFileHandler(
        str(log_path / "artipivot.log"),
        when="midnight",
        backupCount=30,
        encoding="utf-8",
    )
    main_handler.setFormatter(formatter)
    main_handler.setLevel(numeric_level)

    root = logging.getLogger("artipivot")
    root.handlers.clear()
    root.addHandler(main_handler)
    root.setLevel(logging.DEBUG)

    # Error-only log file — for alerting
    error_handler = TimedRotatingFileHandler(
        str(log_path / "error.log"),
        when="midnight",
        backupCount=90,
        encoding="utf-8",
    )
    error_handler.setFormatter(formatter)
    error_handler.setLevel(logging.ERROR)
    root.addHandler(error_handler)

    # DEBUG mode: also output to console
    if numeric_level <= logging.DEBUG:
        console = logging.StreamHandler()
        console.setFormatter(formatter)
        console.setLevel(logging.DEBUG)
        root.addHandler(console)


def serialize(obj, max_len: int = 2000) -> str | dict:
    """Safely serialize a LangChain message or response for debug logging."""
    try:
        if hasattr(obj, "content"):
            return {"type": type(obj).__name__, "content": str(obj.content)[:max_len]}
        return str(obj)[:max_len]
    except Exception:
        return "<unserializable>"
