# worldgit Architecture

This document is the authoritative developer reference for worldgit's internals. It covers the data flow, module responsibilities, key invariants, the SQLite schema, and the staleness propagation algorithm.

---

## Data Flow

```
┌─────────────┐     add_fact()      ┌──────────────┐
│    Agent    │ ──────────────────► │  WorldStore  │
│  (or CLI)   │     add_decision()  │  (SQLite)    │
└─────────────┘ ──────────────────► │              │
                                    │  staging     │
                    commit()        │  table       │
                ──────────────────► │              │
                                    │  facts       │
                                    │  decisions   │
                                    │  commits     │
                                    └──────────────┘
                                           │
                                    diff_commits()
                                           │
                                           ▼
                                    ┌──────────────┐
                                    │  DiffResult  │
                                    │  added_facts │
                                    │  removed_    │
                                    │  facts       │
                                    └──────────────┘
                                           │
                                   compute_staleness()
                                           │
                                           ▼
                                    ┌──────────────┐
                                    │ Staleness    │
                                    │ Alert[]      │
                                    │ (ranked by   │
                                    │ impact_score)│
                                    └──────────────┘
```

**Sequence:**

1. Agent calls `repo.add_fact(subject, predicate, obj)` — fact is inserted into `facts` table and `staging` table.
2. Agent calls `repo.decide(label, content, depends_on=[...fact_ids...])` — decision is inserted into `decisions` table + `decision_facts` join table + `staging`.
3. Agent calls `repo.commit(message)` — all staged IDs are collected, unioned with parent's fact/decision sets, and written as a new `WorldCommit` row. Staging table is cleared. `refs.HEAD` is updated.
4. Later, `repo.stale()` is called — `diff_commits()` computes `changed_fact_ids = added ∪ removed` between HEAD and its parent. `compute_staleness()` walks the dependency edges and emits `StalenessAlert` objects.

---

## Module Map

| File | Responsibility |
|------|---------------|
| `fact.py` | Core dataclasses: `Fact`, `Decision`, `StalenessAlert`. All content-addressed IDs are computed here via `_sha16()`. |
| `store.py` | SQLite persistence layer. `WorldStore` owns the database connection. `WorldCommit` is the snapshot dataclass. |
| `staleness.py` | Pure staleness logic. `diff_commits()` computes the fact delta; `compute_staleness()` propagates it through the decision graph. No I/O beyond reading from `WorldStore`. |
| `repo.py` | High-level API (`WorldRepo`). Thin wrapper that composes `WorldStore` + `staleness` module. This is the primary public interface. |
| `report.py` | Output formatters: `print_stale()` (Rich terminal), `print_diff()`, `print_log()`, `to_json()`, `to_markdown()`. |
| `cli.py` | Click CLI. Subcommands: `fact`, `decide`, `commit`, `stale`, `diff`, `log`, `status`. Reads `--db` from context. |
| `api.py` | FastAPI REST server. Endpoints mirror the CLI subcommands. Suitable for OpenAI function-calling integration. |
| `mcp_server.py` | Model Context Protocol server stub. Exposes worldgit tools to MCP-compatible agents (Claude, etc.). |

---

## Key Invariants

### 1. Fact.id is deterministic

```
Fact.id = SHA-256[:16]("{subject}|{predicate}|{object}")
```

The same triple always produces the same 16-character hex ID, regardless of `confidence` or `recorded_at`. This means:

- `add_fact()` is idempotent — inserting the same triple twice is a no-op (`INSERT OR IGNORE`).
- Two independent agents recording the same fact will refer to it by the same ID.
- Confidence changes do **not** create a new fact — confidence is metadata, not identity.

### 2. WorldCommit.id is deterministic

```
WorldCommit.id = SHA-256[:16](json.dumps({
    "message": ...,
    "fact_ids": sorted([...]),
    "decision_ids": sorted([...]),
    "parent_id": ...,
}, sort_keys=True))
```

Two commits with the same content always get the same ID. Timestamps are **not** included in the hash (they are stored separately).

### 3. Staging area is cleared on commit

`commit()` executes `DELETE FROM staging` after writing the commit row. The staging table never persists items across commits. If you call `commit()` twice in a row without staging anything, the second call raises `ValueError("Nothing to commit")`.

### 4. compute_staleness() is O(changed_facts × avg_decisions_per_fact)

For each changed fact, `compute_staleness()` queries `decision_facts` for all decisions that depend on it, then deduplicates via `seen_decision_ids`. Total work is proportional to the number of dependency edges that touch changed facts — not the total number of facts or decisions in the store.

### 5. WorldStore is thread-unsafe

`WorldStore` holds a single `sqlite3.Connection` that is **not** shared across threads. Use one `WorldStore` (and one `WorldRepo`) per process. For concurrent access, run separate processes with separate database files, or add an external lock.

---

## SQLite Schema

