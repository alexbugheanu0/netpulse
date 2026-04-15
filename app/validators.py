"""
Request validator for NetPulse.

Checks that an IntentRequest is safe and executable before any SSH
connection is opened. All validation failures raise ValueError with
an operator-friendly message.
"""

from __future__ import annotations

from typing import Dict

from app.logger import get_logger
from app.models import Device, IntentRequest, IntentType, ScopeType

logger = get_logger(__name__)

# Safe read-only intents — no state is changed on the device
READ_ONLY_INTENTS: frozenset[IntentType] = frozenset({
    IntentType.SHOW_INTERFACES,
    IntentType.SHOW_VLANS,
    IntentType.SHOW_TRUNKS,
    IntentType.SHOW_VERSION,
    IntentType.HEALTH_CHECK,
})

# Intents that write or save data (even if they only read from the device)
WRITE_LIKE_INTENTS: frozenset[IntentType] = frozenset({
    IntentType.BACKUP_CONFIG,
})


def validate_request(
    req: IntentRequest,
    inventory: Dict[str, Device],
) -> None:
    """
    Validate an IntentRequest against the inventory and allowed ruleset.

    Checks:
    - Intent is in the allowed set
    - Device exists in inventory (single-scope)
    - Device has SSH enabled
    - At least one SSH-enabled device exists (all-scope)

    Raises ValueError with a clear message on any violation.
    """
    all_intents = set(IntentType)
    if req.intent not in all_intents:
        raise ValueError(
            f"Unsupported intent: '{req.intent}'. "
            f"Allowed: {[i.value for i in IntentType]}"
        )

    if req.scope == ScopeType.SINGLE:
        if not req.device:
            raise ValueError("A device name is required for single-device requests.")

        if req.device not in inventory:
            raise ValueError(
                f"Device '{req.device}' not found in inventory.\n"
                f"Known devices: {list(inventory.keys())}"
            )

        device = inventory[req.device]
        if not device.ssh_enabled:
            raise ValueError(
                f"Device '{req.device}' has SSH disabled in inventory. "
                "Enable it or choose a different device."
            )

    if req.scope == ScopeType.ALL:
        ssh_devices = [d for d in inventory.values() if d.ssh_enabled]
        if not ssh_devices:
            raise ValueError(
                "No SSH-enabled devices found in inventory. "
                "Check devices.yaml and ensure ssh_enabled: true."
            )

    logger.info(
        f"Validation passed — intent={req.intent.value}, "
        f"device={req.device}, scope={req.scope.value}"
    )
