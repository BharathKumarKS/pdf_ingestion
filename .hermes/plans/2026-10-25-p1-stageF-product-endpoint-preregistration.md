# P1 — Stage F: the ONE product-endpoint run — nomic/`v3` vs qwen3/`v2` (pre-registration)

> **Written 2026-10-25, session 18 (S5), BEFORE any number of this A/B exists.** The nomic plan's §3
> Stage F is *"ONE pre-registered product-endpoint run"* and §5's gate is *"F is the only stage whose
> result can license a ship — everything before it is preparation."* This file fixes what that run
> measures and how its numbers may be read, so the result cannot be interpreted after the fact
> (§D1's rule). **A commit containing this file and nothing measured is the point of it** (§I61's
> precedent).
>
> Read first: `HANDOFF.md` (session 18), the nomic plan §3 Stage F / §5 / §7, `IMPROVEMENTS.md`
> **§I84** (§I68's fix, landed this session), **§I77** (why nomic over gemma), **§I74** (the measured
> gemma-vs-nomic contrast this run is the product-endpoint counterpart of), **§I70/§I72** (the oracle
> screen and the cross-encoder survival test), **§I64** (Phase E on v2 — the registered row the v2 arm
> must reproduce), **§I58** (ceiling normalisation), **§I68** (the defect that made any A/B on this
> path depend on a tolerance), **§I55** (the reranker's fallback), **§I80** (the A2 `.env` warning).

---

## 1. The question

**Does the nomic-768 index (`knowledge_base_v3`) beat the incumbent qwen3-1024 index
(`knowledge_base_v2`) at the PRODUCT retrieval endpoint, on the same 133 gold queries?**

This is the product-endpoint counterpart of §I74, which measured the two embedders **at the
cross-encoder** on a fixed pool (`gemma − nomic` POST **+0.029248**, a thin margin ~1.19× the run's
own floor). §I70's screen measured them on an **oracle** (exact brute-force cosine over a fixed
corpus). **Neither is the product**: the product's funnel is
`dense(low→full rescore) + sparse + colbert → RRF → page dedup → MMR → cross-encoder`, over a **live
index**, with **HyDE** on factual/overview queries. That is the thing to test, and it is the only
stage whose result can license a ship.

⚠️ **What this run is NOT is a finding that nomic beats gemma.** Gemma was declined on measured
**cost** (§I77: its endpoint truncates at 2048 tokens, exposing 37.3 % of children), and the plan's §0
**forbids** restating the decline as *"gemma was worse"* — the measured gain still favours gemma
(§I74). This run compares nomic against **the incumbent**, not against gemma.

## 2. What this A/B IS, and is NOT

| | |
|---|---|
| **IS** | a **paired, single-variable** A/B on the **product retrieval path** (`store.search_with_das` + the shipped cross-encoder + `evaluate_rag.compute_retrieval_metrics`), 133 gold queries, **HyDE ON and frozen** (§4) |
| **IS** | a comparison of two **whole indexes** (model, dim, and the vectors built from them). The embedder is the treatment; everything downstream is held fixed |
| **IS NOT** | a re-ingest, a Qdrant write, a graph write, a config change to `src/`. **No writes to any collection.** |
| **IS NOT** | the §D12 cross-system comparison. Both arms are the same 133 queries, same day, one instrument, one funnel |
| **IS NOT** | the §I66 stage decomposition. That is Stage G, run **alongside** this one (§I66's own note) |
| **IS NOT** | the fine-tune (plan §4). Different lever, later |
| **IS NOT** | retrieval + synthesis + judge. **Retrieval-only first** (§10) |

## 3. The two arms — and the per-arm config that makes them possible

The treatment is the **index**, so each arm needs its **own embedder, its own dims and its own
collection**, switched by environment (§I80: the A2 `.env` flip is **still not applied**, so a run
that forgets these exports silently uses Qwen3/1024 against the wrong collection — the S2/S3 trap).

| arm | collection | `DENSE_MODEL` | `DENSE_DIM` | `DENSE_DIM_LOW` | query / document prefix | role |
|---|---|---|---|---|---|---|
| **A** | `knowledge_base_v2` | `Qwen/Qwen3-Embedding-0.6B` | 1024 | 64 | Qwen3's `QUERY_INSTRUCTION`, no document prefix | **control / baseline** — the incumbent, and the arm that must reproduce a registered row (E8) |
| **B** | `knowledge_base_v3` | `nomic-ai/nomic-embed-text-v1.5` | 768 | 64 | `search_query: ` / `search_document: ` | **treatment** — the adopted embedder |

⚠️ **The low lane's WIDTH is resolved off the collection, never from `cfg`** (Stage A,
`store._resolve_low_lane`) — both collections carry `dense_64`, so the read path slices to 64 in both
arms. The full lane is `dense_1024` on v2 and `dense_full` on v3, also resolved off the collection.

