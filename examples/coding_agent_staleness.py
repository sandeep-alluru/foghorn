"""
coding_agent_staleness.py — foghorn for coding agent decision tracking.

Story: A coding agent made 8 architecture decisions while building a SaaS app.
When security advisories arrive, foghorn identifies which decisions are stale
and notifies the agent before its next coding session.

foghorn's staleness model: decisions depend on Fact IDs (content-addressed).
When a fact is retracted and replaced, decisions that depended on the old fact
ID are stale.

This simulates how Claude Code / Cursor could integrate foghorn to warn AI
agents that their architectural assumptions are out of date.

Run:
    python examples/coding_agent_staleness.py
"""

from __future__ import annotations

import shutil
import tempfile
from datetime import datetime

from foghorn.repo import WorldRepo


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def banner(title: str) -> None:
    width = 66
    print()
    print("=" * width)
    print(f"  {title}")
    print("=" * width)
    print()


def section(title: str) -> None:
    print(f"\n── {title} {'─' * max(0, 58 - len(title))}")
    print()


# ---------------------------------------------------------------------------
# Main simulation
# ---------------------------------------------------------------------------

def main() -> None:
    tmp = tempfile.mkdtemp()
    try:
        _run(tmp)
    finally:
        shutil.rmtree(tmp)


