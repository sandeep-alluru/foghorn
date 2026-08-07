"""foghorn — Decision staleness alerts for AI agents."""

from __future__ import annotations

from importlib.metadata import version as _version

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
    "ClosedLoopError",
    "DEFAULT_MAX_SOURCE_AGE_SECONDS",
    "DEFAULT_SOURCE_PREDICATES",
    "Decision",
    "DiffResult",
    "Fact",
    "GateOutcome",
    "PropagationResult",
    "Recommendation",
    "StalenessAlert",
    "WorldCommit",
    "WorldRepo",
    "WorldStore",
    "assert_fresh",
    "assert_not_current_state_store",
    "assert_sources_fresh",
    "compute_staleness",
    "diff_commits",
    "export_graphviz",
    "export_json",
    "gate_source_freshness",
    "gate_staleness",
    "import_json",
    "is_source_predicate",
    "propagate_staleness",
    "recommend",
]
