"""Fact and Decision data models — the content-addressed primitives of foghorn."""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any


def _sha16(text: str) -> str:
    """Return the first 16 hex chars of SHA-256(text)."""
    return hashlib.sha256(text.encode()).hexdigest()[:16]


@dataclass
class Fact:
    """An immutable, content-addressed triple that agents assert about the world.

    Facts are the atoms of foghorn. Two Facts with the same subject, predicate,
    and object always have the same ID, regardless of when they were recorded.

    Attributes:
        id: Content-addressed identifier — SHA-256[:16] of "{subject}|{predicate}|{object}".
        subject: The entity this fact is about (e.g. "Redis").
        predicate: The relationship being asserted (e.g. "is-appropriate-for").
        object: The value of the assertion (e.g. "rate-limiting").
        confidence: Belief weight in [0.0, 1.0]. Default 1.0 (certain).
        recorded_at: Unix timestamp when this fact was committed.
    """

    subject: str
    predicate: str
    object: str
    confidence: float = 1.0
    recorded_at: float = field(default_factory=time.time)
    id: str = field(init=False)

    def __post_init__(self) -> None:
        self.id = _sha16(f"{self.subject}|{self.predicate}|{self.object}")

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-compatible dict."""
        return {
            "id": self.id,
            "subject": self.subject,
            "predicate": self.predicate,
            "object": self.object,
            "confidence": self.confidence,
            "recorded_at": self.recorded_at,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Fact:
        """Deserialize from a dict produced by to_dict()."""
        f = cls(
            subject=d["subject"],
            predicate=d["predicate"],
            object=d["object"],
            confidence=d.get("confidence", 1.0),
            recorded_at=d.get("recorded_at", 0.0),
        )
        return f

    def __repr__(self) -> str:
        return f"Fact({self.id!r}: {self.subject!r} {self.predicate!r} {self.object!r})"


@dataclass
class Decision:
    """A named agent conclusion recorded alongside the facts it depended on.

    Decisions are the nodes that foghorn watches for staleness. When any
    Fact listed in ``fact_ids`` changes, this Decision is marked stale.

    Attributes:
        id: Content-addressed identifier — SHA-256[:16] of "{label}|{content}".
        label: Short slug describing the decision (e.g. "chose-redis-for-rate-limiting").
        content: Full reasoning text or justification.
        fact_ids: IDs of the Facts this decision directly depended on.
        recorded_at: Unix timestamp when this decision was recorded.
    """

    label: str
    content: str
    fact_ids: list[str] = field(default_factory=list)
    recorded_at: float = field(default_factory=time.time)
    id: str = field(init=False)

    def __post_init__(self) -> None:
        self.id = _sha16(f"{self.label}|{self.content}")

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-compatible dict."""
        return {
            "id": self.id,
            "label": self.label,
            "content": self.content,
            "fact_ids": self.fact_ids,
            "recorded_at": self.recorded_at,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Decision:
        """Deserialize from a dict produced by to_dict()."""
        dec = cls(
            label=d["label"],
            content=d["content"],
            fact_ids=d.get("fact_ids", []),
            recorded_at=d.get("recorded_at", 0.0),
        )
        return dec

    def __repr__(self) -> str:
        return f"Decision({self.id!r}: {self.label!r}, depends_on={len(self.fact_ids)} facts)"


@dataclass
class StalenessAlert:
    """Emitted when a Decision's upstream facts have changed.

    Attributes:
        decision_id: ID of the stale Decision.
        decision_label: Human-readable label for display.
        stale_fact_ids: Which specific facts changed and triggered this alert.
        impact_score: Confidence-weighted importance in [0.0, 1.0].
            Higher = more confidence was placed in the now-changed facts.
    """

    decision_id: str
    decision_label: str
    stale_fact_ids: list[str]
    impact_score: float

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-compatible dict."""
        return {
            "decision_id": self.decision_id,
            "decision_label": self.decision_label,
            "stale_fact_ids": self.stale_fact_ids,
            "impact_score": round(self.impact_score, 4),
        }
