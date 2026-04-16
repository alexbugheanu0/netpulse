"""Unit tests for CLI output parsers."""

from app.parsers import (
    parse_ping,
    parse_show_cdp_neighbors,
    parse_show_interfaces_errors,
    parse_show_mac_table,
    parse_show_spanning_tree,
    parse_show_version,
    parse_show_vlans,
)


# ── parse_show_vlans ───────────────────────────────────────────────────────────

VLAN_OUTPUT = """\
VLAN Name                             Status    Ports
---- -------------------------------- --------- ------
1    default                          active    Gi0/1
10   MGMT                             active
20   SERVERS                          active
1002 fddi-default                     act/unsup
"""

def test_parse_show_vlans_count():
    result = parse_show_vlans(VLAN_OUTPUT)
    assert len(result) == 4


def test_parse_show_vlans_fields():
    result = parse_show_vlans(VLAN_OUTPUT)
    assert result[0]["vlan_id"] == "1"
    assert result[0]["name"]    == "default"
    assert result[0]["status"]  == "active"


def test_parse_show_vlans_skips_header():
    result = parse_show_vlans(VLAN_OUTPUT)
    assert all(r["vlan_id"].isdigit() for r in result)


# ── parse_show_version ─────────────────────────────────────────────────────────

VERSION_OUTPUT = """\
Cisco IOS Software, Version 15.2(4)E8, RELEASE SOFTWARE
Technical Support: http://www.cisco.com/techsupport
sw-core-01 uptime is 12 weeks, 3 days
cisco WS-C2960S-48FPS-L (PowerPC405) processor (revision V0) with 131072K bytes of memory.
Processor board ID FOC1234X5YZ
"""

def test_parse_show_version_software():
    result = parse_show_version(VERSION_OUTPUT)
    assert "software" in result
    assert "Cisco IOS" in result["software"]


def test_parse_show_version_uptime():
    result = parse_show_version(VERSION_OUTPUT)
    assert "uptime" in result
    assert "12 weeks" in result["uptime"]


def test_parse_show_version_hardware():
    result = parse_show_version(VERSION_OUTPUT)
    assert "hardware" in result
    assert "cisco" in result["hardware"].lower()


def test_parse_show_version_missing_key_absent():
    result = parse_show_version("No useful output here.")
    assert "software" not in result
    assert "uptime"   not in result


# ── parse_show_interfaces_errors ──────────────────────────────────────────────

INTERFACES_OUTPUT = """\
GigabitEthernet1/0/1 is up, line protocol is up (connected)
  Hardware is Gigabit Ethernet, address is aabb.cc00.0100
  MTU 1500 bytes
     0 packets input, 0 bytes
     0 input errors, 0 CRC, 0 frame, 0 overrun, 0 ignored
     0 output errors, 0 collisions, 0 interface resets
GigabitEthernet1/0/2 is up, line protocol is up (connected)
  Hardware is Gigabit Ethernet, address is aabb.cc00.0200
     47 input errors, 12 CRC, 0 frame, 0 overrun, 0 ignored
     3 output errors, 0 collisions, 2 interface resets
GigabitEthernet1/0/3 is down, line protocol is down (notconnect)
     0 input errors, 0 CRC, 0 frame, 0 overrun, 0 ignored
     0 output errors, 0 collisions, 0 interface resets
"""

def test_parse_interfaces_errors_count():
    result = parse_show_interfaces_errors(INTERFACES_OUTPUT)
    assert len(result) == 3


def test_parse_interfaces_errors_clean_port():
    result = parse_show_interfaces_errors(INTERFACES_OUTPUT)
    gi1 = next(r for r in result if r["port"] == "GigabitEthernet1/0/1")
    assert gi1["input_errors"]  == 0
    assert gi1["crc"]           == 0
    assert gi1["output_errors"] == 0


def test_parse_interfaces_errors_dirty_port():
    result = parse_show_interfaces_errors(INTERFACES_OUTPUT)
    gi2 = next(r for r in result if r["port"] == "GigabitEthernet1/0/2")
    assert gi2["input_errors"]  == 47
    assert gi2["crc"]           == 12
    assert gi2["output_errors"] == 3
    assert gi2["resets"]        == 2


def test_parse_interfaces_errors_link_state():
    result = parse_show_interfaces_errors(INTERFACES_OUTPUT)
    gi3 = next(r for r in result if r["port"] == "GigabitEthernet1/0/3")
    assert gi3["link"]     == "down"
    assert gi3["protocol"] == "down"


# ── parse_show_cdp_neighbors ──────────────────────────────────────────────────

CDP_OUTPUT = """\
-------------------------
Device ID: sw-dist-01
Entry address(es):
  IP address: 192.168.1.2
Platform: cisco WS-C2960S-48FPS-L,  Capabilities: Switch IGMP
Interface: GigabitEthernet1/0/1,  Port ID (outgoing port): GigabitEthernet0/2
-------------------------
Device ID: sw-acc-02
Entry address(es):
  IP address: 192.168.1.11
Platform: cisco WS-C2960-24TC-L,  Capabilities: Switch IGMP
Interface: GigabitEthernet1/0/2,  Port ID (outgoing port): GigabitEthernet0/1
"""

