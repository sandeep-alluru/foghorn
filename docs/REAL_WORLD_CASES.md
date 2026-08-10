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

## Case ACTIVITY-FRAMES — deterministic screen-activity memory (arXiv 2608.05784)

**Source:** Track B public research (`20260808T041217Z` and prior sessions) —
[Activity Frames: Deterministic Screen-Activity Compilation for Agent Memory](https://arxiv.org/abs/2608.05784).

**What fails:**

1. Computer-use agents re-pay frontier inference to re-derive routines the user
   already performed because agent memory records what the user *said*, not what
   the user *did*.
2. LLM summaries of raw screen capture are used as day memory — paper reports
   ~66–80% accuracy vs ~98% for compiled frames.
3. Raw uncompiled capture is too large and non-auditable as a prompt block;
   no evidence pointers back to raw rows.

**Product in this repo:**

| Control | API |
|---------|-----|
| Raw row / frame types | `RawCaptureRow`, `ActivityFrame` |
| Deterministic compiler | `compile_activity_frames` (app/site/gap split, zero-model) |
| Stable id | `activity_frame_fingerprint` (SHA-256, byte-identical) |
| Validity | `frame_is_valid` (timing + non-empty evidence_ptrs) |
| Memory gate | `gate_activity_memory(memory_mode=…)` |
| Raise form | `assert_activity_memory_ok` |

**Rules (load-bearing):**

- `memory_mode=llm_summary` → **FAIL** (refuse summary-only activity memory)
- `memory_mode=raw_uncompiled` → **FAIL** (must compile first)
- No frames when required → **FAIL_LOUD**
- Frame without evidence pointers → **FAIL_LOUD**
- `frame_id` ≠ deterministic fingerprint → **FAIL** (tamper / model rewrite)
- Claimed frame ids not in inventory → **FAIL**
- Valid compiled frames with evidence → **PASS**

**Tests:** `tests/test_activity_frames.py` — arXiv day-activity fixture.

**Non-Ornament:** Call `gate_activity_memory` **before** answering questions
about a session day or replaying a routine from screen memory. Pair with
`gate_staleness` / `gate_source_freshness` for fact→decision edges and wiki age.

---

## Case EVIDENCE-LINK — unprovenanced feature engineering (arXiv 2608.06366)

**Source:** Track B public research (`20260810T001224Z` / prior sessions) —
[Tracing the Heart: An Evidence-Linked Pipeline for Heart-Failure Feature
Engineering](https://arxiv.org/abs/2608.06366v1).

**What fails:**

1. Multi-agent feature pipelines emit derived/aggregated clinical (or general)
   features without provenance back to source tables, raw rows, or guidelines.
2. Agents claim **decision-grade** readiness with zero evidence links.
3. Rubric/structure failures still ship as green features.
4. `gate_source_freshness` ages wiki facts; `gate_activity_memory` requires
   activity `evidence_ptrs` — neither gates **engineered feature provenance**.

**Product in this repo:**

| Control | API |
|---------|-----|
| Feature / link types | `FeatureRecord`, `EvidenceLink` |
| Kind helpers | `is_feature_kind`, `is_evidence_kind` |
| Analyzer | `analyze_evidence_links` |
| Provenance gate | `gate_evidence_links(..., claim_decision_grade=…)` |
| Raise form | `assert_evidence_linked(...)` |

**Rules (load-bearing):**

- claim decision-grade + zero features → **FAIL_LOUD**
- claim decision-grade + features with zero links → **FAIL_LOUD**
- feature below `min_links_per_feature` → **FAIL**
- empty / unknown `source_id` (when inventory given) → **FAIL**
- `rubric_ok=False` → **FAIL**
- fully linked, rubric-ok features → **PASS**

**Tests:** `tests/test_evidence_link.py` — Tracing the Heart fixture class.

**Non-Ornament:** Call `gate_evidence_links` **before** using engineered
features in decisions. Pair with `gate_source_freshness` for wiki age and
`gate_activity_memory` for screen evidence pointers.

---

## Case TA-RAG — tone / contextual decoupling (arXiv 2608.06672)

**Source:** Track B research (`20260810T161237Z`) —
[TA-RAG: Tone Awareness as a Design Imperative for Retrieval-Augmented
Generation](https://arxiv.org/abs/2608.06672v1).

**What fails:**

1. Retrieved docs carry formal/academic/clinical style that shapes RAG output
   **before** user tone instructions are honored.
2. **Contextual decoupling**: facts correct, recipient tone wrong
   (linguistic / cognitive / relational misalignment).
3. Agents claim tone-matched replies while `response_tone` follows sources.
4. Freshness and evidence gates do not check **register** alignment.

**Product in this repo:**

| Control | API |
|---------|-----|
| Doc type | `RetrievedDoc` |
| Analyzer | `analyze_tone_alignment` → `ToneReport` |
| Gate | `gate_tone_awareness(...)` |
| Helpers | `infer_tone_from_text`, `formality_band` |
| Raise form | `assert_tone_aware` |

**Rules (load-bearing):**

- empty requested tone / phantom claim → **FAIL_LOUD**
- claimed match but response_tone ≠ request → **FAIL**
- contextual decoupling (response follows source formality) → **FAIL**
- misalignment count above budget → **FAIL**
- aligned request/response → **PASS**

**Tests:** `tests/test_tone_awareness.py`

**Non-Ornament:** Call `gate_tone_awareness` after retrieval, before shipping
user-facing text that claimed a register. Pair with `gate_source_freshness`
and `gate_evidence_links`.

## Related farm lessons
- Writer fixed without tracing readers (cache key bugs)
- Silent success / vacuous guards
- MCP write-only tools are ornaments
- Amazon Q stale wiki — wall-clock source age (this section)
- Activity Frames — compile + refuse LLM-summary memory (this section)
- Evidence-linked features — refuse unprovenanced engineering (this section)
- TA-RAG — refuse tone-decoupled RAG answers (this section)
