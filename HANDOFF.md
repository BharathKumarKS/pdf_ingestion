# HANDOFF.md — current work state

> **Living document — where we are *now*, not what the system is.** The durable map is
> `ARCHITECTURE.md` (read **§8 Invariants and traps** before your first change); the backlog is
> `IMPROVEMENTS.md`. Keep this file short — it loads into every session.
>
> **Last updated: 2026-10-17 (late: **P1 Step 8 attempt 1 FAILED — transient stall at parent 260/341; §I16 blocks the re-run**)** ·
> `feat/p0-9-gold-dataset-v2` · P0 items 1–8 done; **P0-9 (gold set)
> is MEASURED.** Sessions 1–3c, 3d, 3d-ii and **Session 4/4b (all four steps) are done.** The v2 A/B:
> **rerank vs no-rerank R@20 Δ −0.0101, 95% CI [−0.0299, +0.0097] → UNRESOLVED at n=133** (the
> pre-registered rule is not met and cannot be met at a feasible n — §D9). **Step 4 ran 2026-10-16
> 20:13–21:22** (`--skip-visual`, `logs/p0-9/session4b_step4.log`) and measured the second half:
> **abstention 17/34 = 0.500** (> the 0.0 majority baseline → **met**; half the negatives still
> answered) and the text-lane generation metrics (**Faith 0.661 · Ans.Rel 0.852 · Citation 1.000**,
> n=133); the **visual lane** was measured separately (**33 q, R@20 0.960**). **Reranker decision:
> keep it enabled for now — settle it with an ablation / A-B after the re-ingest (§D13).** 3c's
> overview lane: **40 overview queries** (min 22 / median 58 / max 314 pages); negatives 23 → **34**.
> **3d** settled the §B4a fork on option (a) (`4697961`); **3d-ii** (visual path + D8 judge + scan,
> `3a18da4`) gave **33 usable visual queries** (§B4d, `18250f1`); **v2** assembled (`e69c347`) then
> pruned by §D6 (`f109379`): **166 answerable + 34 negatives = 200** (17.0%). **Session 4b:** harness
> fixes (`769e60d`); §D4 re-measured and **reframed** (one coordinate system + inherent ±1
> chunk-boundary fuzz → **no labels changed**; §D4 is now a known symmetric noise floor); funnel
> re-ran post-fix on the same 133 queries: **Δ −0.0101, CI [−0.0299, +0.0097] → still UNRESOLVED**.
> §B4f, §D11, §I10 resolved. Artifacts: `p0-9-gold-v2_2026-10-17_0422.md` (step 4),
> `p0-9-gold-v2-visual_2026-10-17_0410.md` (visual); outcome: pre-registration → "Step 4 outcome".
> **Next: Step 8 (the run) → the reranker ablation; Session 5 (human verification) runs now.**
> **P1 re-ingest STARTED 2026-10-16** — plan: `.hermes/plans/2026-10-16-p1-reingest-plan.md`
> (10 steps, decisions closed). Done: Step 0 (config), Step 1 (`cluster_embedder.py`, 11 tests),
> **Step 2 (`parent_chunker.py` + `models.py`; 9 tests + 1 slow)** — `test_book.pdf` → **42** parents,
> every one with ≥1 in-range page and a heading stack (the plan's "43" was Docling's *default*
> `max_tokens=512`; at the configured `parent_max_tokens=5000` it is 42).
> **Step 3 (E1 `chunker.py` → chonkie `SemanticChunker`, parent-aware; 8 tests + 1 slow)** — 42
> parents → **91 children** raw / **66** at the inherited `min_chunk_tokens=32`; spans tile each
> parent exactly, no child crosses a parent. Segmentation model = chonkie's default (local
> `potion-base-32M`); the indexed vectors stay the cluster dense model. §E1 carries the merge
> measurement (91 → 66, −27%).
> **Step 4 (E3 `late_chunk_embedder.py`; 12 tests + 1 slow) DONE 2026-10-17.** The plan's FIRST
> ACTION — the **Qwen3** local-tokenizer↔cluster-token alignment probe — ran live first and
> **CONFIRMED the alignment** (local tokenizer plain + exactly one trailing `<|endoftext|>` vector;
> offsets tile; appending text leaves earlier vectors bit-identical; a word swap moves only its own
> index and later; no truncation at 5,200 tokens) → **R2's 1024d + 64d stands, no jina fallback**.
> Also measured: per-token cost ≈ 160× the pooled payload / 55× the wall time → ~48 min and
> ~13.6 GB for 968 pages (fine as the Step 8 background job; only *parents* get a per-token call).
> **Independent review (round 1) found a real defect** — a call to the non-existent
> `self._embed_isolated` on the zero-token-parent branch — fixed + regression test; round 2
> `passed: true`. Evidence `logs/p1/step4/` (README = the review record), register §E3b.
> **Step 5 (E5 `is_content`) DONE 2026-10-17** — `src/pdf_ingestion/content_filter.py`: the
> `_NON_CHAPTER` list promoted out of `store.py` **plus two structural signals**, wired into the
> chunker (tags every child), the Qdrant payload, SQLite (`chunks.is_content`), the card rebuild,
> and retrieval (`must_not is_content == False`). **The keyword list alone could not pass the
> plan's acceptance test** — no page-936 index row carries a keyword — so an exact index-heading
> rule and an index-table-layout rule were added; measured over 5,048 chunks: **page 936 splits**
> (content 4660–4667 kept, index 4668–4683 dropped), 5 false negatives all explained, 242 false
> positives = the front-matter recall gap (**§E5 outcome**; page bounds left in place). Evidence
> `logs/p1/step5/`. Review (single-turn, evidence embedded): `passed: true`, C1–C5 confirmed.
> **Step 6 (§D4 per-PDF-page numbering) VERIFIED 2026-10-17 — no source change.** The code landed
> in Step 3 (children take `page_number` from `parent.page_for_offset`), so Step 6 is the
> measurement. Against an **independent extractor** (PyMuPDF text; the numbers came from Docling),
> head-only, **both paths on the same unit** on the 968-page book: offset 0 **71.5% → 99.95%** (all
> chunks 5047 → all children 3796; offset −1 333 → **1**), and **100%** on first-per-page
> (54.4% → 100%). 0 children without a page. An independent reviewer **refuted the first version**
> for comparing unequal samplings — the fix also showed the recorded "45% at −1" was itself a
> first-chunk-per-page artifact. Round 2 `passed: true`, M1–M5 confirmed. Evidence
> `logs/p1/step6/` (README + `realbook.json` + cached `children.json`). The plan's "remove the dead
> path" moves to Step 7 — the legacy `chunk_document` is still called by `store.ingest_document`.
> Suite **356 pass / 4 fail** (the same pre-existing class: 2 SPLADE fixtures, 2 zero-result
> searches) + 6 skips (the live-E2E tests, which now need `SV_EMBED_URL`).
> **Step 7 (schema + write path) DONE 2026-10-17** — new `src/pdf_ingestion/chunking_pipeline.py`
> is the single ingest path (`ParentChunker.convert` → `SemanticChunker.chunk_parents` →
> `LateChunkEmbedder.embed_children` → `save_document`); `store.ingest_pdf` delegates to it and the
> legacy flat path (`chunk_document`/`build_page_map`/`_page_for_offset`) is **deleted** (Step 6's
> deferred half). Created schema = `dense_64 + dense_1024 + colbert + sparse`; the vector name is
> **resolved from the collection** (`store._dense_name_from`) so the deployed `knowledge_base`
> (still `dense_768`) stays writable — pinned by a test. Payload + SQLite carry
> `parent_id`/`parent_text`. `raptor_tree._embed` moved to the dense lane (summaries share the
> collection's slot; without it 14 tests fail). Live probe `logs/p1/step7/` on `test_book.pdf`
> with the **real** cluster lane + **real** Qwen3 tokenizer: 42 parents → 66 children, exactly 3
> named vectors present, Qdrant points == SQLite chunks == children (66),
> `dense_64 == mrl_slice(dense_1024, 64)` to 1e-5. ruff: 51 findings before, 51 after.
> **✅ THE QUERY SIDE IS SWITCHED (Step 7b, 2026-10-17)** — the UI, `main.py`, `evaluate_rag`,
> `funnel_boundary_recall`, `calibrate_eval_pages`, `why_colbert` and the intent router now all
> embed with the cluster dense lane (Qwen3, 1024d + query instruction), so the funnel and the
> §D13 ablation can read a rebuilt collection. The three scripts that query Qdrant directly also
> lost their hard-coded `using="dense_768"` (now resolved from the collection) — a second,
> independent reason the funnel could not read v2. **R-a discharged:** the router's schema check
> compares against `dense_dim`, its prototypes come from the dense lane, and the classifier was
> **retrained at 1024d** (`--train-only`, 1,158 queries, **96.6 %** held-out accuracy). The 768d
> model is recoverable from git (`git show 161e01b:data/models/intent_classifier.pkl`); a local
> copy also sits at `data/models/intent_classifier_768d.pkl.bak` — **gitignored, so absent from a
> fresh clone**. **Deliberately partial:** the
> concept-graph lane still embeds with the retired 768d model because `concept_embeddings` is
> still 768d (the UI passes it a second, `graph_vec`) — **§I12**, released by Step 9; likewise
> `reembed_chunks.py` / `validate_embedders.py` — **§I13**. **Found and fixed on the way:** the
> endpoint returns **unnormalised** pooled vectors and only the index side normalised, so any
> dot-product consumer was off by ~6,000× (no retrieval number moved — Qdrant normalises for
> COSINE). Evidence `logs/p1/step8/`; register `IMPROVEMENTS.md` §E6 "SWITCHED 2026-10-17".
> **⛔ Step 8 attempt 1 FAILED 2026-10-17 20:05:54 → 21:32:15 (86 min, exit 1); the fix has since
> landed and attempt 2 is running.** The run
> `scripts/ingest_base_textbook.py --pdf …feynman… --collection-name knowledge_base_v2 --reindex`
> got **further than the plan expected and then lost all of it**: Docling parsed 968 pages in
> **4 min** → **341 parents → 3,796 children** → the late-chunk phase ran **260 of 341 parents**
> (40.4 min, 360,685 tokens) → parent 260's per-token call to `:8123` raised `httpx.ReadTimeout`
> and aborted. **Nothing was written** (`knowledge_base_v2` = 0 points; SQLite still only the old
> doc) because `save_document` is the single write point and runs only after *every* parent is
> embedded. **The cluster was healthy before and after** — a pooled call returned 200 in 0.14 s
> right after — so it was a **transient stall, not an outage**.
> **✅ FIXED (§I16):** `cluster_embedder._post` now has a bounded jittered retry (1+3 attempts,
> retrying only `TransportError`/429/5xx; other 4xx fail fast) and **per-path read timeouts**
> (120 s pooled / 300 s per-token — a measured 4,647-token parent legitimately took 92 s, so the
> old flat 120 s could false-trip a healthy request). **And the loop that issues those calls was
> strictly serial** — `LateChunkEmbedder.embed_children` now embeds parents concurrently
> (`late_chunk_workers`, default 8), reassembled in parent order so the output is byte-identical.
> Measured knee (`probe_concurrency_knee.py`): **84 tok/s at 1 worker → 597 at 16**, still rising,
> so 8 is deliberately conservative. Serial latency is `≈ 5.2 s + tokens/53` — a **~5 s fixed
> overhead per request**, i.e. ~30 min of the failed run was pure overhead. Suite **371 pass / 4
> pre-existing fail / 6 skip**; ruff unchanged. Review: 2 reviewers on `openai/gpt-oss-20b` —
> one pass (weak signal, spot-checked instead), one finding adjudicated as **half real**: the
> claimed `TypeError` is **false**, but the shared tokenizer's **unsynchronised lazy load** is a
> genuine race and is now fixed (warmed before the pool).
> **Still open in §I16:** httpx's read timeout is per *read operation*, so a trickling body can
> outlive any timeout — the 42-minute gap is consistent with that. Needs a total-request deadline
> or a checkpoint. **§I17 (new):** the two remaining serial-batch lanes (ColBERT batch 4 ≈ 949
> requests, SPLADE batch 32 ≈ 119) are ~15 min and were deliberately NOT bundled into this fix.
> **Pre-flight that landed** (all measured, all tracked): cluster probed; both optional lanes
> resolved live — SPLADE and ColBERT are both **cluster**-served, no model download; the exact
> entry point dry-run on the 19-page fixture into a throwaway collection (**82 s**, 42 parents →
> 66 children, all four vectors on all 66 points). Two env values **must** be passed on the
> command line — `QDRANT_HOST=10.0.10.65` and `SV_EMBED_URL=…:8123/embeddings`; the latter is
> **missing from `.env`** (§I14). `--reindex` is mandatory. Evidence: `logs/p1/step8-run/`.
> Full detail: `IMPROVEMENTS.md` §E6–§E7, §I14–§I17.
>
> **Steps 2–3 went through independent review 2026-10-17** (verifier = `openai/gpt-oss-20b`, a
> different model from the author's). It found one genuine defect — a parent with no provenance
> silently gave every child `page_number=None` — now fixed with a loud warning + test. Two of its
> three "logic errors" were diff-only artifacts (a helper defined outside the diff; a guard
> misread), and its C2 refutation rested on a flawed check of the author's own. Adjudicated with
> evidence: **page-map agreement is 0 mismatches / 169 elements and 0 / 5555 sampled characters**
> against Docling's per-element provenance as an independent oracle. See "Verified facts" for the
> verifier's model and its one hard limit (no multi-turn tool sessions).
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

> ✅ **UNBLOCKED AND RUN 2026-10-14 18:03–18:06.** The router came back mid-afternoon.
> `logs/p0-9/run_session4_v2.sh` (written 17:55) ran **steps 1–2** on the cluster index
> (`QDRANT_HOST=10.0.10.65`, 5,135 points), **133 text queries**, one shared HyDE cache.
> **Steps 3 and 4 did not run** — §D7: `required_n.py`'s `--queries` default is **v1** →
> *"0 shared queries"*, exit 1; `evaluate_rag.py` wrote no artifact. Full numbers:
> pre-registration → "Outcome".

### Session 4 — the v2 A/B result (2026-10-14)

| boundary | rerank | no-rerank | reading |
|---|---|---|---|
| B1_dense64_1000 | 0.7924 | 0.7924 | precedes the reranker — identical, as it must be |
| B2_dense768_500 | 0.7415 | 0.7415 | " |
| B3_sparse_250 | 0.6743 | 0.6743 | " |
| B4_rrf_union_100 | 0.5943 | 0.5942 | " (§D10 — not bit-reproducible) |
| B5_colbert_100 | 0.6007 | 0.6007 | " |
| **B5b_retriever_top20** | **0.4495** | **0.4495** | the 100→20 cut costs **0.15** of recall |
| **B6_rerank_20** | **0.4389** | **0.4495** | the reranker alone: **−0.0107**, CI **[−0.0304, +0.0091]** |

**Verdict: unresolved at n=133** — the CI straddles 0, so the pre-registered rule (§4) is not met.
30 queries worse / 37 better / 66 identical — churn, not a uniform loss. Exploratory per-type:
**factual −0.0469, CI [−0.0787, −0.0152] → resolved (the reranker hurts factual)**, multihop
+0.0091 and overview +0.0176 both unresolved. The factual result survives a Bonferroni correction
for 3 subgroups, but it is a **subgroup, not the pre-registered endpoint**.

**Why v2 looks worse than v1's 0.636 — and mostly is not** (§D9): R@20 is divided by the label
count, and v2's overview labels average **73.8** pages (max 314) against v1's **3.4** (max 13).
v1's mean ceiling was 1.0000; v2's text lane is 0.8016 and its overview lane only 0.3992. On v2's
88 text queries with ≤20 labels — structurally v1-like — B5b scores **0.6037** vs v1's 0.636.
**v1 and v2 R@20 numbers are not comparable; never put them in the same table unnormalised.**

**Two harness defects found while reading the result:** the funnel ignores `max_content_page` and
so does not mirror deployed retrieval — arm-asymmetrically (2.15% of the rerank arm's top-20 slots
are back-matter pages the app never serves, vs 0.95%) — §D8; and RRF fusion is not
bit-reproducible at the pool level even with HyDE pinned (7/133 queries at B4, 2/133 at B5; the
top-20 was stable) — §D10.

### UI — text-query visual search (2026-10-14)

The visual tabs — admin **Visual Search** and student **Find a Figure** — now accept a **typed
description** as well as an uploaded image: a `Describe it / Upload an image` radio drives the same
ColPali MaxSim search via `embed_query_text` (local, no re-ingest). Duplicate pages no longer appear:
`store.visual_search` collapses by page, and `save_colpali_embeddings` now replaces a document's
pages instead of accumulating another copy (**§B4b**, both halves fixed in code; the existing 2,835
points are still 3× until a re-ingest/cleanup). A text query **ranks, not filters** — the 0.58
threshold is image-calibrated (**§B4e**). Tests: `tests/test_visual_index.py` (4).

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
5. **⛔ STILL OPEN — Normalise the gold labels' page numbering** (`IMPROVEMENTS.md` §D4).
   `relevant_pages` mixes DB page numbers (from the generator) with PDF page numbers (from the
   scan); measured, they differ by 0/−1 on ~45% of pages (and up to +2, §D4's visual note). It was
   to be done **before** Session 4 assembled v2 and **was not** — so the A/B numbers above carry
   about a page of label noise, which is also the floor under how finely the reranker delta can be
   read (pre-registration §6).

### Next — the Session 4b plan (ordered; do in a FRESH session)

> **Session 4b, not "Session 5"** — `p0-9-SESSIONS.md` already assigns Session 5 to human
> verification (Task 7). This is a follow-on to Session 4, named per the 3b/3c/3d-ii convention.

**Scope decision (2026-10-14, Bharath):** tasks 1 and 2 below are done **together** — fixing the
funnel changes the numbers and normalising the labels changes them again, so both land before the
re-run, which then yields **one** clean number instead of two moving ones.

0. ✅ **DONE (`12e0dd5`).** `logs/p0-9/v2_{rerank,norerank,hyde}.json` + `run_session4_v2.sh` are
   tracked; the A/B evidence is in git.
1. ✅ **DONE (`769e60d`).** The three harness defects fixed:
   a. `required_n.py` — `--queries` is now **required** (§D7). Verified: reproduces n=133, SD_d
      0.1163, required N 43.
   b. `funnel_boundary_recall.py` — `max_content_page` applied in `build_filter` **and** `post()`,
      mirroring `store.py` (§D8).
   c. `logs/p0-9/run_session4_v2.sh` — step 3 passes `--queries`; `set -e` + `ERR` trap abort on a
      failed step.
2. ✅ **DONE — REFRAMED, no labels changed (§D4).** Re-measured: the DB `page_number` and the PDF
   page index are **one coordinate system** with inherent ±1 chunk-boundary fuzz (`SentenceChunker`
   merges across page boundaries), not two numberings; `chunks` stores no PDF-page field, so there
   is nothing to reconcile. No label edit can remove the fuzz, and it is **symmetric across the A/B
   arms** → a known noise floor, not an open defect. Durable fix folds into the E1/E2/E3 re-ingest.
3. ✅ **DONE (2026-10-15, `logs/p0-9/session4b_rerun.log`).** Funnel re-ran post-fix, same 133
   queries, HyDE cached (**no LLM calls**). **Δ −0.0101, 95% CI [−0.0299, +0.0097] → still
   UNRESOLVED at n=133.** The §D8 fix raised every pre-reranker boundary (B1 0.7924→0.7999, B5b
   0.4495→0.4492) and moved the headline delta by **0.0006** — inside the noise. Full table +
   per-type: pre-registration → "Session 4b re-run".
4. ✅ **DONE (2026-10-16, 20:13–21:22) — step 4 (`evaluate_rag.py` on v2) ran.** `--skip-visual`,
   `logs/p0-9/session4b_step4.log` → `data/eval_results/p0-9-gold-v2_2026-10-17_0422.md`. Measured
   the *other half* of the pre-registered decision: **abstention 17/34 = 0.500** (> the 0.0 majority
   baseline → **met**) and the text-lane generation metrics (Faith 0.661 · Ans.Rel 0.852 · Citation
   1.000, n=133). The **visual lane** (33 q) was measured **separately**: **R@20 0.960**
   (`p0-9-gold-v2-visual_2026-10-17_0410.md`). §B4f and §D11 resolved. Outcome: pre-registration →
   "Step 4 outcome"; registered `IMPROVEMENTS.md` §D12.
5. ✅ **DECIDED (2026-10-16, owner) — keep the reranker enabled for now.** The observed 0.011 needs
   **n≈934** to resolve while the pre-registered δ=0.05 needed only **43**, so "extend in blocks of
   30" (§5) reaches δ≈0.026 at n=163 and can never resolve 0.011. Decision: **do not drop it and do
   not extend the query set** — settle it with a **fresh ablation / A-B after the re-ingest**
   (E1/E2/E3 + §E5 + §D4), when the label fuzz and chunk-boundary noise that currently swamp the
   effect are removed. Keep the **factual-lane** loss (−0.0469, resolved) as the hypothesis to
   re-check. Rejected: (i) drop now (cost is small, effect unresolved not proven-negative);
   (ii) extend (0.011 needs n≈934; §5 forbids extending until an arm wins). Registered `§D13`.
6. **Only then P1 item 10** (ranking) — and drive it off the **ceiling-normalised** numbers (§D9),
   not the raw overview R@20 of 0.14.
7. **Runnable NOW, no cluster — Session 5 (human verification, Task 7).** Prepared 2026-10-16:
   fill in `data/gold_v2_review.md` (**30 queries, 6 per stratum**), then
   `uv run python scripts/score_review_sheet.py`. Protocol (sample, verdicts, the ±1 window
   rule, pre-registered consequences):
   `.hermes/plans/2026-10-16-p0-9-5-verification-protocol.md`. This is the productive thing to do
   while step 4 is blocked on the outage — it is the only P0-9 task that needs nothing but you.

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

**✅ REFUTED 2026-10-16 (§B4g) — the index is NOT polluting the overview lane.** Back-matter pages
(`page >= 937`) occupy **0.32%** of the overview top-20 slots in the pre-fix funnel artifacts
(2/625) — the **lowest** of any type (factual 1.66%, multihop 0.68%); only 2 of 40 overview
queries touch one. P1 item 10 therefore need **not** wait on a back-matter fix. (The 0.191 MRR is
from the superseded v1 run and is not re-testable from disk — re-check on v2's per-type MRR after
step 4.) Original hypothesis, kept for the record:

Overview queries are the
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
| 9 | **gold-set rebuild** | Sessions 1–3c done — `ca3324e`, `52d2179` (measure) + `5cbf564`, `4f112b0`, `fffc3b3`, `c9d8d0c`, `668cd0f` (tools) + `1870dc9`, `8e81572` (scan) + 3b (negatives pruned, index gate) + 3c (`871a5a4` tools, `a6971f3` 40 overview questions, then the book-wide scan) + **3d code (`4697961`)** + **3d-ii (`3a18da4`, `18250f1` — 33 usable visual labels, §B4d)** + **Session 4 (`e69c347`, `f109379`)** + **Session 4b (`769e60d` harness fixes; §D4 reframed; funnel re-run) + step 4 (2026-10-16)** — v2 = 200 (166 answerable + 34 negatives); **abstention 17/34 = 0.500 (met), Faith 0.661, visual lane 33 q R@20 0.960** (`p0-9-gold-v2_2026-10-17_0422.md`). **✅ P0-9 is MEASURED — both halves of the pre-registered decision now have numbers (reranker unresolved; abstention met).** Reranker decision deferred to a post-re-ingest ablation (§D13). on `feat/p0-9-gold-dataset-v2` |

Test suite: **361 pass / 4 fail / 6 skip** (`uv run pytest tests/ -q -m "not slow"`, re-measured
2026-10-17 after Step 7b — 356/4 before it, +3 `test_config_invariants.py` dense-lane tests and
+2 `test_cluster_embedder.py` normalisation tests). The 4 are **pre-existing** and were
**re-confirmed on a clean `HEAD` worktree** (so they are not regressions from the query switch):
`tests/test_splade.py` (×2) hardcode a missing `tests/data/sample_physics.pdf`, and
`test_phase1.py::TestStore::test_hybrid_search_includes_global` +
`test_phase2.py::TestPhase1Regression::test_search_still_works_after_phase2` return 0 results.
The 6 skips are the live-E2E tests (they need `SV_EMBED_URL`). **Do not "fix" the 4 here.**

---

## Session hygiene

Start each P0-9 stage in a **fresh** session (`/new`) and read only that stage's section of the
plan. The previous long session reached ~271k tokens/call with 2 lossy compactions behind it —
**do not continue P0-9 inside a compacted session.** See `p0-9-SESSIONS.md` for the split and the
handoff steps.

**Independent verification is a step, not a nicety.** Run `requesting-code-review`'s Step 5 on
every commit that changes source. `delegate_task` already runs on a different model
(`openai/gpt-oss-20b` — see "Verified facts"), so the independence costs nothing, but it is only
real if it is invoked: Steps 2 and 3 shipped unreviewed on 2026-10-17 and the reviewer immediately
found a genuine defect (a parent with no provenance silently gave every child `page_number=None`).
Budget `max_tokens` ≥32k for the reviewer — on a 300-line diff the hidden reasoning trace alone
exceeded 16k output tokens and the verdict came back empty. **Step 4 re-measured the ceiling:
32k is not always enough either** — one round ran 216 s, produced 126,818 characters of hidden
reasoning, hit `finish_reason=length` and returned empty content; trimming the prompt (drop the
test source) got a verdict. Treat an empty round as **no verdict, never a pass**, and expect two
rounds to be needed when the first one finds a defect (fix → re-ask on the fixed code).

---

## Priority plan (agreed)

**P0 — make the numbers trustworthy.** 1–8 ✅ · **9 ✅ gold set — MEASURED (2026-10-16); both
halves of the pre-registered decision now have numbers (reranker unresolved; abstention met).**

**P1 — then improve metrics.** The re-ingest is now the gating item:
 0. **Re-ingest (E1/E2/E3 + §E5 + §D4)** ⚠️ requires re-ingest — semantic chunking, parent/child
    hierarchy, late/contextual chunking, chunk-level front/back-matter classification, and
    per-PDF-page numbering. It removes the ±1 label fuzz (§D4) and the chunk-boundary noise that
    currently swamp the reranker effect; **the reranker ablation (§D13) and every metric below
    re-measure on the rebuilt index.** Honour the `clean_stale_*` ordering (§B4b, §E5).
    **Steps 0–7b done (2026-10-17)** — code, schema, write path *and* the query-side dense-lane
    switch. **Step 8 attempt 1 FAILED at 86 min (transient endpoint stall, nothing written) —
    §E7; the re-run is blocked on the §I16 retry/checkpoint fix.** Then Step 9 (Phase 2/3
    re-index, which also releases §I12/§I13).
10. **Ranking** — overview MRR is the one genuinely bad number (report it ceiling-normalised, §D9,
    not the raw 0.14). Cheapest first: config (MMR λ / RRF) → the cross-encoder → hard-negative
    fine-tuning. **The index-page hypothesis is REFUTED (§B4g)** — nothing gates item 10 on a
    back-matter fix. Run the **reranker ablation (§D13)** here, on the re-ingested index.
11. ✅ **SUPERSEDED** — v2 carries **33 calibrated visual queries** (§B4d); the old "7 uncalibrated
    visual queries" belong to v1. Re-check the visual lane after the re-ingest.
12. Per-lane attribution in the eval report (which lane moves which query type).
13. ✅ **DONE 2026-10-16** — Test the fallback chains. `tests/test_fallback_chains.py` (8
    tests) drives the real classes with a broken backend. Revealed §I9 (a failed embedding
    silently degrades to zero vectors). Not actually gated on P0-9.
14. ✅ **DONE 2026-10-16** — `render_math()` golden-file test.
    `tests/data/formula_split_golden.json` + `tests/test_frontend_formula_render.py` (10
    tests). Done as part of fixing §B1 (formula cards rendered prose as maths), which this
    test now pins. Not actually gated on P0-9.

**Also done 2026-10-16 (Group 2 UI/backlog pass, no cluster needed):** §B1 (formula
render), §I3 (Admin Status now shows store vs SQLite counts), §I5 (Topic/Difficulty fully
removed), §B2 half (already done in code), §B4g (index hypothesis refuted). Registered:
§B5 (Unicode maths in formula expressions is not valid LaTeX) and §I9 (zero-vector
embedding fallback).

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
| Dense lane (query + `knowledge_base`) | **Qwen3-Embedding-0.6B, 1024d + 64d MRL** (`dense_model`/`dense_dim` in `config.py`), cluster `:8123`. The endpoint returns **unnormalised** vectors (norm ≈ 70–131) — normalised client-side for the pooled paths only. The query instruction IS applied (cos vs the same text as a passage = 0.8436) |
| Legacy dense embedder | **Nomic 768d + 64d MRL** (`embedding_model`) — **retired from the query path and from `knowledge_base`** (2026-10-17, §E6). Still builds `derivative_artifacts` + `concept_embeddings` and `reembed_chunks.py` until Step 9 (§I12/§I13) |
| Intent classifier | **Retrained at 1024d 2026-10-17** (`--train-only`, 1,158 queries, **96.6 %** held-out acc, macro F1 0.96). The router's schema check compares `n_features_in_` against `dense_dim`; a stale 768d model is rejected loudly → prototype fallback. 768d model recoverable via `git show 161e01b:data/models/intent_classifier.pkl` (the local `.bak` is gitignored) |
| Reranker | `BAAI/bge-reranker-v2-m3` |
| Chunker | `chonkie.SentenceChunker` (class named `SemanticChunker`) |
| Intent classifier (versions) | `LogisticRegression` on `dense_dim` features, pinned `scikit-learn~=1.9`, schema-checked at load |
| Card types | **8** in `CardType` (single source for `DA_CARD_TYPES`) |
| Eval queries (v1) | 30 = 23 calibrated non-visual + 7 uncalibrated `visual` — **superseded by v2; do not use** |
| Baseline (v1, 23 q) | Recall@20 **0.636** · Hit@20 1.000 · MRR 0.361 · NDCG@20 0.432 (`p0-judge-canonical_2026-10-06_0010.md`) — **not comparable to v2** (§D9) |
| Gold v2 | `data/eval_queries_v2.json` — **200** = 166 answerable (53 factual + 40 multihop + 40 overview + 33 visual) + 34 negatives (17.0%). The funnel's text lane is the **133** |
| v2 label sizes | text lane mean **22.2** pages (factual 9.5 · multihop 4.4 · overview **73.8**, max 314) → R@20 ceiling **0.8016** overall, **0.3992** on overview (§D9) |
| v2 funnel (133 text q) | pre-fix (2026-10-14): B1 0.7924 · **B5b retriever top-20 0.4495** · **B6 reranked 0.4389** · Δ **−0.0107**, CI [−0.0304, +0.0091]. **post-fix (2026-10-15, `769e60d`):** B1 0.7999 · **B5b 0.4492** · **B6 0.4391** · Δ **−0.0101**, CI [−0.0299, +0.0097] → **still unresolved** |
| v2 step 4 (133 text q, 2026-10-16) | R@20 **0.465** · Hit@20 0.947 · MRR 0.827 · NDCG@20 0.540 · Faith **0.661** · Ans.Rel 0.852 · Citation 1.000 (n=133; factual 0.564 / multihop 0.619 / overview 0.178). **Abstention 17/34 = 0.500** (> the 0.0 majority baseline → **met**). 164/200 synthesis, **4876 judge calls, 0 failed**, 3565.7s — `data/eval_results/p0-9-gold-v2_2026-10-17_0422.md` |
| Visual lane (v2, 33 q) | **R@20 0.960** · R@100 0.836 · Hit@20 1.000 · MRR 0.914 · NDCG@20 0.891 — **first measurement** 2026-10-16 (cluster `visual_knowledge_base`, ColPali text-query path; `data/eval_results/p0-9-gold-v2-visual_2026-10-17_0410.md`). §B4f resolved (base model cached); §I10 fixed the per-query 5.5 GB reload that OOM-killed the first try |
| Judge lane (v1, 23 q) | Faithfulness **0.701 (a floor)** · Ans.Relevance 0.927 · Citation 1.000 |
| Judge gateway | **`http://10.0.10.70:8000`** — serves `Qwen/Qwen3-VL-8B-Instruct` (the D9 VLM) among 6 models; ~0.8 s per page judgment at concurrency 1. The P0-9 plan's `10.0.10.51:8000` is **dead**. |
| Cluster LLM catalogue (probed 2026-10-17) | **Listed ≠ serving.** `/v1/models` returns 6 ids, but only **2 text models answer**: `openai/gpt-oss-20b` (200, ~0.3 s on a trivial prompt) and `Qwen/Qwen3-VL-8B-Instruct` (200). **`openai/gpt-oss-120b` is listed and 502 ×3** ("Backend inference unreachable"), as is `deepseek-ai/DeepSeek-R1-Distill-Qwen-7B` (backend `10.0.50.71` down). Same trap class as §B4a's ColPali endpoint — re-probe, never trust the catalogue. |
| Verifier model | `delegate_task` children run **`openai/gpt-oss-20b`** (cluster) — `delegation.model` in `~/.hermes/config.yaml`, alias `sv-gptoss`. That is a *different* model from the main agent (`deepseek/deepseek-v4.1-flash`), so the independent-review step is free. `delegation.fallback_providers` is **`[]`** (it was the main agent's own model → a cluster outage silently turned the verifier into self-review). **Limit (measured 2026-10-17):** it cannot sustain a multi-turn *tool* session — after 25 API calls the provider rejected the request as malformed because the model's own harmony control tokens (`<\|channel\|>commentary`) had leaked into message content and the server could not parse the replayed history. Single-turn tool calling works. So the verifier runs **single-turn with the evidence embedded**, not as a tool-using agent; a mid-run protocol failure counts as *no verdict*, never a pass. |

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
