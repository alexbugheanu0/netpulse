"""
Output parsers for raw Cisco CLI output.

v1 uses simple line-by-line parsing. Each function returns either a list
of dicts or a single dict that can be used for display or further processing.

To upgrade to TextFSM/ntc-templates:
    from ntc_templates.parse import parse_output
    parsed = parse_output(platform="cisco_ios", command="show vlan brief", data=raw)

TODO (OpenClaw integration): Structured parsed_data from these functions
is the primary input for OpenClaw reasoning — keep the dict schemas stable.
"""

from __future__ import annotations

from typing import Any

from app.logger import get_logger

logger = get_logger(__name__)


def parse_show_interfaces(raw: str) -> list[dict[str, str]]:
    """
    Parse 'show interfaces status' output.
    Returns a list of dicts, one per port line.
    """
    results: list[dict[str, str]] = []
    lines = raw.splitlines()

    for line in lines:
        stripped = line.strip()
        # Skip empty lines and header lines
        if not stripped or stripped.startswith("Port"):
            continue
        parts = stripped.split()
        if len(parts) >= 3:
            results.append({
                "port":   parts[0],
                "name":   parts[1] if len(parts) > 4 else "",
                "status": parts[-4] if len(parts) > 4 else parts[1],
                "vlan":   parts[-3] if len(parts) > 4 else parts[2],
                "raw":    stripped,
            })

    return results


def parse_show_vlans(raw: str) -> list[dict[str, str]]:
    """
    Parse 'show vlan brief' output.
    Returns a list of dicts with vlan_id, name, status.
    """
    results: list[dict[str, str]] = []
    for line in raw.splitlines():
        parts = line.split()
        if parts and parts[0].isdigit():
            results.append({
                "vlan_id": parts[0],
                "name":    parts[1] if len(parts) > 1 else "",
                "status":  parts[2] if len(parts) > 2 else "",
            })
    return results


def parse_show_version(raw: str) -> dict[str, str]:
    """
    Parse key fields from 'show version' output.
    Returns a dict with software, uptime, and hardware keys where found.
    """
    result: dict[str, Any] = {}
    for line in raw.splitlines():
        lower = line.lower()
        if "cisco ios" in lower or "ios-xe" in lower:
            result.setdefault("software", line.strip())
        if "uptime is" in lower:
            result.setdefault("uptime", line.strip())
        if "cisco" in lower and "processor" in lower:
            result.setdefault("hardware", line.strip())
        if "serial number" in lower or "processor id" in lower:
            result.setdefault("serial", line.strip())
    return result


def parse_raw(raw: str) -> str:
    """Fallback: return raw output unchanged."""
    return raw
