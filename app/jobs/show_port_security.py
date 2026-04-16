"""Job: show port-security status and violation counts."""

from __future__ import annotations

from app.logger import get_logger
from app.models import Device, JobResult
from app.parsers import parse_show_port_security
from app.ssh_client import run_command

logger = get_logger(__name__)

COMMAND = "show port-security"


def run(device: Device) -> JobResult:
    """
    Run 'show port-security' and return per-interface security state.

    Each entry includes: interface, max_mac, current_mac, violations, action.
    Violation action values: Protect / Restrict / Shutdown.
    A Shutdown action combined with violations > 0 indicates the port
    may be in err-disabled state.
    """
    try:
        raw    = run_command(device, COMMAND)
        parsed = parse_show_port_security(raw)

        violated = [p for p in parsed if p.get("violations", 0) > 0]
        shutdown  = [p for p in parsed if p.get("action", "").lower() == "shutdown"]

        if not parsed:
            display = f"No port-security configured on {device.name}."
        elif violated:
            v_ports = ", ".join(
                f"{p['interface']}({p['violations']} viol)" for p in violated[:5]
            )
            display = (
                f"Port-security on {device.name}: {len(parsed)} secured port(s), "
                f"{len(violated)} with violations — {v_ports}"
            )
        else:
            display = (
                f"Port-security on {device.name}: {len(parsed)} secured port(s), "
                f"{len(shutdown)} with Shutdown action, 0 violations."
            )

        return JobResult(
            success=True,
            device=device.name,
            intent="show_port_security",
            command_executed=COMMAND,
            parsed_data=parsed,
            raw_output=display,
        )

    except Exception as exc:
        logger.error(f"show_port_security failed on {device.name}: {exc}")
        return JobResult(
            success=False,
            device=device.name,
            intent="show_port_security",
            command_executed=COMMAND,
            error=str(exc),
        )
