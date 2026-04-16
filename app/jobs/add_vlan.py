"""Job: add a VLAN to a device (write operation — requires prior approval)."""

from __future__ import annotations

from app.logger import get_logger
from app.models import Device, JobResult
from app.ssh_client import run_config_commands

logger = get_logger(__name__)


def run(device: Device, vlan_id: int, vlan_name: str) -> JobResult:
    """
    Add a VLAN to the device.

    Executes in global config mode:
        vlan <vlan_id>
        name <vlan_name>

    This is a write operation. It must only be called after the operator
    has confirmed the action via the Telegram approval workflow.
    """
    commands = [
        f"vlan {vlan_id}",
        f"name {vlan_name}",
    ]
    command_str = " / ".join(commands)

    try:
        output = run_config_commands(device, commands)
        logger.info(f"add_vlan: VLAN {vlan_id} ({vlan_name}) added to {device.name}")

        return JobResult(
            success=True,
            device=device.name,
            intent="add_vlan",
            command_executed=command_str,
            raw_output=output,
            parsed_data={"vlan_id": vlan_id, "vlan_name": vlan_name},
        )

    except Exception as exc:
        logger.error(f"add_vlan failed on {device.name}: {exc}")
        return JobResult(
            success=False,
            device=device.name,
            intent="add_vlan",
            command_executed=command_str,
            error=str(exc),
        )
