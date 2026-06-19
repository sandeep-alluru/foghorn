"""Tests for foghorn.propagate — PropagationResult and propagate_staleness."""

from __future__ import annotations

import pytest

from foghorn.propagate import PropagationResult, propagate_staleness
from foghorn.repo import WorldRepo


@pytest.fixture
def repo(tmp_path):
    db = tmp_path / "world.db"
    r = WorldRepo.init(str(db))
    yield r
    r.close()


def test_propagate_no_facts_changed(repo: WorldRepo) -> None:
    """Empty changed_fact_ids → PropagationResult with nothing stale."""
    result = propagate_staleness(repo, [])
    assert isinstance(result, PropagationResult)
    assert result.directly_stale == []
    assert result.transitively_stale == []
    assert result.propagation_depth == 0


def test_propagate_directly_stale_decision(repo: WorldRepo) -> None:
    """A fact that a decision depends on should appear in directly_stale."""
    f = repo.add_fact("Redis", "is-appropriate-for", "rate-limiting")
    repo.decide("chose-redis", "Redis fits our needs", depends_on=[f.id])
    repo.commit("initial")

    result = propagate_staleness(repo, [f.id])
    assert "chose-redis" in result.directly_stale
    assert result.propagation_depth >= 1


def test_propagate_no_stale_for_unrelated_fact(repo: WorldRepo) -> None:
    """A changed fact that no decision depends on should yield no stale decisions."""
    f1 = repo.add_fact("Redis", "is-fast", "yes")
    f2 = repo.add_fact("Postgres", "is-relational", "yes")
    repo.decide("chose-redis", "Redis is fast", depends_on=[f1.id])
    repo.commit("c1")

    # Only f2 changed — decision depends on f1
    result = propagate_staleness(repo, [f2.id])
    assert "chose-redis" not in result.directly_stale


def test_propagate_multiple_decisions(repo: WorldRepo) -> None:
    """Multiple decisions depending on the same fact are all reported."""
    f = repo.add_fact("Python", "is-language", "yes")
    repo.decide("use-python-backend", "Python for the API", depends_on=[f.id])
    repo.decide("use-python-scripts", "Python for scripts too", depends_on=[f.id])
    repo.commit("c1")

    result = propagate_staleness(repo, [f.id])
    assert "use-python-backend" in result.directly_stale
    assert "use-python-scripts" in result.directly_stale


def test_propagate_impact_summary_non_empty(repo: WorldRepo) -> None:
    """impact_summary should be a non-empty string."""
    f = repo.add_fact("S3", "is-storage", "yes")
    repo.decide("use-s3", "Use S3 for storage", depends_on=[f.id])
    repo.commit("c1")

    result = propagate_staleness(repo, [f.id])
    assert isinstance(result.impact_summary, str)
    assert len(result.impact_summary) > 0


def test_propagate_returns_changed_fact_ids(repo: WorldRepo) -> None:
    """The result should echo back the changed_fact_ids."""
    f = repo.add_fact("A", "b", "c")
    repo.commit("c1")
    result = propagate_staleness(repo, [f.id])
    assert f.id in result.changed_fact_ids


def test_propagate_convenience_method(repo: WorldRepo) -> None:
    """repo.propagate() convenience method should work identically."""
    f = repo.add_fact("K8s", "is-orchestrator", "yes")
    repo.decide("use-k8s", "Deploy on K8s", depends_on=[f.id])
    repo.commit("c1")

    result = repo.propagate([f.id])
    assert isinstance(result, PropagationResult)
    assert "use-k8s" in result.directly_stale
