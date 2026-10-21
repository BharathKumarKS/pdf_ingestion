# P1 Step 9 — downstream phases, pulled forward. Execution plan.

> **Written 2026-10-18.** Read `HANDOFF.md` (current state), `IMPROVEMENTS.md` §D14 (the gate that
> forced this) and `.hermes/plans/2026-10-16-p1-reingest-plan.md` §5 Step 9 + **§7 decision 2** (the
> decision this asks to change). This file is the *procedure*; it is not a register.
>
> **Why this exists.** Step 10's preflight gate fails because the graph holds only the *previous*
> ingest's document. Owner decision 2026-10-18: build the downstream phases rather than scope the
> check. That is **Step 9** — the item §7 decision 2 explicitly deferred.

---

## 0. Scope decision to confirm BEFORE anything runs

**§7 decision 2 (closed 2026-10-16) says:** *"Scope of the run → minimal first. Phase 1 only … then
re-measure the text funnel + the §D13 reranker ablation. **Cards / visual / graph are deferred — the
ablation lives entirely in the text lane, so none of them gate it.**"*

So "what we agreed on" currently points the **other** way from "take the cards and ColPali along
too". That is not a reason to refuse it — it is a reason to state what changes. Two things are true
and they pull in opposite directions:

**(i) The funnel ablation genuinely does not need any of it.** `funnel_boundary_recall.py` reads only
`knowledge_base_v2` + the cluster embedders. Cards, ColPali and the graph are invisible to it. §7
decision 2 is correct about §2.

**(ii) Step 10 §4 genuinely does need it.** `evaluate_rag.py` calls `store.search_with_das` (the DA
card lane) and, for multihop, `graph_builder.graph_search`; the visual lane reads
`visual_knowledge_base`. All three collections today hold **only the old document**:

| Store | Points / nodes | Document |
|---|---|---|
| `derivative_artifacts` | 81,837 | 100 % `6d55c52b` (old) |
| `visual_knowledge_base` | 1,033 | 100 % `6d55c52b` (old) |
| Memgraph graph | 1 doc / 5,051 chunks | 100 % `6d55c52b` (old) |
| `knowledge_base_v2` | 3,796 | 100 % `7ba61432` (new) |

So **§4's numbers cannot be about v2** until Step 9 runs. Doing Step 9 before §4 is not a reversal of
§7 decision 2 — it is the thing §7 decision 2 assumed would happen *after* §2.

**(iii) ⚠️ The crux — Phase 2 mutates the collection §2 measures.** `raptor_tree.py` stores its
summary nodes in **the same Qdrant collection as the chunks** (`source_type="raptor_summary"`, doc
line 273: *"A RAPTOR summary is stored in the same Qdrant collection as the chunks"*). Today
`knowledge_base_v2` = **3,796 points == SQLite chunks exactly** (Step 8's `verify_collection.py`
exit 0). Running Phase 2 adds RAPTOR points on top, which **breaks that invariant** and changes the
candidate pools the funnel replays. The old index had 5,135 points = 5,051 chunks + **84 RAPTOR
nodes**, so the recorded baselines (§D12, §D13) were measured on a collection that *did* contain
RAPTOR nodes.

**Therefore the ordering is a real choice, and it is the owner's:**

| | Order | §2 ablation measures | Comparable to the old baseline? | Risk |
|---|---|---|---|---|
| **A** | graph → gate → **§2** → Phase 2/3 → **§4** | 3,796 chunks only (no RAPTOR) | No — old index had RAPTOR; but the *delta* is what matters and both arms share the same pool | §2's absolute R@20 is not like-for-like with §D12's 0.465; §4 must be re-run after Phase 2 anyway |
| **B** | graph → Phase 2/3 → gate → **§2 + §4** | 3,796 chunks + RAPTOR nodes | Yes — same composition as the old index | §2 is delayed by hours and its pool gains RAPTOR nodes mid-comparison against §D13's recorded old-index number |

**✅ DECIDED 2026-10-18 (owner): Order A — minimal first.** The owner's clarification: *"doing only
what is required now. minimal first."* So this execution has a **hard stop point**, and Phases B/C/D
are **not** part of it:

> **NOW:** Phase A (graph) → Phase E gate → Step 10 §2 (the ablation) → **STOP and report.**
>
> **LATER, as a separate decision once §2's numbers exist:** Phase B (cards + RAPTOR) → Phase C (DA
> re-index) → Phase D (ColPali) → Step 10 §4.

The graph is in "now" only because the preflight gate mechanically requires it (§D14) — it is the one
piece of Step 9 without which §1 cannot pass. §2 then runs on the clean re-ingested index, before
Phase 2 would mutate the collection (see (iii) above). **Nothing in Phase B/C/D is started until §2
has been measured and reported.** §4 runs after Phase E, when all three side lanes are about v2.

**Curriculum — located and folded in.** The SupportVectors course materials live at the **repo root**
(`/Users/bharathkumar/repo/Support_Vectors/Beyond_RAG_Advanced_Agentic_Knowledge_Architectures/`):
`Week_Plan/` (12 lesson plans), `Week_Summary/` (12 summaries), `Slides/` (9 decks), `Labs/`
(`Week_1`–`Week_11`), `Project/Docs/`. Requirements relevant to this plan, quoted rather than
paraphrased:

| Requirement | Source | Effect on this plan |
|---|---|---|
| **"every index must earn its place through ablation"** | `Week_Plan/week-10-…`, slides | Directly endorses §2/§4's design — the ablation is the course's own method, not a local preference |
| **"3–8 questions per chunk; embed the question, carry the answer and source ids in the payload"** | `week-4-`, `week-10-…`, `week_10_the-library-of-many-catalogues` | Phase C's **§F1** is course compliance, not a preference (registered as §A3) |
| **Factoids: "self-containment, an nli faithfulness filter, a cap per chunk"** | `week-10-…`, `week_10_…catalogues` | The project has **no card faithfulness gate** — registered as §A3; a candidate Phase B verifier |
| **"Run both over a fifty-chunk sample. Then do the thing engineers skip and should not: read the artifacts."** | `Week_Plan/week-4-…` lab | Becomes a **Phase B verifier**: sample the generated cards and read them, not just count them |
| **Summaries at chunk / section / document altitudes** | `week-10-…` | Confirms RAPTOR is the right Phase B shape |
| **One atomic fact per card; typed cards; metadata side + information side** (Otlet / OKF) | `Week_Summary/Week 9`, `Week 10` | The standard against which §A3's card-volume question is judged |

`sv_ray_cluster_access/` is **not** curriculum — it is cluster-access docs only (§I8: SupportVectors
IP, endpoints unreachable, not importable). `Project/Docs/synapse_full_report.pdf` is **this
project's own** report, and it is **stale**: it documents `dense_768`/768d, `chunk_size=512`,
`splade_enabled False`, 5,051 chunks and 84,657 DA vectors — i.e. the pre-re-ingest pipeline. Do not
treat it as a spec.

---

## 1. Preconditions — re-verify, do not assume

| # | Claim | Verified 2026-10-18 |
|---|---|---|
| P1 | Memgraph reachable, Bolt `localhost:7687` | ✅ v2.18.1 — check Bolt, **never** `.State.Health.Status` (permanently `unhealthy` from a broken healthcheck, §D14) |
| P2 | `knowledge_base_v2` = 3,796 points, doc `7ba61432` | ✅ `colbert,dense_1024,dense_64` |
| P3 | SQLite doc `7ba61432` = 3,796 chunks; doc `6d55c52b` = 5,048 | ✅ |
| P4 | Cluster LLM answers (`openai/gpt-oss-20b`) | ✅ real completion, preflight |
| P5 | Local models cached: Nomic (concept names, DA cards) + ColPali | ✅ `data/models/` |
| P6 | PDF on disk for rasterizing (ColPali) | ⚠️ **not yet checked** — `doc.source_path` or `base_textbook_dir`; verify before Phase D |
| P7 | Docker daemon up (Memgraph is a local compose service) | ✅ started 2026-10-18 |

---

## 2. Execution model — background jobs, verifier between each

Every phase is **one background job** (`terminal(background=true, notify=true)`), launched from a
`logs/p1/step10/*.sh` script that prints resolved settings and asserts stubs are off. **Verifiers do
not live inside the job** — they run after it, from Bolt / Qdrant / SQLite, because the recurring
failure mode in this codebase is a phase that reports success while writing nothing:

- `graph_builder.build_graph`'s `failed` counter **can never increment** (`_extract_concepts`
  swallows every exception) → an LLM outage yields an **empty graph reported as "0 failed"**;
- §I15 — `save_document` swallows SPLADE/ColBERT failures → an incomplete index reported as success;
- §I9 — a failed embedding degrades to **zero vectors** silently.

**Rule for every verifier below: count in the destination store and compare against SQLite — never
read the script's own summary line.** A phase that fails its verifier stops the chain; nothing
downstream runs.

---

## Phase A — Memgraph concept graph (doc `7ba61432`)

*Detailed procedure already written: `.hermes/plans/2026-10-18-p1-step10-graph-rebuild-plan.md`
(its G1–G5 are this phase's A1–A5). Summary:*

> **⚠️ What Phase A is NOT (checked against the agreement, 2026-10-18).** This phase re-runs the
> **existing** graph code for the new document. It adds **no graph analytics**: no community
> detection, no community summaries, no PPR, no entity resolution, no new traversal. The agreed home
> for all of that is **`IMPROVEMENTS.md` §G** ("Graph — adopt the course's Memgraph analytics
> layer"), registered as its own work with its own plan, and **nothing in Step 9 or Step 10 pulls it
> forward**:
>
> | # | §G item | State |
> |---|---|---|
> | G1 | **PPR** over the concept adjacency matrix | agreed, on the **HANDOFF P2** list (`abstention · guardrails · PPR · semantic caching · OKF cards`) |
> | G2 | **Community detection + community summaries** | agreed as backlog. **Not implemented anywhere today** — the current graph has none |
> | G3 | **Entity resolution** (merge `'orbit'` / `'Orbit'` / `'planetary orbit'`) | **§I2 calls this "the known bug"** and says *"deduplicating concept names is the bigger lever than ranking"* |
> | G4 | global / local / drift query modes | agreed, brainstorm-stage |
> | G5 | genuine multi-hop (`hop_distance` is a **constant 0**) | **§I2: "multihop" is nominal** |
>
> So the answer to *"are we following the course's Memgraph approach by community detection?"* is:
> **not in this step, and it was never in this step.** Phase A exists only to make §D14's
> `graph.matches-qdrant` check pass; it is the same code path the old document went through.
>
> **And the course itself argues against rushing G2 here.** `Week_Plan/week-5-…` (the GraphRAG
> week): community detection is *"cheap by comparison but not free"* and then *"you owe leaf
> summaries, merged summaries, summaries of summaries — LLM calls all the way up the hierarchy"*;
> GraphRAG is *"always a sidecar — it extends the motorcycle; it never replaces it"*; and on size:
> *"Emergence needs mass. Run Leiden on the entity graph of a three-page essay — fifteen entities,
> twenty edges — you get three tiny 'communities' whose summaries paraphrase the essay, at LLM
> prices. **You cannot detect ocean currents in a bathtub.**"* The same deck notes **MemGraphRAG's
> "refusal to do community detection at all"**. Our corpus is **one book**. The course's own
> ordering puts **entity resolution (G3) before any community work** — *"resolve poorly and the graph
> fragments, and every downstream step inherits the fracture."*
>
> **Consequence:** if we want the graph analytics layer, it needs its **own plan + signoff**, and G3
> (entity resolution) is the item the evidence supports first — not G2. It is not part of Step 10,
> and adding it now would change the very substrate §2 is about to measure.

- **A1 settings gate** — `logs/p1/step10/run_graph.sh`. *Verifier:* prints `ASSERTIONS OK`.
- **A2 before-snapshot + one-chunk probe** — *Verifier:* graph holds exactly 1 document (`6d55c52b`),
  0 chunks for `7ba61432`; and `_extract_concepts` on one real chunk returns **≥1 named concept**.
  **0 concepts → STOP** (it would build an empty graph).
- **A3 build** — `scripts/run_phase3.py --doc-id 7ba61432 --graph-only`.
  **Cost — measured, not estimated (my first estimate of 45–90 min was wrong by ~2–3×):**
  concept extraction logs progress every 500 chunks, and the first two blocks took **21.1 min**
  (500/3796 at 17:45:06) and **21.6 min** (1000/3796 at 18:06:43) — i.e. **~21 min per 500 chunks,
  ≈ 10 s per LLM call at `concept_gen_workers=4`**. Full extraction therefore ≈ **2.7 h**, before the
  sequential local-CPU concept-name embedding and the ~65k-statement sequential Cypher write.
  **Realistic total ≈ 3–3.5 h.** Do not raise `concept_gen_workers` mid-run: §I18's discipline is
  that concurrency is not raised without sustained-load evidence, and the endpoint has degraded under
  load twice.
  *Verifier (from Bolt):* exit 0; `7ba61432` has **3,796** Chunk nodes (== SQLite); concepts > 0;
  edges > 0; **concept density ≥ 0.78/chunk** (old doc: 7,815/5,051 = 1.55; below half that is the
  signature of mass silent extraction failure).
- **A4 retire the old document's graph** — `clean_stale_graph.py --qdrant-host 10.0.10.65` with
  `QDRANT_COLLECTION=knowledge_base_v2`, **dry-run first**. ⚠️ Destructive to the deployed
  `knowledge_base`'s graph until cutover. *Verifier (before):* exactly **1** stale doc (`6d55c52b`),
  `7ba61432` marked "keep (has vectors)". *Verifier (after):* 1 document, 3,796 chunks. Never `--force`.
- **A5 gate** — `scripts/preflight.py` → **exit 0**, `graph.matches-qdrant` < 1 % (was 100 %).

---

## Phase B — Phase 2: cards + RAPTOR (doc `7ba61432`)

```bash
uv run python scripts/run_phase2.py --doc-id 7ba61432
```

Cards → SQLite `cards`; RAPTOR summaries → **`knowledge_base_v2`** (`source_type="raptor_summary"`).
`generate_phase2_artifacts` skips non-content chunks via the E5 `content_filter`, so the card
denominator is **fewer than 3,796 chunks** — measure it, don't assume it.

**Cost:** the re-ingest plan's own estimate is **~5k chunks × 8 types ≈ 40k LLM calls — "the
expensive part"**; `card_gen_workers=8`. Expect **hours**. Measure with a `--limit`-style probe first
if one exists; otherwise time the first N cards from the log before letting it run.

**Verifier (SQLite + Qdrant, after the job):**
1. exit 0 and no `Failed:` row in the run table (run_phase2 catches per-doc exceptions and prints
   them into the table — an exception does **not** fail the process);
2. cards exist for `7ba61432` and **every card's `chunk_id` is a v2 chunk id** (a card pointing at a
   `6d55c52b` chunk means the wrong document was processed);
3. the card types present == the **8** in `CardType` (`tests/test_config_invariants.py` pins this);
4. card count is in family with the content-chunk count — record it; a count near zero is the §I9
   signature;
5. RAPTOR nodes > 0 in SQLite, and `knowledge_base_v2` grew by exactly the RAPTOR node count
   (this is the invariant Phase 2 breaks — record the new total);
6. RAPTOR node vectors are **not** zero (the `--raptor-only` flag exists precisely because "RAPTOR
   used zero vectors" happened once);
7. **read the artifacts** (course requirement, `Week_Plan/week-4-…` lab: *"the thing engineers skip
   and should not"*) — sample ~10 generated cards of different types and inspect them by eye for
   self-containment (no dangling "it"/"this"), atomicity (one fact per card), and faithfulness to the
   source chunk. **A card that is not supported by its chunk is a defect even though it counts.**
   Record what was read and what was found; do not report a pass on counts alone.

---

## Phase C — Phase 2b: DA re-index (§A2 + §F1)

```bash
uv run python scripts/index_derivative_artifacts.py --clear
```

Rebuilds `derivative_artifacts` from SQLite `cards`. Also lands **§F1** (question cards embed the
question only; the answer rides in the payload).

**Cost:** §A2 — "~82k embeddings locally on CPU — likely tens of minutes to hours" (for the old
doc's card count; scale to v2's).

**Verifier:**
1. `derivative_artifacts` `payload.card_id` ∩ SQLite `cards.id` is **non-empty** — §A2's measured
   defect was that the two shared **no ids at all**; this is the exact check that catches a stale
   collection;
2. all 8 card types present in DA (the old collection had **5 of 8**);
3. DA document ids == `{7ba61432}` — the old document's 81,837 points must be gone (the `--clear`
   semantics) or explicitly retired; if they coexist, the DA lane serves cards the v2 index has no
   chunks for.

---

## Phase D — Phase 3: ColPali visual (doc `7ba61432`)

```bash
uv run python scripts/run_phase3.py --doc-id 7ba61432 --pdf <path>     # no --graph-only
uv run python scripts/clean_stale_visual.py --qdrant-host 10.0.10.65   # dry-run
uv run python scripts/clean_stale_visual.py --qdrant-host 10.0.10.65 --apply
```

Rasterizes 968 pages and embeds them locally (ColPali, ~5 GB, **CPU**, batch 4 — §I10 fixed a 5.5 GB
reload per query; a single process should hold it once). **Cost: hours.** ⚠️ Requires the PDF on disk
(P6 — verify first).

**Verifier (before cleanup):** `visual_knowledge_base` contains points for `7ba61432` and the count is
**≈ one per page** (not a multiple) — §B4b's defect was **3 vectors/page**, and
`clean_stale_visual.py` cannot catch it because it keys on `document_id`.
**Verifier (after cleanup):** exit 0, and the only surviving document id is `7ba61432`. Exit 2
("no document id is shared with the text index") means the wrong Qdrant — stop, do not force.

---

## Phase E — re-run the gate, then resume Step 10

```bash
export QDRANT_HOST=10.0.10.65 QDRANT_COLLECTION=knowledge_base_v2
uv run python scripts/preflight.py
```

**Verifier:** **exit 0** on all checks — graph, DA, visual, classifier width, endpoints.

Then, per the §0 ordering decision:
- **Order A:** Step 10 §2 (the ablation) runs **before** Phase B, and §4 runs after Phase E.
- **Order B:** both §2 and §4 run after Phase E.

Either way, Step 10 §3 (the §D4 label re-derivation) and §4's decision/registration are unchanged —
see `.hermes/plans/2026-10-18-p1-step10-remeasure-plan.md`.

---

## Course-standards checks to fold in (grounded in `IMPROVEMENTS.md` §H)

§H is the repo's own compliance table against the course's stated retrieval standards. Two ⚠️ rows
should be **re-measured on the rebuilt index** as part of this work, because the re-ingest changes
both quantities:

1. **"Chunk sizes sane vs the reranker's 512-token window"** — measured **57 of 5,048** chunks exceed
   it (max 1,701) and are silently truncated. Re-measure on v2's 3,796 chunks; E1/E2 changed the
   chunking, so this number is new information, and a large tail would directly cap the reranker's
   ceiling in §2.
2. **"Measure recall@N at each funnel boundary"** — §H marks this ⚠️, but `funnel_boundary_recall.py`
   now reports B1–B6 individually. Confirm the row is stale and correct it rather than re-doing work.

Also adjacent and **not** in this step: §F2 (RAPTOR writes only `dense_64`/`dense_768` and has no
hybrid retrieval) — a real deviation from the course's "hybrid is the default", but it is its own
change, and Phase B deliberately does not touch it.

---

## Register at the end

- **§D14** — fix (c) taken; measured before/after dangling %.
- **§7 decision 2** — record that it was reopened and what was chosen (§0 A vs B).
- **Step 9** — record which halves are done. Cards + DA + visual + graph is the **whole** of Step 9;
  say so explicitly rather than leaving it half-claimed.
- **§A2, §F1, §B4b, §I12/§I13** — each is discharged or explicitly not by these phases.
- **HANDOFF.md** — "IMMEDIATE NEXT STEPS" currently names Step 10 §1; update to name this.
- Every number must grep back to `logs/p1/step10/`.

---

## Explicitly NOT in this step

- **§F2** (RAPTOR hybrid retrieval), **§A1** (regenerate the `question` card type), **§I12**
  (`concept_embeddings` → 1024d), **§I13** (`reembed_chunks.py` / `validate_embedders.py` on the
  retired model), **§I20** (`save_document` atomicity), **§I17** (ColBERT/SPLADE batch sizes).
- **Any code change.** Every phase here runs existing scripts. If a phase's verifier fails, that
  becomes a new register entry and a stop — not an in-flight fix.
- **Step 10 §2–§4 themselves** — they resume only at Phase E, in the §0 order you choose.
