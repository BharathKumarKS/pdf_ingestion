# P1 — PRE-REGISTRATION: at the cross-encoder, is `embeddinggemma-300m` worth its extra adoption cost over `nomic-embed-text-v1.5`?

> **Written 2026-10-24 (session 15), BEFORE the harness exists and before any number is seen.**
> ⚠️ **Not committed** — the owner has not authorised a commit this session; the discipline the
> commit serves (freeze the spec first) is honoured by writing this before the run and not editing
> it once the run starts: **if any number in this file is edited after the run begins, the run is
> void.**
>
> Read first: `IMPROVEMENTS.md` §I70 (the oracle screen), §I72 (the cross-encoder survival test this
> extends), §I66 (the stage decomposition), §I67 (the width levers, both nulls), §I58 (the ceiling
> rule).

---

## §0 — WHY THIS, AND WHY IT IS THE LAST CHEAP MEASUREMENT BEFORE THE CALL

§I70's screen ranked the candidates on an **oracle**: `gemma@768` > `nomic@768` > `qwen3@1024`, with
gemma beating nomic by **+0.046480** (CI [+0.016960, +0.076000], 52/19/62) at the **base lane**.

§I72 then measured what survives the product's last retrieval stage, and found the cross-encoder a
**strong equaliser**: against the incumbent, the gap **halved** (+0.184317 → **+0.097559**), because
the cross-encoder lifted the weaker embedder by **+0.0888** and the stronger by **+0.0020**.

⚠️ **§I72 measured gemma against the INCUMBENT, not against nomic.** So the question that actually
decides the adoption is still open: **does the cross-encoder compress the gemma-vs-nomic gap too?**
It matters because the two candidates have very different adoption costs:

