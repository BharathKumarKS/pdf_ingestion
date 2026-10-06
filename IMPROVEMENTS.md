# IMPROVEMENTS — tracked backlog

Everything known-but-not-yet-done, in one place so it can be taken in a single pass.
Each entry says **what**, **why it matters**, and **the evidence** — so nothing has to be
re-derived later. Add to this file rather than leaving a note in a commit message.

Last updated: 2026-10-06

---

## A. Queued — do when there is a real need (not blocking anything)

### A1. Regenerate the `question` card type with the corrected prompt
- **What:** re-run card generation for `question` cards only, using
  `prompts/question_answer_generator.md` as fixed on 2026-10-06.
- **Why:** the prompt bug (questions anchored to the source) is fixed for *new*
  generation, and the existing corpus was backfilled by a *pattern filter*. The filter
  is a safety net, not the fix — regeneration is the version that stops being
  whack-a-mole. 2,975 cards were removed by the second filter pass alone.
- **Evidence:** filter history — 9,829 caught, then 2,975 more after a recall gap;
  measured 0 non-valuable remaining, but only after two iterations.
- **Cost:** ~5,048 chunks × 1 LLM call.

### A2. Re-index `derivative_artifacts` from SQLite
- **What:** `uv run python scripts/index_derivative_artifacts.py --clear`
- **Why:** the collection is a **retired card generation** — it shares no card ids with
  SQLite, and was built by the old 5-type list, so it lacks `objective`, `misconception`
  and `example` (10,927 cards). The DA retrieval lane therefore serves cards the UI does
  not have.
- **Evidence:** DA 81,837 points vs SQLite 82,164 cards; id overlap **0**; types present
  in DA = 5 of 8.
- **Cost:** ~82k embeddings locally on CPU — likely tens of minutes to hours.
- **Note:** do A1 first if doing both, so this indexes the cleaned card set once.

---

## B. UI / UX backlog — combine into one pass

### B1. Formula card: the explanation renders as mathematics ⚠️ verified
- **What:** on a formula card, the whole `content` string is passed to `st.latex()`
  (`streamlit_app.py`, `render_math`, the `card_type == "formula"` branch). The content
  is `"<formula> where <prose explanation>"`, so the prose is typeset as maths: spaces
  collapse and letters go italic.
- **Symptom:** `a = F/m` renders correctly, then
  `whereaisthelinearaccelerationofthebody(m·s⁻²),Fisthenetexternalforce…`
- **Fix:** split at the first top-level ` where ` — render the formula with `st.latex()`
  and the explanation with `st.markdown()`.
- **Evidence:** 1,534 formula cards; **1,516 (98.8%) contain ` where `**; 1,401 split
  cleanly with a naive regex; the remaining ~115 have `where` *inside* LaTeX
  (`\text{where}`, or as part of an expression), so the split must respect brace depth,
  not just match the word. 18 cards are pure formula with no explanation.
- **Root-cause note:** the generator emits one unstructured string. The durable fix is
  for `formula` cards to carry the formula and the explanation as separate fields.

### B2. Study Cards: the two card categories still unruled
- `summary` (RAPTOR summaries exposed as cards, titled "Summary") — nothing to self-test;
  candidate for exclusion from the student set.
