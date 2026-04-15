"""Job: show version."""

from __future__ import annotations

from app.logger import get_logger
from app.models import Device, JobResult
from app.parsers import parse_show_version
from app.ssh_client import run_command

logger = get_logger(__name__)

COMMAND = "show version"


def run(device: Device) -> JobResult:
    """Run 'show version' on a device and parse key fields."""
    try:
        raw = run_command(device, COMMAND)
        parsed = parse_show_version(raw)
        return JobResult(
            success=True,
            device=device.name,
            intent="show_version",
            command_executed=COMMAND,
            parsed_data=parsed,
            raw_output=raw,
        )
    except Exception as exc:
        logger.error(f"show_version failed on {device.name}: {exc}")
        return JobResult(
            success=False,
            device=device.name,
            intent="show_version",
            command_executed=COMMAND,
            error=str(exc),
        )
