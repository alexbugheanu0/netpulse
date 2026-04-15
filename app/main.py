"""
NetPulse CLI entry point.

Usage (natural language):
    python3 app/main.py "show trunk status on sw-dist-01"
    python3 app/main.py "show vlans on sw-core-01"
    python3 app/main.py "backup config from sw-acc-02"
    python3 app/main.py "health check all switches"

Usage (structured flags):
    python3 app/main.py --intent show_trunks --device sw-dist-01
    python3 app/main.py --intent health_check
"""

from __future__ import annotations

import argparse
import sys
from typing import Callable

from app.formatter import print_banner, print_error, print_info, print_result, print_results_table
from app.inventory import get_all_devices, get_device, load_inventory
from app.intents import parse_intent
from app.logger import get_logger
from app.models import Device, IntentRequest, IntentType, JobResult, ScopeType
from app.validators import validate_request

from app.jobs import (
    backup_config,
    health_check,
    show_interfaces,
    show_trunks,
    show_version,
    show_vlans,
)

logger = get_logger(__name__)

# Maps every allowed intent to its job's run() function
JOB_MAP: dict[IntentType, Callable[[Device], JobResult]] = {
    IntentType.SHOW_INTERFACES: show_interfaces.run,
    IntentType.SHOW_VLANS:      show_vlans.run,
    IntentType.SHOW_TRUNKS:     show_trunks.run,
    IntentType.SHOW_VERSION:    show_version.run,
    IntentType.BACKUP_CONFIG:   backup_config.run,
    IntentType.HEALTH_CHECK:    health_check.run,
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="netpulse",
        description="NetPulse — Network Operations Copilot for Cisco Switches",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            '  python3 app/main.py "show trunk status on sw-dist-01"\n'
            '  python3 app/main.py "health check all switches"\n'
            "  python3 app/main.py --intent show_vlans --device sw-core-01\n"
        ),
    )
    parser.add_argument(
        "query",
        nargs="?",
        help="Natural language query (e.g. \"show vlan on sw-core-01\")",
    )
    parser.add_argument(
        "--intent",
        type=str,
        choices=[i.value for i in IntentType],
        help="Explicit intent (bypasses NL parsing)",
    )
    parser.add_argument(
        "--device",
        type=str,
        help="Explicit device name (e.g. sw-dist-01)",
    )
    return parser


def resolve_request(args: argparse.Namespace) -> IntentRequest:
    """Build an IntentRequest from CLI args — structured flags take priority."""
    if args.intent:
        scope = ScopeType.SINGLE if args.device else ScopeType.ALL
        return IntentRequest(
            intent=IntentType(args.intent),
            device=args.device,
            scope=scope,
            raw_query=f"--intent {args.intent} --device {args.device or 'all'}",
            confirmation_required=(args.intent == IntentType.BACKUP_CONFIG.value),
        )

    if args.query:
        return parse_intent(args.query)

    raise ValueError(
        "Provide a natural language query or use --intent / --device flags.\n"
        "Run with --help for examples."
    )


def run_jobs(req: IntentRequest, inventory: dict) -> list[JobResult]:
    """Dispatch job(s) and collect results."""
    job_fn = JOB_MAP[req.intent]

    if req.scope == ScopeType.ALL:
        devices = get_all_devices(inventory)
        return [job_fn(device) for device in devices]

    device = get_device(req.device, inventory)  # type: ignore[arg-type]
    return [job_fn(device)]


def main() -> None:
    print_banner()

    parser = build_parser()
    args = parser.parse_args()

    # Load inventory
    try:
        inventory = load_inventory()
    except Exception as exc:
        print_error(f"Failed to load inventory: {exc}")
        sys.exit(1)

    # Parse intent
    try:
        req = resolve_request(args)
    except ValueError as exc:
        print_error(str(exc))
        sys.exit(1)

    print_info(
        f"Intent: {req.intent.value}  |  "
        f"Device: {req.device or 'all'}  |  "
        f"Scope: {req.scope.value}"
    )

    # Validate
    try:
        validate_request(req, inventory)
    except ValueError as exc:
        print_error(str(exc))
        sys.exit(1)

    # Execute
    try:
        results = run_jobs(req, inventory)
    except Exception as exc:
        print_error(f"Unexpected error: {exc}")
        logger.exception("Unhandled error in run_jobs")
        sys.exit(1)

    # Display
    if len(results) == 1:
        print_result(results[0])
    else:
        print_results_table(results)

    # Non-zero exit if any job failed (useful for scripts/CI)
    if any(not r.success for r in results):
        sys.exit(2)


if __name__ == "__main__":
    main()
