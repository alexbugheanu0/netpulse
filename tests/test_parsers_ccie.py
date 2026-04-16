"""
Tests for the 5 CCIE-level parser functions added in the CCIE skills upgrade.

All tests use representative Cisco IOS output samples. No live devices required.
"""

from __future__ import annotations

import pytest

from app.parsers import (
    parse_show_arp,
    parse_show_etherchannel,
    parse_show_logging,
    parse_show_port_security,
    parse_show_route,
)


# ── parse_show_route ───────────────────────────────────────────────────────────

ROUTE_OUTPUT = """\
Codes: C - connected, S - static, R - RIP, M - mobile, B - BGP
       O - OSPF, IA - OSPF inter area, N1 - OSPF NSSA external type 1

Gateway of last resort is 10.0.0.1 to network 0.0.0.0

S*    0.0.0.0/0 [1/0] via 10.0.0.1
      10.0.0.0/8 is variably subnetted, 4 subnets, 2 masks
C        10.0.0.0/24 is directly connected, GigabitEthernet0/0
L        10.0.0.11/32 is directly connected, GigabitEthernet0/0
O        10.0.1.0/24 [110/2] via 10.0.0.2, 00:15:23, GigabitEthernet0/0
B        192.168.1.0/24 [20/0] via 203.0.113.1, 01:00:00
"""

def test_route_parses_static_default():
    routes = parse_show_route(ROUTE_OUTPUT)
    defaults = [r for r in routes if r["prefix"] == "0.0.0.0"]
    assert len(defaults) == 1
    assert defaults[0]["protocol"] == "S"

def test_route_parses_connected():
    routes = parse_show_route(ROUTE_OUTPUT)
    connected = [r for r in routes if r["protocol"] == "C"]
    assert len(connected) == 1
    assert connected[0]["prefix"] == "10.0.0.0"

def test_route_parses_ospf_with_ad_metric():
    routes = parse_show_route(ROUTE_OUTPUT)
    ospf = [r for r in routes if r["protocol"] == "O"]
    assert len(ospf) == 1
    assert ospf[0]["admin_distance"] == 110
    assert ospf[0]["metric"] == 2
    assert ospf[0]["next_hop"] == "10.0.0.2"

def test_route_parses_bgp():
    routes = parse_show_route(ROUTE_OUTPUT)
    bgp = [r for r in routes if r["protocol"] == "B"]
    assert len(bgp) == 1
    assert bgp[0]["prefix"] == "192.168.1.0"

def test_route_skips_subnetted_header():
    routes = parse_show_route(ROUTE_OUTPUT)
    for r in routes:
        assert "subnetted" not in r["prefix"]

def test_route_empty_output():
    assert parse_show_route("") == []

def test_route_no_default_route():
    raw = "C     10.1.1.0/24 is directly connected, Gi0/1\n"
    routes = parse_show_route(raw)
    has_default = any(r["prefix"] == "0.0.0.0" for r in routes)
    assert not has_default

def test_route_returns_list_of_dicts():
    routes = parse_show_route(ROUTE_OUTPUT)
    assert isinstance(routes, list)
    assert all(isinstance(r, dict) for r in routes)
    for r in routes:
        assert "protocol" in r
        assert "prefix" in r


# ── parse_show_arp ─────────────────────────────────────────────────────────────

ARP_OUTPUT = """\
Protocol  Address          Age (min)  Hardware Addr   Type   Interface
Internet  10.0.0.1                -   0050.7966.6800  ARPA   GigabitEthernet0/0
Internet  10.0.0.2               42   0050.7966.6801  ARPA   GigabitEthernet0/0
Internet  10.0.0.50              12   Incomplete      ARPA   GigabitEthernet0/0
"""

def test_arp_parses_local_entry():
    entries = parse_show_arp(ARP_OUTPUT)
    local = [e for e in entries if e["age"] == "-"]
    assert len(local) == 1
    assert local[0]["ip"] == "10.0.0.1"

