"""Job: backup running-config to a local file."""

from __future__ import annotations

from datetime import datetime

from app.config import BACKUP_DIR
from app.logger import get_logger
from app.models import Device, JobResult

from app.ssh_client import run_command

logger = get_logger(__name__)

COMMAND = "show running-config"


def run(device: Device) -> JobResult:
    """
    Retrieve the running config from a device and write it to output/backups/.

    Backup filename format: <device-name>_YYYYMMDD_HHMMSS.cfg
    Example: sw-core-01_20260415_143022.cfg
    """
    try:
        raw = run_command(device, COMMAND)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename  = f"{device.name}_{timestamp}.cfg"
        filepath  = BACKUP_DIR / filename
        filepath.write_text(raw, encoding="utf-8")

        logger.info(f"Config backup saved: {filepath}")

        return JobResult(
            success=True,
            device=device.name,
            intent="backup_config",
            command_executed=COMMAND,
            raw_output=f"Saved to: {filepath}",
            parsed_data={"backup_file": str(filepath)},
        )

    except Exception as exc:
        logger.error(f"backup_config failed on {device.name}: {exc}")
        return JobResult(
            success=False,
            device=device.name,
            intent="backup_config",
            command_executed=COMMAND,
            error=str(exc),
        )