- `factoid` where `content == title` (a bare sentence echo, e.g. *"The simple lever is
  fundamentally reversible."*) — legitimate facts, but ~29k of them; candidate for
  ranking/capping rather than display.
- **Status:** raised, deliberately **not** actioned — the call is Bharath's.

### B3. Visual search threshold needs re-calibration on real figures
- **What:** the 600 cutoff was fitted against **synthetic** negatives (noise/blank/
  gradient images). A genuine cropped figure scores lower than those, so a legitimate
  query may be wrongly rejected.
- **Fix:** re-measure against real figure crops and unrelated-but-document-like images;
  show the score and an honest "no page matched" message rather than silence.

### B4. Visual search cannot handle images that aren't book pages ⚠️ verified
- **What:** uploading a synthetic/redrawn figure (e.g. a clean render of the
  Boltzmann–Gibbs relation) returns "the book has no such image", even though the book
  explains the concept.
- **Why it fails — two independent reasons:**
  1. **Wrong input modality for the model.** `colpali_embedder` exposes only
     `embed_query_image`; the visual lane has *no text-query path*. But
     `vidore/colpali-v1.2` is trained on **(text query, page image)** pairs — its query
     encoder expects text. Feeding it an image is off-distribution, so even a genuine
     crop of a real figure is being asked a question the model was never trained on.
  2. **Visual similarity ≠ concept similarity.** ColPali matches appearance/layout
     (typography, page furniture, figure shape), not meaning. A synthetic render shares
     no visual features with a 1960s scanned page even when the concept is on it, so
     MaxSim stays low and the 600 threshold correctly reports no match.
- **The threshold is not the bug** — it is what stopped the earlier "confidently returns
  unrelated pages" defect. Lowering it reintroduces that.
- **Fix (image → text → retrieve → synthesize):**
  1. VLM reads the image (`Qwen3-VL-8B-Instruct` is already on the cluster) → caption +
     equation as LaTeX + concept names.
  2. Use that text as the query for the **existing hybrid text lane** (Nomic + SPLADE +
     reranker) — the same path as Ask a Question. LaTeX is a strong lexical signal for
     SPLADE; the caption is a strong dense signal.
  3. Synthesize from the retrieved passages, reusing the Ask-a-Question synthesis, so the
     output explains the image *and* cites the book.
- **Bonus:** the same VLM caption can be used as a **text query for ColPali**, which is
  how ColPali is designed to be used — so both lanes work as intended and can be fused
  (RRF): ColPali finds the *figure* page, the text lane finds the *explanation* page.
- **Keep ColPali for its real strength:** "find the diagram that looks like this"
  (a student photographs a lecture-slide figure and wants the book's version).

---

## C. Product — deferred by decision, not forgotten

| # | Item | Note |
|---|---|---|
| C1 | **Feedback capture** (thumbs / "was this helpful?") | The only real-user signal available; today the gold set + judge are the entire measurement apparatus |
| C2 | **Question history** | Each question replaces the page; no history table exists (`cards`, `chunks`, `documents`, `page_images`, `raptor_nodes`). Students iterate on a topic and must re-ask |
| C3 | **Key Facts panel — measure before removing or expanding** | 8 cards injected after every answer; never evaluated for helpfulness |
| C4 | **Topic / Difficulty** | Removed as inert (persisted, never read). Revisit as a real feature: scoped card generation at a chosen level |

---

## D. Gates the heavy lifting — the gold set (P0-9)

Rebuild the eval set; **everything else is unmeasurable without it**.

- **Current state:** 30 queries, 23 calibrated, median **2** labelled pages, labels are
  LLM-generated (Qwen3-VL) with **zero human verification**.
- **Power analysis:** at n=23 only effects ≥ ~0.15 are detectable. Target **~120–150**
  queries to detect a 0.05–0.10 effect (α=0.05, power=0.80, σ_d≈0.25–0.30).
- **Per-type generation strategy** (one method cannot do all three):
  - `factual` — generate the question **from a known page** (labels correct by construction)
  - `overview` — pick a *topic*, then an exhaustive book-wide scan for all pages on it
  - `multihop` — pick two concepts from the **Memgraph concept graph** (`PREREQUISITE_OF`
    edges already exist) and find the pages establishing each plus the link
- **Also needed:** graded relevance (0/1/2) instead of binary; human verification of a
  20–30% sample to *measure* the labeller's error rate; and **never derive labels from
  the retriever** (the original `calibrate_eval_pages.py` approach was circular — the
  ground truth was whatever the retriever returned, so false negatives were invisible).
- **Then:** metric fixes (Precision@20 is pinned at its ~0.10 ceiling by a fixed ÷20
  denominator over a 2-page ground truth → use Recall@k / R-precision / Hit@k, and report
  any precision number against its ceiling), then the judge lane, then ranking work.

### D2. What the boundary measurement changes about fine-tuning (2026-10-06)
- **The contrastive 3-phase curriculum fine-tunes the bi-encoder (the retriever)** — the
  course's Week 11 lab trains a `SentenceEmbeddingModel`. It is **not** the reranker.
- **Measured headroom, from `data/eval_results/funnel-boundary-recall_2026-10-06.md`:**
  - retrieval gap (what a better bi-encoder could buy): recall 0.895 → 1.0 = **0.105**
  - ranking gap (what a better reranker could buy): 0.561 → 0.895 = **0.334**
  → ranking is the lever by ~3×. **Fine-tune the cross-encoder first.**
- **So the bi-encoder fine-tune is deprioritised, not cancelled.** It addresses a 0.105 gap
  and it requires a **full re-ingest** (re-embed 5,135 chunks + 82k cards + the visual lane).
  The cross-encoder fine-tune needs **no re-embedding** — it is a separate model trained on
  (query, passage) pairs drawn from the existing index.
- **The two models use different objectives, and this was always true:**
  | model | objective |
  |---|---|
  | bi-encoder (retriever) | contrastive / InfoNCE (in-batch, then mined hard negatives) → triplet |
  | cross-encoder (reranker) | **binary relevance over (query, passage) pairs** with mined hard negatives — single stage |
  So "fine-tune the reranker with contrastive loss" is a category error; the contrastive
  phases belong to the bi-encoder.
- **What the measurement gives the fine-tune:** a target. The reranker must beat **0.598**
  (the retriever's own top-20) to be worth keeping. Today it scores 0.561 — it is not
  earning its place, so the fine-tune has a concrete, measurable job.
- **Order:** run the lane on/off A/B first (see below). If removing the reranker raises
  Recall@20, "fine-tune it" becomes a choice — make it earn its place — rather than a
  necessity, and the free option should be tested first.

### D3. Pin HyDE before any A/B
- Two identical runs of the same command gave Recall@20 of **0.631** and **0.561** — a 0.07
  spread from LLM sampling alone. **Nothing below ~0.07 is currently measurable**, so any
  lane on/off comparison is uninterpretable until HyDE is pinned (temperature 0 / fixed
  seed, or cache the generated hypotheticals and reuse them across runs).

### D1. The reranker fine-tune needs a *training* set, not the eval set
- **The eval set and the training set are different artifacts** and must not be conflated.
  The eval set is for **measuring** (small is fine); the training set is for **fitting**
  (small is fatal).
- **Scale:** a cross-encoder reranker is normally trained on **thousands** of
  (query, positive, hard-negative) triples. n=23 — and even the ~120–150 target — will
  overfit immediately. Fine-tuning the reranker is therefore **blocked on a training-set
  build**, not on the eval set.
- **Sources for it:** the same per-type generator that builds the eval set, run at much
  larger scale with a **held-out split** (train/eval never share queries); LLM-generated
  queries per passage (the approach in `scripts/generate_gold_dataset.py`); and generously
  mined negatives — for each query, every retrieved-but-not-labelled passage is a negative,
  so one query yields many triples.
- **Recipe placement:** the phases (in-batch negatives → mined hard negatives) belong to
  the **bi-encoder** (stages 1–2). The **cross-encoder is stage 3** — a single training run
  on triples. Fine-tuning *only* the reranker means **skipping stages 1–2** and going
  straight to stage 3, which is legitimate: mine the triples with the current untrained
  retriever, then train.
- **Within stage 3** there is still optional curriculum (easy/random negatives first, then
  hard) and optional **iterative re-mining** (train → re-mine with the improved reranker →
  retrain). That is iteration, not the bi-encoder's 1-2-3 phasing.

---

## E. Ingestion & chunking — closing the gap to the course pipeline

The course's ingestion pipeline is: **Docling → parent chunks (markup/heading boundaries)
→ a semantic chunker → semantic child chunks → then either contextual or late chunking.**
This project does: **Docling → markdown → size-based sentence chunking → independent
embedding.** The middle and back of that pipeline are missing.

### E1. Semantic chunking instead of size-based sentence chunking ⚠️ requires re-ingest
- **What:** swap `chonkie.SentenceChunker` (chunk_size 512 / overlap 64) for
  `chonkie.SemanticChunker`, which cuts where consecutive-sentence similarity drops.
- **Measured on the same text** (4,977 chars of Docling markdown):

  | Chunker | chunks | avg chars |
  |---|---|---|
  | TokenChunker | 3 | 1,659 |
  | **SentenceChunker (current)** | **12** | **436** |
  | RecursiveChunker | 15 | 331 |
  | **SemanticChunker** | **19** | **261** |

  A sentence chunk ended mid-thought (*"…Now we would like to sho"*); the semantic chunk
  was a complete, self-contained claim. Semantic chunks are smaller and topic-coherent —
  which should raise **base retrieval recall** (the thing you asked about), because a
  chunk that covers one idea matches a query about that idea more sharply.
- **Does it require re-ingest?** **Yes.** Chunk boundaries change ⇒ new chunk ids, new
  embeddings, new Qdrant points, new cards. Everything downstream is rebuilt.
- **Caveat:** semantic chunking costs an embedding pass at ingest and its `threshold` is
  a tuning knob. Smaller chunks also mean more of them (19 vs 12 here) — re-check the
  funnel's candidate counts after switching.

### E2. Parent/child hierarchy (hierarchical markdown → parent chunks) ⚠️ requires re-ingest
- **What:** use Docling's markdown heading structure to define **parent** chunks
  (section-level), with semantic chunks as **children** inside them.
- **Why:** the hierarchy is what makes contextual/late chunking possible at all — both
  need a parent to draw context from. Today the heading structure is parsed and then
  discarded (only leaf chunks survive).
- **Evidence:** Docling's output *is* hierarchical — on 3 pages of the Feynman PDF it
  emitted `## Work and Potential Energy (A)` / `## 13-1 Energy of a falling body`, and
  per-element provenance gives the page for each. The structure exists; nothing stores it.

### E3. Late chunking or contextual chunking ⚠️ requires re-ingest
- **What:** one of the two context-preserving methods, on top of E2's parents:
  - **Late chunking** — embed the parent once, then mean-pool the token embeddings inside
    each child's character span. No LLM calls at ingest; needs a long-context embedder
    and per-token offsets. **`chonkie` 1.7 ships a `LateChunker`**, so this may not need
    hand-rolling.
  - **Contextual chunking** — an LLM rewrites each child to be self-standing.
- **Demonstrated difference** on a chunk containing a dangling *"This"*:
  - *before:* "The learning process … adjusting **these** weights … **This** is typically
    done through backpropagation…"
  - *after contextual chunking:* "…consisting of interconnected nodes called neurons that
    process information through weighted connections. The learning process in **these
    neural networks** involves adjusting the weights based on training data. …"
  The pronoun was resolved and the chunk became self-standing — that is the context the
  current pipeline loses.
- **Boundary clarification (the mechanism, verified):** the boundaries are **not** chosen
  in embedding space. The **chunker** chooses them as character spans; late chunking only
  changes how each chunk's *vector* is computed. On a 104-token parent with a chunk span
  of `[263, 610]`, 60 tokens overlapped the span; those 60 token embeddings (each already
  carrying whole-parent context, because the parent was embedded once with
  `truncation=False`) are mean-pooled into the chunk vector.
- **Also a slip worth correcting in the course note:** the whole document goes to a
  long-context *embedding* model, not an LLM.

### E4. Stale docstrings describing a pipeline that was never built ✅ fixed
- `chunker.py` claimed *"Chonkie-based semantic chunker"*, *"Two-pass chunking … Semantic
  grouping via chonkie SemanticChunker"*, and *"span tracking for Jina late chunking"*.
  None of it is true: the chunker is `SentenceChunker`, `SemanticChunker` is never
  imported, and the embedder is Nomic and encodes chunks independently. Corrected.
- **Why this matters beyond tidiness:** a docstring describing intent gets read as a
  description of reality — exactly the failure mode `silent-failure-audit` warns about.
  This is how the "semantic chunking" claim would have survived into the report.

---

## F. Card & graph lanes

### F1. Embed the question only, not question+answer ✅ code changed ⚠️ requires re-ingest
- **Was:** question cards embedded `content + "\n" + answer`.
- **Now:** question only. The answer rides in the Qdrant payload as a new `answer` field —
  it was **not** there before (only concatenated into `text`), so without this change
  dropping it from the vector would have lost it from the lane entirely.
- **Why:** a student's query resembles a *question*, not an answer. Mixing the answer into
  the vector dilutes the question's signal and lets a query match text the student never
  wrote. The course embeds queries (query–paraphrase pairs), never answers.
- **Takes effect only after the DA collection is re-indexed.**

### F2. Bring RAPTOR into the hybrid lane ⚠️ requires re-ingest
- **What:** RAPTOR writes only `dense_64` + `dense_768` and queries only `dense_768` via a
  plain `query_points` — no sparse lane, no ColBERT rescoring, no prefetch funnel.
- **Why:** it is the **only** lane without hybrid retrieval, and it serves the *overview*
  questions — the ones with the worst ranking (MRR 0.191). It is also a direct deviation
  from the course's "hybrid is the default".
- **Note:** no rationale exists in the code; this reads as an omission, not a decision.

### F3. Graph lane contributes a 100-character preview
- `graph_search` returns `text_preview = info["text"][:100]`, and the app appends
  `f"[Concept-linked] {text_preview}"` **directly** to the LLM passages — no per-lane
  summarization.
- **Consequence:** the graph lane hands the model ~100 chars per hit while the chunk lane
  supplies everything else. This is a plausible cause of the earlier observation that
  graph answers "look like the retrieved chunks": the lane is barely contributing.
- **Fix:** hydrate the full chunk text for graph hits, or summarize the subgraph properly.

---

## G. Graph — adopt the course's Memgraph analytics layer

The course teaches a Memgraph concept-graph branch (three-layer memory, adjacency matrix,
PPR, memory-guided QA) and a GraphRAG branch (entity-relationship extraction, community
detection, global/local/drift query modes). This project has the *storage* model right
(`Document/Page/Chunk/Concept` + `PART_OF/ON_PAGE/MENTIONS/RELATES_TO/PREREQUISITE_OF`)
but none of the analytics built on top of it.

| # | Item | Why it matters here |
|---|---|---|
| G1 | **PPR (personalized PageRank)** over the concept adjacency matrix | The course's answer to "which concepts actually matter for this query". Replaces the current fixed-hop walk. Already on the P2 list |
| G2 | **Community detection + community summaries** | Gives *overview* questions graph support, which they currently have none of (they fall back to RAPTOR, the weakest lane) |
| G3 | **Entity resolution** (merge duplicate concept nodes) | **This is the known bug**: `'orbit'` / `'Orbit'` / `'planetary orbit'` / `'Planetary Orbit'` are separate nodes, so most chunks tie at 1 matched concept. The course has a dedicated lab for exactly this step |
| G4 | **global / local / drift query modes** | To brainstorm — the project has one traversal mode. Drift is the interesting one for multihop |
| G5 | **Genuine multi-hop traversal** | `hop_distance` is currently a constant 0, so "multihop" is nominal |

---

## H. Course standards — compliance check (de-identified)

Standards the course states explicitly for retrieval, and where this project stands.
Architecturally the project is **at or beyond** the standard; the gaps are concentrated in
the final precision stage and in measurement.

| Standard | Status |
|---|---|
| Funnel: per-doc cost rises only as volume falls | ✅ (wider pools than the course's reference: 1000→500→250→100→20) |
| One collection, named vectors, nested prefetch in a single round trip | ✅ |
| Hybrid dense + sparse candidate generation in parallel | ✅ |
| Late-interaction model as a common judge across branches | ✅ (inactive only on file-backed Qdrant, and it logs that) |
| Cross-encoder last, and only ever sees a shortlist | ✅ |
| Batch the reranker's scoring call | ✅ |
| Cross-encoder trained on (query, passage) pairs with mined hard negatives | ❌ **zero-shot, never trained** — the one standard not met |
| Measure recall@N at **each** funnel boundary | ⚠️ measures @100 and @20 only — cannot see which stage leaks |
| Chunk sizes sane vs the reranker's 512-token window | ⚠️ 57 of 5,048 chunks exceed it (max 1,701) and are silently truncated |
| Use a modern cross-encoder | ✅ already on the recommended upgrade (`bge-reranker-v2-m3`) |

---

## Re-ingest ordering — what must happen before what

The question "do we re-ingest before fine-tuning?" — **yes, and the order is forced:**

1. **Re-ingest first** (E1/E2/E3 + F1/F2). Every ingestion change alters chunk ids,
   boundaries, embeddings and cards. Fine-tuning trains on *retrieved* passages, so
   training on the current chunks means training against a corpus that is about to change
   underneath it — the mined hard negatives would be mined from a retired index.
2. **Then the training-set build** (D1) over the new corpus, with a held-out split.
3. **Then the reranker fine-tune** (A1/D1).

**What does NOT need re-ingest:** the docstring fixes (E4), the card-embed-text code change
(F1 — code is done, it takes effect on the next index run), the metric/boundary work,
the gold-set rebuild (P0-9), and the graph analytics (G — Memgraph is built from existing
chunks; only entity resolution changes what is written).

**One dependency to watch:** the gold set's `relevant_pages` are page-level, so a
re-chunk does not invalidate them. But any query whose answer was only findable *because*
of the old boundaries may change behaviour — re-run the baseline after re-ingest and
re-record it, rather than comparing across the two.