| | low lane (the funnel's fast first stage) | extra work |
|---|---|---|
| **nomic@768** | MRL **64** exists ⇒ the lane stays **64-wide** and the name `dense_64` stays **true** | the shared re-ingest only |
| **gemma@768** | smallest trained slot is **128** ⇒ the lane **widens 64 → 128** | ⚠️ **plus a code change**: `store.py:451` hardcodes `using="dense_64"` while the slice is `query_vector[:cfg.dense_dim_low]`, and the schema check keys on the literal `"dense_64" in vectors_cfg` (§I13: a name that encodes its dimension lies the moment it changes) |

Both candidates share the expensive half (re-ingest, re-index every derived collection, retrain the
intent classifier, drop-and-recreate the collection). The **difference is the low lane**: nomic is a
same-width drop-in, gemma is a width change plus a rename plus a schema-detection repoint.

**So this measurement decides whether gemma's measured advantage is worth paying for.**

## §1 — THE QUESTION, IN ONE LINE

Given the same 100 candidates per query ordered by cosine under `gemma@768` and under `nomic@768`,
does the cross-encoder preserve gemma's advantage, and is what survives larger than the
instrument's resolution floor?

## §2 — THE DESIGN

Identical to §I72's, extended by one arm. Instrument: §I70's corpus and pool, so the anchor rows are
**exactly** the register's.

* **Corpus / pool**: doc `7ba61432`, the shipped pool (§I70's arm C — `is_content is not False`,
  pages in `[30, 936]`): **3,489** chunks. §I71 measured the §I39 content filter a null on this lane,
  so the shipped pool is the correct control.
* **Queries**: the same **133** (`gold-*` / `ovw-*` with `relevant_pages`), sorted by id.
* **Embedders — three arms, and only two of them are a contrast**:
  * `qwen3@1024` — **the instrument anchor**, from the **stored** `dense_1024` vectors (free). Not a
    candidate; it exists so guard G1 can pin this harness to §I70.
  * `nomic@768` — cluster-embedded from the chunk text with `search_document: ` / `search_query: `.
  * `gemma@768` — cluster-embedded with `title: none | text: ` / `task: search result | query: `.
* **HyDE OFF** — raw query vectors, consistent with §I70/§I71/§I72.
* **Ordering**: exact cosine over the whole pool (no ANN).
* **Candidates**: the top **F = 100** chunks by cosine (`cfg.reranker_fetch_k`, the product's own
  pool width, asserted at run time, not chosen).
* **The stage under test**: the live cluster cross-encoder (`cfg.sv_rerank_url`,
  `BAAI/bge-reranker-v2-m3`), called exactly as `src/pdf_ingestion/reranker.py` does, `top_k = 20`
  (`cfg.reranker_top_k`), with the **raw query text** (HyDE off).
* **Metric**: page-deduped **ceiling-normalised R@20**, ceiling = the reachable set (§I58) =
  **888** pages. ⚠️ **Two conventions are reported** (§I72's correction, and the reason that run's
  first attempt was VOID):
  * the **contrast** uses the **product's** convention — pages of the top-k **chunks**
    (`scripts/evaluate_rag.py:333-341`), which is also the only one available for a reranked arm;
  * the **anchor** rows use **§I70's** convention — top-k **pages** from the full deduped ranking —
    because that is the convention the register's numbers were produced under.

## §3 — PRE-REGISTERED ENDPOINT AND RULE

* **Primary endpoint: paired, ceiling-normalised R@20 POST-rerank, `gemma@768 − nomic@768`, n = 133.**
* **Reported alongside, always:** the same contrast **PRE**-rerank; each arm's PRE and POST R@20; the
  **survival ratio**; the qwen3 anchor rows in both conventions; the failed-call count and the n.
* **The rule, fixed before the run.** Let `δ = POST Δ(gemma − nomic)` and let the resolution floor at
  n = 133 be ≈ **0.020** (§0 of the plan; re-derived from this run's own SD_d and reported):

  | outcome | reading | disposition |
  |---|---|---|
  | **δ resolves positive AND δ > 0.020** | the advantage survives the last retrieval stage at a size the instrument can resolve | **gemma is worth its extra cost** — proceed to the low-lane rename and the scratch-index product run |
  | **δ unresolved, or 0 < δ ≤ 0.020** | what survives is at or below the resolution floor | **take nomic** — a same-width drop-in, no code change, and the data does not contradict it. Recorded as a *data* decision, not a cost concession |
  | **δ resolves negative** | the cross-encoder **reverses** the base-lane ordering | **take nomic**, and record that the oracle screen's ordering does not survive this stage — a finding about the instrument, not just about the models |

* ⚠️ **If the third row occurs it must not be softened.** A reversal would mean the screen that
  chose gemma is measuring something the product does not see, and that belongs in the register as
  loudly as a win would.
* **ONE run. ONE contrast.** The three arms are the two candidates plus one anchor; no further arm is
  added after seeing numbers.

## §4 — GUARDS (each must be able to FAIL)

| # | check |
|---|---|
| **G1** | **the instrument anchor**: the PRE arm under **§I70's convention** reproduces §I70's `qwen3@1024` R@20 **0.293934** EXACTLY, and the pool is 3,489 with 888 reachable pages. |
| **G2** | **a second, independent anchor**: the PRE arm under §I70's convention reproduces §I70's `nomic@768` R@20 **0.433930** EXACTLY. ⚠️ This is the stronger of the two — it pins the **candidate's own** embedding path (cluster prefixes included), not just the incumbent's stored vectors. |
| **G3** | the rerank service is **live and reordering** (at least one list's order differs from its input). |
| **G4** | **negative control** — the same list reranked twice returns the identical order (a nondeterministic reranker would make the contrast a tolerance, §I68's class). |
| **G5** | every failed rerank call is **counted and reported** with its ids, and the contrast states its n. Never silently dropped (§I55's class). |
| **G6** | **A-vs-A** for **both** candidates: each re-embedded at a different batch size is bit-identical (`max_abs_diff == 0.0`). |
| **G7** | one shared chunk→page mapping; ceiling 888; and the `documents` sent are the candidate texts in cosine rank order (alignment asserted, not assumed). |

## §5 — WHAT THIS DOES **NOT** TEST

* **Not the product endpoint.** The cross-encoder is applied to a **cosine-ordered** pool; the product
  reranks a pool that has been through Qdrant's RRF, page dedup and MMR, and §I68 measured that
  fusion nondeterministic server-side — hence excluded rather than simulated.
* **No** SPLADE lane, DA/card lane, graph lane, RAPTOR, ColPali visual lane, intent router or
  generator.
* **No late chunking.** The incumbent's stored vectors have it; both candidates embed raw chunk text
  without it (§I70's asymmetry, conservative for the candidates).
* **Not the ingest cost.** The re-ingest, the derived collections and the intent-classifier retrain
  are shared by both candidates and are **not** measured here.

## §6 — COST

No LLM calls, **no writes** to any collection. 133 queries × **3 arms** = **399 rerank calls**
(100 documents ≈ 45 KB each), plus two candidate re-embeds (measured at ~34 s for nomic and ~61–73 s
for gemma in §I70/§I72) and one payload scroll. **~15 min wall**, dominated by the rerank calls.

## §7 — ARTEFACTS

* `logs/p1/step10/ce_gvn.py` — the harness (helpers copied verbatim from `ce_survival.py` so G1/G2
  can be exact reproductions; ⚠️ `ce_survival.py` is **NOT edited** — its artifact is registered
  against that revision).
* `logs/p1/step10/ce_gvn.json` — meta, verifiers, per-query PRE/POST rows for three arms, endpoints.
* `logs/p1/step10/ce_gvn_verifier.py` — an **independently written** stdlib aggregation over the raw
  per-query array, `--check` / `--extract`.
* The register entry (`IMPROVEMENTS.md` §I74) and the `HANDOFF.md` block.

**Verifier dispatched with the run, not after** (§I70/§I71/§I72's rule) — `openai/gpt-oss-20b`,
read-only (`read_file` / `search_files` only; this machine's shell returns empty stdout with exit 0).
