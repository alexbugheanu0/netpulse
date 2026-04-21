"""Unit tests for request validation."""

import pytest
from unittest.mock import patch

from app.models import Device, IntentRequest, IntentType, ScopeType
from app.ssot import ProtectedResources
from app.validators import policy_check, validate_request

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


# ── policy_check() ─────────────────────────────────────────────────────────────
# All tests use a minimal ProtectedResources fixture injected via mock so they
# do not depend on the live ssot/ YAML files on disk.

_PROTECTED = ProtectedResources(
    protected_vlans=[
        {"id": "10", "name": "MGMT",    "reason": "Management plane"},
        {"id": "1",  "name": "default", "reason": "Native VLAN"},
    ],
    protected_devices=[
        {
            "name": "sw-core-01",
            "role": "core",
            "reason": "Core switch",
            "extra_rules": [
                "shutdown_interface always requires approval on this device regardless of interface type"
            ],
        }
    ],
    protected_interfaces=[
        {
            "device": "sw-core-01",
            "interfaces": ["Gi1/0/1", "Gi1/0/2"],
            "reason": "Uplinks to distribution layer",
        }
    ],
)


def _write_req(intent: IntentType, device="sw-acc-02", **kwargs):
    """Build a write IntentRequest defaulting to a non-protected device."""
    return IntentRequest(
        intent=intent,
        device=device,
        scope=ScopeType.SINGLE,
        raw_query="test",
        **kwargs,
    )


def _patch_protected():
    return patch("app.validators.load_protected_resources", return_value=_PROTECTED)


def test_policy_check_blocks_remove_protected_vlan():
    """remove_vlan on VLAN 10 (MGMT) must be rejected."""
    req = _write_req(IntentType.REMOVE_VLAN, vlan_id=10)
    with _patch_protected(), pytest.raises(ValueError, match="protected resource"):
        policy_check(req)


def test_policy_check_blocks_remove_native_vlan():
    """remove_vlan on VLAN 1 (default / native) must be rejected."""
    req = _write_req(IntentType.REMOVE_VLAN, vlan_id=1)
    with _patch_protected(), pytest.raises(ValueError, match="protected resource"):
        policy_check(req)


def test_policy_check_allows_remove_non_protected_vlan():
    """remove_vlan on a VLAN not in protected_vlans must pass."""
    req = _write_req(IntentType.REMOVE_VLAN, vlan_id=50)
    with _patch_protected():
        policy_check(req)  # should not raise


def test_policy_check_blocks_shutdown_on_protected_device():
    """shutdown_interface on sw-core-01 is forbidden by extra_rules."""
    req = _write_req(
        IntentType.SHUTDOWN_INTERFACE,
        device="sw-core-01",
        interface="Gi1/0/5",
    )
    with _patch_protected(), pytest.raises(ValueError, match="unconditionally forbidden"):
        policy_check(req)


def test_policy_check_allows_shutdown_on_non_protected_device():
    """shutdown_interface on an access switch not in protected_devices must pass."""
    req = _write_req(
        IntentType.SHUTDOWN_INTERFACE,
        device="sw-acc-02",
        interface="Gi1/0/5",
    )
    with _patch_protected():
        policy_check(req)  # should not raise


def test_policy_check_blocks_write_on_protected_interface():
    """set_interface_vlan targeting a protected uplink (Gi1/0/1 on sw-core-01) must be rejected."""
    req = _write_req(
        IntentType.SET_INTERFACE_VLAN,
        device="sw-core-01",
        interface="Gi1/0/1",
        vlan_id=30,
    )
    with _patch_protected(), pytest.raises(ValueError, match="protected resource"):
        policy_check(req)


def test_policy_check_blocks_no_shutdown_on_protected_interface():
    """no_shutdown_interface on a protected uplink must be rejected."""
    req = _write_req(
        IntentType.NO_SHUTDOWN_INTERFACE,
        device="sw-core-01",
        interface="Gi1/0/2",
    )
    with _patch_protected(), pytest.raises(ValueError, match="protected resource"):
        policy_check(req)


def test_policy_check_allows_interface_op_on_non_protected_interface():
    """Interface op on a port not in protected_interfaces must pass."""
    req = _write_req(
        IntentType.SET_INTERFACE_VLAN,
        device="sw-core-01",
        interface="Gi1/0/10",
        vlan_id=30,
    )
    with _patch_protected():
        policy_check(req)  # should not raise


def test_policy_check_allows_add_vlan_on_non_protected_resources():
    """add_vlan has no per-VLAN protection for new VLANs — must pass."""
    req = _write_req(IntentType.ADD_VLAN, vlan_id=50, vlan_name="TEST")
    with _patch_protected():
        policy_check(req)  # should not raise


def test_policy_check_error_message_names_resource_and_reason():
    """Error message must identify the VLAN, name, and reason from the YAML."""
    req = _write_req(IntentType.REMOVE_VLAN, vlan_id=10)
    with _patch_protected():
        with pytest.raises(ValueError) as exc_info:
            policy_check(req)
    msg = str(exc_info.value)
    assert "10" in msg
    assert "MGMT" in msg
    assert "Management plane" in msg


