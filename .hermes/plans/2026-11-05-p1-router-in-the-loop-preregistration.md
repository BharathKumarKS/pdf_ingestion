# P1 — THE ROUTER-IN-THE-LOOP RUN — pre-registration

> **Written 2026-11-05, BEFORE the run.** Per **D6.1** it is **committed ALONE**, and nothing
> measured is in it. Read first: `IMPROVEMENTS.md` **§I116** (the eval bypasses the router), **§I82** /
> **D6.5** (the router's agreement is 0.5714), **§I97** (the per-type rerank-query policy the router
> gates).

---

## 1. The question

Every retrieval metric in the programme is computed with `query_type` taken from the **gold label**
(`evaluate_rag.py:817`). The **product** instead routes with `IntentRouter.classify()` — agreement
with the gold labels **0.5714** — and that one label gates **three** things: **HyDE** (fires only for
`factual`/`overview`), **lane selection** (`also_raptor`/`also_graph`), and the **rerank query**
(`hyp if overview else query`).

> **How much does the product's REAL routing cost at the endpoint, versus the oracle routing every
> metric assumes?**

This is the end-to-end leak §I116 recorded as unmeasured. It is a **read-only retrieval-only** run.

---

## 2. What this IS, and IS NOT

| | |
|---|---|
| **IS** | a **read-only** run over the **133 text-lane gold queries**, two arms differing in **only one thing**: where `query_type` comes from. |
| **IS** | arm **A** = the gold `query_type` (today's eval — the oracle); arm **B** = `IntentRouter.classify(q_vec)` (the product's real routing). |
| **IS NOT** | a generator run, a `src/` change, a store write, or a re-ingest. |
| **IS NOT** | a visual-lane run — the 33 `vis-*` queries are excluded (they carry no chunk-level metric, §I115). |

⚠️ **The router may predict `visual` for a text-lane query.** The product's *ask* path does not branch
to the ColPali lane on intent (it always runs the text funnel; only the dedicated visual tab calls
`visual_search`), so the harness maps a `visual` prediction the same way the ask path does — **the
vector lane still runs** — and **records the prediction** (G6) so the mis-route is visible rather
than silently absorbed.

---

## 3. The quantities

```
arm set   {A gold, B router}  x  133 text-lane queries   (retrieval-only, CE top-20)
PRIMARY        paired Δ R@20 (B − A)
secondary      nDCG@20, MAP, MRR@20, Hit@20, coverage of reachable labelled pages
```
A delta is **RESOLVED** iff its paired 95 % CI (`mean ± 1.96·SD/√n` over the per-query differences)
excludes 0.

---

## 4. Predictions (fixed BEFORE the numbers exist)

1. **Anchor (not a finding):** arm A reproduces the product endpoint — `lane_inclusion.json` arm
   **F0** (R@20 **0.4563**, nDCG@20 **0.5503**) — within ±0.02. If it does not, the instrument is not
   the product's and the run is **void**.
2. The router **differs** from the gold on a substantial share of queries (agreement **0.5714**).
3. **The test:** does arm **B** resolve **negative**? Three admissible outcomes:
   * **RESOLVED NEGATIVE** ⇒ the product is worse than every published number — the headline.
   * **UNRESOLVED** ⇒ the router's errors do not move the endpoint; the oracle assumption is benign.
   * **RESOLVED POSITIVE** ⇒ the router beats the gold labels (would mean the labels are worse than
     the classifier — a label-quality finding, not a router win).

**Falsification clause.** If the router does **not** differ from the gold on any query (G3), the arms
are identical by construction and the run reports nothing.

---

## 5. Guards (each must be able to FAIL)

| # | check |
|---|---|
| **G1** | population **133** text-lane queries (no `vis-*`). |
| **G2** | **zero errors** in both arms. |
| **G3** | the router **differs** from the gold on ≥ 1 query (else identity by construction). |
| **G4** | arm A reproduces F0 (R@20 0.4563, nDCG@20 0.5503) within ±0.02. |
| **G5** | **determinism**: arm A re-run is bit-identical on the endpoint metrics. |
| **G6** | the router's predicted-label distribution is **recorded** (a `visual` prediction on a text query is counted, not dropped). |

---

## 6. Bounds

* One corpus, one document, **one router** (the 768d `data/models/intent_classifier.pkl`). A better
  router would move the number; this measures *this* one.
* The HyDE hypothetical is **frozen** (§I73 cache; a miss RAISES rather than calling the LLM).
* **Read-only**: no collection write, no re-ingest, no `src/` change.

---

## 7. Verifier and mutation proof

* **Independent stdlib verifier** `logs/p1/step10/router_in_loop_verifier.py` — re-derives every
  aggregate and the paired CI from the artifact's **raw per-query** arrays; re-checks G1–G6.
* **Mutation proof** `logs/p1/step10/router_in_loop_mutation.py` — one mutation per check; **no inert
  check** (every check reddened by ≥ 1 mutation).
* An **independent cross-family reviewer** (`openai/gpt-oss-20b`, read-only) on a compact extract,
  per the verification contract.

---

## 8. Registration

On completion: an `IMPROVEMENTS.md` entry (§I117 or next), the artifact
`logs/p1/step10/router_in_loop.json`, the run log, the verifier and mutation proof. **Read-only at
run time.** ⚠️ **If it lands, the deck's "0.4563 R@20" must be re-labelled as an oracle-routing
number.**
