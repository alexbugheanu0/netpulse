"""Job: diagnose endpoint reachability from fixed Cisco IOS evidence."""

from __future__ import annotations

import ipaddress
import re
from typing import Any

from app.logger import get_logger
from app.models import Device, JobResult
from app.parsers import (
    parse_show_arp,
    parse_show_interfaces,
    parse_show_interfaces_errors,
    parse_show_mac_table,
    parse_show_port_security,
    parse_show_spanning_tree,
)
from app.ssh_client import run_command

logger = get_logger(__name__)

COMMANDS = (
    "show ip arp",
    "show mac address-table",
    "show interfaces status",
    "show interfaces",
    "show port-security",
    "show spanning-tree",
)


def run(device: Device, endpoint: str | None) -> JobResult:
    """
    Correlate ARP, MAC, interface, error, port-security, and STP evidence.

    The endpoint may be an IP or MAC address. The job never accepts CLI input;
    it always runs the fixed commands in COMMANDS and derives a diagnosis from
    parsed output.
    """
    try:
        if not endpoint:
            raise ValueError("endpoint is required")

        raw = {command: run_command(device, command) for command in COMMANDS}

        arp_entries = parse_show_arp(raw["show ip arp"])
        mac_entries = parse_show_mac_table(raw["show mac address-table"])
        interfaces = parse_show_interfaces(raw["show interfaces status"])
        errors = parse_show_interfaces_errors(raw["show interfaces"])
        port_security = parse_show_port_security(raw["show port-security"])
        stp_entries = parse_show_spanning_tree(raw["show spanning-tree"])

        diagnosis = _diagnose(
            endpoint=endpoint,
            arp_entries=arp_entries,
            mac_entries=mac_entries,
            interfaces=interfaces,
            errors=errors,
            port_security=port_security,
            stp_entries=stp_entries,
        )

        return JobResult(
            success=True,
            device=device.name,
            intent="diagnose_endpoint",
            command_executed=", ".join(COMMANDS),
            parsed_data=diagnosis,
            raw_output=_render_summary(device.name, diagnosis),
        )

    except Exception as exc:
        logger.error(f"diagnose_endpoint failed on {device.name}: {exc}")
        return JobResult(
            success=False,
            device=device.name,
            intent="diagnose_endpoint",
            command_executed=", ".join(COMMANDS),
            error=str(exc),
        )


def _diagnose(
    *,
    endpoint: str,
    arp_entries: list[dict[str, str]],
    mac_entries: list[dict[str, str]],
    interfaces: list[dict[str, str]],
    errors: list[dict[str, Any]],
    port_security: list[dict[str, Any]],
    stp_entries: list[dict[str, str]],
) -> dict[str, Any]:
    endpoint_type = "ip" if _is_ip(endpoint) else "mac"
    endpoint_mac = _normalise_mac(endpoint) if endpoint_type == "mac" else ""
    arp_entry = None

    if endpoint_type == "ip":
        arp_entry = next((e for e in arp_entries if e.get("ip") == endpoint), None)
        if arp_entry and not _is_incomplete_arp(arp_entry):
            endpoint_mac = _normalise_mac(arp_entry.get("mac", ""))

    mac_entry = None
    if endpoint_mac:
        mac_entry = next(
            (
                e for e in mac_entries
                if _normalise_mac(e.get("mac", "")) == endpoint_mac
            ),
            None,
        )

    access_port = mac_entry.get("port") if mac_entry else None
    vlan = mac_entry.get("vlan") if mac_entry else None

    interface_status = _find_by_port(interfaces, "port", access_port)
    error_entry = _find_by_port(errors, "port", access_port)
    port_sec_entry = _find_by_port(port_security, "interface", access_port)
    stp_for_port = [
        e for e in stp_entries
        if access_port and _same_interface(e.get("port", ""), access_port)
    ]

    findings: list[str] = []
    likely_cause = "No obvious fault found from ARP, MAC, interface, error, port-security, or STP evidence."
    confidence = "medium"
    next_action = "Check upstream routing, ACLs, host firewall, or application path."

    if endpoint_type == "ip" and arp_entry is None:
        findings.append("No ARP entry found for endpoint IP.")
        likely_cause = "Endpoint IP is not resolved in ARP on this device."
        confidence = "medium"
        next_action = "Verify the endpoint is powered on, in the expected VLAN, and using the correct gateway."
    elif arp_entry and _is_incomplete_arp(arp_entry):
        findings.append("ARP entry is incomplete.")
        likely_cause = "ARP resolution is failing; likely endpoint offline, wrong VLAN, or L2 path issue."
        confidence = "high"
        next_action = "Check endpoint link state, VLAN assignment, and local cabling before changing config."
    elif endpoint_mac and mac_entry is None:
        findings.append("Endpoint MAC was not learned in the MAC address table.")
        likely_cause = "The switch has L3 evidence but no learned L2 location for the endpoint."
        confidence = "medium"
        next_action = "Trace the endpoint from adjacent switches or verify recent traffic from the host."
    elif interface_status and _bad_interface_status(interface_status):
        status = interface_status.get("status", "unknown")
        findings.append(f"Endpoint port status is {status}.")
        likely_cause = f"Endpoint is learned on a port that is {status}."
        confidence = "high"
        next_action = "Inspect endpoint cabling, transceiver, admin state, and err-disable reason."
    elif error_entry and _has_errors(error_entry):
        findings.append(
            "Endpoint port has interface errors "
            f"(input={error_entry.get('input_errors', 0)}, "
            f"crc={error_entry.get('crc', 0)}, "
            f"output={error_entry.get('output_errors', 0)})."
        )
        likely_cause = "Physical layer or duplex-quality issue on the endpoint port."
        confidence = "high"
        next_action = "Check cable, optics, patch path, NIC, and switchport counters after clearing counters."
    elif port_sec_entry and int(port_sec_entry.get("violations", 0) or 0) > 0:
        findings.append(
            "Port-security violations found "
            f"({port_sec_entry.get('violations')} violation(s), "
            f"action={port_sec_entry.get('action', 'unknown')})."
        )
        likely_cause = "Port-security may be restricting or shutting down endpoint traffic."
        confidence = "high"
        next_action = "Review authorized MACs and port-security policy before clearing the violation."
    elif _has_blocking_stp(stp_for_port, vlan):
        findings.append("STP is blocking the endpoint port for the endpoint VLAN.")
        likely_cause = "Spanning Tree is blocking the endpoint path."
        confidence = "high"
        next_action = "Inspect STP topology, root bridge, and recent topology changes."
    else:
        if arp_entry:
            findings.append("ARP entry is resolved.")
        if mac_entry:
            findings.append("MAC address is learned on a switchport.")
        if interface_status:
            findings.append(f"Interface status is {interface_status.get('status', 'unknown')}.")

    evidence = {
        "arp_entry": arp_entry,
        "mac_entry": mac_entry,
        "interface_status": interface_status,
        "interface_errors": error_entry,
        "port_security": port_sec_entry,
        "spanning_tree": stp_for_port,
    }

    return {
        "endpoint": endpoint,
        "endpoint_type": endpoint_type,
        "resolved_ip": arp_entry.get("ip") if arp_entry else (endpoint if endpoint_type == "ip" else None),
        "resolved_mac": _format_mac(endpoint_mac) if endpoint_mac else None,
        "access_port": access_port,
        "vlan": vlan,
        "likely_cause": likely_cause,
        "confidence": confidence,
        "findings": findings,
        "next_action": next_action,
        "evidence": evidence,
    }


