# DECISIONS.md — the decision log

> **What this is.** Every point where a real fork was taken: the options, what was chosen, **why**, and
> **why not the alternatives** — with the number that backs it. Written so a decision can be defended
> (interview, review) or re-read months later without reconstructing it from chat.
>
> **How to read an entry.** Each has: **Options** → **Chosen** → **Why** (the evidence) → **Why not**
> the others → **Reversibility** (what it would cost, and what new evidence would reopen it).
> **The register (`IMPROVEMENTS.md` §) is the source**; this file is the index of the *choices*.
>
> ⚠️ **The rule this log obeys:** a choice is stated with the **size** of the effect, not just its sign,
> and a **null is recorded as a result**, never silently dropped. Where a decision was **cost-driven,
> not accuracy-driven**, it says so — that distinction is the one most often lost.

---

## 0. The standing doctrine (the meta-decisions)

**D0.1 — "Explore cheap, confirm powered."** A 40-query screen (~2 min) indicates; a 133-query powered
run (~1 h) confirms. **Why:** the downstream-widths work burned three ~1-hour runs confirming a null a
screen had already indicated. **Why not** run everything powered: cost. **The rule it yields:** the
resolution floor at n=133 is ≈ **0.020**; **any knob with a plausible effect below ~0.020 is out of
scope for this gold set** — record it, do not chase it. **Reversibility:** a larger gold set lowers the
floor and reopens every recorded-and-unresolved knob at once.

**D0.2 — Not every finding is an effect size.** §I47/§I49/§I68 are **bugs needing a fix**, not a power
analysis. **Why:** asking "is it significant?" of a deterministic defect (a 400, a dropped candidate)
is the wrong instrument. **Why not** treat everything as an A/B: it would launder a defect into a
"measured-and-unresolved" and hide it.

**D0.3 — `[verified]` is a claim about verification, not a mood.** A reviewer verdict is **banked only
if it is substantive**; a cheap verdict (few API calls, seconds, or citations that do not resolve) is
**corroboration at best** and is recorded as **not banked**. **Why:** repeated sessions produced
reviewers that "confirmed" 7/7 while citing line numbers that do not exist. **The substantive half is
the author's mechanical evidence** — the measurement, the mutation proofs, the suite.

**D0.4 — Verification completeness is enforced by a DETERMINISTIC gate with a MECHANICAL trigger, not
by prose.** Every step carries four parts (acceptance · independent reviewer · stdlib verifier ·
mutation proof), and **"a step with no verdict is not done"**. That rule lived only as prose in a plan,
so it was silently skipped: measured 2026-11-05, **P0, R8 and C2 were all marked ✅ with no reviewer** —
a *consistent* omission nothing caught, because a hand-written status table cannot distinguish "no
reviewer" from "recorded elsewhere".
* **Chosen:** `scripts/verify_plan_coverage.py` — **deterministic** (no model, no judgment): for every
  `✅ DONE` row it asserts the verifier cell is non-empty, the mutation cell is non-empty, an independent
  reviewer **resolves** (a `deleg_*` id, or a `…review…` artifact that exists on disk), and every
  backticked `path/like/this` exists. Bound to the suite by `tests/test_plan_verification_coverage.py`
  so it **cannot itself be skipped**, with its own negative tests (it must redden on a missing reviewer
  and on a missing artifact). Demonstrated: run against the pre-fix table it names **exactly P0, R8, C2**.
* **Why not a "verifier of the verifier" (a second model reading the table):** that is a **judgment**
  check, so it fails for the same reason the first one did — it fires only if someone remembers to run
  it, and then you need a trigger for the trigger. A **deterministic** gate needs no verifier of its own.
* **The residual judgment, stated:** whether a reviewer's verdict is **substantive** cannot be gated —
  it stays under **D0.3** (*a partial verdict is no verdict*), plus recording the reviewer's model id.
* **Reversibility:** cheap — the gate is ~90 lines and its rules are per-plan; a plan whose table has a
  different shape needs its own parser, not a new doctrine. **What would reopen it:** a step type that
  legitimately has no reviewer (then the rule is amended *in the gate*, visibly, not by leaving a cell
  blank).

---

## 1. The embedder / index

