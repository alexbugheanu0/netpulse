"""
SSH client for NetPulse — thin wrapper around Netmiko.

Credentials come from environment variables only (see config.py).
Callers pass pre-approved command strings — no raw user input is
forwarded to the device.

Only fixed read commands against enrolled inventory devices are permitted.
Configuration-mode execution is retained as a rejecting compatibility stub.

TODO (OpenClaw integration): Add an optional session_log path parameter
so OpenClaw can capture and analyse the full CLI session transcript.
"""

from __future__ import annotations

from netmiko import ConnectHandler
from netmiko.exceptions import (
    NetmikoAuthenticationException,
    NetmikoTimeoutException,
)

from app.access_policy import require_read_command
from app.config import SSH_PASSWORD, SSH_PORT, SSH_SECRET, SSH_TIMEOUT, SSH_USERNAME
from app.inventory import load_inventory
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
    if SSH_SECRET:
        raise EnvironmentError(
            "NETPULSE_SECRET must be unset: NetPulse is configured for read-only device access."
        )
    params: dict = {
        "device_type": device.platform,
        "host":        device.ip,
        "username":    SSH_USERNAME,
        "password":    SSH_PASSWORD,
        "port":        SSH_PORT,
        # TCP connect timeout only — reachable devices connect in < 2s.
        # read_timeout is passed per-command in send_command() to keep
        # the full SSH_TIMEOUT budget for slow 'show' output.
        "timeout":     min(SSH_TIMEOUT, 8),
        # Disables Netmiko's inter-command safety delays; saves 1-2s per
        # connection on Cisco IOS/IOS-XE without affecting output correctness.
        "fast_cli":    True,
    }
    return params


def _require_enrolled_device(device: Device) -> None:
    """Allow connections only to the enabled inventory record being targeted."""

    enrolled = load_inventory().get(device.name)
    if not enrolled or not enrolled.ssh_enabled:
        raise PermissionError(
            f"Device '{device.name}' is not an SSH-enabled enrolled switch."
        )
    if enrolled.ip != device.ip:
        raise PermissionError(
            f"Device '{device.name}' does not match its enrolled inventory address."
        )


def run_command(device: Device, command: str) -> str:
    """
    Open an SSH session to device, run a single pre-approved command,
    and return the raw output string.

    Raises:
        EnvironmentError:                  SSH credentials not set in .env
        NetmikoAuthenticationException:    bad username/password
        NetmikoTimeoutException:           device unreachable or too slow
        Exception:                         any other Netmiko or network error
    """
    _require_enrolled_device(device)
    require_read_command(command)
    logger.info(f"SSH → {device.name} ({device.ip}) | read command: {command!r}")

    try:
        with ConnectHandler(**_connection_params(device)) as conn:
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


def run_commands(device: Device, commands: list[str]) -> dict[str, str]:
    """
    Open a single SSH session and run multiple show commands in sequence.

    Returns {command: raw_output} for every command in the list.  Compared
    to calling run_command() N times, this saves N-1 TCP handshakes + SSH
    login sequences against the same device — the dominant source of latency
    for multi-command jobs like health_check and device_facts.

    Raises the same exceptions as run_command() if the session cannot be
    established.  Individual command failures are not caught here; callers
    that need per-command resilience should catch exceptions around this call
    and fall back to run_command() individually.
    """
    _require_enrolled_device(device)
    for command in commands:
        require_read_command(command)
    logger.info(
        f"SSH → {device.name} ({device.ip}) | "
        f"{len(commands)} command(s) in one session: {commands}"
    )

    try:
        with ConnectHandler(**_connection_params(device)) as conn:
            outputs: dict[str, str] = {}
            for cmd in commands:
                outputs[cmd] = conn.send_command(cmd, read_timeout=SSH_TIMEOUT)
                logger.debug(
                    f"Response from {device.name} [{cmd!r}]: "
                    f"{len(outputs[cmd])} chars"
                )
            return outputs

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

    This entry point exists for compatibility with legacy jobs only. Read-only
    mode rejects it before any connection is opened.
    """
    raise PermissionError(
        "Device configuration commands are blocked: NetPulse is read-only."
    )
