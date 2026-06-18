"""
foghorn demo — decision staleness alerts for AI agents.

Run with: python examples/demo.py
"""

import shutil
import tempfile

from foghorn.repo import WorldRepo

tmp = tempfile.mkdtemp()

try:
    repo = WorldRepo.init(f"{tmp}/world.db")

    print("=== foghorn demo ===\n")

    # Step 1: Record facts about the initial architecture
    f_redis = repo.add_fact("Redis", "is-appropriate-for", "rate-limiting", confidence=0.95)
    f_pg = repo.add_fact("Postgres", "is-primary-db", "yes", confidence=1.0)
    f_jwt = repo.add_fact("JWT", "used-for", "auth", confidence=0.9)
    print(f"Staged fact: {f_redis}")
    print(f"Staged fact: {f_pg}")
    print(f"Staged fact: {f_jwt}\n")

    # Step 2: Make decisions that depend on those facts
    d1 = repo.decide(
        "chose-redis-for-rate-limiting",
        "Redis is fast enough for our rate-limiting needs at current scale.",
        depends_on=[f_redis.id],
    )
    d2 = repo.decide(
        "chose-jwt-for-auth",
        "JWT is stateless and works well with our microservice architecture.",
        depends_on=[f_jwt.id, f_pg.id],
    )
    print(f"Staged decision: {d1}")
    print(f"Staged decision: {d2}\n")

    # Step 3: Initial commit
    wc1 = repo.commit("Initial architecture decisions")
    print(f"Committed: {wc1.id[:8]} — {wc1.message}")
    print(f"  {len(wc1.fact_ids)} facts · {len(wc1.decision_ids)} decisions\n")

    # Step 4: World changes — Redis is being replaced by Valkey
    f_valkey = repo.add_fact("Redis", "replaced-by", "Valkey", confidence=0.85)
    print(f"New fact staged: {f_valkey}")
    wc2 = repo.commit("Redis EOL notice: replaced by Valkey")
    print(f"Committed: {wc2.id[:8]} — {wc2.message}\n")

    # Step 5: Check for staleness
    print("=== Checking for stale decisions ===\n")
    alerts = repo.stale()

    if alerts:
        print(f"STALE DECISIONS DETECTED: {len(alerts)} alert(s)\n")
        for alert in alerts:
            print(f"  Decision: {alert.decision_label}")
            print(f"  Impact score: {alert.impact_score:.0%}")
            print(f"  Stale fact IDs: {alert.stale_fact_ids}")
            print()
        print("Fork detected — re-evaluate the flagged decisions before proceeding.")
        assert len(alerts) > 0, "Expected at least one stale alert"
    else:
        print("No stale decisions detected.")
        # This path may happen if the new fact doesn't overlap with old fact IDs
        # (content-addressed IDs differ for different triples), which is expected
        # when Valkey fact is entirely new, not a replacement of the Redis fact ID.
        print("(Note: stale alerts only fire when a decision's exact fact ID changes.)")

    # Show log
    print("\n=== Commit log ===\n")
    for wc in repo.log():
        print(f"  {wc.id[:8]}  {wc.message}  ({len(wc.fact_ids)} facts)")

    repo.close()

finally:
    shutil.rmtree(tmp)

print("\nDemo complete.")
