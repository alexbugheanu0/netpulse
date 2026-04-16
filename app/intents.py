"""
Natural language intent router for NetPulse.

Uses deterministic keyword/regex matching — no LLM API calls.
Order in INTENT_PATTERNS matters: more specific patterns are checked first
to avoid false positives on shared keywords.

Device name format: hyphenated with a numeric suffix, e.g. sw-core-01,
rtr-edge-02. Use --device explicitly when the name won't match.

TODO (OpenClaw integration): Expose parse_intent() as an OpenClaw tool call.
OpenClaw passes a user query; this function returns a structured IntentRequest.
"""

from __future__ import annotations

import re
from typing import Optional

from app.logger import get_logger
from app.models import IntentRequest, IntentType, ScopeType

logger = get_logger(__name__)

# Ordered from most specific to least — first match wins.
# SSOT audit intents must appear BEFORE the plain show_* intents that share
# keywords (e.g. "audit vlans" must match AUDIT_VLANS, not SHOW_VLANS).
INTENT_PATTERNS: list[tuple[IntentType, list[str]]] = [
    (IntentType.HEALTH_CHECK,       [r"\bhealth[\s_-]?check\b"]),
    # SSOT audit intents — placed before show_trunks / show_vlans
    (IntentType.DRIFT_CHECK,        [r"\bdrift[\s_-]?check\b", r"\bdrift\b", r"\bcompliance\b"]),
    (IntentType.AUDIT_VLANS,        [r"\baudit.{0,20}vlan", r"\bvlan.{0,20}(audit|drift|check)"]),
    (IntentType.AUDIT_TRUNKS,       [r"\baudit.{0,20}trunk", r"\btrunk.{0,20}(audit|drift|check)"]),
    (IntentType.DEVICE_FACTS,       [r"\bdevice[\s_-]?facts?\b", r"\bfacts?\b"]),
    # Standard show intents
    (IntentType.DIFF_BACKUP,        [r"\bdiff\b", r"\bconfig\s+changes?\b"]),
    (IntentType.BACKUP_CONFIG,      [r"\bbackup\b", r"\brunning[\s_-]?config\b"]),
    (IntentType.SHOW_ERRORS,        [r"\berrors?\b", r"\bdrops?\b", r"\bcrc\b",
                                     r"\berr[\s_-]?disabled?\b", r"\bbpdu[\s_-]?guard\b"]),
    (IntentType.SHOW_CDP,           [r"\bcdp\b", r"\blldp\b", r"\bneighbors?\b",
                                     r"\btopology\b", r"\bconnected\s+to\b"]),
    (IntentType.SHOW_MAC,           [r"\bmac\b"]),
    (IntentType.SHOW_SPANNING_TREE, [r"\bspanning[\s_-]?tree\b", r"\bstp\b",
                                     r"\broot[\s_-]?bridge\b", r"\bdiscarding\b",
                                     r"\bblocking\b", r"\bforwarding\b"]),
    (IntentType.PING,               [r"\bping\b"]),
    # L3 and advanced diagnostic intents
    (IntentType.SHOW_ROUTE,         [r"\brouting[\s_-]?table\b", r"\bshow\s+ip\s+route\b",
                                     r"\broute\s+to\b", r"\bbest[\s_-]?path\b",
                                     r"\bdefault[\s_-]?route\b", r"\bstatic[\s_-]?route\b",
                                     r"\bnext[\s_-]?hop\b"]),
    (IntentType.SHOW_ARP,           [r"\barp\b", r"\bwho\s+has\b", r"\barp[\s_-]?cache\b",
                                     r"\barp[\s_-]?entry\b", r"\bmac\s+for\s+ip\b"]),
    (IntentType.SHOW_ETHERCHANNEL,  [r"\betherchannel\b", r"\bport[\s_-]?channel\b",
                                     r"\blacp\b", r"\bpagp\b", r"\bbundle\b",
                                     r"\blag\b", r"\bportchannel\b"]),
    (IntentType.SHOW_PORT_SECURITY, [r"\bport[\s_-]?security\b", r"\bsecure[\s_-]?mac\b",
                                     r"\bmac[\s_-]?violation\b", r"\bsticky[\s_-]?mac\b"]),
    (IntentType.SHOW_LOGGING,       [r"\blogging\b", r"\bsyslog\b",
                                     r"\brecent[\s_-]?events?\b", r"\blast[\s_-]?reload\b",
                                     r"\brecent[\s_-]?errors?\b", r"\bwhat\s+happened\b",
                                     r"\blog[\s_-]?messages?\b"]),
    (IntentType.SHOW_TRUNKS,        [r"\btrunk\b"]),
    (IntentType.SHOW_VLANS,         [r"\bvlans?\b"]),
    (IntentType.SHOW_INTERFACES,    [r"\binterfaces?\b"]),
    (IntentType.SHOW_VERSION,       [r"\bshow\s+version\b", r"\bversion\b"]),
]

