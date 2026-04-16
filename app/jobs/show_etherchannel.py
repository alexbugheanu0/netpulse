"""Job: show EtherChannel / LACP bundle status."""

from __future__ import annotations

from app.logger import get_logger
from app.models import Device, JobResult
from app.parsers import parse_show_etherchannel
from app.ssh_client import run_command

logger = get_logger(__name__)

COMMAND = "show etherchannel summary"

# Port flag codes that indicate a problem condition
_PROBLEM_FLAGS = {"D", "s", "H", "I", "u"}


def run(device: Device) -> JobResult:
    """
    Run 'show etherchannel summary' and return parsed bundle state.

    Each bundle includes group number, port-channel name, protocol
    (LACP/PAgP/NONE), port-channel flags, and member ports with their
    individual flag codes.

    Flag codes of interest:
      U = port-channel in use       D = member port is down
      P = bundled (in portchannel)  s = suspended (incompatible config)
      H = hot-standby (LACP)        I = stand-alone (not bundled)
    """
    try:
        raw    = run_command(device, COMMAND)
        parsed = parse_show_etherchannel(raw)

        if not parsed:
            display = f"No EtherChannel groups found on {device.name}."
        else:
            lines = [f"EtherChannel summary on {device.name}:"]
            for bundle in parsed:
                members = bundle.get("member_ports", [])
                problem = [
                    f"{m['port']}({m['flags']})"
                    for m in members
                    if any(f in m["flags"] for f in _PROBLEM_FLAGS)
                ]
                bundled = [m for m in members if "P" in m["flags"]]
                status = "DEGRADED" if problem else "OK"
                lines.append(
                    f"  Group {bundle['group']} {bundle['port_channel']} "
                    f"[{bundle['protocol']}] {status}: "
                    f"{len(bundled)}/{len(members)} members bundled"
                    + (f" — problem ports: {', '.join(problem)}" if problem else "")
                )
            display = "\n".join(lines)

        return JobResult(
            success=True,
            device=device.name,
            intent="show_etherchannel",
            command_executed=COMMAND,
            parsed_data=parsed,
            raw_output=display,
        )

    except Exception as exc:
        logger.error(f"show_etherchannel failed on {device.name}: {exc}")
        return JobResult(
            success=False,
            device=device.name,
            intent="show_etherchannel",
            command_executed=COMMAND,
            error=str(exc),
        )
