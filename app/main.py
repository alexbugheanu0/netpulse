"""
NetPulse CLI entry point.

Usage — natural language:
    python3 -m app.main "show trunk status on sw-dist-01"
    python3 -m app.main "show vlans on sw-core-01"
    python3 -m app.main "show version on sw-core-01"
    python3 -m app.main "show errors on sw-core-01"
    python3 -m app.main "show cdp neighbors on sw-dist-01"
    python3 -m app.main "show mac table on sw-acc-01"
    python3 -m app.main "show spanning tree on sw-core-01"
    python3 -m app.main "ping 10.0.0.1 from sw-core-01"
    python3 -m app.main "backup config from sw-acc-02"
    python3 -m app.main "diff config on sw-core-01"
    python3 -m app.main "health check all switches"
    python3 -m app.main "show interfaces on all switches"
    python3 -m app.main "audit vlans on sw-core-01"
    python3 -m app.main "audit trunks on sw-dist-01"
    python3 -m app.main "device facts for sw-acc-01"
    python3 -m app.main "drift check sw-core-01"

Usage — structured flags (always unambiguous):
    python3 -m app.main --intent show_trunks   --device sw-dist-01
    python3 -m app.main --intent show_vlans    --device sw-core-01
    python3 -m app.main --intent show_errors   --device sw-core-01
    python3 -m app.main --intent show_cdp      --device sw-dist-01
    python3 -m app.main --intent show_mac      --device sw-acc-01
    python3 -m app.main --intent show_spanning_tree --device sw-core-01
    python3 -m app.main --intent ping          --device sw-core-01 --target 10.0.0.1
    python3 -m app.main --intent backup_config --device sw-acc-02
    python3 -m app.main --intent diff_backup   --device sw-core-01
    python3 -m app.main --intent health_check                        # all devices
    python3 -m app.main --intent show_version  --role core           # all core switches
    python3 -m app.main --intent audit_vlans   --device sw-core-01
    python3 -m app.main --intent audit_trunks  --device sw-dist-01
    python3 -m app.main --intent audit_vlans   --scope all           # all devices (explicit)
    python3 -m app.main --intent device_facts  --device sw-acc-01
    python3 -m app.main --intent drift_check   --device sw-core-01

Useful flags:
    --dry-run              Show what would run without connecting
    --filter Gi1/0/1       Filter output lines containing this string
    --format json          Output results as JSON (machine-readable)
    --format csv           Output results as CSV
    --check                TCP reachability check before running jobs

Exit codes:
    0  all jobs succeeded
    1  startup error (bad inventory / bad flags / validation failure)
    2  one or more jobs failed at runtime
"""

from __future__ import annotations

import argparse
import sys

from app import executor
from app.executor import JOB_MAP
from app.formatter import (
    print_banner,
    print_error,
    print_info,
    print_reachability_table,
    print_result,
    print_results_csv,
    print_results_json,
    print_results_table,
)
from app.inventory import (
    check_reachability,
    get_all_devices,
    get_devices_by_role,
    load_inventory,
)
from app.intents import parse_intent
from app.logger import get_logger
from app.models import IntentRequest, IntentType, ScopeType
from app.validators import validate_request

logger = get_logger(__name__)