def test_parse_cdp_count():
    result = parse_show_cdp_neighbors(CDP_OUTPUT)
    assert len(result) == 2


def test_parse_cdp_device_fields():
    result = parse_show_cdp_neighbors(CDP_OUTPUT)
    n = result[0]
    assert n["device_id"]   == "sw-dist-01"
    assert n["ip"]          == "192.168.1.2"
    assert "WS-C2960" in n["platform"]
    assert n["local_port"]  == "GigabitEthernet1/0/1"
    assert n["remote_port"] == "GigabitEthernet0/2"


# ── parse_show_mac_table ──────────────────────────────────────────────────────

MAC_OUTPUT = """\
          Mac Address Table
-------------------------------------------
Vlan    Mac Address       Type        Ports
----    -----------       --------    -----
   1    0050.7966.6800    DYNAMIC     Gi0/1
  10    aabb.cc00.0101    STATIC      Gi0/2
  20    1234.5678.9abc    DYNAMIC     Gi0/3
"""

def test_parse_mac_count():
    result = parse_show_mac_table(MAC_OUTPUT)
    assert len(result) == 3


def test_parse_mac_fields():
    result = parse_show_mac_table(MAC_OUTPUT)
    assert result[0]["vlan"] == "1"
    assert result[0]["mac"]  == "0050.7966.6800"
    assert result[0]["type"] == "DYNAMIC"
    assert result[0]["port"] == "Gi0/1"


def test_parse_mac_static_entry():
    result = parse_show_mac_table(MAC_OUTPUT)
    assert result[1]["type"] == "STATIC"


# ── parse_show_spanning_tree ──────────────────────────────────────────────────

STP_OUTPUT = """\
VLAN0001
  Spanning tree enabled protocol rstp
  Root ID    Priority    32769
  Bridge ID  Priority    32769

Interface           Role Sts Cost      Prio.Nbr Type
------------------- ---- --- --------- -------- --------------------------------
Gi0/1               Root FWD 4         128.1    P2p
Gi0/2               Desg FWD 4         128.2    P2p
Gi0/3               Altn BLK 4         128.3    P2p

VLAN0010
  Spanning tree enabled protocol rstp
Interface           Role Sts Cost      Prio.Nbr Type
------------------- ---- --- --------- -------- --------------------------------
Gi0/1               Root FWD 4         128.1    P2p
"""

def test_parse_stp_count():
    result = parse_show_spanning_tree(STP_OUTPUT)
    assert len(result) == 4


def test_parse_stp_vlan_field():
    result = parse_show_spanning_tree(STP_OUTPUT)
    vlan1_ports = [r for r in result if r["vlan"] == "VLAN0001"]
    assert len(vlan1_ports) == 3


def test_parse_stp_port_fields():
    result = parse_show_spanning_tree(STP_OUTPUT)
    root_port = next(r for r in result if r["role"] == "Root" and r["vlan"] == "VLAN0001")
    assert root_port["port"]  == "Gi0/1"
    assert root_port["state"] == "FWD"
    assert root_port["cost"]  == "4"


def test_parse_stp_blocking_port():
    result = parse_show_spanning_tree(STP_OUTPUT)
    altn = next(r for r in result if r["role"] == "Altn")
    assert altn["state"] == "BLK"


# ── parse_ping ────────────────────────────────────────────────────────────────

PING_SUCCESS = """\
Type escape sequence to abort.
Sending 5, 100-byte ICMP Echos to 10.0.0.1, timeout is 2 seconds:
!!!!!
Success rate is 100 percent (5/5), round-trip min/avg/max = 1/2/4 ms
"""

PING_PARTIAL = """\
Type escape sequence to abort.
Sending 5, 100-byte ICMP Echos to 10.0.0.1, timeout is 2 seconds:
!!.!!
Success rate is 80 percent (4/5), round-trip min/avg/max = 1/3/6 ms
"""

PING_FAIL = """\
Type escape sequence to abort.
Sending 5, 100-byte ICMP Echos to 10.0.0.1, timeout is 2 seconds:
.....
Success rate is 0 percent (0/5)
"""

def test_parse_ping_success():
    result = parse_ping(PING_SUCCESS)
    assert result["success_rate"] == "100"
    assert result["sent"]         == "5"
    assert result["received"]     == "5"
    assert result["min_ms"]       == "1"
    assert result["avg_ms"]       == "2"
    assert result["max_ms"]       == "4"


def test_parse_ping_partial():
    result = parse_ping(PING_PARTIAL)
    assert result["success_rate"] == "80"
    assert result["received"]     == "4"


def test_parse_ping_fail():
    result = parse_ping(PING_FAIL)
    assert result["success_rate"] == "0"
    assert result["min_ms"] is None  # no RTT line when 0% success
