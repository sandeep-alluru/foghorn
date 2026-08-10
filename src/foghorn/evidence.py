"""Evidence-linked features / provenance gate (EVIDENCE-LINK, arXiv 2608.06366).

Public case: *Tracing the Heart* — evidence-linked, rubric-grounded feature
engineering. Multi-agent EHR pipelines that emit derived features without
provenance (source table, raw row, guideline cite) are not decision-grade.

Product role in foghorn:
  Gate derived/aggregated features so agents refuse decision-grade use when
  evidence pointers are missing, empty, broken, or fail rubric compliance.
  Twin of activity-frame ``evidence_ptrs`` and wiki ``gate_source_freshness``.

Non-Ornament:
  Call ``gate_evidence_links`` before treating engineered features as facts for
  decisions. A feature store without provenance is ornament.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from typing import Any

from foghorn.closed_loop import ClosedLoopError, GateOutcome

# Predicates / kinds that mark engineered (derived) features.
DEFAULT_FEATURE_KINDS: frozenset[str] = frozenset(
    {
        "derived_feature",
        "feature",
        "aggregated_feature",
        "rubric_feature",
        "engineered_feature",
        "clinical_feature",
        "hf_feature",
        "structured_feature",
        "scored_feature",
    }
)

# Predicates / kinds that mark provenance edges.
DEFAULT_EVIDENCE_KINDS: frozenset[str] = frozenset(
    {
        "evidence_for",
        "evidence_link",
        "derived_from",
        "provenanced_from",
        "source_table",
        "source_row",
        "cites",
        "grounded_on",
        "guideline_cite",
        "raw_source",
    }
)


@dataclass(frozen=True)
class FeatureRecord:
    """A derived/engineered feature that must carry evidence provenance.

    Attributes:
        feature_id: Stable id of the feature.
        name: Human-readable feature name.
        kind: Feature class (``derived_feature``, ``aggregated_feature``, …).
        rubric_ok: Whether rubric/structure checks passed (default True).
        value: Optional payload (not gated on content).
        meta: Optional extra fields.
    """

    feature_id: str
    name: str = ""
    kind: str = "derived_feature"
    rubric_ok: bool = True
    value: Any = None
    meta: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not str(self.feature_id or "").strip():
            raise ValueError("FeatureRecord.feature_id must be non-empty")

    def to_dict(self) -> dict[str, Any]:
        return {
            "feature_id": self.feature_id,
            "name": self.name,
            "kind": self.kind,
            "rubric_ok": self.rubric_ok,
            "value": self.value,
            "meta": dict(self.meta),
        }


@dataclass(frozen=True)
class EvidenceLink:
    """Provenance edge from a feature to a source artifact.

    Attributes:
        feature_id: Feature this evidence supports.
        source_id: Id of source table row, fact, guideline, or raw capture.
        source_kind: Class of source (``source_table``, ``guideline_cite``, …).
        detail: Optional free-text cite / path.
    """

    feature_id: str
    source_id: str
    source_kind: str = "evidence_link"
    detail: str = ""

    def __post_init__(self) -> None:
        if not str(self.feature_id or "").strip():
            raise ValueError("EvidenceLink.feature_id must be non-empty")
        if not str(self.source_id or "").strip():
            raise ValueError("EvidenceLink.source_id must be non-empty")

    def to_dict(self) -> dict[str, Any]:
        return {
            "feature_id": self.feature_id,
            "source_id": self.source_id,
            "source_kind": self.source_kind,
            "detail": self.detail,
        }


def _canon(s: str) -> str:
    return (s or "").strip().lower().replace(" ", "_").replace("-", "_")


def is_feature_kind(kind: str, *, extra: Iterable[str] | None = None) -> bool:
    """True if *kind* marks an engineered/derived feature."""
    k = _canon(kind)
    if not k:
        return False
    allowed = set(DEFAULT_FEATURE_KINDS)
    if extra:
        allowed |= {_canon(x) for x in extra}
    return k in allowed or k.endswith("_feature") or k.startswith("feature_")


def is_evidence_kind(kind: str, *, extra: Iterable[str] | None = None) -> bool:
    """True if *kind* marks a provenance/evidence edge."""
    k = _canon(kind)
    if not k:
        return False
    allowed = set(DEFAULT_EVIDENCE_KINDS)
    if extra:
        allowed |= {_canon(x) for x in extra}
    return k in allowed or "evidence" in k or k.startswith("source_")


def _as_feature(item: Any) -> FeatureRecord:
    if isinstance(item, FeatureRecord):
        return item
    if isinstance(item, dict):
        fid = str(
            item.get("feature_id")
            or item.get("id")
            or item.get("name")
            or ""
        ).strip()
        if not fid:
            raise ValueError("feature missing feature_id/id/name")
        rubric = item.get("rubric_ok", item.get("rubric_pass", True))
        return FeatureRecord(
            feature_id=fid,
            name=str(item.get("name") or fid),
            kind=str(item.get("kind") or item.get("predicate") or "derived_feature"),
            rubric_ok=bool(rubric),
            value=item.get("value"),
            meta=dict(item.get("meta") or {}),
        )
    raise TypeError(f"unsupported feature type: {type(item)!r}")


def _as_link(item: Any) -> EvidenceLink:
    if isinstance(item, EvidenceLink):
        return item
    if isinstance(item, dict):
        fid = str(item.get("feature_id") or item.get("subject") or "").strip()
        sid = str(
            item.get("source_id")
            or item.get("object")
            or item.get("target")
            or item.get("evidence_ptr")
            or ""
        ).strip()
        if not fid or not sid:
            raise ValueError("evidence link needs feature_id and source_id")
        return EvidenceLink(
            feature_id=fid,
            source_id=sid,
            source_kind=str(
                item.get("source_kind")
                or item.get("kind")
                or item.get("predicate")
                or "evidence_link"
            ),
            detail=str(item.get("detail") or item.get("message") or ""),
        )
    raise TypeError(f"unsupported evidence link type: {type(item)!r}")


def analyze_evidence_links(
    features: Sequence[Any] | None = None,
    evidence_links: Sequence[Any] | None = None,
    *,
    known_source_ids: Sequence[str] | None = None,
    min_links_per_feature: int = 1,
) -> dict[str, Any]:
    """Summarize feature provenance coverage (does not gate).

    Returns covered/unlinked feature ids, broken source pointers, and rubric
    failures. Use :func:`gate_evidence_links` to refuse decision-grade use.
    """
    feats = [_as_feature(f) for f in (features or [])]
    links: list[EvidenceLink] = []
    for raw in evidence_links or []:
        links.append(_as_link(raw))

    known = {str(s).strip() for s in (known_source_ids or []) if str(s).strip()}
    by_feature: dict[str, list[EvidenceLink]] = {f.feature_id: [] for f in feats}
    for link in links:
        by_feature.setdefault(link.feature_id, []).append(link)

    unlinked: list[str] = []
    underlinked: list[str] = []
    for f in feats:
        n = len(by_feature.get(f.feature_id) or [])
        if n == 0:
            unlinked.append(f.feature_id)
        elif n < min_links_per_feature:
            underlinked.append(f.feature_id)

    broken: list[dict[str, str]] = []
    empty_source: list[dict[str, str]] = []
    for link in links:
        if not link.source_id:
            empty_source.append(link.to_dict())
            continue
        if known and link.source_id not in known:
            broken.append(
                {
                    "feature_id": link.feature_id,
                    "source_id": link.source_id,
                    "kind": "missing_source",
                }
            )

    rubric_fail = [f.feature_id for f in feats if not f.rubric_ok]

    return {
        "feature_count": len(feats),
        "evidence_link_count": len(links),
        "feature_ids": [f.feature_id for f in feats],
        "unlinked_feature_ids": unlinked,
        "underlinked_feature_ids": underlinked,
        "broken_source_ptrs": broken,
        "empty_source_ptrs": empty_source,
        "rubric_fail_ids": rubric_fail,
        "links_by_feature": {
            fid: [lk.to_dict() for lk in lks] for fid, lks in by_feature.items()
        },
        "fully_linked": (
            len(feats) > 0
            and len(unlinked) == 0
            and len(underlinked) == 0
            and len(broken) == 0
            and len(empty_source) == 0
            and len(rubric_fail) == 0
        ),
    }


def _fail_loud(reason: str, **kwargs: Any) -> GateOutcome:
    return GateOutcome(
        ok=False,
        verdict="FAIL_LOUD",
        reason=reason,
        exit_code=2,
        human_required=True,
        **kwargs,
    )


def _fail(reason: str, **kwargs: Any) -> GateOutcome:
    return GateOutcome(
        ok=False,
        verdict="FAIL",
        reason=reason,
        exit_code=1,
        human_required=True,
        **kwargs,
    )


def gate_evidence_links(
    features: Sequence[Any] | None = None,
    evidence_links: Sequence[Any] | None = None,
    *,
    known_source_ids: Sequence[str] | None = None,
    claim_decision_grade: bool = False,
    require_features: bool = True,
    min_links_per_feature: int = 1,
    refuse_rubric_fail: bool = True,
    refuse_broken_sources: bool = True,
) -> GateOutcome:
    """Refuse decision-grade use of features without evidence provenance.

    Public case: arXiv 2608.06366 *Tracing the Heart: An Evidence-Linked
    Pipeline for Heart-Failure Feature Engineering*. Derived features without
    structural integrity, rubric compliance, and provenance are not
    decision-grade. Foghorn already ages wiki sources and requires activity
    evidence_ptrs; this gate covers **feature engineering** provenance.

    Rules:

    1. ``claim_decision_grade`` with zero features when required → **FAIL_LOUD**
    2. Empty features + empty links (non-claim, require_features) → **FAIL_LOUD**
    3. Any feature with fewer than ``min_links_per_feature`` links → **FAIL**
       (or **FAIL_LOUD** when claim_decision_grade and zero links total)
    4. Evidence pointer with empty ``source_id`` → **FAIL**
    5. ``source_id`` not in ``known_source_ids`` (when provided) → **FAIL**
    6. ``rubric_ok=False`` when ``refuse_rubric_fail`` → **FAIL**
    7. Fully linked, rubric-ok features → **PASS**

    Args:
        features: Feature records (dicts or :class:`FeatureRecord`).
        evidence_links: Provenance edges (dicts or :class:`EvidenceLink`).
        known_source_ids: Optional inventory of valid source artifact ids.
        claim_decision_grade: Features claimed ready for clinical/decision use.
        require_features: Empty feature inventory → FAIL_LOUD when claiming
            or when True and no links either.
        min_links_per_feature: Minimum evidence edges per feature (default 1).
        refuse_rubric_fail: Rubric non-compliance → FAIL.
        refuse_broken_sources: Unknown source_id → FAIL when inventory given.
    """
    try:
        summary = analyze_evidence_links(
            features,
            evidence_links,
            known_source_ids=known_source_ids,
            min_links_per_feature=min_links_per_feature,
        )
    except (TypeError, ValueError) as exc:
        return _fail_loud(
            f"EVIDENCE-LINK: invalid feature/link payload: {exc}",
            source_count=0,
        )

    n_feat = int(summary["feature_count"])
    n_links = int(summary["evidence_link_count"])
    unlinked = tuple(summary["unlinked_feature_ids"])
    under = tuple(summary["underlinked_feature_ids"])
    broken = tuple(summary["broken_source_ptrs"])
    empty_src = tuple(summary["empty_source_ptrs"])
    rubric_fail = tuple(summary["rubric_fail_ids"])

    if claim_decision_grade and require_features and n_feat == 0:
        return _fail_loud(
            "EVIDENCE-LINK: claim_decision_grade with zero features - "
            "phantom evidence-linked pipeline (arXiv 2608.06366); refuse "
            "decision-grade use without engineered feature inventory",
            source_count=0,
        )

    if require_features and n_feat == 0 and n_links == 0:
        return _fail_loud(
            "EVIDENCE-LINK: empty features and empty evidence links - "
            "nothing to ground; compile provenance before use",
            source_count=0,
        )

    if claim_decision_grade and n_feat > 0 and n_links == 0:
        return _fail_loud(
            f"EVIDENCE-LINK: {n_feat} decision-grade feature(s) with zero "
            f"evidence links - refuse unprovenanced feature engineering "
            f"(arXiv 2608.06366 Tracing the Heart)",
            source_count=n_feat,
            stale_source_ids=unlinked,
        )

    if unlinked or under:
        bad = list(unlinked) + [u for u in under if u not in unlinked]
        return _fail(
            f"EVIDENCE-LINK: {len(bad)} feature(s) lack required provenance "
            f"(min_links={min_links_per_feature}): {bad[:8]}"
            + ("…" if len(bad) > 8 else ""),
            source_count=n_feat,
            stale_source_ids=tuple(bad),
        )

    if empty_src:
        return _fail(
            f"EVIDENCE-LINK: {len(empty_src)} evidence pointer(s) with empty "
            f"source_id - refuse broken provenance",
            source_count=n_feat,
        )

    if refuse_broken_sources and broken:
        ids = [b.get("source_id", "") for b in broken]
        return _fail(
            f"EVIDENCE-LINK: {len(broken)} evidence pointer(s) reference "
            f"unknown sources {ids[:8]} - refuse dangling provenance",
            source_count=n_feat,
            stale_source_ids=tuple(str(x) for x in ids if x),
        )

    if refuse_rubric_fail and rubric_fail:
        return _fail(
            f"EVIDENCE-LINK: {len(rubric_fail)} feature(s) failed rubric/"
            f"structure checks: {list(rubric_fail)[:8]} - refuse "
            f"non-compliant engineered features",
            source_count=n_feat,
            stale_source_ids=rubric_fail,
        )

    return GateOutcome(
        ok=True,
        verdict="PASS",
        reason=(
            f"EVIDENCE-LINK ok: features={n_feat} links={n_links} "
            f"claim_decision_grade={claim_decision_grade}"
        ),
        exit_code=0,
        source_count=n_feat,
        human_required=False,
        stale_source_ids=(),
    )


def assert_evidence_linked(
    features: Sequence[Any] | None = None,
    evidence_links: Sequence[Any] | None = None,
    **kwargs: Any,
) -> GateOutcome:
    """Raise :class:`ClosedLoopError` unless :func:`gate_evidence_links` is ok."""
    outcome = gate_evidence_links(features, evidence_links, **kwargs)
    if not outcome.ok:
        raise ClosedLoopError(f"{outcome.verdict}: {outcome.reason}")
    return outcome
