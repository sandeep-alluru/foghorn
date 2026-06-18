"""Tests for staleness propagation: diff_commits() and compute_staleness()."""

import pytest

from foghorn.fact import Decision, Fact
from foghorn.staleness import compute_staleness, diff_commits
from foghorn.store import WorldStore


@pytest.fixture
def store(tmp_path):
    s = WorldStore(str(tmp_path / "world.db"))
    yield s
    s.close()


def test_diff_commits_no_parent_returns_all_as_added(store):
    f = Fact("Redis", "is-appropriate-for", "rate-limiting")
    store.add_fact(f)
    wc = store.commit("first")
    result = diff_commits(store, None, wc)
    assert any(x.id == f.id for x in result.added_facts)
    assert result.removed_facts == []


def test_diff_commits_detects_added_and_removed(store):
    f1 = Fact("Redis", "is-appropriate-for", "rate-limiting")
    store.add_fact(f1)
    wc1 = store.commit("first")

    f2 = Fact("Valkey", "replaced-by", "Redis")
    store.add_fact(f2)
    wc2 = store.commit("second")

    result = diff_commits(store, wc1, wc2)
    assert any(x.id == f2.id for x in result.added_facts)
    assert f1.id not in result.changed_fact_ids


def test_compute_staleness_empty_when_no_facts_changed(store):
    f = Fact("Redis", "is-appropriate-for", "rate-limiting")
    store.add_fact(f)
    d = Decision("chose-redis", "Redis fits", fact_ids=[f.id])
    store.add_decision(d)
    store.commit("initial")
    alerts = compute_staleness(store, set())
    assert alerts == []


def test_compute_staleness_returns_alerts_for_changed_facts(store):
    f = Fact("Redis", "is-appropriate-for", "rate-limiting")
    store.add_fact(f)
    d = Decision("chose-redis", "Redis fits", fact_ids=[f.id])
    store.add_decision(d)
    store.commit("initial")

    alerts = compute_staleness(store, {f.id})
    assert len(alerts) == 1
    assert alerts[0].decision_id == d.id


def test_impact_score_is_confidence_weighted(store):
    f = Fact("Redis", "is-appropriate-for", "rate-limiting", confidence=0.6)
    store.add_fact(f)
    d = Decision("chose-redis", "Redis fits", fact_ids=[f.id])
    store.add_decision(d)
    store.commit("initial")

    alerts = compute_staleness(store, {f.id})
    assert len(alerts) == 1
    assert abs(alerts[0].impact_score - 0.6) < 1e-9


def test_staleness_alerts_sorted_by_impact_descending(store):
    f_high = Fact("Redis", "is-appropriate-for", "rate-limiting", confidence=0.9)
    f_low = Fact("JWT", "used-for", "auth", confidence=0.4)
    store.add_fact(f_high)
    store.add_fact(f_low)
    d1 = Decision("chose-redis", "Redis fits", fact_ids=[f_high.id])
    d2 = Decision("chose-jwt", "JWT fits", fact_ids=[f_low.id])
    store.add_decision(d1)
    store.add_decision(d2)
    store.commit("initial")

    alerts = compute_staleness(store, {f_high.id, f_low.id})
    assert len(alerts) == 2
    assert alerts[0].impact_score >= alerts[1].impact_score
