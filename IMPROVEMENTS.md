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
