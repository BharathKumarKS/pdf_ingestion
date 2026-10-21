# P1 Step 10 — prerequisite: rebuild the Memgraph concept graph. Execution plan.

> **Written 2026-10-18, after the Step 10 §1 gate failed twice.** Read `HANDOFF.md` for current
> state and `IMPROVEMENTS.md` §D14 for the finding this executes. This file is the *procedure*; it
> is not a register.
>
> **Why this exists.** Step 10's preflight gate (`scripts/preflight.py`) exits 1 on
> `graph.matches-qdrant`: **5,051/5,051 graph chunk ids absent from `knowledge_base_v2` (100.0%)**.
> The graph holds only the **previous** ingest's document (`6d55c52b`, 5,048 chunks); the re-ingested
> document (`7ba61432`, 3,796 chunks) has no graph at all. Chunk ids are `uuid4()` per ingest
> (`chunker.py:147`), so the two id sets are disjoint **by construction** — no environment action
> clears this. **Owner decision 2026-10-18: build the graph** (fix (c) of §D14), which pulls forward
> the graph half of **Step 9**, deferred by Step 10 plan §5.
>
> **Scope of the deviation:** this does **only** the Memgraph graph. Step 9's other halves — Phase 2
> cards + RAPTOR, and the ColPali visual re-index — stay deferred. Nothing here gates on them.

---

## Preconditions — re-verify, do not assume

| # | Claim | Verified |
|---|---|---|
| P1 | Memgraph reachable on `localhost:7687` | ✅ 2026-10-18 v2.18.1, `docs=1 chunks=5051 concepts=7815` |
| P2 | `knowledge_base_v2` = 3,796 points, doc `7ba61432` | ✅ preflight PASS, `colbert,dense_1024,dense_64` |
| P3 | SQLite holds doc `7ba61432` with 3,796 chunks | ✅ 2026-10-18 |
| P4 | Cluster LLM answers (`openai/gpt-oss-20b` @ `10.0.10.70:8000`) | ✅ preflight `llm.completion -> 'OK'` |
| P5 | Legacy Nomic embedder cached locally (concept-name vectors) | ✅ `data/models/models--nomic-ai--nomic-embed-text-v1.5` |
| P6 | `concept_embeddings` = 768d cosine, 11,229 points | ✅ 2026-10-18 |

⚠️ **Container health is not a signal here.** `synapse_memgraph` reports `unhealthy` permanently
because its compose healthcheck runs `mg_client`, which does not exist in `memgraph/memgraph:2.18.1`
(§D14). Check **Bolt on 7687**, never `.State.Health.Status`.

---

## G1. Resolved-settings gate — assert what is actually in force

```bash
export QDRANT_HOST=10.0.10.65
export QDRANT_COLLECTION=knowledge_base_v2
uv run python scripts/run_phase3.py --doc-id 7ba61432-c5e0-416d-aecf-25a232523481 --graph-only
```

Run it through `logs/p1/step10/run_graph.sh` (already written), which prints the resolved settings
and **asserts** `use_stub_graph`, `use_stub_llm`, `use_stub_embedder` are all **false** before
launching. `.env` overriding a config default is how Step 8 attempt 3 ran at 8 workers while
everyone believed 4 — the gate exists so that cannot happen silently again.

**Verifier:** the script prints the resolved settings and `ASSERTIONS OK`, then reaches the build.
**Any assertion failure → stop.**

---

## G2. Before-state snapshot + a one-chunk LLM probe

Two cheap checks before spending an hour of cluster time.

**G2a — snapshot the "before".** Node/edge/chunk counts per document, plus the
`concept_embeddings` point count, to `logs/p1/step10/graph_before.json`.

**Verifier:** the file exists; the graph holds exactly **1** document (`6d55c52b`) and **0** chunks
for `7ba61432`.

**G2b — probe concept extraction on ONE chunk.** Call `GraphBuilder._extract_concepts` on a single
real chunk from the re-ingested document.

**Verifier:** the probe returns **≥1 concept with a non-empty `name`** and parses as JSON.
**If it returns 0 concepts → STOP.** `call_llm` returns `""` on failure and
`_extract_concepts` catches every exception, so a broken LLM silently yields empty concepts; this
probe is the only cheap place to catch it before a 3,796-chunk run produces an empty graph.

---

## G3. Build the graph for the re-ingested document

```bash
bash logs/p1/step10/run_graph.sh      # background; ~45–90 min estimated
```

`--graph-only` skips ColPali entirely and sets `force_graph=True`, so the graph is built
unconditionally. `build_graph` **MERGEs by id**, so re-running this step is idempotent.

