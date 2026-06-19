# Case Study: Eliminating Cross-Agent Data Inconsistency in a Multi-Agent Research Pipeline

## Company Profile

**Synthesis AI** is an enterprise research automation company based in New York, NY. With 30 engineers, they build multi-agent LLM pipelines that automate competitive intelligence, market research, and due diligence workflows for financial services and consulting firms. Their platform processes roughly 2,000 research assignments per month, each requiring coordination between 5 specialized AI agents.

## The Problem

Synthesis AI's research pipeline consists of five sequential agents: Scout (market data collection), Analyst (quantitative modeling), Writer (report drafting), Reviewer (accuracy checking), and Publisher (final formatting and delivery). These agents share a knowledge base of market facts — company revenues, market sizes, competitive positions, regulatory statuses.

The problem emerged at scale: Scout might discover that a target company's Q3 revenue was $847M (revised upward from a previously cached $612M figure). Scout would update the shared knowledge base. But Writer — which had already started drafting the competitive analysis section — was still using the old $612M figure it had read earlier in the pipeline run. By the time Reviewer caught the discrepancy, Writer had produced 8 pages of analysis anchored to the wrong number. Reviewer would flag it, Writer would need to regenerate, and in several cases the cascading corrections required all downstream agents to partially restart.

On their most complex research assignments, this cross-agent data inconsistency accounted for an average of 2.3 hours of wasted computation and rework per pipeline run — representing roughly 35% of total pipeline cost. The root cause was invisible: there was no mechanism to tell downstream agents "the fact you read 20 minutes ago has since been updated, and your analysis is now built on stale data."

Their first attempted fix — having every agent re-read all facts before every action — was computationally prohibitive (tripled pipeline cost) and caused its own consistency issues when fact updates happened mid-agent-execution.

## Solution Architecture

Synthesis AI replaced their ad-hoc shared knowledge base with a foghorn WorldRepo shared across all five agents in a pipeline run. When Scout updates a fact, `propagate_staleness()` immediately identifies which downstream agent decisions are affected. Each agent handoff begins with a staleness check — if the receiving agent has made any decisions on facts that have since changed, it gets a targeted staleness report before it continues.

```
┌────────────────────────────────────────────────────────────────────────┐
│              Synthesis AI Research Pipeline                            │
│                                                                        │
│  ┌─────────┐    ┌──────────┐    ┌────────┐    ┌──────────┐    ┌─────┐│
│  │  Scout  │ →  │ Analyst  │ →  │ Writer │ →  │ Reviewer │ →  │ Pub ││
│  └────┬────┘    └────┬─────┘    └───┬────┘    └────┬─────┘    └──┬──┘│
│       │              │              │               │              │   │
│       │         ┌────▼──────────────▼───────────────▼─────────────▼─┐ │
│       └────────►│         Shared foghorn WorldRepo                  │ │
│                 │                                                    │ │
│                 │  Scout adds/updates Facts                         │ │
│                 │  Each agent records Decisions with fact_ids       │ │
│                 │  At each handoff: propagate_staleness()           │ │
│                 │  → stale decisions flagged before next agent runs │ │
│                 └────────────────────────────────────────────────────┘ │
└────────────────────────────────────────────────────────────────────────┘
```

A critical design choice: fog horn's `propagate_staleness()` is called at agent *handoff*, not continuously. This means agents don't get interrupted mid-execution by real-time fact updates. Instead, they complete their work, then the pipeline coordinator checks whether any of their decisions were grounded in facts that Scout updated after they read them — before handing off to the next agent.

## Implementation

