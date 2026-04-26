"""Unit tests for the OpenClaw adapter and summarizer."""

import json
import os
import re
from unittest.mock import patch

import pytest

from app.models import Device, IntentType, JobResult
from app.openclaw_adapter import (
    OPENCLAW_ALLOWED_INTENTS,
    OpenClawRequest,
    OpenClawResponse,
    run_openclaw,
)
from app.summarizer import summarize

# ── Shared test fixtures ───────────────────────────────────────────────────────

MOCK_INVENTORY = {
    "sw-core-01": Device(
        name="sw-core-01",
        hostname="sw-core-01",
        ip="192.168.1.1",
        platform="cisco_ios",
        role="core",
        ssh_enabled=True,
    ),
}

VLAN_RESULT = JobResult(
    success=True,
    device="sw-core-01",
    intent="show_vlans",
    command_executed="show vlan brief",
    parsed_data=[
        {"vlan_id": "1",  "name": "default", "status": "active"},
        {"vlan_id": "10", "name": "MGMT",    "status": "active"},
    ],
    raw_output="1    default   active\n10   MGMT      active",
    elapsed_ms=180.0,
)

HEALTH_RESULT = JobResult(
    success=True,
    device="sw-core-01",
    intent="health_check",
    command_executed="show version, show interfaces status, show vlan brief",
    parsed_data={
        "version":    {"software": "Cisco IOS Software, Version 15.2(4)E8, RELEASE SOFTWARE"},
        "interfaces": [
            {"port": "Gi0/1", "status": "connected"},
            {"port": "Gi0/2", "status": "notconnect"},
        ],
        "vlans": [
            {"vlan_id": "1",  "name": "default", "status": "active"},
            {"vlan_id": "10", "name": "MGMT",    "status": "active"},
        ],
    },
    raw_output="Health check — sw-core-01\n  [version] ...",
    elapsed_ms=540.0,
)

BACKUP_RESULT = JobResult(
    success=True,
    device="sw-core-01",
    intent="backup_config",
    command_executed="show running-config",
    parsed_data={"backup_file": "/home/alex/netpulse-project/output/backups/sw-core-01_20260415_120000.cfg"},
    raw_output="Backup complete.",
    elapsed_ms=320.0,
)

TRUNK_RESULT = JobResult(
    success=True,
    device="sw-core-01",
    intent="show_trunks",
    command_executed="show interfaces trunk",
    parsed_data=None,
    raw_output=(
        "Port        Mode         Encapsulation  Status        Native vlan\n"
        "Gi1/0/1     on           802.1q         trunking      1\n"
        "Gi1/0/2     on           802.1q         trunking      1\n"
        "\n"
        "Port        Vlans allowed on trunk\n"
        "Gi1/0/1     1-4094\n"
        "Gi1/0/2     1,10,20,30,100\n"
    ),
    elapsed_ms=150.0,
)

VERSION_RESULT = JobResult(
    success=True,
    device="sw-core-01",
    intent="show_version",
    command_executed="show version",
    parsed_data={
        "software": "Cisco IOS Software, Version 15.2(4)E8, RELEASE SOFTWARE",
        "uptime":   "sw-core-01 uptime is 12 weeks, 3 days",
    },
    elapsed_ms=90.0,
)


def _patch_all(inventory=None, validate_ok=True, results=None):
    """Context-manager triple that patches inventory + validate + execute."""
    inv = inventory or MOCK_INVENTORY
    res = results or [VLAN_RESULT]

    def _validate(req, inv):
        if not validate_ok:
            raise ValueError("mock validation failure")

    return (
        patch("app.openclaw_adapter.load_inventory", return_value=inv),
        patch("app.openclaw_adapter.validate_request", side_effect=_validate),
        patch("app.openclaw_adapter.executor.execute",  return_value=res),
    )


# ── Allowlist ──────────────────────────────────────────────────────────────────

