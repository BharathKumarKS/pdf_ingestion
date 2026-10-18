# P1 Step 8 — THE RUN (evidence + pre-flight record)

**Date:** 2026-10-17 · branch `feat/p0-9-gold-dataset-v2` · author model `deepseek/deepseek-v4.1-flash`

**Status: 🔄 IN PROGRESS** — the run started 20:05:54 and is the Docling parse of the 968-page
book at the time of writing. This file is updated with the final counts when it completes.

Register: `IMPROVEMENTS.md` §E7 (this step), §I14, §I15 · Plan: `.hermes/plans/2026-10-16-p1-reingest-plan.md` §5 Step 8

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

## Verification of the real run (to be filled in on completion)

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
