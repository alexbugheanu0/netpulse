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
}


def _make_req(intent: IntentType, device: str | None, scope: ScopeType) -> IntentRequest:
    return IntentRequest(
        intent=intent,
        device=device,
        scope=scope,
        raw_query="test",
    )


def test_valid_single_request():
    req = _make_req(IntentType.SHOW_VLANS, "sw-core-01", ScopeType.SINGLE)
    validate_request(req, INVENTORY)  # should not raise


def test_valid_all_scope():
    req = _make_req(IntentType.HEALTH_CHECK, None, ScopeType.ALL)
    validate_request(req, INVENTORY)  # sw-core-01 has ssh_enabled, should pass


def test_device_not_found():
    req = _make_req(IntentType.SHOW_VLANS, "sw-missing-99", ScopeType.SINGLE)
    with pytest.raises(ValueError, match="not found in inventory"):
        validate_request(req, INVENTORY)


def test_device_ssh_disabled():
    req = _make_req(IntentType.SHOW_VLANS, "sw-acc-01", ScopeType.SINGLE)
    with pytest.raises(ValueError, match="SSH disabled"):
        validate_request(req, INVENTORY)


def test_all_scope_no_ssh_enabled_devices():
    no_ssh_inv = {
        "sw-acc-01": INVENTORY["sw-acc-01"]  # ssh_enabled=False
    }
    req = _make_req(IntentType.HEALTH_CHECK, None, ScopeType.ALL)
    with pytest.raises(ValueError, match="No SSH-enabled"):
        validate_request(req, no_ssh_inv)


def test_missing_device_name_single_scope():
    req = _make_req(IntentType.SHOW_TRUNKS, None, ScopeType.SINGLE)
    with pytest.raises(ValueError, match="device name is required"):
        validate_request(req, INVENTORY)
