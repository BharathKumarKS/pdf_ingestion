# P1 — the embedder screen, the HyDE cache, and the domain fine-tune (next-session plan)

> **Written 2026-10-24, session 13, at the owner's direction.** This is the successor to
> `2026-10-23-p1-downstream-widths-and-embedder-screen-plan.md`: the **widths half is closed as a
> null** (§I67 — the fusion width and the re-score cut are both nulls at the product endpoint, at
> ample power), so what remains is the **embedder half**, plus two workstreams the owner raised:
> a HyDE cache, and domain fine-tuning.
>
> Read first: `IMPROVEMENTS.md` §I63 (the cross-embedder instrument and the +0.1400 result), §I62 (the
> Nomic prefix trap), §I58 (ceiling normalisation), §I67/§I68/§I69 (the closed widths work, the RRF
> non-determinism, the float leak), `HANDOFF.md` session 13.

---

## §0 — DOCTRINE: explore cheap, confirm powered (a process correction)

**Why this is section 0.** Session 13 spent three ~1-hour runs confirming a null that a 40-query
screening had already indicated. That is the failure mode to avoid, and it is a process error, not a
statistics one.

**The resolution floor.** `n = 133` is fixed (every labelled query; more means hand-labelling new
data). At the widths' measured spread, the smallest effect this design can resolve is

```
1.96 · SD_d / √n  =  1.96 · 0.115 / √133  ≈  0.020
```

The width effect measured **0.0032 — ~6× below the floor**, and resolving it would need ~5,000
queries. **Consequence: any knob whose plausible effect is < ~0.02 is OUT OF SCOPE for this gold set**
and should be recorded as such, not re-tested.

**The three rules that follow:**

1. **Explore cheap first.** A screening subsample (40 queries), an oracle instrument (exact cosine),
   no pre-registration. Look for signal.
2. **Confirm powered, and only if the exploration found something.** Pre-registration, CIs, negative
   control — *once*.
3. ⚠️ **Not every finding is an effect size.** Correctness and robustness defects need a **fix**, not a
   power analysis: §I47 (a lane dead on every multihop query), §I49 (768d collection vs 1024d query),
   §I68 (the fusion is non-deterministic). Do not run these through the effect-size lens — it is what
   makes a session feel like it is circling.

**Power is still the right lens for RANKING-QUALITY claims** — and a powered negative is a real
result: it says the lever is dead and tuning stops. That is what §I67 now is.

---

## §1 — THE EMBEDDER SCREEN (do this first; ~15 min total)

**Instrument: §I63's cross-embedder experiment, unchanged.** Hold the corpus fixed, swap only the
embedder, **exact brute-force cosine** (not Qdrant — §I60 measured up to 18.5 % HNSW loss), 133
queries, ceiling-normalised paired R@20 (§I58). **124 s wall, no LLM calls, no writes.**
`logs/p1/step10/cross_embedder_experiment.{py,json}` is the template.

⚠️ **Keep HyDE OFF in the screen** (§2). The screen is on raw query vectors; adding HyDE would confound
the embedder comparison with the generator.

**Candidates — each at ITS OWN smallest trained MRL slot AND at full dim** (owner decision 2026-10-23:
do not force a fixed 64d):