**D1.1 — Adopt `nomic-ai/nomic-embed-text-v1.5` @768/64 over the incumbent Qwen3-1024 and over
`google/embeddinggemma-300m`.**
* **Options:** (a) stay on Qwen3-1024; (b) nomic-768; (c) gemma-768.
* **Chosen:** **nomic** (owner decision 2026-10-25, §I77).
* **Why:** ⚠️ **This is a COST decision on NEW MEASUREMENT, not a finding that nomic is better.** On the
  same corpus, gemma's endpoint **truncates at 2048 tokens** (71/341 parents exceed it → **37.3 %** of
  children affected, **9.2 %** losing vectors outright) while nomic's window is **8192** and **0/341**
  parents exceed it; gemma's tokenizer is a **gated** HF repo, nomic's is **ungated**.
* **Why not gemma:** the measured gain actually **favours gemma** (§I74: gemma − nomic POST **+0.029248**
  at the cross-encoder). ⚠️ **The plan's §0 forbids restating the decline as "gemma was worse"** — it was
  declined on cost, and the truncation made its late-chunk path *unbuildable* (§I77).
* **Why not Qwen3:** it ranks **worse** on this corpus (oracle §I63: nomic − qwen3 **+0.1400** R@20).
* **Reversibility:** a re-ingest + every derived collection + the classifier. **What reopens it:** an
  ungated, ≥8192-window gemma (or a working 2048-split strategy).

**D1.2 — The low lane is named `dense_128` / `dense_64` (the dimension in the name), not `dense_low`.**
* **Options:** (a) `dense_low` (a name that does not encode the width); (b) `dense_128`/`dense_64`.
* **Chosen:** **(b)**, on an **owner override** of the plan's own recommendation (§I13's trap).
* **Why:** owner instruction, implemented and recorded as the owner's call so it is not re-litigated.
* **Why not (a):** the plan rejected a width-in-the-name **because the next embedder change repeats the
  rename** — and that cost **was paid**: the nomic switch renamed `dense_128` → `dense_64` across 33
  literals / 18 files and invalidated the 874-dir resume cache.
* **Reversibility:** a rename sweep. **Honest note:** this is the one decision here whose stated cost
  was realised, and it is recorded that way.

**D1.3 — Build into a NEW collection (`knowledge_base_v3`); leave `v2` untouched and queryable.**
* **Options:** (a) rebuild in place; (b) a new collection.
* **Chosen:** **(b).** **Why:** a dimension is **immutable** — v3 had to be created at 768, and v2 must
  stay live for the A/B (the control arm *is* v2). **Why not in place:** it would destroy the baseline
  the experiment needs. **Reversibility:** cheap (drop v3).

**D1.4 — Shape B (re-embed preserving chunk ids) over Shape A (re-parse + re-chunk).**
* **Options:** (a) Shape A — re-parse the PDF, new chunk ids; (b) Shape B — recompute the dense lanes
  from stored payloads, **carry `colbert` + `sparse` over by id**.
* **Chosen:** **(b)** (§I81). **Why:** the payloads carry `text`/`parent_text`/`char_start`/`char_end`,
  so late chunking is reproducible **without re-parsing**, and **cards (8.9 h) + the graph (1 h 6 m)
  stay valid**. Verified: chunk_id set **byte-identical** (3,796/3,796), point ids preserved, and the
  late-chunk path reproduces the source at **cos 1.000000**. **Why not (a):** new ids invalidate every
  derived artifact. **Reversibility:** a full re-ingest (~10 h).

**D1.5 — Signoff 4 (the MRL truncation convention): KEEP the project's plain slice + re-normalise.**
* **Options:** (a) `layer_norm`-then-slice (Nomic's model card); (b) plain slice (what the code does).
* **Chosen:** **(b)**, on measurement (§I79). **Why:** the A/B is a **null** — Δ **+0.000314**, CI
  [−0.0035, +0.0042] straddles 0 and sits **below the run's floor (0.003853)**. So every Nomic-64
  number in the register **stands** and needs no re-measurement. **Why not (a):** no measured benefit,
  and it would invalidate §I59's rows. **Reversibility:** none needed.

---

## 2. Ingestion & chunking

**D2.1 — The content filter does NOT ship (§I71).** **Options:** ship it / record-and-not-wire.
**Chosen:** **not wired.** **Why:** paired Δ ceiling-normalised R@20 **−0.0063**, CI
[−0.0211, +0.0085] **UNRESOLVED** — a null, and under half the floor. **Why not ship:** no evidence it
helps. ⚠️ **The headline is the premise error:** the filter's stated reach was **263 chunks** (a
*whole-corpus* count) but the base lane's pool is the **content window `[30, 936]`**, which already
excludes **244 of the 263** — the real treatment is **19 chunks**, so the null was near-predictable.
**Lesson recorded:** *when a guard asserts a reproduction of a number from elsewhere, name the
population AND the convention.*

