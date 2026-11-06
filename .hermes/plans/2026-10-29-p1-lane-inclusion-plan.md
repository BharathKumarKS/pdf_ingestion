# Plan — put every lane through ONE fusion: RAPTOR (overview) into the pool, DA + graph into the fusion

**Status: PLAN ONLY — nothing implemented, nothing run.** Written for approval. Every step carries a
verifier that can FAIL, and the two expensive/irreversible steps (the index write, the cluster run)
are separately gated.

---

## 0. What the code actually does today (verified in the tree, not from the handoff)

There are **four** lane insertion points, and only the first is a fusion:

| # | lane | where it enters | through RRF? | code |
|---|---|---|---|---|
| 1 | dense (64→full rescore) + sparse + colbert | `store._qdrant_search` | **yes** — `_rrf_merge(rrf_k=1)` | `store.py:647-672` |
| 2 | DA | `store.search_with_das` — appended to the dense list **after `search()` returns** | **no** — post-fusion | `store.py:892-909` |
| 3 | graph | the **caller**, after `search_with_das` returns | **no** — post-fusion **and post-MMR** | `evaluate_rag.py:230-241` |
| 4 | RAPTOR | `store.search_raptor` exists, but the eval path **never calls it** | **n/a** | caller only at `streamlit_app.py:589` (limit=2, shown separately, not pooled) |

⚠️ **Correction to the report's scope note.** `logs/p1/step10/nomic_gap_report.md` says *"The DA lane
is merged inside the fusion, before dedup and MMR."* Reading the code: DA is appended **after** the
fusion (`search()` has already returned a fused list) and before dedup/MMR. So DA **never
participates in RRF** — it is an unranked append, one stage earlier than the graph lane. The report
line is imprecise and should be corrected in place.

⚠️ **Two defects that follow from the append pattern.**
- **Graph hits carry a fabricated score.** `evaluate_rag.py:240` does `gh.setdefault("score", 1.0)`,
  so a graph hit passes the `hits_above` threshold gate (`:246`) **by construction**, whatever the
  threshold. RRF would remove this (it ranks by rank, not score).
- **Every one of DA / graph / RAPTOR swallows its own failure with NO counter** — `search_da` catches
  and returns `[]` (`store.py:761`); the graph and RAPTOR callers catch and warn
  (`evaluate_rag.py:243`, `streamlit_app.py:594`). This is exactly the §I96 class the ColBERT
  counter (already landed this session) closes for one lane. Until they are counted, a run cannot
  tell a lane that returned nothing from a lane that was never live.

**Measured state of these lanes (from the register — the honest starting point):**
- **DA is a measured HARM**: −0.0262 at the endpoint (§I56).
- **graph as wired adds pool pages and LOWERS MRR** 0.781 → 0.667 (report §6).
- **RAPTOR is absent from v3** — verified live this session: `knowledge_base_v3` has **3,796** points,
  lanes `colbert, dense_64, dense_full` + `sparse`, and **no `raptor_summary` nodes**.
- **overview is the worst type**: R@20 **0.1882** against its ceiling **0.3992**, coverage **0.1937**.

⇒ The registered question is **NOT "does this improve things"** — it is *"does making a lane a
first-class RRF participant change its sign and its ordering, versus appending it?"* For DA and graph
the null (or a continued harm) is a real, recordable outcome.

---

## 1. Design

**One fusion entry point.** Add `store.search_fused(...)` (name TBC) that:
1. collects each lane's **ranked** list — dense(+sparse+colbert), DA, graph, RAPTOR;
2. fuses **all** of them with `store._rrf_merge(..., rrf_k=1)` and **per-lane weights** `w_L`;
3. then dedup → MMR → (rerank unchanged).

`search_with_das` stays as-is for the current wiring; `search_fused` is the new path, so F0 (control)
and the arms differ by **one toggle**, not by a fork.

---

## 2. Steps, each with its verifier

### S1 — Count the DA, graph and RAPTOR dropouts (prerequisite; sibling of the ColBERT counter)
Add `da_dropouts`, `graph_dropouts`, `raptor_dropouts` (+ `last_*`) beside `colbert_dropouts`,
incremented in each `except`.
**Verifier:** per lane, a unit test that forces the failure and asserts the counter increments, and a
negative control (success → no increment); **mutation proof** (delete the increment → that lane's test
fails, and only it); a **live probe** per lane against the cluster. *Cost: config-only.*

