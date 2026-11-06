# P1 — PLAN: adopt `nomic-ai/nomic-embed-text-v1.5` @768/**64**, re-ingest into `knowledge_base_v3`, then domain fine-tune

> **Written 2026-10-25 (session 17) for EXECUTION IN THE NEXT SESSION.** Nothing below is built
> except where marked ✅.
> **Read first, in this order and only this much:** `HANDOFF.md` (session 17) → this plan's **§0, §1,
> §8** → then only the § your stage needs. `IMPROVEMENTS.md` **§I77** (and its addendum) is the
> evidence that decided the embedder; §I76, §I70, §I72, §I74 are the rest of the chain.
> **`ARCHITECTURE.md` §8 (Invariants and traps) before the first change.**
>
> **This plan SUPERSEDES `.hermes/plans/2026-10-24-p1-gemma-adoption-and-reembed-plan.md`.** That
> plan is kept, not deleted: it holds the Stage A work that is **still in force**, the gemma
> evidence, and the reasoning this one reverses. ⚠️ Read §0 before assuming anything in it is dead.

---

## §0 — THE DECISION, AND EXACTLY WHAT IT REVERSES

**Owner decision, 2026-10-25: adopt `nomic-ai/nomic-embed-text-v1.5` at 768d full / 64d MRL**, and
re-ingest into a new `knowledge_base_v3`.

**⚠️ This is a COST decision taken on NEW MEASUREMENT — it is NOT a finding that nomic is better, and
it must never be restated as one.** The record, stated so both halves survive:

* **The measured gain still favours gemma.** §I74's product-stage contrast, `gemma − nomic` through
  the cross-encoder, is **+0.029248 [+0.004620, +0.053876]** — resolved, but **~1.19× the run's own
  resolution floor (0.024628)** with the CI's lower bound **below** it. The plan of 2026-10-24 recorded
  the choice as *"a cost decision that declined the winning arm"*, and that framing still holds.
* **What changed is the cost side, and it is measured.** §I77 found the gemma late-chunk path broken
  in two ways; its addendum then measured **both candidates on the same corpus and cluster**:

  | | gemma (window 2048) | **nomic (window 8192)** |
  |---|---|---|
  | parents over the endpoint window | 71 / 341 (20.8 %) | **0 / 341 (0.0 %)** |
  | children living in a truncated parent | 1,415 / 3,796 (37.3 %) | **0 (0.0 %)** |
  | children losing vectors outright | 351 (9.2 %) | **0** |
  | alignment delta (`n_api − n_local`) | +2 | +2 *(shared — not a differentiator)* |
  | tokenizer availability | **gated HF repo** (cost a detour) | **ungated** |

  So the window defect is **gemma-specific**, and the alignment defect is **shared machinery that
  must be built whichever arm is adopted**.

**What this reverses, precisely:**
1. the **embedder**: gemma → nomic (2026-10-24's adoption);
2. the **low-lane name**: `dense_128` → **`dense_64`**;
3. **`dense_dim_low`: 128 → 64.**

**⚠️ What it does NOT reverse, and this is the part worth keeping: Stage A's machinery stays and is
load-bearing.** `_LOW_VECTOR_NAMES = ("dense_128", "dense_64")` plus `_resolve_low_lane` — which reads
the lane's **name and width off the collection** — is what makes this embedder choice a **config
switch** rather than a code fork. The rename of the *full* lane to the width-free `dense_full` also
stays: it is correct for a 768 lane under either model, which is why the width moved 1024 → 768
without a second rename.

---

## §1 — WHAT NOMIC CHANGES, AND THE FOUR TRAPS IT INTRODUCES

**The setting deltas from the gemma plan:**

| setting | gemma plan | **nomic** |
|---|---|---|
| `dense_model` | `google/embeddinggemma-300m` | **`nomic-ai/nomic-embed-text-v1.5`** |
| `dense_dim` | 768 | **768** *(unchanged)* |
| `dense_dim_low` | 128 | **64** |
| low lane name | `dense_128` | **`dense_64`** |
| full lane name | `dense_full` | `dense_full` *(unchanged)* |
| `query_instruction` | Qwen3's instruct string | **`search_query: `** |
| document-side prefix | *(none — Qwen3 needs none)* | **`search_document: ` — NEW MECHANISM, see trap 1** |

**⚠️ TRAP 1 — the document-side prefix does not exist on the cluster path.** Measured 2026-10-25:
`NomicEmbedder` (the LOCAL embedder) prefixes **both** sides (`search_query: ` / `search_document: `),
but `ClusterDenseEmbedder` — which is what the re-ingest actually uses — applies `cfg.query_instruction`
on the query path and **nothing on the passage path** ("Documents carry no instruction"). §I62 measured
that the cluster is a **generic passthrough** and applies no prefix itself. ⇒ nomic would be used **out
of distribution** unless a document prefix is added. §I62 measured the size of getting this wrong:
unprefixed cosine **0.949** against **1.000000** prefixed.

**⚠️ TRAP 2 — the prefix collides with late chunking, and the failure is SILENT.** `LateChunkEmbedder`
computes character offsets by tokenizing the **raw** parent text (`_offsets(parent.text)`) and sends the
**same raw text** to the per-token endpoint. Add a prefix on one side only and **every child's span
shifts by the prefix's token count** — a mis-pooled vector with no warning at all (§I47's class). The
prefix must be applied to **both** the tokenization used for offsets **and** the endpoint input, with the
child's `[char_start, char_end)` span translated into the prefixed text's coordinates. **This is the
single most dangerous item in this plan.**