def test_policy_check_fails_closed_when_protected_resources_missing():
    """When protected-resources.yaml is missing, policy_check must raise ValueError (fail closed)."""
    req = _write_req(IntentType.REMOVE_VLAN, vlan_id=10)
    with patch("app.validators.load_protected_resources",
               side_effect=FileNotFoundError("not found")):
        with pytest.raises(ValueError, match="Cannot load ssot/protected-resources.yaml"):
            policy_check(req)


def test_policy_check_fails_closed_when_protected_resources_malformed():
    """When protected-resources.yaml is malformed, policy_check must raise ValueError (fail closed)."""
    req = _write_req(IntentType.ADD_VLAN, vlan_id=50, vlan_name="TEST")
    with patch("app.validators.load_protected_resources",
               side_effect=ValueError("bad yaml")):
        with pytest.raises(ValueError, match="Cannot load ssot/protected-resources.yaml"):
            policy_check(req)


def test_validate_request_calls_policy_check_for_write_intents():
    """validate_request() must invoke policy_check() for write intents."""
    req = IntentRequest(
        intent=IntentType.REMOVE_VLAN,
        device="sw-core-01",
        scope=ScopeType.SINGLE,
        vlan_id=10,
        raw_query="test",
    )
    # policy_check raises for protected VLAN 10 — confirms it was called.
    with _patch_protected(), pytest.raises(ValueError, match="protected resource"):
        validate_request(req, INVENTORY)


def test_validate_request_does_not_call_policy_check_for_read_intents():
    """validate_request() must NOT invoke policy_check() for read-only intents."""
    req = _req(IntentType.SHOW_VLANS, device="sw-core-01")
    # Even if load_protected_resources would raise, read intents must not trigger it.
    with patch("app.validators.load_protected_resources",
               side_effect=RuntimeError("should not be called")):
        validate_request(req, INVENTORY)  # should not raise


# ── ping_target IP validation ──────────────────────────────────────────────────

def _ping_req(target: str) -> IntentRequest:
    return IntentRequest(
        intent=IntentType.PING,
        device="sw-core-01",
        scope=ScopeType.SINGLE,
        ping_target=target,
        raw_query="test",
    )


def test_ping_valid_unicast_ipv4():
    """A normal unicast IPv4 address must pass validation."""
    validate_request(_ping_req("10.0.0.1"), INVENTORY)  # should not raise


def test_ping_valid_unicast_ipv6():
    """A normal unicast IPv6 address must pass validation."""
    validate_request(_ping_req("2001:db8::1"), INVENTORY)  # should not raise


def test_ping_invalid_string_rejected():
    """A non-IP string must be rejected."""
    with pytest.raises(ValueError, match="not a valid IP address"):
        validate_request(_ping_req("not-an-ip"), INVENTORY)


def test_ping_broadcast_ipv4_rejected():
    """The IPv4 broadcast address must be rejected."""
    with pytest.raises(ValueError, match="broadcast or multicast"):
        validate_request(_ping_req("255.255.255.255"), INVENTORY)


def test_ping_multicast_ipv4_rejected():
    """A multicast IPv4 address must be rejected."""
    with pytest.raises(ValueError, match="broadcast or multicast"):
        validate_request(_ping_req("224.0.0.1"), INVENTORY)


def test_ping_unspecified_address_rejected():
    """The unspecified address (0.0.0.0) must be rejected."""
    with pytest.raises(ValueError, match="broadcast or multicast"):
        validate_request(_ping_req("0.0.0.0"), INVENTORY)


# ── VLAN ID range validation ───────────────────────────────────────────────────

def _vlan_req(intent: IntentType, vlan_id: int, vlan_name: str = "TEST") -> IntentRequest:
    return IntentRequest(
        intent=intent,
        device="sw-core-01",
        scope=ScopeType.SINGLE,
        vlan_id=vlan_id,
        vlan_name=vlan_name if intent == IntentType.ADD_VLAN else None,
        raw_query="test",
    )


def test_vlan_id_zero_rejected():
    """VLAN ID 0 is invalid and must be rejected."""
    with _patch_protected(), pytest.raises(ValueError, match="out of range"):
        validate_request(_vlan_req(IntentType.ADD_VLAN, 0), INVENTORY)


def test_vlan_id_negative_rejected():
    """Negative VLAN IDs must be rejected."""
    with _patch_protected(), pytest.raises(ValueError, match="out of range"):
        validate_request(_vlan_req(IntentType.REMOVE_VLAN, -1), INVENTORY)


def test_vlan_id_4095_rejected():
    """VLAN ID 4095 exceeds the valid range and must be rejected."""
    with _patch_protected(), pytest.raises(ValueError, match="out of range"):
        validate_request(_vlan_req(IntentType.ADD_VLAN, 4095), INVENTORY)


def test_vlan_id_1_accepted():
    """VLAN ID 1 is the minimum valid value."""
    with _patch_protected():
        validate_request(_vlan_req(IntentType.ADD_VLAN, 1, "DEFAULT"), INVENTORY)  # should not raise


def test_vlan_id_4094_accepted():
    """VLAN ID 4094 is the maximum valid value."""
    with _patch_protected():
        validate_request(_vlan_req(IntentType.ADD_VLAN, 4094, "LAST"), INVENTORY)  # should not raise