# Human-readable command preview used by --dry-run only.
# Actual command constants live in each job module.
COMMAND_PREVIEW: dict[IntentType, str] = {
    IntentType.SHOW_INTERFACES:    "show interfaces status",
    IntentType.SHOW_VLANS:         "show vlan brief",
    IntentType.SHOW_TRUNKS:        "show interfaces trunk",
    IntentType.SHOW_VERSION:       "show version",
    IntentType.SHOW_ERRORS:        "show interfaces",
    IntentType.SHOW_CDP:           "show cdp neighbors detail",
    IntentType.SHOW_MAC:           "show mac address-table",
    IntentType.SHOW_SPANNING_TREE: "show spanning-tree",
    IntentType.PING:               "ping <target> repeat 5",
    IntentType.BACKUP_CONFIG:      "show running-config  →  output/backups/",
    IntentType.DIFF_BACKUP:        "(local file diff — no SSH)",
    IntentType.HEALTH_CHECK:       "show version + show interfaces status + show vlan brief",
    # L3 and advanced diagnostic intents
    IntentType.SHOW_ROUTE:         "show ip route",
    IntentType.SHOW_ARP:           "show ip arp",
    IntentType.SHOW_ETHERCHANNEL:  "show etherchannel summary",
    IntentType.SHOW_PORT_SECURITY: "show port-security",
    IntentType.SHOW_LOGGING:       "show logging",
    # SSOT audit intents
    IntentType.AUDIT_VLANS:        "show vlan brief  →  compare vs ssot/vlans.yaml",
    IntentType.AUDIT_TRUNKS:       "show interfaces trunk  →  compare vs ssot/trunks.yaml",
    IntentType.DEVICE_FACTS:       "show version + show interfaces status  →  device summary",
    IntentType.DRIFT_CHECK:        "show vlan brief + show interfaces trunk  →  combined drift check",
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="netpulse",
        description="NetPulse — Network Operations Copilot for Cisco Switches",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            '  python3 -m app.main "show errors on sw-core-01"\n'
            '  python3 -m app.main "ping 10.0.0.1 from sw-core-01"\n'
            '  python3 -m app.main "health check all switches"\n'
            "  python3 -m app.main --intent show_vlans  --device sw-core-01\n"
            "  python3 -m app.main --intent show_errors --role access\n"
            "  python3 -m app.main --intent health_check --format json\n"
        ),
    )
    parser.add_argument(
        "query",
        nargs="?",
        help='Natural language query, e.g. "show vlans on sw-core-01"',
    )
    parser.add_argument(
        "--intent",
        choices=[i.value for i in IntentType],
        help="Explicit intent (bypasses NL parsing)",
    )
    parser.add_argument(
        "--device",
        help="Target a single device by name, e.g. sw-dist-01",
    )
    parser.add_argument(
        "--role",
        help="Target all SSH-enabled devices with this role (e.g. core, access)",
    )
    parser.add_argument(
        "--target",
        help="Destination IP for --intent ping, e.g. 10.0.0.1",
    )
    parser.add_argument(
        "--filter",
        dest="filter_str",
        metavar="FILTER",
        help="Only show output lines containing this string (case-insensitive)",
    )
    parser.add_argument(
        "--format",
        choices=["text", "json", "csv"],
        default="text",
        help="Output format (default: text)",
    )
    parser.add_argument(
        "--scope",
        choices=["single", "all", "role"],
        help=(
            "Explicit scope override: single | all | role. "
            "When omitted, scope is derived from --device (single), "
            "--role (role), or neither (all)."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would run without opening any SSH connections",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="TCP port-22 reachability preflight — prints results and exits without running jobs",
    )
    return parser


def resolve_request(args: argparse.Namespace) -> IntentRequest:
    """
    Build an IntentRequest from CLI args.

    --device and --role are mutually exclusive.
    Structured flags (--intent) take priority over a NL query.
    Omitting both --device and --role with --intent targets all devices.
    """
    if args.intent:
        if args.device and args.role:
            raise ValueError("--device and --role are mutually exclusive.")

        if args.device:
            scope = ScopeType.SINGLE
        elif args.role:
            scope = ScopeType.ROLE
        else:
            scope = ScopeType.ALL

        # Explicit --scope overrides the derived value above.
        if args.scope:
            scope = ScopeType(args.scope)

        return IntentRequest(
            intent=IntentType(args.intent),
            device=args.device,
            role=args.role,
            scope=scope,
            ping_target=args.target,
            raw_query=(
                f"--intent {args.intent} "
                f"--device {args.device or ''} "
                f"--role {args.role or ''}"
            ).strip(),
        )

    if args.query:
        return parse_intent(args.query)

    raise ValueError(
        "Provide a natural language query or use --intent / --device flags.\n"
        "Run with --help for examples."
    )


def main() -> None:
    parser = build_parser()
    args   = parser.parse_args()

    if args.format == "text":
        print_banner()

    # Step 1: load inventory
    try:
        inventory = load_inventory()
    except Exception as exc:
        print_error(f"Failed to load inventory: {exc}")
        sys.exit(1)

    # Step 2: resolve intent (NL or structured flags)
    try:
        req = resolve_request(args)
    except ValueError as exc:
        print_error(str(exc))
        sys.exit(1)

    if args.format == "text":
        print_info(
            f"Intent: {req.intent.value}  |  "
            f"Device: {req.device or req.role or 'all'}  |  "
            f"Scope: {req.scope.value}"
        )

    # Step 3: validate request against inventory
    try:
        validate_request(req, inventory)
    except ValueError as exc:
        print_error(str(exc))
        sys.exit(1)

    # Step 4: optional TCP reachability pre-check — exits after printing the table.
    # --check is a preflight-only mode; execution must NOT continue into Step 6.
    if args.check:
        reachability = check_reachability(inventory)
        if args.format == "text":
            print_reachability_table(inventory, reachability)
        sys.exit(0)

    # Step 5: dry run — show targets and command without connecting
    if args.dry_run:
        command = COMMAND_PREVIEW.get(req.intent, req.intent.value)
        if req.intent == IntentType.PING:
            command = f"ping {req.ping_target} repeat 5"
        print_info(f"[DRY RUN] Command: {command!r}")

        if req.scope == ScopeType.SINGLE:
            target_devices = [inventory[req.device]]  # type: ignore[index]
        elif req.scope == ScopeType.ROLE:
            target_devices = get_devices_by_role(req.role, inventory)  # type: ignore[arg-type]
        else:
            target_devices = get_all_devices(inventory)

        for d in target_devices:
            print_info(f"  → {d.name} ({d.ip})")
        sys.exit(0)

    # Step 6: execute via shared executor
    try:
        results = executor.execute(req, inventory)
    except Exception as exc:
        print_error(f"Unexpected error during job execution: {exc}")
        logger.exception("Unhandled error in executor.execute()")
        sys.exit(1)

    # Step 7: apply output filter (keeps lines matching filter_str)
    if args.filter_str:
        results = [
            r.model_copy(update={
                "raw_output": "\n".join(
                    line for line in r.raw_output.splitlines()
                    if args.filter_str.lower() in line.lower()
                )
            })
            for r in results
        ]

    # Step 8: display results
    if args.format == "json":
        print_results_json(results)
    elif args.format == "csv":
        print_results_csv(results)
    else:
        if len(results) == 1:
            print_result(results[0])
        else:
            print_results_table(results)

    if any(not r.success for r in results):
        sys.exit(2)


if __name__ == "__main__":
    main()
