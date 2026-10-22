# P1 §G3 — entity resolution on the rebuilt graph. Execution plan.

> **Written 2026-10-22. FOR SIGNOFF — nothing implemented.** Executes `IMPROVEMENTS.md` §G3.
> Read §I2 (the defect), §I29, §I30, §I31 (the measured lever and its four traps), and
> `HANDOFF.md` (D1: *the gate that releases §G3 is the rebuild landing* — **it has landed**).
>
> **Prerequisite, and it is met:** the §I21 graph rebuild finished 2026-10-21 (3,533 chunks,
> 7,427 concepts, `failed_chunks = 0`). §G3 runs on **that** graph, not on the 2026-10-19 one.
>
> **Sequencing:** this plan runs **after** the §I12 Lane B rebuild
> (`2026-10-22-p1-i12-derived-collections-dense-lane-plan.md` §6). Running it before would have its
> merge undone by that rebuild.

---

## 0. SETTLED — supersedes these earlier statements

| Earlier statement (where) | Superseded by |
|---|---|
| "§I30 lever: **1,186 merge groups**, 2,692 concepts = **34.4 %**" (register, and quoted in the §G plan) | **Measured on the OLD graph (7,834 concepts).** The rebuild changed the concept set to **7,427**; the lever **must be re-measured before it is quoted again** (§I21's own effect size is *"unmeasured — do not assume it is large, do not assume it is zero"*). §I30's numbers are a **before-arm**. |
| `2026-10-18-p1-graph-analytics-plan.md` §"Phase G3" — verifier 3's wording | Already REWRITTEN 2026-10-20 per §I29 (the query-side distribution, not per-chunk). This plan keeps that rewrite and adds the traps. |
| The §G plan's G3 verifier 3 *"most chunks tie at 1"* | **Wrong quantity** — §I2's *"ties at 1"* is **query-side**; a chunk mentions **4.25** concepts on average. See §3. |

---

## 1. The defect, sized (re-measure first — do not inherit §I30)

`'orbit'` / `'Orbit'` / `'planetary orbit'` / `"Earth's orbit"` are **separate `Concept` nodes**, so a
query resolving to one spelling reaches only that spelling's chunks. §G3 collapses each near-duplicate
group to one canonical node, re-pointing `MENTIONS` and `RELATES_TO` and preserving aliases.

**It is a post-hoc mutation, NOT a re-extraction.** The 3,533 LLM extraction calls are unchanged by
merging names, and the checkpoint makes them free anyway. This is also what the course's Lab 1 does
(*"find at least three entity-resolution failures … and measure how merging them changes the hub
list"*).

### Step G3-0 — re-measure the lever on the rebuilt graph (do this FIRST)

Re-run the existing probe against the rebuilt graph and **register the new numbers**:

    uv run python logs/p1/step10/probe_g3_lever.py     # re-pointed at the rebuilt graph

Record: distinct concept names, normalised keys, merge groups, concepts-in-groups (as a **share** of
the vocabulary), and the top groups' chunk gains. **The §I30 figures (1,186 / 2,692 / 34.4 %) are the
before-arm**; if the new share differs materially, the §G3 design review budget changes with it
(§I31 trap 1 says review the top ~50 groups, not all of them — the top-50 list is what carries the
measured gain, so it must be re-derived too).

⚠️ **§I31 trap 4 applies to this very step:** a number registered from a probe is invalidated the
moment the probe changes. Freeze the probe, *then* register the numbers.

---

## 2. The design — and the four traps that must be designed OUT, not caught in review

**Candidate signal:** name normalisation (case, singular/plural, leading articles, parentheticals) —
the course's canonical example is *"the FDA" vs "FDA"*, which is pure normalisation. `Concept.embedding`
is a **secondary** signal only; after the §I12 Lane B rebuild it is **1024d** (the dense lane), so any
embedding-based step must use `get_cluster_embedder`, not the retired 768d Nomic.

**Deliberately conservative:** merging two genuinely distinct concepts is **worse** than leaving a
duplicate. Every merge must be **reversible and logged**.

| Trap (§I31) | What it does | The rule |
|---|---|---|
| **T1 — a normalisation group is not a synonym set** | `['velocity','Velocity','Velocity = √(g h)']` — the third is a *formula*, not a spelling variant | Review the top groups by eye; never auto-merge a group whose members differ in more than surface form |
| **T2 — substring matching must NOT be used** | **809** normalised substring pairs, most genuinely distinct (`air` ⊂ 12+ concepts) | Normalisation **only**. No substring-derived merge |
| **T3a — punctuation stripping kills Greek** | `re.sub(r"[^a-z0-9 ]+"," ",n)` maps `χ, γ, ħω, π, ε, τ, η, α` all to `""` → one bogus group | Unicode class: `re.sub(r"[^\w ]+"," ",n,flags=re.UNICODE)` |
| **T3b — the plural rule survives T3a** | trailing-`s` strip turns `'s'` → `""`, a **valid** merge key | **Skip empty keys AND count them** (`names_skipped_empty_key`); a bare skip hides the case |

**Design rule from T3:** a normaliser must never return a key no name could legitimately produce, and
any name it cannot key must be **counted, not dropped**. Silence is the failure mode — the merge
counts improve while the graph degrades.

---

## 3. Verifiers (each must be able to FAIL — and the query-side one is the load-bearing one)

| # | Check | Why it discriminates |
|---|---|---|
| **V1** | distinct `Concept` count **falls**; **no name is lost** — every merged name survives as an **alias** on the survivor | Catches a merge that drops a name instead of aliasing it |
| **V2** | `MENTIONS` + `RELATES_TO` edge counts conserved **modulo the merges** — assert the **delta == the number of collapsed edges** | Catches edges silently dropped. A bare "> 0" passes a merge that destroyed 90 % of the graph |
| **V3** | **QUERY-SIDE** (§I29): for a sample of gold queries, the number of chunks scoring `matched_concepts ≥ 2` **rises**, and the median `matched_concepts` of the retrieved top-k **rises**. **Baseline arm measured BEFORE the merge** | The old wording measured per-chunk, which starts saturated at **96.9 %** (3.1 pts of headroom) — a bad merge looks like success. §I2's *"ties at 1"* is query-side; §I32 measured **97.86 %** of the query-side mass at 1, so G3's effect is readable **here** (~30× the discriminating room). Needs a 1024d query embedding against `concept_embeddings` — which is why §I12 Lane B is a prerequisite |
| **V4** | the measured lever reproduces: the top groups' chunk unions match G3-0's re-measured values (`force` → its union, `kinetic energy` → its union) | A merge that does not reproduce those unions did not merge what it thinks it merged |
| **V5** | **the traps did not fire:** no merge joined a formula to a spelling variant (T1); no merge is substring-derived (T2); `names_skipped_empty_key` is reported and non-hidden (T3) | Both T1/T2 are silent — counts improve while the graph degrades |
| **V6** | **`concept_embeddings` is synced:** every merged-away alias's point is deleted (`uuid5("concept:{name}")`), the canonical survivor's point exists, and a probe `_find_concepts_scored` for a merged concept name returns the survivor | A merge that leaves the ANN index holding deleted names re-creates §G1's measured confound (a top-8 seed naming a concept absent from the graph — **mean 3.02 of 8** did, pre-merge) |
| **V7** | **spot-read ~10 merges by eye** and record them (the course's *"read the artifacts"* rule) | A merge joining `'entropy'` to `'enthalpy'` is a defect even though every count improves |

**V3 is the endpoint; V6 is the one this plan adds that the register does not yet carry.** V1/V2/V4/V5
are structural guards; V7 is the human check the course requires.

---

## 4. Pre-registered outcome rule

- §G3 is **done** iff **V3's query-side median rises**, **V1/V2 hold**, and **V7's read sample contains
  no bad merge**. V4 must reproduce the re-measured lever.
- **A merge that improves the counts but fails V7 is REVERTED, not recorded as a partial success** —
  the counts improving while the graph degrades is exactly §I31's failure mode.
- Because every merge is logged and reversible, an unsuccessful G3 leaves the graph as it was; there
  is no "partially merged" state to reconcile.

---

## 5. Parallelization

- **G3-0 (re-measure the lever)** is read-only, LLM-free, and **safe to run alongside anything** —
  including the §I12 Lane A DA re-index (which hits the cluster embedder, not Memgraph).
- The **merge itself** is single-writer on Memgraph and must not overlap another graph write. It is
  therefore **serial** with respect to the §I12 Lane B rebuild (which is why §6 of the §I12 plan
  sequences Lane B *before* G3).
- **V3's baseline arm** should be measured **in the same session as the merge**, before it, so the
  before/after pair is taken under one configuration.

---

## 6. Register, at the end

- **§G3 closed** with V1–V7 evidence; **§I2** closed by G3 (and §G5, if taken).
- **§I30 superseded** — the re-measured lever replaces the before-arm numbers.
- **§I31 traps 1–4** confirmed handled, each with the check that caught it (or the reason it did not fire).
- **§I29** confirmed: G3's verifier is the query-side distribution.
- Update `HANDOFF.md`'s D1 block: §G3's gate (the rebuild) is discharged; §G3 is done; §G2 is next.

---

## 7. Explicitly NOT in this plan

- **No concept-extraction prompt change** — it would invalidate the 3,533 extraction calls and the
  checkpoint key. G3 is designed as a post-hoc merge precisely to avoid that.
- **No `concept_embeddings` rebuild** — that is §I12 Lane B, a prerequisite, not part of G3. G3 only
  **syncs** the collection to the merged node set (V6).
- **No community detection** — that is §G2, gated behind G3's clean node set.
- **No substring matching, no auto-merge of formula-bearing groups** (T1/T2).
- **No new dependency** — G3 is name normalisation + optional `Concept.embedding`; `python-igraph` +
  `leidenalg` are G2's, taken by the 2026-10-21 owner decision.
