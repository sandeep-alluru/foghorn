"""Export and import utilities for foghorn repositories."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from foghorn.repo import WorldRepo


def export_json(repo: WorldRepo) -> str:
    """Export the entire repository state as a JSON string.

    Exports all facts, decisions, and commits currently known to the store.
    The resulting JSON is suitable for archiving, migration, or seeding a
    fresh repository via :func:`import_json`.

    Args:
        repo: The repository to export.

    Returns:
        A JSON string with keys ``"facts"``, ``"decisions"``, and ``"commits"``.
    """
    store = repo.store

    facts = [f.to_dict() for f in store.list_facts()]
    decisions = [d.to_dict() for d in store.list_decisions()]
    commits = [c.to_dict() for c in store.log()]

    return json.dumps(
        {
            "foghorn_export_version": 1,
            "facts": facts,
            "decisions": decisions,
            "commits": commits,
        },
        indent=2,
        sort_keys=True,
    )


def import_json(path_or_str: str, target_repo: WorldRepo) -> int:
    """Import a JSON export into a target repository.

    Imports all facts and decisions from the export. Each unique fact and
    decision is staged and committed to the target repository as a single
    "import" commit.  If there is nothing new to stage, no commit is created.

    Args:
        path_or_str: Either a JSON string or a path to a JSON file.
        target_repo: The :class:`~foghorn.repo.WorldRepo` to import into.

    Returns:
        The total number of items (facts + decisions) imported.

    Raises:
        ValueError: If the JSON is not a valid foghorn export.
        FileNotFoundError: If a path is given but does not exist.
    """
    # Detect whether path_or_str is a file path or raw JSON.
    # Guard against very long strings that would cause OSError on Path.exists().
    raw: str
    if len(path_or_str) < 4096:
        p = Path(path_or_str)
        try:
            is_file = p.exists() and p.is_file()
        except OSError:
            is_file = False
        raw = p.read_text(encoding="utf-8") if is_file else path_or_str
    else:
        raw = path_or_str

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON: {exc}") from exc

    if not isinstance(data, dict):
        raise ValueError("Export JSON must be a top-level object.")

    version = data.get("foghorn_export_version", 0)
    if version != 1:
        raise ValueError(f"Unsupported export version: {version} (expected 1)")

    from foghorn.fact import Decision, Fact

    store = target_repo.store
    imported = 0

    for fact_dict in data.get("facts", []):
        fact = Fact.from_dict(fact_dict)
        # add_fact is idempotent (INSERT OR IGNORE)
        store.add_fact(fact)
        imported += 1

    for dec_dict in data.get("decisions", []):
        decision = Decision.from_dict(dec_dict)
        store.add_decision(decision)
        imported += 1

    if imported > 0 and store.staged_count() > 0:
        store.commit(f"Import: {imported} items from foghorn export")

    return imported


def export_graphviz(repo: WorldRepo) -> str:
    """Export the fact → decision dependency graph in Graphviz DOT format.

    Each fact and decision is a node; directed edges run from facts to the
    decisions that depend on them. The resulting DOT string can be rendered
    with ``dot -Tsvg graph.dot > graph.svg``.

    Args:
        repo: The repository to graph.

    Returns:
        A Graphviz DOT string.
    """
    store = repo.store
    facts = store.list_facts()
    decisions = store.list_decisions()

    lines: list[str] = [
        "digraph foghorn {",
        "  rankdir=LR;",
        '  node [fontname="Helvetica", fontsize=10];',
        "",
        "  // Facts",
    ]

    for fact in facts:
        label = f"{fact.subject}\\n{fact.predicate}\\n{fact.object}"
        label = label.replace('"', '\\"')
        lines.append(
            f'  "fact_{fact.id}" [shape=ellipse, style=filled, fillcolor="#d0e8ff",'
            f' label="{label}"];'
        )

    lines.append("")
    lines.append("  // Decisions")

    for dec in decisions:
        label = dec.label.replace('"', '\\"')
        lines.append(
            f'  "dec_{dec.id}" [shape=box, style=filled, fillcolor="#ffe0b0", label="{label}"];'
        )

    lines.append("")
    lines.append("  // Edges (fact -> decision)")

    for dec in decisions:
        for fid in dec.fact_ids:
            lines.append(f'  "fact_{fid}" -> "dec_{dec.id}";')

    lines.append("}")
    return "\n".join(lines)
