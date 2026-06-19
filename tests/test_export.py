"""Tests for foghorn.export — export_json, import_json, export_graphviz."""

from __future__ import annotations

import json

import pytest

from foghorn.export import export_graphviz, export_json, import_json
from foghorn.repo import WorldRepo


@pytest.fixture
def repo(tmp_path):
    db = tmp_path / "world.db"
    r = WorldRepo.init(str(db))
    yield r
    r.close()


@pytest.fixture
def populated_repo(tmp_path):
    db = tmp_path / "pop.db"
    r = WorldRepo.init(str(db))
    f = r.add_fact("Redis", "supports", "pub-sub")
    r.decide("use-redis-pubsub", "Redis pub-sub is fast", depends_on=[f.id])
    r.commit("initial state")
    yield r
    r.close()


def test_export_json_returns_string(populated_repo: WorldRepo) -> None:
    """export_json should return a non-empty JSON string."""
    result = export_json(populated_repo)
    assert isinstance(result, str)
    assert len(result) > 0


def test_export_json_valid_json(populated_repo: WorldRepo) -> None:
    """export_json output must be valid JSON with expected keys."""
    raw = export_json(populated_repo)
    data = json.loads(raw)
    assert "facts" in data
    assert "decisions" in data
    assert "commits" in data


def test_export_json_contains_data(populated_repo: WorldRepo) -> None:
    """Exported JSON should contain the fact and decision we added."""
    data = json.loads(export_json(populated_repo))
    fact_subjects = [f["subject"] for f in data["facts"]]
    decision_labels = [d["label"] for d in data["decisions"]]
    assert "Redis" in fact_subjects
    assert "use-redis-pubsub" in decision_labels


def test_import_json_returns_count(tmp_path: "Path", populated_repo: WorldRepo) -> None:
    """import_json should return a positive count of imported items."""
    target_db = tmp_path / "target.db"
    target = WorldRepo.init(str(target_db))
    raw = export_json(populated_repo)
    count = import_json(raw, target)
    target.close()
    assert count > 0


def test_import_json_from_file(tmp_path, populated_repo: WorldRepo) -> None:
    """import_json should accept a file path as well as a raw JSON string."""
    json_path = tmp_path / "export.json"
    json_path.write_text(export_json(populated_repo), encoding="utf-8")
    target_db = tmp_path / "target2.db"
    target = WorldRepo.init(str(target_db))
    count = import_json(str(json_path), target)
    target.close()
    assert count > 0


def test_export_graphviz_returns_dot(populated_repo: WorldRepo) -> None:
    """export_graphviz should return a valid DOT string."""
    dot = export_graphviz(populated_repo)
    assert dot.startswith("digraph foghorn {")
    assert "}" in dot


def test_export_graphviz_contains_nodes(populated_repo: WorldRepo) -> None:
    """DOT output should contain fact and decision nodes."""
    dot = export_graphviz(populated_repo)
    assert "fact_" in dot
    assert "dec_" in dot
    assert "Redis" in dot


def test_repo_export_json_convenience(populated_repo: WorldRepo) -> None:
    """repo.export_json() convenience method should work identically."""
    result = populated_repo.export_json()
    data = json.loads(result)
    assert "facts" in data
