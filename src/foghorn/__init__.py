"""foghorn — Decision staleness alerts for AI agents."""

from __future__ import annotations

from importlib.metadata import version as _version

from foghorn.fact import Decision, Fact, StalenessAlert
from foghorn.repo import WorldRepo
from foghorn.staleness import DiffResult, compute_staleness, diff_commits
from foghorn.store import WorldCommit, WorldStore

__version__ = _version("foghorn")

__all__ = [
    "Decision",
    "DiffResult",
    "Fact",
    "StalenessAlert",
    "WorldCommit",
    "WorldRepo",
    "WorldStore",
    "compute_staleness",
    "diff_commits",
]
