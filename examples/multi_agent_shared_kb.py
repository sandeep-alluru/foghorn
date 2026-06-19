"""
multi_agent_shared_kb.py — foghorn for a multi-agent research pipeline.

Story: 3 agents share a single foghorn knowledge base:
  - ResearchAgent: discovers facts about competitor landscape
  - AnalysisAgent: makes strategic decisions based on those facts
  - WriterAgent:   makes content decisions based on analysis decisions

When ResearchAgent updates a fact (OpenAI drops o3-mini pricing), foghorn
shows how the staleness ripples through downstream agents.

This simulates a LangGraph-style multi-agent system where agents share
a common world model.

Run:
    python examples/multi_agent_shared_kb.py
"""

from __future__ import annotations

import shutil
import tempfile
from dataclasses import dataclass
from typing import NamedTuple

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
    print(f"\n── {title} {'─' * max(0, 60 - len(title))}")
    print()


# ---------------------------------------------------------------------------
# Simulated agent identities
# ---------------------------------------------------------------------------

@dataclass
class AgentRole:
    name: str
    role: str
    emoji: str


RESEARCH_AGENT = AgentRole("ResearchAgent", "competitor-intelligence", "")
ANALYSIS_AGENT = AgentRole("AnalysisAgent", "strategic-decisions", "")
WRITER_AGENT   = AgentRole("WriterAgent",   "content-strategy",     "")


# ---------------------------------------------------------------------------
# Dependency tracking: which decisions depend on which facts
# Foghorn tracks this via fact_ids on each decision, but we also
# maintain an explicit map for the ASCII art propagation graph.
# ---------------------------------------------------------------------------

