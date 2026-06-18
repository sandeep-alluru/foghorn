"""Staleness propagation engine — find decisions invalidated by fact changes."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from worldgit.fact import Fact, StalenessAlert

if TYPE_CHECKING:
    from worldgit.store import WorldCommit, WorldStore


@dataclass
class DiffResult:
    """Summary of changes between two world commits.

    Attributes:
        added_facts: Facts present in ``b`` but not ``a``.
        removed_facts: Facts present in ``a`` but not ``b``.
        changed_fact_ids: Union of added and removed fact IDs (convenience set).
        commit_a_id: ID of the base commit (or None for the empty state).
        commit_b_id: ID of the head commit.
    """

    added_facts: list[Fact]
    removed_facts: list[Fact]
    changed_fact_ids: set[str]
    commit_a_id: str | None
    commit_b_id: str


def diff_commits(
    store: WorldStore,
    commit_a: WorldCommit | None,
    commit_b: WorldCommit,
) -> DiffResult:
    """Compute the fact-level diff between two commits.

    Args:
        store: The WorldStore to resolve Fact objects from.
        commit_a: The base commit (None = empty state).
        commit_b: The head commit to compare against.

    Returns:
        DiffResult with added/removed facts and the union of changed IDs.
    """
    ids_a = commit_a.fact_ids if commit_a else set()
    ids_b = commit_b.fact_ids

    added_ids = ids_b - ids_a
    removed_ids = ids_a - ids_b

    added_facts = [f for fid in added_ids if (f := store.get_fact(fid)) is not None]
    removed_facts = [f for fid in removed_ids if (f := store.get_fact(fid)) is not None]

    added_facts.sort(key=lambda f: f.recorded_at)
    removed_facts.sort(key=lambda f: f.recorded_at)

    return DiffResult(
        added_facts=added_facts,
        removed_facts=removed_facts,
        changed_fact_ids=added_ids | removed_ids,
        commit_a_id=commit_a.id if commit_a else None,
        commit_b_id=commit_b.id,
    )


def compute_staleness(
    store: WorldStore,
    changed_fact_ids: set[str],
) -> list[StalenessAlert]:
    """Given a set of changed fact IDs, return staleness alerts for affected decisions.

    For each Decision that depends on at least one changed fact, emit a
    StalenessAlert. The ``impact_score`` is the average confidence of the
    changed facts that the decision depended on.

    Args:
        store: The WorldStore to resolve Decisions from.
        changed_fact_ids: Set of Fact IDs that have been added or removed.

    Returns:
        List of StalenessAlert, sorted by impact_score descending.
    """
    if not changed_fact_ids:
        return []

    seen_decision_ids: set[str] = set()
    alerts: list[StalenessAlert] = []

    for fact_id in changed_fact_ids:
        decisions = store.get_decisions_for_fact(fact_id)
        for decision in decisions:
            if decision.id in seen_decision_ids:
                continue
            seen_decision_ids.add(decision.id)

            stale_ids = [fid for fid in decision.fact_ids if fid in changed_fact_ids]
            if not stale_ids:
                continue

            # Impact = mean confidence of the changed facts this decision relied on
            confidences: list[float] = []
            for fid in stale_ids:
                fact = store.get_fact(fid)
                if fact is not None:
                    confidences.append(fact.confidence)
            impact = sum(confidences) / len(confidences) if confidences else 0.5

            alerts.append(
                StalenessAlert(
                    decision_id=decision.id,
                    decision_label=decision.label,
                    stale_fact_ids=stale_ids,
                    impact_score=impact,
                )
            )

    alerts.sort(key=lambda a: a.impact_score, reverse=True)
    return alerts
