# HANDOFF.md — current work state

> **Living document — where we are *now*, not what the system is.** The durable map is
> `ARCHITECTURE.md` (read **§8 Invariants and traps** before your first change); the backlog is
> `IMPROVEMENTS.md`. Keep this file short — it loads into every session.
>
> **Last updated: 2026-10-14** · `feat/p0-9-gold-dataset-v2` · P0 items 1–8 done; **P0-9 (gold
> set) — Sessions 1–3c, 3d, 3d-ii done; Session 4 partly done (v2 assembled + abstention wired +
> decision pre-registered; the A/B run is blocked on the cluster).** 3c's overview lane is
> complete: **40 overview queries**, topics derived from the book's own section headings, every one
> scan-labelled over the whole book (min 22 / median 58 / max 314 pages — none narrow); negatives
> grown 23 → **34**. **3d settled the §B4a fork on option (a)** (commit `4697961`). **3d-ii is done**
> — visual generation path + D8 judge variant + scan (commit `3a18da4`); **33 usable visual queries**
> of 40 (§B4d, commit `18250f1`). **v2 is assembled** (commit `e69c347`): **168 answerable + 34
> negatives = 202** (16.8%). Next: **run Session 4's A/B** (see "Session 4" below) — blocked until
> the cluster router is back.
> If this date is old, re-check `git log --oneline -5` and `git status --short` first.

---

## Scope decision (settled)

**Single-user now.** The `tenant_id` plumbing exists but is **not enforced** — there is no auth,
and the UI takes the tenant from a text box. Deliberate deferral: **multi-tenancy is the final
stage, after metrics are solid.** Do not "fix" auth or tenant isolation while working on metrics,
and do not add new `tenant_id` defaults.

---

## Current focus — P0-9, the gold-set rebuild (Sessions 1–3c built; run 3c + 3d next)

Gates all of P1. **Required-`N` is now measured** (Session 1, below). Two documents, both committed:

| Doc | Purpose |
|---|---|
| `.hermes/plans/2026-10-06_174001-p0-9-gold-dataset-v2.md` | Full plan: tasks 0–8, decisions D1–D10, power analysis. **Read only your task's section** — do not load all 1044 lines. |
| `.hermes/plans/p0-9-SESSIONS.md` | The session split: which tasks belong in which fresh session. |

### Session 2 delivered 2026-10-12 — the tools exist (no large LLM spend)

| Tool | What it does now |
|---|---|
| `scripts/generate_gold_dataset.py` | + `--multipage-count`: overview/multihop questions from distant page triples (`min_gap` 60). D10 applied — `max_tokens` 512→2048, and an empty generation batch retries, logs the raw response and **raises** instead of silently returning `[]`. |
| `scripts/validate_eval_calibration.py` | Parallelized (Task 4a): one open PDF + per-page image/text cache, disk verdict cache keyed by (query_id, page, model, prompt-hash), thread pool (`--workers`, default 8), one shared `httpx.Client`. D9 — each page judged from its rendered **image** plus full text, not `text[:800]`. New `--ramp-probe`. |
| `scripts/expand_gold_labels.py` | Widens `relevant_pages` to every page that answers the question, via the two-pass scan. `--dry-run` / `--limit N`. |
| `scripts/generate_negatives.py` | Three-tier negatives, accepted only if a full scan finds no YES page. `--dry-run` / `--n N`. |

Verified: each tool passes `--dry-run` and a stubbed `--limit`/`--n` probe; the hot pages are
judged once, not twice; a re-run makes zero judge calls. **D9 verified live** against the cluster
VLM (p254 → YES "½mv² is kinetic energy", p3 → NO copyright page, ~0.8 s/call). Suite at the
floor: **211 pass / 5 fail / 5 skip**.

### Session 3 delivered 2026-10-13 — the scan ran (all three steps, exit 0)

Judge `Qwen/Qwen3-VL-8B-Instruct` @ `http://10.0.10.70:8000`, `--workers 8` (ramp-probe knee:
4.21 calls/s, 0 errors; 16/32 collapse to ~1.2/s from queueing). Commits `1870dc9`, `8e81572`.

| Artifact | Content |
|---|---|
| `data/eval_queries_gold.json` | 103 questions — 55 factual / 8 overview / 40 multihop |
| `data/eval_queries_gold_expanded.json` | 66/103 queries widened to >1 page (max 134), scan-expanded |
| `data/eval_negatives.json` | 24 negatives, 8 per tier — **see caveat** |

