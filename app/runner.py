"""Unified lifecycle runner for NetPulse requests."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.adapters.cisco_ios import CiscoIOSAdapter, build_intent_request, is_write_intent
from app.adapters.compute_mock import ComputeMockAdapter
from app.adapters.instrument_mock import InstrumentMockAdapter
from app.adapters.storage_mock import StorageMockAdapter
from app.audit_log import (
    finish_audit,
    record_execution,
    record_postcheck,
    record_precheck,
    save_audit,
    start_audit,
)
from app.inventory import load_inventory
from app.models import JobResult
from app.planner import ExecutionPlan, build_plan, save_plan, serialize_plan
from app.risk import RiskDecision, RiskLevel, classify_intent


def run_request(
    original_request: str,
    normalized_intent: str,
    params: dict[str, Any],
    user: str | None = None,
    source: str | None = None,
    dry_run: bool = False,
    approval_received: bool = False,
) -> dict[str, Any]:
    """Run the full NetPulse lifecycle and return JSON-compatible output."""

    run_params = dict(params)
    run_params.setdefault("original_request", original_request)
    plan = build_plan(normalized_intent, run_params, user=user, source=source, dry_run=dry_run)
    risk_decision = classify_intent(normalized_intent, run_params)
    _apply_risk_to_plan(plan, risk_decision)

    audit = start_audit(plan, risk_decision)
    audit_path: Path | None = None
    plan_path: Path | None = None

    try:
        plan_path = save_plan(plan)
        record_precheck(audit, "plan_saved", {"path": str(plan_path)})
        record_precheck(audit, "risk_classification", risk_decision.model_dump())

        if not risk_decision.allowed or risk_decision.risk == RiskLevel.BLOCKED:
            final = finish_audit(
                audit,
                "blocked",
                errors=[risk_decision.reason],
                approval_received=approval_received,
            )
            audit_path = save_audit(final)
            return _response(
                success=False,
                status="blocked",
                plan=plan,
                risk_decision=risk_decision,
                plan_path=plan_path,
                audit_path=audit_path,
                error=risk_decision.reason,
            )

        if risk_decision.approval_required and not approval_received:
            final = finish_audit(audit, "approval_required", approval_received=False)
            audit_path = save_audit(final)
            return _response(
                success=False,
                status="approval_required",
                plan=plan,
                risk_decision=risk_decision,
                plan_path=plan_path,
                audit_path=audit_path,
                error="Approval is required before execution.",
            )

        if dry_run:
            final = finish_audit(audit, "dry_run", approval_received=approval_received)
            audit_path = save_audit(final)
            plan.final_status = "dry_run"
            return _response(
                success=True,
                status="dry_run",
                plan=plan,
                risk_decision=risk_decision,
                plan_path=plan_path,
                audit_path=audit_path,
                execution_results=[],
                verification=None,
            )

        execution_results = _execute_plan(plan, normalized_intent, run_params, risk_decision)
        for result in execution_results:
            record_execution(audit, result)

        verification = _verify_if_needed(plan, normalized_intent, run_params, execution_results)
        if verification is not None:
            record_postcheck(audit, verification)

        success = _all_success(execution_results) and (
            verification is None or bool(verification.get("verified"))
        )
        status = "success" if success else "failed"
        plan.final_status = status
        _mark_steps(plan, "completed" if success else "failed")

        errors = _collect_errors(execution_results)
        if verification and verification.get("error"):
            errors.append(str(verification["error"]))
        final = finish_audit(audit, status, errors=errors, approval_received=approval_received)
        audit_path = save_audit(final)
        return _response(
            success=success,
            status=status,
            plan=plan,
            risk_decision=risk_decision,
            plan_path=plan_path,
            audit_path=audit_path,
            execution_results=execution_results,
            verification=verification,
            error=None if success else "; ".join(errors) or "Execution failed.",
        )

    except Exception as exc:
        error_message = (
            f"Inventory file not found: {exc}."
            if isinstance(exc, FileNotFoundError)
            else str(exc)
        )
        plan.final_status = "failed"
        _mark_steps(plan, "failed")
        final = finish_audit(
            audit,
            "failed",
            errors=[error_message],
            approval_received=approval_received,
        )
        audit_path = save_audit(final)
        return _response(
            success=False,
            status="failed",
            plan=plan,
            risk_decision=risk_decision,
            plan_path=plan_path,
            audit_path=audit_path,
            error=error_message,
        )


def _execute_plan(
    plan: ExecutionPlan,
    intent: str,
    params: dict[str, Any],
    risk_decision: RiskDecision,
) -> list[Any]:
    if intent in {"prepare_lab_environment", "prepare_experiment_environment"}:
        return _execute_genesis_demo(plan, params)

    if plan.domain == "network":
        inventory = _load_inventory(params)
        injected_validate = params.get("_validate_request")
        injected_execute = params.get("_executor_execute")
        if injected_validate or injected_execute:
            req = build_intent_request(intent, params)
            if injected_validate:
                injected_validate(req, inventory)
            if injected_execute:
                return injected_execute(req, inventory)
        adapter = CiscoIOSAdapter(inventory)
        if is_write_intent(intent):
            return adapter.execute_write(intent, params)
        return adapter.execute_read(intent, params)

    adapter = _mock_adapter(plan.domain)
    if risk_decision.approval_required:
        return [adapter.execute_write(intent, params)]
    return [adapter.execute_read(intent, params)]


def _verify_if_needed(
    plan: ExecutionPlan,
    intent: str,
    params: dict[str, Any],
    execution_results: list[Any],
) -> dict[str, Any] | None:
    if intent in {"prepare_lab_environment", "prepare_experiment_environment"}:
        success = _all_success(execution_results)
        return {
            "verified": success,
            "checks": ["mock_network", "mock_compute", "mock_storage", "mock_instrument"],
            "evidence": "All demo readiness checks passed." if success else execution_results,
            "error": None if success else "demo_readiness_failed",
        }

    if plan.domain != "network" or not is_write_intent(intent):
        return None

    inventory = _load_inventory(params)
    return CiscoIOSAdapter(inventory).verify(intent, params, execution_results)  # type: ignore[arg-type]


def _load_inventory(params: dict[str, Any]) -> dict[str, Any]:
    if params.get("_inventory") is not None:
        return params["_inventory"]
    loader = params.get("_inventory_loader") or load_inventory
    return loader()


def _execute_genesis_demo(plan: ExecutionPlan, params: dict[str, Any]) -> list[dict[str, Any]]:
    compute = ComputeMockAdapter()
    storage = StorageMockAdapter()
    instrument = InstrumentMockAdapter()
    results: list[dict[str, Any]] = []

    for step in plan.steps:
        if step.action == "check_network_path":
            result = {
                "success": True,
                "adapter": "cisco_ios",
                "intent": step.action,
                "summary": "Mock network path is reachable for simulation job demo-001.",
                "parsed_data": {"path": "lab-net/demo-001", "reachable": True},
            }
        elif step.adapter == "compute_mock":
            if step.action == "allocate_simulation_nodes":
                result = compute.execute_write(step.action, params)
            else:
                result = compute.execute_read(step.action, params)
        elif step.adapter == "storage_mock":
            result = storage.execute_read(step.action, params)
        elif step.adapter == "instrument_mock":
            if step.action == "prepare_instrument_mock":
                result = instrument.execute_write(step.action, params)
            else:
                result = instrument.execute_read(step.action, params)
        else:
            result = {
                "success": True,
                "adapter": step.adapter,
                "intent": step.action,
                "summary": "Mock environment verification passed.",
                "parsed_data": {"verified": True},
            }
        step.status = "completed" if result.get("success") else "failed"
        results.append(result)

    return results


def _mock_adapter(domain: str) -> Any:
    if domain == "compute":
        return ComputeMockAdapter()
    if domain == "storage":
        return StorageMockAdapter()
    if domain == "instrument":
        return InstrumentMockAdapter()
    raise ValueError(f"No adapter registered for domain '{domain}'.")


def _apply_risk_to_plan(plan: ExecutionPlan, risk_decision: RiskDecision) -> None:
    plan.risk_summary = risk_decision.reason
    plan.approval_required = risk_decision.approval_required
    for step in plan.steps:
        step.risk = risk_decision.risk.value
        step.requires_approval = risk_decision.approval_required


def _mark_steps(plan: ExecutionPlan, status: str) -> None:
    for step in plan.steps:
        if step.status == "planned":
            step.status = status


def _all_success(results: list[Any]) -> bool:
    for result in results:
        if isinstance(result, JobResult):
            if not result.success:
                return False
        elif isinstance(result, dict):
            if not result.get("success"):
                return False
        else:
            return False
    return True


def _collect_errors(results: list[Any]) -> list[str]:
    errors: list[str] = []
    for result in results:
        if isinstance(result, JobResult) and result.error:
            errors.append(result.error)
        elif isinstance(result, dict) and result.get("error"):
            errors.append(str(result["error"]))
    return errors


def _response(
    *,
    success: bool,
    status: str,
    plan: ExecutionPlan,
    risk_decision: RiskDecision,
    plan_path: Path | None,
    audit_path: Path | None,
    execution_results: list[Any] | None = None,
    verification: dict[str, Any] | None = None,
    error: str | None = None,
) -> dict[str, Any]:
    return {
        "success": success,
        "status": status,
        "request_id": plan.request_id,
        "intent": plan.normalized_intent,
        "domain": plan.domain,
        "plan": serialize_plan(plan),
        "risk_decision": risk_decision.model_dump(),
        "approval_required": risk_decision.approval_required,
        "plan_path": str(plan_path) if plan_path else None,
        "audit_path": str(audit_path) if audit_path else None,
        "execution_results": _jsonable(execution_results or []),
        "verification": _jsonable(verification),
        "error": error,
    }


def _jsonable(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    return value