### S2 — RAPTOR into `knowledge_base_v3` (B1/B2) — ⚠️ THE ONLY INDEX WRITE
Run the project's own RAPTOR pass for the tenant (`run_phase2.py --raptor-only`, per the handoff).
**Expected: 3,796 → 3,869 points (+73 `raptor_summary` nodes).**
**Verifier:** (a) `scripts/verify_collection_lanes.py --collection knowledge_base_v3` exits **0** and
reports **raptor 73, 0 gaps** (its raptor requirement correctly excludes `colbert` on summary nodes);
(b) the 73 nodes' **ids and payload sha match `knowledge_base_v2`'s** raptor nodes — they are the same
summaries, carried, not silently regenerated; if they differ, that diff is the finding, recorded;
(c) the **chunk count is unchanged at 3,796** — nothing else moved; (d) a read-back that
`store.search_raptor` returns the 73-candidate result on an overview query.
⚠️ **Gate: a write. Approval before running.**

### S3 — Wire the RAPTOR lane onto the eval path (read-only code)
Call `search_raptor` in `evaluate_rag.run_retrieval` for `query_type == "overview"`, and feed it into
the fusion (S4).
**Verifier:** a unit test that `search_raptor` **is called** for an overview query and **is not** for
factual/multihop; a test that its hits reach the pool **before** dedup/MMR; and that the artifact
records the raptor lane count **per query** (so a silent zero is visible).

### S4 — The fusion refactor (read-only code)
`search_fused` as in §1, with per-lane weights.
**Verifier:** a unit test asserting (a) every lane's hits carry an **`rrf_score`** — i.e. they went
through `_rrf_merge`, and **no** candidate is appended with a fabricated score; (b) a candidate's
fused rank **depends on its rank within its lane** (reverse a lane's order → the fused order moves);
(c) the fused set is a **superset** of the control's per-lane sets (no lane's candidates vanish);
(d) setting a lane's weight to **0 removes its contribution** (the weight is load-bearing, not
decorative). Mutation-prove each.

### S5 — The measurement (pre-registered, D6.1 — pre-registration committed ALONE before the run)
**Arms — ONE lane change each, because they are mutually confounding:**
| arm | change vs F0 |
|---|---|
| **F0** | control — today's wiring (DA post-fusion, graph post-MMR, no RAPTOR) |
| **F1** | DA **into** the fusion |
| **F2** | graph **into** the fusion (instead of the post-MMR append) |
| **F3** | RAPTOR lane added (S2+S3) |
| **F4** | all three fused, + lane weights (§E2) |

**Endpoint:** product endpoint, paired vs **F0**, per type. **Primary per arm = the type the lane
targets** (graph → multihop, RAPTOR → overview; DA → all). HyDE frozen via the cache.
**Verifier (guards):** (G1) **lane health per query** — S1's counters + the ColBERT counter; **no arm
may be scored on a reduced lane set**; (G2) pool / R@20 invariance where a lane should not move them —
if they move, VOID; (G3) **anchors** — F0 reproduces T0/T4's rows; (G4) the per-query CE
`reranker.fallbacks` flag (reranked metrics valid); (G5) the composition/`rrf_score` check of S4
re-asserted on the run's own pools.
⚠️ **Gate: the long cluster run. Approval before launch.**

---

## 3. Order and dependencies

```
S1 (counters) ─┐
               ├─> S4 (fusion entry point) ─> S5 (measurement)
S2 (WRITE v3) ─> S3 (wire RAPTOR) ─────────┘
```
- **S1 is independent** of the rest and protects every number in S5.
- **S2 must precede S3** (the lane cannot be wired before it exists).
- **S4 enables all three arms**; do it once.
- **S5 is last** and is the only long run.

## 4. What this plan does NOT claim
- It does not claim any of the three lanes will improve the endpoint. DA and graph are currently
  measured harms; the plan measures whether fusion-inclusion changes that.
- It does not ship lane weighting (§E2) — F4 is exploratory and is priced separately.
- It does not touch the rerank-query policy (the current session's task) — that is a separate change
  to the CE's input, upstream-independent of the pool, and the two must not be run in the same arm.
