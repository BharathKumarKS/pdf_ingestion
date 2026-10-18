# P1 Step 8 — THE RUN (evidence + pre-flight record)

**Date:** 2026-10-17 · branch `feat/p0-9-gold-dataset-v2` · author model `deepseek/deepseek-v4.1-flash`

**Status: ⛔ ATTEMPT 1 FAILED** — ran 2026-10-17 20:05:54 → 21:32:15 (**86 min**, exit 1), killed by
a transient `httpx.ReadTimeout` on the per-token endpoint at **parent 260 of 341**. Nothing was
written. Diagnosis, the measured throughput and the root cause are below; the re-run is blocked on
**§I16**.

Register: `IMPROVEMENTS.md` §E7 (this step), §I14, §I15, **§I16** · Plan: `.hermes/plans/2026-10-16-p1-reingest-plan.md` §5 Step 8

> **Note on the directory name.** `logs/p1/step8/` already holds **Step 7b's** evidence (the
> query-side dense-lane switch — it took that name because it is Step 8's prerequisite).
> Step 8's own evidence lives here, in `logs/p1/step8-run/`, so the two are not conflated.

## The command

```bash
QDRANT_HOST=10.0.10.65 \
SV_EMBED_URL=http://10.0.10.70:8123/embed-text/v1/embeddings \
  uv run python scripts/ingest_base_textbook.py \
      --pdf data/base_textbooks/feynman-lectures-on-physics-volume1.pdf \
      --collection-name knowledge_base_v2 \
      --title "The Feynman Lectures on Physics, Volume I" \
      --subject Physics --grade Undergraduate \
      --reindex
```

Wrapped as `run_step8.sh` (tracked; the `.log` it writes is gitignored, per this repo's
convention — no `*.log` is tracked anywhere).

**Why a new collection (plan R1 / R-d):** the deployed `knowledge_base` (5,135 points,
`dense_768`) is left completely intact, so a failed run costs nothing and the old index stays
queryable. Rollback = point `QDRANT_COLLECTION` back at `knowledge_base`.

**Why each env value is on the command line rather than in `.env`:**

| var | why |
|---|---|
| `QDRANT_HOST=10.0.10.65` | blank in `.env` (that is the "use the local file store" default). The cluster Qdrant is at the IP — the hostname `ansatz` inside the cluster's own URLs does **not** resolve from this Mac. |
| `SV_EMBED_URL=…:8123/embed-text/v1/embeddings` | **absent from `.env` entirely** (§I14) even though §E6 moved the whole query side onto this lane. Without it `ClusterDenseEmbedder.__init__` raises. |
| `--reindex` | `ingest_base_textbook.py` skips a PDF whose filename is already in `documents`. The old Feynman doc (`6d55c52b`) is there, so without this flag the script prints *"already ingested"* and **exits 0 having done nothing** — a green run that changed nothing. |

## Pre-flight (all of it measured, none of it assumed)

### 1. The cluster is up and the target is clean

| probe | result |
|---|---|
| Qdrant `10.0.10.65:6333` | 200 — collection list returned (includes the deployed `knowledge_base`) |
| deployed `knowledge_base` | **5,135 points**, named vectors `colbert` (128, Cosine) / `dense_64` (64) / `dense_768` (768) — unchanged, untouched by this run |
| `knowledge_base_v2` | **absent** before the run — no stale points to collide with (R-d) |
| dense lane `10.0.10.70:8123/embed-text/v1/embeddings` | 200, real 1024d vector returned |

### 2. The two optional lanes — because `save_document` hides their failures

`DocumentStore.save_document` wraps SPLADE and ColBERT in `try/except Exception ->
logger.warning(..., falling back to dense-only)`. A dead lane therefore does **not** fail the
ingest: the run completes, prints the green success panel, and writes points carrying only
`dense_64` + `dense_1024`. Every count-based check the plan prescribes would still pass on that
incomplete index. That is **§I15**, and it is why this probe exists.

`probe_embedders.py` (live, 2026-10-17) resolves each factory, prints the implementation chosen,
and encodes real text:

| lane | resolved implementation | result |
|---|---|---|
| SPLADE | `ClusterSpladeEmbedder` (`:8000/embed-text/v1/sparse-embeddings`) | **ok** — 2 vectors, 60 non-zero indices, max value 2.370, 0.2 s |
| ColBERT | `ClusterColBERTEmbedder` (`:8000/embed-text/v1/multivector-embeddings`) | **ok** — 2 matrices, shape `(20, 128)`, 0.2 s |