**Cost:** one LLM call per chunk × **3,796 chunks** at `concept_gen_workers=4`, plus sequential
local-CPU embedding of every unique concept name with the legacy Nomic embedder. Estimated 45–90
min; measured, not guessed, once it runs.

**Verifier — count nodes in Memgraph, NOT the script's own stats.** The script prints
`concept_nodes` / `edges` from `graph_stats`, but `build_graph`'s `failed` counter can **never
increment**: `_extract_concepts` swallows every exception and returns an empty concept list, so the
future never raises. An LLM outage therefore produces an **empty graph reported as "0 failed"**.
Assert instead, from Bolt:

1. the run exits 0;
2. the graph now holds **2** documents, and `7ba61432` has **3,796** `Chunk` nodes (== SQLite chunks
   for that document — a count mismatch means a partial write);
3. `7ba61432` has **> 0** `Concept` nodes and `> 0` edges;
4. the concept density is in family with the old document: old = **7,815 concepts / 5,051 chunks ≈
   1.55 per chunk**. **Fail if the new document's ratio is below half of that (≈ 0.78)** — that is
   the signature of mass silent extraction failure, and it is the number the script will not show.

**Any failure → stop and report; do not proceed to G4.**

---

## G4. Remove the OLD document's graph — ⚠️ DESTRUCTIVE, separate decision

**This step is what actually makes the gate pass, and it is the one with a live consequence.**

G3 is additive: afterwards the graph holds both documents, so `graph.matches-qdrant` would report
5,048/8,844 ≈ **57 % dangling** — still a FAIL. The old document's nodes must go.

```bash
uv run python scripts/clean_stale_graph.py --qdrant-host 10.0.10.65 --dry-run
uv run python scripts/clean_stale_graph.py --qdrant-host 10.0.10.65 --yes
```

The tool's source of truth is `cfg.qdrant_collection`, so `QDRANT_COLLECTION=knowledge_base_v2` must
be exported — that is what makes `6d55c52b` stale and `7ba61432` live.

**⚠️ Consequence to accept explicitly:** the deleted graph is the one belonging to the
**currently-deployed** `knowledge_base` (5,135 points). Removing it degrades the deployed app's
multihop lane until the cutover. `graph_search` filters on **tenant, not `document_id`**, so while
both documents coexist the multihop lane also returns unresolvable old-doc chunks — i.e. the graph
is already degraded by G3 and G4 is the repair, not the damage. Plan R1's "old index untouched"
applies to the **Qdrant collection**, which this step does not touch.

**Verifier (before applying):** `--dry-run` reports exactly **1** stale document (`6d55c52b`,
5,048 chunks) and marks `7ba61432` **"keep (has vectors)"**. If any other document is marked stale,
**stop** — the run is pointed at the wrong Qdrant.

**Verifier (after applying):** the graph holds **1** document (`7ba61432`) with **3,796** chunks.
Never pass `--force`: its no-overlap guard refusing (exit 2) is the correct outcome for a
mis-pointed run, and `--force` defeats the only safety this tool has.

---

## G5. Re-run the gate

```bash
export QDRANT_HOST=10.0.10.65
export QDRANT_COLLECTION=knowledge_base_v2
uv run python scripts/preflight.py
```

**Verifier:** **exit 0**, and `graph.matches-qdrant` reports **< 1 % dangling** (it was 100 %).
This is the precondition Step 10 §1 demanded; only then does the ablation (Step 10 §2) start.

---

## G6. Register

- **§D14** — record that fix (c) was taken, with the measured before/after dangling %.
- **Step 9** — record that its **graph half is now done** (Step 9's remainder: Phase 2 cards +
  RAPTOR, ColPali visual re-index). This is a *partial* discharge of a deferred item, so say so
  explicitly rather than marking Step 9 done.
- **HANDOFF.md** — the "IMMEDIATE NEXT STEPS" list currently says Step 10 §1 is the next action;
  update it to name this prerequisite.
- Every number quoted must grep back to `logs/p1/step10/`.

---

## Explicitly NOT in this step

- **ColPali / `visual_knowledge_base`** — `--graph-only` skips it; the visual re-index stays with
  Step 9. (`visual_knowledge_base` is currently 1,033 points, not the 2,835 of §B4b — already
  changed; re-check after the re-ingest.)
- **Phase 2 cards + RAPTOR** — the other half of Step 9, still deferred.
- **`concept_embeddings` migration to 1024d** — §I12; the graph lane stays on the legacy 768d lane
  by design for now. G3 *adds/updates* concept vectors; it does not retire the old ones.
- **`clean_stale_visual.py`** — not applicable while ColPali is skipped.
- **Step 10 §2–§4** (the ablation, the §D4 label re-derivation, the decision) — unchanged, and they
  resume only after G5 passes.
