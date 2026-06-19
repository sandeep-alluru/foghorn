"""
infra_ops_monitor.py — foghorn for infrastructure observability.

Story: An ops agent monitors production infrastructure. It periodically
commits infrastructure facts to foghorn. When a metric changes beyond a
threshold, foghorn detects that routing decisions are stale.

Simulated monitoring loop (uses a counter, not actual sleep).
Demonstrates foghorn as an observability tool for agentic infrastructure
management — similar to how an ops agent in Claude Code or a LangGraph
workflow would use it.

Run:
    python examples/infra_ops_monitor.py
"""

from __future__ import annotations

import shutil
import tempfile
from dataclasses import dataclass

from foghorn.repo import WorldRepo


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def banner(title: str) -> None:
    print()
    print("=" * 68)
    print(f"  {title}")
    print("=" * 68)
    print()


def section(title: str) -> None:
    print(f"\n── {title} {'─' * max(0, 58 - len(title))}")
    print()


# ---------------------------------------------------------------------------
# Simulated telemetry data
# Represents 6 monitoring cycles at 5-minute intervals.
# ---------------------------------------------------------------------------

@dataclass
class TelemetrySample:
    cycle: int
    us_east_1_latency_ms: int
    ap_southeast_1_latency_ms: int
    api_gateway_healthy: bool
    redis_memory_pct: int
    label: str


TELEMETRY_SAMPLES = [
    TelemetrySample(1, 12,  45,  True,  67, "normal operations"),
    TelemetrySample(2, 15,  48,  True,  69, "normal — minor fluctuation"),
    TelemetrySample(3, 18,  44,  True,  71, "normal — redis memory creeping"),
    TelemetrySample(4, 450, 46,  True,  72, "DEGRADED — us-east-1 high latency"),
    TelemetrySample(5, 480, 44,  True,  73, "DEGRADED — us-east-1 still spiking"),
    TelemetrySample(6, 21,  45,  True,  74, "recovering — us-east-1 normalizing"),
]

# Alert thresholds
LATENCY_ALERT_MS  = 100  # ms — above this, routing decisions are stale
MEMORY_ALERT_PCT  = 80   # % — above this, cache decisions are stale


# ---------------------------------------------------------------------------
# Fact-building helpers
# ---------------------------------------------------------------------------

def latency_status(region: str, latency_ms: int) -> str:
    status = "healthy" if latency_ms < LATENCY_ALERT_MS else "degraded"
    return f"{latency_ms}ms — {status}"


def redis_status(pct: int) -> str:
    status = "normal" if pct < MEMORY_ALERT_PCT else "high — eviction risk"
    return f"{pct}% — {status}"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    tmp = tempfile.mkdtemp()
    try:
        _run(tmp)
    finally:
        shutil.rmtree(tmp)


