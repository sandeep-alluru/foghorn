"""Activity Frames - deterministic screen-activity memory (arXiv 2608.05784).

Public case: Activity Frames (Track B / arXiv 2608.05784). Computer-use agents
re-derive routines the user already performed because agent memory records what
the user *said*, not what the user *did*. LLM summaries of raw capture lose
fidelity (paper: ~66-80% vs ~98% for compiled frames).

Product role in foghorn:
  Compile passively captured screen rows into typed, byte-identical activity
  frames (app, site, timing, input volume, evidence pointers) with **no model
  in the loop**, then **gate** agent memory so pipelines refuse LLM-summary-only
  or raw-uncompiled capture as the load-bearing "what happened" memory.

Non-Ornament:
  Call ``gate_activity_memory`` before answering questions about a session day
  or replaying a routine from memory. Fail loud when frames lack evidence.
"""

from __future__ import annotations

import hashlib
import itertools
import json
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal

from foghorn.closed_loop import ClosedLoopError, GateOutcome

MemoryMode = Literal["compiled", "llm_summary", "raw_uncompiled"]

# Default max gap (seconds) between rows still in the same episode frame.
DEFAULT_GAP_SPLIT_SECONDS: float = 300.0


@dataclass(frozen=True)
class RawCaptureRow:
    """One raw capture stream row (pre-compile).

    Attributes:
        row_id: Stable id of the raw row (evidence pointer target).
        timestamp: Unix seconds (or any monotonic clock).
        application: Foreground application name.
        site: Optional site/URL host (browser) or window title token.
        input_kind: Optional input class (``key``, ``click``, ``scroll``, …).
        meta: Optional extra fields (ignored by compile fingerprint except
            when callers pass them through explicitly).
    """

    row_id: str
    timestamp: float
    application: str
    site: str = ""
    input_kind: str = ""
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "row_id": self.row_id,
            "timestamp": self.timestamp,
            "application": self.application,
            "site": self.site,
            "input_kind": self.input_kind,
            "meta": dict(self.meta),
        }


@dataclass(frozen=True)
class ActivityFrame:
    """Compiled typed activity frame (deterministic, zero-model).

    Bounded episode carrying application, site, timing, input volume, and
    evidence pointers back to raw rows - byte-identical and cacheable.
    """

    frame_id: str
    application: str
    site: str
    t_start: float
    t_end: float
    input_volume: int
    evidence_ptrs: tuple[str, ...]
    frame_type: str = "activity"
    row_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "frame_id": self.frame_id,
            "application": self.application,
            "site": self.site,
            "t_start": self.t_start,
            "t_end": self.t_end,
            "input_volume": self.input_volume,
            "evidence_ptrs": list(self.evidence_ptrs),
            "frame_type": self.frame_type,
            "row_count": self.row_count,
        }


def _canon_app(app: str) -> str:
    return (app or "").strip() or "unknown"


def _canon_site(site: str) -> str:
    return (site or "").strip().lower()


def activity_frame_fingerprint(
    *,
    application: str,
    site: str,
    t_start: float,
    t_end: float,
    evidence_ptrs: Sequence[str],
    input_volume: int,
) -> str:
    """Stable SHA-256 hex of the frame content (byte-identical across runs)."""
    payload = {
        "application": _canon_app(application),
        "site": _canon_site(site),
        "t_start": float(t_start),
        "t_end": float(t_end),
        "evidence_ptrs": list(evidence_ptrs),
        "input_volume": int(input_volume),
    }
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def _row_from_mapping(item: RawCaptureRow | dict[str, Any]) -> RawCaptureRow:
    if isinstance(item, RawCaptureRow):
        return item
    if not isinstance(item, dict):
        raise TypeError(f"raw row must be RawCaptureRow or dict, got {type(item)!r}")
    rid = str(item.get("row_id") or item.get("id") or "").strip()
    if not rid:
        raise ValueError("raw capture row missing row_id")
    ts = item.get("timestamp", item.get("ts", item.get("t")))
    if ts is None:
        raise ValueError(f"raw capture row {rid!r} missing timestamp")
    app = str(item.get("application") or item.get("app") or "")
    site = str(item.get("site") or item.get("url") or item.get("host") or "")
    kind = str(item.get("input_kind") or item.get("kind") or "")
    meta = item.get("meta") if isinstance(item.get("meta"), dict) else {}
    return RawCaptureRow(
        row_id=rid,
        timestamp=float(ts),
        application=app,
        site=site,
        input_kind=kind,
        meta=dict(meta),
    )


