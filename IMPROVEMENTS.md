# IMPROVEMENTS — tracked backlog

Everything known-but-not-yet-done, in one place so it can be taken in a single pass.
Each entry says **what**, **why it matters**, and **the evidence** — so nothing has to be
re-derived later. Add to this file rather than leaving a note in a commit message.

Last updated: 2026-10-17

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

### B1. Formula card: the explanation renders as mathematics ✅ FIXED 2026-10-16
- **What:** on a formula card, the whole `content` string was passed to `st.latex()`
  (`streamlit_app.py`, `render_math`, the `card_type == "formula"` branch). The content
  is `"<formula> where <prose explanation>"`, so the prose was typeset as maths: spaces
  collapse and letters go italic.
- **Symptom:** `a = F/m` renders correctly, then
  `whereaisthelinearaccelerationofthebody(m·s⁻²),Fisthenexternalforce…`
- **Fix (applied):** `_split_formula()` splits the card at the first **top-level**
  occurrence of the word `where`, and `render_math` renders the two halves with
  `st.latex()` / `st.markdown()`. Cards with no credible boundary are prose-led and fall
  back to markdown (where the delimiter/brace converters still typeset the maths embedded
  in them). Tests: `tests/test_frontend_formula_render.py` + the golden file
  `tests/data/formula_split_golden.json`.
- **Evidence — CORRECTED.** The original entry's numbers were stale (measured before the
  card-value filters removed ~3k cards). Re-measured on the live 1,534 formula cards:
  - **1,517 contain the word `where`** — *not* 1,516 containing `" where "`. Only **1,389**
    use the single-spaced separator; the rest are `" where:"` (colon + a bulleted list),
    `" where\n"`, `"\nwhere "`, `"\n\nwhere\n"` and multi-space forms. **Keying on
    `" where "` leaks 128 cards** — the splitter keys on the word.
  - **0 cards are "pure formula with no explanation"** — the claim of 18 pure cards is
    wrong. All **17** no-`where` cards are prose-bearing (`. Here …`, `Thus:`,
    `Definitions:`, or prose-led like "For two vectors \(a\) and \(b\) …"). They were the
    *worst* case, since the prose had nowhere to go but `st.latex()`. Handled by the
    markdown fallback.
  - **0** `where` occurrences are nested inside LaTeX in the live corpus (the
    brace-depth guard is still required — see the synthetic case in the golden file).
  - Verified end-to-end by capturing the `st.*` calls for all 1,534 cards:
    **1,513 render latex+markdown, 21 fall back to markdown, 0 expressions brace-unbalanced,
    0 `st.latex` arguments contain prose.**
- **Fixed alongside — a latent bug the split exposed.** The old wrapper-strip
  (`re.sub(r'^[\$\{\(]+|[\$\}\)]+$', '', …)`) was harmless while it ran on the whole card
  (whose tail is prose), but applied to the split expression it eats a real closing brace:
  **254 of 1,517 expressions end in `}`** (`\frac{..}{..}`) and were left unbalanced. No
  card in the corpus is wrapper-enclosed, so the strip was removed.
- **Root-cause note (still open, upstream):** the generator emits one unstructured string.
  The durable fix is for `formula` cards to carry the formula and the explanation as
  separate fields — that needs card regeneration, so it rides with §A1.

### B2. Study Cards: the two card categories still unruled — HALF DONE 2026-10-16
- ✅ **Already done in code** (found while working B1): `_STUDENT_CARD_TYPES`
  (`streamlit_app.py`) is `["formula", "definition", "question", "misconception",
  "example"]` — `summary`, `factoid` and `objective` are **already excluded from the
  student set** (the comment above it cites the reason: 5k–11k each, they crash the
  browser). So "candidate for exclusion from the student set" is settled by the code, not
  by a decision.
- ⬜ **Still open — an admin/product decision, not a code task:**
  - `summary` (RAPTOR summaries exposed as cards, titled "Summary") — nothing to
    self-test. It is admin-only today; the open question is whether it should exist as a
    *card type* at all.
  - `factoid` where `content == title` (a bare sentence echo, e.g. *"The simple lever is
    fundamentally reversible."*) — legitimate facts, but ~29k of them. Admin-only today;
    the open question is whether the admin view should rank/cap them rather than list
    them.
  Both need Bharath's call; neither blocks anything.

### B5. NEW 2026-10-16 (found while fixing B1) — formula expressions contain Unicode maths that is not valid LaTeX
- **What:** many formula-card expressions use Unicode maths characters rather than LaTeX
  commands: `∮_S \mathbf{E}` (∮), `∂²p/∂t² = c² ∇²p` (∂, ², ∇²), `\varepsilon_0 =
  8.854\times10^{-12}` (×, ⁻¹²), `m_μ = 206\,m_e` (μ, ₑ). `st.latex()` renders via KaTeX,
  which expects LaTeX markup — a Unicode superscript like `²` or `⁻¹²` inside a maths
  expression is not guaranteed to parse, and where it fails the card shows the raw source
  in an error colour.
- **Why it matters:** it is the same class of defect as B1 — content that *looks* fine in
  the store and renders wrong. B1's fix routes the explanation to markdown (where Unicode
  is fine); it does **not** clean the expression half.
- **Not measured yet:** how many of the 1,513 latex-rendered expressions actually fail
  KaTeX. Measuring it needs a KaTeX check, not a Python one — do that before "fixing" it.
- **Likely fix:** normalise the expression at render time (map `²`→`^{2}`, `⁻¹²`→`^{-12}`,
  `×`→`\times`, `∂`→`\partial`, …) or, better, have the generator emit LaTeX (folds into
  the B1 upstream note / §A1). Low cost, but **do not start without the measurement** —
  a blind normaliser can corrupt expressions that render correctly today.

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

#### B4a. Verified 2026-10-13 (P0-9 3c recon) — the cluster side, and the fork
- `GET http://10.0.10.70:8000/routes` advertises
  `colpali_models: ["TomoroAI/tomoro-colqwen3-embed-4b"]` and
  `colpali_endpoint: http://ansatz:8123/embed-image/v1/multivector-embeddings` — so ColQwen3 is
  the router's registered visual model, and its endpoint accepts **both** text and image
  (`input_type="auto"`).
- **But the endpoint is down.** Every request shape returns **HTTP 500 in ~3.2 s**: text with
  `input_type=auto`, with `input_type=text`, with `is_query=true`, plain `input`, and a real
  base64 page image. The `colbert` endpoint on the same router returns 200, so the router is up
  and the colpali upstream is the failure. **§B4's text-query path is blocked on the cluster,
  not on our code.**
- **Two ways to get the text-query path — not equivalent:**

  | option | work | re-ingest? | blocked on |
  |---|---|---|---|
  | (a) add `embed_query_text` to the local `colpali-v1.2` embedder (`colpali_engine` supports `process_queries`) | small | **no** — same embedding space as the stored page vectors | nothing; runs offline |
  | (b) swap the lane to ColQwen3 on the cluster | new HTTP client + config | **yes** — a different embedding space, so all 945 page images must be re-embedded (§I1) | the cluster serving the endpoint |

- **Do not** use `sv_ray_cluster_access` / `embed_colpali` — §I8: SupportVectors IP, "reference
  only, keep gitignored… not importable here (needs `svlearn`)". The repo's pattern is a direct
  HTTP client (`colbert_embedder.ClusterColBERTEmbedder`). **Session 3d owns this decision.**

**Decision taken 2026-10-13 (3d): option (a).** The cluster endpoint was re-probed and is **still
down** — `POST /embed-image/v1/multivector-embeddings` returns **HTTP 500 ("Internal Server Error")
in ~3.1 s on all five request shapes** (text `input_type=auto` / `=text`, `is_query=true`, plain
`input`, no `model`), while the **colbert** endpoint on the same host returns **200 in 0.15 s** — the
router is up, the colpali upstream is the failure. So (b) is blocked on the cluster, not on our code.
(a) was verified end-to-end **offline**: `colpali_engine`'s `process_queries` yields a
**(N_patches, 128)** matrix whose patch_dim matches the stored pages (128) and whose patches are
L2-normalised — same embedding space, no re-ingest. `ColPaliEmbedder.embed_query_text` now exists
(real + stub), and `evaluate_rag.run_visual_retrieval` drives it. **(b) stays a candidate for a later
lane-upgrade pass (§I1) once the cluster serves the endpoint.**

#### B4b. Verified 2026-10-13 (P0-9 3d) — the visual index holds THREE vectors per page
- `visual_knowledge_base` (local Qdrant) has **2,835 points for 945 pages — every page exactly 3×**,
  all under **one** `document_id` (`b2d9fb56`). Three Phase-3 runs each minted fresh `page_image_id`s
  (`save_page_images` deactivates old `PageImage` rows but never deletes their Qdrant points), so a
  visual search returns every page three times.
- **Effect (measured):** the top-20 of a visual search held only **7 distinct pages** — duplicate
  slots cap Recall@20 / Hit@20 / NDCG@20 for the whole visual lane. **Mitigated in code:**
  `run_visual_retrieval` now collapses repeats by `page_number` before slicing to `top_k`, so the
  metric is correct (20/20 distinct). The **index is still 3× too large** and the Streamlit visual
  search still returns the duplicates.
- **`clean_stale_visual.py` does not catch this.** It deletes points whose `document_id` is absent
  from `knowledge_base`, but all 2,835 points share one id. Worse, the local visual doc id
  (`b2d9fb56`) is **not** the text doc id (`5fcc9006`), so the script would flag the *entire* visual
  index stale and then hit its own guard and refuse (exit 2). The documented remedy covers stale
  *documents*, not duplicate *pages within a live document*.
- **Root fix (fold into the E1/E2/E3 re-ingest pass):** `save_colpali_embeddings` / the Phase-3
  orchestrator must delete a document's existing visual points before upserting — same shape as the
  text path. **Re-ingest: yes (visual only).** Until then, keep the page-level dedup in the eval lane.
- **Also open:** the visual doc id (`b2d9fb56`) ≠ the text doc id (`5fcc9006`) — the two indexes come
  from different ingests, so `page_number` is the only join key between them. Confirm this is
  intended before trusting any cross-lane visual number.
- **Cluster ≠ local (measured 2026-10-15, Session 4b).** The **2,835 / 3×** figure is the **local**
  index only. The **cluster** `visual_knowledge_base` (10.0.10.65, what the eval runs against) holds
  **1,033 points** — one doc (`6d55c52b`, the *same* id as the cluster `knowledge_base`), ~**914
  distinct pages** with ~**86 duplicate pages** in the first 1,000 (~9%). So the 3× defect does not
  apply to the cluster lane; there is a residual ~9% page duplication. The eval lane dedupes by
  `page_number` regardless. The "local doc id ≠ text doc id" caveat above is **local-only** — on the
  cluster the visual and text doc ids match.
