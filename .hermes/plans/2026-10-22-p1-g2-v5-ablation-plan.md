# P1 §G2 — **V5, the ablation**. Execution plan.

> **Written 2026-10-22. FOR SIGNOFF — nothing built.** Executes verifier **V5** of
> `.hermes/plans/2026-10-22-p1-g2-community-summaries-plan.md` (§3, "the ablation"; §4, the
> pre-registered rule). Read that plan's §3/§4, `IMPROVEMENTS.md` §I52/§I53/§I54, and `HANDOFF.md`.
>
> **Why this needs its own plan.** The §G2 summaries are **built and verified** (V1/V2/V4/V6 PASS,
> V3 read by eye) but they are a **JSON artifact and no code reads it**. V5 is therefore a **build**
> (a retrieval path that does not exist) **plus** a measurement — and §4 of the §G2 plan makes it the
> **endpoint**: a positive wires the summaries into retrieval, a null or negative records them
> measured-and-negative and wires **nothing**.
>
> **Sequencing.** Runs after §G3 (done) and after the §I12 Lane B rebuild (done). It is the last
> §G2 step. It does **not** gate §G5/§I2 (genuine 1–2 hop traversal), which is a separate item.

---

## 0. Settled — what V5 is not

| Not this | Why |
|---|---|
| a re-measurement | the lane has never been measured; the summaries are wired into **nothing** |
| a page-level recall race | ⚠️ **V3 measured the leaf partition as a two-population mixture** (166 of 218 leaves hold ≤ 5 concepts and ~4 % of the text; 34 hold > 50 concepts; p90 108, max 336). One summary can cover hundreds of pages, so a recall number is **inflatable by construction** — the §G1 equal-pool defect, in the other direction |
| a point-query path | the §G2 plan §7: summaries serve the **global sensemaking query only** |
| a reason to re-spend the summary budget | §4: a null V5 is a **result**, not an unresolved one |

---

## 1. The build V5 requires

Nothing today reads `logs/p1/step10/g2_summaries_2026-10-22.json`. V5 needs a retrieval path:

