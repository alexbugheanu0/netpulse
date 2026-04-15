"""
SSH client for NetPulse — thin wrapper around Netmiko.

Reads credentials from environment variables only.
Never accepts raw CLI from user input — callers pass pre-approved commands.

TODO (OpenClaw integration): Add optional session_log path parameter so
OpenClaw can capture and analyse raw session transcripts.
"""

from __future__ import annotations

from netmiko import ConnectHandler
from netmiko.exceptions import (
    NetmikoAuthenticationException,
    NetmikoTimeoutException,
)

from app.config import SSH_PASSWORD, SSH_PORT, SSH_SECRET, SSH_TIMEOUT, SSH_USERNAME
from app.logger import get_logger
from app.models import Device

logger = get_logger(__name__)


def run_command(device: Device, command: str) -> str:
    """
    Open an SSH session to device, run a single pre-approved command,
    and return the raw output string.

    Raises:
        EnvironmentError: SSH credentials not configured in .env
        NetmikoAuthenticationException: bad username/password/enable secret
        NetmikoTimeoutException: device unreachable or slow to respond
        Exception: any other Netmiko or network error
    """
    if not SSH_USERNAME or not SSH_PASSWORD:
        raise EnvironmentError(
            "SSH credentials are not set. "
            "Define NETPULSE_USERNAME and NETPULSE_PASSWORD in your .env file."
        )

    connection_params: dict = {
        "device_type": device.platform,
        "host": device.ip,
        "username": SSH_USERNAME,
        "password": SSH_PASSWORD,
        "port": SSH_PORT,
        "timeout": SSH_TIMEOUT,
        "session_log": None,
    }

    if SSH_SECRET:
        connection_params["secret"] = SSH_SECRET

    logger.info(f"SSH → {device.name} ({device.ip}) | command: {command!r}")

    try:
        with ConnectHandler(**connection_params) as conn:
            if SSH_SECRET:
                conn.enable()
            output: str = conn.send_command(command, read_timeout=SSH_TIMEOUT)
            logger.debug(f"Response from {device.name} ({len(output)} chars)")
            return output

    except NetmikoAuthenticationException as exc:
        logger.error(f"Auth failed on {device.name}: {exc}")
        raise

    except NetmikoTimeoutException as exc:
        logger.error(f"Timeout connecting to {device.name} ({device.ip}): {exc}")
        raise

    except Exception as exc:
        logger.error(f"SSH error on {device.name}: {exc}")
        raise
