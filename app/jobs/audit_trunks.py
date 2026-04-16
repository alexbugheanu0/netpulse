"""
Job: audit trunk allowed-VLAN configuration against the SSOT baseline.

Execution flow:
  1. Run 'show interfaces trunk' via the existing show_trunks job.
  2. Parse the raw output for per-port allowed VLAN lists.
  3. Load the expected trunk profile from ssot/trunks.yaml for this device's role.
  4. Call audit.compare_trunks() for pure-Python comparison.
  5. Return a JobResult whose parsed_data is the serialised AuditResult dict.
"""

from __future__ import annotations

from app.audit import compare_trunks
from app.logger import get_logger
from app.models import Device, JobResult
from app.parsers import parse_show_trunks_allowed
from app.ssot import get_expected_trunk_profile, load_trunk_ssot

from app.jobs import show_trunks

logger = get_logger(__name__)


def run(device: Device) -> JobResult:
    """Compare actual trunk allowed VLANs against ssot/trunks.yaml baseline."""

    # Step 1 — collect raw trunk output (reuses show_trunks job for SSH)
    trunk_result = show_trunks.run(device)
    if not trunk_result.success:
        return JobResult(
            success=False,
            device=device.name,
            intent="audit_trunks",
            command_executed="show interfaces trunk",
            error=f"Failed to collect trunk data: {trunk_result.error}",
        )

    # Step 2 — parse the "Vlans allowed on trunk" section from raw output
    actual_ports = parse_show_trunks_allowed(trunk_result.raw_output)

    # Step 3 — load SSOT
    ssot    = load_trunk_ssot()
    profile = get_expected_trunk_profile(device.name, device.role, ssot)
    expected_allowed: list[int] = profile.get("allowed_vlans", [])

    # Step 4 — compare
    audit = compare_trunks(device.name, expected_allowed, actual_ports)

    logger.info(
        f"audit_trunks {device.name}: status={audit.status.upper()}, "
        f"ports={len(actual_ports)}, findings={len(audit.findings)}"
    )

    return JobResult(
        success=True,
        device=device.name,
        intent="audit_trunks",
        command_executed="show interfaces trunk",
        parsed_data=audit.model_dump(),
        raw_output=_format_text(audit),
    )


def _format_text(audit) -> str:
    """Human-readable text block for CLI display."""
    lines = [
        f"Trunk Audit — {audit.device.upper()}",
        f"Status : {audit.status.upper()}",
        f"Summary: {audit.summary}",
    ]
    if audit.findings:
        lines.append("\nFindings:")
        for f in audit.findings:
            tag = f"  [{f.status.upper():9}]"
            lines.append(f"{tag} {f.message}")
    if audit.next_action and audit.status != "compliant":
        lines.append(f"\nNext action: {audit.next_action}")
    return "\n".join(lines)
