"""Structured logging configuration for forensic auditability and observability."""

import json
import logging
import sys
from datetime import UTC, datetime
from typing import Any


class StructuredJsonFormatter(logging.Formatter):
    """JSON log formatter tailored for forensic platforms and audit traceability."""

    def format(self, record: logging.LogRecord) -> str:
        log_entry: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "func": record.funcName,
            "line": record.lineno,
        }

        # Include custom forensic context fields if attached to record
        for attr in ("case_id", "evidence_id", "user_id", "action", "sha256", "duration_ms"):
            if hasattr(record, attr):
                log_entry[attr] = getattr(record, attr)

        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_entry)


def setup_logging(log_level: str = "INFO", json_format: bool = False) -> None:
    """Configure system-wide logging with either structured JSON or clean colored text."""
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level.upper())

    # Clear existing handlers to prevent duplicate lines
    for handler in list(root_logger.handlers):
        root_logger.removeHandler(handler)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level.upper())

    if json_format:
        formatter: logging.Formatter = StructuredJsonFormatter()
    else:
        formatter = logging.Formatter(
            fmt="%(asctime)s [%(levelname)s] %(name)s (%(module)s:%(lineno)d): %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # Silence overly verbose external loggers
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)


logger = logging.getLogger("ps05.api")
