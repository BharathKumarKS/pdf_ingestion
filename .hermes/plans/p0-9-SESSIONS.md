# P0-9 — session split

**Purpose:** run the gold-set rebuild across several *short* sessions instead of one long one.

**Why:** every turn re-sends the whole conversation, so cost per turn grows with the
conversation and total cost grows roughly with turns². Measured on this machine: a 19-call
session ran at **~72k tokens/call**; a 316-call session ran at **~238k tokens/call** and cost
**$2.44**. Splitting keeps each session small and avoids lossy compaction.

**Rule of thumb:** one session per commit boundary. Each stage below ends with a commit and a
HANDOFF refresh, then `/new`.

| Session | Scope | Tasks | Heavy run? |
|---|---|---|---|
| 1 | Measure | 0, 1, 2 | no |
| 2 | Build the tools | 3, 4a, 5 (code only) | no |
| 3 | **Run the scan** | 4, 5 (execution) | **yes — background job** |
| 3b | **Fix the scan output** (negatives + index-page hits) | new — see below | no |
| 3c | **Extend the gold set — overview** (topic → book-wide scan) | new — see below | medium (generation) |
| 3d | **Visual lane** (text+image query path, §B4) + visual queries + labels + metric | new — see below | heavy (model + re-embed) |
| 4 | Assemble & decide | 6, 8 | medium |
| 5 | Human verification | 7 | no (manual) |

Task numbers refer to
`.hermes/plans/2026-10-06_174001-p0-9-gold-dataset-v2.md`.

**Status 2026-10-12:** cluster verified up. Sessions 1→4 are a **dependency chain — do not run
them in parallel** (see below). Session 5 (human verification) is scheduled for 2026-10-13.

---

## Can these run in parallel? No — and here is why

Two separate reasons, either one fatal:

1. **They are a chain, not a set.** Session 1's required-N sizes Session 2's generation; Session 2's
   tools are what Session 3 runs; Session 3's artifacts are what Session 4 assembles. Starting
   Session 3 before Session 2 finishes means running tools that do not exist yet.
2. **All sessions share one working tree.** Two agents in the same repo directory see each other's
   uncommitted edits, and one session's `git add -A` / `git commit` sweeps the other's half-finished
   work into its commit. This is the killer — it corrupts both, silently.

**Where the parallelism actually lives** (do this instead):

- **Inside Session 3** — the ~25k scan calls, via threads (Task 4a). That is the 8–14× speedup.
- **Inside Session 4** — the A/B configs run as **parallel background processes**; they are
  independent read-only runs against the index.
- **Session 5** — the user's manual work, which is naturally independent of everything.

**If you truly need two agent sessions at once**, they must not share a tree: give each its own
`git worktree add <dir> <branch>` (separate branch, separate directory) and merge afterwards. The
merge overhead is real, and the chain above means the payoff is small — prefer the in-session
parallelism instead.


---

## How to open a session

Paste one line, e.g. for session 2:

> Read `HANDOFF.md`, then `.hermes/plans/p0-9-SESSIONS.md` (session 2), then **only the
> "Task 3" / "Task 4a" / "Task 5" sections** of the P0-9 plan. Do not read the whole plan.

Reading only your section is the point — the plan is 1,044 lines (~11k tokens) and you do not
need most of it.

---

## Session 1 — Measure (Tasks 0, 1, 2)

- **Deliverable:** `feat/p0-9-gold-dataset-v2` branch; `scripts/required_n.py` written **and run**;
  the real σ_d for *this* comparison recorded in `IMPROVEMENTS.md` §F4b; `tests/test_gold_schema.py`
  committed (expected: 5 skipped).
- **Definition of done:** the required-N number exists and is committed. Nothing downstream starts
  before it does — this number sizes everything.
- **Watch:** if `required_n.py` reports **>200**, that is a finding to report, not a number to
  quietly generate past.
