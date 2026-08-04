# Closed loop — `foghorn`

**Status:** reader wired (eagle-eyes / 2026-08-04)  
**Owner loop:** L6

## Load-bearing job

Fact→decision dependency staleness alerts

## Who reads the output?

- Library API: `foghorn.gate_staleness` / `assert_fresh` (`closed_loop.py`)
- Pipeline or Jarvis L6 reads `StalenessAlert` before re-using a decision
- CLI: `foghorn stale --exit-code`

## What outcome changes?

Skip reuse / force recompute when impact high; empty world or LWW misuse → FAIL_LOUD

## When NOT to use (anti-ornament)

NEVER use as LWW episode/current-state store (D-FOGHORN: oldest-fact next() wiped frames)

## Non-Ornament checklist

- [x] Reader implemented in CI, gate, or eagle-eyes script (`gate_staleness` + tests)
- [x] Empty/wrong output fails loudly (`FAIL_LOUD`, exit 2)
- [x] Not exposed as free MCP in product agents (import/CI gate only)
- [x] Linked gap IDs in mem0 when improving (D-FOGHORN regression + mode guard)

## Related failures (farm memory)

- 2026-07-22 MCP buffet trim: write-only tools removed from Foundry framework
- D-FOGHORN: misuse of append-only fact log as current state
- Dual-path mem0: never rely on MCP-only for critical memory

## Daily rotation note

Prefer small daily commits that raise scorer pillars or finish remaining wiring (CI job invoking gate).

## Auto-run 2026-08-04
- pytest_rc: 0
- node: clawer-samurai-2

## Auto-run 2026-08-04
- pytest_rc: 0
- node: clawer-samurai-2
