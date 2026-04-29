"""
Chat-friendly one-line summaries for NetPulse job results.

Used by openclaw_adapter.py to build the 'summary' field in OpenClawResponse.
Summaries must be:
  - one line, no newlines
  - no raw CLI output
  - suitable for Slack / Teams / Telegram messages
  - always non-empty
"""

from __future__ import annotations

import re

from app.models import JobResult

# Matches the start of a trunk port line (abbreviated IOS port names)
_PORT_RE = re.compile(r"^[A-Za-z]+[\d/]+")


def summarize(result: JobResult) -> str:
    """
    Return a single human-readable summary line for a JobResult.

    On failure, classify the error into a user-friendly message
    (auth problem, timeout, missing device, etc.) rather than dumping
    the raw exception string.
    """
    device = result.device.upper()

    if not result.success:
        return _failure_summary(device, result.error or "unknown error")

    intent = result.intent
    data   = result.parsed_data

    if intent == "show_interfaces":
        ports       = data if isinstance(data, list) else []
        connected   = [p for p in ports if "connected" in p.get("status", "")]
        err_disabled = [p for p in ports if "err-disabled" in p.get("status", "").lower()]
        suffix      = f", {len(err_disabled)} err-disabled" if err_disabled else ""
        return (
            f"{device}: {len(ports)} port(s), "
            f"{len(connected)} connected{suffix}."
        )

    if intent == "show_vlans":
        vlans = data if isinstance(data, list) else []
        ids   = ", ".join(v["vlan_id"] for v in vlans[:8])
        more  = f" (+{len(vlans) - 8} more)" if len(vlans) > 8 else ""
        return f"{device}: {len(vlans)} VLAN(s) — {ids}{more}."

    if intent == "show_trunks":
        return _trunks_summary(device, result.raw_output or "")

    if intent == "show_version":
        return _version_summary(device, data)

    if intent == "show_errors":
        ports  = data if isinstance(data, list) else []
        errors = [
            p for p in ports
            if p.get("input_errors", 0) > 0 or p.get("output_errors", 0) > 0
        ]
        if errors:
            names = ", ".join(p["port"] for p in errors[:4])
            extra = f" (+{len(errors) - 4} more)" if len(errors) > 4 else ""
            return f"{device}: {len(errors)} port(s) with errors — {names}{extra}."
        return f"{device}: No interface errors found."

    if intent == "show_cdp":
        neighbours = data if isinstance(data, list) else []
        if neighbours:
            ids   = ", ".join(n.get("device_id", "?") for n in neighbours[:4])
            extra = f" (+{len(neighbours) - 4} more)" if len(neighbours) > 4 else ""
            return f"{device}: {len(neighbours)} CDP neighbour(s) — {ids}{extra}."
        return f"{device}: No CDP neighbours found."

    if intent == "show_mac":
        return _mac_summary(device, data)

    if intent == "show_spanning_tree":
        ports    = data if isinstance(data, list) else []
        blocking = [p for p in ports if p.get("state") in ("BLK", "BKN")]
        if blocking:
            names = ", ".join(p["port"] for p in blocking[:3])
            return f"{device}: STP — {len(blocking)} port(s) blocking ({names})."
        return f"{device}: STP — {len(ports)} port/VLAN entries, none blocking."

    if intent == "show_route":
        return _route_summary(device, data)

    if intent == "show_arp":
        entries    = data if isinstance(data, list) else []
        incomplete = [e for e in entries if "incomplete" in e.get("mac", "").lower()]
        local      = [e for e in entries if e.get("age") == "-"]
        dynamic    = len(entries) - len(local) - len(incomplete)
        if incomplete:
            ips = ", ".join(e["ip"] for e in incomplete[:3])
            extra = f" (+{len(incomplete)-3} more)" if len(incomplete) > 3 else ""
            return (
                f"{device}: {len(entries)} ARP entries "
                f"({len(local)} local, {dynamic} dynamic) — "
                f"{len(incomplete)} INCOMPLETE ({ips}{extra})."
            )
        return (
            f"{device}: {len(entries)} ARP entries "
            f"({len(local)} local, {dynamic} dynamic), all resolved."
        )

    if intent == "show_etherchannel":
        return _etherchannel_summary(device, data)

    if intent == "show_port_security":
        return _port_security_summary(device, data)

    if intent == "show_logging":
        return _logging_summary(device, data)

    if intent == "diagnose_endpoint":
        return _diagnose_endpoint_summary(device, data)

    if intent == "ping":
        return result.raw_output or f"{device}: ping result unavailable."

    if intent == "backup_config":
        return _backup_summary(device, data)

    if intent == "diff_backup":
        d        = data if isinstance(data, dict) else {}
        changes  = d.get("changed_lines", 0)
        previous = d.get("previous", "?")
        latest   = d.get("latest",   "?")
        if changes == 0:
            return f"{device}: No config changes between {previous} and {latest}."
        return f"{device}: {changes} changed line(s) between {previous} and {latest}."

    if intent == "health_check":
        return _health_summary(device, data)

    # SSOT audit intents — AuditResult stores its own summary string
    if intent in ("audit_vlans", "audit_trunks", "drift_check"):
        if isinstance(data, dict) and data.get("summary"):
            return data["summary"]
        return f"{device}: {intent} completed."

    if intent == "device_facts":
        return _device_facts_summary(device, data)

    return f"{device}: {intent} completed."