**Both are cluster-served**, so no local model download is on the critical path. (The earlier
assumption that SPLADE would fall back to fastembed ONNX — and need `prithivida/Splade_PP_en_v1`,
which is *not* in the HF cache — was wrong: `SV_SPARSE_URL`/`SV_COLBERT_URL` **are** set in `.env`,
pointing at `:8000`. `.env.example` says `:8123` for the same three services; both ports answer.
That disagreement is the §I11 class and is recorded in §I14.)

### 3. The dry run — the exact entry point, 19-page fixture, real cluster

`dryrun_testbook.sh` → `dryrun_testbook.log`. Writes to a **throwaway** collection
(`knowledge_base_probe`, deleted afterwards) and a **scratch** SQLite (`data/step8_probe.db`,
removed), so neither the deployed index nor `data/synapse.db` is touched.

**82 s wall.** 42 parents → 66 children → 66 Qdrant points.

| stage | time | note |
|---|---|---|
| Docling parse + parents | ≈ 10 s | of which ~9 s is the one-time model load |
| semantic children | 0.8 s | |
| late-chunk embed (42 parents) | **47.5 s** | the per-token cluster calls — the dominant cost |
| SPLADE (66 chunks) | 6.4 s | 0.097 s/chunk |
| ColBERT (66 chunks) | 9.8 s | 0.148 s/chunk |
| Qdrant upsert | 1.5 s | |
| **total** | **82 s** | |

`verify_collection.py` on the probe collection (→ `verify_probe.json`):

| check | result |
|---|---|
| named vectors present | `colbert` 128 · `dense_1024` 1024 · `dense_64` 64, all Cosine |
| sparse vector present | `sparse` |
| **points carrying each lane** | colbert 66/66 · dense_1024 66/66 · dense_64 66/66 · **sparse 66/66** |
| points scrolled == reported | 66 == 66 |
| Qdrant points == SQLite chunks | 66 == 66 (same `document_id`) |
| `all_lanes_on_every_point` | **true** |

## What the dry run taught that the plan does not say

1. **Scope the count check by `document_id`.** `save_document` always mints a **new** document
   uuid, so the run *adds* a second `documents` row with the same filename and a second block of
   rows in `chunks`; the old doc (`6d55c52b`, 5,048 chunks) is deliberately left in place because
   its points live in the deployed collection. "Collection points == SQLite chunks" is therefore
   only true **per document**, not against the raw table — against the raw table it will read as a
   mismatch of exactly the old corpus. The admin document list will show the same filename twice
   until the old doc is retired (Step 10 / §E6 territory; nothing changed here).
2. **This run applies the pending SQLite migrations.** `chunks.parent_id` and `chunks.is_content`
   are added on first `get_engine()` against the deployed `data/synapse.db`. The existing 5,048
   rows get **NULL**, which is the intended §E5 behaviour: the retrieval filter is
   `must_not is_content == False`, so a NULL row is *not* excluded and the deployed index is
   unaffected.
3. **One probe artifact, not a defect:** the probe reported `without_parent_id: 1`. That child's
   `parent_id` is the string `"0"` and the check was `if payload.get("parent_id")` — falsy for a
   zero-valued field, not a missing one. All 66 children carry a parent.

## Attempt 1 — the failure (2026-10-17 20:05:54 → 21:32:15, 86 min, exit 1)

It got **further than the plan expected, and then lost all of it.**

| phase | result |
|---|---|
| Docling parse, 968 pages | **4 min** (20:05:59 → 20:09:58) — not the "tens of minutes" the plan feared |
| parents / children | **341 parents → 3,796 children** |
| late-chunk phase | **260 of 341 parents** completed (20:10:03 → 20:50:26 = 40.4 min, 360,685 tokens, 2,905 children) |
| parent 260 | per-token POST to `:8123` raised `httpx.ReadTimeout` → **process aborted** |
| written | **nothing** — `knowledge_base_v2` = 0 points; SQLite still holds only the old doc |

**Nothing partial was left behind.** `save_document` is the single write point and it runs only
after *every* parent is embedded, so an abort anywhere in the embedding phase leaves both stores
untouched. (The one side effect is the SQLite migration, which is intended and harmless — see
"What the dry run taught", point 2.)

### It was variance, not an outage

A pooled call to the same endpoint returned **200 in 0.14 s immediately after** the abort. The
endpoint was up. What the 260 completed parents show (parsed from the log):

