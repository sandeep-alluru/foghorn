"""Closed-loop reader/gate for foghorn (D-FOGHORN + STALE-WIKI / Amazon Q).

Who reads the output?
  CI / L6 / eagle-eyes: ``StalenessAlert`` lists that force recompute or skip reuse.
  Agent runtimes that must refuse answers grounded on expired wiki/docs sources.

What outcome changes?
  High-impact stale decisions → FAIL (exit 1).
  Empty world, missing store, or **LWW/current-state misuse** → FAIL_LOUD (exit 2).
  Wiki/doc source facts older than max age → FAIL (Amazon Q stale-wiki class).
  Missing source inventory when required → FAIL_LOUD.

When NOT to use:
  NEVER as a last-write-wins episode / current-state store (D-FOGHORN).
"""

from __future__ import annotations

import contextlib
import time
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from foghorn.fact import Fact, StalenessAlert
from foghorn.repo import WorldRepo

# Predicates that mark retrieval/wiki grounding (Amazon Q stale wiki class).
DEFAULT_SOURCE_PREDICATES: frozenset[str] = frozenset(
    {
        "wiki_source",
        "wiki_page",
        "source",
        "documentation",
        "doc_source",
        "from_wiki",
        "knowledge_base",
        "kb_source",
        "retrieved_from",
        "cited_source",
        "page_url",
    }
)

# Default max age: 7 days (wiki/docs drift beyond a week is untrusted by default).
DEFAULT_MAX_SOURCE_AGE_SECONDS: float = 7 * 86400.0


class ClosedLoopError(ValueError):
    """Raised when the gate refuses empty, unusable, or misused worlds."""


Mode = Literal["staleness", "current_state"]


@dataclass(frozen=True)
class GateOutcome:
    """Result of a closed-loop read of a foghorn world or source-age gate.

    Attributes:
        ok: True only when a pipeline may continue (no high-impact stale).
        verdict: ``PASS``, ``FAIL``, or ``FAIL_LOUD``.
        reason: Human-readable explanation (always non-empty).
        exit_code: 0 PASS, 1 FAIL (stale), 2 FAIL_LOUD (empty/misuse).
        alerts: Staleness alerts when scoring ran.
        max_impact: Highest impact_score among alerts (0.0 if none).
        stale_source_ids: Fact ids that exceeded max source age.
        oldest_age_seconds: Age of the oldest examined source fact.
        source_count: Number of source facts examined.
        human_required: True when refresh/re-retrieval needs a human or re-fetch.
    """

    ok: bool
    verdict: str
    reason: str
    exit_code: int
    alerts: tuple[StalenessAlert, ...] = ()
    max_impact: float = 0.0
    stale_source_ids: tuple[str, ...] = ()
    oldest_age_seconds: float | None = None
    source_count: int = 0
    human_required: bool = False

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
            "stale_source_ids": list(self.stale_source_ids),
            "oldest_age_seconds": self.oldest_age_seconds,
            "source_count": self.source_count,
            "human_required": self.human_required,
        }


def _fail_loud(
    reason: str,
    *,
    human_required: bool = False,
    source_count: int = 0,
    oldest_age_seconds: float | None = None,
    stale_source_ids: tuple[str, ...] = (),
) -> GateOutcome:
    return GateOutcome(
        ok=False,
        verdict="FAIL_LOUD",
        reason=reason,
        exit_code=2,
        alerts=(),
        max_impact=0.0,
        human_required=human_required,
        source_count=source_count,
        oldest_age_seconds=oldest_age_seconds,
        stale_source_ids=stale_source_ids,
    )


def _fail(
    reason: str,
    *,
    human_required: bool = True,
    source_count: int = 0,
    oldest_age_seconds: float | None = None,
    stale_source_ids: tuple[str, ...] = (),
    max_impact: float = 0.0,
    alerts: tuple[StalenessAlert, ...] = (),
) -> GateOutcome:
    return GateOutcome(
        ok=False,
        verdict="FAIL",
        reason=reason,
        exit_code=1,
        alerts=alerts,
        max_impact=max_impact,
        human_required=human_required,
        source_count=source_count,
        oldest_age_seconds=oldest_age_seconds,
        stale_source_ids=stale_source_ids,
    )