**Four blockers had to be fixed first** (Session 2 only ran `--dry-run`/stubs, so they survived):
the run-order command omits `--judge-backend openai` (defaults to Anthropic → 401); `call_llm_raw`
posted to `{base}/chat/completions` (gateway serves only `/v1/...` → 404); 2048 `max_tokens` was
still too small for `gpt-oss-20b`'s reasoning trace (content came back null/truncated → raised to
8192); and the model's LaTeX (`\(m v\)`, `\frac`, `\theta`) is not valid JSON (`\f`,`\t`,`\n`,`\b`
even decode to control characters) → `_extract_questions` now escapes every backslash but `\"`/`\\`.

> ✅ **Negatives re-verified (Session 3b) — resolved.** The term-bearing re-scan now covers every
> page carrying a negative's key terms (±2) — the pages the stride-15 scan never reached. Result:
> **1 definitively invalid** — `neg-nea-004` (carbon-14 half-life) is answered on **p107** →
> **dropped**; `neg-in_-001`'s only YES was on **p944, the index** → now capped to PARTIAL by the
> back-matter gate (below), so it stays. **6 kept but flagged `needs_review`** because the judge
> returns content PARTIALs (the book *discusses* the topic): `in_-001, in_-002, in_-005, in_-007,
> in_-008, nea-008`. **17 clean.** The plan's fear that near_miss would "mostly be rejected" did
> **not** materialise once the term pages were actually scanned.
> Evidence: `logs/p0-9/report_negatives.py`, `logs/p0-9/prune_negatives.py`, `logs/p0-9/session3b/`.

### Session 3d delivered 2026-10-13 (code landed; the queries followed as 3d-ii)

Commit `4697961` on `feat/p0-9-gold-dataset-v2`. **§B4a fork settled on option (a)**, on evidence:
the cluster colpali endpoint was re-probed and is **still down** (HTTP 500 on all five request
shapes, ~3.1 s; the **colbert** endpoint on the same host returns 200 in 0.15 s), so option (b) /
ColQwen3 is blocked on the cluster. Option (a) verified end-to-end **offline** — `process_queries`
gives an `(N, 128)` matrix whose patch_dim matches the stored pages, L2-normalised, no re-ingest.

| Deliverable | State |
|---|---|
| (1) text-query path | ✅ `ColPaliEmbedder.embed_query_text` + stub |
| (3) visual metric | ✅ `evaluate_rag.run_visual_retrieval` — text → MaxSim over `visual_knowledge_base`, page-level metrics reused; visual queries now score instead of being skipped |
| (2) visual queries + labels (30–40) | ✅ **done as 3d-ii** — 33 usable of 40 (see "Session 3d-ii" below) |

Tests: +4 stub text-path, +3 visual-lane. Suite **225 pass / 5 fail** (same 5 pre-existing).

**Found and registered (`IMPROVEMENTS.md` §B4b):** the local `visual_knowledge_base` holds
**2,835 points for 945 pages — every page exactly 3×**, one doc id (`b2d9fb56`); top-20 held only
**7 distinct pages**, capping the whole lane's Recall@20. `clean_stale_visual.py` cannot catch it
(keys on `document_id`), and the visual doc id ≠ the text doc id (`5fcc9006`). Nothing was deleted;
the eval lane dedupes by page meanwhile. Root fix folded into the E1/E2/E3 re-ingest pass.

### Session 3d-ii delivered 2026-10-14 — the visual queries and their labels

Commit `3a18da4`. Three deliverables, all built: (1) the **visual generation path**
(`generate_gold_dataset.py --visual-count` — text-only generator, one figure question per
`<!-- image -->` page in the content region) → `data/eval_queries_gold_visual.json` (**40**,
source pages 37–915); (2) the **D8 visual judge variant** (`_VISUAL_JUDGE_PROMPT`, strict) plus the
anchor window, in `validate_eval_calibration.py`; (3) the **book-wide scan** →
`data/eval_queries_gold_visual_expanded.json`.

| Result | Value |
|---|---|
| Generated | 40 visual questions |
| **Usable after hygiene** | **33** (23 single-page, 7 two-page, 2 three-page, 1 four-page) |
| Uncalibrated (no YES page) | **6** — `vis-004, 009, 016, 017, 023, 025` |
| Dropped as non-specific | **1** — `vis-024` (71 YES pages — "the diagram of the wave signals") |

