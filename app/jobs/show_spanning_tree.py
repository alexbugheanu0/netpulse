"""Job: show spanning-tree."""

from __future__ import annotations

from app.logger import get_logger
from app.models import Device, JobResult
from app.parsers import parse_show_spanning_tree
from app.ssh_client import run_command

logger = get_logger(__name__)

COMMAND = "show spanning-tree"


def run(device: Device) -> JobResult:
    """
    Run 'show spanning-tree' and return port roles and states per VLAN.

    Ports in BLK (blocking) or Altn (alternate) role are highlighted in the
    summary — these are the first things to check during a loop incident.
    """
    try:
        raw    = run_command(device, COMMAND)
        parsed = parse_show_spanning_tree(raw)

        if parsed:
            # Flag blocking/alternate ports for quick operator attention
            blocking = [p for p in parsed if p["state"] in ("BLK", "BKN")]
            lines = [f"STP on {device.name} — {len(parsed)} port/VLAN entries:"]
            if blocking:
                lines.append(f"  [!] {len(blocking)} port(s) blocking:")
                for p in blocking:
                    lines.append(
                        f"      {p['port']:20s} VLAN={p['vlan']}  "
                        f"role={p['role']}  state={p['state']}"
                    )
            for p in parsed:
                lines.append(
                    f"  {p['vlan']:8s}  {p['port']:20s}  "
                    f"role={p['role']:4s}  state={p['state']}  cost={p['cost']}"
                )
            display = "\n".join(lines)
        else:
            display = raw  # Fall back to raw output if parser finds nothing

        return JobResult(
            success=True,
            device=device.name,
            intent="show_spanning_tree",
            command_executed=COMMAND,
            parsed_data=parsed,
            raw_output=display,
        )

    except Exception as exc:
        logger.error(f"show_spanning_tree failed on {device.name}: {exc}")
        return JobResult(
            success=False,
            device=device.name,
            intent="show_spanning_tree",
            command_executed=COMMAND,
            error=str(exc),
        )
