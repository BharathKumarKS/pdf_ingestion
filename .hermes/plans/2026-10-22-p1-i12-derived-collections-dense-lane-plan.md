# P1 §I12 — move the derived collections onto the dense lane (drop & recreate). Execution plan.

> **Written 2026-10-22. FOR SIGNOFF — nothing in this plan has been run.** The *code* half is
> already committed (`6773022`); this plan is the **data** half, which is the only part left.
> Read `IMPROVEMENTS.md` §I12, §I13, §I47 and `HANDOFF.md` open-decision (v) before executing.

---

## 0. SETTLED — this plan supersedes these earlier statements

| Earlier statement (where) | Superseded by |
|---|---|
| "`concept_embeddings` → 1024d (§I12) — **the graph lane stays on the legacy 768d lane for now**" (`2026-10-18-p1-graph-analytics-plan.md` §"Explicitly NOT in this step") | **This plan.** The code move landed in `6773022`; the data move is now required, not deferred. |
| "`GraphBuilder.build_graph` MERGEs by id, so re-running is **idempotent** for this document" (`logs/p1/step10/run_graph.sh:14`) | **False for `RELATES_TO`.** The write is `MERGE … ON MATCH SET r.weight = r.weight + 1`, so a re-run **doubles the edge weights** (§I43's duplication class, in the graph). The graph must be **cleared** before any re-run. |
| `config.py:45` comment: `embedding_dim: int = 768  # legacy Nomic dense dim (DA + concept collections)` | **Stale.** Both collections are now created at `dense_dim` (`database.py:354`, `:380`). The comment names a lane they no longer use — see §7 hygiene. |

If any of the three appears again in a document this plan does not list, the plan wins.

---

## 1. What is already done (code — verified by reading, not assumed)

| Piece | Where | State |
|---|---|---|
| `derivative_artifacts` created at `dense_dim` | `src/core/database.py:348-354` (`_ensure_da_collection`) | ✅ `VectorParams(size=cfg.dense_dim)` |
| `concept_embeddings` created at `dense_dim` | `src/core/database.py:374-380` (`_ensure_concept_collection`) | ✅ `VectorParams(size=cfg.dense_dim)` |
| Concept **names** embedded on the dense lane | `src/pdf_ingestion/graph_builder.py:355-362` | ✅ `get_cluster_embedder(cfg).embed_query(name)` |
| Loud dimension guard, **before** the expensive half | `graph_builder.py:249-256` → `_assert_collection_dim` `:582-609` | ✅ raises `RuntimeError` naming the fix |
| DA re-index builds on the dense lane | `scripts/index_derivative_artifacts.py:104-122` | ✅ `get_cluster_embedder` + `embed_documents`; `--clear` deletes + recreates |
| Preflight probes lane **dimension**, not just point count | `scripts/preflight.py:151-176` | ✅ FAILs when `size != dense_dim` |
| UI graph lane on the dense lane (second 768d vector deleted) | `src/frontend/streamlit_app.py:603`, `:1312-1317` | ✅ `get_cluster_embedder(cfg).embed_query(...)` |

**What is NOT done — the data on the cluster:**

| Collection | Points | Dim | State |
|---|---|---|---|
| `concept_embeddings` | **15,276** | **768d** | accumulates across ingests; no `document_id` in payload |
| `derivative_artifacts` | **81,837** | **768d** | retired card generation; id overlap with SQLite = 0; 5 of 8 card types |

Both are 768d while every query carries the dense lane's 1024d, so **both lanes return `[]` on every
query** — §I12 (DA, every query) and §I47 (graph, every multihop query). This plan fixes both.

---

## 2. The two halves are INDEPENDENT — run them in parallel

    Lane A — DA lane (derivative_artifacts)      ─┐
      independent of the graph and of Lane B     ├─ run concurrently
    Lane B — graph lane (concept_embeddings)     ─┘

Lane A never touches Memgraph. Lane B never touches `derivative_artifacts`. They share no resource
except the cluster's embedding endpoint (`10.0.10.70:8123`) — the only contention point, and it is
read-only fan-out. **Order between A and B does not matter.** What DOES matter is §6: Lane B must
land **before §G3**.

---

## 3. Lane A — `derivative_artifacts` (one existing command)

**Command (single step; `--clear` already drops, recreates at `dense_dim`, and re-indexes):**

    uv run python scripts/index_derivative_artifacts.py --clear \
        --doc-id 7ba61432-c5e0-416d-aecf-25a232523481

**Why the `--doc-id` scope is mandatory, not optional:** the script's own SQLite query filters
`Card.is_active == True` **only** (`index_derivative_artifacts.py:128-137`). SQLite holds the OLD
document's 82,164 cards alongside the current document's 75,645. Without `--doc-id` the run would
index **both** generations into the freshly-cleared collection — the exact accumulation this plan
exists to remove.

⚠️ **OWNER DECISION REQUIRED before running (A-decide):** which document should the DA lane serve?
The candidate is `7ba61432` (the Step 8 re-ingest, the one being evaluated). The alternative is to
index every active card regardless of document. State the choice; do not let the script's default
decide it. **Pre-registered default: `--doc-id 7ba61432-…`**, on the grounds that DA exists to serve
the evaluated index.

### Lane A verifiers (each must be able to FAIL)

| # | Check | Command / probe | Before (expected) | After (required) |
|---|---|---|---|---|
| A1 | collection dim | `preflight.py` → the `qdrant.derivative_artifacts.dim` record | `768d … REJECTED` (FAIL) | `1024d == dense_dim — lane is callable` (PASS) |
| A2 | point count > 0 and **scoped** | count points; compare against active cards for `7ba61432` | 81,837 (retired generation) | == active-card count for the doc, ±0 |
| A3 | **the lane actually returns** (the §I47 discriminator) | `DocumentStore(cfg).search_da(dense_vec_1024, tenant)` | `[]` (dim rejected) | **> 0 hits** |
| A4 | card types present | distinct `card_type` over the collection payload | 5 of 8 | **8 of 8** (`ALL_CARD_TYPES`) |
| A5 | nothing else moved | point counts of `knowledge_base_v2`, `visual_knowledge_base` | — | **unchanged** |

**A3 is the load-bearing check.** A1/A2 are structural; A3 is the effect the whole move exists for,
and it is the one §I12's own log line proved was missing (`a3d_retrieval_only.log`, 167 skips).

---

## 4. Lane B — `concept_embeddings` (drop → rebuild)

There is **no** "re-embed concepts only" script in the tree (checked: no `scripts/*concept*`).
`scripts/reset_for_reingest.py` would delete the right collection — **and also `knowledge_base` and
every SQLite row** (`reset_for_reingest.py:39-43`, `:92-106`). It is **too broad for this job** and
must not be used here.

**Lane B is therefore two steps: (B1) drop, (B2) rebuild.**

### B1 — drop `concept_embeddings` only

`get_qdrant(cfg)` recreates it at `dense_dim` on the next call (`database.py:244-245`), so the drop
is all that is needed; the guard at `graph_builder.py:249` then passes.

**NEW script required:** `scripts/reset_derived_collections.py` (modelled on
`clear_graph_document.py`'s safety shape — the project's convention for destructive ops):

- **dry-run is the DEFAULT**; `--yes` applies. No `--force`.
- an **allowlist** of droppable collections (`derivative_artifacts`, `concept_embeddings`); any other
  name — `knowledge_base`, `visual_knowledge_base` — is **refused, exit 2**. This is the guard that
  stops a typo from deleting the index, and its refusal is the strongest evidence the run is pointed
  at the right target.
- prints, per collection: name, point count, **dim**, and the source it will be repopulated from
  (SQLite active cards / Memgraph `Concept` nodes) — so the dry-run names exactly what is removed.

    uv run python scripts/reset_derived_collections.py --collections concept_embeddings        # dry-run
    uv run python scripts/reset_derived_collections.py --collections concept_embeddings --yes  # apply

**NEW code ⇒ its own verifier (§5 step B1):** the allowlist refusal must be proven to discriminate
(passing `knowledge_base` must exit 2 and delete nothing), and the dry-run must be run against the
live cluster and its output saved.

### B2 — rebuild the graph, which repopulates `concept_embeddings` at 1024d

⚠️ **The graph MUST be cleared first.** `build_graph` has no delete step and its edge writes are
`MERGE … ON MATCH SET r.weight = r.weight + 1`, so a rebuild over the existing graph **doubles every
`RELATES_TO` weight**. The clear is already built and verified (`scripts/clear_graph_document.py`,
`f007f85`).

    # 1. clear the document's graph (dry-run first, then --yes)
    uv run python scripts/clear_graph_document.py --doc-id 7ba61432-c5e0-416d-aecf-25a232523481
    uv run python scripts/clear_graph_document.py --doc-id 7ba61432-c5e0-416d-aecf-25a232523481 --yes

    # 2. rebuild — the checkpoint reuses all 3,533 extractions, so only embed+upsert+write repeat
    uv run python scripts/run_phase3.py --doc-id 7ba61432-c5e0-416d-aecf-25a232523481 --graph-only

**Why this is cheap:** the extraction checkpoint
(`data/graph_cache/7ba61432__9e758046e4a15115.jsonl`, present on disk) is keyed on
document + model + prompt digest. The extractor is unchanged (`Qwen/Qwen3-VL-8B-Instruct`), so the
3,533 extractions are **reused** and the run repeats only the embed + upsert + Memgraph-write phases
— minutes, not the 62 min the extraction took. **Verify the reuse, do not assume it:** the log must
show `N already checkpointed` with N == 3,533 and a low `pending` count.

⚠️ **Do not resume a partially-written build across this change.** The collection is dropped between
B1 and B2; a build launched before B1 and resumed after would upsert 1024d vectors into a collection
it believes is 768d (or vice versa). The guard catches it loudly — that is the point — but do not
create the situation.

### Lane B verifiers

| # | Check | Before (expected) | After (required) |
|---|---|---|---|
| B1a | allowlist discriminates | — | `--collections knowledge_base` → **exit 2**, nothing deleted |
| B1b | dry-run names the target | — | prints `concept_embeddings`, 15,276 pts, **768d** |
| B2a | guard passes (was the sequencing hazard) | would `raise` (768d ≠ 1024d) | **no raise** — build proceeds |
| B2b | extraction reused, not re-paid | — | log: `3,533 already checkpointed`, `failed_chunks = 0` |
| B2c | collection dim | 768d | **1024d == dense_dim** (`preflight.py` `qdrant.concept_embeddings.dim` PASS) |
| B2d | points ≈ distinct concepts in Memgraph | 15,276 (stale accumulator) | **== distinct `Concept` count** (expect ≈ 7,427; §I22: count it in Memgraph, never read the run's `concept_nodes`) |
| B2e | **the lane actually returns** (the §I47 discriminator) | `_find_concepts_scored(np.zeros(1024))` → **0** concepts | **> 0** concepts |
| B2f | graph edge weights NOT doubled (⚠️ **not** the edge COUNT — see below) | — | `min(RELATES_TO.weight) == 1` (a doubled build re-matches every edge, so min would be 2); measured: min 1, 93.1 % at weight 1, max 24 |
| B2g | §I21 still live | — | 3,533 chunk nodes, not 3,796 |

**B2e is the load-bearing check**, exactly as A3 is for Lane A. It is §I47's own probe:
`_find_concepts_scored(np.zeros(1024))` → 0 before (dim rejected), `>0` after.

---

## 5. Pre-registered outcome rule

- Lane A is **done** iff A3 returns `> 0` hits **and** A1/A4/A5 hold.
- Lane B is **done** iff B2e returns `> 0` concepts **and** B2c/B2d/B2f/B2g hold.
- An empty lane after the move is a **FAIL**, not an unresolved result: the move's entire purpose is
  to make the lanes callable. There is no "unresolved" reading here — a lane that returns `[]` is the
  state the plan exists to leave.
- **§I12 and §I47 are closed** when both lanes return non-empty in `evaluate_rag.py`'s own harness
  (not only in the probe), which also requires the harness's DA-lane skip count to reach **0**.

---

## 6. ORDERING vs the rest of the graph work (this is the part that pays twice if missed)

    NOW, parallel:   Lane A (DA)   ||   Lane B (concept_embeddings rebuild)
                     ────────────────────────────────────────────────────
                     then §G3 (entity resolution)  →  then §G2 (communities)

**Lane B must land BEFORE §G3.** §G3 merges near-duplicate `Concept` nodes in Memgraph, which changes
the concept-name set that `concept_embeddings` holds. If §G3 ran first, the Lane B rebuild would
re-extract and rewrite the graph from the checkpoint and **undo the merge** — the same work, paid
twice. And if Lane B ran and §G3 then merged, `concept_embeddings` would hold pre-merge aliases —
stale again. So:

1. **Lane B** rebuilds the graph (clean node set, 1024d concept_embeddings).
2. **§G3** merges — and, as part of its scope, **syncs `concept_embeddings`**: delete the merged
   aliases' points (point id is `uuid5("concept:{name}")`, `graph_builder.py:634`) and keep the
   canonical survivor's. This is written into the §G3 plan as a required step, because a merge that
   leaves the ANN index holding deleted names re-creates §G1's measured confound.

Lane A has no such coupling and may run at any time.

---

## 7. Register, at the end

- **§I12 closed** (both lanes callable), **§I47 closed** (graph lane live on multihop).
- **§I13** — re-check its two scripts (`reembed_chunks.py`, `validate_embedders.py`): the session-6
  update says `validate_embedders.py` is done and `reembed_chunks.py` now refuses; confirm both still
  hold after this move.
- **Hygiene finding to register:** `src/core/config.py:45` still comments `embedding_dim` as
  "(DA + concept collections)" — false since `6773022`. A migration note left in code outliving the
  migration is the §I13-adjacent class; fix the comment in the same pass.
- **`run_graph.sh:14`'s "idempotent" comment is wrong** (see §0) — correct it, since it is the file a
  future session copies to re-run the build.

---

## 8. Explicitly NOT in this plan

- **No Phase-1 re-ingest.** Neither lane change touches `knowledge_base_v2`, the chunker, or
  embeddings of chunks. `is_content` (the §E5 filter) is written at ingest, so the card/retrieval
  lanes' re-ingest stays its own deferred item.
- **No §G3 merge.** That is the §G3 plan; this one only prepares the substrate §G3 runs on.
- **No `--force`** on any script. `reset_for_reingest.py` is **not used** (too broad — §4).
- **Not the deployed `knowledge_base`** (v1, doc `6d55c52b`). This plan moves the collections the
  re-ingested index uses; the deployed app's lanes are a separate cutover decision.