# Matches hyphenated device names ending in a numeric segment: sw-core-01, rtr-edge-02
DEVICE_PATTERN = re.compile(r"\b([a-z][a-z0-9]*(?:-[a-z0-9]+)*-\d+)\b", re.IGNORECASE)

# Extracts an IPv4 address for ping target
IP_PATTERN = re.compile(r"\b(\d{1,3}(?:\.\d{1,3}){3})\b")

# "all" keyword triggers scope=ALL
ALL_SCOPE_PATTERN = re.compile(r"\ball\b", re.IGNORECASE)


def _match_intent(query: str) -> Optional[IntentType]:
    """Return the first IntentType whose pattern matches the lowercased query, or None."""
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
        "show trunk status on sw-dist-01"      -> show_trunks,   device=sw-dist-01
        "backup running config from sw-acc-02" -> backup_config, device=sw-acc-02
        "health check all switches"            -> health_check,  scope=all
        "show errors on sw-core-01"            -> show_errors,   device=sw-core-01
        "show cdp neighbors on sw-dist-01"     -> show_cdp,      device=sw-dist-01
        "show mac table on sw-acc-01"          -> show_mac,      device=sw-acc-01
        "show spanning tree on sw-core-01"     -> show_spanning_tree
        "ping 10.0.0.1 from sw-core-01"        -> ping, device=sw-core-01, ping_target=10.0.0.1
        "diff config on sw-core-01"            -> diff_backup,   device=sw-core-01

    Raises ValueError with an operator-friendly message if intent or device
    cannot be resolved.
    """
    intent = _match_intent(query)
    if not intent:
        supported = [i.value for i in IntentType]
        raise ValueError(
            f"Could not match query to a supported intent: '{query}'\n"
            f"Supported intents: {supported}\n"
            "Tip: use --intent / --device flags for unambiguous input."
        )

    scope = ScopeType.ALL if ALL_SCOPE_PATTERN.search(query) else ScopeType.SINGLE

    device_match = DEVICE_PATTERN.search(query)
    device: Optional[str] = device_match.group(1).lower() if device_match else None

    # Ping requires a target IP extracted from the query
    ping_target: Optional[str] = None
    if intent == IntentType.PING:
        ip_match = IP_PATTERN.search(query)
        if not ip_match:
            raise ValueError(
                f"No target IP address found in ping query: '{query}'\n"
                "Example: 'ping 10.0.0.1 from sw-core-01'"
            )
        ping_target = ip_match.group(1)

    if scope == ScopeType.SINGLE and device is None:
        raise ValueError(
            f"No device name found in query: '{query}'\n"
            "Include a device name (e.g. sw-core-01), use 'all' for all devices,\n"
            "or use --device explicitly."
        )

    req = IntentRequest(
        intent=intent,
        device=device,
        scope=scope,
        ping_target=ping_target,
        raw_query=query,
    )
    logger.info(
        f"Parsed intent: {req.intent.value}, device={req.device}, "
        f"scope={req.scope.value}, ping_target={req.ping_target}"
    )
    return req