def test_arp_parses_remote_entry():
    entries = parse_show_arp(ARP_OUTPUT)
    remote = [e for e in entries if e["age"] == "42"]
    assert len(remote) == 1
    assert remote[0]["mac"] == "0050.7966.6801"

def test_arp_parses_incomplete():
    entries = parse_show_arp(ARP_OUTPUT)
    incomplete = [e for e in entries if "incomplete" in e["mac"].lower()]
    assert len(incomplete) == 1
    assert incomplete[0]["ip"] == "10.0.0.50"

def test_arp_skips_header():
    entries = parse_show_arp(ARP_OUTPUT)
    assert all(e["protocol"].lower() != "protocol" for e in entries)

def test_arp_empty_output():
    assert parse_show_arp("") == []

def test_arp_returns_list_of_dicts():
    entries = parse_show_arp(ARP_OUTPUT)
    assert isinstance(entries, list)
    assert len(entries) == 3
    for e in entries:
        assert "ip" in e and "mac" in e and "interface" in e


# ── parse_show_etherchannel ───────────────────────────────────────────────────

ETHERCHANNEL_OUTPUT = """\
Flags:  D - down        P - bundled in port-channel
        I - stand-alone s - suspended  H - Hot-standby (LACP only)
        R - Layer3      S - Layer2     U - in use      f - failed to allocate aggregator

Number of channel-groups in use: 2
Number of aggregators:           2

Group  Port-channel  Protocol    Ports
------+-------------+-----------+-----------------------------------------------
1      Po1(SU)         LACP      Gi1/0/1(P)   Gi1/0/2(P)
2      Po2(SD)         LACP      Gi1/0/3(D)   Gi1/0/4(s)
"""

def test_etherchannel_parses_two_groups():
    bundles = parse_show_etherchannel(ETHERCHANNEL_OUTPUT)
    assert len(bundles) == 2

def test_etherchannel_group1_healthy():
    bundles = parse_show_etherchannel(ETHERCHANNEL_OUTPUT)
    g1 = next(b for b in bundles if b["group"] == "1")
    assert g1["protocol"].upper() == "LACP"
    assert len(g1["member_ports"]) == 2
    bundled = [m for m in g1["member_ports"] if "P" in m["flags"]]
    assert len(bundled) == 2

def test_etherchannel_group2_has_problem_ports():
    bundles = parse_show_etherchannel(ETHERCHANNEL_OUTPUT)
    g2 = next(b for b in bundles if b["group"] == "2")
    problem = [m for m in g2["member_ports"] if any(f in m["flags"] for f in {"D", "s"})]
    assert len(problem) == 2

def test_etherchannel_empty_output():
    assert parse_show_etherchannel("") == []

def test_etherchannel_returns_list_of_dicts():
    bundles = parse_show_etherchannel(ETHERCHANNEL_OUTPUT)
    for b in bundles:
        assert "group" in b
        assert "port_channel" in b
        assert "member_ports" in b
        assert isinstance(b["member_ports"], list)


# ── parse_show_port_security ──────────────────────────────────────────────────

PORT_SECURITY_OUTPUT = """\
Secure Port  MaxSecureAddr  CurrentAddr  SecurityViolation  Security Action
                (Count)       (Count)          (Count)
---------------------------------------------------------------------------
      Gi1/0/1              1              1                  0         Shutdown
      Gi1/0/2              5              3                  2         Restrict
      Gi1/0/3              3              0                  0         Protect
---------------------------------------------------------------------------
Total Addresses in System (excluding one mac per port)     : 4
Max Addresses limit in System (excluding one mac per port) : 4096
"""

def test_port_security_parses_three_ports():
    ports = parse_show_port_security(PORT_SECURITY_OUTPUT)
    assert len(ports) == 3

def test_port_security_violation_detected():
    ports = parse_show_port_security(PORT_SECURITY_OUTPUT)
    violated = [p for p in ports if p["violations"] > 0]
    assert len(violated) == 1
    assert violated[0]["interface"] == "Gi1/0/2"
    assert violated[0]["violations"] == 2

