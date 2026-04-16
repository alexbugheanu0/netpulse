"""Job: show vlan brief."""

from __future__ import annotations

from app.logger import get_logger
from app.models import Device, JobResult
from app.parsers import parse_show_vlans
from app.ssh_client import run_command

logger = get_logger(__name__)

COMMAND = "show vlan brief"


def run(device: Device) -> JobResult:
    """Run 'show vlan brief' and return raw output with parsed VLAN list."""
    try:
        raw = run_command(device, COMMAND)
        parsed = parse_show_vlans(raw)
        return JobResult(
            success=True,
            device=device.name,
            intent="show_vlans",
            command_executed=COMMAND,
            parsed_data=parsed,
            raw_output=raw,
        )
    except Exception as exc:
        logger.error(f"show_vlans failed on {device.name}: {exc}")
        return JobResult(
            success=False,
            device=device.name,
            intent="show_vlans",
            command_executed=COMMAND,
            error=str(exc),
        )
