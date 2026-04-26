"""Redact secrets before NetPulse data leaves process boundaries."""

from __future__ import annotations

import os
import re
from typing import Any


REDACTION = "[REDACTED]"

_SENSITIVE_ENV_NAMES = (
    "NETPULSE_PASSWORD",
    "NETPULSE_SECRET",
)

_KEY_VALUE_PATTERNS = (
    re.compile(r"(?i)\b(NETPULSE_PASSWORD|NETPULSE_SECRET)\s*=\s*([^\s,;]+)"),
    re.compile(r"(?i)\b(password|secret|enable_secret)\s*[:=]\s*([^\s,;]+)"),
)


def redact_text(text: str) -> str:
    """Redact known secret values and common secret key/value patterns."""

    redacted = text
    for secret in _secret_values():
        redacted = redacted.replace(secret, REDACTION)
    for pattern in _KEY_VALUE_PATTERNS:
        redacted = pattern.sub(lambda match: f"{match.group(1)}={REDACTION}", redacted)
    return redacted


def redact_data(value: Any) -> Any:
    """Recursively redact sensitive values from JSON-compatible data."""

    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, list):
        return [redact_data(item) for item in value]
    if isinstance(value, tuple):
        return [redact_data(item) for item in value]
    if isinstance(value, dict):
        return {key: redact_data(item) for key, item in value.items()}
    return value


def _secret_values() -> list[str]:
    values: list[str] = []
    for name in _SENSITIVE_ENV_NAMES:
        value = os.getenv(name, "")
        if len(value) >= 4:
            values.append(value)
    return values
