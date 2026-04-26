"""Job: show interfaces trunk."""

from __future__ import annotations

from app.logger import get_logger
from app.models import Device, JobResult
from app.ssh_client import run_command
from app.jobs._job_cache import get_job_result, store_job_result

logger = get_logger(__name__)

COMMAND = "show interfaces trunk"


def run(device: Device) -> JobResult:
    """
    Run 'show interfaces trunk' and return the raw output.

    The trunk table is self-explanatory in raw form — no structured parser needed.
    """
    cache_key = ("show_trunks", device.name)
    cached = get_job_result(cache_key)
    if cached is not None:
        return cached

    try:
        raw = run_command(device, COMMAND)
        result = JobResult(
            success=True,
            device=device.name,
            intent="show_trunks",
            command_executed=COMMAND,
            raw_output=raw,
        )
        store_job_result(cache_key, result)
        return result
    except Exception as exc:
        logger.error(f"show_trunks failed on {device.name}: {exc}")
        return JobResult(
            success=False,
            device=device.name,
            intent="show_trunks",
            command_executed=COMMAND,
            error=str(exc),
        )
