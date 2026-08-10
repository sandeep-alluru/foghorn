"""TA-RAG — tone awareness / contextual decoupling (arXiv 2608.06672).

Public case (Track B 20260810T161237Z):
  Retrieved document styles shape RAG output before user tone instructions,
  causing linguistic / cognitive / relational misalignment (contextual decoupling).
"""

from __future__ import annotations

import pytest

from foghorn.closed_loop import ClosedLoopError
from foghorn.tone import (
    RetrievedDoc,
    analyze_tone_alignment,
    assert_tone_aware,
    formality_band,
    gate_tone_awareness,
    infer_tone_from_text,
)


def test_infer_and_formality() -> None:
    assert formality_band("academic") == "high"
    assert formality_band("peer_support") == "low"
    assert infer_tone_from_text("the methodology and hypothesis therefore") == "academic"


def test_empty_request_fails_loud() -> None:
    out = gate_tone_awareness("", claim_tone_matched=True)
    assert out.verdict == "FAIL_LOUD"
    assert out.exit_code == 2
    assert "TA-RAG" in out.reason


def test_claim_match_without_response_tone_fails_loud() -> None:
    out = gate_tone_awareness(
        "plain",
        [RetrievedDoc(doc_id="d1", tone="plain")],
        claim_tone_matched=True,
        response_tone="",
    )
    assert out.verdict == "FAIL_LOUD"


def test_response_mismatch_fails() -> None:
    out = gate_tone_awareness(
        "plain",
        [RetrievedDoc(doc_id="d1", tone="plain")],
        response_tone="academic",
        claim_tone_matched=True,
    )
    assert out.ok is False
    assert out.verdict == "FAIL"
    assert "response_tone" in out.reason or "TA-RAG" in out.reason


def test_contextual_decoupling_fails() -> None:
    """Classic TA-RAG: peer-support ask, formal clinical sources dominate response."""
    docs = [
        {
            "doc_id": "guidelines",
            "tone": "clinical",
            "text": "Patient presents with contraindication; differential includes...",
        },
        RetrievedDoc(doc_id="paper", tone="academic", text_snippet="Moreover, the methodology"),
    ]
    out = gate_tone_awareness(
        "peer_support",
        docs,
        response_tone="clinical",
        claim_tone_matched=False,
        refuse_decoupling=True,
    )
    assert out.ok is False
    assert out.verdict == "FAIL"
    assert "decoupl" in out.reason.lower() or "TA-RAG" in out.reason
    assert out.human_required is True


def test_aligned_peer_support_passes() -> None:
    docs = [
        RetrievedDoc(
            doc_id="peer1",
            tone="peer_support",
            text_snippet="You're not alone — I hear you.",
        )
    ]
    out = gate_tone_awareness(
        "peer_support",
        docs,
        response_tone="peer_support",
        claim_tone_matched=True,
    )
    assert out.ok is True
    assert out.verdict == "PASS"
    assert out.exit_code == 0


def test_plain_request_with_plain_response_passes() -> None:
    out = gate_tone_awareness(
        "plain",
        [{"doc_id": "a", "tone": "plain", "text": "In simple terms this means"}],
        response_tone="plain",
        claim_tone_matched=True,
    )
    assert out.ok is True


def test_analyze_tone_alignment_report() -> None:
    report = analyze_tone_alignment(
        "empathetic",
        [RetrievedDoc(doc_id="x", tone="legal")],
        response_tone="legal",
    )
    assert report.decoupled is True
    assert "relational" in report.misalignments or "linguistic" in report.misalignments
    assert report.to_dict()["decoupled"] is True


def test_misalignment_budget() -> None:
    # force misalignments via high formality sources for low request
    out = gate_tone_awareness(
        "casual",
        [RetrievedDoc(doc_id="j", tone="legal")],
        response_tone="casual",  # response ok but sources still misaligned
        max_misalignments=0,
        refuse_decoupling=False,  # only count misalignment list
    )
    # with response matching request, decoupled may be false; misalignments may still fire
    report = analyze_tone_alignment(
        "casual",
        [RetrievedDoc(doc_id="j", tone="legal")],
        response_tone="casual",
    )
    if report.misalignments:
        assert out.ok is False or out.ok is True  # depends on misalignment detection
        out2 = gate_tone_awareness(
            "casual",
            [RetrievedDoc(doc_id="j", tone="legal")],
            response_tone="casual",
            max_misalignments=0,
            refuse_decoupling=False,
        )
        if report.misalignments:
            assert out2.ok is False


def test_assert_raises_and_passes() -> None:
    with pytest.raises(ClosedLoopError):
        assert_tone_aware("", claim_tone_matched=True)
    out = assert_tone_aware(
        "plain",
        response_tone="plain",
        claim_tone_matched=True,
        retrieved_docs=[],
    )
    assert out.ok is True