# ── Intent-specific helpers ────────────────────────────────────────────────────

def _failure_summary(device: str, error: str) -> str:
    """Classify a job error into a short, operator-friendly failure message."""
    low = error.lower()

    if "authentication" in low or "auth" in low:
        return (
            f"{device}: Authentication failed — "
            "check NETPULSE_USERNAME / NETPULSE_PASSWORD in .env."
        )
    if "timed out" in low or "timeout" in low:
        return f"{device}: Unreachable or slow — connection timed out."
    if "not found in inventory" in low:
        return f"{device}: Device not found in inventory."
    if "ssh disabled" in low:
        return f"{device}: SSH is disabled for this device in inventory."
    if "credentials are not set" in low or "not set" in low:
        return f"{device}: SSH credentials not configured — check .env file."
    if "connection refused" in low:
        return f"{device}: Connection refused on port 22."
    # Generic fallback — cap length so it stays one readable line
    short = error[:120].replace("\n", " ")
    return f"{device}: Failed — {short}"


def _trunks_summary(device: str, raw: str) -> str:
    """
    Count active trunk interfaces from 'show interfaces trunk' raw output.

    The first table section lists port/mode/encapsulation/status/native-vlan.
    Lines containing 'trunking' in that section are the active trunk ports.
    """
    trunking_ports = list(dict.fromkeys(  # deduplicate, preserve order
        line.split()[0]
        for line in raw.splitlines()
        if _PORT_RE.match(line.strip()) and "trunking" in line
    ))

    if trunking_ports:
        shown = ", ".join(trunking_ports[:3])
        extra = f" (+{len(trunking_ports) - 3} more)" if len(trunking_ports) > 3 else ""
        return f"{device}: {len(trunking_ports)} active trunk(s) — {shown}{extra}."

    # Fall back: count any port-like lines (may be notconnect / other state)
    port_lines = [l for l in raw.splitlines() if _PORT_RE.match(l.strip())]
    if port_lines:
        return f"{device}: Trunk table retrieved — no active trunk interfaces found."
    return f"{device}: No trunk interfaces found."