def compile_activity_frames(
    rows: Sequence[RawCaptureRow | dict[str, Any]],
    *,
    gap_split_seconds: float = DEFAULT_GAP_SPLIT_SECONDS,
) -> list[ActivityFrame]:
    """Segment raw capture into typed activity frames (deterministic, zero-model).

    Split rules (all mechanical - no LLM):

    1. Sort by ``timestamp`` ascending (stable on equal timestamps by ``row_id``).
    2. Start a new frame when **application** or **site** changes vs previous row.
    3. Start a new frame when the gap from previous row exceeds
       ``gap_split_seconds`` (default 300s).
    4. ``input_volume`` = count of rows with non-empty ``input_kind``.
    5. ``evidence_ptrs`` = ordered ``row_id`` list for rows in the frame.
    6. ``frame_id`` = :func:`activity_frame_fingerprint` of the content.

    Empty input → empty list (caller may FAIL_LOUD via the gate).
    """
    if gap_split_seconds < 0:
        raise ValueError("gap_split_seconds must be >= 0")

    parsed = [_row_from_mapping(r) for r in rows]
    if not parsed:
        return []

    ordered = sorted(parsed, key=lambda r: (r.timestamp, r.row_id))

    frames: list[ActivityFrame] = []
    bucket: list[RawCaptureRow] = [ordered[0]]

    def _flush(group: list[RawCaptureRow]) -> None:
        if not group:
            return
        app = _canon_app(group[0].application)
        site = _canon_site(group[0].site)
        t_start = float(group[0].timestamp)
        t_end = float(group[-1].timestamp)
        ptrs = tuple(r.row_id for r in group)
        volume = sum(1 for r in group if (r.input_kind or "").strip())
        fid = activity_frame_fingerprint(
            application=app,
            site=site,
            t_start=t_start,
            t_end=t_end,
            evidence_ptrs=ptrs,
            input_volume=volume,
        )
        frames.append(
            ActivityFrame(
                frame_id=fid,
                application=app,
                site=site,
                t_start=t_start,
                t_end=t_end,
                input_volume=volume,
                evidence_ptrs=ptrs,
                frame_type="activity",
                row_count=len(group),
            )
        )

    for prev, cur in itertools.pairwise(ordered):
        app_change = _canon_app(cur.application) != _canon_app(prev.application)
        site_change = _canon_site(cur.site) != _canon_site(prev.site)
        gap = float(cur.timestamp) - float(prev.timestamp)
        gap_split = gap > gap_split_seconds
        if app_change or site_change or gap_split:
            _flush(bucket)
            bucket = [cur]
        else:
            bucket.append(cur)
    _flush(bucket)
    return frames


def frame_is_valid(frame: ActivityFrame) -> bool:
    """True when a compiled frame is load-bearing (evidence + timing)."""
    if not frame.frame_id or not frame.application:
        return False
    if frame.t_end < frame.t_start:
        return False
    if not frame.evidence_ptrs:
        return False
    return not any(not str(p).strip() for p in frame.evidence_ptrs)


