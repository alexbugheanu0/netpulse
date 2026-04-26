"""Structured execution plans for NetPulse requests."""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PLAN_OUTPUT_DIR = Path("output/plans")

READ_COMMAND_PREVIEW: dict[str, str] = {
    "show_interfaces": "show interfaces status",
    "show_vlans": "show vlan brief",
    "show_trunks": "show interfaces trunk",
    "show_version": "show version",
    "show_errors": "show interfaces",
    "show_cdp": "show cdp neighbors detail",
    "show_mac": "show mac address-table",
    "show_spanning_tree": "show spanning-tree",
    "ping": "ping <target> repeat 5",
    "backup_config": "show running-config -> output/backups/",
    "diff_backup": "local backup diff",
    "health_check": "show version + show interfaces status + show vlan brief",
    "show_route": "show ip route",
    "show_arp": "show ip arp",
    "show_etherchannel": "show etherchannel summary",
    "show_port_security": "show port-security",
    "show_logging": "show logging",
    "audit_vlans": "show vlan brief -> compare against SSOT",
    "audit_trunks": "show interfaces trunk -> compare against SSOT",
    "device_facts": "show version + show interfaces status",
    "drift_check": "show vlan brief + show interfaces trunk -> SSOT drift check",
}

WRITE_COMMAND_PREVIEW: dict[str, str] = {
    "add_vlan": "vlan <vlan_id> / name <vlan_name>",
    "remove_vlan": "no vlan <vlan_id>",
    "shutdown_interface": "interface <interface> / shutdown",
    "no_shutdown_interface": "interface <interface> / no shutdown",
    "set_interface_vlan": "interface <interface> / switchport mode access / switchport access vlan <vlan_id>",
}

MOCK_DEMO_INTENTS: dict[str, list[dict[str, str]]] = {
    "prepare_lab_environment": [
        {
            "action": "check_network_path",
            "target": "demo network path",
            "adapter": "cisco_ios",
            "expected_result": "Network path is reachable for the simulation job.",
        },
        {
            "action": "check_compute_health",
            "target": "simulation cluster",
            "adapter": "compute_mock",
            "expected_result": "Compute nodes are healthy.",
        },
        {
            "action": "check_storage_path",
            "target": "demo dataset path",
            "adapter": "storage_mock",
            "expected_result": "Dataset and mount path are ready.",
        },
        {
            "action": "check_instrument_status",
            "target": "mock lab instrument",
            "adapter": "instrument_mock",
            "expected_result": "Instrument is ready for the simulation.",
        },
        {
            "action": "verify_environment",
            "target": "simulation job demo-001",
            "adapter": "mock_verifier",
            "expected_result": "All mocked readiness checks passed.",
        },
    ],
}


@dataclass
class PlanStep:
    """One planned action in an execution plan."""

    step_id: str
    action: str
    target: str
    adapter: str
    risk: str = "pending"
    requires_approval: bool = False
    precheck: str | None = None
    command_preview: str | None = None
    expected_result: str = ""
    status: str = "planned"


@dataclass
class ExecutionPlan:
    """JSON-compatible execution plan created before any execution."""

    request_id: str
    timestamp: str
    user: str | None
    source: str | None
    original_request: str
    normalized_intent: str
    domain: str
    scope: dict[str, Any]
    steps: list[PlanStep]
    expected_outputs: list[str]
    risk_summary: str = "pending"
    approval_required: bool = False
    rollback_plan: list[str] = field(default_factory=list)
    dry_run: bool = False
    final_status: str = "planned"


def create_request_id() -> str:
    """Create a short unique request id for plans and audit artifacts."""

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    return f"np-{stamp}-{uuid.uuid4().hex[:8]}"


