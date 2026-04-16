"""Job: bring up an interface (write operation — requires prior approval)."""

from __future__ import annotations

from app.logger import get_logger
from app.models import Device, JobResult
from app.ssh_client import run_config_commands

logger = get_logger(__name__)


def run(device: Device, interface: str) -> JobResult:
    """
    Remove the administrative shutdown from an interface.

    Executes in global config mode:
        interface <interface>
        no shutdown

    This is a write operation. It must only be called after the operator
    has confirmed the action via the Telegram approval workflow.
    """
    commands = [
        f"interface {interface}",
        "no shutdown",
    ]
    command_str = " / ".join(commands)

    try:
        output = run_config_commands(device, commands)
        logger.info(
            f"no_shutdown_interface: {interface} brought up on {device.name}"
        )

        return JobResult(
            success=True,
            device=device.name,
            intent="no_shutdown_interface",
            command_executed=command_str,
            raw_output=output,
            parsed_data={"interface": interface, "state": "no shutdown"},
        )

    except Exception as exc:
        logger.error(f"no_shutdown_interface failed on {device.name}: {exc}")
        return JobResult(
            success=False,
            device=device.name,
            intent="no_shutdown_interface",
            command_executed=command_str,
            error=str(exc),
        )
