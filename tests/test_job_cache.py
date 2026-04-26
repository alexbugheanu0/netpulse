"""Tests for short-lived caches used by expensive read-only jobs."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from app.jobs.device_facts import run as run_device_facts
from app.jobs.health_check import run as run_health_check
from app.jobs.show_vlans import run as run_show_vlans
from app.jobs._job_cache import clear_job_cache
from app.models import Device


DEVICE = Device(
    name="sw-core-01",
    hostname="sw-core-01.lab.local",
    ip="192.168.100.11",
    platform="cisco_ios",
    role="core",
    ssh_enabled=True,
)


@pytest.fixture(autouse=True)
def _clear_cache():
    clear_job_cache()
    yield
    clear_job_cache()


def test_health_check_reuses_cached_result():
    collected = {
        "version": {"software": "Cisco IOS Software, Version 15.2(4)E8", "uptime": "sw-core-01 uptime is 12 weeks"},
        "interfaces": [{"port": "Gi0/1", "status": "connected"}],
        "vlans": [{"vlan_id": "1", "name": "default"}],
    }

    with patch("app.jobs.health_check.collect_with_fallback", return_value=(collected, [])) as mock_collect:
        first = run_health_check(DEVICE)
        second = run_health_check(DEVICE)

    assert mock_collect.call_count == 1
    assert first.model_dump() == second.model_dump()
    assert first.success is True


def test_device_facts_reuses_cached_result():
    collected = {
        "version": {"software": "Cisco IOS Software, Version 15.2(4)E8", "uptime": "sw-core-01 uptime is 12 weeks"},
        "interfaces": [{"port": "Gi0/1", "status": "connected"}],
    }

    with patch("app.jobs.device_facts.collect_with_fallback", return_value=(collected, [])) as mock_collect:
        first = run_device_facts(DEVICE)
        second = run_device_facts(DEVICE)

    assert mock_collect.call_count == 1
    assert first.model_dump() == second.model_dump()
    assert first.success is True


def test_show_vlans_reuses_cached_result():
    raw = "1 default active\n10 MGMT active\n"

    with patch("app.jobs.show_vlans.run_command", return_value=raw) as mock_run:
        first = run_show_vlans(DEVICE)
        second = run_show_vlans(DEVICE)

    assert mock_run.call_count == 1
    assert first.model_dump() == second.model_dump()
    assert first.success is True
