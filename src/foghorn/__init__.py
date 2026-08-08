"""foghorn — Decision staleness alerts for AI agents."""

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
from foghorn.export import export_graphviz, export_json, import_json
from foghorn.fact import Decision, Fact, StalenessAlert
from foghorn.propagate import PropagationResult, propagate_staleness
from foghorn.recommend import Recommendation, recommend
from foghorn.repo import WorldRepo
from foghorn.staleness import DiffResult, compute_staleness, diff_commits
from foghorn.store import WorldCommit, WorldStore

__version__ = _version("foghorn-ai")

__all__ = [
    "ActivityFrame",
    "ClosedLoopError",
    "DEFAULT_GAP_SPLIT_SECONDS",
    "DEFAULT_MAX_SOURCE_AGE_SECONDS",
    "DEFAULT_SOURCE_PREDICATES",
    "Decision",
    "DiffResult",
    "Fact",
    "GateOutcome",
    "PropagationResult",
    "RawCaptureRow",
    "Recommendation",
    "StalenessAlert",
    "WorldCommit",
    "WorldRepo",
    "WorldStore",
    "activity_frame_fingerprint",
    "assert_activity_memory_ok",
    "assert_fresh",
    "assert_not_current_state_store",
    "assert_sources_fresh",
    "compile_activity_frames",
    "compute_staleness",
    "diff_commits",
    "export_graphviz",
    "export_json",
    "frame_is_valid",
    "gate_activity_memory",
    "gate_source_freshness",
    "gate_staleness",
    "import_json",
    "is_source_predicate",
    "propagate_staleness",
    "recommend",
]
