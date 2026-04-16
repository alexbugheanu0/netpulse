"""Job: show recent syslog entries."""

from __future__ import annotations

from app.logger import get_logger
from app.models import Device, JobResult
from app.parsers import parse_show_logging
from app.ssh_client import run_command

logger = get_logger(__name__)

COMMAND = "show logging"

# Severity codes 0-3 (emergency through error) are operator-actionable
_CRITICAL_SEVERITY = 3


def run(device: Device) -> JobResult:
    """
    Run 'show logging' and return the 20 most recent syslog entries.

    Each entry includes: timestamp, facility, severity_code (0=emerg … 7=debug),
    mnemonic, and message.

    Severity codes to flag:
      0 emergency, 1 alert, 2 critical, 3 error — these need attention.
      4 warning, 5 notice, 6 informational, 7 debug — routine or verbose.
    """
    try:
        raw    = run_command(device, COMMAND)
        parsed = parse_show_logging(raw)

        critical = [
            e for e in parsed
            if e.get("severity_code", 7) <= _CRITICAL_SEVERITY
        ]

        if not parsed:
            display = f"No syslog entries found on {device.name} (logging buffer may be empty)."
        elif critical:
            recent = critical[-1]
            display = (
                f"Logs on {device.name}: {len(parsed)} recent entries, "
                f"{len(critical)} severity≤ERROR — "
                f"last: {recent['facility']}-{recent['severity_code']}-{recent['mnemonic']}: "
                f"{recent['message'][:80]}"
            )
        else:
            recent = parsed[-1]
            display = (
                f"Logs on {device.name}: {len(parsed)} recent entries, "
                f"no errors/criticals — "
                f"last: {recent['facility']}-{recent['severity_code']}-{recent['mnemonic']}: "
                f"{recent['message'][:80]}"
            )

        return JobResult(
            success=True,
            device=device.name,
            intent="show_logging",
            command_executed=COMMAND,
            parsed_data=parsed,
            raw_output=display,
        )

    except Exception as exc:
        logger.error(f"show_logging failed on {device.name}: {exc}")
        return JobResult(
            success=False,
            device=device.name,
            intent="show_logging",
            command_executed=COMMAND,
            error=str(exc),
        )
