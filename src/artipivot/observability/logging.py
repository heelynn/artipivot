"""structlog configuration — single-file, level-based logging with contextvars auto-injection."""

from __future__ import annotations

import logging
import os
from datetime import timezone
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
from zoneinfo import ZoneInfo

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


def _resolve_tz(tz_name: str | None) -> timezone | ZoneInfo:
    """Resolve timezone name to a tzinfo object. Defaults to Asia/Shanghai."""
    name = tz_name or os.environ.get("ARTIPIVOT_LOG_TZ", "Asia/Shanghai")
    if name.upper() in ("UTC", "GMT"):
        return timezone.utc
    return ZoneInfo(name)


_SHARED_PROCESSORS = [
    structlog.contextvars.merge_contextvars,
    structlog.stdlib.add_log_level,
    structlog.processors.StackInfoRenderer(),
    structlog.processors.format_exc_info,
    structlog.processors.UnicodeDecoder(),
    _mask_sensitive,
]


def _json_renderer(logger, method_name: str, event_dict: dict) -> str:
    """Render log event as JSON string."""
    return orjson.dumps(event_dict, default=str).decode()


def _text_renderer(logger, method_name: str, event_dict: dict) -> str:
    """Render log event as human-readable plain text."""
    ts = event_dict.pop("timestamp", "")
    level = event_dict.pop("level", "").upper()
    event = event_dict.pop("event", "")
    fields = " ".join(f"{k}={v}" for k, v in event_dict.items())
    return f"{ts} {level:5s} {event}  {fields}"


_RENDERERS = {
    "json": _json_renderer,
    "text": _text_renderer,
}


def configure_logging(
    log_dir: str | None = None,
    level: str | None = None,
    log_format: str | None = None,
    output: str | None = None,
    tz: str | None = None,
) -> None:
    """Configure structlog with two files: artipivot.log (all levels) + error.log (errors only).

    All params fall back to environment variables, then defaults:
      log_dir   > ARTIPIVOT_LOG_DIR     > "logs"
      level     > ARTIPIVOT_LOG_LEVEL   > "INFO"
      log_format> ARTIPIVOT_LOG_FORMAT  > "json"
      output    > ARTIPIVOT_LOG_OUTPUT  > "file"
      tz        > ARTIPIVOT_LOG_TZ      > "Asia/Shanghai"
    """
    effective_level = level or os.environ.get("ARTIPIVOT_LOG_LEVEL", "INFO")
    numeric_level = getattr(logging, effective_level.upper(), logging.INFO)

    fmt = (log_format or os.environ.get("ARTIPIVOT_LOG_FORMAT", "json")).lower()
    renderer = _RENDERERS.get(fmt, _json_renderer)

    tzinfo = _resolve_tz(tz)

    # Custom timestamp processor with timezone support
    def _tz_timestamp(logger, method_name: str, event_dict: dict) -> dict:
        from datetime import datetime
        event_dict["timestamp"] = datetime.now(tzinfo).isoformat()
        return event_dict

    output_mode = (
        output or os.environ.get("ARTIPIVOT_LOG_OUTPUT", "file")
    ).lower()

    shared_processors = [
        *_SHARED_PROCESSORS[:1],  # merge_contextvars
        *_SHARED_PROCESSORS[1:2],  # add_log_level
        _tz_timestamp,
        *_SHARED_PROCESSORS[2:],  # StackInfoRenderer, format_exc_info, UnicodeDecoder, mask
    ]

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
        foreign_pre_chain=shared_processors,
    )

    root = logging.getLogger("artipivot")
    root.handlers.clear()
    root.setLevel(logging.DEBUG)

    if output_mode in ("file", "both"):
        log_path = Path(log_dir or os.environ.get("ARTIPIVOT_LOG_DIR", "logs"))
        log_path.mkdir(parents=True, exist_ok=True)

        # Main log file — all events, level-filtered
        main_handler = TimedRotatingFileHandler(
            str(log_path / "artipivot.log"),
            when="midnight",
            backupCount=30,
            encoding="utf-8",
        )
        main_handler.setFormatter(formatter)
        main_handler.setLevel(numeric_level)
        root.addHandler(main_handler)

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

    if output_mode in ("console", "both"):
        console = logging.StreamHandler()
        console.setFormatter(formatter)
        console.setLevel(numeric_level)
        root.addHandler(console)

    if not root.handlers:
        # Fallback: if misconfigured, at least log to file
        log_path = Path(log_dir or os.environ.get("ARTIPIVOT_LOG_DIR", "logs"))
        log_path.mkdir(parents=True, exist_ok=True)
        fallback = TimedRotatingFileHandler(
            str(log_path / "artipivot.log"),
            when="midnight",
            backupCount=30,
            encoding="utf-8",
        )
        fallback.setFormatter(formatter)
        fallback.setLevel(numeric_level)
        root.addHandler(fallback)


def serialize(obj, max_len: int = 2000) -> str | dict:
    """Safely serialize a LangChain message or response for debug logging."""
    try:
        if hasattr(obj, "content"):
            return {"type": type(obj).__name__, "content": str(obj.content)[:max_len]}
        return str(obj)[:max_len]
    except Exception:
        return "<unserializable>"