| measure | value |
|---|---|
| per-parent time | median **5.13 s**, mean 9.35 s, **max 136.5 s** |
| parent size | median 1,190 tokens, mean 1,387, max 4,762 |
| throughput | median **214 tokens/s**, **min 9** |
| drift across the run | first 50 parents **10.8 s** avg → last 50 **16.5 s** avg, at near-identical token counts (1,378 vs 1,472) |
| worst case | parent 219: **136.5 s for 1,180 tokens** |

Two things follow. The endpoint **degrades as the run proceeds**, so the tail is the risky region
— and the abort landed exactly there. And the fatal stall had **already happened once** at parent
219 and been survived by luck, which is why re-running unchanged is a coin-flip rather than a fix.

### Root cause: §I16 — no retry, no checkpoint

`ClusterDenseEmbedder._post` (`cluster_embedder.py:150-177`) builds `httpx.Client(timeout=120)`
and issues each batch as a **single un-retried POST**. Any timeout propagates through
`LateChunkEmbedder.embed_parent` and kills the document. Two aggravating facts:

- **The 120 s timeout does not bound the damage.** httpx's read timeout is per *read operation*,
  not per request. The per-token response is ~160× the pooled one (§E3), so a trickling body
  resets the timer on every chunk — the measured gap between the last success and the abort was
  **42 minutes**, consistent with a slow drip.
- **The ingest has no checkpoint.** Loss is per *document*, not per parent.

**Fix (not applied):** bounded retry with exponential backoff in `_post` + a read timeout sized
for the per-token payload; optionally a per-parent checkpoint. The retry is the small fix and the
one that would have saved this run.

### What a re-run costs

Extrapolated from the measurements: ≈ 62 min late-chunk + 4 min parse + ~6 min SPLADE + ~9 min
ColBERT ≈ **1.5 h**, of which the last third is the risky region.

## The fix (2026-10-17, same session) — retry + concurrency

### What changed

| file | change |
|---|---|
| `src/pdf_ingestion/cluster_embedder.py` | `_post` now goes through `_post_with_retry`; read timeout is per path (120 s pooled / **300 s per-token**) with a 10 s connect timeout |
| `src/pdf_ingestion/late_chunk_embedder.py` | `embed_children` embeds parents concurrently via `ThreadPoolExecutor`, reassembled in parent order; the tokenizer is warmed before the pool starts |
| `src/core/config.py` | `late_chunk_workers: int = 8` |

### Retry policy

Bounded at 1 + 3 attempts, jittered exponential backoff (2 s doubling, ×[0.5, 1.5)). Retries only
what could plausibly succeed — `httpx.TransportError` (verified to be the parent of
`httpx.ReadTimeout`: MRO `ReadTimeout → TimeoutException → TransportError`), HTTP 429, and 5xx.
Other 4xx fail immediately with no sleep: a malformed request fails identically every time.

The per-token timeout was raised on evidence, not caution — a measured 4,647-token parent took
**92 s** end to end, so the old flat 120 s was marginal for a legitimately slow healthy request,
and a false trip is its own bug.

### Concurrency: why 8, and why threads

Measured against the live endpoint, 1,749-token payload (`probe_concurrency_knee.py`):

| workers | wall s | req/s | tok/s | s/req |
|---|---|---|---|---|
| 1 | 20.83 | 0.05 | 84 | 20.83 |
| 2 | 17.82 | 0.11 | 196 | 8.91 |
| 4 | 34.27 | 0.12 | 204 | 8.57 |
| 8 | 36.28 | 0.22 | 386 | 4.53 |
| 16 | 46.90 | 0.34 | **597** | 2.93 |

Serial latency fits `seconds ≈ 5.2 + tokens/53` — a **~5 s fixed overhead per request**, which is
why 341 serial parents burned ~30 min in overhead alone and why concurrency pays. The knee was
still rising at 16, but 16 was a short burst on a cluster shared with other students, and the same
endpoint measurably degrades under sustained load (10.8 s avg on the first 50 parents → 16.5 s on
the last 50 in the failed run). **8 is the conservative default.**

Threads, not processes: the phase is ~100% HTTP waiting, so the GIL is released per request and
threads overlap the waiting. Processes would pickle large float matrices for no gain. (Docling
does use processes — it is genuinely CPU-bound.)

### Evidence that the output did not change