def test_allowlist_contains_required_intents():
    required = {
        IntentType.SHOW_INTERFACES,
        IntentType.SHOW_VLANS,
        IntentType.SHOW_TRUNKS,
        IntentType.SHOW_VERSION,
        IntentType.BACKUP_CONFIG,
        IntentType.HEALTH_CHECK,
        # Previously-blocked intents now allowed
        IntentType.SHOW_ERRORS,
        IntentType.SHOW_CDP,
        IntentType.SHOW_MAC,
        IntentType.SHOW_SPANNING_TREE,
        IntentType.PING,
        # New CCIE intents
        IntentType.SHOW_ROUTE,
        IntentType.SHOW_ARP,
        IntentType.SHOW_ETHERCHANNEL,
        IntentType.SHOW_PORT_SECURITY,
        IntentType.SHOW_LOGGING,
    }
    assert required <= OPENCLAW_ALLOWED_INTENTS


def test_allowlist_includes_diff_backup():
    """diff_backup is a local-file-only job and is safe to expose via OpenClaw."""
    assert IntentType.DIFF_BACKUP in OPENCLAW_ALLOWED_INTENTS


# ── Schema validation ──────────────────────────────────────────────────────────

def test_missing_intent_field_rejected():
    p1, p2, p3 = _patch_all()
    with p1, p2, p3:
        resp = run_openclaw({"device": "sw-core-01"})
    assert resp["success"] is False
    assert resp["error"] is not None
    # Error message should mention the field name
    assert "intent" in resp["error"].lower()


def test_invalid_scope_rejected():
    p1, p2, p3 = _patch_all()
    with p1, p2, p3:
        resp = run_openclaw({"intent": "show_vlans", "device": "sw-core-01", "scope": "galaxy"})
    assert resp["success"] is False
    assert resp["error"] is not None


def test_invalid_scope_error_is_operator_friendly():
    """Scope validation error should name the bad value and list valid options."""
    p1, p2, p3 = _patch_all()
    with p1, p2, p3:
        resp = run_openclaw({"intent": "show_vlans", "device": "sw-core-01", "scope": "galaxy"})
    err = resp["error"]
    assert "galaxy" in err
    assert "single" in err or "all" in err  # at least one valid scope shown


def test_unknown_intent_rejected():
    p1, p2, p3 = _patch_all()
    with p1, p2, p3:
        resp = run_openclaw({"intent": "delete_all_configs", "device": "sw-core-01"})
    assert resp["success"] is False
    assert "delete_all_configs" in resp["error"]


def test_disallowed_intent_rejected():
    """Adapter blocks a recognised IntentType that is not in OPENCLAW_ALLOWED_INTENTS."""
    import app.openclaw_adapter as oc_mod

    # Temporarily shrink the allowlist so show_vlans is excluded, exercising the
    # disallowed-intent code path without touching production state.
    trimmed = frozenset(i for i in oc_mod.OPENCLAW_ALLOWED_INTENTS if i != IntentType.SHOW_VLANS)
    p1, p2, p3 = _patch_all()
    with p1, p2, p3, patch.object(oc_mod, "OPENCLAW_ALLOWED_INTENTS", trimmed):
        resp = run_openclaw({"intent": "show_vlans", "device": "sw-core-01"})
    assert resp["success"] is False
    assert "not permitted" in resp["error"]


# ── Successful requests ────────────────────────────────────────────────────────

def test_valid_single_device_request():
    p1, p2, p3 = _patch_all()
    with p1, p2, p3:
        resp = run_openclaw({"intent": "show_vlans", "device": "sw-core-01", "scope": "single"})

    assert resp["success"] is True
    assert resp["intent"]  == "show_vlans"
    assert resp["scope"]   == "single"
    assert len(resp["results"]) == 1
    r = resp["results"][0]
    assert r["device"]  == "sw-core-01"
    assert r["success"] is True
    assert "summary" in r
    assert r["parsed_data"] is not None
    assert r["error"] is None


def test_valid_all_scope_request():
    p1, p2, p3 = _patch_all(results=[HEALTH_RESULT])
    with p1, p2, p3:
        resp = run_openclaw({"intent": "health_check", "scope": "all"})

    assert resp["success"] is True
    assert resp["scope"]   == "all"
    assert len(resp["results"]) == 1


def test_response_envelope_keys_present():
    p1, p2, p3 = _patch_all()
    with p1, p2, p3:
        resp = run_openclaw({"intent": "show_vlans", "device": "sw-core-01"})

    for key in ("success", "intent", "scope", "results", "error"):
        assert key in resp, f"Missing key: {key!r}"


