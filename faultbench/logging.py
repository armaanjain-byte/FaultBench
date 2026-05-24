"""Structured logging configuration for FaultBench.

Provides a single ``get_logger`` function that returns a bound structlog
logger configured with:
- JSON rendering for production (when LOG_FORMAT=json)
- Human-readable console rendering for development
- Automatic timestamping, log level, and caller info
"""

from __future__ import annotations

import logging
import os
import sys

import structlog


_CONFIGURED = False


def _configure_structlog() -> None:
    """One-time structlog configuration.  Idempotent — safe to call
    multiple times but only the first call takes effect.
    """
    global _CONFIGURED
    if _CONFIGURED:
        return
    _CONFIGURED = True

    log_format = os.environ.get("FAULTBENCH_LOG_FORMAT", "console").lower()
    log_level_name = os.environ.get("FAULTBENCH_LOG_LEVEL", "INFO").upper()
    log_level = getattr(logging, log_level_name, logging.INFO)

    # Shared processors for both renderers
    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.UnicodeDecoder(),
    ]

    if log_format == "json":
        renderer: structlog.types.Processor = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer(colors=sys.stderr.isatty())

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    # Configure stdlib logging to use structlog formatting
    formatter = structlog.stdlib.ProcessorFormatter(
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
    )

    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(log_level)

    # Silence noisy third-party loggers
    logging.getLogger("docker").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """Return a bound structlog logger for the given module name.

    Usage::

        from faultbench.logging import get_logger
        log = get_logger(__name__)
        log.info("operation_started", task="task_001")

    Args:
        name: Typically ``__name__`` of the calling module.

    Returns:
        A structlog BoundLogger that supports ``.info()``, ``.warning()``,
        ``.error()``, ``.debug()``, and ``.exception()`` with keyword args
        as structured context.
    """
    _configure_structlog()
    return structlog.get_logger(name)
