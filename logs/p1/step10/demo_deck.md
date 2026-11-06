# Synapse Learning Worlds — mentor demo deck (outline + speaker notes)

> **Finish line: A — capstone-defensible** (retrieval measured + working demo + write-up).
> Every number below was read out of an artifact; sources named per slide.
> Live app verified 2026-11-02 on port 8503 against `knowledge_base_v3` (10.0.10.65).

---

## SLIDE 1 — Title

**Synapse Learning Worlds** — a hybrid RAG system for physics learning, and the measurement
programme behind it.

*Subtitle:* One textbook (Feynman Lectures Vol. 1), 133 gold queries, and a funnel we measured
end to end.

**SPEAKER NOTES**
> One sentence of scope: "It answers physics questions grounded in a textbook, and — the part I want
> to show you — we measured *where the answers come from and where they get lost*." Signal that the
> talk is half product, half evidence.

---

## SLIDE 2 — The problem, and what we built

* The problem: a student asks a physics question; the system must find the right **pages** and answer
  from them — and we need to know *how well*, not just that it "works".
* What we built: a 4-phase ingestion + retrieval pipeline, an eval harness over **133 labelled
  queries** (factual 53 / overview 40 / multihop 40), and a **measurement discipline**.
* Product today: `knowledge_base_v3` — nomic-embed-text-v1.5, 768d, pooled — cross-encoder top-20.

**SPEAKER NOTES**
> Keep this short. The audience needs: (a) what it does, (b) that there is a labelled eval set, (c)
> that there is a discipline. The interesting content is slides 4–7.

---

## SLIDE 3 — Architecture (the 4 phases)

| Phase | What it does | Where it lands |
|---|---|---|
| 1 | Docling parse → chunk → MRL embed | Qdrant `knowledge_base_v3` |
| 2 | LLM card generation (8 types/chunk) + RAPTOR summaries | same collection + summary nodes |
| 3 | ColPali page images + concept graph | `visual_knowledge_base` + Memgraph |
| 4 | Intent router → hybrid search (dense + SPLADE + ColBERT → RRF) → cross-encoder top-20 | the product endpoint |

**SPEAKER NOTES**
> One line per phase. Do NOT go deep — offer to go deep in Q&A. ✅ UPDATED 2026-11-02: the visual lane
> (Phase 3 ColPali) NOW has data for the CURRENT document — 968 page vectors were written for doc
> 7ba61432 this session (`visual_knowledge_base`: 968 new + 1,033 old = 2,001). It IS exercised. The
> remaining caveat is that the 33 visual queries carry no labels, so the lane is built and populated
> but not *measurable*.

---

## SLIDE 4 — The funnel: where the pages go

Coverage of a query's **reachable labelled pages** (n=133), source `t0_baseline.json`:

| boundary | coverage | Δ |
|---|---|---|
| base (exact 64d MRL) | **0.919** | — |
| cut (full-dim) | **0.838** | −0.081 |
| fusion (product pool ≤100) | **0.684** | −0.154 |
| cross-encoder top-20 | **0.455** | −0.229 |

**SPEAKER NOTES**
> This is the money slide. "We can say exactly how many pages we start with and how many survive each
> stage." The two big losses are the **fusion** and the **cross-encoder**. Everything after this slide
> is: we went after each of those, and here is what moved and what didn't.

---

## SLIDE 5 — Retrieval metrics: complete, per query type

Source `levers_report.md` §2 (`lane_inclusion.json` arm F0). `R-ceil@20` / `P-ceil@20` are the
course's ceilings (W7 §3.3).

| type | n | coverage | R@20 | R-ceil@20 | P@20 | P-ceil@20 | nDCG@20 | MAP | MRR@20 | Hit@20 |
|---|---|---|---|---|---|---|---|---|---|---|
| factual | 53 | 0.588 | 0.588 | 0.949 | 0.129 | 0.300 | 0.592 | 0.475 | 0.781 | 0.906 |
| **overview** | 40 | **0.194** | **0.188** | **0.399** | 0.512 | 1.000 | 0.538 | 0.127 | **0.802** | 1.000 |
| multihop | 40 | 0.581 | 0.550 | 0.956 | 0.105 | 0.214 | 0.507 | 0.376 | 0.729 | 0.900 |
| **all 133** | 133 | 0.468 | 0.456 | 0.786 | 0.237 | 0.485 | **0.550** | 0.341 | **0.772** | 0.932 |

