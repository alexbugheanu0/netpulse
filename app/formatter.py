"""
Rich-based CLI output formatter for NetPulse.

All terminal output goes through this module.
Other modules never call print() directly — use console, print_result, etc.
"""

from __future__ import annotations

import csv
import json
import sys
from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from app.models import JobResult

console = Console()


def print_banner() -> None:
    """Print the NetPulse startup banner."""
    console.print(
        Panel(
            "[bold cyan]NetPulse v1[/bold cyan]  —  Network Operations Copilot for Cisco Switches",
            expand=False,
        )
    )


def print_result(result: JobResult) -> None:
    """Pretty-print a single JobResult (used for single-device runs)."""
    elapsed = f"  [dim]{result.elapsed_ms:.0f}ms[/dim]" if result.elapsed_ms else ""
    status  = "[green]✓ OK[/green]" if result.success else "[red]✗ FAIL[/red]"
    header  = (
        f"{status}   [bold]{result.device}[/bold]  →  "
        f"[magenta]{result.intent}[/magenta]{elapsed}"
    )

    console.print(Panel(header, expand=False))

    if not result.success:
        console.print(f"  [red]Error:[/red] {result.error}\n")
        return

    if result.raw_output:
        console.print(result.raw_output)

    console.print()


def print_results_table(results: list[JobResult]) -> None:
    """Print a summary table for multi-device (scope=all/role) runs."""
    show_elapsed = any(r.elapsed_ms is not None for r in results)

    table = Table(title="NetPulse — Run Summary", show_lines=True, expand=False)
    table.add_column("Device",  style="cyan",    no_wrap=True)
    table.add_column("Intent",  style="magenta", no_wrap=True)
    table.add_column("Status",  no_wrap=True)
    if show_elapsed:
        table.add_column("Elapsed", no_wrap=True, style="dim")
    table.add_column("Details")

    for r in results:
        status = "[green]OK[/green]" if r.success else "[red]FAIL[/red]"
        detail = (
            r.error or ""
            if not r.success
            else (r.raw_output[:120] + "…") if len(r.raw_output) > 120 else r.raw_output
        )
        elapsed_str = f"{r.elapsed_ms:.0f}ms" if r.elapsed_ms else ""
        row = [r.device, r.intent, status]
        if show_elapsed:
            row.append(elapsed_str)
        row.append(detail)
        table.add_row(*row)

    console.print(table)


def print_reachability_table(
    inventory: dict[str, Any],
    reachability: dict[str, bool],
) -> None:
    """Print a pre-flight reachability check table."""
    table = Table(title="Reachability Check (port 22)", show_lines=True, expand=False)
    table.add_column("Device", style="cyan",  no_wrap=True)
    table.add_column("IP",     style="dim")
    table.add_column("Role",   style="dim")
    table.add_column("Status", no_wrap=True)

    for name, device in inventory.items():
        reachable = reachability.get(name, False)
        status    = "[green]✓ reachable[/green]" if reachable else "[red]✗ unreachable[/red]"
        table.add_row(name, device.ip, device.role, status)

    console.print(table)
    console.print()


def print_results_json(results: list[JobResult]) -> None:
    """Write all results as a JSON array to stdout."""
    print(json.dumps([r.model_dump() for r in results], indent=2, default=str))


def print_results_csv(results: list[JobResult]) -> None:
    """
    Write results to stdout in CSV format.

    If all results share list-type parsed_data with consistent keys, each
    row includes those keys plus a leading 'device' column.
    Otherwise falls back to: device, intent, success, elapsed_ms, raw_output, error.
    """
    writer = csv.writer(sys.stdout)

    # Try structured output if parsed_data is a uniform list of dicts
    if all(isinstance(r.parsed_data, list) and r.parsed_data for r in results):
        all_keys: list[str] = []
        for r in results:
            for row_dict in r.parsed_data:  # type: ignore[union-attr]
                for k in row_dict:
                    if k not in all_keys:
                        all_keys.append(k)
        writer.writerow(["device"] + all_keys)
        for r in results:
            for row_dict in r.parsed_data:  # type: ignore[union-attr]
                writer.writerow([r.device] + [row_dict.get(k, "") for k in all_keys])
        return

    # Generic fallback
    writer.writerow(["device", "intent", "success", "elapsed_ms", "raw_output", "error"])
    for r in results:
        writer.writerow([
            r.device, r.intent, r.success, r.elapsed_ms or "",
            r.raw_output.replace("\n", " "), r.error or "",
        ])


def print_error(msg: str) -> None:
    """Print a fatal operator-facing error and stop."""
    console.print(f"[bold red]Error:[/bold red] {msg}")


def print_info(msg: str) -> None:
    """Print a dim informational line (intent/device/scope summary)."""
    console.print(f"[dim]{msg}[/dim]")