def test_port_security_action_parsed():
    ports = parse_show_port_security(PORT_SECURITY_OUTPUT)
    by_iface = {p["interface"]: p for p in ports}
    assert by_iface["Gi1/0/1"]["action"] == "Shutdown"
    assert by_iface["Gi1/0/2"]["action"] == "Restrict"
    assert by_iface["Gi1/0/3"]["action"] == "Protect"

def test_port_security_mac_counts():
    ports = parse_show_port_security(PORT_SECURITY_OUTPUT)
    by_iface = {p["interface"]: p for p in ports}
    assert by_iface["Gi1/0/1"]["max_mac"] == 1
    assert by_iface["Gi1/0/2"]["current_mac"] == 3

def test_port_security_empty_output():
    assert parse_show_port_security("") == []

def test_port_security_no_violations():
    ports = parse_show_port_security(PORT_SECURITY_OUTPUT)
    no_viol = [p for p in ports if p["violations"] == 0]
    assert len(no_viol) == 2


# ── parse_show_logging ─────────────────────────────────────────────────────────

LOGGING_OUTPUT = """\
Syslog logging: enabled (0 messages dropped, 3 messages rate-limited, 0 flushes, 0 overruns, xml disabled, filtering disabled)

No Active Message Discriminator.

No Inactive Message Discriminator.

    Console logging: disabled
    Monitor logging: level debugging, 0 messages logged, xml disabled, filtering disabled
    Buffer logging:  level debugging, 150 messages logged, xml disabled, filtering disabled
    Logging Exception size (8192 bytes)
    Count and timestamp logging messages: disabled
    Persistent logging: disabled

No active filter modules.

    Trap logging: level informational, 72 message lines logged

Log Buffer (8192 bytes):
*Apr 15 10:00:00.001: %SYS-5-CONFIG_I: Configured from console by admin on vty0
*Apr 15 10:05:23.456: %LINEPROTO-5-UPDOWN: Line protocol on Interface GigabitEthernet1/0/5, changed state to down
*Apr 15 10:05:24.789: %LINK-3-UPDOWN: Interface GigabitEthernet1/0/5, changed state to down
*Apr 15 10:10:00.001: %OSPF-5-ADJCHG: Process 1, Nbr 10.0.0.2 on GigabitEthernet0/0 from FULL to DOWN
*Apr 15 10:15:00.000: %SEC-6-IPACCESSLOGP: list ACL-MGMT denied tcp 10.1.2.3(54321) -> 10.0.0.11(22)
"""

def test_logging_parses_five_entries():
    entries = parse_show_logging(LOGGING_OUTPUT)
    assert len(entries) == 5

def test_logging_parses_facility_and_severity():
    entries = parse_show_logging(LOGGING_OUTPUT)
    lineproto = next(e for e in entries if e["facility"] == "LINEPROTO")
    assert lineproto["severity_code"] == 5
    assert lineproto["mnemonic"] == "UPDOWN"

def test_logging_flags_severity_3():
    entries = parse_show_logging(LOGGING_OUTPUT)
    critical = [e for e in entries if e["severity_code"] <= 3]
    assert len(critical) == 1
    assert critical[0]["facility"] == "LINK"
    assert critical[0]["severity_code"] == 3

def test_logging_parses_timestamp():
    entries = parse_show_logging(LOGGING_OUTPUT)
    assert all("Apr" in e["timestamp"] for e in entries)

def test_logging_empty_output():
    assert parse_show_logging("") == []

def test_logging_returns_at_most_20():
    # Generate 30 log lines
    line = "*Apr 15 10:00:00.000: %SYS-6-LOGGINGHOST_STARTSTOP: something\n"
    raw = "Log Buffer:\n" + line * 30
    entries = parse_show_logging(raw)
    assert len(entries) <= 20

def test_logging_returns_list_of_dicts():
    entries = parse_show_logging(LOGGING_OUTPUT)
    for e in entries:
        assert "timestamp" in e
        assert "facility" in e
        assert "severity_code" in e
        assert "mnemonic" in e
        assert "message" in e