**SPEAKER NOTES**
> Two things to say out loud: (1) **read recall against its ceiling** — overview's raw 0.188 looks ~3×
> worse than factual's 0.588, but against their own ceilings it is 47 % vs 62 %; (2) overview has the
> **lowest recall but the highest MRR** — when it finds a relevant page it ranks it first; it just
> finds few. That shape is the whole overview story. ⚠️ **Precision is ceiling-bound on every type**
> (0.237 of a 0.485 ceiling overall) — say so before it is asked.

---

## SLIDE 5b — Generator metrics: the answer side

Source `data/eval_results/v3_judged_full_2026-11-03_0115.md` — a **cross-family** judge
(`Qwen/Qwen3-VL-8B-Instruct` vs the `gpt-oss-20b` generator). Synthesis **167/200**, **5,057 judge
calls, 0 failed**.

| type | n | Faithfulness | Answer relevance | Cite % | Citation validity |
|---|---|---|---|---|
| factual | 53 | 0.683 | 0.855 | 0.830 | 0.945 |
| multihop | 40 | 0.702 | 0.742 | 0.750 | 0.683 |
| overview | 40 | **0.510** | **0.975** | **0.975** | **0.282** |
| **all 133** | 133 | **0.636** | **0.857** | **0.850** | **0.646** |

**Abstention (negatives): 22/34 = 0.647.**

**SPEAKER NOTES**
> This closes the "generator unmeasured" gap (it was the open item on slide 8). ⚠️ **Citation is TWO
> numbers, and the one we shipped was broken (§I115):** `citation_accuracy` read **1.000 everywhere**
> because its regex matched **no citation in the whole run** (the generator emits `Page`+U+202F and
> `【Page N】`, not `[Page N]`), so its own "no citations — not penalised" rule returned 1.0 for every
> answer. The real picture: **85 % of answers cite a page, and 65 % of the cited pages were
> retrieved.** **Faithfulness is moderate (0.636) and tracks the retrieval weakness** — overview is
> lowest (0.510), the same type with the worst R@20; multihop is highest (0.702). **Answer relevance
> is high everywhere and *inverted* on overview (0.975)**: the system answers overview questions well
> but grounds them least. ⚠️ **Caveat, say it:** a judge score on a single run — no independent
> verifier or mutation proof yet.

---

## SLIDE 5c — Per-type k: does a wider cut help?

Source `per_type_k_sweep.json` (§I105) — the CE arm, mean per type, paired vs k=20. Both §I105 and
§I106 are pre-registered, independently verified and mutation-proved.

| type | R@20 | R@30 | R@40 | R@47 | nDCG@20 | nDCG@47 | ΔnDCG@47 |
|---|---|---|---|---|---|---|---|
| factual | 0.557 | 0.635 | 0.689 | 0.725 | 0.452 | 0.500 | +0.048 |
| **overview** | **0.188** | 0.268 | 0.327 | **0.370** | **0.538** | 0.531 | **−0.007** |
| multihop | 0.550 | 0.564 | 0.590 | 0.605 | 0.508 | 0.527 | +0.019 |

**SPEAKER NOTES**
> This is the "different k per query type" question, answered. **Overview benefits most on RECALL** —
> R@20 0.188 → R@47 0.370, roughly 2× (and 0.768 at k=250 on the wide pool). ⚠️ **But ranked quality
> does NOT rise:** overview nDCG@k is flat (0.538 → 0.531), and in the comparable regime (`k < n_rel`)
> it is a small **RESOLVED HARM** (−0.027 @30, −0.029 @40, −0.041 @100). The one number that looked like
> a gain — *capture* — rose only because the ceiling fell (a denominator artifact). ⇒ **wider k is a
> context-budget knob, not a ranking lever.** ⚠️ **The open reading is the generator**: does the extra
> overview context improve the ANSWER? That is now measurable — the §I108 generator eval ran at k=20.

