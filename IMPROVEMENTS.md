# IMPROVEMENTS — tracked backlog

Everything known-but-not-yet-done, in one place so it can be taken in a single pass.
Each entry says **what**, **why it matters**, and **the evidence** — so nothing has to be
re-derived later. Add to this file rather than leaving a note in a commit message.

Last updated: 2026-10-20

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

### A2. Re-index `derivative_artifacts` from SQLite — ✅ **DONE 2026-10-22** (§I49 Lane A)
- **What:** `uv run python scripts/index_derivative_artifacts.py --clear --doc-id 7ba61432-…`
- **Done:** the collection was re-indexed from SQLite at the dense lane's **1024d**:
  **81,837 @ 768d → 73,406 @ 1024d**, **8/8** card types (was 5), and
  `search_da(dense_vec_1024, 'global')` returns **20 hits** (was **0** — the §I12 discriminator).
  `knowledge_base_v2` 3,869 and `visual_knowledge_base` 1,033 unchanged; preflight went
  **2 BLOCKER(S) → All checks passed**. Evidence: `logs/p1/step10/i12_laneA_da_reindex_2026-10-22.log`,
  `…/i12_laneA_verify_2026-10-22.txt`.
- **Why:** the collection had been a **retired card generation** — it shared no card ids with
  SQLite and was built by the old 5-type list, so the DA lane served cards the UI does not have.
- ⚠️ **The lane is live but has never been MEASURED on v2.** §D12 (2026-10-16) is the last run with
  a live DA lane and it is on the OLD document; the §3d smoke test ran with the lane dead. The
  measurement is `logs/p1/step10/da_lane_ablation.py` (2026-10-22).
- ⚠️ **A1 was NOT done first**, so this index reflects the **current** card set, not a regenerated
  one. If §A1 runs, §A2 must be repeated — A2's own note said so.
- ⚠️ **Not verified by §A2's own acceptance criterion:** the recorded verifiers are dim, hit count,
  type set and preflight. An **id-overlap check against SQLite** is not among them.

### A3. Card volume vs quality — is 8 types × N items per chunk the right shape? (owner question, 2026-10-18)
- **What:** the owner asked whether we need this many cards per page, or whether we should generate
  **fewer, higher-quality** cards rather than volume. Registered here so it is decided on evidence
  before Phase 2 is re-run for the rebuilt index.
- **Measured 2026-10-18 (SQLite `cards`, the deployed document `6d55c52b`):** **82,164** cards for
  **5,048** chunks = **16.3 cards/chunk**; the 5,048 chunks carry **756 distinct pages**, so
  **≈109 cards/page**. By type — `question` **32,002** (39 %), `factoid` **31,604** (38 %),
  `objective` 5,018, `misconception` 4,340, `summary` 3,603, `definition` 2,606, `formula` 1,534,
  `example` 1,457. The two multi-item types are **77 %** of the set. (Owner's figure of "5 cards per
  page" does not match the measurement — recorded so the note is grounded.)
- **The per-type rate is NOT out of band.** `question` = 32,002/5,048 = **6.3 per chunk** and
  `factoid` = 6.3 per chunk. The course's stated band is **3–8 QA pairs per chunk**
  (`Week_Plan/week-4-summer-lesson-plan.pdf`, `Week_Plan/week-10-summer-lesson-plan.pdf`,
  `Slides/week_10_the-library-of-many-catalogues.pdf`). So the volume comes from **8 types × multiple
  items each**, not from one type over-producing.
- **What the course actually mandates (SupportVectors materials, repo root):**
  - **QA pairs — 3–8 per chunk**: *"the only artifact that puts a query-shaped object in the index:
    question as vector, answer in payload"*. ⚠️ That is **exactly §F1**, so §F1 is a
    course-compliance fix, not a preference.
  - **Factoids/propositions** — Dense X: *"self-containment, an **nli faithfulness filter**, a **cap
    per chunk**"*. The project has **no faithfulness gate on cards at all** — nothing checks a card is
    actually supported by its source chunk.
  - **The monographic principle** (Otlet, week 9/10): **one atomic fact per card**; a card is
    **typed**; progressive disclosure — *"a metadata side … and an information side"*.
  - **Summaries at three altitudes** (chunk / section / document / corpus) — RAPTOR's job here.
  - **Method, stated twice:** *"every index must earn its place through ablation"* (week 10), and
    *"Run both over a fifty-chunk sample. Then do the thing engineers skip and should not: **read the
    artifacts**"* (week 4 lab). So this is settled by measuring retrieval and eyeballing output — not
    by argument.
- **Hypotheses to test (not yet decided):** (a) cap items per chunk per type; (b) drop or merge the
  low-yield types (`example` 1,457 and `formula` 1,534 are ~2 % each) — note the course names only
  factoids, QA pairs and summaries; (c) add the course's **faithfulness filter** as a card gate;
  (d) measure retrieval with a reduced set vs the full set (an ablation, per the course's own rule).
- **⚠️ requires a Phase 2 re-run** (cards are generated, not indexed — the policy change is free, the
  regeneration is not). Order after §A1, and before the §A2 DA re-index so DA indexes the final set.
- **Related:** §A1, §A2, §F1, §F2, §I15. **No re-ingest of Phase 1.**

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

**Update 2026-10-19 (P1 Step 10 §3a–§3c) — the fix is verified ON THE DEPLOYED INDEX, and the
"labels must be re-derived" premise turned out to be backwards.**

Step 6 verified the code path *before* Step 8 deployed it. §3a re-ran the **same** measurement (the
helpers are literally imported from `logs/p1/step6/probe_page_numbering.py`, so the two cannot
drift) against what is actually in SQLite — `chunks.page_number` per document — and it reproduces
Step 6 **chunk for chunk**:

| document | sampling | n | offset 0 | offset −1 | other |
|---|---|---|---|---|---|
| `7ba61432` (new, deployed) | all children | 3796 | **2150 / 2151 = 0.9995** | 1 | — |
| `7ba61432` (new, deployed) | first per page | 933 | **547 / 547 = 1.0000** | 0 | — |
| `6d55c52b` (old, deployed) | all chunks | 5048 | 1888 / 2639 = 0.7154 | 333 | +1: 322, +2: 73, +3: 20, −2: 3 |
| `6d55c52b` (old, deployed) | first per page | 757 | 230 / 423 = 0.5437 | 192 | +1: 1 |

0 chunks without a `page_number`; 933 distinct pages. **The deployed index speaks PDF-page
coordinates.** Evidence: `logs/p1/step10/{probe_deployed_page_numbering.py,a3a_probe.log,
page_numbering_deployed.json}`.

⚠️ **A verifier bug worth recording** (it produced a spurious FAIL on the first run): the probe
applied the "offset 0 ≥ 99 %" floor to **both** documents. The old document is the *baseline*, not
the thing under test — its ±1 cluster is the defect this fix removed, so asserting on it can only
ever fail. Fixed: the floor is asserted on the new document only; the old one is reported.
**Lesson: a verifier that asserts on the control as well as the treatment will always fail.**

**The premise correction.** Step 10 §3 said "the labels were built against the old DB page numbering
… so the labels must be re-derived against the new path". The truth is the reverse: the fix moved
the **index** into the labels' coordinate system. `expand_gold_labels.py` labels come from the fitz
scan, which is *already* PDF-page indexed — the same key the new index now emits. So the scan
component needs no re-derivation, and §D4's own conclusion ("no edit can remove the fuzz") stands:
the fuzz was removed by the index change, not by a label edit. What remained was a small,
quantifiable residual — see §D6's 2026-10-19 update for the 4 unreachable generator pages, and
`logs/p1/step10/{audit_gold_labels.py,a3b_audit.log,label_audit.json}` for the provenance split
(generator vs scan) per lane. No re-ingest.

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

**Update 2026-10-19 (P1 Step 10 §3b–§3c) — the deferred label edit is DONE, and the 4 pages turned
out to be a §D4 defect wearing a §D6 costume.**

`logs/p1/step10/audit_gold_labels.py` measured the provenance of every answerable label (the
generator page is recorded in `calibration_note` in **three** formats — single-chunk, multi-page,
and two kinds that carry no generator page at all; a parser that handles only the first silently
under-reports multihop):

| lane | queries | label pages | generator pages in labels | scan-only |
|---|---|---|---|---|
| factual | 53 | 506 | 53 (all single-chunk) | 453 |
| multihop | 40 | 175 | 86 (17 single-chunk + 23 **multi-page**) | 89 |
| overview | 40 | 2954 | 0 (topic-derived by construction) | 2954 |
| visual | 33 | 47 | 0 (the note is traceability only, by design) | 47 |

- **All 4 unreachable pages are MULTI-PAGE generator pages in old-DB numbering** — `gold-081`
  `[23, 172, 627]`, `gold-087`/`gold-088` `[24, 169, 274]`, `gold-094` `[22, 108, 474]`. The
  multi-page generator path never went through the scan expansion that re-pointed the single-chunk
  ones, so its pages kept the old numbering — and page 22–24 sits below `min_content_page` 30.
  **This is §D4's defect surfacing as a §D6 one**, not a generator sampling bug.
- **Fix applied (option B, owner-approved):** `build_gold_v2.py` gained `_clamp_unretrievable()`,
  which removes *individual* pages outside `[lo, hi]` from entries that survive the existing
  whole-query drop. It is a clamp in the **assembler**, not an edit to the artifact — so a rebuild
  re-applies it and a change to `max_content_page` propagates automatically. Rebuilt
  `data/eval_queries_v2.json`; verified the diff is **exactly** those 4 pages and every other entry
  is byte-identical.
- **Measured effect:** unreachable label pages **4 → 0**; multihop label pages 175 → 171; text-lane
  achievable maximum **0.9910 → 1.0000**. The §D9 ceiling is **unchanged** (0.8016 / overview
  0.3992 — reproduced exactly by the audit), because §D9's ceiling is the top-K cut, a different
  quantity from a page that cannot be retrieved at all. Both are now reported separately.
- **Guard:** `tests/test_gold_schema.py` 7 passed after the rebuild.
- **Evidence:** `logs/p1/step10/{audit_gold_labels.py,a3b_audit.log,label_audit.json,a3c_rebuild.log}`.
  No re-ingest.

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

**Update 2026-10-19 — the post-re-ingest ablation RAN. Still unresolved, but the noise floor halved.**

Ran on the rebuilt index (`knowledge_base_v2`, 3,796 points, doc `7ba61432`) after A4+A5 cleared the
§D14 gate. Harness `logs/p1/step10/run_step10_v2.sh`; verifier `logs/p1/step10/check_ab_arms.py`
(**exit 0**). Both arms n=**133**, same collection, same HyDE cache (`logs/p0-9/v2_hyde.json`), same
dense slot `dense_1024`. **§D10 stability: `B5b_retriever_top20` moved on 0 of 133 queries** — the
A/B is valid, not void.

- **Result: Δ = +0.0099 (rerank − no-rerank), SD_d 0.1411, SE 0.0122, 95 % CI [−0.0140, +0.0339] →
  UNRESOLVED.** 33 worse / 36 better / 64 identical. The sign flipped from the old index's −0.0101,
  which is what an effect that size inside this CI looks like.
- **The real change is the variance, not the mean.** SD_d fell **0.2315 → 0.1411 (−39 %)** and the
  required N for the pre-registered δ=0.05 fell **169 → 63** (`required_n.py`). n=133 now *exceeds*
  the pre-registered requirement, so the test is no longer underpowered for δ=0.05 — the observed
  0.0099 would still need N≈1,600, i.e. the effect is small, not merely unmeasured.
- **The §D13 hypothesis did NOT reproduce.** The factual-lane loss (−0.0469, *resolved* on the old
  index) is now Δ=**+0.0026**, CI [−0.0440, +0.0493] → **unresolved**. The re-ingest removed it, so
  the "the reranker hurts factual" claim does not carry over to the rebuilt index. All three
  per-type subgroups are unresolved (factual +0.0026 / multihop +0.0309 / overview −0.0013).
- **Verdict per the pre-registered rule: UNRESOLVED → keep the reranker enabled, do not extend the
  query set.** That is §D13's own fallback, unchanged; the rule did not need to be re-invented.
- **Ceiling (§D9):** R@20 raw rerank 0.4153 vs no-rerank 0.4054 → ÷0.8016 = **0.5181 vs 0.5057**.
  ⚠️ **Not comparable to §D12's 0.465.** §2 ran *before* Phase 2 (§0 Order A), so the candidate pool
  is 3,796 chunks with **no RAPTOR nodes**; §D12's number was measured on a pool that had them.
  Only the *paired delta* is meaningful here.
- **Evidence:** `logs/p1/step10/run_step10_v2.log`, `v2_rerank.json`, `v2_norerank.json`,
  `ab_verifier.log`, `ab_verdict.json`. No re-ingest.

### D14. NEW 2026-10-18 (found pre-flighting Step 10) — the preflight gate cannot pass for a re-ingested collection
- **What:** `scripts/preflight.py` requires Memgraph **unconditionally** and compares the graph's
  chunk ids against `cfg.qdrant_collection` — the collection **under test**. Both fail for Step 10's
  target `knowledge_base_v2`, for two independent reasons.
- **Measured (2026-10-18 16:24):** `QDRANT_HOST=10.0.10.65 QDRANT_COLLECTION=knowledge_base_v2 uv run
  python scripts/preflight.py` → **exit 1, 2 BLOCKER(S)**, both graph:
  `memgraph` FAIL (`localhost:7687` connection refused — the Docker daemon is not running) and
  `graph.matches-qdrant` FAIL (cascades). **Every other check PASSED**: `qdrant.knowledge_base_v2`
  3,796 points (`colbert,dense_1024,dense_64`), `intent-classifier` `n_features_in_=1024` == the
  dense lane, all four endpoint probes HTTP 200, and a real completion
  (`openai/gpt-oss-20b -> 'OK'`). Log: scratch `preflight.txt`.
- **Why it matters — cause 1 (local service):** Memgraph is a local
  `docker compose --profile phase3` service (ARCHITECTURE §11); the cluster hosts do not expose 7687
  (probed 2026-10-18). The **funnel ablation never touches the graph** — `funnel_boundary_recall.py`
  and `required_n.py` contain no Memgraph reference — so the gate is stricter than the measurement it
  guards.
- **Why it matters — cause 2 (structural, and the real defect):** even with Memgraph up, the check
  **cannot** pass against a fresh collection. Chunk ids are `str(uuid.uuid4())` per ingest
  (`src/pdf_ingestion/chunker.py:147`), so a graph built from the *previous* ingest shares no ids with
  `knowledge_base_v2`; the check would report ~100 % dangling. The graph is rebuilt in Phase 3 /
  Step 9, which the Step 10 plan §5 **defers by decision**. Consequence: the graph lane silently drops
  for multihop queries in `evaluate_rag.py` (`try/except` at ~line 211 logs a warning and continues) —
  exactly the §D11 class of failure the preflight exists to catch, now turned into a permanent
  false-positive blocker.
- **Fix (not done — direction is an owner decision):** (a) start Memgraph
  (`docker compose --profile phase3 up -d memgraph`; the `--profile phase3` flag is required or it
  silently does nothing); (b) **scope** the graph↔Qdrant check to the collection the graph was built
  from, or skip it with an explicit "graph lane not measured" note when the collection under test is
  not the graph's — otherwise a re-ingest transition can never pass the gate; (c) rebuild the graph
  against the new collection — that is **Step 9**, deferred. (b) is the durable fix; (a) alone does
  **not** clear the gate.
- **No re-ingest.**

**Update 2026-10-18 (after starting Memgraph — cause 1 cleared, cause 2 confirmed).** Docker Desktop
was started and `docker compose --profile phase3 up -d memgraph` brought `synapse_memgraph` up. The
preflight was re-run against `knowledge_base_v2`: **`memgraph` now PASSES** (`docs=1 chunks=5051
concepts=7815`) but **`graph.matches-qdrant` FAILS with 5,051/5,051 graph chunk ids absent from Qdrant
(100.0%)** → still exit 1, 1 BLOCKER. Cause 2 is therefore confirmed as the only remaining blocker, and
**starting Memgraph did not clear the gate** — exactly as predicted above. Two further defects found
in the same pass:
- **The compose healthcheck is broken.** `docker-compose.yml` tests the container with `mg_client`,
  which **does not exist** in `memgraph/memgraph:2.18.1` (`exec: "mg_client": executable file not found
  in $PATH`), so the container reports **`unhealthy` permanently while serving Bolt on 7687 normally**
  (v2.18.1, TCP open, driver connects). Anything that gates on container health would be misled.
  `preflight.py` is not affected — it probes Bolt directly.
- **The preflight's printed remedy is wrong here.** It advises
  `clean_stale_graph.py --qdrant-host <host> --dry-run`, but that script's source of truth is
  `cfg.qdrant_collection` — against `knowledge_base_v2` **every** graph document looks stale, and its
  own no-overlap guard would **refuse** (exit 2) rather than delete. The graph is not stale: it is the
  correct graph for the **deployed** `knowledge_base` (5,135 points, plan R1 — untouched). Do **not**
  run it against `knowledge_base_v2`, and do not pass `--force`.
- **Net:** the gate can only pass via fix **(b)** (scope the graph↔Qdrant check to the collection the
  graph was built from, or skip it with an explicit "graph lane not measured" note) or fix **(c)**
  (rebuild the graph = Step 9). Starting Memgraph was necessary but not sufficient.

**Update 2026-10-19 — fix (c) was TAKEN; the gate now PASSES (exit 0).**

Owner decision 2026-10-18: rebuild the graph (fix (c) — Step 9's *graph half* only; cards / DA /
ColPali stayed deferred). Phase A built doc `7ba61432`'s graph (A3, 16 h 25 m — §I23). Then:

- **A4 — `clean_stale_graph.py` with `QDRANT_COLLECTION=knowledge_base_v2 --qdrant-host 10.0.10.65`.**
  Dry-run (read-only) showed exactly **1** stale document (`6d55c52b`, 5,051 chunks, 757 pages, 7,815
  touched concepts) and `7ba61432` "keep (has vectors)"; the no-overlap guard did **not** fire, i.e.
  graph and Qdrant genuinely overlap and the run was pointed at the right store. Applied with `--yes`,
  **never `--force`**: removed **1 document / 5,051 chunks / 757 pages / 4,664 orphaned concepts**
  (the other 3,151 touched concepts survive because `7ba61432`'s chunks still mention them —
  `Concept` nodes are MERGEd by name).
- **Measured before → after: `graph.matches-qdrant` 5,051/5,051 absent (100.0 %) → 0/3,796 absent
  (0.0 %).** Memgraph now `docs=1 chunks=3,796 pages=933 concepts=7,834 edges=73,336`, density
  **2.064/chunk** (old doc 1.547; floor 0.774). Old-document residue: **0 chunks / 0 pages**.
- **A5 — `preflight.py` → exit 0, every check PASS.**
- ⚠️ **The consequence predicted above is now realised, not hypothetical:** the deleted graph was the
  **deployed** `knowledge_base`'s (5,135 points). The deployed app's multihop lane has **no graph**
  until cutover. The Qdrant collection itself is untouched (plan R1). This was the accepted price of
  fix (c) and it was accepted explicitly, with the reasoning that G3 (the additive build) had already
  degraded that lane — `graph_search` filters on tenant, not `document_id` — so G4 is the repair.
- **Fix (b) — DONE 2026-10-20, see §I34.** It was the durable fix and it was missing; the check is now
  scoped to the graph's own collection (the verdict gained a PASS/**SKIP**/FAIL state). A future
  re-ingest no longer produces a false "retired content" blocker telling the operator to run
  `clean_stale_graph.py`: it reports **SKIP** and names both collections. The *class* is treated.
  ⚠️ Residual: the graph lane is then genuinely **not measured** for that run, and whether that should
  be non-blocking (as implemented) or a hard blocker is an **owner decision** (§I34).
- **Correction to the note above:** the earlier advice "Do **not** run `clean_stale_graph.py` against
  `knowledge_base_v2`" applied while the graph held *only* the old document — at that point every
  graph document was genuinely the deployed one's and deleting would have destroyed live data. After
  the rebuild (A3) the old document is genuinely superseded, so running it against
  `knowledge_base_v2` is correct. The guard's refusal behaviour is unchanged: it refuses on **zero**
  overlap, which is the signature of the wrong Qdrant, not of a legitimate multi-document cleanup.
- **Evidence:** `logs/p1/step10/{a4_dryrun.log,a4_apply.log,a4_verify.log,graph_after_cleanup.json,
  a5_preflight.log}`. No re-ingest.

---

### D15. P1 Step 10 §3d — retrieval-only run on the rebuilt index: a SMOKE TEST, not a measurement (2026-10-19)

- **What:** `scripts/evaluate_rag.py --query-file data/eval_queries_v2.json --retrieval-only
  --skip-visual` on `knowledge_base_v2` (133 text queries), after the §3c label clamp.
  `data/eval_results/p1-step10-retrieval-only_2026-10-20_0411.md`, exit 0, 200/200 processed.
- **Result:** R@20 **0.452** · Hit@20 0.910 · MRR 0.728 · NDCG@20 0.508 · R@100 0.626 ·
  abstention **28/34 = 0.824**. Per lane R@20: factual 0.570 · multihop 0.543 · overview 0.206.
- **Ceiling-normalised against §D9** (text 0.8016 / factual 0.9557 / multihop 1.0000 / overview
  0.3992) versus §D12's recorded baseline:

  | lane | §D12 raw | §3d raw | Δ raw | §D12 ÷ceil | §3d ÷ceil | Δ ÷ceil |
  |---|---|---|---|---|---|---|
  | text (all 133) | 0.465 | 0.452 | −0.013 | 0.5801 | 0.5639 | −0.0162 |
  | factual | 0.564 | 0.570 | +0.006 | 0.5901 | 0.5964 | +0.0063 |
  | multihop | 0.619 | 0.543 | −0.076 | 0.6190 | 0.5430 | −0.0760 |
  | overview | 0.178 | 0.206 | +0.028 | 0.4459 | 0.5160 | +0.0701 |

- ⚠️ **These are NOT comparable to §D12, and the run is deliberately labelled a smoke test.** Four
  independent differences, each sufficient on its own:
  1. **The DA lane is absent** — dead on every query (§I12 update: 768-vs-1024). §D12's DA lane was
     live. This is one fewer lane than §D12 had, in the recall direction.
  2. **Retrieval-only** — §D12 measured abstention with generation available (a declining answer
     counts); here abstention is score-threshold-only, so the **0.824 vs 0.500** jump is a *mode*
     difference, not a quality improvement. Do not read it as progress.
  3. **Index composition** — v2 is 3,796 chunks with no RAPTOR nodes; the old index was 5,135
     (5,051 chunks + 84 RAPTOR).
  4. **§3c's label clamp** landed between the two, moving the achievable maximum (0.9910 → 1.0000)
     but not the §D9 ceiling.
- **What it *is* good for:** it proves the retrieval path runs end-to-end on the rebuilt index and
  produces a complete report — the §D11 class of failure (rc=0 with an empty report) did not recur.
  It is also the first run to expose the dead DA lane, which is its most valuable output.
- **The authoritative run is deferred to Phase E**, per the Step 9 plan's §4 and the owner's
  decision (2026-10-19) — after Phase B/C/D, when DA / visual / graph are all about v2.
- **Evidence:** `logs/p1/step10/a3d_retrieval_only.log`;
  `data/eval_results/p1-step10-retrieval-only_2026-10-20_0411.md`. No re-ingest.

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
- ⚠️ **RE-MEASURED ON THE REAL CORPUS 2026-10-24 (session 16) — the merge is BIGGER than the fixture
  said: 33.6 %, not 27 %.** The numbers above are a **42-parent fixture** (`test_book.pdf`). On the
  live document `7ba61432` the raw chonkie segmentation yields **5,715 children** and the shipped
  `min_chunk_tokens=32` merge leaves **3,796** — so the merge removes **1,919 children (33.6 %)**.
  ⚠️ **This is a scope correction, not a disproof** — the fixture figure was right for the fixture.
  Also measured in the same probe, and load-bearing for the arm that settles this knob:
  **the E1 chunking is EXACTLY reproducible from the stored payloads** (341 parents reconstructed
  from `parent_id`/`parent_text`; re-cutting reproduces all 3,796 children boundary-for-boundary and
  text-for-text, in ~3 s) — so testing `min_chunk_tokens` needs **no Docling re-parse**; and the
  **embed cache cannot help such an arm** (`embed_cache.CachedParent.rebuild` validates against the
  live children's text and char spans, so a different cut is an honest miss).
  Evidence: `logs/p1/step10/rechunk_from_payload_probe.{py,json}` (sha256 `1c47e3bcbb203295…`).
  The arm is pre-registered: `.hermes/plans/2026-10-24-p1-min-chunk-tokens-ab-preregistration.md`.

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

**SWITCHED 2026-10-17 — the query side is on the dense lane.** Every call site in the table
above now embeds with the cluster dense lane (Qwen3, 1024d, query instruction), so the funnel
and the §D13 ablation can read a rebuilt collection. No re-ingest was needed for this.

| site | how it was switched |
|---|---|
| `src/frontend/streamlit_app.py` (query, HyDE) | `get_cluster_embedder(cfg)` — `embed_query` has the same signature, so it is a drop-in |
| `src/main.py` `/search` | `get_query_vector(req.query, settings)` — the single-accessor form |
| `scripts/evaluate_rag.py` | `get_cluster_embedder`; the config snapshot now reports `dense_model`/`dense_dim` |
| `scripts/funnel_boundary_recall.py`, `why_colbert.py`, `calibrate_eval_pages.py` | dense lane **and** the hard-coded `using="dense_768"` replaced by the collection-resolved name (`store._dense_vector_name()`), which was a second, independent reason the funnel could not read v2 |
| `src/core/intent_router.py` | prototypes embedded via the dense lane; the schema check now compares `n_features_in_` against `dense_dim` |
| `scripts/train_intent_classifier.py` | features from the dense lane; the report records `embedding_model`/`embedding_dim` |
| `scripts/preflight.py` | the classifier-width check compares against `dense_dim` |

**The intent classifier was retrained at 1024d** (plan R-a) — 1,158 validated queries (250
factual / 250 overview / 250 multihop / 408 visual), LogisticRegression, **96.6 % accuracy**
on the 232-item held-out split (macro F1 0.96; the confusion is overview↔multihop, 4+2 of 232).
The retired 768d model is preserved at `data/models/intent_classifier_768d.pkl.bak` — **note it is
gitignored (`data/models/*`), so a fresh clone does not get it**; the tracked copy is in git at
`git show 161e01b:data/models/intent_classifier.pkl`. Until a retrain, the router
now **rejects** the stale classifier loudly and falls back to 1024d prototypes — both states
are captured in the evidence.

**Evidence** (`logs/p1/step8/`): `probe_query_lane.py` run live against the cluster →
`evidence_pre_retrain.json` and `evidence.json`. Measured: query vector 1024d and unit-norm;
the query instruction IS applied (cosine against the same text embedded as a *passage* = 0.8436
— near 1.0 would mean the instruction never reached the model); the 64d MRL view matches the
inline `store` slice to 0.0; the 768d classifier is rejected pre-retrain and the 1024d one loads
and routes factual/overview/visual correctly post-retrain; the dense vector name resolves to
`dense_1024`. Suite: **361 pass / 4 pre-existing fail / 6 skip** (the 4 confirmed pre-existing
on a clean HEAD worktree — 2 `test_splade.py` fixtures + 2 zero-result searches).

**Finding while probing — the embedding endpoint returns UNNORMALISED vectors.** Measured:
pooled query norm ≈ 70.1, pooled passage ≈ 83.9, per-token ≈ 90–131. The **index** side always
normalised (`late_chunk_embedder._finish`); the **query** side did not, and neither did
`embed_documents` (which is what `raptor_tree._embed` uses for summary vectors). Invisible under
Qdrant's COSINE distance — it normalises internally, so no retrieval number moved — but any
dot-product consumer was off by a factor of ~6,000, and the class docstring claimed
"L2-normalised" the whole time. Fixed: the pooled paths normalise client-side (`l2_normalise`),
per-token stays raw (the mean is taken before normalising), pinned by
`test_cluster_embedder.py::test_pooled_paths_normalise_an_unnormalised_endpoint` and
`::test_per_token_path_stays_raw`.

**Consequence for R1's old-vs-new comparison.** One query path cannot address two different
vector dimensions, so the deployed `knowledge_base` (`dense_768`) is no longer *queryable by the
app* — the comparison now rests on the recorded artifacts (`logs/p0-9/v2_*.json`), not on
re-querying the old index. Nothing is deleted; pointing `QDRANT_COLLECTION` back at
`knowledge_base` is still a valid rollback, but it needs the query lane pointed back too
(`EMBEDDING_DIM`/`get_embedder`), which is now a deliberate two-part switch.

**Deliberately NOT switched — the concept-graph lane.** `graph_search` ranks **concept** nodes
in `concept_embeddings`, which is still built by the retired 768d embedder, so the UI passes it a
**separate** `graph_vec` (and the admin Graph Search tab still embeds with `get_embedder`).
Passing the dense lane's `q_vec` there would be a dimension error. This is a hold-back, not an
oversight — registered as **§I12**, released by Phase 3's re-index (plan Step 9). Two scripts that
also still write/validate the retired model are registered as **§I13**.

**Deviation from the plan's module map:** `ChunkingPipeline.process_all_documents` was **not**
written. It has no caller in a single-textbook repo, and an untested second entry point is
dead code from the day it lands. `process_pdf` is the whole API.

---

### E7. P1 Step 8 — the run: attempt 1 FAILED at 86 min (transient endpoint stall); pre-flight + diagnosis landed

- **What:** `scripts/ingest_base_textbook.py --pdf …feynman… --collection-name knowledge_base_v2
  --reindex` against the cluster — the E1/E2/E3 pipeline on the real 968-page book. Fresh
  collection (plan R1/R-d): the deployed `knowledge_base` is untouched, so a failed run costs
  nothing and rollback is pointing `QDRANT_COLLECTION` back.
- **Environment (two things must be passed on the command line, not read from `.env`):**
  `QDRANT_HOST=10.0.10.65` (blank in `.env`) and `SV_EMBED_URL=…:8123/embed-text/v1/embeddings`
  (**absent from `.env` — §I14**). `--reindex` is also mandatory: without it the script finds the
  old Feynman filename in `documents` and exits 0 having done nothing.
- **Dry run on the 19-page fixture (2026-10-17, `logs/p1/step8-run/dryrun_testbook.log`):** the
  exact entry point, real cluster, throwaway collection + scratch SQLite. 42 parents → 66 children,
  **82 s wall**, all four vectors on all 66 points, points == SQLite chunks == 66. Stage split:
  Docling parse ≈ 10 s (incl. ~9 s one-time model load), children 0.8 s, late-chunk 42 parents
  **47.5 s**, SPLADE 6.4 s, ColBERT 9.8 s, Qdrant upsert 1.5 s.
- **⛔ ATTEMPT 1 FAILED 2026-10-17 20:05:54 → 21:32:15 (86 min), exit 1.** It got **further than
  the plan expected** and then lost all of it: Docling parsed 968 pages in **4 min** (not the
  "tens of minutes" the plan feared) → **341 parents → 3,796 children** → the late-chunk phase
  ran **260 of 341 parents** (40.4 min, 360,685 tokens, 2,905 children) → parent 260's per-token
  call to `:8123` stalled and raised `httpx.ReadTimeout` → the process aborted. **Nothing was
  written:** `knowledge_base_v2` = 0 points, SQLite still holds only the old doc (`6d55c52b`,
  5,048 chunks) — `save_document` is the single write point and it runs only after *every* parent
  is embedded. The cluster was healthy before and after (a pooled call to `:8123` returned 200 in
  0.14 s immediately afterwards), so this was a **transient stall, not an outage**.
- **⛔ ATTEMPT 2 ALSO FAILED 2026-10-18 07:02:17 → 07:55:53 (53.6 min, exit 1) — the endpoint
  itself collapsed, and the retry could not save it.** Same pipeline, with the §I16 fix in place
  (retry + 8 workers). Parse 07:02:17 → 07:05:13 (341 parents, 3,796 children — **identical to
  attempt 1**, chunking is deterministic). Late-chunk ran **fast while healthy**: 142 parents in
  409.7 s = **2.89 s/parent, 470 tok/s** (attempt 1: 5.13 s/parent, 214 tok/s). Then the last
  parent completed at **07:12:05** and the log went **silent for 21.5 minutes**. The first retry
  was logged at **07:33:35**; from there 597 retries (589 `ConnectTimeout`, 8 `ReadTimeout`) ran
  at a steady ~26/min until 07:55:36, then the process died. **Nothing written again** — `v2` =
  0 points, SQLite untouched.
- **What this proves about the fix, and what it does not.** The retry **worked**: it converted a
  single-failure abort into ~600 attempts over 22 minutes instead of dying at the first timeout.
  It could not save the run because the service was *actually gone*, not stalling — `ConnectTimeout`
  means nothing was accepting the connection. The failure moved from "one bad read kills 86 min of
  work" to "a genuinely dead endpoint kills the run after 22 min of retrying", which is the correct
  behaviour for both.
- **The 21.5-minute silent window is the §I16 open item, now measured.** The workers were blocked
  inside requests that never returned and never tripped a read timeout (httpx's read timeout is per
  *read operation*, not per request — see §I16). So the retry had nothing to catch during that
  window: it only began firing once the sockets finally errored. **A hard total-request deadline is
  the fix**; without it any single hung request can silently consume the run.
- **⚠️ Whether the 8 workers contributed to the collapse is UNPROVEN and cannot be excluded.**
  Evidence that it did: the endpoint was healthy at 470 tok/s for 7 minutes under 8× load and then
  stopped accepting connections entirely — a crash/OOM signature, not a gradual slowdown. Evidence
  that it did not: the same endpoint measured **84 tok/s serial** on the morning of attempt 2 vs
  **214 tok/s** during attempt 1, i.e. it was already ~2.5× degraded *before* attempt 2 started and
  independently of this client; other cluster services (`:8000` sparse, LLM) stayed healthy; the
  Qdrant holds **34 collections** from other students, so the box is shared and contended. The
  honest reading: a cluster-side problem that concurrent load may have accelerated. **Do not re-run
  at 8 workers without deciding this.** §I18 records the probe's blind spot that made 8 look safer
  than it was.
- **⛔ ATTEMPT 3 FAILED 2026-10-18 08:41:17 → 09:48:05 (66.8 min, exit 1) — it reached 339 of 341
  parents and discarded everything.** The closest yet, and the clearest possible demonstration of
  the checkpoint gap. **⚠️ It also ran at 8 workers, not the 4 that had been decided** — `.env`
  carries `LATE_CHUNK_WORKERS=8` (added when 8 was still the default), `.env` overrides the config
  default, and the run was launched without asserting the effective value. Author's error, and the
  reason it is recorded here rather than quietly re-run.
- **The numbers:** 339/341 parents in **3826.4 s = 63.8 min**, 480,559 tokens, **11.29 s/parent,
  126 tok/s**. Only **15 retries** in the whole run (8 `ConnectTimeout` at 09:14–09:21, 7
  simultaneous `ReadTimeout` at 09:41:24), then parent 340 finished at **09:47:57** and the last
  parent(s) hit `ConnectTimeout` until the attempts were exhausted. **Nothing written again** —
  `v2` = 0 points, SQLite still 5,048 chunks / 1 document.
- **The retry and deadline both behaved correctly.** 15 retries absorbed 15 transient failures that
  would each have killed attempt 1 outright, and the 09:41 stall (7 workers timing out together,
  ~300 s of no data) was bounded by the per-read timeout rather than hanging. The failure was a
  genuinely unreachable endpoint at the very end, which no retry policy can fix.
- **Concurrency did NOT pay under sustained load — measured, and it contradicts the burst probe.**
  At 8 workers the run achieved **126 tok/s**; serial attempt 1 achieved **214 tok/s** median and the
  morning serial probe **84 tok/s**. Against the same morning endpoint, 8 workers bought only ~**1.5×**
  over serial (126 vs 84), not the 4–7× the burst probe promised. This is the strongest evidence yet
  that §I18's method note is the real lesson: **a burst probe cannot predict sustained behaviour on
  this endpoint.** 11.29 s/parent at 8 workers vs 5.13 s/parent at 1 worker in attempt 1 — the
  "concurrency" setting was slower than serial by 2.2×, on a comparable corpus.
- **Measured throughput, attempt 1 (from the log, all 260 completed parents):** median **5.13 s/parent**
  (mean 9.35, max **136.5**), parent size median 1,190 tokens (mean 1,387, max 4,762), median
  **214 tokens/s** (min **9**). The endpoint **degrades as the run proceeds** — the first 50
  parents averaged 10.8 s, the last 50 **16.5 s**, at near-identical token counts (1,378 vs 1,472).
  One parent took 136 s for only 1,180 tokens. So the tail of the run is the risky part, and the
  abort landed exactly there. Extrapolated full run: **~1.5 h** (≈ 62 min late-chunk + 4 min
  parse + ~6 min SPLADE + ~9 min ColBERT).
- **Root cause is a robustness gap, not a logic bug — registered as §I16.**
  `cluster_embedder._post` uses `httpx.Client(timeout=120)` and has **no retry**: one slow read
  aborts the whole document. Combined with the write path having no checkpoint, a single transient
  stall discards 86 minutes of cluster work. Re-running unchanged is a coin-flip at best — the
  same stall occurred at parent 219 (136 s) earlier in the *successful* stretch.
- **Consequence the plan's own verification misses — scope the counts by `document_id`.**
  `save_document` always creates a **new** document uuid, so the run *adds* a second
  `documents` row with the same filename and a second block of rows in `chunks`; the old doc
  (`6d55c52b`, 5,048 chunks) is left in place deliberately (its points live in the deployed
  collection). "Collection points == SQLite chunks" is therefore only true **per document_id** —
  compared against the raw table it will read as a mismatch of exactly the old corpus. The admin
  document list will also show the same filename twice until the old doc is retired (Step 10 /
  §E6 territory — not changed here).
- **Also observed:** the first run against the deployed SQLite applies the pending migrations
  (`chunks.parent_id`, `chunks.is_content`). Existing 5,048 rows get **NULL**, which is the
  intended §E5 behaviour — the retrieval filter is `must_not is_content == False`, so NULL rows
  stay retrievable and the deployed index is unaffected.
- **Verification tooling (landed with this step):** `logs/p1/step8-run/verify_collection.py`
  scrolls every point of a collection and reports per-lane coverage, exiting non-zero if any
  enabled lane is missing from any point — the check that catches **§I15**. Plus
  `probe_embedders.py` (resolves each embedder factory and encodes real text, so a broken lane is
  loud *before* a 1.5-hour run).

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
| G3 | **Entity resolution** (merge duplicate concept nodes) | **This is the known bug**: `'orbit'` / `'Orbit'` / `'planetary orbit'` / `'Planetary Orbit'` are separate nodes, so a query resolving to one spelling reaches only that spelling's chunks. **Sized 2026-10-20 (§I30): 1,186 merge groups covering 2,692 concepts = 34.4 % of the vocabulary; no group gains nothing; `force` 95 → 175 chunks, `kinetic energy` 51 → 102.** ⚠️ *"most chunks tie at 1 matched concept"* is a **query-side** statement — a chunk mentions 4.25 concepts on average (§I29). The course has a dedicated lab for exactly this step |
| G4 | **global / local / drift query modes** | To brainstorm — the project has one traversal mode. Drift is the interesting one for multihop |
| G5 | **Genuine multi-hop traversal** | `hop_distance` is currently a constant 0, so "multihop" is nominal |

### G1 outcome — BUILT, MEASURED, and the ablation says NO (2026-10-21)

**Built:** `src/pdf_ingestion/graph_analytics.py::personalized_pagerank` — the syllabus iteration
verbatim, `v(k+1) = (1−lam)·W·v(k) + lam·v(0)` with `W = D⁻¹A` over the weighted `RELATES_TO`
adjacency, `lam = 1/2`, 10 iterations (commit `e78a7ef`; 18 unit tests; behaviour probe
`logs/p1/step10/g1_ppr_probe.py`). ⚠️ `W = D⁻¹A` is row-stochastic, **not** doubly stochastic, so
total mass is conserved only on a regular graph — the probe reports `sum(v) = 8.23` and the output
is deliberately **not** normalised. That is the specified iteration, not a defect.

**Measured — verifier 4, the ablation (`logs/p1/step10/g1_ppr_ablation.py`, commit `50af094`):**
40 multihop gold queries, both arms seeing the same seeds and the same candidates and differing
only in the ranking key.

| metric | fixed-hop | PPR | delta (ppr−fixed) | 95 % CI | verdict |
|---|---|---|---|---|---|
| MRR | 0.2889 | 0.2550 | **−0.0339** | [−0.0877, +0.0199] | UNRESOLVED |
| R@3 | 0.1684 | 0.1201 | **−0.0484** | [−0.1042, +0.0075] | UNRESOLVED |
| R@5 | 0.2062 | 0.1742 | −0.0319 | [−0.1059, +0.0420] | UNRESOLVED |
| R@10 | 0.2248 | 0.2137 | −0.0111 | [−0.0661, +0.0439] | UNRESOLVED |
| R@20 | 0.2556 | 0.2653 | +0.0097 | [−0.0093, +0.0288] | UNRESOLVED |

**Verdict: PPR re-ranking does not improve the graph lane.** No metric resolves, and the point
estimates are negative at every cut that can discriminate. The one positive figure (R@20) sits at
the cut that bites on **7 of 40** queries.

**⚠️ Two limits, both in the artifact — do not quote these numbers without them:**
1. **The test is structurally weak.** The lane's candidate pool is median **7.5 chunks / 6.5 pages**
   per query, so a page-level Recall@k above the pool is inert: the cut returns the whole set and
   **both arms are identical by construction**. `meta.power.cut_bites_at_k` counts the queries where
   the cut can change the set — k=3: 35/40, k=5: 24/40, k=10: 13/40, k=20: 7/40.
2. **Candidate EXPANSION was not tested** (chunks that mention no seed concept but are graph-near).
   Verifier 4 specifies a ranking comparison, so that is what ran. **A null here is not evidence
   that PPR cannot help the lane** — it is evidence that *re-ranking alone* does not, on this graph,
   at this pool size.

**Confounds measured, not assumed:** `concept_embeddings` holds **15,276** points while Memgraph
holds **7,834** `Concept` nodes — of which **7,808** carry at least one `RELATES_TO` edge. That
second figure is the node count of the graph PPR actually runs on, and it is the PPR **behaviour**
probe (`logs/p1/step10/g1_ppr_probe.json`, `graph.nodes`) that prints it — **not** the ablation
artifact, whose `meta.graph` is only a host string. **Do not confuse the two** (a reviewer did,
2026-10-21; the first draft of this sentence then blamed the wrong artifact, and a second pass
caught it). A top-8 seed can therefore name a concept absent from the graph — **mean 3.02 of 8** do. Both arms see the same seeds so the delta is unaffected, and the artifact *verifies* that a
graph-restricted seed set agrees exactly with the unrestricted one (an absent seed matches no node
in either arm), which is the evidence the confound is inert here. This ran **before** the §I21
rebuild, so it is a before-arm; §G3's merges would move it again.

**Verification:** `openai/gpt-oss-20b`, delegs `deleg_2c9e024e` (9/9 confirmed, re-ran the probe)
and `deleg_96b9a464` (5/5). **Spot-checked by the author**, because 4 of the 9 were confirmed from
the probe's *docstring* rather than its code — re-read the code and the mechanism holds.

**⚠️ WHY EVERY METRIC IS UNRESOLVED — three separate causes, decomposed 2026-10-21.** "Unresolved"
means the 95 % CI on the paired difference spans zero. It is **not** "no difference found", and the
distinction matters here because the instrument is mostly inert:

| metric | cut bites | queries that actually DIFFER | mean Δ | SD | CI half-width | N needed for δ=0.05 |
|---|---|---|---|---|---|---|
| MRR | — | 13/40 | −0.0339 | 0.1736 | 0.0538 | **95** |
| R@3 | 35/40 | **7/40** | −0.0484 | 0.1803 | 0.0559 | **102** |
| R@5 | 24/40 | 6/40 | −0.0319 | 0.2387 | 0.0740 | **179** |
| R@10 | 13/40 | 4/40 | −0.0111 | 0.1776 | 0.0550 | **99** |
| R@20 | 7/40 | 3/40 | +0.0097 | 0.0615 | 0.0191 | 12 |

1. **The ranking cannot matter for most queries.** At k=20 the cut returns the *entire* candidate
   pool for 33 of 40 queries, so both arms return the same set — **37/40 queries are exactly equal**.
   That is identity by construction, not a measurement, and it is why the single positive figure
   (+0.0097 at R@20) is the *least* trustworthy number in the table.
2. **Even where the cut bites, almost nothing moves.** At k=3 the cut bites on 35/40 queries but only
   **7** change. The metric is **page-level and coarse**: pages dedupe and count once, at their best
   chunk's rank, so reordering chunks usually leaves the retrieved page *set* unchanged. The ranking
   moves chunks; the metric counts pages, and is blind to most of what the ranking does.
3. **Power.** Where a query does move it moves a lot — one relevant page entering or leaving the
   top-k is worth 1/|relevant| ≈ 0.33 on a 0–1 scale — so SD is 0.17–0.24 against a mean of
   0.03–0.05. At n=40 the design is **underpowered 2.4–4.5×**.

**Consequence — do NOT read this as evidence against PPR either.** Every metric that moves at all
moves *negative*, but never far enough from zero to be called. To actually settle §G1 the lever is a
**different instrument**, not more of the same: ~100+ multihop queries, or a **chunk-level** metric
that responds to a reordering, or the **expansion arm**, where the candidate pool is larger and the
cut genuinely bites.

**✅ CLOSED 2026-10-21 (owner decision) — measured-and-negative; the fixed-hop ranking stays.**
§G1 ships nothing. The null *is* the finding: on this graph, at this pool size, PPR re-ranking does
not beat the fixed-hop ordering, and every cut that can discriminate points negative.
`graph_analytics.personalized_pagerank` stays in the tree as a measured, unit-tested module — it is
the syllabus algorithm implemented faithfully and the behaviour probe
(`logs/p1/step10/g1_ppr_probe.json`) is the record of what it does — but it is **not wired into the
retrieval path**, and nothing depends on it. **The expansion arm is NOT authorised and is not a
pending task**: it stays recorded above as the one untested lever, because it is a *different
treatment* (PPR *selecting* candidates, not ordering them), it would need its own pre-registration,
and it would need a chunk-level instrument to be readable at all. **Do not re-run this ablation
unchanged** — a future revisit needs one of: ~100+ multihop queries, a chunk-level metric that
responds to a reordering, or the expansion arm.

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

> ⚠️ **CORRECTED 2026-10-20 — "nearly every chunk ties at 1" is only true on the QUERY side, and the
> plan's G3 verifier quotes it as if it were a property of chunks.** Measured: a chunk mentions a mean
> of **4.25** distinct concepts, and **96.9 %** of concept-bearing chunks mention ≥2 — so that reading
> has 3.1 points of headroom and cannot discriminate. The "ties at 1" claim is about
> `matched_concepts` in `graph_search` — how many of the **query's** 8 concepts a chunk matches
> (`graph_builder.py:449-459`). The **lever** half of this entry is confirmed and sized: see **§I30**
> (1,186 merge groups, 34.4 % of the vocabulary, no group gains nothing). The **query-side** number
> remains unmeasured — see **§I29**.

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

### I12. NEW 2026-10-17 (found switching the query side, §E6) — `concept_embeddings` is still a 768d collection, so the graph lane is on its own lane

- **What:** the query side moved to the cluster dense lane (Qwen3, 1024d), but
  `concept_embeddings` — the collection the concept-graph lane ranks against
  (`graph_builder._find_concepts_scored`) — is **still built by the retired local Nomic 768d
  embedder** (`graph_builder.py:266`, `get_embedder(cfg).embed_query(name)`). The two spaces
  cannot be mixed: a 1024d query against a 768d collection is a dimension error.
- **Consequence:** the UI now embeds a **second** vector for that lane
  (`streamlit_app.py`: `graph_vec = get_embedder(cfg).embed_query(query)`) and the admin Graph
  Search tab still uses the retired embedder. So the switch is *complete for the KB lanes and
  deliberately partial for the graph lane* — not an oversight, and no silent degradation:
  the lane keeps working exactly as it did before.
- **Why it matters beyond the UI:** `store.py` creates `concept_embeddings` (and
  `derivative_artifacts`) at `cfg.embedding_dim` (768) in `_ensure_concept_collection` /
  `_ensure_da_collection`. On a fresh machine those collections are *created* 768d, so the
  split is not just legacy data — it is the current default. Any future "point the query side at
  the dense lane everywhere" change must move these three collections in the same pass.
- **Fix:** Phase 3's re-index (plan Step 9) rebuilds `concept_embeddings` with the dense lane and
  re-embeds concept names; `_ensure_*_collection` switches to `dense_dim`; the second `graph_vec`
  in the UI is deleted. **Also unblocks §G3 (entity resolution)**, which wants a re-write of the
  concept nodes anyway.
- **Cost:** needs a Phase-3 re-index (embedding calls for every concept name) — no re-ingest of
  the text corpus.
- **Not blocking Step 10.** The funnel and the reranker ablation live entirely in the text lane.

**Update 2026-10-19 (P1 Step 10 §3d) — measured: the claim "no silent degradation" holds for the UI
but NOT for `evaluate_rag.py`, where the DA lane is dead on every query.**

The Step 10 §3d retrieval-only run logged, for **every** query:

    WARNING | store:search_da:604 - DA search failed (Unexpected Response: 400 (Bad Request)
    b'{"status":{"error":"Wrong input: Vector dimension error: expected dim: 768, got 1024"}}'),
    skipping DA lane

- **Why:** `store.search_da(query_vector, …)` queries `derivative_artifacts` with the **caller's**
  vector. `streamlit_app.py` avoids this by embedding a second 768d vector for the graph lane — that
  is what makes the "no silent degradation" claim true *there*. `evaluate_rag.py` has no such second
  vector: it passes the dense-lane 1024d vector straight in, so the query is rejected on every call
  and `search_da`'s `except Exception` returns `[]`. **The DA lane contributes nothing to any
  `evaluate_rag.py` number**, and nothing in the report says so — the only trace is a WARNING line
  per query in the log.
- **Consequence for the record:** every `evaluate_rag.py` measurement taken after the 2026-10-17
  query-side switch (Step 7b, §E6) has had **one fewer lane than it appears to**. §D12's baseline
  (2026-10-16) predates that switch, so its DA lane *was* live — one more reason §D12 and any later
  run are not like-for-like. Counted in the §3d run: **152 DA-lane skips** across the 166 non-visual
  queries.
- **Why the preflight does not catch it:** `preflight.py` passes `qdrant.derivative_artifacts` on a
  **point count** alone (81,837). It never issues a query against the lane, so a lane that cannot be
  called at all still reads PASS. A dimension-compatibility probe per named-vector collection would
  have caught this — worth folding into the §I12 fix.
- **Fix:** the same one §I12 already names — Phase 3's re-index moves `derivative_artifacts` and
  `concept_embeddings` to `dense_dim` in one pass. Until then, any `evaluate_rag.py` run must be
  labelled "DA lane absent".
- **Evidence:** `logs/p1/step10/a3d_retrieval_only.log` (the WARNING lines);
  `data/eval_results/p1-step10-retrieval-only_2026-10-20_0411.md` (the report, which does not
  mention the missing lane). No re-ingest.

### I13. NEW 2026-10-17 (found switching the query side, §E6) — two scripts still write/validate the retired 768d model

- **What:** after the switch, `get_embedder` (the retired local Nomic embedder) is still called by:
  - `scripts/reembed_chunks.py:54` — **writes 768d vectors into the KB collection.** It was
    already stale for the 4-vector schema (it writes a bare `{"dense": [...]}`), and it now also
    targets the wrong dimension, so running it against a rebuilt collection fails loudly on the
    dimension rather than silently corrupting — which is the better of the two failure modes, but
    it is not a working recovery path for the new index.
  - `scripts/validate_embedders.py:115` — a diagnostic that checks query/passage discrimination of
    the **local** embedder (it normalises both sides itself, so its own numbers stay valid). It now
    validates a model the query path no longer uses, which reads as a green light for the wrong lane.
- **Why it matters:** `reembed_chunks.py` is the documented recovery path when Qdrant is empty but
  SQLite has chunks (its own docstring). After Step 8 that path is broken, and the failure is only
  discovered at recovery time — the worst moment.
- **Fix:** `reembed_chunks.py` moves to the dense lane and writes the full 4-vector payload
  (`dense_64` + the collection's dense slot, + colbert/sparse where enabled) — i.e. it should
  reuse `store.save_document`'s payload builder instead of re-declaring it. `validate_embedders.py`
  should validate the dense lane (and keep the legacy check only as an explicit
  `--legacy-embedder` mode).
- **Cost:** small — two scripts, no re-ingest. Not on the critical path; do it before anyone needs
  a recovery.

**Update 2026-10-21 (session 6) — the two scripts are addressed, and the "small" cost above is WRONG
for `reembed_chunks.py`. It is a re-ingest-shaped job, and the script now REFUSES rather than
half-doing it.**

- ✅ **`validate_embedders.py` — DONE.** The dense lane is now the default and the retired 768d Nomic
  check sits behind an explicit `--legacy-embedder` flag, with the lane named in its output. That is
  the whole fix the entry asks for.
- ⚠️ **`reembed_chunks.py` — the fix is NOT "move it to the dense lane".** Measured on the live
  collection 2026-10-21: `knowledge_base_v2` requires **four** lanes on every point —
  `dense_64` (64d), `dense_1024` (1024d), `colbert` (128d **multivector**, `max_sim`) **and** the
  sparse vector `sparse`. This script computes **only the dense one**. Because Qdrant accepts a point
  with named vectors **absent**, a dense-only upsert would *succeed* and leave the ColBERT and SPLADE
  stages of the funnel looking at nothing — a **degraded index that looks recovered**, discovered at
  the worst possible moment (which is what this entry's own "Why it matters" warns about). So the
  entry's fix text ("reuse `store.save_document`'s payload builder") is right but understated: it
  means recomputing every lane, including the re-normalised 64d MRL truncation (`ARCHITECTURE.md` §8
  trap 5) and the multivector/sparse payload shapes — not re-pointing one embedder.
- **What was done instead, deliberately:** the script now exits with the reason and the path forward
  rather than writing a partial payload. Measured: `reembed_chunks.py --doc-id 7ba61432…` against the
  cluster → `REFUSING: collection 'knowledge_base_v2' expects named vectors ['colbert', 'dense_1024',
  'dense_64'], and this script computes only the dense lane(s). Writing it would leave ['colbert',
  'sparse'] ABSENT on every point …`, exit 1, nothing written. It is still a loud failure (it already
  failed loudly at the upsert with a vector-name error), but now it fails with the reason and before
  any work.
- **Still open, and now correctly scoped:** extend `reembed_chunks.py` to rebuild all four lanes.
  Until then the documented recovery path for "Qdrant empty, SQLite intact" is
  `scripts/ingest_base_textbook.py --reindex`, not this script.
- **No re-ingest. No LLM calls.**

### I14. NEW 2026-10-17 (found pre-flighting Step 8) — `SV_EMBED_URL` is missing from the live `.env`, and the whole query path now needs it

- **What:** `SV_COLBERT_URL` / `SV_SPARSE_URL` / `SV_RERANK_URL` are set in `.env`, but
  **`SV_EMBED_URL` is not** — it exists only in `.env.example` (`:8123/embed-text/v1/embeddings`).
  `Settings.sv_embed_url` therefore resolves to `""`, and `ClusterDenseEmbedder.__init__` raises
  `ValueError("... requires sv_embed_url (set SV_EMBED_URL)")`.
- **Why it matters now and not before:** §E6 moved the *entire* query side — the UI, `main.py`,
  `evaluate_rag.py`, `funnel_boundary_recall.py`, `calibrate_eval_pages.py`, `why_colbert.py` and
  the intent router — onto the cluster dense lane. Before the switch the dense lane was only used
  by the re-ingest probes, which set the variable inline on the command line (as `logs/p1/step7/README.md`
  documents). After the switch, **every query-side entry point fails at runtime on a machine whose
  `.env` lacks the key** — which is this one. It fails loudly (a `ValueError`, not a silent
  fallback), so nothing is corrupted; the app simply does not start a search.
- **Consequence for the run:** Step 8 must export `SV_EMBED_URL` explicitly (the run script does),
  and so must anyone who starts the app.
- **Fix:** add `SV_EMBED_URL=http://10.0.10.70:8123/embed-text/v1/embeddings` to `.env`, beside the
  other three. (`.env` is not agent-writable — the owner must add it, or it goes in via
  `hermes config`/a manual edit.)
- **Cost:** none. No re-ingest.
- **Note the port split is real and is the §I11 class again:** the live `.env` points sparse/colbert/
  rerank at `:8000` while `.env.example` says `:8123`. Both were probed 2026-10-17 and **both
  answer** (SPLADE 200 with 60 non-zero indices; ColBERT 200 with a `(20, 128)` matrix) — but the
  two files disagreeing about the same service is exactly how a future 404 gets introduced.

### I15. NEW 2026-10-17 (found pre-flighting Step 8) — `save_document` swallows SPLADE/ColBERT failures, so an incomplete index is reported as a success

- **What:** `DocumentStore.save_document` wraps both optional lanes in a bare
  `try/except Exception -> logger.warning("... falling back to dense-only")`
  (`store.py:204-211` SPLADE, `:215-222` ColBERT). A missing model, an unreachable endpoint or a
  shape mismatch does **not** fail the ingest: the run completes, prints the green
  "✓ Ingestion complete" panel, and writes points that carry only `dense_64` + `dense_1024`.
- **Why it matters:** this is the §I9 shape at the *index* level rather than the query level, and
  it is worse to detect. A point missing its `sparse` vector is still a valid point, still counted,
  and still returned by a dense-only search — so every count-based check the plan prescribes
  ("collection points == SQLite chunks") **passes on an index whose hybrid lane is empty**. The
  failure surfaces much later, as "hybrid search adds nothing", with no error anywhere.
- **Measured (Step 8 dry run, 2026-10-17):** on `test_book.pdf` both lanes were in fact healthy —
  SPLADE via `ClusterSpladeEmbedder`, ColBERT via `ClusterColBERTEmbedder` (both at `:8000`), all
  four vectors present on all 66 points. So this is a **latent** hazard, not a live break.
- **Mitigation landed with Step 8:** `logs/p1/step8-run/verify_collection.py` scrolls every point
  and reports, per named vector, how many points carry it — and **exits non-zero** if any lane is
  missing from any point. That check is what the run's verification now uses, in addition to counts.
- **Options for the real fix (not decided):** (a) collect the failures and raise at the end of
  `save_document` if any lane that is `enabled` produced nothing; (b) keep the fallback but return
  the per-lane counts so the ingest report can print "SPLADE 0/3,796" — the §I9 option (b) shape.
  **(a) is recommended for the re-ingest path specifically**, where a half-written collection costs
  a full re-run to correct.
- **Cost:** small. No re-ingest.

### I16. NEW 2026-10-17 (found by Step 8's failed run) — `cluster_embedder._post` has NO retry and a 120 s read timeout, so one transient stall discards a 90-minute run

- **What:** `ClusterDenseEmbedder._post` (`cluster_embedder.py:150-177`) builds
  `httpx.Client(timeout=120)` and issues each batch as a **single un-retried POST**. Any
  `httpx.ReadTimeout` / `ConnectError` / 5xx propagates straight out of `embed_documents_tokens`,
  through `LateChunkEmbedder.embed_parent`, and aborts the whole document. Measured: the Step 8
  run died this way at parent **260 of 341**, after 86 minutes, having embedded 360,685 tokens.
- **Why it is worse than a normal flaky-call bug:** the ingest has **no checkpoint**. The
  pipeline is parse → children → embed *every* parent → `save_document`, and `save_document` is
  the only write. So the failure mode is not "lose one parent", it is "lose the entire document" —
  86 minutes of cluster work, and the next attempt starts from zero. The plan's R-d says the run is
  "resumable only at document granularity", which is accurate but understates it: a *single* bad
  read inside that document is enough.
- **It is not an outage, it is variance.** A pooled call to the same endpoint returned 200 in
  0.14 s immediately after the abort. In the 260 parents that *did* succeed, throughput ranged
  from **214 tokens/s median** down to **9 tokens/s** on one parent that took 136 s for 1,180
  tokens — i.e. the same stall happened earlier and got lucky. And the endpoint **degrades as the
  run proceeds**: first 50 parents averaged 10.8 s, last 50 averaged 16.5 s at the same token
  counts. The risky region is the tail, which is exactly where the abort landed.
- **Why the 120 s timeout does not bound the damage:** httpx's read timeout is per *read
  operation*, not per request. A response body that keeps trickling (the per-token payload is
  ~160× the pooled one — §E3) resets the timer on every chunk, so a pathological stall can burn
  far longer than 120 s before it trips. The measured gap between the last success and the abort
  was **42 minutes**, consistent with a slow drip rather than a clean timeout.
- **Fix (not yet applied):** bounded retry with exponential backoff around the POST in
  `_post` (the repo's own `scripts/` code already uses a retry helper for the LLM path), plus a
  read timeout sized for the per-token payload rather than the pooled one, and a log line when a
  retry happens. Separately worth considering: a **per-parent checkpoint** (persist embeddings as
  they are computed, or write the collection in parent batches) so the loss window is one parent
  instead of one document. The retry is the small fix and the one that would have saved this run.
- **Cost:** small for the retry (one function + tests + review); larger for checkpointing.
- **Blocks Step 8's re-run** — see §E7. A re-run without this fix is a coin-flip.
- **FIXED 2026-10-17 (same session):** `_post` now goes through `_post_with_retry` —
  bounded (1 + 3 attempts), jittered exponential backoff (2 s doubling, ×[0.5, 1.5)), retrying
  only what could plausibly succeed (`httpx.TransportError` — the parent of timeouts and
  connect/read errors — plus HTTP 429 and 5xx; other 4xx fail immediately). The read timeout is
  now **per path** instead of one flat 120 s: 120 s pooled, **300 s per-token**, with a 10 s
  connect timeout. The per-token raise is justified by measurement, not caution — a 4,647-token
  parent took **92 s** end to end against the live endpoint, so the old flat 120 s was marginal
  for a legitimately slow large parent, and a false trip on a healthy request is its own bug.
  Six tests pin the policy (retry-then-succeed, backoff growth + jitter, 5xx retried, 4xx not
  retried and not slept on, attempts bounded at 4, per-path timeouts). Suite **370 pass / 4
  pre-existing fail / 6 skip**; ruff identical to baseline.
- **ALSO FIXED in the same pass — the reason the retry alone would not have been enough:**
  the loop that *issues* those calls was strictly serial. `LateChunkEmbedder.embed_children`
  now embeds parents concurrently via a `ThreadPoolExecutor` (`late_chunk_workers`, default 8),
  reassembling results in parent order so the output is byte-identical to the serial path.
  Measured against the live endpoint (`logs/p1/step8-run/probe_concurrency_knee.py`, 1,749-token
  payload): aggregate throughput **84 tok/s at 1 worker → 597 tok/s at 16**, no errors, no
  collapse. Serial latency is ≈ `5.2 s + tokens/53` — i.e. **~5 s of fixed per-request overhead**,
  which is why concurrency pays here and why 341 serial parents cost ~30 min in overhead alone.
  8 is the conservative default: the knee was still rising at 16, but that was a short burst on a
  cluster shared with other students, and the same endpoint measurably degrades under sustained
  load (first 50 parents 10.8 s avg → last 50 16.5 s in the failed run).
- **✅ FIXED 2026-10-18 — the total-request deadline, which is the shape the retry could not
  catch.** `_post_json` now reads the response body in chunks against a wall clock and raises
  `httpx.ReadTimeout` (deliberately — it is a `TransportError`, so the retry treats it as
  transient and re-issues on a fresh connection) once one request exceeds its budget:
  **300 s pooled, 900 s per-token**. The per-read timeout above cannot do this job: it is per
  *read operation*, so a trickling body resets it on every chunk. Measured cost of the gap —
  attempt 2 sat **silent for 21.5 minutes** inside exactly such requests, and because no timeout
  fired, the retry had nothing to catch. Three tests pin it: a deliberately slow-dripping response
  stream (81 chunks, would take ~6 s unbounded) is cut off, retried 4 times with 3 backoffs, and
  finishes in under 3 s; a normal response is unaffected; and the per-token deadline is asserted
  to exceed the pooled one. **A test-fixture bug found on the way:** the `no_sleep` fixture patched
  `"...cluster_embedder.time.sleep"`, which resolves to the GLOBAL `time` module and therefore
  neutered every other sleeper in the process — including the slow stream it was meant to be
  measuring against, which is why the first version of the test passed vacuously ("did not raise").
  It now replaces the module's own `time` binding via a shim, keeping the blast radius at one
  module.
- **Still open — checkpointing.** The deadline bounds a single request, but the ingest still has no
  per-parent checkpoint: a failure at parent 340 of 341 discards the whole document, because
  `save_document` is the only write point. The retry and the deadline make that much less likely
  (two independent failure shapes are now handled) but they do not make it cheap. Registered, not
  claimed fixed. **⚠️ This was the single most valuable remaining fix — see §I19 (built
  2026-10-18) and §I19a (in attempt 5, the run it was built for, it hit nothing).**

### I19. NEW 2026-10-18 (found by Step 8 attempt 3) — the ingest has no checkpoint, so 339/341 parents of finished work can be discarded by one unreachable request

- **What:** the ingest computes every parent's embeddings in memory and writes **once**, at the end,
  via `save_document`. There is no per-parent persistence and no resume. Attempt 3 completed
  **339 of 341 parents** (63.8 min, 480,559 tokens) and then hit `ConnectTimeout` on the last
  parent(s); the process aborted and **all 63.8 minutes were discarded** — `knowledge_base_v2` is
  still at 0 points. Attempts 1 and 2 lost 86 and 53.6 minutes the same way.
- **Why it is now the top fix:** three consecutive failures have each discarded a nearly-complete
  document, and the pattern is stable — the endpoint is flaky enough that *some* failure is likely
  on any 60–90 minute run, so the expected cost of a re-run is the full run every time. With a
  checkpoint, attempt 4 would need only the **2 missing parents**; without one it needs all 341.
  Retry and the deadline (both now landed) reduce the *probability* of an abort; a checkpoint reduces
  its *cost*, which is the part that is currently unbounded.
- **Why it is not a two-line change (and was not bundled):** the obvious version — write to Qdrant
  and SQLite per parent batch — would make a partially-written collection look complete to every
  downstream reader (the funnel, the eval, the UI), which is a worse failure than a clean abort. The
  safer shape is a **side-car resume cache**: for each (pdf content hash, `parent_id`), persist that
  parent's pooled child vectors (`dense_1024`, `dense_64`, `token_span`) to disk as the parent
  completes; on re-run, load the cache, embed only the missing parents, and keep `save_document` as
  the single atomic write point. That preserves the one-write invariant, needs no schema change, and
  is invalidated by hashing the PDF plus the chunking config (parent_max_tokens, semantic_threshold,
  min_chunk_tokens) so a config change cannot silently reuse stale vectors.
- **Cost:** medium — a cache module, its invalidation key, and tests. Needs independent review like
  any other source change. No re-ingest of the corpus is implied (it only affects the run).
- **Evidence it would have worked:** attempt 3's 339 completed parents are exactly the population
  the cache would have held; the 4th attempt's late-chunk phase would have been 2 requests instead
  of 341.
- **✅ BUILT 2026-10-18** — `src/pdf_ingestion/embed_cache.py` + wiring, 19 tests. Full detail in the
  commit messages; the four things worth keeping in the register:
  1. **The first version could never have worked in production, and its tests passed anyway.**
     A hit was validated by comparing `chunk_id` — which is `str(uuid.uuid4())`, minted fresh every
     run — so the ids could never match across runs and the cache would have silently never hit,
     while looking perfectly healthy (files written, no errors, zero benefit). The tests missed it
     because they handed the SAME child objects to both passes, so the uuids happened to agree: the
     test was measuring its own object reuse. Verified against the real chunker that two calls give
     different ids and identical text+spans. **Fixed** by keying on content — a sha of each child's
     text plus its char span. **Third instance in one session of a test that passes while proving
     nothing about production** (see `RETROSPECTIVE.md` §4).
  2. **`np.savez(path)` silently appends `.npz`.** Writing to `p0.npz.tmp` actually created
     `p0.npz.tmp.npz`, so the `os.replace` failed on a file that was never created and **every
     write failed**. Fixed by writing through an open handle.
  3. **A "never raises" function that could raise.** `mkdir` sat outside the `try` in `put`, and the
     cleanup `unlink` could fail the same way the write did — so an unusable cache directory would
     have aborted an ingest. A cache that can fail a run is worse than no cache. Both fixed.
  4. **`chunk_size` measured INERT**, so the fingerprint's field list is evidence-based rather than
     guessed: varying it 128/256/512/1024 on an 8,600-char parent produced byte-identical children.
     What actually moves boundaries is `semantic_threshold` (0.8 → 2 children, 0.3 → **39**) and
     `min_chunk_tokens` (32 → 2, 300 → 1) — both already present. `chunk_size`/`chunk_overlap` are
     carried anyway as cheap insurance, and the comment says so. A `_CACHE_SCHEMA_VERSION` constant
     is included in the fingerprint to cover the case config cannot: a **code** change that alters
     chunking or vectors.
- **Independent review (round 2), adjudicated not accepted.** One reviewer, `openai/gpt-oss-20b`,
  single-turn, returned `passed:false` with 6 findings in 17.5 s / 1 API call. Adjudicated against
  the running code:

  | # | claim | verdict |
  |---|---|---|
  | 1 | fingerprint omits `chunk_size`, and omits the chunker code entirely | **half real** — `chunk_size` measured inert, but both it and a code-version constant are now included |
  | 2 | 64-bit sha prefix risks collision | **not worth changing, changed anyway** — widened to 128 bits at zero cost |
  | 3 | counters are unlocked | **real but unobservable here** — see below |
  | 4 | temp-file name could collide across processes | **not applicable** — single writer per parent, one process |
  | 5 | `dense_1024` is a view into the npz, invalid after the file closes | **FALSE** — measured: the array reads correctly after close (sum exactly 1024×1.5); numpy reads the member into memory |
  | 6 | a truncated npz could load partially and be used silently | **FALSE** — measured: truncated and garbage both raise and are caught as a safe miss |

  **Finding 3 is the interesting one.** The reviewer is theoretically right that `self.hits += 1`
  is a read-modify-write. But measured directly, an **unlocked** increment lost **zero** at 8×25,
  16×150 and **32×300** thread-iterations with `sys.setswitchinterval(1e-6)` — CPython's GIL plus
  the specializing interpreter complete the sequence inside a time slice. The lock is kept as cheap
  insurance (it is load-bearing on a free-threaded build), and the test **says in its own docstring
  that it does not discriminate on this interpreter**, rather than implying it proves the fix.
  An earlier version of that test appeared to fail against the unlocked counter; re-measured in
  isolation it does not, so that observation is not relied on. **Two of six findings were false,
  one was a non-issue, and none was a defect in the shipped code** — which is the same shape as the
  previous round and is why reviewer output is treated as candidate defects, not verdicts.

#### I19a. NEW 2026-10-18 (found by Step 8 attempt 5) — the cache hit NOTHING in the run it was built for: a digest-width change with no schema bump left every entry permanently unmatched

- **What:** attempt 5 logged `Late-chunk cache: 341 hits / 0 misses / 341 written (key
  2ec020b785942cf2)` and then **rejected all 341 entries** — one
  `Late-chunk cache: entry for parent N does not match the current children — re-embedding` warning
  per parent, 341 of them, and the full **36.1-minute** late-chunk phase re-embedded from scratch.
  The run that §I19's cache was built for is the one run where it delivered **zero** benefit.
- **Root cause, measured.** Commit `f0098a1` widened the per-child digest `_text_sha` from
  `sha1(text)[:16]` to `[:32]` — a change to the cache's **identity function** — while leaving
  `_CACHE_SCHEMA_VERSION` at `1`. So the old entries stayed *reachable*: they sit in the same
  fingerprint directory the current code computes, are read successfully by `get()`, and can never
  compare equal, because `rebuild()` compares a 32-char digest against a stored 16-char string.
  - Why attempt 4's entries are in the *new* directory: attempt 4 launched at **11:26:08** from a
    working tree mid-edit — the 9 fingerprint fields and `schema=1` were already on disk, the
    widening was not — and imported that half-edited module. It wrote its entries at 11:40–11:51.
  - Evidence: the live directory held **341** entries in two vintages — ids **0–215 `<U32`**
    (attempt 5, 12:19 onward) and **216–340 `<U16`** (attempt 4, 11:40–11:51). Recomputed for the
    run's own config, `fingerprint()` returns `2ec020b785942cf2` exactly, so both vintages resolve
    to one directory. 125 legacy entries remain on disk, unreachable by construction.
- **Why it matters beyond the wasted 36 minutes:** the guard and the defect shipped in the **same
  commit**. `_CACHE_SCHEMA_VERSION` exists precisely for "a CODE change that alters the children or
  the vectors, even if no config value does" — and the change that broke the cache was a widening
  of the digest, which is that case. A guard introduced alongside the defect it fails to catch is
  the §I19 point 1 pattern again in a different costume: the previous instance was a test that
  proved nothing about production; this is a version constant that guarded nothing.
- **Second-order defect — the counter reads as success.** `get()` increments `hits` when the file
  *loads*, before `rebuild()` validates it, so the summary line reported **341 hits / 0 misses**
  for a run with **0** usable hits. Anyone reading the log (including the HANDOFF next-step that
  said to look for exactly this line) would conclude the cache worked. A counter that fails in the
  optimistic direction is worse than no counter.
- **Cost:** small, no re-ingest implied (the cache only affects runs).
- **Test gap:** the suite reuses freshly-written entries, so no test covers "an entry written by an
  older identity scheme". That is the same object-reuse blind spot as §I19 point 1.
- **✅ FIXED 2026-10-18** — two of the three fixes below, and deliberately **not** the first:
  1. **NOT APPLIED — the schema bump is wrong here, and was rejected on evidence.** Attempt 5
     rewrote **all 341** entries with the corrected 32-char digest, so the directory now holds a
     single vintage (`<U32`, mtimes 12:19–12:55) and the mixed-directory problem no longer exists.
     Bumping `_CACHE_SCHEMA_VERSION` to 2 would have discarded 341 entries **verified to work** and
     re-cost the 36 minutes this item exists to save. The constant stays at `1`; a bump is owed only
     when a future identity change lands while valid entries exist.
  2. **APPLIED — the digest scheme is named and checked.** `_DIGEST_SCHEME = "sha1:32"` is written
     into every entry and checked in `get`; a mismatch is a **miss** (counted as `stale`), never a
     content mismatch. Entries predating the field — all 341 of attempt 5's — have the scheme read
     off the stored array's width, which is exact because the width is the only thing the scheme
     names. That fallback is what keeps the live cache valid rather than "fixing" it by discarding
     it.
  3. **APPLIED — a hit is counted after validation.** `get` no longer bumps `hits`; the embedder
     calls `record_hit()` only once `rebuild()` has returned chunks, and a genuine content mismatch
     under the current scheme is counted as `rejected`. `summary()` now reads
     `341 hits / 0 misses / 0 stale / 0 rejected / 0 written`.
- **Evidence.** New read-only probe `logs/p1/step8-run/probe_cache_hit.py` mirrors
  `process_pdf` lines 95–104 and stops before `save_document`, so it touches neither Qdrant nor
  SQLite (verified: cache mtimes, point count and SQLite rows all unchanged). Run against the live
  cache with the dense lane pointed at a dead port, so a full hit needs no cluster at all:
  **341 hits / 0 misses / 0 stale / 0 rejected / 0 embeddings issued / 0.8 s**, `VERDICT: HIT` —
  once before the fix and once after. Tests: **22** in `test_embed_cache.py` (was 19); all three new
  ones fail against the unfixed code, one of them on the behaviour rather than a missing attribute
  (`assert 1 == 0` on `hits` for a rejected entry). Suite **406 pass / 4 pre-existing fail /
  6 skip**; ruff clean on the touched files.
- **The hit-proof is demonstrated** — HANDOFF's step-3 item is discharged without a second ingest.
  What is *not* demonstrated end to end is a future scheme change behaving as designed on a real
  run; that is pinned by test, not by a run.

### I17. NEW 2026-10-17 (found auditing the ingest for concurrency) — two serial-batch lanes remain in the ingest: ColBERT at batch 4, SPLADE at batch 32

- **What:** with the late-chunk loop parallelised (§I16), the two remaining hot spots in the
  ingest are both **serial batches of HTTP requests**:
  - `ClusterColBERTEmbedder._post(..., batch_size=4)` — **4 texts per request**, so ~3,796
    children need **~949 sequential requests**. Measured 9.8 s / 66 chunks on the fixture
    (0.148 s/chunk) → **≈ 9.4 min** for the book.
  - `ClusterSpladeEmbedder._post(..., batch_size=32)` — ~**119 sequential requests**. Measured
    6.4 s / 66 chunks (0.097 s/chunk) → **≈ 6.1 min**.
  Together ~15 min of the run's non-late-chunk cost, and unlike the late-chunk lane they were
  never concurrency-audited.
- **Why it matters:** the ingest is now dominated by whichever lane is serial. At 8 workers the
  late-chunk phase should fall from ~62 min to roughly **10–25 min** — the range is wide because
  the endpoint's own speed moves a lot: serial throughput measured **214 tok/s median during the
  failed run** but only **84 tok/s** the next morning on the same payload. Do not quote a single
  number for this until the re-run produces one.
- **Estimate caveat:** the per-chunk costs were measured on the 19-page fixture, where per-request
  overhead is amortised over few chunks; the book-scale figures are extrapolations, not
  measurements. Confirm with a probe before acting.
- **Fix (not applied — deliberately):** raise ColBERT's batch size (4 looks like a GPU-memory
  default chosen for a local model, but this is the cluster serving it) and/or run both lanes'
  batches concurrently with the same `ThreadPoolExecutor` pattern now used for late chunking.
  Either way it needs its own endpoint-concurrency probe first: the whole reason the late-chunk
  worker count is 8 and not 16 is that the knee was measured rather than assumed, and this
  endpoint has already shown it degrades under sustained load. Bundling an unmeasured concurrency
  change into the retry fix would repeat the mistake this project has made twice (§B4a, §I11).
- **Cost:** small to medium; no re-ingest needed to change it, but it only pays off on the next
  index run.
- **Not blocking Step 8's re-run.**

### I20. NEW 2026-10-18 (found by Step 8 attempt 4's failure) — `save_document` is NOT the atomic write point it is documented as

- **What:** the design rests on "`save_document` is the single write point, so an abort leaves both
  stores untouched". It is a single *entry* point, but it is **not atomic**: it (1) commits SQLite,
  (2) encodes SPLADE, (3) encodes ColBERT, (4) upserts Qdrant in batches. A failure at any step
  after (1) leaves the two stores disagreeing. Measured on attempt 4: the run reached step (4),
  Qdrant rejected the payload as too large, and the result was **3,796 chunk rows in SQLite for a
  document with zero points in Qdrant**, plus **128 points already written** by the batches that had
  succeeded — a half-written collection that every downstream reader would treat as real.
- **Why it matters:** it is the same hazard the resume cache was deliberately designed *around*
  (§I19: "incremental writes would make a partially-written collection look complete"). The
  protection was placed in the cache and not applied to the writer it was protecting. Two of the
  four steps can fail for mundane reasons (a size limit, a network blip), and the failure is
  invisible: the SQLite document row looks complete, and `chunk_count` says 3,796.
- **Cleanup required before a re-run, and it is not automatic:** the orphaned `documents` row and
  its `chunks` must be deleted by hand, and the partially-written collection deleted, or the next
  run adds a *third* document row and leaves 128 orphan points with a foreign `document_id`.
- **Fix (not applied — needs a decision, not a patch):** either (a) upsert Qdrant **before**
  committing SQLite, so the store that can be verified cheaply is the last to change; or (b) write
  a `status` column on the document row (`pending` → `complete`) and have every reader filter on it,
  so a half-written document is invisible rather than merely inconsistent; or (c) make the batch
  loop transactional with a rollback of the SQLite rows on failure. **(b) is the most robust and the
  smallest reader-side change**, and it also fixes the duplicate-filename issue registered in §E7 —
  a document is only "there" when its status says so.
- **Cost:** medium. No re-ingest needed; it changes what a reader sees, so it needs its own tests.
- **Found because attempt 4 got further than any previous run** — this bug was hidden behind the
  earlier failures for three attempts.

### I18. NEW 2026-10-18 (found by Step 8 attempt 2) — the concurrency ramp probe used ONE payload size, so it never tested the real size distribution

- **What:** `probe_concurrency_knee.py` fired N concurrent requests of a **fixed 1,749-token**
  payload and found throughput still rising at 16 workers with no errors, which is why 8 was chosen
  as a "conservative" default. But the real corpus is not uniform: attempt 1 measured parent sizes
  with **median 1,190 tokens, mean 1,387, max 4,762**. At 8 workers the in-flight footprint is
  therefore up to **8 concurrent requests of ~2.7× the probed size**, and a per-token response is
  ~160× the pooled payload (§E3) — a measured 4,647-token parent returns ~19 MB. The probe never
  exercised that regime, so **"no collapse up to 16" does not transfer to 8 workers on this corpus**.
- **Why it matters:** this is the same class of error the repo has recorded twice before — §B4a
  (a ColPali endpoint probed with the wrong request shape) and §I11 (a copied endpoint that read as
  authoritative). A concurrency probe validates a *regime*, and a fixed payload size is a regime
  assumption that was never stated. Attempt 2 then ran 8 workers against the real distribution and
  the endpoint stopped accepting connections after 7 minutes (§E7).
- **Fix (not applied):** a ramp probe should sweep **both** axes — workers × payload size — or at
  minimum use the real corpus's p95 size rather than a mid-range constant. Cheap to redo: the probe
  is ~5 minutes. Until then, treat 8 as an **unvalidated** setting and prefer 2–4.
- **✅ RE-PROBED 2026-10-18 (`probe_knee_by_size.py`) — the result is "no harm shown", NOT
  "8 is validated", and the default is now 4 on risk grounds.** 12 cells, 1/2/4/8 workers ×
  1381/3497/5521 tokens (the last above the real corpus max of 4,762), **zero errors anywhere**,
  and the service health-checked between every cell. So the "8 workers OOMs the endpoint" reading
  of attempt 2 is **not supported by a short burst** — at any tested size, including one larger
  than the real maximum.
  **But the probe does not rank the worker counts.** One wave per cell is a tiny sample and the
  endpoint's own variance swamps the signal — at 1381 tokens, 1 worker (307 tok/s) *beat* 2 workers
  (167) and was beaten by 4 (552); at 3497 tokens, 1 worker (410) beat 2 (122), 4 (252) and was
  close to 8 (429). Measured tok/s:

  | payload | 1 w | 2 w | 4 w | 8 w |
  |---|---|---|---|---|
  | 1381 | 307 | 167 | **552** | 550 |
  | 3497 | 410 | 122 | 252 | **429** |
  | 5521 | 99 | 167 | 393 | **455** |

  At 8 workers the aggregate is flat at ~430–550 tok/s across all three sizes, which is the one
  stable thing in the table. **Default set to 4**: it is statistically indistinguishable from 8 at
  the median size where most parents sit (552 vs 550), it halves the concurrent in-flight footprint
  (~19 MB per large per-token response) on a cluster shared with other students, and the only
  observed failure was 8 workers under *sustained* load — which a burst probe cannot test. Raise it
  only with evidence about sustained load.
- **Method note worth keeping:** a concurrency probe answers "does a burst break it", which is not
  the question a 60-minute run asks. Both probes here were burst-shaped; neither could have caught
  a degradation that needs minutes of load to appear. If this matters again, the probe has to hold
  the load for minutes and watch for the drift the run showed (10.8 s → 16.5 s per parent).
- **Related and also not applied:** a **total-request deadline** (the §I16 open item). Attempt 2's
  21.5-minute silent window happened inside requests that never tripped a per-read timeout, so
  neither the retry nor any timeout bounded them. Combined with no checkpoint, one hung request can
  silently consume an entire run. The deadline is the higher-value fix of the two.
- **Cost:** small (probe re-run), small-to-medium (deadline), medium (checkpointing).

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

### I21. NEW 2026-10-18 (found by the Step 10 Phase A2 probe) — the Phase 3 graph build does not apply the E5 content filter

- **What:** `generate_phase3_artifacts` passes **every** chunk of the document to
  `GraphBuilder.build_graph` (`store.py` ~1668: `store.get_chunks_with_embeddings(document_id)`, no
  filter). §E5's `content_filter` — described in `generate_phase2_artifacts` as *"shared with ingest +
  retrieval"* — **is** applied in Phase 2 (cards) and in retrieval, but **not** in Phase 3 (graph).
- **Measured 2026-10-18 (A2 probe, doc `7ba61432`, `chunk_index` 100, page 27):** the probed chunk is
  a **table-of-contents fragment** — `"Linear Systems and Review, 1 = . 25-1 Linear differential
  equations . . ., 1 = . . ."` — and concept extraction returned **4 concepts** from it
  (`Linear differential equations` / `Superposition principle` / `Oscillations in linear systems` /
  `Analogous systems`), i.e. the TOC line was treated as physics content.
- **Why it matters:** concepts harvested from front/back matter enter the graph and are matched by
  `graph_search` at query time, so a query can be answered with a table-of-contents node. It is also
  an inconsistency: Phase 2 and retrieval both gate on E5, Phase 3 does not. The old graph's
  **7,815 concepts / 5,051 chunks** were built the same way, so the existing graph carries this too.
- **Effect size: not measured.** The old index ran this way throughout P0-9, so the recorded numbers
  already include it. Do not assume it is large; do not assume it is zero.
- **Fix (not done — no code changes in Step 10):** apply `content_filter.is_content` in the Phase 3
  graph path, mirroring `generate_phase2_artifacts`. Would change the concept set → requires a graph
  rebuild, not a re-ingest.
- **✅ D1 SETTLED 2026-10-21 (owner) — the filter fix comes first; §G3 does NOT run on the current
  graph.** The order is: extend the filter (§I39, **DONE** — signals 4 and 5, TOC 72/77 and index
  186/187, zero body loss) → apply `is_content` in the Phase 3 path → harden the graph build (§I23:
  checkpoint, bounded retry, a real failure count, a deliberate extraction model) → **rebuild the
  graph** → *then* §G3, then §G2. **The gate that releases §G3 is the rebuild landing.**
  - **Why not G3 now:** §G3's merge target list *is* the concept set, and this fix **changes the
    concept set**, so a merge computed today is discarded by the rebuild — paid for twice. §I30's
    lever (1,186 merge groups over 34.4 % of the vocabulary) was also measured **on the current
    graph**, so it re-measures after the rebuild. §I21's own effect size is **unmeasured**: *"do not
    assume it is large; do not assume it is zero."*
  - **Why §G2 waits too:** community detection + LLM community summaries are where the noise
    actually costs money — TOC concepts fragment communities and the summaries are LLM calls on a
    shared cluster. The previous session's note stands: *decide D1 before spending summary budget.*
  - **Not gated, and therefore the one graph item that can start now:** **§G1 (PPR)** is a traversal
    change over the adjacency matrix and does not depend on which concepts are in the graph.
  - **Cost of the rebuild, for the record:** the last one measured **16 h 25 m** for 3,796 chunks
    (§I23), against a 2 h estimate, with 44 LLM failures reported as "0 failed". That is why the
    §I23 hardening is in the chain ahead of it rather than after.
- **Evidence:** `logs/p1/step10/probe_graph_before.py` (the probe), `logs/p1/step10/graph_before.json`.
- **No re-ingest** (graph rebuild only). ⚠️ **But the same filter fix has two prices** — the graph
  lane needs only the rebuild, while the **card + retrieval** lanes need a **full re-ingest** because
  `is_content` is written into the payload at ingest. Fixing both in one pass is why this rides with
  the E1/E2/E3 re-ingest rather than being a standalone job.

### I22. NEW 2026-10-18 (found reading `build_graph` for the Step 10 graph plan) — `graph_stats["concept_nodes"]` reports MENTIONS edges, not distinct concepts

- **What:** in `GraphBuilder.build_graph` the counter is incremented **inside the per-concept loop**,
  which runs once per chunk (`graph_builder.py:362`, inside `for concept in concepts:` under
  `for chunk in chunks:`). So `concept_node_count` counts **`(chunk, concept)` pairs** — i.e. MENTIONS
  edges — while it is returned as `"concept_nodes"` (line 394) and surfaced as "Concept Nodes" /
  "concept nodes" by `scripts/run_phase3.py:93` and `store.py:1692`.
- **Measured contrast:** Memgraph holds **7,815 distinct** `Concept` nodes for the old document
  (`6d55c52b`), and 5,051 chunks each mentioning several concepts — so the reported figure is a
  substantially larger number than the distinct-concept count it is labelled as. The two are not the
  same quantity and the label says it is.
- **✅ CONFIRMED EMPIRICALLY 2026-10-19** (the Phase A build finished). For doc `7ba61432` the run
  reported **`15619` concept nodes** in both the log line (`build_graph:387`) and the `run_phase3.py`
  table, while Memgraph holds **7,834 distinct** `Concept` nodes for that document. **The reported
  figure is almost exactly 2× the truth** (15,619 / 7,834 = 1.99) — consistent with ~2 MENTIONS per
  concept, which is the (chunk, concept) pair count, as the code reads. Treat every previously
  quoted "concept nodes" number as a MENTIONS count.
- **Why it matters:** every run table and log line read so far has been read as "distinct concepts".
  It also makes the figure useless as a **verifier** — a graph with half the concepts but the same
  mention count would look unchanged. **This is why the Step 10 A3 verifier counts
  `count(DISTINCT k)` in Memgraph rather than reading `graph_stats`.**
- **Fix (not done — no code changes in Step 10):** count distinct names in a set and report that, or
  rename the field to `mentions` and add a real `concept_nodes`. Report-side + counter only.
- **✅ CONFIRMED FROM THE GRAPH SIDE 2026-10-20.** An independent read-only Cypher count on doc
  `7ba61432` returns **`MENTIONS` = 15,619** — the exact figure the run log reported as
  *"concept nodes"*. That closes the loop: the mislabelled counter is the MENTIONS edge count, and it
  is now verified from both sides (the log and the graph). Edge inventory for the document:
  `PREREQUISITE_OF` 11,892 + `MENTIONS` 15,619 + `RELATES_TO` 37,300 + `PART_OF` 4,729 +
  `ON_PAGE` 3,796 = **73,336**, matching HANDOFF's recorded total.
- **No re-ingest** (no graph rebuild needed to fix the label).
- **Evidence:** `src/pdf_ingestion/graph_builder.py:349–396`; `logs/p1/step10/verify_graph.py`;
  `logs/p1/step10/probe_g3_baseline.json` (the graph-side count).

### I23. NEW 2026-10-18 (found watching the Step 10 Phase A graph build) — the Phase 3 graph build has no checkpoint and no retry, and burns a reasoning model on a JSON extraction task

> **⚠️ UPDATE 2026-10-21 (session 6) — the collapse is NOT a one-off; it happened again on the REBUILD,
> and a liveness probe does not detect it.**
>
> The rebuild (Qwen extractor, 3,533 chunks) ran at **~94 chunks/min** for its first ~35 min, then
> **collapsed ~58× mid-run with no error**:
>
> | window | chunks | elapsed | rate |
> |---|---|---|---|
> | 22:17:34 → 22:25:25 | 2400 → 3025 | 471 s | **1.33/s ≈ 80 chunks/min** |
> | 22:26:41 → 22:44:57 | 3075 → 3100 | 1096 s | **0.023/s ≈ 1.4 chunks/min** |
>
> - **The trap: a single-request liveness probe reads ALL-CLEAR during the collapse.** At the bottom of
>   the collapse a real completion to `Qwen/Qwen3-VL-8B-Instruct` returned **HTTP 200 in 0.16 s**
>   (`max_tokens: 8`), and `/v1/models` answered 200 in 2.2 s — while the build's four concurrent
>   ~2,000-token extraction calls were starving. (Both are **session observations**, not in the run
>   log; they are one-off readings of a transient condition and cannot be re-created. The *rates* below
>   are derived from the log and are re-derivable.) This is §11's "listed ≠ serving" trap in a new form:
>   **a trivial prompt does not measure the queue a batch job sits in.** Do not conclude "the endpoint
>   is fine, so the build is fine" from either probe.
> - **What DID show it:** the checkpoint's line count (static across a 45 s sample) and the widening gap
>   between progress lines. **Read the rate, not a status code.**
> - **4 `ReadTimeout`s** appeared at the bottom (first at 22:44:50) — §I24's bounded retry working as
>   designed: 300 s deadline, 3 attempts, then the chunk is marked failed and **counted**, not swallowed.
> - **The checkpoint is what makes this survivable** (§I23's own fix): 3,100 of 3,533 extractions were
>   already durable, so the collapse cost wall-clock, not work. A chunk whose extraction FAILED is not
>   checkpointed as done, so it is re-attempted on resume. **Second time the register has had to say
>   it: do not budget Phase 3 runs in hours on this shared cluster, and never read a collapse as a
>   crash.**
> - ⚠️ **Timing note, stated rather than claimed:** the collapse began ~22:26, ~6 min after this
>   session's last verifier call finished (~22:20) and ~25 min after the docs review (96 API calls,
>   21:55-22:01). Both hit the same endpoint. The timing does **not** point at this session — but a
>   cluster-pinned verifier is **not** free during a measured cluster run, and that should be assumed
>   next time rather than discovered.
>
> **Status at 2026-10-21 22:45: 3,100 / 3,533 extracted, still running (tmux `graphrebuild`), rate
> unknown and volatile.**
>
> - **✅ AND IT RECOVERED — the collapse was TRANSIENT, which is the part that matters.** By 22:45:35
>   the rate was back to **~79 chunks/min** (3150 → 3175 in 19 s), and extraction **finished at
>   22:50:25 with `0 FAILED`** — all four timed-out calls succeeded on retry. The whole build was
>   **DONE at 22:54:37**: extraction ~62 min, concept-name embedding ~1.5 min (7,427 names, local
>   CPU), Qdrant upsert ~0.5 min, Memgraph writes ~2.7 min. So an 18-minute 58× stall cost wall-clock
>   and nothing else — but **the probe read all-clear throughout it**, so nothing would have told you
>   whether to wait or to kill it. The checkpoint and the rate are the only instruments that did.

- **What:** three compounding defects, all measured on the live run of
  `run_phase3.py --graph-only` for doc `7ba61432` (started 17:21:55, 3,796 chunks,
  `concept_gen_workers=4`):
  1. **No checkpoint.** `build_graph` extracts concepts for **all** chunks in memory before writing
     anything, so an abort at any point discards every completed extraction. Same class as §I19,
     different phase. Observed: 2,000 chunks of work held in RAM with no way to persist it.
  2. **No retry, and failures are silent.** `src/core/llm.py::_call_openai` has **no retry** and a
     120 s timeout; on timeout it returns `""`. `_extract_concepts` catches every exception and returns
     an empty concept list, so those chunks get **zero concepts while `build_graph`'s `failed` counter
     stays 0**. Measured: **12 timeouts in 4 h** (bursts at 19:23, 20:40, 21:10), i.e. 12 chunks that
     will contribute no concepts and will not be reported.
  3. **Throughput collapsed ~8× mid-run.** 23.3 chunks/min for the first 1,500 (≈10 s/call at 4
     workers), then **3.0 chunks/min** for the next 500 (≈80 s/call). Projected remaining time:
     **~10 h** for the last 1,796 chunks.
- **Cause of the collapse — measured, two distinct factors:**
  - **Model choice (ours).** A single realistic probe (2,000-char chunk, `response_format=json_object`):
    `openai/gpt-oss-20b` → **12.9 s**, `completion_tokens 1244`, of which **4,495 chars were hidden
    reasoning**; `Qwen/Qwen3-VL-8B-Instruct` → **3.2 s**, `completion_tokens 166`, **0 reasoning chars**.
    Both returned valid JSON. **A reasoning model is being spent on a structured-extraction task.**
    (Caveat: the two did not return the same content — 10 concepts / 10 prereqs vs 5 / 3 — so a swap
    is a quality decision, not a free speedup.)
  - **Contention (not ours).** A single call is 12.9 s *now* while the 4 concurrent in-flight calls
    average ~80 s — so concurrency is costing ~6× on a **shared** cluster (ARCHITECTURE §11: `.65` is
    shared with ~29 other bootcamp collections). **Do not raise `concept_gen_workers`**: §I18 already
    measured 8 workers *slower* than 4, and more concurrency against a serialising server is the wrong
    direction.
- **Why it matters:** any future Phase 3 build on a book-sized corpus is a **multi-hour, uncheckpointed,
  silently-lossy** job. It is not the graph code's cost that is surprising — it is that a 1-hour
  estimate became 10 h with no failure signal.
- **Fix (not done):** (a) checkpoint extractions keyed on chunk content, mirroring the Step 8 embed
  cache (§I19); (b) bounded retry + a real failure count in `llm.py` / `_extract_concepts`; (c) settle
  the extraction model deliberately (reasoning vs non-reasoning) with an output-quality comparison;
  (d) move the **concept-name embedding** phase (7,815 unique names, local CPU, sequential, legacy
  Nomic 768d) off the CPU — either to the cluster's GPU embed endpoint (§I12) or via an **MPS** path
  in `embedder.py`, which today is `device = "cuda" if use_gpu else "cpu"` with **no availability
  check** (unlike `parser.py`), so `USE_GPU=true` on this Mac would try `cuda` and fail. Measured:
  `torch 2.8.0`, arm64, **cuda False / mps True**.
- **STATUS 2026-10-21 — (a), (b) and (d) are DONE; (c) is OPEN and is an owner decision.**
  - **(a) + (b) DONE 2026-10-20** (`50af715`): NEW `src/pdf_ingestion/graph_checkpoint.py` — a
    side-car JSONL keyed on document + model + **prompt digest**, flush+fsync per record; a FAILED
    extraction is never resumed as done. `build_graph` now returns **`failed_chunks`** (the honest
    count, where the old local reported 44 failures as "0 failed") plus `chunks_resumed` and
    `checkpoint_path`. 25 tests, both guards proven to discriminate. Verifier `deleg_5fd5575a` 9/9.
  - **The `resume` flag was unreachable until 2026-10-21** (`aaef7fe`): `generate_phase3_artifacts`
    never forwarded it, so the checkpoint could only ever be ON from the CLI. Verifier
    `deleg_92c32542` 8/8.
  - **(d) DONE 2026-10-21** (`1fa94a3`): NEW `resolve_device(use_gpu)` in `embedder.py` — CPU when
    `use_gpu` is false (early return, before `import torch`), else CUDA → MPS → CPU, and it cannot
    raise; `_load()` passes the resolved device for any non-cpu value. 8 offline tests in
    `tests/test_embedder_device.py`; reverting the resolver to the old semantics fails 4 of them.
    Verifier `deleg_f2fda5ec` 8/8. **Measured on this Mac: `resolve_device(True) == "mps"`.**
    ⚠️ **Not covered, and NOT fixed — the sibling site:** `colpali_embedder.py:87` is
    `"cuda" if (use_gpu and torch.cuda.is_available()) else "cpu"`. It checks availability, so it
    cannot crash, but it has **no MPS path** either — and ColPali is where the accelerator matters
    most (a ~5 GB model over per-page images). Deliberately not changed blind: MPS support in that
    stack (attention/bfloat16 paths) is a real question, not a one-liner.
  - **(c) MEASURED 2026-10-21 — the comparison RAN and the single-chunk impression did NOT
    reproduce.** `logs/p1/step10/i23c_extraction_model_compare.{py,json}`, commit `c596940`: 24
    content chunks (a reproducible random draw, uuid-ordered), BOTH arms on the production prompt
    (imported, not retyped), the same payload knobs as `_call_openai`, the same acceptance rules as
    `_extract_concepts` — **three runs**, so the instrument's own noise is measured:

    | metric (3 runs) | gpt-oss-20b | Qwen3-VL-8B | verdict |
    |---|---|---|---|
    | concepts/chunk mean | 4.29 / 4.25 / 4.46 | 4.54 / 4.46 / 4.62 | **OVERLAPPING — no claim** |
    | in the prompt's 3-7 band | 23 / 23 / 22 of 24 | 23 / 23 / 23 of 24 | no claim |
    | prereq edges/chunk | 2.00 / 2.21 / 2.08 | 1.04 / 0.96 / 1.04 | separated, ~2× |
    | off-enum concept types | 0 / 0 / 0 | 11 / 8 / 9 | separated |
    | symbol-like names | 5 / 2 / 2 | 1 / 1 / 1 | separated, but 2-5 vs 1 of ~100 |
    | p50 latency (s) | 10.11 / 10.31 / 10.24 | 2.97 / 2.83 / 3.16 | separated, **3.4×** |
    | completion tokens / 24 chunks | ~1,118 (+98k reasoning chars) | 162 | ~7× |
    | graph-vocabulary overlap % | 73.2 / 81.9 / 85.3 | 64.4 / 66.3 / 63.6 | separated, but circular |

    **The 10-vs-5 concept gap that motivated this item is gone at n=24** — both arms land at ~4.3-4.6
    and both obey the prompt's own "3-7 concepts maximum" rule. That number was one chunk.
    ⚠️ **The overlap metric is circular by construction** (the graph's vocabulary was built by
    gpt-oss-20b, so it partly measures that model agreeing with itself) and it swings 12 points
    across runs — the largest spread of any metric. ⚠️ **The probe is not bit-reproducible**
    (temperature 0.3): two consecutive runs moved gpt-oss-20b's overlap 82.11 → 86.46 % and its p50
    10.92 → 9.58 s. Every difference above is read against that spread. ⚠️ **No LLM judge** — the
    cluster serves two text models and both are arms here, so a judge would score its own output.
  - **What the difference is worth, which is the part that decides it:** the two things gpt-oss-20b
    does better are **not read by any code path.** `graph_search` is a **MENTIONS-only, single-hop**
    lookup (`graph_builder.py:525-536` — the Cypher matches `(ch:Chunk)-[:MENTIONS]->(k)`);
    `PREREQUISITE_OF` is only ever **written** (11,892 edges in the live graph), and nothing branches
    on a concept's `type` — the live gpt-oss-built graph already carries 8 off-enum nodes
    (`theory` 7, `principle` 1). So the ~2× prerequisite edges and the cleaner type field are
    **latent structure, not consumed structure**, while the 3.4× latency is paid on every rebuild.
  - **⚠️ The swap is one-way.** The checkpoint key includes the model (`_extraction_model()` +
    `prompt_digest`), so choosing Qwen now and changing your mind later re-extracts everything.
  - **Verification:** design fidelity `deleg_f35f4a2a` task 1 — **6/6 confirmed**, no confound
    besides the model id. Artifact arithmetic checked mechanically for all six arm-runs (consistent).
    ⚠️ **Every reviewer of this comparison was `openai/gpt-oss-20b` — one of the two arms** (the lab
    serves only two text models, so the alternative was the other arm). That is acceptable for what
    was actually checked, which is *design fidelity* (does the probe mirror production?) and
    *arithmetic* (do the fields agree with each other?) — neither is a judgement about output
    quality. It would NOT be acceptable for a quality verdict, and none was taken: the quality
    reading is left to the owner, and the artifact ships a side-by-side sample for it. Recorded
    because a reviewer drawn from the compared set is a limitation, not a formality.
    ⚠️ The same round's arithmetic reviewer refuted two of those; **void on wrong-file
    attribution** — every number it cited is a real value from `rep1`, not the registered artifact,
    and its `per_chunk` length of 25 exists in no artifact. A prior attempt (`deleg_2cb7b098`) is
    also void: the endpoint rejected the replayed history mid-run and its `search_files` returned
    whole-file heads.
  - **OWNER DECISION, pending:** keep `openai/gpt-oss-20b` for the rebuild or switch to
    `Qwen/Qwen3-VL-8B-Instruct`. The cost side is **derived, not measured**: scaling §I23's measured
    **16 h 25 m** build by the measured p50 ratio (10.11-10.31 s / 2.83-3.16 s = **3.2-3.6×**) gives
    **≈4.5-5.1 h**, and that is an **upper bound on the saving** — it scales the whole build although
    only the extraction half is model-bound (the concept-name embedding and the Memgraph writes are
    not, and the embedding phase is local CPU). The two arms' *quality* difference is the measured
    part; the time saving is an extrapolation from two measured quantities.
- **No re-ingest** (Phase 3 only).
- **Evidence:** `logs/p1/step10/graph_build.log`; scratch probes `lat.txt`, `usage.txt`, `mps.txt`.
- **✅ FINAL MEASUREMENT 2026-10-19 — the run completed, and it took 16 h 25 m, not 2 h.**
  `17:21:55 → 09:47:04` for 3,796 chunks. Progress: 2,500 at 21:35 → **3,000 at 05:55** (8 h 20 m for
  one 500-block!) → 3,500 at 09:08 → extraction done 09:27. So the contention was not a 2.75-hour
  window that passed: **throughput collapsed again overnight and stayed collapsed.** The earlier
  "recovered, ETA ~23:30" reading was wrong — it was a brief lull, and my estimate was wrong for the
  third time on this one job. **Total LLM failures: 44** (up from 12), reported as **"0 failed"** —
  i.e. **~44 chunks (1.2% of 3,796) contributed no concepts and were never reported.** The graph still
  passed its density check (2.064 concepts/chunk vs the old document's 1.547), so the losses are a
  tail, not a collapse — but they are invisible without counting in Memgraph.
  Lesson for any future Phase 3 run: **budget in days, not hours, on a shared cluster, and do not
  trust a recovered throughput reading.**

### I24. FIXED 2026-10-20 — `src/core/llm.py` had NO total-request deadline and NO retry: a trickling response hung a call for 41 minutes, and every Phase 2/3 LLM phase used it

- **What (before):** `_call_openai` / `_call_ollama` issued **one un-retried POST** with
  `timeout=OLLAMA_TIMEOUT` (120 s) and returned `""` on failure (logged ERROR).
- **Why it mattered — this was §I16's defect in a second module.** §I16 established the mechanism
  exactly: *"httpx's read timeout is per read operation, not per request. A response body that keeps
  trickling resets the timer on every chunk."* It fixed that in `cluster_embedder._post_json` with a
  wall-clock total-request deadline. **The shared LLM caller never got that fix**, and `_call_openai`
  is what cards, RAPTOR summaries, concept extraction, HyDE and the judge all use.
- **Measured 2026-10-19 (Phase B):** card generation began 21:54:16; chunks 69-70's eight card types
  all timed out at **22:12:42-44**, then **no log line at all until 22:53:48** — a **41-minute silent
  window** inside requests the 120 s read timeout could not bound, and with no retry nothing could
  catch it. §I16 reports the *same* ~42-minute figure for the embed path: same failure shape.
- **Fix (APPLIED 2026-10-20, `src/core/llm.py`):** the body is now read in chunks against a
  wall-clock deadline (`_LLM_DEADLINE = 300 s`), raised as `httpx.ReadTimeout` so the retry treats it
  as transient; bounded retry (3 attempts, jittered doubling backoff, `_LLM_RETRY_BACKOFF = 2 s`) on
  transport errors, 429 and 5xx — never on other 4xx. The failure contract is unchanged (`""` + ERROR
  log), and a failure before the first attempt (unbuildable client) also returns `""` rather than
  raising. **Failures are now counted** — `llm_call_stats()` returns
  `{calls, failures, retries, deadline_hits}` and is reset per measured run.
- **Scope limit, deliberately recorded:** the fix covers the **raw** LLM path only. With
  `use_instructor: true` in `config.yaml`, 4 of 8 card types (summary, question, objective, factoid)
  go through `instructor`/`openai` SDK calls that never touch `llm.py`. `config.yaml` currently sets
  **`use_instructor: false`** (and the Phase B log confirms *"instructor disabled in config.yaml —
  using raw LLM"*), so all 8 types are covered today — but flipping that flag silently reopens §I24
  for half the card types.
- **Evidence:** `tests/test_llm_deadline_retry.py` (14 tests: deadline fires on a trickling body,
  retry on 5xx/transport, no retry on 4xx, bounded attempts, counters, URL/payload contract);
  `tests/test_fallback_chains.py` updated to the new transport boundary — its old
  `monkeypatch.setattr(llm.httpx, "post", …)` was **silently inert** after this change and the test
  made a *real* network call.
- **No re-ingest.**

### I25. FIXED 2026-10-20 — the card generator's per-card-type handler made a TOTAL card loss invisible: zero `Failed:` rows, exit 0

- **What (before):** `generate_cards_for_chunk` caught each card type's exception, logged a WARNING
  and returned `[]` **for that type**. The outer `generate_cards_for_chunks` then received a
  **successful** future holding a short list, so its `failed` counter never incremented for a
  timed-out card type, and the closing line read `Generated N cards for 3,791 chunks (0 failed)`.
  `run_phase2.py` printed a `Failed:` row only when the **whole document** raised.
- **Why it mattered:** the Phase B plan's fact (ii) — "a per-chunk exception is swallowed" —
  **understated it**: the swallow is one level **deeper** (per card type) and produces **no `Failed:`
  row at all**. B4's verifier check [1] ("no `Failed:` row in `phaseb_run.log`") therefore passes
  **vacuously** on a run in which every card call failed. Measured on the aborted run: **16 `LLM CALL
  FAILED` ERRORs, 16 card-type failures, `Failed:` rows = 0.**
- **Fix (APPLIED 2026-10-20):** `generate_cards_for_chunk` now delegates to
  `_generate_chunk_with_report`, which returns `(cards, failed_types)`. The per-type failures are
  counted per run (`Counter`), checkpointed per chunk (§I27), logged in the closing line
  (`… {} chunks with a failed card type, {} failed card-type calls, {} LLM failures of {} calls`),
  and surfaced in `generate_phase2_artifacts`'s result as `failed_card_types` / `failed_chunks` /
  `card_gen_stats`. `run_phase2.py` prints a **"Card types failed"** column, red when non-zero.
- **What still catches it:** B4's checks **[3]** (distinct card-type set == the 8 in `CardType`) and
  **[4]** (cards/content-chunk ratio). Keep both. **The log check is no longer the guard** — the
  guard is `failed_card_types == {}`, read from the generator's own closing line.
- **B4's check [1] was REPLACED 2026-10-20** (`logs/p1/step10/verify_phaseb_cards.py`). It now
  requires the generator's closing line to be **present** (absence = the phase never reached the
  end) and to read **0 failed chunks / 0 failed card-type calls / 0 LLM failures**, and it fails on
  the "Card types that failed at least once" warning. The old `Failed:`-row check is kept as a
  secondary signal only. **Self-tested on four logs:** the real aborted log → **FAIL** (it reported
  0 `Failed:` rows, which is exactly the vacuous pass this fixes); a synthetic clean log → counters
  clean; a synthetic failing log → FAIL on the counts *and* the warning; a log with no closing line
  → FAIL.
- **Evidence:** `tests/test_card_checkpoint.py::test_a_failed_card_type_is_retried_on_resume`
  (asserts the counts), `tests/test_fallback_chains.py::test_a_dead_backend_is_counted`; the
  verifier self-test above.
- **No re-ingest.**

### I26. ⛔ SUPERSEDED 2026-10-20 — the "knee between 8 and 16 in-flight calls" claim below is WRONG (it rested on a one-chunk burst probe and on timeouts taken with the defective §I24 caller). Read "MEASURED 2026-10-20" at the end of this entry, which replaces it: throughput scales to 32 in-flight with zero failures.

- **Measured 2026-10-19, `openai/gpt-oss-20b` @ `10.0.10.70:8000`:**

  | in-flight calls | config | per chunk | aggregate | errors |
  |---|---|---|---|---|
  | **8** (one chunk; the B1 probe, 3 runs) | `card_gen_workers=1` equivalent | **7.6 / 10.9 / 10.1 s** | ≈ **0.73-1.05 card-calls/s** | **0** |
  | **16** (the real run) | `card_gen_workers=2` | **≈ 97 s** (74 chunks / 60 min) | ≈ **0.165 card-calls/s** | **16 timeouts** |

- **So doubling concurrency cut aggregate throughput ≈4.4×.** The endpoint has no headroom at 16 —
  it has **congestion collapse**, the same shape §I23 measured for the graph build (4 concurrent →
  ~80 s/call against 12.9 s for a single call).
- **Why the plan's ceiling was the wrong number:** it compared against **4.21 calls/s**, but that knee
  was measured for the **VLM judge** (`Qwen/Qwen3-VL-8B-Instruct`, one page image, ~0.8 s/call) — a
  different model, prompt size and response length. **A knee belongs to one model + one prompt shape
  on one server; it does not transfer.** Card prompts are long and `gpt-oss-20b` emits a hidden
  reasoning trace (§I23: 4,495 reasoning chars for a 2,000-char chunk), so its per-call cost is ~10×
  the judge's.
- **The ramp was structurally unmeasurable on the real run** (before §I27): `generate_cards_for_chunks`
  wrote **nothing** until every chunk was done and there is **no cards-only flag** (`--raptor-only`
  rebuilds RAPTOR, not cards) — so a restart to change the worker count discarded the entire card run.
  **Now measured by a standalone probe instead:**
  `logs/p1/step10/probe_card_throughput.py` (sweeps workers × wall-clock budget over a deterministic,
  evenly-spaced 400-chunk sample; reports chunks/min, the last-60 s rate, p50/p90/max chunk wall time,
  error counts and the checkpoint write cost). See **"Measured 2026-10-20"** below.
- **Cheap-abort property confirmed, not assumed:** the aborted run left **0 cards, 0 RAPTOR nodes**,
  `knowledge_base_v2` still at **3,796** points, and the old document's **82,164** active cards
  untouched — the single write point makes a failed card run free.
- **No re-ingest.**

> ### ⛔ SUPERSEDED 2026-10-20 — the "congestion collapse" reading above is WRONG, and so is the
> ### `CARD_GEN_WORKERS=1` recommendation that came from it. Read the measurement below instead.
>
> **Why it was wrong — two errors, both mine.** (a) The 8-in-flight comparison was a **one-chunk
> probe** (7.6 / 10.9 / 10.1 s), i.e. a burst, and §I18's own rule says a burst does not measure
> sustained throughput. The sustained per-chunk cost at 8 in-flight measures **78 s at p50**, not
> 10 s — the probe was catching a fast moment, and both the "4.4× collapse" arithmetic and the
> 10.6 h ETA were built on that number. (b) The real run's 16 "timeouts" were measured with the
> **defective caller §I24 describes** — one un-retried POST, 120 s read timeout. A call that times
> out produces no card and was never retried, so *lost work* was counted as *slowness*.

**MEASURED 2026-10-20 — the card throughput sweep (controlled).** Instrument:
`logs/p1/step10/probe_card_throughput.py`, over a deterministic, evenly-spaced 400-chunk content
sample (`p50 103 / p90 205 / max 1,347` tokens), wall-clock budget per cell, **zero DB writes**.
Sweep 1 ran `1,2,4`; the **control sweep then re-ran `1,4,1`** to separate "concurrency helps" from
"the cluster got faster while I was measuring" — cells run in sequence with no repetition are
confounded, and the fix is to measure the first cell again at the end.

| sweep | workers | in-flight | chunks | **chunks/min** | last-60 s | p50 s | p90 s | max s | failed chunks | LLM failures | retries |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 1 | 8 | 12 | **3.77** | 3.0 | 88.4 | 150.3 | 190.8 | 0 | 0 | 0 |
| 1 | 2 | 16 | 20 | **6.52** | 7.0 | 91.2 | 158.6 | 184.0 | 0 | 0 | 0 |
| 1 | 4 | 32 | 32 | **10.42** | 13.0 | 104.5 | 167.5 | 184.2 | 0 | 0 | 4 |
| ctrl | 1 | 8 | 10 | **3.02** | 1.0 | 63.7 | 132.4 | 198.7 | 0 | 0 | 0 |
| ctrl | 4 | 32 | 21 | **8.36** | 10.0 | 82.6 | 138.9 | 150.8 | 0 | 0 | 1 |
| ctrl | 1 | 8 | 8 | **2.74** | 1.0 | 80.6 | 108.3 | 175.2 | 0 | 0 | 0 |

- **`workers=1` measured three times — 3.77 / 3.02 / 2.74 chunks/min (mean 3.18, spread 1.03),
  including once at the very end of the session after the `workers=4` cell.** The cluster did **not**
  drift during the sweep, so the scaling below is an effect of concurrency, not of time.
- **Throughput rises monotonically and never collapses: 3.18 → 6.52 → 9.39 chunks/min.**
  **2.05×** going 8 → 16 in-flight, **2.96×** going 8 → 32. Sublinear, but **still rising at 32
  in-flight** — the knee was not reached.
- **Zero failed chunks and zero LLM failures in all six cells (~40 min of load, 103 chunks).**
  Five retries in total, all of which succeeded. **There is no collapse to reproduce at 16, and none
  appeared at 32.**
- **The sustained per-chunk cost is ~64-105 s at p50 in every cell**, against the **10.1 s** the
  Phase B plan and the 10.6 h estimate were built on — an ~8× error in the planning number.
- **ETA for 3,791 chunks: `workers=1` → ~19.9 h · `workers=2` → ~9.7 h · `workers=4` → ~6.7 h.**
- **Checkpoint overhead measured: 3.0-3.6 ms per chunk write (fsync'd)** — negligible against
  ~80 s/chunk, so §I27 does not slow the run down.
- **What this does NOT establish, and must not be read as established:** `workers=8` (64 in-flight)
  was **not** tested, and the trend was still rising at 4 — so the knee may be above 4, not at it.
  The `workers=4` evidence is two cells (~5.5 min of load, 53 chunks), which is not a soak.
  And `.70` is a **shared** cluster (§I18, §I23): 32 in-flight calls is a real load on a resource
  other students are using, which is an etiquette question, not only a throughput one.
- **Decision this supports (owner's call):** run at **`workers=4`** (~6.7 h) rather than 1 (~19.9 h),
  with §I27's checkpoint making an abort cheap and §I24's deadline+retry making a transient stall
  survivable. **Do not go back to `workers=1` on §I26's original reasoning** — that reasoning rested
  on a burst probe and on timeouts the new caller would have retried.
- **Evidence:** `logs/p1/step10/phaseb_throughput_probe.{log,json}` and
  `..._control.{log,json}`.

### I27. FIXED 2026-10-20 — the card phase had no checkpoint and no resume, so a ~10.6 h run was all-or-nothing

- **What (before):** `generate_cards_for_chunks` held every card in memory and
  `DocumentStore.save_cards` wrote **once**, after the last chunk. No resume, no cards-only rebuild
  flag. An abort at chunk 3,700 of 3,791 discarded the entire card run.
- **Why it mattered:** the only measured-healthy configuration for this workload is
  `CARD_GEN_WORKERS=1` at ~10 s/chunk (§I26), i.e. **~10.6 hours** — and the endpoint had just been
  observed hanging for 41 minutes (§I24) and collapsing under concurrency (§I26). Retry and the
  deadline reduce the *probability* of an abort; only a checkpoint reduces its *cost*.
- **Fix (APPLIED 2026-10-20):** `src/pdf_ingestion/card_checkpoint.py` — an append-only JSONL
  side-car (`data/card_cache/<doc8>__<key>.jsonl`) that records each completed chunk's cards and the
  card types that failed. A re-run skips the checkpointed chunks **and still returns their cards**, so
  `save_cards` remains the single write point.
  - **Key = `(document_id, card types, model)`**, not the chunk list. Entries are validated against
    the chunk list being generated *now*, so a re-ingest (new `uuid4` chunk ids) simply matches
    nothing and its cards are dropped rather than written. Keying the *file* on the sorted chunk list
    was rejected: any knob that changed the filtered chunk set would make the previous 10.6 h
    **unfindable** instead of partially reusable.
  - **A chunk whose card types failed is NOT treated as done** — it is re-attempted on resume, so a
    run aborted during an outage cannot resume having "completed" the chunks that timed out.
  - **Header checked on read** (document / key / model / schema / digest-scheme), per §I19a: a
    mismatched file is an honest miss, not a file that loads and is wrong.
  - **Crash safety:** `flush()` + `fsync()` per write; a torn final line is truncated on load, so a
    crash costs one chunk, never the file.
  - Config: `card_checkpoint_enabled` (default true), `card_checkpoint_dir`, `card_checkpoint_every`;
    `run_phase2.py --no-resume` discards it.
- **Why not incremental SQLite writes (the alternative considered):** `save_cards` calls
  `_deactivate_cards()` first, so saving every N chunks would **delete the previous interval's cards**,
  leaving only the last batch. Even fixed, a partially-written card set in the DB is indistinguishable
  from a complete one to `evaluate_rag.py`, the UI and §A3's volume count — §I25's failure class again.
- **Evidence:** `tests/test_card_checkpoint.py` (15 tests: round-trip, resume issues no LLM calls,
  only missing chunks regenerated, failed-type chunk retried, `resume=False`, disabled, stale entries
  ignored, header checked on read, torn line truncated). The probe reports the write cost
  (**~5 ms/chunk, fsync'd** — negligible against ~10 s/chunk).
- **No re-ingest.**

### I28. NEW 2026-10-20 (found waiting on the card run's first log line) — `get_chunks_with_embeddings` retrieves **every named vector** for the whole document, over-fetching ~6× and costing minutes at the start of every Phase 2/3 run

- **What:** `DocumentStore.get_chunks_with_embeddings` (`store.py:820`) does
  `self._qdrant.retrieve(collection_name=…, ids=[c.qdrant_point_id for c in chunks], with_vectors=True)`
  — i.e. **all named vectors on all 3,796 points**, including the **ColBERT token matrices**, and the
  caller uses only the dense vector (for RAPTOR clustering).
- **Why it matters — it is a startup stall on a network path, and it costs ~2 GB of RAM.** Measured
  2026-10-20 on the Phase B run: `Processing 7ba61432…` sat for **3 minutes 6 seconds**
  (19:05:10 → 19:08:16) before `Generating cards for 3791 chunks …` appeared, and **RSS climbed
  36 MB → 1,992 MB** as the response was deserialized — the ColBERT token matrices held in memory
  for the rest of the run. Sizing from the stored dims: ColBERT is `(128, n_tokens)` per chunk — at
  the corpus's ~103-token median that is ~53 KB/chunk, so **~200 MB of vectors against ~33 MB
  actually wanted** (and the JSON/base64 envelope inflates that several-fold on the wire). It is
  **~6× the payload and ~60× the memory** the caller needs, paid by *every* Phase 2 and Phase 3 run.
- **Not a hang, and not a regression:** it is pre-existing behaviour. The trap is diagnostic — a
  watcher who sees no log line for minutes will read it as a stalled run and may kill it.
- **Fix (not applied):** pass an explicit `using=`/vector-name selector so only the dense slot is
  returned, or store the RAPTOR input vectors separately. One-line-ish change at the call site; **the
  contract to preserve is that the returned dense order matches `chunks` order** (the caller zips them).
- **No re-ingest** (read path only). **Does not block Phase B** — it only costs time at startup.
- **Evidence:** `src/pdf_ingestion/store.py:836-841`; the Phase B run log's gap between
  `Processing …` and `Generating cards for …`; `logs/p1/step10/phaseb_run.log`.

### I29. NEW 2026-10-20 (found running the §G3 baseline probe) — the §G3 verifier measures the WRONG quantity, and read as written it has 3.1 points of headroom

- **What:** the §G plan's G3 verifier 3 says *"the §I2 symptom improves: the share of chunks matching
  ≥2 distinct concepts rises. That is the measured quantity §I2 says is the real problem (currently
  most chunks tie at 1)"*. That sentence fuses **two different quantities**, and the one it names is
  not the one §I2 describes.
- **Measured 2026-10-20 (read-only, doc `7ba61432`, `logs/p1/step10/probe_g3_baseline.py`):** read as
  "distinct concepts a chunk mentions", the quantity is **already 0.9687** — and **0.9172** at ≥3:

  | concepts mentioned per chunk | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 |
  |---|---|---|---|---|---|---|---|---|
  | chunks | 115 | 189 | 686 | 1,015 | 1,131 | 400 | 135 | 1 |
  | | | | | | | | | |

  3,672 of 3,796 chunks carry ≥1 concept; mean **4.25** concepts/chunk. So a verifier phrased this way
  can move **at most 3.1 points** (115/3,672 = 3.1 % of concept-bearing chunks sit at exactly 1) —
  it cannot discriminate a good merge from a bad one.
- **The quantity §I2 actually means is QUERY-SIDE.** `GraphBuilder.graph_search`
  (`src/pdf_ingestion/graph_builder.py:449-459`) scores a chunk by
  `size(collect(DISTINCT k.name))` over the **query's** `top_k=8` concepts, then
  `ORDER BY matched_concepts DESC`. *That* is what ties at 1. A chunk's total concept count is
  irrelevant to the ranking.
- **Why it matters:** as written, G3's headline verifier would pass trivially (96.9 % → 97 %, i.e.
  noise) and a real regression would look like a success. **Do not use it.** Measure the query-side
  distribution — needs a 768d query embedding against `Concept.embedding`, so it is a cluster-embed
  probe, not a pure-Cypher one (§I12 keeps the graph lane on the 768d legacy model).
- **MEASURED 2026-10-20 — see §I32.** The query-side `matched_concepts` distribution is now
  measured over all 200 v2 gold queries: **97.86 %** of matching chunks tie at exactly 1
  (mean 1.0219, share ≥2 = 0.0214, 200/200 parity with the production `graph_search` call).
  So the quantity §I29 rejected has **3.1 points** of headroom and the quantity it should have
  named has **97.86 %** of its mass at the floor. **Design G3's verifier against §I32's number.**
- **No re-ingest** (measurement only).
- **Evidence:** `logs/p1/step10/probe_g3_baseline.py`, `probe_g3_baseline.json`;
  `src/pdf_ingestion/graph_builder.py:449-459`.

### I30. NEW 2026-10-20 — the §G3 lever, MEASURED: 1,186 merge groups over 34.4 % of the concept vocabulary, and no group gains nothing

- **What:** §I2 asserts *"deduplicating concept names is the bigger lever than ranking"* but the size
  of the lever was never measured. Measured now, read-only and LLM-free
  (`logs/p1/step10/probe_g3_lever.py`), by the mechanism G3 actually uses: a query resolving to one
  spelling reaches only that spelling's chunks, so merging a group unions the chunk sets — the delta
  is what G3 recovers.
- **Measured (doc `7ba61432`):**

  | quantity | value |
  |---|---|
  | distinct concept names | 7,834 |
  | normalised merge keys | **6,327** (see the correction below) |
  | merge groups (>1 member) | **1,186** |
  | concepts inside a merge group | **2,692 = 34.4 %** of the vocabulary |
  | groups that gain **nothing** | **0** — the lever is real in every group |

  > ⚠️ **CORRECTED 2026-10-20 (same session, caught by re-running after a guard change).** This row
  > first read **6,328**, and that number was **wrong**: it counted a bogus `""` merge key. Exactly one
  > concept name normalises to the empty string — **`'s'`**, the single letter, destroyed by the
  > plural rule (`'s'` ends in `s`, is not `ss`, so `n[:-1]` → `""`). The `""` key was therefore
  > treated as a real concept key. A guard now skips empty keys and reports the count
  > (`names_skipped_empty_key`), which is **1** here — so the guard is *not* a no-op, and the true
  > count is **6,327**. Cross-check: 1,186 groups hold 2,692 names, leaving 5,141 singleton keys;
  > 1,186 + 5,141 = 6,327 ✓, and 2,692 + 5,141 = 7,833 = 7,834 − 1 (the skipped `'s'`) ✓. **The lever
  > numbers above are unaffected** — every other field re-ran identical.

  > **Verification note (2026-10-20) — the independent reviewer VERIFIED the wrong number, and that
  > is the useful part.** An adversarial reviewer (`openai/gpt-oss-20b`, a different model from the
  > author's, 14 API calls, 371 s — a substantive pass, not a cheap one) checked eight claims and
  > returned **ALL_VERIFIED**, explicitly confirming `normalised_keys = 6328` and reproducing its
  > arithmetic (7,834 − 2,692 = 5,142 singletons; 5,142 + 1,186 = 6,328). **It was wrong, and it could
  > not have been right**: the artifact it was given genuinely contained the bogus `""` key, so the
  > number was *internally consistent*. A reviewer checks the claim against the artifact; it cannot see
  > that the artifact's key construction is wrong unless it re-derives the metric itself.
  > **What settled it was re-running the probe after the guard change** — mechanical evidence, not the
  > reviewer's agreement. Two further limits in that same pass: it cited `probe_g3_lever.json` for
  > `distinct_concepts_mentioned` and `normalised_keys`, which are **baseline** fields the lever artifact
  > does not contain (wrong attribution, right values), and its claim-F arithmetic as written
  > (`3740-3672=124`) does not compute — its conclusion was right, its stated working was not.
  > **So: a passing verifier is evidence of consistency, not of correctness. Weight it accordingly.**
  > **Round 2 (after the guard fix) confirmed the corrected values:** a second independent pass
  > (same reviewer model, 20 API calls, 158 s) returned `ALL_FIXES_CONFIRMED` and `VERIFIED` on all
  > eight numbers — **6,327** and `names_skipped_empty_key = 1` included — and confirmed the two
  > `norm()` functions are now identical. One caveat on that pass's own wording: it reported the two
  > **rejected** findings (F2, F4) as `CORRECTLY_CLOSED` rather than `WRONGLY_REJECTED`, which is the
  > schema's word for a sound rejection — but it never explicitly re-argued either rejection, so read
  > it as *no objection raised*, not as independent endorsement. The rejection evidence for those two
  > is the author's own probe (0 null names + the live `unique` constraint; all 20 after-merge hubs
  > with `members ≥ 2`).

  Largest groups by chunks newly reachable (union − best single spelling):

  | group | union | best single | gained |
  |---|---|---|---|
  | `Force` / `force` / `forces` | 175 | 95 | **+80 (45 % of "force" chunks invisible to a wrong-spelling query)** |
  | `kinetic energy` / `Kinetic Energy` / `Kinetic energy` | 102 | 51 | **+51 (exactly half)** |
  | `Temperature` / `temperature` | 113 | 62 | +51 |
  | `velocity` / `Velocity` / `Velocity = √(g h)` | 172 | 121 | +51 |
  | `speed of light` / `Speed of light` / `Speed of Light` | 98 | 51 | +47 |

  The hub list **reorders**: `velocity` 121 → 172, `force` 95 → **175 (becomes the top hub)**,
  `electric field` 70 → 115. That reordering is the course's own Lab 1 exercise (*"measure how merging
  them changes the hub list"*).
- **Caveat, stated:** the summed "newly reachable" figure is a **sum over groups**, so a chunk reached
  by two groups is counted twice — it is not a distinct-chunk count. The per-group ratios (half, 45 %)
  are the trustworthy reading.
- **Why it matters:** it converts §I2 from an assertion into a sized claim, and it justifies doing G3
  **before** G1/G2 — a 34.4 % share of the vocabulary being near-duplicate is large enough that any
  PPR or community structure computed on the unmerged graph is computed on a fractured node set.
- **No re-ingest** (graph-side analysis only). **No LLM calls** — so it is safe to run alongside the
  in-flight card run, unlike anything that hits the cluster's model endpoints (§I23).
- **Evidence:** `logs/p1/step10/probe_g3_lever.py`, `probe_g3_lever.json`.

### I31. NEW 2026-10-20 — three §G3 design traps, all measured: non-synonym groups, substring matching, and the Greek-symbol normaliser

- **What:** the G3 probe surfaced three ways a naive entity-resolution implementation damages the graph.
  Each was hit for real while writing the probe, not hypothesised.
- **Trap 1 — a normalisation group is not a synonym set.** Measured example:
  `['velocity', 'Velocity', 'Velocity = √(g h)']`. The third member is a *formula*, not a spelling
  variant, and merging it into `velocity` is exactly the failure the §G plan warns about (*"merging two
  genuinely distinct concepts is worse than leaving a duplicate"*). With **1,186 groups**,
  eyeballing every one is not affordable; the top ~50 carry most of the measured gain (§I30), so
  review should be budgeted there.
- **Trap 2 — substring matching must NOT be used.** There are **809** normalised substring pairs and
  most are genuinely distinct concepts, not duplicates: `air` ⊂ {air acceleration, air density, air
  displacement, air molecule, air movement, air pressure, air temperature, air trough, air velocity, …}
  (12+); `absorption` ⊂ {absorption coefficient, absorption probability, absorption spectrum, …}. A
  substring-based merge would collapse the vocabulary catastrophically. The §G plan's *"candidate
  signal: name normalisation"* must be read as normalisation **only**.
- **Trap 3 — the normaliser silently destroys physics notation, in TWO separate ways.** Measured, not
  hypothesised; the two need different fixes and only the first is obvious.
  - **(a) punctuation stripping.** `re.sub(r"[^a-z0-9 ]+", " ", n)` maps every Greek symbol to the
    **empty string**, collapsing `χ (x, t)`, `γ`, `ħ ω`, `π`, `ε`, `γ (ratio of specific heats)`, `τ`,
    `η`, `α` into **one** bogus merge group. Observed on the first probe run. Fix: a Unicode-aware
    class — `re.sub(r"[^\w ]+", " ", n, flags=re.UNICODE)`. Verified after the fix: `χ (x, t)` → `χ`,
    `γ` → `γ`, both kept.
  - **(b) the plural rule, which survives fix (a).** A trailing-`s` strip (`if n.endswith("s") and not
    n.endswith("ss"): n = n[:-1]`) turns the single-letter concept **`'s'` into `""`** — and the `""`
    key is then a *valid merge key*, so it merges whatever else normalises there and **inflates the
    normalised-key count by one** (§I30's correction). Fix: skip empty keys explicitly and **report the
    count** (`names_skipped_empty_key`, measured = **1**). A bare skip would hide the case; the reported
    counter is what makes it visible.
  - **Design rule from both:** a normaliser must never return a key that no name could legitimately
    produce, and any name it *cannot* key must be counted, not dropped. Silence here is the failure
    mode — the merge counts improve while the graph degrades.

- **Trap 4 — a number registered from a probe is invalidated the moment the probe changes.** §I30's
  `normalised_keys` was registered as 6,328 from a run of the *pre-guard* script; adding the empty-key
  guard moved it to 6,327. The value was in the register before the script that produced it was final.
  **Rule: whenever a probe script changes, re-run it and re-check every number already registered from
  it** — and prefer registering numbers only after the script is frozen. The re-run is cheap; the
  register is what the next session trusts.
- **Trap 5 (scope limit on verification) — a verifier cannot detect a wrong metric, only an
  inconsistent claim.** Both probes were reviewed by a different model, which returned ALL_VERIFIED
  *including* the wrong 6,328 (§I30's verification note). It also misattributed fields to the wrong
  artifact and wrote arithmetic that does not compute while reaching the right answer. **Verification
  buys consistency-checking; it does not buy metric critique.** The two findings that mattered most in
  this whole exercise — that the §G plan's G3 verifier measures the wrong quantity (§I29) and that
  `normalised_keys` was inflated by a bogus key — came from *reading the code and re-running it*, not
  from any reviewer. Do not let a green verifier stand in for re-deriving the metric.
- **Also measured while probing:** **124 of 3,796 chunks (3.3 %) carry zero concepts** (3,672 have ≥1;
  see §I29's histogram). §I23 reported **44** LLM failures (1.2 %) on the same build, so **~80 further
  chunks got a valid LLM response that yielded no concepts** — and neither figure is visible in the run
  log, which reported *"0 failed"*. Refines §I23's number; does not change its conclusion.
- **Why it matters:** the first two traps are silent (the counts improve while the graph degrades), so
  they need to be designed out, not caught in review.
- **No re-ingest** (graph-side analysis only).
- **Evidence:** `logs/p1/step10/probe_g3_lever.py`; `logs/p1/step10/probe_g3_baseline.py`.

### I32. MEASURED 2026-10-20 — the §I29 query-side number, and it is the opposite of the chunk-side one: **97.86 % of matching chunks tie at exactly 1 concept**

- **What:** §I29 registered the query-side `matched_concepts` distribution as "the next G3
  measurement, not a result". Measured now — read-only, no LLM, deterministic.
  `logs/p1/step10/g3_query_side_baseline.py`. For each of the **200** v2 gold queries: embed the
  raw query with **nomic 768d** via `:8123` (the model `Concept.embedding` uses, §I12), take the
  top-8 concepts exactly as `GraphBuilder._find_concepts_scored(vec, top_k=8)` does, then run the
  **same ranking Cypher** `graph_search` runs (`graph_builder.py:449-459`) but with **no LIMIT**,
  so the whole distribution is visible rather than the top 5.
- **Measured (collection `knowledge_base_v2`, graph doc `7ba61432`):**

  | quantity | value |
  |---|---|
  | queries | 200 (166 answerable, 34 negative) |
  | chunks matching ≥1 of the query's 8 concepts | **3,512** |
  | `matched_concepts` = 1 | **3,437 = 97.86 %** |
  | `matched_concepts` = 2 | 73 |
  | `matched_concepts` = 3 | 2 |
  | mean | **1.0219** |
  | share ≥2 | **0.0214** |
  | top-5 median of medians | **1.0** (hist: 1 → 196 queries, 1.5 → 1, 2 → 3) |
  | parity with the production `graph_search` call | **200/200** |

- **Why it matters — this is the number §I29 said was missing, and it vindicates §I29's
  objection quantitatively.** The quantity §I29 rejected (a chunk's TOTAL concept count) is
  already 0.9687 with **3.1 points** of headroom. The quantity `graph_search` actually ranks by
  has **97.86 %** of its mass at exactly 1. So G3's effect is readable here and was
  unreadable there — a ~30× difference in discriminating room. **Design G3's verifier against
  this number, not against 0.9687.**
- **The mechanism is visible in the anchor.** For `gold-062` the top-8 concepts are
  `Kinetic energy of gas particles`, `total energy equals kinetic energy for monatomic gas`,
  `total energy of a particle`, `Total energy of a particle`, `Kinetic energy`,
  `kinetic energy`, `Kinetic Energy`, `kinetic theory of gases` — i.e. **one concept in three
  spellings** plus near-synonyms. A chunk mentioning "kinetic energy" therefore matches at most
  1 of the 8, which is exactly §I2's "ties at 1" and exactly what §I30's merges would repair.
- **Reproducible:** two runs are **byte-identical** (sha256
  `8f8526857ea49273f2430484ad203a189f81ee486102470e287ae63911f8e0c7`); the JSON carries **no
  wall-clock field** for that reason. Non-degenerate (values {1,2,3}); 0 embed errors; 0 queries
  resolving no concepts.
- **No re-ingest** (measurement only). **No LLM calls.**
- **Verification note (2026-10-20).** An independent reviewer (`openai/gpt-oss-20b`) re-ran the script
  to its own scratch path, obtained the **identical sha256**, and recomputed the aggregate from the
  `queries` array itself. **VERIFIED on all nine checks** — the five aggregate numbers, the degeneracy
  verdict, byte-identity, the `gold-062` anchor (on-topic), and parity 200/200 — with no objections.
  (Its own `claims_checked` field says 5 while its `findings` array lists 9; the findings are what
  carry the evidence, and they cover all nine.) One earlier reviewer of the same artifact returned
  `REFUTED` *after its own bad re-run had zeroed the artifact* — a void verdict, not a disagreement
  (§I38).
- **Evidence:** `logs/p1/step10/g3_query_side_baseline.py`, `..._baseline.json`, `..._baseline.log`;
  `src/pdf_ingestion/graph_builder.py:449-459`.

### I33. NEW 2026-10-20 — the §G plan's Leiden premise is FALSE: `leiden_communities` exists in networkx 3.6.1 but **cannot run** — it is a backend-dispatch stub

- **What:** the §G plan §2 records, as **verified**, that *"Leiden and `modularity` are both
  present in the installed networkx 3.6.1 … no new dependency"*. `modularity` is native.
  `nx.community.leiden_communities` is **not**:
  ```
  NotImplementedError: 'leiden_communities' is not implemented by 'networkx' backend.
  This function is included in NetworkX as an API to dispatch to other backends.
  ```
  Measured 2026-10-20: the only registered backend is `nx_loopback`; **igraph, leidenalg,
  nx_parallel and graphblas are all absent** from the venv. So the *symbol* exists and the
  *algorithm* does not — the plan verified the name, not the behaviour.
- **Consequence, measured:** the §G2 modularity gate was run on **Louvain** instead (native), and
  Louvain returned **1 disconnected community of 75 members** (community index 35, "air
  density / air pressure / carrier frequency / beat / …"). **Leiden's entire selling point over
  Louvain is that every community it returns is connected.** So the gate's verifier 3 ("every
  community asserted connected") is **unmet on the substitute**, and the script measures
  connectivity rather than assuming it.
- **Result of the gate (before arm, report-only, one-sided):**

  | | |
  |---|---|
  | graph | 7,808 nodes, 37,296 undirected edges (from 37,300 directed `RELATES_TO`, 4 self-loops dropped), 89 components, density 0.001224 |
  | partitioner | **louvain** (leiden unavailable), resolution 1, unweighted, seed 20261020 |
  | `Q(observed)` | **0.589597** (199 communities) |
  | `Q(rewired null)` | **0.280330** (22 communities) |
  | `Q(observed partition)` on the rewired graph | −0.001994 |
  | gap / ratio | **+0.309267 / 2.1032** → **PASS (one-sided)** |

  The null is a degree-preserving rewiring (`double_edge_swap`, 372,960 swaps, degree sequence
  confirmed preserved). Two runs byte-identical
  (sha256 `13a4e364043f82f6924c75a651467c4d84a39683f01cd4fa3d9415ffd5e9fb86`).
- **Why it matters:** (a) a *"verified in the plan"* claim was verified only at the level of
  symbol existence — the same failure class as §I29; (b) the one-sided caveat still holds (a PASS
  is trustworthy, a FAIL would be confounded by §I21's TOC concepts), so the gate's **PASS** stands;
  (c) the **connectedness verifier cannot be satisfied** without either adding a backend dependency
  or accepting Louvain + measuring connectivity. **Owner decision needed.**
- **No re-ingest. No LLM calls.** Local CPU, ~6 s.
- **Evidence:** `logs/p1/step10/g2_modularity_gate.py`, `..._gate.json`, `..._gate.log`.

### I34. FIXED 2026-10-20 — §D14 fix (b): the preflight graph↔Qdrant check is now SCOPED, so it can no longer cry "retired content" at a healthy graph

- **What:** `scripts/preflight.py` check [4] compared every chunk id in the graph against the
  collection **under test**. Chunk ids are `uuid4()` per ingest, so when the collection under test
  is a different ingest from the graph's, the check reported ~100 % dangling and printed
  *"Graph has retired content. Fix: `clean_stale_graph.py …`"* — an instruction that, run against a
  live collection, would delete a correct graph (§D14 fix (c) was chosen, so the graph is right and
  the check was wrong).
- **Fix (b), implemented:** the verdict gained a third state — **PASS / FAIL / SKIP** — and the graph
  check now resolves the graph's own `Document` ids and counts how many points in the collection
  under test carry them. None present → the check is reported as **SKIP** with an explicit
  *"MISMATCH: the graph was built from a different ingest … the graph lane is NOT MEASURED for this
  collection … This is not retired content — do NOT run `clean_stale_graph.py`"*, and it is **not**
  a blocker. Present → the original dangling check runs unchanged, with the scope count appended as
  evidence.
- **Measured (all three arms, real runs):**

  | arm | collection under test | before the fix | after the fix |
  |---|---|---|---|
  | positive | `knowledge_base_v2` (the graph's) | PASS, 0/3,796 absent (0.0 %), exit **0** | PASS, 0/3,796 absent (0.0 %) + *graph doc(s) present: 3,796 points*, exit **0** |
  | negative | `knowledge_base` (NOT the graph's) | FAIL, 3,796/3,796 absent (100.0 %) + the `clean_stale_graph.py` instruction, exit **1** | **SKIP** + the MISMATCH message, no `clean_stale_graph.py` instruction, exit **0** |

  Every **non-graph** check is identical before vs after (18 of them; the only other difference in
  the negative arm is the collection-under-test row being renamed `qdrant.knowledge_base_v2` →
  `qdrant.knowledge_base`, showing 3,796 vs 5,135 points — config, not code).
- **⚠️ Residual, and it needs a decision:** a re-ingest transition now reports **SKIP** rather than
  a false blocker, so it passes the gate — but the **graph lane is genuinely not measured** for that
  run. Whether that should be non-blocking (as implemented, matching the plan's "skip it with an
  explicit note") or a hard blocker (the multihop lane silently contributes nothing — the §D11
  class of failure the preflight exists to catch) is an **owner decision**, not a code question.
- **⚠️ Also note:** `preflight.py` is **not** LLM-free — `check_completions` issues one real
  completion per distinct pipeline (model, url); the four sections dedupe to **one** call. So a
  preflight run is ~1 LLM call on the shared cluster, not zero.
- **No re-ingest.**
- **Evidence:** `logs/p1/step10/a2_preflight_before.log`, `..._after.log`, `..._negative.log`,
  `..._negative_before.log`; `scripts/preflight.py`.

### I35. FIXED 2026-10-20 — §I28's over-fetch is gone: `get_chunks_with_embeddings` now asks for the one lane it reads

- **What:** §I28 found that `DocumentStore.get_chunks_with_embeddings` issued
  `retrieve(..., with_vectors=True)`, returning **every named vector on every point** — including
  the `colbert` token matrices nothing there uses. It now resolves the dense lane name off the
  collection schema (`_dense_name_from(self._collection_vectors())`) **before** the retrieve and
  passes `with_vectors=[named_dense] if named_dense else True`; the `True` fallback preserves the
  legacy single-vector-collection path that `_extract_dense` already handled.
- **Measured (3,796 ids, fresh process per arm):**

  | | before | after |
  |---|---|---|
  | retrieve wall | 195.1 s | **12.9 s** |
  | RSS | 309.8 → 5,320.2 MB (growth **5,010.3**) | 306.6 → 922.5 MB (growth **615.9**) |
  | vector names returned | `colbert, dense_1024, dense_64, sparse` | **`dense_1024` only** |
  | in-process head-to-head | 107.6 s | **9.8 s** (10.95×) |

  **Contract holds:** `arrays_equal` true, `max_abs_diff` **0.0**, shape preserved, chunk order
  matches the id list, and the dense matrix sha256 is **identical** across every arm
  (`3fcbc5ab…`). The call change is asserted at the client boundary (spy prints the kwargs).
  §I28's own anchor was 3 min 06 s / 36 → 1,992 MB; re-measured larger here because the card run is
  sharing the tunnel — **the before-arm wall time varied 107.6–195.1 s across runs, so quote the
  ratio, not the absolute.**
- **Not verified by re-running the card phase** (the plan forbids it: hours, and the run is in
  flight). The fix benefits the *next* Phase 2/3 run; the running one has already paid the cost.
- **Tests:** `uv run pytest tests/ -q -m "not slow" -k "store or chunk or embed"` → 177 passed,
  1 failed (`tests/test_phase1.py::TestStore::test_hybrid_search_includes_global`, `assert 0 > 0`).
  **That failure is pre-existing** — confirmed by reverting only `store.py` and re-running the one
  test, which fails identically.
- **No re-ingest.**
- **Verification note (2026-10-20).** Reviewer 3 returned **VERIFIED** (6 findings, no objections,
  27 API calls / 492 s) after checking the exact field paths: `call_changed.with_vectors_issued ==
  "['dense_1024']"`, `is_bool_true == false`, `contract` all true, the dense-matrix sha256 equal
  across both fresh-process sections, and the only consumer reading the dense lane. It also **re-ran
  the head-to-head itself** (`uv run python logs/p1/step10/a3_fetch_probe.py --arm both`, twice),
  which reproduced `CONTRACT OK: True` and rewrote `both_one_process` — the artifact was re-validated
  afterwards (parses, contract all true, fresh-process sections untouched). Reviewer 1 had returned
  `REFUTED` on a **field misattribution** — it compared the fresh-process claim against
  `both_one_process`'s RSS, which the artifact's own `same_process_note` flags as allocator-affected —
  and separately **left `store.py` reverted** (§I38); that verdict is overturned on evidence, not
  withdrawn by argument. One weakness in reviewer 3's pass: its "legacy fallback" finding is
  **reasoned, not executed** (no collection without a named dense slot was available to test against).
- **Evidence:** `logs/p1/step10/a3_fetch_probe.py`, `..._probe.json`, `..._probe.log`;
  `src/pdf_ingestion/store.py`.

### I36. NEW 2026-10-20 — a plan premise was carried from the register without re-running it: A2's "today: exit 1, 1 BLOCKER" was already stale

- **What:** the non-LLM work plan's A2 says `preflight.py` "exits 0 for
  `QDRANT_COLLECTION=knowledge_base_v2` (**today: exit 1, 1 BLOCKER**)". Measured 2026-10-20 before
  touching anything: **exit 0, 0 blockers**, `graph.matches-qdrant` **PASS** 0/3,796 (0.0 %). The
  "exit 1" figure was §D14's **2026-10-18** record, taken *before* the owner chose fix (c) and the
  graph was rebuilt (2026-10-19, A3/A4/A5) — after which the premise no longer held.
- **Why it matters:** it is §I31 trap 4 one level up. Trap 4 is *"a number registered from a probe
  dies when the probe changes"*; this is *"a premise registered from a state dies when the state
  changes"*. A plan that inherits a blocker from the register and does not re-run it will build its
  verifier around a symptom that is already gone — here, verifier arm 1 ("exits 0") was satisfied
  **before** the fix and therefore proved nothing. The load-bearing arms were the negative arm and
  "nothing else changed". **Rule: a plan that quotes a measured blocker must re-run that
  measurement, and record the date it was taken.**
- **No re-ingest.**
- **Evidence:** `logs/p1/step10/a2_preflight_before.log` (exit 0, pre-fix);
  `logs/p1/step10/a5_preflight.log` (exit 0, 2026-10-19); §D14's own 2026-10-18 record.

### I37. NEW 2026-10-20 — `rich` silently DROPS `[...]` inside a table cell, so a check's own detail string can vanish with no error

- **What:** a `preflight.py` detail string was extended with
  `"  [graph doc(s) present in collection: 3,796 point(s)]"`. The row printed
  `0/3,796 graph chunk ids absent from Qdrant (0.0%)` — **the appended evidence was gone, no
  exception, exit 0.** `rich` parses `[...]` in a cell as **markup**; an unrecognised tag is
  swallowed. Minimal reproduction: a table cell containing
  `"0/3,796 absent (0.0%)  [graph doc(s) present in collection: 3,796 point(s)]"` renders as
  `0/3,796 absent (0.0%)` alone.
- **Why it matters:** it is a **measurement-integrity** trap, not a cosmetic one. The scoped
  preflight check was working correctly the whole time — the *evidence that it was working* was
  being deleted on the way to the screen, which makes a working guard look like a no-op and invites
  exactly the "is this guard vacuous?" review question that was raised. **Rule: no square brackets
  in any string that goes into a `rich` table cell; use parentheses.** Caught by reading the log
  back rather than trusting the code, which is why "raw output captured to a file and read back" is
  a verifier step.
- **No re-ingest.**
- **Evidence:** `scripts/preflight.py` (the `# NOTE: no square brackets…` comment);
  `logs/p1/step10/a2_preflight_after.log` (before/after of the fix).

### I38. NEW 2026-10-20 — an independent reviewer can DESTROY the thing it is reviewing: two real incidents in one session

- **What:** two independent reviewers (`openai/gpt-oss-20b`, a different model from the author's)
  mutated the artifacts under review. Neither self-reported it.
  - **A3's reviewer reverted `src/pdf_ingestion/store.py` to run a "is this test failure
    pre-existing?" check, and did not restore it.** The change under review was gone from the
    working tree; it was only caught by re-running `git diff` after the review returned. The child's
    own completion notice said `completed`.
  - **A1's reviewer re-ran the measurement script without `--out`**, so it wrote to the script's
    **default artifact path**, under a **bare `python`** with no project dependencies — the concept
    search returned nothing and it wrote an **all-zeros JSON over the good artifact**, then reviewed
    that and returned `REFUTED` on it. Its own finding says so: *"All queries have an empty
    `matched_concepts_histogram` in the source JSON"*.
- **Why it matters — two lessons, one per side.**
  1. **Reviewer-side:** a brief that says "verify the artifact" is not enough; it must say **do not
     modify anything under the repo**, must give scratch paths explicitly, and must name the exact
     interpreter (`uv run python`). "Restore it afterwards" is not a control — a child that has
     finished cannot be made to. And **a child's self-report is not evidence**: both said they had
     completed; one had deleted the change. Verify the tree after every review.
  2. **Author-side, and this is the more general defect:** the measurement script's `--out`
     **defaulted to the registered artifact path**, so any re-run silently replaced the record, and
     an unreachable dependency produced a **clean-looking all-zeros artifact** rather than an error.
     Fixed in the same session: `--out` refuses to overwrite without `--force` (exit 4), the concept
     collection is probed up front (abort, exit 3), queries resolving no concepts are counted, and a
     zero-total run **aborts without writing**. **Rule: a measurement script must not be able to
     overwrite its own registered artifact by accident, and "no data" must never be
     indistinguishable from "all-zero data".**
- **No re-ingest.**
- **Evidence:** `logs/p1/step10/g3_query_side_baseline.py` (the guards + their comments);
  `git diff src/pdf_ingestion/store.py`; the A1/A3 review transcripts under
  `~/.hermes/cache/delegation/live/`.

### I39. FIXED 2026-10-21 (session 2) — the E5 content filter's *documented* gap went LIVE at the re-ingest: TOC and index chunks passed as content, **6.7 % of the card corpus is built from them**

- **What:** `src/pdf_ingestion/content_filter.py` (`is_content`, §E5) is a text rule — keyword
  markers, an exact index-heading line, an index pipe-table shape, and an all-punctuation rule. Its
  own docstring states the limit: *"It does **not** yet catch all front-matter prose (publisher's
  note, preface) or the Name-Index / TOC continuation rows — those are recorded as an §E5 follow-up,
  **and the page bounds still cover them until the Step 8 run zeroes them**."*
  **The re-ingest is that Step 8 run.** Measured 2026-10-21 on doc `7ba61432`: the flag now catches
  **5 chunks in the whole document**, and all five are copyright/legal boilerplate (copyright page,
  "all rights reserved", acknowledgements, author affiliations, the print statement).
- **Measured — chunks by page band, and the cards built from them:**

  | band | pages | chunks | cards | % of cards |
  |---|---|---|---|---|
  | front matter | 1-30 | 120 | 2,256 | 3.0 % |
  | — of which TOC / editorial | 20-26 | 19 | 390 | 0.5 % |
  | body | 31-900 | 3,349 | 65,906 | 87.1 % |
  | back matter | 901-970 | 327 | 7,483 | 9.9 % |
  | — of which **index** | 936-970 | 193 | **4,710** | **6.2 %** |
  | | | | **75,645** | |

  So **4,710 + 390 = 5,100 cards (6.7 %)** are built from pure index/TOC chunks, and the filter flags
  **none** of them. `is_content` by band: front matter 115/120 "content", body **3,349/3,349**, back
  matter **327/327**.
- **Observed card quality (B6, 22 cards read — 8 by type, then a seeded document-wide sample):** on
  genuine body chunks the cards are good, and one is exemplary — a `formula` card from p545 carries
  the full plasma-frequency relation in LaTeX with every symbol defined and its validity conditions.
  The junk is all from the non-body bands, and it is unmistakable:
  - `factoid` p23 → *"The section 5-5, 2 references section 5-9."* (from the **TOC**)
  - `question` p941 → *"What do the codes 25-3, 39-19, and 40-1 refer to?"* (from the **index**)
  - `formula` p20 → invents `f = 1/N` from an editorial passage about **how many staff members wrote
    the course** — a fabricated formula from administrative prose
  - `factoid` p20 → *"The considered plans were mostly rather similar."* (verbatim filler)
- **Why it matters:** this is §I21's noise, and it is not confined to the graph. The graph build
  omits the filter entirely (§I21); the **card** lane applies it, and the filter lets TOC and index
  through — so the same non-content regions that fragment communities also contribute ~6.7 % of the
  card corpus, where they are retrievable and citable. **Fixing §I21's filter fixes both lanes**, and
  the fix has a precise target: the two signals the docstring already names as missing (TOC
  continuation rows, front-matter prose) plus a page-band backstop.
- **No re-ingest to measure** (read-only). A fix **does** require a re-ingest to take effect.
- **Evidence:** `logs/p1/step10/b6_card_samples_2026-10-21.txt` (the 22 cards + the band counts);
  `src/pdf_ingestion/content_filter.py` (docstring and rule); `src/pdf_ingestion/chunker.py:158`.

#### I39 outcome — FIXED 2026-10-21 (session 2): two signals added, and the band table above CORRECTED

**⚠️ The band table above is wrong, and it is wrong in the direction that hid the problem.**
Re-measured from the text (`logs/p1/step10/i39_boundary_probe.py`):

| | §I39's table | measured |
|---|---|---|
| TOC | 19 chunks, pages 20-26 | **77 chunks, pages 22-34** |
| index | 193 chunks, pages 936-970 | 187 chunks, pages **937-968** (p936 is chapter prose) |
| body | 3,349 chunks, pages 31-900 | 3,467 chunks, pages 35-936 |

So ~55 TOC chunks were being counted as **body**, which is exactly why the handoff's "a page-reference
density test catches 187/193 index chunks **with 0 body false positives**" did not reproduce: a
false-positive count taken over "pages 31-900" **includes the TOC itself**. Re-measured with the TOC
and index pages excluded, the un-anchored half of that pattern gives **558** body hits and the
comma-anchored half gives **0**. The claim conflated the two.

**The fix — two signals, both measured, both with zero body collateral:**

| # | signal | catches | body loss |
|---|---|---|---|
| 4 | `is_toc_layout` — a dot-leader **run** (`(?:\.\s?){4,}`) **plus a section number** (`\b\d{1,2}-\d{1,2}\b`) | **72 / 77** TOC chunks | **0** |
| 5 | `is_index_density` — ≥34 % of non-blank lines match `,\s*(?:[IVX]{1,3}-)?\d{1,3}-\d{1,3}` | **186 / 187** index chunks | **0** |

**End-to-end on doc `7ba61432` (3,796 chunks, `logs/p1/step10/i39_verify_filter.py`):** TOC 72/77
dropped, index 186/187, front matter 5/65, **body 0/3,467 — no content chunk is lost.**

**Rejected, both measured** (`logs/p1/step10/i39_signal_design.py`, `i39_fp_inspect.py`):
- **A bare dot-leader run.** Fires on real prose: p661's ratchet discussion
  (`"click . . . . . click-click . . . click . . ."`) and the preface's quoted ellipses (p7-8).
  Adding the section-number requirement removes exactly those three and keeps all 72 TOC catches.
- **A bare `N-N, N =` literal.** Catches only 15/77 TOC and, worse, **133/187 index** chunks — it is
  an index signal, not a TOC one.

**Also measured: signals 2 and 3 are DEAD on this corpus.** `is_index_heading` fires on **0** chunks
(no `## Index -1` line survives the chunker) and `is_index_layout` fires on **0** (the index does not
come through as pipe rows). Kept — they are book-agnostic and free — but signal 5 is what carries
this corpus. **That is why the whole index passed as content.**

**What is still NOT caught, and is the remaining §E5 gap:** **front-matter prose** — the preface and
publisher's note (60 of 65 front-matter chunks). No keyword, no structural marker, and the page
bounds that used to cover them were zeroed by the re-ingest. A page-band backstop or a preface
signal is the next step; the effect is 2,256 cards (3.0 %) on the old bands.
- **Takes effect on a re-ingest** — `is_content` is written into the payload at ingest, so the
  5,100 existing junk cards are **not** removed by this code change. That is the same re-ingest the
  E1/E2/E3 pass needs, so it rides along.
- **No cluster, no re-ingest to land.** Tests: 4 added to `tests/test_content_filter.py`, all built
  from verbatim corpus rows. `tests/test_content_filter.py` + `tests/test_backmatter_gate.py`:
  **27 passed**.
- **Evidence:** `logs/p1/step10/i39_{filter_signal_probe,boundary_probe,signal_design,fp_inspect,
  verify_filter}.py`; `src/pdf_ingestion/content_filter.py` (`is_toc_layout`, `is_index_density`).

### I40. NEW 2026-10-21 — the B5 RAPTOR verifier silently falls back to the LOCAL embedded Qdrant and returns a confident FAIL against the wrong store

- **What:** `logs/p1/step10/verify_phaseb_raptor.py` builds its client from `cfg.qdrant_host`, and
  falls back to `path=cfg.qdrant_local_path` (`./data/qdrant`) when that is unset. Run without
  `QDRANT_HOST` exported it printed `collection: knowledge_base @ ./data/qdrant`, scanned a **stale
  local dataset** (5,132 points, 84 `raptor_summary` points), compared it against
  `phaseb_before.json` — which had snapshotted the **cluster** (3,796) — and returned
  **`B5 VERDICT: FAIL`** with 86 "missing lane" lines and *"collection grew by 1336 but SQLite has 73
  nodes"*. Every one of those findings was an artifact of pointing at the wrong store.
- **Re-run correctly** (`QDRANT_HOST=10.0.10.65 QDRANT_COLLECTION=knowledge_base_v2`):
  **`B5 VERDICT: PASS`**, exit 0 — `knowledge_base_v2` 3,796 → **3,869 points, grew by exactly 73 =
  the SQLite RAPTOR node count**; `source_type=raptor_summary` 73; chunk points 3,796 unchanged;
  **0** chunk points missing a lane; **0** RAPTOR points with a zero `dense_1024` vector; levels
  {1: 62, 2: 8, 3: 3} within `raptor_max_levels=3`.
- **Why it matters:** the verifier has no guard against the store it is pointed at, and it **prints a
  verdict rather than refusing**. The `B5` header names `knowledge_base_v2` in its docstring while the
  code will happily scan a different collection — so the one line that would have exposed the mistake
  (`collection: … @ ./data/qdrant`) sits above 90 lines of plausible failure detail. This is the same
  class as §D14's false-positive blocker and §I36's stale premise: **a check that reports on the
  wrong object is worse than no check**, because its output looks like evidence. A guard belongs at
  the top: if the resolved target is not the collection the run wrote to, abort.
- **No re-ingest.**
- **Evidence:** `logs/p1/step10/b5_raptor_verify_2026-10-21.log` (both runs, the FAIL first and the
  PASS after the correct env), `logs/p1/step10/phaseb_raptor_verify.json`.

### I41. NEW 2026-10-21 — B4's secondary `Failed:`-row check is contaminated by §I25's own warning text

- **What:** `verify_phaseb_cards.py` keeps a secondary signal, *"`Failed:` rows in the run table"*,
  implemented as a substring test (`if "Failed:" in ln`). §I25's fix emits a warning whose text
  **contains that literal** — *"…must read this count, not the absence of a 'Failed:' row
  (IMPROVEMENTS.md §I25)"*. So on any run where the warning fires, the warning itself is counted as a
  `Failed:` row. Observed: `secondary: 'Failed:' rows in the run table = 1`, and the row printed is
  the warning at `03:53:15.246`.
- **Why it matters:** it cannot flip a PASS to a FAIL (the warning is only emitted when the primary
  counters are already non-zero, which fails the run on their own), so the verdict is unaffected — but
  it inflates a diagnostic and points the reader at the run table when the real signal is the
  counter. **A check whose trigger text contains the string it searches for will always
  self-match.** Either anchor the search on the run table's row shape, or drop the secondary check now
  that the primary counters exist.
- **No re-ingest.**
- **Evidence:** `logs/p1/step10/b4_cards_verify_2026-10-21.log`;
  `src/pdf_ingestion/card_generator.py:540` (the warning), `verify_phaseb_cards.py:86`.

### I42. FIXED 2026-10-21 — `save_cards` could not write for a document that already had cards, so §I27's retry path was unusable (and so is any Phase 2 re-run)

- **What:** retrying the 2 chunks B4 flagged (`formula`×1, `question`×1 — §I25's counters) the
  generator resumed correctly, regenerated the 2 chunks, and then died at the SQLite write:
  ```
  sqlite3.IntegrityError: UNIQUE constraint failed: cards.id
  ```
  **Mechanism, and it is specific.** `card_id` is a fresh `str(uuid.uuid4())`
  (`card_generator.py:220` and 7 more sites), so a *fresh* run can never collide. But the card
  checkpoint (§I27) **stores the `card_id`s it wrote and replays them on resume** — so a resumed run
  re-inserts the ORIGINAL ids. `save_cards` called `_deactivate_cards()` first, which sets
  `is_active = 0` and **leaves the rows in place**, and `cards.id` is the PRIMARY KEY. Deactivate-then-
  insert therefore collides with the very rows it is replacing.
- **Measured:** first attempt — resume line *"3789 of 3791 chunks already done (75628 cards) — 2 with a
  failed card type to retry"*, cards generated, then `IntegrityError` and the run table showed `—`.
  **No data loss:** the write is a single `session.commit()`, so the rollback left **75,645 active
  cards, unchanged** (verified immediately after).
- **Fix:** `save_cards` now **deletes the document's card rows** before inserting. A full-set write
  replaces the set — the generator returns the complete card set for the document, so every existing
  row is superseded — and **nothing in the codebase reads `is_active = 0` cards** (checked: no reader
  filters on it; `get_cards` and both verifiers filter `is_active = 1`).
  ⚠️ This is a **behaviour change** (deactivate → delete) on a shared write path: the deactivated rows
  were a soft-delete audit trail, and they are gone. `_deactivate_cards` is now unused; it is left in
  place rather than deleted.
- **Verified end-to-end:** re-run → *"Removed 75645 existing cards for doc 7ba61432… before
  re-generating"* → *"Saved 75662 cards to SQLite"*, exit 0, and the generator's closing line reads
  **`Generated 75662 cards for 3791 chunks (0 chunks with a failed card type, 0 failed card-type calls,
  0 LLM failures of 0 calls)`** — so B4's 2 failures are closed and the corpus grew by 17 cards (the 2
  chunks had contributed 17 partial cards; regenerating them produced 34).
- **Why it matters — this was a blocker, not a nuisance.** It made §I27's *retry* path (a chunk with a
  failed card type is re-attempted) unusable, and it blocks **every Phase 2 re-run for a document that
  already has cards**: §A1 (regenerate the `question` cards, ~5,048 LLM calls) and §A3 (the
  reduced-volume ablation) both require one. The deployed document `6d55c52b` (82,164 cards) would hit
  the same wall. It also means the failure was **latent since §I27 landed**: the checkpoint feature was
  added and its own recovery path could never have succeeded on a second run.
- **No re-ingest.** The retry itself costs ~16 card calls + the RAPTOR rebuild.
- **Evidence:** `logs/p1/step10/phaseb_retry_2026-10-21.log` (the `IntegrityError`),
  `logs/p1/step10/phaseb_retry2_2026-10-21.log` (the clean re-run),
  `src/pdf_ingestion/store.py` (`save_cards`), `src/pdf_ingestion/card_checkpoint.py:178`.

### I43. FIXED 2026-10-21 (session 2) — the RAPTOR write path APPENDED on a re-run: one Phase 2 re-run duplicated all 73 RAPTOR points in Qdrant

- **What:** `save_raptor_tree` deactivates the document's existing **SQLite** rows and then upserts
  **Qdrant** points with fresh ids, without removing the previous run's points — so re-running Phase 2
  for a document that already has RAPTOR nodes **duplicates them in the vector store** while SQLite
  stays clean. Measured 2026-10-21 after the §I42 retry: `knowledge_base_v2` = **3,942 points**, of
  which **146 carry `source_type=raptor_summary`** against **73** active `raptor_nodes` rows in
  SQLite. 3,796 chunk points (correct) + **146** = 3,942. Before the retry the collection was
  3,869 = 3,796 + 73, i.e. exactly one set. The retry's own log shows the asymmetry precisely:
  ```
  store:save_raptor_tree:1047 - Deactivated 73 existing RAPTOR nodes for doc 7ba61432… before re-generating
  store:save_raptor_tree:1098 - Saved 73 RAPTOR nodes
  ```
  SQLite: 73 deactivated, 73 saved → correct. Qdrant: 73 left behind, 73 added → **146**.
- **Same class as §I42, sibling path — but this half fails SILENTLY.** §I42 was the *cards* write
  (`save_cards` deactivated instead of deleting, so the checkpoint's replayed ids collided —
  `UNIQUE constraint failed`, loud). The RAPTOR path makes the *opposite* mistake on the vector side:
  it never deletes the old points, so there is no collision, no error, and no log line — just
  accumulation. The run reported `RAPTOR nodes 73` and looked entirely clean.
- **Why it matters:** RAPTOR retrieval would see each summary **twice**, so duplicate summaries
  compete for the same slots in the `overview` lane and the map–reduce input is doubled with
  near-identical text. Any Phase 2 re-run — which §A1 and §A3 both require — silently degrades the
  overview lane, and nothing in the run log says so (the run reported `RAPTOR nodes 73`).
- **Fix (DONE 2026-10-21, session 2):** `save_raptor_tree` now **deletes the document's existing
  RAPTOR points** (`_delete_raptor_points()`, a new helper: `Filter(must=[document_id,
  source_type=raptor_summary])`) **before** the SQLite write and the upsert, and **deletes** the
  document's SQLite rows instead of deactivating them — §I42's change, on this path. Both halves are
  now replace-semantics, so a re-run leaves one generation.
  - **Why the Qdrant delete runs first and RAISES rather than logging:** the SQLite write is
    committed below it, so a delete that failed quietly would leave the duplicate in place while the
    run reported success — the exact silent failure this entry records. That is a **deliberate
    departure** from `_delete_colpali_pages` (best-effort, logs a warning), whose read path dedupes
    by page so a failed delete merely degrades to the old behaviour; **nothing downstream dedupes
    RAPTOR points.**
  - **Why deleting the rows is safe:** `build_tree()` takes the chunk texts/ids/embeddings as
    arguments and does **not** read existing rows, so it returns the complete tree either way; and
    nothing reads `is_active = 0` raptor rows (`get_raptor_tree` filters on `is_active`).
    `_deactivate_raptor_nodes` is left in place but is now **uncalled**, marked as superseded.
  - **The 73 already-orphaned points were removed** by `scripts/dedupe_raptor_points.py` (dry-run
    first: it prints every point it would delete with its level and a text preview, and names the
    survivors; `--yes` applies). Survivor rule: a point survives iff its id is the
    `qdrant_point_id` of an **active** `raptor_nodes` row for that document. Dry run said
    **146 → 73 survivors / 73 orphans (levels 62/8/3, i.e. the superseded generation) / 0 active
    nodes missing a point**; applied, and the post-delete count read back **73**.
- **Verified end-to-end.** After the cleanup, **B5 PASSES** (exit 0) — `logs/p1/step10/
  b5_raptor_verify_2026-10-21_post_dedupe.log`: `points now 3869 (before 3796)` /
  `source_type=raptor_summary 73` / `grew by 73 (SQLite nodes: 73)` / `chunk points missing a lane 0`
  / `RAPTOR points with a ZERO dense_1024 vector 0`. An independent re-probe
  (`logs/p1/step10/i43_raptor_dup_probe.py`) reads 3,869 = 3,796 chunks + 73 RAPTOR, **0 orphans**.
  New regression test `tests/test_phase2.py::TestRaptorTree::
  test_raptor_rerun_replaces_points_instead_of_appending` runs Phase 2 twice and asserts the point
  count equals the node count. **It was proven to discriminate** — with the `_delete_raptor_points`
  call replaced by `removed_points = 0` it fails with *"14 RAPTOR points for 7 nodes after two runs
  — the write appended"*. Suite: **439 passed / 4 failed / 6 skipped** (`uv run pytest tests/ -q -m
  "not slow"`, 194 s); the 4 are the pre-existing documented failures (2 × `test_splade.py` missing
  PDF fixture, `test_phase1.py::test_hybrid_search_includes_global`, `test_phase2.py::
  TestPhase1Regression::test_search_still_works_after_phase2`) — **no new failure.**
- **Independent review 2026-10-21** (verifier `openai/gpt-oss-20b` — a different model from the
  author's; pin confirmed live with `hermes config get delegation`). Six questions asked; **5 SOUND,
  1 DEFECT**, final verdict **FAIL**. The defect: *the Qdrant delete happens before the SQLite
  transaction commits, so an upsert that raises leaves the old points gone and the new rows
  unpersisted — an inconsistent store.* **Adjudicated: real, but the ordering is kept — and the
  reviewer's proposed correction is wrong.**
  - The two-store write was **never atomic**; the window existed before this change too, in the
    other direction. So the question is not "is there a failure window" but "what state does it
    leave", and the two candidates are **absence** and **duplication**. This change fails into
    **absence** — which is exactly what B5 and `i43_raptor_dup_probe.py` **count** (`active nodes
    with no point in Qdrant`). The alternative ordering fails into **duplicates**, which is the
    failure that went **unnoticed for a whole run** and is the reason §I43 exists. Absence is
    visible and recoverable; duplication is neither. **Order kept.**
  - The reviewer's corrections do not hold: *"wrap the upsert in try/except that re-throws"* is a
    **no-op** (the exception already propagates), and its own alternative — *"delete after the
    successful upsert"* — re-introduces duplication on failure, which the reviewer itself noted.
  - **What the review did land:** the failure was not **loud**. The upsert is now wrapped so a
    failure logs an ERROR naming the state (`N SQLite nodes, M summary vectors`), the reason, and
    the recovery (`--raptor-only`, then re-run B5) **before re-raising**. Pinned by
    `tests/test_phase2.py::TestRaptorTree::test_raptor_upsert_failure_is_loud_and_leaves_no_points`
    (patches `QdrantClient.upsert` to raise; asserts the raise **and** that **0** RAPTOR points
    survive — i.e. the failure is visible as absence, which is the property the ordering choice
    rests on).
  - Also added, **reported not judged**: a WARNING when `len(points) < len(nodes)` — nodes whose
    embedding is `None` are skipped, so SQLite and Qdrant legitimately differ by that much (B5
    already reports the same gap).
- **No re-ingest** (the points are derived; the orphans were deleted, not rebuilt — the surviving set
  is the one SQLite says is current).
- **⚠️ Non-finding, recorded so it is not chased:** the read-only probe reports the old document
  `6d55c52b` as having **84 active `raptor_nodes` rows with no point in `knowledge_base_v2`**. That
  is **correct, not residue** — the old document is still deployed in the *other* collection
  (`knowledge_base` = 5,135 points = 5,051 chunks + **84** RAPTOR nodes, per the handoff's verified
  facts). The probe only ever counted one collection.
- **Evidence:** `logs/p1/step10/phaseb_retry2_2026-10-21.log`; `logs/p1/step10/i43_raptor_dup_probe
  .{py,json}`; `logs/p1/step10/i43_raptor_rows_probe.py`; `scripts/dedupe_raptor_points.py`;
  `logs/p1/step10/i43_raptor_dedupe.json`; `logs/p1/step10/b5_raptor_verify_2026-10-21_post_dedupe
  .log`; `src/pdf_ingestion/store.py` (`_delete_raptor_points`, `save_raptor_tree`).

### I44. NEW 2026-10-21 — the handoff cited a B5 log as FAIL evidence, but that file contains a PASS from an *earlier* run

- **What:** the handoff's "B5 FAIL" row cited `logs/p1/step10/b5_raptor_verify_2026-10-21.log` as its
  evidence. That file holds a **PASS** — `points now 3869 (before 3796)`, `raptor_summary 73`,
  `grew by 73` — i.e. the run **before** the §I42 retry duplicated the points. The FAIL itself is real
  and was confirmed by direct measurement (3,942 / 146), but **its log is not on disk**: the verifier
  was re-run to a file that already existed, or its output only ever went to the session.
- **Why it matters:** a cited artifact that contradicts the claim it is cited for is worse than no
  citation — a future session that opens it reads PASS and concludes §I43 was never real. It is the
  same class as the lost 2026-10-19 aborted-run log (`.gitignore:68` is `*.log`, so **no `.log` file
  is ever in git**; `>` silently destroys the previous run's log).
- **Rule, already in the traps and now with a second instance:** a verifier's output goes to a
  **new, dated** filename, never to the name an earlier run used; and a handoff cites an artifact
  **only after** reading it back.
- **Evidence:** `logs/p1/step10/b5_raptor_verify_2026-10-21.log` (contains PASS, 3,869) versus the
  measured live state 3,942 / 146; the post-fix run is
  `logs/p1/step10/b5_raptor_verify_2026-10-21_post_dedupe.log`.

### I45. NEW 2026-10-21 (session 6) — the graph rebuild's settings gate asserted a model the build no longer calls

- **What:** `logs/p1/step10/run_graph.sh`'s launch gate exists to *"assert what is actually in force"*.
  It printed `openai_model` — `openai/gpt-oss-20b`, from `.env` — and that was correct until §I23(c)
  made the extractor **per stage** in `config.yaml` under `concept_extraction:`. The graph build calls
  `Qwen/Qwen3-VL-8B-Instruct`. So the gate's own banner named a model the run would never call, and that
  banner is the only place a reader would look to confirm the extractor.
- **Why it matters:** it is §I22's class again — a field whose label says one thing and whose value is
  another. A ~5 h run whose log names the wrong extractor is unrecoverable evidence: the log *is* the
  record, and §I23's "0 failed" and §I22's "15619 concept nodes" are two existing examples of this
  project having had to correct a number *after* trusting a run's own report.
- **Measured:** the gate, extracted verbatim (`sed -n '23,70p'`) and run so the build was not started,
  printed both lines side by side:
  `openai_model : openai/gpt-oss-20b @ http://10.0.10.70:8000` /
  `concept_extraction: Qwen/Qwen3-VL-8B-Instruct   <- what the graph build actually calls`.
- **✅ FIXED 2026-10-21 (session 6), commit `d4a596b`.** The gate now resolves the model the way
  `build_graph` does — `GraphBuilder(settings=c)._extraction_model()`, which reads the
  `concept_extraction` section and falls back to `.env` — prints it, and asserts it is non-empty.
  `GraphBuilder(settings=…)` opens **no** Bolt connection (the driver is lazy), so the gate stays
  side-effect-free. Verifier `openai/gpt-oss-20b`, deleg `deleg_51e615b9`, no defects; it confirmed the
  resolver is the build's own, that the constructor is side-effect-free, and that the assert is not
  vacuous (it fails when the section is emptied).
- ⚠️ **Found in the same read, and deliberately NOT fixed in the script:** `run_graph.sh` redirects
  **nothing**, so launching it as the 2026-10-19 build did — `> logs/p1/step10/graph_build.log` —
  **overwrites** the log §I22 and §I23 cite as their evidence. The rebuild was launched to a new dated
  filename instead. This is §I44's rule a third time (*a run's output goes to a new, dated filename*).
  If the harness is re-run again, give it its own dated `$LOG` — it already computes one and never uses it.
- **No re-ingest. No LLM calls.** A 7-line diff to a bash harness.

### I46. NEW 2026-10-21 (session 6) — Memgraph 2.18.1 cannot express "a node with no incoming edge", so orphan detection must be two-phase and by name

- **What:** clearing a document's graph has to remove the `Concept` nodes that only that document's
  chunks mentioned. The natural Cypher for that is a negative pattern, and **all four forms fail** —
  probed against the live server, not read from a docstring:
  `NOT (k)<-[:MENTIONS]-()` → *"Not yet implemented: atom expression '(k)<-[:MENTIONS]-()'"*;
  `NOT ()-[:MENTIONS]->(k)` → the same, *"atom expression '()-[:MENTIONS]->(k)'"*;
  `NOT EXISTS { MATCH (:Chunk)-[:MENTIONS]->(k) }` → parse error (`mismatched input '{'`);
  `OPTIONAL MATCH (:Chunk)-[:MENTIONS]->(k) AS m … WHERE m IS NULL` → parse error
  (`mismatched input 'AS'`).
- **Why it matters:** `clean_stale_graph.py` already carried this as a *docstring claim* ("Memgraph does
  not implement the `(k)<-[:MENTIONS]-()` atom pattern"), and the new
  `scripts/clear_graph_document.py` would have been written against the elegant one-query form if the
  claim had been taken on faith in the other direction — i.e. assumed *fixed* in 2.18.1. It is not.
  The workable predicate is a positive one: `WHERE NOT (c.document_id IN $ids)` **does** parse.
- **The shape that works:** two phases, by name — read the target's concept names, read the names a
  surviving chunk still mentions, delete the difference.
  ⚠️ And the surviving set must be read as *"names mentioned by chunks whose `document_id` is NOT in the
  target set"*, **not** as *"all mentions minus the target's"*: a concept mentioned by both a doomed
  chunk and a surviving one is in both sets, and subtracting would orphan it and delete a live
  document's concept. Caught by a test, not by review (`tests/test_graph_clear.py`).
- **Evidence:** the four probe failures and the working predicate, `logs/p1/step10/` (probe output in the
  session record; the surviving form is in `scripts/clear_graph_document.py`).
- **No re-ingest. No LLM calls.**

### I47. NEW 2026-10-21 (session 6, found while starting §I12) — §I12's sibling: the GRAPH lane is dead on every multihop query in `evaluate_rag.py`

- **What:** `scripts/evaluate_rag.py` passes the dense-lane **1024d** `q_vec` straight into
  `graph.graph_search(query_vector=q_vec, …)` (`evaluate_rag.py:191-196`). `graph_search` hands it to
  `_find_concepts_scored`, which queries `concept_embeddings` — a **768d** collection (§I12). The query
  is rejected, the `except Exception` in `_find_concepts_scored` swallows it and returns `[]`, and
  `graph_search` then hits its own `if not scored_concepts: return []`. **The graph lane contributes
  nothing.**
- **Measured on the live cluster 2026-10-21 (read-only, one ANN call per arm):**
  `_find_concepts_scored(np.zeros(1024))` →
  `WARNING Concept Qdrant search failed (Unexpected Response: 400 (Bad Request)
  b'{"status":{"error":"Wrong input: Vector dimension error: expected dim: 768, got 1024"}}')`
  → **0 concepts**. The same call with `np.zeros(768)` → **3 concepts**. So the lane is not degraded,
  it is **absent**.
- **Why it matters:** §I12's update already records the dead **DA** lane in this harness ("every
  `evaluate_rag.py` measurement taken after the 2026-10-17 query-side switch has had **one fewer lane
  than it appears to**"). For **multihop** queries it is **two fewer**: DA on every query, and the graph
  lane on every multihop query. It also means §G5's "multihop is nominal" is worse than recorded: in
  the harness the lane does not return anything at all.
- **⚠️ WHICH runs are affected — MEASURED, and the first draft of this entry had it WRONG.** The lane
  died with the **2026-10-17** query-side switch (§E6), not before it. Measured in the §3d
  retrieval-only log (`logs/p1/step10/a3d_retrieval_only.log`): **40** `Concept Qdrant search failed`
  warnings — **exactly one per 40 multihop query** — alongside **167** DA-lane failures. So the affected
  runs are the **post-switch** ones.
  **Step 4's multihop R@20 0.619 is NOT contaminated.** It is real and correct:
  `data/eval_results/p0-9-gold-v2_2026-10-17_0422.md` line 11 reads
  `| multihop | 0.709 | 0.619 | … | 40/40 |`, and that run was **2026-10-16 20:13-21:22 — it predates
  the switch**, so its query vector was the then-current 768d and **both** lanes were live. This is
  §I12's own point about §D12's baseline, applied to the graph lane.
  An earlier draft of this entry asserted the opposite — that 0.619 had been measured with the graph
  lane contributing zero — by inferring it from the code rather than reading a log. That is the
  "a plausible inference is not a measurement" error this register exists to catch: an independent
  reviewer marked the claim **UNVERIFIABLE** rather than accepting it, and the log settled it.
- **Why nothing caught it:** the same reason as the DA lane — the failure is a per-query `WARNING` and
  `preflight.py` checks the collection by **point count**, never by issuing a query. The register
  already asks for a dimension-compatibility probe per named-vector collection; that would catch both.
- **Fix:** the same one §I12 names — move `concept_embeddings` (and `derivative_artifacts`) to
  `dense_dim` in one pass, after which one `q_vec` serves every lane. **No separate fix is needed for
  the graph lane**; that is the point of doing §I12 properly.
- **⚠️ Sequencing hazard, stated so it is not hit:** `concept_embeddings` is **768d on the cluster** and
  Qdrant cannot change a collection's dimension. The moment the concept-name embedder moves to the
  dense lane, a Phase-3 build against the **un-recreated** collection fails at the upsert (loudly — a
  400, not corruption). So the lane move must ship **with** dropping the two collections, and a
  *resumed* in-flight build must not be resumed against the new code. See §I12's fix note.
- **Evidence:** the live probe output above (session record); `scripts/evaluate_rag.py:191-196`;
  `src/pdf_ingestion/graph_builder.py:_find_concepts_scored`. **No re-ingest. No LLM calls.**

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

### I48. NEW 2026-10-22 (found drafting the §I12 dense-lane plan) — two comments outlived their migration, and one of them is load-bearing

- **What:** the §I12 dense-lane move landed in code (`6773022`) but two comments still assert the
  pre-move behaviour. Both are the §I13-adjacent class — a note left beside the code reads as
  authoritative precisely because it is beside the code.
  1. **`src/core/config.py:45`** — `embedding_dim: int = 768  # legacy Nomic dense dim (DA + concept
     collections)`. **False since `6773022`:** `_ensure_da_collection` (`database.py:354`) and
     `_ensure_concept_collection` (`database.py:380`) both create at `cfg.dense_dim`. The parenthetical
     names a lane they no longer use, so the next reader either re-does landed work or designs around
     a constraint that is gone. **Fix:** correct the comment (the field is still the *legacy* Nomic
     dim, but no longer for those two collections).
  2. **`logs/p1/step10/run_graph.sh:14`** — *"`GraphBuilder.build_graph` MERGEs by id, so re-running is
     **idempotent** for this document."* **False for `RELATES_TO`:** the edge write is
     `MERGE … ON MATCH SET r.weight = r.weight + 1`, so a rebuild over an existing graph **doubles
     every edge weight** — the §I43 duplication class, in the graph. This is the **load-bearing** one:
     `run_graph.sh` is the file a future session copies to re-run the build, so the wrong claim is
     exactly what would be acted on. `HANDOFF.md` already records the correct behaviour (item 3's
     `force_graph` note); the script comment was not swept.
- **Why it matters:** both are cheap to fix and both mislead in the direction of doing work twice
  (a redundant re-ingest) or corrupting the graph (a re-run without a clear). The second is worse
  because the file is a run harness, not prose.
- **Cost:** comment edits only. No re-ingest, no LLM calls.
- **Evidence:** `src/core/config.py:45`; `logs/p1/step10/run_graph.sh:14`; the correct behaviour in
  `HANDOFF.md` item 3 and `graph_builder.py`'s edge writes.

### I49. 2026-10-22 — §I12/§I47 EXECUTED and closed, plus three findings the run produced

- **What was done (both lanes, on the cluster, verified):**
  - **Lane A — `derivative_artifacts`.** `index_derivative_artifacts.py --clear --doc-id
    7ba61432-…` → **73,406** vectors at **1024d** (was 81,837 at 768d, a retired card generation
    with 0 id overlap). Verifiers: dim 1024 ✓; `search_da(dense_vec_1024, 'global')` returns **20
    hits** (was **0** — the §I12 discriminator); **8/8** card types (was 5);
    `knowledge_base_v2` 3,869 and `visual_knowledge_base` 1,033 **unchanged**. Log
    `logs/p1/step10/i12_laneA_da_reindex_2026-10-22.log`, verify
    `logs/p1/step10/i12_laneA_verify_2026-10-22.txt`.
  - **Lane B — `concept_embeddings`.** Dropped (19,719 pts @ 768d — it had GROWN from §I12's
    15,276, confirming the "the rebuild only ADDS to it" prediction), graph cleared (verified
    independently 0/0/0/0), then `run_phase3.py --graph-only` rebuilt. Result: **7,427** points at
    **1024d**; `_find_concepts_scored(np.zeros(1024))` returns **8** concepts (was **0** — the §I47
    discriminator). Graph shape **identical to the verified 2026-10-21 rebuild**: 3,533 Chunk /
    907 Page / 7,427 Concept / 14,407 MENTIONS / **22,799 RELATES_TO** / 3,295 PREREQUISITE_OF —
    identical to the pre-clear counts.
  - ⚠️ **CORRECTED the same session — the `RELATES_TO` COUNT is NOT the evidence the clear worked,
    and the first draft of this entry said it was.** The edge write is
    `MERGE (ka)-[r:RELATES_TO]-(kb) ON CREATE SET r.weight = 1 ON MATCH SET r.weight = r.weight + 1`
    (`graph_builder.py:457-462`). `MERGE` **reuses** an existing edge and only increments its
    `weight` — so an UNCLEARED rebuild would leave the count at **22,799 too**, with doubled
    weights. The count is invariant to the bug.
    **The discriminator is the weight distribution.** Measured on the rebuilt graph: `n=22,799`,
    **`min(weight)=1`**, `max=24`, `sum=25,741`, `mean=1.129`, and **21,215 of 22,799 edges
    (93.1 %) sit at weight 1**. A doubled build would have re-matched every edge at least once in
    the second pass, so **`min(weight)` would be 2 and no edge would read 1**. `min(weight) = 1`
    is therefore the real proof; the count matching is a coincidence of the MERGE semantics.
    (Credit: the independent reviewer marked the count-based claim **UNVERIFIABLE** and asked what
    would be needed to be sure — the right challenge, and it was correct.)
  - ✅ **DECISIVE PROOF, and it adjudicates the reviewer's later REFUTED — which is VOID.** A second,
    focused review of the corrected (weight-based) claim returned **REFUTED**, on the reasoning that
    "1,029 edges with weight 2 … contradicts the claim that no edge weight was doubled". **That
    misreads what weight 2 means.** Within a SINGLE build an edge's weight is the number of chunks in
    which its two concepts co-occur — so a pair co-occurring in exactly two chunks *should* read 2.
    Measured directly on the graph, for every sampled edge:
    `weight == count(DISTINCT chunks mentioning BOTH endpoints)` —
    `w=24 ⟺ 24 chunks` ('Angular Momentum'/'Torque'), `w=22 ⟺ 22` (\"Newton's Second Law\"/'Acceleration'),
    `w=2 ⟺ 2` (4 samples), `w=1 ⟺ 1` (4 samples); **14 of 14 match, 0 mismatch**.
    If a second pass had run over an uncleared graph, every edge would read `co_occurrence + 1`, and
    **no edge could read 1** (the 21,215 weight-1 edges alone settle it). The identity holding
    exactly means build #2 was built fresh from an empty graph — the clear worked.
    **Adjudication: the weight-based claim is CONFIRMED; the reviewer's REFUTED verdict is void, on
    a false premise.** Second instance this session of a reviewer reaching the right *domain* and the
    wrong *reasoning* (the first was C4) — the register's standing rule holds: a verifier buys
    consistency-checking, not correctness. (The `45598` an undirected `MATCH` returns is 2 × 22,799 —
    each edge seen from both endpoints, not a real count.) Log `…/i12_laneB_rebuild_2026-10-22.log`, verify `…/i12_laneB_verify_2026-10-22.txt`.
  - **Preflight before → after:** `derivative_artifacts.dim` and `concept_embeddings.dim` both
    **FAIL → PASS**; **2 BLOCKER(S) → All checks passed**. Evidence
    `logs/p1/step10/i12_preflight_{before,after}_2026-10-22.txt`.
- **Finding 1 — THE STORE TRAP, and it would have silently done nothing.** `.env` leaves
  `QDRANT_HOST` **blank**, so `get_settings()` resolves to the **local embedded** Qdrant
  (`./data/qdrant`), NOT the cluster. The two stores hold different (and differently stale)
  generations: locally `concept_embeddings` had **0** points and `derivative_artifacts` 81,818; on
  the cluster they were **19,719** and **81,837**. Every command in the §I12 plan therefore needs
  `QDRANT_HOST=10.0.10.65 QDRANT_COLLECTION=knowledge_base_v2`, and the **dry-run must be read**
  before applying. Registering this because a §I12 run without the override would have dropped the
  local collections, recreated them, and reported success while the cluster lanes stayed dead.
- **Finding 2 — the §G3 lever RE-MEASURED on the rebuilt graph, and it MOVED (§I30 is a before-arm).**
  `probe_g3_lever.py` on doc `7ba61432`: **1,059** merge groups (was 1,186) covering **2,451**
  concepts = **33.0 %** of the 7,427-name vocabulary (was 34.4 % of 7,834); **3** groups gain
  nothing (was 0); `names_skipped_empty_key = 0` (the single-letter `'s'` concept is gone — §I31
  trap 3b no longer fires here). The top group is now **`temperature`** (union 100 / best 52 /
  **+48**), not `force`. **§I30's numbers must not be quoted again**; G3's review budget and its
  verifier 4 anchor follow the re-measured values.
- **Finding 3 — the §G2 gate RE-RUN on the rebuilt graph, and it PASSES (the before-arm is
  superseded).** `g2_leiden_gate.py`: res 1.0 **leiden Q=0.783332** vs rewired null **0.394314** →
  surplus **+0.389018** (ratio 1.9866), n=338, **all communities connected**; Louvain
  **disconnected** at res 0.5 (reproducing §I33). Hierarchy nesting 0.9349 (0.5→1.0) / 0.8779
  (1.0→2.0). Artifact `logs/p1/step10/g2_leiden_gate_2026-10-22_post_rebuild.json`. **§G2 is
  un-gated and may proceed.**
- **Also noted:** `g2_leiden_gate.py`'s `ONE_SIDED_CAVEAT` string still says the graph "carries TOC
  concepts because the Phase 3 build does not apply the E5 content filter (§I21)" — **false since
  the rebuild**; the caveat should be updated or dropped. And `index_derivative_artifacts.py`'s
  default `--batch 32` runs at ~39 texts/s against ~50 texts/s at batch 512 (measured), so the DA
  re-index is ~25 % slower than it needs to be.
- **Cost:** no Phase-1 re-ingest, no LLM extraction (checkpoint reused all 3,533). Wall: Lane A
  ~40 min (73,406 embeddings), Lane B ~45 min (7,427 concept-name embeddings, sequential at
  ~0.33 s/call — the embed loop is one call per name, a known inefficiency).
- **New code:** `scripts/reset_derived_collections.py` (dry-run default, allowlist refuses
  `knowledge_base`/`visual_knowledge_base`, `--yes` to apply) + `tests/test_reset_derived_collections.py`
  (10 tests; proven to discriminate — breaking the allowlist fails 4).

---

### I50. 2026-10-22 — §G3 and §G2 execute to their apply lines, and four defects the runs exposed

**Where §G3 stands.** The merge is BUILT, dry-run-verified, and **NOT yet applied**.
`scripts/resolve_concepts.py --doc-id 7ba61432-…` (dry run is the default) reports **1,053 merge
groups / 1,362 aliases**, taking the concept vocabulary **7,427 → 6,065**, with **1,362**
`concept_embeddings` points to delete (V6). ⚠️ Needs
`QDRANT_HOST=10.0.10.65 QDRANT_COLLECTION=knowledge_base_v2`, or the V6 sync targets the **LOCAL
embedded** store and deletes nothing (§I49 Finding 1).

**Finding 1 — V7's by-eye read caught a defect in the T1 formula detector, and it was the author's.**
`is_formula_like()` counted the ASCII hyphen as a formula character, so **46 groups** were flagged
"formula-bearing" and never merged. Reading the flagged list showed **~40 were pure typography**:
`half life` / `Half-life` / `half-life` / `Half-Life`; `x ray` / `X-rays` / `x-rays`; `space time` /
`Space-Time`; `work energy theorem` / `Work-Energy Theorem`. None is a formula. With the hyphen
removed from `_FORMULA_CHARS`, **6 groups** remain flagged and all six are genuinely formula-shaped:
`A = B` / `A = -B`; `Eq. (49.16)…`; `Equation (50.4)…`; `formula (43.15)…`; `Lens Formula (27.16)`;
`Square root of 2` — every one caught by the digit rule or the operator set, so the hyphen guarded
nothing. **The count is the proof:** mergeable groups go **1,013 → 1,053**, and §I49's T1-unaware
probe measured **1,059**; 1,059 − 6 flagged = **1,053** exactly. Pinned both directions by
`test_trap1_hyphenated_compounds_are_spelling_variants_not_formulas` and
`test_trap1_real_formulas_are_still_flagged`.
⚠️ A T1 false positive does not corrupt the graph — it silently **skips merges**, and no count in the
merge report shows it. V7 is the only check that can see this.

**Finding 2 — V3's before-arm, RE-MEASURED on the rebuilt graph and the dense lane.**
`logs/p1/step10/g3_query_side_baseline_2026-10-22.json`: 200 queries, **0 embed errors**, wall 86 s,
**2,176** chunks matching ≥1 of a query's 8 concepts; histogram 1 → 2,038 · 2 → 134 · 3 → 4;
**mean 1.0653, share≥2 0.0634**, share≥3 0.0018, exactly-1 0.9366, verdict **NON-DEGENERATE**;
top-5 median of medians **1.0** (189/200), `graph_search` parity **200/200**.
⚠️ **§I32's 97.86 %-at-1 is superseded as a CONFIGURATION, not as a finding** — it was measured on
the old graph through the 768d lane. The new number is the correct before-arm for the merge because
it is taken under the configuration the after-arm will use. **Room to move:** share≥2 went
0.0194 → **0.0634** (~3× the discriminating room) and the top-5 median still sits at **1.0**, so
V3's endpoint is not saturated and CAN rise.

**Finding 3 — the V3 probe was measuring a dead lane and would have written an all-zeros artifact.**
It embedded with the 768d legacy Nomic model and asserted `cfg.embedding_dim`. §I49 moved
`concept_embeddings` to the **1024d dense lane**, so every ANN query would be rejected,
`_find_concepts_scored` would return `[]` for all 200 queries, and the artifact would have looked
like a measurement. It now uses `get_query_vector` (the production query path) and asserts
`cfg.dense_dim`. **A probe pinned to a lane that has since moved measures nothing — and says so only
if you are lucky.**

**Finding 4 — §G2 was partitioning a DIFFERENT graph than the gate that released it, twice over.**
The gate reported Q=0.783332 at resolution 1.0 on 7,398 nodes; the builder reported 0.7786. Two
independent causes, both settled by measurement:
  (a) **isolated concepts.** `read_concept_graph` added every concept the document mentions, so the
      **29** concepts with no `RELATES_TO` edge became nodes: 7,427 vs the gate's 7,398.
  (b) **node INSERTION ORDER.** With the node set fixed, Q still differed. `nx_to_igraph` indexes
      vertices by `list(g.nodes())` — insertion order — and igraph's seeded RNG draws from that
      indexing, so the SAME graph read two ways gives two different partitions. Measured
      (`q_order_probe.py`): the gate's row order → **Q=0.783332, n=338** (exact reproduction);
      sorted by (a,b) → 0.776639, n=342; reversed → 0.783601, n=342 — same 7,398 nodes and 22,799
      edges in all three.
  Fix: `read_concept_graph` copies the gate's Cypher **verbatim** and `nesting` uses the gate's own
  definition (fraction of fine communities lying *wholly* inside one coarse community) rather than a
  member-weighted variant. The builder now reproduces the gate **exactly**: Q 0.7412 / 0.7833 /
  0.8344 and nesting 0.8779 / 0.9349.
  ⚠️ **The general trap: "the same graph" is not enough for a seeded partitioner — the row order is
  part of the input.** A gate and the thing it releases must read the store the same way, and the
  agreement must be checked by reproducing the gate's number, not by matching node counts. The 29
  isolates are counted, not dropped (`read_concept_names`).

**Also fixed:** §G2's CLI dry run passed an empty text provider, so every community was "skipped"
and it reported **0 prompt chars** — it did not deliver the "see the cost before you spend it" its
own docstring promises. It now reads full text (a local SQLite read, no LLM) and reports
**2,761,845** prompt chars for the leaf level with **0** LLM calls.

**Suite:** 572 pass / 4 fail / 6 skip — the same 4 pre-existing failures.

---

### I51. 2026-10-22 — §G3 EXECUTED: the merge is applied and structurally verified; its endpoint is null, and the endpoint is inert

**Owner disposition (2026-10-22):** keep the merge; record §G3 as **measured-and-null on its
pre-registered median**; proceed to §G2.

**Applied.** `scripts/resolve_concepts.py --doc-id 7ba61432-… --yes` on the live graph — 1,053 merge
groups, 1,362 aliases. The before-state was captured to `g3_state_before.json` FIRST, so the
verifiers could be asserted **against** it rather than eyeballed. Journal
`g3_merge_journal_2026-10-22.jsonl` (revert with `entity_resolution.revert_merges`).

| | before | after |
|---|---|---|
| Concept | 7,427 | **6,065** |
| MENTIONS | 14,407 | 14,405 |
| RELATES_TO | 22,799 | 21,670 |
| PREREQUISITE_OF | 3,295 | 3,161 |
| `concept_embeddings` | 7,427 | **6,065** |

**V1 PASS** — 1,362 names merged away, 1,362 survive as aliases, **0 lost**.
**V2 PASS** — the after-state **exactly equals** the remapped before-state for all three edge types
(`g3_verify_merge.py`); the deltas are precisely the collapsed duplicates (MENTIONS 2, RELATES_TO
1,129, PREREQUISITE_OF 134). ⚠️ The first version of this check only printed the deltas and asserted
they were non-negative — the plan explicitly forbids that ("a bare '> 0' passes a merge that destroyed
90 % of the graph"). The strengthened form remaps every before-state edge through the alias map, drops
the self-loops a merge creates, and demands **set equality**.
**V4 PASS** — all 1,053 survivors' chunk counts equal the union of their merged members.
**V6 PASS** (`g3_verify_v6.py`) — 0 of 1,362 alias points remain; 0 of 1,053 canonical points missing;
`_find_concepts_scored` still returns 8 (the §I47 discriminator); **0** ANN points name a concept
absent from the graph.

**V3 — the endpoint, and it did not move:**

| | before | after |
|---|---|---|
| chunks matching ≥2 concepts | 138 (share 0.0634) | **158 (0.0641)** |
| mean matched_concepts | 1.0653 | 1.0662 |
| queries whose top-5 median is 2 | 11 | **14** |
| **median of the retrieved top-5** | **1.0** | **1.0** |

V3 has two clauses and only the first moved. The candidate pool also grew 2,176 → 2,464.

⚠️ **THE ENDPOINT IS INERT, WHICH MAKES THE NULL UNINFORMATIVE RATHER THAN NEGATIVE.** For the median
to leave 1.0, **more than half** of the 200 queries need a top-5 median ≥ 2; **14** do. The
pre-registered endpoint cannot move at this granularity — the §G1 ablation's defect class again,
where a cut larger than the candidate pool made both arms identical by construction. **Do not read
this null as "entity resolution does not help retrieval"; it is a null about a metric that could not
have moved.** Re-pre-registering a sensitive endpoint (the ≥2-chunk count, or share≥2) is an OWNER
decision and was explicitly NOT taken.

**Cost:** ~2 min (≈9,500 Cypher statements + 1,362 Qdrant point deletes). No LLM.

---

### I52. 2026-10-22 — §G2's summariser is a DIFFERENT MODEL from the graph build's extractor, and its prompt budget was sized from the wrong one

**What was found.** `community_summaries._default_llm` calls `src.core.llm.call_llm`, and `call_llm`
posts **`cfg.openai_model`** — `.env` sets that to **`openai/gpt-oss-20b`**. The Phase 3 graph build's
concept extraction uses a *different* model (`Qwen/Qwen3-VL-8B-Instruct`, `config.yaml:concept_extraction`).
The two have very different contexts, and the §G2 pre-flight measured the wrong one:

| model | who runs it | `max_model_len` | 60k chars | 265k chars |
|---|---|---|---|---|
| `Qwen/Qwen3-VL-8B-Instruct` | graph build's extractor | **15,000** | 13,814 tok ✓ | **HTTP 400** |
| `openai/gpt-oss-20b` | **§G2's summariser** (`call_llm`) | **131,072** | 13,359 tok, 3.0 s | **58,530 tok, 9.7 s, `finish_reason=stop`, 964-char answer** |

Both read from `/v1/models`; both tokenise real physics text at **4.49-4.53 chars/token**.

**The consequence, had it not been caught.** The first budget was set at 50,000 chars from the Qwen
model's 15,000-token context, which triggered a design change (map-reduce batching, owner-approved)
whose *premise was false*: on the model §G2 actually runs, the largest leaf prompt — **273,470 chars
≈ 60k tokens** — fits in one call with ~43k tokens to spare. Re-measured and corrected the same
session; budget is now **400,000 chars** (`DEFAULT_MAX_PROMPT_CHARS`), at which **zero** communities
of this corpus batch. The map-reduce machinery is kept as the safety net.

**The §G2 leaf prompts are badly skewed** (`g2_prompt_size_probe.py`, 218 leaves, 6,041 nodes):

| threshold | leaves over it | share of leaves | chars in them | share of all chars |
|---|---|---|---|---|
| > 10,000 chars | 36 | 16.5 % | 3,084,209 | **95.7 %** |
| > 60,000 chars | 18 | 8.3 % | 2,455,768 | 76.2 % |
| > 120,000 chars | 9 | 4.1 % | 1,681,830 | 52.2 % |

**178 of 218 leaves are ≤ 2,000 chars (~1-2 chunks) and hold 4.3 % of the text.** So "one summary per
leaf community" produces a handful of enormous communities and ~178 micro-summaries. That is a §G2
result to read V3/V5 against, not a defect of the code — but it means the summary tree's information
density is concentrated in ~20 nodes.

**Two silent failures were found on the same path, both fixed with discriminating tests:**

1. **A failed LLM call wrote an EMPTY summary and still counted as a call.** `call_llm` returns `""`
   on failure rather than raising (§I24's contract), and the old code stored that `""` and incremented
   the cost ledger — so a run in which *every* call failed would report a full ledger, exit 0, and
   write an artifact of empty summaries. **This is §I25's class exactly** (a total loss that reads as a
   success). Now counted (`empty_returns`) and the CLI exits non-zero when it is non-zero; the count,
   not the absence of an exception, is the run's exit criterion.
2. **The dry run reported 403 parent communities as "skipped (no source material)" — they are
   PARENTS.** A dry run never generates child summaries, so every parent's body is empty *by
   construction*, and the old counter folded that into the "no source" bucket. The pre-flight cost
   report therefore read as though 403 communities would never be summarised, while understating the
   run by exactly those 403 calls. Now counted separately (`deferred_parents`).

**Also fixed, same path:** the dry run could not estimate the parent levels' cost at all (a parent's
prompt is built from summaries that do not exist yet) and now says so explicitly; and with batching,
one community is no longer one call, so the dry run computes and reports the leaf-level map-call
count it would actually issue (`planned_leaf_map_calls`).

**THE GENERAL TRAP — measure the model THE PHASE RUNS, not the one another phase runs.** A repo with
per-stage model config (`concept_extraction.model`, `judge_model`, `openai_model`) has several models
in play at once, and "the extractor is Qwen" is true of one phase and false of the next. Two more
traps found measuring it:

- **A filler-text token ratio is ~40 % optimistic.** Repeated English filler measured 6.23 chars/token;
  real physics chunk text measures 4.49-4.53. A budget sized from filler over-runs the context by 40 %.
- **`/v1/models` lists models the gateway will not serve at the context you assume** — it lists six
  ids, of which the two the project uses have contexts of 131,072 and 15,000. Read
  `max_model_len` per id; never carry one model's limit to another.

**Evidence:** `logs/p1/step10/g2_prompt_size_probe.{py,json}`, `g2_summariser_model_probe.{py,json}`,
`g2_token_ratio_probe.{py,json}`, `g2_dryrun_2026-10-22.{txt,json}`; tests in
`tests/test_community_summaries.py` (13, each new guard proven to fail when reverted).
**Register this against:** §I23(c) (which model the extraction phase runs), §I24 (the `""` failure
contract), §I25 (the total-loss-that-reads-as-success class).

---

### I53. 2026-10-22 — §G2 BUILT AND VERIFIED (V1/V2/V4/V6 PASS), and V3 finds the leaf partition is a two-population mixture, not a topic hierarchy

**Built.** `bash logs/p1/step10/run_g2_summaries.sh` (new harness; asserts the Qdrant override and
prints the summariser's real identity into the log). Artifact
`logs/p1/step10/g2_summaries_2026-10-22.json`, log `…/g2_summaries_2026-10-22.log`.

| | |
|---|---|
| wall | **19 min 42 s** (16:48:37 → 17:08:19) |
| LLM calls | **597** — level 0 (res 2.0) **218** · level 1 (res 1.0) **198** · level 2 (res 0.5) **181** |
| `empty_returns` | **0** (the run's exit criterion, §I52) |
| batched / truncated | **0 / 0** (budget 400,000 chars; no community exceeded it) |
| skipped (no source) | **24** (4 + 20 parents with no children) |
| summaries | **597 non-empty** of 621 entries; lengths min 178 / p50 554 / max 1,555 chars |
| model | `openai/gpt-oss-20b` (the summariser — NOT the graph build's Qwen extractor, §I52) |

**V1 (gate) PASS** — re-run on the post-§G3 merged graph: res 0.5 Q=0.740124 / res 1.0 **0.687197** /
res 2.0 0.634980, against rewired nulls 0.506882 / **0.349002** / 0.311354 → surplus **+0.338195**
(ratio 1.969) at 1.0, n=202, **Leiden connected at every resolution**, Louvain **disconnected** at
res 1.0 (reproducing §I33 on the merged graph). Nesting 0.8911 (0.5→1.0) / 0.8394 (1.0→2.0).
Artifact `logs/p1/step10/g2_leiden_gate_2026-10-22_post_merge.json`. ⚠️ The gate's `ONE_SIDED_CAVEAT`
still claimed the §I21 TOC confound applied — **false since the rebuild**; §I49 flagged it and it is
now corrected in the script.
**V1r PASS** — the builder reproduces the gate's Q at all three resolutions and both nesting values
**exactly** (the §I50 Finding 4 invariant, re-checked after the merge).

**V2 PASS** — every community internally connected at all three resolutions (218 / 202 / 201
communities, 0 disconnected).

**V4 PASS** — ledger complete and **reproducible**: a re-run with a recording fake LLM issues
**597** calls, matching the artifact's `total_calls` and its per-level breakdown, with
`single_calls + map_calls + reduce_calls == total_calls`. 0 empty returns.

**V6 PASS** — 25 sampled leaf prompts are **byte-verbatim** the prompt the builder sent for that
community, built from the full SQLite text; 2,145 chunks of the corpus are longer than the graph's
500-char `chunk_text` stub, and every such chunk appears **in full**. So no summary is a summary of a
stub.

Verifier: `logs/p1/step10/g2_verify_summaries.py` → `…/g2_verify_summaries_2026-10-22.txt`,
**ALL CHECKS PASSED** (14 checks). It re-reads the graph and re-derives everything with a fake LLM —
it never reads the artifact's own claims back to itself.

**V3 — the by-eye read (PASS on quality, and it finds the granularity defect).** Sampled largest 5 /
middle 5 / smallest 5 of the 218 leaves → `…/g2_v3_by_eye_sample_2026-10-22.txt`. **The summaries
themselves are good**: factual, terse, source-grounded, correct LaTeX, nothing invented. **No phantom
clusters.** But the *partition* is a two-population mixture:

| leaf concepts | leaves | share | prompt chars held |
|---|---|---|---|
| ≤ 5 | **166** | **76.1 %** | ~4 % |
| > 10 | 41 | 18.8 % | 96 % |
| > 50 | 34 | 15.6 % | 95 % |
| > 200 | 8 | 3.7 % | 46 % |

min 2 · p50 **4** · p75 5 · **p90 108** · max 336 concepts per leaf.

So the "finest" resolution (2.0 — fixed by the syllabus spec) does **not** resolve the graph's dense
core: it yields ~166 micro-communities of one passage each, plus ~34 grab-bags whose summaries read
as *"most of mechanics"* / *"thermodynamics + kinetic theory + quantum statistics"* / *"waves +
interference + polarization + Fourier"*. They are accurate but they are not topic units, and several
overlap heavily. **The community hierarchy therefore has no middle granularity** — which is exactly
the level GraphRAG's community summaries exist to provide, and it is what V5's ablation must be read
against. Read V3's finding together with §I52's prompt-size table: the two are the same distribution
seen from two sides.

**A monitoring gap, registered not fixed:** the build logs **nothing per call** and has **no
checkpoint** — 597 sequential LLM calls, and an abort at call 596 loses all of it. §I23's lesson
(a long LLM phase needs a checkpoint and a rate signal) applies to §G2 as written; the run happened to
complete in 20 min, but nothing in the log could have distinguished "healthy and slow" from "stalled".
**✅ FIXED 2026-10-22 — see §I53a.**

**Cost:** 597 LLM calls, 19 min 42 s wall. No Phase-1 re-ingest, no graph writes, no Qdrant writes —
the summaries are a JSON artifact and are **not yet wired into retrieval**.

---

### I54. 2026-10-22 — the §G2 review: a reviewer without the artifact is no verdict, and it still found a real defect once it had one

**Three dispatches, one verdict.** The standing rule is "a step with no verifier is not done". What it
does not say, and what cost three rounds here, is that **a reviewer is only as good as what you hand
it**:

| # | what the prompt contained | result |
|---|---|---|
| 1 (`deleg_30f94c21`) | the *description* of the change, not the diff | **UNVERIFIABLE × 10**, 11 s, "no code is provided" |
| 2 (`deleg_62b487a2`) | the full diff, but **not the C1-C10 claim definitions** | **UNVERIFIABLE × 10**, 25 s, "No description of C1 in the provided context" |
| 3 (`deleg_1a6fc8cb`) | the claims first, then the diff | **8 verdicts + 6 defects**, 50 s — and one of them is real |

Both failed rounds are the **same defect shape this project keeps finding in code**: a process that
returns a well-formed result, is green-ish, and tested nothing. The difference is that here the
process is a reviewer, so the failure is *silent by construction* — "UNVERIFIABLE ×10" is easy to
skim as a cautious pass. **It is not a pass. It is no verdict, and the step stays uncommitted.**

⚠️ **The rule, now explicit:** embed **both** the artifact under review **and** the list of claims —
and if the reviewer's answer says it could not see the thing, stop and re-dispatch; do not
re-interpret its output as a weaker verdict. A second-order tell: a review that takes ~10-25 s on a
600-line diff has not read it.

**What the real review found — and it was a genuine defect.** `planned_leaf_map_calls` counted the
leaf level's **prompts** (single-batch communities included) but the test compared it to a real run's
`map_calls`, which **excludes** them. On the live corpus the plan reads **218** and `map_calls` reads
**0** (every leaf is single-batch at the 400,000-char budget) — so the assertion passed **only because
the fixture batched every community**. A fixture-dependent test that would have failed on the data it
was written for. Fixed: the field is `planned_leaf_prompts`, a real run exposes the matching
`leaf_prompt_calls`, and two tests pin the semantics in **both** regimes (all-batch and no-batch).

⚠️ **Fixing it exposed a THIRD wrong comparison of the same quantity.** The obvious replacement,
`calls_by_level[0]`, is also wrong: it **includes the leaf reduce calls** (in the fixture, 14 = 12 map
+ 2 reduce). So the quantity has exactly one right counterpart, and the two wrong ones were both
tried here. `planned_leaf_prompts == leaf_prompt_calls` is now the assertion, and it holds in both
regimes because it is level-scoped.

**The reviewer's "blocker" was false — but it pointed at a real guard.** It claimed
`_summarise_with_batching` can loop forever when a reduce step returns empty for every group. It
cannot: `merged` empty ⇒ `parts` empty ⇒ `len(parts) > 1` is False ⇒ the loop exits and the community
is summarised as `""` with every failure counted. **But the guard it doubted — `if len(merged) >=
len(parts): break` — is load-bearing for a different input:** a reduce that returns a summary at least
as long as the budget makes `_batch_texts` emit one full-room group per part, so the merge does not
shrink and `parts = merged` would spin at the same length forever. **Proved mechanically, not argued:**
removing the guard makes the new termination test **hang** (`timeout 25` → exit 124); restoring it
passes. So a false finding still bought a real test.

**Three of the five defects volunteered by the code-less second round were FALSE** (checked against
the source): "reduce appends empty strings" (both MAP and REDUCE filter on `text.strip()`);
"`prompt_chars` over-reports" (`_call` records the real `len(prompt)`); "calls_by_level is incremented
for a source-less community" (that branch `continue`s first). Two were real-but-benign (a conservative
over-count in `_batch_texts` that guarantees the budget is never exceeded; the dry-run-only `planned_*`
fields). **The general lesson: a reviewer that says it lacked the artifact is no verdict, and any
findings it volunteers anyway must be checked against the code — not accepted, and not dismissed
either, because the same round that invented three defects also, with the code, found the real one.**

**Register against:** the "verifier at every step" rule (`HANDOFF.md` → Session hygiene, `README.md`),
§I38 (a reviewer can destroy what it reviews), §I44 (evidence that is not on disk is not evidence).

---

### I53a. 2026-10-22 — the §G2 build is now checkpointed and logs per call (the §I53 monitoring gap, closed)

**What was built.** NEW `src/pdf_ingestion/summary_checkpoint.py` (side-car JSONL), wired into
`community_summaries.summarize_communities` (`checkpoint=`, `on_call=`) and
`scripts/build_community_summaries.py` (`--no-resume`, `--cache-dir`, `--progress-every`,
`--progress-seconds`). `data/summary_cache/` is gitignored alongside the other three caches.

**The key is the RUN, not its inputs:** `(document, model, seed, resolutions, prompt budget, prompt
digests)`. The model is `cfg.openai_model` — the **summariser**, which §I52 established is a
different model from the graph build's extractor; the seed must match `g2_leiden_gate.py`'s or the
communities are not the ones the gate approved (§I50 Finding 4).

**Why an input digest and not just `(level, community)`.** A parent's input is its children's
**summaries**, so a child that was re-attempted and now summarises differently must invalidate its
parent. Each entry stores the digest of the exact material it was built from (a leaf's ordered
passages, a parent's ordered child summaries) and is reused only on a match. Without that, a resume
after a partial outage would keep stale parent summaries over fresh children — §I25's class, one
level up.

**A community whose calls returned empty is `ok=False` and is re-attempted**, never counted as done
(`call_llm` returns `""` on failure, §I24). A community with genuinely no source material makes no
call and is **not recorded at all** — the safe direction, since a transiently empty read is then
re-read rather than frozen.

**Per-call logging.** `on_call(kind, where, prompt_chars, elapsed, empty)` fires once per LLM call
(single/map/reduce), and the CLI prints a line per call plus a rolling `N call(s) in M min = R
calls/min`. This is §I23's lesson made concrete: the 2026-10-22 build's log could not distinguish
"healthy and slow" from "stalled", and §I23 had already measured an 18-minute 58× stall that a
single-request liveness probe read as all-clear.

**Tests:** `tests/test_summary_checkpoint.py` (15) + 3 progress tests in
`tests/test_community_summaries.py`. **Four load-bearing guards were proven to discriminate by
mutation** — recording a failed summary as done, ignoring the input digest in `lookup`, dropping the
per-call report, and not checking the header's model each fail their own test; the pristine tree
passes 35.

**✅ INDEPENDENT VERIFIER RAN 2026-10-22 (session 10) — `openai/gpt-oss-20b`, `deleg_dd8d2c29`,
`status=completed`.** Verdict **8/9 CONFIRMED** (C1 `run_key` identity, C2 the digest+`ok` gate, C3
`ok=bool(summary.strip())`, C4 the four guards can fail, C5 side-car, C6 dry run writes nothing, C7
torn-line recovery, C8 strictly additive). **C9 — the "599 passed / 4 failed / 6 skipped" suite count —
is `unverified`, and correctly so:** the reviewer was handed the §I53a diff, not the whole suite, and
said so. That count is measured separately (session 10: **606 / 4 pre-existing / 6**, the +7 being
§I55's new tests). **No silent wrong answer was found.**

⚠️ **The verdict was cheap (3 API calls, 33 s) and its cited LINE NUMBERS are fabricated** — it cites
"lines 544–560" of a 292-line file and "lines 1574–1580" of a 549-line one, i.e. offsets into the
concatenated review pack rather than into the sources. So it was **not banked**: the five test names
it cited were checked to exist, and **all four guards were re-proven by mutation on the author's own
run** — (a) `ok=bool(summary.strip())` → `ok=True` fails 1 test; (b) the digest check → `if False:`
fails 2; (c) the `on_call` report → `if False:` fails 3; (d) dropping the header's `model` check fails
1. Every failure was on its **own assertion**, not a collection error, and the tree was restored
byte-identical (`diff` → 0). **The confirmation therefore rests on that mechanical evidence, not on
the reviewer's agreement** — the reviewer's contribution is that it read the same code and found no
counter-example.

**Committed with the verdict, and the `[verified]` prefix is warranted**: the item is complete as
scoped (module + wiring + 18 tests + mutation proof), and the one unverified claim is a suite-wide
count outside the diff, measured independently above.

**Cost:** local code only; no LLM calls, no cluster work. The fix is what makes the next §G2-scale
LLM phase (V5, or a re-run at another resolution) restartable instead of all-or-nothing.

---

### I55. 2026-10-22 — the cross-encoder reranker swallows its own failures, and `evaluate_rag.py` reports `reranker.enabled=true` regardless

**What was found.** `ClusterCrossEncoderReranker.rerank` (`reranker.py:131-141`) catches **every**
exception, logs `RERANKER DISABLED — … Returning UNRANKED results in original retrieval order`, and
returns `chunks[:top_k]`. Nothing counts it, nothing surfaces it, and the eval artifact records
`reranker.enabled = true`. **This is §I25's class exactly** — a failure that reads as a success — and
it means a reported R@20 / NDCG@20 can be computed on **unranked** output with no trace in the
artifact.

**Measured, not inferred** (`logs/p1/step10/reranker_payload_probe.py`, which builds the SAME pool
`search_with_das` would hand the reranker and POSTs the SAME payload straight to the endpoint):

| | |
|---|---|
| queries whose pool the endpoint **rejects** | **1 / 133 (0.8 %)** — `gold-004`, HTTP **500** |
| accepted | median **59,651** total chars / **100** docs |
| rejected | **50,773** total chars / **100** docs — **smaller** than many accepted pools |

**The trigger is content token-density, not payload size.** Synthetic isolation: 100 docs × 2,500
chars of plain ASCII, of unicode, of bare backslashes and of digits all return **200**; the same
count of **real LaTeX/unicode physics text** returns **500** from ~40 docs upward, and **20** docs
of the same text returns 200. A single 60,000-char document returns **400** (a second, distinct
limit). So a character-count budget is the wrong instrument — the same trap §I52 recorded for
token ratios (filler measures 6.23 chars/token, real physics 4.49-4.53).

**Why it matters more than its rate suggests.** 0.8 % is small in aggregate, but the failure is
**per-query deterministic** (the same query fails on every arm and every run), so it does not average
out within a query — and any measurement that depends on the reranked **order** (this project's
R@20/NDCG endpoints, the §2 reranker ablation, and the §G1 PPR ablation's ranking comparison) carries
that contamination silently. It also made the DA ablation's top-20 comparison **inert by
construction** for that query: the DA lane appends its candidates *last* in the pool, so an unranked
top-20 is always the dense head.

**Also measured while isolating it:** `_batch_texts`-style char budgets cannot predict rejection;
`max_doc_chars` does not separate accepted (max 2,345) from rejected (2,949) cleanly either — the
server-side rule is **not determined** and is recorded as such rather than guessed.

**✅ FIXED 2026-10-22 (session 10) — the swallow is COUNTED, surfaced, and the run refuses to
certify a reranked metric.** Three parts, all in the one change:

- `src/pdf_ingestion/reranker.py` — `ClusterCrossEncoderReranker` counts every swallow
  (`self.fallbacks`), keeps the last error (`self.last_fallback`), and the ERROR line now names the
  count. The counter is per-instance and `get_reranker()` is a singleton, so one query's fallback is
  the *delta* across its own `rerank()` call.
- `scripts/evaluate_rag.py` — `run_retrieval` takes that delta and returns `reranker_fallback`;
  `evaluate_query` carries it onto each result; `collect_reranker_fallbacks(results)` gathers the
  affected ids.
- **The artifact** — the config snapshot's `reranker` block gains `fallbacks`,
  `queries_with_fallback`, `reranked_metrics_valid` (**false** when any fired) and `last_error`; the
  **Run integrity** section carries a ⚠️ line naming the queries; the Config section prints
  `Reranker fallbacks: N (RERANKED METRICS INVALID — see Run integrity)`; and `main()` **exits 3**
  instead of 0. The artifact is still written — it is the evidence.

Tests: `tests/test_reranker_fallback.py` (7). **Both guards proven to discriminate by mutation** —
removing `self.fallbacks += 1` fails 1 test, neutering the per-query delta fails 2, each on its own
assertion (not a collection error); the tree was restored byte-identical (`diff` → 0).

⚠️ **What the fix deliberately does NOT do: it does not exclude a fallback query from the metrics.**
That changes the denominators and every historical comparison. §I56 excluded `gold-004` by hand for
exactly this reason; the run now **tells** you to, instead of doing it silently. Registered as the
follow-on decision.

**⚠️ VERIFIER v1 RAN — AND ITS ONE DISMISSAL WAS WRONG.** `openai/gpt-oss-20b`, `deleg_8c4afa8b`,
`status=completed`: **7/8 confirmed**, overall `confirmed`, no silent wrong answer reported. Its **C8
("enumerate every path where the cross-encoder swallows but the counter does not move") it answered
*"only the exception path increments the counter; early return or empty results don't increment and
don't cause silent rerank"*** — and it was handed the code. **That is false**, and it is the class I
had asked it to hunt. The verdict was also cheap (2 API calls, 16.8 s) with **fabricated line
numbers** ("`reranker.py` lines 511–519" of a 180-line file), so it was never banked; my own probe
found the path it missed.

**✅ SECOND PATH FOUND AND FIXED — a clean HTTP 200 that ranks NOTHING** (probe, session 10):

| response | returned | `fallbacks` | log level |
|---|---|---|---|
| `{"results": []}` | **0 chunks** | **0** | DEBUG only |
| `{}` (no `results` key) | **0 chunks** | **0** | DEBUG only |
| `{"results": [{"corpus_id": 0, "score": 0.9}]}` | 1 chunk | 0 | DEBUG |

The three response-shaping branches fall through to `ranked = []`, the method returns it, and
`evaluate_rag` — whose `aggregate_metrics` skips only `skipped`/`error`/negatives — **averages the
query in as a total miss** while the artifact says `reranked_metrics_valid: true`. This is *worse*
than the swallowed exception: the exception returns the **unranked pool**, this returns **nothing**,
so every metric for that query is 0 by construction.

**Fix:** `if not ranked: raise ValueError(...)` before the return, so the empty ranking goes into the
**same** handler — one counter, one log line, one disposition (fall back to `chunks[:top_k]`). A pool
of 100 documents cannot legitimately rank 0.

**Guards, all proven to discriminate by mutation on the author's own run** (each failure on its own
assertion, never a collection error; tree restored byte-identical, `diff` → 0):

| mutation | tests that fail |
|---|---|
| `self.fallbacks += 1` → `pass` | 1 |
| `if not ranked: raise` → `pass` | **2** (both parametrisations) |
| delta → `reranker_fallback = False` | 2 |

`tests/test_reranker_fallback.py` now 9 tests (17 in the two reranker files, pristine green).

⚠️ **The v1 verdict does NOT cover this revision** — the file changed after it ran. **Verifier v2 ran
(`deleg_297b66a3`, `status=completed`): 7/8 CONFIRMED, overall `confirmed`, no silent wrong answer.**
Same caveats as v1 — cheap (2 API calls, 19.1 s) and its cited line numbers are again fabricated
("`reranker.py` line 581–589" of a ~190-line file) — so it is **not** the evidence: the new guard's
discrimination is the author's own mutation run above, and C1–C7 were checked against the source. Its
one substantive observation was that the `if not chunks: return []` early return yields an empty
top-k without incrementing — **correctly judged harmless**: `run_retrieval` (and the Streamlit caller)
only reach `rerank` when the pool is non-empty, so that guard is unreachable in practice and returning
`[]` for an empty pool is the right answer. **§I55 is verified as of v2.**

**Evidence:** `logs/p1/step10/reranker_payload_probe.{py,json}`; the synthetic isolation is in the
session log. **Register against:** §I25 (the total-loss-that-reads-as-success class), §I24 (the `""`
failure contract), §I52 (measure the thing the phase actually runs), §I44 (evidence on disk).

---

### I56. 2026-10-22 — the DA lane MEASURED on v2: it is live and it is not inert, it is resolved-NEGATIVE on the product endpoint, and resolved-POSITIVE on overview

**The first measurement of this lane on v2.** §I49 proved it *answers*; nothing had measured whether
its answers change the result. §D12 (2026-10-16, OLD document) was the last run with a live lane and
the §3d smoke test ran with it dead, so this is a first measurement, not a re-measurement.

**Instrument:** `logs/p1/step10/da_lane_ablation.py` — the production path
(`store.search_with_das` → page-dedup → MMR → cross-encoder) with **`cfg.da_enabled` toggled and
everything else pinned**: same query, same query vector, same `mmr_candidates` pool, same collection,
same reranker. Artifact `logs/p1/step10/da_lane_ablation.json`.

| | |
|---|---|
| queries | **133** answerable text queries (53 factual / 40 multihop / 40 overview) |
| pool, DA **off** | min **57** / median **77** / max **90** chunks |
| the lane answers | **100** DA hits per query (its own `fetch_k`) — i.e. on **every** query |
| the lane adds | mean **32** new chunks per query = **+41.5 %** of the pool |
| survival | **104 / 133** queries carry a DA-added chunk into the top-20 |
| excluded | **1** query (`gold-004`) — §I55 reranker fallback; the top-20 headline is n=**132** |
| cost | **no LLM calls**; ~24 min wall, one cluster session |

| endpoint | DA off | DA on | delta | 95 % CI | verdict |
|---|---|---|---|---|---|
| **candidate set R@100** | 0.5948 | 0.5822 | **−0.0125** | [−0.0442, +0.0192] | UNRESOLVED (W/L/T 44/17/72) |
| **top-20 R@20** (product endpoint) | 0.4385 | 0.4123 | **−0.0262** | [−0.0485, −0.0038] | **RESOLVED NEGATIVE** (W/L/T 5/27/100) |

| by type (candidate-set R@100) | DA off | DA on | delta | 95 % CI | verdict |
|---|---|---|---|---|---|
| factual (n=53) | 0.7155 | 0.6459 | **−0.0696** | [−0.1431, +0.0038] | UNRESOLVED (negative point estimate) |
| multihop (n=40) | 0.6335 | 0.6391 | +0.0056 | [−0.0234, +0.0345] | UNRESOLVED |
| **overview (n=40)** | 0.3960 | 0.4410 | **+0.0449** | [+0.0326, +0.0572] | **RESOLVED POSITIVE** |

**Reading it correctly — three things the numbers do not say on their own.**

1. ⚠️ **The "candidate set" is POST-MMR, not the raw union.** `search_with_das` appends the DA
   parents and then runs **MMR over the combined pool** to select `fetch_k`. So a lane that can only
   *add* candidates can still **lower** candidate-set recall — it displaces dense candidates through
   MMR's diversity objective. The −0.0125 is a statement about *the DA lane interacting with MMR*,
   not about raw union recall. **Not tested:** DA with MMR off, or DA as a re-ranking rather than a
   pool-append. Either could move this number.
2. **The lane is not inert.** 104/133 queries carry a DA-added chunk into the top-20, so a null here
   would have been a real null rather than the §G1 pool defect. This one is a resolved negative.
3. **It is not uniformly bad.** The overview lane **resolves positive (+0.0449)** and factual carries
   a negative point estimate (−0.0696, unresolved at n=53). The average hides a sign change.

**Confounds, all recorded:** HyDE is **OFF** in both arms (deliberately — one HyDE call per arm would
risk two different query vectors and break the single-variable property); the **graph lane is
excluded** (multihop only, a second lever); 1/133 reranker fallback excluded per §I55. Absolute
numbers are therefore **not** production numbers; the delta is the measurement.

**What this does NOT license.** It does not say "delete the DA lane" — the overview result is a real
positive on the lane the summaries (§G2) also target. It also does not say the lane helps: on the
product endpoint it resolves **negative**. The disposition is an **OWNER decision** and is not taken
here. The three defensible options: keep as-is; gate the lane by `query_type` (overview only); or
turn it off. Each needs its own pre-registered comparison.

⚠️ **The probe's own retry wrapper swallowed its retries** and a 951 s gap between two progress lines
had no explanation in the log — §I25's class, inside the probe measuring §I25's class. Fixed
(retries are now logged); the run's numbers are unaffected.

**Register against:** §I12 (the lane was dead — 768-vs-1024), §I47, §I49 (the lane made live),
§A2 (closed), §I55 (the reranker fallback), §D12 (the last live-lane run, on the old document).

---

### I57. 2026-10-22 — "is the new system better?" has NO valid answer yet: the one cross-system pair is confounded six ways, and the new index has never had generation metrics

**What was asked, and what exists.** The question is whether the rebuilt system beats the deployed one
per metric. There is exactly **one** pair of runs on the **same query set** that differ by index:

| | §D12 (OLD) | §3d (NEW) |
|---|---|---|
| report | `p0-9-gold-v2_2026-10-17_0422.md` | `p1-step10-retrieval-only_2026-10-20_0411.md` |
| collection | **`knowledge_base`** (deployed, doc `6d55c52b`) | **`knowledge_base_v2`** (doc `7ba61432`) |
| index | 5,135 points (5,051 chunks + 84 RAPTOR) | 3,796 points, **NO RAPTOR nodes at all** |
| DA lane | **live** | **DEAD** (768-vs-1024, §I12) |
| generation | full — the judge ran | **retrieval-only** |
| abstention | generation mode | score-threshold only |
| label clamp | before §3c | after §3c |

**Instrument (new, scripted — this had no scripted answer before):**
`logs/p1/step10/compare_old_vs_new_index.py` → `…/compare_old_vs_new_index.json`. It parses the two
`.md` reports and pairs them by query id. **`evaluate_rag.py` writes only a `.md`**, which is why this
comparison was previously eyeball-only — **it should emit per-query JSON**; registering that as the
durable fix.

**Paired, n=133 (same 133 answerable v2 queries in both):**

| metric | OLD | NEW | delta | 95 % CI | verdict | W/L/T |
|---|---|---|---|---|---|---|
| Recall@100 | 0.6392 | 0.6258 | −0.0134 | [−0.0590, +0.0322] | unresolved | 49/32/52 |
| Recall@20 | 0.4645 | 0.4524 | −0.0121 | [−0.0614, +0.0373] | unresolved | 51/32/50 |
| Hit@20 | 0.9474 | 0.9098 | −0.0376 | [−0.0862, +0.0110] | unresolved | 3/8/122 |
| **Ctx.Prec** | 0.2346 | 0.2609 | **+0.0263** | **[+0.0110, +0.0417]** | **RESOLVED +** | 48/32/53 |
| **MRR** | 0.8267 | 0.7280 | **−0.0987** | **[−0.1690, −0.0284]** | **RESOLVED −** | 23/39/71 |
| NDCG@20 | 0.5399 | 0.5079 | −0.0320 | [−0.0801, +0.0160] | unresolved | 61/57/15 |

| by type, Recall@20 | OLD | NEW | delta | 95 % CI | verdict |
|---|---|---|---|---|---|
| factual (n=53) | 0.5639 | 0.5698 | +0.0059 | [−0.0943, +0.1061] | unresolved |
| multihop (n=40) | 0.6194 | 0.5433 | −0.0762 | [−0.1697, +0.0173] | unresolved |
| **overview (n=40)** | 0.1778 | 0.2061 | **+0.0283** | **[+0.0101, +0.0464]** | **RESOLVED +** |

**What the data is telling.**

1. **On the aggregate, the new system is statistically indistinguishable** — R@100, R@20, Hit@20 and
   NDCG@20 all straddle 0. There is **no evidence of the aggregate improvement the rebuild was hoped
   to deliver**, and no evidence of harm either.
2. **MRR resolves NEGATIVE (−0.0987)** — the *first* relevant page ranks lower, on 39 of 133 queries.
   That is the one retrieval metric that clearly got worse.
3. **Ctx.Prec resolves POSITIVE (+0.0263)** and **overview R@20 resolves POSITIVE (+0.0283, 26/10/4)**
   — two real wins, both in the direction the §I21/§I39 content filter was aimed at.
4. ⚠️ **The magnitudes are not attributable.** Six things changed at once, and at least three push in
   opposite directions: the new run had **no RAPTOR** (its overview lane's fallback) and a **dead DA
   lane**, while the old run's labels were built against the old index (§D4/§D6). §I56 measured the DA
   lane at **−0.0262 on top-20 R@20** on the *new* index — so the old run's live DA lane was, if
   anything, a handicap; the new run's dead lane was a *benefit*. That the aggregate still only ties
   is the uncomfortable part.
5. ⚠️ **The new index has never had generation metrics.** Faithfulness and Answer Relevance have **no
   new-system number at all** — the only v2 run was retrieval-only. So the half of the evaluation the
   product actually ships (an answer, not a page list) is **unmeasured** on the new system.
6. ⚠️ **Abstention is not comparable** (0.500 vs 0.824 is a *mode* difference, not progress — §D15).

**What would actually answer the question.** **Phase E — the authoritative `evaluate_rag.py` run on
the current `knowledge_base_v2`** — has never happened. Since §3d the index has gained RAPTOR (B5),
a live DA lane and a live graph lane (§I49), the §I21 graph filter, the §G3 merge, and §G2's
summaries exist but are not wired. **Every one of those is now in place and none of it has been
measured end-to-end.** Phase E is one cluster session (retrieval + judge) and it is the only thing
that can turn this table into a real comparison.

**Not claimed:** that the new system is better, or worse. The honest statement is: **no valid
comparison exists yet, and the one available proxy shows a tie on aggregate with a worse MRR and two
real wins in context precision and the overview lane.**

**Register against:** §D9 (v1 vs v2 R@20 are not comparable at all — a different trap from this one),
§D15 (the four differences that make §3d a smoke test), §D4/§D6 (the labels were built against the
deployed index), §I56 (the DA lane's measured effect), §I44 (evidence on disk).

**✅ THE REGISTERED DURABLE FIX LANDED 2026-10-22 (session 11).** `evaluate_rag.py` now emits a
**machine-readable per-query JSON twin** alongside the `.md`. NEW `write_run_artifacts` writes the
`.md` (content unchanged — it stays the regression baseline) **and** a `.json` carrying
`config_snapshot`, an `integrity` block, `aggregated`, and the per-query `results`, so a cross-run
comparison pairs runs **by query id** instead of parsing markdown — which is the only reason
`compare_old_vs_new_index.py` had to. `_json_default` converts numpy scalars via `.item()` and
**re-raises** for anything else, so an unrepresentable object is loud rather than silently
stringified into the artifact.

**Three guards, all proven to discriminate by mutation on the author's own run** (each failing on
its own assertion, tree restored byte-identical): dropping the `json_path.write_text(...)` line
fails **3**; `if hasattr(o, "item"):` → `if False:` fails **1**; `raise TypeError(...)` →
`return str(o)` fails **1**. `tests/test_eval_integrity.py` 20 passed.

⚠️ **A first attempt at the encoder guard COULD NOT FAIL and was caught before it was believed.**
The test used `np.float64`, on the claim that `json.dumps` rejects it — **false**: `np.float64`
subclasses Python `float`, so json serialises it natively. The mutation (neutering the encoder)
therefore passed 19/19. The fallback exists for `np.int64` / `np.float32` / `np.bool_`, which are
**not** Python subclasses and do raise — measured, not assumed. Test and docstring were corrected to
those types. Same class as §I63's constant-vector probe: **a check that cannot fail is not a check.**

⚠️ **Verifier `deleg_e9e29bc5` (openai/gpt-oss-20b) returned 6 CONFIRMED / 1 REFUTED — and the
refutation is VOID.** It refuted C6 ("the change is additive; §I55's exit-3 is intact") on the
grounds that "main() now returns 3 when any reranker fallback occurs … introducing a new exit
code". **That code is not this change's**: the author's diff contains no `return 3` (it only reads
the existing `n_reranker_fallbacks` into the new integrity dict), and `git log -S'return 3' --
scripts/evaluate_rag.py` pins that line to `6f17abe` (§I55), committed before it. The reviewer
inspected the current file and attributed a pre-existing line to the diff under review — **a
reviewer without the diff's boundary will misattribute what it reads.** The verdict was also cheap
(4 API calls, 18.8 s, no test run) with pack-relative line numbers, so it was **not banked**: the
mutation runs above are the evidence.

**Register against (this block):** §I55 (the exit-3 the reviewer misattributed), §I44 (evidence on
disk), §I63 (the "check that cannot fail" trap, again), §I25 (a failure that reads as a success).

---

### I58. 2026-10-22 — the gold set does NOT need rebuilding for the new index; it is *better* served by it, and that exposes the real problem

**The question.** The labels were authored while `knowledge_base` (doc `6d55c52b`) was live. Does the
rebuilt `knowledge_base_v2` (doc `7ba61432`) need a new eval set to be assessed correctly?

**No — and rebuilding one would be circular.** A label here is a **PDF page that answers the
question**, established by a VLM scan of the document (§3b: 453 factual + 89 multihop labels are
scan-only). That is a property of the **document**, not of the index, and **the PDF is the same one**
in both ingests. Deriving labels *from* the new index would make the eval measure only the system it
was built from — precisely the circularity §D6 was settled to avoid for v1 ("early labels were
retriever-derived"). **An index-independent label set is the only kind that can compare two indexes,
and this one already is one.**

**Measured, not argued** (`logs/p1/step10/eval_set_index_validity.py` → `…json`; SQLite only, no
cluster, no LLM). Per query, how many of its labels a retriever can *ever* reach, reproducing the live
filter (`store.py:389-402`: `page_number ∈ [30, 936]` and `is_content is not False`):

| | OLD `knowledge_base` | NEW `knowledge_base_v2` |
|---|---|---|
| reachable pages / chunks in window | 724 / 4,519 | **888 / 3,489** |
| **achievable max**, mean | 0.8806 | **0.9545** |
| achievable max, min | 0.3750 | 0.0000 |
| queries capped below 1.0 | **76** | **41** (24 at ±1) |
| labels unreachable (exact / ±1) | — | **57 / 26** of 3,631 |
| labels unreachable by type | — | factual 5/2 · multihop 6/3 · **overview 46/21** |

**The new index is a BETTER index by this measure** — it reaches 95.5 % of the labelled pages against
the old index's 88.1 %, from fewer chunks (more pages covered, thinner per-page redundancy).

**⚠️ And that is the finding that matters more than the question.** Ceiling-normalised (§D9):

| | achievable max | observed R@100 (§I57) | **headroom captured** | left on the table |
|---|---|---|---|---|
| OLD index | 0.8806 | 0.6392 | **72.6 %** | 0.2414 |
| NEW index | 0.9545 | 0.6258 | **65.6 %** | **0.3287** |

So the R@100 *tie* in §I57 is **not** "the new index is no better". The index improved and **the
retriever did not capture the improvement** — the new system leaves **0.33** of reachable recall
unused, against 0.24 for the old one. The bottleneck has moved from the corpus to the retrieval path.

**A small, real repair list — not a rebuild:**

1. ⚠️ **`gold-003` is structurally unscoreable in the new index.** Its single label is page **30** —
   exactly `min_content_page`, and the new ingest has **no chunk at page 30**. Unreachable even at ±1,
   so its R@20 is **0 by construction**. §D15 recorded "Unreachable label pages 4 → 0" *before* the
   §I21 filter and the re-chunk; this one is new. **One query, and it silently drags the factual
   lane's mean down.**
2. **`gold-009` / `gold-010`** are the §D4 ±1 fuzz (label page 99, reachable at ±1) — measurable, but
   they read 0 at exact page matching.
3. **Overview is the most capped lane** (30 of 40 queries; 46 of 2,954 labels unreachable) — but note
   this is largely a *label-size* artifact, not reachability: with a mean of 73.8 labels, **any single
   miss caps the query below 1.0** (§D9). Judge overview by the ceiling-normalised number, not by
   "capped".
4. The remaining ~50 unreachable labels are ~1.6 % exact / ~0.7 % at ±1 — a noise floor, not a defect.

**Recommendation:** **re-point `gold-003` (and optionally the two ±1 queries) and leave the set
alone.** A full rebuild would cost a book-wide VLM scan (~36k judge calls, §3c) and would destroy
comparability with every historical run, for a ~1 % label-reachability gain.

**Register against:** §D6 (labels must not be retriever-derived), §D9 (ceiling-normalised reporting),
§D4 (the ±1 fuzz), §D15 ("unreachable label pages 4 → 0" — superseded, and now stale), §I57 (the tie
this explains), §I21/§I39 (the filter that changed the corpus).

---

### I59. 2026-10-22 — the base MRL-64 lane IS down in the new index, and the cause decomposes: a 64d-truncation penalty that is 8.7× worse for Qwen3, plus a full-dim ranking loss that is NOT attributable

**The question.** Does the base retriever capture better in the old or the new index? `dense_64 @1000`
is the only retrieval stage that faces the whole corpus — production is
`dense_64(1000) → dense_<full>(500)` (`store.py:416`) — so this is the rebuild's most direct
retrieval-stage comparison.

**Instrument:** `logs/p1/step10/base_retriever_mrl64.py` → `…json`. 133 queries, page-level recall at
k ∈ {1000, 500, 100, 20}, reported **raw and ceiling-normalised** (§D9 — the two indexes' achievable
maxima differ, so raw compares different denominators). The production filter is copied verbatim from
`store.py:336-369`.

⚠️ **The two indexes are in different embedding spaces, so each is queried with its OWN embedder** —
the old index is `dense_768` (Nomic `nomic-embed-text-v1.5`), the new one is `dense_1024` (Qwen3
`Qwen/Qwen3-Embedding-0.6B`). A Qwen3 64d vector is meaningless against the old index's `dense_64`.
⚠️ **Both `dense_64` lanes are EXACT MRL slices of their full-dimension vectors** — verified on 200
sampled points per index, `cosine(slice(full), low) = 1.0000` for every one. Neither lane is corrupt;
any difference is genuine ranking information at 64d.

**Result (n=133; achievable max old 0.8731 / new 0.9771):**

| lane, ceiling-normalised | k | OLD | NEW | delta | 95 % CI | verdict |
|---|---|---|---|---|---|---|
| **MRL-64** | **1000** | **0.9224** | **0.8151** | **−0.1086** | [−0.1456, −0.0717] | **RESOLVED −** |
| MRL-64 | 500 | 0.9224 | 0.7880 | −0.1359 | [−0.1760, −0.0959] | RESOLVED − |
| MRL-64 | 100 | 0.6397 | 0.3587 | −0.2783 | [−0.3404, −0.2161] | RESOLVED − |
| MRL-64 | 20 | 0.4220 | 0.1028 | −0.3185 | [−0.3833, −0.2538] | RESOLVED − |
| **full-dim** | **1000** | 0.9352 | 0.9266 | **−0.0092** | [−0.0321, +0.0136] | **unresolved** |
| full-dim | 500 | 0.9352 | 0.9224 | −0.0134 | [−0.0364, +0.0096] | unresolved |
| full-dim | 100 | 0.7006 | 0.5691 | −0.1348 | [−0.1774, −0.0923] | RESOLVED − |
| full-dim | 20 | 0.4987 | 0.2939 | −0.2026 | [−0.2556, −0.1496] | RESOLVED − |

Raw (for the record): full-dim R@1000 **+0.0890** [**+0.0519, +0.1261**] **RESOLVED in the NEW
index's favour**; MRL-64 R@1000 −0.0102 [−0.0512, +0.0309] unresolved. So at the pool level the new
index reaches MORE raw pages — it just has a higher ceiling to be measured against.

**The decomposition — and why it is clean.**

1. **The 64d truncation penalty is a property of the MODEL, and it is 8.7× worse for Qwen3.** Measured
   *within* each index (same chunks, same model, full-dim vs 64d), so it is not confounded:

   | | full-dim R@1000 | MRL-64 R@1000 | **truncation penalty** |
   |---|---|---|---|
   | OLD (Nomic) | 0.9352 | 0.9224 | **0.0128** |
   | NEW (Qwen3) | 0.9266 | 0.8151 | **0.1115** |

   Nomic v1.5 is explicitly MRL-trained and its 64d slice is nearly lossless. Qwen3-Embedding-0.6B
   supports custom output dims but its **64d end is far weaker**. At R@20 the same penalty is 0.0767
   (old) vs 0.1911 (new).
2. **The full-dim ranking loss is NOT attributable.** R@20 falls 0.4987 → 0.2939 (ceiling-normalised,
   resolved) with **no truncation involved at all**. That is embedder **and** chunking together (5,048
   vs 3,796 chunks over the same PDF) and this instrument cannot separate them.
   **✅ ATTRIBUTED 2026-10-22 (session 10, §I63) — IT IS THE EMBEDDER.** Holding the corpus fixed and
   swapping *only* the embedder, **Nomic 768d beats Qwen3 1024d by +0.1400** ceiling-normalised R@20
   (CI **[+0.0907, +0.1893]**, W/L/T 60/26/47), and by +0.0599 at R@100. The paragraph above stands as
   the record of what *this* instrument could not do; the attribution came from a different one.
3. **Neither loss is a page-density artifact.** Page-level recall is not chunk-count-neutral, so it was
   checked: the old index has **6.24** chunks/page and returns a median **413** distinct pages from
   1000 chunks; the new has **3.93** chunks/page and returns **531**. The mechanical effect favours the
   **new** index — and it is still worse. The finding survives its own confound.
4. **§I57's production tie is consistent with all of this.** Production rescores the top-1000 with the
   full-dimension lane and then reranks, so the *ordering* loss is largely absorbed — which is why the
   end-to-end R@20 tied while the base stage fell off a cliff. The loss is currently **masked, not
   absent**: any query whose relevant page falls outside the 64d top-1000 is unrecoverable, and the
   margin is thinner than before.

**What this does and does not license.**

- ⚠️ **It does NOT license reverting to Nomic.** Effect 2 (the larger absolute loss) is confounded with
  chunking, so a model swap would not reliably fix it — and a revert costs a re-ingest plus a re-index
  of `derivative_artifacts` (73,406 pts) and `concept_embeddings` (6,065 pts), both moved to 1024d in
  §I49, plus the intent classifier, whose width **is** `dense_dim`.
- ✅ **The cheap, targeted fix for Effect 1 is the STAGE, not the model.** The 64d prefetch exists to
  make ANN fast at scale; `knowledge_base_v2` holds **3,489** in-window chunks, where a 1024d ANN is
  instant. The two-stage funnel is **pure downside here** — it gives up 0.1115 of pool recall to save
  microseconds. Either raise the 64d limit (1000 → 5000, cheap) or drop the 64d prefetch and ANN the
  full dimension directly. **No re-ingest, no model change.**
- ⚠️ Effect 2 needs its own instrument before any embedder decision: it is the §D9/§I57 class again —
  a delta that mixes the embedder with the corpus change.

**Cost:** no LLM calls; ~9 min wall (the local Nomic embedder is the slow part, CPU); cluster Qdrant
reads only. **No writes to any collection.**

**Register against:** §I57 (the tie this explains), §I58 (the ceiling normalisation), §D9, §I12/§I49
(the 1024d move a revert would undo), §I52 (measure the model the phase runs), §E6 (the query-side
switch to Qwen3).

---

### I60. 2026-10-22 — the MRL dimension sweep: the pool is saturated at EVERY dimension, so the width is irrelevant and the ANN is the only lever

**The question.** Would widening the first stage (64d → 128d) or raising its prefetch limit recover
the pool §I59 found degraded?

**Instrument:** `logs/p1/step10/mrl_dimension_sweep.py` → `…json`. Because `dense_64` is a verified
*exact* MRL slice of the full-dimension vector (§I59), `full[:d]` re-normalised **is** `dense_<d>`, so
every dimension can be reconstructed **client side** from the stored full vector and brute-forced
against the whole collection. **Read-only: no new named vector, no re-embed, no write.** 133 queries,
d ∈ {64, 128, 256, 512, 1024}, k ∈ {20, 100, 500, 1000, 2000, 5000}.

⚠️ **The `k`-unit note here is CORRECTED — 2026-10-22 (session 10, §I63).** The earlier claim in this
entry — "`k` here is in **CHUNKS** (top-k chunks → deduped page pool); §I59's `k` is in **PAGES**" —
**is wrong in its mechanism**. **Both** apply `k` to a deduped **page** list. What differs is the
**pool depth** the page list is drawn from: this sweep's `max(KS)` is 5000, i.e. **every chunk**, while
§I59's is the **top-1000 chunks** (production's prefetch depth, `store.py:416`). At k=20 and k=100 the
two page lists are identical; they diverge at k≥500, where §I59's list is already exhausted — R@1000
**1.0000 here** against **0.926563** in §I59. Measured, not argued:
`cross_embedder_experiment.py`'s X2 and X2b reproduce **both** rows exactly, all four k each. The
withdrawn "ANN gap" comparison stays withdrawn, but the reason it was nonsense is the **pool depth**,
not a k-unit mismatch.

**The grid, ceiling-normalised (k in pages — see the correction above):**

| NEW index (Qwen3) | R@20 | R@100 | R@500 | **R@1000** |
|---|---|---|---|---|
| d=64 | 0.0256 | 0.1507 | 0.6611 | **1.0000** |
| d=128 | 0.0680 | 0.2070 | 0.7296 | **1.0000** |
| d=256 | 0.0925 | 0.3030 | 0.7741 | **1.0000** |
| d=512 | 0.2608 | 0.5126 | 0.8988 | **1.0000** |
| d=1024 | 0.2939 | 0.5691 | 0.9230 | **1.0000** |

| OLD index (Nomic) | R@20 | R@100 | R@500 | **R@1000** |
|---|---|---|---|---|
| d=64 | 0.3806 | 0.6126 | 0.9369 | **1.0000** |
| d=128 | 0.4369 | 0.6501 | 0.9474 | **1.0000** |
| d=256 | 0.4757 | 0.6769 | 0.9602 | **1.0000** |
| d=512 | 0.4792 | 0.7008 | 0.9590 | **1.0000** |

**Three findings.**

1. **The pool is SATURATED at 1000 chunks at every dimension in both indexes — R@1000 = 1.0000
   everywhere.** The pool already contains every reachable relevant page. So **the MRL width is
   irrelevant to coverage, and raising the limit above 1000 buys nothing in exact search.**
2. **The width matters enormously for RANKING, monotonically.** New index R@20: 0.0256 (64d) →
   0.2939 (1024d) = **11.5×**; R@100 0.1507 → 0.5691. Truncation damages the **order**, not the
   **coverage**.
3. **§I59's truncation finding SURVIVES with the ANN confound removed.** Nomic barely degrades with
   truncation (R@20 0.3806 → 0.4792, 1.26×) while Qwen3 degrades 11.5×. The Qwen3 64d slice really
   is much weaker; it was not an artifact.

**The owner's objection, and it is correct.** Production is a Qdrant **prefetch**:
`Prefetch(prefetch=[dense_64(1000)], query=vec_full, using=dense_1024, limit=500)` — the inner stage
selects 1000 candidates and the outer query **re-scores them at full dimension**. So the 64d lane's
*order* is discarded and only its *membership* survives. **The only 64d number that matters is pool
coverage at the limit**, and finding 1 says the dimension does not affect it. **128d is therefore
dead**: it would add a named vector and a cluster write for zero coverage gain and a ranking gain
(0.0680) that is still only 23 % of what 1024d already provides.

**What is left, and it is not the width.** Qdrant at limit=1000 reaches **0.8151** where exact search
reaches **1.0000** — the loss is the **filtered-HNSW search path**, not the vector. That is
`prefetch_limit_sweep.py` (§I61, in progress).

**Cost:** no LLM calls, ~30 s of compute, cluster reads only. **No writes.**

**Register against:** §I59 (whose truncation finding this confirms), §I57, §I58, §I44.

---

### I61. 2026-10-23 — the prefetch limit, NOT the dimension, is the lever: raising it recovers the pool the filtered ANN is losing

**✅ WRITTEN UP 2026-10-23 (session 11).** The sweep **ran on 2026-10-22 but was never registered** —
`logs/p1/step10/prefetch_limit_sweep.{py,json}` existed with a full summary and §I60 referred to it
only as "§I61, in progress". The numbers below are **re-derived from the artifact's own per-query
array** (all 16 cells exact); nothing here is read off the summary block.

**The question.** §I60's *exact brute-force* sweep found the pool **saturated at 1000 chunks at every
MRL dimension** (ceiling-normalised R@1000 = 1.0000, both indexes). Yet §I59's **Qdrant** query at the
same limit reached only **0.8151** (new) / **0.9224** (old). If the gap is the **filtered HNSW search
path** — Qdrant walks a graph whose nodes the filter excludes — then **the limit is the lever and the
dimension is not**. This measures it directly.

**Design.** Query `dense_64` and the full-dimension lane at limits {1000, 1500, 2000, 3489}. ⚠️
`limit` is in **CHUNKS** and recall is over the **deduped PAGE pool** (§I60's convention, *not*
§I59's, whose `k` indexes pages — §I63 settled that distinction). `limit = 3489` (every in-window
chunk of the new index) is **effectively exact search and is the control**. Read-only: no LLM calls,
no writes. ⚠️ **A 40-query strided subsample** of the 133 answerable text queries
(`queries[::3][:40]`), i.e. a **screening** result, not the pre-registered endpoint.

**Result — mean ceiling-normalised pool recall, re-derived:**

| index | lane | limit 1000 | 1500 | 2000 | 3489 (=exact) |
|---|---|---|---|---|---|
| **NEW** (40 q) | **`dense_64`** | **0.804127** | 0.904495 | 0.971526 | **1.0000** |
| NEW | full-dim | 0.932368 | 0.965171 | 0.971966 | 1.0000 |
| OLD (39 q) | `dense_64` | 0.930702 | 0.955416 | 0.974099 | 0.998992 |
| OLD | full-dim | 0.934881 | 0.960130 | 0.984654 | 0.999251 |

**Four findings.**

1. ⚠️ **At the PRODUCTION limit (1000) the new index's 64d prefetch lane covers only 0.804127 of the
   reachable pool, against 0.932368 for full-dim — a 0.128241 gap.** On the **old** index the same
   comparison is 0.930702 vs 0.934881, a **0.004179** gap. So the new index's 64d prefetch loses
   **~30× more pool coverage** than the old index's does. §I59's "8.7× worse truncation penalty for
   Qwen3" is a *ranking* measurement; **this is the same weakness showing up as coverage.**
2. **Raising the limit recovers it, and the recovery is large at every step** (new `dense_64`):
   +0.100368 (1000→1500), +0.067031 (1500→2000), +0.028474 (2000→exact).
3. ⚠️ **At limit 2000 the dimension STOPS MATTERING** — 64d 0.971526 vs full-dim 0.971966, a gap of
   **0.00044**. So §I60's "128d is dead" is confirmed **from a second, independent direction**: with
   a high enough limit the 64d lane is as good as full-dim at the pool level, so there is no case for
   adding a 128d named vector.
4. **The control holds: at `limit = 3489` (every in-window chunk) BOTH lanes are exactly 1.0000.**
   The loss is **entirely the ANN search path**, not the vector and not the filter — nothing is
   unreachable, it is only under-returned.

**The cheap fix this licenses — and it is code/config only.** Raise the 64d prefetch limit in
`store.py` (1000 → 2000, or to the collection's in-window chunk count, which is **exact search** at
this corpus size). **No re-ingest, no model change, no new named vector, no Qdrant write.** §I59
reached the same recommendation from the ranking side; this is its coverage-side confirmation.

⚠️ **What this does NOT license: shipping the change on this evidence.** The sweep is a 40-query
screening subsample with **no paired CI and no pre-registration**. The change touches the production
retrieval path, so it needs its own **pre-registered** A/B (raise-the-limit vs current, 133 queries,
paired, on the product endpoint) before it ships — the §D1 discipline every other lever here has been
held to. It is registered as **the next lever to test**, not as a pending commit.

⚠️ **A naming trap in the artifact, recorded so the next reader is not caught:** the summary block's
`median_pages_in_pool` **is** a median, but the neighbouring `pool_recall_ceiling_norm` is a
**mean**. Both are unlabelled; reading the second as a median gives 1.0000 for **15 of the 16 cells**
— only `new` / `mrl64` / `limit 1000` differs, at a median of 0.8875. (The author's own first
re-derivation did exactly that and first wrote "12 of 16"; the verifier's count of 15 was right and
the entry is corrected.) The write-up above uses means, matching the artifact's own aggregation.

**✅ INDEPENDENT VERIFIER RAN 2026-10-23 — `openai/gpt-oss-20b`, `deleg_ba350d60`,
`status=completed`: 7/7 CONFIRMED.** Substantive rather than cheap (**20 API calls, 64.6 s**): it
re-derived the mean for **all 16 cells** from the per-query array and matched every one, and it read
the script's `--sample` handling to confirm the `queries[::3][:40]` selection.

⚠️ **Its one flagged "defect" is VOID, and it is the third misattribution of the session.** It
reported: *"Summary reports old lanes at limit 3489 as pool_recall_ceiling_norm 1.0, whereas
per-query means are 0.999251 (fulldim) and 0.998992 (mrl64)."* **The summary does not say 1.0** — it
says **0.999251** and **0.998992**, exactly the means. The reviewer compared against the wrong field
(most likely `median_pages_in_pool`, or the `new` rows) and reported a disagreement that does not
exist. Checked mechanically: both cells match to 1e-9.

⚠️ **But the same verdict contained a REAL catch about the author's text, in a place it did not point
at:** its "median is 1.0 for 15 of 16 cells" is **correct**, and this entry had said 12. That number
is now fixed. **The lesson is the §I57 one again, from the other side:** a reviewer that reports a
defect has to have its *claim* checked, not just its *count* — here the count was right and the
stated defect was invented, so accepting the flag wholesale would have "corrected" a cell that was
already correct, while rejecting it wholesale would have left a wrong number in the register.

**Register against:** §I60 (whose "128d is dead" this confirms from the coverage side), §I59 (the
ranking-side loss this mirrors), §I63 (the k-units/pool-depth distinction that fixes the convention
here), §I57 (the production tie this would be measured against), §I58 (the ceiling normalisation),
§I44 (an artifact that is not written up is not evidence).

**✅ THE PRE-REGISTERED A/B RAN 2026-10-23 — and the lever is a NULL at the product endpoint.**
`logs/p1/step10/prefetch_limit_ab.json`, pre-registration committed `e0fed5e` before the run. Raising
the prefetch 1000 → 2000 moves R@20 by **+0.0028, CI [−0.0006, +0.0062] → UNRESOLVED**; exact search
(3489) gives **+0.0031, UNRESOLVED**; Hit@20 is identical to 4 dp in every arm; the negative control is
bit-exact (0 mismatches over 931 metrics). The mechanism reproduces at full sample (lane coverage
0.815 → 1.000) and **still does not move the product**. **The change does NOT ship; this entry is
recorded measured-and-unresolved.** Full detail in **§I65**; the mechanism — the loss is the 100-slot
fusion, not the prefetch and not the re-score cut — in **§I66**.

---

### I62. 2026-10-22 — the cluster serves Nomic, but does NOT apply its task prefixes — and the timing table for any Nomic re-embed

**Found while costing the cross-embedder experiment** (§I59 Effect 2 needs "hold the corpus fixed,
swap only the embedder"). Two facts, both measured.

**1. The cluster serves Nomic.** `POST http://10.0.10.70:8123/embed-text/v1/embeddings` with
`model = "nomic-ai/nomic-embed-text-v1.5"` returns **768d** in **0.18 s**. It is not in the
advertised model list (`/v1/models` on 8123 is a 404), so this is discoverable only by trying it.

**2. ⚠️ THE CLUSTER DOES NOT APPLY NOMIC'S TASK PREFIXES.** `embedder.NomicEmbedder` prepends
`search_document: ` / `search_query: ` itself; the cluster endpoint is a generic passthrough and does
not. Measured on 5 real chunk texts (`nomic_prefix_check.py`):

| how the text was sent | cosine vs the local `NomicEmbedder` |
|---|---|
| cluster, **raw** | **0.949040** |
| cluster, prefixed `search_document: ` | **1.000000** |

**A naive re-embed would have landed in a slightly different space** — cosine 0.949, a small *uniform*
degradation that reads as noise — and every number from the experiment would have been wrong while
the run looked healthy. **§I25's class.** The caller MUST prefix. This is now verified, not assumed.

**3. The timing table** (measured on 400 real in-window chunks, median 461 chars; batch = one HTTP call):

| batch | latency | throughput | 3,489 chunks |
|---|---|---|---|
| 16 | 0.35 s | 45 chunks/s | 1.28 min |
| 32 | 0.47 s | 68 chunks/s | 0.85 min |
| 64 | 0.68 s | 94 chunks/s | 0.62 min |
| **128** | **1.06 s** | **121 chunks/s** | **0.48 min** |

133 query vectors in one call: **1.78 s**. So a full Nomic re-embed of the new index is **~29 s of GPU**
plus seconds to write ~10.7 MB — **under 10 minutes wall including the harness.** ⚠️ By contrast the
**local CPU** path (§I59 used it) runs ~3 s/query → 3,489 chunks would be **~3 hours**. Use the cluster.

**Register against:** §I59 (the experiment this unblocks), §I52 (measure the model the phase runs),
§I25 (a failure that reads as a success), §I19a (a cache that hit nothing — the same "looks fine,
is wrong" shape).

---

### I63. 2026-10-22 — the cross-embedder experiment: §I59's Effect 2 IS THE EMBEDDER. On the same corpus, Nomic 768d beats Qwen3 1024d by +0.1400 ceiling-normalised R@20

**The question.** §I59 measured a **full-dimension ranking loss** in the new index (R@20
ceiling-normalised 0.4987 → 0.2939, resolved, **no truncation involved at all**) and could not
attribute it: the two indexes differ in the embedding MODEL *and* the chunking (5,048 vs 3,796 chunks
over the same PDF) *and* the content-filter state. **Hold the corpus fixed; swap only the embedder.**

**Design (pre-registered; plan `.hermes/plans/2026-10-22-p1-cross-embedder-experiment-plan.md`).** The
NEW corpus (doc `7ba61432`, **3,489** in-window chunks) is embedded **twice**: arm **Q** = Qwen3
1024d (the stored index vectors, re-derived here) and arm **N** = Nomic 768d (embedded this run).
**Exact** brute-force cosine over the whole corpus, page-deduped — **not** Qdrant, because §I60 showed
the filtered-HNSW path costs up to 18.5 % of the pool. 133 queries. Endpoint **R@20, N vs Q, paired,
ceiling-normalised**; attributable iff the CI excludes 0.

**Instrument:** `logs/p1/step10/cross_embedder_experiment.py` → `…json` (sha256 `7c5e92f9…`).
No LLM calls, **no writes**, **124 s wall** (the Nomic re-embed is 38.9 s of it).

| arm | corpus | embedder | R@20 | R@100 | R@500 | R@1000 |
|---|---|---|---|---|---|---|
| **Q** (control) | new, `7ba61432` | Qwen3 1024d | 0.2939 | 0.5691 | 0.9230 | 1.0000 |
| **N** (treatment) | new, `7ba61432` | Nomic 768d | **0.4339** | **0.6290** | 0.9273 | 1.0000 |

| endpoint (ceiling-normalised) | delta (N − Q) | 95 % CI | W/L/T | verdict |
|---|---|---|---|---|
| **R@20** | **+0.1400** | **[+0.0907, +0.1893]** | 26/60/47 | **RESOLVED — N > Q** |
| R@100 (secondary) | +0.0599 | [+0.0132, +0.1067] | 34/51/48 | RESOLVED — N > Q |
| R@500 | +0.0044 | [−0.0172, +0.0260] | 30/25/78 | unresolved |
| R@1000 | 0.0000 | [0.0000, 0.0000] | 0/0/133 | **saturated** (both arms 1.0000) |

**The answer, per the pre-registered rule.** `N > Q` → **Qwen3 ranks worse than Nomic on this
corpus.** So §I59's Effect 2 — the full-dimension ranking loss no instrument could attribute — **is
attributable to the embedder**, and it is large: **+0.14 of ceiling-normalised R@20**, nearly half of
arm Q's entire score, better on **60 of 133** queries and worse on 26. The saturation at R@1000 is
§I60's finding again, from the other direction: coverage is not the problem, **order** is.

⚠️ **What this does NOT license — a revert.** The plan's §1 is explicit and it still holds: a revert
is a re-ingest plus a re-index of `derivative_artifacts` (73,406 pts) and `concept_embeddings` (6,065
pts) — both moved to 1024d in §I49 — plus the intent classifier, whose width **is** `dense_dim`. That
is an **owner decision** on a much larger evidence base than one metric. The finding is that *the
embedder is the lever*; choosing it is a separate decision, not taken here.

⚠️ **The re-chunk is not exonerated.** This isolates the embedder *given this corpus*. It does not say
the re-chunk is neutral — only that it is not *needed* to explain the loss.

**Verifiers — all six pass, and two of them are exact reproductions of registered rows.**

| # | check | result |
|---|---|---|
| X1 | the cluster Nomic reproduces the LOCAL `NomicEmbedder` | doc cos **1.000000** prefixed / **0.937749** raw; query cos **1.000000** — §I62's prefix trap confirmed live, in the run that depends on it |
| X2 | arm Q reproduces §I60's d=1024 row **exactly** | R@20 0.293934, R@100 0.569074, R@500 0.922982, R@1000 1.0 — **all four exact** |
| X2b | arm Q reproduces §I59's `new_fulldim` row **exactly**, at the other pool depth | R@20 0.293934, R@100 0.569074, R@500 0.922421, R@1000 0.926563 — **all four exact** |
| X3 | both arms see an identical chunk→page mapping | pool 3,489; one shared pages array (sha256 `0ca575fabc5c59be`) |
| X4 | **A-vs-A negative control** — arm N re-embedded at batch 64 vs 128 | **max_abs_diff 0.0**, 0 mismatches: the instrument manufactures no delta |
| X5 | errors reported, never silently dropped | 0 errors, 133 queries kept |

**⚠️ A measurement-design finding: the plan's §5 is wrong in its mechanism, and X2+X2b together are
what settles it.** Both checks can be exact only because **§I59 and §I60 are the SAME ranking read at
two POOL DEPTHS**. **Both** apply `k` to a deduped **page** list. What differs is how deep the chunk
pool feeding that list is: §I59's is the **top-1000 chunks** (production's prefetch depth,
`store.py:416`), §I60's is **every chunk** (its `max(KS)` is 5000). At k=20 and k=100 the two page
lists are identical, so the pre-registered endpoint is convention-free; they diverge at k≥500, where
§I59's list is already exhausted — §I59 R@1000 **0.926563** against §I60's **1.0000**. The plan's §5
states this as *"§I59's k is in PAGES, §I60's is in CHUNKS"*: **the mechanism is not that**, and a
reader who took it literally would mis-attribute the divergence to the k-unit instead of to the pool
depth. Both registered numbers are now reproduced exactly, so the discrepancy is **settled, not
argued** — and this artifact carries both views (`ceiling_norm` = every-chunk pool, the primary;
`ceiling_norm_top1000pool` = §I59's).

**✅ INDEPENDENT VERIFIER RAN 2026-10-22 (session 10) — `openai/gpt-oss-20b`, `deleg_ac1507f8`,
`status=completed`: 8/8 CONFIRMED, no silent wrong answer.** The verdict was cheap (2 API calls,
15.9 s) and its cited line numbers are offsets into the review pack rather than the sources, so it
was **not banked**; the two claims that carry the headline were re-derived independently:

1. **The endpoint arithmetic, recomputed from the artifact's own per-query array** (not from the
   probe's summary): R@20 mean **0.139996**, CI **[0.090737, 0.189255]**, W/L/T **26/60/47** — all
   three match the artifact exactly; R@100 0.059919 / [0.013168, 0.106669] / 34/51/48 likewise. The
   two arms' aggregate means recompute to 0.293934 and 0.433930.
2. **The ordering guarantee, by a probe that can FAIL** — the cluster response is deliberately
   returned SHUFFLED, with each item's true `index` attached: `cluster_embed` restores input order
   (ratios 1,2,3), and across **two batches of 2** (where `index` restarts per request) it still
   gives 1,2,1,2 — no cross-batch contamination, so `q_n[i-1]` cannot be paired with the wrong
   query's ranking. (The first version of this probe used a constant vector per row, which
   normalises to the same unit vector and therefore **could not fail** — recorded because it is the
   "check that cannot fail" trap, caught before it was believed.)

⚠️ **"Chunking held fixed" means both arms used the NEW corpus's chunks — it does NOT test the
chunking.** Both arms rank the same 3,489 re-chunked units (the semantic/contextual chunking of doc
`7ba61432`), which is exactly what makes the N-vs-Q delta attributable to the embedder. It says
nothing about whether that chunking is good.

**And that leaves a residual, which is the honest limit of this result.** Three ceiling-normalised
R@20 numbers are now on the same scale (arm Q reproduces §I59's new full-dim row exactly, so they are
comparable):

| | corpus | embedder | R@20 |
|---|---|---|---|
| old index | old chunks (5,048) | Nomic | 0.498722 |
| new index | new chunks (3,489) | Qwen3 | 0.293934 |
| new corpus | new chunks (3,489) | **Nomic** | 0.433930 |

§I59's Effect 2 is a drop of **−0.204788**. Swapping the embedder alone recovers **+0.139996 — 68.4 %**
of it. **A residual of +0.064792 (31.6 %) is still unattributed**, and it mixes three things this
experiment deliberately held fixed: the chunking, the content-filter state, and the chunk count
(5,048 → 3,489). So the correct statement is *"the embedder is the larger half of Effect 2, and the
re-chunk is not exonerated for the remainder"* — **not** "the embedder explains it". §I59's Effect 2
should be read as 68 % attributed, not closed.

⚠️ **The residual does NOT mean the chunking is unbuilt — it is built, and it is in the corpus being
measured.** E1 (semantic chunking), E2 (Docling `HybridChunker` parents) and E3 (late chunking over
the parent's per-token embeddings) landed **2026-10-17** and the corpus was re-ingested with them
(`.hermes/plans/2026-10-16-p1-reingest-plan.md`; the *why* is `IMPROVEMENTS.md` §E1–§E3). So the
3,489 chunks arm N and arm Q both ranked **are** the E1/E2/E3 corpus. **What is missing is not the
chunking but its attribution** — no experiment has ever isolated "the chunking helped or hurt" from
"the embedder changed", which is exactly the 0.0648 this probe could not touch. Two concrete
follow-ons sit inside that gap: the plan's Step 10 re-measure, and one knob never re-tuned —
`min_chunk_tokens = 32`, inherited from the old size-based chunker, measured (§E1) to merge **27 %**
of the new, smaller children (91 → 66 on the fixture) with the merge never re-checking the grown
child's size.

**Register against:** §I59 (the effect this attributes), §I60 (whose row X2 reproduces), §I58 (the
ceiling rule), §I62 (the prefix trap X1 confirms), §I49 (what a revert would cost), §I52 (measure the
model the phase runs), §I57 (the production tie this is consistent with).

**Cost:** no LLM calls; 124 s wall; cluster reads + one Nomic re-embed. **No writes to any
collection.**

---


### I64. 2026-10-23 — PHASE E: the new system's generation metrics exist at last, and they are indistinguishable from the deployed system's — while the ranking stays worse

**The run that had never happened.** §I57 established that `knowledge_base_v2` had **no generation
metrics at all** (the only v2 run was retrieval-only, §3d) and that this was the one thing blocking
"is the new system better?". Phase E is that run: the authoritative FULL `evaluate_rag.py`
(retrieval + synthesis + judge) against the rebuilt index, pre-registered
(`.hermes/plans/2026-10-22-p1-phaseE-preregistration.md`, committed `36e28f3` **before** the run
finished) and harnessed (`logs/p1/step10/run_phaseE.sh`).

**Cost:** 4,180 s wall (1 h 10 m of compute, ~2 h 23 m clock), **5,434 judge calls, 0 failures**,
167/167 synthesis, 167/167 faithfulness. No re-ingest, no graph write, no Qdrant write.

**Artifact:** `data/eval_results/p1-phaseE-v2_2026-10-23_0650.{md,json}` (the `.json` twin is the
§I57 fix's first production use). Log `logs/p1/step10/phaseE_run_2026-10-22_2127.txt`.

| scope | n | R@100 | R@20 | Hit@20 | Ctx.Prec | MRR | NDCG@20 | Faith | Ans.Rel | Cite |
|---|---|---|---|---|---|---|---|---|---|---|
| **overall** | **133** | 0.6737 | 0.4250 | 0.9023 | 0.2421 | 0.7059 | 0.5050 | **0.6368** | **0.8521** | 1.0 |
| factual | 53 | 0.8214 | 0.5217 | 0.8491 | 0.1302 | 0.7251 | 0.4716 | 0.6853 | 0.7925 | 1.0 |
| multihop | 40 | 0.6391 | 0.5236 | 0.8750 | 0.0962 | 0.5146 | 0.4945 | 0.7343 | 0.8000 | 1.0 |
| overview | 40 | 0.5127 | 0.1982 | 1.0000 | 0.5362 | 0.8717 | 0.5598 | 0.4750 | 0.9833 | 1.0 |

Abstention **18/34 = 0.5294**. All five pre-registered guards pass (E1 collection is
`knowledge_base_v2`; E2 judge `Qwen/Qwen3-VL-8B-Instruct` named and cross-family; E3 133 metrics rows
+ 34 negatives; E4 `reranked_metrics_valid=false` with **gold-004** named; **E5 the `aggregated`
block re-derives EXACTLY from the per-query `results` array** — the check that makes the §I57 fix
earn its place).

**The answer, stated as narrowly as the evidence allows.** Against §D12 (the deployed system, the
only comparable run — **a different run on a different day, so this is descriptive, not causal**):

| metric | OLD §D12 | NEW Phase E | delta |
|---|---|---|---|
| R@100 | 0.639 | 0.6737 | **+0.0347** |
| R@20 | 0.465 | 0.4250 | −0.0400 |
| Hit@20 | 0.947 | 0.9023 | −0.0447 |
| Ctx.Prec | 0.235 | 0.2421 | +0.0071 |
| **MRR** | **0.827** | **0.7059** | **−0.1211** |
| NDCG@20 | 0.540 | 0.5050 | −0.0350 |
| **Faithfulness** | **0.661** | **0.6368** | **−0.0242** |
| **Answer Relevance** | **0.852** | **0.8521** | **+0.0001** |
| Citation | 1.000 | 1.0000 | 0 |
| Abstention | 0.500 | 0.5294 | +0.0294 |

- **The half that was missing is now measured, and it is a TIE.** Faithfulness 0.637 vs 0.661 and
  Answer Relevance 0.852 vs 0.852 — the deployed system's answer quality is not beaten, and it is
  not beaten by the new one either. There is **no generation-side improvement to show**, which is
  the honest headline: the rebuild's hoped-for gain did not appear where the product actually ships
  (an answer, not a page list).
- **Ceiling-normalised (§I58), the new index still captures LESS of its headroom**: R@100 **0.7058**
  vs OLD **0.7259**; R@20 **0.4453** vs OLD **0.5275**. §I58's finding — *the index improved and the
  retriever did not capture it* — reproduces on a fresh full run with every lane live.
- **Raw R@100 rose** (+0.0347) while **ranking fell** (MRR −0.1211). More pages are reachable, and
  they are ordered worse. That is §I59's "the loss is masked, not absent" seen end-to-end.
- ⚠️ **The §I55 fallback is real and reported both ways.** gold-004's top-20 is UNRANKED
  (`reranked_metrics_valid=false`, the run exited **3**). Without it (n=132): R@20 0.4282, MRR
  0.7112, Faith 0.6378 — i.e. the fallback query moves the headline by ≤0.003, so **the conclusion
  does not depend on it**. Reported because §I55 says a fallback query must be named, not averaged
  silently.

⚠️ **A consistency worth recording, and NOT an attribution.** §3d (retrieval-only, **dead** DA lane,
**no** RAPTOR) measured NEW R@20 **0.4524**; Phase E (live DA lane **and** RAPTOR) measures **0.4250**
— a fall of **−0.0274**, very close to §I56's independently measured DA-lane effect on top-20 R@20
(**−0.0262**). ⚠️ **But several things changed at once between the two runs, not two** — RAPTOR was
added, the DA lane went live, the **graph lane** went live for multihop, and the §G3 merge landed
(§I57's own list). So this is **consistent with** §I56 and **does not attribute** the drop to the DA
lane; it is the reason §I56's "keep as-is" disposition is worth settling with a **one-variable**
comparison (DA live vs DA off, everything else pinned) rather than left assumed.

**Confounds, all recorded (this is not a clean A/B):** the six §I57 lists, plus this run's own —
visual excluded (§3, matching §D12's effective n=133), a different calendar day, and the §D12 arm's
labels having been built against the deployed index (§D4/§D6).

**✅ INDEPENDENT VERIFIER RAN 2026-10-23 — `openai/gpt-oss-20b`, `deleg_4bdde8d0`,
`status=completed`: 7/7 CONFIRMED, no defects.** Unlike the two cheap verdicts earlier this session
(§I57's 4 calls / 19 s, the harness's 8 calls / 32 s), this one was substantive — **15 API calls,
104.6 s** — and it did the work the claims asked for rather than agreeing: it **counted 133
answerable metrics rows and 34 negatives out of `results` itself**, and **recomputed every overall
mean from `results`**, matching the `aggregated` block exactly (R@100 0.6737, R@20 0.4250, Hit@20
0.9023, Ctx.Prec 0.2421, MRR 0.7059, NDCG@20 0.5050, Faith 0.6368, Ans.Rel 0.8521, Citation 1.000).
It also confirmed gold-004 carries `reranker_fallback=true` with `recall_at_20 0.0`, and listed the
confounds it could see directly in the two artifacts (collection, embedding dimensionality, and the
per-metric deltas). **E5 therefore has a second, independent re-derivation — not just the author's.**

**Register against:** §I57 (the question this answers), §I58 (the ceiling normalisation that carries
the finding), §I56 (the DA-lane effect this is consistent with), §I55 (the fallback it reports),
§I59 (the masked ordering loss), §I63 (the embedder that is the larger half of it).

---

### I65. 2026-10-23 — the §I61 prefetch-limit A/B RAN, and the lever is a NULL at the product endpoint: coverage is not the constraint

**§I61's own gate, discharged.** §I61 found the lever (the 64d prefetch limit, not the MRL dimension,
is what loses pool coverage) and registered it as *"the next lever to test"*, requiring **its own
pre-registered A/B (raise-the-limit vs current, 133 queries, paired, on the product endpoint)** before
it ships, because the sweep behind it was a **40-query screening subsample with no paired CI**.
Pre-registration `.hermes/plans/2026-10-23-p1-i61-prefetch-limit-ab-preregistration.md`, **committed
`e0fed5e` before the run** (the plan file alone, nothing measured — that is the point of it).

**Design (fixed before any number existed).** Four arms, one variable (`cfg.dense_prefetch_limit`),
everything else pinned — same collection, same query file, same 133 answerable text queries, same
query vector (**HyDE off**, so every arm shares one vector), same `mmr_candidates` 100,
`reranker_fetch_k` 100, `reranker_top_k` 20, same reranker, DA lane on:

| arm | limit | role |
|---|---|---|
| **C** | **1000** | control — the shipped value |
| **T** | **2000** | primary treatment |
| **S** | **3489** | sensitivity — every in-window chunk = exact search |
| **N** | 1000 | **negative control** — arm C re-run; **E4 requires it to be bit-exact** |

**The change is config-only** — `cfg.dense_prefetch_limit` (default 1000) read by
`store._qdrant_search`; the outer full-dim re-score cut stays 500 and the inner stage stays the 64d
lane, both **pinned by `tests/test_dense_prefetch_limit.py`** (8 tests; restoring the hardcoded `1000`
fails **5 of 8 on their own assertions**, tree restored byte-identical). No re-ingest, no model
change, no named vector, no Qdrant write.

**Artifacts:** `logs/p1/step10/prefetch_limit_ab.{py,json}`, harness
`logs/p1/step10/run_prefetch_ab.sh` (its resolved-settings gate refuses a blank `QDRANT_HOST`, a
collection other than `knowledge_base_v2`, **and a `dense_prefetch_limit` that is not the shipped
1000** — so arm C cannot silently stop being the production arm), log
`logs/p1/step10/prefetch_ab_run_2026-10-23_0637.txt`. n=133, **0 errors**, 31 min.

**E4 PASSED, and it is load-bearing: 931 metrics compared, 0 mismatches, max_abs_diff 0.0.** With HyDE
off there is no legitimate source of per-query nondeterminism left, so a non-zero N−C would have
voided the A/B. It is exactly zero.

| endpoint | C (1000) | T (2000) | S (3489) | ΔT−C | ΔS−C |
|---|---|---|---|---|---|
| **R@20 (raw)** | **0.431769** | 0.434590 | 0.434849 | **+0.0028** CI [−0.0006, +0.0062] **UNRESOLVED** | +0.0031 CI [−0.0004, +0.0065] **UNRESOLVED** |
| R@20 ceiling-norm | 0.527178 | 0.530172 | 0.530547 | +0.0030 UNRESOLVED | +0.0034 UNRESOLVED |
| R@100 | 0.604785 | 0.606341 | 0.607089 | +0.0016 UNRESOLVED | +0.0023 UNRESOLVED |
| Hit@20 | 0.9173 | 0.9173 | 0.9173 | **+0.0000** | **+0.0000** |
| NDCG@20 / MRR / Ctx.Prec | — | — | — | all UNRESOLVED | all UNRESOLVED |

Win/Loss/Tie T vs C on R@20: **6 / 2 / 125**. Per type, all unresolved (factual +0.0050, multihop
+0.0021, overview +0.0007). **Power is ample, not the limit:** SD_d 0.020013 → the n required for
δ=0.05 is **1**; the effect is ~17× below the project's δ. The cut bites (pool min 63 / median 100
against a top-20 cut).

**The mechanism reproduced at full sample (M1), so §I61's screening was right about the mechanism:**

| 64d lane pool coverage | screening (§I61, 40 q) | full sample (n=133) |
|---|---|---|
| limit 1000 | 0.804127 | **0.815136** |
| limit 2000 | 0.971526 | **0.960627** |
| limit 3489 | 1.0000 | **1.0000** |

**The verdict, per the pre-registered rule: the change does NOT ship and §I61 is recorded
measured-and-unresolved.** A real mechanism (the lane's coverage goes 0.815 → 1.000) with a product
endpoint that does not move (+0.003, CI includes 0). **Coverage is not the binding constraint** — and
that is the finding that matters beyond this lever, because it kills the whole "return more relevant
documents" family of hypotheses for this corpus. §I66 explains mechanistically why the gain does not
propagate, and it also **refutes this entry's own first hypothesis** about where the loss sits.

⚠️ **Not production numbers.** HyDE is off in both arms by design (pre-registration §4), so the
**absolute** values are not the shipped system's; the **delta** is unaffected. Not comparable to §I64's
Phase E table (different run, HyDE on).

**✅ INDEPENDENTLY VERIFIED — 12/12 CONFIRMED, NO DEFECTS.** `openai/gpt-oss-20b`,
`deleg_0296daa3` task 1/2, **15 API calls, 315 s** (a substantive verdict, not a cheap one). It
recomputed every aggregate itself from the per-query array rather than reading the summary block, and
independently re-checked the load-bearing guard:

| claim | verdict | the reviewer's own numbers |
|---|---|---|
| C1 | confirmed | `n_queries` 133, `n_queries_errored` 0, 133 rows |
| **C2 — the negative control** | **confirmed** | **checked programmatically over all 133 rows: every `arms.N.*` equals `arms.C.*` exactly, no mismatches** |
| C3 | confirmed | C 0.431769 · T 0.434590 · S 0.434849 |
| C4 | confirmed | ΔT−C +0.0028 CI [−0.0006, +0.0062] unresolved · ΔS−C +0.0031 CI [−0.0004, +0.0065] unresolved (SD_T 0.020013, SD_S 0.020037) |
| C5 | confirmed | W/L/T 6 / 2 / 125 |
| C6 | confirmed | `hit_at_20` 0.9173 for all three arms; ΔT−C exactly 0 on every query |
| C7 | confirmed | mechanism means 0.815136 · 0.960627 · 1.0000 |
| C8 | confirmed | SD 0.020013; `ceil((1.96·SD/0.05)²)` = 1, arithmetic checked |
| C9 | confirmed | HyDE OFF, `no_llm_calls` true, collection `knowledge_base_v2`, fetch_k 100 / top_k 20 / mmr 100 / outer cut 500 |
| C10 | confirmed | `_qdrant_search` passes `cfg.dense_prefetch_limit`, outer cut stays 500, inner stage stays `dense_64` |
| C11 | confirmed | **ran only `tests/test_dense_prefetch_limit.py`: 8 passed** |
| C12 | confirmed | no row with `n_reachable` 0 or `n_relevant` 0, no null `recall_at_20` |

**Post-review integrity re-checked, as the standing rule requires:** both artifacts are **byte-identical
to their pre-review hashes** (`prefetch_limit_ab.json 395cef8e…`, `rescore_cut_curve.json 038e12ba…`),
the working tree is clean, and `pyproject.toml`/`uv.lock` are untouched — the child's "files modified:
none" is true. ⚠️ **One citation is loose and is not what the entry rests on:** its C10 evidence says
"the argument list to `qdrant.search`", where the code calls `self._qdrant.query_points`. The claim
holds on the source and is independently pinned by the test file; the paraphrase is imprecise, which
is the §I57 lesson again — a verdict's *citation* needs checking even when its *claim* survives.

**Why the route took three attempts, recorded so the next session does not repeat it.** The first two
dispatches died — output-length truncation after reading the 255 KB artifact whole, then
`Unknown role: assistant<|channel|>commentary` (control tokens leaking into the replayed history).
**Neither is a statement about the gateway: the variable is the BRIEF.** Given a compact raw-row
extract (the author's summary block deliberately excluded, so it still had to recompute) and told to
write one script that prints only the aggregates rather than read the artifact into its context, the
same model on the same data returned the full verdict above. §I66's sibling did the same at 6 calls.

**Two supporting checks, neither of which is a second opinion on its own.** (a) An independent
aggregation implementation (manual sums, a different CI formulation, none of the probe's aggregation
code reused) reproduces every summary value from the per-query array — **author checking author, and
labelled as such**. (b) A **single-turn** reviewer on the *method* (no tools, data embedded) confirmed
the design — single-variable, the negative control meaningful, the endpoint right for this lever, no
inert headline, no cross-arm leakage, HyDE-off legitimate — and returned its **silent-failure audit
`unverified`** with three claimed defects, all adjudicated against the artifact: two do **not** occur
(0 rows with `n_relevant == 0`; **0 null metric values** and **every delta denominator == 133**), and
the third (no explicit nondeterminism check) *is* guard E4, which passed bit-exact.
⚠️ **That third concern is registered rather than dismissed**, because it is right in its *concern*
even though the mechanism does not fire here: a null metric value would silently shrink a delta
denominator. The aggregation should count its exclusions. Registered as a hardening item.

**Register against:** §I61 (the lever this closes), §I60 (128d is dead — confirmed from the coverage
side), §I66 (where the loss actually is), §I58 (the ceiling rule), §I44 (an artifact that is not
written up is not evidence), §I25 (a null that reads as a result).

---

### I66. 2026-10-23 — the loss is NOT the prefetch and NOT the re-score cut: it is the 100-slot fusion. A direct (N, L) ceiling, and a refutation of this session's own hypothesis

**Why this exists.** §I65 left the loss between the 64d lane and the funnel's pool unexplained, and
§I65's entry named the **outer full-dim re-score cut** (`limit=500`, hardcoded in
`store._qdrant_search`) as the prime suspect for the 8 queries whose pool held **none** of their
labelled pages even at exact prefetch. **That hypothesis is WRONG, and this probe refutes it.** It
also produces the (prefetch N × re-score cut L) ceiling that the next step needs.

**Method — exact, so it isolates the cut rather than confounding it.** `logs/p1/step10/rescore_cut_curve.py`
→ `rescore_cut_curve.json`. Fetches all **3,489 in-window content chunks / 888 pages** of doc
`7ba61432` with their `dense_1024` vectors, then for each of the 133 queries: the MRL lane's output at
limit N is the **exact brute-force 64d** top-N (so the filtered-HNSW loss — §I60 measured up to
18.5 % — is excluded); the candidate set passed to fusion is the **exact full-dim top-L within it**.
No ANN, no Qdrant scoring, no RRF, no dedup, no MMR. Read-only, no LLM calls, 24 s.
**Cross-check: the SQLite reachable-page set and the collection's page set agree exactly
(symmetric difference 0).**

**Coverage = fraction of a query's REACHABLE labelled pages present in the candidate set:**

| | L=100 | L=200 | **L=500** | L=1000 | L=2000 | L=3489 |
|---|---|---|---|---|---|---|
| N=1000 | 0.5123 | 0.6182 | **0.7478** | 0.8151 | 0.8151 | 0.8151 |
| N=2000 | 0.5127 | 0.6471 | 0.8240 | 0.9157 | 0.9606 | 0.9606 |
| N=3489 | 0.5192 | 0.6488 | **0.8286** | 0.9266 | 0.9773 | 1.0000 |

Production is the bold cell. **Internal consistency, and it is exact:** at N=1000 with L≥N the cell is
**0.8151**, which is §I65's independently measured M1 lane coverage (**0.815136**); at N=3489/L=3489 it
is **1.0000**, M1's exact-prefetch value. The probe reproduces the A/B's mechanism arm from a
different code path — that is what makes the rest of the grid trustworthy.

**At exact prefetch, the cut's own contribution (paired vs L=500):**

| L | coverage | Δ vs 500 | CI95 |
|---|---|---|---|
| 1000 | 0.9266 | **+0.0980** | [+0.0752, +0.1207] RESOLVED |
| 2000 | 0.9773 | **+0.1486** | [+0.1178, +0.1795] RESOLVED |
| 3489 | 1.0000 | **+0.1714** | [+0.1389, +0.2038] RESOLVED |

**⚠️ THE REFUTATION — the 500-cut is NOT what lost the 8 zero-pool queries.** Cell `N3489_L500` per
query, read from the artifact: **5 of the 8 have ALL their labelled pages inside the L=500 candidate
set** — `gold-004` (1.0, best labelled chunk ranks **127th** of 3,489 at full dimension), `gold-013`
(1.0, rank 204), `gold-035` (1.0, rank 108), `gold-052` (1.0, rank 470), `gold-064` (1.0, rank 116);
**2 more are partially inside** — `gold-011` (0.333, rank 23) and `gold-088` (0.5, rank 109); and
**only `gold-078` is entirely lost** (cell 0.0, best rank **1325**). **Yet §I65's pipeline pool held
none of them.** So for **7 of the 8** the cut did not remove the page, and for 5 of those it did not
remove any of their labelled pages. The loss is **downstream of the cut**, in RRF / page dedup / MMR.
⚠️ **An earlier draft of this entry said "6 of the 8 … (cell = 1.0)"; the count and the parenthetical
disagreed with each other.** The precise split is **5 fully / 2 partially / 1 entirely** — caught by
re-reading the cells, not by the reviewer.

**The decomposition this licenses** (all of a query's reachable labelled pages as the denominator):

| stage | production (N=1000) | exact prefetch (N=3489) |
|---|---|---|
| 64d lane | 0.8151 | 1.0000 |
| → after the full-dim **re-score cut** L=500 | 0.7478 | 0.8286 |
| → after the **fusion** (RRF + dedup + MMR to 100) | **0.6048** | **0.6071** |
| → after the cross-encoder to top-20 | 0.4318 | 0.4348 |

**⚠️ And this explains §I65's null mechanistically: at exact prefetch the fusion's own loss GROWS
(0.143 → 0.222).** Handing the fusion more candidates does not grow the pool, because the fusion's
output width (`fetch_k` = 100) does not grow — the extra candidates simply compete for the same 100
slots. **The binding constraint is the 100-slot fusion output, not the prefetch and not the cut.**
Depth histogram, for scale: the query's best labelled chunk sits within full-dim rank ≤100 for
**123/133** queries, ≤500 for **131/133**, ≤1000 for 132/133, ≤2000 for 133/133 (median rank 4, max
1325) — so the cut rarely blocks a *query*, while it costs a large fraction of its *labels* (queries
average 27.3 labels).

**What this licenses, and what it does not.** It licenses a **measurement** of the two downstream
widths — the re-score cut L and `fetch_k`/MMR — as the next lever, and it gives that measurement its
expected ceilings. It does **not** license shipping either: a raised ceiling is not recall, and the
fusion's 0.143–0.222 loss has never been attributed between RRF, page dedup and MMR. **Both are
candidates for a pre-registered A/B on the product endpoint, exactly as §I61's lever was.**

⚠️ **One caveat on the ceiling's meaning.** This is a *page-level* ceiling and the fusion is
*chunk-level* before it dedups pages, so the grid is an upper bound on what a chunk-level cut of the
same size can deliver — not a prediction of the pipeline. The pipeline's own observed value is quoted
beside it above for that reason.

**✅ VERIFICATION — a TOOL-USING reviewer did run in the end, and it recomputed the arithmetic
itself.** The route matters, so it is recorded in full. Two dispatches had died on the gateway's
multi-turn loop (§I65 records the signatures), so the claims were split and re-dispatched as smaller
children told to **write one script that loads a compact raw-row extract and prints only the
aggregates** — never to read the 255 KB artifact. That shape worked:

- **`deleg_e9bd91ca` task 1/2, `openai/gpt-oss-20b`, 6 API calls, 141 s — ALL FIVE CONFIRMED, and
  "None" for what it could not check:** **C1** counts `(3489, 888, 133, 133)`; **C2** the
  SQLite↔collection cross-check `(888, 888, 0)`; **C3** **the entire 18-cell grid recomputed from the
  rows and matching every expected value**; **C4** `0.815136` vs `0.8151` at 6 dp and `1.000000` vs
  `1.0000`; **C9** `nre=0 rows: 0`, `nr=0 rows: 0`, `null cells: 0`. **This is independent
  verification of the grid — not the author's arithmetic.**
- **C7 and C8 have independent verdicts; C5 and C6 do not, and the entry says which is which.**
  - **C7 (the refutation) — CONFIRMED by a single-turn reviewer** (`openai/gpt-oss-20b`, no tools, the
    eight rows embedded): `eq_1.0: 5`, `gt_0: 7`, `eq_0.0: 1`, `lost_ids: ["gold-078"]`,
    `refutation_stands: true`. **It reproduces the corrected split exactly** (5 / 2 / 1) — the same
    numbers the entry quotes, from a source independent of the author's reading of them.
  - **C8 (the method is exact) — CONFIRMED by the single-turn reviewer**: brute-force matrix products
    over fetched vectors; Qdrant used only to fetch; the 64d lane is an exact ranking of a re-normalised
    64-slice. (A later single-turn attempt returned `unverified` for C8 — **the brief's fault, not the
    code's**: a string-substitution bug in the prompt dropped the code block, so the reviewer was asked
    to judge source it had not been given. Recorded because a brief that omits the artifact produces
    `UNVERIFIABLE ×N`, which is no verdict and must not be read as a weakening of the first one.)
  - ✅ **C5 (paired deltas) and C6 (histogram) ARE independently reproduced after all — the reviewer
    did the work and was interrupted before it could report.** Its own script's output was recovered
    from a stray file it left in the repo root (below): `logs/p1/step10/cut_curve_verifier_child_output_2026-10-23.txt`
    (sha256 `faccda90…`). It reproduces **every mean to 1e-17** — 0.0979535789 / 0.1486482556 /
    0.1713906842 / 0.0000000000 — and **C6 exactly** (counts 123/128/131/132/133/133, median 4, max
    1325), and its **C7 per-query values are identical to the artifact's own cells**. So C5, C6 and C7
    all have a source independent of the author.
    ⚠️ **And it exposed a real convention difference worth recording: the CI half-widths disagree by
    exactly the SD convention.** The artifact uses the **sample** SD (`statistics.stdev`, ddof=1); the
    reviewer's script used the **population** SD (ddof=0). Its second number matches the ddof=0
    half-width to 1e-9 (0.0226999571 vs 0.0227857795 at L=1000 — a ratio of exactly √(132/133)).
    ⚠️ **It changes no conclusion, and that was checked rather than assumed:** every L-delta stays
    resolved, and the A/B's tightest interval — ΔT−C, which sits on the zero boundary — includes 0
    under both conventions (sample CI [−0.000601, +0.006201], population CI [−0.000588, +0.006188]).
    The artifact's choice (ddof=1) is the standard one for a paired CI; the reviewer's is not wrong, it
    is a different convention, and the entry now names which is which so the next reader does not read
    a 0.4 % half-width difference as a discrepancy in the means.
  - ⚠️ **Four dispatch attempts at that half failed on environment faults, not substance**:
    control-token corruption (55 s), `interrupted` after 451 s waiting, `interrupted` again after 36
    API calls in 60 s — and the last of those is the one whose output was recovered. Per
    `independent-verification` ("do not loop; change strategy") a fifth attempt was abandoned, and the
    claims are recorded at the strength they actually have.

⚠️ **A PROCESS FINDING, and the check that caught it: the interrupted child wrote THREE files into the
repo ROOT**, against an explicit "do not modify anything under the repo" in its brief —
`test_file.txt` (`'hi'`), `test_root.txt` (`'rootwrite'`) and `write_metrics_output.txt`. The first two
are plainly the child probing whether it could write there at all. **`git status --short` after the
fan-out is what surfaced them**, and without it the child's own report ("files modified: none") would
have been the only evidence — which is the `independent-verification` rule that a child's cleanup claim
is a claim like any other. The two probe files were deleted; the third was **preserved as the evidence
it is** (moved to `logs/p1/step10/`, named above) rather than discarded with the mess.
- **Mechanical, and labelled as author-checking-author:** an independently written aggregation
  reproduces every summary value from the per-query array (grid, all paired deltas, the histogram, the
  counts — 0 mismatches), and the probe re-run after its last edit is **byte-identical**
  (`038e12ba…`). Recorded as mechanical evidence, not as a second opinion.

⚠️ **One earlier reviewer's C7 evidence was sloppy and is NOT what the entry rests on**: it wrote
`gold-004,013,035,052,064,088 have >0; 078,088 have 0`, double-listing `gold-088` and getting the
split wrong in both directions. The per-query cells give **5 at 1.0, 2 partial, 1 at 0.0** — and the
re-dispatch brief now demands the three counts separately rather than a single rounded number.

**Register against:** §I65 (the A/B whose null this explains, and whose hypothesis it refutes), §I61
(the mechanism), §I60 (the ANN loss excluded here by construction), §I58 (the ceiling rule), §I56 (the
DA lane enters the same fusion stage), §I25 (a hypothesis that reads as a finding unless measured).

---

### I67. 2026-10-23 — the downstream-widths A/B is **VOID**: the server Qdrant's filtered ANN is NON-DETERMINISTIC, so the bit-exact negative control is unachievable

**Found by the pre-registered A/B itself, and it is the A/B's own guard that caught it.** The
pre-registration `.hermes/plans/2026-10-23-p1-downstream-widths-ab-preregistration.md` fixed **E4 —
the negative control must be bit-exact — as load-bearing: "if it does not, the instrument is noisy, the
A/B is VOID, and no endpoint is read."** E4 **failed**, so **no endpoint from this run may be read.**

**1. What the run did.** 133 answerable text queries, six arm-configurations, on the product retrieval
path (`store.search_with_das` + the shipped cross-encoder + `evaluate_rag.compute_retrieval_metrics`),
`knowledge_base_v2`, HyDE off, prefetch pinned at 2000, `da_fetch_k` pinned at 100. Two new settings
(`dense_rescore_limit` = the re-score cut L; `da_fetch_k` = the DA lane's depth, decoupled from
`fetch_k`) and the fusion width **W** = `mmr_candidates` **and** `reranker_fetch_k` moving together
(§I66's binding constraint — raising either alone does not widen the fusion; pinned by
`tests/test_downstream_widths.py`, 17 tests, mutation-proven: hardcoding the cut fails 2, recoupling
the DA lane fails 1). Harness `logs/p1/step10/downstream_widths_ab.py`, verifier
`…_verifier.py`, artifact `logs/p1/step10/downstream_widths_ab.json`, log
`…_run_2026-10-23_2138.txt`. **~65 min wall** (not the ~45 estimated), with one transient ~24-min
cluster stall (60→70 queries) that recovered.

**2. ⚠️ E4 FAILED — and it is REPRODUCIBLE, not a blip.** 1,064 metrics compared, **2 mismatches,
max_abs_diff 0.0**: on `ovw-041` arm C's pool is **95** and arm N's is **94** (one chunk). **Every
metric is bit-exact** — only the pool *size/pages* differ. The diagnosis:

| probe | result |
|---|---|
| the C config, `search_with_das`, `ovw-041`, **6 identical repeats** | pools **95, 95, 95, 94, 94, 95** — two distinct chunk sets |
| `search_da` alone, 6 repeats | **6/6 identical** — the DA lane is deterministic |
| `search()` (the dense funnel) alone, 6 repeats | **1 of 6 differed** — the funnel is the non-deterministic part |
| SPLADE encode ×6 · ColBERT encode ×6 · dense encode ×6 | **6/6 identical each** — all three cluster encoders are deterministic |

So the query-side vectors are stable and the DA lane is stable; the wobble is on the **Qdrant side**:
the **filtered ANN prefetch** (`dense_64` → `dense_1024`, with the `is_content` payload filter) returns a
marginally different candidate set run-to-run. That is the server's HNSW/segment behaviour, outside our
code — and §I60 already measured up to **18.5 % HNSW loss** on this collection, so a marginal
candidate-set wobble is the same mechanism, one order smaller.

**3. ⚠️ The consequence is general, not local to this A/B.** A bit-exact negative control **cannot be
guaranteed on this cluster** while the ANN is non-deterministic. §I65's identical structure **passed**
bit-exact at 133 queries — so that pass was **not a property of the instrument**, and any future A/B
that relies on it inherits this risk. **This is the §I44 class in the measurement layer: a guard that
passed once is not a guard that holds.**

**4. The endpoints are recorded but MUST NOT be read** (pre-registration §6). For the record only, so
the next reader does not re-derive them and mistake them for findings — the shape is *two nulls*:
Δ R@20 ceiling-normalised **W1−C +0.0032** CI [−0.0164, +0.0227] UNRESOLVED; **W2−C +0.0027**
[−0.0171, +0.0224] UNRESOLVED; **L1−W2 +0.0029** [−0.0021, +0.0078] UNRESOLVED; **L2−W2** identical to
L1 (the cut saturates). Power was ample, not the limit (SD_d 0.115 → required n for δ=0.05 is **21**;
the effect is ~15× below δ). Secondary, and equally unread: **MRR RESOLVES POSITIVE** for the width
(+0.0935 [+0.0559, +0.1311]) while **context_precision RESOLVES NEGATIVE** (−0.0075 / −0.0083) — the
same "a wider pool reorders the pool, not the product" shape §I65 warned about. ⚠️ **None of this is a
result**; it is what a VOID run's numbers look like, quoted so they are not quoted as findings.

**5. ⚠️ A design finding that survives the VOID: the cut is INERT at the shipped width.** A smoke test
measured Δ **exactly 0.0000**, W/L/T **0/0/3 identical**, when the cut arms ran at the shipped
**W=100** — because the fusion emits only 100 candidates, so raising L merely reshuffles candidates far
below the cut. The cut was therefore re-registered (before the run) to run at **W=500** and be read
against **W2**, where it can express; the pool then moved (W2 325 → L1 325 chunks but the **page set**
changed, E7 `cut_moves_pages: True`). **The measurement lesson stands independent of the VOID: a knob
downstream of a saturated cut is inert by construction (§G1's defect), and testing it requires the
upstream width to admit it.**

**6. Two transient cluster faults, both survived** (recorded, not defects): a
`_collection_vectors` inspection **timeout** at 22:02 (schema assumed, run unaffected), and one
**`RERANKER DISABLED` ReadTimeout** at 22:22 (§I55) — **rescued by the harness's one-shot identity
retry**, so the artifact's fallback counts are **0 in every arm**. ⚠️ That retry is a deliberate
difference from §I65's harness (which flagged any fallback): here a *transient* fallback that succeeds
on retry is not flagged, so "0 fallbacks" means "no query was left unranked", not "no fallback fired".

**7. ⚠️ A PROCESS DEVIATION, recorded because it cannot be inferred from git.** The pre-registration was
committed **together with the results** (owner decision), **not alone before the run** as §I65's was.
Git therefore does **not** prove the file predated the numbers; the file's content and the plan's §1.3
are unchanged since before the run, and this note is the record of the ordering.

**8. Disposition: VOID, and the next move is a RE-REGISTRATION, not a re-run of this one.** The A/B as
pre-registered cannot pass E4 on this cluster, so re-running it unchanged would reproduce the failure.
Two honest options, both requiring a NEW pre-registration: (a) define E4 against a **measured noise
floor** — the negative control repeated *k* times to establish the instrument's own spread, with the
endpoint compared to that floor; or (b) run the A/B with the ANN forced to **exact search** so the
control is deterministic, **declared as a change to the retrieval path** (it is then not the product
path). ⚠️ **Do not relax E4 after the fact** — that is exactly the post-hoc interpretation §D1's rule
exists to prevent, and the reason the endpoints above are quoted as unread.

**Register against:** §I66 (the lever this A/B was built to test, and the binding constraint it named),
§I65 (the identical harness that passed E4 — and why that pass was not a guarantee), §I60 (the measured
HNSW loss, the same mechanism), §I58 (the ceiling rule), §I56 (the DA lane — decoupled here), §I55 (the
reranker fallback, rescued and counted), §I44 (an artifact/guard that passed once), §D1 (pre-registration).

---

### I68. 2026-10-24 — ⚠️ **Qdrant's server-side RRF fusion is NON-DETERMINISTIC** — the same query returns a different candidate set on consecutive calls (a product defect, and the root cause of §I67's VOID)

**Found while root-causing §I67** (the downstream-widths A/B that failed its bit-exact negative control).
It is recorded separately because it is **not a property of that A/B** — it is a property of the
retrieval funnel the product ships, and it stands on its own.

**1. The measurement — lane by lane, 6 identical repeats each, same query vector:**

| query | `dense_64` ANN | `sparse` ANN | `colbert` ANN | **server-side RRF (all three fused)** |
|---|---|---|---|---|
| `ovw-041` | 1/6 distinct | 1/6 | 1/6 | 1/6 |
| `gold-004` | 1/6 | 1/6 | 1/6 | **5/6** |
| `gold-078` | 1/6 | 1/6 | 1/6 | **3/6** |
| `gold-052` | 1/6 | 1/6 | 1/6 | **6/6** |

**Every individual lane is perfectly deterministic** — including under `search_params=SearchParams(exact=True)`
and `hnsw_ef=512`, which changed nothing. **The non-determinism is in `FusionQuery(fusion=Fusion.RRF)`
itself**: identical inputs, identical lane results, and `gold-052` returned **six different fused
candidate sets in six runs**. The query-side vectors are not the cause either — SPLADE, ColBERT and the
dense encoder each hashed **6/6 identical** on the same text.

**2. How far it reaches downstream — measured, and it is usually absorbed.** The fusion feeds page
dedup → MMR → the cross-encoder, and most of the wobble dies there:

| probe | result |
|---|---|
| 30 queries × **4 repeats** of the shipped config, `search_with_das` + rerank + metrics | **R@20 ceiling-normalised spread max 0.000000**, pool-size spread **0** — 0/30 queries differed |
| the §I67 run's 1,064 arm-C-vs-arm-N comparisons | **0 metric mismatches**, max_abs_diff **0.0**; only `n_pool`/`n_pages` differed, on **1** query (`ovw-041`: 95 vs 94) |

So the defect is **sparse** — it bites a minority of queries, and on the endpoint it usually leaves no
trace. **But it is not always absorbed** (`ovw-041` moved the pool by a chunk), and **it made a
pre-registered A/B unreadable** (§I67). ⚠️ **The lesson: a retrieval path that is not reproducible
cannot support a bit-exact control, and "the metrics happened to match" is not the same as "the
instrument is deterministic".**

**3. Why it is a PRODUCT finding, not just an eval one.** The same query, issued twice, can retrieve a
different candidate set. On this corpus the effect is small and usually invisible at top-20, but it is
**unbounded in principle** (nothing in the code bounds it), it makes **any** A/B on this path depend on
a tolerance rather than an equality, and it is the kind of thing a reviewer of a "hybrid RAG platform"
will ask about. It is not caused by our code and cannot be fixed by a setting we control.

**4. The in-repo fix path — and it already exists.** `store._rrf_merge` (client-side reciprocal rank
fusion, `store.py`) is present and used elsewhere. **Moving the dense funnel off Qdrant's server-side
`FusionQuery` and onto the client-side merge would make the funnel deterministic** — the lanes are
already deterministic, so fusing them in Python removes the only non-deterministic step. ⚠️ That is a
**change to the product path** (the ranking may differ slightly at ties), so it needs its own
before/after comparison and its own register entry — **not** a silent swap to make an A/B pass.
⚠️ **Do not** reach for `exact=True` as the fix: the probe above shows the ANN is already deterministic,
so it changes nothing about this defect.

**4a. THE BLAST RADIUS — MEASURED 2026-10-24 (session 16). It is NOT a one-file no-op, and two
"obvious" readings of it are wrong.** An independent read-only reconnaissance was dispatched for this
fix; ⚠️ **it under-reported the blast radius in both directions below, and its claims were re-checked
against the source before being recorded here** (the standing rule: a delegated check is a self-report).

* ⚠️ **Server-side RRF is NOT only in `store.py`.** `FusionQuery(fusion=Fusion.RRF)` is also called by
  `scripts/funnel_boundary_recall.py:249` and `:279`, and by `scripts/why_colbert.py:84`.
  `funnel_boundary_recall.py` is **the harness §I68's own 23-query pinned-HyDE measurement ran
  through** — so the instrument that measured the nondeterminism **shares it**, and an A/B of this fix
  must decide explicitly whether the harness moves with the product or is pinned as a before-arm.
* ⚠️ **There ARE unit tests on this path — the recon reported there were none.** Both
  `tests/test_dense_prefetch_limit.py:51` and `tests/test_downstream_widths.py:55` call
  `store._qdrant_search(...)` **directly** and assert on the very `Prefetch` structure the swap removes
  (`test_dense_prefetch_limit.py:61-65` asserts `prefetch[0].prefetch`). So the fix **breaks them by
  construction** — and they are precisely the tests that pin §I61's `dense_prefetch_limit` and §I67's
  downstream widths. They must be **rewritten to assert the new call shape**, not deleted.
  `tests/test_backmatter_gate.py:114,146` also monkeypatches `_qdrant_search` (signature-level only).
* ✅ `_rrf_merge` itself is a pure, deterministic `@staticmethod` (`store.py:635-656`) with **four
  existing tests** (`tests/test_phase_a.py:16-53`) and **no production caller** — so wiring it in is a
  genuine change of behaviour, not a call to something already exercised.
* ⚠️ **A semantic difference to check before the swap, not yet measured:** `_rrf_merge` keeps each
  chunk's **best raw `score` across lanes** (`store.py:649`). Raw scores from different lanes are **not
  comparable** (dense cosine vs ColBERT MaxSim vs sparse dot product), whereas Qdrant's server-side RRF
  never surfaces that comparison. Downstream, `_mmr_select` consumes `rrf_score` **or** `score`
  (`store.py:666`). What MMR actually receives after the swap is a question the before/after must
  answer — recorded as **to check**, not as a proven defect.

**5. Disposition.** Registered, **not fixed**. The §I67 re-run proceeds with **E4′ (metrics-only)** —
which is a *disambiguation* of the original pre-registration's wording, justified by the measured
zero metric-floor, **not** a fix for this defect. This entry is the standing record that the funnel is
non-deterministic until the client-side merge lands.

**Register against:** §I67 (the VOID it caused, and the A/B it blocked), §I60 (the measured HNSW loss —
a *different* mechanism, and the reason "exact search" was the wrong first guess), §I66 (the fusion
stage), §I44 (a guard that passed once is not a guard that holds), §D1 (pre-registration).

---

### I69. 2026-10-24 — ⚠️ `ndcg` comes back as **`np.float64`**, and numpy scalars do not survive JSON — so an eval artifact's summary is NOT re-derivable from its own per-query array at rounding ties

**Found by the E5 guard of the §I67 re-run, which FAILED** while every endpoint re-derived exactly. It
is the §I57/§I44 class — an artifact whose summary cannot be reconstructed from its own data — and the
cause is a type leak, not a wrong number.

**1. The symptom.** `downstream_widths_ab.py --recheck` re-derives the whole summary from the
artifact's own per-query array and compares it byte-for-byte. It reported `DIFFERS` on **`by_type`**,
on **3 keys**:

| key | stored (the run) | re-derived (from the artifact's array) |
|---|---|---|
| `by_type[multihop].ndcg_at_top_k__C` | 0.496002 | 0.496003 |
| `by_type[multihop].ndcg_at_top_k__N` | 0.496002 | 0.496003 |
| `by_type[overview].ndcg_at_top_k__L2` | 0.461548 | 0.461547 |

**Every `all_queries` aggregate — i.e. every endpoint — re-derived byte-identically.** Only this one
secondary metric, only in the per-`query_type` cut, differed, by **1e-6**.

**2. The cause, measured.** Both means sit **exactly on a 6th-decimal tie** (`repr(mean) == 0.4960025`
and `0.4615475`), and the two sides round it **oppositely**:

```
mean over np.float64  -> round(x, 6) = 0.496002      <- what the RUN stored
mean over python float -> round(x, 6) = 0.496003     <- what re-derivation gets
```

`evaluate_rag.compute_retrieval_metrics` returns **`ndcg` as `np.float64`** — it sums
`g / np.log2(i + 2)` — while **every other metric is a plain Python `float`** (verified: `ndcg_at_20`
→ `float64`, all others → `float`). ⚠️ **`np.float64` IS a subclass of `float`**, so `json.dumps`
serializes it **silently** and the type is **lost on read**; re-derivation therefore aggregates plain
floats, and numpy's `round(np.float64, 6)` and CPython's `round(float, 6)` disagree at a decimal tie.
The run's summary was computed over `np.float64`; the re-derivation over `float`. **Same numbers, two
rounding conventions.**

**3. Why it matters beyond this artifact.** Any eval artifact that stores a `ndcg`-derived aggregate
inherits this: **the summary is not a function of the file.** A reviewer who re-derives from the
per-query array — which is exactly what E5 and §I57 exist to enable — gets a different number at any
tie, with no way to tell a tie from a real discrepancy. It also means `json.dumps` **silently accepts
numpy scalars**, so a type leak like this cannot surface as an error anywhere. ⚠️ **It is benign for
conclusions here** (1e-6, one secondary metric, no endpoint affected) — but it is exactly the kind of
"the artifact is not what it claims" defect §I44 records, and it made a guard fail.

**4. Fixed at the point of record.** `downstream_widths_ab.py` gains `_f()` — `float(x) if x is not
None else None` — applied to **every** metric as it is recorded, so the per-query values and the summary
are both plain Python floats and the artifact is self-consistent. ⚠️ **The fix requires a RE-RUN to
produce a clean artifact**: the existing artifact's summary was written by the old path, so its 3 tie
values remain numpy-rounded and will still not re-derive. The *conclusion* (both levers are nulls, §I67)
does not depend on them — it rests on `all_queries`, which re-derives byte-identically.

**5. The general rule.** **Coerce numpy scalars to Python floats at the point of record, in any eval
harness.** `np.float64` passes `isinstance(x, float)`, so nothing will stop it; and the failure mode is
silent, tie-only, and breaks the artifact's self-consistency rather than any single number.

**Register against:** §I57 (the per-query-JSON twin, whose whole purpose is re-derivability), §I44 (an
artifact that is not what it claims), §I67 (the re-run whose E5 caught it), §I25 (a silent failure that
reads as success).

---

### I70. 2026-10-24 — the EMBEDDER SCREEN: `google/embeddinggemma-300m` PASSES the pre-registered rule. It beats BOTH the incumbent (Qwen3-1024) and §I63's Nomic-768 — on an ORACLE instrument, so this licenses a re-ingest decision, not a ship

**The question.** §I63 showed the embedder is the larger half of §I59's full-dimension ranking loss
(Nomic-768 beat Qwen3-1024 by **+0.1400** ceiling-normalised R@20 on this corpus). The plan's §1 turns
that into a decision: **screen the candidate embedders cheaply, on an oracle, before costing a
re-ingest.** Instrument: §I63's cross-embedder experiment, extended — hold the corpus fixed (new doc
`7ba61432`, **3,489** in-window chunks), swap only the embedder, **exact brute-force cosine** over the
whole corpus (page-deduped; **not** Qdrant, because §I60 measured up to **18.5 %** of the pool lost to
the filtered-HNSW path), 133 gold queries, endpoint **paired ceiling-normalised R@20** (§I58).
**HyDE OFF** — raw query vectors, so the comparison is not confounded by the generator. No LLM calls,
no writes.

**Artifacts.** Probe `logs/p1/step10/embedder_screen.py` (**sha256 `13f90fae…`**); artifact
`logs/p1/step10/embedder_screen.json` (**sha256 `990e400f…`**, wall **252 s** on the final run);
independent aggregation `logs/p1/step10/embedder_screen_verifier.py`; reviewer pack
`logs/p1/step10/embedder_screen_verifier_extract.json`.
⚠️ **The run is throughput-dependent, not broken:** the gemma re-embed of the same 3,489 chunks took
**66 s**, then **1,074 s** (cluster contended), then **73 s** — a **16×** swing on identical work.
`meta.embed_seconds` records which. The measured numbers were identical across all three runs.

**Candidates — each at ITS OWN smallest trained MRL slot AND at full dim** (owner decision 2026-10-23:
do not force a fixed 64d), plus the incumbent's 64d lane as a reference arm:

| arm | model | native / low slot | ceiling-norm R@20 | R@100 | R@500 |
|---|---|---|---|---|---|
| `qwen3@1024` *baseline* | `Qwen/Qwen3-Embedding-0.6B` (incumbent) | 1024 / 32 | 0.293934 | 0.569074 | 0.922982 |
| `qwen3@64` (reference) | ″ | — / 64 | 0.102763 | 0.358682 | 0.788671 |
| `qwen3@32` | ″ | — / 32 | 0.075134 | 0.251154 | 0.757741 |
| `nomic@768` *baseline* | `nomic-ai/nomic-embed-text-v1.5` | 768 / 64 | 0.433930 | 0.628993 | 0.927347 |
| `nomic@64` | ″ | — / 64 | 0.364342 | 0.569055 | 0.916027 |
| **`gemma@768`** | **`google/embeddinggemma-300m`** | **768 / 128** | **0.480410** | **0.704882** | **0.946105** |
| `gemma@128` | ″ | — / 128 | 0.410032 | 0.615558 | 0.913470 |
| `mpnet@768` | `tomaarsen/mpnet-base-nli-matryoshka` | 768 / 64 | 0.306226 | 0.497232 | 0.859879 |
| `mpnet@64` | ″ | — / 64 | 0.253096 | 0.422891 | 0.796950 |

**The pre-registered rule, applied mechanically** (a candidate must beat **BOTH** baselines on paired
ceiling-normalised R@20 with a CI excluding 0 — nomic is in the comparison because it already beats the
incumbent, so losing to nomic is not an improvement):

| arm | Δ vs `qwen3@1024` | Δ vs `nomic@768` | beats both? |
|---|---|---|---|
| **`gemma@768`** | **+0.186476 [+0.133280, +0.239672]** W/L/T **78/12/43** | **+0.046480 [+0.016960, +0.076000]** W/L/T **52/19/62** | **✅ PASSES** |
| `gemma@128` | +0.116098 [+0.066087, +0.166109] | −0.023898 [−0.053772, +0.005976] *straddles 0* | ❌ |
| `nomic@64` | +0.070408 [+0.018394, +0.122421] | −0.069588 [−0.098859, −0.040317] | ❌ |
| `mpnet@768` | +0.012292 [−0.043602, +0.068187] *straddles 0* | −0.127704 [−0.164277, −0.091130] | ❌ |
| `mpnet@64` | −0.040831 [−0.098377, +0.016715] | −0.180830 [−0.226113, −0.135547] | ❌ |
| `qwen3@64` | −0.191171 [−0.244010, −0.138332] | −0.331167 [−0.391207, −0.271127] | ❌ |
| `qwen3@32` | −0.218800 [−0.271065, −0.166535] | −0.358796 [−0.419999, −0.297593] | ❌ |

**`gemma@768` is the only arm that passes, and it passes on both contrasts with room.** It is
**+0.0465 over the best known embedder on this corpus**, and that delta is **~2.3× the §0 resolution
floor** (~0.020), so it is not a rounding-scale result — it is 52 queries better against 19 worse.
**`mpnet` behaves exactly as predicted** (NLI-trained, not retrieval): it does not beat the incumbent,
and its own-slot variant is worse still.

⚠️ **What this does NOT license — a ship.** It is an **oracle**: exact cosine over the whole corpus,
not the funnel. Per the plan §3 it licenses exactly two things: (a) **costing the re-ingest**
(58.6 min ingest + 8.9 h cards + 1 h 6 m graph + `derivative_artifacts` 73,406 + `concept_embeddings`
7,427 + the intent classifier + RAPTOR + ColPali + §I58's `_REPOINT` map — a new embedder means new
chunk ids, so **all** of it), and (b) **ONE** pre-registered product-endpoint run with HyDE on and
frozen. Both are **owner decisions, not taken here**.

⚠️ **The 64d problem is the adoption cost, and it is real.** EmbeddingGemma has **no 64d slot** — its
smallest trained MRL dim is **128**. The funnel's fast first stage is `dense_dim_low = 64`, so adopting
gemma means **a new named vector at 128 and a re-index of every collection** — and at 128 the model is
**not** better than nomic at 768 (−0.0239, unresolved). So the win is at **full dimension (768)**;
the low lane would have to change width as well as model. `qwen3@32` (the incumbent's own smallest
trained slot) is **much worse** than its 64d lane (0.0751 vs 0.1028) — the plan's "do not force a fixed
64d" decision cuts both ways.

⚠️ **One asymmetry, recorded not hidden.** The incumbent arm ranks the vectors **stored in Qdrant**,
which the production ingest produced **with late chunking** (the per-token mean over the parent
context); every other arm embeds the chunk text directly, **without** late chunking. So the comparison
is **conservative for the candidates** — gemma beats a late-chunked incumbent while not having late
chunking itself. ⚠️ It cuts the other way for a candidate that *loses*: it may be losing to late
chunking, not to the model. §I63 carried the same asymmetry for nomic. **Not measured here:** whether
late chunking helps or hurts each of these models.

⚠️ **A truncation check, because gemma has a 2048-token window.** Measured on the corpus
(`meta.chunk_char_stats`): median **457** chars, p90 **959**, max **2,949** ⇒ **max ≈ 655 estimated
tokens** (chars / 4.5, §I52's measured chars-per-token on real physics text) and
**0 of 3,489 chunks** over gemma's window. Truncation is not a confound here.

⚠️ **A REGISTERED FINDING, not measured by this screen — the project's Nomic MRL truncation may not be
Nomic's.** `embedder.NomicEmbedder._truncate` (and `cluster_embedder.mrl_slice`) is a **plain slice to
the first `dim` coordinates + re-normalise**. Nomic's own model card for `nomic-embed-text-v1.5`
prescribes **`F.layer_norm(x, (768,))` over the FULL 768 dims first, then the slice, then
`F.normalize`** — i.e. a layer-norm before truncation. Those are different functions, so **every
Nomic-64d number in the register (§I59's `new_mrl64` / `old_mrl64`, and `nomic@64` here) is measured
under the project's convention, not Nomic's.** It is stated as a discrepancy between two sources, not
as a measured effect: the layer-norm variant would need the **un-normalised** pooled vectors, which the
cluster does return but this probe discards. **Do not "fix" `_truncate` without re-measuring** — §I59's
registered rows were produced with the current convention.

**Verifiers — all eleven pass, and four of them are EXACT reproductions of rows registered by earlier,
separate experiments.** That is what makes the baselines comparable rather than merely plausible.

| # | check | result |
|---|---|---|
| V1 | the cluster is a generic passthrough: the prefix changes the vector for every prefixed model, vectors depend on the text, and nomic reproduces the **local** `NomicEmbedder` | doc cos **1.000000** / query cos **1.000000** (raw 0.937749) — §I62's prefix trap, confirmed live in the run that depends on it |
| V2 | **A-vs-A negative control** — nomic re-embedded at batch 128 vs 64 | **max_abs_diff 0.0**, 0 mismatches |
| V3 | `qwen3@1024` reproduces §I60's d=1024 row exactly (every-chunk pool) | R@20 0.293934 · R@100 0.569074 · R@500 0.922982 · R@1000 1.0 — all exact |
| V4 | `qwen3@1024` reproduces §I59's `new_fulldim` exactly (top-1000 pool) | R@20 0.293934 · R@100 0.569074 · R@500 0.922421 · R@1000 0.926563 — all exact |
| V5 | `qwen3@64` reproduces §I59's `new_mrl64` exactly | R@20 0.102763 · R@100 0.358682 · R@500 0.788044 · R@1000 0.815136 — all exact |
| V6 | every arm ranks one shared `pages` array; n_relevant identical across all 9 arms | pool 3,489; pages sha256 `0ca575fabc5c59be` (the same array §I63 used) |
| V7 | errors reported, never silently dropped | 0 errors, 133 queries kept |
| V8 | slice sanity — each low-dim vector is unit-norm and the exact truncation of its full vector | max norm error 4.8e-12; `is_exact_truncation` true for all 5 |
| V9 | the endpoint ignores `dimensions` | asked 128, got the native dim on all four models |
| V10 | all four models served at their expected native dims | qwen3 1024 · nomic 768 · gemma 768 · mpnet 768 |
| V11 | `nomic@768` reproduces §I63's arm N exactly | R@20 0.433930 · R@100 0.628993 · R@500 0.927347 — all exact |
| V12 | **the INCUMBENT's** query path applies `cfg.query_instruction` — the one prefix nothing else asserted (V1 skips qwen3) | production path == `instruction + text` at cos **1.000000**; raw (no instruction) cos **0.818934**, so the instruction is load-bearing |

**Two further pieces of mechanical evidence, kept separate from any verdict** (the author checking the
author, per the standing rule):
1. **The whole screen was run THREE times and all three artifacts agree exactly** — `arms`,
   `endpoints`, `decision` and all 133 per-query `arms` blocks are identical across every run. That is
   an A-vs-A across runs, and it extends V2's batch-invariance to the gemma arm (which V2 does not
   cover, since V2's control is nomic). ⚠️ The **wall time varied 5×** across those runs on identical
   work (see the artifacts note above) — which is exactly why the throughput is recorded and the
   numbers, not the clock, are the evidence.
2. **The artifact's summary re-derives from its own raw per-query array, 0 mismatches.**
   `embedder_screen_verifier.py --check` is a **second, independently written** aggregation — stdlib
   only, no numpy, different code shape, reading only the raw array — and it reproduces every
   aggregate, every endpoint and every decision field. ⚠️ §I69's float leak does not apply here: the
   probe records through `round(..., 6)` on Python floats only.

**✅ INDEPENDENT VERIFIER RAN 2026-10-24 — `openai/gpt-oss-20b`, `deleg_1dd4aa6a`,
`status=completed`: 10/10 CONFIRMED, and its one finding is REAL.** ⚠️ **But it was cheap — 4 API
calls, 39 s** — so per the standing rule it is **not banked**: the substantive half is the mechanical
evidence above (three identical runs, the independently written aggregation at 0 mismatches, four exact
reproductions of registered rows), and the reviewer's citations were checked before its verdict was
used. Every identifier it cited resolves (`V1_cluster_is_a_passthrough`, `V2_A_vs_A_control`,
`V3`/`V4`/`V5`/`V11`, `rank_pages`, `scroll_pool`, and the verifier's `recompute` / `diff_report`), and
its model is read from the run's `manifest.json`, not from a note.

**Its finding, adjudicated as ACCEPTED AND FIXED — V1 skips qwen3, so the INCUMBENT's query-side
prefix was the one prefix no guard asserted directly.** V1 deliberately skips qwen3 (its *document*
vectors are the stored index vectors, not a cluster call), and that left `cfg.query_instruction` on the
query side of the baseline everything is compared against unasserted: a silent change there would have
moved the baseline with no guard failing. ⚠️ It was in fact pinned **indirectly** — V3/V4/V5/V11
reproduce four rows produced by *other* scripts through that same `embed_query` path, so a change would
break all four — but **indirect is not asserted**, so the fix is a direct one: **V12** asserts
`embed_query(text)` equals the cluster embedding of `instruction + text` (cos **1.000000**) and that
the instruction is load-bearing (raw cos **0.818934**). The screen was re-run so the artifact is
self-consistent with the probe revision that produced it.

**Cost:** no LLM calls, **no writes** to any collection; 252 s wall on the final run, of which the
gemma re-embed was 73 s — ⚠️ but that same step took 1,074 s under cluster contention, so the cost is
throughput-dependent and `meta.embed_seconds` records which run it was.

**Register against:** §I63 (the instrument and the +0.1400 this supersedes as the best-known), §I59/§I60
(the rows V3/V4/V5 reproduce), §I58 (the ceiling rule), §I62 (the prefix trap V1 confirms), §I52 (the
chars-per-token constant used for the truncation check, and the "measure the model the phase runs"
rule), §I67/§I68 (the widths chain this is the successor to), §0 of the plan (explore cheap, confirm
powered), §I69 (the float leak that does not apply here).

### I71. 2026-10-24 — the CONTENT FILTER is a NULL on base-lane page ranking, and the reason is structural: the content window already excludes 244 of the filter's 263 rejects. The first run went VOID on a PRE-REGISTRATION PREMISE ERROR (a corpus count written into a guard about a window-filtered pool)

**The question.** §I63's 0.0648 residual (Nomic, old corpus → new corpus) mixes **three** things —
the chunking, the content-filter state, and the chunk count — and none had been isolated. This is
**arm 1**, and it isolates the **content-filter state**, because that is the one of the three that can
be varied with **no parse, no re-chunk and no re-embed**: the §I39 filter changes *which chunks are in
the candidate pool*, over vectors already stored.

**Pre-registration:** `.hermes/plans/2026-10-24-p1-chunking-filter-ab-preregistration.md`, committed
**alone** as `aa4b55b` before the harness existed. **Re-registration:**
`.hermes/plans/2026-10-24-p1-chunk-filter-ab-reregistration.md` (written after the first run, before
the second — §I67's E4 → E4′ precedent). The pre-registration was **not edited**; editing it after the
run started would have voided the run by its own terms.

**The design.** Two arms over the SAME stored vectors, the SAME 133 gold queries and the SAME metric
code — the pool filter is the only variable:

| arm | pool |
|---|---|
| **C** (control) | the shipped filter: `is_content is not False` **and** page inside the content window `[30, 936]` — §I70's pool, **3,489** chunks |
| **T** (treatment) | `C` **minus** every chunk the **CURRENT** `content_filter.is_content()` rejects **when run over the chunk TEXT** — **19** chunks |

⚠️ **The treatment is computed from the TEXT, not from the stored `is_content` column** (guard C4):
the stored column is **STALE** — it is written at ingest and the §I39 extension landed after both
ingests — and reading it would have produced a **5-chunk** treatment and a near-null.

Endpoint: **paired, ceiling-normalised R@20, arm T − arm C, n = 133** (§I58's rule), primary embedder
**gemma@768** (the §I70 winner), secondary **qwen3@1024** (free — the stored vectors). HyDE OFF, no LLM
calls, no writes. Rule, fixed before the run: **attributable iff the 95 % CI excludes 0**; otherwise
the honest statement is a **RESULT** of no movement, not an unresolved one.

**Artifacts.** Harness `logs/p1/step10/chunk_filter_ab.py`; artifact
`logs/p1/step10/chunk_filter_ab.json` (**sha256 `4e64f1ac07dbfda7ad4ce8485c9fad45fe180ed90248232aa578a28072607de2`**,
wall **176.4 s**; gemma embed 61.7 s + control 72.4 s); independent aggregation
`logs/p1/step10/chunk_filter_ab_verifier.py`; reviewer pack
`logs/p1/step10/chunk_filter_ab_verifier_extract.json`; run log
`logs/p1/step10/chunk_filter_ab_run_session15.txt`. **The VOID first run is preserved** as
`logs/p1/step10/chunk_filter_ab_firstrun_VOID.json` (sha256 `0b25fd3467d68c8244efc38c1406f64f9554c81836ad67a067829da4bc584916`).

#### THE HEADLINE — the pre-registration's premise was wrong, and the correction IS the finding

The pre-registration's **F1** recorded *"the CURRENT filter would exclude 263 (6.9 %)"* for the new
corpus and built guards on it. Measured over the collection's **3,796 chunks**, that 263 is right —
but it is a **WHOLE-CORPUS** count, and this arm's pool is the **content window**:

| band | chunks | pages | in the pool (pages 30–936)? |
|---|---|---|---|
| TOC | 72 | 22–34 | **19** (pages 30–34 only) |
| index | 186 | **937–968** | **0** — entirely above the window's 936 |
| front matter | 5 | **2–14** | **0** — entirely below the window's 30 |
| **total** | **263** | | **19 in, 244 out** |

So the treatment is **19 chunks, not 263** — **the window bounds already exclude 93 % of what the
filter would have removed from the base lane.** ⚠️ **§I39's premise is true of the CORPUS and false of
the BASE LANE.** The ~5,100 junk *cards* §I39 measured come from the **card generator**, which does
**not** apply the window bounds — the retrieval lane does. The filter's marginal reach on the base
lane is therefore **structurally capped at 19 chunks**, which is why a null here was close to
predictable in advance and why the *size* of the lever, not just its sign, is the result.

⚠️ **F2's "pages with chunks 933" is also wrong:** §I70's own artifact records `reachable_pages: 888`,
and this run measures **888** from two independent directions that agree exactly (guard **X1** — the
distinct pages present in the Qdrant pool, and §I58's `reachable_pages()` over SQLite).

#### THE FIRST RUN WAS VOID (C2, C4, C3)

| guard | registered | measured | verdict |
|---|---|---|---|
| **C1** | arm C reproduces §I70's qwen3@1024 row exactly | R@20 0.293934 · R@100 0.569074 · R@500 0.922982 · R@1000 1.0 | ✅ PASS |
| **C2** | treatment pool == C − flagged; flagged == **263**; bands 72/186/5 | flagged **19**; bands **19/0/0** | ❌ **FAIL** |
| **C3** | A-vs-A: arm C byte-identical on a re-embed | vectors **bit-identical** (`max_abs_diff 0.0`, 0 rows differing) but **266 metric mismatches** | ❌ **FAIL** |
| **C4** | built from the TEXT, not the column — 263, not 5 | in-pool **19**; stored `False` **5** | ❌ **FAIL** |
| C5 / C6 / X1 / X2 | empty ceilings reported / one shared page map / pool pages == §I58 / remote store | 0 empty; sha256 `0ca575fa…`; 888 == 888; `10.0.10.65` | ✅ PASS |

**Two of the three failures were PRE-REGISTRATION PREMISE ERRORS and one was a HARNESS BUG** — and the
distinction is the point:

* **C2/C4** failed because the pre-registration measured 263 over the **corpus** and wrote it into a
  guard about a **window-filtered pool**. The arm's *definition* was faithful throughout (**T = C minus
  the filter's rejects**); only the registered **size** was wrong. Restated as **C2′/C4′** — in-pool
  flagged **19**, whole-corpus **263** = 72/186/5 with **244 out of window** — **justified by the
  measurement in the table above, not by relaxing a check the data failed.**
* **C3** failed for a reason that indicts the *check*, not the endpoint: **266 metric mismatches on
  bit-identical vectors** is impossible, and the tell is exactly that shape. Cause: the control arm was
  scored against the raw reachable set (`reach_C`, 888 pages) while arm C itself is scored against
  **its own per-query ceiling** (`relevant ∩ reach_C`). **A control compared under a different
  denominator is not a control.** Fixed; the vector half of the guard (**C3(a)**, `max_abs_diff 0.0`)
  passed on the first run and is unchanged. ⚠️ C3 was **a check that could only fail**, and it was
  caught by that shape — record it so the fix is not read as a relaxation.

#### THE RESULT (the re-registered run — all eight guards PASS)

| arm | embedder | ceiling-norm R@20 | R@100 | raw R@20 | raw R@100 |
|---|---|---|---|---|---|
| **C** | gemma@768 | **0.480410** | 0.704882 | 0.469155 | 0.688542 |
| **T** | gemma@768 | **0.474080** | 0.697513 | 0.462764 | 0.681137 |
| **C** | qwen3@1024 | 0.293934 | 0.569074 | 0.289340 | 0.559740 |
| **T** | qwen3@1024 | 0.293934 | 0.569074 | 0.289340 | 0.559740 |

| contrast (paired, T − C) | Δ | 95 % CI | W/L/T | verdict |
|---|---|---|---|---|
| **gemma@768, ceiling-norm R@20 — PRIMARY** | **−0.006330** | **[−0.021115, +0.008456]** | 1/8/124 | **UNRESOLVED** |
| gemma@768, raw R@20 | −0.006391 | [−0.021173, +0.008391] | 1/7/125 | UNRESOLVED |
| qwen3@1024, ceiling-norm R@20 | +0.000009 | [−0.000009, +0.000028] | 0/1/132 | UNRESOLVED |
| qwen3@1024, raw R@20 | **+0.000000** | [0.000000, 0.000000] | 0/0/133 | UNRESOLVED |

**Per the pre-registered rule the filter does NOT ship on this evidence**, and the honest statement is
the pre-registered one: **applying the content filter does not move base-lane page ranking on this
corpus — a RESULT, not an unresolved one.** ⚠️ The point estimate is **slightly negative** (8 queries
better, 1 worse, 124 tied), and it is **under half the resolution floor** (0.014786 at n = 133), so it
is not a measured harm either. Under qwen3 the treatment is **literally inert** (raw R@20 identical on
all 133 queries; ceiling-normalised differs on exactly one) — the 19 TOC chunks never enter the
top-20 there.

**Reported alongside, always (pre-reg §3):** pages covered **C 888 / T 887** — removing the 19 chunks
drops **exactly one page** from the ceiling; `chunks/page` **C 3.9291 / T 3.9121** (⚠️ the confound
that makes page-deduped recall favour a corpus with more chunks per page — §I70 measured 6.68 old vs
4.07 new).

⚠️ **One extra EXACT reproduction, found after the run and worth recording:** arm **C under gemma@768**
reproduces **§I70's `gemma@768` row exactly** — R@20 **0.480410**, R@100 **0.704882**, R@500
**0.946105**. That is a **third** registered row this harness reproduces (with C1's qwen3 row and
C6's page-array sha256 `0ca575fabc5c59be…`, the same array §I70's V6 reported), and it is the
strongest evidence available that the new model's arm is on the same instrument as the register.

#### VERIFIERS — all eight pass (the re-registered run), and the arithmetic has an independent re-derivation

| # | check | result |
|---|---|---|
| C1 | arm C reproduces §I70's qwen3@1024 row **exactly** | all four k exact |
| C2′ | pool partition + bands, in-pool and corpus | 3,489 − 19 = 3,470; corpus 72/186/5; 244 out of window |
| C3 | A-vs-A — arm C re-run on a re-embed at batch 64 vs 128 | vectors `max_abs_diff 0.0`; **0 metric mismatches** |
| C4′ | built from the TEXT, not the stored column | 19 ≠ 5; corpus 263 reproduces §I39 |
| C5 | empty-ceiling queries reported, never dropped | 0 occurred; 133/133 in both arms; none dropped |
| C6 | one shared chunk→page mapping | sha256 `0ca575fabc5c59bee67faab710bb753fdc8c9141763898fa68bced6d1e6d9944` |
| X1 | pool pages == §I58 `reachable_pages()` | **888 == 888**, pool-only 0, sqlite-only 0 |
| X2 | the resolved config names the remote store (§I49) | `10.0.10.65` / `knowledge_base_v2` |

**Mechanical evidence (the author checking the author, kept separate from any verdict):**
`chunk_filter_ab_verifier.py --check` is a **second, independently written stdlib aggregation** — no
numpy, different code shape, reading only the raw per-query array — and it **re-derives every
aggregate, every endpoint, every CI and every decision field with 197 checks / 0 mismatches.** The
artifact's summary block is never used as ground truth by it.

**Independent verifier dispatched 2026-10-24 (`openai/gpt-oss-20b`, `deleg_fac6860b`, model resolved
from `hermes config get delegation` — provider `custom` @ `10.0.10.70:8000`, **empty fallback chain**,
so it cannot silently degrade to the author's family).** ⚠️ Dispatched **read-only** (`read_file` /
`search_files` only, `terminal` named and forbidden) because **this session's shell returns empty
stdout with exit 0** — smoke-tested with an `echo` first, per the pre-registration's own instruction.

**✅ VERDICT — `deleg_fac6860b`, `status=completed`: 8/8 CONFIRMED, no refutations.** ⚠️ **But it is
NOT BANKED: 4 API calls, 32.8 s** — a cheap verdict, and its citation quality confirms why. **Two of
its cited field paths DO NOT EXIST in the artifact** (`meta.assembly`, `decision.pages_C`; verified
absent — the real paths are `meta` and `meta.chunk_stats.pages_C`), and its line-number citations do
not resolve. Every citation that *does* resolve is real (`meta.chunk_stats` 3,489/3,470/888/887,
`meta.first_run_void.reasons`, `decision.endpoint`, `meta.preregistration`,
`arms.C.qwen3.ceiling_norm.R@20 = 0.293934`), so its **verdicts stand as a weak corroboration** while
its **citations do not** — the substantive half remains the mechanical evidence above.

**Its two "additional risks", adjudicated — BOTH REFUTED:**
1. *"The artifact does not include per-query outputs, so per-query anomalies cannot be spotted."*
   **False** — the artifact carries all **133** rows under `queries[]`, each with both arms × both
   embedders × four cuts, plus `n_reachable` per arm. The reviewer appears to have read only the
   summary blocks it cited.
2. *"The run log is tiny; it does not validate that the pool used the text-based filter rather than
   the stale `is_content` flag."* **False, and it is the guard's whole job** — the log prints
   `IN-POOL flagged …: 19`, `CORPUS flagged: 263`, `stored is_content values: {'True': 3791,
   'False': 5}`, and **C4** asserts `19 ≠ 5` (a 5-chunk treatment would have been the stale-column
   failure). `meta.first_run_void.reasons` records the same distinction.
⚠️ **What the review did NOT test, and could not:** the arithmetic (LLM reviewers cannot add 133
numbers — that is the verifier's 197 checks), and the one thing a read-only reviewer is structurally
unable to reach — whether the *endpoint* measures what the brief says it does.

#### WHAT THIS ARM DOES NOT DO, AND WHAT COMES NEXT

* **It does not test the chunking.** It isolates the content-filter state, one of the three things in
  §I63's residual. The null is **not** evidence that the chunking is fine.
* **It does not touch the product path.** The base lane is a **ceiling**, not the endpoint: §I66
  measured the loss as the 100-slot fusion and the cross-encoder (0.7478 → 0.6048 → 0.4318), and §I65
  is the case where a measured ceiling did not become recall.
* **It does not measure the ingest-time side effects** of the filter (new chunk ids, card
  regeneration, graph rebuild) — that is a build, not an arm.
* **▶ NEXT ARMS, in the pre-registered order** (pre-reg §5): **`min_chunk_tokens`** (32; §E1 measured
  it merging 27 % of the new children and never re-checking the grown child's size), then
  **`semantic_threshold`** (0.8), then **late chunking** (36 min/arm — and it changes the embedding,
  not the chunking, so it is its own contrast).
* ⚠️ **§0's power rule still applies:** n = 133, resolution floor ≈ **0.020**. Any knob with a
  plausible effect below that is out of scope for this gold set — record it, do not chase it.

**Register against:** §I39 (the filter and its measured hit rates — whose corpus-level counts are
**correct** and whose applicability to the base lane this entry corrects), §I21 (the filter in the
graph path — the graph holds 3,533 = 3,796 − 263, i.e. it *does* see the whole corpus), §I58 (the
ceiling rule), §I63 (the 0.0648 residual this arm was meant to move), §I70 (the embedder screen — the
instrument, the gemma row this run reproduces, and the 888/933 figure this entry corrects), §I67 (the
VOID → re-registration precedent), §I49 Finding 1 (the resolved-store trap, guard X2), §I69 (the float
leak), §I36/§I44 (**the plan-premise-error class** this entry joins: a measured number carried into a
context it was not measured in).

### I72. 2026-10-24 — the embedder's base-lane gain SURVIVES the cross-encoder, but it is HALVED: the cross-encoder is a strong equaliser, lifting the WEAKER embedder ~44× more than the stronger. The first run went VOID on a METRIC-CONVENTION mismatch in a guard — the session's third instance of the plan-premise-error class

**The question.** §I70 screened the candidate embedders on an **oracle** and found
`google/embeddinggemma-300m` @768 the only arm that passes the pre-registered rule: **+0.186476**
ceiling-normalised R@20 over the incumbent `Qwen/Qwen3-Embedding-0.6B` @1024, **+0.046480** over
`nomic-ai/nomic-embed-text-v1.5` @768. That is a **base-lane** (dense ranking) result. The product
path runs four more stages, and §I66 measured the **cross-encoder as the largest single loss**
(0.6048 → 0.4318). With §I65/§I66/§I67 as three consecutive precedents of a measured retrieval-side
ceiling that did not become recall, the largest unmeasured risk in adopting gemma is that the
cross-encoder re-orders both pools toward the same answer. **That is cheap to test without a
re-ingest** — the question is whether the *ranking signal* survives a stage, not what the index
stores.

**Design.** Same corpus and pool as §I70/§I71 (doc `7ba61432`, the shipped pool, **3,489** chunks),
same **133** queries, **HyDE off**, exact cosine (no ANN). Per query: take the top **100** chunks by
cosine under each embedder (`cfg.reranker_fetch_k` — the product's own pool width, asserted at run
time), push each list through the **live** cluster cross-encoder (`cfg.sv_rerank_url`,
`BAAI/bge-reranker-v2-m3`, `top_k=20`), and compute page-level ceiling-normalised R@20 **before**
(PRE) and **after** (POST). Endpoint: paired ceiling-normalised R@20 POST, `gemma@768 − qwen3@1024`,
n = 133. **Rule, fixed before the run: the bet SURVIVES iff the POST delta is > 0 with a 95 % CI
excluding 0.**

**Artifacts.** Harness `logs/p1/step10/ce_survival.py`; artifact `logs/p1/step10/ce_survival.json`
(**sha256 `47f207477035a273b41fcd722b91c9d0a0244c8836a9e9e6c00c61be49d8c326`**); independent
aggregation `…_verifier.py`; reviewer pack `…_verifier_extract.json`; run log
`…_run_session15.txt`. **The VOID first run is preserved** as `ce_survival_firstrun_VOID.json`
(sha256 `0947bc0d6c541b52f332815030c1dc80ba497753fc24a7ce83414cfe6112f5dd`). Pre-registration
`.hermes/plans/2026-10-24-p1-cross-encoder-survival-preregistration.md`, re-registration
`…-reregistration.md`. **No LLM calls, no writes to any collection.**

#### THE RESULT (re-registered run — all eight guards pass, exit 0)

| stage | qwen3@1024 | gemma@768 | Δ (gemma − qwen3) | 95 % CI | W/L/T | verdict |
|---|---|---|---|---|---|---|
| **PRE** (cosine order) | 0.274348 | 0.458665 | **+0.184317** | [+0.130809, +0.237824] | 12/77/44 | RESOLVED |
| **POST** (cross-encoder) | 0.363144 | 0.460703 | **+0.097559** | [+0.056072, +0.139045] | 22/46/65 | RESOLVED |

**survival ratio (post / pre) = 0.5293.**

⚠️ **The headline is not "it survives" — it is HOW it survives.** The cross-encoder is a strong
**equaliser**: it lifts the *weaker* embedder by **+0.0888** (qwen3 0.274348 → 0.363144) and the
stronger by **+0.0020** (gemma 0.458665 → 0.460703). So it roughly **halves** the embedder gap while
**reversing nothing**. Two consequences worth carrying into the adoption decision:

* The incremental value of gemma **at the product's last retrieval stage** is **+0.0976**, not the
  base lane's +0.1865 — the embedder's advantage is real but a cross-encoder recovers more than half
  of it from the weaker model.
* ⚠️ **It also explains part of why §I67's width levers were nulls**: the cross-encoder already
  repairs a great deal of pool-quality difference, so widening the pool has little left to repair.

#### THE FIRST RUN WAS VOID — AND THE REASON IS THE SESSION'S THIRD PREMISE ERROR

**Two page-level recall conventions are in play, and the pre-registration used one in its §2 and the
other in its §4:**

| convention | what it does | where it comes from |
|---|---|---|
| **"top-k PAGES"** | rank *every* chunk, dedupe to pages, take the first `k` **pages** | §I70's screen — this produced the register's **0.293934** / **0.480410** |
| **"pages of the top-k CHUNKS"** | dedupe the top-k **chunks** to pages | the **PRODUCT**'s eval, `scripts/evaluate_rag.py:333-341`; and the only one available for a reranked arm, since the cross-encoder returns chunks |

The pre-registration's §2 correctly described the **product** convention (product-faithful, and the
only option for the POST arm); its §4 then required the PRE arm to reproduce **§I70's** rows, which
are in the **other** convention. **They are not the same number**, and the gap is consistent across
both embedders — **−0.0196** (qwen3) and **−0.0217** (gemma) — which is what made the diagnosis
mechanical rather than a guess. So **S1 failed, the run was VOID**, and its numbers are not
registered.

**Restated as S1′** (re-registration; §I67's E4→E4′ and §I71's C2→C2′ precedent, justified **by
measurement, not relaxation**):

* **S1′(a)** — the harness computes §I70's convention **separately** and asserts it reproduces
  **0.293934** / **0.480410** **exactly**: ✅ both exact. That is what pins this harness to the
  register, and it keeps the original guard's whole purpose.
* **S1′(b)** — the PRE and POST arms of the *contrast* both use the **product** convention, asserted
  to be the same function on both sides. Both conventions are now reported side by side forever, and
  the artifact names which one each row is in.

⚠️ **This is the third instance of one class in a single session** — §I71's F1 (a corpus count used
as a pool count), §I70's F2 (a page count that contradicted its own artifact), and now a *metric
convention* asserted across two files. The tell was available before the run in all three cases. The
standing lesson: **when a guard asserts a reproduction of a number from elsewhere, state the
population AND the convention that number was produced under, and assert the two sides of your own
contrast share one.**

#### GUARDS — all eight pass

| # | check | result |
|---|---|---|
| S0 | the resolved config is the one the spec names | collection, rerank URL, model, `fetch_k=100`, `top_k=20` |
| **S1′** | (a) §I70's convention reproduces the register exactly; (b) the contrast is single-convention | **0.293934 / 0.480410 exact**; both sides `pages_of_chunk_idxs` |
| S2 | the rerank service is **live and reordering** | **266 of 266** lists changed order |
| **S3** | negative control — the same list reranked twice is identical | **10/10 identical** |
| S4 | failures counted and reported, n stated | **0** failures; no arm missing without a record |
| S5 | A-vs-A — gemma re-embedded at a different batch is bit-identical | `max_abs_diff 0.0`, 0 rows differing |
| S6 | one shared chunk→page map; ceiling 888; documents in cosine rank order | all aligned; sha256 recorded |

⚠️ **S3 is a real instrument result, not a formality: the cluster cross-encoder is DETERMINISTIC**
(10/10 repeat calls, byte-identical order) — in direct contrast to **Qdrant's server-side RRF
fusion, which §I68 measured nondeterministic**. That is worth knowing: it means a reranked A/B on
this path does *not* inherit §I68's tolerance problem, and it makes the reranker a legitimate
instrument to build on. ⚠️ Caveat: 10 controls over the first 5 queries × 2 embedders — enough to
license the claim for this run, not a characterisation of the service under load.

**Mechanical evidence (the author checking the author, kept apart from any verdict):**
`ce_survival_verifier.py --check` — an independently written stdlib aggregation reading only the raw
per-query array — re-derives every aggregate, contrast, CI, survival ratio and decision field at
**144 checks / 0 mismatches**.

**✅ INDEPENDENT VERIFIER RAN — `openai/gpt-oss-20b`, `deleg_c05e651f`, `status=completed`:
7/8 CONFIRMED, 1 UNVERIFIED, no refutations.** ⚠️ **Not banked** (23 API calls, 40 s, and its
citations are pack-relative line numbers); the substantive half remains the mechanical evidence. Its
field names all resolve in the artifact.

**Its findings, adjudicated:**

1. **C6 `unverified` — the determinism claim, on sample size.** *"10 controls over 5 queries may not
   be statistically robust enough to prove machine-wide determinism."* ✅ **Accepted, and it is
   already the recorded caveat** — §I72 states exactly that limitation (10 controls over 5 queries ×
   2 embedders; enough to license the claim for this run, not a characterisation under load). The
   claim is **not** upgraded: the cross-encoder was deterministic across 10 repeat calls, and that is
   all that is asserted.
2. ⚠️ **Its "rounding mismatch" risk is REFUTED — the error is in the reviewer's own arithmetic.**
   It claimed `gain_qwen3 + gain_gemma` (0.0888 + 0.0020 = 0.0908) should equal `post_delta`
   (0.0976) and "could conceal a minor error in aggregation". **It should not**, and the correct
   identity holds exactly: `post_delta = pre_delta + gain_gemma − gain_qwen3` →
   `0.184317 + 0.002038 − 0.088796 = 0.097559` ✅ (checked to 1e-9), and **per-query to 1e-12 with 0
   violations across all 133 rows** — where rounding cannot hide anything. The reviewer added two
   quantities that the algebra subtracts. ⚠️ Recorded because a plausible-sounding internal-consistency
   doubt is exactly the kind that gets acted on: **check the reviewer's arithmetic against the
   artifact before defending anything.**
3. *"`metric_conventions` is only in `meta`, so if those strings were altered the document would not
   reflect the true conventions."* ⚠️ Generic, and covered: the artifact's **sha256 is registered**
   and the conventions are asserted by guard S1′ from the **data**, not from the prose — the
   §I70-convention row reproduces 0.293934 / 0.480410 exactly, which no altered string could fake.
4. *"Determinism is confirmed for gemma and qwen3 only; other embeddings are not tested."* ⚠️
   **Conflates two things** — S3's control tests the **reranker service**, not the embeddings
   (whose determinism is S5's A-vs-A re-embed, `max_abs_diff 0.0`). Not a gap in this run.

#### WHAT THIS DOES AND DOES NOT LICENSE

* ✅ **It licenses the next step, not a ship.** A SURVIVES verdict means the base-lane ranking signal
  reaches the product's last retrieval stage, so the scratch-index **product-endpoint run** (plan §3)
  is worth its cost.
* ⚠️ **It is NOT the product endpoint.** The cross-encoder here is applied to a **cosine-ordered**
  pool. The product reranks a pool that has been through Qdrant's RRF, page dedup and MMR — and
  §I68's nondeterminism is why that stage is excluded rather than simulated. No SPLADE lane, no
  DA/graph/RAPTOR/visual lane, no intent router, no generator.
* ⚠️ **It does not measure late chunking** — the incumbent's stored vectors were produced with it,
  the gemma arm embeds raw chunk text without it (§I70's asymmetry, conservative for the candidate).
* ⚠️ **It says nothing about the corpus.** §I71 left §I63's residual attributed to the chunking
  proper; this entry does not touch it.

**Register against:** §I70 (the oracle screen this tests the propagation of), §I66 (the stage
decomposition — this is the cross-encoder stage measured directly), §I65/§I67 (the two nulls that
make this test necessary), §I68 (the nondeterministic fusion this run deliberately excludes, and the
contrast that makes S3's result informative), §I55 (the reranker's swallow class, which S4 counts),
§I58 (the ceiling rule), §I71 (§I39's filter, a null — so the shipped pool is the right control),
§I36/§I44 (**the plan-premise-error class**, here a metric convention rather than a count).

### I73. 2026-10-24 — the HyDE cache is BUILT: one frozen hypothetical per query id, so an A/B stops embedding a different query vector per arm

**The defect it removes.** `evaluate_rag.py` generated a HyDE hypothetical with an LLM **per query,
per run**, whenever `hyde_enabled` and the query is `factual`/`overview` — **there was no cache**.
So two arms of the same A/B embedded **different text** for the same query, and the *instrument*
moved the number instead of the treatment. Same class as §I68 (the nondeterministic fusion). It is
the prerequisite for the product-endpoint comparison in the plan's §3.

**Design (plan §2).** Cache the **TEXT**, not the vector: the hypothetical string is
**embedder-independent**, so ONE file serves every candidate embedder in §I70's screen and the
eventual re-ingest. Keyed by **query id**.

**Artifacts.**
`src/pdf_ingestion/hyde_cache.py` · `tests/test_hyde_cache.py` (**14 tests**) ·
`scripts/build_hyde_cache.py` · `data/hyde_cache/<queries-digest>__<model>__<prompt-digest>.json`
(gitignored) · the generated cache: `18ece9b9404688c8__openai_gpt-oss-20b__ab681b8e43855a46.json`
— **127 entries, 0 failed, 314.3 s** (24 calls/min).

**Four properties, each with a mutation-proven guard** (all six mutations make their guard FAIL —
recorded):

1. **A miss is LOUD and never generates.** `get()` raises `HydeCacheMiss` naming the query id;
   generation happens only in `build()`, explicitly. ⚠️ A silent live LLM call mid-run would
   reintroduce exactly the nondeterminism the cache exists to remove (§I25's class).
2. **The header is validated ON READ, not just the filename.** Model, prompt digest, queries digest
   and schema version must all match, or the file is refused — a model, prompt or query-set change
   is an honest miss, never a silent reuse. The prompt digest covers the **system message** as well
   as the template, because both go to the model.
3. **An empty model return is a FAILURE, not a cached value** — counted, not cached, and the build
   exits non-zero listing the ids (§I25/§I52's class: a total loss that reads as a success).
4. **A rebuild reuses what exists.** A cache that re-pays the full LLM pass every run is the defect
   it was written to avoid.

⚠️ **The prompt is DUPLICATED in the repo** — `scripts/evaluate_rag.py` and
`scripts/funnel_boundary_recall.py` each carry a verbatim copy, and the cache key derives from this
module's copy. A test asserts all four prompt fragments still appear in **both** call sites, so a
fork is caught rather than silently keying the cache on text nothing sends (§I28's sweep, applied to
a constant). ⚠️ `funnel_boundary_recall.py` also carries its **own** ad-hoc `--hyde-cache` file
(`{qid: hyp}`, path chosen by the caller) — a second, unvalidated cache with no header check. It is
**not** consolidated here; recorded so the next reader knows there are two.

⚠️ **Not wired into §I70's screen** — the screen is HyDE-off by design. It is for the product-path
run in the plan's §3.

**Register against:** §I68 (the nondeterminism class), §I25/§I52 (a silent empty return, and "measure
the model the phase runs" — the cache freezes `cfg.openai_model`), §I28 (a duplicated constant and
its consumers), §I23 (per-call logging plus a rolling rate line, so a stalled build is
distinguishable from a slow one), §I70/§I72 (the screens it will serve).

### I74. 2026-10-24 — gemma@768 vs nomic@768 AT THE CROSS-ENCODER: gemma wins, but narrowly. Its advantage shrinks 36 % through the stage (+0.0455 → +0.0292, both resolved) — the disposition is GEMMA by the pre-registered rule, and the margin is ~1.2× the instrument's own resolution floor

**The question.** §I70 ranked the candidates on the **base lane**: `gemma@768` **0.480410** >
`nomic@768` **0.433930** > `qwen3@1024` **0.293934** (ceiling-normalised R@20). §I72 then found the
cross-encoder a strong **equaliser** against the incumbent (+0.184317 → +0.097559). ⚠️ But §I72
measured gemma against the **incumbent**, not against **nomic** — and nomic is the cheap candidate.
This run closes that gap, because the two have different adoption costs:

| | low lane (the funnel's fast first stage) | extra work |
|---|---|---|
| **nomic@768** | MRL **64** exists ⇒ lane stays **64-wide**, name `dense_64` stays **true** | the shared re-ingest only |
| **gemma@768** | smallest slot **128** ⇒ lane **widens 64 → 128** | ⚠️ **plus a code change**: `store.py:451` hardcodes `using="dense_64"` while the slice is `query_vector[:cfg.dense_dim_low]`, and the schema check keys on the literal `"dense_64"` (§I13) |

**Design.** §I72's, plus a third arm. Same corpus and shipped pool (`7ba61432`, **3,489** chunks),
same **133** queries, HyDE off, exact cosine; per query the top **100** chunks by cosine per arm
(`cfg.reranker_fetch_k`, the product's own pool width, asserted at run time), pushed through the
**live** cluster cross-encoder (`top_k=20`, raw query). **Three arms, two of them the contrast**:
`qwen3@1024` is the **instrument anchor** (stored vectors), `nomic@768` and `gemma@768` the
candidates. Endpoint: paired ceiling-normalised R@20 POST, `gemma − nomic`, n = 133. ⚠️ The
**contrast** uses the **product's** convention (pages of the top-k *chunks*,
`evaluate_rag.py:333-341`); the **anchor** rows use **§I70's** (top-k *pages*) — §I72's correction,
which is why both are computed.

**Artifacts.** Harness `logs/p1/step10/ce_gvn.py`; artifact `logs/p1/step10/ce_gvn.json`
(**sha256 `7de5cca46c2b48f1cb4915302ee5c0398e872942bc336272d9a5c4e923b0d6a1`**); independent
aggregation `…_verifier.py`; reviewer pack `…_verifier_extract.json`; run log
`…_run_session15.txt`; pre-registration
`.hermes/plans/2026-10-24-p1-gemma-vs-nomic-at-the-cross-encoder-preregistration.md`.
⚠️ `ce_survival.py` was **not edited** — its artifact is registered against that revision. **No LLM
calls, no writes.**

#### THE RESULT (all nine guards pass, exit 0)

**Three anchors, all EXACT** under §I70's convention — this harness is §I70's instrument:

| anchor | this run | §I70 |
|---|---|---|
| `qwen3@1024` R@20 | **0.293934** | 0.293934 |
| `nomic@768` R@20 | **0.433930** | 0.433930 |
| `gemma@768` R@20 | **0.480410** | 0.480410 |

**The primary contrast** (product convention; R@20 per arm PRE → POST: qwen3 0.274348 → 0.363144,
nomic 0.413195 → 0.431455, gemma 0.458665 → 0.460703):

| contrast | Δ | 95 % CI | W/L/T | verdict |
|---|---|---|---|---|
| **PRE** (cosine order) | **+0.045469** | [+0.020104, +0.070835] | 16/50/67 | RESOLVED |
| **POST** (cross-encoder) | **+0.029248** | [+0.004620, +0.053876] | 12/34/87 | RESOLVED |

**survival ratio = 0.643251.** So gemma's advantage over nomic **shrinks 36 %** through the stage —
less than the 47 % its advantage over the incumbent lost (§I72), i.e. the equaliser compresses a
close pair less than a distant one. Context contrasts POST: `gemma − qwen3` **+0.097559**,
`nomic − qwen3` **+0.068311** — so **nomic alone already recovers ~70 % of gemma's gain over the
incumbent.**

**THE DISPOSITION: `GEMMA`**, by the pre-registered rule — δ = +0.029248 > the pre-registered floor
0.020 **and** the CI excludes 0.

⚠️ **The margin is thin, and the fields that say so are in the artifact; the reading is this entry's.**
`decision.resolution_floor_this_run` = **0.024628** (1.96·SD_d/√n for this contrast) and
`decision.post_ci` = **[+0.004620, +0.053876]**. So the point estimate is only **~1.19× the
instrument's own floor**, and the CI's lower bound sits **well below** it — the data are also
consistent with a true effect smaller than the floor. ⚠️ **The artifact records both floors and the
CI; it does not itself label the margin "thin" — that judgement is derived here from those three
fields and should be quoted as such.** A narrow win is a win under a rule fixed in advance, and
softening it on cost grounds is exactly what the rule exists to prevent; but the next reader is
entitled to know it is narrow.

#### GUARDS — all nine pass

| # | check | result |
|---|---|---|
| G0 | the resolved config is the one the spec names | `fetch_k=100`, `top_k=20`, remote store |
| **G1** | anchor: §I70 convention reproduces `qwen3@1024` **0.293934** exactly | exact |
| **G2** | anchor: §I70 convention reproduces `nomic@768` **0.433930** exactly | exact — ⚠️ the stronger of the two: it pins the **candidate's own** cluster embedding path, prefixes included |
| G3 | the rerank service is live and reordering | **399 of 399** lists changed order |
| G4 | negative control — the same list reranked twice is identical | **15/15 identical** |
| G5 | failures counted and reported, n stated | **0** failures |
| **G6** | A-vs-A for **both** candidates, bit-identical | gemma `max_abs_diff 0.0` · nomic `0.0` |
| G7 | one shared chunk→page map; ceiling 888; documents in cosine rank order | all aligned |

**Mechanical evidence (the author checking the author):** `ce_gvn_verifier.py --check` re-derives
every aggregate, contrast, CI, survival ratio and decision field from the raw per-query array at
**182 checks / 0 mismatches**. ⚠️ **Its first `--check` run reported ONE mismatch — and the bug was
in the verifier, not the artifact**: its context-contrast loop had the operand order backwards for
the `nomic_minus_qwen3` label, so it recomputed `qwen3 − nomic` (−0.068311) against the artifact's
`nomic − qwen3` (+0.068311). That is the verifier doing its job on the one input it could still
catch, and it is recorded rather than quietly fixed.

**⚠️ THE INDEPENDENT VERIFIER — FIRST DISPATCH FAILED, RE-DISPATCHED SMALLER.** `deleg_862d3e0a`
(`openai/gpt-oss-20b`, read-only, 5 API calls, 17 s) **died on output-length truncation** — the
model's reply was cut off before it finished, so **nothing was checked and that is NO VERDICT, not a
pass** (§I70's rule: a truncated reply is no verdict). The likely cause is the pack size: it was
pointed at the **400 KB** artifact, which is the §I70 failure signature (a reviewer truncated after
reading a large artifact whole). **Recovery, per the standing recipe:** a **23 KB compact pack**
(`~/.hermes/cache/scratch/ce_gvn_compact_pack.json` — meta, verifiers, arms, endpoints, decision and
4 sample rows, with the 133-row array deliberately excluded, since its arithmetic already has an
independent re-derivation) and a brief capped at **5 claims / under 500 words**, dispatched as
`deleg_4b0ece7b`. ⚠️ **§I74 is NOT `[verified]` until that returns**, and a second truncation would
leave it to the human rather than to a third attempt.

**✅ THE RE-DISPATCH RETURNED — `deleg_4b0ece7b`, `status=completed`: 5/5 CONFIRMED, no refutations,
"Additional risks: none".** It read the 23 KB pack only, in **5 API calls / 16.7 s** — i.e. the
smaller pack and the 500-word cap fixed the truncation outright. ⚠️ **Still NOT banked** (very cheap,
and the substantive half remains the 182-check mechanical re-derivation). Its citations were checked
rather than assumed: `meta.i70_rows_for_the_anchors`, `arms_i70_convention`, `metric_conventions`,
`decision.post_delta`, `decision.post_ci`, `decision.post_n`, `decision.post_wlt`,
`decision.resolution_floor_this_run` and `decision.scope` **all resolve in the pack**; ⚠️ **one
citation is misattributed** — it places the rule at `decision.rule.decision_rule`, whereas the pack
carries it at top-level `rule.decision_rule`. ⚠️ And on claim 3 it says *"with the implied resolved
status"*: it **inferred** resolution from the delta rather than reading the flag, which happens to be
correct here (the CI [+0.004620, +0.053876] lies wholly above 0) but is an inference, not a check —
recorded so the next reader does not read it as one.

**Register against:** §I70 (the oracle screen whose rows the three anchors reproduce), §I72 (the
survival test this extends from one candidate to two, and whose convention correction it inherits),
§I66 (the stage decomposition), §I67 (the nulls that make a stage diagnostic worth running), §I68
(the nondeterministic fusion excluded here), §I13 (a named-vector slot whose name encodes its
dimension — the reason gemma's low lane is a code change and nomic's is not), §I55 (the reranker
swallow class G5 counts), §I58 (the ceiling rule).

---

### I75. 2026-10-24 — ⚠️ THE GRAPH LANE IS **REACHABLE AND SERVING**. The recorded blocker — *"Memgraph is DOWN — 7687 refused"* — is a **MIS-SCOPED PROBE**, and it has been keeping a working lane out of scope for several sessions

**The claim that was in force.** `HANDOFF.md` session 13 §5 lists the graph lane as **out of scope**:
*"the graph lane (Memgraph is DOWN — 7687 refused — and `hop_distance` is a constant 0)"*, and the
gemma adoption plan's §5 repeats it. The lane's disposition has been decided on that line.

**It is false, and the error is the §I49 Finding 1 class — a host assumed rather than resolved.**
The probe that produced "7687 refused" tested **the cluster IPs** (`10.0.10.70`, `10.0.10.65`), which
is where Qdrant and the embedder live. But Memgraph is not on the cluster: the code's default is
`memgraph_host = "localhost"` (`src/core/config.py:238`, port `:239`) and `.env` sets
`MEMGRAPH_HOST=localhost`. Measured 2026-10-24 (session 16):

| check | result |
|---|---|
| `docker ps` | `synapse_memgraph`, `memgraph/memgraph:2.18.1`, **Up 6 days**, `0.0.0.0:7687->7687/tcp` published |
| `127.0.0.1:7687` | **OPEN** |
| Bolt query round-trip | **~2 s**, real data returned |
| graph contents | **1 Document / 3,533 Chunk / 907 Page / 6,065 Concept / 14,405 MENTIONS / 21,670 RELATES_TO / 3,161 PREREQUISITE_OF**, and the only `Document` id is the **live** `7ba61432-c5e0-416d-aecf-25a232523481` |

⚠️ **A second red herring, recorded so nobody chases it: the container reports `unhealthy` and has
for its whole life.** `docker inspect` shows `FailingStreak: 24362` and every entry the same:
`OCI runtime exec failed: exec: "mg_client": executable file not found in $PATH`. The healthcheck
execs a binary that is not in the image — **a broken probe, not a broken database**, and it is
indistinguishable from a real outage to anyone reading `docker ps`. Fix the healthcheck before
trusting that column.

**The lane does not merely connect — it SERVES.** Probe `logs/p1/step10/graph_lane_probe.py` →
`graph_lane_probe.json`, exercising the **production** path (`cluster_embedder.embed_query` →
`GraphBuilder.graph_search` → `_find_concepts_scored` (Qdrant `concept_embeddings` ANN) → Memgraph
Cypher → chunks), **read-only, no LLM calls, ~5 s**:

* **5/5** probed multihop queries resolved **8/8** concepts and returned **5 chunks each**
  (`limit=5`). **VERDICT: REACHABLE AND SERVING.**

⚠️ **What the probe does NOT show, and should not be read as:** that the lane helps. Every query
returned **exactly its limit** — the lane always fills its budget — and several concept sets are
visibly off-query (a question about the focus of an **ellipse** at a tilt resolves to
*"focusing on a point on the sun"*; a question about the **'blob' from different points** resolves to
*"speed of the moving object"*). That is consistent with §I70's note that the concept vocabulary holds
near-duplicates, and with §I56's measured **negative** on the DA lane. **Reachability is not
contribution**, and §I56 is the cautionary case for exactly this inference.

**`hop_distance` is a constant `0`, confirmed live — §G5/§I2 stands, unchanged.** `graph_search`
(`src/pdf_ingestion/graph_builder.py:544-555`) is a **single-hop** lookup —
`MATCH (ch:Chunk)-[:MENTIONS]->(k:Concept)` with **no traversal** — and hardcodes `hop_distance: 0`
at `:570`. So "multihop" is **nominal**, and that is a **code** defect, not an infrastructure one.
⚠️ **Do not conflate the two**: this entry removes the *infrastructure* blocker only.

**⚠️ AN UNEXPLAINED STORE CHANGE, FLAGGED AND NOT GUESSED.** The §I21 rebuild was verified at
**7,427 Concept** nodes and §I49 recorded `concept_embeddings` at **7,427 @1024d**. Measured now:
**Memgraph 6,065 Concept nodes** and **Qdrant `concept_embeddings` 6,065 points @1024d** — **exactly
equal**, both **−1,362**. `Chunk` (3,533), `Page` (907) and `Document` (1) are unchanged, so the
corpus is intact and only the **concept layer** moved. Two candidate mechanisms, **neither
established**: `scripts/clean_stale_graph.py` deletes Concept nodes with no points in Qdrant (it
would produce exactly this lockstep), or a further concept re-index. ⚠️ **This probe does not
distinguish them, and the reading is not evidence for either — it needs its own check.** Recorded
because a store that changes its contents with no register entry is the §I44 class.

⚠️ **Also hit live, and already documented:** Memgraph 2.18.1 **refuses** the single-query orphan form
`WHERE NOT (c)<-[:MENTIONS]-()` — `Not yet implemented: atom expression` — which is why
`clear_graph_document.py` does orphan detection **two-phase and by name**. The trap is real and
reproducible; do not write that Cypher form.

**What this changes.** The graph lane should be **re-admitted to scope**, and two documents are now
stale on this point: `HANDOFF.md` session 13 §5 and the gemma adoption plan's §5 "OUT OF SCOPE" line.
⚠️ **What it does NOT change:** §G5/§I2 (`hop_distance` constant 0), §G1 (closed, measured-and-
negative) and §I56 (the DA lane's measured negative) are all untouched — this entry removes a false
*blocker*, it does not supply a *result*.

**Cost:** one probe, ~5 s of cluster work, **no writes** to Memgraph or Qdrant, **no LLM calls**.
**Register against:** §I49 Finding 1 (the resolved-store trap — the same class of error, a different
host), §G5/§I2 (`hop_distance`), §I45 (Memgraph 2.18.1 Cypher limitations), §I21 (the rebuild whose
counts this entry's discrepancy is measured against), §I56 (a live lane that still measured
negative — the reason reachability must not be read as contribution), §I44 (a store changing without
a record).

---

### I76. 2026-10-24 — ⚠️ `knowledge_base_v2` CARRIES **FOUR** LANES, INCLUDING `sparse`. The gemma plan's §8 "correction" (*"no sparse lane; a four-lane Stage E assertion is unpassable"*) is **itself wrong**, and the error is a lane inventory read from **one** config key

**The claim that was in force.** The gemma adoption plan's §2 and §8 (written session 16) correct an
earlier draft: *"the `sparse` lane **does not exist on v2** (`splade_enabled=False`, so nothing to
carry over, and a four-lane Stage E assertion is unpassable)"*. `HANDOFF.md` session 16 §5 repeats it
as one of the plan's four verified-wrong literals. **Both halves are false.**

**Measured 2026-10-24 (session 17), read-only REST against the live store:**

| check | result |
|---|---|
| resolved `cfg.splade_enabled` | **`True`** — `.env:159 SPLADE_ENABLED=true` overrides `src/core/config.py:178`'s default `False` |
| v2 `config.params.vectors` | `colbert`(128, max_sim) · `dense_1024`(1024) · `dense_64`(64) — **three** |
| v2 `config.params.sparse_vectors` | **`{"sparse": {}}`** — a **fourth**, in a **separate key** |
| points, total | **3,869** |
| points carrying `dense_64` / `dense_1024` | **3,869 / 3,869** — all |
| points carrying `colbert` / `sparse` | **3,796 / 3,796** — real SPLADE `indices` + `values` on the points |
| the **73** points without `colbert`/`sparse` | **`raptor_level: 1` summary nodes** — dense lanes only |

**Mechanism — a lane inventory read from one field.** The session-16 correction read
`config.params.vectors` and stopped; the sparse lane lives in `config.params.sparse_vectors`.
⚠️ **The repo already knew this and says so verbatim:** `scripts/reembed_chunks.py:59` — *"Sparse lanes
live in a SEPARATE config key, so a named-vector check alone misses them"* — and its own docstring
(`:103-104`) states v2 *"carries **FOUR** lanes on every point — `dense_64`, `dense_1024`, `colbert`
(128d multivector, max_sim) and the sparse…"*. The script that refuses because of the four-lane shape
was in the tree while the plan was written.

**Why it is not cosmetic — three consequences:**

1. **Stage B:** v3 must declare **four** lanes. A three-lane v3 would be a **regression against v2 on
   a lane the product path reads** — `store.py:460` `if cfg.splade_enabled and query_text` adds the
   `sparse` prefetch, and `splade_enabled` resolves **True** here.
2. **Stage F's A/B is confounded by lane presence.** v3-vs-v2 on the funnel would compare a store
   missing a lane against one carrying it, **on the very path being measured** — and the difference
   would be read as an embedder effect.
3. **Stage E's per-point assertion needs a scope, not a deletion.** *"Every enabled lane on every
   point"* is **already false on v2 itself**: the 73 `raptor_level: 1` nodes carry the dense lanes
   only. The assertion must be **scoped by point kind** (chunk points: all four; RAPTOR summary nodes:
   dense lanes) — scoped, per §I26, not edited away to get past it.

**Cost of the fix, and it is small:** SPLADE vectors are **text-derived**, independent of the dense
embedder, and Shape B preserves `chunk_id` — so the `sparse` lane (and `colbert`) can be **carried
over by id** from v2 rather than recomputed. Cheap — but it must be **in the plan**, or the run
produces a three-lane v3 and Stage F measures a store that is missing a lane.

⚠️ **Flagged, NOT established — needs its own check.** With `splade_enabled` resolving **True** on this
machine, any product-path run that loaded `.env` was running the **sparse lane** (and any that did not
was not). `CLAUDE.md`'s *"laptop with existing Feynman data: `SPLADE_ENABLED=false`"* is **not** what
`.env` resolves to today. Whether §I65/§I67's funnel runs included the sparse lane is **not asserted
here** — it is readable from those harnesses' resolved-config prints and must be checked before either
entry is quoted as sparse-off.

**Cost:** four read-only REST probes, **no writes**, no LLM calls, ~2 s.
**Register against:** §I49 Finding 1 (assumed vs **resolved** — the same class, a config key this
time), §I13 (the four-lane refusal this contradicts), §I33 (a count-based gate holds a dead lane
green — the reason the assertion is per-point), §I26 (scope the gate, do not edit it away), §I44 (a
store fact that existed but was not on disk).

---

### I77. 2026-10-25 — ⚠️ THE LATE-CHUNK PATH DOES NOT WORK UNDER GEMMA: the alignment contract is off-by-**TWO**, and the endpoint **truncates at 2048 tokens**

**The claim that was in force.** `late_chunk_embedder.py`'s alignment contract — *"``n_api ==
n_local + 1`` with the extra vector last… probed live 2026-10-17"* — was probed against **Qwen3**,
and C0 assumed it would carry to gemma. It does not.

**Measured (C0, 20 parents, serial, live cluster): 20 of 20 parents FAILED**, every one with
`Token alignment broken for parent N: local tokenizer produced X tokens, the endpoint returned X+2
vectors`. Not a sample of failures — all of them.

Then quantified offline (tokenizer only, no cluster, no writes):

| check | result |
|---|---|
| special tokens gemma adds | **2** (`<bos>` + `<eos>`): 755 → 757 with `add_special_tokens=True` |
| ⇒ the content matrix | **`matrix[1:-1]`**, not `matrix[:-1]` |
| parents over the window | **71 / 341 (20.8 %)** |
| children fully inside 2048 | 3,445 / 3,796 (**90.8 %**) |
| children straddling the cutoff | 70 (1.8 %) |
| children **ENTIRELY** beyond it | **281 (7.4 %)** |

**Two independent defects, and neither is incidental:**

1. **The alignment rule is off-by-two for gemma.** ⚠️ `_content_tokens` **raises** on any count other
   than `n_local` or `n_local + 1`, which is why this surfaced at all instead of silently shifting
   every span by one or two tokens — the guard earned its keep (§I47's class, working as designed).
   The fix is a **model-aware** rule (gemma: `matrix[1:-1]`).
2. **The gemma endpoint truncates at 2048 tokens.** The library warns *"Token indices sequence length
   is longer than the specified maximum sequence length for this model (4653 > 2048). Running this
   sequence through the model will result in indexing errors."* A parent longer than the window has
   **no token vectors past 2048**, so late chunking over the whole parent is **impossible** for it.
   Qwen3's window is far larger, so the existing corpus never met this — ⚠️ **the adoption introduces
   it.** **351 children (9.2 %) cannot be late-chunked faithfully**: 281 have no overlapping vectors
   at all and 70 straddle the cutoff.

⚠️ **What this does NOT touch, stated before anyone reads it as a reason to revisit the adoption:**
§I70 / §I72 / §I74 measured gemma on **pooled chunk embeddings, not late-chunked ones** — so the
measured gains (+0.029248 vs nomic, +0.186476 vs the incumbent) are **unaffected**. Late chunking is
**orthogonal** to the measured gain.

⚠️ **Why it matters for Shape B, and why it is a DECISION rather than a bug fix.** The late-chunk pass
*is* the Shape B re-embed's core, and as it stands **the pass cannot run at all**. The options:

* **(a)** accept a **MIXED index** — late-chunked for 90.8 %, isolated (E3's own control) for 9.2 % —
  and **pre-register** that mixture, because it is a different index from either pure arm;
* **(b)** **split long parents** before late-chunking — new boundaries ⇒ **new chunk ids** ⇒ the cards
  (keyed on `chunk_id`) and the graph (chunk nodes keyed by id) invalidate ⇒ **this is Shape A**;
* **(c)** drop late chunking for gemma entirely (every child isolated) — simplest, abandons E3.

**OWNER DECISION, NOT TAKEN.** ⚠️ And the Shape B cost estimate (**~48 min**, itself derived) is
**moot until this is settled** — the pass produces nothing today.

**Cost:** 20 cluster calls (~1 min) + an offline tokenizer pass over 341 parents. **No writes, no LLM
calls, no re-parse.** Probe + artifacts: `logs/p1/step10/c0_late_chunk_timing.{py,json}` (the failure,
`status: FAILED`, 20/20) and `c0_gemma_alignment_and_truncation.{py,json}` (the quantification).

**⚠️ ADDENDUM 2026-10-25 — the two defects were then measured against the DECLINED alternative,
because that is what decides whether §I77 is a reason to revisit the embedder choice.** Same corpus,
same cluster, tokenizer-only (`logs/p1/step10/nomic_window_and_alignment.{py,json}`):

| | **gemma** (window 2048) | **nomic** (window 8192) |
|---|---|---|
| max parent tokens in corpus | 5,880 | 4,712 |
| parents over the window | **71 / 341 (20.8 %)** | **0 / 341 (0.0 %)** |
| children living in a truncated parent | **1,415 / 3,796 (37.3 %)** | **0 (0.0 %)** |
| children losing vectors (beyond + straddling) | **351 (9.2 %)** | **0** |
| **alignment delta** (`n_api − n_local`) | **+2** | **+2** |

**⇒ The WINDOW defect is gemma-specific. The ALIGNMENT defect is NOT.** nomic's endpoint appends the
same two special tokens (`n_api == n_local + 2`; measured 3,879 vs 3,877 on the corpus's longest
parent) — so the alignment fix is **shared machinery, required whichever candidate is adopted, and it
is therefore not a reason to prefer either.** The window is the only axis where the candidates
genuinely differ, and there the difference is total: **37.3 % of children sit in a truncated parent
under gemma and 0 % under nomic.**

⚠️ **And one correction to the 9.2 %, which makes it worse than "a fallback":** of the 351 damaged
children, **281 overlap no token at all** and take `_pool`'s **parent-mean fallback — which WARNS** —
but **70 STRADDLE the 2048 cutoff and would be pooled from a truncated token set with NO warning.**
That is the §I25/§I47 class (a silently wrong answer, presented as a normal one), and it means any
window fix must cover the **straddle** case explicitly, not only the empty-span case. Count it.

⚠️ **This is new evidence about the COST side of a decision that was recorded as a cost decision**
(*"nomic was declined as a COST decision, not a data finding"*). Re-opening it on new measurement is
legitimate; restating it as *"nomic was worse"* still is not — the measured gain favours gemma.
**Register against:** §I47 (a loud guard where a bare 400 or a silent shift would have hidden this),
§E3 (late chunking's design and its own control), §I70/§I72/§I74 (**what** was measured, and that it
was pooled), §I13/§I76 (the gemma adoption's other shape changes), §I44 (a fact that now exists on
disk because a probe wrote it there).
