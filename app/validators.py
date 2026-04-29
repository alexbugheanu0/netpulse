"""
Request validator for NetPulse.

Checks that an IntentRequest is safe and executable before any SSH
connection is opened. All validation failures raise ValueError with
an operator-friendly message.
"""

from __future__ import annotations

import ipaddress
import re

from app.logger import get_logger
from app.models import Device, IntentRequest, IntentType, ScopeType
from app.ssot import load_protected_resources

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

MAC_RE = re.compile(
    r"^(?:"
    r"(?:[0-9a-f]{4}\.){2}[0-9a-f]{4}|"
    r"(?:[0-9a-f]{2}:){5}[0-9a-f]{2}|"
    r"(?:[0-9a-f]{2}-){5}[0-9a-f]{2}"
    r")$",
    re.IGNORECASE,
)


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

        # VLAN intents require vlan_id within the valid Cisco range
        if req.intent in {IntentType.ADD_VLAN, IntentType.REMOVE_VLAN,
                          IntentType.SET_INTERFACE_VLAN}:
            if req.vlan_id is None:
                raise ValueError(
                    f"Intent '{req.intent.value}' requires a vlan_id."
                )
            if not (1 <= req.vlan_id <= 4094):
                raise ValueError(
                    f"VLAN ID {req.vlan_id} is out of range. "
                    "Valid Cisco VLAN IDs are 1–4094."
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

    if req.intent == IntentType.PING and req.ping_target:
        try:
            addr = ipaddress.ip_address(req.ping_target)
        except ValueError:
            raise ValueError(
                f"'{req.ping_target}' is not a valid IP address. "
                "ping_target must be a valid unicast IPv4 or IPv6 address."
            )
        if addr.is_multicast or addr.is_unspecified or (
            isinstance(addr, ipaddress.IPv4Address) and int(addr) == 0xFFFFFFFF
        ):
            raise ValueError(
                f"'{req.ping_target}' is a broadcast or multicast address. "
                "Only unicast addresses are permitted as a ping target."
            )

    if req.intent == IntentType.DIAGNOSE_ENDPOINT:
        if not req.endpoint:
            raise ValueError(
                "Intent 'diagnose_endpoint' requires an endpoint IP or MAC address."
            )
        if not _valid_endpoint(req.endpoint):
            raise ValueError(
                f"'{req.endpoint}' is not a valid endpoint. "
                "Use an IPv4 address or MAC address."
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

    if req.intent in WRITE_INTENTS:
        policy_check(req)

    logger.info(
        f"Validation passed — intent={req.intent.value}, "
        f"device={req.device}, scope={req.scope.value}, role={req.role}"
    )


def policy_check(req: IntentRequest) -> None:
    """
    Enforce forbidden rules from ssot/protected-resources.yaml for write intents.

    Raises ValueError with a clear operator message if the request targets a
    protected VLAN, device, or interface. This function is the code-level
    enforcement of the rules documented in ssot/change-policy.yaml —
    specifically the cases that must *never* execute regardless of whether
    the agent layer obtained user confirmation.

    auto_approve vs require_approval decisions remain in the agent layer
    (SKILL.md / Telegram approval workflow) since the code has no mechanism
    to verify that chat-level confirmation actually occurred.
    """
    try:
        protected = load_protected_resources()
    except Exception as exc:
        # Fail closed: an inaccessible or malformed policy file must block
        # all write operations, not silently permit them.
        raise ValueError(
            f"Cannot load ssot/protected-resources.yaml: {exc}. "
            "Write operations are blocked until the policy file is accessible."
        ) from exc

    # ── Protected VLANs: block remove_vlan targeting a listed VLAN id ─────────
    if req.intent == IntentType.REMOVE_VLAN and req.vlan_id is not None:
        for entry in protected.protected_vlans:
            if str(req.vlan_id) == str(entry.get("id", "")):
                reason = entry.get("reason", "protected VLAN")
                raise ValueError(
                    f"VLAN {req.vlan_id} ({entry.get('name', '')}) is a protected resource. "
                    f"Reason: {reason}. "
                    "This operation is forbidden by ssot/protected-resources.yaml."
                )

    # ── Protected Devices: apply per-device extra_rules ────────────────────────
    if req.device:
        for entry in protected.protected_devices:
            if entry.get("name") == req.device:
                extra_rules: list[str] = entry.get("extra_rules") or []
                for rule in extra_rules:
                    # Rule text: "shutdown_interface always requires approval on this device..."
                    # We treat any extra_rule mentioning an intent name as an unconditional block.
                    if req.intent.value in rule.lower() and "always" in rule.lower():
                        reason = entry.get("reason", "protected device")
                        raise ValueError(
                            f"Write intent '{req.intent.value}' on device '{req.device}' "
                            f"is unconditionally forbidden by ssot/protected-resources.yaml. "
                            f"Reason: {reason}."
                        )

    # ── Protected Interfaces: block interface-touching intents ─────────────────
    INTERFACE_INTENTS: frozenset[IntentType] = frozenset({
        IntentType.SHUTDOWN_INTERFACE,
        IntentType.NO_SHUTDOWN_INTERFACE,
        IntentType.SET_INTERFACE_VLAN,
    })
    if req.intent in INTERFACE_INTENTS and req.device and req.interface:
        for entry in protected.protected_interfaces:
            if entry.get("device") == req.device:
                protected_ifaces: list[str] = entry.get("interfaces") or []
                if req.interface in protected_ifaces:
                    reason = entry.get("reason", "protected interface")
                    raise ValueError(
                        f"Interface '{req.interface}' on device '{req.device}' "
                        f"is a protected resource. Reason: {reason}. "
                        "This operation is forbidden by ssot/protected-resources.yaml."
                    )


def _valid_endpoint(value: str) -> bool:
    try:
        addr = ipaddress.ip_address(value)
    except ValueError:
        return bool(MAC_RE.match(value.strip()))
    return not (
        addr.is_multicast
        or addr.is_unspecified
        or (isinstance(addr, ipaddress.IPv4Address) and int(addr) == 0xFFFFFFFF)
    )