`test_worker_count_does_not_change_the_output` runs the serial and pooled paths over 6 parents and
asserts identical `chunk_id` order, identical `parent_id` order, identical `token_span`, and
`np.allclose` vectors. `test_workers_overlap_the_cluster_wait` proves genuine overlap (6 parents ×
0.25 s artificial delay complete in < 0.9 s). `test_a_failing_parent_aborts_loudly…` proves a lost
parent raises rather than silently shrinking the document.

### Test + lint state

| | before this session | after |
|---|---|---|
| fast suite | 361 pass / 4 fail / 6 skip | **371 pass / 4 fail / 6 skip** |
| ruff (touched files) | 4 findings | 4 findings — **no new** |

The 4 failures are the known pre-existing class (2 SPLADE fixtures, 2 zero-result searches).

## Independent review (round 1) — 2 reviewers, `openai/gpt-oss-20b`, single-turn, diff as DATA

| task | scope | verdict |
|---|---|---|
| 1 | `cluster_embedder.py` retry | `passed: true`, no findings |
| 2 | `late_chunk_embedder.py` + `config.py` | `passed: false`, 2 findings (both `risk`) |

**Adjudicated, not accepted.** Task 1's pass is **weak evidence, not strong**: 1 API call, 19.9 s
for a 200-line diff with seven specific questions — a read-and-agree pass. So each of its real
risks was checked directly instead:

| risk | checked how | result |
|---|---|---|
| is `httpx.ReadTimeout` actually a `TransportError`? | printed the MRO | **yes** — `ReadTimeout → TimeoutException → TransportError`; and `HTTPStatusError` is *not* a `TransportError`, so the `isinstance` order is irrelevant |
| does a per-request `timeout=` override an injected client's own timeout? | client set to 1.0 s, request set to 300 s, read `request.extensions["timeout"]` | **yes, 300.0 won** — the injected client is a transport carrier in tests, so this is the intended behaviour |
| can `assert last is not None` be stripped by `python -O` and change behaviour? | reasoned over the loop | **no** — the loop can only exit via `break`, which always sets `last` |

Task 2's two findings:

1. **"`int(getattr(...) or 1)` raises `TypeError` when the value is `None`" — FALSE.** The `or 1`
   is inside the `int()` argument, so it is evaluated first. Executed: `None → 1`, `-5 → 1`,
   attribute absent `→ 1`, `"6" → 6`. No `TypeError`. The reviewer misread the parenthesisation —
   the diff-only-reviewer failure mode this repo has now recorded three times.
2. **"the shared tokenizer is not thread-safe" — the stated reason is wrong, the concern is real.**
   Encoding from several threads *is* safe (`PreTrainedTokenizerFast` encodes through a `&self`
   Rust tokenizer and is used in multi-threaded data loading routinely). The genuine hazard is the
   **unsynchronised lazy load**: `_get_tokenizer` guards with a bare `if self._tokenizer is None`,
   so the first N workers can each pass the check and build the model concurrently — wasted work
   plus HuggingFace cache-lock contention, and silent. **Fixed** by resolving the tokenizer before
   the pool starts, pinned by `test_tokenizer_is_resolved_before_the_pool_starts`.

Round 1 therefore produced **one real, actionable finding** (the tokenizer pre-warm) and one
false positive. No claim was applied on faith.

## Still open after this fix

The retry does not cover every stall shape. httpx's read timeout is per *read operation*, not per
request, so a body that trickles indefinitely resets the timer and can outlive any timeout — the
failed run's 42-minute gap is consistent with exactly that. A hard total-request deadline (or a
per-parent checkpoint) would close it; neither is a small change. Registered as open in §I16
rather than claimed fixed.

## Attempt 2 — 2026-10-18 07:02:17 → 07:55:53 (53.6 min, exit 1)

Same pipeline, **with the §I16 fix live** (retry + 8 workers). It got further, faster, and then the
endpoint itself collapsed.

| phase | result |
|---|---|
| Docling parse | 07:02:17 → 07:05:13 — 341 parents, 3,796 children (**identical to attempt 1**) |
| late-chunk, healthy | **142 parents in 409.7 s = 2.89 s/parent, 470 tok/s** (attempt 1: 5.13 s/parent, 214 tok/s) |
| last parent completed | **07:12:05** |
| silent window | **21.5 minutes** — no log lines at all |
| first retry logged | 07:33:35 |
| retries | **597** (589 `ConnectTimeout`, 8 `ReadTimeout`) at a steady ~26/min until 07:55:36 |
| written | **nothing** — `v2` = 0 points, SQLite untouched |