def test_result_contains_elapsed_ms():
    p1, p2, p3 = _patch_all()
    with p1, p2, p3:
        resp = run_openclaw({"intent": "show_vlans", "device": "sw-core-01"})
    assert resp["results"][0]["elapsed_ms"] == 180.0


def test_raw_query_accepted_and_ignored_safely():
    p1, p2, p3 = _patch_all()
    with p1, p2, p3:
        resp = run_openclaw({
            "intent": "show_vlans",
            "device": "sw-core-01",
            "raw_query": "show vlans on sw-core-01",
        })
    assert resp["success"] is True


# ── Error paths ────────────────────────────────────────────────────────────────

def test_validation_failure_returns_error():
    p1, p2, p3 = _patch_all(validate_ok=False)
    with p1, p2, p3:
        resp = run_openclaw({"intent": "show_vlans", "device": "sw-core-01"})

    assert resp["success"] is False
    assert "mock validation failure" in resp["error"]
    assert resp["results"] == []


def test_failed_job_result_propagates():
    failed = JobResult(
        success=False,
        device="sw-core-01",
        intent="show_vlans",
        command_executed="show vlan brief",
        error="Connection timed out",
    )
    p1, p2, p3 = _patch_all(results=[failed])
    with p1, p2, p3:
        resp = run_openclaw({"intent": "show_vlans", "device": "sw-core-01"})

    assert resp["success"] is False
    assert resp["results"][0]["success"]  is False
    assert resp["results"][0]["error"]    == "Connection timed out"
    # summarize() should produce a non-empty failure message
    assert resp["results"][0]["summary"]


def test_inventory_file_not_found_returns_error():
    with patch("app.openclaw_adapter.load_inventory",
               side_effect=FileNotFoundError("/path/to/devices.yaml")):
        resp = run_openclaw({"intent": "show_vlans", "device": "sw-core-01"})

    assert resp["success"] is False
    assert "inventory" in resp["error"].lower()
    assert "not found" in resp["error"].lower()


def test_inventory_parse_error_returns_error():
    with patch("app.openclaw_adapter.load_inventory",
               side_effect=ValueError("YAML parse error at line 5")):
        resp = run_openclaw({"intent": "show_vlans", "device": "sw-core-01"})

    assert resp["success"] is False
    assert resp["error"] is not None


# ── No Rich / ANSI leakage into JSON output ────────────────────────────────────

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def test_no_ansi_in_success_response():
    """Rich markup must never appear in JSON output from the adapter."""
    p1, p2, p3 = _patch_all()
    with p1, p2, p3:
        resp = run_openclaw({"intent": "show_vlans", "device": "sw-core-01"})
    serialised = json.dumps(resp)
    assert not _ANSI_RE.search(serialised), "ANSI escape codes found in JSON response"


def test_no_ansi_in_error_response():
    """Error responses are plain text — no Rich markup."""
    p1, p2, p3 = _patch_all(validate_ok=False)
    with p1, p2, p3:
        resp = run_openclaw({"intent": "show_vlans", "device": "sw-core-01"})
    serialised = json.dumps(resp)
    assert not _ANSI_RE.search(serialised), "ANSI escape codes found in error JSON"


# ── Summary generation ─────────────────────────────────────────────────────────

def test_summary_is_non_empty_string():
    p1, p2, p3 = _patch_all()
    with p1, p2, p3:
        resp = run_openclaw({"intent": "show_vlans", "device": "sw-core-01"})
    summary = resp["results"][0]["summary"]
    assert isinstance(summary, str)
    assert len(summary) > 0


def test_summary_mentions_device():
    p1, p2, p3 = _patch_all()
    with p1, p2, p3:
        resp = run_openclaw({"intent": "show_vlans", "device": "sw-core-01"})
    assert "SW-CORE-01" in resp["results"][0]["summary"]


def test_summary_mentions_vlan_count():
    p1, p2, p3 = _patch_all()
    with p1, p2, p3:
        resp = run_openclaw({"intent": "show_vlans", "device": "sw-core-01"})
    # VLAN_RESULT has 2 VLANs
    assert "2" in resp["results"][0]["summary"]


def test_failure_summary_contains_failed():
    failed = JobResult(
        success=False,
        device="sw-core-01",
        intent="show_vlans",
        command_executed="show vlan brief",
        error="Some unexpected error",
    )
    summary = summarize(failed)
    assert "SW-CORE-01" in summary
    # Should contain some indication of failure
    assert any(w in summary.lower() for w in ("fail", "error", "unreachable", "auth"))


