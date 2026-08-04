# Closed loop — `foghorn`

**Status:** stub (eagle-eyes Phase 0 / 2026-08-04)  
**Owner loop:** L6

## Load-bearing job

Fact→decision dependency staleness alerts

## Who reads the output?

Pipeline or Jarvis L6 reads StalenessAlert before re-using a decision

## What outcome changes?

Skip reuse / force recompute when impact high

## When NOT to use (anti-ornament)

NEVER use as LWW episode/current-state store (D-FOGHORN: oldest-fact next() wiped frames)

## Non-Ornament checklist

- [ ] Reader implemented in CI, gate, or eagle-eyes script
- [ ] Empty/wrong output fails loudly
- [ ] Not exposed as free MCP in product agents
- [ ] Linked gap IDs in mem0 when improving

## Related failures (farm memory)

- 2026-07-22 MCP buffet trim: write-only tools removed from Foundry framework
- D-FOGHORN: misuse of append-only fact log as current state
- Dual-path mem0: never rely on MCP-only for critical memory

## Daily rotation note

This file exists so pillar **C (closed loop)** can rise with real wiring over time. Prefer small daily commits that move a checkbox toward done.

## Auto-run 2026-08-04
- pytest_rc: 0
- node: clawer-samurai-2

## Auto-run 2026-08-04
- pytest_rc: 0
- node: clawer-samurai-2
