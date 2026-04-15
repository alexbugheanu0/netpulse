"""
SNMP client scaffold — v1 placeholder.

SSH is the primary transport in this release.
This module exists as a clean extension point.

To activate SNMP support:
1. pip install pysnmp
2. Implement get_sys_descr() and get_interface_counters() below
3. Set snmp_enabled: true in devices.yaml for target devices

TODO (OpenClaw integration): SNMP polling can feed real-time interface
counters and sysDescr data into OpenClaw for trend analysis and alerting.
"""

from __future__ import annotations

from app.logger import get_logger

logger = get_logger(__name__)


def get_sys_descr(ip: str, community: str = "public") -> str:
    """
    Retrieve sysDescr (OID 1.3.6.1.2.1.1.1.0) from a device via SNMPv2c.

    Not implemented in v1 — returns a placeholder string.
    Requires pysnmp to be installed and SNMP enabled on the device.
    """
    logger.warning(f"SNMP get_sys_descr called for {ip} — not implemented in v1.")
    return f"[SNMP not implemented] sysDescr for {ip}"


def get_interface_counters(ip: str, community: str = "public") -> dict:
    """
    Retrieve interface counter OIDs from a device via SNMP.

    Not implemented in v1 — returns an empty dict.
    """
    logger.warning(f"SNMP get_interface_counters called for {ip} — not implemented in v1.")
    return {}
