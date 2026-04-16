"""
Job: collect and summarise key facts about a device.

Runs 'show version' and 'show interfaces status' in two SSH calls and
assembles a clean facts dict. No SSOT comparison — this is a collection-only
intent useful for a quick device overview or as a pre-flight before auditing.

Execution flow:
  1. Run 'show version' → platform, IOS version, uptime, serial
  2. Run 'show interfaces status' → port count, connected ports, err-disabled
  3. Assemble and return a structured facts dict.
"""

from __future__ import annotations

import re

from app.logger import get_logger
from app.models import Device, JobResult
from app.parsers import parse_show_interfaces, parse_show_version
from app.ssh_client import run_command

logger = get_logger(__name__)

COMMANDS = {
    "version":    "show version",
    "interfaces": "show interfaces status",
}


def run(device: Device) -> JobResult:
    """Collect version + interface facts and return a structured summary."""
    collected: dict = {}
    errors: list[str] = []

    for key, command in COMMANDS.items():
        try:
            raw = run_command(device, command)
            collected[key] = (
                parse_show_version(raw)
                if key == "version"
                else parse_show_interfaces(raw)
            )
            logger.info(f"device_facts [{key}] OK on {device.name}")
        except Exception as exc:
            logger.warning(f"device_facts [{key}] FAILED on {device.name}: {exc}")
            errors.append(f"{key}: {exc}")

    success = len(errors) < len(COMMANDS)  # at least one command succeeded

    ver:   dict  = collected.get("version", {}) or {}
    ports: list  = collected.get("interfaces", []) or []

    # Extract IOS version from software string
    software = ver.get("software", "")
    m = re.search(r"Version\s+([\d()A-Za-z.]+)", software)
    ios_version = m.group(1) if m else ""

    # Extract human-readable uptime
    uptime_raw = ver.get("uptime", "")
    m = re.search(r"uptime is\s+(.+)", uptime_raw, re.IGNORECASE)
    uptime = m.group(1).strip() if m else uptime_raw.strip()

    # Port statistics from 'show interfaces status'
    connected    = [p for p in ports if "connected"    in p.get("status", "").lower()]
    err_disabled = [p for p in ports if "err-disabled" in p.get("status", "").lower()]

    facts: dict = {
        "device":              device.name,
        "role":                device.role,
        "platform":            device.platform,
        "ip":                  device.ip,
        "ios_version":         ios_version,
        "uptime":              uptime,
        "serial":              ver.get("serial", ""),
        "hardware":            ver.get("hardware", ""),
        "total_ports":         len(ports),
        "connected_ports":     len(connected),
        "err_disabled_ports":  len(err_disabled),
        "collection_errors":   errors,
    }

    # One-line summary for CLI / chat
    summary_parts: list[str] = []
    if ios_version:
        summary_parts.append(f"IOS {ios_version}")
    if ports:
        summary_parts.append(f"{len(connected)}/{len(ports)} ports up")
    if err_disabled:
        summary_parts.append(f"{len(err_disabled)} err-disabled")
    if uptime:
        summary_parts.append(uptime)

    summary = (
        f"{device.name.upper()}: {' | '.join(summary_parts)}."
        if summary_parts
        else f"{device.name.upper()}: facts collected."
    )

    return JobResult(
        success=success,
        device=device.name,
        intent="device_facts",
        command_executed=", ".join(COMMANDS.values()),
        parsed_data=facts,
        raw_output=summary + (f"\nErrors: {'; '.join(errors)}" if errors else ""),
        error="; ".join(errors) if errors else None,
    )
