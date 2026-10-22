# P1 §G2 — community detection + community summaries. Execution plan.

> **Written 2026-10-22. FOR SIGNOFF — nothing implemented.** Executes `IMPROVEMENTS.md` §G2.
> Read the §G plan §3 (the corpus-size gate), §I33 (the Louvain/Leiden decision), §I21/§I39
> (the noise that fragments communities), and `HANDOFF.md`.
>
> **Sequencing:** runs **after §G3** (community structure is computed on the *merged* node set) and
> after the §I12 Lane B rebuild. This is the expensive phase — it spends LLM budget — which is why
> the course's own gate is re-run first (§2) rather than assumed.

---

## 0. SETTLED — supersedes these earlier statements

| Earlier statement (where) | Superseded by |
|---|---|
| `2026-10-18-p1-graph-analytics-plan.md` §2: *"**No new dependency is needed** … `leiden_communities` present in networkx 3.6.1"* | **FALSE — corrected by §I33.** networkx's `leiden_communities` is a **backend-dispatch stub that raises `NotImplementedError`**. Owner decision 2026-10-21: **take the dependency** — `uv add python-igraph leidenalg` (*"as that's the improvement over louvain"*). |
| §G2 before-arm: *"Q 0.589597 vs rewired null 0.280330 → PASS"* (Louvain) | **Superseded — re-run on Leiden**, and **on the rebuilt graph**. Measured 2026-10-21 on the OLD graph: **Leiden Q=0.601572 vs null 0.286665, surplus +0.314907 (ratio 2.0985)**, Louvain arm reproduces 0.589597 exactly, Louvain is **disconnected** at 1.0 and 2.0. Both are **before-arms** (pre-rebuild, pre-G3). |
| §G plan §2: *"if it is slow, `leidenalg` + `igraph` can be added. Flagged as a decision"* | **Decided.** The dependency is taken; networkx Leiden is not runnable. |

---

## 1. What this builds, and the course's own warning