def build_plan(
    intent: str,
    params: dict[str, Any],
    user: str | None = None,
    source: str | None = None,
    dry_run: bool = False,
) -> ExecutionPlan:
    """Build a structured execution plan for a supported intent."""

    request_id = str(params.get("request_id") or create_request_id())
    domain = str(params.get("domain") or _infer_domain(intent))
    scope = _build_scope(params)
    steps = _build_steps(intent, params, domain)

    return ExecutionPlan(
        request_id=request_id,
        timestamp=datetime.now(timezone.utc).isoformat(),
        user=user,
        source=source,
        original_request=str(params.get("original_request") or params.get("raw_query") or intent),
        normalized_intent=intent,
        domain=domain,
        scope=scope,
        steps=steps,
        expected_outputs=[step.expected_result for step in steps if step.expected_result],
        rollback_plan=_rollback_plan(intent, params),
        dry_run=dry_run,
    )


def serialize_plan(plan: ExecutionPlan) -> dict[str, Any]:
    """Return a JSON-compatible dict representation of an execution plan."""

    return asdict(plan)


def save_plan(plan: ExecutionPlan, output_dir: str | Path = PLAN_OUTPUT_DIR) -> Path:
    """Persist an execution plan as pretty JSON and return its path."""

    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{plan.request_id}.json"
    path.write_text(json.dumps(serialize_plan(plan), indent=2, default=str) + "\n")
    return path


def _build_scope(params: dict[str, Any]) -> dict[str, Any]:
    return {
        "device": params.get("device"),
        "devices": params.get("devices"),
        "scope": params.get("scope", "single"),
        "role": params.get("role"),
        "target": params.get("target"),
    }


def _build_steps(intent: str, params: dict[str, Any], domain: str) -> list[PlanStep]:
    if intent in MOCK_DEMO_INTENTS:
        return [
            PlanStep(
                step_id=f"step-{idx:02d}",
                action=step["action"],
                target=step["target"],
                adapter=step["adapter"],
                precheck="mock readiness check",
                expected_result=step["expected_result"],
            )
            for idx, step in enumerate(MOCK_DEMO_INTENTS[intent], start=1)
        ]

    target = _target_from_params(params)
    adapter = "cisco_ios" if domain == "network" else f"{domain}_mock"
    preview = _command_preview(intent, params)
    action = intent
    expected = _expected_result(intent, target)

    return [
        PlanStep(
            step_id="step-01",
            action=action,
            target=target,
            adapter=adapter,
            precheck="validate inventory, scope, parameters, and policy",
            command_preview=preview,
            expected_result=expected,
        )
    ]


def _infer_domain(intent: str) -> str:
    if intent in MOCK_DEMO_INTENTS:
        return "lab"
    if intent.startswith(("check_compute", "allocate_simulation")):
        return "compute"
    if intent.startswith(("check_storage", "check_dataset", "verify_mount")):
        return "storage"
    if intent.startswith(("check_instrument", "prepare_instrument")):
        return "instrument"
    return "network"


def _target_from_params(params: dict[str, Any]) -> str:
    if params.get("device"):
        return str(params["device"])
    if params.get("role"):
        return f"role:{params['role']}"
    if params.get("target"):
        return str(params["target"])
    return str(params.get("scope") or "all")


def _command_preview(intent: str, params: dict[str, Any]) -> str | None:
    if intent == "ping" and params.get("ping_target"):
        return f"ping {params['ping_target']} repeat 5"
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


def _expected_result(intent: str, target: str) -> str:
    if intent.startswith(("show_", "audit_", "device_facts", "drift_check", "health_check")):
        return f"Structured read results from {target}."
    if intent == "backup_config":
        return f"Configuration backup artifact for {target}."
    if intent == "diff_backup":
        return "Local backup diff result."
    if intent == "ping":
        return f"Ping reachability result from {target}."
    return f"Intent {intent} completed and verified for {target}."


def _rollback_plan(intent: str, params: dict[str, Any]) -> list[str]:
    if intent == "add_vlan":
        return [f"no vlan {params.get('vlan_id')}"]
    if intent == "remove_vlan":
        return [f"vlan {params.get('vlan_id')}"]
    if intent == "shutdown_interface":
        return [f"interface {params.get('interface')}", "no shutdown"]
    if intent == "no_shutdown_interface":
        return [f"interface {params.get('interface')}", "shutdown"]
    if intent == "set_interface_vlan":
        return ["Restore previous access VLAN from backup or change record."]
    return []
