"""
Unit tests for app/audit.py comparison logic and app/parsers.py VLAN helpers.

All tests are pure Python — no SSH, no SSOT file I/O, no mocking required.
"""

from __future__ import annotations

import json

import pytest

from app.audit import compare_trunks, compare_vlans, worst_status
from app.models import AuditFinding, AuditStatus
from app.parsers import expand_vlan_range, parse_show_trunks_allowed


# ── expand_vlan_range ──────────────────────────────────────────────────────────

def test_expand_vlan_range_simple_list():
    assert expand_vlan_range("1,10,20,30,100") == [1, 10, 20, 30, 100]


def test_expand_vlan_range_single():
    assert expand_vlan_range("10") == [10]


def test_expand_vlan_range_with_range():
    assert expand_vlan_range("1-5,10") == [1, 2, 3, 4, 5, 10]


def test_expand_vlan_range_mixed():
    result = expand_vlan_range("1,5-8,20")
    assert result == [1, 5, 6, 7, 8, 20]


def test_expand_vlan_range_none():
    assert expand_vlan_range("none") == []


def test_expand_vlan_range_empty():
    assert expand_vlan_range("") == []


def test_expand_vlan_range_all_vlans_is_large():
    result = expand_vlan_range("1-4094")
    assert len(result) > 200   # caller uses this to detect permit-all trunks
    assert 1 in result
    assert 4094 in result


def test_expand_vlan_range_deduplicates():
    assert expand_vlan_range("1,1,10,10") == [1, 10]


# ── parse_show_trunks_allowed ──────────────────────────────────────────────────

_TRUNK_OUTPUT = """\
Port        Mode         Encapsulation  Status        Native vlan
Gi1/0/1     on           802.1q         trunking      1
Gi1/0/2     on           802.1q         trunking      1

Port        Vlans allowed on trunk
Gi1/0/1     1,10,20,30,100
Gi1/0/2     1,10,20,30,100,200

Port        Vlans allowed and active in management domain
Gi1/0/1     1,10,20,30,100
Gi1/0/2     1,10,20,30,100,200

Port        Vlans in spanning tree forwarding state and not pruned
Gi1/0/1     1,10,20,30,100
Gi1/0/2     1,10,20,30,100
"""


def test_parse_show_trunks_allowed_basic():
    results = parse_show_trunks_allowed(_TRUNK_OUTPUT)
    assert len(results) == 2

    gi1 = next(r for r in results if r["port"] == "Gi1/0/1")
    gi2 = next(r for r in results if r["port"] == "Gi1/0/2")

    assert gi1["allowed_vlans"] == [1, 10, 20, 30, 100]
    assert gi2["allowed_vlans"] == [1, 10, 20, 30, 100, 200]


def test_parse_show_trunks_allowed_all_vlans():
    raw = """\
Port        Vlans allowed on trunk
Gi1/0/1     1-4094

Port        Vlans allowed and active in management domain
Gi1/0/1     1,10
"""
    results = parse_show_trunks_allowed(raw)
    assert len(results) == 1
    assert len(results[0]["allowed_vlans"]) > 200


def test_parse_show_trunks_allowed_none():
    raw = """\
Port        Vlans allowed on trunk
Gi1/0/1     none

Port        Vlans allowed and active in management domain
Gi1/0/1     none
"""
    results = parse_show_trunks_allowed(raw)
    assert len(results) == 1
    assert results[0]["allowed_vlans"] == []


def test_parse_show_trunks_allowed_empty_input():
    assert parse_show_trunks_allowed("") == []


def test_parse_show_trunks_allowed_no_trunk_section():
    raw = "Port   Mode   Status\nGi1/0/1  on  notconnect"
    assert parse_show_trunks_allowed(raw) == []


# ── worst_status ───────────────────────────────────────────────────────────────

def test_worst_status_empty():
    assert worst_status([]) == AuditStatus.COMPLIANT


def test_worst_status_single_missing():
    f = AuditFinding(status=AuditStatus.MISSING, field="x", message="x")
    assert worst_status([f]) == AuditStatus.MISSING


def test_worst_status_mixed():
    findings = [
        AuditFinding(status=AuditStatus.COMPLIANT, field="x", message="ok"),
        AuditFinding(status=AuditStatus.WARNING,   field="y", message="warn"),
        AuditFinding(status=AuditStatus.EXTRA,     field="z", message="extra"),
    ]
    assert worst_status(findings) == AuditStatus.EXTRA


def test_worst_status_mismatch_wins():
    findings = [
        AuditFinding(status=AuditStatus.MISSING,  field="a", message="m"),
        AuditFinding(status=AuditStatus.MISMATCH, field="b", message="mm"),
    ]
    assert worst_status(findings) == AuditStatus.MISMATCH


# ── compare_vlans ──────────────────────────────────────────────────────────────

_EXPECTED_VLANS = [
    {"id": "1",   "name": "default"},
    {"id": "10",  "name": "MGMT"},
    {"id": "20",  "name": "SERVERS"},
    {"id": "30",  "name": "USERS"},
    {"id": "100", "name": "VOICE"},
]

_ACTUAL_VLANS_OK = [
    {"vlan_id": "1",   "name": "default", "status": "active"},
    {"vlan_id": "10",  "name": "MGMT",    "status": "active"},
    {"vlan_id": "20",  "name": "SERVERS", "status": "active"},
    {"vlan_id": "30",  "name": "USERS",   "status": "active"},
    {"vlan_id": "100", "name": "VOICE",   "status": "active"},
]


def test_compare_vlans_compliant():
    result = compare_vlans("sw-acc-01", _EXPECTED_VLANS, _ACTUAL_VLANS_OK)
    assert result.status == AuditStatus.COMPLIANT
    assert result.warnings == []
    assert "compliant" in result.summary.lower()