Community detection over the concept graph, plus one LLM summary per leaf community merged upward
(*"write a narrative summary of each leaf community … then merge leaf summaries into
parent-community summaries"*), stored as a new derivative artifact, retrieved by map-reduce **for the
global-sensemaking query only**.

The course is explicit that this is a **sidecar** with a **size floor**:

> *"Emergence needs mass. Run Leiden on the entity graph of a three-page essay … you get three tiny
> 'communities' whose summaries paraphrase the essay, at LLM prices. **You cannot detect ocean
> currents in a bathtub.**"*
> *"GraphRAG, in any variant, is always a sidecar — it extends the motorcycle; it never replaces it."*
> *"Routing a point query through community summaries … is using a telescope to read your own
> wristwatch — slower, costlier, and often worse."*

One book (7,427 concepts) is neither a bathtub nor an ocean, so the **gate decides it** — and the
gate is cheap, so it runs before any summary budget is spent.

---

## 2. Step G2-0 — re-run the modularity gate on the rebuilt, G3-merged graph (GATES EVERYTHING)

Pre-registered here, before running: compute modularity `Q` of the Leiden partition and compare it
against **a degree-preserving random rewiring of the same graph** — the course's Lab 2 procedure
(*"structure is a surplus over chance, so compute the chance"*).

    uv run python logs/p1/step10/g2_leiden_gate.py     # re-pointed at the rebuilt+merged graph

**Report both numbers at every resolution.** The decision rule, fixed now:

- **Q not meaningfully above the rewired null → G2 is NOT built.** The communities are
  salt-and-pepper; summarizing them manufactures confident garbage. That is a **recorded result**, not
  a failure.
- **Q clearly above the null → G2 proceeds**, at **2–4 levels** (*"Microsoft GraphRAG's hierarchy is
  typically 2–4 levels deep precisely because that is how many levels of genuine structure a real
  entity graph holds. Ask for more and you are summarizing noise"*).

**Required parameters (from the syllabus spec, per `HANDOFF.md`):**
- resolutions **0.5, 1.0, 2.0**;
- **assert every community is connected** — Leiden's guarantee over Louvain, and the reason the owner
  chose it;
- report the **hierarchy nesting** across levels (measured 0.87 for 0.5→1.0 and 0.74 for 1.0→2.0 on
  the old graph — re-measure).

⚠️ **Re-measure, do not inherit.** Every number in §0's second row is a **before-arm** taken on the
pre-rebuild, pre-merge graph. G3 changes the node set; the rebuild changed it too.

---

## 3. Verifiers (each must be able to FAIL)

| # | Check | Why it discriminates |
|---|---|---|
| **V1** | the modularity-vs-rewired-null gate (§2), **both numbers recorded at every resolution** | A gate quoted without its null is not a gate |
| **V2** | **every community is connected** (Leiden's guarantee) | Louvain failed this on the old graph (a 75-member disconnected community, §I33). A "community" that is internally disconnected is the exact defect Leiden exists to prevent |
| **V3** | **topical coherence by eye** — read a sample of communities and their summaries (the course's *"phantom cluster"* warning) | A provenance check passes a phantom cluster; only a topical read catches it |
| **V4** | **cost ledger kept open** — count every LLM call (*"you are re-deriving the Karamazov invoice"*) | The summary tree is LLM calls all the way up; an uncounted cost is how this phase overruns |
| **V5** | **the ablation** — overview/sensemaking queries, community summaries vs the RAPTOR-only lane they supplement | The course's rule: *"every index must earn its place through ablation."* No claim without this |
| **V6** | **summarization joins back to full passages** — `Chunk.chunk_text` is truncated to **500 chars** in the graph, so leaf summaries must read full text from SQLite/Qdrant, not the graph's truncated copy | A summary built on 500-char stubs is a summary of stubs |

**V5 is the endpoint.** V2 is the structural guarantee the owner chose Leiden for.

---

## 4. Pre-registered outcome rule

- **G2 is built** iff V1's gate passes **and** V2 holds (all communities connected) **and** V5's
  ablation shows a positive contribution on overview queries. If V5 is null or negative, **G2 is
  recorded as measured-and-negative** and the summaries are not wired into retrieval — the same
  disposition §G1 received.
- A null V5 is a **result**, not an unresolved one: the summary budget is not re-spent to chase it.
- The cost ledger (V4) is reported **beside** the ablation, so a positive V5 is read against what it
  cost.

---

## 5. Parallelization

- **G2-0 (the gate)** is read-only, LLM-free, and safe to run alongside anything — including §I12
  Lane A and the §G3 lever re-measure.
- **Detection** (Leiden over igraph) is CPU-bound and local; it may run in parallel with cluster work.
- **Summarization** spends cluster LLM budget and is the one phase that must be **serialized against
  other cluster-LLM work** (e.g. a card re-run) — §I23 measured that shared-GPU contention collapsed
  a build's throughput ~8×. Do not run it beside another LLM-heavy phase.
- **V5's ablation** needs the summaries landed; it is the last step and is serial by construction.

---

## 6. Register, at the end

- **§G2 closed** with V1–V6 evidence; the modularity numbers recorded with their null at every resolution.
- **§I33 closed** (Leiden taken, Louvain comparison recorded, disconnectedness demonstrated).
- **§I21/§I39** confirmed as the prerequisite they were argued to be: compare community fragmentation
  before (TOC-noise graph) and after (filtered rebuild) — the rebuild's whole purpose was to stop TOC
  concepts fragmenting communities.
- Update `HANDOFF.md`: §G2 done; the remaining §G item is **§G5** (genuine multi-hop; `hop_distance`
  is a constant 0), and **§G4** (global/local/drift modes) stays a brainstorm item.

---

## 7. Explicitly NOT in this plan

- **No building before the gate passes.** §2 gates everything.
- **No point queries routed through community summaries** — the course is blunt that this is the wrong
  instrument; summaries serve the **global sensemaking query only**.
- **No summaries built on the graph's truncated 500-char chunk text** (V6).
- **No §G4** (global/local/drift query modes) — brainstorm stage, not a build item.
- **No §G5** — separate item, cheap once G1/G3 landed; §G1 is closed (measured-and-negative).
