# P1 — T3: THE LANE-COMPLETE v2-vs-v3 A/B (the full-funnel ship test) — pre-registration

> **Written 2026-11-02, BEFORE the run.** Per **D6.1** it is **committed ALONE**, and nothing measured
> is in it.
>
> Read first: `.hermes/plans/2026-10-26-p1-nomic-full-lanes-and-fusion-plan.md` **§D** (T3's definition),
> `IMPROVEMENTS.md` **§I85** (the base-lane null this completes), **§I89** (the finding that named the
> defect blocking it), **§I98** (lane inclusion into the fused pool — the *other* wiring),
> **§I104/§A** (the per-space query-vector fix that unblocks this), and
> `logs/p1/step10/stageF_product_endpoint.py` (the instrument this extends).

---

## 1. The question

**On the FULL funnel — every lane the product actually wires — does the nomic-768 index
(`knowledge_base_v3`, arm B) beat the incumbent qwen3-1024 index (`knowledge_base_v2`, arm A) at the
product retrieval endpoint, on the same 133 gold queries?**

§I85 answered this **on the base lanes only** (DA and graph both OFF, because a 1024-dim arm could not
query the 768-dim derived collections — §I12/§D15) and got a **NULL** (ΔcR@20 −0.0012, UNRESOLVED).
⚠️ **§I85's own note: "the full-funnel comparison is unmeasured."** §A (the per-space query-vector fix,
§I104) makes the derived lanes **reachable from either arm**, so the comparison is now **like-for-like**
and the question can be closed.

⚠️ **T3 is a MEASUREMENT, not a retrieval improvement.** §A is a **defect fix**; nothing in it says the
endpoint improves. T3 asks whether, once the derived layer is a **held-constant across arms**, the
base-lane null survives.

---

## 2. What this IS, and IS NOT

