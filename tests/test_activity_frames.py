"""ACTIVITY-FRAMES — deterministic screen-activity memory (arXiv 2608.05784).

Track B public research maps Activity Frames → foghorn deep-dive.
Failure: agents re-derive routines from LLM summaries / raw capture instead of
compiled frames with evidence pointers (paper: summaries 66–80% vs frames ~98%).
"""

from __future__ import annotations

import pytest

from foghorn.activity import (
    ActivityFrame,
    RawCaptureRow,
    activity_frame_fingerprint,
    assert_activity_memory_ok,
    compile_activity_frames,
    frame_is_valid,
    gate_activity_memory,
)
from foghorn.closed_loop import ClosedLoopError


def _rows_same_app() -> list[RawCaptureRow]:
    base = 1_700_000_000.0
    return [
        RawCaptureRow("r1", base + 0, "Chrome", "github.com", "click"),
        RawCaptureRow("r2", base + 5, "Chrome", "github.com", "key"),
        RawCaptureRow("r3", base + 10, "Chrome", "github.com", "key"),
        RawCaptureRow("r4", base + 20, "Code", "", "key"),
        RawCaptureRow("r5", base + 25, "Code", "", "click"),
    ]


def test_compile_splits_on_application_change() -> None:
    frames = compile_activity_frames(_rows_same_app())
    assert len(frames) == 2
    assert frames[0].application == "Chrome"
    assert frames[0].site == "github.com"
    assert frames[0].evidence_ptrs == ("r1", "r2", "r3")
    assert frames[0].input_volume == 3
    assert frames[0].row_count == 3
    assert frames[1].application == "Code"
    assert frames[1].evidence_ptrs == ("r4", "r5")
    assert frames[1].input_volume == 2


def test_compile_splits_on_site_change() -> None:
    base = 1_700_000_100.0
    rows = [
        RawCaptureRow("a", base, "Chrome", "news.ycombinator.com", "click"),
        RawCaptureRow("b", base + 2, "Chrome", "arxiv.org", "click"),
    ]
    frames = compile_activity_frames(rows)
    assert len(frames) == 2
    assert frames[0].site == "news.ycombinator.com"
    assert frames[1].site == "arxiv.org"


def test_compile_splits_on_gap() -> None:
    base = 1_700_000_200.0
    rows = [
        RawCaptureRow("a", base, "Terminal", "", "key"),
        RawCaptureRow("b", base + 900, "Terminal", "", "key"),  # >300s default
    ]
    frames = compile_activity_frames(rows, gap_split_seconds=300)
    assert len(frames) == 2


def test_compile_is_byte_identical() -> None:
    rows = _rows_same_app()
    a = compile_activity_frames(rows)
    b = compile_activity_frames(list(reversed(rows)))  # order independent
    assert [f.frame_id for f in a] == [f.frame_id for f in b]
    assert a[0].to_dict() == b[0].to_dict()


def test_fingerprint_stable() -> None:
    fid = activity_frame_fingerprint(
        application="Chrome",
        site="github.com",
        t_start=1.0,
        t_end=2.0,
        evidence_ptrs=["r1", "r2"],
        input_volume=2,
    )
    fid2 = activity_frame_fingerprint(
        application="Chrome",
        site="github.com",
        t_start=1.0,
        t_end=2.0,
        evidence_ptrs=["r1", "r2"],
        input_volume=2,
    )
    assert fid == fid2
    assert len(fid) == 64


def test_llm_summary_mode_fails() -> None:
    """Paper failure: LLM summary as sole activity memory."""
    out = gate_activity_memory(memory_mode="llm_summary")
    assert out.ok is False
    assert out.verdict == "FAIL"
    assert out.exit_code == 1
    assert out.human_required is True
    assert "llm_summary" in out.reason
    assert "ACTIVITY-FRAMES" in out.reason


def test_raw_uncompiled_mode_fails() -> None:
    out = gate_activity_memory(memory_mode="raw_uncompiled")
    assert out.ok is False
    assert out.verdict == "FAIL"
    assert "raw_uncompiled" in out.reason


def test_empty_compiled_fails_loud() -> None:
    out = gate_activity_memory([], memory_mode="compiled", require_frames=True)
    assert out.ok is False
    assert out.verdict == "FAIL_LOUD"
    assert out.exit_code == 2
    assert "no compiled" in out.reason.lower() or "empty" in out.reason.lower()


def test_missing_evidence_fails_loud() -> None:
    bad = ActivityFrame(
        frame_id="x",
        application="Chrome",
        site="",
        t_start=1.0,
        t_end=2.0,
        input_volume=0,
        evidence_ptrs=(),  # no evidence
    )
    # fingerprint mismatch + missing evidence — evidence checked first path
    out = gate_activity_memory([bad], memory_mode="compiled")
    assert out.ok is False
    assert out.verdict == "FAIL_LOUD"
    assert "evidence" in out.reason.lower()


def test_valid_compiled_passes() -> None:
    frames = compile_activity_frames(_rows_same_app())
    out = gate_activity_memory(frames, memory_mode="compiled")
    assert out.ok is True
    assert out.verdict == "PASS"
    assert out.exit_code == 0
    assert out.source_count == 2
    payload = out.to_dict()
    assert payload["source_count"] == 2


