"""
FlowSight Logging Configuration

Structured logging with structlog for JSON output and rich console output.
"""

import logging
import sys
from pathlib import Path
from typing import Any

import structlog
from rich.logging import RichHandler

from flowsight.config import settings


def setup_logging() -> None:
    """Configure structured logging for the application."""
    
    log_level = getattr(logging, settings.logging.level.upper())
    
    # Configure standard library logging
    logging.basicConfig(
        level=log_level,
        format="%(message)s",
        handlers=[
            RichHandler(
                rich_tracebacks=True,
                tracebacks_show_locals=True,
                show_time=True,
                show_level=True,
                show_path=False,
            )
        ],
    )
    
    # Configure structlog
    processors = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="ISO"),
        structlog.processors.StackInfoRenderer(),
        structlog.dev.set_exc_info,
    ]
    
    if settings.logging.format == "json":
        processors.append(structlog.processors.JSONRenderer())
    else:
        processors.append(structlog.dev.ConsoleRenderer(colors=True))
    
    structlog.configure(
        processors=processors,
        wrapper_class=structlog.stdlib.BoundLogger,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )
    
    # Set log levels for noisy libraries
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("influxdb_client").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)


def get_logger(name: str | None = None) -> structlog.BoundLogger:
    """Get a structured logger instance."""
    return structlog.get_logger(name)


class LogContext:
    """Context manager for adding contextual information to logs."""
    
    def __init__(self, **kwargs: Any):
        self.kwargs = kwargs
        self.tokens = []
    
    def __enter__(self):
        for key, value in self.kwargs.items():
            token = structlog.contextvars.bind_contextvars(**{key: value})
            self.tokens.append((key, token))
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        for key, token in self.tokens:
            structlog.contextvars.unbind_contextvars(key)