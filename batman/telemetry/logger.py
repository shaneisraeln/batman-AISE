"""Structured JSON logging.

Never logs raw API keys, secrets, or raw inference inputs.
"""

from __future__ import annotations

import json
import logging
import sys

_SENSITIVE_KEYS = {"api_key", "raw_key", "authorization", "secret", "password", "token"}


class JSONFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if hasattr(record, "extra_fields") and isinstance(record.extra_fields, dict):
            payload.update(_redact(record.extra_fields))
        return json.dumps(payload, default=str)


def _redact(fields: dict) -> dict:
    out = {}
    for k, v in fields.items():
        if k.lower() in _SENSITIVE_KEYS:
            out[k] = "***redacted***"
        else:
            out[k] = v
    return out


def get_logger(name: str = "batman", level: str = "INFO") -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(JSONFormatter())
        logger.addHandler(handler)
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    logger.propagate = False
    return logger


def log_event(logger: logging.Logger, message: str, **fields) -> None:
    logger.info(message, extra={"extra_fields": _redact(fields)})
