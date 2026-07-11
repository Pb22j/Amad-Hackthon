"""Logging helpers that avoid leaking financial data."""

from __future__ import annotations

import logging

from user_interaction_layer.security.redaction import redact_sensitive_text


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)


def safe_log_value(value: object) -> str:
    return redact_sensitive_text(str(value))

