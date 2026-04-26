"""Shared helpers for multi-command SSH collection jobs."""

from __future__ import annotations

from typing import Any, Callable

from app.logger import get_logger
from app.models import Device
from app.ssh_client import run_command, run_commands

logger = get_logger(__name__)


def collect_with_fallback(
    device: Device,
    commands: dict[str, str],
    parsers: dict[str, Callable[[str], Any]],
    job_name: str,
) -> tuple[dict[str, Any], list[str]]:
    """
    Run a batch of commands in one session and fall back to per-command calls.

    Returns (collected, errors), where collected maps the logical command key
    to parsed data and errors is a list of human-readable parse/transport issues.
    """
    collected: dict[str, Any] = {}
    errors: list[str] = []

    try:
        outputs = run_commands(device, list(commands.values()))
        for key, command in commands.items():
            try:
                collected[key] = parsers[key](outputs[command])
                logger.info(f"{job_name} [{key}] OK on {device.name}")
            except Exception as exc:
                logger.warning(f"{job_name} [{key}] parse FAILED on {device.name}: {exc}")
                errors.append(f"{key}: {exc}")
    except Exception as session_exc:
        logger.warning(
            f"Batch SSH session failed on {device.name} ({session_exc}), "
            "falling back to per-command calls"
        )
        for key, command in commands.items():
            try:
                raw = run_command(device, command)
                collected[key] = parsers[key](raw)
                logger.info(f"{job_name} [{key}] OK on {device.name} (fallback)")
            except Exception as exc:
                logger.warning(f"{job_name} [{key}] FAILED on {device.name}: {exc}")
                errors.append(f"{key}: {exc}")

    return collected, errors
