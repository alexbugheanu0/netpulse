"""Unit tests for the server-side `query` filter used by the OpenClaw adapter."""

from __future__ import annotations

import pytest

from app.query_filter import FILTERABLE_INTENTS, apply_query


# ── No-op paths ────────────────────────────────────────────────────────────────

def test_empty_query_returns_data_unchanged():
    data = [{"ip": "10.0.0.1"}, {"ip": "10.0.0.2"}]
    assert apply_query("show_arp", data, None) is data
    assert apply_query("show_arp", data, "") is data
    assert apply_query("show_arp", data, "   ") is data


def test_non_filterable_intent_returns_data_unchanged():
    """show_vlans is not in FILTERABLE_INTENTS — query is ignored."""
    data = [{"vlan_id": "10", "name": "MGMT"}]
    assert apply_query("show_vlans", data, "MGMT") is data


def test_non_list_parsed_data_returned_unchanged():
    """Audit dicts and health_check dicts must not be filtered."""
    data = {"version": {"software": "..."}, "vlans": []}
    assert apply_query("show_route", data, "10.0.0.0") is data


def test_filterable_intents_constant_contents():
    expected = {
        "show_arp", "show_mac", "show_route",
        "show_interfaces", "show_errors",
        "show_cdp", "show_logging",
    }
    assert FILTERABLE_INTENTS == frozenset(expected)


# ── show_arp ───────────────────────────────────────────────────────────────────

def test_arp_filter_exact_ip_match():
    data = [
        {"ip": "10.0.0.1", "mac": "aabb.cc00.0001", "interface": "Gi0/1"},
        {"ip": "10.0.0.5", "mac": "aabb.cc00.0005", "interface": "Gi0/2"},
    ]
    out = apply_query("show_arp", data, "10.0.0.5")
    assert len(out) == 1
    assert out[0]["ip"] == "10.0.0.5"


def test_arp_filter_mac_substring_any_format():
    data = [
        {"ip": "10.0.0.1", "mac": "aabb.cc00.0001"},
        {"ip": "10.0.0.2", "mac": "aabb.cc00.0002"},
    ]
    # Colon separators should match dot-separated parser output.
    out = apply_query("show_arp", data, "aa:bb:cc:00:00:02")
    assert len(out) == 1
    assert out[0]["ip"] == "10.0.0.2"


def test_arp_filter_no_match_returns_empty_list():
    data = [{"ip": "10.0.0.1", "mac": "aabb.cc00.0001"}]
    out = apply_query("show_arp", data, "192.168.200.1")
    assert out == []


# ── show_mac ───────────────────────────────────────────────────────────────────

def test_mac_filter_by_port():
    data = [
        {"vlan": "10", "mac": "aabb.cc00.0001", "port": "Gi1/0/5"},
        {"vlan": "10", "mac": "aabb.cc00.0002", "port": "Gi1/0/6"},
    ]
    out = apply_query("show_mac", data, "Gi1/0/5")
    assert len(out) == 1
    assert out[0]["port"] == "Gi1/0/5"


def test_mac_filter_by_vlan_id():
    data = [
        {"vlan": "10", "mac": "aabb.cc00.0001", "port": "Gi1/0/5"},
        {"vlan": "20", "mac": "aabb.cc00.0002", "port": "Gi1/0/6"},
    ]
    out = apply_query("show_mac", data, "20")
    assert len(out) == 1
    assert out[0]["vlan"] == "20"


# ── show_route ─────────────────────────────────────────────────────────────────

def test_route_filter_exact_prefix():
    data = [
        {"protocol": "S", "prefix": "0.0.0.0",    "mask": "0",  "next_hop": "10.0.0.1"},
        {"protocol": "C", "prefix": "10.10.0.0", "mask": "24"},
    ]
    out = apply_query("show_route", data, "10.10.0.0")
    assert len(out) == 1
    assert out[0]["prefix"] == "10.10.0.0"


def test_route_filter_cidr_prefix_matches_prefix_mask():
    data = [
        {"protocol": "O", "prefix": "10.10.0.0", "mask": "24", "next_hop": "10.0.0.5"},
        {"protocol": "O", "prefix": "10.20.0.0", "mask": "24", "next_hop": "10.0.0.5"},
    ]
    out = apply_query("show_route", data, "10.10.0.0/24")
    assert len(out) == 1
    assert out[0]["prefix"] == "10.10.0.0"


