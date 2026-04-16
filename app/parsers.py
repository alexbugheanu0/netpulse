"""
Output parsers for raw Cisco CLI output.

v1 uses simple line-by-line parsing. Each function returns a list of dicts
or a single dict suitable for display or downstream processing.

To upgrade to TextFSM/ntc-templates (more robust, multi-vendor):
    pip install ntc-templates
    from ntc_templates.parse import parse_output
    parsed = parse_output(platform="cisco_ios", command="show vlan brief", data=raw)

TODO (OpenClaw integration): The dict schemas returned here are the primary
structured input for OpenClaw reasoning. Keep schemas stable across v1 patches.

TODO (config diff mode): Add parse_running_config() that returns a normalised
dict representation of the running config for line-by-line diffing against a
saved baseline.
"""

from __future__ import annotations

import re
from typing import Any

from app.logger import get_logger

logger = get_logger(__name__)


# ── Existing parsers ───────────────────────────────────────────────────────────

def parse_show_interfaces(raw: str) -> list[dict[str, str]]:
    """
    Parse 'show interfaces status' output into a list of port dicts.

    Expected columns: Port, Name, Status, Vlan, Duplex, Speed, Type
    Lines that don't start with a recognised port token are skipped.
    """
    results: list[dict[str, str]] = []
    for line in raw.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("Port"):
            continue
        parts = stripped.split()
        if len(parts) >= 3:
            results.append({
                "port":   parts[0],
                "name":   parts[1] if len(parts) > 4 else "",
                "status": parts[-4] if len(parts) > 4 else parts[1],
                "vlan":   parts[-3] if len(parts) > 4 else parts[2],
                "raw":    stripped,
            })
    return results


def parse_show_vlans(raw: str) -> list[dict[str, str]]:
    """
    Parse 'show vlan brief' output into a list of VLAN dicts.

    Only lines whose first token is a numeric VLAN ID are included.
    """
    results: list[dict[str, str]] = []
    for line in raw.splitlines():
        parts = line.split()
        if parts and parts[0].isdigit():
            results.append({
                "vlan_id": parts[0],
                "name":    parts[1] if len(parts) > 1 else "",
                "status":  parts[2] if len(parts) > 2 else "",
            })
    return results


def parse_show_version(raw: str) -> dict[str, Any]:
    """
    Parse key fields from 'show version' output.

    Returns a dict with software, uptime, hardware, and serial keys
    where those lines are found. Missing fields are absent — callers
    should use .get().
    """
    result: dict[str, Any] = {}
    for line in raw.splitlines():
        lower = line.lower()
        if "cisco ios" in lower or "ios-xe" in lower:
            result.setdefault("software", line.strip())
        if "uptime is" in lower:
            result.setdefault("uptime", line.strip())
        if "cisco" in lower and "processor" in lower:
            result.setdefault("hardware", line.strip())
        if "serial number" in lower or "processor id" in lower:
            result.setdefault("serial", line.strip())
    return result


# ── New parsers ────────────────────────────────────────────────────────────────

def parse_show_interfaces_errors(raw: str) -> list[dict[str, Any]]:
    """
    Parse 'show interfaces' (full) for per-interface error counters.

    Returns a list of dicts with port, link/protocol state, and error counts.
    Only ports that appear in the output are included (use the job to filter
    for non-zero counters before display).
    """
    results: list[dict[str, Any]] = []
    current: dict[str, Any] = {}

    for line in raw.splitlines():
        stripped = line.strip()

        # Interface header: "GigabitEthernet1/0/1 is up, line protocol is up (connected)"
        m = re.match(r"^(\S+)\s+is\s+(\w+),\s+line protocol is\s+(\w+)", stripped)
        if m:
            if current:
                results.append(current)
            current = {
                "port":          m.group(1),
                "link":          m.group(2),
                "protocol":      m.group(3),
                "input_errors":  0,
                "crc":           0,
                "output_errors": 0,
                "resets":        0,
            }
            continue

        if not current:
            continue

        # "0 input errors, 0 CRC, 0 frame, 0 overrun, 0 ignored"
        m = re.search(r"(\d+) input errors.*?(\d+) CRC", stripped)
        if m:
            current["input_errors"] = int(m.group(1))
            current["crc"]          = int(m.group(2))

        # "0 output errors, 0 collisions, 0 interface resets"
        m = re.search(r"(\d+) output errors.*?(\d+) interface resets", stripped)
        if m:
            current["output_errors"] = int(m.group(1))
            current["resets"]        = int(m.group(2))

    if current:
        results.append(current)

    return results


