"""
Rich-based CLI output formatter for NetPulse.

All terminal output goes through this module.
Other modules import console, print_result, etc. — never print() directly.
"""

from __future__ import annotations

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from app.models import JobResult

console = Console()


def print_banner() -> None:
    """Print the NetPulse header banner."""
    console.print(
        Panel(
            "[bold cyan]NetPulse v1[/bold cyan]  —  Network Operations Copilot for Cisco Switches",
            expand=False,
        )
    )


def print_result(result: JobResult) -> None:
    """Pretty-print a single JobResult."""
    status_str = "[green]✓ OK[/green]" if result.success else "[red]✗ FAIL[/red]"
    header = f"{status_str}   [bold]{result.device}[/bold]  →  [magenta]{result.intent}[/magenta]"

    console.print(Panel(header, expand=False))

    if not result.success:
        console.print(f"  [red]Error:[/red] {result.error}\n")
        return

    if result.raw_output:
        console.print(result.raw_output)

    console.print()


def print_results_table(results: list[JobResult]) -> None:
    """Print a summary table for multi-device runs."""
    table = Table(title="NetPulse — Run Summary", show_lines=True, expand=False)
    table.add_column("Device",  style="cyan",    no_wrap=True)
    table.add_column("Intent",  style="magenta", no_wrap=True)
    table.add_column("Status",  no_wrap=True)
    table.add_column("Details")

    for r in results:
        status = "[green]OK[/green]" if r.success else "[red]FAIL[/red]"
        if not r.success:
            detail = r.error or ""
        else:
            detail = (r.raw_output[:100] + "…") if len(r.raw_output) > 100 else r.raw_output
        table.add_row(r.device, r.intent, status, detail)

    console.print(table)


def print_error(msg: str) -> None:
    console.print(f"[bold red]Error:[/bold red] {msg}")


def print_info(msg: str) -> None:
    console.print(f"[dim]{msg}[/dim]")
