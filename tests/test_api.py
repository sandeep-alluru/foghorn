"""Tests for worldgit FastAPI REST endpoints."""

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient

from worldgit.api import app

client = TestClient(app)


def test_health_returns_ok():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
    assert "version" in r.json()


def test_app_title():
    assert app.title == "worldgit API"


def test_fact_endpoint_returns_fact(tmp_path):
    db = str(tmp_path / "world.db")
    r = client.post(
        "/fact",
        json={
            "subject": "Redis",
            "predicate": "is-appropriate-for",
            "object": "rate-limiting",
            "db": db,
        },
    )
    assert r.status_code == 200
    data = r.json()
    assert data["subject"] == "Redis"
    assert "id" in data


def test_decide_endpoint_returns_decision(tmp_path):
    db = str(tmp_path / "world.db")
    # Stage a fact first
    r_fact = client.post(
        "/fact", json={"subject": "Redis", "predicate": "is", "object": "fast", "db": db}
    )
    fact_id = r_fact.json()["id"]

    r = client.post(
        "/decide",
        json={
            "label": "chose-redis",
            "content": "Redis is fast enough",
            "depends_on": [fact_id],
            "db": db,
        },
    )
    assert r.status_code == 200
    data = r.json()
    assert data["label"] == "chose-redis"
    assert fact_id in data["fact_ids"]


def test_commit_endpoint_creates_commit(tmp_path):
    db = str(tmp_path / "world.db")
    client.post("/fact", json={"subject": "Redis", "predicate": "is", "object": "fast", "db": db})
    r = client.post("/commit", json={"message": "test commit", "db": db})
    assert r.status_code == 200
    data = r.json()
    assert data["message"] == "test commit"
    assert "id" in data


def test_commit_nothing_staged_returns_422(tmp_path):
    db = str(tmp_path / "world.db")
    r = client.post("/commit", json={"message": "empty", "db": db})
    assert r.status_code == 422


def test_stale_endpoint_returns_alerts(tmp_path):
    db = str(tmp_path / "world.db")
    # First commit: add fact + decision
    r_fact = client.post(
        "/fact", json={"subject": "Redis", "predicate": "is", "object": "fast", "db": db}
    )
    fact_id = r_fact.json()["id"]
    client.post(
        "/decide",
        json={
            "label": "chose-redis",
            "content": "Redis is fast",
            "depends_on": [fact_id],
            "db": db,
        },
    )
    client.post("/commit", json={"message": "first", "db": db})
    # Second commit: change the fact
    client.post(
        "/fact", json={"subject": "Valkey", "predicate": "replaced", "object": "Redis", "db": db}
    )
    client.post("/commit", json={"message": "second", "db": db})
    # Check staleness
    r = client.get("/stale", params={"db": db})
    assert r.status_code == 200
    data = r.json()
    assert "has_stale" in data
    assert "alerts" in data


def test_log_endpoint_returns_commits(tmp_path):
    db = str(tmp_path / "world.db")
    client.post("/fact", json={"subject": "Redis", "predicate": "is", "object": "fast", "db": db})
    client.post("/commit", json={"message": "first commit", "db": db})
    r = client.get("/log", params={"db": db})
    assert r.status_code == 200
    assert len(r.json()["commits"]) == 1
