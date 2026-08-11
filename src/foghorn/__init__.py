"""foghorn - Decision staleness alerts for AI agents."""

from __future__ import annotations

from importlib.metadata import version as _version

from foghorn.activity import (
    DEFAULT_GAP_SPLIT_SECONDS,
    ActivityFrame,
    RawCaptureRow,
    activity_frame_fingerprint,
    assert_activity_memory_ok,
    compile_activity_frames,
    frame_is_valid,
    gate_activity_memory,
)
from foghorn.closed_loop import (
    DEFAULT_MAX_SOURCE_AGE_SECONDS,
    DEFAULT_SOURCE_PREDICATES,
    ClosedLoopError,
    GateOutcome,
    assert_fresh,
    assert_not_current_state_store,
    assert_sources_fresh,
    gate_source_freshness,
    gate_staleness,
    is_source_predicate,
)
from foghorn.evidence import (
    DEFAULT_EVIDENCE_KINDS,
    DEFAULT_FEATURE_KINDS,
    EvidenceLink,
    FeatureRecord,
    analyze_evidence_links,
    assert_evidence_linked,
    gate_evidence_links,
    is_evidence_kind,
    is_feature_kind,
)
from foghorn.export import export_graphviz, export_json, import_json
from foghorn.fact import Decision, Fact, StalenessAlert
from foghorn.propagate import PropagationResult, propagate_staleness
from foghorn.recommend import Recommendation, recommend
from foghorn.repo import WorldRepo
from foghorn.staleness import DiffResult, compute_staleness, diff_commits
from foghorn.store import WorldCommit, WorldStore
from foghorn.sufficiency import (
    DEEP_SUFFICIENCY_DIMENSIONS,
    DEFAULT_SUFFICIENCY_DIMENSIONS,
    EvidenceBundle,
    SufficiencyReport,
    analyze_evidence_sufficiency,
    assert_evidence_sufficient,
    gate_evidence_sufficiency,
)
from foghorn.tone import (
    DEFAULT_TONES,
    HIGH_FORMALITY_TONES,
    LOW_FORMALITY_TONES,
    RetrievedDoc,
    ToneReport,
    analyze_tone_alignment,
    assert_tone_aware,
    formality_band,
    gate_tone_awareness,
    infer_tone_from_text,
)

__version__ = _version("foghorn-ai")

__all__ = [
    "DEEP_SUFFICIENCY_DIMENSIONS",
    "DEFAULT_EVIDENCE_KINDS",
    "DEFAULT_FEATURE_KINDS",
    "DEFAULT_GAP_SPLIT_SECONDS",
    "DEFAULT_MAX_SOURCE_AGE_SECONDS",
    "DEFAULT_SOURCE_PREDICATES",
    "DEFAULT_SUFFICIENCY_DIMENSIONS",
    "DEFAULT_TONES",
    "HIGH_FORMALITY_TONES",
    "LOW_FORMALITY_TONES",
    "ActivityFrame",
    "ClosedLoopError",
    "Decision",
    "DiffResult",
    "EvidenceBundle",
    "EvidenceLink",
    "Fact",
    "FeatureRecord",
    "GateOutcome",
    "PropagationResult",
    "RawCaptureRow",
    "Recommendation",
    "RetrievedDoc",
    "StalenessAlert",
    "SufficiencyReport",
    "ToneReport",
    "WorldCommit",
    "WorldRepo",
    "WorldStore",
    "activity_frame_fingerprint",
    "analyze_evidence_links",
    "analyze_evidence_sufficiency",
    "analyze_tone_alignment",
    "assert_activity_memory_ok",
    "assert_evidence_linked",
    "assert_evidence_sufficient",
    "assert_fresh",
    "assert_not_current_state_store",
    "assert_sources_fresh",
    "assert_tone_aware",
    "compile_activity_frames",
    "compute_staleness",
    "diff_commits",
    "export_graphviz",
    "export_json",
    "formality_band",
    "frame_is_valid",
    "gate_activity_memory",
    "gate_evidence_links",
    "gate_evidence_sufficiency",
    "gate_source_freshness",
    "gate_staleness",
    "gate_tone_awareness",
    "import_json",
    "infer_tone_from_text",
    "is_evidence_kind",
    "is_feature_kind",
    "is_source_predicate",
    "propagate_staleness",
    "recommend",
]
