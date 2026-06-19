# Case Study: Preventing Stale Architecture Decisions in a Coding Assistant

## Company Profile

**StackForge** is a developer tools company based in San Francisco, CA. With 45 engineers, they build a Claude-powered coding assistant used by over 12,000 developers across 300+ enterprise customers. Their product is positioned as a "senior engineer co-pilot" — it makes architecture decisions, not just autocomplete suggestions. Their stack is Python/FastAPI on the backend, React on the frontend, with a PostgreSQL knowledge base for enterprise-specific context.

## The Problem

StackForge's coding assistant makes architecture decisions when initializing new projects. In January 2025, it confidently recommended Redis for caching (appropriate for their enterprise customers' typical use case) and Node 18 LTS as the runtime for a new microservice. The agent recorded these decisions and moved on.

Six months later, Redis changed to a Business Source License (BSL), creating legal concerns for several StackForge enterprise customers who operated SaaS businesses. Node 18 reached end-of-life in April 2025, becoming a security liability. Neither change was reflected anywhere the agent could see — the agent continued generating code referencing `node:18-alpine` base images and Redis 7.x client configurations in new files for the same project.

The support team was fielding tickets like "your agent keeps regenerating our Dockerfile with Node 18 after we've updated it three times." Engineers were manually correcting agent output — except when they missed it, because the agent sounded so confident.

The underlying problem was that the agent had no concept of the *temporal validity* of its own past decisions. A decision made in January with correct information could be quietly wrong by July, with nothing in the system flagging it.

## Solution Architecture

StackForge integrated foghorn as the architecture decision store for their coding assistant. Every decision the agent makes (technology choices, version pins, library selections) is recorded as a foghorn Fact + Decision pair. Their "approved tools" team maintains a WorldRepo commit that represents the current state of vetted technologies.

When the approved tools list changes (Redis relicensed, Node 18 EOL), a single foghorn commit propagates staleness through the dependency graph, identifying every prior agent decision that was grounded in the now-changed facts.

```
┌────────────────────────────────────────────────────────────────────┐
│                       StackForge Platform                          │
│                                                                    │
│  DevOps team         ┌──────────────────────────────────────────┐ │
│  updates "approved   │  WorldRepo (project-level foghorn DB)    │ │
│  tools" KB    ────→  │                                          │ │
│                      │  Fact: "Redis" "license" "BSL-1.1"       │ │
│                      │  Fact: "Node" "lts-version" "20"         │ │
│                      │  commit("June 2025 tool policy update")  │ │
│                      └──────────────────────┬───────────────────┘ │
│                                             │                      │
│                                    propagate_staleness()           │
│                                             │                      │
│                                             ↓                      │
│  Coding agent      ┌────────────────────────────────────────────┐ │
│  session start  →  │  repo.stale() → [StalenessAlert, ...]     │ │
│                    │  "chose-redis-for-session-cache" STALE     │ │
│                    │  "pinned-node-18-runtime" STALE            │ │
│                    │                                            │ │
│                    │  ⚠️ 3 prior decisions are stale           │ │
│                    │  — review before proceeding               │ │
│                    └────────────────────────────────────────────┘ │
└────────────────────────────────────────────────────────────────────┘
```

## Implementation