def test_timeout_error_summary():
    result = JobResult(
        success=False,
        device="sw-dist-01",
        intent="show_version",
        command_executed="show version",
        error="TCP connection to 10.0.0.2:22 timed out after 30s",
    )
    summary = summarize(result)
    assert "SW-DIST-01" in summary
    assert "timed out" in summary.lower() or "unreachable" in summary.lower()


def test_auth_error_summary():
    result = JobResult(
        success=False,
        device="sw-access-01",
        intent="show_interfaces",
        command_executed="show interfaces status",
        error="Authentication failed for user 'admin'",
    )
    summary = summarize(result)
    assert "SW-ACCESS-01" in summary
    assert "auth" in summary.lower() or "credential" in summary.lower()


def test_health_check_summary_includes_ports_and_version():
    summary = summarize(HEALTH_RESULT)
    assert "SW-CORE-01" in summary
    assert "15.2(4)E8" in summary   # IOS version extracted
    assert "1/2" in summary          # 1 connected out of 2 ports


def test_health_check_summary_includes_vlan_count():
    summary = summarize(HEALTH_RESULT)
    assert "2" in summary  # 2 VLANs


def test_trunks_summary_counts_active_trunks():
    summary = summarize(TRUNK_RESULT)
    assert "SW-CORE-01" in summary
    assert "2" in summary             # 2 trunking ports
    assert "Gi1/0/1" in summary or "trunk" in summary.lower()


def test_version_summary_extracts_version_number():
    summary = summarize(VERSION_RESULT)
    assert "SW-CORE-01" in summary
    assert "15.2(4)E8" in summary


def test_version_summary_includes_uptime():
    summary = summarize(VERSION_RESULT)
    assert "12 weeks" in summary


def test_backup_config_summary_shows_filename_not_full_path():
    summary = summarize(BACKUP_RESULT)
    assert "SW-CORE-01" in summary
    # Should show the filename
    assert "sw-core-01_20260415_120000.cfg" in summary
    # Should NOT show the full absolute path prefix
    assert "/home/alex" not in summary


# ── parsed_data truncation (default) and verbose opt-out ───────────────────────

def _make_arp_result(n: int) -> JobResult:
    """JobResult with an ARP parsed_data list of length n."""
    return JobResult(
        success=True,
        device="sw-core-01",
        intent="show_arp",
        command_executed="show ip arp",
        parsed_data=[
            {
                "protocol":  "Internet",
                "ip":        f"10.0.0.{i}",
                "age":       "5",
                "mac":       f"aabb.cc00.{i:04x}",
                "type":      "ARPA",
                "interface": "Gi0/1",
            }
            for i in range(1, n + 1)
        ],
        raw_output="",
        elapsed_ms=100.0,
    )


def test_parsed_data_truncated_by_default():
    """Without verbose=True, parsed_data is capped at PARSED_DATA_SAMPLE_SIZE rows."""
    p1, p2, p3 = _patch_all(results=[_make_arp_result(25)])
    with p1, p2, p3:
        resp = run_openclaw({"intent": "show_arp", "device": "sw-core-01"})
    r = resp["results"][0]
    assert len(r["parsed_data"]) == 10
    assert r["parsed_data_truncated"] is True
    assert r["parsed_data_total_rows"] == 25


def test_parsed_data_untruncated_when_small_enough():
    """Lists already <= 10 rows are returned unchanged with no truncation flag."""
    p1, p2, p3 = _patch_all(results=[_make_arp_result(5)])
    with p1, p2, p3:
        resp = run_openclaw({"intent": "show_arp", "device": "sw-core-01"})
    r = resp["results"][0]
    assert len(r["parsed_data"]) == 5
    assert r["parsed_data_truncated"] is False
    assert r["parsed_data_total_rows"] is None


def test_parsed_data_full_when_verbose_true():
    """verbose=True disables truncation entirely."""
    p1, p2, p3 = _patch_all(results=[_make_arp_result(25)])
    with p1, p2, p3:
        resp = run_openclaw({
            "intent":  "show_arp",
            "device":  "sw-core-01",
            "verbose": True,
        })
    r = resp["results"][0]
    assert len(r["parsed_data"]) == 25
    assert r["parsed_data_truncated"] is False
    assert r["parsed_data_total_rows"] is None