class DepNode(NamedTuple):
    agent: str
    kind: str   # "fact" or "decision"
    label: str


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
    banner("foghorn — Multi-Agent Shared Knowledge Base Demo")

    print("  3-agent LangGraph-style pipeline:")
    print("  ResearchAgent → AnalysisAgent → WriterAgent")
    print()
    print("  All agents share one foghorn WorldRepo.")
    print("  When ResearchAgent updates a fact, downstream agents")
    print("  discover their decisions are stale before taking action.")
    print()

    repo = WorldRepo.init(f"{tmp}/shared_kb.db")

    # -----------------------------------------------------------------------
    # PHASE 1: ResearchAgent discovers initial competitor landscape
    # -----------------------------------------------------------------------
    section("Phase 1 — ResearchAgent: competitor intelligence")

    print(f"  [{RESEARCH_AGENT.name}] Researching AI API pricing landscape...\n")

    # Facts discovered by ResearchAgent
    f_openai_o3 = repo.add_fact(
        "OpenAI o3-mini",
        "pricing",
        "$1.10/M input tokens, $4.40/M output tokens (as of 2025-Q1)",
        confidence=0.95,
    )
    f_anthropic = repo.add_fact(
        "Anthropic Claude-3-5-Haiku",
        "pricing",
        "$0.80/M input tokens, $4.00/M output tokens (as of 2025-Q1)",
        confidence=0.95,
    )
    f_gemini = repo.add_fact(
        "Google Gemini-1.5-Flash",
        "pricing",
        "$0.075/M input tokens, $0.30/M output tokens (as of 2025-Q1)",
        confidence=0.90,
    )
    f_context_window = repo.add_fact(
        "OpenAI o3-mini",
        "context-window",
        "128K tokens — sufficient for most coding and analysis tasks",
        confidence=0.99,
    )
    f_reasoning = repo.add_fact(
        "OpenAI o3-mini",
        "capability",
        "strong reasoning via chain-of-thought, AIME benchmark: 90.0%",
        confidence=0.88,
    )

    facts_r1 = [f_openai_o3, f_anthropic, f_gemini, f_context_window, f_reasoning]
    for f in facts_r1:
        print(f"  [FACT]  {f.id[:8]}  {f.subject:<30} {f.predicate:<20}")

    c1 = repo.commit("Initial competitor landscape — ResearchAgent")
    print(f"\n  Committed: {c1.id[:8]}  {c1.message}")

    # -----------------------------------------------------------------------
    # PHASE 2: AnalysisAgent makes strategic decisions
    # -----------------------------------------------------------------------
    section("Phase 2 — AnalysisAgent: strategic decisions")

    print(f"  [{ANALYSIS_AGENT.name}] Analyzing competitor landscape...\n")

    d_use_o3 = repo.decide(
        "recommend-o3mini-for-agents",
        "o3-mini at $1.10/M input is cost-effective for agentic workflows "
        "requiring strong reasoning. AIME 90% validates reasoning quality. "
        "128K context sufficient for multi-step tasks.",
        depends_on=[f_openai_o3.id, f_reasoning.id, f_context_window.id],
    )
    d_tier_model = repo.decide(
        "use-gemini-for-classification",
        "Gemini-1.5-Flash at $0.075/M input for high-volume classification "
        "tasks. Cost is 14x cheaper than o3-mini for simple tasks.",
        depends_on=[f_gemini.id, f_openai_o3.id],
    )
    d_positioning = repo.decide(
        "position-against-openai-cost",
        "Market positioning: our platform saves customers 30% vs o3-mini "
        "by using tiered model routing (Gemini for simple, o3 for complex). "
        "Pricing advantage is defensible at current rates.",
        depends_on=[f_openai_o3.id, f_gemini.id],
    )
    d_budget = repo.decide(
        "monthly-api-budget-50k-tokens",
        "Monthly budget ceiling: 50K o3-mini output tokens ($220/month). "
        "Based on current pricing of $4.40/M output tokens.",
        depends_on=[f_openai_o3.id],
    )

    decisions_a2 = [d_use_o3, d_tier_model, d_positioning, d_budget]
    for d in decisions_a2:
        print(f"  [DECISION]  {d.label}")
        print(f"              depends on: {[fid[:8] for fid in d.fact_ids]}")
        print()

    c2 = repo.commit("Strategic analysis decisions — AnalysisAgent")
    print(f"  Committed: {c2.id[:8]}  {c2.message}")

    # -----------------------------------------------------------------------
    # PHASE 3: WriterAgent creates content based on AnalysisAgent decisions
    # -----------------------------------------------------------------------
    section("Phase 3 — WriterAgent: content decisions")

    print(f"  [{WRITER_AGENT.name}] Planning content strategy...\n")

    # WriterAgent reads facts directly to make content decisions
    d_blog_post = repo.decide(
        "write-blog-cost-comparison",
        "Publish a blog post: 'How we save 30% on AI inference costs using "
        "tiered routing'. Lead with the o3-mini vs Gemini cost comparison. "
        "Cite: o3-mini $1.10/M vs Gemini $0.075/M (14x delta).",
        depends_on=[f_openai_o3.id, f_gemini.id],
    )
    d_pricing_page = repo.decide(
        "update-pricing-page-with-savings",
        "Update pricing page to show 30% savings claim vs OpenAI o3-mini. "
        "Based on $1.10/M benchmark price. Include calculator widget.",
        depends_on=[f_openai_o3.id],
    )
    d_demo = repo.decide(
        "create-demo-using-o3mini-benchmark",
        "Create interactive demo showing reasoning quality on coding tasks. "
        "Reference AIME 90% benchmark score for credibility.",
        depends_on=[f_reasoning.id],
    )

    decisions_w3 = [d_blog_post, d_pricing_page, d_demo]
    for d in decisions_w3:
        print(f"  [DECISION]  {d.label}")
        print(f"              depends on: {[fid[:8] for fid in d.fact_ids]}")
        print()

    c3 = repo.commit("Content strategy decisions — WriterAgent")
    print(f"  Committed: {c3.id[:8]}  {c3.message}")

    # -----------------------------------------------------------------------
    # DEPENDENCY GRAPH (ASCII art)
    # -----------------------------------------------------------------------
    section("Dependency Graph — Before update")

    print("  Facts (ResearchAgent)          Decisions (AnalysisAgent / WriterAgent)")
    print()
    print(f"  [{f_openai_o3.id[:8]}] o3-mini pricing ──────┬──→ [{d_use_o3.id[:8]}]    recommend-o3mini-for-agents")
    print(f"                               ├──→ [{d_tier_model.id[:8]}] use-gemini-for-classification")
    print(f"                               ├──→ [{d_positioning.id[:8]}] position-against-openai-cost")
    print(f"                               ├──→ [{d_budget.id[:8]}]    monthly-api-budget-50k-tokens")
    print(f"                               ├──→ [{d_blog_post.id[:8]}] write-blog-cost-comparison")
    print(f"                               └──→ [{d_pricing_page.id[:8]}] update-pricing-page-with-savings")
    print()
    print(f"  [{f_gemini.id[:8]}] gemini pricing    ──────┬──→ [{d_tier_model.id[:8]}] use-gemini-for-classification")
    print(f"                               ├──→ [{d_positioning.id[:8]}] position-against-openai-cost")
    print(f"                               └──→ [{d_blog_post.id[:8]}] write-blog-cost-comparison")
    print()
    print(f"  [{f_reasoning.id[:8]}] o3 reasoning    ──────┬──→ [{d_use_o3.id[:8]}]    recommend-o3mini-for-agents")
    print(f"                               └──→ [{d_demo.id[:8]}]    create-demo-using-o3mini-benchmark")
    print()
    print(f"  [{f_context_window.id[:8]}] o3 ctx window  ─────→  [{d_use_o3.id[:8]}]    recommend-o3mini-for-agents")
    print()
    print(f"  [{f_anthropic.id[:8]}] anthropic pricing   (no decisions depend on this yet)")

    # -----------------------------------------------------------------------
    # FACT UPDATE: OpenAI drops o3-mini pricing significantly
    # -----------------------------------------------------------------------
    section("Fact Update — ResearchAgent: OpenAI o3-mini price drop")

    print(f"  [{RESEARCH_AGENT.name}] Detected pricing update from OpenAI...\n")
    print("  OpenAI reduced o3-mini pricing by 86%:")
    print("  OLD: $1.10/M input, $4.40/M output")
    print("  NEW: $0.15/M input, $0.60/M output")
    print()
    print("  This changes the cost comparison dynamics significantly.")
    print("  Retracting old pricing fact and committing updated fact...")
    print()

    # Retract old fact, add new one
    repo.retract_fact(f_openai_o3.id)
    f_openai_o3_new = repo.add_fact(
        "OpenAI o3-mini",
        "pricing",
        "$0.15/M input tokens, $0.60/M output tokens (2025-Q2 price drop, -86%)",
        confidence=0.99,
    )
    print(f"  Retracted: {f_openai_o3.id[:8]}  (old pricing)")
    print(f"  Added:     {f_openai_o3_new.id[:8]}  (new pricing)")

    c4 = repo.commit("OpenAI o3-mini price drop -86% — ResearchAgent update")
    print(f"\n  Committed: {c4.id[:8]}  {c4.message}")

    # -----------------------------------------------------------------------
    # STALENESS PROPAGATION: Which agents are affected?
    # -----------------------------------------------------------------------
    section("Staleness Propagation — Who needs to re-evaluate?")

    alerts = repo.stale()

    if not alerts:
        print("  No staleness detected via repo.stale().")
        print("  (This can happen when fact IDs don't overlap with decision dependencies.)")
    else:
        print(f"  {len(alerts)} decision(s) flagged as stale:\n")

        analysis_stale = []
        writer_stale = []

        analysis_labels = {d.label for d in decisions_a2}
        writer_labels = {d.label for d in decisions_w3}

        for alert in alerts:
            print(f"  [STALE]  {alert.decision_label}")
            print(f"           impact_score: {alert.impact_score:.2f}")
            print()
            if alert.decision_label in analysis_labels:
                analysis_stale.append(alert)
            elif alert.decision_label in writer_labels:
                writer_stale.append(alert)

        # Show propagation summary
        print("  STALENESS PROPAGATION SUMMARY:")
        print()
        print(f"  ResearchAgent updated: o3-mini pricing (ID: {f_openai_o3.id[:8]} → {f_openai_o3_new.id[:8]})")
        print()
        print(f"  AnalysisAgent: {len(analysis_stale)} stale decision(s)")
        for a in analysis_stale:
            print(f"    - {a.decision_label}  (impact: {a.impact_score:.2f})")
        print()
        print(f"  WriterAgent: {len(writer_stale)} stale decision(s)")
        for a in writer_stale:
            print(f"    - {a.decision_label}  (impact: {a.impact_score:.2f})")

    # -----------------------------------------------------------------------
    # PROPAGATION GRAPH (post-update)
    # -----------------------------------------------------------------------
    section("Propagation Graph — After pricing update")

    print("  STALE fact (retracted):")
    print(f"  [~~{f_openai_o3.id[:8]}~~]  o3-mini pricing ($1.10/M)  ← STALE: 6 decisions depended on this")
    print()
    print("  NEW fact (active):")
    print(f"  [{f_openai_o3_new.id[:8]}]  o3-mini pricing ($0.15/M)  ← No decisions reference this yet")
    print()
    print("  Agents that must re-evaluate:")
    print()
    print("    AnalysisAgent:")
    print("      - recommend-o3mini-for-agents     (budget math changes at $0.15/M)")
    print("      - use-gemini-for-classification   (cost delta narrows: 2x not 14x)")
    print("      - position-against-openai-cost    (30% savings claim is now wrong)")
    print("      - monthly-api-budget-50k-tokens   (budget ceiling drops from $220 to $30)")
    print()
    print("    WriterAgent:")
    print("      - write-blog-cost-comparison      (all price figures are outdated)")
    print("      - update-pricing-page-with-savings (savings claim needs recalculation)")
    print()
    print("    Not affected:")
    print("      - WriterAgent: create-demo-using-o3mini-benchmark  (depends on reasoning, not pricing)")
    print("      - AnalysisAgent had no decisions on Anthropic or Gemini pricing alone")

    # -----------------------------------------------------------------------
    # Commit log
    # -----------------------------------------------------------------------
    section("Commit Log — Full history")

    for wc in repo.log():
        print(f"  {wc.id[:8]}  {wc.message}")
        print(f"             {len(wc.fact_ids)} facts in snapshot  •  {len(wc.decision_ids)} decisions")
        print()

    repo.close()

    print("=" * 68)
    print("  Demo complete.")
    print("  Integrate foghorn.stale() into your agent startup to catch")
    print("  stale decisions before they cause production issues.")
    print("=" * 68)
    print()


if __name__ == "__main__":
    main()
