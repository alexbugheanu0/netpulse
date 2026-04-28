"""Server-side approval receipts for NetPulse write execution."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from app.planner import ExecutionPlan
from app.risk import RiskDecision

APPROVAL_STATE_DIR = Path("state/approvals")
APPROVAL_SECRET_PATH = Path("state/approval_secret")
APPROVAL_TTL_SECONDS = 15 * 60

_RUNTIME_PARAM_KEYS = {
    "approval_received",
    "approval_receipt",
    "approval_response",
    "approved_by",
    "request_id",
    "original_request",
    "raw_query",
    "_inventory",
    "_inventory_loader",
    "_validate_request",
    "_executor_execute",
}


class ApprovalError(ValueError):
    """Raised when an approval record or receipt cannot be trusted."""


def create_pending_approval(
    plan: ExecutionPlan,
    risk_decision: RiskDecision,
    params: dict[str, Any],
    *,
    expires_in_seconds: int = APPROVAL_TTL_SECONDS,
) -> dict[str, Any]:
    """Persist a pending approval record and return its public metadata."""

    now = _now()
    record = {
        "request_id": plan.request_id,
        "status": "pending",
        "created_at": now.isoformat(),
        "expires_at": (now + timedelta(seconds=expires_in_seconds)).isoformat(),
        "user": plan.user,
        "source": plan.source,
        "intent": plan.normalized_intent,
        "params_hash": approval_subject_hash(plan.normalized_intent, params),
        "risk": risk_decision.model_dump(),
        "scope": plan.scope,
        "approved_by": None,
        "approved_at": None,
        "consumed_at": None,
    }
    _write_record(record)
    return _public_record(record)


def approve_pending_request(
    *,
    request_id: str,
    approved_by: str,
    intent: str,
    params: dict[str, Any],
) -> dict[str, Any]:
    """Approve a pending request and return a signed approval receipt."""

    record = _load_record(request_id)
    _ensure_record_can_approve(record)

    params_hash = approval_subject_hash(intent, params)
    if record.get("intent") != intent or record.get("params_hash") != params_hash:
        raise ApprovalError("Approval does not match the pending request.")

    pending_user = record.get("user")
    if pending_user and approved_by and pending_user != approved_by:
        raise ApprovalError("Approval user does not match the original requester.")

    approved_at = _now().isoformat()
    receipt = {
        "request_id": request_id,
        "intent": intent,
        "params_hash": params_hash,
        "approved_by": approved_by,
        "approved_at": approved_at,
        "expires_at": record["expires_at"],
    }
    receipt["signature"] = _signature(receipt)

    record["status"] = "approved"
    record["approved_by"] = approved_by
    record["approved_at"] = approved_at
    record["receipt_hash"] = _receipt_hash(receipt)
    _write_record(record)
    return receipt


def validate_approval_receipt(
    receipt: dict[str, Any] | None,
    plan: ExecutionPlan,
    params: dict[str, Any],
) -> dict[str, Any]:
    """Validate a signed receipt against the stored pending approval."""

    if not receipt:
        raise ApprovalError("A signed approval receipt is required before execution.")

    request_id = str(receipt.get("request_id") or "")
    if request_id != plan.request_id:
        raise ApprovalError("Approval receipt request_id does not match this plan.")

    record = _load_record(request_id)
    if record.get("status") != "approved":
        raise ApprovalError("Approval has not been confirmed for this request.")
    if record.get("consumed_at"):
        raise ApprovalError("Approval receipt has already been used.")
    if _parse_time(record["expires_at"]) <= _now():
        raise ApprovalError("Approval has expired.")

    params_hash = approval_subject_hash(plan.normalized_intent, params)
    if receipt.get("intent") != plan.normalized_intent:
        raise ApprovalError("Approval receipt intent does not match this plan.")
    if receipt.get("params_hash") != params_hash or record.get("params_hash") != params_hash:
        raise ApprovalError("Approval receipt parameters do not match this plan.")
    if record.get("receipt_hash") != _receipt_hash(receipt):
        raise ApprovalError("Approval receipt does not match the stored approval.")
    if not hmac.compare_digest(str(receipt.get("signature") or ""), _signature(receipt)):
        raise ApprovalError("Approval receipt signature is invalid.")

    return {
        "request_id": request_id,
        "approved_by": receipt.get("approved_by"),
        "approved_at": receipt.get("approved_at"),
        "expires_at": receipt.get("expires_at"),
        "params_hash": params_hash,
    }


def consume_approval_receipt(receipt: dict[str, Any] | None) -> None:
    """Mark a receipt as single-use after an execution attempt starts."""

    if not receipt:
        return
    record = _load_record(str(receipt.get("request_id") or ""))
    record["status"] = "consumed"
    record["consumed_at"] = _now().isoformat()
    _write_record(record)


def approval_subject_hash(intent: str, params: dict[str, Any]) -> str:
    """Hash the intent and stable user-controlled parameters being approved."""

    subject = {
        "intent": intent,
        "params": _normalise_params(params),
    }
    payload = json.dumps(subject, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _normalise_params(params: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in sorted(params.items())
        if value is not None
        and key not in _RUNTIME_PARAM_KEYS
        and not key.startswith("_")
    }


def _ensure_record_can_approve(record: dict[str, Any]) -> None:
    if record.get("status") == "consumed":
        raise ApprovalError("Approval has already been used.")
    if _parse_time(record["expires_at"]) <= _now():
        raise ApprovalError("Approval has expired.")
    if record.get("status") not in {"pending", "approved"}:
        raise ApprovalError("Approval is not pending.")


def _public_record(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "request_id": record["request_id"],
        "status": record["status"],
        "expires_at": record["expires_at"],
        "intent": record["intent"],
        "risk": record["risk"],
        "scope": record["scope"],
    }


def _load_record(request_id: str) -> dict[str, Any]:
    path = _record_path(request_id)
    if not path.exists():
        raise ApprovalError("No pending approval was found for this request_id.")
    return json.loads(path.read_text())


def _write_record(record: dict[str, Any]) -> None:
    APPROVAL_STATE_DIR.mkdir(parents=True, exist_ok=True)
    path = _record_path(record["request_id"])
    path.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def _record_path(request_id: str) -> Path:
    safe_id = "".join(ch for ch in request_id if ch.isalnum() or ch in {"-", "_"})
    if not safe_id:
        raise ApprovalError("Invalid approval request_id.")
    return APPROVAL_STATE_DIR / f"{safe_id}.json"


def _signature(receipt: dict[str, Any]) -> str:
    payload = "|".join(
        str(receipt.get(key) or "")
        for key in ("request_id", "intent", "params_hash", "approved_by", "approved_at", "expires_at")
    )
    return hmac.new(_approval_secret(), payload.encode("utf-8"), hashlib.sha256).hexdigest()


def _receipt_hash(receipt: dict[str, Any]) -> str:
    payload = json.dumps(
        {key: value for key, value in receipt.items() if key != "signature"},
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _approval_secret() -> bytes:
    env_secret = os.environ.get("NETPULSE_APPROVAL_SECRET")
    if env_secret:
        return env_secret.encode("utf-8")

    if APPROVAL_SECRET_PATH.exists():
        return APPROVAL_SECRET_PATH.read_bytes().strip()

    APPROVAL_SECRET_PATH.parent.mkdir(parents=True, exist_ok=True)
    secret = secrets.token_hex(32).encode("utf-8")
    APPROVAL_SECRET_PATH.write_bytes(secret + b"\n")
    try:
        os.chmod(APPROVAL_SECRET_PATH, 0o600)
    except OSError:
        pass
    return secret


def _parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value)


def _now() -> datetime:
    return datetime.now(timezone.utc)
