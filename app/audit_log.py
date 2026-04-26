"""JSON audit artifacts for NetPulse execution requests."""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.planner import ExecutionPlan, serialize_plan
from app.risk import RiskDecision


AUDIT_OUTPUT_DIR = Path("output/audit")


def start_audit(plan: ExecutionPlan, risk_decision: RiskDecision) -> dict[str, Any]:
    """Create an audit object before any execution occurs."""

    return {
        "_started_monotonic": time.monotonic(),
        "request_id": plan.request_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "user": plan.user,
        "source": plan.source,
        "original_request": plan.original_request,
        "normalized_intent": plan.normalized_intent,
        "domain": plan.domain,
        "devices": _targets_from_plan(plan),
        "targets": _targets_from_plan(plan),
        "plan": serialize_plan(plan),
        "risk_decision": risk_decision.model_dump(),
        "approval_required": risk_decision.approval_required,
        "approval_received": False,
        "prechecks": [],
        "execution_results": [],
        "postchecks": [],
        "final_status": "started",
        "errors": [],
        "duration_ms": None,
    }


def record_precheck(audit: dict[str, Any], name: str, result: Any, status: str = "ok") -> None:
    """Append a structured precheck record."""

    audit.setdefault("prechecks", []).append({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "name": name,
        "status": status,
        "result": result,
    })


def record_execution(audit: dict[str, Any], result: Any) -> None:
    """Append an execution result, converting Pydantic objects when needed."""

    audit.setdefault("execution_results", []).append(_jsonable(result))


def record_postcheck(audit: dict[str, Any], result: Any) -> None:
    """Append a post-change verification result."""

    audit.setdefault("postchecks", []).append(_jsonable(result))


def finish_audit(
    audit: dict[str, Any],
    final_status: str,
    errors: list[str] | None = None,
    approval_received: bool | None = None,
) -> dict[str, Any]:
    """Finalize an audit object with status, duration, and optional errors."""

    if approval_received is not None:
        audit["approval_received"] = approval_received
    if errors:
        audit.setdefault("errors", []).extend(str(err) for err in errors)
    started = audit.pop("_started_monotonic", None)
    if started is not None:
        audit["duration_ms"] = round((time.monotonic() - started) * 1000, 1)
    audit["final_status"] = final_status
    audit["finished_at"] = datetime.now(timezone.utc).isoformat()
    return audit


def save_audit(audit: dict[str, Any], output_dir: str | Path = AUDIT_OUTPUT_DIR) -> Path:
    """Write the audit artifact under output/audit/YYYY-MM-DD."""

    timestamp = str(audit.get("timestamp") or datetime.now(timezone.utc).isoformat())
    day = timestamp[:10]
    directory = Path(output_dir) / day
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{audit['request_id']}.json"
    path.write_text(json.dumps(_jsonable(audit), indent=2, default=str) + "\n")
    return path


def _targets_from_plan(plan: ExecutionPlan) -> list[str]:
    targets = [step.target for step in plan.steps]
    return list(dict.fromkeys(targets))


def _jsonable(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, tuple):
        return [_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    return value