```python
# synthesis/pipeline/knowledge_base.py
from foghorn.repo import WorldRepo
from foghorn.propagate import PropagationResult
from foghorn.fact import Decision, StalenessAlert

PIPELINE_REPO_PATH = "/data/pipelines/{run_id}/world.db"


class PipelineKnowledgeBase:
    """Shared foghorn WorldRepo for a single pipeline run."""

    def __init__(self, run_id: str) -> None:
        self.run_id = run_id
        self.repo = WorldRepo.init(PIPELINE_REPO_PATH.format(run_id=run_id))
        self._changed_fact_ids: list[str] = []

    # --- Scout calls this when it discovers or updates a market fact ---
    def record_market_fact(
        self, subject: str, predicate: str, value: str, confidence: float = 1.0
    ) -> str:
        """Record or update a market fact. Returns the fact ID."""
        fact = self.repo.add_fact(subject, predicate, value, confidence=confidence)
        self._changed_fact_ids.append(fact.id)
        self.repo.commit(f"Scout: {subject} {predicate} = {value!r}")
        return fact.id

    # --- Each agent calls this to record what it decided and why ---
    def record_decision(
        self, agent_name: str, label: str, reasoning: str, fact_ids: list[str]
    ) -> str:
        """Record an agent decision with its fact dependencies."""
        full_label = f"{agent_name}/{label}"
        decision = self.repo.decide(
            label=full_label,
            content=reasoning,
            depends_on=fact_ids,
        )
        self.repo.commit(f"{agent_name} decision: {label}")
        return decision.id

    # --- Pipeline coordinator calls this at every agent handoff ---
    def check_staleness_for_handoff(
        self, from_agent: str, to_agent: str
    ) -> PropagationResult:
        """Check which decisions are stale before handing off to the next agent."""
        if not self._changed_fact_ids:
            from foghorn.propagate import PropagationResult
            return PropagationResult(
                changed_fact_ids=[],
                impact_summary="No facts changed since last check.",
            )

        result = self.repo.propagate(self._changed_fact_ids)
        self._changed_fact_ids = []  # Reset after check

        if result.directly_stale or result.transitively_stale:
            print(f"  [foghorn] Handoff {from_agent} → {to_agent}: {result.impact_summary}")
            print(f"  Directly stale  : {result.directly_stale}")
            print(f"  Transitively stale: {result.transitively_stale}")

        return result

    def close(self) -> None:
        self.repo.close()


# --- Pipeline coordinator ---
class ResearchPipeline:
    def __init__(self, run_id: str, assignment: dict) -> None:
        self.kb = PipelineKnowledgeBase(run_id)
        self.assignment = assignment

    def run(self) -> str:
        # 1. Scout: gather market facts
        scout_fact_ids = self._run_scout()

        # Handoff Scout → Analyst: check if any Analyst decisions are stale
        # (on first run, nothing is stale yet; this becomes important on re-runs)
        staleness = self.kb.check_staleness_for_handoff("Scout", "Analyst")

        # 2. Analyst: build quantitative model
        analyst_fact_ids = self._run_analyst(scout_fact_ids, staleness)
        staleness = self.kb.check_staleness_for_handoff("Analyst", "Writer")

        # 3. Writer: draft report — only proceeds if no stale decisions
        if staleness.directly_stale:
            print(f"  [WARNING] Writer inheriting {len(staleness.directly_stale)} stale decisions")
            print(f"  Re-running Analyst with updated facts...")
            analyst_fact_ids = self._run_analyst(scout_fact_ids, staleness, rerun=True)
            staleness = self.kb.check_staleness_for_handoff("Analyst", "Writer")

        writer_content = self._run_writer(analyst_fact_ids)
        staleness = self.kb.check_staleness_for_handoff("Writer", "Reviewer")

        # 4. Reviewer, 5. Publisher: pass through with staleness context
        reviewed = self._run_reviewer(writer_content, staleness)
        self.kb.close()
        return reviewed

    def _run_scout(self) -> list[str]:
        fact_ids = []
        # ... scout collects data ...
        fid = self.kb.record_market_fact(
            "Acme Corp", "q3-revenue-millions", "847", confidence=0.97
        )
        fact_ids.append(fid)
        return fact_ids
```

When Scout discovers the corrected $847M revenue figure and calls `record_market_fact()`, the coordinator calls `check_staleness_for_handoff()` before passing to Writer. The `PropagationResult` shows `directly_stale: ["Analyst/revenue-model-acme"]` — Writer is blocked from consuming stale analyst output, and the Analyst reruns against the correct figure. Total rework: one agent re-execution rather than three.

## Results

- **94% elimination of cross-agent data inconsistencies** — measured as the fraction of pipeline runs where downstream agents consumed stale facts, down from 38% of runs to 2.3%
- **2.3 hours saved per pipeline run** on average — the rework cycles that previously required multi-agent restarts are now prevented by targeted staleness propagation
- **Handoff check latency**: `propagate_staleness()` across a typical pipeline KB (300 facts, 150 decisions, 5 agents) runs in under 80ms — negligible overhead at pipeline handoff
- **Propagation depth visibility**: `PropagationResult.propagation_depth` tells the coordinator how many agent-levels deep the staleness cascades, enabling smarter re-run scoping
- **Zero ambiguity about which agent decisions are stale**: The `directly_stale` and `transitively_stale` lists tell the pipeline coordinator exactly which decisions need to be re-evaluated — not "something might be wrong," but "Analyst/revenue-model-acme is stale because Scout updated acme q3-revenue-millions"

## Key Takeaways

- Shared mutable knowledge in multi-agent systems requires explicit dependency tracking. Passing data through a queue or shared database doesn't capture the crucial information: which agent decisions *depended on* which facts.
- Staleness should be detected at handoff, not continuously. Continuous staleness monitoring interrupts agents mid-execution; handoff-time checks give each agent a stable window to work while still catching inconsistencies before they propagate.
- `propagate_staleness()` is cheap enough to call on every handoff. At sub-100ms for typical knowledge bases, there's no reason to batch or throttle it.
- The `PropagationResult.impact_summary` is designed to be inserted directly into an agent's context. When the pipeline coordinator tells Writer "Analyst/revenue-model-acme is stale," Writer can ask for a re-run rather than guessing that something changed.
- Design for re-runs, not for perfect first-pass consistency. The goal isn't to make facts never change mid-pipeline — it's to make stale-fact discovery cheap enough that targeted re-runs are practical.

## Try It Yourself

```bash
# Install foghorn
pip install foghorn-ai

# Simulate a two-agent staleness scenario
python -c "
from foghorn.repo import WorldRepo

with WorldRepo.init('/tmp/pipeline-demo.db') as repo:
    # Scout records initial market fact
    f1 = repo.add_fact('Acme Corp', 'q3-revenue-millions', '612', confidence=0.8)
    repo.commit('Scout: initial market data')

    # Analyst makes a decision based on this fact
    repo.decide('revenue-model-acme', 'Based on 612M revenue, growth rate is 12%', depends_on=[f1.id])
    repo.commit('Analyst: revenue model')

    # Scout discovers corrected figure
    f2 = repo.add_fact('Acme Corp', 'q3-revenue-millions', '847', confidence=0.97)
    repo.commit('Scout: corrected revenue figure')

    # Check propagation at handoff
    result = repo.propagate([f2.id])
    print(result.impact_summary)
    print('Stale decisions:', result.directly_stale)
"

# Use the CLI to inspect staleness
foghorn stale --db /tmp/pipeline-demo.db --format markdown
```
