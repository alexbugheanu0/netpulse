"""Job: show interfaces trunk."""

from __future__ import annotations

from app.logger import get_logger
from app.models import Device, JobResult
from app.ssh_client import run_command

logger = get_logger(__name__)

COMMAND = "show interfaces trunk"


def run(device: Device) -> JobResult:
    """
    Run 'show interfaces trunk' on a device.
    Returns raw output — trunk table formatting is self-explanatory.
    """
    try:
        raw = run_command(device, COMMAND)
        return JobResult(
            success=True,
            device=device.name,
            intent="show_trunks",
            command_executed=COMMAND,
            raw_output=raw,
        )
    except Exception as exc:
        logger.error(f"show_trunks failed on {device.name}: {exc}")
        return JobResult(
            success=False,
            device=device.name,
            intent="show_trunks",
            command_executed=COMMAND,
            error=str(exc),
        )