- **✅ Fixed in code 2026-10-14 (the UI text-query work).** Both halves are now closed, though the
  *existing* 2,835 points are untouched:
  - **Read path** — `DocumentStore.visual_search` collapses duplicate pages itself (over-fetches
    `limit × 5`, keeps each page's best occurrence, returns `limit` distinct pages). The UI and the
    eval lane both stop showing a page 3×. `dedupe_by_page=False` is the escape hatch.
  - **Write path** — `save_colpali_embeddings` now deletes the `(document_id, page_number)` it is
    about to write *before* upserting, so a re-ingest **replaces** a document's pages instead of
    adding another full copy. Keyed per page, so a partial re-ingest touches only its own pages.
  - Tests: `tests/test_visual_index.py` (4).
  - **Still 3× in the live index.** The fix prevents *new* duplication; it does not remove the
    1,890 existing duplicates. **The re-ingest is the chosen path — no one-off dedupe script was
    written.** See "Visual-index cleanup rides along with the re-ingest" at the end of this file for
    the verification step (and the trap where the re-ingest mints a new visual `document_id`).

#### B4e. Open 2026-10-14 — the visual score threshold is image-calibrated; a text query needs its own
- `visual_score_threshold` (**0.58**) was calibrated for **image** queries. `visual_search` divides
  the MaxSim sum by the query's own patch count to get a mean-best-cosine, so the *scale* depends on
  how many patches the query has. An image is a fixed grid (~1031 patches); a short **text** query
  yields far fewer, so its mean-best-cosine sits on a different scale — the 0.58 image threshold
  drops nearly every page.
- **Consequence for the new UI text path:** it **ranks, not filters** (`score_threshold=0.0`) and
  displays the cosine, rather than silently returning "no results" against an image-calibrated bar.
- **Fix (needs a run, not a decision):** calibrate a separate text threshold from the **33 labelled
  visual queries** — run `run_visual_retrieval` over them and take the knee of the score
  distribution. Until then the text path is unfiltered.
- **Not blocking**, but any visual-lane number is threshold-dependent, so pin this before comparing
  the visual lane across configs.

#### B4f. RESOLVED 2026-10-16 (P0-9 4b) — the visual lane could not run offline: ColPali's base model was not cached
- **What:** `evaluate_rag.py` step 4 reached the visual lane and then spent **~27.7 min per visual
  query** doing HuggingFace retry-backoff, scoring **0** on every one. Cause: the cache holds only
  the **LoRA adapter** `vidore/colpali-v1.2` (`adapter_config.json` + `adapter_model.safetensors`),
  not its base `vidore/colpaligemma-3b-pt-448-base` — which is absent from the machine entirely
  (`~/.cache/huggingface/hub/` has no `colpaligemma` entry), and `huggingface.co` is unreachable
  (DNS fails). So `ColPaliEmbedder` cannot construct and `run_visual_retrieval` returns nothing.
- **Evidence:** `logs/p0-9/session4b_step4_aborted.log` — first visual query at 22:18, ~27.7 min
  apart thereafter; `store.visual_search failed (timed out)`; recall@20 = 0.000 on every visual q.
- **Why it contradicts §B4a:** §B4a recorded option (a) as "verified end-to-end offline". That
  verification must have run while the base model was present (or online); it is not present now.
- **Fix (a prerequisite, not a decision):** obtain `vidore/colpaligemma-3b-pt-448-base` into the HF
  cache (or point `COLPALI_MODEL` at a local path that bundles the base), then the lane loads offline.
  Until then **run step 4 with `--skip-visual`** and report the visual lane as *unmeasured*, not 0 —
  a 0 would read as "the lane retrieves nothing", which is false.
- **Also:** set `HF_HUB_OFFLINE=1` / `TRANSFORMERS_OFFLINE=1` for offline eval runs, so a missing
  model fails **fast** instead of burning ~27.7 min of backoff per query. Every eval script should
  run offline by default; nothing here should phone home.
- **Not blocking the text/abstention half** of the pre-registered decision — that is the text lane
  and runs without ColPali.
- **✅ RESOLVED 2026-10-16 (P0-9 4b).** `vidore/colpaligemma-3b-pt-448-base` was downloaded into the
  HF cache (5.5 GB, 8/8 files; HuggingFace reachable again) and `ColPaliEmbedder` verified loading
  **offline** (`HF_HUB_OFFLINE=1`; `embed_query_text` → 23×128, L2-normalised). The visual lane then
  ran against the **cluster** index (`visual_knowledge_base` @ 10.0.10.65, 1033 points / 945 pages)
  and is **measured for the first time**: 33/33 queries, **R@20 0.960**, R@100 0.836, Hit@20 1.000,
  MRR 0.914, NDCG@20 0.891 — `data/eval_results/p0-9-gold-v2-visual_2026-10-17_0410.md`. The lane is
  no longer "unmeasured"; §I10 records the OOM that the first attempt hit.

#### B4g. Verified 2026-10-16 (P0-9 4b, offline) — the index-page hypothesis is REFUTED for the funnel's overview lane
- **What was hypothesised:** the index/back-matter pages pollute the overview lane's retrieval and
  explain its bad MRR (0.191), so ranking work (P1 item 10) should not start until they are excluded.
- **Measured (no cluster needed):** counted back-matter pages (`page_number >= 937`, §B4's
  `back_matter_start`) in every query's top-20 from the **pre-fix** funnel artifacts
  (`git show 12e0dd5:logs/p0-9/v2_rerank.json`, 133 text queries):
  overview B5b **2/625 slots = 0.32%**, factual 1.66%, multihop 0.68% — overview is the
  **least** polluted type, not the most; only **2 of 40** overview queries carry a back-matter page
  at all (`ovw-012`→p942, `ovw-049`→p950). The reranker arm is the polluted one (overview B6
  2.11%, factual 2.92%) — consistent with §D8's arm asymmetry, not with an overview-specific effect.
- **Consequence:** the index is **not** the cause of overview MRR 0.191, so P1 item 10 need **not**
  wait on a back-matter fix. Ranking should be driven off the ceiling-normalised numbers (§D9)
  as already planned. The §D8 bound (`max_content_page`) is still worth keeping; it is simply not
  the ranking lever.
- **Caveat:** this bounds the *funnel* artifacts. The 0.191 MRR itself comes from the v1
  `evaluate_rag` run (23 queries, 8 pre-3c overview) — a different, superseded set that predates
  the bound; it cannot be re-tested from artifacts on disk. Treat the refutation as
  "not the cause of the funnel's overview numbers", and re-check on v2's own per-type MRR once
  step 4 runs.

#### B4c. Verified 2026-10-13 (P0-9 3d-ii) — the visual judge is over-permissive; the criterion must be strict
- **What:** the 3d-ii visual judge variant (D8's "does this page show the described
  figure/table/graph?") is answered by the 8B VLM (`Qwen/Qwen3-VL-8B-Instruct`) with **YES for
  essentially any page carrying a figure**. Measured on `vis-001` ("Show me the figure that
  displays water magnified one billion times"): a loose prompt returned **266 YES pages** — the
  label became "every figure page in the book", so Recall@20's denominator was meaningless.
- **Why:** the same failure class as the index-page false hits (§B4 / Session 3b) — an 8B VLM
  reads "does this page show a figure/diagram/graph/table" as "does this page show *a* figure",
  not "the *specific* figure described". Prompt wording is the only lever that moved it.
- **Fix (applied in `_VISUAL_JUDGE_PROMPT`):** force the model to work out *which* figure is
  printed on the page (caption number + subject) and to require a **subject AND quantities/axes
  match**; state explicitly that "a different diagram is NO even if it is also a physics
  diagram". Verified on the probe: p37 (the true page) YES, p38 (steam, same chapter) PARTIAL,
  p800/p504/p532 (unrelated figures) NO. `vis-001` → `[37]`, `vis-002` → `[77]`.
- **Durable note:** this is a *prompt-level* fix, so it is exactly the kind of thing Session 5's
  human verification must check — a stricter criterion that the VLM still under-applies would
  silently re-widen the labels. If the visual lane is kept, add a labelled-page probe like
  `tests/test_backmatter_gate.py` pins the index gate.
- **Related — the term sweep explodes on generic visual vocabulary.** A visual question's
  content words are dominated by the *request* ("show", "figure", "diagram", "fig", "graph")
  plus common nouns ("water", "angle", "one", "times"), so the term-bearing sweep selected
  ~600 pages/query and the scan cost was unbounded. Fixed by (a) dropping a term that appears
  on more than `_TERM_MAX_DF` (25) pages and (b) adding an **anchor window** (`_VISUAL_ANCHOR`,
  ±4) around the question's `source_page`, because the figure is on that page or adjacent and a
  stride-4 sample alone misses it ~75% of the time. Average pages/query fell ~694 → ~240.

#### B4d. Verified 2026-10-14 (P0-9 3d-ii) — visual label hygiene: 33 usable of 40; the strict criterion × a YES-only filter
- The 3d-ii scan produced **40** visual questions; **33 are usable** after hygiene (23 single-page,
  7 two-page, 2 three-page, 1 four-page labels). Within the 30–40 target.
- **6 left uncalibrated** (`relevant_pages: []`): `vis-004, 009, 016, 017, 023, 025`. Two distinct
  causes, both in the log:
  - **`vis-004`, `vis-025` — correct page found, graded PARTIAL, then discarded.** The anchor window
    reached the true page and the strict VLM named the right figure ("Figure 33-6, which includes
    diagrams of incident, reflected…") but returned **PARTIAL**, and `expand_gold_labels.py:88`
    keeps **YES only** (`found = {h["page"] for h in hits if h["verdict"] == "YES"}`) — so a
    correct-but-PARTIAL verdict yields an empty label. The §B4c strict criterion is now *too* strict
    for an under-specified question.
  - **`vis-009, 016, 017, 023` — "No hot zones found in coarse pass."** Even the ±4 anchor window
    returned NO on every page, despite the source page carrying an `<!-- image -->` marker. Either
    the caption Docling attached does not match the *rendered* figure, or the 8B VLM cannot read the
    small caption text on the page image.
  - **These are NOT generator hallucinations.** The source pages carry the figures the questions
    describe (checked against the `chunks` table), so the gap is in the *scan/judge*, not the
    generator. A re-scan that credits a *correct* PARTIAL as a hit would recover them.
- **1 dropped as non-specific:** `vis-024` ("Show me the diagram of the wave signals.") scored
  **71 YES pages** — every wave/shock diagram in the book (Figs 51-2, 51-5, 51-9, 51-10, 51-12…).
  A vague question has no single answer page, so no threshold or cap rescues it: the **generator
  must reject non-specific questions** (a specificity gate), or the question must name the figure.
  Dropped (emptied + `calibrated: false`); the raw 71-page label is preserved in
  `logs/p0-9/run_session3dii_visual_scan.log`.
- **Consequence:** the visual lane's metric denominator is **33**, not 40. The 6 uncalibrated are not
  lost work — they are the evidence that the *judge criterion* needs a second pass. **Deferred** (own
  item, needs cluster VLM calls): either accept a correct PARTIAL, or regenerate with a
  specificity-gated prompt.
- **Minor (fold into §D4):** the anchor window (`validate_eval_calibration.py:785`) uses
  `source_page` — which is **DB page numbering** — as if it were **PDF** numbering (line 98's comment
  says the window is PDF). The ±4 window still covers the true page at the measured ≤+2 offset, so no
  label is lost to it, but the window is centred wrong; fix with §D4's numbering normalisation.

### F4. ColBERT: replace-with-RRF is the wrong comparison — **fuse** them instead
- **Measured** (`scripts/why_colbert.py`, 23 queries, same 100-candidate union pool):

  | ordering of the pool | recall@20 |
  |---|---|
  | RRF | **0.588** |
  | dense_768 alone | 0.576 |
  | ColBERT MaxSim | 0.551 |
  | **RANDOM (the floor)** | **0.351** |

- **"Is the pool uniform, so no reordering can help?"** — **No.** Random scores 0.351
  against 0.588 for RRF, so ordering carries a lot of signal. The pool is not the
  constraint.
- **"Is 128-d too coarse?"** — **Partly.** ColBERT *does* separate candidates on a
  labelled page from the rest (mean score gap **+0.40**), so it is not blind. But the gap
  is only ~17% of the score spread (2.31), it is **negative for 2 of 23 queries**, and it
  is fragile: the deficit is dominated by **raptor-002**, where ColBERT loses all 9
  relevant pages. Excluding that one query the gap narrows from 0.037 to 0.018.
- **The real explanation is structural.** RRF *fuses two rankers* (dense + sparse).
  ColBERT *replaces* them with a single MaxSim score. So the comparison was never
  "reranker vs reranker" — it was **fusion of two signals vs one signal**, and one signal
  loses. ColBERT's own separation is too weak to make up for the fusion it discards.
- **Actionable fix: don't replace RRF with ColBERT — add it as a third contributor.**
  Qdrant's nested prefetch accepts a ColBERT prefetch alongside the dense and sparse ones,
  so the outer `FusionQuery(RRF)` can fuse **three** rankings. ColBERT then contributes its
  signal instead of overwriting the other two. This is testable with the existing harness
  (one more `Prefetch` in `store._qdrant_search`).
- **Also worth noting:** dense alone (0.576) is close to RRF (0.588), so the SPLADE branch
  is adding little on top of dense here — consistent with B3's 0.885 vs B1's 0.895.

#### F4a. What the course materials actually say (checked 2026-10-06)

Asked to verify the recollection that the lecture notes propose a three-way RRF. **They do
not — as far as the notes record it.** `Labs/week_9/retrieval_funnel_ablation_study/` is
explicit about the merge:

- `docs/concepts/retrieval_funnel_philosophy.md:74` presents **two** resolutions to the
  incomparable-scores problem, and names **rank-based fusion (RRF)** first:
  *"Cheap, robust, no model needed; but it only reshuffles existing opinions, **adding no
  new evidence**."* The second is *"Rescoring with a stronger common judge — **the
  notebook's choice**"* (ColBERT, then the cross-encoder).
- `docs/architecture.md:240` files RRF under *"Fusion alternatives"*: *"An alternative shown
  in the Qdrant documentation is Reciprocal Rank Fusion (RRF) — a good discussion point
  **for when no strong reranker is available**."*

So the course's *documented* design is ColBERT-rescore (what this repo did before the
change), with RRF as the cheap fallback. **But the course's stated philosophy supports the
decision below**, because it frames the merge as the cheap half of one operation: *"merge
**and rerank** is one phrase in the funnel philosophy, not two: a merged pool without a
common judge is just a pile."* Fuse cheaply, let the strong judge do the real ranking —
which is exactly three-way RRF followed by a cross-encoder.

**And the course already documents our reranker finding.** Its self-assessment Q8 is titled
*"Cross-Encoder: Friend or Foe?"* and asks students to find the configuration where the
cross-encoder causes the **most noticeable F1 drop** (green bar shorter than blue). A
cross-encoder that reduces F1 is therefore an *expected* result in this course's own
ablation study, not an anomaly. That materially strengthens the case for testing the
reranker properly rather than removing it on n=23.

#### F4b. Decision (2026-10-06) — keep 3-way RRF **with** the reranker; defer the call

**Settled:** the funnel stays as three-way RRF **plus** the cross-encoder. The reranker is
**not** switched off. The final decision is deferred to a properly powered test after the
gold set (P0-9), the re-ingest, and reranker fine-tuning — on significance, not on n=23.

**Consequence, accepted knowingly:** the app's measured R@20 is therefore **0.569**, below
the 0.600 it was before the merge change. This is a deliberate intermediate state, not an
oversight — the merge is a strict improvement to the *retriever* (0.598 → 0.651) and the
reranker question is what is unresolved.

**Why deferring is the right call:** three independent measurements now say the zero-shot
reranker is a liability, but all three are on 23 queries, and the course's own ablation
study shows the cross-encoder's effect is *configuration-dependent* (sometimes helping,
sometimes dropping F1). One untrained reranker on a tiny sample cannot distinguish "the
reranker is wrong for physics text" from "this reranker is wrong because nobody trained it".
Fine-tuning + a powered gold set separates those two questions. **The target a fine-tuned
reranker must beat is now 0.651, not 0.598.**

**Two separable questions, worth not conflating:**
1. *Does a cross-encoder help at all here?* — answerable on the gold set with the **current
   zero-shot** reranker; needs no fine-tuning.
2. *Does a fine-tuned cross-encoder beat the raw fusion?* — needs the training set (D1).
Question 1 is the cheaper one and gates question 2.

**Required-N, measured 2026-10-12** (`scripts/required_n.py`, reconstructed from the 23-query
per-query page sets against `data/eval_queries.json`):

| comparison | σ_d | N @ δ=0.05 | N @ observed effect |
|---|---|---|---|
| **reranker** — retriever's own top-20 → after cross-encoder (`rrf3` run) | **0.2315** | **169** | **62** @ δ=0.083 |
| merge — ColBERT-outer vs 3-way RRF, final R@20 | 0.1184 | 45 | 16 @ δ=0.083 |

σ_d is the SD of the **per-query difference** (not of the scores), so it differs per comparison;
the reranker comparison is the noisier one and it governs the gold-set size. General form for the
reranker: **`N = 0.4206/δ²`** where `0.4206 = (z_a+z_b)²·σ_d²` for α=0.05, power=0.80. The 169 at
δ=0.05 is under the 200 "report-it-as-a-finding" threshold; the observed effect (0.083) needs 62.

**Label error rate (Task 7 / Session 5) — ⬜ PENDING, protocol pre-registered 2026-10-16.**
The plan's Task 7 records the human-verified label error rate here. It is now prepared and needs
no cluster, so it can run while Session 4b step 4 is blocked on the outage:

- protocol (sample, verdicts, consequences): `.hermes/plans/2026-10-16-p0-9-5-verification-protocol.md`
- sheet to fill in: `data/gold_v2_review.md` — **30 queries, 6 per stratum** (factual / multihop /
  overview / visual / negatives), generated by `scripts/build_review_sheet.py`
  - **queries are printed verbatim (fixed 2026-10-17).** `_cell` capped every cell at 88 chars, so
    20 of the 30 sampled queries were cut mid-clause (`… · topic: …`) and could not be judged —
    the sheet's one job. **127/200** v2 queries exceed 88 chars (median 113, longest 405), so this
    was the common case, not an edge. `_cell` now only collapses newlines and escapes `|` (both
    still required: a raw `|` breaks the row and the scorer's `parts[5]` verdict split); topic
    tags are no longer capped either. Verified: all 30 query cells byte-equal the source query,
    zero ellipses, scorer still parses 30 rows / 5 strata. No re-ingest — sheet-only artifact.
- score it: `uv run python scripts/score_review_sheet.py` (per-stratum + pooled, 95% Wilson CI;
  refuses to report while any row is blank)
- **the sample is stratified, not the plan's uniform 25** — the five strata came from five
  different judge paths, and uniform-25 under-samples the visual and negative lanes (the two with
  known label uncertainty). Deviation logged in the protocol §10.
- record here as `label error rate = X/N = Y% (95% CI …)`, per-stratum breakdown, then apply the
  pre-registered consequence (§8 of the protocol).

*(Note: HANDOFF's "N_min = 31 for the 0.083 effect" is a **different criterion** — the n at which a
single config's 95% CI half-width equals 0.083, i.e. `(1.96·σ_d/δ)²` — not the paired-power N. The
paired-power figure is 62. Recorded so the two are not conflated.)*

#### F5. ColBERT queries were never query-encoded — F4's comparison was unfair

**Found 2026-10-06, fixed in `b4cb637`.** `ClusterColBERTEmbedder` sent the parameter
`encoding_type`; the SV cluster endpoint takes **`is_query`** (bool) and **silently ignores
`encoding_type` entirely.** Measured against the live cluster:

| payload | query matrix |
|---|---|
| `encoding_type='query'` (what we sent) | 8×128 — identical to the document encoding |
| `encoding_type='document'` | 8×128 |
| **`is_query=True`** (correct) | **32×128** — query padding + augmentation |
| `is_query=False` | 8×128 |

`query-encoded == doc-encoded` → **True**. So every query we ever encoded went through the
**document** encoder, discarding precisely the query/document asymmetry late interaction
exists to exploit. After the fix `embed_query()` returns `(32, 128)` live.

**Why this matters beyond the bug:** F4's conclusion — *"RRF beats ColBERT because RRF is a
fusion and ColBERT is one signal"* — was measured with ColBERT's queries mis-encoded.
**That was not a fair comparison**, and the conclusion needs re-measuring on the fixed code
(see F5a). The three-way-RRF decision may still be right; we can no longer claim ColBERT was
given a fair run.

**No re-ingest required.** Documents were sent *without* `is_query`, so the server default
(`is_query=False`) gave them the correct document encoding **by accident**. Only the query
side was wrong — so this is a pure query-time fix. This is the one lane upgrade in the
current backlog that costs nothing to adopt.

**Two more defects from the same sweep:**
- `_post` iterated `resp.json()["data"]` **by position and ignored `item["index"]`**, which
  the server does return. A reordered batch would have silently attached embeddings to the
  wrong texts. Now sorted by index.
- `scripts/preflight.py` probed the same endpoints with the same wrong parameters
  (`encoding_type`, `top_n`), so its ColBERT and rerank checks were not exercising the real
  call shape.
- `reranker.py` sent `top_n`; the rank endpoint ignores it (`top_n=2` over 6 documents
  returned all 6, while `top_k=2` returns 2). **Not a correctness bug** — `rerank()` slices
  to `top_k` itself — but it moved every candidate over the wire. Fixed.

**Test gap that let it survive:** `tests/test_colbert_embedder.py` covered only
`StubColBERTEmbedder`, never the cluster class. New `tests/test_colbert_cluster_payload.py`
(6 tests) pins the payload contract, the response-order contract, and the documented
8-input batch limit.

#### F5a. Re-measured after the fix — the fix is correct, the effect is unresolvable

Same 23 queries, same pinned HyDE cache, merge A/B re-run on the fixed code:

| merge | R@20 after fix | R@20 before | delta |
|---|---|---|---|
| ColBERT as outer query | 0.578 | 0.600 | **−0.022** |
| RRF dense+sparse *(no ColBERT)* | **0.589** | **0.589** | **±0.000** |
| RRF dense+sparse+ColBERT | 0.567 | 0.569 | −0.002 |
| RRF 3-way, no reranker | 0.602 | 0.651 | **−0.049** |

**The sanity check passes:** `rrf2` is byte-identical (0.589 → 0.589), exactly as it must be
— that lane contains no ColBERT at all. So the harness is measuring the change and only the
change.

**The fix is verifiably correct.** The corrected query matrix is `(32, 128)` with **every row
unit-norm, 24 distinct rows in the tail, and mean pairwise cosine 0.56** — i.e. genuine
**query augmentation** (ColBERT appends `[MASK]` tokens and the model fills them with learned
expansion terms). Those rows are *meant* to participate in MaxSim. This is not padding to be
stripped; `num_tokens` reports 32 because all 32 are real. So the code now does what ColBERT
does.

**But recall moved slightly DOWN, and that is not resolvable at n=23.** The largest move
(−0.049) is roughly one standard error for this query set (`σ_d = 0.23`, so `SE ≈ 0.05`).
The honest reading:

- **F4's conclusion is neither confirmed nor overturned.** It was measured on a mis-encoded
  ColBERT, and the corrected ColBERT scores marginally *lower* on this sample — but the
  sample cannot distinguish −0.05 from 0.
- **Keep the fix regardless.** A query should be query-encoded; a mis-encoding scoring
  marginally higher on 23 queries is not a reason to preserve a bug. If the powered gold set
  later shows augmented query encoding consistently *hurts* on physics prose, that is a real
  finding about ColBERT-on-this-domain — but it must be shown on n≥120, not inferred here.
- A plausible mechanism worth testing later: augmentation adds generic expansion terms that
  may **flatten** the ranking for short factual queries. Untested.

**This is now the fifth conclusion blocked by n = 23** (reranker, merge/F4, ColBERT
encoding, abstention, and every per-type claim). The gold set (P0-9) is the bottleneck for
all of them.

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
- **v2 update (2026-10-14):** the v1 numbers in this entry (0.598 / 0.561, and the 0.895→1.0 vs
  0.561→0.895 gaps) are **not comparable to v2** — different query set, and v2's label sizes make
  R@20 mean something different (§D9). On v2 the same pair reads: retriever's own top-20 **0.4495**
  → reranked **0.4389**, CI on the paired difference [−0.0304, +0.0091] → **unresolved at n=133**;
  the loss is concentrated in the **factual** lane (−0.0469, CI [−0.0787, −0.0152] → resolved).
  So the "must beat X to earn its place" threshold is **0.4495** on v2, not 0.598.

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

### D4. Gold labels mix two page numberings (DB vs PDF) — label precision
- **What:** `relevant_pages` is built from two coordinate systems. `generate_gold_dataset.py`
  sets it from the DB chunk `page_number`; `expand_gold_labels.py` unions in the PDF page
  numbers returned by `scan_query`. Measured (Session 3b): those two numberings differ by 0 or
  −1 on ~45% of pages (425 unambiguous pages: 232 at 0, 192 at −1).
- **Effect:** about a one-page of label noise. The union tends to over-include, so it nudges
  recall *up* rather than down — not alarming, but it is part of why recall is not 1.0 and it
  caps how finely a reranker delta can be read.
- **Fix (do before Session 4 assembles v2):** normalise both sources to one numbering (or have
  `scan_query` record the DB `page_number` it corresponds to) and re-derive `relevant_pages`.
- **Not blocking**, but it should be settled before the A/B numbers are believed.
- **Visual-lane measurement (3d-ii, 2026-10-13):** the offset is not only 0/−1. Matching a
  distinctive phrase from each image-marker chunk against the PDF text (150 chunks), the
  chunk's content landed on PDF pages at delta **{0: 101, +1: 25, +2: 10, −1: 8}** — so the
  DB→PDF offset reaches **+2**. Consequence for the visual lane: the generator's
  `source_page` is stored as **traceability only, never a label**; visual `relevant_pages` are
  filled *exclusively* by the fitz scan, whose 1-based PDF page index is the same key the
  `visual_knowledge_base` payload uses (`page_number`, `image_key` `page_0532.png` ↔ p532).
  The visual lane is therefore free of this defect; the text lane is not.
- **Re-measured 2026-10-14 (Session 4b) — the premise needs revising.** The DB `page_number`
  and the fitz PDF page index are the **same coordinate system** (both run 1…~968), not two
  numberings to reconcile; `chunks` stores **no PDF-page field** (columns: id, document_id,
  tenant_id, chunk_index, text, page_number, qdrant_point_id, char_start, char_end,
  token_count, version, is_active, created_at, updated_at), so there is nothing to join on.
  The 0/−1 is **chunk-boundary fuzz**: `SentenceChunker` merges text across PDF page
  boundaries, so a straddling chunk gets one `page_number` (where it starts/ends) and the
  label inherits it. Measured over the 425 unambiguous DB pages: a page's **first** chunk
  starts on PDF p−1 for **45%** (192) and on p for **55%** (232); its **last** chunk ends on
  p for **44%** (189), p+1 for **41%** (173), p+2 for **6%**, p+3 for **2%**. Whole-page
  span: **57%** of DB pages sit on one PDF page, **35%** span two, **6%** span three (e.g.
  DB page 252's 13 chunks land on PDF 252, 253, 254).
- **Consequence:** there is no shift to apply — the fuzz is inherent to the parser's
  chunk→page assignment, so re-deriving `relevant_pages` cannot remove it; only a re-ingest
  that assigns `page_number` per PDF page can (fold into the E1/E2/E3 pass). The mixing is
  **symmetric across the rerank / no-rerank arms** (both read the same labels), so it widens
  the delta's CI rather than biasing one arm. **Session 4b stopped here** pending the owner's
  decision: reframe §D4 as an inherent noise floor and proceed, attempt an approximate
  chunk-derived PDF→DB remap, or defer to the re-ingest. **No labels were changed.**
  **Decision (2026-10-14, owner): reframe.** Treat this as an inherent ±1 noise floor — do
  **not** re-derive `relevant_pages` (no edit can remove the fuzz) and do **not** block the
  funnel re-run on it. §D4 is hereby a *known, symmetric* label-noise floor, not an open
  defect; the durable fix (page numbers assigned per PDF page) folds into the E1/E2/E3
  re-ingest. Proceed to the Session 4b funnel re-run.
- **✅ DURABLE FIX LANDED AND VERIFIED — P1 Steps 3+6 (2026-10-17).** The parent-aware path (E2/E1)
  assigns `page_number` from Docling's per-element provenance (`prov.charspan`/`page_no`) at the
  child's start offset, not from a chunk-start page map. Measured with
  `logs/p1/step6/probe_page_numbering.py` against an **independent extractor** (PyMuPDF page text
  via `PageStore`; the numbers came from Docling), head-only, on the 968-page book, **both paths on
  the same unit**:

  | path | sampling | n | offset 0 | offset −1 | other |
  |---|---|---|---|---|---|
  | old (deployed DB) | all chunks | 5047 | 1888 (71.5%) | 333 (12.6%) | +1: 322, +2: 73, +3: 20, −2: 3 |
  | old (deployed DB) | first per page | 756 | 230 (54.4%) | 192 (45.4%) | +1: 1 |
  | **new (parent-aware)** | **all children** | 3796 | **2150 (99.95%)** | **1 (0.05%)** | — |
  | new (parent-aware) | first per page | 933 | 547 (100%) | 0 | — |

  The offset collapses to 0 on both units; **0** children without a page. The 1,645 children whose
  head PyMuPDF cannot locate (serialisation difference) are reported separately; their mid/tail
  fallback shows **one** −1, so no wrong-page cluster hides there. An independent reviewer refuted
  the first version of this measurement for comparing unequal samplings; the fix (measure both
  units on both paths) also showed the recorded "45% at −1" was a first-chunk-per-page artifact —
  over **all** its chunks the old path spreads both ways (71.5% at 0, 12.6% at −1, 12.2% at +1,
  tail to ±3). Evidence: `logs/p1/step6/README.md`. **Not yet deployed** — `store.ingest_document`
  still uses the legacy path until Step 7; the funnel/label numbers move only after the Step 8
  re-ingest, and §D13's reranker ablation is the first thing that reads them.

### D5. `generate_negatives.py` verifies at stride 15 — weaker than the Session 3b re-scan
- **What:** `generate_negatives.py` accepts a candidate if its own two-pass scan (stride 15,
  then ±8 dense) finds no YES page. But a near-miss fact can sit on a page the stride never
  reaches, so the generator re-accepts negatives that are genuinely answerable. Verified
  2026-10-13 (P0-9 3c): the grown run accepted 36/36, and the term-bearing re-scan then found
  **two** answerable ones — `neg-nea-004` (carbon-14 half-life, **p107** — already known from
  Session 3b) *and* the newly added `neg-nea-010` (age of the universe, **p106/157**).
- **Effect:** a grown negatives file is *less* trustworthy than the pruned one it replaces.
  Committing it unmodified would have put two answerable queries into the abstention metric —
  the exact defect Session 3b existed to fix.
- **Fix (now the required procedure):** after every `generate_negatives.py` run, always
  `logs/p0-9/verify_negatives.py` (term-bearing sweep, ±2 neighbours) then
  `logs/p0-9/prune_negatives.py` (drop content-YES, flag content-PARTIAL as `needs_review`).
  `verify_negatives.py` keeps a per-seed term list — extend `TERMS` whenever `_SEEDS` grows,
  or the new seeds are silently skipped.
- **Better fix (not done):** fold the term sweep into `generate_negatives.py` itself, so the
  generator cannot accept a candidate it has not swept. Until then the two-step procedure is
  a manual invariant that is easy to forget.

### D6. Verified 2026-10-14 (Session 4 pre-run) — gold labels can fall outside the retrievable window
- **What:** retrieval is bounded to the content region — `min_content_page` (**30**) …
  `max_content_page` (**936**). A gold label outside that window can never be retrieved, so the
  query measures nothing. Session 3b checked **back-matter** labels and found none; **front
  matter was not checked**, and that is where the gap was.
- **Measured (168 answerable in v2, window [30, 936]):**
  - **2 queries labelled entirely below the window** — `gold-001`, `gold-002`, both **page 3**
    (the preface), both factual questions generated from a preface chunk ("the year Feynman
    received the Oersted Medal for Teaching"; "how a Scientific American reviewer described the
    Lectures"). These are **unanswerable by construction**.
  - **4 queries partly outside** (one unreachable page each, all multihop): `gold-081` (p23),
    `gold-087` (p24), `gold-088` (p24), `gold-094` (p22). Each has its recall capped below 1.0
    because `compute_retrieval_metrics` counts *all* labelled pages in the denominator.
- **How it surfaced:** the first v2 `--limit 2` probe scored **0.000 recall on every lane** for
  `gold-001`/`gold-002`. The retriever was fine — `gold-003` (label p30) was in the top-20 — the
  labels were simply unreachable. Undetected, this bakes ~1.2% of dead recall into the headline.
- **Fix (applied):** `build_gold_v2.py` now **drops** an answerable entry whose labels fall
  entirely outside the window and reports the ids. The 4 partly-outside are **kept and noted
  here**; their unreachable page is left in the label (stripping it is a label edit, deferred).
  Guard: `tests/test_gold_schema.py::test_answerable_labels_are_retrievable`.
- **Root cause (upstream, no re-ingest):** the generator samples chunks with no content-region
  bound, so a preface chunk yields a preface-labelled question. Fold into
  `generate_gold_dataset.py`: skip chunks below `min_content_page` / above `max_content_page`
  when sampling — exactly as `image_marker_pages` already does for the visual path.
- **Related:** §D4 (DB↔PDF numbering) is a *different* label-precision defect; both are label
  validity, neither is a retrieval problem.

### D7. `required_n.py` silently falls back to the v1 query file
- **What:** `--queries` defaults to `data/eval_queries.json` — **v1**, 30 entries, ids `vec-NNN`.
  v2's ids are `gold-NNN` / `ovw-NNN` / `vis-NNN`, so the id join matches nothing: the script
  prints *"only 0 shared queries — cannot estimate; check the JSON shape"* and **exits 1**.
- **Measured (2026-10-14, Session 4):** `logs/p0-9/run_session4_v2.sh` step 3 does **not** pass
  `--queries`, so the pre-registered powered decision silently did not run — it looks like a
  completed step in the run script. The identical command with
  `--queries data/eval_queries_v2.json` works: n=133, SD_d **0.1164**, SE 0.0101, required N **43**
  at δ=0.05 (and **934** at the observed 0.011).
- **Why it matters:** the one number the whole session exists to produce comes from this script.
  A wrong default turns it into a no-op that produces no artifact and no error anyone notices.
- **Fix:** make `--queries` **required**, or default it to `data/eval_queries_v2.json`; and make
  the <5-shared-queries path exit non-zero *and* be checked by the run script. No re-ingest.
  **✅ Applied 2026-10-14 (Session 4b, pending commit):** `--queries` is now `required=True`;
  `run_session4_v2.sh` passes `--queries data/eval_queries_v2.json` to step 3. Verified: the
  command now reproduces n=133, SD_d 0.1164, required N 43 at δ=0.05.

### D8. The funnel does not apply `max_content_page` — it does not mirror deployed retrieval
- **What:** `funnel_boundary_recall.py::build_filter` (lines 52–54) and its local post-filter
  (lines 202–204) apply `min_content_page` **only**. `store.py` applies **both** bounds
  (lines 198–208 in the filter, 240–249 in the post-filter). So the funnel's candidate pools
  contain index/back-matter pages the app now excludes — although the module docstring claims it
  replays each stage "mirroring `store._qdrant_search` exactly".
- **Measured on the v2 run** (`max_content_page` = 936): back-matter pages (>936) occupy
  **43 of 2,001** top-20 slots in the **rerank** arm (2.15%, 30 queries affected) but only
  **19 of 1,991** in the **no-rerank** arm (0.95%, 10 queries). Gold labels carry no back-matter
  pages (§B4b), so those slots are pure waste — and the **reranker is the arm that promotes them**
  (e.g. `gold-003` no-rerank top-20 contains p944/p950; `gold-004` contains p940/p947).
- **Why it matters:** every funnel number ever reported — including v1's 0.895 / 0.561 in §D2 —
  was measured on a candidate pool the product does not serve, and the defect is
  **arm-asymmetric**, so it biases the reranker comparison specifically.
- **Fix:** add the upper bound to `build_filter` and to the local `post()` filter. Two lines.
  No re-ingest. **✅ Applied 2026-10-14 (Session 4b, pending commit):** both now apply
  `max_content_page`, mirroring `store.py`; `run_session4_v2.sh` also aborts on a failed step
  (`set -e` + `ERR` trap) so a broken step can no longer fall through to the next.

### D9. Recall@k is capped by the label denominator — report it against the ceiling
- **What:** `R@20 = |top20 ∩ rel| / |rel|`, so any query with more than 20 relevant pages has a
  ceiling of `20/|rel|`. v2's overview labels were scan-expanded book-wide (mean **73.8**,
  median 56.5, max **314** pages) → that lane's mean ceiling is **0.3992**. The whole v2 text
  lane's mean ceiling is **0.8016**. v1's 23 queries had a mean label size of **3.4** (max 13) →
  ceiling **1.0000**.
- **Measured (2026-10-14):** v2 overview R@20 0.1402 is **35% of its achievable 0.3992**, not 14%
  of 100%. And the apparent regression from v1 is mostly this arithmetic: v2's 88 text queries
  with ≤20 labels (structurally v1-like) score B5b **0.6037** against v1's recorded **0.636** —
  a ~0.03 gap, inside the label-noise (§D4) and HyDE bands, not 0.19.
- **Why it matters:** **any** cross-dataset or cross-lane comparison of R@20 is invalid unless
  normalised by the ceiling. This is also why the overview lane looks catastrophic while being
  merely unmeasurable at k=20 — the ranking work in HANDOFF P1 item 10 should not be driven by
  that raw number.
- **Fix:** report `R@20 ÷ (min(20,|rel|)/|rel|)` alongside the raw value, and/or use a k that
  scales with `|rel|` (R@`|rel|`) for the overview lane. Report-side only. No re-ingest.

### D10. RRF fusion is not bit-reproducible at the pool level, even with HyDE pinned
- **What:** with a shared HyDE cache, `B1`/`B2`/`B3` and `B5b` are byte-identical across the two
  arms of the v2 A/B (as they must be — they precede the reranker), but `B4_rrf_union_100` differs
  on **7 of 133** queries and `B5_colbert_100` on **2**. The top-20 (`B5b`) survived in every case,
  so the headline metric is unaffected.
- **Measured:** e.g. `gold-024` gets p529 in one arm and p810 in the other at B4; `gold-044`
  p223 vs p95; `ovw-009` loses p41 at B5.
- **Why it matters:** ARCHITECTURE §12 attributes non-reproducibility to HyDE at temperature 0.3.
  **Pinning HyDE does not fully fix it** — a second, smaller source sits at the fusion stage. It is
  below the current effect size (pool-level, never top-20), but "same command, same cache" is not
  a guarantee, and it sets a floor under any future A/B claim.
- **Fix (not done):** investigate Qdrant RRF tie-breaking / prefetch ordering. Until then, note it
  in every A/B rather than assuming determinism. No re-ingest.

### D11. `store._qdrant_search` turns a cluster outage into a per-query `UnboundLocalError`
- **What:** the schema-detection block (lines ~276–284) did:
  ```python
  try:
      col_info = self._qdrant.get_collection(cfg.qdrant_collection)
      vectors_cfg = col_info.config.params.vectors
      has_new_schema = isinstance(vectors_cfg, dict) and "dense_64" in vectors_cfg
  except Exception:
      has_new_schema = False          # vectors_cfg never assigned
  if not has_new_schema:
      using = "dense" if isinstance(vectors_cfg, dict) ...   # UnboundLocalError
  ```
  When `get_collection` raises — which it does the moment the cluster is unreachable — the `except`
  sets the flag but leaves `vectors_cfg` unbound, so the **next line crashes on every query**.
- **Measured (2026-10-16, Session 4b step 4):** the cluster dropped before the run; **all 167
  non-visual queries** failed with `cannot access local variable 'vectors_cfg'`, so `evaluate_rag.py`
  exited `rc=0` having written an **empty report** (`0/0` scope, 0 judge calls). A connection outage
  surfaced as a misleading crash, and the run *looked* like it completed. Log:
  `logs/p0-9/session4b_step4.log`.
- **Why it matters:** the same class as the P0 "kill silent fallbacks" work — a failure that does not
  name its cause. It also means **any** eval run during a cluster blip silently produces nothing
  rather than erroring.
- **Fix (applied 2026-10-16):** initialise `vectors_cfg = None` before the `try` and **log a warning**
  in the `except` (naming the collection and the exception) instead of swallowing silently. The
  sibling block at ~line 400 was already safe (its `except` sets `using = None` and logs).
- **Also:** the cluster at `10.0.10.65`/`10.0.10.70` is **intermittently unreachable** (up
  2026-10-15 20:0x, down 2026-10-16 10:4x–now) — an eval run should preflight it and fail fast.
  No re-ingest.

### D12. Step 4 ran — abstention, generation metrics and the visual lane are measured (2026-10-16)
- **What:** the last unmeasured half of the P0-9 decision — `evaluate_rag.py` on `data/eval_queries_v2.json`
  (`--skip-visual`, reranker ON). Both prior attempts died (ColPali base model missing → §B4f; cluster
  outage → §D11, both since fixed).
- **Measured** — artifact `data/eval_results/p0-9-gold-v2_2026-10-17_0422.md`, run 2026-10-16 20:13–21:22:
  - **Abstention (34 negatives): 17/34 = 0.500** — vs the majority-class baseline of **0.0** (always
    answering) → the pre-registered rule is **met**; half the negatives are still answered.
  - Text lane n=133: R@20 **0.465** · Hit@20 0.947 · MRR 0.827 · NDCG@20 0.540 · Faith **0.661** ·
    Ans.Rel 0.852 · Citation 1.000. Per type — factual 0.564 (53), multihop 0.619 (40), overview 0.178 (40).
  - Visual lane (33 q, measured separately): **R@20 0.960**.
  - Run integrity: 164/200 synthesis, 162/200 faithfulness, **4876 judge calls, 0 failed**, 3 queries
    returned no answer, elapsed 3565.7s.
- **Why it matters:** this closes P0-9's measurement — both halves of the pre-registered decision now
  have numbers (reranker unresolved; abstention met). The abstention 0.500 is weak in absolute terms
  (half the negatives answered), so it clears the bar without being good.
- **Evidence:** `data/eval_results/p0-9-gold-v2_2026-10-17_0422.md`; `logs/p0-9/session4b_step4.log`;
  pre-registration "Step 4 outcome". No re-ingest.

### D13. Reranker decision — deferred to a post-re-ingest ablation / A-B (owner, 2026-10-16)
- **What:** on v2 the reranker's isolated contribution is **−0.0101, CI [−0.0299, +0.0097] → unresolved
  at n=133** (§D2's v2 update; §D9). The pre-registered δ=0.05 needed only n=43, but the observed
  0.011 needs **n≈934**, and extending in blocks of 30 reaches only δ≈0.026 at n=163 — so it cannot be
  resolved at a feasible n, and §5 forbids extending until an arm wins.
- **Decision (owner):** **keep the reranker enabled for now.** Do not drop it and do not extend the
  query set. Settle it **after the re-ingest** (the E1/E2/E3 chunking + §E5 + §D4 page-number fixes)
  with a **fresh ablation / A-B** on the rebuilt index, when the label-noise floor (§D4) and the
  chunk-boundary fuzz have been removed — the observed 0.011 sits inside both.
- **Why not decide now:** the current floor (label fuzz ±1, HyDE band, §D10 pool-level
  non-reproducibility) is the same order as the effect, so any verdict now is a coin-flip. A re-ingest
  changes the retrieval substrate, which is the honest place to re-measure it.
- **Alternatives rejected:** (i) drop it now on cost/benefit — rejected, because the cost is small and
  the effect is unresolved, not proven-negative; (ii) extend the query set — rejected, §5 forbids
  extending until an arm wins and 0.011 needs n≈934. Keep the **factual-lane** loss (−0.0469, resolved)
  as the hypothesis to re-check in the ablation.
- **Evidence:** `IMPROVEMENTS.md` §D2/§D9; pre-registration "Step 4 outcome" + "Session 4b re-run".

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
- **Measured 2026-10-17 (`test_book.pdf`, 42 parents → children):** the *inherited*
  `min_chunk_tokens=32` — a threshold set for the old size-based chunker — merges a material
  share of the new, smaller children:

  | `min_chunk_tokens` | children | median tokens | avg chars |
  |---|---|---|---|
  | 0 (raw chonkie) | 91 | 60 | 312 |
  | 16 | 80 | 68 | 355 |
  | **32 (current default)** | **66** | **84** | **430** |
  | 64 | 55 | 106 | 517 |

  So E1's "smaller, topic-coherent" gain is partly clawed back: **91 → 66 children, −27%**,
  with average child size up 312 → 430 chars. Every parent's *first* child escapes the merge
  (the "promote rather than drop" branch), which is why `min=3` tokens survives at any
  setting. **Not changed yet** — the plan keeps the merge behaviour, and the threshold is a
  measurement, not a code choice: settle it with the funnel's candidate counts after the
  re-ingest (§E1 caveat) rather than by guessing now.
- **Re-measured 2026-10-17, for the Step 4 unit question** (`logs/p1/step4/probe_child_units.py`,
  `child_units.json`): **6 of 66 children (9%) sit BELOW the 32-token threshold** (3 of them below
  16). Token counts: min 3 / p25 62 / median 85 / max 372. The merge **never re-checks the grown
  child's size**, so a merge can land under the threshold again — and the first child of every
  parent is promoted unconditionally. The survivors are the expected shapes: `F = Ma` (3 tokens),
  a copyright/editor line (8), objectives bullet lists (26, 31, 31). Note the overlap with **§E5** —
  most of them are front-matter or objective lists, which is exactly what chunk-level `is_content`
  is for. Still a measurement to settle after the re-ingest (funnel candidate counts), not a code
  change now.

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

#### E3a. VERIFIED 2026-10-16 — the cluster CAN serve late chunking (corrects a wrong reading)

- **What was believed:** "the cluster cannot do late chunking — no endpoint returns a dense model's
  per-token hidden states." **Wrong.** `POST /embed-text/v1/embeddings` accepts
  **`return_token_embeddings: true`** and then returns per-token, **native-dimension** vectors:
  `jinaai/jina-embeddings-v2-base-en` → `(1, 22, 768)`; `Qwen/Qwen3-Embedding-0.6B` → `(1, 19, 1024)`.
  Batching works; each response item carries `index` — honour it rather than array order.
- **The alignment precondition holds:** a **local** jina tokenizer produced exactly 22 tokens for the
  same text the API returned 22 vectors for, so a local `offset_mapping` lines up 1:1 with the API's
  token vectors. Only the *tokenizer* is local; the vectors still come from the cluster.
- **The class repo documents this path** — `Labs/Week_3/chunking_pipeline/docs/notebooks/
  02-contextual_and_late_chunking.ipynb`, cell 13 ("Alternative: API-based late chunking (SV cluster)").
- **Why the earlier reading was wrong:** only the *pooled* form had ever been requested. The
  multivector (ColBERT) endpoint returns 128-d per token with `embedding_type: "colbert"` for **every**
  model name, which made it look like the only per-token surface — it is not.
- **Consequence:** late chunking and MRL compose. Mean is linear, so `mean(tok)[:64] == mean(tok[:64])`
  (pinned by `tests/test_cluster_embedder.py`), i.e. a late-chunked vector still has a valid 64d view.
  This is the E3 method chosen for the P1 re-ingest — no LLM calls.
- **Evidence:** live probes 2026-10-16 (`.hermes/plans/2026-10-16-p1-reingest-plan.md` §2.1).

#### E3b. Step 4 LANDED 2026-10-17 — Qwen3 alignment verified, `late_chunk_embedder.py` built

- **What:** `src/pdf_ingestion/late_chunk_embedder.py` (+ `EnrichedChunk`). Per parent: one cluster
  call with `return_token_embeddings=True`; local tokenizer for offsets; mean-pool the token vectors
  inside each child's char span; L2-normalise → `dense_1024`, MRL-slice 1024→64 → `dense_64`.
  Children are **never** embedded individually in the late path (that is the `embed_isolated` twin,
  kept as the E3 control and as the `late_chunk_enabled=False` path).
- **The FIRST ACTION the plan demanded (alignment for Qwen3, not just jina) — CONFIRMED.**
  `logs/p1/step4/probe_qwen3_alignment.py` → `alignment.json`, live against
  `10.0.10.70:8123`: the local `Qwen/Qwen3-Embedding-0.6B` tokenizer called with
  `add_special_tokens=False` yields exactly the content tokens; the endpoint returns **exactly one
  extra TRAILING `<|endoftext|>` vector** (so `matrix[:-1]` is the content matrix); offsets tile the
  text; appending text leaves every earlier vector **bit-identical** (max |Δ| 0.0, control: the
  EOS position moves by 18.2); a one-word swap moves index *k* and later (11.99) and leaves every
  index before *k* bit-identical; a 5,200-token input is **not** truncated (5201 vectors).
  → R2's 1024d + 64d design holds; the jina fallback was **not** needed. The plan's §2.1 alignment
  claim is now verified for the model R2 actually selects.
- **Independent recomputation** (`logs/p1/step4/verify_evidence.py` → `evidence.json`): over all
  **66 children** of `test_book.pdf`, pooling recomputed from the raw endpoint response by hand
  agrees with the module to **max |Δ| = 0.0** on both `dense_1024` and `dense_64`; 0 fallbacks;
  MRL linearity holds to 6e-8.
- **E3 effect size on the fixture — small, and that is the honest reading:** late-vs-isolation
  cosine over 66 children = **min 0.914 / median 0.9997 / max 0.99999** (27 below 0.999). The
  synthetic dangling-*"This"* child (the plan's acceptance case) gives **0.850**. The small median
  is expected *on this fixture*: Docling parents are tiny there (max 547 tokens over 19 pages) and
  the semantic children are large fractions of their parents, so "parent context" adds little the
  child did not already contain. On the 968-page book parents reach 5000 tokens and children stay
  ~400 chars, so the child/parent ratio — and with it the effect — should be materially larger.
  **This is a prediction to re-measure at Step 10, not a claim.**
- **Cost — measured, then extrapolated** (`probe_late_chunk_cost.py` → `cost.json`): per-token
  output is **~160×** the pooled payload and **~55×** the wall time (57.1 s / 267 MB for the
  fixture's 6,773 parent tokens). Extrapolated to 968 pages: **~2,911 s (~48 min)** and
  **~13.6 GB** of JSON, plus ~5.5 min of Docling parse. Acceptable as the Step 8 background job;
  it is why only **parents** get a per-token call. (One batch of 42 parents in a single request is
  what produced the 267 MB response — batching at `embedding_batch_size` is the safer shape.)
- **The strip is assertive, not load-bearing** — stated plainly because it is easy to overclaim:
  the extra vector sits at the END, so an offset-derived index list never contains it and
  `raw[idx] == content[idx]`. Dropping it changes **no** child's vector. Its value is the **count
  assertion** (`n_api == n_local + 1`, else `n_api == n_local`, else raise), which turns a future
  layout change — a BOS at the front, a truncated response — into a loud error instead of a
  silent one-token shift of every child vector. Measured cost of that failure mode: shifting the
  indices by one changes a child vector by up to **0.0908** (≈ a real ranking change).
- **Guards:** a span overlapping no token falls back to the **parent mean** with a warning (not a
  zero vector, not a dropped child); a token-count or dimension mismatch **raises**; children
  referencing an unknown parent raise; a parent tokenizing to zero tokens falls back to isolation.
- **Tests:** `tests/test_late_chunk_embedder.py` — **12 fast** (mock transport carrying the real
  endpoint contract: one extra trailing vector) + **1 slow** (real Qwen3 tokenizer + real cluster).
  Suite at the floor.
- **Independent review found a real defect** (round 1, `openai/gpt-oss-20b`, single-turn): the
  zero-token-parent branch called `self._embed_isolated`, which does not exist — an AttributeError
  on a reachable path, and the one branch with no test. Fixed, regression test added
  (`test_parent_that_tokenizes_to_zero_tokens_falls_back_to_isolation`), round 2 → `passed: true`,
  `logic_errors: []`. Record: `logs/p1/step4/README.md`.

### E4. Stale docstrings describing a pipeline that was never built ✅ fixed
- `chunker.py` claimed *"Chonkie-based semantic chunker"*, *"Two-pass chunking … Semantic
  grouping via chonkie SemanticChunker"*, and *"span tracking for Jina late chunking"*.
  None of it is true: the chunker is `SentenceChunker`, `SemanticChunker` is never
  imported, and the embedder is Nomic and encodes chunks independently. Corrected.
- **Why this matters beyond tidiness:** a docstring describing intent gets read as a
  description of reality — exactly the failure mode `silent-failure-audit` warns about.
  This is how the "semantic chunking" claim would have survived into the report.

### E5. Classify chunks content vs non-content at ingest (front/back matter) ⚠️ requires re-ingest
- **What:** at ingest, tag each chunk `is_content: true/false` from its own text (seed the
  rule with the `_NON_CHAPTER` keyword list already in `store.py`, currently wired only into
  the RAPTOR rebuild), store it in the Qdrant payload, and filter retrieval on it. This
  *replaces* the page-number bounds (`min_content_page` / `max_content_page`).
- **Why page bounds are not enough** (measured 2026-10-13, Session 3b):
  - The parser's payload `page_number` and the PDF page index are offset by 0 or −1 on ~45%
    of pages (425 unambiguous pages: 232 at offset 0, 192 at −1) — a page bound lands
    differently in the two coordinate systems.
  - One page holds both: DB page 936 carries the last chapter's ending (chunks 4660-4668)
    **and** the first ~15 index chunks (4669-4683, `## Index -1`). No page bound can split it:
    `max_content_page=936` leaks those ~15 chunks; `935` would drop the chapter ending.
  - Front matter is the same game: `min_content_page=30` still leaves the TOC tail (p30-33).
- **What it fixes:** front matter, back matter, and the mixed page — one text-based rule,
  book-agnostic, immune to the ±1 numbering offset.
- **Does it require re-ingest?** **Yes** — the flag is written into the payload at ingest.
  Fold it into the E1/E2/E3 re-ingest pass (see "Re-ingest ordering").
- **Interim (Session 3b):** `max_content_page=936` is approximately right — ~15 index chunks
  (0.3% of 5,048) remain retrievable. Do not chase the remainder with page arithmetic; this
  item is the fix.

#### E5 outcome — P1 Step 5 (2026-10-17): the rule, and its measured limits

**Landed:** `src/pdf_ingestion/content_filter.py` (the promoted `_NON_CHAPTER` list + two
structural signals), wired into the chunker (tags every child), the Qdrant payload
(`is_content`), SQLite (`chunks.is_content`), the RAPTOR/card rebuild, and retrieval
(`must_not is_content == False`, both in the Qdrant filter and as a Python post-filter).
Evidence: `logs/p1/step5/probe_is_content.py` → `evidence.json`; tests
`tests/test_content_filter.py` + `tests/test_backmatter_gate.py`.

**The keyword list alone is not enough — measured, not assumed.** On the real corpus none of
the page-936 index rows contain a `_NON_CHAPTER` marker: they are pipe-table rows
(`| Angle | Avogadro's number, 41-18, II-8-9 |`) and separator rows (`|---…---|`). A rule
seeded only with the keyword list would **not** satisfy the plan's own acceptance test
(page 936 splits). Two structural signals were therefore added: an **index heading** matched
as a whole line (`## Index -1`, `## Name Index` — so `## The Origin of the Refractive Index`,
a real chapter on p533, is *not* caught) and an **index table** layout (≥⅓ of lines are
"term, page-ref" entries *and* ≥½ the lines are pipe rows — so a content table of bare
numbers, `| 60 ◦ | 8 ◦ |`, is not caught).

**Measured against a page-region oracle** (pages ≥937 back matter, <34 front matter;
page-936 index run = chunks 4669–4683), 5,048 chunks:

| metric | value |
|---|---|
| page 936 | **splits correctly** — content 4660–4667 kept, index 4668–4683 dropped |
| false negatives (content dropped) | **5** — 2 pure separator rows (no text), 2 chapter bibliographies (`## bibliography`), 1 boundary chunk (4668) whose prose ends with the `## Index` heading. **No prose or numeric table is dropped.** |
| false positives (non-content kept) | **242** — the remaining recall gap |

**Known gap (the 242):** front-matter *prose* (publisher's note, preface — no keyword in the
chunk itself) and the TOC / Name-Index continuation rows (different layout: `| 1-1 | …`, or
rows that start with a page ref). These stay covered by the page bounds (`min_content_page` /
`max_content_page`) until the Step 8 run zeroes them; **do not zero the page bounds until
this recall gap is closed or measured as immaterial at Step 10.** Extending the rule (e.g.
parent-heading context, a TOC dot-leader signal) is a follow-up, not a blocker for Step 5.

**Backward compatibility (why this can land before the re-ingest):** `must_not
is_content == False` never excludes a point that *lacks* the field, and the Python
post-filter keeps `is_content is None`. So the current index (points written before the
re-ingest carry no `is_content`) is unchanged, and the filter takes effect on the rebuilt
one.

---

### E6. P1 Step 7 — the write path lands; the dense-lane switch leaves the QUERY side open ⚠️ blocks Step 10

**Landed 2026-10-17.** The re-ingest's write path exists end to end: `ChunkingPipeline`
(`src/pdf_ingestion/chunking_pipeline.py`) is the single ingest path
(`ParentChunker.convert` → `SemanticChunker.chunk_parents` → `LateChunkEmbedder.embed_children`
→ `DocumentStore.save_document`), and `store.ingest_pdf` delegates to it — so the script, the
UI upload and the tests all build the same index. The collection schema is
`dense_64 + dense_1024 + colbert + sparse` (`dense_768` retired), the payload and SQLite both
carry `parent_id` (+ `parent_text` in the payload, plan §7 decision 4), and the legacy flat
path (`chunk_document` / `build_page_map` / `_page_for_offset`) is **deleted** — Step 6's
deferred half.

**Vector names are resolved from the collection, not hard-coded** (`store._dense_name_from`).
The deployed `knowledge_base` still carries `dense_768`, and R1 keeps it queryable for the
old-vs-new comparison, so a hard-coded `dense_1024` would have made the deployed index
unwritable the moment this landed. Pinned by
`tests/test_chunking_pipeline.py::test_save_document_writes_dense_768_into_a_dense_768_collection`.

**Forced consequence — RAPTOR summaries moved to the dense lane.** A summary vector lives in
the *same* collection and the *same* full-dimension slot as the chunks, so
`raptor_tree._embed` had to switch from the local Nomic 768d embedder to the cluster's Qwen3
(passages embedded raw; the query instruction stays on the query side). Without it Phase 2's
upsert fails on a dimension mismatch — 14 test failures, not a silent degradation. Phase 2/3
still belong to Step 9; this was the minimum to keep one collection coherent.

**Evidence** (`logs/p1/step7/`): a live probe on `test_book.pdf` with the **real** cluster
dense lane and the **real** Qwen3 tokenizer — 42 parents → 66 children (19 pages, the Step 2/3
counts), the collection carrying exactly `colbert/dense_1024/dense_64`, every point 1024d+64d
and unit-norm, Qdrant points == SQLite chunks == children (66), every payload with
`parent_id`/`parent_text`/`is_content`, every child with an in-range page, and
`dense_64 == mrl_slice(dense_1024, 64)` within 1e-5. Suite: **356 pass / 4 pre-existing fail /
6 skipped** (the 6 skips are the live-E2E tests, which now need `SV_EMBED_URL`). ruff: 51
findings before, 51 after — no new ones.

**THE GAP — the query side still embeds with the retired model.** `get_query_vector` exists
(`cluster_embedder.py`) as the single accessor for the dense-lane query, and the Step 7 tests
use it, but these call sites still call the local Nomic embedder:

| site | what breaks |
|---|---|
| `src/frontend/streamlit_app.py` (query, HyDE, graph query) | UI search against v2: dimension error |
| `src/main.py` `/search` | same |
| `scripts/evaluate_rag.py`, `scripts/funnel_boundary_recall.py`, `scripts/calibrate_eval_pages.py`, `scripts/why_colbert.py` | Step 10's funnel + ablation cannot run against v2 |
| `scripts/reembed_chunks.py` | writes 768d vectors into the KB collection |
| `src/core/intent_router.py` (prototypes **and** the `embedding_dim` schema check) | R-a: the classifier + prototypes are 768d; the router must retrain (`scripts/train_intent_classifier.py`) or it falls back to prototype cosine |

This fails **loudly** (Qdrant rejects a 768d query against a `dense_1024` slot), and the
deployed index is unaffected, so nothing is silently wrong today — but **Step 10 cannot
measure until this is switched**. No re-ingest is needed to fix it: it is a code change plus
one retrain run against the cluster. Registered as the next action in `HANDOFF.md`.

**Deviation from the plan's module map:** `ChunkingPipeline.process_all_documents` was **not**
written. It has no caller in a single-textbook repo, and an untested second entry point is
dead code from the day it lands. `process_pdf` is the whole API.

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

## I. Lane upgrades, observability, UI — carried over from HANDOFF P1 (2026-10-12)

Cost class noted per item. **Every embedder upgrade needs a full re-ingest.**

### I1. Embedder upgrades — each lane has something newer ⚠️ requires re-ingest

| Lane | Current | Newer available |
|---|---|---|
| dense | `nomic-embed-text-v1.5` | `nomic-embed-text-v2.5` |
| ColBERT | `colbertv2.0` | `lightonai/GTE-ModernColBERT-v1` (also 128-dim → drop-in) |
| sparse | `Splade_PP_en_v1` | `Qdrant/bm42-all-minilm-l6-v2-attentions` |
| visual | `colpali-v1.2` | `TomoroAI/tomoro-colqwen3-embed-4b` |

Cross-encoder: already on the best of the five offered (`bge-reranker-v2-m3`) — nothing to do.
Chat: nothing better is actually serving — `gpt-oss-120b` HTTP 502s; the ceiling is `gpt-oss-20b`.

### I2. Graph lane — 1–2 hop traversal still missing ⚠️ no re-ingest

`graph_search` now ranks by distinct concepts matched, then concept similarity (the scores were
previously discarded). **Still missing:** real 1–2 hop `RELATES_TO` traversal — `hop_distance`
remains the constant 0. **Root cause of poor relevance:** the concept vocabulary holds
near-duplicates as *separate nodes* ('orbit' / 'Orbit' / 'planetary orbit' / "Earth's orbit"),
so nearly every chunk ties at 1 distinct concept. **Deduplicating concept names is the bigger
lever than ranking.**

### I3. Admin Status should report the STORES, not SQLite ✅ DONE 2026-10-16

Three separate bugs came from local SQLite describing a different ingest than the index (visual
readiness, the sidebar badge, the graph). A status panel driven by store counts would have caught
all three.

**Fixed:** the Admin Status tab now carries a **"🗄️ Store (Qdrant) vs SQLite"** table beside the
existing SQLite-derived metrics — `knowledge_base`, `visual_knowledge_base`, `derivative_artifacts`
and `concept_embeddings` each show the store's exact point count next to the SQLite row count, with
a `Match` column (`✅` / `⚠️ Δ ±N` / `⚠️ store empty`). Backed by a new additive store method
`DocumentStore.count_collection(collection_name)` (returns 0 and logs a WARNING if the cluster is
unreachable — covered by `tests/test_fallback_chains.py`). The row-building logic is extracted to
`_store_vs_sqlite_rows()` so it is testable despite the tab sitting behind `is_admin`
(`tests/test_frontend_status_panel.py`, 7 tests).
**What it already surfaces:** the `derivative_artifacts` row disagrees with the SQLite card count by
design — that collection is the retired card generation with **zero id overlap** (§A2). That is the
panel doing its job, not a bug to chase here.

### I4. Phoenix does not trace LLM calls

`src/core/llm.py` posts with raw `httpx`, and the `openai` SDK is imported **nowhere** in `src/`,
so `OpenAIInstrumentor()` patches a library that is never used. Retrieval stages are traced;
synthesis, card generation and RAPTOR are invisible — including their latency and token counts.
Fix: call through the `openai` SDK, or emit manual spans around `call_llm`.

### I5. Upload tab's "Topic" and "Difficulty" are inert ✅ DONE 2026-10-16

Persisted to the Document row and the chunk payload, but nothing filters or steers on them.
Wire or remove.

**Resolved by removal** (the widgets and their comment were already gone; completed here): the two
unused `subject, difficulty = None, None` locals were deleted, and `ingest_pdf` no longer receives
`extra_meta={"subject": None, "difficulty": None}` — that was writing two always-null keys into
every Document row and chunk payload for a feature that does not exist. Revisit as a real feature
(scoped card generation) is tracked as §C4.

### I6. Test the fallback chains ✅ DONE 2026-10-16

Stub tests structurally cannot reach the fallback paths (stub embedder/LLM/ColPali/graph/SPLADE).
A lane that silently falls back to a stub in production is a silent-failure class P0-2 did not cover.

**Done:** `tests/test_fallback_chains.py` (8 tests) drives the REAL classes with a deliberately
broken backend and pins what each fallback returns — a failed LLM call returns `""` and logs at
ERROR; **a production failure is asserted to differ from the stub's `"{}"`** (so a stub leaking into
production is detectable); a 200-with-no-choices response returns `""`; a failed embedder `encode`
degrades to a zero vector of the right shape; `visual_search` returns `[]` and `count_visual_vectors`
/ `count_collection` return `0` on an outage. The store tests assert the WARNING was logged, so they
cannot pass vacuously via an early return.
**Finding registered as §I9** (the zero-vector embedder fallback is a genuine silent-degradation
risk, not just untested).

### I7. `render_math()` golden-file test ✅ DONE 2026-10-16

Would end the six-commit LaTeX patch cycle. Partly done — `tests/test_frontend_math.py` pins the
two converter bugs, but there is no golden-file end-to-end check.

**Done:** `tests/data/formula_split_golden.json` (8 cases drawn from real cards, covering every
separator shape found in the corpus) + `tests/test_frontend_formula_render.py` (10 tests). The
golden test pins the split; the render tests capture what `render_math` actually hands to
`st.latex` / `st.markdown`, so the B1 defect class (prose reaching `st.latex`) now fails a test
rather than waiting for someone to look at the page.

### I8. `sv_ray_cluster_access/` — reference only, keep gitignored

Its own header declares it SupportVectors IP, not for reuse or sharing. Not importable here
(needs `svlearn`), and every endpoint it documents is unreachable. Keep as reference only.

### I9. NEW 2026-10-16 (found by §I6) — a failed embedding silently degrades to ZERO vectors

- **What:** `NomicEmbedder._encode` (`embedder.py`) catches **any** exception from the model and
  substitutes `np.zeros((len(texts), embedding_dim))`, logging at ERROR. The zero vectors then flow
  on as if they were real embeddings — stored on ingest, and searched at query time.
- **Why it matters:** it is the worst shape of silent failure. Retrieval does not error, it returns
  *wrong* results: a zero vector has zero similarity to everything, so an ingested chunk becomes
  unfindable and a query embedding makes every score meaningless. The caller cannot tell a real
  vector from a fallback one by looking at it.
- **Measured (pinned by `tests/test_fallback_chains.py`):** the fallback is exactly all-zeros of
  shape `(768,)`, and it is logged at ERROR. That is the current, intended-but-questionable
  behaviour — the test freezes it so a change cannot happen unnoticed.
- **Options (not decided):** (a) raise instead of substituting, so ingest fails loudly and the
  caller retries; (b) keep the fallback but make it observable — return a flag/count alongside the
  vectors so `evaluate_rag.py` and the ingest path can report "N chunks embedded as zeros"; (c) do
  nothing, on the grounds that the ERROR log is enough. **(a) or (b) is recommended** — a zero
  vector is never the right answer to "the model is down", and the cost of (b) is small.
- **Cost:** small — the fallback is one branch in `_encode`, plus its call sites.
- **Not blocking anything.**

---

### I10. FIXED 2026-10-16 (found running the P0-9 4b visual lane) — ColPali had no singleton: one 5.5 GB model load PER QUERY

- **What:** `get_colpali_embedder()` built a fresh `ColPaliEmbedder` on **every call**, and
  `evaluate_rag.run_visual_retrieval` calls it once per query. Every other heavy factory in the repo
  is a memoised singleton (`_colbert_instance`, `_reranker_instance`, `_graph_builder_instance`,
  `_splade_instance`); ColPali was the one that was not.
- **Why it matters:** each call reloaded ~5.5 GB of weights from disk — 33 model loads for a
  33-query lane. It thrashed memory and the run was **OOM-killed (SIGKILL, exit −9) at query 15**,
  right after a load that took **50 s instead of the usual 10 s** (i.e. it was swapping). No report
  was written; it presented as a crash, not a config problem.
- **Fix:** `colpali_embedder.py` now follows the established pattern — module-level `_colpali_instance`
  + `get_colpali_embedder()` memoisation + `reset_colpali_embedder()`, wired into the
  `reset_db_singletons` autouse fixture (`tests/conftest.py`). After the fix the model loads **once**
  and the whole lane finishes in **23.6 s**. No re-ingest, no schema change.
- **Cost:** small — factory-only change.
- **Report gap (same run, minor):** the visual run's report `Config` block prints the **text** lane's
  settings (`Collection: knowledge_base`, embedder nomic, reranker bge) even though the visual lane
  read `visual_knowledge_base` with ColPali. A reader can misread which index was scored; the visual
  lane's collection/model belong in the snapshot.

### I11. NEW 2026-10-16 — `.env.example` pointed the embedding endpoints at the LLM router port

- **What:** `SV_COLBERT_URL` / `SV_SPARSE_URL` / `SV_RERANK_URL` were documented as
  `http://10.0.10.70:8000/...`. The cluster fronts **two** services: `:8000` is the LLM router
  (chat/completions only) and `:8123` serves embeddings / colbert / sparse / rerank / colpali. Every
  embedding path on `:8000` returns 404.
- **Why it matters:** it is the same class as the dead `10.0.10.51:8000` recorded in the P0-9 plan —
  a copied endpoint that reads as authoritative. Anyone following `.env.example` gets 404s and
  concludes the lane is broken.
- **Fixed:** the three URLs now point at `:8123`, with the two-service split written down beside them.
- **Cost:** none. No re-ingest.

---

The question "do we re-ingest before fine-tuning?" — **yes, and the order is forced:**

1. **Re-ingest first** (E1/E2/E3/E5 + F1/F2). Every ingestion change alters chunk ids,
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

### Visual-index cleanup rides along with the re-ingest (§B4b)

The 2,835-point / 945-page / 3× visual index is **not** cleaned by a one-off script — the
re-ingest is the chosen path (decided 2026-10-14). The write path already replaces a document's
pages instead of accumulating them, so a Phase-3 re-ingest that **reuses the same visual
`document_id`** comes out clean (one point per page).

**Verify, don't assume — count the collection afterwards:**

```bash
# expect ~945 (one per page), NOT 2,835
uv run python -c "from src.pdf_ingestion.store import DocumentStore; \
from src.core.config import get_settings; print(DocumentStore(get_settings()).count_visual_vectors(['global']))"
```

- If it is ~945, done.
- If it is still ~2,835 (or 945 + 1,890), the re-ingest minted a **new** visual `document_id` and
  the old points survived as orphans. **`clean_stale_visual.py` will NOT remove them** — it keys on
  a `document_id` absent from `knowledge_base`, and the visual doc id is *never* in
  `knowledge_base` (different ingest), so it hits its own guard and exits 2 (§B4b). Delete the
  orphaned `document_id` explicitly instead.
- **Ordering trap, unchanged:** still run `clean_stale_visual.py` after every Phase-3 re-ingest per
  `ARCHITECTURE.md` §8 — the above is about the *duplicate-pages* defect, not the *stale-document*
  one.
