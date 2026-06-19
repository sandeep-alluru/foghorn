"""Impact propagation — find all transitively stale decisions when facts change."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from foghorn.repo import WorldRepo


@dataclass
class PropagationResult:
    """Result of propagating staleness from a set of changed facts.

    Attributes:
        changed_fact_ids: The fact IDs that triggered the propagation.
        directly_stale: Labels of decisions that directly depend on changed facts.
        transitively_stale: Labels of decisions that depend on directly stale decisions
            (requires decisions to reference other decisions via their fact_ids — if the
            architecture only records fact→decision edges, this will be empty).
        propagation_depth: Maximum depth reached in the propagation graph.
        impact_summary: Human-readable summary of the propagation result.
    """

    changed_fact_ids: list[str]
    directly_stale: list[str] = field(default_factory=list)
    transitively_stale: list[str] = field(default_factory=list)
    propagation_depth: int = 0
    impact_summary: str = ""


def propagate_staleness(repo: WorldRepo, changed_fact_ids: list[str]) -> PropagationResult:
    """Find all directly and transitively stale decisions for a set of changed facts.

    The propagation graph is fact → decision. Decisions that share a common "fact"
    edge with other decisions (i.e., decisions whose ID appears in another decision's
    ``fact_ids`` list) are considered transitive dependents.

    Args:
        repo: The :class:`~foghorn.repo.WorldRepo` to query.
        changed_fact_ids: IDs of facts that have changed.

    Returns:
        A :class:`PropagationResult` with direct and transitive stale decision labels.
    """
    if not changed_fact_ids:
        return PropagationResult(
            changed_fact_ids=[],
            impact_summary="No facts changed — nothing is stale.",
        )

    store = repo.store
    all_decisions = store.list_decisions()

    # Build a set of directly stale decision IDs (depend on a changed fact)
    directly_stale_ids: set[str] = set()
    directly_stale_labels: list[str] = []

    for decision in all_decisions:
        if (
            any(fid in changed_fact_ids for fid in decision.fact_ids)
            and decision.id not in directly_stale_ids
        ):
            directly_stale_ids.add(decision.id)
            directly_stale_labels.append(decision.label)

    # Build transitive closure: decisions whose fact_ids reference stale decision IDs
    # (some workflows record decision dependencies as fact IDs for cross-linking)
    transitively_stale_ids: set[str] = set()
    transitively_stale_labels: list[str] = []
    depth = 1 if directly_stale_ids else 0

    # BFS over decision→decision edges where a fact_id is a decision ID
    frontier = set(directly_stale_ids)
    visited: set[str] = set(directly_stale_ids)
    current_depth = 1

    while frontier:
        next_frontier: set[str] = set()
        for decision in all_decisions:
            if decision.id in visited:
                continue
            # Decision references a stale decision via its fact_ids
            if any(fid in frontier for fid in decision.fact_ids):
                transitively_stale_ids.add(decision.id)
                transitively_stale_labels.append(decision.label)
                next_frontier.add(decision.id)
        if not next_frontier:
            break
        visited |= next_frontier
        frontier = next_frontier
        current_depth += 1
        if current_depth > depth:
            depth = current_depth

    # Build human-readable summary
    n_direct = len(directly_stale_labels)
    n_transitive = len(transitively_stale_labels)
    n_facts = len(changed_fact_ids)

    if n_direct == 0:
        summary = (
            f"{n_facts} fact(s) changed but no decisions depend on them directly."
        )
    elif n_transitive == 0:
        summary = (
            f"{n_facts} fact(s) changed → {n_direct} decision(s) directly stale "
            f"(no transitive dependencies found)."
        )
    else:
        summary = (
            f"{n_facts} fact(s) changed → {n_direct} decision(s) directly stale, "
            f"{n_transitive} decision(s) transitively stale (depth {depth})."
        )

    return PropagationResult(
        changed_fact_ids=list(changed_fact_ids),
        directly_stale=directly_stale_labels,
        transitively_stale=transitively_stale_labels,
        propagation_depth=depth,
        impact_summary=summary,
    )
