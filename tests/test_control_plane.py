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
    from app import approval as approval_mod
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
    monkeypatch.setattr(approval_mod, "APPROVAL_STATE_DIR", tmp_path / "approvals")
    monkeypatch.setattr(approval_mod, "APPROVAL_SECRET_PATH", tmp_path / "approval_secret")


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
    assert write.risk == RiskLevel.BLOCKED
    assert write.allowed is False
    assert write.approval_required is False
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


def test_runner_blocks_write_before_execution(monkeypatch, tmp_path):
    _patch_artifact_paths(monkeypatch, tmp_path)
    monkeypatch.setattr("app.runner.load_inventory", lambda: (_ for _ in ()).throw(RuntimeError("executed")))

    result = run_request(
        original_request="add vlan 250",
        normalized_intent="add_vlan",
        params={"device": "sw-a-01", "scope": "single", "vlan_id": 250, "vlan_name": "TEST"},
    )

    assert result["success"] is False
    assert result["status"] == "blocked"
    assert result["approval_required"] is False
    assert result["execution_results"] == []
    assert Path(result["audit_path"]).exists()


def test_runner_legacy_approval_cannot_unlock_write(monkeypatch, tmp_path):
    _patch_artifact_paths(monkeypatch, tmp_path)
    monkeypatch.setattr("app.runner.load_inventory", lambda: (_ for _ in ()).throw(RuntimeError("executed")))

    result = run_request(
        original_request="add vlan 250",
        normalized_intent="add_vlan",
        params={"device": "sw-a-01", "scope": "single", "vlan_id": 250, "vlan_name": "TEST"},
        approval_received=True,
    )

    assert result["success"] is False
    assert result["status"] == "blocked"
    assert result["execution_results"] == []


def test_runner_receipt_cannot_unlock_write(monkeypatch, tmp_path):
    _patch_artifact_paths(monkeypatch, tmp_path)
    monkeypatch.setattr("app.runner.load_inventory", lambda: (_ for _ in ()).throw(RuntimeError("executed")))
    base_params = {"device": "sw-a-01", "scope": "single", "vlan_id": 250, "vlan_name": "TEST"}
    result = run_request(
        original_request="add vlan 250",
        normalized_intent="add_vlan",
        params=base_params,
        user="alice",
        source="test",
        approval_receipt={"receipt": "cannot-authorize-write"},
    )

    assert result["success"] is False
    assert result["status"] == "blocked"
    assert result["execution_results"] == []


def test_runner_blocks_external_probe_intent(monkeypatch, tmp_path):
    _patch_artifact_paths(monkeypatch, tmp_path)
    monkeypatch.setattr("app.runner.load_inventory", lambda: (_ for _ in ()).throw(RuntimeError("executed")))
    result = run_request(
        original_request="ping 8.8.8.8 from sw-a-01",
        normalized_intent="ping",
        params={"device": "sw-a-01", "scope": "single", "ping_target": "8.8.8.8"},
    )

    assert result["status"] == "blocked"
    assert result["execution_results"] == []


def test_runner_blocks_non_network_domain(monkeypatch, tmp_path):
    _patch_artifact_paths(monkeypatch, tmp_path)
    result = run_request(
        original_request="show vlans outside network domain",
        normalized_intent="show_vlans",
        params={"device": "sw-a-01", "scope": "single", "domain": "compute"},
    )

    assert result["success"] is False
    assert result["status"] == "blocked"
    assert result["execution_results"] == []


def test_runner_does_not_execute_write_even_with_injected_executor(monkeypatch, tmp_path):
    _patch_artifact_paths(monkeypatch, tmp_path)
    inventory = {
        "sw-a-01": Device(
            name="sw-a-01",
            hostname="sw-a-01",
            ip="192.0.2.20",
            platform="cisco_ios",
            role="access",
            ssh_enabled=True,
        )
    }
    job_result = JobResult(
        success=True,
        device="sw-a-01",
        intent="add_vlan",
        command_executed="vlan 250 / name TEST",
        parsed_data={"vlan_id": 250, "vlan_name": "TEST"},
    )
    params = {
        "device": "sw-a-01",
        "scope": "single",
        "vlan_id": 250,
        "vlan_name": "TEST",
        "_inventory_loader": lambda: inventory,
        "_validate_request": lambda req, inv: None,
        "_executor_execute": lambda req, inv: [job_result],
    }

    result = run_request(
        original_request="add vlan 250",
        normalized_intent="add_vlan",
        params=params,
        user="alice",
        source="test",
    )

    audit = json.loads(Path(result["audit_path"]).read_text())
    assert result["success"] is False
    assert result["status"] == "blocked"
    assert result["execution_results"] == []
    assert audit["final_status"] == "blocked"


def test_openclaw_telegram_formatting_is_concise():
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
