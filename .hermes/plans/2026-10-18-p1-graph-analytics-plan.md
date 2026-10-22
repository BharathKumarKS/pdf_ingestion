# P1 §G — the graph analytics layer (PPR, entity resolution, community detection). Execution plan.

> **Written 2026-10-18. FOR SIGNOFF — nothing here is implemented, and no graph code has changed.**
> Read `IMPROVEMENTS.md` §G (the register this executes), §I2 (the measured defect it starts with),
> §I21/§I22 (found while planning this) and `HANDOFF.md` (P2 list). This file is the *procedure*.

---

## ⛔ SETTLED 2026-10-22 — this file's §2 and §3 are superseded. THE BLOCK BELOW WINS ON CONFLICT.

Three decisions have moved since this plan was written. Do not act on the older text.

1. **§2's "No new dependency is needed … `leiden_communities` present in networkx 3.6.1" is FALSE**
   (§I33). networkx's `leiden_communities` is a backend-dispatch stub that raises
   `NotImplementedError`. **Owner decision 2026-10-21: take the dependency** —
   `uv add python-igraph leidenalg` (*"as that's the improvement over louvain"*).
2. **The graph §G3 and §G2 run on has been REBUILT** (2026-10-21): 3,533 chunks / **7,427 concepts**
   (not 3,796 / 7,834), `failed_chunks = 0`, §I21's filter live. Every count in §1 and §3 of this file
   is a **before-arm** and must be re-measured, not inherited.