**The 6 uncalibrated are a scan/judge gap, not generator hallucinations** — the source pages carry
the figures the questions describe. Two causes (§B4d): `vis-004/025` found the *correct* page but
the strict VLM graded it **PARTIAL**, and `expand_gold_labels.py:88` keeps **YES only**;
`vis-009/016/017/023` got NO everywhere, even in the ±4 anchor window. A re-scan that credits a
correct PARTIAL, or a specificity-gated generator, would recover them — **deferred** (needs cluster
VLM calls). Tests: `tests/test_visual_queries.py` (8, passing); suite **236 pass / 5 fail** (the
same 5 pre-existing).

### Session 4 delivered 2026-10-14 (partly — the harness, blocked on the cluster)

Commit `e69c347`. **`data/eval_queries_v2.json` is assembled** by the new `scripts/build_gold_v2.py`:
**95 text** (55 factual + 40 multihop) + **40 overview** (3c) + **33 visual** (3d-ii, calibrated
only) + **34 negatives** = **202** (16.8% negatives). The 8 pre-3c overview entries inside
`gold_expanded` are dropped (superseded); v1 is not merged (D6). `tests/test_gold_schema.py` passes
(6). The **abstention metric is wired** into `evaluate_rag.py`: a negative
(`answerable: false`) measures `abstained` (a declining answer OR a top-1 score below the
threshold), negatives are excluded from the by-type retrieval averages, and an `abstention` block
prints under the summary table. Suite **242 pass / 5 fail** (same 5).

**The decision is pre-registered** before any numbers exist:
`.hermes/plans/2026-10-14-p0-9-4-preregistration.md` — reranker stays iff it beats no-reranker on
R@20 by more than the 95% CI on the paired difference; abstention must beat the majority baseline.
Scope decided there: the **text-lane funnel runs on 135 queries and excludes the 33 visual**
(the funnel has no ColPali lane, so visual queries would dilute the delta); the visual lane and the
negatives are measured by `evaluate_rag.py`. `funnel_boundary_recall.py` gained `--include-visual`
(default: excluded).

> ⛔ **BLOCKED 2026-10-14 12:45 — the cluster router is down.** The `--limit 2` probe to
> `http://10.0.10.70:8000` failed with `[Errno 61] Connection refused` on the **LLM** (HyDE →
> empty), **SPLADE**, and **rerank** endpoints; only the local dense lane worked. The same router
> answered at **08:15** today (the 3d-ii scan), so it went down since. **No A/B numbers can be
> produced until it is back.** The probe also ran against the *local* Qdrant — the run order needs
> `export QDRANT_HOST=10.0.10.65` (the cluster index, 5,135 points), not `data/qdrant`.

**To resume** (once the router answers): the two funnel commands + `required_n.py` and the
`evaluate_rag.py` run are written out in §3 of the pre-registration file. Nothing else blocks.

### Next actions before Session 4 (ordered — do in a FRESH session)

1. ✅ **DONE (3b) — Prune + re-verify the negatives.** Dropped `neg-nea-004`; `neg-in_-001` kept
   (its only YES was the index, now gated); 6 flagged `needs_review`. `data/eval_negatives.json`
   now holds 23 negatives. Residual uncertainty (content PARTIALs) → Session 5.
2. ✅ **DONE (3b) — Stop index/back-matter pages counting as hits.** Two layers: (a) the judge gate
   caps index pages at PARTIAL (scanner, deterministic — not prompt-only, since the VLM is
   inconsistent on the index); (b) `max_content_page` excludes back matter from retrieval. The gold
   labels were checked and carry **no** back-matter pages. See "Index-page false hits" below.
3. ✅ **DONE (3c) — the overview lane.** **40 overview queries**, topics from the book's section
   headings, every one scan-labelled over the whole book (stride 4 + term sweep, ~36k judge
   calls). Round 1 produced 40 topics of which 1 (`ovw-026` Energy-Momentum Tensor) was absent
   from Vol 1 and 8 were narrow (≤15 pages); **round 2 replaced those 8 with 9 new book-spanning
   topics** (min 22 / median 58 / max 314 pages). Negatives 23 → **34** (2 dropped as answerable
   by the term-bearing re-scan, 9 flagged `needs_review`).
   Assembled: **135 answerable + 34 negatives = 169 → 20.1% negatives**.
   Artifacts: `data/eval_queries_gold_overview_expanded.json`, `data/eval_negatives.json`.
   Targets + deviations: `.hermes/plans/2026-10-13-p0-9-3c-preregistration.md` (Outcome + Round 2).