- **Handoff:** commit, tick Task 0/1/2 in the plan, update `HANDOFF.md` "Current focus" with the
  measured N, `/new`.

## Session 2 — Build the tools (Tasks 3, 4a, 5 code only)

- **Deliverable:** multi-page generation added to `generate_gold_dataset.py`; the scanner
  parallelized (**Task 4a** below); `generate_negatives.py` written. **No large LLM spend.**
- **Definition of done:** each tool passes a `--dry-run` and a `--limit 2` probe.
- **Watch:** D9 (send the page **image**) and D10 (raise `max_tokens`, kill the silent `[]`) are
  prerequisites here, not later.
- **Handoff:** commit each tool, `/new`.

### Task 4a — parallelize the scanner (new; do this before the big run) ✅ done 2026-10-12

`scripts/validate_eval_calibration.py` is fully sequential — one page, wait, next. Four changes,
mirroring the pattern already in `scripts/evaluate_rag.py:377` (`_JUDGE_WORKERS = 8`):

1. **Open the PDF once and pre-render all 938 pages to images once.** `extract_page_text` opens
   the whole 968-page PDF **on every call** (`validate_eval_calibration.py:87`) — ~33,000 opens.
2. **Cache verdicts to disk**, keyed by (query_id, page, model, prompt-hash). Gives resume, makes
   re-runs bit-identical, and fixes a live waste: `scan_query` **re-judges hot pages in pass 2**
   (lines 243–246) for pages already judged in pass 1.
3. **`ThreadPoolExecutor` over the page list**, one pool per pass (threads, not processes — these
   are I/O-bound HTTP waits). Two waves: pass 1 coarse, pass 2 dense.
4. **One shared `httpx.Client`**, not module-level `httpx.post` (line 135).

**Before the full run, ramp-probe the gateway**: 100 throwaway page-judgments at concurrency 1, 4,
8, 16, 32; record calls/sec and error rate. The knee is your worker count. Do not guess — the
server batches, and above its limit you get queueing or 429/503.

## Session 3 — Run the scan (Tasks 4, 5 execution) — **background job**

- **This is a job, not a conversation.** Launch with `terminal(background=true, notify=true)` and
  **end the session immediately.** Do not sit and watch it.
- **Deliverable on disk:** `data/eval_queries_gold_expanded.json`, `data/eval_negatives.json`.
- **Expected:** ~25k calls; ~1–2h parallelized (see Task 4a's ramp probe), ~14h sequential.
- **Handoff:** nothing to write mid-run — the artifacts are the handoff. Start session 4 when the
  notification fires.

**Run order — three steps, each feeding the next.** The sessions table does not assign the
*generation* run, but Task 4 has no input without it:

```bash
# 1. generate the gold questions  -> data/eval_queries_gold.json
uv run python scripts/generate_gold_dataset.py --tenant global \
    --n-chunks 40 --questions-per-chunk 2 --multipage-count 20

# 2. scan-expand the labels       -> data/eval_queries_gold_expanded.json
uv run python scripts/expand_gold_labels.py --workers <knee>

# 3. verified negatives           -> data/eval_negatives.json
uv run python scripts/generate_negatives.py --n 24 --workers <knee>
```

**Judge for steps 2 and 3 — it must be a VLM** (D9 sends the page image):

```
--judge-api-base http://10.0.10.70:8000 --judge-model Qwen/Qwen3-VL-8B-Instruct
```

Step 1 takes no judge flags — it generates from `.env`'s LLM settings (`OPENAI_API_BASE`
`http://10.0.10.70:8000`, `OPENAI_MODEL` `openai/gpt-oss-20b`), which is correct: the generator
needs no page image.

The plan's `http://10.0.10.51:8000` is **dead**. `JUDGE_MODEL` is unset in `.env`, so
`--judge-from-env` alone would judge with the text-only `openai/gpt-oss-20b`, which cannot see
the page. Set `--workers` from `--ramp-probe` (100 throwaway page-judgements at concurrency
1/4/8/16/32) — do not guess. The verdict cache makes a re-run bit-identical and resumable.

