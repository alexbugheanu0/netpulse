"""Unit tests for the intent parser."""

import pytest

from app.intents import parse_intent
from app.models import IntentType, ScopeType


# ── Original intents ───────────────────────────────────────────────────────────

def test_parse_show_trunks():
    req = parse_intent("show trunk status on sw-dist-01")
    assert req.intent == IntentType.SHOW_TRUNKS
    assert req.device == "sw-dist-01"
    assert req.scope  == ScopeType.SINGLE


def test_parse_show_vlans():
    req = parse_intent("show vlan on sw-core-01")
    assert req.intent == IntentType.SHOW_VLANS
    assert req.device == "sw-core-01"
    assert req.scope  == ScopeType.SINGLE


def test_parse_show_interfaces():
    req = parse_intent("show interfaces on sw-acc-01")
    assert req.intent == IntentType.SHOW_INTERFACES
    assert req.device == "sw-acc-01"


def test_parse_show_version():
    req = parse_intent("show version on sw-core-01")
    assert req.intent == IntentType.SHOW_VERSION
    assert req.device == "sw-core-01"


def test_parse_backup_config():
    req = parse_intent("backup running config from sw-acc-02")
    assert req.intent == IntentType.BACKUP_CONFIG
    assert req.device == "sw-acc-02"


def test_parse_health_check_single():
    req = parse_intent("health check sw-dist-01")
    assert req.intent == IntentType.HEALTH_CHECK
    assert req.device == "sw-dist-01"
    assert req.scope  == ScopeType.SINGLE


def test_parse_health_check_all():
    req = parse_intent("health check all switches")
    assert req.intent == IntentType.HEALTH_CHECK
    assert req.scope  == ScopeType.ALL
    assert req.device is None


def test_parse_all_scope_no_device_needed():
    req = parse_intent("show vlans on all switches")
    assert req.scope  == ScopeType.ALL
    assert req.device is None


def test_device_pattern_matches_non_sw_prefix():
    req = parse_intent("show version on rtr-core-01")
    assert req.intent == IntentType.SHOW_VERSION
    assert req.device == "rtr-core-01"


def test_parse_unknown_query_raises():
    with pytest.raises(ValueError, match="Could not match"):
        parse_intent("do something weird on sw-core-01")


def test_parse_missing_device_raises():
    with pytest.raises(ValueError, match="No device name"):
        parse_intent("show vlan without a device")


# ── New intents ────────────────────────────────────────────────────────────────

def test_parse_show_errors():
    req = parse_intent("show errors on sw-core-01")
    assert req.intent == IntentType.SHOW_ERRORS
    assert req.device == "sw-core-01"


def test_parse_show_errors_drops_keyword():
    req = parse_intent("show drops on sw-acc-01")
    assert req.intent == IntentType.SHOW_ERRORS


def test_parse_show_cdp():
    req = parse_intent("show cdp neighbors on sw-dist-01")
    assert req.intent == IntentType.SHOW_CDP
    assert req.device == "sw-dist-01"


def test_parse_show_cdp_neighbors_keyword():
    req = parse_intent("show neighbors on sw-core-01")
    assert req.intent == IntentType.SHOW_CDP


def test_parse_show_mac():
    req = parse_intent("show mac table on sw-acc-01")
    assert req.intent == IntentType.SHOW_MAC
    assert req.device == "sw-acc-01"


def test_parse_show_spanning_tree():
    req = parse_intent("show spanning tree on sw-core-01")
    assert req.intent == IntentType.SHOW_SPANNING_TREE
    assert req.device == "sw-core-01"


def test_parse_show_stp_keyword():
    req = parse_intent("show stp on sw-dist-01")
    assert req.intent == IntentType.SHOW_SPANNING_TREE


def test_parse_ping_single():
    req = parse_intent("ping 10.0.0.1 from sw-core-01")
    assert req.intent      == IntentType.PING
    assert req.device      == "sw-core-01"
    assert req.ping_target == "10.0.0.1"
    assert req.scope       == ScopeType.SINGLE