def parse_show_cdp_neighbors(raw: str) -> list[dict[str, str]]:
    """
    Parse 'show cdp neighbors detail' into a list of neighbour dicts.

    Keys: device_id, ip, platform, local_port, remote_port.
    """
    results: list[dict[str, str]] = []
    current: dict[str, str] = {}

    for line in raw.splitlines():
        stripped = line.strip()

        if "Device ID:" in stripped:
            if current:
                results.append(current)
            current = {"device_id": stripped.split("Device ID:")[-1].strip()}

        elif "IP address:" in stripped and current:
            current.setdefault("ip", stripped.split("IP address:")[-1].strip())

        elif stripped.startswith("Platform:") and current:
            current["platform"] = stripped.split("Platform:")[-1].split(",")[0].strip()

        elif stripped.startswith("Interface:") and current:
            parts = stripped.split(",")
            current["local_port"]  = parts[0].replace("Interface:", "").strip()
            if len(parts) > 1:
                current["remote_port"] = (
                    parts[1].replace("Port ID (outgoing port):", "").strip()
                )

    if current:
        results.append(current)

    return results


def parse_show_mac_table(raw: str) -> list[dict[str, str]]:
    """
    Parse 'show mac address-table' output into a list of MAC entry dicts.

    Keys: vlan, mac, type, port.
    Lines whose first token is not a numeric VLAN ID are skipped.
    """
    results: list[dict[str, str]] = []
    for line in raw.splitlines():
        parts = line.split()
        if parts and parts[0].isdigit() and len(parts) >= 4:
            results.append({
                "vlan": parts[0],
                "mac":  parts[1],
                "type": parts[2],
                "port": parts[3],
            })
    return results


def parse_show_spanning_tree(raw: str) -> list[dict[str, str]]:
    """
    Parse 'show spanning-tree' output into per-port STP state entries.

    Keys: vlan, port, role, state, cost.
    Captures interface lines that show role (Root/Desg/Altn/Back) and
    state (FWD/BLK/LIS/LRN).
    """
    results: list[dict[str, str]] = []
    current_vlan = ""

    for line in raw.splitlines():
        stripped = line.strip()

        if stripped.startswith("VLAN"):
            current_vlan = stripped.split()[0]  # e.g. "VLAN0001"

        # Interface line: "Gi0/1    Root FWD 4    128.1    P2p"
        m = re.match(
            r"^(\S+)\s+(Root|Desg|Altn|Back|Mstr)\s+(\w+)\s+(\d+)",
            stripped,
        )
        if m and current_vlan:
            results.append({
                "vlan":  current_vlan,
                "port":  m.group(1),
                "role":  m.group(2),
                "state": m.group(3),
                "cost":  m.group(4),
            })

    return results


def expand_vlan_range(vlan_str: str) -> list[int]:
    """
    Expand a Cisco VLAN range string to a sorted deduplicated list of VLAN IDs.

    Examples:
        "1,10,20,30,100"  → [1, 10, 20, 30, 100]
        "1-5,10"          → [1, 2, 3, 4, 5, 10]
        "none"            → []
        "1-4094"          → list of all 4094 VLANs (caller checks len > 200)

    Non-numeric tokens are silently skipped.
    """
    stripped = vlan_str.strip().lower()
    if stripped in ("none", ""):
        return []

    vlans: list[int] = []
    for part in vlan_str.split(","):
        part = part.strip()
        if "-" in part:
            try:
                start, end = part.split("-", 1)
                vlans.extend(range(int(start.strip()), int(end.strip()) + 1))
            except ValueError:
                continue
        elif part.isdigit():
            vlans.append(int(part))
    return sorted(set(vlans))


def parse_show_trunks_allowed(raw: str) -> list[dict[str, Any]]:
    """
    Parse the 'Vlans allowed on trunk' section from 'show interfaces trunk' output.

    Returns a list of port entries with expanded allowed VLAN lists:
        [
            {"port": "Gi1/0/1", "allowed_vlans": [1, 10, 20, 30, 100]},
            {"port": "Gi1/0/2", "allowed_vlans": [1, 2, ..., 4094]},  # all-vlans
        ]

    The 'allowed_vlans' list may be very large for '1-4094' trunks.
    Callers should check len(allowed_vlans) > 200 to detect permit-all trunks.

    Handles Cisco output line-wrapping where VLAN lists continue on the next line
    with leading whitespace.
    """
    results: list[dict[str, Any]] = []
    in_section = False
    current_port: str = ""
    current_vlans_str: str = ""

    # A port identifier starts with a letter followed by alphanumeric / / . -
    port_re = re.compile(r"^[A-Za-z][A-Za-z0-9/.\-]+$")

    for line in raw.splitlines():
        stripped = line.strip()
        if not stripped:
            continue

        lower = stripped.lower()

        # Enter the "Vlans allowed on trunk" section (exclude "active" variant)
        if lower.startswith("port") and "vlans allowed on trunk" in lower and "active" not in lower:
            # Flush any pending port from a previous section (shouldn't happen, but safe)
            if current_port:
                results.append({
                    "port": current_port,
                    "allowed_vlans": expand_vlan_range(current_vlans_str),
                })
                current_port = ""
                current_vlans_str = ""
            in_section = True
            continue

        # Any subsequent "Port ..." header means we've left the section
        if in_section and lower.startswith("port "):
            if current_port:
                results.append({
                    "port": current_port,
                    "allowed_vlans": expand_vlan_range(current_vlans_str),
                })
                current_port = ""
                current_vlans_str = ""
            in_section = False
            continue

        if not in_section:
            continue

        parts = stripped.split(None, 1)
        if len(parts) == 2 and port_re.match(parts[0]):
            # New port line — flush previous
            if current_port:
                results.append({
                    "port": current_port,
                    "allowed_vlans": expand_vlan_range(current_vlans_str),
                })
            current_port = parts[0]
            current_vlans_str = parts[1]
        elif current_port and (stripped[0].isdigit() or stripped.lower() == "none"):
            # Continuation line (VLAN list wrapped onto next line)
            current_vlans_str += "," + stripped

    # Flush last port
    if current_port:
        results.append({
            "port": current_port,
            "allowed_vlans": expand_vlan_range(current_vlans_str),
        })

    return results


