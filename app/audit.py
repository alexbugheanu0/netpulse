"""
SSOT comparison logic for NetPulse audit intents.

Pure Python — no SSH calls, no Pydantic validation overhead beyond model
construction, no imports of network modules.

Each compare_* function takes an "expected" baseline (from ssot.py) and
"actual" device data (from a job's parsed_data), then returns a populated
AuditResult ready to be stored in JobResult.parsed_data via .model_dump().

Called exclusively by job modules: audit_vlans, audit_trunks, drift_check.
"""

from __future__ import annotations

from typing import Any

from app.models import AuditFinding, AuditResult, AuditStatus

# ── Severity ranking (higher = worse) ─────────────────────────────────────────
_SEVERITY: dict[AuditStatus, int] = {
    AuditStatus.COMPLIANT: 0,
    AuditStatus.WARNING:   1,
    AuditStatus.EXTRA:     2,
    AuditStatus.MISSING:   3,
    AuditStatus.MISMATCH:  4,
}

# Trunk ports with more than this many allowed VLANs are treated as "allow all"
_ALL_VLANS_THRESHOLD = 200


def worst_status(findings: list[AuditFinding]) -> AuditStatus:
    """Return the most severe status across a list of findings."""
    if not findings:
        return AuditStatus.COMPLIANT
    return max(findings, key=lambda f: _SEVERITY.get(f.status, 0)).status


# ── compare_vlans ──────────────────────────────────────────────────────────────

def compare_vlans(
    device:   str,
    expected: list[dict],   # from SSOT: [{"id": "10", "name": "MGMT"}, ...]
    actual:   list[dict],   # from show_vlans parsed_data: [{"vlan_id": "10", ...}]
) -> AuditResult:
    """
    Compare the expected VLAN list (SSOT) against actual VLANs on a device.

    Produces findings for:
      MISSING  — expected VLAN not present on device
      EXTRA    — VLAN on device not in baseline
      WARNING  — VLAN present on both sides but name does not match baseline
    """
    if not expected:
        return AuditResult(
            device=device,
            intent="audit_vlans",
            status=AuditStatus.COMPLIANT,
            findings=[],
            summary=f"{device.upper()}: No VLAN baseline defined for this role.",
            warnings=["No VLAN baseline configured in ssot/vlans.yaml for this role."],
            next_action="Add expected VLANs to ssot/vlans.yaml under the device's role.",
            evidence={"expected": [], "actual": [v["vlan_id"] for v in actual]},
        )

    expected_map: dict[str, dict] = {str(v["id"]): v for v in expected}
    actual_map:   dict[str, dict] = {v["vlan_id"]: v for v in actual}

    findings: list[AuditFinding] = []

    # MISSING: expected VLANs absent from device
    for vid in sorted(expected_map, key=int):
        if vid not in actual_map:
            ev = expected_map[vid]
            findings.append(AuditFinding(
                status=AuditStatus.MISSING,
                field="vlan_id",
                expected=vid,
                actual=None,
                message=f"VLAN {vid} ({ev.get('name', '?')}) missing from device",
            ))

    # EXTRA: VLANs on device not in baseline
    for vid in sorted(actual_map, key=int):
        if vid not in expected_map:
            av = actual_map[vid]
            findings.append(AuditFinding(
                status=AuditStatus.EXTRA,
                field="vlan_id",
                expected=None,
                actual=vid,
                message=(
                    f"VLAN {vid} ({av.get('name', '?')}) present on device "
                    f"but not in baseline"
                ),
            ))

    # WARNING: name mismatch on VLANs present on both sides
    for vid in expected_map:
        if vid in actual_map:
            exp_name = (expected_map[vid].get("name") or "").upper()
            act_name = (actual_map[vid].get("name") or "").upper()
            if exp_name and act_name and exp_name != act_name:
                findings.append(AuditFinding(
                    status=AuditStatus.WARNING,
                    field="vlan_name",
                    expected=expected_map[vid].get("name"),
                    actual=actual_map[vid].get("name"),
                    message=(
                        f"VLAN {vid} name mismatch: "
                        f"expected '{expected_map[vid].get('name')}', "
                        f"got '{actual_map[vid].get('name')}'"
                    ),
                ))

    status = worst_status(findings) if findings else AuditStatus.COMPLIANT

    if status == AuditStatus.COMPLIANT:
        summary     = (
            f"{device.upper()}: VLAN baseline compliant — "
            f"{len(actual_map)} VLAN(s) match."
        )
        next_action = "No action required."
    else:
        missing = [f.expected for f in findings if f.status == AuditStatus.MISSING]
        extra   = [f.actual   for f in findings if f.status == AuditStatus.EXTRA]
        parts: list[str] = []
        if missing:
            parts.append(f"missing: {', '.join(missing)}")
        if extra:
            parts.append(f"extra: {', '.join(str(v) for v in extra[:5])}")
        summary     = f"{device.upper()}: VLAN drift — {'; '.join(parts)}."
        next_action = (
            "Review VLANs listed as MISSING or EXTRA. "
            "Add missing VLANs or update ssot/vlans.yaml to reflect "
            "any intentional changes."
        )

    return AuditResult(
        device=device,
        intent="audit_vlans",
        status=status,
        findings=findings,
        summary=summary,
        warnings=[f.message for f in findings if f.status != AuditStatus.COMPLIANT],
        next_action=next_action,
        evidence={
            "expected_ids": sorted(expected_map.keys(), key=int),
            "actual_ids":   sorted(actual_map.keys(), key=int),
        },
    )