def test_parse_ping_all_scope():
    req = parse_intent("ping 8.8.8.8 from all switches")
    assert req.intent      == IntentType.PING
    assert req.ping_target == "8.8.8.8"
    assert req.scope       == ScopeType.ALL


def test_parse_ping_missing_ip_raises():
    with pytest.raises(ValueError, match="No target IP"):
        parse_intent("ping from sw-core-01")


def test_parse_diff_backup():
    req = parse_intent("diff config on sw-core-01")
    assert req.intent == IntentType.DIFF_BACKUP
    assert req.device == "sw-core-01"


def test_parse_diff_backup_changes_keyword():
    req = parse_intent("show config changes on sw-core-01")
    assert req.intent == IntentType.DIFF_BACKUP


def test_parse_diff_backup_all_scope():
    req = parse_intent("diff config on all switches")
    assert req.intent == IntentType.DIFF_BACKUP
    assert req.scope  == ScopeType.ALL


# ── Priority / disambiguation ──────────────────────────────────────────────────

def test_health_check_beats_interfaces():
    # "health check" should not fall through to show_interfaces
    req = parse_intent("health check all switches")
    assert req.intent == IntentType.HEALTH_CHECK


def test_show_errors_beats_show_interfaces():
    # "interface errors" — errors keyword should win over interfaces
    req = parse_intent("show interface errors on sw-core-01")
    assert req.intent == IntentType.SHOW_ERRORS


# ── SSOT audit intents ─────────────────────────────────────────────────────────

def test_parse_drift_check():
    req = parse_intent("drift check on sw-core-01")
    assert req.intent == IntentType.DRIFT_CHECK
    assert req.device == "sw-core-01"


def test_parse_drift_keyword_alone():
    req = parse_intent("drift on sw-dist-01")
    assert req.intent == IntentType.DRIFT_CHECK


def test_parse_compliance_keyword():
    req = parse_intent("compliance check sw-acc-01")
    assert req.intent == IntentType.DRIFT_CHECK


def test_parse_audit_vlans():
    req = parse_intent("audit vlans on sw-core-01")
    assert req.intent == IntentType.AUDIT_VLANS
    assert req.device == "sw-core-01"


def test_parse_vlan_audit():
    req = parse_intent("vlan audit sw-acc-01")
    assert req.intent == IntentType.AUDIT_VLANS


def test_parse_audit_vlans_all():
    req = parse_intent("audit vlans on all switches")
    assert req.intent == IntentType.AUDIT_VLANS
    assert req.scope  == ScopeType.ALL


def test_parse_audit_trunks():
    req = parse_intent("audit trunks on sw-dist-01")
    assert req.intent == IntentType.AUDIT_TRUNKS
    assert req.device == "sw-dist-01"


def test_parse_trunk_audit():
    req = parse_intent("trunk audit sw-dist-01")
    assert req.intent == IntentType.AUDIT_TRUNKS


def test_parse_device_facts():
    req = parse_intent("device facts for sw-acc-01")
    assert req.intent == IntentType.DEVICE_FACTS
    assert req.device == "sw-acc-01"


def test_parse_facts_keyword():
    req = parse_intent("facts on sw-core-01")
    assert req.intent == IntentType.DEVICE_FACTS


def test_audit_vlans_beats_show_vlans():
    # "audit vlans" must resolve to AUDIT_VLANS, not SHOW_VLANS
    req = parse_intent("audit vlans on sw-core-01")
    assert req.intent == IntentType.AUDIT_VLANS


def test_audit_trunks_beats_show_trunks():
    # "audit trunks" must resolve to AUDIT_TRUNKS, not SHOW_TRUNKS
    req = parse_intent("audit trunks on sw-dist-01")
    assert req.intent == IntentType.AUDIT_TRUNKS


def test_drift_check_all_devices():
    req = parse_intent("drift check all switches")
    assert req.intent == IntentType.DRIFT_CHECK
    assert req.scope  == ScopeType.ALL