**1a. `src/pdf_ingestion/community_summary_search.py`** — a new module, no cluster dependency of
its own:
- load the summary artifact (path + the artifact's own `document`, `resolutions` fields);
- re-derive the community → concept → chunk mapping with the **existing** readers
  (`read_concept_graph` / `read_concept_chunks` / `build_hierarchy`) rather than storing it: Leiden
  is deterministic given the seed **and the reader's row order**, and `community_summaries.py`
  already pins that order against the gate (its `RELATES_CYPHER` note). Re-deriving is what makes
  the summary-to-passage join checkable instead of trusted;
- **embed the summaries once** (dense lane, 1024d) and hold them in process — ~200 summaries, so a
  query-time ANN over a Qdrant collection is not worth its moving parts;
- `search(query, level, k) -> [{"summary", "level", "community", "score", "chunk_ids", "pages"}]`.

**1b. A CLI** `scripts/search_community_summaries.py` (dry-run default), so the path is exercisable
and inspectable without the eval harness.

**1c. `evaluate_rag.py` gains `--community-summaries`** (default **off**). Off by default is the
point: §4 wires the summaries in only if V5 is positive, so the shipped default must stay the
current path until the owner reads the number.

**1d. Prerequisite, already landed:** the §G2 build is checkpointed and logs per call (§I53 fix), so
any re-run of the summaries for a different resolution/level costs minutes, not 20.

---

## 2. The ablation design

### 2.1 Arms, and the fixed slot budget

The **slot budget is fixed and equal across arms**. Without that, the treatment wins on context
volume alone and the measurement is the §G1 defect again. Every arm is handed **the same number of
context slots**, and the artifact records the **token count** each arm actually fed the generator.

| arm | context handed to the generator | slots |
|---|---|---|
| **A — control** | the shipped overview path: the **2 RAPTOR summary nodes** (`HANDOFF.md`: "RAPTOR search (overview only) → 2 summary nodes") | 2 |
| **B — treatment (primary)** | the **2 top-scoring community summaries at level 2 (res 0.5, 181 communities)** — the coarsest level, and the one the "global sensemaking query" is for | 2 |
| C — sensitivity | the 2 top-scoring community summaries at **level 1 (res 1.0)** | 2 |
| D — sensitivity | A **and** B combined | 4 |

**Pre-registered:** the **endpoint is A vs B**. C and D are reported as sensitivity and are **not**
part of the decision rule — pre-registering one comparison is what stops the best-looking arm from
being chosen after the fact (the §D1 rule this project already follows).

### 2.2 Queries

The **40 `overview`** queries of `data/eval_queries_v2.json` — the lane the summaries exist to serve,
and the lane V3's finding is about. Negatives and visual queries are out of scope.

⚠️ **The overview lane's own ceiling.** §D9 measured the v2 overview lane's achievable maximum at
**0.3992** against the text lane's 0.8016, because overview labels average **73.8** pages. Report
every retrieval number against **that ceiling**, never raw — and treat the generation metrics as the
primary endpoint for exactly this reason.

### 2.3 Endpoints

| # | endpoint | role | why |
|---|---|---|---|
| **P1** | **Faithfulness** (judge, per answer) | **primary** | the course's own rule: *"every index must earn its place through ablation"*. Generation quality is what a summary is *for*, and it cannot be inflated by covering more pages |
| **P2** | **Answer Relevance** (judge) | **primary** | the second half of the step-4 generation pair already measured (Faith 0.661 / Ans.Rel 0.852) |
| S1 | page-level R@k at the **equal slot budget**, ceiling-normalised | secondary | a recall number the summaries can inflate by construction — reported, never the decision |
| S2 | **context tokens fed per arm** | guard | if the arms are not token-comparable, say so rather than calling it a win |
| S3 | per-query paired deltas + **W/L/T** | guard | churn vs a uniform effect |

**Judge:** `Qwen/Qwen3-VL-8B-Instruct` — cross-family from the generator (`openai/gpt-oss-20b`), per
the standing rule. **Generator:** the shipped `openai/gpt-oss-20b` for both arms; a generator swap
would be a second variable.

---

## 3. Pre-registered outcome rule

Quoted from the §G2 plan §4, unchanged:

> **G2 is built** iff V1's gate passes **and** V2 holds (all communities connected) **and** V5's
> ablation shows a positive contribution on overview queries. If V5 is null or negative, **G2 is
> recorded as measured-and-negative** and the summaries are not wired into retrieval — the same
> disposition §G1 received.

Fixed **now**, before any number exists:

- **Positive** = the paired 95 % CI on **P1 (Faithfulness)** excludes 0 in the treatment's favour,
  **and** P2 does not move significantly against it.
- **Null** = either CI straddles 0. **Negative** = P1 resolves against the treatment.
- **Stopping rule: one run of the pre-registered comparison. No extension.** §4 already says a null
  is a result; extending the query set to chase one is the §D1 mistake.
- A **null at the equal slot budget is a null about *that* budget**, not evidence that summaries
  cannot help retrieval — the same reading §G1's ablation carries. Candidate *expansion* (feeding
  the summaries' own source chunks) is a different treatment and is **NOT** tested here.
- If P1 is positive but **S2 shows the arms are not token-comparable**, the result is reported as
  **confounded**, not positive.

---

## 4. Verifiers (each must be able to FAIL)

| # | check | why it discriminates |
|---|---|---|
| **V5a** | the artifact's summaries are the ones the build actually read — a **content digest** of the loaded summaries recorded in the eval artifact | §I44: evidence not on disk is not evidence. An eval that read a different artifact than the one on record is unverifiable |
| **V5b** | the re-derived community → chunk join reproduces the summary's own provenance: **spot-check ≥ 10 communities** and confirm every chunk id resolves in SQLite and the concept set matches the community | the join is re-derived, not stored; if it drifts, the treatment arm reads the wrong passages |
| **V5c** | **both arms see the same slot count** (asserted, not described) and S2 records the token counts | the whole design rests on this; a silent 2-vs-8 comparison is the §G1 defect |
| **V5d** | the **judge is cross-family** and named in the artifact, with its failure count | the §D11 class: a dead judge leaves the columns blank and the artifact still looks complete |
| **V5e** | the control arm reproduces a **known** number — re-run the RAPTOR-only overview path alone and match step 4's Faith/Ans.Rel | a control that does not reproduce cannot anchor a delta |
| **V5f** | a **negative control**: run A vs A (the same arm twice). The CI must straddle 0 | if A-vs-A resolves, the instrument is broken and no A-vs-B number means anything |

**V5f is the cheap one and it is not optional** — it is the only check that can catch an instrument
that manufactures a delta.

---

## 5. Cost, and what it is spent on

| stage | cost |
|---|---|
| build 1a–1c | local code, no LLM |
| embedding ~200 summaries once + 40 query vectors | ~240 dense-lane calls, minutes |
| 4 arms × 40 queries generation | **160** generator calls |
| judge: faithfulness (claim extraction + per-passage entailment) + relevance | **O(1,000–3,000)** judge calls — step 4 measured the pair at this order |
| **total** | **one cluster session, no re-ingest, no graph write, no Qdrant write** |

⚠️ **Serialize against other cluster-LLM work.** §I23 measured shared-GPU contention collapsing a
build's throughput ~8×; do not run this beside a card re-run or a graph rebuild.

---

## 6. Signoff points (owner)

1. **The level choice.** Level 2 (res 0.5, coarsest) is pre-registered as the primary. V3's finding
   is an argument for the coarsest level and an argument against trusting the leaf level — but it is
   a judgement, so it is yours.
2. **The slot budget.** 2 slots is chosen to match the control exactly. A larger budget (8, 16) is a
   *different* experiment (summary map-reduce proper) and would need its own control with the same
   budget.
3. **Whether C and D run at all.** They are sensitivity arms and cost real judge budget. Default:
   run only if the primary resolves or the owner asks.
4. **The disposition if V5 is null.** §4's rule already says recorded-and-negative and not wired.
   Confirm, since it is the one outcome that closes §G2 with nothing shipped.

---

## 7. Explicitly NOT in this plan

- **No wiring before V5.** `--community-summaries` ships **off**; the app path is unchanged until the
  owner reads the number.
- **No re-generation of the summaries** except if the owner picks a different level — and then the
  checkpoint (§I53) makes it cheap, not free.
- **No candidate expansion**, no map-reduce over all 181 communities per query, no point-query
  routing.
- **No §G4** (global/local/drift modes — brainstorm) and **no §G5/§I2** (genuine 1–2 hop traversal;
  `hop_distance` is a constant 0 — a separate open item).
- **No change to the DA, visual or graph lanes.**
