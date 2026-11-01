# P1 — 4A: SCORE-BASED FUSION vs RANK-BASED RRF — does replacing the rank sum with a normalized score sum move the endpoint? (pre-registration)

> **Written 2026-10-31, BEFORE any number of this run exists.** Per **D6.1** it is **committed ALONE**,
> and nothing measured is in it.
>
> Read first: `HANDOFF.md` (session 30), `IMPROVEMENTS.md` **§I100** (the fusion-order run — rank RRF is
> not beaten by any ORDER intervention), **§I92** (the cap/MMR attribution), **§I101** (5A),
> **§I102** (4B), `logs/p1/step10/levers_report.md` §4, and `src/pdf_ingestion/store.py:655-699` +
> `846-883` (`_rrf_merge`, the fusion this replaces).

---

## 1. The question

Every fusion test so far has kept the **rank** mechanism and moved a knob around it: §I92 the cap and MMR,
§I67 the width, §I100 the ORDER (MMR off / ColBERT off / dense-only / level-1 weights). **§I100's own
"NOT measured" list names the untried one:** *"score-based fusion (a normalised score sum instead of
rank-based RRF) — needs cross-lane score normalisation across incomparable scores (cosine / SPLADE /
maxsim); a separate design."* **This is that design.**

**The question: does replacing `Σ 1/(rrf_k + rank)` with a NORMALIZED SCORE SUM change the pool's
coverage, or the endpoint's nDCG@20?** Rank fusion discards the score MAGNITUDE (only order survives);
score fusion keeps it. Whether that helps or hurts is unmeasured.

---

## 2. What this IS, and IS NOT

| | |
|---|---|
| **IS** | a run on the product retrieval path with **one new, additive, inert-by-default** fusion method (`store._score_merge`). The three lanes are queried **identically** in every arm — only the merge changes. |
| **IS NOT** | the product path. ⚠️ **A score fusion is a RETRIEVAL-PATH CHANGE and is declared as one** (the §I67 §8(b) precedent: an exact-search/alternate-path run is "then not the product path"). The default path (`lane_weights=None` → `_rrf_merge(rrf_k=1)`) is byte-identical and pinned by a test. |
| **IS NOT** | a re-ingest, a model change, a named-vector addition, or a write to any collection. **Read-only; the new method is additive.** |
| **IS NOT** | a lane ablation. Every arm uses the SAME live lane set (dense + SPLADE + ColBERT where available), so a difference is attributable to the MERGE, not the lanes. |

---

## 3. The change under test — three normalisations of the same three lanes

The lanes produce **incomparable** scores (dense cosine; SPLADE sparse dot; ColBERT MaxSim), so the
normalisation **is** the experiment. Each lane's candidates are normalised **per query, over that lane's
own candidate set**, then summed (unweighted):

| arm | merge | formula |
|---|---|---|
| **S0** | **the product** — rank RRF, `rrf_k=1` | `Σ_lanes 1/(1 + rank)` |
| **S1** | **min-max** score sum | `Σ_lanes (s − min)/(max − min)` |
| **S2** | **z-score** score sum | `Σ_lanes (s − mean)/std` |

⚠️ **A lane with `max == min` contributes 0 in S1** (degenerate range) — recorded per query, not hidden.
⚠️ **The score sum changes WHICH candidates survive the truncation to the pool width** — so this is a
**composition change as well as an order change** (exactly §I100 item 5's O4 flaw). Stated here so a null
is not later read as a pure order test.

**Arms are computed from ONE lane query per query** (the lanes are identical across arms), so the run is
one lane pass + three merges + three cross-encoder passes per query.

---

## 4. The endpoint and the read rule

Endpoint = the product's: `store.search_with_das` shape (CE over the merged pool, top-20), the product's
lane set, HyDE ON and frozen, `mmr_candidates == reranker_fetch_k == 100`, page-level page-deduped unit
with **both ceilings** beside every number (§I93). **Reported per arm and per query type:** pool coverage
(reachable denominator), `R@20`, `R@100`, `P@20` + ceiling, `nDCG@20`, `MAP`, `MRR@20`, `Hit@20`.

**Read rule (fixed):** a paired Δ (S1 − S0, S2 − S0) is **RESOLVED** iff its paired 95 % CI (10,000
bootstrap resamples, seed 20261031) excludes 0; otherwise **null**.

**Registered predictions (falsifiable):**
1. **S0 reproduces the product** — its pool coverage and endpoint metrics match T0's fusion/ce rows
   (anchor, 1e-4). A failure here VOIDs the run.
2. **S1 and S2 are UNRESOLVED vs S0 at the endpoint** (|ΔnDCG@20| < 0.01) — the register has found no
   fusion-side lever, and the score magnitudes are dominated by the dense lane, which the rank fusion
   already orders well.
3. **S1/S2 change the POOL composition** (the surviving candidate set differs from S0's on a majority of
   queries) — the composition trap, measured rather than asserted.

---

## 5. Guards (each must be able to FAIL)

| # | check |
|---|---|
| **G1** | population — 133 queries, 53/40/40; 0 errors; every arm scored on every query. |
| **G2** | ⚠️ **the default path is INERT** — `_rrf_merge(rrf_k=1)` is byte-identical to the product's fusion on every query (S0 == the shipped pool). A unit test pins it. |
| **G3** | **the three arms share the SAME lanes** — per query, the three arms' input lane lists are identical (asserted on a lane digest). A failure means the lanes, not the merge, moved. |
| **G4** | **the normalisers are exercised** — each lane's raw `max > min` on a recorded fraction of queries; the degenerate-lane count is reported. |
| **G5** | **lane health** — ColBERT/SPLADE dropout counts per query, as §I96 requires (a lane-reduced call is a different pool). |
| **G6** | no NaN/null in any aggregate; page-dedup in every arm. |

---

## 6. Verifier and mutation proof

* **Independent stdlib verifier** `logs/p1/step10/score_fusion_verifier.py` — re-derives every aggregate
  from the artifact's per-query page lists and labels (not the harness's output), re-checks G1–G6, and
  re-runs the bootstrap with the same seed.
* **Mutation proof** `logs/p1/step10/score_fusion_mutation.py` — one mutation per check; **no inert
  check**; run before the numbers are read where the checks allow.

---

## 7. Registration

On completion: an `IMPROVEMENTS.md` entry (the finding, the three arms, the paired CIs, the composition
result, the deviations), a `HANDOFF.md` session-31 block, and the artifact
`logs/p1/step10/score_fusion.json`. **Read-only. No collection write, no re-ingest. The new method is
additive and inert by default.**

---

## 8. What would falsify this

* If S0 does not reproduce the product (G2/G3 fail), the harness is wrong and the run is VOID.
* If S1 or S2 RESOLVES POSITIVE at the endpoint (nDCG@20 CI excludes 0, positive), score fusion IS a lever
  and the register's "no fusion lever" reading is wrong — a new candidate opens.
* If S1/S2 RESOLVES NEGATIVE, the rank fusion is earning its place and the question is closed.
