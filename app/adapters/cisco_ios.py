"""Cisco IOS adapter wrapping NetPulse's existing fixed-intent executor."""

from __future__ import annotations

from typing import Any

from app import executor
from app.inventory import get_all_devices, get_device, get_devices_by_role
from app.models import IntentRequest, IntentType, JobResult, ScopeType
from app.planner import READ_COMMAND_PREVIEW, WRITE_COMMAND_PREVIEW
from app.validators import WRITE_INTENTS, validate_request
from app.verifier import verify_write


class CiscoIOSAdapter:
    """Adapter facade for existing Cisco IOS job modules."""

    def __init__(self, inventory: dict[str, Any]) -> None:
        self.inventory = inventory

    def execute_read(self, intent: str, params: dict[str, Any]) -> list[JobResult]:
        """Validate and execute a read-only Cisco intent."""

        req = build_intent_request(intent, params)
        validate_request(req, self.inventory)
        return executor.execute(req, self.inventory)

    def execute_write(self, intent: str, params: dict[str, Any]) -> list[JobResult]:
        """Validate and execute an approved Cisco write intent."""

        req = build_intent_request(intent, params)
        validate_request(req, self.inventory)
        return executor.execute(req, self.inventory)

    def verify(
        self,
        intent: str,
        params: dict[str, Any],
        execution_result: list[JobResult],
    ) -> dict[str, Any]:
        """Run post-change verification for supported write intents."""

        return verify_write(intent, params, execution_result, self.inventory)

    def dry_run(self, intent: str, params: dict[str, Any]) -> dict[str, Any]:
        """Return the resolved Cisco targets and command preview without SSH."""

        req = build_intent_request(intent, params)
        validate_request(req, self.inventory)
        targets = _resolve_targets(req, self.inventory)
        return {
            "intent": intent,
            "targets": [{"name": d.name, "ip": d.ip, "role": d.role} for d in targets],
            "command_preview": _command_preview(intent, params),
        }


def build_intent_request(intent: str, params: dict[str, Any]) -> IntentRequest:
    """Build the existing IntentRequest model from runner parameters."""

    return IntentRequest(
        intent=IntentType(intent),
        device=params.get("device"),
        scope=ScopeType(params.get("scope", "single")),
        role=params.get("role"),
        ping_target=params.get("ping_target") or params.get("target"),
        raw_query=str(params.get("original_request") or params.get("raw_query") or intent),
        vlan_id=params.get("vlan_id"),
        vlan_name=params.get("vlan_name"),
        interface=params.get("interface"),
    )


def is_write_intent(intent: str) -> bool:
    """Return True when the intent maps to a Cisco write operation."""

    try:
        return IntentType(intent) in WRITE_INTENTS
    except ValueError:
        return False


def _resolve_targets(req: IntentRequest, inventory: dict[str, Any]) -> list[Any]:
    if req.scope == ScopeType.ALL:
        return get_all_devices(inventory)
    if req.scope == ScopeType.ROLE:
        return get_devices_by_role(req.role, inventory)  # type: ignore[arg-type]
    return [get_device(req.device, inventory)]  # type: ignore[arg-type]


def _command_preview(intent: str, params: dict[str, Any]) -> str | None:
    if intent == "ping" and (params.get("ping_target") or params.get("target")):
        return f"ping {params.get('ping_target') or params.get('target')} repeat 5"
    if intent == "add_vlan":
        return f"vlan {params.get('vlan_id')} / name {params.get('vlan_name')}"
    if intent == "remove_vlan":
        return f"no vlan {params.get('vlan_id')}"
    if intent == "shutdown_interface":
        return f"interface {params.get('interface')} / shutdown"
    if intent == "no_shutdown_interface":
        return f"interface {params.get('interface')} / no shutdown"
    if intent == "set_interface_vlan":
        return (
            f"interface {params.get('interface')} / switchport mode access / "
            f"switchport access vlan {params.get('vlan_id')}"
        )
    return READ_COMMAND_PREVIEW.get(intent) or WRITE_COMMAND_PREVIEW.get(intent)
