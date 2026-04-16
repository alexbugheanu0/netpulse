"""
Job: audit VLAN configuration against the SSOT baseline.

Execution flow:
  1. Run 'show vlan brief' via the existing show_vlans job (reuses SSH + parser).
  2. Load the expected VLAN list from ssot/vlans.yaml for this device's role.
  3. Call audit.compare_vlans() for pure-Python comparison.
  4. Return a JobResult whose parsed_data is the serialised AuditResult dict.
"""

from __future__ import annotations

from app.audit import compare_vlans
from app.logger import get_logger
from app.models import Device, JobResult
from app.ssot import get_expected_vlans, load_vlan_ssot

from app.jobs import show_vlans

logger = get_logger(__name__)


def run(device: Device) -> JobResult:
    """Compare actual VLANs on the device against ssot/vlans.yaml baseline."""

    # Step 1 — collect actual VLANs (reuses show_vlans job and its parser)
    vlan_result = show_vlans.run(device)
    if not vlan_result.success:
        return JobResult(
            success=False,
            device=device.name,
            intent="audit_vlans",
            command_executed="show vlan brief",
            error=f"Failed to collect VLANs: {vlan_result.error}",
        )

    # Step 2 — load SSOT (cached per call; file I/O is fast)
    ssot     = load_vlan_ssot()
    expected = get_expected_vlans(device.name, device.role, ssot)

    # Step 3 — compare
    actual = vlan_result.parsed_data or []
    audit  = compare_vlans(device.name, expected, actual)

    logger.info(
        f"audit_vlans {device.name}: status={audit.status.upper()}, "
        f"findings={len(audit.findings)}"
    )

    return JobResult(
        success=True,
        device=device.name,
        intent="audit_vlans",
        command_executed="show vlan brief",
        parsed_data=audit.model_dump(),
        raw_output=_format_text(audit),
    )


def _format_text(audit) -> str:
    """Human-readable text block for CLI display."""
    lines = [
        f"VLAN Audit — {audit.device.upper()}",
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
