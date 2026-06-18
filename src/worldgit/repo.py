"""High-level WorldRepo — the main entry point for worldgit operations."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from worldgit.fact import Decision, Fact, StalenessAlert
from worldgit.staleness import DiffResult, compute_staleness, diff_commits
from worldgit.store import WorldCommit, WorldStore


class WorldRepo:
    """A worldgit repository: a versioned store of agent facts and decisions.

    WorldRepo is the main user-facing API. It wraps WorldStore with the
    higher-level operations of a version-controlled knowledge base.

    Typical workflow::

        repo = WorldRepo.init(".worldgit")
        repo.add_fact("Redis", "is-appropriate-for", "rate-limiting")
        repo.decide("chose-redis", "Redis fits our rate-limiter needs",
                    depends_on=[...fact_ids...])
        commit = repo.commit("Initial architecture decisions")

    Attributes:
        store: The underlying WorldStore.
        path: Path to the repository database.
    """

    def __init__(self, store: WorldStore) -> None:
        self.store = store
        self.path = store.path

    @classmethod
    def init(cls, path: str | Path = ".worldgit/world.db") -> WorldRepo:
        """Create or open a WorldRepo at the given path.

        Args:
            path: Path to the SQLite database file. Parent directories
                are created automatically.

        Returns:
            A WorldRepo ready for use.
        """
        return cls(WorldStore(path))

    def add_fact(
        self,
        subject: str,
        predicate: str,
        obj: str,
        confidence: float = 1.0,
    ) -> Fact:
        """Stage a new Fact for the next commit.

        Args:
            subject: The entity this fact is about.
            predicate: The relationship being asserted.
            obj: The value of the assertion.
            confidence: Belief weight in [0.0, 1.0].

        Returns:
            The created (and staged) Fact.
        """
        fact = Fact(subject=subject, predicate=predicate, object=obj, confidence=confidence)
        self.store.add_fact(fact)
        return fact

    def decide(
        self,
        label: str,
        content: str,
        depends_on: list[str] | None = None,
    ) -> Decision:
        """Stage a new Decision for the next commit.

        Args:
            label: Short slug for this decision (e.g. "chose-redis-for-rate-limiting").
            content: Full reasoning text.
            depends_on: List of Fact IDs this decision relied on.

        Returns:
            The created (and staged) Decision.
        """
        decision = Decision(
            label=label,
            content=content,
            fact_ids=depends_on or [],
        )
        self.store.add_decision(decision)
        return decision

    def commit(self, message: str) -> WorldCommit:
        """Commit all staged facts and decisions.

        Args:
            message: Human-readable commit message.

        Returns:
            The new WorldCommit.

        Raises:
            ValueError: If there is nothing staged to commit.
        """
        if self.store.staged_count() == 0:
            raise ValueError("Nothing to commit — stage facts or decisions first.")
        return self.store.commit(message)

    def retract_fact(self, fact_id: str) -> None:
        """Stage a fact retraction so it is excluded from the next commit snapshot.

        Args:
            fact_id: ID of the Fact to remove from the next snapshot.
        """
        self.store.retract_fact(fact_id)

    def stale(self, since: WorldCommit | None = None) -> list[StalenessAlert]:
        """Return staleness alerts for decisions affected by recent fact changes.

        Compares HEAD to ``since`` (or HEAD's parent if None) and finds all
        Decisions whose upstream facts changed.

        Args:
            since: The base commit to diff against. Defaults to HEAD's parent.

        Returns:
            List of StalenessAlert sorted by impact_score descending.
            Empty list if nothing has changed or there are no decisions.
        """
        head = self.store.head()
        if head is None:
            return []

        base: WorldCommit | None
        if since is not None:
            base = since
        else:
            base = self.store.get_commit(head.parent_id) if head.parent_id else None

        diff = diff_commits(self.store, base, head)
        return compute_staleness(self.store, diff.changed_fact_ids)

    def diff(
        self,
        commit_a: WorldCommit | None = None,
        commit_b: WorldCommit | None = None,
    ) -> DiffResult:
        """Diff two commits (defaults to HEAD~1 vs HEAD).

        Args:
            commit_a: Base commit (None = empty state).
            commit_b: Head commit (None = current HEAD).

        Returns:
            DiffResult with added and removed facts.

        Raises:
            ValueError: If HEAD is empty and no commits are provided.
        """
        if commit_b is None:
            commit_b = self.store.head()
            if commit_b is None:
                raise ValueError("Repository has no commits yet.")

        if commit_a is None and commit_b.parent_id:
            commit_a = self.store.get_commit(commit_b.parent_id)

        return diff_commits(self.store, commit_a, commit_b)

    def log(self) -> list[WorldCommit]:
        """Return all commits from HEAD to root, newest first."""
        return self.store.log()

    def close(self) -> None:
        """Close the underlying database connection."""
        self.store.close()

    def __enter__(self) -> WorldRepo:
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()
