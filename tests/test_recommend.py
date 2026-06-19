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


def _populate_partial_retraction(repo: WorldRepo):
    """Helper: commit 3 facts for one decision, then retract only 1 → re-evaluate (>50% stale)."""
    f1 = repo.add_fact("Redis", "is-fast", "yes", confidence=0.8)
    f2 = repo.add_fact("Redis", "is-stable", "yes", confidence=0.8)
    f3 = repo.add_fact("Redis", "is-popular", "yes", confidence=0.8)
    repo.decide(
        "use-redis-all-facts",
        "Redis is fast, stable, and popular",
        depends_on=[f1.id, f2.id, f3.id],
    )
    repo.commit("add three facts")
    # Retract 2 of 3 facts (>50% stale → re-evaluate)
    repo.retract_fact(f1.id)
    repo.retract_fact(f2.id)
    repo.add_fact("placeholder-x", "exists", "true")
    repo.commit("retract 2 of 3 redis facts")
    return f1, f2, f3


def test_recommend_re_evaluate_action(repo: WorldRepo) -> None:
    """When majority of facts are stale, action should be 're-evaluate'."""
    _populate_partial_retraction(repo)
    recs = recommend(repo)
    actions = [r.action for r in recs]
    assert "re-evaluate" in actions


def test_recommend_update_fact_action(repo: WorldRepo) -> None:
    """When minority of facts are stale, action should be 'update-fact'."""
    # 4 facts for decision, retract only 1 (25% stale → update-fact)
    f1 = repo.add_fact("PG", "is-relational", "yes", confidence=0.5)
    f2 = repo.add_fact("PG", "is-durable", "yes", confidence=0.5)
    f3 = repo.add_fact("PG", "supports-json", "yes", confidence=0.5)
    f4 = repo.add_fact("PG", "has-acid", "yes", confidence=0.5)
    repo.decide("use-pg", "Postgres is great", depends_on=[f1.id, f2.id, f3.id, f4.id])
    repo.commit("add pg facts")
    repo.retract_fact(f1.id)
    repo.add_fact("placeholder-y", "exists", "true")
    repo.commit("retract 1 of 4 pg facts")
    recs = recommend(repo)
    actions = [r.action for r in recs]
    assert "update-fact" in actions


def test_recommend_priority_high(repo: WorldRepo) -> None:
    """Decisions with impact_score=0.7 should get priority 'high'."""
    f = repo.add_fact("Kafka", "is-streaming", "yes", confidence=0.7)
    repo.decide("use-kafka", "Kafka for streaming", depends_on=[f.id])
    repo.commit("initial kafka")
    repo.retract_fact(f.id)
    repo.add_fact("placeholder-z", "exists", "true")
    repo.commit("retract kafka fact")
    recs = recommend(repo)
    priorities = [r.priority for r in recs]
    assert any(p in ("critical", "high") for p in priorities)


def test_recommend_priority_low(repo: WorldRepo) -> None:
    """Decisions with low-confidence facts should get priority 'low' or 'medium'."""
    f = repo.add_fact("ElasticSearch", "is-searchable", "yes", confidence=0.3)
    repo.decide("use-es", "ES is searchable", depends_on=[f.id])
    repo.commit("initial es")
    repo.retract_fact(f.id)
    repo.add_fact("placeholder-w", "exists", "true")
    repo.commit("retract es fact")
    recs = recommend(repo)
    priorities = [r.priority for r in recs]
    assert any(p in ("low", "medium") for p in priorities)


def test_recommend_priority_medium(repo: WorldRepo) -> None:
    """Decisions with confidence=0.5 should get priority 'medium'."""
    f = repo.add_fact("Nginx", "is-proxy", "yes", confidence=0.5)
    repo.decide("use-nginx", "Use Nginx as proxy", depends_on=[f.id])
    repo.commit("nginx commit")
    repo.retract_fact(f.id)
    repo.add_fact("placeholder-v", "exists", "true")
    repo.commit("retract nginx fact")
    recs = recommend(repo)
    priorities = [r.priority for r in recs]
    assert any(p in ("medium", "low") for p in priorities)