def test_compile_from_raw_inside_gate() -> None:
    """Gate may compile raw_rows when frames omitted."""
    out = gate_activity_memory(
        None,
        memory_mode="compiled",
        raw_rows=_rows_same_app(),
    )
    assert out.ok is True
    assert out.source_count == 2


def test_dict_rows_compile() -> None:
    rows = [
        {
            "row_id": "1",
            "timestamp": 10.0,
            "application": "Slack",
            "site": "",
            "input_kind": "key",
        },
        {
            "id": "2",
            "ts": 12.0,
            "app": "Slack",
            "kind": "click",
        },
    ]
    frames = compile_activity_frames(rows)
    assert len(frames) == 1
    assert frames[0].evidence_ptrs == ("1", "2")
    assert frames[0].input_volume == 2


def test_tampered_frame_id_fails() -> None:
    frames = compile_activity_frames(_rows_same_app())
    good = frames[0]
    tampered = ActivityFrame(
        frame_id="0" * 64,  # wrong
        application=good.application,
        site=good.site,
        t_start=good.t_start,
        t_end=good.t_end,
        input_volume=good.input_volume,
        evidence_ptrs=good.evidence_ptrs,
        row_count=good.row_count,
    )
    out = gate_activity_memory([tampered, frames[1]], memory_mode="compiled")
    assert out.ok is False
    assert out.verdict == "FAIL"
    assert "fingerprint" in out.reason.lower() or "byte-identical" in out.reason


def test_invalid_timing_fails() -> None:
    ptrs = ("e1",)
    fid = activity_frame_fingerprint(
        application="X",
        site="",
        t_start=10.0,
        t_end=1.0,
        evidence_ptrs=ptrs,
        input_volume=0,
    )
    bad = ActivityFrame(
        frame_id=fid,
        application="X",
        site="",
        t_start=10.0,
        t_end=1.0,
        input_volume=0,
        evidence_ptrs=ptrs,
    )
    out = gate_activity_memory([bad], memory_mode="compiled")
    assert out.ok is False
    assert out.verdict == "FAIL"
    assert "t_end" in out.reason


def test_claimed_frame_ids_must_exist() -> None:
    frames = compile_activity_frames(_rows_same_app())
    out = gate_activity_memory(
        frames,
        memory_mode="compiled",
        claimed_frame_ids=[frames[0].frame_id, "not-a-real-frame"],
    )
    assert out.ok is False
    assert out.verdict == "FAIL"
    assert "claimed_frame_ids" in out.reason


def test_claimed_frame_ids_ok() -> None:
    frames = compile_activity_frames(_rows_same_app())
    out = gate_activity_memory(
        frames,
        memory_mode="compiled",
        claimed_frame_ids=[frames[0].frame_id],
    )
    assert out.ok is True


def test_arxiv_activity_frames_fixture() -> None:
    """End-to-end public case: refuse LLM memory; accept compiled day block."""
    # Simulate a short "day" of professional screen activity
    base = 1_720_000_000.0
    day_rows = [
        RawCaptureRow("d1", base + 0, "Chrome", "docs.google.com", "key"),
        RawCaptureRow("d2", base + 30, "Chrome", "docs.google.com", "key"),
        RawCaptureRow("d3", base + 60, "Chrome", "docs.google.com", "click"),
        RawCaptureRow("d4", base + 120, "Chrome", "github.com", "click"),
        RawCaptureRow("d5", base + 150, "Chrome", "github.com", "key"),
        RawCaptureRow("d6", base + 400, "Terminal", "", "key"),
        RawCaptureRow("d7", base + 420, "Terminal", "", "key"),
    ]
    # Pre-fix class: agent uses LLM summary only
    refuse = gate_activity_memory(memory_mode="llm_summary")
    assert refuse.ok is False
    assert refuse.verdict == "FAIL"

    # Post-fix class: deterministic compile → gate PASS
    frames = compile_activity_frames(day_rows)
    assert len(frames) >= 3  # docs.google, github, Terminal
    accept = gate_activity_memory(frames, memory_mode="compiled")
    assert accept.ok is True
    assert accept.verdict == "PASS"
    # All frames mechanically auditable
    assert all(frame_is_valid(f) for f in frames)
    # Prompt-ready block is just the frame dicts (86x smaller idea — structural)
    block = [f.to_dict() for f in frames]
    assert all("evidence_ptrs" in b and b["evidence_ptrs"] for b in block)


def test_assert_activity_memory_ok_raises() -> None:
    with pytest.raises(ClosedLoopError):
        assert_activity_memory_ok(memory_mode="llm_summary")


def test_require_frames_false_empty_passes() -> None:
    out = gate_activity_memory([], memory_mode="compiled", require_frames=False)
    assert out.ok is True


def test_unknown_mode_fails_loud() -> None:
    out = gate_activity_memory(memory_mode="magic")  # type: ignore[arg-type]
    assert out.ok is False
    assert out.verdict == "FAIL_LOUD"
