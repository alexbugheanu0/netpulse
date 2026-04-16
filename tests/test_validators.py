"""Unit tests for request validation."""

import pytest

from app.models import Device, IntentRequest, IntentType, ScopeType
from app.validators import validate_request

# Shared test inventory
INVENTORY = {
    "sw-core-01": Device(
        name="sw-core-01",
        hostname="sw-core-01.lab.local",
        ip="192.168.1.1",
        platform="cisco_ios",
        role="core",
        ssh_enabled=True,
        snmp_enabled=False,
    ),
    "sw-acc-01": Device(
        name="sw-acc-01",
        hostname="sw-acc-01.lab.local",
        ip="192.168.1.10",
        platform="cisco_ios",
        role="access",
        ssh_enabled=False,  # SSH disabled intentionally
        snmp_enabled=False,
    ),
    "sw-acc-02": Device(
        name="sw-acc-02",
        hostname="sw-acc-02.lab.local",
        ip="192.168.1.11",
        platform="cisco_ios",
        role="access",
        ssh_enabled=True,
        snmp_enabled=False,
    ),
}


def _req(intent: IntentType, device=None, scope=ScopeType.SINGLE, role=None, ping_target=None):
    return IntentRequest(
        intent=intent, device=device, scope=scope,
        role=role, ping_target=ping_target, raw_query="test",
    )


# ── SINGLE scope ───────────────────────────────────────────────────────────────

def test_valid_single_request():
    req = _req(IntentType.SHOW_VLANS, device="sw-core-01")
    validate_request(req, INVENTORY)  # should not raise


def test_device_not_found():
    req = _req(IntentType.SHOW_VLANS, device="sw-missing-99")
    with pytest.raises(ValueError, match="not found in inventory"):
        validate_request(req, INVENTORY)


def test_device_ssh_disabled():
    req = _req(IntentType.SHOW_VLANS, device="sw-acc-01")
    with pytest.raises(ValueError, match="SSH disabled"):
        validate_request(req, INVENTORY)


def test_missing_device_name_single_scope():
    req = _req(IntentType.SHOW_TRUNKS, device=None, scope=ScopeType.SINGLE)
    with pytest.raises(ValueError, match="device name is required"):
        validate_request(req, INVENTORY)


# ── ALL scope ──────────────────────────────────────────────────────────────────

def test_valid_all_scope():
    req = _req(IntentType.HEALTH_CHECK, scope=ScopeType.ALL)
    validate_request(req, INVENTORY)  # sw-core-01 and sw-acc-02 have SSH enabled


def test_all_scope_no_ssh_enabled_devices():
    no_ssh_inv = {"sw-acc-01": INVENTORY["sw-acc-01"]}  # ssh_enabled=False
    req = _req(IntentType.HEALTH_CHECK, scope=ScopeType.ALL)
    with pytest.raises(ValueError, match="No SSH-enabled"):
        validate_request(req, no_ssh_inv)


# ── ROLE scope ─────────────────────────────────────────────────────────────────

def test_valid_role_scope():
    req = _req(IntentType.SHOW_VLANS, scope=ScopeType.ROLE, role="core")
    validate_request(req, INVENTORY)  # sw-core-01 is core and ssh_enabled


def test_role_scope_no_such_role():
    req = _req(IntentType.SHOW_VLANS, scope=ScopeType.ROLE, role="distribution")
    with pytest.raises(ValueError, match="No devices found with role"):
        validate_request(req, INVENTORY)


def test_role_scope_missing_role_name():
    req = _req(IntentType.SHOW_VLANS, scope=ScopeType.ROLE, role=None)
    with pytest.raises(ValueError, match="role name is required"):
        validate_request(req, INVENTORY)


def test_role_scope_no_ssh_enabled_devices_in_role():
    # access role: sw-acc-01 (ssh disabled), sw-acc-02 (ssh enabled) — should pass
    req = _req(IntentType.SHOW_VLANS, scope=ScopeType.ROLE, role="access")
    validate_request(req, INVENTORY)  # sw-acc-02 has SSH, should not raise


def test_role_scope_all_ssh_disabled():
    # Only sw-acc-01 with ssh disabled in access role
    inv = {"sw-acc-01": INVENTORY["sw-acc-01"]}
    req = _req(IntentType.SHOW_VLANS, scope=ScopeType.ROLE, role="access")
    with pytest.raises(ValueError, match="No SSH-enabled devices with role"):
        validate_request(req, inv)


# ── NON_SSH_INTENTS (diff_backup) ──────────────────────────────────────────────

def test_diff_backup_ssh_disabled_device_is_allowed():
    # diff_backup reads local files — ssh_enabled should not matter
    req = _req(IntentType.DIFF_BACKUP, device="sw-acc-01", scope=ScopeType.SINGLE)
    validate_request(req, INVENTORY)  # should NOT raise even though ssh_enabled=False


def test_diff_backup_all_scope_no_ssh_devices_is_allowed():
    no_ssh_inv = {"sw-acc-01": INVENTORY["sw-acc-01"]}
    req = _req(IntentType.DIFF_BACKUP, scope=ScopeType.ALL)
    validate_request(req, no_ssh_inv)  # should NOT raise


# ── PING ───────────────────────────────────────────────────────────────────────

def test_ping_valid():
    req = _req(IntentType.PING, device="sw-core-01", ping_target="10.0.0.1")
    validate_request(req, INVENTORY)  # should not raise


def test_ping_missing_target_raises():
    req = _req(IntentType.PING, device="sw-core-01", ping_target=None)
    with pytest.raises(ValueError, match="target IP"):
        validate_request(req, INVENTORY)
