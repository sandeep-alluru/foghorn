"""Tests for WorldStore and WorldCommit from foghorn.store."""

import pytest

from foghorn.fact import Decision, Fact
from foghorn.store import WorldStore


@pytest.fixture
def store(tmp_path):
    s = WorldStore(str(tmp_path / "world.db"))
    yield s
    s.close()


def test_worldstore_creates_sqlite_file(tmp_path):
    db_path = tmp_path / "world.db"
    s = WorldStore(str(db_path))
    s.close()
    assert db_path.exists()


def test_add_fact_idempotent(store):
    f = Fact("Redis", "is-appropriate-for", "rate-limiting")
    store.add_fact(f)
    store.add_fact(f)
    facts = store.list_facts()
    assert len([x for x in facts if x.id == f.id]) == 1


def test_get_fact_roundtrip(store):
    f = Fact("Postgres", "is-primary-db", "yes", confidence=0.9)
    store.add_fact(f)
    retrieved = store.get_fact(f.id)
    assert retrieved is not None
    assert retrieved.id == f.id
    assert retrieved.subject == f.subject
    assert retrieved.confidence == f.confidence


def test_get_fact_missing_returns_none(store):
    assert store.get_fact("nonexistent") is None


def test_add_decision_with_fact_dependencies(store):
    f = Fact("Redis", "is-appropriate-for", "rate-limiting")
    store.add_fact(f)
    d = Decision("chose-redis", "Redis fits our needs", fact_ids=[f.id])
    store.add_decision(d)
    retrieved = store.get_decision(d.id)
    assert retrieved is not None
    assert f.id in retrieved.fact_ids


def test_get_decisions_for_fact(store):
    f = Fact("Redis", "is-appropriate-for", "rate-limiting")
    store.add_fact(f)
    d = Decision("chose-redis", "Redis fits", fact_ids=[f.id])
    store.add_decision(d)
    decisions = store.get_decisions_for_fact(f.id)
    assert any(dec.id == d.id for dec in decisions)


def test_commit_creates_worldcommit(store):
    f = Fact("Redis", "is-appropriate-for", "rate-limiting")
    store.add_fact(f)
    wc = store.commit("Initial commit")
    assert wc is not None
    assert f.id in wc.fact_ids
    assert wc.message == "Initial commit"


def test_commit_clears_staging_area(store):
    f = Fact("Redis", "is-appropriate-for", "rate-limiting")
    store.add_fact(f)
    assert store.staged_count() == 1
    store.commit("clear test")
    assert store.staged_count() == 0


def test_log_returns_commits_newest_first(store):
    store.add_fact(Fact("A", "B", "C"))
    store.commit("first")
    store.add_fact(Fact("D", "E", "F"))
    store.commit("second")
    commits = store.log()
    assert len(commits) == 2
    assert commits[0].message == "second"
    assert commits[1].message == "first"


def test_head_returns_head_commit(store):
    assert store.head() is None
    store.add_fact(Fact("A", "B", "C"))
    store.commit("first")
    head = store.head()
    assert head is not None
    assert head.message == "first"


def test_list_facts_oldest_first_not_current_state(store):
    """D-FOGHORN regression: list_facts is chronological; next() is OLDEST, not current.

    Integrators must not treat list_facts() as a LWW current-value store.
    See docs/CLOSED_LOOP.md and farm memory case D-FOGHORN (2026-07-22).
    """
    import time

    f1 = Fact("script", "hash", "aaa", confidence=1.0)
    store.add_fact(f1)
    time.sleep(0.02)
    f2 = Fact("script", "hash", "bbb", confidence=1.0)
    store.add_fact(f2)

    facts = store.list_facts()
    script_facts = [f for f in facts if f.subject == "script" and f.predicate == "hash"]
    assert len(script_facts) >= 2
    # Ordered by recorded_at ascending → first is oldest
    assert script_facts[0].object == "aaa"
    assert script_facts[-1].object == "bbb"
    # The Foundry bug class: next(iter(list_facts())) or facts[0] is NOT latest
    assert next(iter(script_facts)).object != "bbb"


def test_latest_fact_returns_newest_not_oldest(store):
    """D-FOGHORN product fix: current value of (subject, predicate) is max(recorded_at)."""
    import time

    f1 = Fact("script", "hash", "aaa", confidence=1.0, recorded_at=1000.0)
    f2 = Fact("script", "hash", "bbb", confidence=1.0, recorded_at=2000.0)
    # insert oldest first then newest
    store.add_fact(f1)
    store.add_fact(f2)

    latest = store.latest_fact("script", "hash")
    assert latest is not None
    assert latest.object == "bbb"
    # history still oldest-first
    hist = store.list_facts_for("script", "hash")
    assert [f.object for f in hist] == ["aaa", "bbb"]
    # anti-pattern would return aaa
    assert next(iter(hist)).object == "aaa"
    assert next(iter(hist)).object != latest.object


def test_current_fact_map_lww_per_key(store):
    store.add_fact(Fact("script", "hash", "old", recorded_at=1.0))
    store.add_fact(Fact("script", "hash", "new", recorded_at=9.0))
    store.add_fact(Fact("audio", "hash", "x", recorded_at=5.0))
    m = store.current_fact_map()
    assert m[("script", "hash")].object == "new"
    assert m[("audio", "hash")].object == "x"


def test_latest_fact_missing_returns_none(store):
    assert store.latest_fact("nope", "missing") is None