| | |
|---|---|
| **IS** | a **read-only** run against **two** collections (`knowledge_base_v2` @ `QDRANT_HOST=10.0.10.65`, 3,869 pts / qwen3-1024; `knowledge_base_v3`, 3,869 pts / nomic-768), 133 gold queries, **HyDE ON and frozen**, each arm on **the product's own** `evaluate_rag.run_retrieval` + `compute_retrieval_metrics`. |
| **IS** | **FOUR arms**: `A_off`/`B_off` = base lanes only (DA + graph OFF — the **§I85 reproduction**, the instrument anchor); `A_on`/`B_on` = **every lane ON** (DA + graph appended, the product's real wiring, `lanes=None`). |
| **IS** | the **full funnel as shipped**: `dense(low→full) + sparse + colbert → RRF → page dedup → MMR → cross-encoder`, **plus** the DA lane (appended after the fusion, `search_da`'s real placement) **plus** the graph lane (multihop only, appended after the fusion). |
| **IS NOT** | a collection write, a re-ingest, an embedder change, or a `src/` change. **Read-only.** |
| **IS NOT** | the **lane-inclusion** wiring (§I98's `search_fused(lanes=…)`, every lane competing on one RRF). That is a different, already-measured question. T3 measures **the product as it is wired**. |
| **IS NOT** | the RAPTOR lane. ⚠️ `evaluate_rag` never calls `search_raptor` (§I89 finding 3) and v3 holds **0** RAPTOR nodes — so RAPTOR is **absent from both arms** and is **not** part of T3. |

---

## 3. The quantities

```
arm set        {A_off, A_on, B_off, B_on}  x  133 queries
A = knowledge_base_v2 / Qwen3-1024   B = knowledge_base_v3 / nomic-768
P1             paired Δ ceiling-normalised R@20 (§I58),  B_on − A_on      (PRIMARY)
P2             paired Δ raw R@20,                        B_on − A_on      (PRIMARY)
secondary      R@100 (pool), Hit@20, MRR@20, nDCG@20, MAP, precision@20 + its ceiling
per type       factual 53 / overview 40 / multihop 40, for every metric above
lane deltas    A_on − A_off   and   B_on − B_off   (the derived layer's contribution, per arm)
lane liveness  DA hits per query, graph hits per query, in BOTH arms
```

The **`_off` arms reproduce §I85** (the instrument IS the registered one); the **`_on` arms are the
treatment**. The derived-lane deltas are **secondary** — they say what the added lanes did, not whether
nomic ships.

---

## 4. The READ RULE and predictions (fixed BEFORE the numbers exist)

* A delta is **RESOLVED** iff its paired 95 % CI excludes 0.
* **The decision is P1** (per §I85/§I57's rule): **RESOLVED positive** ⇒ the full-funnel ship test
  passes and v3/nomic ships; **UNRESOLVED** ⇒ measured-and-unresolved, nothing ships; **RESOLVED
  negative** ⇒ nomic is worse on the full funnel and does not ship.
* ⚠️ **Per-type floor is ~0.04** (n=40), double the n=133 floor (~0.020). A per-type effect below ~0.04
  is **not detectable** here and is reported as such, never as a null finding.

**Registered predictions (falsifiable):**

1. **Anchors (not findings):** `A_off` reproduces §I85's arm-A row and `B_off` reproduces §I85's
   arm-B row, within the n=133 floor on every shared metric.
2. **Liveness:** with §A landed, `A_on`'s DA and graph lanes are **LIVE** (non-empty) — the §I104 fix
   holds inside the full funnel, not only in the §A probe.
3. **The §I85 null survives:** `B_on − A_on` (P1) is **UNRESOLVED** — adding the derived lanes does
   not turn the base-lane null into a resolved nomic win.
4. **The derived-lane deltas are ≤ 0 or unresolved** per arm, largest for **multihop** (the graph lane's
   target). §I98 measured the graph lane as a **content harm** and DA as a **null**; T3 should not
   invert that.

**Falsification clause.** If **P1 resolves positive** on the full funnel, the base-lane null is
superseded: the derived layer is what carries nomic's advantage, and the ship decision flips. If **P1
resolves negative**, nomic is worse on the full funnel and the index swap is rejected outright.

---

## 5. Guards (each must be able to FAIL)

| # | check |
|---|---|
| **G1** | population **133**; per type **53 / 40 / 40**. |
| **G2** | **reachable pages == 888** (T0's recorded value) — the filter is the registered one. |
| **G3** | **zero errors** in every arm. |
| **G4** | **zero reranker fallbacks** in every arm (§I55 — a fallback returns the pool UNRANKED). |
| **G5** | ⚠️ **arm A's DA lane is LIVE** in `A_on` (`da_hits > 0` on ≥ 1 query) — the §A fix, asserted inside the full funnel. Today (pre-fix) it is 0 by the swallowed 400. |
| **G6** | ⚠️ **arm A's graph lane is LIVE** in `A_on` for multihop — the same fix on the second lane. |
| **G7** | **HyDE is frozen**: the §I73 cache serves **exactly the 93 HyDE-eligible queries** (53 factual + 40 overview); **a miss RAISES**, never a live LLM call. |
| **G8** | **`A_off` reproduces §I85's arm A** and **`B_off` reproduces §I85's arm B** on the shared metrics, within the n=133 floor. ⚠️ **This is the instrument check** — the `_off` arms are §I85's configuration, so if they move, the harness is not §I85's and nothing is attributable. |
| **G9** | **`A_off` and `B_off` are single-variable against §I85**: the ONLY difference from §I85's run is §A's code (which is a **bit-exact no-op** for the base lanes — §I104's A3). |
| **G10** | **determinism**: each `_on` arm run **twice** is bit-exact on every metric of every query (§I68 landed, so this is legitimate). A non-zero self-difference **voids** the arm. |

---

## 6. Bounds

* One corpus, one document (Feynman Vol. 1, 968 pp), one funnel. n=40 per non-factual type.
* The **cluster** (embeddings `10.0.10.70:8123`, reranker, LLM router `:8000`) is a **single point of
  failure**; the run is gated on all three answering before it starts, and a mid-run outage voids the
  affected arm (re-run). ⚠️ Measured 2026-11-02: the cluster dropped for ~30 min.
* **RAPTOR is absent** from both arms (not wired into the eval path; 0 nodes in v3). Stated, not hidden.
* **The visual (ColPali) lane is not on this path** and its queries carry no labels — out of scope.
* **Read-only**: nothing written to any collection, no re-ingest, no embedder change.

---

## 7. Verifier and mutation proof

* **Independent stdlib verifier** `logs/p1/step10/t3_verifier.py` — re-derives every aggregate, endpoint,
  CI and decision field from the **raw per-query arrays**, without importing the harness; re-checks
  G1–G10.
* **Mutation proof** `logs/p1/step10/t3_mutation.py` — one mutation per check, generated from the
  artifact's own field inventory; **no inert check** (every check reddened by ≥ 1 mutation, each
  mutation reddens its intended check).

---

## 8. Registration and what would falsify this

On completion: an `IMPROVEMENTS.md` entry (§I107 or next), a `HANDOFF.md` session-32 block, the artifact
`logs/p1/step10/t3_lane_complete.json` (per-arm `t3_arm_{A_off,A_on,B_off,B_on}*.json`), the verifier and
mutation proof, and the run log. **Read-only at run time. No collection write, no re-ingest.**

* **If G8 fails** (`_off` arms do not reproduce §I85), the harness is not §I85's — **fix before reading
  anything**; the run reports nothing.
* **If G5/G6 fail** (arm A's derived lanes are still empty), §A did not reach the full funnel and T3
  cannot be read as lane-complete — the finding is about §A, not about nomic.
* **If G10 fails** (an `_on` arm is not deterministic), that arm is void and re-run.
* **If P1 resolves** in either direction, the ship decision follows the read rule in §4.
