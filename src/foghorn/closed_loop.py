"""Closed-loop reader/gate for foghorn (Non-Ornament L1 + D-FOGHORN).

Who reads the output?
  CI / L6 / eagle-eyes: ``StalenessAlert`` lists that force recompute or skip reuse.

What outcome changes?
  High-impact stale decisions → FAIL (exit 1).
  Empty world, missing store, or **LWW/current-state misuse** → FAIL_LOUD (exit 2).

When NOT to use:
  NEVER as a last-write-wins episode / current-state store (D-FOGHORN).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from foghorn.fact import StalenessAlert
from foghorn.repo import WorldRepo


class ClosedLoopError(ValueError):
    """Raised when the gate refuses empty, unusable, or misused worlds."""


Mode = Literal["staleness", "current_state"]


@dataclass(frozen=True)
class GateOutcome:
    """Result of a closed-loop read of a foghorn world.

    Attributes:
        ok: True only when a pipeline may continue (no high-impact stale).
        verdict: ``PASS``, ``FAIL``, or ``FAIL_LOUD``.
        reason: Human-readable explanation (always non-empty).
        exit_code: 0 PASS, 1 FAIL (stale), 2 FAIL_LOUD (empty/misuse).
        alerts: Staleness alerts when scoring ran.
        max_impact: Highest impact_score among alerts (0.0 if none).
    """

    ok: bool
    verdict: str
    reason: str
    exit_code: int
    alerts: tuple[StalenessAlert, ...] = ()
    max_impact: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """Serialise for JSON reports (eagle-eyes dogfood, CI artifacts)."""
        return {
            "ok": self.ok,
            "verdict": self.verdict,
            "reason": self.reason,
            "exit_code": self.exit_code,
            "max_impact": self.max_impact,
            "alert_count": len(self.alerts),
            "alerts": [a.to_dict() for a in self.alerts],
        }


def _fail_loud(reason: str) -> GateOutcome:
    return GateOutcome(
        ok=False,
        verdict="FAIL_LOUD",
        reason=reason,
        exit_code=2,
        alerts=(),
        max_impact=0.0,
    )


def _open_repo(source: WorldRepo | str | Path) -> tuple[WorldRepo, bool]:
    """Return (repo, owns_repo). Caller closes if owns_repo."""
    if isinstance(source, WorldRepo):
        return source, False
    path = Path(source)
    if not path.exists() and path.suffix not in {".db", ""}:
        # allow creating? no — missing path fails loud
        raise ClosedLoopError(f"world db path not found: {path}")
    # WorldRepo.init creates parent dirs; for gate we require existing file when path given
    if path.suffix == ".db" and not path.is_file():
        raise ClosedLoopError(f"world db not found: {path}")
    return WorldRepo.init(path), True


def gate_staleness(
    source: WorldRepo | str | Path,
    *,
    mode: Mode = "staleness",
    impact_threshold: float = 0.5,
    require_decisions: bool = True,
) -> GateOutcome:
    """Read a world, surface staleness, fail loudly on empty or D-FOGHORN misuse.

    Args:
        source: Open :class:`WorldRepo` or path to a world SQLite db.
        mode: Must be ``\"staleness\"``. ``\"current_state\"`` is always FAIL_LOUD
            (D-FOGHORN — foghorn is not a LWW episode store).
        impact_threshold: Max alert impact allowed for PASS (any alert at/above
            this impact → FAIL exit 1).
        require_decisions: If True, a world with zero decisions is FAIL_LOUD
            (nothing load-bearing to gate).

    Returns:
        :class:`GateOutcome` — callers should ``sys.exit(outcome.exit_code)``.
    """
    if mode == "current_state":
        return _fail_loud(
            "D-FOGHORN: mode=current_state forbidden — foghorn is fact→decision "
            "staleness only, never LWW episode/current-state store"
        )
    if mode != "staleness":
        return _fail_loud(f"unknown mode={mode!r} — only mode='staleness' is valid")

    owns = False
    repo: WorldRepo | None = None
    try:
        try:
            repo, owns = _open_repo(source)
        except ClosedLoopError as exc:
            return _fail_loud(str(exc))
        except Exception as exc:  # noqa: BLE001
            return _fail_loud(f"open world failed: {exc.__class__.__name__}: {exc}")

        facts = list(repo.store.list_facts())
        decisions = list(repo.store.list_decisions()) if hasattr(repo.store, "list_decisions") else []
        # Fallback: decisions may only live in commits — try common APIs
        if not decisions and hasattr(repo.store, "all_decisions"):
            decisions = list(repo.store.all_decisions())  # type: ignore[attr-defined]

        if require_decisions and len(decisions) == 0:
            return _fail_loud(
                "empty decisions — no load-bearing fact→decision edges to gate "
                "(write-only fact log is ornament)"
            )

        if len(facts) == 0 and len(decisions) == 0:
            return _fail_loud("empty world — nothing to gate")

        try:
            alerts = tuple(repo.stale())
        except Exception as exc:  # noqa: BLE001
            return _fail_loud(f"stale() failed: {exc.__class__.__name__}: {exc}")

        max_impact = max((a.impact_score for a in alerts), default=0.0)
        hot = [a for a in alerts if a.impact_score >= impact_threshold]

        if hot:
            return GateOutcome(
                ok=False,
                verdict="FAIL",
                reason=(
                    f"stale decisions impact>={impact_threshold}: "
                    f"count={len(hot)} max_impact={max_impact:.3f}"
                ),
                exit_code=1,
                alerts=alerts,
                max_impact=max_impact,
            )

        return GateOutcome(
            ok=True,
            verdict="PASS",
            reason=(
                f"no high-impact staleness (alerts={len(alerts)} "
                f"max_impact={max_impact:.3f} threshold={impact_threshold})"
            ),
            exit_code=0,
            alerts=alerts,
            max_impact=max_impact,
        )
    finally:
        if owns and repo is not None:
            try:
                repo.close()
            except Exception:  # noqa: BLE001
                pass


def assert_fresh(
    source: WorldRepo | str | Path,
    **kwargs: Any,
) -> GateOutcome:
    """Gate staleness and raise :class:`ClosedLoopError` unless outcome is ok."""
    outcome = gate_staleness(source, **kwargs)
    if not outcome.ok:
        raise ClosedLoopError(f"{outcome.verdict}: {outcome.reason}")
    return outcome


def assert_not_current_state_store() -> None:
    """Explicit D-FOGHORN guard for integrators (always raises if called wrong).

    Prefer calling :func:`gate_staleness` with ``mode='staleness'`` only.
    """
    raise ClosedLoopError(
        "D-FOGHORN: do not use foghorn as current-state/LWW store; "
        "list_facts() is chronological (oldest first), not latest-wins"
    )
