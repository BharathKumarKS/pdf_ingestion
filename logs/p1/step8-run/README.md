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
