"""CLI integration tests using subprocess."""

import json
import subprocess
import sys


def run(args, db, check=True):
    """Run foghorn CLI with the given args and a temp db."""
    cmd = [sys.executable, "-m", "foghorn.cli", "--db", str(db), *args]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)  # noqa: S603
    if check and result.returncode != 0:
        raise AssertionError(
            f"Command {args} failed with code {result.returncode}:\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )
    return result


def test_help_returns_zero_and_contains_stale(tmp_path):
    db = tmp_path / "world.db"
    result = run(["--help"], db)
    assert result.returncode == 0
    assert "stale" in result.stdout


def test_fact_command_stages_fact(tmp_path):
    db = tmp_path / "world.db"
    result = run(["fact", "Redis", "is-appropriate-for", "rate-limiting"], db)
    assert result.returncode == 0
    assert "Staged fact" in result.stdout


def test_decide_command_stages_decision(tmp_path):
    db = tmp_path / "world.db"
    run(["fact", "Redis", "is-appropriate-for", "rate-limiting"], db)
    result = run(["decide", "chose-redis", "Redis fits our needs"], db)
    assert result.returncode == 0
    assert "Staged decision" in result.stdout


def test_commit_command_creates_commit(tmp_path):
    db = tmp_path / "world.db"
    run(["fact", "Redis", "is-appropriate-for", "rate-limiting"], db)
    result = run(["commit", "-m", "test commit"], db)
    assert result.returncode == 0
    assert "Committed" in result.stdout


def test_stale_format_json_returns_valid_json(tmp_path):
    db = tmp_path / "world.db"
    run(["fact", "Redis", "is-appropriate-for", "rate-limiting"], db)
    run(["commit", "-m", "first"], db)
    result = run(["stale", "--format", "json"], db)
    assert result.returncode == 0
    data = json.loads(result.stdout)
    assert "alerts" in data
    assert "has_stale" in data


def test_stale_exit_code_zero_when_nothing_stale(tmp_path):
    db = tmp_path / "world.db"
    run(["fact", "Redis", "is-appropriate-for", "rate-limiting"], db)
    run(["commit", "-m", "only commit"], db)
    # No parent to diff against, so no staleness
    result = run(["stale", "--exit-code"], db)
    assert result.returncode == 0


def test_log_shows_commits(tmp_path):
    db = tmp_path / "world.db"
    run(["fact", "Redis", "is-appropriate-for", "rate-limiting"], db)
    run(["commit", "-m", "my first commit"], db)
    result = run(["log"], db)
    assert result.returncode == 0