**⚠️ TRAP 3 — the alignment rule must be re-probed for nomic, not assumed.** Measured: nomic's endpoint
returns `n_api == n_local + 2` (3,879 vs 3,877 on the corpus's longest parent) — the same delta as gemma,
and `LateChunkEmbedder._content_tokens` **accepts only `n_local` or `n_local + 1`**, so **it will raise
on every parent exactly as it did under gemma**. ⚠️ The **delta** is measured; **which two tokens they
are** is not. The Qwen3 contract was probed before it was trusted; the nomic one must be too (§I77's
lesson). Note the interaction with TRAP 2: a prefix adds tokens to the input, so the content rule and the
offset rule have to be derived **together**.

**⚠️ TRAP 4 — the MRL truncation convention is now load-bearing (§I70 item 4).** `mrl_slice`
(`cluster_embedder.py`) and `NomicEmbedder._truncate` (`embedder.py`) both do a **plain slice +
re-normalise**, while **Nomic's own model card prescribes `F.layer_norm` over the full 768 dimensions
BEFORE the slice.** Different functions ⇒ **every Nomic-64 number in the register is under the project's
convention, not Nomic's.** Under gemma this was a side note; under nomic the 64d lane **is** the funnel's
fast first stage, so it must be decided and verified rather than inherited. ⚠️ Do **not** "fix" it without
re-measuring: §I59's rows were produced the project's way.

**Two pieces of context that make nomic less of a leap than it looks:**
* **The deployed `knowledge_base` is itself nomic-built** (`dense_768` + `dense_64`, `NomicEmbedder`,
  "MRL truncation: full 768d sliced to 64d then re-normalised"). So this is a **return** to an embedder
  already served in production, with the new chunking + late-chunk pipeline — not a new model class.
* **nomic was already the best-known arm on this corpus** before gemma (§I63: nomic@768 beat Qwen3 by
  **+0.1400**, reproduced exactly in §I70).

---

## §2 — THE ACCEPTANCE SHAPE OF `knowledge_base_v3`

| lane | kind | dim | source |
|---|---|---|---|
| `dense_full` | dense | **768** | nomic, **late-chunked** (parent context) |
| `dense_64` | dense | **64** | nomic MRL slice, re-normalised (⚠️ §1 trap 4) |
| `colbert` | dense multi | 128 | **carried over** — different model, unchanged vectors |
| `sparse` | sparse | — | **carried over** — SPLADE, text-derived |

**⚠️ `v3` ALREADY EXISTS AND IS WRONG FOR THIS PLAN — it must be DROPPED.** It was created on
2026-10-25 under the gemma plan with `dense_128` **128d** + `dense_full` **768d**. A vector dimension is
**immutable**, so the 64d low lane cannot be added in place. It is **empty** (0 points, verified), so the
drop is seconds and destroys nothing. ⚠️ **`knowledge_base_v2` is NOT touched** — it is the A/B baseline.

**Per-point coverage is scoped by point kind** (§I76): chunk points carry all four lanes; `raptor_level`
summary nodes carry the **dense lanes only**. Do not assert "every lane on every point" — that fails on a
known-good collection. `scripts/verify_collection_lanes.py` (✅ built, 11 tests, verified live) is the gate.

---

## §3 — THE STAGES, EACH WITH A VERIFIER

Standing rules for every stage: the verifier **differs in model family from the author AND the subject**;
the run script **prints and asserts the RESOLVED config** (§I49 Finding 1 — a blank `QDRANT_HOST`
silently targets the *local* embedded store); and **a guard that has never been seen to fail is not a
guard.**

### Stage A2 — the nomic embedder config (`.env`, gitignored)

* **Do:** set `DENSE_MODEL=nomic-ai/nomic-embed-text-v1.5`, `DENSE_DIM=768`, **`DENSE_DIM_LOW=64`**, and
  `QUERY_INSTRUCTION="search_query: "`. ⚠️ **The `.env` override route was chosen over a `config.py`
  default change** (owner decision, 2026-10-25) so Stage F can switch per arm in one process and the flip
  reverts without a code edit.
* ⚠️ **AND revert `src/core/config.py`'s `dense_dim_low` default 128 → 64**, with
  `tests/test_config_invariants.py::test_dense_lane_dim_defaults` following it. Stage A set 128 for
  **gemma's** MRL slot; nomic's is 64, so leaving the default at 128 would describe an embedder we did not
  adopt, and a fresh clone without `.env` would create a 128d lane for a 64d model. ⚠️ Safe on the *read*
  path either way — `_resolve_low_lane` takes the width **off the collection**, so a stale default cannot
  mis-slice an existing one; it only affects what a **new** collection is created at, which is exactly why
  it must be right.
* **Verifier A2:** the resolved config prints all four values; the cluster serves nomic at **768**
  (✅ measured 2026-10-25); the tokenizer loads **without credentials** (✅ measured — nomic is ungated);
  `scripts/validate_embedders.py` passes.

### Stage A2b — the prefix wiring and the alignment rule (⚠️ NEW; the plan's riskiest build)

* **Do:** (i) add a **document-side prefix** setting and wire it into `ClusterDenseEmbedder`'s passage
  paths — `embed_documents` **and** `embed_documents_tokens` (the per-token path late chunking uses);
  (ii) make `LateChunkEmbedder` apply the prefix to the **tokenization** as well as the endpoint input and
  translate each child's span into the prefixed text's coordinates (§1 trap 2); (iii) make
  `_content_tokens` **model-aware** rather than assuming the Qwen3 contract (§1 trap 3).
* **Verifier A2b — three guards, each able to fail:**
  1. **Alignment, probed not assumed:** for a real parent, assert the endpoint's vector count against the
     local tokenization of the **prefixed** input and record the rule (`n_api == n_local + k`). A wrong `k`
     must raise, not shift.
  2. **Span invariance (the trap-2 guard):** for one parent, the child→token-index mapping computed with
     the prefix must equal the mapping computed without it, **in the parent's own character
     coordinates.** This is the assertion that catches a silent shift, and it is the one to insist on.
  3. **Prefix actually sent:** the request body for a passage contains `search_document: ` and the query
     body contains `search_query: ` — asserted on the payload, not on the docstring.
* **Gate:** no Stage B/C work starts until A2b is green. ⚠️ **A2b changes the embedding, so nothing that
  depends on vectors may be built before it.**

### Stage B — drop and re-create `knowledge_base_v3` with the §2 schema

* **Do:** **drop** the existing gemma-shaped v3 (empty; §2), then create with `dense_64`(64) +
  `dense_full`(768) + `colbert`(128, max_sim) + `sparse`.
* **Verifier B:** read the **LIVE** collection back (not the code that creates it — §I33) and assert every
  lane's kind and size against §2, and `points_count == 0`. Run
  `scripts/verify_collection_lanes.py --collection knowledge_base_v3` for the per-lane report.
* **Gate:** a lane whose size is wrong fails here, in seconds, rather than after the embedding. ⚠️ This
  gate already earned its place: it caught the 1024d `dense_full` on 2026-10-25.

### Stage C0 — time the late-chunk pass BEFORE committing (cheap, and it is the go/no-go)

* **Do:** run `logs/p1/step10/c0_late_chunk_timing.py --parents 20`. ⚠️ **The unit is PARENTS, not
  chunks** — one cluster call per parent returning per-token vectors; sampling chunks understates the pass
  by the fan-out (341 parents → 3,796 children, ~11 each).
* **Verifier C0:** its four guards pass (`C0-G1` all sampled parents succeed, `C0-G2` alignment held,
  `C0-G3` vectors are the configured width, `C0-G4` every child got a late-chunked vector), and the
  **measured** seconds/parent is recorded with the extrapolation to 341 parents.
* **⚠️ Expected to PASS now and FAILED under gemma:** under gemma this probe returned **20/20 failures**
  (§I77). Under nomic the window is clean (**0/341 parents over it**), so the pass should complete. **A
  failure here is a RESULT, not a setback** — record it and stop.
* **Gate:** the measured number replaces the derived **~48 min** in the cost table. If it exceeds the
  budget, stop and re-decide (⚠️ Shape A is *not* cheaper).

### Stage C — the re-embed (Shape B: re-embed the EXISTING chunks, preserving `chunk_id`)

* **Do:** extend `scripts/reembed_chunks.py` (it is the right shape and refuses today, §I13) to recompute
  **every** lane per point, keeping `qdrant_point_id`, with the late-chunk path wired in; write into
  `knowledge_base_v3`. ⚠️ **Checkpoint it** and **log one line per call plus a rolling rate**, so a stalled
  run is distinguishable from a slow one (§I23/§I25).
* **Why Shape B:** the payloads carry `text`/`parent_text`/`char_start`/`char_end`/`chunk_id`/
  `document_id`/`page_number`, so late chunking is reproducible **without re-parsing**, and the **cards
  (8.9 h) + the graph (1 h 6 m) stay valid** because they are keyed on `chunk_id`.
* ⚠️ **`data/embed_cache/` (874 dirs) CANNOT be reused** — `dense_dim_low` and the model are in
  `embed_cache._FINGERPRINT_FIELDS`, so the rename invalidates every entry. Correct (the vectors change),
  but it must be in the cost, not discovered mid-run.
* **Verifier C:** (i) the `chunk_id` set before == after (**byte-identical sorted list** — the assertion
  the whole shape rests on); (ii) every enabled lane present on every required point, via
  `verify_collection_lanes.py` (⚠️ not a point count — §I33); (iii) **A-vs-A**: one chunk embedded twice at
  different batch sizes is bit-identical; (iv) a **known-vector spot check** — one chunk's late-chunked
  vector reproduces the *v2* value when computed with the *old* model, which proves the late-chunk path is
  the shipped one and not a re-implementation. ⚠️ (iv) is the strongest and is the one to insist on.

### Stage D — retrain the intent classifier

* **Do:** retrain. ⚠️ **Not optional:** `intent_router.py:156` refuses a classifier whose
  `n_features_in_ != cfg.dense_dim`, and the existing pickle is 1024-trained against a 768 embedder — it is
  **rejected on load**.
* **Verifier D:** the new classifier loads, `n_features_in_ == 768`, and it classifies a held-out split of
  the 133 gold queries **at least as well as** the 1024-dim one did — reported as a *comparison*, and a
  regression is a finding to report, not a blocker to bury.

### Stage E — the preflight gate

* **Do:** `scripts/preflight.py` against v3, plus `verify_collection_lanes.py`.
* **Verifier E:** exit 0, and **every lane asserted non-empty by a real query**, not by a count. ⚠️ Expect
  the documented mid-migration trap (§I26): a preflight check comparing a derived index against
  `cfg.qdrant_collection` is unpassable while the derived collections still point at v2 — **scope it, do
  not edit the gate to get past it.**

### Stage F — ONE pre-registered product-endpoint run

* **Do:** **nomic (`knowledge_base_v3`) vs qwen3 (`knowledge_base_v2`)**, 133 queries, paired, on the
  **product retrieval path**, **HyDE ON and frozen** via `data/hyde_cache/` (✅ built, 127 entries = exactly
  the 93 HyDE-eligible queries — nothing to generate, do not extend it). Endpoint: **paired
  ceiling-normalised R@20** (§I58) — ⚠️ and state **which page convention** (the product's is pages of the
  top-k **chunks**, `evaluate_rag.py:333-341`; §I72's correction). Retrieval-only first; the full run with
  synthesis + judge (~70 min, 5,434 judge calls) only if the retrieval endpoint resolves.
* **Pre-registration:** written and **committed ALONE, before the run** (§I61's precedent).
* ⚠️ **Prerequisite for a CLEAN run — decision 5:** §I68, Qdrant's server-side RRF is **nondeterministic**,
  so this A/B depends on a tolerance unless the funnel moves onto `store._rrf_merge` (the client-side RRF
  already in-repo). **Owner decision 2026-10-25: land it before F.** ⚠️ Its blast radius is measured: one
  source file, **two test files that break by construction**, and one harness
  (`scripts/funnel_boundary_recall.py`, which shares the defect).
* **Verifier F:** the §I67 guard set — A-vs-A on one arm (bit-exact), the resolved-store assertion,
  per-point lane presence, and **at least one exact reproduction of a registered row** (the v2 arm must
  reproduce a §I64/§I57 number, or the harness is not the product path).

### Stage G — the §I66 stage decomposition, alongside F

* **Do:** base recall → the funnel/fusion → the cross-encoder → the generator, on v3 vs v2. This is the
  diagnostic half and it is cheap. It answers what the writeup needs: **did the embedder fix the
  full-dimension ranking lane, or just move the loss around?**
* **Verifier G:** the probe **reproduces §I66's v2 decomposition on v2** (a known-answer check) before it
  is trusted on v3.

---

## §4 — THE FINE-TUNE (stage 3, after the re-ingest lands and F has reported)

**The owner's point, and it is measured:** generic embedders lose here (§I63: Qwen3 losing to Nomic by
+0.1400 on this corpus). Domain fit is the lever, and contrastive fine-tuning is the standard recipe.

* **Base model: off-the-shelf nomic** — ⚠️ **the adopted embedder, NOT gemma.** The old plan said "the §1
  winner"; the winner *was* gemma, and gemma was declined. Comparing a fine-tune against a model we did not
  adopt would answer the wrong question.
* **The training set already exists — this is the blocker that normally kills a fine-tune.** **75,645
  cards** on disk, of which **29,321 are `question` cards**, each paired with its source chunk → ~29k
  synthetic (query, passage) pairs in physics. `factoid` (30,635) and `definition` add more.
* **Method:** `MultipleNegativesRankingLoss`-style contrastive training on (query, positive chunk) pairs,
  in-batch negatives. **`MatryoshkaLoss`** so the **64d lane survives** — under nomic that lane is the
  funnel's first stage, so a fine-tune that breaks it breaks the product.
* ⚠️ **The prefix convention must be used in training too** (`search_query: ` / `search_document: `), or
  the fine-tuned model is trained on a different input distribution than the index serves (§1 trap 1).
* **Validate on the SAME instrument as §I70** (§I63's exact-cosine oracle, 133 gold queries) — otherwise a
  fine-tuned model cannot be compared against off-the-shelf ones.
* ⚠️ **Expect leakage and say so up front:** the card questions are **generated from the passages**, so
  train/val separation must be by **document/passage, not by card**, or the number is inflated.
* **Compare against off-the-shelf nomic**, not against the incumbent — and report the comparison as the
  endpoint, including a null.
* GPU job: hours, not minutes.

---

## §5 — COST, AND THE GO/NO-GO GATES

| stage | cost | measured? |
|---|---|---|
| A2 — the nomic config | minutes | n/a |
| **A2b — the prefix wiring + alignment rule** | **~1 session (a BUILD)** | n/a |
| B — drop + re-create v3 | seconds | n/a |
| **C0 — time the late-chunk pass on ~20 parents** | **minutes** | **MEASURE — do not estimate** |
| C — the re-embed (Shape B) | ⚠️ **unknown until C0** (derived ~48 min pre-C0) | derived only |
| C — *if Shape A is forced* | 58.6 min ingest + **8.9 h cards** + 1 h 6 m graph | measured |
| D — intent classifier | ~1 session | n/a |
| E — preflight | seconds | n/a |
| F — product run, retrieval-only | minutes | measured shape (§I65/§I67) |
| F — product run, full (synthesis + judge) | **~70 min, 5,434 judge calls** | measured (§I64) |
| **§4 — the fine-tune** | **GPU hours** | not costed |

**Gates:** A2b green before anything is embedded; **C0's measurement before C**; §I68 before F; and **F is
the only stage whose result can license a ship** — everything before it is preparation.

---

## §6 — EXPLICITLY OUT OF SCOPE

* **Sub-0.020 knobs** — the resolution floor at n = 133 is ~0.020; record, do not chase.
* **Re-testing the widths** — §I67 closed them, including "more candidates pooled at the fusion lane".
* **An all-lanes-at-once matrix** (§I56's unattributability defect).
* **The graph lane** — ✅ reachable and serving (§I75), but ⚠️ `hop_distance` is a constant `0` (a **code**
  defect, §G5/§I2), so "multihop" is nominal. Not to be cited as down again.
* **gemma** — declined on measured cost (§0). ⚠️ **Do not re-open without new data, and do not restate the
  decline as "gemma was worse" — the measured gain still favours it.**

---

## §7 — SIGNOFF POINTS (owner)

1. **nomic over gemma** — ✅ **TAKEN 2026-10-25** (§0), on §I77's measured window exposure.
2. **`dense_dim_low` = 64 and the lane named `dense_64`** — ✅ **TAKEN** (nomic's MRL slot).
3. **Shape B** (re-embed, ids preserved, cards + graph reused) vs Shape A — ⚠️ **PROVISIONAL**, confirmed
   at C0 with the measured number in hand.
4. **The MRL truncation convention** (§1 trap 4): keep the project's plain slice + re-normalise, or move to
   Nomic's `layer_norm`-then-slice? ⚠️ **OPEN — and it changes every 64d number.** Moving it means
   re-measuring §I59's rows.
5. **§I68 before F** — ✅ **TAKEN**.
6. **The fine-tune's validation split** (by document/passage, not by card) — ✅ **TAKEN 2026-10-25
   (session 20): PASSAGE-LEVEL** — hold out passages, and **all cards generated from them**, so no
   held-out card's source passage is in training. ⚠️ **Document-level was offered and rejected as
   degenerate** (there is ONE textbook, so it is all-or-nothing and leaves a tiny val set);
   **card-level was rejected as leaky** (the plan's own §4 warning). It decides whether the §4 number
   means anything. ⚠️ **Taken with §I86 in hand:** the fine-tune's ceiling is now measured low (the
   resolved loss is at the fused pool, and the cross-encoder absorbs it), so S6 is a low-ceiling bet
   whose value is the **null** as much as the gain.

---

## §8 — VERIFIED AGAINST THE LIVE SYSTEM (2026-10-25, session 17)

A plan's literals are unverified until checked. Every path, line reference and number this plan rests on
was measured today; nothing here is inferred from the superseded plan.

| literal | status |
|---|---|
| nomic's full dim | ✅ **768, measured live** (`nomic-ai/nomic-embed-text-v1.5` → 768d from the cluster) |
| nomic's endpoint window | ✅ **8192 declared, and honoured** — 3,879 vectors returned for a 3,877-token input, **no truncation** |
| nomic's max parent tokens on this corpus | ✅ **4,712** (mean 1,387) → **0/341 parents over the window** |
| nomic's alignment delta | ✅ **+2** (3,879 vs 3,877) — ⚠️ *which* two tokens is **NOT** established; probe it (A2b) |
| nomic's tokenizer | ✅ **loads WITHOUT credentials** (ungated; `model_max_length` **8192**) — measured 2026-10-25. ⚠️ Its **class** was not printed, and is not needed: A2b probes the alignment against the endpoint, which is what actually matters |
| `NomicEmbedder` prefixes both sides | ✅ `embedder.py:161,180,186` — `search_document: ` / `search_query: ` |
| `ClusterDenseEmbedder` prefixes the query ONLY | ✅ `cluster_embedder.py:169,300` — documents carry no instruction ⇒ **trap 1 is real** |
| `query_instruction` is currently Qwen3's | ✅ `config.py:97-99` |
| `mrl_slice` / `_truncate` = plain slice + renorm | ✅ `cluster_embedder.py:78-86`, `embedder.py:192-196` ⇒ **trap 4 is real** |
| `_content_tokens` accepts only `n_local` / `n_local+1` | ✅ `late_chunk_embedder.py:117-143` ⇒ **trap 3 will raise** |
| `v3` currently holds the gemma shape | ✅ created 2026-10-25 with `dense_128` 128d + `dense_full` 768d, **0 points** ⇒ **drop it** (§2) |
| `knowledge_base_v2` | ✅ 3,869 points, 4 lanes, **untouched** |
| `verify_collection_lanes.py` | ✅ **BUILT** (it was absent), 11 tests, 5/5 mutations, verified live against v2 |
| `intent_router.py:156` refuses `n_features_in_ != cfg.dense_dim` | ✅ exact |
| `reembed_chunks.py`, `train_intent_classifier.py`, `preflight.py`, `reset_for_reingest.py` | ✅ all present |
| the HyDE cache | ✅ 127 entries = exactly the 93 HyDE-eligible queries; **complete, do not extend** |
| `evaluate_rag.py:333-341` — pages of the top-k **chunks** | ✅ confirmed |
| payload keys `text`/`parent_text`/`char_start`/`char_end`/`chunk_id`/`document_id`/`page_number` | ✅ present on the live points |
| the `sparse` lane exists on v2 | ✅ **3,796/3,869 points** (§I76) — the four-lane shape is measured, not inferred |
