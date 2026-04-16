"""
SSH client for NetPulse — thin wrapper around Netmiko.

Credentials come from environment variables only (see config.py).
Callers pass pre-approved command strings — no raw user input is
forwarded to the device.

Two entry points:
  run_command()         — exec-mode: runs a single show command (read-only)
  run_config_commands() — config-mode: applies a list of config lines via
                          send_config_set() (write operations)

TODO (OpenClaw integration): Add an optional session_log path parameter
so OpenClaw can capture and analyse the full CLI session transcript.
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


def _connection_params(device: Device) -> dict:
    """Build the Netmiko ConnectHandler kwargs for a device."""
    if not SSH_USERNAME or not SSH_PASSWORD:
        raise EnvironmentError(
            "SSH credentials are not set. "
            "Define NETPULSE_USERNAME and NETPULSE_PASSWORD in your .env file."
        )
    params: dict = {
        "device_type": device.platform,
        "host":        device.ip,
        "username":    SSH_USERNAME,
        "password":    SSH_PASSWORD,
        "port":        SSH_PORT,
        "timeout":     SSH_TIMEOUT,
    }
    if SSH_SECRET:
        params["secret"] = SSH_SECRET
    return params


def run_command(device: Device, command: str) -> str:
    """
    Open an SSH session to device, run a single pre-approved command,
    and return the raw output string.

    Raises:
        EnvironmentError:                  SSH credentials not set in .env
        NetmikoAuthenticationException:    bad username/password/enable secret
        NetmikoTimeoutException:           device unreachable or too slow
        Exception:                         any other Netmiko or network error
    """
    logger.info(f"SSH → {device.name} ({device.ip}) | command: {command!r}")

    try:
        with ConnectHandler(**_connection_params(device)) as conn:
            if SSH_SECRET:
                conn.enable()
            output: str = conn.send_command(command, read_timeout=SSH_TIMEOUT)
            logger.debug(f"Response from {device.name}: {len(output)} chars")
            return output

    except NetmikoAuthenticationException as exc:
        logger.error(f"Auth failed on {device.name} ({device.ip}): {exc}")
        raise

    except NetmikoTimeoutException as exc:
        logger.error(f"Timeout on {device.name} ({device.ip}): {exc}")
        raise

    except Exception as exc:
        logger.error(f"SSH error on {device.name} ({device.ip}): {exc}")
        raise


def run_config_commands(device: Device, commands: list[str]) -> str:
    """
    Open an SSH session to device, enter global config mode, apply the given
    list of config lines via send_config_set(), and return the raw output.

    The enable secret (SSH_SECRET) is required for config mode — if it is not
    set the device will likely reject the config-mode entry attempt.

    Callers must pass only pre-approved, hardcoded command lists — no raw
    user input should ever reach this function directly.

    Raises:
        EnvironmentError:                  SSH credentials not set in .env
        NetmikoAuthenticationException:    bad username/password/enable secret
        NetmikoTimeoutException:           device unreachable or too slow
        Exception:                         any other Netmiko or network error
    """
    logger.info(
        f"SSH config → {device.name} ({device.ip}) | "
        f"{len(commands)} command(s): {commands}"
    )

    try:
        with ConnectHandler(**_connection_params(device)) as conn:
            if SSH_SECRET:
                conn.enable()
            output: str = conn.send_config_set(commands)
            logger.debug(
                f"Config response from {device.name}: {len(output)} chars"
            )
            return output

    except NetmikoAuthenticationException as exc:
        logger.error(f"Auth failed on {device.name} ({device.ip}): {exc}")
        raise

    except NetmikoTimeoutException as exc:
        logger.error(f"Timeout on {device.name} ({device.ip}): {exc}")
        raise

    except Exception as exc:
        logger.error(f"SSH config error on {device.name} ({device.ip}): {exc}")
        raise
