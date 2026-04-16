"""Job: ping a target IP from a device."""

from __future__ import annotations

from app.logger import get_logger
from app.models import Device, JobResult
from app.parsers import parse_ping
from app.ssh_client import run_command

logger = get_logger(__name__)

COMMAND_TEMPLATE = "ping {target} repeat 5"


def run(device: Device, target: str) -> JobResult:
    """
    Send 5 ICMP pings from device to target and return the result.

    parsed_data keys: success_rate, sent, received, min_ms, avg_ms, max_ms.
    Job is marked failed if success_rate is 0%.
    """
    command = COMMAND_TEMPLATE.format(target=target)

    try:
        raw    = run_command(device, command)
        parsed = parse_ping(raw)

        rate = int(parsed.get("success_rate", "0"))
        if rate == 100:
            rtt = f"  rtt min/avg/max = {parsed['min_ms']}/{parsed['avg_ms']}/{parsed['max_ms']} ms"
            display = f"ping {target} from {device.name}: {parsed['received']}/{parsed['sent']} OK (100%){rtt}"
        elif rate > 0:
            display = (
                f"ping {target} from {device.name}: "
                f"{parsed['received']}/{parsed['sent']} ({rate}%) — partial loss"
            )
        else:
            display = f"ping {target} from {device.name}: 0/{parsed.get('sent', '?')} — 100% loss"

        return JobResult(
            success=rate > 0,
            device=device.name,
            intent="ping",
            command_executed=command,
            parsed_data=parsed,
            raw_output=display,
        )

    except Exception as exc:
        logger.error(f"ping failed on {device.name}: {exc}")
        return JobResult(
            success=False,
            device=device.name,
            intent="ping",
            command_executed=command,
            error=str(exc),
        )
