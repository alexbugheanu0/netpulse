"""
Job: health check — runs version, interface status, and VLAN queries in one pass.

TODO (OpenClaw integration): Feed parsed_data from this job into OpenClaw to
generate a natural language health summary or flag anomalies automatically.
"""

from __future__ import annotations

from app.logger import get_logger
from app.models import Device, JobResult
from app.parsers import parse_show_interfaces, parse_show_version, parse_show_vlans
from app.ssh_client import run_command

logger = get_logger(__name__)

# Commands run for every health check. Add entries here to extend the check set.
HEALTH_COMMANDS: dict[str, str] = {
    "version":    "show version",
    "interfaces": "show interfaces status",
    "vlans":      "show vlan brief",
}

PARSERS = {
    "version":    parse_show_version,
    "interfaces": parse_show_interfaces,
    "vlans":      parse_show_vlans,
}


def run(device: Device) -> JobResult:
    """
    Run a multi-command health check against a single device.

    Each command is attempted independently — partial failures are captured
    in the error field. The job succeeds only if all commands complete cleanly.
    """
    collected: dict = {}
    errors: list[str] = []

    for key, command in HEALTH_COMMANDS.items():
        try:
            raw = run_command(device, command)
            collected[key] = PARSERS[key](raw)
            logger.info(f"Health [{key}] OK on {device.name}")
        except Exception as exc:
            logger.warning(f"Health [{key}] FAILED on {device.name}: {exc}")
            errors.append(f"{key}: {exc}")

    success = len(errors) == 0

    summary_lines = [f"Health check — {device.name}"]
    for key, val in collected.items():
        preview = str(val)[:120]
        summary_lines.append(f"  [{key}] {preview}")
    if errors:
        summary_lines.append(f"  [errors] {'; '.join(errors)}")

    return JobResult(
        success=success,
        device=device.name,
        intent="health_check",
        command_executed=", ".join(HEALTH_COMMANDS.values()),
        parsed_data=collected,
        raw_output="\n".join(summary_lines),
        error="; ".join(errors) if errors else None,
    )
