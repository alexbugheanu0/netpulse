from __future__ import annotations

import json
from pathlib import Path

from app.audit_log import finish_audit, save_audit, start_audit
from app.models import Device, JobResult
from app.planner import build_plan, serialize_plan
from app.risk import RiskLevel, classify_intent
from app.runner import run_request
from demos.genesis_style.run_demo import audit_summary, build_plan_preview, run_demo


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


def test_risk_blocks_unknown_read_like_intents():
    decision = classify_intent("check_reload_status_and_fix", {})

    assert decision.risk == RiskLevel.BLOCKED
    assert decision.allowed is False


def test_mock_write_intent_requires_approval_by_default():
    decision = classify_intent(
        "prepare_instrument_mock",
        {"domain": "instrument"},
        ssot={"protected_vlans": [], "protected_devices": [], "protected_interfaces": []},
    )

    assert decision.risk == RiskLevel.LOW_CHANGE
    assert decision.approval_required is True
    assert decision.allowed is True


def test_genesis_normal_demo_is_read_only():
    decision = classify_intent("prepare_lab_environment", {"domain": "lab"})

    assert decision.risk == RiskLevel.READ_ONLY
    assert decision.approval_required is False
    assert decision.reason == "Demo readiness checks only; no real infrastructure changes executed."


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


def test_runner_saves_audit_when_plan_save_fails(monkeypatch, tmp_path):
    from app import audit_log as audit_mod

    monkeypatch.setattr("app.runner.save_plan", lambda plan: (_ for _ in ()).throw(RuntimeError("disk full")))
    monkeypatch.setattr("app.runner.save_audit", lambda audit: audit_mod.save_audit(audit, tmp_path / "audit"))

    result = run_request(
        original_request="show vlans",
        normalized_intent="show_vlans",
        params={"device": "sw-core-01", "scope": "single"},
    )

    assert result["success"] is False
    assert result["status"] == "failed"
    assert result["plan_path"] is None
    assert Path(result["audit_path"]).exists()


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


def test_runner_validation_failure_still_writes_audit(monkeypatch, tmp_path):
    _patch_artifact_paths(monkeypatch, tmp_path)
    monkeypatch.setattr("app.runner.load_inventory", lambda: {})

    result = run_request(
        original_request="show vlans on missing switch",
        normalized_intent="show_vlans",
        params={"device": "sw-missing-01", "scope": "single"},
    )

    assert result["success"] is False
    assert result["status"] == "failed"
    assert "not found in inventory" in result["error"]
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
    monkeypatch.setattr("app.runner.load_inventory", lambda: (_ for _ in ()).throw(RuntimeError("real inventory used")))

    result = run_request(
        original_request="Prepare the lab environment for simulation job demo-001.",
        normalized_intent="prepare_lab_environment",
        params={"domain": "lab", "job_id": "demo-001"},
        source="test",
    )

    assert result["success"] is True
    assert result["status"] == "success"
    assert result["risk_decision"]["risk"] == "READ_ONLY"
    assert result["approval_required"] is False
    assert result["verification"]["verified"] is True
    assert len(result["execution_results"]) >= 4


def test_genesis_dry_run_does_not_execute_adapters(monkeypatch, tmp_path):
    _patch_artifact_paths(monkeypatch, tmp_path)
    monkeypatch.setattr("app.runner._execute_genesis_demo", lambda plan, params: (_ for _ in ()).throw(RuntimeError("executed")))

    result = run_demo(dry_run=True)
    audit = json.loads(Path(result["audit_path"]).read_text())

    assert result["status"] == "dry_run"
    assert result["execution_results"] == []
    assert audit["final_status"] == "dry_run"
    assert audit["duration_ms"] is not None


def test_genesis_simulated_write_without_approval_is_gated(monkeypatch, tmp_path):
    _patch_artifact_paths(monkeypatch, tmp_path)
    monkeypatch.setattr("app.runner._execute_genesis_demo", lambda plan, params: (_ for _ in ()).throw(RuntimeError("executed")))

    result = run_demo(simulate_write=True)
    audit = json.loads(Path(result["audit_path"]).read_text())

    assert result["success"] is False
    assert result["status"] == "approval_required"
    assert result["risk_decision"]["risk"] == "LOW_CHANGE"
    assert result["approval_required"] is True
    assert result["execution_results"] == []
    assert audit["final_status"] == "approval_required"
    assert audit["approval_received"] is False


def test_genesis_simulated_write_with_approval_executes_and_verifies(monkeypatch, tmp_path):
    _patch_artifact_paths(monkeypatch, tmp_path)

    result = run_demo(simulate_write=True, approve=True)
    audit = json.loads(Path(result["audit_path"]).read_text())

    assert result["success"] is True
    assert result["status"] == "success"
    assert result["risk_decision"]["risk"] == "LOW_CHANGE"
    assert result["approval_required"] is True
    assert result["verification"]["verified"] is True
    assert any(item["intent"] == "allocate_simulation_nodes" for item in result["execution_results"])
    assert any(item["intent"] == "prepare_instrument_mock" for item in result["execution_results"])
    assert audit["final_status"] == "success"
    assert audit["approval_received"] is True
    assert audit["verification"]["verified"] is True
    assert audit["duration_ms"] is not None


def test_genesis_audit_artifact_contains_required_fields(monkeypatch, tmp_path):
    _patch_artifact_paths(monkeypatch, tmp_path)

    result = run_demo()
    audit = json.loads(Path(result["audit_path"]).read_text())

    for field in {
        "request_id",
        "timestamp",
        "original_request",
        "normalized_intent",
        "plan",
        "risk_decision",
        "approval_required",
        "approval_received",
        "execution_results",
        "verification",
        "postchecks",
        "final_status",
        "duration_ms",
        "errors",
    }:
        assert field in audit


def test_genesis_plan_preview_matches_actual_plan(monkeypatch, tmp_path):
    _patch_artifact_paths(monkeypatch, tmp_path)

    result = run_demo()
    preview = build_plan_preview(result)

    assert preview["request_id"] == result["request_id"]
    assert preview["intent"] == result["plan"]["normalized_intent"]
    assert preview["risk"] == result["risk_decision"]["risk"]
    assert preview["approval_required"] == result["approval_required"]
    assert preview["steps"] == [step["action"] for step in result["plan"]["steps"]]


def test_genesis_audit_summary_reads_saved_artifact(monkeypatch, tmp_path):
    _patch_artifact_paths(monkeypatch, tmp_path)

    result = run_demo()
    summary = audit_summary(result)

    assert summary["request_id"] == result["request_id"]
    assert summary["final_status"] == "success"
    assert summary["approval_required"] is False
    assert summary["approval_received"] is False
    assert summary["verification"] == "passed"
    assert summary["duration_ms"] is not None


def test_openclaw_telegram_formatting_has_no_genesis_demo_text():
    from app.openclaw_adapter import _telegram_response, OpenClawResponse

    response = OpenClawResponse(
        success=True,
        intent="show_vlans",
        scope="single",
        results=[],
        status="success",
        request_id="np-test",
        audit_path="output/audit/test.json",
    )

    payload = _telegram_response(response)
    rendered = json.dumps(payload)

    assert "Genesis" not in rendered
    assert "Dry run enabled" not in rendered
    assert "Approval received" not in rendered
    assert "Verification passed" not in rendered


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
