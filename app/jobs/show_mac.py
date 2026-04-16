"""Job: show MAC address table."""

from __future__ import annotations

from app.logger import get_logger
from app.models import Device, JobResult
from app.parsers import parse_show_mac_table
from app.ssh_client import run_command

logger = get_logger(__name__)

COMMAND = "show mac address-table"


def run(device: Device) -> JobResult:
    """
    Run 'show mac address-table' and return a parsed MAC entry list.

    Note: some IOS versions use 'show mac-address-table' (with hyphen).
    Update COMMAND above if the output is empty on your platform.
    """
    try:
        raw    = run_command(device, COMMAND)
        parsed = parse_show_mac_table(raw)

        if parsed:
            lines = [f"MAC address table on {device.name} ({len(parsed)} entries):"]
            for e in parsed:
                lines.append(
                    f"  VLAN {e['vlan']:5s}  {e['mac']:20s}  {e['type']:10s}  {e['port']}"
                )
            display = "\n".join(lines)
        else:
            display = f"No MAC address table entries found on {device.name}."

        return JobResult(
            success=True,
            device=device.name,
            intent="show_mac",
            command_executed=COMMAND,
            parsed_data=parsed,
            raw_output=display,
        )

    except Exception as exc:
        logger.error(f"show_mac failed on {device.name}: {exc}")
        return JobResult(
            success=False,
            device=device.name,
            intent="show_mac",
            command_executed=COMMAND,
            error=str(exc),
        )
