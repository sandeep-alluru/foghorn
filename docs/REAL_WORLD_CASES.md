# Real-world cases driving foghorn

Mined from farm_memory (Qdrant) and Pioneer Content Foundry production.

## Case D-FOGHORN (2026-07-22) — CRITICAL

**Source:** Qdrant `farm_memory`, category=failure, project=pioneer-content-foundry

**What failed:** Pipeline modules treated foghorn's append-only fact log as a
last-write-wins current-state store. They called `list_facts()` (ordered by
`recorded_at` ascending) and took `next(...)` / first element → **oldest**
value of `script` hash. Every run saw `script_changed=True` → wiped all episode
frame directories → ~**95 minutes** full recapture.

**Root cause:** Missing API for "latest fact for (subject, predicate)". Integrators
improvised with history scan in the wrong direction.

**Product fix in this repo:**
- `WorldStore.latest_fact(subject, predicate)`
- `WorldStore.list_facts_for(subject, predicate=None)`
- `WorldStore.current_fact_map()`
- Docstring on `list_facts` with D-FOGHORN warning
- Tests: `test_latest_fact_not_oldest`, `test_list_facts_oldest_first_not_current_state`
- Closed-loop: `gate_staleness(mode=current_state)` → FAIL_LOUD

**Non-Ornament:** A reader that changes outcome = use `latest_fact` / refuse
`mode=current_state` on the raw log.

## Case STALE-WIKI — Amazon Q expired documentation grounding

**Source:** eagle-eyes matrix public corpus was **partial** (staleness gates
existed; no Amazon Q incident fixture) + Track B `20260807T121230Z` foghorn
deep-dive suggestions (AgentExecutor / retrieval-grounded agents).

**What fails:**

1. Agents ground answers on internal wiki / docs facts that are **unchanged**
   for weeks — `gate_staleness` does not fire (no fact-id churn under a decision).
2. Wall-clock age of the retrieval is never checked; consumers treat old
   `wiki_source` triples as current.
3. Oldest-first log rows can make age checks look at the wrong generation
   without D-FOGHORN latest-per-key discipline.

**Product in this repo:**

| Control | API |
|---------|-----|
| Predicate classifier | `is_source_predicate` / `DEFAULT_SOURCE_PREDICATES` |
| Age gate | `gate_source_freshness(..., max_age_seconds=7d)` |
| Latest-only | `use_latest_only=True` (D-FOGHORN key collapse) |
| Raise form | `assert_sources_fresh(...)` |
| Empty inventory | `require_source_facts` → FAIL_LOUD |

**Rules (load-bearing):**

- No wiki/doc source facts when required → **FAIL_LOUD**
- Any source fact age > max → **FAIL** (`human_required` re-retrieve)
- Fresh sources → **PASS**

**Tests:** `tests/test_source_freshness.py` — Amazon Q 30-day fixture.

**Non-Ornament:** Call `gate_source_freshness` **before** answering from
retrieved wiki/docs. Pair with `gate_staleness` for decision-edge churn.
Age gate is not optional if the agent cites docs.

## Related farm lessons
- Writer fixed without tracing readers (cache key bugs)
- Silent success / vacuous guards
- MCP write-only tools are ornaments
- Amazon Q stale wiki — wall-clock source age (this section)