| model | dims | MRL slots | note |
|---|---|---|---|
| `Qwen/Qwen3-Embedding-0.6B` | 1024 | 32–1024 | **incumbent**; MTEB-ml-v2 64.33 |
| `nomic-ai/nomic-embed-text-v1.5` | 768 | 64–768 | **§I63's known-best on this corpus (+0.1400)** |
| `google/embeddinggemma-300m` | 768 | 512 / 256 / **128** | ⚠️ **NO 64d slot** — adopting it forces a new named vector = another re-index |
| `tomaarsen/mpnet-base-nli-matryoshka` | 768 | 768/512/256/128/**64** | ~110M, `MatryoshkaLoss`-trained, **NLI not retrieval** — expect it to lose |

**Traps to carry in (all already measured — do not re-derive):**
- **The endpoint IGNORES a `dimensions` param** (sending 256 returns 768). Slice client-side and
  **re-normalise**.
- **§I62's prefix trap applies to EmbeddingGemma too**: `"task: search result | query: "` for queries,
  `"title: none | text: "` for documents — **asymmetric**. The cluster is a generic passthrough and
  applies NO prefixes (measured for Nomic: raw cosine 0.949 vs prefixed 1.000000).
- All four are already **served by the cluster** (verified live 2026-10-23 on `10.0.10.70:8123`).

**Pre-registered decision rule (already written, keep it):** a candidate must beat **BOTH** the
incumbent (Qwen3-1024) **and** Nomic-768 on paired ceiling-normalised R@20 with a CI excluding 0,
**before a re-ingest is even costed**. Nomic must be in the comparison because it already beats the
incumbent — losing to Nomic is not an improvement whatever it does against Qwen3.

⚠️ **This is an ORACLE screen, not the product.** Exact cosine over the corpus. A positive licenses
(a) costing the re-ingest and (b) **one** product-endpoint run — it does not ship.

**Deliverable:** `logs/p1/step10/embedder_screen.json` — per model, per slot: paired Δ R@20 (cnorm) vs
both baselines, CI, W/L/T, and the full-dim row.

---

## §2 — THE HYDE CACHE (parallel; small build)

**Why.** `evaluate_rag.py:190` generates a HyDE hypothetical per query with an LLM whenever
`hyde_enabled` — **there is no cache today**. That makes every arm's query vector nondeterministic,
which is fatal to any arm-to-arm comparison (and is the same class as §I68).

**Design — cache the TEXT, not the vector:**
- Key by **query id**; store the hypothetical **string**. The text is **embedder-independent**, so ONE
  cache serves every candidate in §1's screen and the eventual re-ingest. A vector cache would have to
  be rebuilt per embedder and would defeat the purpose.
- File: `data/hyde_cache/<queries-file-digest>__<model>__<prompt-digest>.json` — keyed by the run
  (query file + model + prompt digest), so a model or prompt change does not silently reuse stale text.
- **Freeze the model and the prompt in the file** (the §I52 lesson: measure the model the phase runs).
- Only **factual / overview** queries get a hypothetical (that is what `evaluate_rag.py` does today).
- Generate ONCE, then every arm reads the same file. Reuse across sessions.

⚠️ **Do not wire the cache into §1's screen** — the screen is HyDE-off on purpose. The cache is for the
product-path run in §3.

**Deliverable:** `src/pdf_ingestion/hyde_cache.py` + tests + the generated cache file. It should fail
LOUDLY on a miss (never silently fall back to a live LLM call mid-run — that is §I25's class).

---

## §3 — AFTER THE SCREEN: the re-ingest decision, ONE product run, and the stage decomposition

**Only if §1 produces a winner.**

1. **Cost the re-ingest** honestly — measured from this project: ingest 58.6 min, card run 8.9 h, graph
   rebuild 1 h 6 m, plus `derivative_artifacts` (73,406), `concept_embeddings` (7,427), the intent
   classifier, RAPTOR, ColPali page images, and §I58's `_REPOINT` label map. A new embedder means new
   chunk ids, so all of it.
2. **ONE pre-registered product-endpoint comparison**: new embedder vs the current, 133 queries,
   paired, ceiling-normalised R@20, HyDE **on and frozen** (§2). Not a grid — one contrast.
3. **Run the §I66 stage decomposition alongside it** (base recall → the funnel/fusion → the
   cross-encoder → the generator). This is the *diagnostic* half and it is cheap (the §I66 probe, not a
   full eval). It answers the question that matters for the writeup: **did the better embedder fix the
   full-dimension ranking lane, or just move the loss around?** The current map, for reference:

   | stage | current system |
   |---|---|
   | 64d lane | 0.8151 |
   | → after the full-dim re-score cut | 0.7478 |
   | → after the fusion | 0.6048 |
   | → after the cross-encoder to top-20 | 0.4318 |

---

## §4 — THE DOMAIN FINE-TUNE (stage 3; a BUILD, not an eval)

**The owner's point, and it is measured:** generic embedders are suboptimal here — §I63 had Qwen3
(general) losing to Nomic on this corpus by **+0.1400**. Domain fit is the lever, and contrastive
fine-tuning is the standard recipe.

**The training set already exists.** The card corpus is on disk: **75,645 cards**, of which
**29,321 are `question` cards**, each paired with its source chunk → ~29k synthetic **(query, passage)**
pairs in physics. `factoid` (30,635) and `definition` add more. This is the blocker that normally kills
a fine-tune, and we are not blocked.

**Method:** MultipleNegativesRankingLoss-style contrastive training on (query, positive chunk) pairs,
in-batch negatives. Base model = **the §1 winner** (not a guess). Matryoshka-aware if the base is
(`MatryoshkaLoss`) so the low lane survives.

**Three things that decide whether it works:**

1. **Validate on the SAME instrument as §1** (§I63's exact-cosine oracle, 133 gold queries). Otherwise a
   fine-tuned model cannot be compared against off-the-shelf ones. **The instrument is a prerequisite —
   build it in §1.**
2. ⚠️ **Leakage is real but manageable.** The card questions are LLM-generated *from* the passages, so
   they are easier than real queries. Train on cards, evaluate on gold — different distributions, so the
   test is fair, but **expect a smaller gain at the gold set than on the training distribution. Report
   both, and report a held-out card split too.**
3. **Compare against the §1 winner, not just the incumbent.** A fine-tune that beats Qwen3 but loses to
   off-the-shelf Nomic has bought nothing.

**Cost/risk:** a GPU job on the shared cluster, a training script, a held-out split, a checkpoint, and
then the §3 re-ingest if it wins. **Hours, not minutes** — hence stage 3.

---

## §5 — EXPLICITLY OUT OF SCOPE (recorded so they are not re-opened)

- ⚠️ **Any knob with a plausible effect < ~0.02** (§0). The fusion width and the re-score cut are
  already here — **§I67 closed them as nulls; do not re-test them** (the "add more candidates from DA /
  graph / overview, pooled at the fusion lane" idea is §I66's lever, already tested at 100→300→500).
- ⚠️ **An all-lanes-at-once matrix.** Enabling visual + graph + DA together is §I56's defect exactly —
  it measured −0.0262 with four things changing at once and could not attribute it. **Lane
  contributions must be one variable at a time.**
- ⚠️ **The graph lane is BLOCKED**: Memgraph is **down** (port 7687 refused, measured 2026-10-24), and
  §G5/§I2 records that `hop_distance` is a constant 0, so "multihop" is nominal. Fix those first.
- ⚠️ **The visual lane** needs the ColPali collection populated for the new document before it can be
  evaluated.
- **Sub-0.02 tuning in general** — revisit only if the gold set grows past ~400 queries.

---

## §6 — FIRST ACTIONS FOR THE NEXT SESSION

1. Build the **HyDE cache** (§2) — small, independent, unblocks every later arm.
2. Run the **embedder screen** (§1) — ~15 min, four models, own-slot + full dim. **This is the one item
   that finishes quickly and produces a decisive number.**
3. Read the result and **take the re-ingest call** (owner decision). If a candidate beats both
   baselines: cost it, then §3. If none does: §4 (fine-tune the best base) is the remaining lever.
4. Keep **§0's doctrine** in front: explore cheap, confirm powered, and treat bugs as bugs.

**Open owner decisions carried forward:** the re-ingest (cost, timing); whether to fine-tune at all;
§I56's DA lane (one-variable test, still open); the §I68 client-side-RRF fix (its own plan — it also
removes the instrument nondeterminism); and whether to commit session 13's work (currently uncommitted).