def parse_show_route(raw: str) -> list[dict[str, Any]]:
    """
    Parse 'show ip route' output into a list of route dicts.

    Keys: protocol, prefix, mask, admin_distance, metric, next_hop, interface, age.
    Handles both directly-connected entries (C/L) and learned routes (O/B/S/R/D/i).
    Subnetted / variably-subnetted header lines are skipped.
    """
    results: list[dict[str, Any]] = []

    # protocol code at start of line, e.g. "O", "B", "S*", "C", "L", "R", "D"
    route_re = re.compile(
        r"^([A-Z][A-Z* ]*)\s+"             # protocol code(s)
        r"(\d+\.\d+\.\d+\.\d+)"            # network
        r"(?:/(\d+))?"                      # optional prefix length
        r"(?:\s+\[(\d+)/(\d+)\])?"         # optional [AD/metric]
        r"(?:\s+via\s+(\S+))?"             # optional via next-hop
        r"(?:,\s+(\S+))?"                  # optional interface after next-hop
        r"(?:\s+(\S+))?"                   # optional age
    )

    for line in raw.splitlines():
        stripped = line.strip()
        # Skip section headers and empty lines
        if not stripped or "subnetted" in stripped.lower():
            continue
        # Skip "Gateway of last resort" lines
        if stripped.lower().startswith("gateway"):
            continue

        m = route_re.match(stripped)
        if m:
            proto    = m.group(1).strip().rstrip("* ")
            next_hop = m.group(6).rstrip(",") if m.group(6) else None
            results.append({
                "protocol":       proto,
                "prefix":         m.group(2),
                "mask":           m.group(3),
                "admin_distance": int(m.group(4)) if m.group(4) else None,
                "metric":         int(m.group(5)) if m.group(5) else None,
                "next_hop":       next_hop,
                "interface":      m.group(7),
                "age":            m.group(8),
            })

    return results


def parse_show_arp(raw: str) -> list[dict[str, str]]:
    """
    Parse 'show ip arp' output into a list of ARP entry dicts.

    Keys: protocol, ip, age, mac, type, interface.
    Lines that don't start with 'Internet' are skipped.
    An age of '-' means the entry is local (directly attached).
    A mac of 'Incomplete' means ARP resolution has not completed.
    """
    results: list[dict[str, str]] = []
    for line in raw.splitlines():
        parts = line.split()
        # Expected: Internet  10.0.0.1   0   aabb.cc00.0100  ARPA  Gi0/1
        if len(parts) >= 6 and parts[0].lower() == "internet":
            results.append({
                "protocol":  parts[0],
                "ip":        parts[1],
                "age":       parts[2],
                "mac":       parts[3],
                "type":      parts[4],
                "interface": parts[5],
            })
    return results