def test_dict_parsed_data_not_truncated():
    """health_check's dict parsed_data must not be mangled by truncation."""
    p1, p2, p3 = _patch_all(results=[HEALTH_RESULT])
    with p1, p2, p3:
        resp = run_openclaw({"intent": "health_check", "scope": "all"})
    r = resp["results"][0]
    # Still a dict with the original keys
    assert isinstance(r["parsed_data"], dict)
    assert "interfaces" in r["parsed_data"]
    assert r["parsed_data_truncated"] is False


# ── Server-side query filter ───────────────────────────────────────────────────

def test_query_filter_matches_single_arp_entry():
    p1, p2, p3 = _patch_all(results=[_make_arp_result(10)])
    with p1, p2, p3:
        resp = run_openclaw({
            "intent": "show_arp",
            "device": "sw-core-01",
            "query":  "10.0.0.3",
        })
    rows = resp["results"][0]["parsed_data"]
    assert len(rows) == 1
    assert rows[0]["ip"] == "10.0.0.3"


def test_query_filter_zero_matches_returns_empty_and_no_match_summary():
    p1, p2, p3 = _patch_all(results=[_make_arp_result(10)])
    with p1, p2, p3:
        resp = run_openclaw({
            "intent": "show_arp",
            "device": "sw-core-01",
            "query":  "192.168.99.99",
        })
    r = resp["results"][0]
    assert r["parsed_data"] == []
    assert "no match" in r["summary"].lower()
    assert "192.168.99.99" in r["summary"]


def test_query_filter_on_non_filterable_intent_is_noop():
    """`query` is ignored on intents that don't support filtering."""
    p1, p2, p3 = _patch_all(results=[VLAN_RESULT])
    with p1, p2, p3:
        resp = run_openclaw({
            "intent": "show_vlans",
            "device": "sw-core-01",
            "query":  "whatever",
        })
    # parsed_data should be untouched (2 VLANs returned from mock)
    assert len(resp["results"][0]["parsed_data"]) == 2


def test_query_filter_on_show_route_by_prefix():
    routes = JobResult(
        success=True,
        device="sw-core-01",
        intent="show_route",
        command_executed="show ip route",
        parsed_data=[
            {"protocol": "S",  "prefix": "0.0.0.0",  "mask": "0", "next_hop": "10.0.0.1"},
            {"protocol": "C",  "prefix": "10.0.0.0", "mask": "24"},
            {"protocol": "O",  "prefix": "10.10.0.0", "mask": "24", "next_hop": "10.0.0.5"},
        ],
        elapsed_ms=50.0,
    )
    p1, p2, p3 = _patch_all(results=[routes])
    with p1, p2, p3:
        resp = run_openclaw({
            "intent": "show_route",
            "device": "sw-core-01",
            "query":  "10.10.0.0/24",
        })
    rows = resp["results"][0]["parsed_data"]
    assert len(rows) == 1
    assert rows[0]["prefix"] == "10.10.0.0"


# ── aggregate_summary ──────────────────────────────────────────────────────────

def test_aggregate_summary_absent_on_single_result():
    p1, p2, p3 = _patch_all()
    with p1, p2, p3:
        resp = run_openclaw({"intent": "show_vlans", "device": "sw-core-01"})
    assert resp["aggregate_summary"] is None


def test_aggregate_summary_all_ok():
    r1 = VLAN_RESULT
    r2 = VLAN_RESULT.model_copy(update={"device": "sw-dist-01"})
    p1, p2, p3 = _patch_all(results=[r1, r2])
    with p1, p2, p3:
        resp = run_openclaw({"intent": "show_vlans", "scope": "all"})
    agg = resp["aggregate_summary"]
    assert agg is not None
    assert "2 device" in agg
    assert "OK" in agg


def test_aggregate_summary_reports_failure_device():
    ok = VLAN_RESULT
    bad = JobResult(
        success=False,
        device="sw-acc-02",
        intent="show_vlans",
        command_executed="show vlan brief",
        error="Connection timed out",
    )
    p1, p2, p3 = _patch_all(results=[ok, bad])
    with p1, p2, p3:
        resp = run_openclaw({"intent": "show_vlans", "scope": "all"})
    agg = resp["aggregate_summary"]
    assert "sw-acc-02" in agg
    assert "1 failed" in agg


