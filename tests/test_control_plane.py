from __future__ import annotations

import json
from pathlib import Path

from app.audit_log import finish_audit, save_audit, start_audit
from app.models import Device, JobResult
from app.planner import build_plan, serialize_plan
from app.risk import RiskLevel, classify_intent
from app.runner import run_request


def _patch_artifact_paths(monkeypatch, tmp_path: Path) -> None:
    from app import audit_log as audit_mod
    from app import planner as planner_mod
    from app import runner as runner_mod

    monkeypatch.setattr(
        runner_mod,
        "save_plan",
        lambda plan: planner_mod.save_plan(plan, tmp_path / "plans"),
    )
    monkeypatch.setattr(
        runner_mod,
        "save_audit",
        lambda audit: audit_mod.save_audit(audit, tmp_path / "audit"),
    )


def test_planner_creates_valid_plan():
    plan = build_plan(
        "show_vlans",
        {"device": "sw-core-01", "scope": "single", "raw_query": "show vlans"},
        user="alice",
        source="test",
    )

    data = serialize_plan(plan)
    assert data["request_id"].startswith("np-")
    assert data["normalized_intent"] == "show_vlans"
    assert data["domain"] == "network"
    assert data["steps"][0]["adapter"] == "cisco_ios"
    assert data["steps"][0]["command_preview"] == "show vlan brief"


def test_risk_classification_read_write_and_blocked():
    read = classify_intent("show_vlans", {})
    write = classify_intent(
        "add_vlan",
        {"device": "sw-a-01", "vlan_id": 250, "vlan_name": "TEST"},
        ssot={"protected_vlans": [], "protected_devices": [], "protected_interfaces": []},
    )
    blocked = classify_intent("configure terminal ; reload", {})

    assert read.risk == RiskLevel.READ_ONLY
    assert read.approval_required is False
    assert write.risk == RiskLevel.LOW_CHANGE
    assert write.approval_required is True
    assert blocked.risk == RiskLevel.BLOCKED
    assert blocked.allowed is False


def test_risk_classification_protected_vlan_blocks_remove():
    decision = classify_intent(
        "remove_vlan",
        {"vlan_id": 10},
        ssot={"protected_vlans": [{"id": 10, "reason": "management"}]},
    )

    assert decision.risk == RiskLevel.BLOCKED
    assert decision.allowed is False


def test_audit_artifact_is_written(tmp_path):
    plan = build_plan("show_vlans", {"device": "sw-core-01"})
    risk = classify_intent("show_vlans", {})
    audit = start_audit(plan, risk)
    finish_audit(audit, "success")

    path = save_audit(audit, tmp_path)
    data = json.loads(path.read_text())

    assert path.exists()
    assert data["request_id"] == plan.request_id
    assert data["final_status"] == "success"


def test_runner_dry_run_does_not_execute(monkeypatch, tmp_path):
    _patch_artifact_paths(monkeypatch, tmp_path)
    monkeypatch.setattr("app.runner.load_inventory", lambda: (_ for _ in ()).throw(RuntimeError("executed")))

    result = run_request(
        original_request="show vlans",
        normalized_intent="show_vlans",
        params={"device": "sw-core-01", "scope": "single"},
        dry_run=True,
    )

    assert result["success"] is True
    assert result["status"] == "dry_run"
    assert result["execution_results"] == []
    assert Path(result["audit_path"]).exists()


def test_runner_requires_approval_before_write_execution(monkeypatch, tmp_path):
    _patch_artifact_paths(monkeypatch, tmp_path)
    monkeypatch.setattr("app.runner.load_inventory", lambda: (_ for _ in ()).throw(RuntimeError("executed")))

    result = run_request(
        original_request="add vlan 250",
        normalized_intent="add_vlan",
        params={"device": "sw-a-01", "scope": "single", "vlan_id": 250, "vlan_name": "TEST"},
    )

    assert result["success"] is False
    assert result["status"] == "approval_required"
    assert result["approval_required"] is True
    assert result["execution_results"] == []


def test_genesis_demo_intent_completes_successfully(monkeypatch, tmp_path):
    _patch_artifact_paths(monkeypatch, tmp_path)

    result = run_request(
        original_request="Prepare the lab environment for simulation job demo-001.",
        normalized_intent="prepare_lab_environment",
        params={"domain": "lab", "job_id": "demo-001"},
        source="test",
    )

    assert result["success"] is True
    assert result["status"] == "success"
    assert result["verification"]["verified"] is True
    assert len(result["execution_results"]) >= 4


def test_cisco_supported_intent_routes_through_adapter(monkeypatch, tmp_path):
    _patch_artifact_paths(monkeypatch, tmp_path)
    inventory = {
        "sw-core-01": Device(
            name="sw-core-01",
            hostname="sw-core-01",
            ip="192.0.2.10",
            platform="cisco_ios",
            role="core",
            ssh_enabled=True,
        )
    }
    job_result = JobResult(
        success=True,
        device="sw-core-01",
        intent="show_vlans",
        command_executed="show vlan brief",
        parsed_data=[{"vlan_id": "1", "name": "default", "status": "active"}],
    )

    monkeypatch.setattr("app.runner.load_inventory", lambda: inventory)
    monkeypatch.setattr("app.adapters.cisco_ios.validate_request", lambda req, inv: None)
    monkeypatch.setattr("app.adapters.cisco_ios.executor.execute", lambda req, inv: [job_result])

    result = run_request(
        original_request="show vlans on sw-core-01",
        normalized_intent="show_vlans",
        params={"device": "sw-core-01", "scope": "single"},
    )

    assert result["success"] is True
    assert result["execution_results"][0]["intent"] == "show_vlans"
    assert result["execution_results"][0]["command_executed"] == "show vlan brief"
