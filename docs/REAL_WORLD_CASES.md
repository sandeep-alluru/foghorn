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

## Related farm lessons
- Writer fixed without tracing readers (cache key bugs)
- Silent success / vacuous guards
- MCP write-only tools are ornaments
