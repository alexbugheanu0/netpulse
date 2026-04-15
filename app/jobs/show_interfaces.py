"""Job: show interfaces status."""

from __future__ import annotations

from app.logger import get_logger
from app.models import Device, JobResult
from app.parsers import parse_show_interfaces
from app.ssh_client import run_command

logger = get_logger(__name__)

COMMAND = "show interfaces status"


def run(device: Device) -> JobResult:
    """Run 'show interfaces status' on a device and return parsed results."""
    try:
        raw = run_command(device, COMMAND)
        parsed = parse_show_interfaces(raw)
        return JobResult(
            success=True,
            device=device.name,
            intent="show_interfaces",
            command_executed=COMMAND,
            parsed_data=parsed,
            raw_output=raw,
        )
    except Exception as exc:
        logger.error(f"show_interfaces failed on {device.name}: {exc}")
        return JobResult(
            success=False,
            device=device.name,
            intent="show_interfaces",
            command_executed=COMMAND,
            error=str(exc),
        )
