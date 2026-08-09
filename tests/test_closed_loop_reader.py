"""Closed-loop reader - empty worlds and D-FOGHORN misuse fail loudly."""

from __future__ import annotations

from pathlib import Path

import pytest

from foghorn.closed_loop import (
    ClosedLoopError,
    GateOutcome,
    assert_fresh,
    assert_not_current_state_store,
    gate_staleness,
)
from foghorn.repo import WorldRepo


@pytest.fixture
def repo(tmp_path: Path):
    r = WorldRepo.init(str(tmp_path / "world.db"))
    yield r
    r.close()


def test_current_state_mode_fails_loud(repo: WorldRepo) -> None:
    out = gate_staleness(repo, mode="current_state")  # type: ignore[arg-type]
    assert out.verdict == "FAIL_LOUD"
    assert out.exit_code == 2
    assert "D-FOGHORN" in out.reason


def test_empty_world_fails_loud(repo: WorldRepo) -> None:
    out = gate_staleness(repo)
    assert isinstance(out, GateOutcome)
    assert out.ok is False
    assert out.verdict == "FAIL_LOUD"
    assert out.exit_code == 2


def test_facts_without_decisions_fails_loud(repo: WorldRepo) -> None:
    repo.add_fact("Redis", "is-fast", "yes")
    repo.commit("facts only")
    out = gate_staleness(repo, require_decisions=True)
    assert out.verdict == "FAIL_LOUD"
    assert "decision" in out.reason.lower()


def test_fresh_decision_passes(repo: WorldRepo) -> None:
    f = repo.add_fact("Redis", "is-appropriate-for", "rate-limiting", confidence=0.9)
    repo.decide("chose-redis", "Redis fits", depends_on=[f.id])
    repo.commit("initial")
    out = gate_staleness(repo)
    assert out.ok is True
    assert out.verdict == "PASS"
    assert out.exit_code == 0
    payload = out.to_dict()
    assert payload["ok"] is True


def test_stale_after_retract_fails(repo: WorldRepo) -> None:
    f = repo.add_fact("Mongo", "is-appropriate-for", "document-storage", confidence=0.95)
    repo.decide("use-mongo", "Mongo fits", depends_on=[f.id])
    repo.commit("initial")
    repo.retract_fact(f.id)
    repo.add_fact("placeholder", "exists", "true")
    repo.commit("retract")
    out = gate_staleness(repo, impact_threshold=0.5)
    assert out.ok is False
    assert out.verdict == "FAIL"
    assert out.exit_code == 1
    assert out.max_impact >= 0.5
    assert len(out.alerts) >= 1


def test_missing_db_fails_loud(tmp_path: Path) -> None:
    out = gate_staleness(tmp_path / "nope.db")
    assert out.verdict == "FAIL_LOUD"
    assert out.exit_code == 2


def test_assert_fresh_raises_on_empty(repo: WorldRepo) -> None:
    with pytest.raises(ClosedLoopError, match="FAIL_LOUD"):
        assert_fresh(repo)


def test_assert_not_current_state_store_raises() -> None:
    with pytest.raises(ClosedLoopError, match="D-FOGHORN"):
        assert_not_current_state_store()