def _version_summary(device: str, data) -> str:
    """Extract IOS version number and uptime for a compact summary."""
    if not isinstance(data, dict):
        return f"{device}: show version complete."

    sw     = data.get("software", "")
    uptime = data.get("uptime",   "")

    # "Cisco IOS Software, Version 15.2(4)E8, ..." → "15.2(4)E8"
    ver_match = re.search(r"Version\s+([\d()A-Za-z.]+)", sw)
    version   = ver_match.group(1) if ver_match else ""

    # "sw-core-01 uptime is 12 weeks, 3 days" → "12 weeks, 3 days"
    up_match   = re.search(r"uptime is\s+(.+)", uptime)
    uptime_str = up_match.group(1).strip() if up_match else ""

    parts = [p for p in (f"IOS {version}" if version else "", uptime_str) if p]
    return f"{device}: {' | '.join(parts)}." if parts else f"{device}: show version complete."


def _backup_summary(device: str, data) -> str:
    """Show only the filename (not the full path) in the backup summary."""
    if not isinstance(data, dict):
        return f"{device}: Config backup complete."
    full_path = data.get("backup_file", "")
    # Extract just the filename from the path
    filename = full_path.split("/")[-1] if "/" in full_path else full_path
    if filename:
        return f"{device}: Config saved — {filename}."
    return f"{device}: Config backup complete."


def _diagnose_endpoint_summary(device: str, data) -> str:
    """One-line endpoint diagnosis summary."""
    if not isinstance(data, dict):
        return f"{device}: Endpoint diagnosis completed."

    endpoint = data.get("endpoint", "endpoint")
    port = data.get("access_port") or "unknown port"
    vlan = data.get("vlan") or "unknown VLAN"
    cause = data.get("likely_cause") or "No obvious fault found."
    confidence = data.get("confidence") or "unknown"
    return (
        f"{device}: {endpoint} -> {port} / VLAN {vlan}; "
        f"{cause} Confidence: {confidence}."
    )


def _device_facts_summary(device: str, data) -> str:
    """One-line device facts summary: IOS version | port ratio | uptime."""
    if not isinstance(data, dict):
        return f"{device}: Device facts collected."

    parts: list[str] = []

    ios = data.get("ios_version", "")
    if ios:
        parts.append(f"IOS {ios}")

    total     = data.get("total_ports", 0)
    connected = data.get("connected_ports", 0)
    err_dis   = data.get("err_disabled_ports", 0)
    if total:
        parts.append(f"{connected}/{total} ports up")
    if err_dis:
        parts.append(f"{err_dis} err-disabled")

    uptime = data.get("uptime", "")
    if uptime:
        parts.append(uptime)

    return f"{device}: {' | '.join(parts)}." if parts else f"{device}: Device facts collected."


def _route_summary(device: str, data) -> str:
    """Total routes by protocol; flag missing default route and show its next-hop."""
    routes = data if isinstance(data, list) else []
    if not routes:
        return f"{device}: No routes in routing table."

    default = next((r for r in routes if r.get("prefix") == "0.0.0.0"), None)
    by_proto: dict[str, int] = {}
    for r in routes:
        p = r.get("protocol", "?")
        by_proto[p] = by_proto.get(p, 0) + 1

    proto_str = ", ".join(f"{k}:{v}" for k, v in sorted(by_proto.items()))

    if default is None:
        default_flag = " — WARNING: no default route"
    else:
        nh = default.get("next_hop") or default.get("interface") or "?"
        default_flag = f" — default via {nh}"

    return f"{device}: {len(routes)} routes ({proto_str}){default_flag}."


def _mac_summary(device: str, data) -> str:
    """
    MAC table summary: total entries, top-3 ports by MAC count, and a flag
    for any port with >200 MACs (likely a hub or unmanaged switch downstream).
    """
    entries = data if isinstance(data, list) else []
    if not entries:
        return f"{device}: MAC address table is empty."

    counts: dict[str, int] = {}
    for e in entries:
        port = e.get("port") or "?"
        counts[port] = counts.get(port, 0) + 1

    top = sorted(counts.items(), key=lambda kv: kv[1], reverse=True)[:3]
    top_str = ", ".join(f"{p}:{n}" for p, n in top)
    flooded = [p for p, n in counts.items() if n > 200]

    flood_flag = ""
    if flooded:
        names = ", ".join(flooded[:2])
        flood_flag = f" — WARNING: {len(flooded)} port(s) with >200 MACs ({names})"

    return (
        f"{device}: {len(entries)} MAC entries across {len(counts)} port(s) — "
        f"top: {top_str}{flood_flag}."
    )


