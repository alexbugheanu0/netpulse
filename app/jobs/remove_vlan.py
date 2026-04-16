"""Job: remove a VLAN from a device (write operation — requires prior approval)."""

from __future__ import annotations

from app.logger import get_logger
from app.models import Device, JobResult
from app.ssh_client import run_config_commands

logger = get_logger(__name__)


def run(device: Device, vlan_id: int) -> JobResult:
    """
    Remove a VLAN from the device.

    Executes in global config mode:
        no vlan <vlan_id>

    This is a write operation. It must only be called after the operator
    has confirmed the action via the Telegram approval workflow.
    """
    commands = [f"no vlan {vlan_id}"]
    command_str = commands[0]

    try:
        output = run_config_commands(device, commands)
        logger.info(f"remove_vlan: VLAN {vlan_id} removed from {device.name}")

        return JobResult(
            success=True,
            device=device.name,
            intent="remove_vlan",
            command_executed=command_str,
            raw_output=output,
            parsed_data={"vlan_id": vlan_id},
        )

    except Exception as exc:
        logger.error(f"remove_vlan failed on {device.name}: {exc}")
        return JobResult(
            success=False,
            device=device.name,
            intent="remove_vlan",
            command_executed=command_str,
            error=str(exc),
        )
