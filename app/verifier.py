"""Post-change verification helpers for NetPulse write intents."""

from __future__ import annotations

from typing import Any

from app.inventory import get_device
from app.jobs import show_interfaces, show_trunks, show_vlans
from app.models import JobResult


VerificationResult = dict[str, Any]


def verify_write(
    intent: str,
    params: dict[str, Any],
    execution_results: list[JobResult],
    inventory: dict[str, Any] | None = None,
) -> VerificationResult:
    """Verify supported write intents and return structured evidence."""

    if not execution_results or any(not result.success for result in execution_results):
        return {
            "verified": False,
            "checks": ["execution_success"],
            "evidence": "Execution did not complete successfully; verification skipped.",
            "error": "execution_failed",
        }

    if inventory is None or not params.get("device"):
        return {
            "verified": False,
            "checks": ["inventory_available"],
            "evidence": "No inventory/device was provided for verification.",
            "error": "missing_inventory",
        }

    device = get_device(params["device"], inventory)

    if intent == "add_vlan":
        result = show_vlans.run(device)
        return _verify_vlan_present(params, result)

    if intent == "remove_vlan":
        result = show_vlans.run(device)
        return _verify_vlan_absent(params, result)

    if intent == "set_interface_vlan":
        result = show_interfaces.run(device)
        return _verify_interface_vlan(params, result)

    if intent == "shutdown_interface":
        result = show_interfaces.run(device)
        return _verify_interface_state(params, result, expected_disabled=True)

    if intent == "no_shutdown_interface":
        result = show_interfaces.run(device)
        return _verify_interface_state(params, result, expected_disabled=False)

    if intent in {"modify_trunk", "modify_trunk_allowed_vlans"}:
        result = show_trunks.run(device)
        return {
            "verified": result.success,
            "checks": ["show_interfaces_trunk"],
            "evidence": result.raw_output,
            "error": result.error,
            "todo": "Add structured trunk parser for exact allowed-VLAN assertions.",
        }

    return {
        "verified": False,
        "checks": [],
        "evidence": "",
        "error": f"No verifier implemented for intent '{intent}'.",
    }


def _verify_vlan_present(params: dict[str, Any], result: JobResult) -> VerificationResult:
    vlan_id = str(params.get("vlan_id"))
    rows = result.parsed_data if isinstance(result.parsed_data, list) else []
    match = next((row for row in rows if str(row.get("vlan_id")) == vlan_id), None)
    return {
        "verified": result.success and match is not None,
        "checks": ["show_vlan_brief", f"vlan_{vlan_id}_present"],
        "evidence": match or result.raw_output,
        "error": None if result.success and match is not None else result.error or "vlan_not_found",
    }


def _verify_vlan_absent(params: dict[str, Any], result: JobResult) -> VerificationResult:
    vlan_id = str(params.get("vlan_id"))
    rows = result.parsed_data if isinstance(result.parsed_data, list) else []
    match = next((row for row in rows if str(row.get("vlan_id")) == vlan_id), None)
    return {
        "verified": result.success and match is None,
        "checks": ["show_vlan_brief", f"vlan_{vlan_id}_absent"],
        "evidence": rows if result.success else result.raw_output,
        "error": None if result.success and match is None else result.error or "vlan_still_present",
    }


def _verify_interface_vlan(params: dict[str, Any], result: JobResult) -> VerificationResult:
    interface = str(params.get("interface") or "")
    vlan_id = str(params.get("vlan_id"))
    rows = result.parsed_data if isinstance(result.parsed_data, list) else []
    match = next((row for row in rows if _same_interface(row.get("port"), interface)), None)
    verified = result.success and match is not None and str(match.get("vlan")) == vlan_id
    return {
        "verified": verified,
        "checks": ["show_interfaces_status", f"{interface}_access_vlan_{vlan_id}"],
        "evidence": match or result.raw_output,
        "error": None if verified else result.error or "interface_vlan_mismatch",
    }


def _verify_interface_state(
    params: dict[str, Any],
    result: JobResult,
    expected_disabled: bool,
) -> VerificationResult:
    interface = str(params.get("interface") or "")
    rows = result.parsed_data if isinstance(result.parsed_data, list) else []
    match = next((row for row in rows if _same_interface(row.get("port"), interface)), None)
    status = str((match or {}).get("status", "")).lower()
    disabled = status in {"disabled", "administratively down", "admin-down"}
    verified = result.success and match is not None and disabled is expected_disabled
    return {
        "verified": verified,
        "checks": ["show_interfaces_status", f"{interface}_admin_state"],
        "evidence": match or result.raw_output,
        "error": None if verified else result.error or "interface_state_mismatch",
        "todo": "Cisco abbreviations can vary; enhance interface name normalization if needed.",
    }


def _same_interface(observed: Any, expected: str) -> bool:
    observed_str = str(observed or "").lower()
    expected_str = expected.lower()
    return observed_str == expected_str or observed_str.endswith(expected_str)
