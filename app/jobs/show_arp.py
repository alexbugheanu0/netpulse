"""Job: show ARP table."""

from __future__ import annotations

from app.logger import get_logger
from app.models import Device, JobResult
from app.parsers import parse_show_arp
from app.ssh_client import run_command

logger = get_logger(__name__)

COMMAND = "show ip arp"


def run(device: Device) -> JobResult:
    """
    Run 'show ip arp' and return a parsed ARP cache.

    Each entry includes protocol, ip, age, mac, type, and interface.
    An age of '-' indicates a locally-attached interface.
    A mac of 'Incomplete' means ARP resolution failed — useful signal
    for L2/L3 boundary troubleshooting.
    """
    try:
        raw    = run_command(device, COMMAND)
        parsed = parse_show_arp(raw)

        incomplete = [e for e in parsed if "incomplete" in e.get("mac", "").lower()]
        total = len(parsed)

        if incomplete:
            inc_ips = ", ".join(e["ip"] for e in incomplete[:5])
            display = (
                f"ARP table on {device.name}: {total} entries, "
                f"{len(incomplete)} INCOMPLETE ({inc_ips})"
            )
        else:
            display = f"ARP table on {device.name}: {total} entries, all resolved."

        return JobResult(
            success=True,
            device=device.name,
            intent="show_arp",
            command_executed=COMMAND,
            parsed_data=parsed,
            raw_output=display,
        )

    except Exception as exc:
        logger.error(f"show_arp failed on {device.name}: {exc}")
        return JobResult(
            success=False,
            device=device.name,
            intent="show_arp",
            command_executed=COMMAND,
            error=str(exc),
        )
