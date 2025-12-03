"""Logging configuration with request ID context support."""

import contextvars
import logging
from typing import Optional

request_id_context: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "request_id", default=None
)


class RequestIDFilter(logging.Filter):
    """Logging filter that adds request_id from context to log records."""

    def filter(self, record: logging.LogRecord) -> bool:
        """Add request_id to log record if available in context.

        Args:
            record: Log record to filter.

        Returns:
            Always True (doesn't filter out records).
        """
        request_id = request_id_context.get()
        if request_id:
            record.request_id = f"[{request_id:8s}]"
        else:
            record.request_id = (
                "          "  # 10 spaces to maintain alignment ([8chars])
            )
        return True


def setup_logging_with_request_id(debug: bool = False) -> None:
    """Configure logging with request ID support.

    Args:
        debug: If True, set logging to DEBUG level with detailed formatting.
    """
    level = logging.DEBUG if debug else logging.INFO
    if debug:
        format_str = (
            "%(request_id)s %(asctime)s %(levelname)-8s"
            " @ %(filename)s:%(lineno)d: %(message)s"
        )
    else:
        format_str = "%(request_id)s %(asctime)s %(levelname)-8s @ %(filename)s:%(lineno)d: %(message)s"

    # Remove existing handlers
    root_logger = logging.getLogger()
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Create console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(level)

    # Create formatter with date format
    date_format = "%Y-%m-%d %H:%M:%S"
    formatter = logging.Formatter(format_str, datefmt=date_format)
    console_handler.setFormatter(formatter)

    # Add request ID filter
    request_id_filter = RequestIDFilter()
    console_handler.addFilter(request_id_filter)

    # Configure root logger
    root_logger.setLevel(level)
    root_logger.addHandler(console_handler)

    # Set specific loggers to appropriate levels
    if debug:
        logging.getLogger("scrapit").setLevel(logging.DEBUG)
        logging.getLogger("scrapy").setLevel(logging.INFO)
    else:
        logging.getLogger("scrapit").setLevel(logging.INFO)
        logging.getLogger("scrapy").setLevel(logging.WARNING)


def set_request_id(request_id: Optional[str]) -> None:
    """Set request ID in the current context.

    Args:
        request_id: Request ID to set in context.
    """
    request_id_context.set(request_id)


def get_request_id() -> Optional[str]:
    """Get request ID from the current context.

    Returns:
        Request ID if set, None otherwise.
    """
    return request_id_context.get()