4. ✅ **DONE (3d-ii) — visual queries + labels.** Built the **visual generation path**
   (`generate_gold_dataset.py --visual-count`, text-only generator, one figure question per
   `<!-- image -->` page in the content region) → `data/eval_queries_gold_visual.json` (**40**,
   pages 37–915); the **D8 visual judge variant** (`_VISUAL_JUDGE_PROMPT`, strict) + the anchor
   window in `validate_eval_calibration.py`; the book-wide scan →
   `data/eval_queries_gold_visual_expanded.json`. **33 usable** of 40 (6 uncalibrated, `vis-024`
   dropped as non-specific) — **§B4d**. Commit `3a18da4`.
5. **Normalise the gold labels' page numbering** (`IMPROVEMENTS.md` §D4). `relevant_pages` mixes DB
   page numbers (from the generator) with PDF page numbers (from the scan); measured, they differ by
   0/−1 on ~45% of pages. Pick one numbering and re-derive `relevant_pages` **before** Session 4
   assembles v2, or the A/B deltas carry about a page of label noise.

### Index-page false hits (why + where)

**✅ FIXED (Session 3b).** (a)+(b) done as one deterministic gate in
`scripts/validate_eval_calibration.py`: `back_matter_start()` walks the trailing index run
(structural — heading marker or ≥35% of lines are "Term, <page-ref>" entries; start = **p937** for
Vol 1) and `apply_page_gate()` caps a YES there at PARTIAL. It is applied to the **verdict**, not in
the prompt, so the 12k-entry verdict cache stays valid — and it does not trust the 8B VLM, which
said NO on the index for one question and YES for another. (c) done as a retrieval bound:
`max_content_page` (config + `store.py`), set to **936** in `.env`. (d) `tests/test_backmatter_gate.py`.
Still open, and the durable fix: page bounds cannot be exact — the payload `page_number` is offset
from the PDF page index by 0/−1 on ~45% of pages, and DB page 936 holds **both** content and index —
so the real fix is **chunk-level classification at ingest: `IMPROVEMENTS.md` §E5**, folded into the
E1/E2/E3 re-ingest pass. The interim bound leaves ~15 index chunks (0.3%) retrievable; do not chase
the remainder with page arithmetic.

