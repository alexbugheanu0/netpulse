"""Unit tests for the shared execution engine."""

from __future__ import annotations

from unittest.mock import patch

from app.executor import execute
from app.models import Device, IntentRequest, IntentType, JobResult, ScopeType


def _inventory() -> dict[str, Device]:
    return {
        "sw-a-01": Device(
            name="sw-a-01",
            hostname="sw-a-01.lab.local",
            ip="192.168.10.1",
            platform="cisco_ios",
            role="access",
            ssh_enabled=True,
        ),
        "sw-a-02": Device(
            name="sw-a-02",
            hostname="sw-a-02.lab.local",
            ip="192.168.10.2",
            platform="cisco_ios",
            role="access",
            ssh_enabled=True,
        ),
    }


def test_execute_preserves_device_order_for_multi_device_scope():
    req = IntentRequest(
        intent=IntentType.SHOW_VLANS,
        scope=ScopeType.ALL,
        raw_query="test",
    )

    def fake_job(device: Device) -> JobResult:
        return JobResult(
            success=True,
            device=device.name,
            intent="show_vlans",
            command_executed="show vlan brief",
        )

    with patch("app.executor.JOB_MAP", {IntentType.SHOW_VLANS: fake_job}):
        results = execute(req, _inventory())

    assert [r.device for r in results] == ["sw-a-01", "sw-a-02"]


def test_execute_turns_job_exception_into_failure_result():
    req = IntentRequest(
        intent=IntentType.SHOW_VLANS,
        scope=ScopeType.SINGLE,
        device="sw-a-01",
        raw_query="test",
    )

    def boom(device: Device) -> JobResult:
        raise RuntimeError("boom")

    with patch("app.executor.JOB_MAP", {IntentType.SHOW_VLANS: boom}):
        results = execute(req, _inventory())

    assert len(results) == 1
    result = results[0]
    assert result.success is False
    assert result.device == "sw-a-01"
    assert result.intent == "show_vlans"
    assert "boom" in (result.error or "").lower()
    assert result.elapsed_ms is not None
