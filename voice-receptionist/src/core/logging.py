"""
Structured logging configuration.
Supports JSON and text formats for different environments.
"""

import logging
import sys
from typing import Any, Dict, Optional

import structlog
from structlog.processors import JSONRenderer, TimeStamper, add_log_level

from src.core.config import settings


def setup_logging() -> None:
    """Configure structured logging based on settings."""
    
    # Set log level
    log_level = getattr(logging, settings.log_level.upper(), logging.INFO)
    
    # Choose processors based on format
    if settings.log_format == "json":
        renderer = JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer(colors=True)
    
    # Configure structlog
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            renderer,
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )
    
    # Configure standard logging
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=log_level,
    )
    
    # Set third-party loggers to WARNING
    for logger_name in ["uvicorn", "uvicorn.access", "asyncpg", "aiohttp"]:
        logging.getLogger(logger_name).setLevel(logging.WARNING)


def get_logger(name: str) -> structlog.BoundLogger:
    """
    Get a logger instance with the given name.
    
    Args:
        name: Logger name (typically __name__)
    
    Returns:
        Configured logger instance
    """
    return structlog.get_logger(name)


class LogContext:
    """
    Context manager for adding temporary context to logs.
    
    Usage:
        with LogContext(logger, request_id="abc", user_id="123"):
            logger.info("Processing request")
    """
    
    def __init__(self, logger: structlog.BoundLogger, **context: Any):
        self.logger = logger
        self.context = context
        self.old_context: Dict[str, Any] = {}
    
    def __enter__(self) -> structlog.BoundLogger:
        self.old_context = self.logger._context.copy()
        return self.logger.bind(**self.context)
    
    def __exit__(self, *args):
        self.logger._context = self.old_context


# Request logging helpers
def log_request(
    logger: structlog.BoundLogger,
    method: str,
    path: str,
    status_code: int,
    duration_ms: float,
    **extra: Any
) -> None:
    """Log an HTTP request with standard fields."""
    logger.info(
        "HTTP Request",
        method=method,
        path=path,
        status_code=status_code,
        duration_ms=round(duration_ms, 2),
        **extra
    )


def log_call_event(
    logger: structlog.BoundLogger,
    event: str,
    call_id: str,
    **extra: Any
) -> None:
    """Log a call-related event."""
    logger.info(
        event,
        call_id=call_id,
        **extra
    )


def log_booking_event(
    logger: structlog.BoundLogger,
    event: str,
    booking_id: str,
    business_id: str,
    **extra: Any
) -> None:
    """Log a booking-related event."""
    logger.info(
        event,
        booking_id=booking_id,
        business_id=business_id,
        **extra
    )


# PII scrubbing for logs
PII_PATTERNS = [
    # Phone numbers
    r'\b\d{3}[-.]?\d{3}[-.]?\d{4}\b',
    # Email addresses
    r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
    # SSN
    r'\b\d{3}[-]?\d{2}[-]?\d{4}\b',
    # Credit card
    r'\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b',
]


def scrub_pii(text: str) -> str:
    """
    Remove PII from text for logging.
    
    Args:
        text: Text that may contain PII
    
    Returns:
        Text with PII replaced by [REDACTED]
    """
    import re
    
    result = text
    for pattern in PII_PATTERNS:
        result = re.sub(pattern, "[REDACTED]", result, flags=re.IGNORECASE)
    
    return result


# Initialize logging on module import
setup_logging()
