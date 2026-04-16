"""
Job: combined SSOT drift check (VLAN + trunk + device role).

Runs audit_vlans and audit_trunks for the target device, adds a device-role
check from ssot/device_roles.yaml, and returns a single combined AuditResult.

Execution flow:
  1. Run audit_vlans.run(device) → AuditResult dict
  2. Run audit_trunks.run(device) → AuditResult dict
  3. Load ssot/device_roles.yaml, compare expected vs actual role
  4. Merge all findings into a combined AuditResult
  5. Return JobResult with the merged audit as parsed_data
"""

from __future__ import annotations

from app.audit import worst_status
from app.logger import get_logger
from app.models import AuditFinding, AuditResult, AuditStatus, Device, JobResult
from app.ssot import load_device_roles

from app.jobs import audit_vlans, audit_trunks

logger = get_logger(__name__)


def run(device: Device) -> JobResult:
    """Run VLAN audit + trunk audit + role check, return combined drift result."""

    # Step 1 — VLAN audit (reuses show_vlans internally)
    vlan_job  = audit_vlans.run(device)
    # Step 2 — Trunk audit (reuses show_trunks internally)
    trunk_job = audit_trunks.run(device)

    all_findings: list[AuditFinding] = []

    # Collect VLAN findings (gracefully handles SSH failure)
    vlan_data: dict = {}
    if vlan_job.success and vlan_job.parsed_data:
        vlan_data = vlan_job.parsed_data
        all_findings.extend(
            AuditFinding(**f) for f in vlan_data.get("findings", [])
        )
    elif not vlan_job.success:
        all_findings.append(AuditFinding(
            status=AuditStatus.MISMATCH,
            field="vlan_collection",
            expected=None,
            actual=None,
            message=f"VLAN collection failed: {vlan_job.error}",
        ))

    # Collect trunk findings
    trunk_data: dict = {}
    if trunk_job.success and trunk_job.parsed_data:
        trunk_data = trunk_job.parsed_data
        all_findings.extend(
            AuditFinding(**f) for f in trunk_data.get("findings", [])
        )
    elif not trunk_job.success:
        all_findings.append(AuditFinding(
            status=AuditStatus.MISMATCH,
            field="trunk_collection",
            expected=None,
            actual=None,
            message=f"Trunk collection failed: {trunk_job.error}",
        ))

    # Step 3 — device role check
    expected_roles = load_device_roles()
    expected_role  = expected_roles.get(device.name)

    role_finding: AuditFinding | None = None
    if expected_role and expected_role != device.role:
        role_finding = AuditFinding(
            status=AuditStatus.MISMATCH,
            field="device_role",
            expected=expected_role,
            actual=device.role,
            message=(
                f"Device role mismatch: expected '{expected_role}' "
                f"(ssot/device_roles.yaml), got '{device.role}' (inventory)"
            ),
        )
        all_findings.append(role_finding)

    # Step 4 — aggregate
    overall_status = worst_status(all_findings) if all_findings else AuditStatus.COMPLIANT

    # Build combined summary
    if overall_status == AuditStatus.COMPLIANT:
        summary = (
            f"{device.name.upper()}: Drift check passed — "
            f"VLANs, trunks, and role all match baseline."
        )
        next_action = "No action required."
    else:
        issue_count = len([f for f in all_findings if f.status != AuditStatus.COMPLIANT])
        summary = (
            f"{device.name.upper()}: {issue_count} drift issue(s) found. "
            f"VLAN status: {vlan_data.get('status', 'unavailable').upper()}, "
            f"Trunk status: {trunk_data.get('status', 'unavailable').upper()}."
        )
        next_action = (
            "Review individual findings above. "
            "Run audit_vlans and audit_trunks separately for detailed output."
        )

    vlan_summary  = vlan_data.get("summary",  f"{device.name}: VLAN audit unavailable.")
    trunk_summary = trunk_data.get("summary", f"{device.name}: Trunk audit unavailable.")

    combined = AuditResult(
        device=device.name,
        intent="drift_check",
        status=overall_status,
        findings=all_findings,
        summary=summary,
        warnings=[f.message for f in all_findings if f.status != AuditStatus.COMPLIANT],
        next_action=next_action,
        evidence={
            "vlan_audit":  {
                "status":   vlan_data.get("status"),
                "summary":  vlan_summary,
                "evidence": vlan_data.get("evidence", {}),
            },
            "trunk_audit": {
                "status":   trunk_data.get("status"),
                "summary":  trunk_summary,
                "evidence": trunk_data.get("evidence", {}),
            },
            "device_role": {
                "expected": expected_role,
                "actual":   device.role,
                "match":    expected_role == device.role if expected_role else None,
            },
        },
    )

    logger.info(
        f"drift_check {device.name}: status={combined.status.upper()}, "
        f"total_findings={len(all_findings)}"
    )

    return JobResult(
        success=True,
        device=device.name,
        intent="drift_check",
        command_executed="show vlan brief, show interfaces trunk",
        parsed_data=combined.model_dump(),
        raw_output=_format_text(combined),
    )


def _format_text(audit: AuditResult) -> str:
    """Human-readable text block for CLI display."""
    lines = [
        f"Drift Check — {audit.device.upper()}",
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