**The retry did its job.** It converted "one bad read kills 86 minutes of work" into ~600 attempts
over 22 minutes instead of dying at the first timeout. It could not save the run because the
service was *actually gone*, not stalling — `ConnectTimeout` means nothing was accepting the
connection. That is the correct behaviour in both cases.

**The 21.5-minute silent window is the §I16 open item, now measured.** The workers sat inside
requests that never returned and never tripped a read timeout (httpx's read timeout is per *read
operation*, not per request), so the retry had nothing to catch until the sockets finally errored.
**A hard total-request deadline is the fix.**

### ⚠️ Did the 8 workers cause the collapse? Unproven, and not excludable.

| points to "yes" | points to "no" |
|---|---|
| healthy at 470 tok/s for 7 min under 8× load, then stopped accepting connections entirely — a crash/OOM signature, not a gradual slowdown | the endpoint measured **84 tok/s serial** that morning vs **214 tok/s** during attempt 1 — already ~2.5× degraded before attempt 2 started, independent of this client |
| 8 concurrent per-token responses, each up to ~19 MB, is a much bigger in-flight footprint than any probe exercised | other cluster services (`:8000` sparse, LLM) stayed healthy throughout |
| | Qdrant holds **34 collections from other students** — the box is shared and contended |

Honest reading: **a cluster-side problem that concurrent load may have accelerated.** Registered
as §I18, including the probe's blind spot — it fired a fixed **1,749-token** payload while the real
corpus runs to **4,762 tokens** (median 1,190), so "no collapse up to 16 workers" does not transfer
to 8 workers on this corpus. **8 is an unvalidated setting.**

### Next (recommended, in order)

1. **Re-run the ramp probe sweeping workers × payload size** (~5 min) — validate against the real
   size distribution instead of a mid-range constant.
2. **Add a hard total-request deadline** (§I16) — the higher-value robustness fix; without it one
   hung request can silently consume a run.
3. **Then attempt 3 at a validated worker count** (2–4 expected, not 8).

## Real-endpoint validation of the streaming deadline (2026-10-18)

The reviewer of the deadline diff returned `passed: true` with no findings — but with **1 API call
in 19.2 s**, the same read-and-agree pattern as before, and it did not engage with the one question
that decides whether the design works at all: **does `iter_bytes()` actually stream incrementally on
real traffic, or does httpx buffer the whole body and yield one chunk?** If it buffered, the
deadline would be a single check at the end and the tests (which use `MockTransport`) would be
proving nothing about production.

So it was measured against the **live endpoint** instead of argued:

| check | result |
|---|---|
| real streaming read | **18,719 chunks**, 65.9 MB, **time-to-first-chunk 0.66 s**, total 3.19 s |
| is it incremental? | **yes** — the deadline gets ~18,700 checkpoints per request, not one |
| new code path, real endpoint | per-token `(1682, 1024)` in 5.48 s · pooled `(1024,)` norm **1.000** · query `(1024,)` norm **1.000** |

The third row matters independently: the change moved the client from `client.post(...)` to
`client.stream("POST", ...)`, and **MockTransport cannot prove that swap is safe against a real
server**. It is — the per-token, pooled and query paths all return correctly-shaped, correctly
normalised vectors through the new code.

Recorded because "the mock passed" and "the endpoint works" are different claims, and only the
second one matters for a run against the cluster.

## Verification of the real run (pending a successful run)

```
uv run python logs/p1/step8-run/verify_collection.py knowledge_base_v2 \
    --sqlite data/synapse.db --out logs/p1/step8-run/verify_v2.json
```

This exits non-zero if any enabled lane is missing from any point (§I15), and prints the
per-`document_id` chunk counts alongside the collection's.

## Reproducing

```bash
bash logs/p1/step8-run/dryrun_testbook.sh                      # 82 s, throwaway collection
uv run python logs/p1/step8-run/probe_embedders.py             # both optional lanes, live
bash logs/p1/step8-run/run_step8.sh                            # THE RUN (~1.5 h, background)
```

## Files

| file | role |
|---|---|
| `run_step8.sh` | **the run** (tracked; writes `run_feynman.log`, gitignored) |
| `dryrun_testbook.sh` | the 19-page rehearsal against a throwaway collection |
| `probe_embedders.py` → `probe_embedders.json` | the two optional lanes resolved + encoded live |
| `verify_collection.py` | per-lane coverage of a written collection; non-zero exit on a gap |
| `verify_probe.json` | the dry run's verification record |
| `dryrun_testbook.log`, `run_feynman.log` | raw logs (local only — `*.log` is gitignored repo-wide) |
