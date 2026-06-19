"""foghorn — Decision staleness alerts for AI agents."""

from __future__ import annotations

from importlib.metadata import version as _version

from foghorn.export import export_graphviz, export_json, import_json
from foghorn.fact import Decision, Fact, StalenessAlert
from foghorn.propagate import PropagationResult, propagate_staleness
from foghorn.recommend import Recommendation, recommend
from foghorn.repo import WorldRepo
from foghorn.staleness import DiffResult, compute_staleness, diff_commits
from foghorn.store import WorldCommit, WorldStore

__version__ = _version("foghorn-ai")

__all__ = [
    "Decision",
    "DiffResult",
    "Fact",
    "PropagationResult",
    "Recommendation",
    "StalenessAlert",
    "WorldCommit",
    "WorldRepo",
    "WorldStore",
    "compute_staleness",
    "diff_commits",
    "export_graphviz",
    "export_json",
    "import_json",
    "propagate_staleness",
    "recommend",
]
