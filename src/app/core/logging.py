"""
VedaCore Structured JSON Logging

Provides structured logging with JSON output for production environments.
Replaces print statements with proper logging infrastructure.
"""

import json
import logging
import sys

from typing import Any


class JsonFormatter(logging.Formatter):
    """JSON formatter for structured logging output"""

    def _redact(self, text: str) -> str:
        """Redact sensitive markers like token query params and auth headers.

        - token=... in query strings
        - Authorization: Bearer ... values
        - Strip query on /api/v1/stream URLs
        """
        try:
            import re
            # Redact token=... (case-insensitive)
            text = re.sub(r"(?i)(token=)[^&\s\"]+", r"\1[REDACTED]", text)
            # Redact Authorization header values
            text = re.sub(r"(?i)(authorization:\s*bearer\s+)[^\s\"]+", r"\1[REDACTED]", text)
            # Drop query string for /api/v1/stream URLs
            text = re.sub(r"(/api/v1/stream[^\s\"]*)\?[^\s\"]*", r"\1", text)
            # Redact Referer header entirely to avoid token echo
            text = re.sub(r"(?i)(^|\n)referer:\s*[^\n]+", r"\1Referer: [REDACTED]", text)
        except Exception:
            pass
        return text

    def format(self, record: logging.LogRecord) -> str:
        """
        Format log record as JSON

        Args:
            record: Python logging record

        Returns:
            JSON-formatted log string
        """
        base = {
            "timestamp": self.formatTime(record),
            "level": record.levelname,
            "logger": record.name,
            "message": self._redact(record.getMessage()),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        # Add exception info if present
        if record.exc_info:
            base["exception"] = self.formatException(record.exc_info)

        # Add extra fields from logger.info("msg", extra={...})
        if hasattr(record, "__dict__"):
            for key, value in record.__dict__.items():
                if key not in {
                    "name",
                    "msg",
                    "args",
                    "levelname",
                    "levelno",
                    "pathname",
                    "filename",
                    "module",
                    "lineno",
                    "funcName",
                    "created",
                    "msecs",
                    "relativeCreated",
                    "thread",
                    "threadName",
                    "processName",
                    "process",
                    "getMessage",
                    "exc_info",
                    "exc_text",
                    "stack_info",
                }:
                    base[key] = value

        return json.dumps(base)


def setup_logging(level: str = "INFO", format_json: bool = True) -> None:
    """
    Setup structured logging for VedaCore

    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        format_json: Whether to use JSON formatting
    """
    # Clear existing handlers
    root = logging.getLogger()
    root.handlers.clear()

    # Create console handler
    handler = logging.StreamHandler(sys.stdout)

    if format_json:
        # Use JSON formatter for production
        handler.setFormatter(JsonFormatter())
    else:
        # Use simple formatter for development
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
        handler.setFormatter(formatter)

    # Add handler and set level
    root.addHandler(handler)
    root.setLevel(getattr(logging, level.upper()))


def get_logger(name: str, extra_fields: dict[str, Any] | None = None) -> logging.Logger:
    """
    Get logger with optional extra fields

    Args:
        name: Logger name (usually __name__)
        extra_fields: Additional fields to include in all log messages

    Returns:
        Configured logger instance
    """
    logger = logging.getLogger(name)

    if extra_fields:
        # Create a logger adapter to automatically include extra fields
        return logging.LoggerAdapter(logger, extra_fields)

    return logger


# Convenience functions for common Vedic astrology logging contexts
def get_kp_logger(module: str) -> logging.Logger:
    """Get logger for KP calculation modules"""
    return get_logger(f"vedacore.kp.{module}", {"system": "KP", "domain": "astrology"})


def get_api_logger(endpoint: str) -> logging.Logger:
    """Get logger for API endpoints"""
    return get_logger(f"vedacore.api.{endpoint}", {"layer": "api", "type": "endpoint"})


def get_adapter_logger(adapter_name: str) -> logging.Logger:
    """Get logger for SystemAdapter implementations"""
    return get_logger(
        f"vedacore.adapter.{adapter_name}",
        {"layer": "adapter", "pattern": "SystemAdapter"},
    )
