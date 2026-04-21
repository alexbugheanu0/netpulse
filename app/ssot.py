"""
SSOT (Single Source of Truth) loader for NetPulse.

Reads YAML files from the ssot/ directory and returns typed Python objects
consumed exclusively by app/audit.py comparison logic.

Missing SSOT files produce a warning log and an empty baseline — audits will
report "no baseline defined" rather than crashing.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from app.config import SSOT_DIR
from app.logger import get_logger

logger = get_logger(__name__)


@dataclass
class VlanSSOT:
    """Expected VLAN definitions, keyed by role and optionally by device name."""

    roles:   dict[str, list[dict]]   # role → [{"id": "10", "name": "MGMT"}, ...]
    devices: dict[str, list[dict]]   # device name → [...] (per-device override)


@dataclass
class TrunkSSOT:
    """Expected trunk profiles, keyed by role and optionally by device name."""

    roles:   dict[str, dict]   # role → {"allowed_vlans": [1, 10, ...], "native_vlan": 1}
    devices: dict[str, dict]   # device name → {...} (per-device override)


@dataclass
class ChangePolicy:
    """
    Parsed content of ssot/change-policy.yaml.

    auto_approve and require_approval are keyed by intent name and hold the raw
    condition data from YAML. The forbidden list contains free-form rule strings.
    Only the forbidden/protected-resource enforcement path is used by the validator;
    auto_approve vs require_approval is the agent's (SKILL.md) responsibility.
    """

    auto_approve:     dict[str, Any]  # intent → condition dict
    require_approval: dict[str, Any]  # intent → condition list
    forbidden:        list[str]       # free-form rule descriptions


@dataclass
class ProtectedResources:
    """
    Parsed content of ssot/protected-resources.yaml.

    Three sections:
      protected_vlans      — VLANs that must not be removed without approval.
      protected_devices    — Devices where write intents are always restricted.
      protected_interfaces — Named trunk/uplink interfaces that must not be
                             shut down or have their VLAN changed.
    """

    protected_vlans:      list[dict[str, Any]]  # [{id, name, reason}]
    protected_devices:    list[dict[str, Any]]  # [{name, role, reason, extra_rules}]
    protected_interfaces: list[dict[str, Any]]  # [{device, interfaces, reason}]


# ── Internal helpers ───────────────────────────────────────────────────────────

def _load_yaml(path: Path) -> dict[str, Any]:
    """Load a YAML file and return its contents. Returns {} on missing file."""
    if not path.exists():
        logger.warning(f"SSOT file not found: {path} — using empty baseline.")
        return {}
    try:
        with open(path) as fh:
            return yaml.safe_load(fh) or {}
    except yaml.YAMLError as exc:
        logger.error(f"Failed to parse SSOT file {path}: {exc}")
        raise


# ── Public loaders ─────────────────────────────────────────────────────────────

def load_vlan_ssot() -> VlanSSOT:
    """Load ssot/vlans.yaml."""
    raw = _load_yaml(SSOT_DIR / "vlans.yaml")
    return VlanSSOT(
        roles=raw.get("roles") or {},
        devices=raw.get("devices") or {},
    )


def load_trunk_ssot() -> TrunkSSOT:
    """Load ssot/trunks.yaml."""
    raw = _load_yaml(SSOT_DIR / "trunks.yaml")
    return TrunkSSOT(
        roles=raw.get("roles") or {},
        devices=raw.get("devices") or {},
    )


def load_device_roles() -> dict[str, str]:
    """
    Load ssot/device_roles.yaml.

    Returns a dict mapping device name → expected role string.
    """
    raw = _load_yaml(SSOT_DIR / "device_roles.yaml")
    return raw.get("devices") or {}


def load_change_policy() -> ChangePolicy:
    """Load ssot/change-policy.yaml."""
    raw = _load_yaml(SSOT_DIR / "change-policy.yaml")
    return ChangePolicy(
        auto_approve=raw.get("auto_approve") or {},
        require_approval=raw.get("require_approval") or {},
        forbidden=raw.get("forbidden") or [],
    )


def load_protected_resources() -> ProtectedResources:
    """Load ssot/protected-resources.yaml."""
    raw = _load_yaml(SSOT_DIR / "protected-resources.yaml")
    return ProtectedResources(
        protected_vlans=raw.get("protected_vlans") or [],
        protected_devices=raw.get("protected_devices") or [],
        protected_interfaces=raw.get("protected_interfaces") or [],
    )


# ── Lookup helpers ─────────────────────────────────────────────────────────────

def get_expected_vlans(device_name: str, role: str, ssot: VlanSSOT) -> list[dict]:
    """
    Return the expected VLAN list for a device.

    Device-level override takes precedence over the role-level baseline.
    Returns [] if neither the device nor its role has an entry.
    """
    if device_name in ssot.devices:
        return ssot.devices[device_name]
    return ssot.roles.get(role, [])


def get_expected_trunk_profile(device_name: str, role: str, ssot: TrunkSSOT) -> dict:
    """
    Return the expected trunk profile for a device.

    Device-level override takes precedence over the role-level baseline.
    Returns {} if neither the device nor its role has an entry.
    """
    if device_name in ssot.devices:
        return ssot.devices[device_name]
    return ssot.roles.get(role, {})