def _frame_from_mapping(item: ActivityFrame | dict[str, Any]) -> ActivityFrame:
    if isinstance(item, ActivityFrame):
        return item
    if not isinstance(item, dict):
        raise TypeError(f"frame must be ActivityFrame or dict, got {type(item)!r}")
    ptrs_raw = item.get("evidence_ptrs") or item.get("evidence") or ()
    ptrs = tuple(str(p) for p in ptrs_raw)
    app = _canon_app(str(item.get("application") or item.get("app") or ""))
    site = _canon_site(str(item.get("site") or ""))
    t_start = float(item.get("t_start", item.get("start", 0.0)))
    t_end = float(item.get("t_end", item.get("end", t_start)))
    volume = int(item.get("input_volume", item.get("volume", 0)))
    fid = str(item.get("frame_id") or "").strip()
    if not fid:
        fid = activity_frame_fingerprint(
            application=app,
            site=site,
            t_start=t_start,
            t_end=t_end,
            evidence_ptrs=ptrs,
            input_volume=volume,
        )
    return ActivityFrame(
        frame_id=fid,
        application=app,
        site=site,
        t_start=t_start,
        t_end=t_end,
        input_volume=volume,
        evidence_ptrs=ptrs,
        frame_type=str(item.get("frame_type") or "activity"),
        row_count=int(item.get("row_count") or len(ptrs)),
    )


def _fail_loud(reason: str, *, source_count: int = 0) -> GateOutcome:
    return GateOutcome(
        ok=False,
        verdict="FAIL_LOUD",
        reason=reason,
        exit_code=2,
        human_required=True,
        source_count=source_count,
    )


def _fail(reason: str, *, source_count: int = 0) -> GateOutcome:
    return GateOutcome(
        ok=False,
        verdict="FAIL",
        reason=reason,
        exit_code=1,
        human_required=True,
        source_count=source_count,
    )