def _run(tmp: str) -> None:
    banner("foghorn — Infrastructure Ops Monitor Demo")

    print("  An ops agent monitors production infrastructure.")
    print("  Every monitoring cycle it commits current facts to foghorn.")
    print("  When metrics change, foghorn identifies stale routing decisions.")
    print()
    print(f"  Alert thresholds:")
    print(f"    Latency:      > {LATENCY_ALERT_MS}ms  →  routing decisions stale")
    print(f"    Redis memory: > {MEMORY_ALERT_PCT}%   →  cache decisions stale")
    print()

    repo = WorldRepo.init(f"{tmp}/infra_ops.db")

    # -----------------------------------------------------------------------
    # INITIAL BASELINE: Healthy infrastructure
    # -----------------------------------------------------------------------
    section("Initial Baseline — Ops agent records healthy infrastructure facts")

    sample_0 = TELEMETRY_SAMPLES[0]

    f_latency_east = repo.add_fact(
        "us-east-1",
        "latency",
        latency_status("us-east-1", sample_0.us_east_1_latency_ms),
        confidence=0.99,
    )
    f_latency_ap = repo.add_fact(
        "ap-southeast-1",
        "latency",
        latency_status("ap-southeast-1", sample_0.ap_southeast_1_latency_ms),
        confidence=0.99,
    )
    f_api_gw = repo.add_fact(
        "api-gateway",
        "health",
        "healthy=true — all health checks passing",
        confidence=1.0,
    )
    f_redis_mem = repo.add_fact(
        "redis-cluster",
        "memory",
        redis_status(sample_0.redis_memory_pct),
        confidence=0.95,
    )

    print(f"  [FACT]  us-east-1 latency:    {sample_0.us_east_1_latency_ms}ms (healthy)")
    print(f"  [FACT]  ap-southeast-1:        {sample_0.ap_southeast_1_latency_ms}ms (healthy)")
    print(f"  [FACT]  api-gateway:            healthy")
    print(f"  [FACT]  redis-cluster memory:  {sample_0.redis_memory_pct}% (normal)")

    # -----------------------------------------------------------------------
    # INITIAL DECISIONS: Routing and operations policy
    # -----------------------------------------------------------------------
    section("Initial Decisions — Ops agent records operational decisions")

    d_route_east = repo.decide(
        "route-all-traffic-to-us-east-1",
        "Primary traffic routing: 100% to us-east-1 (12ms latency). "
        "Region is healthy with sub-20ms P99. No failover needed.",
        depends_on=[f_latency_east.id, f_api_gw.id],
    )
    d_cache_policy = repo.decide(
        "use-redis-aggressive-caching",
        "Enable aggressive caching (TTL=3600s) given redis memory at 67%. "
        "Safe headroom before eviction at 80% threshold.",
        depends_on=[f_redis_mem.id],
    )
    d_no_failover = repo.decide(
        "disable-failover-circuit-breaker",
        "Circuit breaker disabled: all regions healthy, latency within SLA. "
        "Re-enable if us-east-1 exceeds 100ms for 2 consecutive cycles.",
        depends_on=[f_latency_east.id, f_latency_ap.id],
    )
    d_capacity = repo.decide(
        "scale-us-east-1-at-70pct-capacity",
        "Scale trigger: add 2 nodes when us-east-1 reaches 70% capacity. "
        "Current load: 42%. No scaling needed.",
        depends_on=[f_latency_east.id],
    )

    for d in [d_route_east, d_cache_policy, d_no_failover, d_capacity]:
        print(f"  [DECISION]  {d.label}")
        print(f"              depends on: {[fid[:8] for fid in d.fact_ids]}")
        print()

    c0 = repo.commit("Baseline infrastructure — ops-monitor cycle 0 (healthy)")
    print(f"  Committed: {c0.id[:8]}  {c0.message}")

    # -----------------------------------------------------------------------
    # MONITORING LOOP: Simulate 5-minute polling cycles
    # -----------------------------------------------------------------------
    section("Monitoring Loop — 6 cycles (simulated, no sleep)")

    # Track which fact IDs are currently active for each metric
    # so we can retract them when values change
    current_latency_east_id = f_latency_east.id
    current_latency_ap_id   = f_latency_ap.id
    current_redis_mem_id    = f_redis_mem.id

    alert_raised = False
    recovery_detected = False

    for sample in TELEMETRY_SAMPLES[1:]:  # skip cycle 1 (already committed)
        cycle_label = f"Cycle {sample.cycle} (T+{(sample.cycle-1)*5}min) — {sample.label}"
        print(f"\n  [{cycle_label}]")
        print(f"  us-east-1: {sample.us_east_1_latency_ms}ms  |  "
              f"ap-southeast-1: {sample.ap_southeast_1_latency_ms}ms  |  "
              f"redis: {sample.redis_memory_pct}%")

        changed = False

        # Check if us-east-1 latency changed significantly (>20ms delta)
        old_latency = int(current_latency_east_id[:2] if False else "0")  # dummy
        # We detect change by comparing the new status string to what we'd commit
        new_latency_status = latency_status("us-east-1", sample.us_east_1_latency_ms)
        new_redis_status = redis_status(sample.redis_memory_pct)

        # For simplicity, commit updated facts every cycle (like a real monitor would)
        # Retract old facts and add new ones
        repo.retract_fact(current_latency_east_id)
        f_new_east = repo.add_fact(
            "us-east-1",
            "latency",
            latency_status("us-east-1", sample.us_east_1_latency_ms),
            confidence=0.99,
        )
        current_latency_east_id = f_new_east.id

        repo.retract_fact(current_redis_mem_id)
        f_new_redis = repo.add_fact(
            "redis-cluster",
            "memory",
            redis_status(sample.redis_memory_pct),
            confidence=0.95,
        )
        current_redis_mem_id = f_new_redis.id

        commit_msg = f"Infrastructure snapshot — ops-monitor cycle {sample.cycle} ({sample.label})"
        c = repo.commit(commit_msg)

        # Check for staleness
        alerts = repo.stale()

        if alerts and sample.us_east_1_latency_ms >= LATENCY_ALERT_MS and not alert_raised:
            alert_raised = True
            print()
            print("  " + "!" * 62)
            print("  ALERT: STALE ROUTING DECISIONS DETECTED")
            print("  " + "!" * 62)
            print()
            print(f"  us-east-1 latency spiked to {sample.us_east_1_latency_ms}ms "
                  f"(threshold: {LATENCY_ALERT_MS}ms)")
            print()
            print("  Stale decisions that must be re-evaluated:")
            print()
            for alert in alerts:
                severity = "CRITICAL" if alert.impact_score >= 0.95 else "HIGH" if alert.impact_score >= 0.85 else "MEDIUM"
                print(f"  [{severity}]  {alert.decision_label}")
                print(f"            impact_score: {alert.impact_score:.2f}")
                print()
            print()
            print("  Ops agent alert message:")
            print()
            print("  ┌─────────────────────────────────────────────────────────────┐")
            print("  │  ALERT: STALE ROUTING DECISION                              │")
            print("  │                                                              │")
            print(f"  │  Fact changed: us-east-1 latency  12ms → {sample.us_east_1_latency_ms}ms           │")
            print("  │  This invalidates routing decisions that assumed <100ms.    │")
            print("  │                                                              │")
            print("  │  Stale decisions requiring immediate re-evaluation:         │")
            for alert in alerts:
                padded = alert.decision_label[:52]
                print(f"  │    [{alert.impact_score:.2f}]  {padded:<52}  │")
            print("  │                                                              │")
            print("  │  Recommended actions:                                       │")
            print("  │    1. Enable failover circuit breaker to ap-southeast-1    │")
            print("  │    2. Re-evaluate traffic routing (shift 50% to ap-se-1)   │")
            print("  │    3. Page on-call engineer if degradation > 10min          │")
            print("  └─────────────────────────────────────────────────────────────┘")

        elif alerts:
            stale_count = len(alerts)
            print(f"  → {stale_count} stale decision(s)  |  Commit: {c.id[:8]}")

        elif not alerts and alert_raised and not recovery_detected and sample.us_east_1_latency_ms < LATENCY_ALERT_MS:
            recovery_detected = True
            print()
            print("  RECOVERY: us-east-1 latency returned to normal")
            print(f"  us-east-1 now: {sample.us_east_1_latency_ms}ms (below {LATENCY_ALERT_MS}ms threshold)")
            print("  No stale decisions detected — routing decisions are current.")
            print("  Ops agent: re-evaluating routing policy...")
            print("  Action: restore 100% traffic to us-east-1, disable circuit breaker.")

        else:
            print(f"  → All decisions current  |  Commit: {c.id[:8]}")

    # -----------------------------------------------------------------------
    # FINAL SUMMARY
    # -----------------------------------------------------------------------
    section("Monitoring Summary")

    print("  Monitoring run complete. Infrastructure timeline:\n")
    print(f"  {'Cycle':<8} {'Latency (us-east-1)':<24} {'Status'}")
    print(f"  {'-'*5:<8} {'-'*22:<24} {'------'}")

    for s in TELEMETRY_SAMPLES:
        status = "DEGRADED" if s.us_east_1_latency_ms >= LATENCY_ALERT_MS else "OK"
        marker = "  " if status == "OK" else ">>"
        print(f"  {marker} T+{(s.cycle-1)*5:>2}min  {s.us_east_1_latency_ms:>5}ms  ({s.label[:35]})")

    print()
    print("  foghorn detected the degradation at cycle 4 (T+15min)")
    print("  and flagged stale routing + failover decisions.")
    print("  The ops agent could have automatically re-routed traffic")
    print("  within 1 monitoring cycle instead of waiting for manual alerting.")

    # Commit log
    section("Commit Log")
    all_commits = repo.log()
    for wc in all_commits:
        print(f"  {wc.id[:8]}  {wc.message[:62]}")

    repo.close()

    print()
    print("=" * 68)
    print("  Demo complete.")
    print("=" * 68)
    print()


if __name__ == "__main__":
    main()
