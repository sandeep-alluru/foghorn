"""TA-RAG tone awareness / contextual decoupling gate (arXiv 2608.06672).

Public case: *TA-RAG: Tone Awareness as a Design Imperative for
Retrieval-Augmented Generation*. Retrieved documents carry professional
jargon, formal, or academic styles that shape RAG output **before** user
tone instructions are honored — *contextual decoupling*: factually fine,
socially/operationally misaligned.

Three communicative misalignments (paper):
  * linguistic — jargon vs plain register
  * cognitive — complexity vs audience capacity
  * relational — professional distance vs peer support

Product role in foghorn (STALE-WIKI / EVIDENCE-LINK twin):
  Gate retrieval-grounded answers so agents refuse when source tone dominates
  the requested recipient tone, even if facts are fresh and evidenced.

Non-Ornament:
  Call ``gate_tone_awareness`` after retrieval, before shipping user-facing
  text that claimed a specific tone/register.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from foghorn.closed_loop import ClosedLoopError, GateOutcome

# Canonical tone / register labels.
DEFAULT_TONES: frozenset[str] = frozenset(
    {
        "plain",
        "casual",
        "peer_support",
        "empathetic",
        "friendly",
        "formal",
        "academic",
        "clinical",
        "legal",
        "technical",
        "professional",
        "bureaucratic",
        "neutral",
    }
)

# Tones that are "high formality / expert" — often clash with peer/plain asks.
HIGH_FORMALITY_TONES: frozenset[str] = frozenset(
    {
        "formal",
        "academic",
        "clinical",
        "legal",
        "technical",
        "professional",
        "bureaucratic",
    }
)

# Tones that are "low formality / audience-aligned" for peer support class.
LOW_FORMALITY_TONES: frozenset[str] = frozenset(
    {
        "plain",
        "casual",
        "peer_support",
        "empathetic",
        "friendly",
    }
)

# Lexical hints for weak tone inference from snippets.
_TONE_LEXICON: dict[str, tuple[str, ...]] = {
    "academic": ("therefore", "moreover", "hypothesis", "et al", "methodology"),
    "clinical": ("patient presents", "differential", "contraindication", "mg/dl", "diagnosis"),
    "legal": ("hereinafter", "pursuant", "shall not", "liable", "jurisdiction"),
    "technical": ("api", "latency", "throughput", "stack trace", "null pointer"),
    "formal": ("respectfully", "kindly note", "please be advised", "herein"),
    "peer_support": ("i hear you", "you're not alone", "same here", "hugs", "sending love"),
    "plain": ("in simple terms", "basically", "for example", "this means"),
    "empathetic": ("i understand", "that sounds hard", "sorry you're", "it's okay to"),
}


@dataclass(frozen=True)
class RetrievedDoc:
    """One retrieved grounding document with optional tone label."""

    doc_id: str
    tone: str = ""
    text_snippet: str = ""
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "doc_id": self.doc_id,
            "tone": self.tone,
            "text_snippet": self.text_snippet,
            "meta": dict(self.meta),
        }


@dataclass(frozen=True)
class ToneReport:
    """Analysis of tone alignment between request, sources, and response."""

    requested_tone: str
    response_tone: str
    source_tones: tuple[str, ...]
    dominant_source_tone: str
    misalignments: tuple[str, ...]  # linguistic | cognitive | relational
    decoupled: bool
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "requested_tone": self.requested_tone,
            "response_tone": self.response_tone,
            "source_tones": list(self.source_tones),
            "dominant_source_tone": self.dominant_source_tone,
            "misalignments": list(self.misalignments),
            "decoupled": self.decoupled,
            "details": dict(self.details),
        }


def _canon_tone(label: str) -> str:
    t = (label or "").strip().lower().replace(" ", "_").replace("-", "_")
    aliases = {
        "peer": "peer_support",
        "peersupport": "peer_support",
        "simple": "plain",
        "lay": "plain",
        "expert": "technical",
        "jargon": "technical",
        "medical": "clinical",
        "doctor": "clinical",
        "friendly_casual": "casual",
    }
    return aliases.get(t, t)


def infer_tone_from_text(text: str) -> str:
    """Weak lexicon-based tone guess (empty string if no signal)."""
    blob = (text or "").lower()
    if not blob:
        return ""
    scores: dict[str, int] = {}
    for tone, words in _TONE_LEXICON.items():
        scores[tone] = sum(1 for w in words if w in blob)
    best = max(scores, key=lambda k: scores[k])
    return best if scores[best] > 0 else ""


def formality_band(tone: str) -> str:
    """Return ``high``, ``low``, or ``mid`` formality band for *tone*."""
    t = _canon_tone(tone)
    if t in HIGH_FORMALITY_TONES:
        return "high"
    if t in LOW_FORMALITY_TONES:
        return "low"
    return "mid"


def _as_doc(item: Any, index: int = 0) -> RetrievedDoc:
    if isinstance(item, RetrievedDoc):
        return item
    if not isinstance(item, dict):
        raise TypeError(f"doc must be RetrievedDoc or dict, got {type(item)!r}")
    did = str(item.get("doc_id") or item.get("id") or item.get("source_id") or f"doc_{index}")
    tone = str(item.get("tone") or item.get("register") or item.get("style") or "")
    snippet = str(item.get("text_snippet") or item.get("text") or item.get("content") or "")
    if not tone and snippet:
        tone = infer_tone_from_text(snippet)
    return RetrievedDoc(
        doc_id=did.strip(),
        tone=_canon_tone(tone),
        text_snippet=snippet,
        meta=dict(item.get("meta") or {}) if isinstance(item.get("meta"), dict) else {},
    )


def analyze_tone_alignment(
    requested_tone: str,
    retrieved_docs: Sequence[Any] | None = None,
    *,
    response_tone: str = "",
    response_text: str = "",
) -> ToneReport:
    """Detect contextual decoupling between request, sources, and response."""
    req = _canon_tone(requested_tone)
    docs = [_as_doc(d, i) for i, d in enumerate(retrieved_docs or [])]
    source_tones = tuple(d.tone for d in docs if d.tone)
    # dominant = mode
    dominant = ""
    if source_tones:
        counts: dict[str, int] = {}
        for t in source_tones:
            counts[t] = counts.get(t, 0) + 1
        dominant = max(counts, key=lambda k: counts[k])

    resp = _canon_tone(response_tone)
    if not resp and response_text:
        resp = _canon_tone(infer_tone_from_text(response_text))

    mis: list[str] = []
    req_band = formality_band(req) if req else "mid"
    dom_band = formality_band(dominant) if dominant else "mid"
    resp_band = formality_band(resp) if resp else "mid"

    # linguistic: register clash request vs sources
    if req and dominant and req != dominant and req_band != dom_band:
        mis.append("linguistic")
    # cognitive: high formality sources for low formality request (jargon load)
    if req_band == "low" and dom_band == "high":
        if "cognitive" not in mis:
            mis.append("cognitive")
    # relational: peer_support/empathetic request vs clinical/formal sources
    if req in {"peer_support", "empathetic", "friendly"} and dominant in HIGH_FORMALITY_TONES:
        if "relational" not in mis:
            mis.append("relational")

    # decoupled: response follows dominant source band, not request
    decoupled = False
    if req and resp:
        if resp != req and formality_band(resp) != req_band:
            if dominant and formality_band(resp) == dom_band:
                decoupled = True
            elif not dominant:
                decoupled = True
        if resp != req and req_band == "low" and resp_band == "high":
            decoupled = True
    elif req and dominant and not resp:
        # no response tone but sources already clash hard
        if req_band == "low" and dom_band == "high":
            decoupled = True

    return ToneReport(
        requested_tone=req,
        response_tone=resp,
        source_tones=source_tones,
        dominant_source_tone=dominant,
        misalignments=tuple(dict.fromkeys(mis)),
        decoupled=decoupled,
        details={
            "doc_count": len(docs),
            "req_band": req_band,
            "dom_band": dom_band,
            "resp_band": resp_band,
        },
    )


def gate_tone_awareness(
    requested_tone: str,
    retrieved_docs: Sequence[Any] | None = None,
    *,
    response_tone: str = "",
    response_text: str = "",
    claim_tone_matched: bool = False,
    require_request: bool = True,
    refuse_decoupling: bool = True,
    refuse_response_mismatch: bool = True,
    max_misalignments: int = 0,
) -> GateOutcome:
    """Refuse RAG outputs that ignore requested tone (contextual decoupling).

    Public case: arXiv 2608.06672 TA-RAG — retrieved document styles shape
    generation before tone instructions, causing linguistic / cognitive /
    relational misalignment even when facts are correct.

    Rules:

    1. ``claim_tone_matched`` with empty requested tone → **FAIL_LOUD**
    2. Empty request when ``require_request`` → **FAIL_LOUD**
    3. ``response_tone`` ≠ ``requested_tone`` when claiming match → **FAIL**
    4. Contextual decoupling (response follows source formality, not request)
       → **FAIL**
    5. Misalignment count above ``max_misalignments`` (default 0) → **FAIL**
    6. Aligned request/response (sources optional) → **PASS**
    """
    req = _canon_tone(requested_tone)
    if require_request and not req:
        return GateOutcome(
            ok=False,
            verdict="FAIL_LOUD",
            reason=(
                "TA-RAG: empty requested_tone — cannot gate tone-aware RAG "
                f"(claim_tone_matched={claim_tone_matched}; arXiv 2608.06672)"
            ),
            exit_code=2,
            human_required=True,
            source_count=0,
        )

    try:
        report = analyze_tone_alignment(
            req,
            retrieved_docs,
            response_tone=response_tone,
            response_text=response_text,
        )
    except (TypeError, ValueError) as exc:
        return GateOutcome(
            ok=False,
            verdict="FAIL_LOUD",
            reason=f"TA-RAG: invalid tone payload: {exc}",
            exit_code=2,
            human_required=True,
        )

    n_docs = int(report.details.get("doc_count") or 0)

    if claim_tone_matched and refuse_response_mismatch:
        resp = report.response_tone
        if not resp:
            return GateOutcome(
                ok=False,
                verdict="FAIL_LOUD",
                reason=(
                    "TA-RAG: claim_tone_matched but response_tone empty — "
                    "phantom tone compliance (arXiv 2608.06672)"
                ),
                exit_code=2,
                human_required=True,
                source_count=n_docs,
            )
        if resp != report.requested_tone:
            return GateOutcome(
                ok=False,
                verdict="FAIL",
                reason=(
                    f"TA-RAG: response_tone={resp!r} ≠ requested_tone="
                    f"{report.requested_tone!r} — refuse claimed tone match"
                ),
                exit_code=1,
                human_required=True,
                source_count=n_docs,
            )

    if refuse_decoupling and report.decoupled:
        return GateOutcome(
            ok=False,
            verdict="FAIL",
            reason=(
                f"TA-RAG: contextual decoupling — requested={report.requested_tone!r} "
                f"dominant_source={report.dominant_source_tone!r} "
                f"response={report.response_tone!r} misalignments="
                f"{list(report.misalignments)}; retrieved style overrode "
                f"recipient tone (arXiv 2608.06672)"
            ),
            exit_code=1,
            human_required=True,
            source_count=n_docs,
            stale_source_ids=tuple(report.misalignments),
        )

    if len(report.misalignments) > max_misalignments:
        return GateOutcome(
            ok=False,
            verdict="FAIL",
            reason=(
                f"TA-RAG: {len(report.misalignments)} communicative misalignment(s) "
                f"{list(report.misalignments)} exceed max={max_misalignments} "
                f"(linguistic/cognitive/relational class)"
            ),
            exit_code=1,
            human_required=True,
            source_count=n_docs,
            stale_source_ids=tuple(report.misalignments),
        )

    resp_label = report.response_tone if report.response_tone else "n/a"
    return GateOutcome(
        ok=True,
        verdict="PASS",
        reason=(
            f"TA-RAG ok: requested={report.requested_tone!r} "
            f"response={resp_label!r} docs={n_docs} decoupled=False"
        ),
        exit_code=0,
        source_count=n_docs,
        human_required=False,
    )


def assert_tone_aware(
    requested_tone: str,
    retrieved_docs: Sequence[Any] | None = None,
    **kwargs: Any,
) -> GateOutcome:
    """Raise :class:`ClosedLoopError` unless :func:`gate_tone_awareness` is ok."""
    outcome = gate_tone_awareness(requested_tone, retrieved_docs, **kwargs)
    if not outcome.ok:
        raise ClosedLoopError(f"{outcome.verdict}: {outcome.reason}")
    return outcome
