"""EVIDENCE-LINK / Tracing the Heart - feature provenance gate.

Public case (Track B 20260810T001224Z / prior):
  arXiv 2608.06366 Tracing the Heart: An Evidence-Linked Pipeline for
  Heart-Failure Feature Engineering. Derived features without provenance,
  rubric compliance, or source inventory are not decision-grade.
"""

from __future__ import annotations

import pytest

from foghorn.closed_loop import ClosedLoopError
from foghorn.evidence import (
    DEFAULT_FEATURE_KINDS,
    EvidenceLink,
    FeatureRecord,
    analyze_evidence_links,
    assert_evidence_linked,
    gate_evidence_links,
    is_evidence_kind,
    is_feature_kind,
)


def test_feature_and_evidence_kind_helpers() -> None:
    assert is_feature_kind("derived_feature") is True
    assert is_feature_kind("aggregated_feature") is True
    assert is_feature_kind("unrelated_metric") is False
    assert is_evidence_kind("evidence_for") is True
    assert is_evidence_kind("source_table") is True
    assert is_evidence_kind("noise") is False
    assert "derived_feature" in DEFAULT_FEATURE_KINDS


def test_phantom_decision_grade_empty_features_fails_loud() -> None:
    """PRE-FIX class: claim decision-grade with no features → FAIL_LOUD."""
    out = gate_evidence_links(
        features=[],
        evidence_links=[],
        claim_decision_grade=True,
    )
    assert out.ok is False
    assert out.verdict == "FAIL_LOUD"
    assert out.exit_code == 2
    assert out.human_required is True
    assert "EVIDENCE-LINK" in out.reason


def test_decision_grade_features_without_links_fails_loud() -> None:
    feats = [
        FeatureRecord(feature_id="ef_frac", name="ejection_fraction", kind="derived_feature"),
        {"feature_id": "bnp_trend", "kind": "aggregated_feature"},
    ]
    out = gate_evidence_links(
        feats,
        evidence_links=[],
        claim_decision_grade=True,
    )
    assert out.verdict == "FAIL_LOUD"
    assert out.ok is False
    assert "zero evidence" in out.reason.lower() or "EVIDENCE-LINK" in out.reason


def test_unlinked_feature_fails() -> None:
    feats = [
        FeatureRecord(feature_id="a", kind="feature"),
        FeatureRecord(feature_id="b", kind="feature"),
    ]
    links = [EvidenceLink(feature_id="a", source_id="ehr.labs.1", source_kind="source_table")]
    out = gate_evidence_links(feats, links, claim_decision_grade=False)
    assert out.ok is False
    assert out.verdict == "FAIL"
    assert "b" in out.stale_source_ids


def test_empty_source_id_fails() -> None:
    feats = [FeatureRecord(feature_id="x")]
    # construct via dict then gate should catch empty if we force it
    with pytest.raises(ValueError, match="source_id must be non-empty"):
        EvidenceLink(feature_id="x", source_id="")
    # via analyze path: _as_link rejects empty
    out = gate_evidence_links(
        feats,
        [{"feature_id": "x", "source_id": "ok"}],
    )
    # valid path
    assert out.ok is True


def test_broken_source_inventory_fails() -> None:
    feats = [FeatureRecord(feature_id="x")]
    links = [EvidenceLink(feature_id="x", source_id="ghost_row", source_kind="source_row")]
    out = gate_evidence_links(
        feats,
        links,
        known_source_ids=["real_row_1", "real_row_2"],
        claim_decision_grade=True,
    )
    assert out.ok is False
    assert out.verdict == "FAIL"
    assert "unknown" in out.reason.lower() or "dangling" in out.reason.lower()


def test_rubric_fail_blocks() -> None:
    feats = [FeatureRecord(feature_id="bad", rubric_ok=False)]
    links = [EvidenceLink(feature_id="bad", source_id="src1")]
    out = gate_evidence_links(feats, links, claim_decision_grade=True)
    assert out.ok is False
    assert out.verdict == "FAIL"
    assert "rubric" in out.reason.lower()


def test_full_provenance_passes() -> None:
    feats = [
        FeatureRecord(feature_id="ef", name="ejection_fraction", kind="clinical_feature"),
        FeatureRecord(feature_id="nyha", name="nyha_class", kind="rubric_feature"),
    ]
    links = [
        EvidenceLink(
            feature_id="ef",
            source_id="echo.table.r12",
            source_kind="source_table",
            detail="LVEF numeric",
        ),
        EvidenceLink(
            feature_id="ef",
            source_id="guideline.acc.hf",
            source_kind="guideline_cite",
        ),
        EvidenceLink(
            feature_id="nyha",
            source_id="notes.visit.9",
            source_kind="source_row",
        ),
    ]
    known = ["echo.table.r12", "guideline.acc.hf", "notes.visit.9"]
    out = gate_evidence_links(
        feats,
        links,
        known_source_ids=known,
        claim_decision_grade=True,
        min_links_per_feature=1,
    )
    assert out.ok is True
    assert out.verdict == "PASS"
    assert out.exit_code == 0
    payload = out.to_dict()
    assert payload["ok"] is True
    assert payload["source_count"] == 2


def test_analyze_evidence_links_summary() -> None:
    summary = analyze_evidence_links(
        [{"id": "f1", "kind": "feature"}, {"feature_id": "f2"}],
        [{"feature_id": "f1", "source_id": "s1"}],
        min_links_per_feature=1,
    )
    assert summary["feature_count"] == 2
    assert "f2" in summary["unlinked_feature_ids"]
    assert summary["fully_linked"] is False


def test_assert_evidence_linked_raises() -> None:
    with pytest.raises(ClosedLoopError):
        assert_evidence_linked(
            [FeatureRecord(feature_id="solo")],
            [],
            claim_decision_grade=True,
        )


def test_assert_evidence_linked_passes() -> None:
    out = assert_evidence_linked(
        [FeatureRecord(feature_id="solo")],
        [EvidenceLink(feature_id="solo", source_id="src")],
        claim_decision_grade=True,
    )
    assert out.ok is True


def test_empty_inventory_non_claim_fails_loud() -> None:
    out = gate_evidence_links(require_features=True)
    assert out.verdict == "FAIL_LOUD"


def test_min_links_per_feature() -> None:
    feats = [FeatureRecord(feature_id="f")]
    links = [EvidenceLink(feature_id="f", source_id="s1")]
    out = gate_evidence_links(feats, links, min_links_per_feature=2)
    assert out.ok is False
    assert out.verdict == "FAIL"


def test_dict_features_and_links() -> None:
    out = gate_evidence_links(
        [{"feature_id": "bmi", "kind": "derived_feature", "rubric_ok": True}],
        [{"feature_id": "bmi", "object": "vitals.ht_wt.3", "predicate": "derived_from"}],
        claim_decision_grade=True,
    )
    assert out.ok is True