# ── compare_trunks ─────────────────────────────────────────────────────────────

def compare_trunks(
    device:           str,
    expected_allowed: list[int],   # from SSOT: [1, 10, 20, 30, 100]
    actual_ports:     list[dict],  # from parse_show_trunks_allowed
) -> AuditResult:
    """
    Compare expected allowed VLANs (SSOT) against actual trunk port state.

    For each trunk port:
      WARNING  — port allows all VLANs (1-4094 / very long list)
      MISSING  — an expected VLAN is not in the allowed list
      EXTRA    — port allows VLANs not in the expected set
      COMPLIANT— allowed VLANs exactly match the expected set
    """
    if not expected_allowed:
        return AuditResult(
            device=device,
            intent="audit_trunks",
            status=AuditStatus.COMPLIANT,
            findings=[],
            summary=f"{device.upper()}: No trunk baseline defined for this role.",
            warnings=["No trunk baseline configured in ssot/trunks.yaml for this role."],
            next_action="Add expected trunk VLANs to ssot/trunks.yaml under the device's role.",
            evidence={"expected": [], "actual_ports": []},
        )

    if not actual_ports:
        return AuditResult(
            device=device,
            intent="audit_trunks",
            status=AuditStatus.WARNING,
            findings=[AuditFinding(
                status=AuditStatus.WARNING,
                field="trunk_ports",
                expected=sorted(expected_allowed),
                actual=[],
                message="No active trunk interfaces found on device",
            )],
            summary=f"{device.upper()}: No active trunk interfaces found.",
            warnings=["No active trunk interfaces found — expected at least one trunk port."],
            next_action=(
                "Verify trunk configuration with 'show interfaces trunk'. "
                "Ensure at least one port is in trunking mode."
            ),
            evidence={"expected": sorted(expected_allowed), "actual_ports": []},
        )

    expected_set = set(expected_allowed)
    findings: list[AuditFinding] = []

    for entry in actual_ports:
        port   = entry["port"]
        actual = entry["allowed_vlans"]

        # Permit-all trunk (1-4094 or similar large range)
        if len(actual) > _ALL_VLANS_THRESHOLD:
            findings.append(AuditFinding(
                status=AuditStatus.WARNING,
                field="allowed_vlans",
                expected=sorted(expected_set),
                actual="1-4094 (all VLANs)",
                message=(
                    f"{port}: trunk allows all VLANs (1-4094) — "
                    f"consider restricting to: {sorted(expected_set)}"
                ),
            ))
            continue

        actual_set = set(actual)
        missing    = sorted(expected_set - actual_set)
        extra      = sorted(actual_set   - expected_set)

        if missing:
            findings.append(AuditFinding(
                status=AuditStatus.MISSING,
                field="allowed_vlans",
                expected=sorted(expected_set),
                actual=sorted(actual_set),
                message=(
                    f"{port}: missing allowed VLANs {missing}. "
                    f"Expected: {sorted(expected_set)}. "
                    f"Actual: {sorted(actual_set)}."
                ),
            ))

        if extra:
            findings.append(AuditFinding(
                status=AuditStatus.EXTRA,
                field="allowed_vlans",
                expected=sorted(expected_set),
                actual=sorted(actual_set),
                message=f"{port}: extra allowed VLANs {extra} not in baseline.",
            ))

        if not missing and not extra:
            findings.append(AuditFinding(
                status=AuditStatus.COMPLIANT,
                field="allowed_vlans",
                expected=sorted(expected_set),
                actual=sorted(actual_set),
                message=f"{port}: allowed VLANs match baseline.",
            ))

    status = worst_status(findings) if findings else AuditStatus.COMPLIANT

    if status == AuditStatus.COMPLIANT:
        summary     = (
            f"{device.upper()}: Trunk baseline compliant — "
            f"{len(actual_ports)} trunk port(s) checked."
        )
        next_action = "No action required."
    else:
        non_ok = [f for f in findings if f.status != AuditStatus.COMPLIANT]
        msgs   = "; ".join(f.message[:80] for f in non_ok[:2])
        summary     = f"{device.upper()}: Trunk drift — {msgs}."
        next_action = (
            "Review trunk ports listed above. "
            "Update 'switchport trunk allowed vlan' commands to match "
            "ssot/trunks.yaml, then re-run audit_trunks to confirm."
        )

    return AuditResult(
        device=device,
        intent="audit_trunks",
        status=status,
        findings=findings,
        summary=summary,
        warnings=[f.message for f in findings if f.status != AuditStatus.COMPLIANT],
        next_action=next_action,
        evidence={
            "expected_allowed": sorted(expected_set),
            "actual_ports": [
                {
                    "port":          p["port"],
                    "allowed_count": len(p["allowed_vlans"]),
                    # Cap at 20 entries in evidence to keep JSON readable
                    "allowed_vlans": p["allowed_vlans"][:20],
                }
                for p in actual_ports
            ],
        },
    )
