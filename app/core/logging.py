"""Structured logging via structlog.

Usage anywhere in the app:
    from app.core.logging import get_logger
    logger = get_logger(__name__)
    logger.info("event", module="my_module", key="value")
"""

from __future__ import annotations

import logging
import sys
import time
from typing import Any

import structlog
from structlog.types import EventDict, WrappedLogger

from app.config import get_settings

_settings = get_settings()


# ---------------------------------------------------------------------------
# Custom processors
# ---------------------------------------------------------------------------


def _add_service_info(
    logger: WrappedLogger, method: str, event_dict: EventDict
) -> EventDict:
    """Inject service-level metadata into every log record."""
    event_dict.setdefault("service", _settings.app_name)
    event_dict.setdefault("env", _settings.environment)
    return event_dict


def _add_timestamp(
    logger: WrappedLogger, method: str, event_dict: EventDict
) -> EventDict:
    """ISO-8601 timestamp."""
    event_dict["timestamp"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    return event_dict


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


def configure_logging() -> None:
    """Call once at app startup to configure structlog and stdlib logging."""
    log_level = getattr(logging, _settings.log_level.upper(), logging.INFO)

    shared_processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        _add_service_info,
        _add_timestamp,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    if _settings.log_format == "json":
        renderer: Any = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer(colors=True)

    structlog.configure(
        processors=shared_processors + [structlog.stdlib.ProcessorFormatter.wrap_for_formatter],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared_processors,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.handlers = [handler]
    root_logger.setLevel(log_level)

    # Silence noisy third-party loggers
    for noisy in ("uvicorn.access", "httpx", "httpcore"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """Return a bound structlog logger for the given module name."""
    return structlog.get_logger(name)