3. **§G3 now runs AFTER the §I12 Lane B rebuild**, and its scope **includes syncing
   `concept_embeddings`** to the merged node set (a merge that leaves the ANN index holding deleted
   names re-creates §G1's measured confound).

**The current procedure for each phase lives in the dated plans, which supersede the matching phase
section below:**

| Phase | Current plan (use this) |
|---|---|
| §I12 Lane B — the rebuild §G3 runs on | `.hermes/plans/2026-10-22-p1-i12-derived-collections-dense-lane-plan.md` |
| §G3 — entity resolution | `.hermes/plans/2026-10-22-p1-g3-entity-resolution-plan.md` |
| §G2 — community detection + summaries | `.hermes/plans/2026-10-22-p1-g2-community-summaries-plan.md` |
| §G1 — PPR | **CLOSED 2026-10-21, measured-and-negative.** Not in this file's §"Phase G1" any more |

This file remains the record of *why* the order is G3 → G1 → G2 → G5 → G4 and the syllabus citations.
>
> **Why now:** the owner asked whether Step 10's graph rebuild follows the course's Memgraph approach
> by community detection. It does not, and never did (§G is separate work). This is that work, planned
> properly so it is a decision rather than an improvisation.

---

## 0. What is being built, and in what order

`IMPROVEMENTS.md` §G registers five items. The order below is **not** the §G list order — it is the
order the evidence supports:

| Order | §G item | Why this position |
|---|---|---|
| **1** | **G3 — entity resolution** | §G calls it *"the known bug"*; §I2: *"Deduplicating concept names is the bigger lever than ranking."* The course: *"resolve poorly and the graph fragments, and every downstream step inherits the fracture."* Everything below depends on a clean node set. |
| **2** | **G1 — PPR** | §G1: *"the course's answer to 'which concepts actually matter for this query'. Replaces the current fixed-hop walk."* Already on the HANDOFF P2 list. Needs the adjacency, not the communities. |
| **3** | **G2 — community detection + summaries** | **Gated** on the course's own modularity test (§3 below). This is the expensive one and the one the course warns about at small corpus size. |
| **4** | **G5 — genuine multi-hop** | §I2: `hop_distance` is a constant 0, so "multihop" is nominal. Cheap once G1/G3 land. |
| **5** | **G4 — global/local/drift query modes** | §G4 is marked "to brainstorm". Not a build item yet. |

**Everything here runs on the graph the current Step 10 Phase A build produces.** That build is the
substrate: `Concept` nodes as entities, `RELATES_TO` with an accumulated `weight` as the
frequency-weighted adjacency, and `(Chunk)-[:MENTIONS]->(Concept)` as the provenance back to passages.

---

## 1. What exists today (measured, not assumed)

**The graph** (doc `6d55c52b`; the new document's build is in flight): 5,051 `Chunk` nodes, 7,815
distinct `Concept` nodes, 757 `Page` nodes, **75,845 edges** — of which `PART_OF` + `ON_PAGE` are
2 × chunks and the rest are `MENTIONS` + `RELATES_TO` (weighted) + `PREREQUISITE_OF`.

**The query path this replaces** — `GraphBuilder.graph_search` ranks by distinct concepts matched,
then concept similarity. §I2: `hop_distance` is the **constant 0**. So there is no traversal to
replace; there is a fixed-hop walk that does not hop.

**The defect that makes G3 first** — near-duplicate concept nodes: `'orbit'` / `'Orbit'` /
`'planetary orbit'` / `"Earth's orbit"` are separate nodes, so most chunks tie at 1 matched concept.
That is why the current ranking cannot discriminate.

---

## 2. Dependency reality — checked, and the news is good

I checked rather than assuming. **No new dependency is needed for either G1 or G2:**

| Capability | Where | State |
|---|---|---|
| **Leiden** | `networkx.algorithms.community.leiden_communities(G, weight='weight', resolution=1, max_level=None, seed=None)` | ✅ **present in the installed networkx 3.6.1** |
| Louvain (for comparison) | `louvain_communities` | ✅ present |
| **Modularity Q** (the course's objective) | `modularity(G, communities, weight='weight', resolution=1)` | ✅ present |
| Partition quality | `partition_quality` | ✅ present |
| **PPR** | `nxalg.pagerank(alpha, personalization, max_iter, tol, nstart, weight, dangling)` **inside Memgraph** | ✅ present — 108 procedures exposed |
| PPR (Python fallback) | `networkx.pagerank(..., personalization=...)` | ✅ present |
| `leidenalg` / `igraph` / `python-louvain` | — | ❌ **absent — and not required** |

Two consequences:
- `nxalg.pagerank` already defaults to `weight="weight"`, which is exactly the property our
  `RELATES_TO` edges carry. PPR can be computed **in-graph** without exporting the graph.
- ⚠️ `nxalg.pagerank`'s `personalization` parameter is typed `STRING?` — what it expects (a property
  name, a serialised map, a query) is **not documented in the signature**. This needs a probe before
  the plan is committed to the in-graph route; the Python fallback is always available.
- ⚠️ The course says *"Run Leiden (leidenalg)"*. networkx's `leiden_communities` implements the same
  algorithm (Traag et al.'s refinement phase included), in pure Python. On ~7,800 nodes / ~76k edges
  that should be fine; if it is slow, `leidenalg` + `igraph` can be added. **Flagged as a decision,
  not assumed away.**

---

## 3. The corpus-size gate — the course's own test, run BEFORE building G2

The course is explicit that community detection has a size floor and is a sidecar
(`Week_Plan/week-5-…`):

> *"Emergence needs mass. Run Leiden on the entity graph of a three-page essay — fifteen entities,
> twenty edges — you get three tiny 'communities' whose summaries paraphrase the essay, at LLM prices.
> **You cannot detect ocean currents in a bathtub.**"*
> *"GraphRAG, in any variant, is always a sidecar — it extends the motorcycle; it never replaces it."*
> *"Extraction is an LLM call per chunk; community detection is cheap by comparison but not free; and
> then you owe leaf summaries, merged summaries, summaries of summaries — LLM calls all the way up."*

Our corpus is **one book** — 7,815 concepts and 75,845 edges, which is neither a bathtub nor an ocean.
So the course's own method decides it, and it is cheap:

**G2 entry gate (pre-registered here, before running):** compute modularity `Q` of the Leiden
partition and compare it against **a degree-preserving random rewiring of the same graph** — the
course's Lab 2 procedure, verbatim (*"structure is a surplus over chance, so compute the chance"*).

- **If Q is not meaningfully above the rewired null → G2 is NOT built.** The communities are
  salt-and-pepper (the course's Figure 1 case: *"the best achievable modularity, Q ≈ 0.32, is close to
  what sparse randomness alone can fake"*), and summarizing them manufactures confident garbage. That
  is a **result**, recorded as such.
- **If Q is clearly above the null → G2 proceeds**, at 2–4 levels (*"Microsoft GraphRAG's hierarchy is
  typically 2–4 levels deep precisely because that is how many levels of genuine structure a real
  entity graph holds. Ask for more and you are summarizing noise"*).

This gate is why G2 is last: it may not survive contact with the data, and running it first would spend
LLM budget before the question is asked.

---

## Phase G3 — entity resolution (do this first)

**What:** collapse near-duplicate `Concept` nodes to one canonical node each, re-pointing `MENTIONS`
and `RELATES_TO`, and preserving the aliases.

**Approach (post-hoc mutation, not a re-extraction).** `build_graph`'s 3,796 LLM calls are the
expensive part and are **not** repeated: the extraction output (which concepts each chunk mentions) is
unchanged by merging names. This is also what the course's Lab 1 does — *"find at least three
entity-resolution failures ('FDA' versus 'the FDA') and measure how merging them changes the hub list"*.

- **Candidate signal:** the `Concept.embedding` already stored on every node (768d), plus name
  normalisation (case, singular/plural, leading articles, parentheticals). The course names **"the
  FDA" vs "FDA"** as the canonical example, which is pure normalisation, not embedding work.
- **Deliberately conservative:** merging two genuinely distinct concepts is worse than leaving a
  duplicate. Every merge must be reversible and logged.

**Verifier:**
1. distinct `Concept` count **falls** and no concept name is lost — every merged name survives as an
   alias on the survivor;
2. `MENTIONS` + `RELATES_TO` edge counts are **conserved modulo the merges** (no edges silently
   dropped) — assert the delta equals the number of collapsed edges;
3. ⚠️ **REWRITTEN 2026-10-20 (§I29) — the check as originally written measures the WRONG quantity and
   cannot discriminate. Do not use the old wording.** It said *"the share of chunks matching ≥2 distinct
   concepts rises … currently most chunks tie at 1"*. That fuses two quantities. Measured: a chunk
   mentions **4.25** distinct concepts on average and **96.9 %** of concept-bearing chunks mention ≥2
   (`logs/p1/step10/probe_g3_baseline.json`) — so read per-chunk, the metric starts at 0.9687 and has
   **3.1 points of headroom**; a bad merge would look like a success. §I2's *"ties at 1"* is **query-side**:
   `graph_search` (`graph_builder.py:449-459`) scores a chunk by how many of the **query's** `top_k=8`
   concepts it mentions. **The check must therefore be:**
   (a) **report** the per-chunk distribution (context, not an assertion — it is already saturated);
   (b) **assert on the query-side distribution**: for a sample of gold queries, the number of chunks
       scoring `matched_concepts ≥ 2` must **rise**, and the median `matched_concepts` of the retrieved
       top-k must rise. Needs a 768d query embedding against `Concept.embedding` (§I12), so it is a
       cluster-embed probe — measure it **before** the merge as the baseline arm, or there is nothing to
       compare against;
   (c) **report the measured lever** from §I30 as the sanity anchor: 1,186 groups, 2,692 concepts
       (34.4 %), and the top groups' chunk gains (`force` 95 → 175, `kinetic energy` 51 → 102). A merge
       that does not reproduce those unions has not merged what it thinks it merged;
   (d) **assert on the two traps** (§I31): no merge may join a group member that is a formula rather than
       a spelling variant, and no merge may be substring-derived. Both are silent — the counts improve
       while the graph degrades.
4. **spot-read ~10 merges by eye** and record them (the course's *"read the artifacts"* rule) — a merge
   that joins `'entropy'` to `'enthalpy'` is a defect even though the counts improve.

---

## Phase G1 — PPR over the concept adjacency

**What:** replace the fixed-hop walk with personalized PageRank, seeded by the query's concepts —
§G1's *"which concepts actually matter for this query"*.

**Two candidate implementations, to be decided by the probe in §2:**
- **in-graph** `CALL nxalg.pagerank(alpha, personalization, weight='weight')` — no export, but the
  `personalization` parameter's expected form is unknown;
- **Python** `networkx.pagerank(G, personalization={node: weight})` over the `RELATES_TO` subgraph.

**Verifier:**
1. the probe settles which route works, and the plan records why the other was rejected;
2. PPR scores are **not** uniform: report the score distribution and the top-20 concepts for a sample
   of queries, and check they are on-topic **by eye**;
3. **hub suppression matters** — the course: *"expand two hops from 'USA' and you have retrieved the
   encyclopedia"*. Measure the top-ranked concepts' degrees; a PPR top-20 dominated by the highest-degree
   nodes means the personalization is not doing its job;
4. **the ablation** (the course's rule, *"every index must earn its place through ablation"*): the graph
   lane's contribution to multihop retrieval, PPR vs the current fixed-hop ranking, on the v2 gold set.
   **No claim without this.**

---

## Phase G2 — community detection + community summaries (gated by §3)

Only if the modularity gate passes.

- **Detect:** `leiden_communities(G, weight='weight', resolution=r, max_level=k)` at 2–4 levels, over
  the **deduplicated** graph from G3.
- **Summarize:** one LLM summary per leaf community, merged upward (*"write a narrative summary of each
  leaf community … then merge leaf summaries into parent-community summaries"*), stored as a new
  derivative artifact. Note `Chunk.chunk_text` is truncated to **500 chars** in the graph, so
  summarization must join back to SQLite/Qdrant for full passages.
- **Retrieve:** map–reduce at query time, for the **global sensemaking query** only. The course is
  blunt that this is the wrong instrument elsewhere: *"Routing a point query through community
  summaries … is using a telescope to read your own wristwatch — slower, costlier, and often worse."*

**Verifier:**
1. the modularity-vs-rewired-null gate from §3, recorded with both numbers;
2. **communities are well-connected** — Leiden's whole point vs Louvain (*"it can output 'communities'
   that are internally disconnected"*). Assert every community is connected;
3. **topical coherence by eye** — the course's *"phantom cluster"* warning: *"an accidental clump that
   passes every per-chunk provenance check, is a provenance failure that only a topical-coherence check
   catches."* Read a sample of communities and their summaries;
4. **cost ledger kept open** — count every LLM call (*"you are re-deriving the Karamazov invoice"*);
5. **the ablation** on overview/sensemaking queries vs the RAPTOR-only lane it would supplement.

---

## Phase G5 — genuine multi-hop

Fix `hop_distance` (constant 0) so a traversal actually traverses, and report real hop counts.
**Verifier:** hop distances are **not** constant; a query requiring two hops retrieves a page neither
one-hop endpoint reaches; the ablation again.

---

## Register, at the end of each phase

§G3 / §G1 / §G2 / §G5 each closed with its measured evidence; §I2 closed by G3+G5; §I21 (the Phase 3
graph build ignoring the E5 content filter — **this is a prerequisite for good communities**, since
TOC concepts are exactly the noise that fragments them) decided; §I22 (the mislabelled
`concept_nodes`) fixed report-side.

---

## Explicitly NOT in this step

- **Any code change until this plan is signed off.** Nothing has been implemented.
- **Changing the concept-extraction prompt.** It would invalidate the current build's 3,796 LLM calls,
  and there is no extraction cache. G3 is designed as a post-hoc merge to avoid exactly that.
- **G4** (global/local/drift query modes) — brainstorm stage.
- **`concept_embeddings` → 1024d** (§I12) — the graph lane stays on the legacy 768d lane for now.
- **Step 10 §2** — unchanged, and it resumes as soon as Phase A's build passes its verifier.
