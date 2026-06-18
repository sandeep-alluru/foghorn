"""worldgit — Decision staleness alerts for AI agents."""

from __future__ import annotations

from importlib.metadata import version as _version

from worldgit.fact import Decision, Fact, StalenessAlert
from worldgit.repo import WorldRepo
from worldgit.staleness import DiffResult, compute_staleness, diff_commits
from worldgit.store import WorldCommit, WorldStore

__version__ = _version("worldgit")

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
