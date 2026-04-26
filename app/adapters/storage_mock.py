"""Deterministic mock storage adapter for demos and tests."""

from __future__ import annotations

from typing import Any


class StorageMockAdapter:
    """Mock storage adapter with deterministic readiness responses."""

    def execute_read(self, intent: str, params: dict[str, Any]) -> dict[str, Any]:
        if intent == "check_storage_path":
            path = params.get("storage_path") or "/mnt/demo"
            return {
                "success": True,
                "adapter": "storage_mock",
                "intent": intent,
                "summary": f"Storage path {path} is reachable.",
                "parsed_data": {"path": path, "reachable": True},
            }
        if intent == "check_dataset_available":
            dataset = params.get("dataset") or "demo-dataset"
            return {
                "success": True,
                "adapter": "storage_mock",
                "intent": intent,
                "summary": f"Dataset {dataset} is available.",
                "parsed_data": {"dataset": dataset, "available": True},
            }
        if intent == "verify_mount_ready":
            return {
                "success": True,
                "adapter": "storage_mock",
                "intent": intent,
                "summary": "Mock mount is ready.",
                "parsed_data": {"mounted": True, "read_write": True},
            }
        return _unsupported(intent)

    def execute_write(self, intent: str, params: dict[str, Any]) -> dict[str, Any]:
        return _unsupported(intent)

    def dry_run(self, intent: str, params: dict[str, Any]) -> dict[str, Any]:
        return {"success": True, "adapter": "storage_mock", "intent": intent, "dry_run": True}

    def verify(self, intent: str, params: dict[str, Any], execution_result: Any) -> dict[str, Any]:
        success = bool(execution_result.get("success")) if isinstance(execution_result, dict) else False
        return {
            "verified": success,
            "checks": ["mock_storage_result_success"],
            "evidence": execution_result,
            "error": None if success else "mock_storage_failed",
        }


def _unsupported(intent: str) -> dict[str, Any]:
    return {
        "success": False,
        "adapter": "storage_mock",
        "intent": intent,
        "error": f"Unsupported storage mock intent: {intent}",
    }
