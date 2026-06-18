"""Tests for foghorn.report formatters."""

import io
import json

from rich.console import Console

from foghorn.fact import StalenessAlert
from foghorn.repo import WorldRepo
from foghorn.report import print_diff, print_log, print_stale, to_json, to_markdown
from foghorn.staleness import diff_commits


def _console(buf: io.StringIO) -> Console:
    return Console(file=buf, highlight=False, no_color=True)


def _make_alerts() -> list[StalenessAlert]:
    return [
        StalenessAlert(
            decision_id="abc123",
            decision_label="chose-redis",
            stale_fact_ids=["fact1", "fact2"],
            impact_score=0.9,
        ),
        StalenessAlert(
            decision_id="def456",
            decision_label="chose-postgres",
            stale_fact_ids=["fact3"],
            impact_score=0.7,
        ),
    ]


def test_print_stale_no_alerts():
    buf = io.StringIO()
    print_stale([], console=_console(buf))
    assert "No stale" in buf.getvalue()


def test_print_stale_with_alerts():
    buf = io.StringIO()
    print_stale(_make_alerts(), console=_console(buf))
    output = buf.getvalue()
    assert "STALE" in output or "stale" in output.lower()
    assert "chose-redis" in output


def test_to_json_no_alerts():
    result = json.loads(to_json([]))
    assert result["has_stale"] is False
    assert result["stale_count"] == 0
    assert result["alerts"] == []


def test_to_json_with_alerts():
    result = json.loads(to_json(_make_alerts()))
    assert result["has_stale"] is True
    assert result["stale_count"] == 2
    assert len(result["alerts"]) == 2
    assert result["alerts"][0]["decision_label"] == "chose-redis"


def test_to_json_with_diff(tmp_path):
    with WorldRepo.init(str(tmp_path / "world.db")) as repo:
        repo.add_fact("Redis", "is-appropriate-for", "rate-limiting")
        c1 = repo.commit("first")
        repo.add_fact("Valkey", "replaced", "Redis")
        c2 = repo.commit("second")
        d = diff_commits(repo.store, c1, c2)
    result = json.loads(to_json([], diff=d))
    assert "diff" in result
    assert "added_facts" in result["diff"]


def test_to_markdown_no_alerts():
    md = to_markdown([])
    assert "No stale" in md
    assert "foghorn" in md


def test_to_markdown_with_alerts():
    md = to_markdown(_make_alerts())
    assert "stale" in md.lower()
    assert "chose-redis" in md
    assert "|" in md  # has table


def test_print_log_empty():
    buf = io.StringIO()
    print_log([], console=_console(buf))
    assert "No commits" in buf.getvalue()


def test_print_log_with_commits(tmp_path):
    with WorldRepo.init(str(tmp_path / "world.db")) as repo:
        repo.add_fact("Redis", "is", "fast")
        repo.commit("first commit")
        commits = repo.log()
    buf = io.StringIO()
    print_log(commits, console=_console(buf))
    assert "first commit" in buf.getvalue()


def test_print_diff(tmp_path):
    with WorldRepo.init(str(tmp_path / "world.db")) as repo:
        repo.add_fact("Redis", "is-appropriate-for", "rate-limiting")
        c1 = repo.commit("first")
        repo.add_fact("Valkey", "replaced", "Redis")
        c2 = repo.commit("second")
        d = repo.diff(c1, c2)
        store = repo.store
        buf = io.StringIO()
        print_diff(d, store, console=_console(buf))
    assert "Valkey" in buf.getvalue() or "+" in buf.getvalue()
