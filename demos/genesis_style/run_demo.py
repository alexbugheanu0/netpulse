"""Run the NetPulse Genesis-style safety-control-plane demo."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.approval import approve_pending_request  # noqa: E402
from app.runner import run_request  # noqa: E402


def build_plan_preview(result: dict[str, Any]) -> dict[str, Any]:
    """Return the compact plan preview printed by the demo."""

    plan = result["plan"]
    return {
        "request_id": result["request_id"],
        "intent": plan["normalized_intent"],
        "risk": result["risk_decision"]["risk"],
        "approval_required": result["approval_required"],
        "steps": [step["action"] for step in plan["steps"]],
    }


def audit_summary(result: dict[str, Any]) -> dict[str, Any]:
    """Return a compact summary from the saved audit artifact."""

    audit_path = Path(result["audit_path"])
    audit = json.loads(audit_path.read_text())
    verification = result.get("verification") or audit.get("verification")
    if verification is None:
        verification_status = "skipped"
    else:
        verification_status = "passed" if verification.get("verified") else "failed"

    return {
        "request_id": audit["request_id"],
        "final_status": audit["final_status"],
        "approval_required": audit["approval_required"],
        "approval_received": audit["approval_received"],
        "verification": verification_status,
        "duration_ms": audit.get("duration_ms"),
    }


def run_demo(dry_run: bool = False, simulate_write: bool = False, approve: bool = False) -> dict[str, Any]:
    """Run one Genesis-style demo mode and return the runner result."""

    request = "Prepare the lab environment for simulation job demo-001."
    intent = "prepare_experiment_environment" if simulate_write else "prepare_lab_environment"
    params = {
        "domain": "lab",
        "job_id": "demo-001",
        "dataset": "demo-dataset",
        "storage_path": "/mnt/demo",
        "node_count": 2,
    }

    if simulate_write and approve and not dry_run:
        pending = run_request(
            original_request=request,
            normalized_intent=intent,
            params=params,
            user="demo-user",
            source="genesis-style-demo",
        )
        receipt = approve_pending_request(
            request_id=pending["request_id"],
            approved_by="demo-user",
            intent=intent,
            params=params,
        )
        approved_params = params | {"request_id": pending["request_id"]}
        return run_request(
            original_request=request,
            normalized_intent=intent,
            params=approved_params,
            user="demo-user",
            source="genesis-style-demo",
            approval_receipt=receipt,
        )

    return run_request(
        original_request=request,
        normalized_intent=intent,
        params=params,
        user="demo-user",
        source="genesis-style-demo",
        dry_run=dry_run,
    )


def print_demo(result: dict[str, Any], dry_run: bool = False, approve: bool = False) -> None:
    """Print the human-readable Genesis-style demo output."""

    request = result["plan"]["original_request"]
    print("1. Intent received")
    print(f"   {request}")
    print("2. Execution plan generated")
    for step in result["plan"]["steps"]:
        print(f"   - {step['action']} -> {step['target']} ({step['adapter']})")
    print("Structured plan preview")
    print(json.dumps(build_plan_preview(result), indent=2))
    print("3. Risk classification")
    print(f"   {result['risk_decision']['risk']}: {result['risk_decision']['reason']}")
    print("4. Mock network/compute/storage checks")
    if dry_run:
        print("   Dry run enabled.")
        print("   Plan generated, but no adapters executed.")
        print("   Audit artifact saved with final_status: dry_run")
    elif result["status"] == "approval_required":
        print("   Approval required.")
        print("   No execution performed.")
        print("   Audit artifact saved.")
    else:
        if approve:
            print("   Approval received.")
        for item in result["execution_results"]:
            print(f"   - {item.get('adapter')}: {item.get('summary')}")
        if approve:
            print("   Execution completed.")
    print("5. Verification results")
    verification = result.get("verification")
    print(json.dumps(verification, indent=2, default=str))
    if verification and verification.get("verified"):
        print("   Verification passed.")
    print("6. JSON audit artifact path")
    print(f"   {result['audit_path']}")
    summary = audit_summary(result)
    print("Audit summary:")
    print(f"- Request ID: {summary['request_id']}")
    print(f"- Final status: {summary['final_status']}")
    print(f"- Approval required: {str(summary['approval_required']).lower()}")
    print(f"- Approval received: {str(summary['approval_received']).lower()}")
    print(f"- Verification: {summary['verification']}")
    print(f"- Duration: {summary['duration_ms']} ms")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the Genesis-style NetPulse demo.")
    parser.add_argument("--dry-run", action="store_true", help="Generate plan/audit without execution.")
    parser.add_argument(
        "--simulate-write",
        action="store_true",
        help="Simulate an approval-gated infrastructure change workflow.",
    )
    parser.add_argument(
        "--approve",
        action="store_true",
        help="Approve the simulated write workflow. Requires --simulate-write.",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.approve and not args.simulate_write:
        raise SystemExit("--approve requires --simulate-write")

    result = run_demo(
        dry_run=args.dry_run,
        simulate_write=args.simulate_write,
        approve=args.approve,
    )
    print_demo(result, dry_run=args.dry_run, approve=args.approve)


if __name__ == "__main__":
    main()
