"""
Natural language intent router for NetPulse.

Uses deterministic keyword/regex matching — no LLM API calls.
The priority order in INTENT_PATTERNS matters: more specific patterns
(health_check, backup_config) are checked before broader ones (show_interfaces).

TODO (OpenClaw integration): Replace or wrap parse_intent() so OpenClaw can
call it as a tool, passing a user query and receiving a structured IntentRequest.
"""

from __future__ import annotations

import re
from typing import Optional

from app.logger import get_logger
from app.models import IntentRequest, IntentType, ScopeType

logger = get_logger(__name__)

# Each entry: (IntentType, list of regex patterns to match against lowercased query)
# First match wins — order from most specific to least specific.
INTENT_PATTERNS: list[tuple[IntentType, list[str]]] = [
    (IntentType.HEALTH_CHECK,    [r"\bhealth[\s_-]?check\b", r"\bhealth\b"]),
    (IntentType.BACKUP_CONFIG,   [r"\bbackup\b", r"\brunning[\s_-]?config\b"]),
    (IntentType.SHOW_TRUNKS,     [r"\btrunk\b"]),
    (IntentType.SHOW_VLANS,      [r"\bvlans?\b"]),
    (IntentType.SHOW_INTERFACES, [r"\binterfaces?\b"]),
    (IntentType.SHOW_VERSION,    [r"\bshow\s+version\b", r"\bversion\b"]),
]

# Matches device names like sw-core-01, sw-dist-01, sw-acc-02
DEVICE_PATTERN = re.compile(r"\b(sw-[\w-]+)\b", re.IGNORECASE)

ALL_SCOPE_PATTERN = re.compile(r"\ball\b", re.IGNORECASE)


def _match_intent(query: str) -> Optional[IntentType]:
    lower = query.lower()
    for candidate, patterns in INTENT_PATTERNS:
        for pattern in patterns:
            if re.search(pattern, lower):
                return candidate
    return None


def parse_intent(query: str) -> IntentRequest:
    """
    Parse a free-form natural language query into a structured IntentRequest.

    Examples:
        "show trunk status on sw-dist-01"  -> show_trunks, device=sw-dist-01
        "backup running config from sw-acc-02" -> backup_config, device=sw-acc-02
        "health check all switches"        -> health_check, scope=all

    Raises ValueError if intent or device cannot be resolved.
    """
    intent = _match_intent(query)
    if not intent:
        supported = [i.value for i in IntentType]
        raise ValueError(
            f"Could not match query to a supported intent: '{query}'\n"
            f"Supported intents: {supported}"
        )

    scope = ScopeType.ALL if ALL_SCOPE_PATTERN.search(query) else ScopeType.SINGLE

    device_match = DEVICE_PATTERN.search(query)
    device: Optional[str] = device_match.group(1).lower() if device_match else None

    if scope == ScopeType.SINGLE and device is None:
        raise ValueError(
            f"No device name found in query: '{query}'\n"
            "Include a device name like 'sw-core-01', or use 'all' for all devices."
        )

    # Backup config touches the filesystem — mark it for awareness
    confirmation_required = intent == IntentType.BACKUP_CONFIG

    req = IntentRequest(
        intent=intent,
        device=device,
        scope=scope,
        raw_query=query,
        confirmation_required=confirmation_required,
    )
    logger.info(f"Parsed intent: {req.intent.value}, device={req.device}, scope={req.scope.value}")
    return req