Original analysis (why): retrieval excludes front matter but **not** back matter: `store.py` filters on
`min_content_page` as a **lower bound only** (`page_number >= min_content_page` — lines 193, 228),
so the index/bibliography at pages ~940–968 stays retrievable. A `_NON_CHAPTER` keyword list
already exists in `store.py` (`"## subject index"`, `"## index\n"`, `"bibliography"`, …) but is
wired **only** into the RAPTOR rebuild path, not retrieval or the scan. Layered fix, cheapest first:
(a) judge criterion — YES means "this page contains the answer", index/contents/cross-reference
pages are PARTIAL at most (fits D8's graded 0/1/2, so the strict YES-only primary is unaffected);
(b) deterministic backstop — detect index pages by structure and gate them, don't trust an 8B VLM
(it said NO on the index for one question and YES for another); (c) corpus hygiene — an upper bound
(`max_content_page`) or exclude non-chapter pages at ingest, which removes the false-hit surface for
the product too (needs a re-ingest — its own item, honour the `clean_stale_*` ordering); (d) make it
visible — an index-page probe in the test suite, and/or a "fraction of retrieved pages that are
back matter" metric.

**Hypothesis (unverified) — index pages may explain the overview number.** Overview queries are the
ones an index page looks superficially good for, and overview MRR **0.191** is the one genuinely bad
number (P1 item 10). Cheap test: count back-matter pages (≥ ~940) in the retrieved sets for the
overview queries — if they are over-represented, the index is polluting the metric and the ranking
work in item 10 should not start until it is excluded.

### Decisions settled 2026-10-12 (do not re-litigate)

| # | Decision |
|---|---|
| **D1** | **Sequential design** — start at 40, extend in blocks of 30. **Recompute σ_d per comparison** (it differs: reranker 0.2315 vs merge 0.118). Do **not** stop naively at the first CI that excludes 0 — pre-register the stopping rule. |
| **D6** | **Fresh file** `data/eval_queries_v2.json`; **do not reuse v1's queries** — v1's provenance is mixed (early labels were retriever-derived → circular). Consequence: **all historical artifacts become non-comparable**; re-run the whole A/B series on v2. Do **not** carry v1's visual queries over — regenerate or calibrate them. |
| **D8** | **Graded 0/1/2** (NO/PARTIAL/YES). Report **Recall@k on YES-only as the strict primary**, graded nDCG as the secondary. D6 removes the v1-comparability constraint that forced a binary choice. |
| **D9** | **Scan the page as an IMAGE** (`Qwen/Qwen3-VL-8B-Instruct` on the cluster) **plus full text** — not the current `text[:800]`. Prerequisite for Task 4. |
| **D10** | Raise `max_tokens` (512 → 2048); make an empty generation batch **loud and asserted**, not a silent `[]`; bounded retry; log the raw response on failure. |

Also settled (2026-10-06): **3-way RRF *with* the cross-encoder stays**; the reranker decision is
deferred to the powered test (F4b). The ColBERT `is_query` fix (`b4cb637`) is correct regardless
of its unresolvable effect, and **needs no re-ingest**.

### Why P0-9 blocks everything — five conclusions, all unresolvable at n=23

σ_d = 0.2315 (reranker comparison, **measured** — `IMPROVEMENTS.md` §F4b) → SE ≈ 0.05 at n=23.
Paired-power **`N = 0.4206/δ²`** for the reranker: **62** to detect the observed 0.083, **169** at
δ=0.05, 43 at δ=0.10. The merge comparison is quieter (σ_d = 0.1184 → 45 at δ=0.05). Recompute σ_d
per comparison — do not reuse one number across comparisons.

| # | question | measured | verdict |
|---|---|---|---|
| 1 | does the cross-encoder help? | 0.651 → 0.569 (**−0.082**) | blocked |
| 2 | ColBERT better as voter or judge? | 0.598 vs 0.651 | blocked |
| 3 | did the ColBERT `is_query` fix help? | −0.022 / −0.049 | blocked |
| 4 | abstention precision | **unmeasurable** — zero negatives | blocked |
| 5 | any per-query-type claim | ~5 queries/type | blocked |

**Do not run another A/B on the 23-query set.** More measurements there generate more
unresolvable numbers, not more knowledge.

---

## P0 status

| # | Item | Evidence |
|---|---|---|
| 1–6 | baseline committed; silent fallbacks killed; sklearn pinned + classifier schema-checked; config-invariant tests; doc drift fixed; eval gate + CI | `6381f7b`, `c3a8727` |
| 7 | metric set fixed (`Precision@k` → `Recall@k` + `Hit@k`) | `1dad73f` |
| 8 | judge lane measured — **1040 judge calls, 0 failures** | `dce5efd`, `data/eval_results/p0-judge-canonical_2026-10-06_0010.md` |
| 9 | **gold-set rebuild** | Sessions 1–3c done — `ca3324e`, `52d2179` (measure) + `5cbf564`, `4f112b0`, `fffc3b3`, `c9d8d0c`, `668cd0f` (tools) + `1870dc9`, `8e81572` (scan) + 3b (negatives pruned, index gate) + 3c (`871a5a4` tools, `a6971f3` 40 overview questions, then the book-wide scan) + **3d code (`4697961`)** + **3d-ii (`3a18da4`, `18250f1` — 33 usable visual labels, §B4d)** + **Session 4 partly (`e69c347` — v2 assembled 202, abstention wired, decision pre-registered)** on `feat/p0-9-gold-dataset-v2`; **next: run the v2 A/B — blocked on the cluster router** |

Test suite: **242 pass / 5 fail** (`uv run pytest tests/ -q -m "not slow"`). The 5 are
**pre-existing** — `tests/test_splade.py` (×2) hardcode a missing `tests/data/sample_physics.pdf`,
and 3 search tests return 0 results. **Not regressions; do not "fix" them here.**

---

## Session hygiene

Start each P0-9 stage in a **fresh** session (`/new`) and read only that stage's section of the
plan. The previous long session reached ~271k tokens/call with 2 lossy compactions behind it —
**do not continue P0-9 inside a compacted session.** See `p0-9-SESSIONS.md` for the split and the
handoff steps.

---

## Priority plan (agreed)

**P0 — make the numbers trustworthy.** 1–8 ✅ · **9 ⛔ gold set (active critical path)**

**P1 — then improve metrics** (all gated on P0-9)
10. Ranking — overview MRR 0.191 is the one genuinely bad number. Cheapest first: config
    (MMR λ / RRF) → the cross-encoder → hard-negative fine-tuning. **First check the index-page
    hypothesis in "Index-page false hits" above** — if back-matter pages are polluting overview
    retrieval, fix that before tuning ranking.
11. Calibrate the 7 `visual` queries (folds into P0-9).
12. Per-lane attribution in the eval report (which lane moves which query type).
13. Test the fallback chains — stub tests cannot reach them.
14. `render_math()` golden-file test — ends the LaTeX patch cycle (partly done).

**P2** abstention · guardrails · PPR · semantic caching · OKF cards

**P6 — kept, deferred to the very end:** NiceGUI migration. **Explicitly wanted — do not drop
it from the plan, and do not start it early.** Frontend stays Streamlit until then.

Full backlog, categorised by why each item is not done yet (queued / fix / deferred-by-decision /
gates), with cost classes and re-ingest ordering: [`IMPROVEMENTS.md`](IMPROVEMENTS.md).

---

## Verified facts — trust these over any doc

| Thing | Truth |
|---|---|
| Feynman Vol 1 PDF | **968 pages** (`mdls kMDItemNumberOfPages`) — README now correct; `Docs/synapse_full_report.pdf` still says 940 |
| Cluster `knowledge_base` | 5,135 points (5,051 chunks + 84 RAPTOR nodes), doc `6d55c52b` |
| SQLite `chunks` | 5,048 — the 5,135−5,048 gap is **unexplained; re-measure, don't trust** |
| Dense embedder | **Nomic 768d + 64d MRL** (`embedding_model` in `config.py`) |
| Reranker | `BAAI/bge-reranker-v2-m3` |
| Chunker | `chonkie.SentenceChunker` (class named `SemanticChunker`) |
| Intent classifier | 768d `LogisticRegression`, pinned `scikit-learn~=1.9`, schema-checked at load |
| Card types | **8** in `CardType` (single source for `DA_CARD_TYPES`) |
| Eval queries | 30 = 23 calibrated non-visual + 7 uncalibrated `visual` |
| Baseline (v1, 23 q) | Recall@20 **0.636** · MRR 0.365 · NDCG@6 0.377 |
| Judge lane (v1, 23 q) | Faithfulness **0.701 (a floor)** · Ans.Relevance 0.927 · Citation 1.000 |
| Judge gateway | **`http://10.0.10.70:8000`** — serves `Qwen/Qwen3-VL-8B-Instruct` (the D9 VLM) among 6 models; ~0.8 s per page judgment at concurrency 1. The P0-9 plan's `10.0.10.51:8000` is **dead**. |

---

## Traps

**→ `ARCHITECTURE.md` §8 (invariants and traps) and §11 (environment notes).** Read §8 before
your first change. The three that matter most for P0-9:

- **ColPali MaxSim is not 0-1** — scores run to ~1031; the configured threshold is 600.
- **Re-run `clean_stale_visual.py` after every Phase 3 re-ingest** (and `clean_stale_graph.py`
  after every re-ingest), or every page returns twice.
- **Retrieval is not bit-reproducible** (HyDE at temperature 0.3) — nothing below ~0.07 is
  measurable until HyDE is pinned. Pin it before any P0-9 A/B.
- **The judge must be a VLM, and `JUDGE_MODEL` is unset in `.env`.** The D9 scan sends the page
  **image**, so `--judge-from-env` alone judges with `openai/gpt-oss-20b` — text-only, it cannot
  see the page. Pass `--judge-model Qwen/Qwen3-VL-8B-Instruct` (and `--judge-api-base
  http://10.0.10.70:8000`) explicitly for the Session 3 scan.

---

## Unrelated to this project

The `reliability-lab` plugin injects a "[Reliability lab — pipeline A]" banner into the user turn
when this profile is armed (`mode: "A"`). It is **profile-wide**, so it leaks into unrelated chats.
Disarm with `/lab off`.