def _etherchannel_summary(device: str, data) -> str:
    """Bundled vs down members; flag any D/s/H problem ports."""
    bundles = data if isinstance(data, list) else []
    if not bundles:
        return f"{device}: No EtherChannel groups configured."

    _PROBLEM = {"D", "s", "H", "I", "u"}
    parts: list[str] = []
    shown = bundles[:2]
    for b in shown:
        members = b.get("member_ports", [])
        problem = [m for m in members if any(f in m.get("flags", "") for f in _PROBLEM)]
        bundled = [m for m in members if "P" in m.get("flags", "")]
        status = "DEGRADED" if problem else "OK"
        prob_str = (
            " [" + ", ".join(f"{m['port']}({m['flags']})" for m in problem[:3]) + "]"
            if problem else ""
        )
        parts.append(
            f"Group {b['group']} {b.get('port_channel','')} "
            f"[{b.get('protocol','')}] {status} {len(bundled)}/{len(members)} bundled{prob_str}"
        )
    extra = f" (+{len(bundles) - 2} more)" if len(bundles) > 2 else ""
    return f"{device}: " + "; ".join(parts) + extra + "."


def _port_security_summary(device: str, data) -> str:
    """Violation counts and Shutdown-action ports."""
    ports = data if isinstance(data, list) else []
    if not ports:
        return f"{device}: No port-security configured."

    violated = [p for p in ports if p.get("violations", 0) > 0]
    if violated:
        v_str = ", ".join(
            f"{p['interface']}({p['violations']})" for p in violated[:4]
        )
        extra = f" (+{len(violated)-4} more)" if len(violated) > 4 else ""
        return f"{device}: {len(violated)} port(s) with security violations — {v_str}{extra}."

    shutdown = [p for p in ports if p.get("action", "").lower() == "shutdown"]
    return (
        f"{device}: {len(ports)} secured port(s), "
        f"{len(shutdown)} with Shutdown action, 0 violations."
    )


def _logging_summary(device: str, data) -> str:
    """Surface severity≤3 entries; quote the most recent critical message."""
    entries = data if isinstance(data, list) else []
    if not entries:
        return f"{device}: No syslog entries found (logging buffer may be empty)."

    critical = [e for e in entries if e.get("severity_code", 7) <= 3]
    if critical:
        last = critical[-1]
        msg = last.get("message", "")[:60]
        return (
            f"{device}: {len(critical)} severity≤ERROR in last {len(entries)} entries — "
            f"last: %{last['facility']}-{last['severity_code']}-{last['mnemonic']}: {msg}"
        )
    last = entries[-1]
    return (
        f"{device}: {len(entries)} recent log entries, no errors/criticals — "
        f"last: %{last['facility']}-{last['severity_code']}-{last['mnemonic']}: "
        f"{last.get('message','')[:60]}"
    )


def _health_summary(device: str, data) -> str:
    """Compact health summary: IOS version | port ratio | VLAN count."""
    if not isinstance(data, dict):
        return f"{device}: Health check complete."

    parts: list[str] = []

    # IOS version from nested version dict
    ver_data = data.get("version", {})
    if isinstance(ver_data, dict):
        sw = ver_data.get("software", "")
        m  = re.search(r"Version\s+([\d()A-Za-z.]+)", sw)
        if m:
            parts.append(f"IOS {m.group(1)}")

    ifaces    = data.get("interfaces", [])
    connected = [p for p in ifaces if "connected" in p.get("status", "")]
    if ifaces:
        parts.append(f"{len(connected)}/{len(ifaces)} ports up")

    vlans = data.get("vlans", [])
    if vlans:
        parts.append(f"{len(vlans)} VLANs")

    if parts:
        return f"{device}: {' | '.join(parts)}."
    return f"{device}: Health check complete."
