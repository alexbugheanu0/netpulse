"""
Pydantic data models for NetPulse.

These models enforce type safety and validation at every layer of the app.

TODO (OpenClaw integration): IntentRequest and JobResult are already
JSON-serialisable. Pass them directly as structured tool call inputs/outputs
when wiring NetPulse into OpenClaw.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel


class IntentType(str, Enum):
    SHOW_INTERFACES    = "show_interfaces"
    SHOW_VLANS         = "show_vlans"
    SHOW_TRUNKS        = "show_trunks"
    SHOW_VERSION       = "show_version"
    SHOW_ERRORS        = "show_errors"        # interface error counters
    SHOW_CDP           = "show_cdp"           # CDP/LLDP neighbours
    SHOW_MAC           = "show_mac"           # MAC address table
    SHOW_SPANNING_TREE = "show_spanning_tree" # STP port roles and states
    PING               = "ping"              # ping <target> from device
    BACKUP_CONFIG      = "backup_config"     # save running-config to file
    DIFF_BACKUP        = "diff_backup"       # diff two most recent backups
    HEALTH_CHECK       = "health_check"      # version + interfaces + vlans
    # L3 and advanced diagnostic intents
    SHOW_ROUTE         = "show_route"        # show ip route — routing table
    SHOW_ARP           = "show_arp"          # show ip arp — ARP cache
    SHOW_ETHERCHANNEL  = "show_etherchannel" # show etherchannel summary — LAG/LACP
    SHOW_PORT_SECURITY = "show_port_security"# show port-security — violations/state
    SHOW_LOGGING       = "show_logging"      # show logging — recent syslog entries
    # SSOT audit intents
    AUDIT_VLANS        = "audit_vlans"       # compare VLANs vs ssot/vlans.yaml
    AUDIT_TRUNKS       = "audit_trunks"      # compare trunks vs ssot/trunks.yaml
    DEVICE_FACTS       = "device_facts"      # collect and summarise device facts
    DRIFT_CHECK        = "drift_check"       # combined VLAN + trunk audit
    # Write / config-push intents (scope=single only; require Telegram approval)
    ADD_VLAN           = "add_vlan"          # add a VLAN to a device
    REMOVE_VLAN        = "remove_vlan"       # remove a VLAN from a device
    SHUTDOWN_INTERFACE    = "shutdown_interface"    # shut down an interface
    NO_SHUTDOWN_INTERFACE = "no_shutdown_interface" # bring up an interface
    SET_INTERFACE_VLAN    = "set_interface_vlan"    # set access VLAN on a port


class ScopeType(str, Enum):
    SINGLE = "single"  # one named device
    ALL    = "all"     # all SSH-enabled devices in inventory
    ROLE   = "role"    # all devices matching a role (core, access, etc.)


class Device(BaseModel):
    """One network device from inventory/devices.yaml."""

    name:         str
    hostname:     str
    ip:           str
    platform:     str           # Netmiko device_type, e.g. cisco_ios, cisco_xe
    role:         str
    ssh_enabled:  bool = True
    snmp_enabled: bool = False  # TODO (SNMP enrichment): wire into snmp_client.py


class IntentRequest(BaseModel):
    """
    A validated, structured intent derived from a natural language query
    or explicit CLI flags. Consumed by validators.py and main.py.
    """

    intent:      IntentType
    device:      Optional[str] = None
    scope:       ScopeType = ScopeType.SINGLE
    role:        Optional[str] = None      # for scope=role, e.g. "core", "access"
    ping_target: Optional[str] = None     # destination IP for intent=ping
    raw_query:   str = ""
    # Write intent parameters (only used by write intents; ignored otherwise)
    vlan_id:     Optional[int] = None     # for add_vlan, remove_vlan, set_interface_vlan
    vlan_name:   Optional[str] = None     # for add_vlan
    interface:   Optional[str] = None     # for shutdown_interface, no_shutdown_interface, set_interface_vlan


class JobResult(BaseModel):
    """
    The result of executing a single job against one device.
    Every job module's run() function returns one of these.

    TODO (OpenClaw integration): Feed parsed_data to OpenClaw for NL
    summaries, anomaly detection, or structured tool call responses.
    """

    success:          bool
    device:           str
    intent:           str
    command_executed: str
    parsed_data:      Optional[Any] = None
    raw_output:       str = ""
    error:            Optional[str] = None
    elapsed_ms:       Optional[float] = None  # populated by executor.py (_timed_run)


# ── Audit / SSOT models ────────────────────────────────────────────────────────

class AuditStatus(str, Enum):
    """
    Severity levels for SSOT audit findings, in ascending order.
    Used to determine the worst-case status across a set of findings.
    """
    COMPLIANT = "compliant"  # all checked items match the baseline
    WARNING   = "warning"    # minor issue: name mismatch, overly-permissive trunk
    EXTRA     = "extra"      # item on device not present in baseline
    MISSING   = "missing"    # item in baseline not present on device
    MISMATCH  = "mismatch"   # explicit disagreement (role, native VLAN, etc.)


class AuditFinding(BaseModel):
    """One finding from a SSOT comparison."""

    status:   AuditStatus
    field:    str            # what was compared: "vlan_id", "allowed_vlans", "role"
    expected: Optional[Any] = None
    actual:   Optional[Any] = None
    message:  str            # operator-friendly description of the finding


class AuditResult(BaseModel):
    """
    Structured audit result for one device.

    Stored as JobResult.parsed_data (via .model_dump()) for all audit intents
    so it serialises cleanly to JSON without needing custom encoders.
    """

    device:      str
    intent:      str
    status:      AuditStatus        # worst (most severe) status across all findings
    findings:    list[AuditFinding]
    summary:     str                # one-line, chat-ready
    warnings:    list[str]          # human-readable warning/error messages
    next_action: str                # recommended next step for the operator
    evidence:    dict[str, Any]     # raw data used in the comparison