## Session 3b — Fix the scan output (before Session 4)

- **Scope:** two defects found after the Session 3 run. Both must land **before** Session 4's A/B
  series, or the reranker comparison is measured through them.
- **Deliverable (1):** `data/eval_negatives.json` pruned and re-verified. `neg-nea-004` is
  **answerable** — p107 states *"Carbon-14 has a half-life of 5000 years."*; `neg-in_-001` returned
  YES on an index page. Re-verify the term-bearing survivors with a full `--scan-stride 1` scan, or
  route them to Session 5.
- **Deliverable (2):** index-page false hits stopped — tighten the judge criterion (YES = *this page
  contains the answer*; index / contents / cross-reference pages are PARTIAL at most) **and** add a
  deterministic structural gate. Do not fix this by prompt alone: the 8B VLM said NO on the index
  for one question and YES for another.
- **Why it blocks:** negatives are the only source of the abstention metric; index pages inflate
  recall in the real eval.
- **Watch:** the `_NON_CHAPTER` list already in `store.py` is wired only into the RAPTOR rebuild,
  and retrieval filters `min_content_page` as a **lower bound only** — back matter is not excluded.
- **Handoff:** commit each fix; `/new`.

## Session 3c — Extend the gold set: overview (tools built 2026-10-13; run pending)

- **Scope — split: visual moved to 3d.** The type mix is *emergent, not designed*: 8 `overview` vs
  40 `multihop`, because the multipage prompt asks for connection-type questions, so
  `classify_question()` labels them `multihop`. 3c adds the **overview** path only.
- **Method (the plan's §D):** pick a *topic*, then an exhaustive book-wide scan for all pages on it.
  Topics are derived from the book's own **section headings** — grounded, and necessary: the RAPTOR
  tree's leaf links are stale (`raptor_nodes.child_ids_json` resolves L2→L1/L3→L2 but L1's 5,048
  leaf refs match only 4 rows in `chunks.id`), so the tree cannot supply labels. One question per
  topic, pre-labelled `overview` / `expected_route=raptor`.
- **Built (commit `871a5a4`):** `generate_gold_dataset.py --overview-count/--overview-output`
  (plus `--n-chunks 0` overview-only runs that never clobber the scanned set);
  `validate_eval_calibration.py` overview **judge variant** (the page is judged on whether it
  *contributes to the synthesis*, not on whether it answers the question) + `--overview-stride 4`
  + a term-bearing sweep over the whole book; `expand_gold_labels.py` marks an entry calibrated
  only when the scan found pages; `generate_negatives.py` seeds 8 → 12 per tier. Targets
  pre-registered in `.hermes/plans/2026-10-13-p0-9-3c-preregistration.md` (overview **40**,
  negatives **32–36**).
- **Deliverable (still to run):** `data/eval_queries_gold_overview.json` (40) →
  `data/eval_queries_gold_overview_expanded.json` (every one scan-labelled); negatives 23 → ≥32.
  Run: `logs/p0-9/run_session3c.sh` — ~40 topics × ~310 pages ≈ **12k judge calls, ~45–50 min**.
- **Watch:** prefer verified labels over hitting 40 exactly. Step 1 needs the generator LLM
  (`gpt-oss-20b`), steps 2–3 the VLM judge.

## Session 3d — Visual lane (text+image query path) + visual queries

- **Why it is its own session (verified 2026-10-13):** the visual lane has **no text-query path**
  (`colpali_embedder` exposes only `embed_query_image`); `evaluate_rag.py` **skips visual queries
  entirely** (line 641), so a labelled visual query is unmeasurable today; and the cluster's
  **colpali endpoint is down** — HTTP 500 in ~3.2 s on every request shape, though `GET /routes`
  advertises `colpali_models: [TomoroAI/tomoro-colqwen3-embed-4b]` and
  `colpali_endpoint: http://ansatz:8123/embed-image/v1/multivector-embeddings`. Full evidence:
  `IMPROVEMENTS.md` §B4a.
