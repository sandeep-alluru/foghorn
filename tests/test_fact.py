"""Tests for Fact, Decision, and StalenessAlert from worldgit.fact."""

from worldgit.fact import Decision, Fact, StalenessAlert

# ── Fact tests ────────────────────────────────────────────────────────────────


def test_fact_id_is_content_addressed():
    f1 = Fact("Redis", "is-appropriate-for", "rate-limiting")
    f2 = Fact("Redis", "is-appropriate-for", "rate-limiting")
    assert f1.id == f2.id


def test_fact_different_content_has_different_id():
    f1 = Fact("Redis", "is-appropriate-for", "rate-limiting")
    f2 = Fact("Redis", "is-appropriate-for", "caching")
    assert f1.id != f2.id


def test_fact_id_length():
    f = Fact("A", "B", "C")
    assert len(f.id) == 16


def test_fact_to_dict_from_dict_roundtrip():
    f = Fact("Postgres", "is-primary-db", "yes", confidence=0.9)
    d = f.to_dict()
    f2 = Fact.from_dict(d)
    assert f2.id == f.id
    assert f2.subject == f.subject
    assert f2.predicate == f.predicate
    assert f2.object == f.object
    assert f2.confidence == f.confidence


def test_fact_confidence_default():
    f = Fact("JWT", "used-for", "auth")
    assert f.confidence == 1.0


def test_fact_to_dict_has_all_keys():
    f = Fact("S", "P", "O")
    d = f.to_dict()
    for key in ("id", "subject", "predicate", "object", "confidence", "recorded_at"):
        assert key in d


# ── Decision tests ─────────────────────────────────────────────────────────────


def test_decision_id_is_content_addressed():
    d1 = Decision("chose-redis", "Redis fits our needs")
    d2 = Decision("chose-redis", "Redis fits our needs")
    assert d1.id == d2.id


def test_decision_different_label_has_different_id():
    d1 = Decision("chose-redis", "Redis fits our needs")
    d2 = Decision("chose-postgres", "Redis fits our needs")
    assert d1.id != d2.id


def test_decision_to_dict_from_dict_roundtrip():
    d = Decision("chose-redis", "Redis is best for rate-limiting", fact_ids=["abc", "def"])
    data = d.to_dict()
    d2 = Decision.from_dict(data)
    assert d2.id == d.id
    assert d2.label == d.label
    assert d2.content == d.content
    assert d2.fact_ids == d.fact_ids


def test_decision_fact_ids_default_empty():
    d = Decision("my-decision", "some reasoning")
    assert d.fact_ids == []


# ── StalenessAlert tests ───────────────────────────────────────────────────────


def test_staleness_alert_to_dict():
    alert = StalenessAlert(
        decision_id="abc123",
        decision_label="chose-redis",
        stale_fact_ids=["f1", "f2"],
        impact_score=0.85,
    )
    d = alert.to_dict()
    assert d["decision_id"] == "abc123"
    assert d["decision_label"] == "chose-redis"
    assert d["stale_fact_ids"] == ["f1", "f2"]
    assert d["impact_score"] == 0.85


def test_staleness_alert_impact_score_rounded():
    alert = StalenessAlert("x", "y", [], 0.123456789)
    d = alert.to_dict()
    assert d["impact_score"] == round(0.123456789, 4)
