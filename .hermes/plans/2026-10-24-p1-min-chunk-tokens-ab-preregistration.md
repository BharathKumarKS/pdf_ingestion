# P1 — PRE-REGISTRATION: does the inherited `min_chunk_tokens=32` merge change base-lane page ranking?

> **Written 2026-10-24 (session 16) at the owner's direction, and to be COMMITTED ALONE, BEFORE THE
> RUN.** That commit is what makes it a pre-registration (§I61's, and arm 1's, precedent — arm 1's
> was `aa4b55b`). The harness, the run and the verifier belong to a later step. **If any number in
> this file is edited after the run starts, the run is VOID.**
>
> Read first: `IMPROVEMENTS.md` §E1 (the merge and the knob), §I63 (the 0.0648 residual this arm is
> trying to move), §I71 (arm 1 — the content filter — and its NULL, plus the plan-premise-error
> class), §I58 (the ceiling rule), §I70 (the embedder screen and its instrument), §I19/§I19a (the
> embed cache), and `HANDOFF.md` session 15 §5.

---

## §0 — WHY THIS ARM, AND WHY IT IS SECOND

Arm 1 (`min_chunk_tokens`'s sibling knob, the §I39 content filter) is **measured and null** (§I71):
it moved base-lane page ranking by −0.006330 with a CI straddling 0, and its treatment turned out to
be **19 chunks, not 263**, because the content window already excluded 93 % of what the filter
rejects. So §I63's **+0.064792 unattributed residual** — the gap between the old corpus and the new
one that the embedder swap did *not* explain — is still unattributed, and the filter is not it.

What remains in that residual is **the chunking itself**. This arm takes the one chunking knob that
has **never been re-tuned**: `min_chunk_tokens = 32` (`src/core/config.py:131`), inherited from the
**removed size-based `chonkie.SentenceChunker`** and carried into the semantic chunker unchanged.
§E1 measured it merging **27 %** of the new, smaller children on a 42-parent fixture. It is the
cheapest remaining chunking variable: it changes **how a parent's text is cut into children** and
nothing else — not the parse, not the parents, not the parent→page provenance.

## §1 — THE MEASURED FACTS THIS ARM RESTS ON

> **Provenance.** Unlike arm 1's §1 (which was a throwaway probe with **no** preserved artifact),
> every fact below was measured in this session by a probe that **wrote its artifact**:
> `logs/p1/step10/rechunk_from_payload_probe.py` →
> `logs/p1/step10/rechunk_from_payload_probe.json` (**sha256 `1c47e3bcbb203295…`**). It is
> **read-only** (no writes to any collection, no LLM calls, no re-embed). Still **not** independently
> verified — the verifier dispatch must re-run these reads.
> ⚠️ **A-vs-A, already on the record:** the probe was run **twice** in this session (two separate
> launches, same code, same store) and both runs agree on **every printed number and on the artifact's
> sha256** (`1c47e3bcbb203295…` — byte-identical, so the artifact was rewritten with identical bytes).
> That is a negative control on the *probe*, and it is **mechanical** evidence — it is not an
> independent opinion, and it does not verify the claims (the verifier still must).

**F1. The E1 chunking is EXACTLY reproducible from the stored payloads — arm 2 needs NO re-parse.**
Every chunk payload carries `parent_id` and `parent_text`. Reconstructing the parents from those and
re-running `SemanticChunker` at the shipped settings reproduces the index **exactly**:

| quantity | measured |
|---|---|
| parents reconstructed from payloads | **341** |
| parents whose `parent_text` disagrees within the group | **0** |
| children stored | **3,796** |
| children re-cut from the reconstructed parents | **3,796** |
| parents whose children match **boundary-for-boundary and text-for-text** | **341 / 341** |

So the whole of E1 is a **pure function of the stored payloads**, computable in **~3 s**. There is
no parse cache (§F3 of arm 1's pre-registration) and this arm does not need one.

**F2. The merge is BIGGER on the real corpus than §E1's fixture recorded.** Raw chonkie children
(no merge) = **5,715**; stored children = **3,796**. So the `min_chunk_tokens=32` merge removes
**1,919 children = 33.6 %**, where §E1's 42-parent fixture measured **27 %** (91 → 66). The knob is
**not** a marginal one on this corpus, and its true effect size was under-recorded.

**F3. The knobs, as shipped** (`src/core/config.py`): `semantic_threshold = 0.8` (:102),
`chunk_size = 512` (:129), `min_chunk_tokens = 32` (:131).

**F4. The store.** `knowledge_base_v2` holds **3,869 points** = **3,796 chunks** + **73 RAPTOR
summary nodes** (`source_type = raptor_summary`, which carry neither `parent_id` nor `is_content`).
Lanes: `dense_1024`, `dense_64`, `colbert` (128). **There is no `sparse` lane** — SPLADE is off for
this environment. Stored `is_content` over the 3,796 chunks: **True 3,791 / False 5** (§I71's stale
column, confirmed).

**F5. §I70's SCREEN RUNS ITS TWO ARMS UNDER TWO DIFFERENT EMBEDDING CONVENTIONS — and it SAYS SO.**
The stored `dense_1024` is **late-chunked** (`late_chunk_embedder.EnrichedChunk.late_chunked: bool =
True`, the E3 path the re-ingest used), while §I70's **gemma** arm is **plain pooled**
(`cluster_embed`, `/embed-text/v1/embeddings` with no `return_token_embeddings`). ⚠️ **This is NOT a
new defect and must not be reported as one**: the screen records it explicitly as a *known
asymmetry* — `embedder_screen.py:29` and the artifact's own
`"late_chunking_asymmetry": "qwen3@1024 ranks the STORED dense_1024 vectors …"` (`:668`). What is
new here is only that **this arm declines to inherit it**: all of arm 2's arms are freshly embedded
under **ONE** convention (§2), and guard M1 names that convention explicitly so a reproduction
cannot be read as "the stored lane".

**F6. The embed cache CANNOT help this arm, and that is a finding, not an obstacle.**
`embed_cache.CachedParent` stores, per parent, the **pooled child vectors** plus each child's
`text_sha`, `char_spans` and `token_spans`; `rebuild()` (`embed_cache.py:132-166`) returns `None`
unless the **live children's text and char spans** line up. A different `min_chunk_tokens` produces
different children ⇒ an **honest miss**. The 874 fingerprint directories under `data/embed_cache/`
therefore buy arm 2 nothing. (The cache's own docstring is explicit that this is the designed
behaviour: a miss costs one request; a wrong re-attachment would corrupt the index silently.)

**F7. ⚠️ A FIDELITY LIMIT, RECORDED RATHER THAN HIDDEN.** `ParentChunk.page_map` — the element-level
char→page provenance map — is **not** stored. The probe reconstructed it from the stored children's
`(char_start, page_number)` pairs, so it is only **as fine as the child starts**. That is sufficient
to reproduce the shipped chunking exactly (F1), but a **new** child whose `char_start` falls between
two stored child starts is assigned the page of the preceding stored child. The harness must
reconstruct the page map the same way and **report how many new children fall off a stored boundary**
— an unquantified page-attribution approximation would silently move the endpoint.

## §2 — THE DESIGN

**The pool filter is not the variable here; the cut is.** All arms share the parse, the parents, the
parent→page provenance, the queries, the metric code and the embedder. **The chunk boundaries are the
only variable.**

| arm | `min_chunk_tokens` | children (expected) | role |
|---|---|---|---|
| **C** (control) | 32 (shipped) | 3,796 | must reproduce the stored index exactly (F1) |
| **T0** | **0** (no merge — raw chonkie segmentation) | **5,715** | **PRIMARY** treatment; `T0 − C` is the endpoint |
| **T16** | 16 | not measured | pre-registered **sensitivity** arm, not the endpoint |

⚠️ At `min_chunk_tokens = 0` the guard `if token_count < self._cfg.min_chunk_tokens and out:`
(`chunker.py:131`) can never fire, so T0 is **exactly** the raw chonkie segmentation. Guard X1
asserts that.

**Embedding convention — ONE, for every arm.** Plain pooled document embeddings with the arm's
prefix, identical to §I70/§I71's `cluster_embed`:

* **PRIMARY: gemma@768** — `google/embeddinggemma-300m`, docs `title: none | text: `, queries
  `task: search result | query: ` (asymmetric; §I62's prefix trap). This is the §I70 winner and
  **arm 1's primary**, so arm 2's numbers sit on the same instrument as arm 1's.
* **SECONDARY: qwen3@1024** — `Qwen/Qwen3-Embedding-0.6B`, plain pooled **re-embed of the arm's own
  children** (⚠️ **not** the stored `dense_1024`, which is late-chunked — F5 — and would put the two
  arms of this run under different conventions, which is the defect F5 records).
* ⚠️ **Why not late chunking, which is what the product ships:** late chunking pools a parent's
  **token** vectors over each child's span, so it is the right convention for a *chunking* arm — but
  the parent token pass is one cluster call per parent with per-token output (~48 min and ~13.6 GB
  of JSON by the ingest's own measurement, `late_chunk_embedder.py:26-29`), the cache does not hold
  it (F6), and **gemma has no registered late-chunked anchor** to reproduce. Recorded as a
  **follow-on** (§5), not smuggled into the primary.

⚠️ **The ceiling moves with the chunking, and that is part of the result.** §I58's reachable set is
"a page with ≥1 chunk, `is_content is not False`, inside the window". A finer cut can put a chunk on
a page that had none. **Each arm is normalised against ITS OWN reachable set**, and **pages covered**
is reported per arm. Never re-normalise one arm against another's ceiling.

⚠️ **`chunks/page` is the standing confound and it is larger here than anywhere else in the
register.** Page-deduped recall scores a page at its single best chunk's rank, so an arm with more
chunks per page gets more chances. Arm 1 measured 6.68 (old corpus) vs 4.07 (new); T0 vs C splits
**5,715 vs 3,796** children over the same parents, so the split is **by construction** in the same
direction. **Report `chunks/page` for every arm**, and read the endpoint beside it — a positive that
is entirely a chances-per-page artifact is not a chunking win.

⚠️ **A negative is interpretable.** The merge joins micro-chunks into their predecessor, which
raises a page's *best* chunk rank when the micro-chunk was the weak one; removing the merge can
therefore lower page-level recall while raising chunk-level precision. This arm measures the
page-level effect, which is what the gold set labels.

## §3 — PRE-REGISTERED ENDPOINT AND RULE

* **Endpoint: paired, ceiling-normalised R@20, arm T0 − arm C, n = 133**, under **gemma@768**.
* **Attributable iff the 95 % CI excludes 0.** Otherwise the honest statement is **"the inherited
  `min_chunk_tokens=32` merge does not move base-lane page ranking on this corpus"** — a RESULT, not
  an unresolved one.
* **ONE run. No extension. No arm added after seeing numbers.** T16 is fixed here, in advance.
* **Reported alongside, always:** raw R@20, R@100, pages covered per arm, **`chunks/page` per arm**,
  the child count per arm, the qwen3@1024 secondary row, the T16 sensitivity row, and F7's
  off-boundary page-attribution count.
* **The decision this feeds:** if T0 resolves **positive**, the merge is worth removing at the next
  re-ingest (which then needs its own product-endpoint run). If **null or negative**, the merge is
  not the 0.0648, and the residual moves to **the segmentation itself** — arm 3,
  `semantic_threshold` (0.8).
* ⚠️ **§0's power rule stands:** n = 133, resolution floor ≈ **0.020**. T0 is expected to be a
  **large** structural change (33.6 % of children, F2), so it is in scope; a knob whose plausible
  effect is below the floor is not.

## §4 — VERIFIERS (each must be able to FAIL)

| # | check |
|---|---|
| **M1** | **instrument**: arm C, freshly embedded plainly with gemma, reproduces **§I70's gemma@768 row EXACTLY** — cR@20 **0.480410** · R@100 **0.704882** · R@500 **0.946105**. The arm **re-embeds**, so a nondeterministic endpoint CAN move it (an identical-by-construction comparison would be the §I63 "check that cannot fail" trap). |
| **M2** | **reproduction, no parse**: arm C's re-chunk reproduces the **stored 3,796 children exactly** — count, and per parent the ordered `(char_start, char_end, text)` — i.e. F1 holds inside the harness. |
| **M3** | **parents faithful**: **341** parents; `parent_text` identical within every parent group (0 inconsistencies). |
| **M4** | **A-vs-A negative control**: arm C embedded twice at **different batch sizes** is byte-identical on every per-query score. |
| **M5** | **no silent drops**: every query whose reachable set is empty **in any arm** is reported, never dropped. |
| **M6** | **the confound is on the record**: `chunks/page` and pages covered reported for **every** arm, and the F7 off-boundary page-attribution count reported. |
| **M7** | **the resolved store is the remote one** — `QDRANT_HOST=10.0.10.65`, `QDRANT_COLLECTION=knowledge_base_v2` (§I49 Finding 1: a run without the override silently targets the LOCAL store). |
| **X1** | *(extra)* T0's child count equals the **raw chonkie** count **5,715** — the knob did what its name says, asserted rather than assumed. |

⚠️ **Standing lesson this arm inherits (§I71/§I70/§I72 — three premise errors in one session):**
**when a guard asserts a reproduction of a number from elsewhere, name the POPULATION and the
CONVENTION it was measured under.** M1 does: the population is arm C's own children, the convention
is plain pooled gemma@768 over the shipped pool — not "the stored lane", which is late-chunked (F5).

## §5 — WHAT THIS ARM DOES NOT DO, AND WHAT COMES AFTER

* **It does not touch the product path.** The base lane is a **ceiling**, not the endpoint: §I66
  measured the loss as the 100-slot fusion and the cross-encoder (0.7478 → 0.6048 → 0.4318), and
  §I65 is the case where a measured ceiling did not become recall. A win here licenses a re-ingest;
  it does not ship.
* **It does not test the shipped (late-chunked) convention** (F5, §2). If T0 resolves, the
  late-chunked replication is the **registered follow-on** and its cost is the parent token pass.
* **It does not fix the merge's own defect.** §E1 measured that the merge **never re-checks the
  grown child's size** (6 of 66 fixture children still sat below the threshold afterwards) and that
  every parent's **first** child is promoted unconditionally. Both are **code** changes, not knob
  settings, and each needs its own arm. ⚠️ **Do not fold a re-check into this run** — that would make
  T0 a two-variable contrast, which is §I56's unattributability defect.
* **It does not measure the ingest-time side effects** of a finer cut (new chunk ids, card
  regeneration, graph rebuild, the intent classifier). That is a build, not an arm.
* **▶ NEXT ARMS, in the pre-registered order** (arm 1's pre-reg §5): after this, **arm 3
  `semantic_threshold`** (0.8), then **arm 4 late chunking** (36 min/arm — and it changes the
  embedding, not the chunking, so it is its own contrast).

## §6 — COST

| stage | cost |
|---|---|
| re-chunk all three arms from the payloads | **~10 s** (measured: 3 s for one pass) |
| plain pooled embeds — 3,796 (C) + 5,715 (T0) + ~4,700 (T16) children × 2 embedders | **~1–3 min per arm** on the cluster |
| scoring (exact cosine, no ANN, no Qdrant scoring) | **~1 min** |

**No LLM calls, no parse, no re-embed of the corpus, no writes to any collection.** Total wall
expectation: **under 15 minutes**, plus the verifier dispatch.

## §7 — ARTEFACTS TO PRODUCE

* `logs/p1/step10/min_chunk_tokens_ab.py` — the harness (extend `chunk_filter_ab.py`: its
  `cluster_embed`, `scroll_pool` and metric helpers are the instrument M1 pins; **copy the metric
  helpers verbatim** so M1 can be an exact reproduction).
* `logs/p1/step10/min_chunk_tokens_ab.json` — the artefact: meta, verifiers, arms, endpoints,
  per-query rows.
* `logs/p1/step10/min_chunk_tokens_ab_verifier.py` — an **independently written** stdlib aggregation
  over the raw per-query array, with `--check` diffing against the artefact (the §I70/§I71 pattern).
  The reviewer gets the extract, never the summary block.
* The register entry in `IMPROVEMENTS.md` (**§I76** — ⚠️ §I75 was taken on 2026-10-24 by the
  graph-lane reachability finding, which is a different subject; do not renumber that one) and the
  `HANDOFF.md` block.
* **The probe is already on disk**: `rechunk_from_payload_probe.{py,json}` — commit it with this
  pre-registration's run, since §1's F1/F2 rest on it.

**Verifier dispatch: with the run, not after.** `openai/gpt-oss-20b` (different family from the
author *and* from the subject). ⚠️ Point it at a **compact pack**, never at the artifact whole — the
§I74 precedent is a reviewer that **died on output-length truncation** when handed a 400 KB
artifact, and a dead reviewer is **no verdict, not a pass**. ⚠️ If this session's shell again returns
**empty stdout with exit 0**, smoke-test one `echo` first and dispatch a **read-only** reviewer
(`read_file` / `search_files` only, `terminal` named and forbidden) with the evidence embedded as
DATA — and record the arithmetic as **mechanical evidence**, not as a second opinion.
