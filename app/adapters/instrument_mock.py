"""Deterministic mock instrument adapter for demos and tests."""

from __future__ import annotations

from typing import Any


class InstrumentMockAdapter:
    """Mock lab instrument adapter with fixed responses."""

    def execute_read(self, intent: str, params: dict[str, Any]) -> dict[str, Any]:
        if intent == "check_instrument_status":
            return {
                "success": True,
                "adapter": "instrument_mock",
                "intent": intent,
                "summary": "Mock instrument is online and idle.",
                "parsed_data": {"online": True, "state": "idle"},
            }
        return _unsupported(intent)

    def execute_write(self, intent: str, params: dict[str, Any]) -> dict[str, Any]:
        if intent == "prepare_instrument_mock":
            return {
                "success": True,
                "adapter": "instrument_mock",
                "intent": intent,
                "summary": "Mock instrument prepared for simulation.",
                "parsed_data": {"prepared": True, "profile": params.get("profile", "demo")},
            }
        return _unsupported(intent)

    def dry_run(self, intent: str, params: dict[str, Any]) -> dict[str, Any]:
        return {"success": True, "adapter": "instrument_mock", "intent": intent, "dry_run": True}

    def verify(self, intent: str, params: dict[str, Any], execution_result: Any) -> dict[str, Any]:
        success = bool(execution_result.get("success")) if isinstance(execution_result, dict) else False
        return {
            "verified": success,
            "checks": ["mock_instrument_result_success"],
            "evidence": execution_result,
            "error": None if success else "mock_instrument_failed",
        }


def _unsupported(intent: str) -> dict[str, Any]:
    return {
        "success": False,
        "adapter": "instrument_mock",
        "intent": intent,
        "error": f"Unsupported instrument mock intent: {intent}",
    }
