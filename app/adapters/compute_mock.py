"""Deterministic mock compute adapter for demos and tests."""

from __future__ import annotations

from typing import Any


class ComputeMockAdapter:
    """Mock compute adapter with no external dependencies."""

    def execute_read(self, intent: str, params: dict[str, Any]) -> dict[str, Any]:
        if intent == "check_compute_health":
            return {
                "success": True,
                "adapter": "compute_mock",
                "intent": intent,
                "summary": "3/3 simulation nodes healthy.",
                "parsed_data": {"healthy_nodes": 3, "total_nodes": 3},
            }
        if intent == "check_node_availability":
            return {
                "success": True,
                "adapter": "compute_mock",
                "intent": intent,
                "summary": "2 simulation nodes available.",
                "parsed_data": {"available_nodes": ["sim-node-01", "sim-node-02"]},
            }
        return _unsupported(intent)

    def execute_write(self, intent: str, params: dict[str, Any]) -> dict[str, Any]:
        if intent == "allocate_simulation_nodes":
            count = int(params.get("node_count") or 2)
            return {
                "success": True,
                "adapter": "compute_mock",
                "intent": intent,
                "summary": f"Allocated {count} mock simulation node(s).",
                "parsed_data": {"allocated_nodes": [f"sim-node-{idx:02d}" for idx in range(1, count + 1)]},
            }
        return _unsupported(intent)

    def dry_run(self, intent: str, params: dict[str, Any]) -> dict[str, Any]:
        return {"success": True, "adapter": "compute_mock", "intent": intent, "dry_run": True}

    def verify(self, intent: str, params: dict[str, Any], execution_result: Any) -> dict[str, Any]:
        return {
            "verified": bool(_success(execution_result)),
            "checks": ["mock_compute_result_success"],
            "evidence": execution_result,
            "error": None if _success(execution_result) else "mock_compute_failed",
        }


def _success(result: Any) -> bool:
    return bool(result.get("success")) if isinstance(result, dict) else False


def _unsupported(intent: str) -> dict[str, Any]:
    return {
        "success": False,
        "adapter": "compute_mock",
        "intent": intent,
        "error": f"Unsupported compute mock intent: {intent}",
    }
