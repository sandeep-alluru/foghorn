"""REVEAL — evidence sufficiency (arXiv 2608.08612).

Public case (Track B 20260811T041245Z):
  Agents stop answering once semantic relevance hits, missing temporal/causal
  or fine-grained evidence. Rubric-guided sufficiency is load-bearing.
"""

from __future__ import annotations

import pytest

from foghorn.closed_loop import ClosedLoopError
from foghorn.sufficiency import (
    DEFAULT_SUFFICIENCY_DIMENSIONS,
    EvidenceBundle,
    analyze_evidence_sufficiency,
    assert_evidence_sufficient,
    gate_evidence_sufficiency,
)


def test_empty_claim_answered_fails_loud() -> None:
    out = gate_evidence_sufficiency([], claim_answered=True)
    assert out.verdict == "FAIL_LOUD"
    assert out.exit_code == 2
    assert "REVEAL" in out.reason


def test_relevance_only_fails() -> None:
    bundles = [
        EvidenceBundle(
            bundle_id="b1",
            claim="when did X happen?",
            evidence_ids=("clip_3",),
            dimensions=("relevance",),
            relevance_only=True,
        )
    ]
    out = gate_evidence_sufficiency(bundles, claim_answered=True)
    assert out.ok is False
    assert out.verdict == "FAIL"
    assert "relevance" in out.reason.lower() or "REVEAL" in out.reason


def test_empty_evidence_ids_fail() -> None:
    bundles = [
        {
            "bundle_id": "b2",
            "claim": "who left?",
            "evidence_ids": [],
            "dimensions": ["temporal", "causal"],
        }
    ]
    out = gate_evidence_sufficiency(bundles, claim_answered=True)
    assert out.ok is False
    assert out.verdict == "FAIL"


def test_missing_dimensions_on_claim_fails() -> None:
    bundles = [
        EvidenceBundle(
            bundle_id="b3",
            claim="why?",
            evidence_ids=("e1",),
            dimensions=("relevance", "temporal"),
            relevance_only=False,
        )
    ]
    out = gate_evidence_sufficiency(
        bundles,
        claim_answered=True,
        required_dimensions=sorted(DEFAULT_SUFFICIENCY_DIMENSIONS),
        refuse_relevance_only=False,
    )
    assert out.ok is False
    assert "missing" in out.reason.lower() or "REVEAL" in out.reason


def test_sufficient_multi_dim_passes() -> None:
    bundles = [
        EvidenceBundle(
            bundle_id="b4",
            claim="full event",
            evidence_ids=("frame_1", "frame_2", "kg_edge"),
            dimensions=(
                "relevance",
                "temporal",
                "causal",
                "fine_grained",
                "completeness",
            ),
            relevance_only=False,
            rubric_scores={
                "relevance": 0.9,
                "temporal": 0.8,
                "causal": 0.85,
                "fine_grained": 0.7,
                "completeness": 0.75,
            },
        )
    ]
    out = gate_evidence_sufficiency(bundles, claim_answered=True)
    assert out.ok is True
    assert out.verdict == "PASS"
    assert out.exit_code == 0


def test_low_rubric_score_fails() -> None:
    bundles = [
        EvidenceBundle(
            bundle_id="b5",
            claim="action detail",
            evidence_ids=("v1",),
            dimensions=("relevance", "temporal", "causal", "fine_grained", "completeness"),
            rubric_scores={
                "relevance": 0.9,
                "temporal": 0.9,
                "causal": 0.9,
                "fine_grained": 0.1,
                "completeness": 0.9,
            },
        )
    ]
    out = gate_evidence_sufficiency(bundles, claim_answered=True, min_score=0.5)
    assert out.ok is False
    assert "score" in out.reason.lower() or "REVEAL" in out.reason


def test_analyze_report() -> None:
    report = analyze_evidence_sufficiency(
        [
            {
                "id": "x",
                "evidence_ids": ["a"],
                "dimensions": ["relevance"],
                "relevance_only": True,
            }
        ]
    )
    assert "x" in report.relevance_only_ids or report.relevance_only_ids
    assert report.to_dict()["bundle_count"] == 1


def test_assert_raises_and_passes() -> None:
    with pytest.raises(ClosedLoopError):
        assert_evidence_sufficient([], claim_answered=True)
    out = assert_evidence_sufficient(
        [
            EvidenceBundle(
                bundle_id="ok",
                evidence_ids=("e",),
                dimensions=tuple(sorted(DEFAULT_SUFFICIENCY_DIMENSIONS)),
                rubric_scores={d: 0.9 for d in DEFAULT_SUFFICIENCY_DIMENSIONS},
            )
        ],
        claim_answered=True,
    )
    assert out.ok is True