- **Deliverable (1) — the text-query path.** Visual search must accept **both text and image**.
  Two options, not equivalent:
  - **(a)** add `embed_query_text` to the local `colpali-v1.2` embedder (`colpali_engine` supports
    `process_queries`) — **no re-ingest**, same embedding space as the stored page vectors, runs
    offline.
  - **(b)** swap the lane to **ColQwen3** (`TomoroAI/tomoro-colqwen3-embed-4b`, the endpoint above,
    `input_type="auto"` = image-or-text) — better model, but a **different embedding space**, so all
    **945 page images must be re-embedded** (a visual re-ingest, §I1), and the endpoint must be up.
  The repo's pattern is a **direct HTTP client** (`colbert_embedder.ClusterColBERTEmbedder`) — not
  `sv_ray_cluster_access` / `embed_colpali` (§I8: reference only, not importable).
- **Deliverable (2) — visual queries with labels.** Generation path targeting **30–40**; v1's 7
  carry `pages=None` (unmeasurable). The corpus supports it: 426 chunks carry image markers on 278
  pages, `page_images` holds 2,835 rows, 945 page PNGs on disk. Needs a **D8 judge variant** for
  questions with no text answer (criterion: "does this page show the described figure/table/graph?").
- **Deliverable (3) — a visual metric.** `evaluate_rag.py` reports nothing for visual queries; wire
  the visual lane (MaxSim over `visual_collection`) so v2 can score them, or they stay unmeasurable.
- **Watch:** keep the generator and the judge apart — the visual question generator stays text-only
  (`gpt-oss-20b`); the VLM (`Qwen3-VL`) only judges. Otherwise the judge grades its own questions.
- **Definition of done:** text+image visual search works and is measured; 30–40 visual queries with
  `relevant_pages`; negatives still ≥15%; suite at the floor.

## Session 4 — Assemble & decide (Tasks 6, 8)

- **Deliverable:** `data/eval_queries_v2.json` (fresh, ≥15% negatives, all entries carry
  `answerable`); abstention metric wired into `evaluate_rag.py`; eval run; **the reranker decision
  with a confidence interval**, written into the report *before* the numbers are seen.
- **Scope settled 2026-10-12: re-run the FULL A/B series on v2**, not just the reranker question.
  D6 invalidated the history, so every claim gets re-measured on the powered set. Run the configs as
  **parallel background processes** (they are independent read-only runs against the index) — that is
  the real parallelism in P0-9, not parallel sessions.
- **Definition of done:** `tests/test_gold_schema.py` passes; suite ≥210 pass / 5 fail; the
  decision rule pre-registered and applied.
- **Handoff:** commit results, tick P0-9 in `HANDOFF.md`, record the decision.

## Session 5 — Human verification (Task 7)

- **Manual.** The agent generates the review sheet (`data/gold_v2_review.md`) in 1–2 turns; the
  **user** opens each labelled page and fills the verdict column.
- **Deliverable:** `label error rate = X/25 = Y%` recorded in `IMPROVEMENTS.md` §F4b.

---

## Boundary ritual (every session)

1. `uv run pytest tests/ -q -m "not slow"` — must stay at the regression floor.
2. `git commit` — **tick the plan item in the same commit that completes it.**
3. Update `HANDOFF.md` "Current focus" — re-measure any counts against the store; never copy a
   number out of a compacted summary.
4. `/new`.

## Open housekeeping

- `calibration_output.txt` (repo root) is **untracked** and referenced by the visual-calibration
  work. Commit it or drop the reference — a fresh clone loses a local-only path silently.
