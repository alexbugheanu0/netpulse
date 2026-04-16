"""Job: set access VLAN on an interface (write operation — requires prior approval)."""

from __future__ import annotations

from app.logger import get_logger
from app.models import Device, JobResult
from app.ssh_client import run_config_commands

logger = get_logger(__name__)


def run(device: Device, interface: str, vlan_id: int) -> JobResult:
    """
    Set the access VLAN on an interface.

    Executes in global config mode:
        interface <interface>
        switchport mode access
        switchport access vlan <vlan_id>

    This is a write operation. It must only be called after the operator
    has confirmed the action via the Telegram approval workflow.
    """
    commands = [
        f"interface {interface}",
        "switchport mode access",
        f"switchport access vlan {vlan_id}",
    ]
    command_str = " / ".join(commands)

    try:
        output = run_config_commands(device, commands)
        logger.info(
            f"set_interface_vlan: {interface} set to VLAN {vlan_id} on {device.name}"
        )

        return JobResult(
            success=True,
            device=device.name,
            intent="set_interface_vlan",
            command_executed=command_str,
            raw_output=output,
            parsed_data={"interface": interface, "vlan_id": vlan_id},
        )

    except Exception as exc:
        logger.error(f"set_interface_vlan failed on {device.name}: {exc}")
        return JobResult(
            success=False,
            device=device.name,
            intent="set_interface_vlan",
            command_executed=command_str,
            error=str(exc),
        )