**D2.2 — `min_chunk_tokens` (arm 2) is measured, not shipped — and was never re-checked.** **Options:**
re-parse the PDF (the plan's reading) / reconstruct from payloads. **Chosen:** reconstruct — the
chunking is a **pure function of stored payloads** (~3 s, byte-identical), **~20× cheaper** than
assumed. **Why:** measuring is cheap; *shipping* a chunking change is what needs a full re-ingest.

**D2.3 — Late chunking under gemma: MIXED index / split parents / drop late chunking.** ⚠️ **This fork
was never resolved — it was made moot by D1.1.** **Why it existed:** gemma's 2048-token truncation made
Shape B's late-chunk pass unbuildable. **Why it stopped mattering:** nomic's 8192 window means **0/341
parents exceed it**. **Recorded because** the question would return with any short-window embedder.

---

## 3. The retrieval path

**D3.1 — The fusion moves from Qdrant's server-side RRF to a client-side `_rrf_merge` (§I68/§I84).**
* **Options:** (a) keep `FusionQuery(fusion=Fusion.RRF)`; (b) fuse in Python.
* **Chosen:** **(b)** — **a product-path change, taken because (a) is a DEFECT.** **Why:** the server's
  RRF is **non-deterministic** — identical inputs, different fused output (`gold-052` returned **6
  distinct candidate sets in 6 runs**). It was the root cause of §I67's VOID and it made **any** A/B on
  this path depend on a tolerance. **Why not `exact=True`:** measured — **the ANN is already
  deterministic**; the nondeterminism is the fusion. **Guard:** the swap is **endpoint-identical**
  (ΔR@20 = **0.0** on all 133 queries, W/L/T 0/0/133). ⚠️ **The merge constant is MEASURED, not chosen:**
  the live server's RRF is exactly `Σ 1/(1+rank)` (**k = 1**); `_rrf_merge`'s own default is 60 and
  would have rescaled every score ~60×. **Reversibility:** high — it is the product path.

**D3.2 — The downstream widths do NOT ship (§I67).** **Options:** raise the fusion width W / the re-score
cut L. **Chosen:** neither. **Why:** both **nulls** at ample power (W: Δ +0.0032, CI [−0.0164, +0.0227];
L: Δ +0.0025, CI [−0.0024, +0.0074]). ⚠️ **A design finding survives the null:** the cut is **inert by
construction** at the shipped W=100 — a knob downstream of a saturated cut cannot be tested without
widening upstream. **Why the chain matters:** §I65 (prefetch is a null) → §I66 (**the 100-slot fusion
output is the binding constraint**) → a raised ceiling is still not recall.

**D3.3 — The DA lane: "keep as-is" (owner), and this session measured its size.** **Options:** change it
/ keep it. **Chosen:** **keep** (§I56), then **this session** measured the DA-off vs DA-on gap at
**+0.0225** R@20 (arm A DA-off 0.4475 vs Phase E DA-on 0.4250), close to §I56's independently measured
**−0.0262**. **Why it stayed a "keep":** the effect is consistent but was **unattributed** (four things
changed at once); the owner's call stands, and the number is now on record.

**D3.4 — The graph lane was recorded "down" on a MIS-SCOPED probe; it is UP (§I75).** **Options:**
exclude it / test reachability. **Chosen:** test. **Why:** the "Memgraph is DOWN — 7687 refused" claim
probed the **cluster** IPs; the code and `.env` point at **localhost:7687**, where the container is Up —
measured 1 Document / 3,533 Chunk / 907 Page / 6,065 Concept and 5/5 multihop queries returning 5 chunks.
⚠️ **Reachability is not contribution** — every query returned exactly its limit. **Why it still stays
excluded:** `hop_distance` is a constant 0 (a code defect, §G5/§I2).

---

## 4. Measurement methodology

**D4.1 — Page-level recall uses the PRODUCT's convention: "pages of the top-k CHUNKS".**
* **Options:** (a) "top-k PAGES" (§I70's screen); (b) "pages of the top-k chunks" (the product,
  `evaluate_rag.py:333-341`).
* **Chosen:** **(b) for any product claim**; (a) is used only to pin the oracle instrument.
* **Why:** the product's top-20 is *chunks*; deduping to pages first changes the number. **Why it
  matters:** §I72's first run went **VOID** on exactly this confusion — two conventions, −0.0196/−0.0217
  apart. **Rule:** *state the convention with the number.*

**D4.2 — Ceiling normalisation is §I58's GLOBAL divisor, not a per-query top-k-slot normalisation.**
* **Options:** (a) `cR@k = mean(R@k) / mean(achievable_max)` (§I58/§I64); (b) `R@k / (min(|rel|,k)/k)`
  (what §I84's `cr20` ≈ 4.44 uses).
* **Chosen:** **(a)**. **Why:** it is the convention that reproduces the register — §I64's **0.4453 =
  0.4250 / 0.9545** and **0.5275 = 0.465 / 0.8806**. **Why not (b):** a different denominator produces a
  different number and cannot reproduce any registered row. **⚠️ Scale note:** when both arms share the
  chunk set the divisor is **identical**, so the paired delta is **divisor-invariant** — the choice
  cannot change a verdict, only a scale.

**D4.3 — HyDE must be ON and FROZEN for any arm comparison.** **Options:** live LLM per query / a cache.
**Chosen:** the **cache** (§I73). **Why:** `call_llm` runs at **temperature 0.3**, so without a cache
**every arm embeds a different hypothetical for the same query** — the instrument, not the treatment,
moves the number (§I68's class). **Why the cache stores TEXT keyed by query id:** it is
embedder-independent, so one file serves every candidate. **A miss RAISES** — never a live call.

**D4.4 — An instrument anchor: the control arm must reproduce a REGISTERED row (E8).**
**Options:** trust the harness / make "this is the product" a measurement. **Chosen:** the measurement.
**Why:** without it, a harness that silently drifts is indistinguishable from a real effect. **How it
was re-pointed this session:** from Phase E (DA ON) to **§3d** (DA OFF), because the run config changed
— see D5.4. **Result:** arm A reproduced §3d at R@20 **0.4475 vs 0.452** (gap −0.0045).

**D4.5 — A negative control must be bit-exact.** **Options:** a tolerance / exact equality. **Chosen:**
**exact** — but **only once it is legitimate.** **Why:** §I67's E4 was unachievable while the fusion was
nondeterministic (1,064 comparisons, 2 mismatches, `max_abs_diff 0.0`). After **D3.1** landed it is a
**real** control; the re-registration **restated** it by measurement (a 30-query × 4-repeat floor of
**0.000000**), **not relaxed it**.

---

## 5. Stage F (the product-endpoint run) — the forks taken this session

**D5.1 — Run the confounded A/B as-is, or RE-REGISTER before running?**
* **Options:** (a) run with arm A's DA lane dead and arm B's live; (b) re-register (DA off both arms)
  and run; (c) build a 1024d DA collection (a ~26-min write).
* **Chosen:** **(b)** (owner decision), committed **alone before the run** (`e708784`, `a409d7d`).
* **Why:** (a) is **not a single-variable A/B** — it is the §I56 unattributability hazard the
  pre-registration existed to avoid — and arm A could no longer reproduce Phase E. (b) is **zero-write**
  and clean.
* **Why not (c):** it is a store **write** the pre-registration forbade, and it would need the same for
  `concept_embeddings`.
* **Reversibility:** the re-registration is a document; re-running is ~13 min.

**D5.2 — Both derived lanes OFF, because a single 768d collection can serve only one arm.**
* **The mechanism:** `search_da` sends the **DENSE query vector**, whose dim **IS the arm's
  `dense_dim`** (1024 vs 768) — so one `derivative_artifacts` (768d, §I83) fits **one** arm. Arm A got
  a **silent 400** (`store.py:748` logs a warning, returns `[]`). The **graph lane** fails identically
  via `concept_embeddings` (also 768d; `graph_builder.py:686` returns `[]`).
* **Chosen:** DA **and** graph **off in both arms**. **Why:** otherwise the treatment arm has an extra
  live lane. ⚠️ **This NARROWED the question** to the base lanes and it is **stated, not hidden**.
* **⚠️ It is a RECURRENCE:** §D15/§I12 recorded the **same 768-vs-1024** DA death in the §3d run.

**D5.3 — Per-arm PROCESS, not an in-process switch.** **Why:** `get_settings`,
`get_cluster_embedder`, `get_reranker` are **process-global singletons**; the arm's model/dim/collection
come from the **environment**. A one-process switch would silently reuse the first arm's embedder.

**D5.4 — E8's anchor: Phase E (DA ON) or §3d (DA OFF)?** **Chosen:** **§3d** (R@20 **0.452**), with the
tolerance = the n=133 floor (**±0.020**) — a **pre-existing derived** quantity, **not a fit**. **Why:**
the run's config is DA-off, so Phase E (DA-on) is no longer the same instrument. **Why the tolerance is
legitimate:** §3d predates the §I68 swap (proved **endpoint-identical**) and the §I58 label re-points
(1–3 queries) — small, named drifts.

**D5.5 — HyDE source: the frozen cache, delivered by monkeypatching `call_llm`.**
**Options:** re-implement `run_retrieval` / patch the LLM call and use the **product's own**
`run_retrieval` verbatim. **Chosen:** patch. **Why:** it keeps the **product function** on the path, so
E8 is meaningful; only the HyDE *source* changes, which §4 mandates. **Why not re-implement:** it would
make "this is the product" a claim rather than a measurement.

**D5.6 — Retrieval-only first; the full synthesis + judge run only on a RESOLVED retrieval endpoint.**
**Why:** the full run costs **~70 min and 5,434 judge calls** (§I64); the endpoint did **not** resolve,
so it was **not spent**. **Why not run it anyway:** the pre-registration's stop rule; and a null on
retrieval cannot be rescued by generation metrics.

**D5.7b — Stage G was run as a pre-check on the FINE-TUNE, and it LOWERED that bet's ceiling.**
* **Options:** go straight to the GPU fine-tune (S6) / spend ~5 min on a read-only stage decomposition first.
* **Chosen:** the decomposition first (§I86). **Why:** it answers the one question that decides whether a
  fine-tune *can* work — **is the loss in the embedder's lane, or in the funnel?**
* **What it found:** every stage is **≤ 0 for nomic** (base −0.0152 unresolved, cut −0.0556 unresolved,
  **fusion −0.0358 RESOLVED −**, cross-encoder −0.0012 unresolved). The **only resolved loss is at the
  fused pool**, and the **cross-encoder absorbs it before the product's cut** (§I72 reproduced).
* **Why that matters:** a better embedder has **little room at the product endpoint** — the gains are
  consumed by the 64d prefilter and the cross-encoder. **So the lever, if any, is the funnel, not the
  embedder.** ⚠️ **It does not veto the fine-tune; it sets its ceiling low** — and that is a decision
  input worth 5 minutes against hours of GPU.
* ⚠️ **And it REFUTED the hypothesis it was run to test** (stated before the run: *"the oracle's +0.14
  survives the base lane and the fusion destroys it"*). The base stage is a **tie/negative**, so there is
  no base-lane advantage to destroy. **The named gap was then closed** (see D5.7c).

**D5.7c — ⚠️ The ORACLE and the INDEX are not the same object: §I63 measured POOLED nomic, v3 stores
LATE-CHUNKED nomic.**
* **The trigger:** Stage G's gap row (full-dim, no prefilter — §I63's own configuration) measured
  **v3 ≈ −0.14 WORSE than v2** (L=500: 0.8286 vs 0.6887, RESOLVED; resolved at every L) — the **opposite
  sign** to §I63's oracle (**nomic +0.1400**) at almost the same magnitude.
* **The cause, source-read not inferred:** §I63's arm N built its vectors with
  `cluster_embed([DOC_PREFIX + t …])` (`cross_embedder_experiment.py:295`) — **pooled whole-chunk** —
  while arm Q used `scroll_pool`'s **stored** vectors (`:265`, `:329`). So the oracle compared
  **pooled nomic against v2's stored vectors**, and it had to: **v3 did not exist when it ran.**
* **Measured:** stored-vs-pooled cosine — v2 0.9559 (min 0.881), **v3 0.8153 (min 0.502)**.
* **Why it matters:** the oracle's +0.14 **was never about the index we built.** It is *not* "the gain
  fails to survive the funnel" — it is that the oracle **measured a different construction**.
  ⚠️ **The register had already flagged it** (§I77: the oracle gains *"embedded the text pooled, not
  late-chunked"*); Stage G is the first measurement that makes it **consequential**.
* ⚠️ **New cheap open question:** pooled nomic scored well; late-chunked nomic (v3) scores worse than
  qwen3 — **consistent with late chunking (E3) being the cause, but NOT isolated.** If so, the lever is
  the **ingestion**, not the embedder. **Test named, finding not claimed.**

**D5.7d — ⚠️⚠️ LATE CHUNKING IS THE CAUSE (§I87). Three arms, one instrument, all guards pass.**
* **Result (full-dim, no prefilter, L=500):** qwen3 late-chunked **0.8286** · qwen3 pooled **0.8071** ·
  **nomic pooled 0.8433** · nomic late-chunked (v3) **0.6887**.
* **The four paired contrasts — the added `qwen3_pooled` arm is what makes it clean:**
  * nomic pooled − nomic late-chunked = **+0.1547** [+0.1128, +0.1965] **RESOLVED** (77/5/51)
  * qwen3 pooled − qwen3 late-chunked = **−0.0215** [−0.0517, +0.0086] **unresolved** (≈ neutral)
  * **nomic pooled − qwen3 pooled = +0.0362** [+0.0034, +0.0691] **RESOLVED** — like-for-like, **nomic wins**
  * nomic late-chunked − qwen3 late-chunked = **−0.1399** [−0.1805, −0.0994] **RESOLVED** — like-for-like, **nomic loses**
* **The reading:** ⚠️ **the sign flip is an INTERACTION — late chunking × nomic.** Same operation, ≈neutral
  for qwen3, −0.155 for nomic. ⇒ **The lever is the INGESTION, not the embedder.** §I63's oracle was not
  wrong about nomic — it measured the construction the index *should* have had.
* ⚠️ **The interaction points at H2, not H1.** **H1** = late chunking genuinely degrades nomic (now has to
  explain why qwen3 is unaffected). **H2** = the nomic late-chunk path **mis-pools** (a defect). **The
  tell:** stored-vs-pooled cosine **v2 0.9559 (min 0.881)** vs **v3 0.8153 (min 0.502)** — a correctly
  pooled child sits *close* to pooled(child text); **0.502 looks like the wrong span, not extra context.**
* ⚠️ **What was verified and what was NOT:** §I80/§I81 verified the alignment declaration and that a
  **Qwen3** recomputation reproduces v2 at cos 1.000000 — **never** that a **nomic** child equals a
  manual span-pooling. **That check does not exist; it is the cheap discriminating test.**
* **⇒ Consequence for the fine-tune:** **S6 is aimed at the embedder, but the lever is the ingestion.**
  Re-target before spending GPU hours. (Signoff 6, passage-level split, was taken — it is not the
  blocker; the *target* is.)

**D5.7 — THE STAGE F RESULT: the index swap does NOT ship.** **Options:** ship on a resolved positive
primary / record-and-not-ship. **Chosen:** **not ship.** **Why:** P1 cR@20 Δ **−0.001213**, CI
[−0.023051, **+0.020626**] — **UNRESOLVED**; the point estimate is **~18× below** the floor (0.0218);
power was **ample** (n=133; 25.4 needed for δ=0.05). The one resolved secondary (R@100 **−0.0354**) is
**negative** for nomic. **Why the null is the interesting part:** the oracle gain (**+0.14**, §I63)
**does not survive the funnel** — the **sparse + ColBERT lanes are model-independent** (identical in
both arms, so they dilute the dense difference) and the **cross-encoder is a strong equaliser** (§I72).

---

## 6. Process / governance

**D6.1 — A pre-registration is committed ALONE, before the run.** **Why:** it is what makes it a
pre-registration — the result cannot be interpreted after the fact. **Precedent:** §I61, §I67, §I71,
Stage F (`51de3f2`).

**D6.2 — A VOID run is preserved, not deleted, and the re-registration is restated BY MEASUREMENT.**
**Why:** a relaxed guard is indistinguishable from a tuned one. §I67 (E4 → E4′, floor 0.000000), §I71
(C2 → C2′), §I72 (S1 → S1′) all restated from a measurement, and all preserved the VOID artifact.

**D6.3 — A child agent's report is a SELF-REPORT; require a verifiable handle and check it yourself.**
**Why:** two dispatched children misreported — one claimed files it never created, another produced a
fabricated `ls` and a guard table for guards it had not implemented. **Corollary:** point a reviewer at
a **compact extract**, never a large artifact whole (a reviewer handed a 400 KB artifact **died on
truncation**).

**D6.4 — The gold set is re-pointed, not rebuilt (§I58).** **Why:** a label is a **PDF page**, a
property of the document, not the index — and deriving labels *from* the new index would be
**circular**. **Why not rebuild:** ~36k judge calls for a ~1 % reachability gain, and it would destroy
comparability with every historical run.

**D6.5 — The intent classifier is RETRAINED, not left (§I82).** **Why:** the router **refuses** a
1024-trained pickle under a 768 embedder (`intent_router.py:156`) — so this was not optional.
⚠️ Its synthetic held-out accuracy (99.6 %) is **self-consistency, not a product measure**; agreement
with the gold labels is **0.5714** (moderate).

**D6.6 — The preflight is CLEAN (exit 0) — and the two blockers it found were the MID-MIGRATION trap,
not hidden (§I82/§I83).** **Why it matters:** the derived collections were still at the retired **1024d**,
which would have failed every downstream write. They were reset through the **allowlisted** script —
⚠️ **not** `reset_for_reingest.py`, which would also have cleared `knowledge_base` + SQLite.

---

## 7. Open forks (not yet decided — the honest list)

* **The full-funnel question.** Stage F measured the **base lanes**; the full funnel needs a **1024d
  `derivative_artifacts` AND a 1024d `concept_embeddings`** (both a write). **Owner decision, not taken.**
* **The re-ingest.** ~58.6 min ingest + 8.9 h cards + 1 h 6 m graph + derived collections + classifier.
  ⚠️ **Stage F gives it no support on the base lanes** — which strengthens the case for the next item.
* **Signoff 6 — the fine-tune's validation split** (by document/passage, not by card). **Open, gates S6.**
* **Signoff 3 — re-confirm Shape B** (the measured number is far under budget; Shape A is not cheaper).
* **Signoff 4 — accept §I79's measurement** (the null is measured; owner to accept).
* **The A2 `.env` flip** (owner action) — every stage has run on **env exports**; forget them and the run
  silently uses Qwen3/1024 against the wrong collection.
* **The arm-2 harness** — the two untracked `min_chunk_tokens_ab*.py` are a **fragment**; arm 2 is
  **NOT built**. §I56's DA lane, §G2's V5 build, §G5/§I2 (`hop_distance` constant 0).

---

## 8. T1 (the base-lane ship test on the pooled index) — the forks taken this session

**D8.1 — Is T1 a NEW instrument, or Stage F's re-run?**
* **Options:** (a) write a fresh pre-registration and harness for the base-lane ship test; (b) adopt
  Stage F's **re-registered** instrument and re-run it against the changed index; (c) fold T1 into T3.
* **Chosen: (b)** (owner direction, this session). The harness is a deliberate **copy** of
  `stageF_product_endpoint.py`.
* **Why:** the **only** thing that changed is arm B's index content (late-chunked → pooled, §I88/§I89) —
  the arms, the funnel, the endpoints, the page convention, the ceiling convention and E1–E8 are
  identical. A copy makes that identity **auditable** rather than asserted, and it is what makes **E9**
  possible at all.
* **Why not (a):** a second harness would be a second instrument, and any difference in the result would
  then be unattributable between "the index changed" and "the harness changed".
* **Why not (c):** T3 needs §A (the per-space query-vector fix) and §B (RAPTOR into v3); T1 answers a
  question that is answerable **now** and is the narrowed ship test.

**D8.2 — Add E9 (arm A bit-exact against Stage F's recorded arm A), or keep E8 alone?**
* **Chosen:** **add E9**, and keep E8. E9 compares **only six metric keys, by name**.
* **Why:** E8 tolerates ±0.020, which is wide enough that a drifted instrument could still pass it. E9
  makes "**arm A did not move**" a **measurement** — and since arm A shares nothing with the treatment, it
  is the strongest available control that the effect read at P1 belongs to arm B. ⚠️ It **passed**:
  133/133, 0 mismatches.
* **Why the six keys and not the whole dict:** `compute_retrieval_metrics` gained
  `map` / `precision_at_k` / `f1_at_k` **after** Stage F (§I90), so a whole-dict comparison would be an
  **over-strict check that fails on correct data** — §I90's own lesson, applied in advance.
* **Reversibility:** if arm A ever legitimately moves (a code change on the arm-A path), E9 is
  **re-pointed by measurement**, never relaxed (D6.2).

**D8.3 — The T1 result is a NULL. Does anything ship?**
* **Chosen:** **nothing ships.** P1 cR@20 **+0.003894 [−0.020984, +0.028771]**, ~**6× below** the run's
  own floor (0.024878); power ample (n=33 would suffice for δ=0.05).
* **Why:** the pre-registered rule is *ship only on a resolved positive primary*, and a point estimate
  below the floor is **reported as such, not converted into a claim** (§0's doctrine).
* **⚠️ The mechanism, which is the actual finding:** the pooled index's advantage is **+0.104 at the base
  lane** (§I89), **−0.019 RESOLVED NEGATIVE at the fusion**, and **+0.0039 unresolved at the endpoint**.
  **The funnel discards the embedder's advantage.** ⇒ **A model change is not the lever; the fusion is.**
  This is why §E (the attribution) is the next task and why **S6 (the fine-tune) stays parked**.

**D8.4 — Report the pooled-vs-late-chunked endpoint delta (D1) at all?**
* **Chosen:** yes, as a **diagnostic**, never as an endpoint.
* **Why:** it isolates what the re-embed itself bought: **+0.004989 [−0.014788, +0.024767], UNRESOLVED** —
  the same treatment that is worth **+0.1547 at the base lane** (§I87) is worth **+0.005 at the
  endpoint**. Without D1 the T1 null could be misread as "the pooled write failed"; D1 shows the write
  worked and the funnel ate it.
* **Why not an endpoint:** it compares an arm against a **previous session's** arm, not a paired
  same-run contrast — a weaker instrument, so it cannot carry a ship decision.

**D8.5 — Attribute the fusion by moving the product's own CONFIG knobs, or by re-implementing the funnel?**
* **Options:** (a) copy `search_with_das`'s body and instrument the intermediates; (b) move only
  `MMR_ENABLED` / `MMR_CANDIDATES` / `RERANKER_FETCH_K` and read the pool the product actually returns;
  (c) add a `dedup_enabled` flag so dedup can be ablated too.
* **Chosen: (b).** The harness calls the product's own `run_retrieval` verbatim in every arm.
* **Why:** (a) makes "this is the product" a claim rather than a measurement, and a re-implementation
  could differ from the product in exactly the step under test. (b) keeps every arm on the shipped path.
* **Why not (c):** it is a **product-path change** whose own before/after would be needed, and dedup's
  effect on a **page-level** metric is **structurally zero** (it removes duplicate chunks, not pages) —
  so the flag would buy a measurement whose answer is already fixed by the unit. ⚠️ Recorded as a
  **code-read, not a measured contrast**.

**D8.6 — The attribution result re-targets the next action. Does the fusion ship a fix?**
* **Chosen: NO — and this is the session's plan-changing finding.** The fusion's loss is **entirely the
  100-slot cap** (`W500 − C = +0.183538 [+0.151074, +0.216001], RESOLVED, 79/0`), and **MMR is innocent**
  (`C_nommr − C = +0.003178`, unresolved; at width 500 **exactly 0.000000, 0/0/133**).
* **Why nothing ships:** **§I67 already measured the SAME width change at the PRODUCT ENDPOINT as a
  null** (+0.0032 / +0.0027, unresolved). A **+0.1835 pool gain buys +0.003 at the endpoint** — shipping
  it would ship a number that does not reach the student (§I65).
* **⇒ What it changes:** §I89's *"the fusion is the binding constraint"* is **correct about the arm
  difference it destroys and wrong as a target for improvement**. The endpoint loss is the
  **pool → top-20 ranking step** (T0: **0.684486 → 0.455330**, **−0.2292**), which has **never been
  attributed**. **The next run is a cross-encoder / top-k attribution, not a fusion fix.**
* **⚠️ Why not the obvious reading ("widen the fusion"):** the width lever is measured, cheap and
  **inert at the endpoint**; re-testing it would be re-measuring a null (§0's doctrine: record it, do
  not chase it).

**D8.7 — Is the cross-encoder fine-tune (or S6, the embedder fine-tune) the right next build?**
* **Chosen: neither yet — attribute the pool→top-20 step FIRST.**
* **Why:** the cross-encoder's **ceiling is the pool it is handed**, and the pool is not the problem
  (0.868 at width 500). What is unmeasured is whether the **ranking** is the limiter or the **20-slot
  cut**. Those have different fixes (a better reranker vs a wider top-k), and neither can be chosen
  before the split is measured. ⚠️ §I72's "the cross-encoder is a strong equaliser" is a **different
  claim** (about the arm difference) and does not answer this.