def parse_show_etherchannel(raw: str) -> list[dict[str, Any]]:
    """
    Parse 'show etherchannel summary' into a list of bundle dicts.

    Keys: group, port_channel, protocol, flags, member_ports (list of dicts
    with keys: port, flags).

    Handles the standard Cisco IOS tabular format:
        1      Po1(SU)     LACP    Gi1/0/1(P)   Gi1/0/2(P)

    Flag meanings (Cisco abbreviations):
      U=in use, D=down, P=bundled, s=suspended, H=hot-standby, I=stand-alone
      M=not in use (min-links not met), S=Layer2, R=Layer3, u=unsuitable
    """
    results: list[dict[str, Any]] = []

    # Group line: starts with a number, e.g. "1      Po1(SU)     LACP    Gi1/0/1(P)  Gi1/0/2(P)"
    group_re  = re.compile(
        r"^(\d+)\s+"                           # group number
        r"([A-Za-z]+[\d/]*)"                   # port-channel name (e.g. Po1)
        r"\(([A-Za-z]+)\)"                     # port-channel flags (e.g. SU)
        r"\s+([A-Za-z-]+)"                     # protocol (LACP/PAgP/NONE/-)
        r"(.*)"                                # rest = member ports
    )
    # Individual member port token: "Gi1/0/1(P)"
    member_re = re.compile(r"([A-Za-z]+[\d/]+)\(([A-Za-z]+)\)")

    for line in raw.splitlines():
        stripped = line.strip()
        m = group_re.match(stripped)
        if m:
            members_raw = m.group(5)
            member_ports = [
                {"port": mm.group(1), "flags": mm.group(2)}
                for mm in member_re.finditer(members_raw)
            ]
            results.append({
                "group":        m.group(1),
                "port_channel": m.group(2) + "(" + m.group(3) + ")",
                "flags":        m.group(3),
                "protocol":     m.group(4).upper(),
                "member_ports": member_ports,
            })
        elif results:
            # Continuation line — additional member ports for the last group
            for mm in member_re.finditer(stripped):
                results[-1]["member_ports"].append({
                    "port":  mm.group(1),
                    "flags": mm.group(2),
                })

    return results


def parse_show_port_security(raw: str) -> list[dict[str, Any]]:
    """
    Parse 'show port-security' output into a list of per-interface dicts.

    Keys: interface, max_mac, current_mac, violations, action.
    Lines that don't start with a port identifier are skipped.
    """
    results: list[dict[str, Any]] = []
    # Port-Security table columns: Interface, Max, CurrentAddr, SecurityViolation, Action
    for line in raw.splitlines():
        stripped = line.strip()
        # Skip header and blank lines
        if not stripped or stripped.startswith("Secure Port") or stripped.startswith("-"):
            continue
        parts = stripped.split()
        # Need at least: interface, max, current, violations, action
        if len(parts) >= 5 and re.match(r"^[A-Za-z][A-Za-z0-9/.\-]+$", parts[0]):
            try:
                results.append({
                    "interface":  parts[0],
                    "max_mac":    int(parts[1]),
                    "current_mac": int(parts[2]),
                    "violations": int(parts[3]),
                    "action":     parts[4],
                })
            except (ValueError, IndexError):
                continue
    return results


def parse_show_logging(raw: str) -> list[dict[str, Any]]:
    """
    Parse 'show logging' output and return the most recent 20 log entries.

    Keys: timestamp, facility, severity_code, mnemonic, message.
    Severity codes: 0=emerg, 1=alert, 2=crit, 3=err, 4=warning, 5=notice, 6=info, 7=debug.
    Lines that don't match the standard syslog format are skipped.
    """
    entries: list[dict[str, Any]] = []

    # Standard Cisco syslog format:
    # *Apr 15 12:34:56.789: %FACILITY-SEVERITY-MNEMONIC: message
    # or: Apr 15 12:34:56.789: %FACILITY-SEVERITY-MNEMONIC: message (no asterisk)
    log_re = re.compile(
        r"[*]?\s*"
        r"(\w{3}\s+\d+\s+[\d:.]+)"         # timestamp
        r":\s+%"
        r"([A-Z0-9_-]+)"                    # FACILITY
        r"-(\d)"                             # severity code
        r"-([A-Z0-9_]+)"                    # MNEMONIC
        r":\s*(.*)"                          # message
    )

    for line in raw.splitlines():
        m = log_re.search(line)
        if m:
            entries.append({
                "timestamp":     m.group(1).strip(),
                "facility":      m.group(2),
                "severity_code": int(m.group(3)),
                "mnemonic":      m.group(4),
                "message":       m.group(5).strip(),
            })

    # Return the 20 most recent entries (last 20 in log order)
    return entries[-20:]


def parse_ping(raw: str) -> dict[str, Any]:
    """
    Parse Cisco ping output into a result dict.

    Keys: success_rate (percent string), sent, received, min_ms, avg_ms, max_ms.
    Absent RTT fields are None (e.g. 0% success has no RTT line).
    """
    result: dict[str, Any] = {
        "success_rate": "0",
        "sent":         None,
        "received":     None,
        "min_ms":       None,
        "avg_ms":       None,
        "max_ms":       None,
    }
    for line in raw.splitlines():
        m = re.search(r"Success rate is (\d+) percent \((\d+)/(\d+)\)", line)
        if m:
            result["success_rate"] = m.group(1)
            result["received"]     = m.group(2)
            result["sent"]         = m.group(3)

        m = re.search(r"min/avg/max = (\d+)/(\d+)/(\d+)", line)
        if m:
            result["min_ms"] = m.group(1)
            result["avg_ms"] = m.group(2)
            result["max_ms"] = m.group(3)

    return result