def _run(tmp: str) -> None:
    banner("foghorn — Coding Agent Decision Staleness Demo")

    print("  Scenario: A coding agent built a SaaS app in Sprint 1.")
    print("  Security advisories changed two technology facts.")
    print("  foghorn detects which architecture decisions are now stale.")
    print()

    repo = WorldRepo.init(f"{tmp}/saas_project.db")

    # -----------------------------------------------------------------------
    # SPRINT 1: Agent records facts about the technology landscape
    # -----------------------------------------------------------------------
    section("Sprint 1 — Agent records architecture facts")

    # Technology facts the agent researched before making decisions.
    # Each fact is content-addressed: same subject+predicate+object → same ID.
    f_node = repo.add_fact(
        "Node.js 18",
        "status",
        "LTS — supported until 2025-04-30",
        confidence=0.99,
    )
    f_redis = repo.add_fact(
        "Redis 7",
        "license",
        "BSD — open source, production ready",
        confidence=0.97,
    )
    f_pg = repo.add_fact(
        "PostgreSQL 15",
        "status",
        "stable LTS — recommended for production",
        confidence=1.0,
    )
    f_jwt = repo.add_fact(
        "JWT (HS256)",
        "security-posture",
        "acceptable for stateless auth with proper expiry",
        confidence=0.90,
    )
    f_docker = repo.add_fact(
        "Docker 24",
        "status",
        "stable — standard container runtime",
        confidence=0.98,
    )

    for f in [f_node, f_redis, f_pg, f_jwt, f_docker]:
        print(f"  [FACT]  {f.id[:8]}  {f.subject:<22} → {f.object[:40]}")

    # -----------------------------------------------------------------------
    # Sprint 1: Agent records 8 decisions depending on those facts
    # -----------------------------------------------------------------------
    section("Sprint 1 — Agent records 8 architecture decisions")

    d_node = repo.decide(
        "chose-nodejs-18",
        "Node.js 18 LTS selected for backend. Active LTS with security "
        "patches guaranteed through 2025. Ecosystem maturity and team "
        "familiarity justify this choice.",
        depends_on=[f_node.id],
    )
    d_redis_sessions = repo.decide(
        "chose-redis-sessions",
        "Redis 7 selected for session storage. BSD license allows commercial "
        "use without restriction. Sub-millisecond reads critical for auth flow.",
        depends_on=[f_redis.id],
    )
    d_redis_cache = repo.decide(
        "chose-redis-cache",
        "Redis 7 for API response cache layer. BSD license and sub-millisecond "
        "performance ideal for our cache tier.",
        depends_on=[f_redis.id],
    )
    d_pg = repo.decide(
        "chose-pg15-primary",
        "PostgreSQL 15 as primary database. Stable LTS, mature JSONB support, "
        "existing team expertise. No migration risk.",
        depends_on=[f_pg.id],
    )
    d_jwt = repo.decide(
        "chose-jwt-stateless",
        "JWT HS256 for stateless authentication. Avoids session DB lookups. "
        "15-minute expiry with refresh token rotation.",
        depends_on=[f_jwt.id],
    )
    d_docker = repo.decide(
        "chose-docker-deployment",
        "Docker 24 for all service containers. Industry standard, CI/CD "
        "integration mature.",
        depends_on=[f_docker.id],
    )
    d_node_dockerfile = repo.decide(
        "pin-node-18-in-dockerfile",
        "Dockerfile uses FROM node:18-alpine. Pinned to Node.js 18 to match "
        "local dev environment and LTS commitment.",
        depends_on=[f_node.id],
    )
    d_redis_ratelimit = repo.decide(
        "chose-redis-rate-limiting",
        "Redis 7 sliding window rate limiter for API endpoints. BSD license "
        "allows this commercial use. Atomic INCR ensures correctness.",
        depends_on=[f_redis.id],
    )

    for d in [d_node, d_redis_sessions, d_redis_cache, d_pg, d_jwt,
              d_docker, d_node_dockerfile, d_redis_ratelimit]:
        print(f"  [DECISION]  {d.label}")

    # Commit Sprint 1
    c1 = repo.commit("Initial architecture — Sprint 1")
    print()
    print(f"  Committed: {c1.id[:8]}  ({len(c1.fact_ids)} facts · {len(c1.decision_ids)} decisions)")
    print(f"  Message:   {c1.message}")

    # -----------------------------------------------------------------------
    # SECURITY ADVISORY: World changes in 2026-Q2
    # -----------------------------------------------------------------------
    section("2026-Q2 Security Advisory — World state changes")

    print("  Two critical advisories arrived today:")
    print()

    # Advisory 1: Node.js 18 EOL.
    # We retract the old fact and add the updated one.
    # Decisions that depended on the old f_node.id will now be stale.
    repo.retract_fact(f_node.id)
    f_node_eol = repo.add_fact(
        "Node.js 18",
        "status",
        "EOL as of 2025-04-30 — upgrade to Node.js 22 LTS immediately",
        confidence=1.0,
    )
    print(f"  [ADVISORY-1] Node.js 18 reached End of Life.")
    print(f"               Old fact ID: {f_node.id[:8]}  (retracted)")
    print(f"               New fact ID: {f_node_eol.id[:8]}  (staged)")
    print(f"               Recommended: upgrade to Node.js 22 LTS.")
    print()

    # Advisory 2: Redis BSL license change.
    repo.retract_fact(f_redis.id)
    f_redis_bsl = repo.add_fact(
        "Redis 7",
        "license",
        "BSL 1.1 — commercial SaaS use requires paid license (evaluate Valkey/KeyDB)",
        confidence=0.95,
    )
    print(f"  [ADVISORY-2] Redis 7 license changed to Business Source License (BSL).")
    print(f"               Old fact ID: {f_redis.id[:8]}  (retracted)")
    print(f"               New fact ID: {f_redis_bsl.id[:8]}  (staged)")
    print(f"               Alternatives: Valkey (Linux Foundation), KeyDB (Snap).")
    print()

    c2 = repo.commit("Security advisory updates — 2026-Q2")
    print(f"  Committed: {c2.id[:8]}  ({len(c2.fact_ids)} facts · {len(c2.decision_ids)} decisions)")
    print(f"  Message:   {c2.message}")

    # -----------------------------------------------------------------------
    # STALENESS CHECK: Which decisions are now invalid?
    # -----------------------------------------------------------------------
    section("Staleness Check — Identifying affected decisions")

    alerts = repo.stale()

    if not alerts:
        # Should not happen with proper retract_fact usage
        print("  No stale decisions detected.")
    else:
        print(f"  {len(alerts)} decision(s) are now stale:\n")
        for alert in alerts:
            severity = (
                "HIGH  " if alert.impact_score >= 0.90
                else "MEDIUM" if alert.impact_score >= 0.75
                else "LOW   "
            )
            print(f"  [{severity}] {alert.decision_label}")
            print(f"             impact_score: {alert.impact_score:.2f}")
            print()

    # -----------------------------------------------------------------------
    # AGENT NOTIFICATION: What the coding agent sees at session start
    # -----------------------------------------------------------------------
    section("Agent Notification — Pre-session staleness brief")

    print("  ┌─────────────────────────────────────────────────────────────┐")
    print("  │  foghorn — Pre-Session Staleness Alert                      │")
    print("  │  Project: saas-backend  |  2026-Q2 Security Review         │")
    print("  └─────────────────────────────────────────────────────────────┘")
    print()

    if alerts:
        print(f"  WARNING: {len(alerts)} architecture decision(s) are stale.")
        print("  Review before proceeding with Sprint 2 tasks:\n")
        for alert in sorted(alerts, key=lambda a: -a.impact_score):
            print(f"    [{alert.impact_score:.2f}]  {alert.decision_label}")

        # Identify which facts changed and summarize the impact
        node_alerts = [a for a in alerts if f_node.id in a.stale_fact_ids]
        redis_alerts = [a for a in alerts if f_redis.id in a.stale_fact_ids]

        print()
        print(f"  Decisions affected by Node.js EOL: {len(node_alerts)}")
        for a in node_alerts:
            print(f"    - {a.decision_label}")

        print()
        print(f"  Decisions affected by Redis BSL change: {len(redis_alerts)}")
        for a in redis_alerts:
            print(f"    - {a.decision_label}")
    else:
        print("  All decisions are current. Proceed with Sprint 2.")

    print()
    print("  Unaffected decisions (still valid):")
    stale_labels = {a.decision_label for a in alerts}
    all_labels = [
        "chose-pg15-primary",
        "chose-jwt-stateless",
        "chose-docker-deployment",
        "chose-nodejs-18",
        "chose-redis-sessions",
        "chose-redis-cache",
        "pin-node-18-in-dockerfile",
        "chose-redis-rate-limiting",
    ]
    valid = [lbl for lbl in all_labels if lbl not in stale_labels]
    for lbl in valid:
        print(f"    [OK]  {lbl}")

    print()
    print("  Next steps:")
    print("  1. Run: foghorn stale  # in your project directory")
    print("  2. Upgrade Node.js: update Dockerfile FROM node:22-alpine")
    print("  3. Evaluate Valkey vs Redis licensing costs")
    print("  4. After decisions are revisited, commit updated facts to foghorn")

    # -----------------------------------------------------------------------
    # Show commit log
    # -----------------------------------------------------------------------
    section("Commit Log")

    for wc in repo.log():
        ts = datetime.fromtimestamp(wc.timestamp).strftime("%Y-%m-%d %H:%M")
        print(f"  {wc.id[:8]}  {ts}  {wc.message}")
        print(f"             {len(wc.fact_ids)} facts  •  {len(wc.decision_ids)} decisions")
        print()

    repo.close()

    print("=" * 66)
    print("  Demo complete.")
    print("=" * 66)
    print()


if __name__ == "__main__":
    main()
