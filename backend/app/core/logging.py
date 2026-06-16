"""Logging helpers for API and worker services."""

from __future__ import annotations

import json
import logging
import sys
from typing import Any

from app.core.config import settings


class JsonFormatter(logging.Formatter):
    """
    Render log records as structured JSON lines.

    This keeps container output searchable and friendly for later shipping.
    """

    def format(self, record: logging.LogRecord) -> str:
        """
        Convert a logging record into a JSON string.

        Args:
            record: Log record to serialize.

        Returns:
            JSON string for the current log line.
        """

        payload: dict[str, Any] = {
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def configure_logging() -> None:
    """
    Configure the root logger for structured stdout logging.

    Returns:
        None. Logging is configured as a global side effect.
    """

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(settings.log_level.upper())


def get_logger(name: str) -> logging.Logger:
    """
    Build a module-scoped logger instance.

    Args:
        name: Logger name, usually __name__.

    Returns:
        Configured logger instance.
    """

    return logging.getLogger(name)

