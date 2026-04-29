"""Risk classification for NetPulse execution intents."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any

from app.ssot import ProtectedResources, load_protected_resources


class RiskLevel(str, Enum):
    """Ordered risk levels used by the execution control plane."""

    READ_ONLY = "READ_ONLY"
    LOW_CHANGE = "LOW_CHANGE"
    MEDIUM_CHANGE = "MEDIUM_CHANGE"
    HIGH_RISK = "HIGH_RISK"
    BLOCKED = "BLOCKED"


@dataclass
class RiskDecision:
    """Decision produced by risk classification before execution."""

    risk: RiskLevel
    approval_required: bool
    allowed: bool
    reason: str

    def model_dump(self) -> dict[str, Any]:
        """Pydantic-like helper for JSON-compatible output."""

        data = asdict(self)
        data["risk"] = self.risk.value
        return data


READ_ONLY_INTENTS: frozenset[str] = frozenset({
    "show_interfaces",
    "show_vlans",
    "show_trunks",
    "show_version",
    "show_errors",
    "show_cdp",
    "show_mac",
    "show_spanning_tree",
    "ping",
    "backup_config",
    "diff_backup",
    "health_check",
    "show_route",
    "show_arp",
    "show_etherchannel",
    "show_port_security",
    "show_logging",
    "audit_vlans",
    "audit_trunks",
    "device_facts",
    "drift_check",
})

LOW_CHANGE_INTENTS: frozenset[str] = frozenset({
    "add_vlan",
})

MEDIUM_CHANGE_INTENTS: frozenset[str] = frozenset({
    "remove_vlan",
    "no_shutdown_interface",
    "set_interface_vlan",
})

HIGH_RISK_INTENTS: frozenset[str] = frozenset({
    "shutdown_interface",
    "modify_trunk",
    "modify_trunk_allowed_vlans",
    "change_default_gateway",
    "change_route",
    "add_route",
    "remove_route",
})

WRITE_INTENTS: frozenset[str] = LOW_CHANGE_INTENTS | MEDIUM_CHANGE_INTENTS | HIGH_RISK_INTENTS


def classify_intent(
    intent: str,
    params: dict[str, Any],
    ssot: ProtectedResources | dict[str, Any] | None = None,
) -> RiskDecision:
    """Classify an intent before execution and decide approval requirements."""

    intent_name = _normalise_intent(intent)

    if intent_name in READ_ONLY_INTENTS:
        return RiskDecision(
            risk=RiskLevel.READ_ONLY,
            approval_required=False,
            allowed=True,
            reason="Read-only intent; no configuration change requested.",
        )

    if intent_name not in WRITE_INTENTS:
        return RiskDecision(
            risk=RiskLevel.BLOCKED,
            approval_required=False,
            allowed=False,
            reason="Unknown or arbitrary CLI-style intent is blocked.",
        )

    protected_decision = _protected_resource_decision(intent_name, params, ssot)
    if protected_decision is not None:
        return protected_decision

    if intent_name in HIGH_RISK_INTENTS:
        return RiskDecision(
            risk=RiskLevel.HIGH_RISK,
            approval_required=True,
            allowed=True,
            reason="Intent can disrupt connectivity or infrastructure state.",
        )

    if intent_name in MEDIUM_CHANGE_INTENTS:
        return RiskDecision(
            risk=RiskLevel.MEDIUM_CHANGE,
            approval_required=True,
            allowed=True,
            reason="Write intent changes infrastructure state and requires approval.",
        )

    return RiskDecision(
        risk=RiskLevel.LOW_CHANGE,
        approval_required=_requires_approval(intent_name),
        allowed=True,
        reason="Low-risk fixed intent; approval is required for real infrastructure writes.",
    )


def _normalise_intent(intent: str) -> str:
    return str(intent).strip().lower().replace(" ", "_")


def _requires_approval(intent: str) -> bool:
    return intent in WRITE_INTENTS


def _protected_resource_decision(
    intent: str,
    params: dict[str, Any],
    ssot: ProtectedResources | dict[str, Any] | None,
) -> RiskDecision | None:
    if intent not in WRITE_INTENTS:
        return None

    try:
        protected = _coerce_protected_resources(ssot)
    except Exception as exc:
        return RiskDecision(
            risk=RiskLevel.BLOCKED,
            approval_required=False,
            allowed=False,
            reason=f"Cannot load protected-resource policy: {exc}. Writes are blocked.",
        )

    vlan_id = params.get("vlan_id")
    if intent == "remove_vlan" and vlan_id is not None:
        for entry in protected.protected_vlans:
            if str(vlan_id) == str(entry.get("id", "")):
                return RiskDecision(
                    risk=RiskLevel.BLOCKED,
                    approval_required=False,
                    allowed=False,
                    reason=f"VLAN {vlan_id} is protected: {entry.get('reason', 'protected VLAN')}.",
                )

    device = params.get("device")
    if device:
        for entry in protected.protected_devices:
            if entry.get("name") != device:
                continue
            for rule in entry.get("extra_rules") or []:
                if intent in str(rule).lower() and "always" in str(rule).lower():
                    return RiskDecision(
                        risk=RiskLevel.BLOCKED,
                        approval_required=False,
                        allowed=False,
                        reason=f"Intent {intent} is forbidden on protected device {device}.",
                    )
            return RiskDecision(
                risk=RiskLevel.HIGH_RISK,
                approval_required=True,
                allowed=True,
                reason=f"Device {device} is protected: {entry.get('reason', 'protected device')}.",
            )

    interface = params.get("interface")
    if device and interface and intent in {
        "shutdown_interface",
        "no_shutdown_interface",
        "set_interface_vlan",
        "modify_trunk",
        "modify_trunk_allowed_vlans",
    }:
        for entry in protected.protected_interfaces:
            if entry.get("device") == device and interface in (entry.get("interfaces") or []):
                return RiskDecision(
                    risk=RiskLevel.HIGH_RISK,
                    approval_required=True,
                    allowed=True,
                    reason=f"Interface {interface} on {device} is protected: {entry.get('reason', 'protected interface')}.",
                )

    return None


def _coerce_protected_resources(
    ssot: ProtectedResources | dict[str, Any] | None,
) -> ProtectedResources:
    if ssot is None:
        return load_protected_resources()
    if isinstance(ssot, ProtectedResources):
        return ssot
    return ProtectedResources(
        protected_vlans=ssot.get("protected_vlans") or [],
        protected_devices=ssot.get("protected_devices") or [],
        protected_interfaces=ssot.get("protected_interfaces") or [],
    )
