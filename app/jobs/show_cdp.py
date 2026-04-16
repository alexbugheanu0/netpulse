"""Job: show CDP neighbours."""

from __future__ import annotations

from app.logger import get_logger
from app.models import Device, JobResult
from app.parsers import parse_show_cdp_neighbors
from app.ssh_client import run_command

logger = get_logger(__name__)

COMMAND = "show cdp neighbors detail"


def run(device: Device) -> JobResult:
    """
    Run 'show cdp neighbors detail' and return a parsed neighbour list.

    Each neighbour includes device_id, IP, platform, local port, and remote port.
    Requires CDP to be enabled on the device and its neighbours.
    """
    try:
        raw    = run_command(device, COMMAND)
        parsed = parse_show_cdp_neighbors(raw)

        if parsed:
            lines = [f"CDP neighbours on {device.name} ({len(parsed)} found):"]
            for n in parsed:
                lines.append(
                    f"  {n.get('device_id', '?'):30s} "
                    f"IP={n.get('ip', '?'):16s} "
                    f"local={n.get('local_port', '?')} → "
                    f"remote={n.get('remote_port', '?')}"
                )
            display = "\n".join(lines)
        else:
            display = f"No CDP neighbours found on {device.name}."

        return JobResult(
            success=True,
            device=device.name,
            intent="show_cdp",
            command_executed=COMMAND,
            parsed_data=parsed,
            raw_output=display,
        )

    except Exception as exc:
        logger.error(f"show_cdp failed on {device.name}: {exc}")
        return JobResult(
            success=False,
            device=device.name,
            intent="show_cdp",
            command_executed=COMMAND,
            error=str(exc),
        )
