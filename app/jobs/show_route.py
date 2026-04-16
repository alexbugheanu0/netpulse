"""Job: show IP routing table."""

from __future__ import annotations

from app.logger import get_logger
from app.models import Device, JobResult
from app.parsers import parse_show_route
from app.ssh_client import run_command

logger = get_logger(__name__)

COMMAND = "show ip route"


def run(device: Device) -> JobResult:
    """
    Run 'show ip route' and return a parsed routing table.

    Each entry includes protocol, prefix, mask, admin_distance, metric,
    next_hop, interface, and age. Protocol codes follow Cisco convention:
    C=connected, S=static, O=OSPF, B=BGP, R=RIP, D=EIGRP, i=IS-IS.
    """
    try:
        raw    = run_command(device, COMMAND)
        parsed = parse_show_route(raw)

        total = len(parsed)
        has_default = any(
            r.get("prefix") == "0.0.0.0" for r in parsed
        )
        by_proto: dict[str, int] = {}
        for r in parsed:
            p = r.get("protocol", "?")
            by_proto[p] = by_proto.get(p, 0) + 1

        proto_str = ", ".join(f"{k}:{v}" for k, v in sorted(by_proto.items()))
        default_str = " | default route present" if has_default else " | NO default route"
        display = (
            f"Routing table on {device.name}: {total} routes "
            f"({proto_str}){default_str}"
        )

        return JobResult(
            success=True,
            device=device.name,
            intent="show_route",
            command_executed=COMMAND,
            parsed_data=parsed,
            raw_output=display,
        )

    except Exception as exc:
        logger.error(f"show_route failed on {device.name}: {exc}")
        return JobResult(
            success=False,
            device=device.name,
            intent="show_route",
            command_executed=COMMAND,
            error=str(exc),
        )