---

## SLIDE 5d — Where the endpoint loss lives (R@20 decomposed, per type)

Source `order_waste_decomp.json` (§I99) — `oracle` = the best any ranker could do on the pool the
product actually built (an upper bound).

| type | R-ceil@20 | pool-oracle | pool's own order | product | waste_pool | waste_order | waste_ce |
|---|---|---|---|---|---|---|---|
| factual | 0.9557 | 0.8052 | 0.5830 | 0.5574 | 0.1505 | **0.2222** | 0.0256 |
| **overview** | 0.3992 | 0.3755 | 0.2103 | 0.1882 | 0.0236 | **0.1652** | 0.0221 |
| multihop | 1.0000 | 0.6466 | 0.5106 | 0.5500 | 0.3534 | 0.1360 | **−0.0394** |
| **all 133** | 0.8016 | 0.6283 | 0.4491 | 0.4442 | **0.1734** | **0.1791** | **0.0050** |

**SPEAKER NOTES**
> The "where can we improve, or is this the max?" slide. Three losses, separated: the pool **missing**
> gold (`waste_pool`), the pool **ordering** gold badly (`waste_order`), and the reranker (`waste_ce`).
> **`waste_order` is the biggest loss (0.179 overall).** The cross-encoder is worth **0.005 overall** —
> and it **hurts** factual and overview; it only helps multihop. ⇒ **chase the pool's coverage and its
> order, not the reranker.** (§I99, verified 42/42 with a mutation proof.)

---

## SLIDE 5e — The ordering loss: the gold is in the pool, ranked 21–100

Source `fusion_attribution.json` (§I92) — a new read-only attribution (§I111).

| type | cov(pool) | oracle@20 | **FUSED@20** | dense-only@20 | cap-500@20 |
|---|---|---|---|---|---|
| factual | 0.811 | 0.8052 | **0.5830** | 0.5291 | 0.5922 |
| **overview** | 0.508 | 0.3755 | **0.2103** | 0.2128 | 0.2078 |
| multihop | 0.647 | 0.6466 | **0.5106** | 0.5058 | 0.5227 |
| **all 133** | 0.671 | 0.6283 | **0.4491** | 0.4270 | 0.4557 |

**SPEAKER NOTES**
> The attribution that says **where to aim**. **39.5 % of the gold the pool holds lands in the top-20;
> 60.5 % sits at ranks 21–100.** The **fusion is NOT the culprit** — the fused order ≈ dense-only
> (Δ +0.0222 overall, unresolved), and widening the cap does not reorder it (cap-500 ≈ fused). ⇒ **the
> gold is ranked low by the lanes themselves: the fix is the retrieval signal, not the fusion.**
> ⚠️ And the honest ceiling: **`R-ceil@20 = 20 × mean(1/n_rel) = 0.3992` for overview** — a broad label
> set (median 56.5 pages), so **no retriever can beat ~0.35 there**. That last line is the answer to "is
> this the max?" — for overview the ceiling is set by the labels, not by the system.

> **§I112 (the query-side lever):** a different query **representation** does NOT help — multi-hypothetical
> **max / mean** (N=5) leave overview R@20 **UNRESOLVED** vs the shipped single HyDE hypothetical
> (C−A +0.0021, D−A +0.0012; the raw-query control is RESOLVED NEGATIVE). ⇒ the signal lever left is the
> **DOCUMENT side** (embedder / re-ingest), not the query side.

---

## SLIDE 6 — The levers ledger: what moved, what didn't

The credibility slide. Source: `IMPROVEMENTS.md` §I67–§I109.

**Moved:**
* Per-type rerank-query policy (raw question for factual, hypothetical for overview): endpoint nDCG@20
  **0.4946 → 0.5503** — the largest measured lever, zero recall cost.

