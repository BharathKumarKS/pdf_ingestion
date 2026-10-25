# P1 — PLAN: adopt `embeddinggemma-300m` @768, move the low lane to 128d, and rebuild the index

> **Written 2026-10-24 (session 15) for EXECUTION IN THE NEXT SESSION.** Nothing in here is built.
> Read `HANDOFF.md` session 15 first, then `IMPROVEMENTS.md` §I70 / §I72 / §I73 / §I74 — those four
> entries are the evidence this plan executes. `ARCHITECTURE.md` §8 (Invariants and traps) before the
> first change.
>
> **The decision is taken by the owner (2026-10-24): `google/embeddinggemma-300m` @768.** The plan
> below is how it lands; it is not a re-litigation of the choice.

---

## §0 — WHAT THIS EXECUTES, AND WHAT IT IS NOT

**The evidence.** §I70 (oracle screen: gemma is the only arm that beats BOTH baselines), §I72 (the
base-lane gain survives the cross-encoder, halved: +0.1843 → +0.0976 vs the incumbent), §I74
(gemma vs nomic at the same stage: **+0.029248 [+0.004620, +0.053876]**, resolved but narrow — ~1.19×
the run's own resolution floor). ⚠️ **The narrow margin is part of the record**: the owner's decision
stands on a win the rule fixed in advance, and every downstream claim must quote the size, not just
the sign.

**⚠️ What this plan does NOT establish.** No product-endpoint measurement of gemma exists. §I70–§I74
are all **stage diagnostics** on a cosine-ordered pool. The one pre-registered product run is
**Stage F** below, and it is the only thing that can license a ship.

**⚠️ nomic was declined.** `nomic-embed-text-v1.5` is a same-width drop-in (MRL 64 keeps `dense_64`
true) and needs **no code change**; gemma needs the low lane widened **and** renamed. Recording this
as a **cost decision that declined the winning arm** is required by the pre-registration discipline —
it is not to be restated later as "nomic was worse".

---

## §1 — THE LANE NAME, AND THE ORDERING TRAP

**⚠️ The instruction "rename the index from 64 to 128d *after* widening the index" cannot be executed
in that order**, and the reason is a code fact, not a preference:

* `store.py:451` sends the prefetch against a **hardcoded** `using="dense_64"`, while the vector it
  sends is `query_vector[:cfg.dense_dim_low]` — so the name and the width are already independent in
  the *slice* and coupled in the *name*.
* `store.py:432` decides the schema with `has_new_schema = isinstance(vectors_cfg, dict) and
  "dense_64" in vectors_cfg` — the **literal string**.
* So a collection whose low lane is 128-dim must be *named* `dense_64` for today's code to find it,
  i.e. **the name would lie about its dimension** — §I13's trap, and the reason §I70 flagged the
  64d lane as gemma's adoption cost at all.

**⇒ The rename lands FIRST, as code; the 128-wide lane is created SECOND, under the new name.**

**The name (decision point 1).** Recommendation: **`dense_low`** — it describes the lane's *role*
(the funnel's fast first stage), not its width, so the next embedder change does not repeat this.
Alternatives rejected: `dense_128` (encodes the dimension — the exact defect being fixed), `dense_mrl`
(describes the *method*, and would lie again if a non-Matryoshka model is ever adopted).

⚠️ **The same defect exists on the full-dimension lane** — `dense_1024` / `dense_768` encode their
widths too. It is *less* urgent because `_dense_name_from()` resolves that name **off the
collection** (`_DENSE_VECTOR_NAMES = ("dense_1024", "dense_768")`), so a 768 lane already works with
no code change. **Decision point 2:** rename it to `dense_full` now (principled, larger blast radius:
store, preflight, every eval/probe script, the derived collections) or defer it and accept that the
next model change pays this again. **Recommendation: rename `dense_low` now (it is mandatory) and
defer `dense_full`, recorded as a known debt with the reason.**

**The new collection (decision point 3).** Recommendation: build into a **NEW collection
`knowledge_base_v3`** and leave `knowledge_base_v2` untouched and queryable. This is what makes
Stage F's A/B possible at all — the same reasoning that kept `dense_768` queryable on the deployed
`knowledge_base` (R1). Overwriting v2 destroys the only baseline.

---

## §2 — THE ACCEPTANCE SHAPE OF A GOOD `knowledge_base_v3`

The target schema, to be asserted rather than assumed:

| lane | kind | dim | source |
|---|---|---|---|
| `dense_full` *or* `dense_768` | dense | **768** | gemma, **late-chunked** (parent context) |
| `dense_low` | dense | **128** | gemma MRL slice, re-normalised |
| `colbert` | dense multi | 128 | **carried over** — a different model, unchanged vectors |
| `sparse` | sparse | — | **carried over** — SPLADE vectors are text-derived, unchanged |

⚠️ **RE-CORRECTED 2026-10-24 (session 17) — the session-16 correction above was WRONG, and so was the
original table's reasoning. `v2` DOES carry a `sparse` lane.** Full evidence and consequences:
`IMPROVEMENTS.md` **§I76**. The short version, measured against the live store:

* resolved `cfg.splade_enabled` is **`True`** (`.env:159` overrides `config.py:178`'s default `False`);
* `v2`'s config declares the sparse lane in **`params.sparse_vectors`** (`{"sparse": {}}`), a
  **separate key** from `params.vectors` — which is the whole error: the session-16 check read
  `params.vectors` alone and saw three lanes;
* **3,796 of 3,869 points** carry real SPLADE vectors, and **3,796** carry `colbert`;
* the **73** that carry neither are **`raptor_level: 1` summary nodes** (dense lanes only).

**⇒ The §2 acceptance shape is FOUR lanes**, and the per-point assertion must be **scoped by point
kind** — "every enabled lane on every point" is **already false on v2 itself** (the 73 RAPTOR nodes).
Scope it (§I26); do not delete it, and do not assert it naively.

⚠️ **Carrying the sparse lane over is cheap and is the recommendation:** SPLADE is text-derived and
independent of the dense embedder, and Shape B preserves `chunk_id` — so `sparse` (and `colbert`) can
be copied by id from v2 rather than recomputed. ⚠️ **But it must be in the plan**: a three-lane v3
would be a **regression on a lane the product path reads** (`store.py:460`), and it would confound
Stage F's v3-vs-v2 A/B with a lane-presence difference on the very path being measured.

⚠️ **The surviving half of the original warning still stands and is the important half:** every
**enabled** lane must be present on **every** point. A dense-only rebuild leaves `colbert` empty and
*looks* recovered — this is precisely why `scripts/reembed_chunks.py` refuses today (§I13), and the
reason Stage E's per-point assertion exists rather than a point count.

---

## §3 — THE STAGES, EACH WITH A VERIFIER

Standing rules for every stage below: the verifier **differs in model family from the author AND from
the subject** (`openai/gpt-oss-20b` is independent of both the author's family and Google's gemma);
the run script **prints and asserts the RESOLVED config** (§I23) including the resolved store
(§I49 Finding 1 — a blank host silently targets the *local* embedded store); and **a guard that has
never been seen to fail is not a guard**.

### Stage A — the code change: `dense_low`, and `dense_dim_low = 128`

* **Do:** replace the hardcoded `"dense_64"` at `store.py:451` with a name resolved the same way
  `_dense_name_from()` resolves the full-dim lane (a `_LOW_VECTOR_NAMES`/`_low_name_from()` pair, so
  the code reads the name off the collection instead of asserting it); repoint the schema check at
  `store.py:432`; set `dense_dim_low = 128`; sweep **every** other literal `"dense_64"` in the repo
  (grep, including probes, eval scripts and `preflight.py`) — §I28's sweep, because a consumer that
  was not repointed keeps reading the old name and silently returns nothing.
* **Verifier A:** unit tests that (i) a collection carrying `dense_low` is detected and queried by
  that name, (ii) a collection carrying only `dense_64` is still **readable** (backward compatibility
  for v2, which stays live for the A/B), (iii) the slice width equals the resolved lane's width —
  a mismatch must **raise**, not silently truncate. ⚠️ **Each test proven to discriminate by
  mutation**: revert the name to the literal and watch (i) fail; restore the old semantics and watch
  (ii) fail.
* **Gate:** no Stage B/C work starts until A is green and its verifier has run.

### ⚠️ Stage A2 — the gemma EMBEDDER config (a gap in this plan, found 2026-10-25 by running Stage B)

**No stage in this plan assigns `dense_model` / `dense_dim`.** Stage A lists only `dense_dim_low = 128`,
and §2 declares `dense_full` at **768** — but `src/core/config.py:72-73` still reads
`dense_model = "Qwen/Qwen3-Embedding-0.6B"`, `dense_dim = 1024`. The plan's own Stage D knows the dim
must move (*"both candidates are 768 against today's 1024"*) and never says who moves it.

**Measured, not inferred:** running Stage B with the current config created `knowledge_base_v3` with
**`dense_full` at 1024d** — a vector dimension is **immutable**, so that collection can never hold
gemma's 768d vectors. It was empty, so it was **dropped** and the prior state restored (v2 untouched
at 3,869 points). ⚠️ **Stage B's own gate is what caught this** ("a lane whose size is wrong fails
here, in seconds, rather than after the embedding") — it earned its place before Stage C ran.

**⇒ Stage A2 is: `dense_model = "google/embeddinggemma-300m"` and `dense_dim = 768`.** It must land
**before** Stage B, because B creates the immutable schema.

⚠️ **And it is not a one-line flip — three things must move in ONE window:**

1. **`cfg.dense_dim` is 42 sites across 16 files** (`store.py`, `database.py`, `intent_router.py`,
   `cluster_embedder.py`, `embed_cache.py`, `graph_builder.py`, `late_chunk_embedder.py`,
   `raptor_tree.py`, and `scripts/{evaluate_rag,funnel_boundary_recall,index_derivative_artifacts,preflight,reset_derived_collections,train_intent_classifier,validate_embedders}.py`).
   `embed_cache._FINGERPRINT_FIELDS` carries it, so the resume cache invalidates.
2. **The derived collections are declared at `dense_dim`** (`concept_embeddings`,
   `derivative_artifacts` — §I12 moved them onto the dense lane). Flipping to 768 makes
   `GraphBuilder._assert_collection_dim` **refuse** against the existing 1024d collections — by
   design (§I47). They must be reset/re-indexed as part of the same window, which Stage C already
   lists but Stage A2 must not run ahead of.
3. ⚠️ **The interim hazard: while the config says 768 and v2 is still the live collection, the
   default product path produces 768d query vectors and `_dense_name_from` resolves v2's
   `dense_1024` lane — a 768-vector against a 1024 slot, which Qdrant rejects.** v2 stays
   *queryable* only by a caller that supplies the matching embedder per arm (which is what Stage F's
   harness does explicitly). So the flip, the derived-collection reset and the re-embed belong to
   **one co-ordinated window**, not to a lazy afternoon.

**Verifier A2:** the resolved config prints `dense_model`/`dense_dim`; the cluster serves the model;
`scripts/validate_embedders.py` passes; and **Stage B then produces `dense_full` at 768d** — read
back from the LIVE collection, not from the code that created it.

### Stage B — create `knowledge_base_v3` with the §2 schema

* **Do:** drop-and-create (a vector dimension is **immutable** — the store cannot resize in place,
  §I33), declaring all four lanes up front.
* **Verifier B:** read the **live** collection's config back and assert every lane's kind and size
  against §2 — ⚠️ **read the LIVE collection, not the code that creates it** (§I33: the code half and
  the data half are separate deliverables). Assert `points_count == 0` before the write.
* **Gate:** a lane whose size is wrong fails here, in seconds, rather than after the embedding.

### Stage C — the re-embed (⚠️ the Shape B / Shape A decision — decision point 4)

**Recommendation: Shape B — re-embed the EXISTING chunks, preserving chunk ids.** The payloads carry
`text`, `parent_text`, `char_start`, `char_end`, `chunk_id`, `document_id`, `page_number`, so
**late chunking can be reproduced without re-parsing the PDF** (`late_chunk_embedder._pool` mean-pools
the parent's token vectors over `[char_start, char_end)` — all three inputs are stored).

| | Shape A — full re-ingest | Shape B — re-embed existing chunks |
|---|---|---|
| re-parses / re-chunks | **yes** → **new chunk ids** | no → **ids preserved** |
| cards (75,645) | must be regenerated — **8.9 h** | **stay valid** (keyed on `chunk_id`) |
| graph (1 h 6 m) | must be rebuilt | **stays valid** (chunk nodes keyed by id) |
| RAPTOR (73 nodes) | regenerated | re-embedded only |
| the re-embed itself | 58.6 min (incl. parse + chunk) | ⚠️ **the late-chunk pass — MEASURE IT FIRST** |

⚠️ **Shape B cannot test the chunking** — it keeps the boundaries. If the chunking is to move at the
same time (§I63's residual, arms 2–4), that **forces Shape A**. This is the one thing that would
invalidate the choice.

* **Do (Shape B):** extend `reembed_chunks.py` (it is the right shape and refuses today, §I13) to
  recompute **every** lane for each point, keeping `qdrant_point_id`, with the late-chunk path wired
  in; write into `knowledge_base_v3`. ⚠️ **Checkpoint it** (§I23/§I25's lessons: hundreds of
  sequential remote calls, keyed on content not on a per-run uuid) and **log one line per call plus a
  rolling rate**, so a stalled run is distinguishable from a slow one.
* ⚠️ **DELIVERABLE, and it does not exist yet: write `scripts/verify_collection_lanes.py`.** The name
  comes from the ingestion skill's supporting files, which were **lost** this session — ⚠️ **there is
  no such script in the repo**, so Stage C's verifier (ii) below has nothing to call. Write it as part
  of Stage C: scroll every point with vectors, assert **every enabled lane is present on every
  point**, report per-lane coverage, and **exit non-zero on a gap** so it can gate the rebuild. Its
  contract is one sentence, which is why it is cheap; the repo gaining its own copy also closes part
  of the skill gap.
* **⚠️ Stage C0 — measure before committing (do this FIRST, it is cheap):** run the late-chunk pass
  on **~20 real PARENTS** against the cluster and time it.
  ⚠️ **CORRECTED 2026-10-24 (session 16): the unit is PARENTS, not chunks.** The late-chunk path
  issues **one cluster call per parent** returning **per-token** vectors, and mean-pools the tokens
  inside each child's span (`late_chunk_embedder.py:26-29`, "one call per parent … that is why the
  pipeline embeds **parents**, never children"). Sampling *chunks* would understate the pass by
  roughly the fan-out (341 parents → 3,796 children, ~11 children/parent) and would mis-gate the
  whole Shape B decision.
  **The measured basis to extrapolate from:** the document has **341 parents** (measured this session
  — `rechunk_from_payload_probe.json`), and the ingest's own costing for this path is **~48 min and
  ~13.6 GB of JSON for the whole book** (`late_chunk_embedder.py:26-29`, extrapolated from
  `test_book.pdf`, 19 pages). The pooled gemma embed of 3,489 chunks, by contrast, is measured at
  **60.5–73.5 s** (§I70/§I72/§I74) — so the two are **not** the same cost class, and the Shape B
  estimate is derived, not measured, and must not be quoted as one.
  ⚠️ **Also budget the memory, not just the wall time**: per-token output is ~160× the pooled payload,
  so this is a streaming job, not an in-memory one.
  **Gate:** if the extrapolated pass exceeds the owner's budget, stop and re-decide (Shape A is *not*
  cheaper; the honest alternative is to ship the non-late-chunked variant as a pre-registered arm).
  ⚠️ **BLOCKED 2026-10-25 — and it blocks Stage C, not just C0.** `google/embeddinggemma-300m` is a
  **GATED HuggingFace repo**, and the late-chunk path needs its **tokenizer locally**
  (`LateChunkEmbedder._get_tokenizer` → `AutoTokenizer.from_pretrained(cfg.dense_model)`), because
  the cluster returns per-token *vectors* but the **character offsets** that define each child's span
  come from a local tokenization. The cluster serves the model fine (measured: 768d embeddings), but
  the tokenizer download returns **401 gated repo**. ⚠️ **No HF credential is configured on this
  machine** (no `HF_TOKEN`, no `HUGGING_FACE_HUB_TOKEN`, no stored token file). The previous ingest
  never hit this because **Qwen3 is not gated**. ⇒ **Shape B's cost cannot be measured, and Stage C
  cannot run, until the gemma tokenizer is available locally** — an owner action (authenticate HF and
  accept the Gemma licence), not a code fix. Probe + artifact:
  `logs/p1/step10/c0_late_chunk_timing.py` → `c0_late_chunk_timing.json`
  (`status: BLOCKED_ON_TOKENIZER`, exit 3). ✅ The probe's corpus half DID verify: **341 parents,
  3,796 children, 11.13 children/parent**, reproducing the register exactly.
* **Verifier C:** (i) `chunk_id` set before == after (byte-identical sorted list) — **this is the
  assertion the whole shape rests on**; (ii) every enabled lane present on **every** point, via the
  `scripts/verify_collection_lanes.py` written in this stage (⚠️ not a point count — §I33: a
  count-based gate holds a dead lane green until someone issues a real query); (iii) **A-vs-A**: one chunk embedded
  twice at different batch sizes is bit-identical; (iv) a **known-vector spot check** — one chunk's
  late-chunked vector reproduces the *v2* value when computed with the *old* model, which proves the
  late-chunk path is the shipped one and not a re-implementation.
  ⚠️ (iv) is the strongest of the four and is the one to insist on.

### Stage D — retrain the intent classifier

* **Do:** retrain. ⚠️ **Not optional and not cosmetic:** `intent_router.py:156` refuses a classifier
  whose `n_features_in_ != cfg.dense_dim`, and both candidates are 768 against today's 1024 — so the
  existing pickle is *rejected* on load. `scripts/train_intent_classifier.py` exists.
* **Verifier D:** the new classifier loads, its `n_features_in_ == 768`, and it **classifies a held-out
  split of the 133 gold queries at least as well as the 1024-dim one did** on the same split —
  ⚠️ reported as a *comparison*, and a regression is a finding to report, not a blocker to bury.

### Stage E — the preflight gate

* **Do:** run `scripts/preflight.py` against v3.
* **Verifier E:** exit 0, and **every lane asserted non-empty by a real query**, not by a count
  (§I33: a point-count gate holds a dead lane green). ⚠️ Expect the documented mid-migration trap
  (§I26): a preflight check comparing a derived index against `cfg.qdrant_collection` is unpassable
  while the derived collections still point at v2 — **scope it, do not edit the gate to get past it**.

### Stage F — ONE pre-registered product-endpoint run

* **Do:** gemma (`knowledge_base_v3`) vs qwen3 (`knowledge_base_v2`), 133 queries, paired, on the
  **product retrieval path**, **HyDE ON and frozen via the new cache** (`src/pdf_ingestion/hyde_cache.py`,
  `data/hyde_cache/…`, 127 entries ✅ built). Endpoint: **paired ceiling-normalised R@20** (§I58) —
  ⚠️ and state **which page convention** (§I72's correction: the product's is pages of the top-k
  chunks, `evaluate_rag.py:333-341`). Retrieval-only first; the full run with synthesis + judge only
  if the retrieval endpoint resolves.
* **Pre-registration:** written and committed **alone, before the run** (§I61's precedent).
* **⚠️ Prerequisite for a *clean* run (decision point 5):** §I68 — Qdrant's server-side RRF is
  **nondeterministic**, so this A/B depends on a tolerance unless the funnel moves onto
  `store._rrf_merge` (the client-side RRF already in-repo). That fix is small and also removes the
  instrument nondeterminism that voided §I67's first run. **Recommendation: land it before Stage F**;
  if it is deferred, the pre-registration must state the tolerance and the A-vs-A control must
  quantify it.
* **Verifier F:** the §I67 guard set — A-vs-A on one arm (bit-exact), the resolved-store assertion,
  per-point lane presence, **and at least one exact reproduction of a registered row** (the v2 arm
  must reproduce a §I64/§I57 number, or the harness is not the product path).

### Stage G — the §I66 stage decomposition, alongside F

* **Do:** base recall → the funnel/fusion → the cross-encoder → the generator, on v3 vs v2. This is
  the **diagnostic** half and it is cheap (the §I66 probe, not a full eval). It answers the question
  the writeup needs: **did the better embedder fix the full-dimension ranking lane, or just move the
  loss around?** ⚠️ §I72 already predicts the answer for the cross-encoder stage — it lifts a weak
  embedder far more than a strong one — so expect **compression**, and design the writeup to survive
  a null.
* **Verifier G:** the probe reproduces §I66's v2 decomposition on v2 (a known-answer check before it
  is trusted on v3).

---

## §4 — COST, AND THE GO/NO-GO GATES

| stage | cost | measured? |
|---|---|---|
| A — code change + tests | ~1 session | n/a |
| B — create v3 | seconds | n/a |
| **C0 — time the late-chunk pass on ~20 chunks** | **minutes** | **MEASURE — do not estimate** |
| C — the re-embed (Shape B) | ⚠️ **unknown until C0** | derived only |
| C — *if Shape A is forced* | **58.6 min ingest + 8.9 h cards + 1 h 6 m graph** | measured (§I70's costing) |
| D — intent classifier | ~1 session | n/a |
| E — preflight | seconds | n/a |
| F — product run, retrieval-only | minutes | measured shape (§I65/§I67) |
| F — product run, full (synthesis + judge) | **~70 min, 5,434 judge calls** | measured (§I64) |

**Gates:** C0's measurement before C; §I68 before F (or a stated tolerance); and **F is the only
stage whose result can license a ship** — everything before it is preparation.

---

## §5 — AFTER THE RE-EMBED: THE NEXT SESSION'S QUEUE

In order, and each one is a *decision point*, not a checklist:

1. **Read Stage F's result before anything else.** If gemma does **not** beat qwen3 at the product
   endpoint, the re-embed was paid for and the lever moves — to §I66's binding constraint (the
   100-slot fusion) or to the domain fine-tune (§4 of the embedder plan; the training set already
   exists: **29,321 `question` cards** paired with their source chunks).
2. **The chunking question, arms 2–4** (still open — §I63's residual is now attributed to the
   chunking proper, §I71 having eliminated the content filter): `min_chunk_tokens` (32), then
   `semantic_threshold` (0.8), then late chunking (36 min/arm).
   ⚠️ **CORRECTED 2026-10-24 (session 16) — this line said "arms 2–3 need a re-chunk; if Shape B was
   taken, they now need Shape A anyway", and that is FALSE for the measurement.** Measured: the E1
   chunking is a **pure function of the stored payloads** — reconstruct the 341 parents from
   `parent_id`/`parent_text` and re-cut, and it reproduces the index **exactly** (3,796 children,
   boundary-for-boundary, ~3 s), so arms 2–3 need **no re-parse, no re-chunk of the corpus and no
   Shape A**. Arm 2 is pre-registered:
   `.hermes/plans/2026-10-24-p1-min-chunk-tokens-ab-preregistration.md`.
   ⚠️ **What IS true, and is the distinction that was lost: a chunking arm needs Shape A only to
   SHIP a chunking change** — new boundaries mean new chunk ids, which invalidate the cards (keyed on
   `chunk_id`) and the graph (chunk nodes keyed by id). **Measuring is cheap; shipping is not.** So
   arms 2–3 are **independent of the Shape A/B decision** and can run before, after, or beside the
   gemma re-embed — and their result is an *input* to whether a future full re-ingest happens at all.
3. **§I68 — the client-side-RRF fix**, if deferred from Stage F. It also makes §I67-class A/Bs clean.
4. **§I56's DA lane** — one-variable test (the owner's "keep as-is" stands; the lane enters the same
   fusion stage §I66 fingers).
5. **§G2's V5 build** (signed off, never built) and **§G5/§I2** (`hop_distance` is a constant 0).
6. **The domain fine-tune** — the remaining lever if the embedder swap underdelivers. Hours on GPU,
   validated on §I70's instrument, compared against **gemma**, not the incumbent.
7. **Housekeeping:** §I55's exclude-from-metrics follow-on, §I58's `gold-003` caveat, §I53 item 6,
   the §I39 filter at the next re-ingest, and **committing sessions 13–15** (~25 files, still
   uncommitted).

---

## §6 — EXPLICITLY OUT OF SCOPE

* **Sub-0.020 knobs** (§0 of the embedder plan): the resolution floor at n = 133 is ~0.020; record,
  do not chase.
* **Re-testing the widths** — §I67 closed them, including "more candidates pooled at the fusion lane".
* **An all-lanes-at-once matrix** (§I56's unattributability defect).
* ⚠️ ~~**The graph lane** — Memgraph is down (7687 refused) and `hop_distance` is a constant 0.~~
  **CORRECTED 2026-10-24 (session 16) — see `IMPROVEMENTS.md` §I75.** **Memgraph is UP** on
  `localhost:7687` (Docker `synapse_memgraph`, published on 7687) and the lane is **REACHABLE AND
  SERVING** (5/5 multihop queries returned 5 chunks each, ~5 s). The "DOWN" reading probed the
  **cluster** IPs; the code and `.env` point at **localhost**. ⚠️ **What remains in scope-exclusion
  is only the code half: `hop_distance` is a constant `0`** (a single-hop lookup,
  `graph_builder.py:544-570`) — so the graph lane is excluded here for the **`hop_distance` reason
  alone**, not for an infrastructure outage, and it is not to be cited as down again.
* **Renaming `dense_full`** — deferred, recorded as debt (§1, decision point 2).
* **nomic** — declined by the owner on cost; do not re-open without new data.

## §7 — SIGNOFF POINTS (owner) — ✅ ALL FIVE TAKEN 2026-10-25 (session 17)

1. The low-lane name → **`dense_128`**. ⚠️ **The owner overrode this plan's `dense_low`
   recommendation.** The plan rejected `dense_128` *because it encodes the dimension* — §I13's trap,
   the exact defect being fixed — so the decision carries a **known cost: the next embedder change
   repeats this rename.** Recorded as the owner's call; not to be re-litigated.
2. `dense_full` → **renamed NOW** (not deferred as debt).
3. → **new `knowledge_base_v3`**, v2 left untouched and queryable (the A/B baseline).
4. → **Shape B**, **provisional** — confirmed at S2's gate with C0's measured number in hand.
5. → **§I68's client-side-RRF fix lands BEFORE Stage F.**

**Also taken:** commit sessions 13–17's work in the repo's per-item style.

⚠️ **What Stage A added that this plan left implicit, and it is load-bearing — the low lane's WIDTH
is resolved off the COLLECTION, not from `cfg.dense_dim_low`.** With `dense_dim_low = 128`, slicing
the query vector to the config value sends **128d into v2's 64d lane**, which loses Stage F's
**baseline arm**. v2's low lane is 64d, v3's is 128d, and the A/B queries **both**, so
`store._resolve_low_lane(vectors_cfg, cfg)` resolves `(name, width)` from the collection: the READ
path slices *to* that width, and the WRITE path asserts the **produced vector's** width against the
lane (`_assert_lane_width`), raising with the lane, both widths and the remedy rather than letting a
bare Qdrant 400 be the only symptom (§I47). Asserting against the *vector* rather than against `cfg`
is what keeps a deployed 64d-lane collection writable.

⚠️ **And §2's four-lane shape is now MEASURED, not inferred — see `IMPROVEMENTS.md` §I76.** v3
declares **four** lanes and carries `sparse`/`colbert` over **by id**.

---

## §8 — VERIFIED AGAINST THE LIVE SYSTEM (2026-10-24, session 16)

A plan's literals are unverified until checked, so every path, line reference and count this plan
rests on was checked before hand-off. **Nothing here is a change of design** — three were wrong and
are corrected in place above; the rest hold and are recorded so the executing session does not
re-check them.

| literal | status |
|---|---|
| `store.py:451` hardcoded `using="dense_64"` | ✅ **exact** |
| `store.py:432` schema check on the literal `"dense_64"` | ✅ **exact** |
| `intent_router.py:156` refuses `n_features_in_ != cfg.dense_dim` | ✅ **exact** |
| `scripts/verify_collection_lanes.py` | ✅ **confirmed ABSENT** — Stage C must write it |
| `scripts/reembed_chunks.py`, `train_intent_classifier.py`, `preflight.py`, `reset_for_reingest.py` | ✅ all **PRESENT** |
| `evaluate_rag.py:333-341` — "pages of the top-k CHUNKS", page-deduped | ✅ **confirmed** (the dedup block is there) |
| HyDE cache "127 entries ✅ built" | ✅ **correct, and COMPLETE for Stage F** — see below |
| payload keys `text`/`parent_text`/`char_start`/`char_end`/`chunk_id`/`document_id`/`page_number` | ✅ all present on the live points |
| the **`sparse` lane** is "carried over" | ✅ **RIGHT after all** — `v2` **does** carry a sparse lane (3,796/3,869 points, `params.sparse_vectors`); the session-16 "correction" was itself wrong — **§I76** |
| Stage C0 samples "~20 chunks" | ❌ **WRONG unit** — parents; corrected in Stage C0 |
| §5's "arms 2–3 now need Shape A anyway" | ❌ **WRONG** — corrected in §5 |
| §6's "Memgraph is down" | ❌ **WRONG** — corrected in §6 (§I75) |

**⚠️ The §I28 sweep surface for `dense_low`, measured rather than estimated:** the literal
`"dense_64"` appears **33 times across 18 files** — `src/pdf_ingestion/store.py`,
`src/core/database.py`, `src/pdf_ingestion/embed_cache.py`, 6 test files, `scripts/reembed_chunks.py`,
`scripts/funnel_boundary_recall.py`, `scripts/why_colbert.py`, and 6 probes under `logs/p1/`. **Scope
Stage A against that list, not against "store.py and preflight".** ⚠️ Note `embed_cache.py` is the
sharp one: its `_FINGERPRINT_FIELDS` includes `dense_dim_low`, so **changing `dense_dim_low` to 128
invalidates the whole late-chunk resume cache** (`data/embed_cache/`, 874 fingerprint dirs) — expected
and correct (the vectors genuinely change), but it means Stage C cannot reuse the existing cache, and
that must be in the cost, not discovered mid-run.

**⚠️ The HyDE cache is complete, and the reading that says otherwise is a trap.** The file
(`data/hyde_cache/18ece9b9404688c8__openai_gpt-oss-20b__ab681b8e43855a46.json`) holds **127 entries**,
while the eval set is **133** — so a naive set-difference says **40 are missing**. They are **all
`multihop`**, and `evaluate_rag.py:190` applies HyDE only when
`query_type in ("factual", "overview")`. So the cache covers **exactly the 93 HyDE-eligible queries**
(53 factual + 40 overview) of the 133, plus 34 negatives. **Nothing is missing and nothing needs
generating.** ⚠️ **Do not "fix" this by extending the cache** — it would add 40 entries that are never
read, and if the query mix ever changes, the miss is supposed to be **loud** (§I73).
