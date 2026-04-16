"""
SNMP client scaffold — v1 placeholder.

SSH is the primary transport in this release. This module exists as a
clean extension point for polling-based enrichment.

To activate SNMP support:
    1. pip install pysnmp  (and add it to requirements.txt)
    2. Set snmp_enabled: true for target devices in devices.yaml
    3. Implement get_sys_descr() and get_interface_counters() below

TODO (SNMP enrichment): Call get_sys_descr() during inventory load to
verify device reachability and cross-check platform strings before SSH jobs run.

TODO (SNMP enrichment): Call get_interface_counters() in health_check.py to
add real-time error/discard/utilisation counters to the health check output.

TODO (OpenClaw integration): Pipe SNMP counter trends into OpenClaw context
so it can detect interface flaps, high error rates, and utilisation spikes.
"""

from __future__ import annotations

from app.logger import get_logger

logger = get_logger(__name__)


def get_sys_descr(ip: str, community: str = "public") -> str:
    """
    Retrieve sysDescr (OID 1.3.6.1.2.1.1.1.0) from a device via SNMPv2c.

    Not implemented in v1 — raises NotImplementedError.
    """
    raise NotImplementedError(
        f"SNMP not implemented in v1. "
        f"Install pysnmp and implement get_sys_descr() to query {ip}."
    )


def get_interface_counters(ip: str, community: str = "public") -> dict:
    """
    Retrieve interface counter OIDs (ifInErrors, ifOutErrors, etc.) via SNMP.

    Not implemented in v1 — raises NotImplementedError.
    """
    raise NotImplementedError(
        f"SNMP not implemented in v1. "
        f"Install pysnmp and implement get_interface_counters() to query {ip}."
    )
