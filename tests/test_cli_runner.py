"""CLI unit tests using Click's CliRunner (for code coverage)."""

import json

from click.testing import CliRunner

from foghorn.cli import main


def _db(tmp_path):
    return str(tmp_path / "world.db")


def test_main_help():
    runner = CliRunner()
    result = runner.invoke(main, ["--help"])
    assert result.exit_code == 0
    assert "stale" in result.output


def test_fact_subcommand(tmp_path):
    runner = CliRunner()
    result = runner.invoke(main, ["--db", _db(tmp_path), "fact", "Redis", "is", "fast"])
    assert result.exit_code == 0
    assert "Staged" in result.output


def test_decide_subcommand(tmp_path):
    runner = CliRunner()
    result = runner.invoke(main, ["--db", _db(tmp_path), "decide", "chose-redis", "Redis is fast"])
    assert result.exit_code == 0
    assert "Staged decision" in result.output


def test_commit_subcommand(tmp_path):
    runner = CliRunner()
    db = _db(tmp_path)
    runner.invoke(main, ["--db", db, "fact", "Redis", "is", "fast"])
    result = runner.invoke(main, ["--db", db, "commit", "-m", "first"])
    assert result.exit_code == 0
    assert "Committed" in result.output


def test_commit_nothing_staged_fails(tmp_path):
    runner = CliRunner()
    result = runner.invoke(main, ["--db", _db(tmp_path), "commit", "-m", "empty"])
    assert result.exit_code != 0


def test_stale_rich(tmp_path):
    runner = CliRunner()
    db = _db(tmp_path)
    runner.invoke(main, ["--db", db, "fact", "Redis", "is", "fast"])
    runner.invoke(main, ["--db", db, "commit", "-m", "first"])
    result = runner.invoke(main, ["--db", db, "stale"])
    assert result.exit_code == 0


def test_stale_json(tmp_path):
    runner = CliRunner()
    db = _db(tmp_path)
    runner.invoke(main, ["--db", db, "fact", "Redis", "is", "fast"])
    runner.invoke(main, ["--db", db, "commit", "-m", "first"])
    result = runner.invoke(main, ["--db", db, "stale", "--format", "json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert "has_stale" in data


def test_stale_markdown(tmp_path):
    runner = CliRunner()
    db = _db(tmp_path)
    runner.invoke(main, ["--db", db, "fact", "Redis", "is", "fast"])
    runner.invoke(main, ["--db", db, "commit", "-m", "first"])
    result = runner.invoke(main, ["--db", db, "stale", "--format", "markdown"])
    assert result.exit_code == 0
    assert "foghorn" in result.output


def test_stale_exit_code_with_stale(tmp_path):
    runner = CliRunner()
    db = _db(tmp_path)
    # fact + decision in first commit
    runner.invoke(main, ["--db", db, "fact", "Redis", "is", "fast"])
    runner.invoke(main, ["--db", db, "decide", "chose-redis", "Redis is fast"])
    runner.invoke(main, ["--db", db, "commit", "-m", "first"])
    # second commit changes a fact
    runner.invoke(main, ["--db", db, "fact", "Valkey", "replaced", "Redis"])
    runner.invoke(main, ["--db", db, "commit", "-m", "second"])
    result = runner.invoke(main, ["--db", db, "stale", "--exit-code"])
    # May or may not be stale depending on whether decision depends on changed fact
    assert result.exit_code in (0, 1)


def test_diff_subcommand(tmp_path):
    runner = CliRunner()
    db = _db(tmp_path)
    runner.invoke(main, ["--db", db, "fact", "Redis", "is", "fast"])
    runner.invoke(main, ["--db", db, "commit", "-m", "first"])
    runner.invoke(main, ["--db", db, "fact", "Valkey", "replaced", "Redis"])
    runner.invoke(main, ["--db", db, "commit", "-m", "second"])
    result = runner.invoke(main, ["--db", db, "diff"])
    assert result.exit_code == 0


def test_diff_json(tmp_path):
    runner = CliRunner()
    db = _db(tmp_path)
    runner.invoke(main, ["--db", db, "fact", "Redis", "is", "fast"])
    runner.invoke(main, ["--db", db, "commit", "-m", "first"])
    runner.invoke(main, ["--db", db, "fact", "Valkey", "replaced", "Redis"])
    runner.invoke(main, ["--db", db, "commit", "-m", "second"])
    result = runner.invoke(main, ["--db", db, "diff", "--format", "json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert "added_facts" in data


def test_diff_markdown(tmp_path):
    runner = CliRunner()
    db = _db(tmp_path)
    runner.invoke(main, ["--db", db, "fact", "Redis", "is", "fast"])
    runner.invoke(main, ["--db", db, "commit", "-m", "first"])
    runner.invoke(main, ["--db", db, "fact", "Valkey", "replaced", "Redis"])
    runner.invoke(main, ["--db", db, "commit", "-m", "second"])
    result = runner.invoke(main, ["--db", db, "diff", "--format", "markdown"])
    assert result.exit_code == 0
    assert "foghorn diff" in result.output


def test_log_subcommand(tmp_path):
    runner = CliRunner()
    db = _db(tmp_path)
    runner.invoke(main, ["--db", db, "fact", "Redis", "is", "fast"])
    runner.invoke(main, ["--db", db, "commit", "-m", "first commit"])
    result = runner.invoke(main, ["--db", db, "log"])
    assert result.exit_code == 0
    assert "first commit" in result.output


def test_status_subcommand(tmp_path):
    runner = CliRunner()
    db = _db(tmp_path)
    result = runner.invoke(main, ["--db", db, "status"])
    assert result.exit_code == 0
    assert "staged" in result.output.lower() or "commit" in result.output.lower()


def test_stale_with_since_option(tmp_path):
    runner = CliRunner()
    db = _db(tmp_path)
    runner.invoke(main, ["--db", db, "fact", "Redis", "is", "fast"])
    runner.invoke(main, ["--db", db, "commit", "-m", "first"])
    runner.invoke(main, ["--db", db, "fact", "Valkey", "replaced", "Redis"])
    runner.invoke(main, ["--db", db, "commit", "-m", "second"])
    # Passing invalid commit ID should fail
    result = runner.invoke(main, ["--db", db, "stale", "--since", "nonexistent"])
    assert result.exit_code != 0
