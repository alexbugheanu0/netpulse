"""Unit tests for the intent parser."""

import pytest

from app.intents import parse_intent
from app.models import IntentType, ScopeType


def test_parse_show_trunks():
    req = parse_intent("show trunk status on sw-dist-01")
    assert req.intent == IntentType.SHOW_TRUNKS
    assert req.device == "sw-dist-01"
    assert req.scope == ScopeType.SINGLE


def test_parse_show_vlans():
    req = parse_intent("show vlan on sw-core-01")
    assert req.intent == IntentType.SHOW_VLANS
    assert req.device == "sw-core-01"
    assert req.scope == ScopeType.SINGLE


def test_parse_show_interfaces():
    req = parse_intent("show interfaces on sw-acc-01")
    assert req.intent == IntentType.SHOW_INTERFACES
    assert req.device == "sw-acc-01"


def test_parse_show_version():
    req = parse_intent("show version on sw-core-01")
    assert req.intent == IntentType.SHOW_VERSION
    assert req.device == "sw-core-01"


def test_parse_backup_config():
    req = parse_intent("backup running config from sw-acc-02")
    assert req.intent == IntentType.BACKUP_CONFIG
    assert req.device == "sw-acc-02"
    assert req.confirmation_required is True


def test_parse_health_check_single():
    req = parse_intent("health check sw-dist-01")
    assert req.intent == IntentType.HEALTH_CHECK
    assert req.device == "sw-dist-01"
    assert req.scope == ScopeType.SINGLE


def test_parse_health_check_all():
    req = parse_intent("health check all switches")
    assert req.intent == IntentType.HEALTH_CHECK
    assert req.scope == ScopeType.ALL
    assert req.device is None


def test_parse_all_scope_overrides_device():
    req = parse_intent("show vlans on all switches")
    assert req.scope == ScopeType.ALL


def test_parse_unknown_query_raises():
    with pytest.raises(ValueError, match="Could not match"):
        parse_intent("do something weird on sw-core-01")


def test_parse_missing_device_raises():
    with pytest.raises(ValueError, match="No device name"):
        parse_intent("show vlan without a device")
