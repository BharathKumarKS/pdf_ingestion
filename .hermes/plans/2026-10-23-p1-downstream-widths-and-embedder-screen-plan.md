# P1 — the downstream widths (re-score cut L, `fetch_k`/MMR), then the embedder screen

> **Written 2026-10-23, session 12, at the owner's direction.** Two separate pieces of work, in this
> order. The first is a measurement with a pre-registration that should be written *before* its run
> (the same discipline §I65's A/B was held to). The second is explicitly **deferred to a later
> session** by the owner — do not start it before the first is settled.
>
> Read first: `IMPROVEMENTS.md` §I65 (the prefetch A/B — a NULL, and the cautionary case), §I66 (where
> the loss actually is, and the ceilings), §I63 (the cross-embedder instrument), §I62 (the prefix
> trap), §I58 (the ceiling rule), §I56 (the DA lane, which enters the same fusion stage), `HANDOFF.md`.

---

## PART 1 — the downstream widths

### 1.1 Why this, and why now

§I65 raised the 64d prefetch limit from 1000 to exact search and the product endpoint moved **+0.003
(CI includes 0)**. §I66 explained it: at exact prefetch the fusion's own loss *grows* (0.143 → 0.222),
because the fusion's output width does not grow — extra candidates compete for the same 100 slots.
**The binding constraint is the 100-slot fusion output, not the prefetch and not the re-score cut.**

The decomposition §I66 measured (denominator = a query's reachable labelled pages):

| stage | production (N=1000) | exact prefetch (N=3489) |
|---|---|---|
| 64d lane | 0.8151 | 1.0000 |
| → after the full-dim re-score cut L=500 | 0.7478 | 0.8286 |
| → after the fusion (RRF + dedup + MMR to 100) | **0.6048** | **0.6071** |
| → after the cross-encoder to top-20 | 0.4318 | 0.4348 |

So there are two hardcoded widths left, and both sit inside the loss:

| width | where | value | ceiling if raised (§I66, exact prefetch) |
|---|---|---|---|
| **L** — the full-dim re-score cut | `store._qdrant_search`, the outer `Prefetch(limit=500)` | **500** | L=1000 → 0.9266 · L=2000 → 0.9773 · L=all → 1.0000 |
| **`fetch_k` / MMR** — the fusion's output width | `search_with_das` (`fetch_k`, `mmr_candidates`) | **100** | not yet measured |

### 1.2 The change under test

Make both settings, exactly as `dense_prefetch_limit` was made one (§I65): a field on `Settings` whose
default **is the shipped value**, read at the single site, with a test that pins (a) the value is read
from config, (b) the other funnel stages do not move with it. **Config-only. No re-ingest, no model
change, no Qdrant write.** The §I65 test (`tests/test_dense_prefetch_limit.py`) is the template.

⚠️ `fetch_k` is threaded in two places with two meanings — `search_with_das(fetch_k=...)` sets the DA
lane's limit *and* the MMR target, while `mmr_candidates` sets the funnel's outer limit. **Read the
call path before naming the knob**, and say in the pre-registration which one moved.

### 1.3 Pre-registration to write (BEFORE the run)

- **Arms, one variable each, everything else pinned.** Recommended split into two sub-experiments so
  each is single-variable:
  - **L-arms**: L ∈ {500 control, 1000, 2000} with the prefetch pinned at **2000** (so the lane is not
    the cap — §I66 shows N=1000 caps L's benefit at 0.8151).
  - **width-arms**: `fetch_k`/MMR ∈ {100 control, 200} with L and N pinned at their chosen values.
- **Primary endpoint**: paired Δ **R@20** on the product retrieval path, 133 queries, CI = mean ±
  1.96·SD/√n. Secondary: R@100, Hit@20, NDCG@20, MRR, ctx-precision, per `query_type`.
- **Decision rule**: ship iff the CI excludes 0 **and** the point estimate > 0. Unresolved ⇒ recorded
  and not shipped.
- **Guards** (each must be able to fail):
  1. the negative control (control arm re-run) is **bit-exact** — else the A/B is VOID (§I65's E4);
  2. the resolved settings gate asserts the collection, the host, **and that the control arm still
     resolves to the shipped values**;
  3. §I55 reranker fallbacks counted and named, headline reported both ways;
  4. every aggregate re-derives from the per-query array (§I57);
  5. the cut must be able to move — report each arm's pool size against the top-20 cut.
- **Record as deliberate confounds**: HyDE off (arms share one query vector; absolute numbers are not
  production numbers), the graph lane excluded, negatives/visual excluded.
- ⚠️ **Do not assume the §I66 ceiling becomes recall.** §I65 is exactly the case where a real ceiling
  gain (+0.185 on the lane's coverage) produced nothing at the endpoint. A raised ceiling is a
  *hypothesis*, not a result.
- **Power**: report the observed SD_d and the n required for δ=0.05 at it.

### 1.4 What would make this uninformative

If the control arm's pool is already ≤ the top-20 cut, the metric is inert by construction (§G1's
defect). §I65 measured pool min 63 / median 100, so the cut bites — re-confirm it per arm.

### 1.5 Cost

No LLM calls (HyDE off), no writes. §I65's four-arm run took **31 min** for 133 queries; a three-arm
run should be ~25 min. Cluster reads only.

---

## PART 2 — the embedder screen (DEFERRED by the owner to a later session)

### 2.1 The owner decision taken 2026-10-23 (session 12)

**Use each model's own available MRL slice — do NOT force a fixed 64d across models.** If a model's
smallest trained slot is 128d, screen it at 128d. This supersedes the earlier "keep 64d" framing.

### 2.2 What the screen is, and why it is not a recall lever

**It is a RANKING screen, not a recall screen.** §I65 and §I66 together show that coverage is not the
binding constraint on this corpus — the 64d lane reaches 1.0000 of the reachable pool at exact
prefetch and the product does not move. The only place an embedder can help here is the
**full-dimension ranking lane**, and §I63 measured that lever's size on this exact corpus:
Nomic-768 beat Qwen3-1024 by **+0.1400** ceiling-normalised R@20 (resolved). That is the honest prior.

### 2.3 Candidates — all ALREADY SERVED by the cluster (verified live 2026-10-23, not assumed)

| model | dims | MRL slots | params / note |
|---|---|---|---|
| `Qwen/Qwen3-Embedding-0.6B` | 1024 | 32–1024 | **incumbent**; MTEB-ml-v2 64.33 |
| `nomic-ai/nomic-embed-text-v1.5` | 768 | 64–768 | §I63's known-best **on this corpus** (+0.1400 over Qwen3) |
| `google/embeddinggemma-300m` | 768 | 512 / 256 / **128** | 308M; MTEB-ml-v2 61.15 @768d. ⚠️ **NO 64d slot** |
| `tomaarsen/mpnet-base-nli-matryoshka` | 768 | 768/512/256/128/**64** | ~110M, trained with `MatryoshkaLoss`; NLI-trained, not retrieval-trained |

⚠️ **`google/embeddinggemma-500m` does not exist.** The family is `embeddinggemma-300m` and
`embeddinggemma-2` (740M total, 270M text backbone; **not loaded** — HTTP 500).
⚠️ **`embeddinggemma-300m` is gated on HF** (the card needs a licence acceptance); it is nevertheless
served by the cluster, which is what matters.

### 2.4 Traps to carry into the implementation

1. **The endpoint IGNORES a `dimensions` parameter.** Verified: sending `dimensions: 256` returns 768.
   Slice client-side and **re-normalise** — the current 64d lane does exactly this.
2. **§I62's prefix trap applies to EmbeddingGemma too.** The cluster is a generic passthrough and
   applies NO task prefixes (measured for Nomic: raw cosine 0.949 vs prefixed 1.000000). EmbeddingGemma
   wants `"task: search result | query: "` for queries and `"title: none | text: "` for documents —
   **asymmetric**. Apply in the caller.
3. **A 64d requirement is a real constraint on the candidate set.** EmbeddingGemma's smallest trained
   slot is 128d, so if the low lane must stay 64d, adopting it forces a collection schema change (a new
   named vector) — another re-index. Nomic and mpnet-matryoshka have genuine 64d slots.
4. **The instrument already exists**: §I63's cross-embedder experiment — hold the corpus fixed, swap
   only the embedder, **exact brute-force cosine** (not Qdrant; §I60 measured up to 18.5 % HNSW loss),
   133 queries, ceiling-normalised paired R@20. 124 s wall, no LLM, no writes.

### 2.5 Pre-registered decision rule

**A candidate must beat BOTH the incumbent (Qwen3-1024) AND Nomic-768** on paired ceiling-normalised
R@20 with a CI that excludes 0, before a re-ingest is even costed. Nomic must be in the comparison
because it already beats the incumbent — a candidate that loses to Nomic is not an improvement
whatever it does against Qwen3.

### 2.6 Cost of acting on a positive result (so a "yes" is not mistaken for cheap)

A new embedder means new chunk ids: re-ingest of 3,796 chunks, then re-index of `derivative_artifacts`
(73,406), `concept_embeddings` (7,427), the intent classifier, 75,645 cards, RAPTOR, the ColPali page
images, and the Memgraph graph (3,533 chunks / 7,427 concepts), plus §I58's `_REPOINT` label map.
Measured from this project: ingest attempt 5 = 58.6 min, card run = 8.9 h, graph rebuild = 1 h 6 m.
**This is why the screen runs first.**
