"""structlog configuration — multi-channel JSON logging with rotation."""

from __future__ import annotations

import logging
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path

import orjson
import structlog


# Channel → retention config
CHANNELS: dict[str, dict] = {
    "main": {"retention_days": 30},
    "trace": {"retention_days": 7},
    "session": {"retention_days": 30},
    "memory": {"retention_days": 30},
    "llm": {"retention_days": 30},
    "tool": {"retention_days": 14},
    "error": {"retention_days": 90},
    "audit": {"retention_days": 365},
}

_SHARED_PROCESSORS = [
    structlog.contextvars.merge_contextvars,
    structlog.stdlib.add_logger_name,
    structlog.stdlib.add_log_level,
    structlog.stdlib.PositionalArgumentsFormatter(),
    structlog.processors.TimeStamper(fmt="iso"),
    structlog.processors.StackInfoRenderer(),
    structlog.processors.format_exc_info,
    structlog.processors.UnicodeDecoder(),
]


def _json_renderer(logger, method_name: str, event_dict: dict) -> str:
    """Render log event as JSON string."""
    return orjson.dumps(event_dict, default=str).decode()


def configure_logging(log_dir: str = "logs", level: str = "INFO") -> None:
    """Configure structlog with multi-channel file handlers."""
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

    for channel, config in CHANNELS.items():
        handler = TimedRotatingFileHandler(
            str(log_path / f"{channel}.log"),
            when="midnight",
            backupCount=config["retention_days"],
            encoding="utf-8",
        )
        handler.setFormatter(formatter)
        handler.setLevel(getattr(logging, level.upper(), logging.INFO))

        ch_logger = logging.getLogger(f"artipivot.{channel}")
        ch_logger.handlers.clear()
        ch_logger.addHandler(handler)
        ch_logger.setLevel(logging.DEBUG)

    # error channel also goes to console for dev convenience
    console = logging.StreamHandler()
    console.setFormatter(formatter)
    console.setLevel(logging.ERROR)
    logging.getLogger("artipivot.error").addHandler(console)


def get_logger(channel: str) -> structlog.stdlib.BoundLogger:
    """Get a logger for the given channel."""
    return structlog.get_logger(f"artipivot.{channel}")