def test_aggregate_summary_health_check_rolls_up_bulk_counts():
    r1 = HEALTH_RESULT
    r2 = HEALTH_RESULT.model_copy(update={"device": "sw-dist-01"})
    p1, p2, p3 = _patch_all(results=[r1, r2])
    with p1, p2, p3:
        resp = run_openclaw({"intent": "health_check", "scope": "all"})

    agg = resp["aggregate_summary"]
    assert agg is not None
    assert "2 device" in agg
    assert "ports up" in agg
    assert "VLAN" in agg


def test_telegram_response_mode_omits_bulky_plan_metadata():
    r1 = VLAN_RESULT
    r2 = VLAN_RESULT.model_copy(update={"device": "sw-dist-01"})
    p1, p2, p3 = _patch_all(results=[r1, r2])
    with p1, p2, p3:
        resp = run_openclaw({
            "intent": "show_vlans",
            "scope": "all",
            "response_mode": "telegram",
        })

    assert resp["success"] is True
    assert "aggregate_summary" in resp
    assert "audit_path" in resp
    assert "request_id" in resp
    assert "plan" not in resp
    assert "risk_decision" not in resp
    assert set(resp["results"][0].keys()) == {"summary"}


def test_telegram_response_mode_excludes_raw_command_output():
    secret_raw = "NETPULSE_PASSWORD=super-secret-value\nshow vlan brief output"
    result = VLAN_RESULT.model_copy(update={"raw_output": secret_raw})
    p1, p2, p3 = _patch_all(results=[result])
    with p1, p2, p3:
        resp = run_openclaw({
            "intent": "show_vlans",
            "device": "sw-core-01",
            "response_mode": "telegram",
        })

    serialised = json.dumps(resp)
    assert "command_executed" not in serialised
    assert "raw_output" not in serialised
    assert "show vlan brief output" not in serialised
    assert "super-secret-value" not in serialised


def test_response_redacts_env_secret_values():
    secret = "device-password-123"
    failed = JobResult(
        success=False,
        device="sw-core-01",
        intent="show_vlans",
        command_executed="show vlan brief",
        error=f"Authentication failed with password={secret}",
    )
    p1, p2, p3 = _patch_all(results=[failed])
    with patch.dict(os.environ, {"NETPULSE_PASSWORD": secret}), p1, p2, p3:
        resp = run_openclaw({"intent": "show_vlans", "device": "sw-core-01"})

    serialised = json.dumps(resp)
    assert secret not in serialised
    assert "[REDACTED]" in serialised


def test_telegram_response_redacts_secret_patterns():
    secret = "enable-secret-456"
    failed = JobResult(
        success=False,
        device="sw-core-01",
        intent="show_vlans",
        command_executed="show vlan brief",
        error=f"NETPULSE_SECRET={secret}",
    )
    p1, p2, p3 = _patch_all(results=[failed])
    with patch.dict(os.environ, {"NETPULSE_SECRET": secret}), p1, p2, p3:
        resp = run_openclaw({
            "intent": "show_vlans",
            "device": "sw-core-01",
            "response_mode": "telegram",
        })

    serialised = json.dumps(resp)
    assert secret not in serialised
    assert "NETPULSE_SECRET=[REDACTED]" in serialised


# ── OpenClawRequest schema ─────────────────────────────────────────────────────

def test_openclaw_request_accepts_query_and_verbose():
    """The new fields default correctly and accept explicit values."""
    req = OpenClawRequest(intent="show_arp", device="sw-core-01")
    assert req.query is None
    assert req.verbose is False
    assert req.response_mode == "full"

    req2 = OpenClawRequest(
        intent="show_arp",
        device="sw-core-01",
        query="10.0.0.5",
        verbose=True,
        response_mode="telegram",
    )
    assert req2.query == "10.0.0.5"
    assert req2.verbose is True
    assert req2.response_mode == "telegram"


def test_openclaw_response_includes_aggregate_summary_field():
    """aggregate_summary must be a declared field on the response model."""
    assert "aggregate_summary" in OpenClawResponse.model_fields
