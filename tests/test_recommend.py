"""Tests for foghorn.recommend — Recommendation and recommend()."""

from __future__ import annotations

import pytest

from foghorn.recommend import Recommendation, recommend
from foghorn.repo import WorldRepo


@pytest.fixture
def repo(tmp_path):
    db = tmp_path / "world.db"
    r = WorldRepo.init(str(db))
    yield r
    r.close()


def _populate_two_commits(repo: WorldRepo):
    """Helper: commit a fact, then retract it, leaving a stale decision."""
    f = repo.add_fact("Mongo", "is-appropriate-for", "document-storage", confidence=0.95)
    repo.decide("use-mongo", "Mongo fits our document needs", depends_on=[f.id])
    repo.commit("initial")
    # Retract fact to trigger staleness
    repo.retract_fact(f.id)
    repo.add_fact("placeholder", "exists", "true")
    repo.commit("retract mongo fact")
    return f


def test_recommend_returns_list(repo: WorldRepo) -> None:
    """recommend() should return a list (possibly empty)."""
    result = recommend(repo)
    assert isinstance(result, list)


def test_recommend_empty_when_no_stale(repo: WorldRepo) -> None:
    """No stale decisions → empty recommendation list."""
    repo.add_fact("Redis", "is-fast", "yes")
    repo.commit("c1")
    result = recommend(repo)
    assert result == []


def test_recommend_produces_recommendations(repo: WorldRepo) -> None:
    """After a fact retraction, recommend() should produce at least one Recommendation."""
    _populate_two_commits(repo)
    result = recommend(repo)
    assert len(result) >= 1


def test_recommendation_fields(repo: WorldRepo) -> None:
    """Each Recommendation must have all required non-empty fields."""
    _populate_two_commits(repo)
    recs = recommend(repo)
    for rec in recs:
        assert isinstance(rec, Recommendation)
        assert rec.decision_label
        assert rec.reason
        assert rec.action in ("re-evaluate", "archive", "update-fact")
        assert rec.priority in ("critical", "high", "medium", "low")
        assert isinstance(rec.stale_facts, list)


def test_recommend_sorted_by_priority(repo: WorldRepo) -> None:
    """Recommendations should be sorted with higher priority first."""
    _populate_two_commits(repo)
    recs = recommend(repo)
    _order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    priorities = [_order[r.priority] for r in recs]
    assert priorities == sorted(priorities), "Recommendations are not sorted by priority"


def test_recommendation_to_dict(repo: WorldRepo) -> None:
    """Recommendation.to_dict() should return a dict with all keys."""
    _populate_two_commits(repo)
    recs = recommend(repo)
    if recs:
        d = recs[0].to_dict()
        for key in ("decision_label", "reason", "action", "priority", "stale_facts"):
            assert key in d


def test_repo_recommend_convenience(repo: WorldRepo) -> None:
    """repo.recommend() convenience method should work identically."""
    _populate_two_commits(repo)
    result = repo.recommend()
    assert isinstance(result, list)
    assert len(result) >= 1