**Everything else is pinned in both arms:** the query file (`data/eval_queries_v2.json`), the 133 gold
queries (`gold-*`/`ovw-*` with labels, sorted by id), the HyDE cache (§4), `mmr_enabled` /
`mmr_candidates` 100, `reranker_fetch_k` 100, `reranker_top_k` 20, the reranker, the DA lane (ON),
SPLADE/ColBERT as configured, `dense_prefetch_limit` 1000, `dense_rescore_limit` 500, and the metric
function. ⚠️ **§I68's client-side RRF is now the funnel in BOTH arms** (§I84) — the fusion is
deterministic, so a non-zero A-vs-A is now a genuine alarm rather than the expected wobble (§I68).

## 4. HyDE — ON and FROZEN (this is a hard precondition, not a nicety)

`evaluate_rag.py` generates a HyDE hypothetical per **factual/overview** query with an LLM
(`call_llm` hardcodes `temperature 0.3`), so without a cache **every arm embeds a different
hypothetical for the same query** and the query vector — not the treatment — moves the number (§I68's
class). The cache exists (§I73) and is used:

`data/hyde_cache/18ece9b9404688c8__openai_gpt-oss-20b__ab681b8e43855a46.json` — **127 entries, 0
failed**, model `openai/gpt-oss-20b`.

⚠️ **The filename and the header are both the contract, and the header is re-validated on read.** As
of this writing the running `.env` resolves to exactly this file — `OPENAI_MODEL=openai/gpt-oss-20b`,
`data/eval_queries_v2.json`'s byte-digest is `18ece9b9404688c8`, the prompt digest is
`ab681b8e43855a46` — so **no rebuild is needed**. ⚠️ **A miss RAISES; it never falls back to a live
LLM call.** If the header disagrees the run must stop, not proceed.

⚠️ **Consequence of HyDE being on: the absolute numbers ARE product-shaped**, unlike §I61/§I65/§I67
(which ran HyDE off). Quote both arms' absolutes and the paired delta.

## 5. Endpoints (pre-registered)

| # | endpoint | role |
|---|---|---|
| **P1** | paired Δ **Recall@20 ceiling-normalised** (§I58), **B − A** | **primary** — the product's own cut, with the denominator equalised |
| **P2** | paired Δ **Recall@20 raw**, B − A | **primary** — reported beside P1; if they disagree both are stated, never averaged |
| S1 | paired Δ R@100 (`fetch_k`), Hit@20, MRR, `context_precision` | secondary |
| S2 | per `query_type` (factual / multihop / overview) Δ cR@20 | secondary |
| **M1** | the funnel's **stage decomposition on both arms** (base → fusion → cross-encoder) — Stage G's probe | **mechanism** — did the embedder fix the full-dimension ranking lane, or move the loss? |
| G1 | §I55 reranker fallback per query, per arm | **guard** |

⚠️ **The page convention is the PRODUCT's — "pages of the top-k CHUNKS"** (`evaluate_rag.py:333-341`),
**not** §I70's "top-k PAGES". §I72's VOID is exactly this confusion; state the convention with the
number.

## 6. Pre-registered reading rule

