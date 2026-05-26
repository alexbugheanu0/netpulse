"""Tests for --check flag behaviour in app/main.py.

Verifies that --check is a pure preflight mode: it prints the reachability
table and exits with code 0 WITHOUT calling executor.execute().
"""

from __future__ import annotations

import argparse
import pytest
from unittest.mock import MagicMock, patch

from app.main import resolve_request
from app.models import Device, ScopeType

MOCK_INVENTORY = {
    "sw-core-01": Device(
        name="sw-core-01",
        hostname="sw-core-01",
        ip="192.168.1.1",
        platform="cisco_ios",
        role="core",
        ssh_enabled=True,
    ),
}

REACHABILITY = {"sw-core-01": True}


def _run_main_with_check(*extra_args):
    """
    Call app.main.main() with --check injected into sys.argv and
    return the SystemExit code.  Patches out the heavy dependencies.
    """
    import sys
    from app.main import main

    argv = ["netpulse", "--intent", "show_vlans", "--device", "sw-core-01", "--check"]
    argv.extend(extra_args)

    with (
        patch("app.main.load_inventory", return_value=MOCK_INVENTORY),
        patch("app.main.validate_request"),
        patch("app.main.check_reachability", return_value=REACHABILITY) as mock_check,
        patch("app.main.executor.execute") as mock_exec,
        patch("app.main.print_banner"),
        patch("app.main.print_reachability_table"),
        patch("app.main.print_info"),
        patch("sys.argv", argv),
    ):
        with pytest.raises(SystemExit) as exc_info:
            main()
        return exc_info.value.code, mock_check, mock_exec


def test_check_flag_exits_zero():
    """--check must produce exit code 0."""
    code, _, _ = _run_main_with_check()
    assert code == 0


def test_check_flag_does_not_call_executor():
    """--check must never invoke executor.execute()."""
    _, _, mock_exec = _run_main_with_check()
    mock_exec.assert_not_called()


def test_check_flag_calls_check_reachability():
    """--check must call check_reachability() to perform the TCP probe."""
    _, mock_check, _ = _run_main_with_check()
    mock_check.assert_called_once()


def test_check_flag_with_json_format_still_exits_zero():
    """--check --format json must also exit 0 without executing."""
    code, _, mock_exec = _run_main_with_check("--format", "json")
    assert code == 0
    mock_exec.assert_not_called()


def _request_args(intent: str, **overrides) -> argparse.Namespace:
    values = {
        "intent": intent,
        "device": None,
        "role": None,
        "scope": None,
        "target": None,
        "endpoint": None,
        "query": None,
    }
    values.update(overrides)
    return argparse.Namespace(**values)


def test_targetless_status_cli_intent_defaults_to_all_inventory_devices():
    req = resolve_request(_request_args("health_check"))
    assert req.scope == ScopeType.ALL
    assert req.device is None


def test_explicit_device_and_role_cli_targets_remain_narrow():
    assert resolve_request(_request_args("show_vlans", device="sw-core-01")).scope == ScopeType.SINGLE
    assert resolve_request(_request_args("show_vlans", role="access")).scope == ScopeType.ROLE


@pytest.mark.parametrize("intent", ["backup_config", "diff_backup", "diagnose_endpoint"])
def test_artifact_and_endpoint_cli_intents_require_explicit_target_or_scope(intent):
    with pytest.raises(ValueError, match="requires --device, --role, or an explicit --scope"):
        resolve_request(_request_args(intent, endpoint="10.0.0.25"))


def test_explicit_all_scope_is_allowed_for_backup():
    req = resolve_request(_request_args("backup_config", scope="all"))
    assert req.scope == ScopeType.ALL
