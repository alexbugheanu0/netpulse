"""Job: diff the two most recent config backups for a device."""

from __future__ import annotations

import difflib

from app.config import BACKUP_DIR
from app.logger import get_logger
from app.models import Device, JobResult

logger = get_logger(__name__)


def run(device: Device) -> JobResult:
    """
    Compare the two most recent config backups for a device in output/backups/.

    Backups are sorted by filename (which encodes the timestamp), so the two
    files with the highest sort order are used. Reports unified diff output.

    No SSH connection is made — this job reads local files only.
    """
    backups = sorted(BACKUP_DIR.glob(f"{device.name}_*.cfg"))

    if len(backups) < 2:
        return JobResult(
            success=False,
            device=device.name,
            intent="diff_backup",
            command_executed="local file diff",
            error=(
                f"Need at least 2 backups for {device.name}, "
                f"found {len(backups)}. Run 'backup_config' first."
            ),
        )

    previous, latest = backups[-2], backups[-1]
    logger.info(f"Diffing {previous.name} → {latest.name}")

    old_lines = previous.read_text(encoding="utf-8").splitlines(keepends=True)
    new_lines = latest.read_text(encoding="utf-8").splitlines(keepends=True)

    diff = list(
        difflib.unified_diff(
            old_lines,
            new_lines,
            fromfile=previous.name,
            tofile=latest.name,
        )
    )

    if diff:
        display = "".join(diff)
        change_count = sum(1 for l in diff if l.startswith(("+", "-")) and not l.startswith(("+++", "---")))
    else:
        display      = f"No changes between {previous.name} and {latest.name}."
        change_count = 0

    return JobResult(
        success=True,
        device=device.name,
        intent="diff_backup",
        command_executed="local file diff",
        parsed_data={
            "previous":     previous.name,
            "latest":       latest.name,
            "changed_lines": change_count,
        },
        raw_output=display,
    )
