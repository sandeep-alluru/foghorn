"""STALE-WIKI / Amazon Q - wall-clock source age gate.

Matrix public corpus was **partial** (gate_staleness exists but no Amazon Q
incident fixture). Track B 20260807T121230Z also maps AgentExecutor / foghorn.

Pre-fix hole: gate_staleness only fires when fact *ids* under a decision
change. An unchanging wiki page fact recorded 30 days ago still PASSes
staleness while the agent answers from expired docs.
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from foghorn.closed_loop import (
    ClosedLoopError,
    assert_sources_fresh,
    gate_source_freshness,
    is_source_predicate,
)
from foghorn.fact import Fact
from foghorn.repo import WorldRepo


def test_is_source_predicate() -> None:
    assert is_source_predicate("wiki_source") is True
    assert is_source_predicate("retrieved_from") is True
    assert is_source_predicate("is-appropriate-for") is False
    assert is_source_predicate("") is False


def test_no_source_facts_fails_loud() -> None:
    facts = [
        Fact("Redis", "is-fast", "yes", recorded_at=time.time()),
    ]
    out = gate_source_freshness(facts, require_source_facts=True)
    assert out.ok is False
    assert out.verdict == "FAIL_LOUD"
    assert out.exit_code == 2
    assert out.human_required is True
    assert "Amazon-Q" in out.reason or "STALE-WIKI" in out.reason


def test_fresh_wiki_source_passes() -> None:
    now = time.time()
    facts = [
        Fact(
            "internal-wiki",
            "wiki_source",
            "https://wiki.example/api-auth",
            recorded_at=now - 3600,  # 1 hour
        ),
    ]
    out = gate_source_freshness(facts, max_age_seconds=7 * 86400, now=now)
    assert out.ok is True
    assert out.verdict == "PASS"
    assert out.source_count == 1
    assert out.oldest_age_seconds is not None
    assert out.oldest_age_seconds < 7200
    payload = out.to_dict()
    assert payload["source_count"] == 1
    assert payload["stale_source_ids"] == []


def test_amazon_q_stale_wiki_fails() -> None:
    """Amazon Q class: wiki page fact 30 days old, decision still grounded."""
    now = time.time()
    old = now - 30 * 86400
    wiki = Fact(
        "corp-wiki",
        "wiki_page",
        "DeployProcedure v1 (outdated)",
        recorded_at=old,
    )
    # Non-source fact does not save the gate
    other = Fact("svc", "status", "up", recorded_at=now)
    out = gate_source_freshness(
        [wiki, other],
        max_age_seconds=7 * 86400,
        now=now,
    )
    assert out.ok is False
    assert out.verdict == "FAIL"
    assert out.exit_code == 1
    assert out.human_required is True
    assert wiki.id in out.stale_source_ids
    assert out.oldest_age_seconds is not None
    assert out.oldest_age_seconds >= 29 * 86400


def test_latest_only_ignores_old_history_row() -> None:
    """D-FOGHORN: age the newest wiki fact, not the oldest log row."""
    now = time.time()
    old = Fact(
        "corp-wiki",
        "wiki_source",
        "v1",
        recorded_at=now - 30 * 86400,
    )
    # Same subject/predicate - content-addressed id differs by object
    # Wait - Fact id is subject|predicate|object so different objects are different facts.
    # For latest by (subject, predicate) we keep newest recorded_at among them.
    new = Fact(
        "corp-wiki",
        "wiki_source",
        "v2-refreshed",
        recorded_at=now - 60,
    )
    out = gate_source_freshness(
        [old, new],
        max_age_seconds=7 * 86400,
        now=now,
        use_latest_only=True,
    )
    # use_latest_only keeps both keys... wait (subject, predicate) is same for both
    # so only newest wins. Good - should PASS.
    assert out.ok is True
    assert out.source_count == 1


def test_latest_only_false_fails_if_any_old() -> None:
    now = time.time()
    old = Fact("w", "wiki_source", "v1", recorded_at=now - 30 * 86400)
    new = Fact("w", "wiki_source", "v2", recorded_at=now - 60)
    out = gate_source_freshness(
        [old, new],
        max_age_seconds=7 * 86400,
        now=now,
        use_latest_only=False,
    )
    assert out.ok is False
    assert old.id in out.stale_source_ids


def test_repo_path(tmp_path: Path) -> None:
    repo = WorldRepo.init(str(tmp_path / "w.db"))
    try:
        now = time.time()
        # add_fact uses current time - force via store
        f = Fact(
            "kb",
            "knowledge_base",
            "policy.pdf",
            recorded_at=now - 100,
        )
        repo.store.add_fact(f)
        repo.commit("wiki")
        out = gate_source_freshness(repo, max_age_seconds=86400, now=now)
        assert out.ok is True
        assert out.source_count >= 1
    finally:
        repo.close()


def test_assert_sources_fresh_raises() -> None:
    now = time.time()
    with pytest.raises(ClosedLoopError):
        assert_sources_fresh(
            [Fact("w", "doc_source", "x", recorded_at=now - 999999)],
            max_age_seconds=10,
            now=now,
        )


def test_require_false_empty_passes() -> None:
    out = gate_source_freshness([], require_source_facts=False)
    assert out.ok is True
