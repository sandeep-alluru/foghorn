"""Rich terminal, JSON, and Markdown output formatters for foghorn."""

from __future__ import annotations

import json
from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from foghorn.fact import StalenessAlert
from foghorn.staleness import DiffResult
from foghorn.store import WorldCommit, WorldStore

_console = Console()


def _truncate(text: str, max_len: int = 72) -> str:
    return text if len(text) <= max_len else text[: max_len - 1] + "…"


def print_stale(
    alerts: list[StalenessAlert],
    console: Console | None = None,
) -> None:
    """Print staleness alerts to the terminal using Rich.

    Args:
        alerts: The StalenessAlert list returned by WorldRepo.stale().
        console: Optional Rich Console to write to (defaults to stdout).
    """
    con = console or _console

    if not alerts:
        con.print("[green]✓ No stale decisions — world state is consistent.[/green]")
        return

    con.print(
        Panel(
            f"[bold red]⚠ {len(alerts)} STALE DECISION(S) DETECTED[/bold red]",
            expand=False,
            border_style="red",
        )
    )
    con.print()

    table = Table(show_header=True, header_style="bold", box=None, padding=(0, 1))
    table.add_column("Impact", width=7)
    table.add_column("Decision", width=30)
    table.add_column("Stale Facts", no_wrap=False)

    for alert in alerts:
        impact = f"{alert.impact_score:.0%}"
        stale = ", ".join(alert.stale_fact_ids[:3])
        if len(alert.stale_fact_ids) > 3:
            stale += f" (+{len(alert.stale_fact_ids) - 3} more)"
        table.add_row(impact, _truncate(alert.decision_label, 30), stale)

    con.print(table)
    con.print()


def print_diff(
    diff: DiffResult,
    store: WorldStore,
    console: Console | None = None,
) -> None:
    """Print a fact-level diff between two commits.

    Args:
        diff: The DiffResult from WorldRepo.diff().
        store: WorldStore used to resolve fact content for display.
        console: Optional Rich Console to write to (defaults to stdout).
    """
    con = console or _console

    a_id = (diff.commit_a_id or "empty")[:8]
    b_id = diff.commit_b_id[:8]
    con.print(
        Panel(
            f"[bold]foghorn diff[/bold]  [dim]{a_id}[/dim] → [dim]{b_id}[/dim]",
            expand=False,
        )
    )

    if not diff.added_facts and not diff.removed_facts:
        con.print("[dim]No changes.[/dim]")
        return

    table = Table(show_header=True, header_style="bold", box=None, padding=(0, 1))
    table.add_column("Δ", width=2)
    table.add_column("Subject", width=16)
    table.add_column("Predicate", width=20)
    table.add_column("Object", no_wrap=False)

    for fact in diff.added_facts:
        table.add_row(
            Text("+", style="bold green"),
            fact.subject,
            fact.predicate,
            Text(fact.object, style="green"),
        )
    for fact in diff.removed_facts:
        table.add_row(
            Text("-", style="bold red"),
            fact.subject,
            fact.predicate,
            Text(fact.object, style="red"),
        )

    con.print(table)
    con.print()


def print_log(commits: list[WorldCommit], console: Console | None = None) -> None:
    """Print the commit log in a compact format.

    Args:
        commits: List of WorldCommit objects (newest first).
        console: Optional Rich Console to write to (defaults to stdout).
    """
    con = console or _console

    if not commits:
        con.print("[dim]No commits yet.[/dim]")
        return

    for wc in commits:
        short_id = wc.id[:8]
        nfacts = len(wc.fact_ids)
        ndecs = len(wc.decision_ids)
        con.print(
            f"[bold yellow]{short_id}[/bold yellow]  "
            f"[white]{_truncate(wc.message, 50)}[/white]  "
            f"[dim]{nfacts} facts · {ndecs} decisions[/dim]"
        )


def to_json(
    alerts: list[StalenessAlert],
    diff: DiffResult | None = None,
) -> str:
    """Serialize staleness alerts (and optionally a diff) to JSON.

    Args:
        alerts: List of StalenessAlert objects.
        diff: Optional DiffResult to include in the output.

    Returns:
        JSON string suitable for CI/CD consumption.
    """
    data: dict[str, Any] = {
        "has_stale": len(alerts) > 0,
        "stale_count": len(alerts),
        "alerts": [a.to_dict() for a in alerts],
    }
    if diff is not None:
        data["diff"] = {
            "commit_a": diff.commit_a_id,
            "commit_b": diff.commit_b_id,
            "added_facts": [f.to_dict() for f in diff.added_facts],
            "removed_facts": [f.to_dict() for f in diff.removed_facts],
        }
    return json.dumps(data, indent=2)


def to_markdown(alerts: list[StalenessAlert]) -> str:
    """Generate a GitHub PR comment in Markdown from staleness alerts.

    Args:
        alerts: List of StalenessAlert objects.

    Returns:
        Markdown string suitable for posting as a PR comment.
    """
    if not alerts:
        return (
            "## foghorn staleness report\n\n"
            "🟢 **No stale decisions** — world state is consistent.\n"
        )

    lines = [
        "## foghorn staleness report",
        "",
        f"🔴 **{len(alerts)} stale decision(s)** — review before merging.",
        "",
        "| Impact | Decision | Stale Facts |",
        "|--------|----------|-------------|",
    ]
    for alert in alerts[:20]:
        impact = f"{alert.impact_score:.0%}"
        stale = ", ".join(f"`{fid[:8]}`" for fid in alert.stale_fact_ids[:3])
        if len(alert.stale_fact_ids) > 3:
            stale += f" (+{len(alert.stale_fact_ids) - 3} more)"
        label = alert.decision_label.replace("|", "\\|")
        lines.append(f"| {impact} | {label} | {stale} |")

    if len(alerts) > 20:
        lines.append(f"| … | *{len(alerts) - 20} more* | |")

    lines += [
        "",
        "<details><summary>Full JSON</summary>",
        "",
        "```json",
        to_json(alerts),
        "```",
        "",
        "</details>",
        "",
        "*Generated by [foghorn](https://github.com/sandeep-alluru/foghorn)*",
    ]
    return "\n".join(lines)