1. **Ship only on a resolved positive primary.** Arm **B** ships iff the paired 95 % CI on ΔcR@20 (P1)
   **excludes 0** and the point estimate is **> 0**. CI = `mean ± 1.96·SD/√n` over the per-query
   paired differences (the repo's convention).
2. **Unresolved is a result, not a licence.** If the CI includes 0, the entry records
   **measured-and-unresolved**, and the re-ingest does **not** ship on this evidence — §I70/§I72/§I74
   remain the register's account of the embedder.
3. **Negative is recorded, not hidden.** If it resolves negative, the entry says so and nothing ships.
4. **P2 does not substitute for P1**, and P1 does not substitute for P2.
5. **§I55 fallback queries are excluded from the top-20 headline and named.** A fallback returns the
   pool **unranked**, making any top-k comparison on that query inert by construction. Headline
   reported with and without them.
6. **Quote the size, not just the sign.** §I74's margin was ~1.19× the run's own resolution floor with
   the CI's lower bound below it. If this run's margin is of that shape, the entry says so.
7. **No causal claim beyond these two indexes.** One corpus, one document, one day, one funnel.
8. **M1 is a mechanism check, not a second endpoint.** It must be read as *where* the difference sits,
   not as a second verdict on the same question.

## 7. Guards (each must be able to FAIL)

| # | check |
|---|---|
| **E1** | each arm's **resolved** config names its collection and a non-blank `QDRANT_HOST`, and prints `dense_model`/`dense_dim` — a run against the local embedded store, or with the wrong model, is unverifiable (§I49 Finding 1; the S2/S3 trap) |
| **E2** | arm A resolves to `Qwen/Qwen3-Embedding-0.6B`/1024/`knowledge_base_v2`; arm B to `nomic-ai/nomic-embed-text-v1.5`/768/`knowledge_base_v3` — asserted, and recorded in the artifact |
| **E3** | **133** queries compared in every arm; errored queries counted and named, never silently dropped |
| **E4** | **negative control: one arm run TWICE is bit-exact on every metric of every query.** ⚠️ This is now a *legitimate* bit-exact control because §I68 landed (§I84: the funnel is deterministic). A non-zero self-difference means the instrument is noisy → the run is **VOID** and no endpoint is read |
| **E5** | every aggregate re-derives from the artifact's own per-query array (§I57) — nothing read off the summary block |
| **E6** | §I55 fallbacks counted and named per arm; headline reported with and without |
| **E7** | the cut can move: report each arm's pool size against the top-20 cut. A pool ≤ 20 would make the top-k metric inert by construction and must be reported as uninformative rather than as a null |
| **E8** | **arm A reproduces a REGISTERED row.** The v2 arm must reproduce a §I64/§I57 number (Phase E's v2 retrieval row) under the stated convention. ⚠️ If it does not, the harness is **not** the product path and the run is VOID — this is the check that makes the whole comparison mean anything |

**E4 and E8 are the load-bearing guards.** E4 makes the instrument's determinism an assertion rather
than an assumption; E8 makes "this is the product" a measurement rather than a claim.

## 8. Power

`n = 133` is fixed (every answerable text query), so power is reported, not chosen. The entry states
the observed `SD_d` and the `n` required for `δ = 0.05` at that `SD_d`. **The resolution floor at
n = 133 is ≈ 0.020** — a result whose point estimate sits below it is reported as such, not converted
into a claim (§0's doctrine).

## 9. Verifier

One independent, **cross-family** reviewer (the standing rule; the author is DeepSeek-family), which
must: re-derive every aggregate from the per-query array itself; check E1–E8; confirm the negative
control is exactly zero; confirm E8's reproduction against the registered row; and look for a query
silently excluded from a denominator. The probe's own numbers are the claim, so the verifier is
dispatched **with** the run, not after the numbers are being quoted. ⚠️ Point it at a **compact
extract** (the raw per-query array + the claims), never the full artifact (§I74's lesson: a reviewer
handed a 400 KB artifact died on truncation).

## 10. Cost, and the stop rule

* **Retrieval-only: minutes** (measured shape, §I65/§I67 — 133 queries × two arms, cluster reads only,
  HyDE served from the cache). **This is what runs first.**
* **The full run (synthesis + judge) only if the retrieval endpoint RESOLVES**: ~70 min, **5,434 judge
  calls** (§I64). ⚠️ Do not spend it on an unresolved retrieval result.
* **Serialize against other cluster-LLM work** — HyDE is cached, but the cross-encoder and the
  embedders are shared with the cluster.

## 11. Preconditions (all must hold before the run starts)

1. ⚠️ **§I68's fix is landed in the working tree, and its own diff reviewer has NOT returned** (§I84
   records the measurement and the mutation proof; the fix is **uncommitted and unverified** until
   that reviewer reports). The funnel is measured deterministic — before 2/6, 6/6, 6/6, 5/6 distinct,
   after 1/6 on all four — so E4 is a real control, but **do not run F on top of an uncommitted,
   unverified product-path change.**
2. ✅ **`knowledge_base_v3` is populated** — 3,796 points / four lanes (§I81), preflight exit 0 (§I83).
3. ✅ **The HyDE cache resolves for this run** — verified above (§4).
4. ⚠️ **The per-arm environment is exported** (§3). The A2 `.env` flip is **not** applied; the run
   script must export and **assert** every value, or the run is unverifiable (E1/E2).
5. ⚠️ **This file is committed ALONE, before the run** (§I61's precedent). Nothing measured is in it.

## 12. Stated, deliberately — the confounds this design does NOT remove

* **The intent router is NOT on the eval path.** `evaluate_rag.py` uses each query's gold `query_type`
  for routing; it records the router's config but does not call it, and `search_with_das` does not use
  it. So the classifier's dimension does **not** confound the retrieval arms. ⚠️ **Stated because the
  router WOULD refuse a 1024-trained pickle against a 768 embedder** (`intent_router.py:156`) — the
  product UI on the v2 arm is a separate question from this A/B, and is out of scope here.
* **RAPTOR is not in v3** (§I81's scope note: 73 nodes are a separate `run_phase2.py --raptor-only`
  step). The funnel's overview path reads RAPTOR; if the overview cut (S2) shows an effect, **that
  absence is a candidate explanation and must be named**, not attributed to the embedder.
* **The graph lane** fires on multihop only and is a second lever; per-`query_type` numbers are
  reported so its absence from the headline is visible.
* **One document.** The corpus is a single textbook; a corpus-size dependence cannot be seen here.