```sql
-- Content-addressed triple store
CREATE TABLE facts (
    id          TEXT PRIMARY KEY,   -- SHA-256[:16] of "subject|predicate|object"
    subject     TEXT NOT NULL,
    predicate   TEXT NOT NULL,
    object      TEXT NOT NULL,
    confidence  REAL NOT NULL DEFAULT 1.0,
    recorded_at REAL NOT NULL       -- Unix timestamp
);

-- Named agent conclusions
CREATE TABLE decisions (
    id          TEXT PRIMARY KEY,   -- SHA-256[:16] of "label|content"
    label       TEXT NOT NULL,      -- short slug
    content     TEXT NOT NULL,      -- full reasoning text
    recorded_at REAL NOT NULL
);

-- Dependency edges: decision → fact
CREATE TABLE decision_facts (
    decision_id TEXT NOT NULL,
    fact_id     TEXT NOT NULL,
    PRIMARY KEY (decision_id, fact_id)
);

-- Commit snapshots
CREATE TABLE commits (
    id          TEXT PRIMARY KEY,
    message     TEXT NOT NULL,
    parent_id   TEXT,               -- NULL for the initial commit
    timestamp   REAL NOT NULL
);

-- Commit → fact membership
CREATE TABLE commit_facts (
    commit_id   TEXT NOT NULL,
    fact_id     TEXT NOT NULL,
    PRIMARY KEY (commit_id, fact_id)
);

-- Commit → decision membership
CREATE TABLE commit_decisions (
    commit_id   TEXT NOT NULL,
    decision_id TEXT NOT NULL,
    PRIMARY KEY (commit_id, decision_id)
);

-- Named references (currently only HEAD)
CREATE TABLE refs (
    name        TEXT PRIMARY KEY,
    commit_id   TEXT NOT NULL
);

-- Items staged for the next commit
CREATE TABLE staging (
    type        TEXT NOT NULL,      -- 'fact' or 'decision'
    id          TEXT NOT NULL,
    PRIMARY KEY (type, id)
);
```

**Notes:**
- `commit_facts` and `commit_decisions` store the *cumulative* fact/decision sets (parent ∪ staged), not just the delta. This makes `get_commit()` O(1) without requiring traversal.
- `decision_facts` is the critical dependency graph. `get_decisions_for_fact(fact_id)` is a direct index scan on this table.
- All foreign key relationships are logical (not enforced by SQLite) for simplicity — worldgit's Python layer maintains integrity.

---

## Staleness Propagation Algorithm

```python
def compute_staleness(store, changed_fact_ids):
    if not changed_fact_ids:
        return []

    seen_decision_ids = set()
    alerts = []

    for fact_id in changed_fact_ids:
        # O(edges touching fact_id)
        decisions = store.get_decisions_for_fact(fact_id)

        for decision in decisions:
            if decision.id in seen_decision_ids:
                continue          # already processed this decision
            seen_decision_ids.add(decision.id)

            # Which of this decision's facts are in the changed set?
            stale_ids = [fid for fid in decision.fact_ids if fid in changed_fact_ids]
            if not stale_ids:
                continue

            # Impact = mean confidence of the now-stale facts
            confidences = [store.get_fact(fid).confidence for fid in stale_ids]
            impact = mean(confidences)

            alerts.append(StalenessAlert(
                decision_id=decision.id,
                decision_label=decision.label,
                stale_fact_ids=stale_ids,
                impact_score=impact,
            ))

    # Sort highest impact first
    alerts.sort(key=lambda a: a.impact_score, reverse=True)
    return alerts
```

**Why mean confidence?**

If a decision depended on 3 facts and 2 of them changed, the impact score reflects how confident the agent was in those 2 facts. A fact with `confidence=1.0` changing is more impactful than one with `confidence=0.3` changing. Using the mean (rather than max or sum) keeps the score in [0.0, 1.0] and treats each stale fact equally regardless of how many total facts the decision had.

**Edge case: fact is in `changed_fact_ids` but not in the `facts` table**

This happens when a fact was *removed* (it existed in `commit_a` but not `commit_b`). `store.get_fact(fid)` returns `None`. In this case, the confidence is omitted from the mean calculation, and if all stale facts are missing, `impact` defaults to `0.5`. This is intentional: we still alert, but with a neutral score, because we no longer have the confidence metadata.

---

## Extension Points

- **Custom confidence models** — subclass `Fact` and override `__post_init__` to derive confidence from external signals.
- **Async store** — replace `WorldStore` with an async SQLite adapter (e.g. `aiosqlite`) for use in async agent frameworks.
- **Remote store** — implement the same `add_fact` / `get_fact` / `commit` interface against a remote database (Postgres, DynamoDB) for multi-agent scenarios.
- **Webhooks** — call `compute_staleness()` in a background thread and POST alerts to a webhook URL whenever a new commit is created.
