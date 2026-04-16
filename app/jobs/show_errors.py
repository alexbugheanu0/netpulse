"""Job: show interface error counters."""

from __future__ import annotations

from app.logger import get_logger
from app.models import Device, JobResult
from app.parsers import parse_show_interfaces_errors
from app.ssh_client import run_command

logger = get_logger(__name__)

COMMAND = "show interfaces"


def run(device: Device) -> JobResult:
    """
    Run 'show interfaces' and surface only ports with non-zero error counters.

    parsed_data contains all ports. raw_output contains only the error summary
    (or a clean message if no errors are found) — keeps display concise.
    """
    try:
        raw    = run_command(device, COMMAND)
        parsed = parse_show_interfaces_errors(raw)

        errors = [
            p for p in parsed
            if p["input_errors"] > 0 or p["output_errors"] > 0
        ]

        if errors:
            lines = [f"Ports with errors on {device.name}:"]
            for p in errors:
                lines.append(
                    f"  {p['port']:25s} "
                    f"in_err={p['input_errors']}  crc={p['crc']}  "
                    f"out_err={p['output_errors']}  resets={p['resets']}"
                )
            display = "\n".join(lines)
        else:
            display = f"No interface errors found on {device.name}."

        return JobResult(
            success=True,
            device=device.name,
            intent="show_errors",
            command_executed=COMMAND,
            parsed_data=parsed,
            raw_output=display,
        )

    except Exception as exc:
        logger.error(f"show_errors failed on {device.name}: {exc}")
        return JobResult(
            success=False,
            device=device.name,
            intent="show_errors",
            command_executed=COMMAND,
            error=str(exc),
        )