def _open_repo(source: WorldRepo | str | Path) -> tuple[WorldRepo, bool]:
    """Return (repo, owns_repo). Caller closes if owns_repo."""
    if isinstance(source, WorldRepo):
        return source, False
    path = Path(source)
    if not path.exists() and path.suffix not in {".db", ""}:
        # allow creating? no - missing path fails loud
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
            (D-FOGHORN - foghorn is not a LWW episode store).
        impact_threshold: Max alert impact allowed for PASS (any alert at/above
            this impact → FAIL exit 1).
        require_decisions: If True, a world with zero decisions is FAIL_LOUD
            (nothing load-bearing to gate).

    Returns:
        :class:`GateOutcome` - callers should ``sys.exit(outcome.exit_code)``.
    """
    if mode == "current_state":
        return _fail_loud(
            "D-FOGHORN: mode=current_state forbidden - foghorn is fact→decision "
            "staleness only, never LWW episode/current-state store"
        )
    if mode != "staleness":
        return _fail_loud(f"unknown mode={mode!r} - only mode='staleness' is valid")

    owns = False
    repo: WorldRepo | None = None
    try:
        try:
            repo, owns = _open_repo(source)
        except ClosedLoopError as exc:
            return _fail_loud(str(exc))
        except Exception as exc:
            return _fail_loud(f"open world failed: {exc.__class__.__name__}: {exc}")

        facts = list(repo.store.list_facts())
        decisions = (
            list(repo.store.list_decisions()) if hasattr(repo.store, "list_decisions") else []
        )
        # Fallback: decisions may only live in commits - try common APIs
        if not decisions and hasattr(repo.store, "all_decisions"):
            decisions = list(repo.store.all_decisions())

        if require_decisions and len(decisions) == 0:
            return _fail_loud(
                "empty decisions - no load-bearing fact→decision edges to gate "
                "(write-only fact log is ornament)"
            )

        if len(facts) == 0 and len(decisions) == 0:
            return _fail_loud("empty world - nothing to gate")

        try:
            alerts = tuple(repo.stale())
        except Exception as exc:
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
            with contextlib.suppress(Exception):
                repo.close()


def assert_fresh(
    source: WorldRepo | str | Path,
    **kwargs: Any,
) -> GateOutcome:
    """Gate staleness and raise :class:`ClosedLoopError` unless outcome is ok."""
    outcome = gate_staleness(source, **kwargs)
    if not outcome.ok:
        raise ClosedLoopError(f"{outcome.verdict}: {outcome.reason}")
    return outcome


def is_source_predicate(
    predicate: str,
    *,
    extra: Iterable[str] | None = None,
) -> bool:
    """True if *predicate* marks wiki/doc/retrieval grounding."""
    p = (predicate or "").strip().lower().replace("-", "_").replace(" ", "_")
    if not p:
        return False
    banned = set(DEFAULT_SOURCE_PREDICATES)
    if extra:
        banned |= {str(x).strip().lower().replace("-", "_") for x in extra}
    if p in banned:
        return True
    return any(p.startswith(b + "_") or p.endswith("_" + b) for b in banned)


def _facts_from_source(
    source: WorldRepo | Sequence[Fact],
) -> list[Fact]:
    if isinstance(source, WorldRepo):
        return list(source.store.list_facts())
    return list(source)


def _latest_by_subject_predicate(facts: Sequence[Fact]) -> list[Fact]:
    """Keep only the newest recorded_at per (subject, predicate) - D-FOGHORN."""
    best: dict[tuple[str, str], Fact] = {}
    for f in facts:
        key = (f.subject, f.predicate)
        prev = best.get(key)
        if prev is None or f.recorded_at >= prev.recorded_at:
            best[key] = f
    return list(best.values())


def gate_source_freshness(
    source: WorldRepo | Sequence[Fact],
    *,
    max_age_seconds: float = DEFAULT_MAX_SOURCE_AGE_SECONDS,
    now: float | None = None,
    predicates: Iterable[str] | None = None,
    subjects: Iterable[str] | None = None,
    require_source_facts: bool = True,
    use_latest_only: bool = True,
) -> GateOutcome:
    """Refuse decisions grounded on expired wiki/docs (Amazon Q stale-wiki class).

    Public incident: Amazon Q / stale internal wiki - agents answer from
    retrieved documentation that is no longer current. ``gate_staleness`` only
    fires when fact *ids* change under a decision; it does **not** fail on
    wall-clock age of an unchanging wiki page fact.

    Rules:

    * No source facts when ``require_source_facts`` → **FAIL_LOUD**
    * Any source fact with age > ``max_age_seconds`` → **FAIL**
      (``human_required`` - re-retrieve or human review)
    * Fresh sources only → **PASS**
    * ``use_latest_only`` (default): apply D-FOGHORN - age the newest fact per
      (subject, predicate), not the oldest log row.

    Args:
        source: WorldRepo or sequence of Facts.
        max_age_seconds: Maximum allowed age (default 7 days).
        now: Reference time (default ``time.time()``).
        predicates: Override source predicate set (default wiki/doc set).
        subjects: If set, only examine these subjects.
        require_source_facts: Empty source inventory → FAIL_LOUD.
        use_latest_only: Deduplicate to latest per key before aging.
    """
    if max_age_seconds < 0:
        return _fail_loud(
            "STALE-WIKI: max_age_seconds must be >= 0",
            human_required=True,
        )

    t_now = float(now if now is not None else time.time())
    all_facts = _facts_from_source(source)
    extra_preds = predicates
    subject_filter = {str(s).strip() for s in subjects if str(s).strip()} if subjects else None

    source_facts = [
        f
        for f in all_facts
        if is_source_predicate(f.predicate, extra=extra_preds)
        and (subject_filter is None or f.subject in subject_filter)
    ]

    if use_latest_only and source_facts:
        source_facts = _latest_by_subject_predicate(source_facts)

    if require_source_facts and len(source_facts) == 0:
        return _fail_loud(
            "STALE-WIKI/Amazon-Q: no wiki/doc source facts to gate "
            f"(predicates={sorted(DEFAULT_SOURCE_PREDICATES)[:6]}…) - "
            "cannot ground answers without a retrievable source inventory",
            human_required=True,
            source_count=0,
        )

    if not source_facts:
        return GateOutcome(
            ok=True,
            verdict="PASS",
            reason="STALE-WIKI: no source facts required; nothing to age-check",
            exit_code=0,
            source_count=0,
            human_required=False,
        )

    stale_ids: list[str] = []
    oldest_age = 0.0
    for f in source_facts:
        age = t_now - float(f.recorded_at)
        if age > oldest_age:
            oldest_age = age
        if age > max_age_seconds:
            stale_ids.append(f.id)

    if stale_ids:
        return _fail(
            f"STALE-WIKI/Amazon-Q: {len(stale_ids)} source fact(s) older than "
            f"max_age={max_age_seconds:.0f}s (oldest_age={oldest_age:.0f}s) "
            f"ids={stale_ids[:8]} - refuse answer grounded on expired wiki/docs; "
            f"re-retrieve before decision",
            human_required=True,
            source_count=len(source_facts),
            oldest_age_seconds=oldest_age,
            stale_source_ids=tuple(stale_ids[:20]),
        )

    return GateOutcome(
        ok=True,
        verdict="PASS",
        reason=(
            f"STALE-WIKI ok: sources={len(source_facts)} "
            f"oldest_age={oldest_age:.0f}s max_age={max_age_seconds:.0f}s"
        ),
        exit_code=0,
        source_count=len(source_facts),
        oldest_age_seconds=oldest_age,
        stale_source_ids=(),
        human_required=False,
    )


def assert_sources_fresh(
    source: WorldRepo | Sequence[Fact],
    **kwargs: Any,
) -> GateOutcome:
    """Raise :class:`ClosedLoopError` unless :func:`gate_source_freshness` is ok."""
    outcome = gate_source_freshness(source, **kwargs)
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
