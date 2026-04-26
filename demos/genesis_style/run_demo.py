"""Run the NetPulse Genesis-style safety-control-plane demo."""

from __future__ import annotations

import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.runner import run_request  # noqa: E402


def main() -> None:
    request = "Prepare the lab environment for simulation job demo-001."
    result = run_request(
        original_request=request,
        normalized_intent="prepare_lab_environment",
        params={
            "domain": "lab",
            "job_id": "demo-001",
            "dataset": "demo-dataset",
            "storage_path": "/mnt/demo",
            "node_count": 2,
        },
        user="demo-user",
        source="genesis-style-demo",
    )

    print("1. Intent received")
    print(f"   {request}")
    print("2. Execution plan generated")
    for step in result["plan"]["steps"]:
        print(f"   - {step['action']} -> {step['target']} ({step['adapter']})")
    print("3. Risk classification")
    print(f"   {result['risk_decision']['risk']}: {result['risk_decision']['reason']}")
    print("4. Mock network/compute/storage checks")
    for item in result["execution_results"]:
        print(f"   - {item.get('adapter')}: {item.get('summary')}")
    print("5. Verification results")
    print(json.dumps(result["verification"], indent=2, default=str))
    print("6. JSON audit artifact path")
    print(f"   {result['audit_path']}")


if __name__ == "__main__":
    main()
