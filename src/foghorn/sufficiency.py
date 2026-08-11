"""REVEAL — evidence sufficiency verification (arXiv 2608.08612).

Public case: *REVEAL: A Rubric-Guided Agent for Explicit Evidence Sufficiency
Verification in Long-Video Question Answering*. Retrieval-augmented agents
often stop once **semantically relevant** clues are found, while temporal,
causal, or fine-grained action evidence is still missing. Relevance ≠
sufficiency.

Product role in foghorn (EVIDENCE-LINK / TA-RAG twin):
  Gate answers that claim completion when the evidence rubric is incomplete —
  not only “has a source,” but **enough** of the right kinds of support.

Non-Ornament:
  Call ``gate_evidence_sufficiency`` before accepting a retrieved-memory
  answer as decided. Pair with ``gate_evidence_links`` (provenance) and
  ``gate_source_freshness`` (age).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from foghorn.closed_loop import ClosedLoopError, GateOutcome

# Rubric dimensions for evidence sufficiency (REVEAL-class).
DEFAULT_SUFFICIENCY_DIMENSIONS: frozenset[str] = frozenset(
    {
        "relevance",
        "temporal",
        "causal",
        "fine_grained",
        "completeness",
    }
)

# Dimensions beyond bare topical match (paper: stop-too-early class).
DEEP_SUFFICIENCY_DIMENSIONS: frozenset[str] = frozenset(
    {
        "temporal",
        "causal",
        "fine_grained",
        "completeness",
    }
)


@dataclass(frozen=True)
class EvidenceBundle:
    """Evidence supporting one claim or answer span.

    Attributes:
        bundle_id: Stable id.
        claim: Claim / question fragment being supported.
        evidence_ids: Provenance ids (frames, chunks, facts).
        dimensions: Sufficiency dimensions this bundle covers.
        relevance_only: True if only semantic relevance was checked.
        rubric_scores: Optional per-dimension scores in [0, 1].
    """

    bundle_id: str
    claim: str = ""
    evidence_ids: tuple[str, ...] = ()
    dimensions: tuple[str, ...] = ()
    relevance_only: bool = False
    rubric_scores: dict[str, float] = field(default_factory=dict)
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "bundle_id": self.bundle_id,
            "claim": self.claim,
            "evidence_ids": list(self.evidence_ids),
            "dimensions": list(self.dimensions),
            "relevance_only": self.relevance_only,
            "rubric_scores": dict(self.rubric_scores),
            "meta": dict(self.meta),
        }


@dataclass(frozen=True)
class SufficiencyReport:
    """Aggregate evidence-sufficiency analysis."""

    bundle_count: int
    covered_dimensions: tuple[str, ...]
    missing_dimensions: tuple[str, ...]
    relevance_only_ids: tuple[str, ...]
    empty_evidence_ids: tuple[str, ...]
    low_score_dims: tuple[str, ...]
    details: dict[str, Any] = field(default_factory=dict)

    @property
    def sufficient(self) -> bool:
        return (
            not self.missing_dimensions
            and not self.relevance_only_ids
            and not self.empty_evidence_ids
            and not self.low_score_dims
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "bundle_count": self.bundle_count,
            "covered_dimensions": list(self.covered_dimensions),
            "missing_dimensions": list(self.missing_dimensions),
            "relevance_only_ids": list(self.relevance_only_ids),
            "empty_evidence_ids": list(self.empty_evidence_ids),
            "low_score_dims": list(self.low_score_dims),
            "sufficient": self.sufficient,
            "details": dict(self.details),
        }


def _canon_dim(label: str) -> str:
    d = (label or "").strip().lower().replace(" ", "_").replace("-", "_")
    aliases = {
        "relevant": "relevance",
        "semantic": "relevance",
        "time": "temporal",
        "timing": "temporal",
        "cause": "causal",
        "causality": "causal",
        "action": "fine_grained",
        "fine_grained_action": "fine_grained",
        "detail": "fine_grained",
        "complete": "completeness",
        "coverage": "completeness",
    }
    return aliases.get(d, d)


def _as_bundle(item: Any, index: int = 0) -> EvidenceBundle:
    if isinstance(item, EvidenceBundle):
        return item
    if not isinstance(item, dict):
        raise TypeError(f"bundle must be EvidenceBundle or dict, got {type(item)!r}")
    bid = str(item.get("bundle_id") or item.get("id") or f"bundle_{index}").strip()
    eids_raw = item.get("evidence_ids") or item.get("sources") or item.get("evidence") or []
    if isinstance(eids_raw, str):
        eids_raw = [eids_raw]
    eids = tuple(str(x).strip() for x in eids_raw if str(x).strip())
    dims_raw = item.get("dimensions") or item.get("dims") or item.get("rubric") or []
    if isinstance(dims_raw, str):
        dims_raw = [dims_raw]
    dims = tuple(_canon_dim(str(x)) for x in dims_raw if _canon_dim(str(x)))
    scores_in = item.get("rubric_scores") or item.get("scores") or {}
    scores: dict[str, float] = {}
    if isinstance(scores_in, dict):
        for k, v in scores_in.items():
            try:
                scores[_canon_dim(str(k))] = float(v)
            except (TypeError, ValueError):
                continue
    rel_only = bool(item.get("relevance_only") or item.get("semantic_only") or False)
    if not rel_only and dims and set(dims) <= {"relevance"}:
        rel_only = True
    return EvidenceBundle(
        bundle_id=bid,
        claim=str(item.get("claim") or item.get("question") or ""),
        evidence_ids=eids,
        dimensions=dims,
        relevance_only=rel_only,
        rubric_scores=scores,
        meta=dict(item.get("meta") or {}) if isinstance(item.get("meta"), dict) else {},
    )


def analyze_evidence_sufficiency(
    bundles: Sequence[Any] | None,
    *,
    required_dimensions: Sequence[str] | None = None,
    min_score: float = 0.5,
    require_deep_dims: bool = True,
) -> SufficiencyReport:
    """Summarize rubric coverage across evidence bundles (no gate)."""
    parsed = [_as_bundle(b, i) for i, b in enumerate(bundles or [])]
    required = [
        _canon_dim(x)
        for x in (
            required_dimensions
            if required_dimensions is not None
            else sorted(DEFAULT_SUFFICIENCY_DIMENSIONS)
        )
        if _canon_dim(x)
    ]
    covered: set[str] = set()
    rel_only: list[str] = []
    empty: list[str] = []
    low: list[str] = []

    for b in parsed:
        if not b.evidence_ids:
            empty.append(b.bundle_id)
        for d in b.dimensions:
            covered.add(d)
        for d, sc in b.rubric_scores.items():
            covered.add(d)
            if sc < min_score:
                low.append(f"{b.bundle_id}:{d}")
        if b.relevance_only or (
            require_deep_dims
            and b.dimensions
            and not (set(b.dimensions) & DEEP_SUFFICIENCY_DIMENSIONS)
            and "relevance" in b.dimensions
        ):
            rel_only.append(b.bundle_id)

    missing = tuple(d for d in required if d not in covered)
    return SufficiencyReport(
        bundle_count=len(parsed),
        covered_dimensions=tuple(sorted(covered)),
        missing_dimensions=missing,
        relevance_only_ids=tuple(dict.fromkeys(rel_only)),
        empty_evidence_ids=tuple(dict.fromkeys(empty)),
        low_score_dims=tuple(dict.fromkeys(low)),
        details={
            "required_dimensions": required,
            "min_score": min_score,
        },
    )


def gate_evidence_sufficiency(
    bundles: Sequence[Any] | None,
    *,
    claim_answered: bool = False,
    require_bundles: bool = True,
    required_dimensions: Sequence[str] | None = None,
    refuse_relevance_only: bool = True,
    refuse_missing_dimensions: bool = True,
    refuse_empty_evidence: bool = True,
    refuse_low_scores: bool = True,
    min_score: float = 0.5,
    require_deep_dims: bool = True,
) -> GateOutcome:
    """Refuse answers that stop at relevance without sufficient evidence.

    Public case: arXiv 2608.08612 REVEAL — agents answer once semantic
    retrieval hits, missing temporal/causal/fine-grained support.

    Rules:

    1. ``claim_answered`` with zero bundles → **FAIL_LOUD**
    2. Empty inventory when required → **FAIL_LOUD**
    3. Bundles with empty ``evidence_ids`` → **FAIL**
    4. Relevance-only bundles (no deep dims) → **FAIL**
    5. Required rubric dimensions missing globally → **FAIL**
    6. Rubric scores below ``min_score`` → **FAIL**
    7. Multi-dimension sufficient evidence → **PASS**
    """
    if not bundles:
        if claim_answered or require_bundles:
            return GateOutcome(
                ok=False,
                verdict="FAIL_LOUD",
                reason=(
                    "REVEAL: empty evidence bundles — cannot claim answered "
                    f"without sufficiency inventory (claim_answered={claim_answered}; "
                    "arXiv 2608.08612)"
                ),
                exit_code=2,
                human_required=True,
                source_count=0,
            )
        return GateOutcome(
            ok=True,
            verdict="PASS",
            reason="REVEAL: no bundles required",
            exit_code=0,
        )

    try:
        report = analyze_evidence_sufficiency(
            bundles,
            required_dimensions=required_dimensions,
            min_score=min_score,
            require_deep_dims=require_deep_dims,
        )
    except (TypeError, ValueError) as exc:
        return GateOutcome(
            ok=False,
            verdict="FAIL_LOUD",
            reason=f"REVEAL: invalid evidence payload: {exc}",
            exit_code=2,
            human_required=True,
        )

    n = report.bundle_count

    if refuse_empty_evidence and report.empty_evidence_ids:
        return GateOutcome(
            ok=False,
            verdict="FAIL",
            reason=(
                f"REVEAL: {len(report.empty_evidence_ids)} bundle(s) have zero "
                f"evidence_ids {list(report.empty_evidence_ids)[:8]} — refuse "
                f"unsupported claims"
            ),
            exit_code=1,
            human_required=True,
            source_count=n,
            stale_source_ids=report.empty_evidence_ids,
        )

    if refuse_relevance_only and report.relevance_only_ids:
        return GateOutcome(
            ok=False,
            verdict="FAIL",
            reason=(
                f"REVEAL: {len(report.relevance_only_ids)} bundle(s) are "
                f"relevance-only {list(report.relevance_only_ids)[:8]} — refuse "
                f"early answer without temporal/causal/fine-grained sufficiency "
                f"(arXiv 2608.08612)"
            ),
            exit_code=1,
            human_required=True,
            source_count=n,
            stale_source_ids=report.relevance_only_ids,
        )

    if refuse_missing_dimensions and report.missing_dimensions and claim_answered:
        return GateOutcome(
            ok=False,
            verdict="FAIL",
            reason=(
                f"REVEAL: missing sufficiency dimensions "
                f"{list(report.missing_dimensions)} covered="
                f"{list(report.covered_dimensions)} — refuse incomplete rubric"
            ),
            exit_code=1,
            human_required=True,
            source_count=n,
            stale_source_ids=report.missing_dimensions,
        )

    if refuse_low_scores and report.low_score_dims:
        return GateOutcome(
            ok=False,
            verdict="FAIL",
            reason=(
                f"REVEAL: rubric scores below min={min_score} on "
                f"{list(report.low_score_dims)[:8]} — refuse weak evidence"
            ),
            exit_code=1,
            human_required=True,
            source_count=n,
        )

    # When claiming answered, still require no missing dims even if flag set
    if claim_answered and report.missing_dimensions and refuse_missing_dimensions:
        # already handled above
        pass

    return GateOutcome(
        ok=True,
        verdict="PASS",
        reason=(
            f"REVEAL ok: bundles={n} covered={list(report.covered_dimensions)} "
            f"relevance_only=0 claim_answered={claim_answered}"
        ),
        exit_code=0,
        source_count=n,
        human_required=False,
    )


def assert_evidence_sufficient(
    bundles: Sequence[Any] | None,
    **kwargs: Any,
) -> GateOutcome:
    """Raise :class:`ClosedLoopError` unless :func:`gate_evidence_sufficiency` is ok."""
    outcome = gate_evidence_sufficiency(bundles, **kwargs)
    if not outcome.ok:
        raise ClosedLoopError(f"{outcome.verdict}: {outcome.reason}")
    return outcome