**Measured and did NOT move (each a pre-registered run):**
| lever | verdict |
|---|---|
| fusion width (§I67), cap (§I92), MMR (§I92) | inert at the endpoint |
| fusion **order** — MMR off / no ColBERT / dense-only / reweighted (§I100) | null or harm |
| score-based fusion vs rank RRF (§I103) | null overall; **harm on multihop** |
| RAPTOR / DA / graph lanes into the pool (§I98) | RAPTOR is a **resolved harm on overview** |
| **wider k**, cap 100 → 500, k → 250 (§I105/§I106) | recall/coverage only; **ranked quality resolved-negative** for overview |

**⚠️ Newly closed / flagged (2026-11-02):**
| item | verdict |
|---|---|
| generator stage (§I108) | **measured** — faithfulness 0.636, answer relevance 0.857; citation was **broken and is fixed** (§I115): 85 % of answers cite, 65 % of cited pages retrieved |
| visual / ColPali lane (§I107) | the raw cosine **cannot separate** in-domain from near-domain; no usable gate |
| T3 lane-complete A/B (§I109) | **ran but FLAGGED** — anchor guard G8 failed (diagnosed: stale anchor); verdict needs an owner decision |

**SPEAKER NOTES**
> This is where the project separates itself from "I built a RAG app." Each row is a pre-registered
> experiment with an independent verifier and a mutation proof — and most came back **negative**.
> Say plainly: "the negative results are the contribution; they're what stops us chasing dead ends."

---

## SLIDE 7 — Why this is a capstone, not a side project: the method

* Every run is **pre-registered** (arms, metrics, predictions, a falsification clause) and the
  pre-registration is committed **alone, before** the run.
* Every result has an **independent verifier** (stdlib, re-derives every cell from the raw data) and a
  **mutation proof** (mutate the artifact; every check must go red; **no inert checks**).
* A **decision log** (`DECISIONS.md`) records every fork, why, and why not the alternatives.
* Suite: **736 passed / 4 failed / 6 skipped** — the 4 are a documented pre-existing set.

**SPEAKER NOTES**
> This is the slide that justifies the effort. The punchline: "when I say a lever is a dead end, I can
> show you the pre-registration, the artifact, the verifier and the mutation proof." Offer to walk
> through one (the wider-k result is the freshest).

---

## SLIDE 8 — What is measured, and what is NOT (say this before you're asked)

**Measured:** retrieval quality, per type, at every funnel boundary; every major lever; determinism;
**and the generator** (faithfulness, answer relevance, citation coverage + validity, abstention — §I108/§I115).
**NOT measured / open:**
* ✅ the **generator stage** is now **MEASURED** (2026-11-02): faithfulness 0.636, answer relevance 0.857,
  citation 85 % cite / 65 % of cited pages retrieved (§I115 — the shipped 1.000 was a regex artefact),
  abstention 22/34. ⚠️ Caveat: a judge score on a single run — no verifier yet.
* the **visual / ColPali lane** — HAS data for the current document (968 vectors, written 2026-11-02);
  the remaining gap is that the 33 visual queries carry no labels, so it is not *measurable*. §I107
  found the raw cosine **cannot separate** in-domain from near-domain, so it is also **not gateable**.
* **T3** (the lane-complete v2-vs-v3 A/B) **ran but is FLAGGED** — its anchor guard G8 failed and was
  diagnosed as a **stale anchor** (§I109); its verdict needs an owner decision before it is read.
* multi-tenant behaviour — deliberately deferred (single-user scope).

**SPEAKER NOTES**
> Lead with the honesty. A mentor will find the gaps anyway; naming them first is the strong move. The
> generator gap is the honest answer to "how much is left" for a *product* (finish line B) — but not
> for a *capstone* (finish line A).

---

## SLIDE 9 — Where we stand / how much is left (finish line A)

* **Done:** ingestion (3 phases), the eval harness, the retrieval programme, the levers ledger, and
  (2026-11-02) the **generator measurement**. The endpoint's ranking loss is **closed** (nDCG@20 0.5503
  vs the pool's own 0.5506).
* **Left for the capstone (weeks):**
  1. **T3** — the lane-complete v2-vs-v3 A/B: it **ran but is FLAGGED** (anchor guard G8 failed, diagnosed
     as a stale anchor, §I109) — resolve the anchor, then read whether the embedder or the ingestion
     moved reachability.
  2. The **pool → top-20 ranking attribution** — the remaining measured lever.
  3. The **write-up** (Medium/Substack) + this demo.