def _render_summary(device_name: str, diagnosis: dict[str, Any]) -> str:
    port = diagnosis.get("access_port") or "unknown port"
    vlan = diagnosis.get("vlan") or "unknown VLAN"
    return (
        f"Endpoint diagnosis on {device_name}: {diagnosis['endpoint']} -> "
        f"{port} / VLAN {vlan}. Likely cause: {diagnosis['likely_cause']} "
        f"Next action: {diagnosis['next_action']}"
    )


def _is_ip(value: str) -> bool:
    try:
        ipaddress.ip_address(value)
    except ValueError:
        return False
    return True


def _normalise_mac(mac: str) -> str:
    return re.sub(r"[^0-9a-f]", "", mac.lower())


def _format_mac(mac: str) -> str:
    if len(mac) != 12:
        return mac
    return f"{mac[0:4]}.{mac[4:8]}.{mac[8:12]}"


def _is_incomplete_arp(entry: dict[str, str]) -> bool:
    return "incomplete" in str(entry.get("mac", "")).lower()


def _find_by_port(rows: list[dict[str, Any]], key: str, port: str | None) -> dict[str, Any] | None:
    if not port:
        return None
    return next((row for row in rows if _same_interface(str(row.get(key, "")), port)), None)


def _same_interface(left: str, right: str) -> bool:
    return _canonical_interface(left) == _canonical_interface(right)


def _canonical_interface(name: str) -> str:
    value = name.strip().lower()
    replacements = {
        "tengigabitethernet": "te",
        "gigabitethernet": "gi",
        "fastethernet": "fa",
        "ethernet": "eth",
        "port-channel": "po",
        "portchannel": "po",
    }
    for full, short in replacements.items():
        if value.startswith(full):
            value = short + value[len(full):]
            break
    return re.sub(r"[^a-z0-9]", "", value)


def _bad_interface_status(entry: dict[str, str]) -> bool:
    status = str(entry.get("status", "")).lower()
    return status not in {"connected", "up"}


def _has_errors(entry: dict[str, Any]) -> bool:
    return (
        int(entry.get("input_errors", 0) or 0) > 0
        or int(entry.get("output_errors", 0) or 0) > 0
        or int(entry.get("crc", 0) or 0) > 0
        or int(entry.get("resets", 0) or 0) > 0
    )


def _has_blocking_stp(entries: list[dict[str, str]], vlan: str | None) -> bool:
    for entry in entries:
        if vlan and _stp_vlan_id(entry.get("vlan", "")) != str(vlan):
            continue
        if entry.get("state") in {"BLK", "BKN"}:
            return True
    return False


def _stp_vlan_id(value: str) -> str:
    match = re.search(r"(\d+)$", value)
    return str(int(match.group(1))) if match else value
