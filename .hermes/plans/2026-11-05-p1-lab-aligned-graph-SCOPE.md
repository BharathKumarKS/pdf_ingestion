# §I120 — Lab-aligned graph implementation: SCOPE (2026-11-05)

> **STATUS: SCOPED, NOT PLANNED.** Per the owner (2026-11-05): *"scope the lab-aligned graph
> implementation… plan it in the next session **after** the guardrails plan and implementation."*
> So this file is the **input to that plan**, not the plan. Do not start it before the guardrails
> workstream is done.

## Why this exists

§I120 measured that **we implement the lab's PPR *iteration* but not its *substrate***. Our
`personalized_pagerank` is the MemGraphRAG iteration verbatim, but we run it over a **dense, untyped
co-occurrence graph** (`RELATES_TO`, weight = co-mention count) with a **single** reset over seed
concepts, hub suppression only *reported*, and PPR as a **re-ranker**. §G1's null is therefore
evidence about *PPR re-ranking over a co-occurrence graph* — **not** about the lab's method.

**⇒ The fair test of MemGraphRAG's method needs its substrate built first.** This scope lists what
that is. ⚠️ It is a **capability build, not a metric win**: §I98 already measured the graph lane as a
content *harm* at the endpoint, so the deliverable is a defensible PPR test, not a promised gain.

## The reference

- Lab: `Labs/Week_5/week5.2/memgraphrag_concepts` (module `src/memg_concepts/`).
- Paper: **arXiv:2606.00610**; ref impl `XMUDeepLIT/MemGraphRAG`. PDFs in `Research Papers/`.
- Lab modules to mirror: `memory.py` (three-layer), `extraction.py`, `graph_builder.py`,
  `adjacency.py`, `pagerank.py`, `retrieval.py`.

## What the lab has that we lack

| # | Lab component | Ours today |
|---|---|---|
| 1 | **Three-layer memory**: Schema / Fact / Passage (`memory.py`) | Concept names + prerequisites only |
| 2 | **Typed triples**: `(head_type, relation, tail_type)` + `(head_entity, relation, tail_entity)` | LLM concept names; `RELATES_TO` = **co-occurrence** |
| 3 | **Heterogeneous graph**: `PASSAGE, SCHEMA, TYPE, ENTITY`; `instance_of`, `evidence` (w=0.8), `similarity` (cos ≥ 0.82) | `Document/Page/Chunk/Concept`; `MENTIONS`, co-occurrence `RELATES_TO` |
| 4 | **Per-layer reset vectors** `P_init(p)/P_init(e)/P_init(t)` | one reset over seed concepts |
| 5 | **Applied hub suppression** `1/log(deg+1)` in `P_init(e)/P_init(t)` | only *reported* (`hub_suppression_report`) |
| 6 | **PPR as retrieval** (ranks all nodes → passages), to convergence | PPR as a **re-ranker** over one lane's candidates |

## What we would build (draft — the plan will order and pre-register these)

1. **Typed extraction** — an LLM prompt/schema producing schema+fact triples (not just concept
   names). Decide: extend `_extract_concepts` vs a new extractor.
2. **Three-layer memory** — port/mirror `GlobalMemory` (schema frequency, `stable_schemas`,
   `active_facts`, conflict detect/resolve).
3. **Graph substrate** — extend the Memgraph schema with `Schema/Type/Entity` nodes and typed edges,
   **or** build a parallel in-memory indexing graph (the lab's is in-process). ⚠️ Single-writer on
   Memgraph; coordinate with the existing `Concept`/`Chunk` graph.
4. **Adjacency / transition matrices** + **per-layer reset vectors** with hub suppression.
5. **PPR retrieval lane** — rank nodes → passages (a new arm), not the re-ranker.
6. **Pre-registered ablation** — the lab-style PPR arm vs the shipped graph lane, at the endpoint.
   ⚠️ The page-level instrument must be checked for *bite* first (§I120's flood finding: our
   co-occurrence pool is 15 pages shipped, 296/802 expanded — the instrument, not the treatment, was
   the problem in §G1).

## Cost / risks to state in the plan

- **LLM-heavy extraction** over the corpus → a full re-extract (the lab uses `gpt-oss-20b`).
- **A new graph schema** — the existing `Concept` graph is the §G3-merged one (6,065 concepts);
  decide merge vs parallel.
- **Corpus**: the lab demos on `attention.pdf`; ours is the Feynman text (~906 content pages).
- **No metric expectation** — §I98 (lane = harm) and §I100 (lanes ≈ 0 endpoint) bound any claim.
- **Cluster**: the retrieval ablation needs sparse + rerank (down as of 2026-11-05); the *build* does
  not.

## Ordering (owner, 2026-11-05)

1. **Guardrails plan + implementation** (input + output) — next.
2. **This plan** — the session after.
