"""Staleness recommendations — actionable advice for stale decisions."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from foghorn.repo import WorldRepo


@dataclass
class Recommendation:
    """An actionable recommendation for a stale decision.

    Attributes:
        decision_label: The label of the stale decision.
        reason: Why the decision is considered stale.
        action: Recommended action: ``"re-evaluate"``, ``"archive"``, or
            ``"update-fact"``.
        priority: ``"critical"``, ``"high"``, ``"medium"``, or ``"low"``.
        stale_facts: Subjects of the facts that triggered this recommendation.
    """

    decision_label: str
    reason: str
    action: str
    priority: str
    stale_facts: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        """Serialize to a plain dict."""
        return {
            "decision_label": self.decision_label,
            "reason": self.reason,
            "action": self.action,
            "priority": self.priority,
            "stale_facts": self.stale_facts,
        }


def recommend(repo: WorldRepo) -> list[Recommendation]:
    """Generate actionable recommendations for all stale decisions.

    Compares the HEAD commit to its parent (or the empty state if there is only
    one commit) and produces a :class:`Recommendation` for each decision whose
    upstream facts have changed since that base commit.

    Priority is determined by the decision's ``impact_score``:

    - ``impact_score >= 0.9`` → ``"critical"``
    - ``impact_score >= 0.7`` → ``"high"``
    - ``impact_score >= 0.4`` → ``"medium"``
    - otherwise → ``"low"``

    The recommended action depends on how many facts are stale relative to the
    total facts the decision depended on:

    - All facts stale → ``"archive"``
    - Majority stale (> 50 %) → ``"re-evaluate"``
    - Minority stale → ``"update-fact"``

    Args:
        repo: The :class:`~foghorn.repo.WorldRepo` to analyse.

    Returns:
        List of :class:`Recommendation`, sorted by priority (critical first).
    """
    alerts = repo.stale()
    if not alerts:
        return []

    store = repo.store
    recommendations: list[Recommendation] = []

    _priority_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}

    for alert in alerts:
        decision = store.get_decision(alert.decision_id)
        if decision is None:
            continue

        total_facts = len(decision.fact_ids)
        n_stale = len(alert.stale_fact_ids)

        # Determine action
        if total_facts == 0:
            action = "review"
            reason = "Decision has no fact dependencies — review if still relevant"
        elif total_facts > 0 and n_stale >= total_facts:
            action = "archive"
            reason = (
                f"All {total_facts} fact(s) this decision depended on have changed — "
                "the decision is no longer grounded in current world state."
            )
        elif total_facts > 0 and n_stale / total_facts > 0.5:
            action = "re-evaluate"
            reason = (
                f"{n_stale} of {total_facts} upstream fact(s) have changed — "
                "a majority of the evidence base is outdated."
            )
        else:
            action = "update-fact"
            reason = (
                f"{n_stale} upstream fact(s) changed; review and update or retract "
                "those facts before re-asserting this decision."
            )

        # Determine priority from impact_score
        score = alert.impact_score
        if score >= 0.9:
            priority = "critical"
        elif score >= 0.7:
            priority = "high"
        elif score >= 0.4:
            priority = "medium"
        else:
            priority = "low"

        # Resolve stale fact subjects for display
        stale_fact_subjects: list[str] = []
        for fid in alert.stale_fact_ids:
            fact = store.get_fact(fid)
            if fact is not None:
                stale_fact_subjects.append(f"{fact.subject} {fact.predicate} {fact.object}")
            else:
                stale_fact_subjects.append(fid)

        recommendations.append(
            Recommendation(
                decision_label=alert.decision_label,
                reason=reason,
                action=action,
                priority=priority,
                stale_facts=stale_fact_subjects,
            )
        )

    recommendations.sort(key=lambda r: _priority_order.get(r.priority, 9))
    return recommendations
