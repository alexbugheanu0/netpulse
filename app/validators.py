"""
Request validator for NetPulse.

Checks that an IntentRequest is safe and executable before any SSH
connection is opened. All validation failures raise ValueError with
an operator-friendly message.
"""

from __future__ import annotations

from app.logger import get_logger
from app.models import Device, IntentRequest, IntentType, ScopeType

logger = get_logger(__name__)

# These intents operate on local data only — no SSH connection is opened.
NON_SSH_INTENTS: frozenset[IntentType] = frozenset({
    IntentType.DIFF_BACKUP,
})

# Write intents push config to devices. They are restricted to scope=single
# and require specific parameters validated below.
WRITE_INTENTS: frozenset[IntentType] = frozenset({
    IntentType.ADD_VLAN,
    IntentType.REMOVE_VLAN,
    IntentType.SHUTDOWN_INTERFACE,
    IntentType.NO_SHUTDOWN_INTERFACE,
    IntentType.SET_INTERFACE_VLAN,
})


def validate_request(
    req: IntentRequest,
    inventory: dict[str, Device],
) -> None:
    """
    Validate an IntentRequest against the loaded inventory.

    Checks vary by scope:
    - SINGLE: device exists, SSH enabled (unless non-SSH intent)
    - ALL:    at least one SSH-enabled device (unless non-SSH intent)
    - ROLE:   role exists in inventory, at least one SSH-enabled device with that role

    Special cases:
    - DIFF_BACKUP: no SSH check needed (reads local files)
    - PING: ping_target must be set

    Raises ValueError with a clear message on any violation.
    """
    needs_ssh = req.intent not in NON_SSH_INTENTS

    # ── Write intent constraints ───────────────────────────────────────────────
    if req.intent in WRITE_INTENTS:
        if req.scope != ScopeType.SINGLE:
            raise ValueError(
                f"Write intent '{req.intent.value}' requires scope=single. "
                "Bulk writes across all devices or roles are not permitted."
            )

        # VLAN intents require vlan_id
        if req.intent in {IntentType.ADD_VLAN, IntentType.REMOVE_VLAN,
                          IntentType.SET_INTERFACE_VLAN}:
            if req.vlan_id is None:
                raise ValueError(
                    f"Intent '{req.intent.value}' requires a vlan_id."
                )

        # add_vlan also requires vlan_name
        if req.intent == IntentType.ADD_VLAN and not req.vlan_name:
            raise ValueError("Intent 'add_vlan' requires a vlan_name.")

        # Interface intents require interface
        if req.intent in {IntentType.SHUTDOWN_INTERFACE,
                          IntentType.NO_SHUTDOWN_INTERFACE,
                          IntentType.SET_INTERFACE_VLAN}:
            if not req.interface:
                raise ValueError(
                    f"Intent '{req.intent.value}' requires an interface "
                    "(e.g. 'Gi1/0/5')."
                )

    if req.intent == IntentType.PING and not req.ping_target:
        raise ValueError(
            "A target IP is required for ping. "
            "Use --target <ip> or include it in the query: 'ping 10.0.0.1 from sw-core-01'."
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
        if needs_ssh and not device.ssh_enabled:
            raise ValueError(
                f"Device '{req.device}' has SSH disabled in inventory. "
                "Set ssh_enabled: true in devices.yaml or choose a different device."
            )

    elif req.scope == ScopeType.ALL:
        if needs_ssh:
            ssh_devices = [d for d in inventory.values() if d.ssh_enabled]
            if not ssh_devices:
                raise ValueError(
                    "No SSH-enabled devices in inventory. "
                    "Check devices.yaml — at least one device must have ssh_enabled: true."
                )

    elif req.scope == ScopeType.ROLE:
        if not req.role:
            raise ValueError("A role name is required for role-scoped requests.")

        role_devices = [d for d in inventory.values() if d.role == req.role]
        if not role_devices:
            available = sorted({d.role for d in inventory.values()})
            raise ValueError(
                f"No devices found with role '{req.role}'.\n"
                f"Available roles: {available}"
            )

        if needs_ssh:
            ssh_role_devices = [d for d in role_devices if d.ssh_enabled]
            if not ssh_role_devices:
                raise ValueError(
                    f"No SSH-enabled devices with role '{req.role}'. "
                    "Check ssh_enabled in devices.yaml."
                )

    logger.info(
        f"Validation passed — intent={req.intent.value}, "
        f"device={req.device}, scope={req.scope.value}, role={req.role}"
    )
