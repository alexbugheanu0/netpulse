"""Job: show interfaces status."""

from __future__ import annotations

from app.logger import get_logger
from app.models import Device, JobResult
from app.parsers import parse_show_interfaces
from app.ssh_client import run_command
from app.jobs._job_cache import get_job_result, store_job_result

logger = get_logger(__name__)

COMMAND = "show interfaces status"


def run(device: Device) -> JobResult:
    """Run 'show interfaces status' and return raw output with parsed port list."""
    cache_key = ("show_interfaces", device.name)
    cached = get_job_result(cache_key)
    if cached is not None:
        return cached

    try:
        raw = run_command(device, COMMAND)
        parsed = parse_show_interfaces(raw)
        result = JobResult(
            success=True,
            device=device.name,
            intent="show_interfaces",
            command_executed=COMMAND,
            parsed_data=parsed,
            raw_output=raw,
        )
        store_job_result(cache_key, result)
        return result
    except Exception as exc:
        logger.error(f"show_interfaces failed on {device.name}: {exc}")
        return JobResult(
            success=False,
            device=device.name,
            intent="show_interfaces",
            command_executed=COMMAND,
            error=str(exc),
        )
