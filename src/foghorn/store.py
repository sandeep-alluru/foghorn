"""SQLite-backed content-addressed store for Facts, Decisions, and Commits."""

from __future__ import annotations

import json
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from foghorn.fact import Decision, Fact, _sha16


@dataclass
class WorldCommit:
    """A snapshot of world state at a point in time.

    Attributes:
        id: Content-addressed identifier.
        message: Human-readable commit message.
        fact_ids: Set of Fact IDs in this snapshot.
        decision_ids: Set of Decision IDs in this snapshot.
        parent_id: ID of the parent commit, or None for the initial commit.
        timestamp: Unix timestamp of this commit.
    """

    message: str
    fact_ids: set[str] = field(default_factory=set)
    decision_ids: set[str] = field(default_factory=set)
    parent_id: str | None = None
    timestamp: float = field(default_factory=time.time)
    id: str = field(init=False)

    def __post_init__(self) -> None:
        payload = json.dumps(
            {
                "message": self.message,
                "fact_ids": sorted(self.fact_ids),
                "decision_ids": sorted(self.decision_ids),
                "parent_id": self.parent_id,
            },
            sort_keys=True,
        )
        self.id = _sha16(payload)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-compatible dict."""
        return {
            "id": self.id,
            "message": self.message,
            "fact_ids": sorted(self.fact_ids),
            "decision_ids": sorted(self.decision_ids),
            "parent_id": self.parent_id,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> WorldCommit:
        """Deserialize from a dict produced by to_dict()."""
        c = cls(
            message=d["message"],
            fact_ids=set(d.get("fact_ids", [])),
            decision_ids=set(d.get("decision_ids", [])),
            parent_id=d.get("parent_id"),
            timestamp=d.get("timestamp", 0.0),
        )
        if "id" in d:
            c.id = d["id"]
        return c


class WorldStore:
    """SQLite-backed persistence layer for foghorn.

    All Facts, Decisions, and Commits are stored in a single SQLite database.
    Content-addressed IDs guarantee deduplication: storing the same fact twice
    is a no-op.

    Attributes:
        path: Path to the SQLite database file.
    """

    _SCHEMA = """
    CREATE TABLE IF NOT EXISTS facts (
        id TEXT PRIMARY KEY,
        subject TEXT NOT NULL,
        predicate TEXT NOT NULL,
        object TEXT NOT NULL,
        confidence REAL NOT NULL DEFAULT 1.0,
        recorded_at REAL NOT NULL
    );
    CREATE TABLE IF NOT EXISTS decisions (
        id TEXT PRIMARY KEY,
        label TEXT NOT NULL,
        content TEXT NOT NULL,
        recorded_at REAL NOT NULL
    );
    CREATE TABLE IF NOT EXISTS decision_facts (
        decision_id TEXT NOT NULL,
        fact_id TEXT NOT NULL,
        PRIMARY KEY (decision_id, fact_id)
    );
    CREATE TABLE IF NOT EXISTS commits (
        id TEXT PRIMARY KEY,
        message TEXT NOT NULL,
        parent_id TEXT,
        timestamp REAL NOT NULL
    );
    CREATE TABLE IF NOT EXISTS commit_facts (
        commit_id TEXT NOT NULL,
        fact_id TEXT NOT NULL,
        PRIMARY KEY (commit_id, fact_id)
    );
    CREATE TABLE IF NOT EXISTS commit_decisions (
        commit_id TEXT NOT NULL,
        decision_id TEXT NOT NULL,
        PRIMARY KEY (commit_id, decision_id)
    );
    CREATE TABLE IF NOT EXISTS refs (
        name TEXT PRIMARY KEY,
        commit_id TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS staging (
        type TEXT NOT NULL,
        id TEXT NOT NULL,
        PRIMARY KEY (type, id)
    );
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.path))
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(self._SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        """Close the database connection."""
        self._conn.close()

    # ── Facts ─────────────────────────────────────────────────────────────────

    def add_fact(self, fact: Fact) -> None:
        """Store a Fact (no-op if already stored)."""
        self._conn.execute(
            "INSERT OR IGNORE INTO facts VALUES (?,?,?,?,?,?)",
            (fact.id, fact.subject, fact.predicate, fact.object, fact.confidence, fact.recorded_at),
        )
        self._conn.execute(
            "INSERT OR IGNORE INTO staging VALUES (?,?)",
            ("fact", fact.id),
        )
        self._conn.commit()

    def get_fact(self, fact_id: str) -> Fact | None:
        """Retrieve a Fact by ID, or None if not found."""
        row = self._conn.execute("SELECT * FROM facts WHERE id=?", (fact_id,)).fetchone()
        if row is None:
            return None
        return Fact.from_dict(dict(row))

    def list_facts(self) -> list[Fact]:
        """Return all stored Facts ordered by recorded_at."""
        rows = self._conn.execute("SELECT * FROM facts ORDER BY recorded_at").fetchall()
        return [Fact.from_dict(dict(r)) for r in rows]

    # ── Decisions ─────────────────────────────────────────────────────────────

    def add_decision(self, decision: Decision) -> None:
        """Store a Decision and its dependency edges (no-op if already stored)."""
        self._conn.execute(
            "INSERT OR IGNORE INTO decisions VALUES (?,?,?,?)",
            (decision.id, decision.label, decision.content, decision.recorded_at),
        )
        for fid in decision.fact_ids:
            self._conn.execute(
                "INSERT OR IGNORE INTO decision_facts VALUES (?,?)",
                (decision.id, fid),
            )
        self._conn.execute(
            "INSERT OR IGNORE INTO staging VALUES (?,?)",
            ("decision", decision.id),
        )
        self._conn.commit()

    def get_decision(self, decision_id: str) -> Decision | None:
        """Retrieve a Decision by ID, or None if not found."""
        row = self._conn.execute("SELECT * FROM decisions WHERE id=?", (decision_id,)).fetchone()
        if row is None:
            return None
        fact_ids = [
            r[0]
            for r in self._conn.execute(
                "SELECT fact_id FROM decision_facts WHERE decision_id=?", (decision_id,)
            ).fetchall()
        ]
        d = Decision.from_dict(dict(row))
        d.fact_ids = fact_ids
        return d

    def list_decisions(self) -> list[Decision]:
        """Return all stored Decisions ordered by recorded_at."""
        rows = self._conn.execute("SELECT * FROM decisions ORDER BY recorded_at").fetchall()

        if not rows:
            return []

        # Batch fetch all fact IDs for these decisions in one query
        decision_ids = [r["id"] for r in rows]
        placeholders = ",".join("?" * len(decision_ids))
        # Placeholders are built from "?" * N — no injection risk
        df_sql = (
            "SELECT decision_id, fact_id FROM decision_facts "
            f"WHERE decision_id IN ({placeholders})"
        )
        fact_rows = self._conn.execute(df_sql, decision_ids).fetchall()

        # Group fact IDs by decision
        fact_map: dict[str, list[str]] = {r["id"]: [] for r in rows}
        for fr in fact_rows:
            fact_map[fr["decision_id"]].append(fr["fact_id"])

        result = []
        for row in rows:
            d = Decision.from_dict(dict(row))
            d.fact_ids = fact_map[d.id]
            result.append(d)
        return result

    def get_decisions_for_fact(self, fact_id: str) -> list[Decision]:
        """Return all Decisions that depend on a given Fact."""
        decision_id_rows = self._conn.execute(
            "SELECT decision_id FROM decision_facts WHERE fact_id=?", (fact_id,)
        ).fetchall()

        if not decision_id_rows:
            return []

        decision_ids = [r[0] for r in decision_id_rows]
        placeholders = ",".join("?" * len(decision_ids))

        # Batch fetch all decision rows in one query
        sql_dec = f"SELECT * FROM decisions WHERE id IN ({placeholders})"
        rows = self._conn.execute(sql_dec, decision_ids).fetchall()

        if not rows:
            return []

        # Batch fetch all fact IDs for these decisions in one query
        # Placeholders are built from "?" * N — no injection risk
        df2_sql = (
            "SELECT decision_id, fact_id FROM decision_facts "
            f"WHERE decision_id IN ({placeholders})"
        )
        fact_rows = self._conn.execute(df2_sql, decision_ids).fetchall()

        # Group fact IDs by decision
        fact_map: dict[str, list[str]] = {did: [] for did in decision_ids}
        for fr in fact_rows:
            fact_map[fr["decision_id"]].append(fr["fact_id"])

        decisions = []
        for row in rows:
            d = Decision.from_dict(dict(row))
            d.fact_ids = fact_map.get(d.id, [])
            decisions.append(d)
        return decisions

    # ── Commits ───────────────────────────────────────────────────────────────

    def retract_fact(self, fact_id: str) -> None:
        """Stage a fact retraction so it is excluded from the next commit snapshot."""
        self._conn.execute(
            "INSERT OR IGNORE INTO staging VALUES (?,?)",
            ("retraction", fact_id),
        )
        self._conn.commit()

    def commit(self, message: str) -> WorldCommit:
        """Create a new commit from staged facts and decisions."""
        staged_facts = {
            r[0] for r in self._conn.execute("SELECT id FROM staging WHERE type='fact'").fetchall()
        }
        staged_decisions = {
            r[0]
            for r in self._conn.execute("SELECT id FROM staging WHERE type='decision'").fetchall()
        }
        retracted_facts = {
            r[0]
            for r in self._conn.execute("SELECT id FROM staging WHERE type='retraction'").fetchall()
        }

        head_id = self._get_ref("HEAD")
        parent = self.get_commit(head_id) if head_id else None

        parent_fact_ids = parent.fact_ids if parent else set()
        parent_decision_ids = parent.decision_ids if parent else set()

        wc = WorldCommit(
            message=message,
            fact_ids=(parent_fact_ids | staged_facts) - retracted_facts,
            decision_ids=parent_decision_ids | staged_decisions,
            parent_id=head_id,
        )

        self._conn.execute(
            "INSERT OR IGNORE INTO commits VALUES (?,?,?,?)",
            (wc.id, wc.message, wc.parent_id, wc.timestamp),
        )
        for fid in wc.fact_ids:
            self._conn.execute("INSERT OR IGNORE INTO commit_facts VALUES (?,?)", (wc.id, fid))
        for did in wc.decision_ids:
            self._conn.execute("INSERT OR IGNORE INTO commit_decisions VALUES (?,?)", (wc.id, did))
        self._conn.execute("INSERT OR REPLACE INTO refs VALUES (?,?)", ("HEAD", wc.id))
        self._conn.execute("DELETE FROM staging")
        self._conn.commit()
        return wc

    def get_commit(self, commit_id: str) -> WorldCommit | None:
        """Retrieve a WorldCommit by ID, or None if not found."""
        row = self._conn.execute("SELECT * FROM commits WHERE id=?", (commit_id,)).fetchone()
        if row is None:
            return None
        fact_ids = {
            r[0]
            for r in self._conn.execute(
                "SELECT fact_id FROM commit_facts WHERE commit_id=?", (commit_id,)
            ).fetchall()
        }
        decision_ids = {
            r[0]
            for r in self._conn.execute(
                "SELECT decision_id FROM commit_decisions WHERE commit_id=?", (commit_id,)
            ).fetchall()
        }
        wc = WorldCommit.from_dict(dict(row))
        wc.fact_ids = fact_ids
        wc.decision_ids = decision_ids
        return wc

    def log(self) -> list[WorldCommit]:
        """Return all commits from HEAD to root, newest first."""
        head_id = self._get_ref("HEAD")
        if not head_id:
            return []
        commits: list[WorldCommit] = []
        current_id: str | None = head_id
        seen: set[str] = set()
        while current_id and current_id not in seen:
            seen.add(current_id)
            wc = self.get_commit(current_id)
            if wc is None:
                break
            commits.append(wc)
            current_id = wc.parent_id
        return commits

    def head(self) -> WorldCommit | None:
        """Return the HEAD commit, or None if the repo is empty."""
        head_id = self._get_ref("HEAD")
        return self.get_commit(head_id) if head_id else None

    def _get_ref(self, name: str) -> str | None:
        row = self._conn.execute("SELECT commit_id FROM refs WHERE name=?", (name,)).fetchone()
        return row[0] if row else None

    def staged_count(self) -> int:
        """Return number of staged (uncommitted) items."""
        row = self._conn.execute("SELECT COUNT(*) FROM staging").fetchone()
        return row[0] if row else 0
