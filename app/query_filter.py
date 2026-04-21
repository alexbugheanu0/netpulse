"""
Server-side `query` filter for OpenClaw responses.

When the user asks about a single resource ("ARP for 10.0.0.50", "MAC on
Gi1/0/5", "route to 10.10.0.0/24"), the agent can set `query` in the payload
and this module filters `parsed_data` down to matching rows *before* the
response is sent back over the chat channel. That trims hundreds of rows
to one and saves substantial tokens.

Matching is intentionally permissive (case-insensitive substring) so the
agent does not need to normalise user input. For CIDR routes we support
both "10.10.0.0/24" and bare network "10.10.0.0" lookups.

Non-supported intents (e.g. show_vlans, show_version, health_check) silently
ignore `query` and return data unchanged — the caller does not need to know
which intents are filterable.
"""

from __future__ import annotations

from typing import Any, Callable, Optional

# Intents for which `query` does something useful. Anything not listed here
# is a no-op and returns `parsed_data` unchanged.
FILTERABLE_INTENTS: frozenset[str] = frozenset({
    "show_arp",
    "show_mac",
    "show_route",
    "show_interfaces",
    "show_errors",
    "show_cdp",
    "show_logging",
})


def apply_query(intent: str, parsed_data: Any, query: Optional[str]) -> Any:
    """
    Return `parsed_data` filtered by `query` for supported intents.

    - If `query` is falsy, returns `parsed_data` unchanged.
    - If `intent` is not filterable, returns `parsed_data` unchanged.
    - If `parsed_data` is not a list, returns it unchanged (audits etc.).
    - On match failure returns [] (caller should surface "no match" summary).
    """
    if not query:
        return parsed_data
    if intent not in FILTERABLE_INTENTS:
        return parsed_data
    if not isinstance(parsed_data, list):
        return parsed_data

    fn = _FILTERS.get(intent)
    if fn is None:
        return parsed_data

    q = query.strip()
    if not q:
        return parsed_data

    # Pre-normalise the query once. For now we only need the MAC-normalised
    # form; individual matchers still lowercase the query themselves so they
    # can compare against other fields.
    q_mac = _normalise_mac(q)

    return [
        row for row in parsed_data
        if isinstance(row, dict) and fn(row, q, q_mac)
    ]


# ── Per-intent matchers ────────────────────────────────────────────────────────

def _match_arp(row: dict, q: str, q_mac: str) -> bool:
    """Match on IP, interface, or MAC (any format)."""
    ql = q.lower()
    return (
        ql in str(row.get("ip", "")).lower()
        or (q_mac and q_mac in _normalise_mac(str(row.get("mac", ""))))
        or ql in str(row.get("interface", "")).lower()
    )


def _match_mac(row: dict, q: str, q_mac: str) -> bool:
    """Match on MAC (any format), port substring, or VLAN id."""
    ql = q.lower()
    return (
        (q_mac and q_mac in _normalise_mac(str(row.get("mac", ""))))
        or ql in str(row.get("port", "")).lower()
        or ql == str(row.get("vlan", "")).lower()
    )


def _match_route(row: dict, q: str, q_mac: str) -> bool:
    """
    Match on prefix — accept either 'A.B.C.D' or 'A.B.C.D/N'.

    Parser returns {prefix: 'A.B.C.D', mask: 'N' or None}, so we compare
    the query against either the bare prefix or 'prefix/mask'.
    """
    ql = q.lower().strip()
    prefix = str(row.get("prefix", "")).lower()
    mask = row.get("mask")
    full = f"{prefix}/{mask}" if mask else prefix

    if ql == prefix or ql == full:
        return True
    # substring fallback so "10.10" also matches "10.10.0.0/24"
    return ql in prefix or ql in full


def _match_port(row: dict, q: str, q_mac: str) -> bool:
    """Match on port name substring — used for show_interfaces and show_errors."""
    ql = q.lower()
    return ql in str(row.get("port", "")).lower()


def _match_cdp(row: dict, q: str, q_mac: str) -> bool:
    """Match on device_id, platform, local_port, or remote_port substrings."""
    ql = q.lower()
    return any(
        ql in str(row.get(k, "")).lower()
        for k in ("device_id", "platform", "local_port", "remote_port", "ip")
    )


def _match_logging(row: dict, q: str, q_mac: str) -> bool:
    """Match on mnemonic, facility, or message substrings."""
    ql = q.lower()
    return any(
        ql in str(row.get(k, "")).lower()
        for k in ("mnemonic", "facility", "message")
    )


_FILTERS: dict[str, Callable[[dict, str, str], bool]] = {
    "show_arp":        _match_arp,
    "show_mac":        _match_mac,
    "show_route":      _match_route,
    "show_interfaces": _match_port,
    "show_errors":     _match_port,
    "show_cdp":        _match_cdp,
    "show_logging":    _match_logging,
}


# ── Helpers ────────────────────────────────────────────────────────────────────

def _normalise_mac(mac: str) -> str:
    """
    Lowercase a MAC and strip separators so "aa:bb:cc:00:01:02",
    "aabb.cc00.0102", and "AABB-CC00-0102" all compare equal.
    """
    return mac.lower().replace(":", "").replace(".", "").replace("-", "")
