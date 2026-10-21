# P1 Step 10 — the re-measure, on the rebuilt index. Execution plan.

> **Written 2026-10-18, after Step 8 attempt 5 succeeded.** Read `HANDOFF.md` first for current
> state, `IMPROVEMENTS.md` §D9/§D10/§D11/§D13 for the register entries this executes, and
> `ARCHITECTURE.md` §8 before changing code. This file is the *procedure*; it is not a register.
>
> **Preconditions — all met, re-verify rather than assume:**
> - `knowledge_base_v2` holds **3,796 points, all four lanes on every point** (`verify_collection.py`
>   exit 0). The old deployed `knowledge_base` (5,135 points, `dense_768`) is untouched (plan R1).
> - The query side is on the 1024d dense lane (Step 7b, 2026-10-17) — without it every funnel query
>   errors on a dimension mismatch (§E6).
> - The intent classifier was retrained at 1024d (96.6 % held-out, 2026-10-17).

---

## 0. Pre-register BEFORE any number exists

**This project's rule, and §D13 rests on it.** The previous ablation's decision rule was written down
before the run; repeating it from memory after seeing numbers is how an unresolved effect becomes a
decided one. Write `.hermes/plans/2026-10-18-p1-step10-preregistration.md` first, containing:

- the metric and the arm definition (funnel `B5b` R@20, rerank ON vs OFF, same HyDE cache, same
  collection, same query file);
- the decision rule: reranker stays iff `rerank − no-rerank` on R@20 exceeds the 95 % CI on the
  paired difference;
- **the honest power statement.** At the available n (135 text queries) the CI on the paired
  difference will be on the order of ±0.04. The last run's effect was 0.011 (§D13), so the rule may
  again be *unreachable*, not merely unmet. State up front what an unresolved result means —
  §D13's answer was "keep it enabled, do not extend the query set", and §5 forbids extending until
  an arm wins. Do not invent a new rule mid-run;
- what would falsify the *hypothesis* carried from §D13: the reranker's factual-lane loss
  (−0.0469, resolved on the old index) should be re-checked, not assumed.

**Verifier:** the file exists and is dated before the first arm's JSON. Nothing else.

---

## 1. Preflight — fail fast, do not let a blip write an empty report

```bash
export QDRANT_HOST=10.0.10.65
export QDRANT_COLLECTION=knowledge_base_v2
uv run python scripts/preflight.py
```

**Why this step exists:** §D11 — a cluster outage once made all 167 non-visual queries fail with an
`UnboundLocalError`, and `evaluate_rag.py` exited **rc=0 having written an empty report** (`0/0`
scope). The failure looked like a completed run. The `vectors_cfg` crash is fixed; the *lesson* is
that the preflight is the gate, and it must check the classifier width against `dense_dim` too.

**Verifier:** exit 0, and the report names the cluster endpoints as reachable. **Any non-zero →
stop.** Do not proceed to an arm.

---

## 2. The ablation — adapt the existing harness, do not write a new one

`logs/p0-9/run_session4_v2.sh` already does exactly this A/B (funnel rerank ON, funnel rerank OFF
with the **same** HyDE cache, `required_n.py`, then `evaluate_rag.py` with a cross-family judge). Copy
it to `logs/p1/step10/run_step10_v2.sh` and change:

- add `export QDRANT_COLLECTION=knowledge_base_v2` (both scripts resolve the collection from
  `cfg.qdrant_collection`, so this is the whole switch);
- write the arm JSONs to `logs/p1/step10/` (`v2_rerank.json`, `v2_norerank.json`) so the p0-9
  artifacts stay as the recorded baseline;
- keep the judge cross-family from the generator (`--judge-backend openai --judge-api-base
  http://10.0.10.70:8000 --judge-model Qwen/Qwen3-VL-8B-Instruct`). `--judge-from-env` falls back to
  the generator when `JUDGE_MODEL` is unset — self-grading, which the plan forbids;
- reuse `logs/p0-9/v2_hyde.json`. HyDE is per-query, not per-index, so the same cache keeps the two
  arms paired; regenerating it would add an LLM sample to the difference;
- keep `set -e` + the `ERR` trap.

**Verifier (per arm, before reading any score):**
- both JSONs exist and contain the **same query count** (135 text queries; `--include-visual` off);
- `required_n.py` prints the paired delta **with its 95 % CI** against the pre-registered δ;
- every R@20 is reported **÷ ceiling** as well as raw (§D9: v2's text-lane mean ceiling is
  **0.8016**, the overview lane's **0.3992** — a raw 0.14 on the overview lane is 35 % of its
  ceiling, not 14 %);
- **§D10 check:** RRF is not bit-reproducible at pool level, so `B4_rrf_union_100` / `B5_colbert_100`
  may differ between arms on a handful of queries. `B5b` (top-20) must be **stable**; if it moved,
  the A/B is void and must be re-run, not interpreted.

**Cost:** ~3 min/arm for the funnel with a warm HyDE cache; `evaluate_rag.py` is the expensive one
(~30–60 min of judge calls).

---

## 3. The gold labels' page numbers (§D4), before trusting any R@k

The labels were built against the old DB page numbering; the rebuilt index uses the parent
provenance map. §D4's fix landed with Step 7/8, so the labels must be re-derived against the new
path — otherwise every R@k is measured against the wrong pages.

```bash
uv run python scripts/calibrate_eval_pages.py      # read its --help first; not yet walked through
```

**Verifier:** §D4's own procedure — measure **both units on both paths**, expect **0** children
without a page and no ±1 cluster; then re-run `evaluate_rag.py` and compare per-lane R@20 against
§D12's recorded baseline (text **0.465**; factual 0.564 / multihop 0.619 / overview 0.178),
ceiling-normalised.

**Open risk — §D6:** gold labels can fall outside the retrievable window. If a lane moves oddly,
check this before believing the change is real.

---

## 4. Decide, then register

- **§D13** — close it with the verdict the pre-registration's rule produces, including "unresolved"
  if that is what the CI says. An unresolved verdict is a result, not a failure to get one.
- **§D4** — close once the labels are re-derived and the numbers hold.
- **§D9** — every reported number carries its ceiling.
- **HANDOFF.md** — move "Current focus"; record the artifact path under `data/eval_results/`.
- **The artifact is the source of truth** — every number quoted in the register must grep back to
  the file in `data/eval_results/`.

---

## 5. Explicitly NOT in this step

- **§I20** (`save_document` is not atomic: it commits SQLite before upserting Qdrant, so a failure
  leaves 3,796 chunk rows for a document with zero points). Decide **after** this step — it may want
  a second index build, which is exactly when atomicity matters. Registered, not fixed.
- **§I17** (ColBERT batch 4 / SPLADE batch 32 remain serial; measured on attempt 5 at 15.6 min
  combined). Needs its own **sustained** endpoint probe first — §I18's lesson is that a burst probe
  does not predict sustained behaviour, and this endpoint has already degraded under load twice.
- **Step 9** (Phase 2 cards + RAPTOR, Phase 3 visual + graph) — deferred by decision (§7 of the
  re-ingest plan: minimal first, then re-measure the text funnel; the ablation lives entirely in the
  text lane and none of Phase 2/3 gates it).