```python
# stackforge/agent/decision_store.py
from foghorn.repo import WorldRepo
from foghorn.propagate import PropagationResult

REPO_PATH = "/data/projects/{project_id}/foghorn/world.db"

def record_architecture_decision(
    project_id: str,
    decision_label: str,
    reasoning: str,
    technology: str,
    tech_version: str,
    use_case: str,
) -> None:
    """Record an agent architecture decision tied to current world facts."""
    with WorldRepo.init(REPO_PATH.format(project_id=project_id)) as repo:
        # Record the facts this decision depends on
        fact_license = repo.add_fact(technology, "license", "MIT", confidence=0.95)
        fact_version = repo.add_fact(technology, "current-lts", tech_version, confidence=0.99)
        fact_approved = repo.add_fact(technology, "approved-for", use_case, confidence=1.0)

        repo.commit(f"World state at decision time: {decision_label}")

        # Record the decision with its fact dependencies
        repo.decide(
            label=decision_label,
            content=reasoning,
            depends_on=[fact_license.id, fact_version.id, fact_approved.id],
        )
        repo.commit(f"Architecture decision: {decision_label}")


def check_session_staleness(project_id: str) -> list[str]:
    """Check for stale decisions before starting a coding session.
    Returns human-readable warnings for the agent's context."""
    with WorldRepo.init(REPO_PATH.format(project_id=project_id)) as repo:
        alerts = repo.stale()
        if not alerts:
            return []

        warnings = []
        recommendations = repo.recommend()

        for rec in recommendations:
            if rec.priority in ("critical", "high"):
                warnings.append(
                    f"WARNING: Decision '{rec.decision_label}' is stale. "
                    f"Reason: {rec.reason} "
                    f"Affected facts: {', '.join(rec.stale_facts)}"
                )
        return warnings


def update_approved_tools(
    project_id: str,
    changes: dict,  # {"Redis": {"license": "BSL-1.1"}, "Node": {"current-lts": "20"}}
) -> PropagationResult:
    """DevOps updates the approved tools list; propagate staleness downstream."""
    with WorldRepo.init(REPO_PATH.format(project_id=project_id)) as repo:
        changed_fact_ids = []
        for technology, updates in changes.items():
            for predicate, new_value in updates.items():
                new_fact = repo.add_fact(technology, predicate, new_value)
                changed_fact_ids.append(new_fact.id)

        repo.commit(f"Tool policy update: {list(changes.keys())}")
        return repo.propagate(changed_fact_ids)


# --- In the coding agent session startup ---
def agent_session_preamble(project_id: str) -> str:
    """Build the stale-decision warning block for the agent's system prompt."""
    warnings = check_session_staleness(project_id)
    if not warnings:
        return ""

    lines = [f"⚠️ {len(warnings)} prior architecture decision(s) are stale — review before proceeding:"]
    for w in warnings:
        lines.append(f"  - {w}")
    lines.append("\nDo not generate code that assumes the above decisions are still valid.")
    return "\n".join(lines)
```

When DevOps called `update_approved_tools()` after the Redis relicensing, `propagate_staleness()` returned a `PropagationResult` showing 47 decisions across 23 active projects were directly stale. The next time any agent opened a coding session on those projects, it received the `⚠️ 3 prior decisions are stale` warning before writing a single line of code.

## Results

- **78% reduction in stale-decision bugs** in production code, measured as the number of support tickets mentioning deprecated/invalid technology choices in generated code
- **Agent self-identification of stale context in under 50ms** — `repo.stale()` on a typical project with 200 decisions and 500 facts runs in 42ms on commodity hardware
- **12 engineering teams** across StackForge's enterprise customer base are using foghorn-backed decision tracking for their projects
- **Zero Redis BSL incidents** among the 23 affected projects — all were warned before the next agent session, and engineers reviewed and updated the affected files proactively
- **Propagation clarity**: `PropagationResult.impact_summary` gave DevOps a machine-readable explanation of exactly which downstream decisions each tool policy change affected, without requiring them to understand the individual project architectures

## Key Takeaways

- Architecture decisions have expiration dates. Any agent that makes long-lived decisions (technology choices, version pins, vendor selections) needs a mechanism to discover when those decisions are no longer grounded in current facts.
- Facts and decisions are different primitives. foghorn's separation of Fact (what is true about the world) from Decision (what the agent concluded based on those facts) is what makes staleness propagation tractable.
- `propagate_staleness()` is the diff tool for your agent's knowledge graph. When a fact changes, you don't need to know which decisions it affects — foghorn walks the dependency graph for you.
- Warning in the system prompt is more effective than blocking. Rather than preventing agents from generating code on stale decisions, StackForge surfaces the warning in the agent's context. The agent can then ask the user whether to proceed — preserving autonomy while eliminating the "confidently wrong" failure mode.
- Local-first is production-ready. The single-SQLite-file design means each project gets its own isolated knowledge base without requiring shared infrastructure.

## Try It Yourself

```bash
# Install foghorn
pip install foghorn-ai

# Initialize a repo, add facts, make a decision, then update a fact and check staleness
python -c "
from foghorn.repo import WorldRepo

with WorldRepo.init('/tmp/demo.db') as repo:
    f1 = repo.add_fact('Redis', 'license', 'MIT')
    f2 = repo.add_fact('Redis', 'approved-for', 'rate-limiting')
    repo.commit('Initial world state')
    repo.decide('chose-redis', 'Redis is MIT-licensed and fast', depends_on=[f1.id, f2.id])
    repo.commit('Architecture decision')

    # Now the world changes
    repo.add_fact('Redis', 'license', 'BSL-1.1')
    repo.commit('Redis relicensed')

    alerts = repo.stale()
    print(f'Stale decisions: {[a.decision_label for a in alerts]}')
    recs = repo.recommend()
    print(f'Recommendation: {recs[0].action} — {recs[0].reason}')
"

# Or use the CLI
foghorn stale --db /tmp/demo.db
```
