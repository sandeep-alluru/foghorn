"""Command-line interface for foghorn."""

from __future__ import annotations

import sys

import click

from foghorn.repo import WorldRepo
from foghorn.report import print_diff, print_log, print_stale, to_json, to_markdown


def _repo(ctx: click.Context) -> WorldRepo:
    """Return a WorldRepo from the context or default path."""
    db_path = ctx.obj.get("db") if ctx.obj else ".foghorn/world.db"
    return WorldRepo.init(db_path)


@click.group()
@click.version_option(package_name="foghorn-ai")
@click.option(
    "--db",
    default=".foghorn/world.db",
    show_default=True,
    help="Path to the foghorn database.",
    envvar="FOGHORN_DB",
)
@click.pass_context
def main(ctx: click.Context, db: str) -> None:
    """Decision staleness alerts for AI agents.

    foghorn tracks which agent decisions depend on which facts,
    and alerts you when upstream facts change.
    """
    ctx.ensure_object(dict)
    ctx.obj["db"] = db


@main.command()
@click.argument("subject")
@click.argument("predicate")
@click.argument("object")
@click.option(
    "--confidence", type=float, default=1.0, show_default=True, help="Belief weight in [0.0, 1.0]."
)
@click.pass_context
def fact(ctx: click.Context, subject: str, predicate: str, object: str, confidence: float) -> None:
    """Stage a new fact triple.

    \b
    Examples:
      foghorn fact Redis is-appropriate-for rate-limiting
      foghorn fact "Postgres" "is-primary-db" "yes" --confidence 0.9
    """
    with _repo(ctx) as repo:
        f = repo.add_fact(subject, predicate, object, confidence)
        click.echo(f"Staged fact  {f.id}  {f.subject} {f.predicate} {f.object}")


@main.command()
@click.argument("label")
@click.argument("content")
@click.option(
    "--on",
    "depends_on",
    multiple=True,
    metavar="FACT_ID",
    help="Fact ID this decision depends on. Repeat for multiple.",
)
@click.pass_context
def decide(ctx: click.Context, label: str, content: str, depends_on: tuple[str, ...]) -> None:
    """Stage a decision that depends on facts.

    \b
    Examples:
      foghorn decide chose-redis "Redis fits our rate-limiter requirements" \\
          --on abc123 --on def456
    """
    with _repo(ctx) as repo:
        d = repo.decide(label, content, list(depends_on))
        click.echo(f"Staged decision  {d.id}  {d.label}  (depends on {len(d.fact_ids)} facts)")


@main.command("commit")
@click.option("-m", "--message", required=True, help="Commit message.")
@click.pass_context
def commit_cmd(ctx: click.Context, message: str) -> None:
    """Commit staged facts and decisions.

    \b
    Examples:
      foghorn commit -m "Initial architecture decisions"
    """
    with _repo(ctx) as repo:
        try:
            wc = repo.commit(message)
            click.echo(f"Committed  {wc.id[:8]}  {wc.message}")
            click.echo(f"  {len(wc.fact_ids)} facts · {len(wc.decision_ids)} decisions")
        except ValueError as exc:
            raise click.ClickException(str(exc)) from exc


@main.command()
@click.option(
    "--since", default=None, metavar="COMMIT_ID", help="Diff against this commit instead of HEAD~1."
)
@click.option(
    "--format",
    "fmt",
    type=click.Choice(["rich", "json", "markdown"]),
    default="rich",
    show_default=True,
)
@click.option(
    "--exit-code",
    is_flag=True,
    default=False,
    help="Exit 1 if stale decisions are found (useful in CI).",
)
@click.pass_context
def stale(ctx: click.Context, since: str | None, fmt: str, exit_code: bool) -> None:
    """Show decisions invalidated by recent fact changes.

    \b
    Examples:
      foghorn stale
      foghorn stale --format json
      foghorn stale --exit-code   # fails CI if anything is stale
    """
    with _repo(ctx) as repo:
        since_commit = None
        if since:
            since_commit = repo.store.get_commit(since)
            if since_commit is None:
                raise click.ClickException(f"Commit not found: {since}")
        alerts = repo.stale(since=since_commit)

        if fmt == "rich":
            print_stale(alerts)
        elif fmt == "json":
            click.echo(to_json(alerts))
        elif fmt == "markdown":
            click.echo(to_markdown(alerts))

        if exit_code and alerts:
            sys.exit(1)


@main.command()
@click.option(
    "--format",
    "fmt",
    type=click.Choice(["rich", "json", "markdown"]),
    default="rich",
    show_default=True,
)
@click.pass_context
def diff(ctx: click.Context, fmt: str) -> None:
    """Show fact changes between HEAD and its parent.

    \b
    Examples:
      foghorn diff
      foghorn diff --format json
    """
    with _repo(ctx) as repo:
        try:
            d = repo.diff()
        except ValueError as exc:
            raise click.ClickException(str(exc)) from exc

        if fmt == "rich":
            print_diff(d, repo.store)
        elif fmt == "json":
            data = {
                "commit_a": d.commit_a_id,
                "commit_b": d.commit_b_id,
                "added_facts": [f.to_dict() for f in d.added_facts],
                "removed_facts": [f.to_dict() for f in d.removed_facts],
            }
            click.echo(__import__("json").dumps(data, indent=2))
        elif fmt == "markdown":
            lines = ["## foghorn diff", ""]
            for f in d.added_facts:
                lines.append(f"+ `{f.subject}` **{f.predicate}** `{f.object}`")
            for f in d.removed_facts:
                lines.append(f"- `{f.subject}` **{f.predicate}** `{f.object}`")
            click.echo("\n".join(lines))


@main.command()
@click.pass_context
def log(ctx: click.Context) -> None:
    """Show commit history.

    \b
    Examples:
      foghorn log
    """
    with _repo(ctx) as repo:
        commits = repo.log()
        print_log(commits)


@main.command()
@click.pass_context
def status(ctx: click.Context) -> None:
    """Show staged (uncommitted) facts and decisions."""
    with _repo(ctx) as repo:
        staged = repo.store.staged_count()
        head = repo.store.head()
        if head:
            click.echo(f"HEAD  {head.id[:8]}  {head.message}")
        else:
            click.echo("No commits yet.")
        click.echo(f"{staged} staged item(s) ready to commit.")


@main.command()
@click.pass_context
def recommend(ctx: click.Context) -> None:
    """Show actionable recommendations for all stale decisions.

    \b
    Examples:
      foghorn recommend
      foghorn --db /path/to/world.db recommend
    """
    from rich.console import Console
    from rich.table import Table

    from foghorn.recommend import recommend as _recommend

    with _repo(ctx) as repo:
        recs = _recommend(repo)

    if not recs:
        click.echo("No stale decisions — everything looks fresh!")
        return

    console = Console()
    table = Table(
        show_header=True,
        header_style="bold",
        box=None,
        padding=(0, 1),
    )
    table.add_column("Decision", style="bold", min_width=20)
    table.add_column("Priority", width=10)
    table.add_column("Action", width=14)
    table.add_column("Reason")

    priority_colors = {
        "critical": "bold red",
        "high": "red",
        "medium": "yellow",
        "low": "dim",
    }

    for rec in recs:
        color = priority_colors.get(rec.priority, "")
        table.add_row(
            rec.decision_label,
            f"[{color}]{rec.priority}[/{color}]",
            rec.action,
            rec.reason[:80],
        )

    console.print(table)
    console.print(f"\n[dim]{len(recs)} recommendation(s)[/dim]")


if __name__ == "__main__":
    main()