def test_compare_vlans_missing_vlan():
    actual = [v for v in _ACTUAL_VLANS_OK if v["vlan_id"] != "30"]
    result = compare_vlans("sw-acc-01", _EXPECTED_VLANS, actual)
    assert result.status == AuditStatus.MISSING
    missing = [f for f in result.findings if f.status == AuditStatus.MISSING]
    assert any(f.expected == "30" for f in missing)


def test_compare_vlans_extra_vlan():
    actual = _ACTUAL_VLANS_OK + [{"vlan_id": "999", "name": "ROGUE", "status": "active"}]
    result = compare_vlans("sw-acc-01", _EXPECTED_VLANS, actual)
    assert result.status == AuditStatus.EXTRA
    extra = [f for f in result.findings if f.status == AuditStatus.EXTRA]
    assert any(f.actual == "999" for f in extra)


def test_compare_vlans_name_mismatch():
    actual = [
        {"vlan_id": "1",   "name": "default",  "status": "active"},
        {"vlan_id": "10",  "name": "MGMT",     "status": "active"},
        {"vlan_id": "20",  "name": "WEBSERV",  "status": "active"},   # wrong name
        {"vlan_id": "30",  "name": "USERS",    "status": "active"},
        {"vlan_id": "100", "name": "VOICE",    "status": "active"},
    ]
    result = compare_vlans("sw-acc-01", _EXPECTED_VLANS, actual)
    assert result.status == AuditStatus.WARNING
    warn = [f for f in result.findings if f.status == AuditStatus.WARNING]
    assert any(f.field == "vlan_name" and f.expected == "SERVERS" for f in warn)


def test_compare_vlans_no_baseline():
    result = compare_vlans("sw-acc-01", [], _ACTUAL_VLANS_OK)
    assert result.status == AuditStatus.COMPLIANT
    assert "no vlan baseline" in result.summary.lower()


def test_compare_vlans_result_is_json_serialisable():
    result = compare_vlans("sw-acc-01", _EXPECTED_VLANS, _ACTUAL_VLANS_OK)
    dumped = result.model_dump()
    # Must not raise
    raw = json.dumps(dumped)
    assert "compliant" in raw


def test_compare_vlans_evidence_present():
    result = compare_vlans("sw-acc-01", _EXPECTED_VLANS, _ACTUAL_VLANS_OK)
    assert "expected_ids" in result.evidence
    assert "actual_ids"   in result.evidence


# ── compare_trunks ─────────────────────────────────────────────────────────────

_EXPECTED_ALLOWED = [1, 10, 20, 30, 100]


def test_compare_trunks_compliant():
    ports = [
        {"port": "Gi1/0/1", "allowed_vlans": [1, 10, 20, 30, 100]},
        {"port": "Gi1/0/2", "allowed_vlans": [1, 10, 20, 30, 100]},
    ]
    result = compare_trunks("sw-dist-01", _EXPECTED_ALLOWED, ports)
    assert result.status == AuditStatus.COMPLIANT
    assert result.warnings == []


def test_compare_trunks_missing_vlan_on_port():
    ports = [{"port": "Gi1/0/1", "allowed_vlans": [1, 10, 20, 100]}]  # 30 missing
    result = compare_trunks("sw-dist-01", _EXPECTED_ALLOWED, ports)
    assert result.status == AuditStatus.MISSING
    missing = [f for f in result.findings if f.status == AuditStatus.MISSING]
    assert len(missing) == 1
    assert 30 in missing[0].expected


def test_compare_trunks_extra_vlan_on_port():
    ports = [{"port": "Gi1/0/1", "allowed_vlans": [1, 10, 20, 30, 100, 200]}]
    result = compare_trunks("sw-dist-01", _EXPECTED_ALLOWED, ports)
    assert result.status == AuditStatus.EXTRA
    extra = [f for f in result.findings if f.status == AuditStatus.EXTRA]
    assert any(200 in (f.actual or []) for f in extra)


def test_compare_trunks_all_vlans_is_warning():
    # Expanded 1-4094 list → more than 200 items
    all_vlans = list(range(1, 4095))
    ports = [{"port": "Gi1/0/1", "allowed_vlans": all_vlans}]
    result = compare_trunks("sw-dist-01", _EXPECTED_ALLOWED, ports)
    assert result.status == AuditStatus.WARNING
    assert any(f.status == AuditStatus.WARNING for f in result.findings)


def test_compare_trunks_no_trunks():
    result = compare_trunks("sw-dist-01", _EXPECTED_ALLOWED, [])
    assert result.status == AuditStatus.WARNING
    assert "no active trunk" in result.summary.lower()


def test_compare_trunks_no_baseline():
    ports = [{"port": "Gi1/0/1", "allowed_vlans": [1, 10, 20, 30, 100]}]
    result = compare_trunks("sw-dist-01", [], ports)
    assert result.status == AuditStatus.COMPLIANT
    assert "no trunk baseline" in result.summary.lower()


def test_compare_trunks_result_is_json_serialisable():
    ports = [{"port": "Gi1/0/1", "allowed_vlans": [1, 10, 20, 30, 100]}]
    result = compare_trunks("sw-dist-01", _EXPECTED_ALLOWED, ports)
    dumped = result.model_dump()
    raw = json.dumps(dumped)
    assert "compliant" in raw


def test_compare_trunks_evidence_present():
    ports = [{"port": "Gi1/0/1", "allowed_vlans": [1, 10, 20, 30, 100]}]
    result = compare_trunks("sw-dist-01", _EXPECTED_ALLOWED, ports)
    assert "expected_allowed" in result.evidence
    assert "actual_ports"     in result.evidence