* **Optional / stretch (finish line B):** polish the UI; multi-tenant.

**SPEAKER NOTES**
> "For a defensible capstone, I am weeks away, not months." Be precise: the *retrieval* research is
> essentially complete; what remains is one controlled comparison, one attribution, and the write-up.

---

## SLIDE 10 — The plan to the finish line

1. **T3** — the v2-vs-v3 lane-complete A/B (pre-register → run → verify).
2. **The pool → top-20 attribution** — the last unmeasured retrieval lever.
3. **The generator measurement** (stretch) — turns "measured retriever" into "measured learning system".
4. **The write-up** — the Medium/Substack piece + the portfolio framing.

**SPEAKER NOTES**
> Keep it to four bullets. The order matters: T3 first (it's unblocked and it decides a fork), then the
> attribution, then — if time — the generator.

---

## SLIDE 11 — Live demo (2 queries)

* **Factual:** "What is Newton's second law?" → answer + cited pages (~66 s).
* **Overview (the hard type):** "How does Feynman develop conservation of energy across mechanics,
  waves and thermodynamics?" → a synthesized answer citing pages 251 / 94 / 316 / 921 (~96 s).

**SPEAKER NOTES**
> The overview answer is the surprise: the retrieval *metric* for overview is our weakest, yet the
> *answer* reads well. Say that out loud — it is exactly the "generator unmeasured" point on slide 8,
> and it is an honest, interesting tension rather than a hidden weakness. Have the app already running
> on port 8503; do not start it live.

---

## SLIDE 12 — Close / asks

* What I'd like from you: a read on **finish line A vs B** (is the capstone defensible as retrieval-only
  + demo, or does it need the generator measured?).
* And: any steer on the **write-up** angle for the industry re-entry.

**SPEAKER NOTES**
> End with a specific ask. The mentor's value here is judgment on scope, not code review.

---

## APPENDIX — Architecture diagrams

The full ingestion + retrieval architecture, **verified against the code**. Rendered as the last two
pages/slides of this deck: `demo_deck.pdf` p14–15, `demo_deck.pptx` slides 14–15.

**Source of truth:** `Docs/synapse_architecture_v2.html` (+ `.pdf`). **Verified by**
`logs/p1/step10/arch_v2_verifier.py` (**48/48 checks** — every claim re-derived from `config.py` /
`store.py` / `evaluate_rag.py` / the live Qdrant) and an **independent cross-family reviewer**
(`gpt-oss-20b`, read-only): **11/12 claims confirmed**. ⚠️ The 12th — the generator model — was
**refuted against `config.py`'s DEFAULT** (`meta-llama/Llama-3.2-8B-Instruct`); the refutation is
**invalid**: `.env` overrides it and the *resolved* `openai_model` is `openai/gpt-oss-20b`.

* **Diagram 1 — Ingestion (Phases 1·2·3):** PDF → Docling → Chonkie (512 tok / 64 overlap) → Nomic MRL
  (`dense_64` + `dense_full` 768) + ColBERT + SPLADE → `knowledge_base_v3` (3,869 pts) + SQLite;
  Phase 2 cards (8 types, gpt-oss-20b) → `derivative_artifacts` (73,406) + RAPTOR (3 levels) → KB
  summary nodes; Phase 3 ColPali → `visual_knowledge_base` (2,001) + Memgraph + `concept_embeddings` (6,065).
* **Diagram 2 — Retrieval:** embed → intent router → HyDE (+ per-type rerank policy) → Qdrant nested
  prefetch (`dense_64`→`dense_full`→ColBERT) + SPLADE → **client-side RRF** (`_rrf_merge`, rrf_k=1, §I68) →
  DA lane (appended **before** dedup/MMR) → page dedup → MMR (λ=0.7) → RAPTOR / Graph lanes →
  cross-encoder (100→20) → `gpt-oss-20b` synthesis with `[Page N]` citations.

**Rebuild all deck artifacts from one command:** `bash logs/p1/step10/build_deck.sh`.