def test_route_filter_default_route_lookup():
    data = [
        {"protocol": "S", "prefix": "0.0.0.0",   "mask": "0",  "next_hop": "10.0.0.1"},
        {"protocol": "C", "prefix": "10.10.0.0", "mask": "24"},
    ]
    out = apply_query("show_route", data, "0.0.0.0/0")
    assert len(out) == 1
    assert out[0]["prefix"] == "0.0.0.0"


# ── show_interfaces / show_errors (port substring) ─────────────────────────────

def test_interfaces_filter_by_port_substring():
    data = [
        {"port": "Gi1/0/1", "status": "connected"},
        {"port": "Gi1/0/2", "status": "notconnect"},
        {"port": "Gi1/0/10", "status": "connected"},
    ]
    out = apply_query("show_interfaces", data, "Gi1/0/1")
    # Both Gi1/0/1 and Gi1/0/10 contain "Gi1/0/1" — substring match is the
    # intentional contract; callers wanting exact should pass the full name.
    ports = {row["port"] for row in out}
    assert "Gi1/0/1" in ports
    assert "Gi1/0/10" in ports


def test_errors_filter_by_port():
    data = [
        {"port": "Gi1/0/5", "crc": 10, "input_errors": 10},
        {"port": "Gi1/0/6", "crc": 0,  "input_errors": 0},
    ]
    out = apply_query("show_errors", data, "Gi1/0/5")
    assert len(out) == 1
    assert out[0]["crc"] == 10


# ── show_cdp ───────────────────────────────────────────────────────────────────

def test_cdp_filter_matches_device_id():
    data = [
        {"device_id": "sw-dist-01", "platform": "C9300", "local_port": "Gi1/0/1", "remote_port": "Gi1/0/24"},
        {"device_id": "sw-acc-01",  "platform": "C9200", "local_port": "Gi1/0/2", "remote_port": "Gi1/0/24"},
    ]
    out = apply_query("show_cdp", data, "sw-dist-01")
    assert len(out) == 1
    assert out[0]["device_id"] == "sw-dist-01"


def test_cdp_filter_matches_local_port():
    # Remote ports intentionally don't contain "Te1/1/1" so the substring match
    # on the query is unambiguous against local_port only.
    data = [
        {"device_id": "sw-dist-01", "platform": "C9300", "local_port": "Gi1/0/1", "remote_port": "Gi0/0/1"},
        {"device_id": "sw-acc-01",  "platform": "C9200", "local_port": "Te1/1/1", "remote_port": "Gi0/0/2"},
    ]
    out = apply_query("show_cdp", data, "Te1/1/1")
    assert len(out) == 1
    assert out[0]["device_id"] == "sw-acc-01"


# ── show_logging ───────────────────────────────────────────────────────────────

def test_logging_filter_matches_mnemonic():
    data = [
        {"facility": "LINEPROTO", "severity_code": 5, "mnemonic": "UPDOWN",   "message": "Line protocol up"},
        {"facility": "SEC",        "severity_code": 6, "mnemonic": "IPACCESSLOGP", "message": "ACL hit"},
    ]
    out = apply_query("show_logging", data, "UPDOWN")
    assert len(out) == 1
    assert out[0]["mnemonic"] == "UPDOWN"


def test_logging_filter_matches_message_substring():
    data = [
        {"facility": "LINEPROTO", "severity_code": 5, "mnemonic": "UPDOWN",   "message": "Line protocol up on Gi1/0/5"},
        {"facility": "SEC",        "severity_code": 6, "mnemonic": "IPACCESSLOGP", "message": "ACL hit"},
    ]
    out = apply_query("show_logging", data, "Gi1/0/5")
    assert len(out) == 1


# ── Robustness ─────────────────────────────────────────────────────────────────

def test_filter_survives_non_dict_rows():
    """Mixed-type lists do not raise; non-dict rows are silently skipped."""
    data = [{"ip": "10.0.0.1"}, "not-a-dict", None, {"ip": "10.0.0.2"}]
    out = apply_query("show_arp", data, "10.0.0.1")
    assert len(out) == 1
    assert out[0]["ip"] == "10.0.0.1"
