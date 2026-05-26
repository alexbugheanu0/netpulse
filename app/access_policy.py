"""Central access policy for inventory-scoped, read-only NetPulse operation."""

from __future__ import annotations

from app.models import IntentType


ALLOWED_READ_INTENTS: frozenset[IntentType] = frozenset({
    IntentType.SHOW_INTERFACES,
    IntentType.SHOW_VLANS,
    IntentType.SHOW_TRUNKS,
    IntentType.SHOW_VERSION,
    IntentType.SHOW_ERRORS,
    IntentType.SHOW_CDP,
    IntentType.SHOW_MAC,
    IntentType.SHOW_SPANNING_TREE,
    IntentType.BACKUP_CONFIG,
    IntentType.DIFF_BACKUP,
    IntentType.HEALTH_CHECK,
    IntentType.SHOW_ROUTE,
    IntentType.SHOW_ARP,
    IntentType.SHOW_ETHERCHANNEL,
    IntentType.SHOW_PORT_SECURITY,
    IntentType.SHOW_LOGGING,
    IntentType.DIAGNOSE_ENDPOINT,
    IntentType.AUDIT_VLANS,
    IntentType.AUDIT_TRUNKS,
    IntentType.DEVICE_FACTS,
    IntentType.DRIFT_CHECK,
})

# Targetless status and audit reads are evaluated across enrolled switches.
# Evidence creation and endpoint diagnosis require explicit targeting because
# their scope or resulting artifacts deserve an operator choice.
IMPLICIT_ALL_READ_INTENTS: frozenset[IntentType] = ALLOWED_READ_INTENTS - frozenset({
    IntentType.BACKUP_CONFIG,
    IntentType.DIFF_BACKUP,
    IntentType.DIAGNOSE_ENDPOINT,
})

# Commands may be sent only after an intent and inventory target pass validation.
ALLOWED_READ_COMMANDS: frozenset[str] = frozenset({
    "show interfaces status",
    "show vlan brief",
    "show interfaces trunk",
    "show version",
    "show interfaces",
    "show cdp neighbors detail",
    "show mac address-table",
    "show spanning-tree",
    "show running-config",
    "show ip route",
    "show ip arp",
    "show etherchannel summary",
    "show port-security",
    "show logging",
})


def require_read_only_intent(intent: IntentType | str) -> None:
    """Reject any operation that is not an explicitly authorised device read."""

    try:
        typed_intent = intent if isinstance(intent, IntentType) else IntentType(intent)
    except ValueError as exc:
        raise ValueError("Unknown or arbitrary NetPulse intent is blocked.") from exc

    if typed_intent not in ALLOWED_READ_INTENTS:
        raise ValueError(
            f"Intent '{typed_intent.value}' is blocked: NetPulse is configured "
            "for read-only access to enrolled switches only."
        )


def require_read_command(command: str) -> None:
    """Reject command text not used by the approved read-intent jobs."""

    if command not in ALLOWED_READ_COMMANDS:
        raise PermissionError(
            "Device command blocked: NetPulse permits fixed read-only commands only."
        )