def gate_activity_memory(
    frames: Sequence[ActivityFrame | dict[str, Any]] | None = None,
    *,
    memory_mode: MemoryMode = "compiled",
    raw_rows: Sequence[RawCaptureRow | dict[str, Any]] | None = None,
    require_frames: bool = True,
    require_evidence: bool = True,
    gap_split_seconds: float = DEFAULT_GAP_SPLIT_SECONDS,
    claimed_frame_ids: Iterable[str] | None = None,
) -> GateOutcome:
    """Refuse non-deterministic or evidence-free activity memory.

    Activity Frames class (arXiv 2608.05784):

    * ``memory_mode="llm_summary"`` → **FAIL** - LLM day-summary is not
      load-bearing memory (paper accuracy gap vs compiled frames).
    * ``memory_mode="raw_uncompiled"`` → **FAIL** - must compile first.
    * ``memory_mode="compiled"`` with no frames when required → **FAIL_LOUD**.
    * Frame missing evidence pointers → **FAIL_LOUD**.
    * Invalid timing (``t_end < t_start``) → **FAIL**.
    * ``claimed_frame_ids`` not subset of compiled inventory → **FAIL**.
    * Valid compiled frames with evidence → **PASS**.

    If ``raw_rows`` is provided and ``frames`` is None/empty under compiled mode,
    frames are compiled in-process (deterministic) before gating.
    """
    mode = (memory_mode or "compiled").strip().lower()
    if mode not in {"compiled", "llm_summary", "raw_uncompiled"}:
        return _fail_loud(
            f"ACTIVITY-FRAMES: unknown memory_mode={memory_mode!r} "
            "(use compiled|llm_summary|raw_uncompiled)"
        )

    if mode == "llm_summary":
        return _fail(
            "ACTIVITY-FRAMES: memory_mode=llm_summary refused - "
            "LLM summaries of screen capture are not load-bearing activity "
            "memory (arXiv 2608.05784: compiled frames beat summaries). "
            "Compile raw rows with compile_activity_frames and use "
            "memory_mode='compiled'."
        )

    if mode == "raw_uncompiled":
        return _fail(
            "ACTIVITY-FRAMES: memory_mode=raw_uncompiled refused - "
            "raw capture must be compiled into typed activity frames "
            "(app/site/timing/input_volume/evidence_ptrs) before use as "
            "agent memory. Call compile_activity_frames(...)."
        )

    # compiled mode
    compiled: list[ActivityFrame] = []
    if frames:
        try:
            compiled = [_frame_from_mapping(f) for f in frames]
        except (TypeError, ValueError) as exc:
            return _fail_loud(
                f"ACTIVITY-FRAMES: invalid frame payload: {exc}",
            )

    if not compiled and raw_rows is not None:
        try:
            compiled = compile_activity_frames(raw_rows, gap_split_seconds=gap_split_seconds)
        except (TypeError, ValueError) as exc:
            return _fail_loud(
                f"ACTIVITY-FRAMES: compile failed: {exc}",
            )

    if require_frames and len(compiled) == 0:
        return _fail_loud(
            "ACTIVITY-FRAMES: no compiled activity frames - cannot ground "
            "session/day answers on empty activity inventory (record raw "
            "capture then compile_activity_frames)",
            source_count=0,
        )

    if not compiled:
        return GateOutcome(
            ok=True,
            verdict="PASS",
            reason="ACTIVITY-FRAMES: no frames required; nothing to gate",
            exit_code=0,
            source_count=0,
            human_required=False,
        )

    invalid_timing: list[str] = []
    missing_evidence: list[str] = []
    for fr in compiled:
        if fr.t_end < fr.t_start:
            invalid_timing.append(fr.frame_id[:16])
        if (
            require_evidence
            and not frame_is_valid(fr)
            and (not fr.evidence_ptrs or any(not str(p).strip() for p in fr.evidence_ptrs))
        ):
            # distinguish timing already caught
            missing_evidence.append(fr.frame_id[:16] or "(empty-id)")

    if missing_evidence:
        return _fail_loud(
            f"ACTIVITY-FRAMES: {len(missing_evidence)} frame(s) lack evidence "
            f"pointers back to raw rows ids={missing_evidence[:8]} - "
            "compiled memory must be mechanically auditable",
            source_count=len(compiled),
        )

    if invalid_timing:
        return _fail(
            f"ACTIVITY-FRAMES: {len(invalid_timing)} frame(s) have t_end < t_start "
            f"ids={invalid_timing[:8]}",
            source_count=len(compiled),
        )

    if claimed_frame_ids is not None:
        inventory = {f.frame_id for f in compiled}
        claimed = [str(c).strip() for c in claimed_frame_ids if str(c).strip()]
        missing = [c for c in claimed if c not in inventory]
        if missing:
            return _fail(
                f"ACTIVITY-FRAMES: claimed_frame_ids not in compiled inventory "
                f"missing={missing[:8]} inventory_size={len(inventory)} - "
                "refuse answers citing uncompiled/unknown frames",
                source_count=len(compiled),
            )

    # Re-fingerprint check: frame_id must match content (tamper / non-deterministic).
    mismatched: list[str] = []
    for fr in compiled:
        expected = activity_frame_fingerprint(
            application=fr.application,
            site=fr.site,
            t_start=fr.t_start,
            t_end=fr.t_end,
            evidence_ptrs=fr.evidence_ptrs,
            input_volume=fr.input_volume,
        )
        if fr.frame_id != expected:
            mismatched.append(fr.frame_id[:16])
    if mismatched:
        return _fail(
            f"ACTIVITY-FRAMES: {len(mismatched)} frame_id(s) do not match "
            f"deterministic fingerprint ids={mismatched[:8]} - "
            "frames must be byte-identical / cacheable (no model rewrite)",
            source_count=len(compiled),
        )

    return GateOutcome(
        ok=True,
        verdict="PASS",
        reason=(f"ACTIVITY-FRAMES ok: frames={len(compiled)} evidence_ok mode=compiled"),
        exit_code=0,
        source_count=len(compiled),
        human_required=False,
    )


def assert_activity_memory_ok(
    frames: Sequence[ActivityFrame | dict[str, Any]] | None = None,
    **kwargs: Any,
) -> GateOutcome:
    """Raise :class:`ClosedLoopError` unless :func:`gate_activity_memory` is ok."""
    outcome = gate_activity_memory(frames, **kwargs)
    if not outcome.ok:
        raise ClosedLoopError(f"{outcome.verdict}: {outcome.reason}")
    return outcome
