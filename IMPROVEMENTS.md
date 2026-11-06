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

### G5 outcome — GENUINE MULTI-HOP BUILT, DEFAULT-OFF, VERIFIED (2026-11-05)

**What was built.** `graph_search` was a single-hop concept lookup that hard-coded `hop_distance = 0`
(§I2: *"multihop is nominal"*). It now traverses: new setting **`cfg.graph_max_hops`** (default **1**)
+ a branched query — `max_hops == 1` keeps the legacy Cypher **byte-identical** (no `RELATES_TO`,
`0 AS hop_distance`); `>= 2` expands the seed set along `RELATES_TO` edges and reports the real
minimum edge count via `min(size(relationships(p)))`. **Default 1 is deliberate** — the expansion is a
new treatment and must not move the shipped lane until its ablation runs (§G1's rule).

**Live behaviour probe** (`logs/p1/step10/graph_multihop_probe.py` → `.json`, read-only, 8 multihop
queries, live Memgraph + cluster embedder, limit 500):

| | hop-1 (shipped) | hop-2 (expansion) |
|---|---|---|
| `hop_distance` | all **0** (8/8) | **{0, 1, 2}** — not constant (8/8) |
| chunks returned | 8–112 | 500 (cap) |
| **new chunks vs hop-1** | — | **+388 … +492** (adds on 8/8) |
| wall | ~0.3 s | ~2.1 s |

⇒ **the traversal traverses**: a 2-hop chunk — one that mentions a *neighbour* of a seed, never the
seed — is reached, which is exactly the plan's verifier (*"a query requiring two hops retrieves a page
neither one-hop endpoint reaches"*).

**⚠️ THREE THINGS THE LIVE PROBE CAUGHT THAT THE FAKE-DRIVER UNIT TESTS COULD NOT** (recorded, not hidden):
1. **Memgraph has no `LENGTH()` on paths** — the first query errored `Function 'LENGTH' doesn't exist`;
   fixed to `size(relationships(p))`. A unit test with a fake driver cannot see a Cypher dialect gap.
2. **3 hops is prohibitive** — measured **0.3 s (1) / 2.3 s (2) / 66.5 s (3)**, and 2-hop already
   reaches **2,780 of 6,065** concepts. The bound is therefore **clamped to 2**, not 3.
3. **The expansion's tail is invisible at the shipped ranking.** With hop-first ordering and a top-20
   limit the returned list is filled by hop-0 chunks, so the new hop-1/2 chunks only enter when the
   seed set is short. A real property for the ablation to read against — not a defect.

**Verification.** Tests `tests/test_graph_multihop.py` **6/6**; mutation `graph_multihop_mutation.py`
→ `.json`: baseline all PASS, **6/6 checks reddened, none inert**, failures on assertions. Independent
verifier **`openai/gpt-oss-20b` (`deleg_fa7bdec1`), 7/7 claims CONFIRMED** (cited lines re-checked by
the author; tree unchanged after the review).

**⚠️ §I2 is only PARTLY closed.** The traversal exists and is verified, but it **ships OFF** (default
1) until its **ablation** runs — PPR's rule (§G1), and the lane is a measured content HARM (§I98), so
the ablation must show the expansion *earns its place*, not merely that it runs. The ablation needs
the full retrieval path and is **BLOCKED** while the cluster's sparse + rerank lanes are down.

**Register against:** §I2 (the constant-0 defect), §G1 (the "no claim without the ablation" rule),
§I98 (the lane's content harm), §G3 (the merge this ran on).

---

### G3 outcome — the SENSITIVE re-measurement: still UNRESOLVED, but DIRECTIONAL (2026-11-05)

**Why.** §I51 recorded §G3's merge as measured-and-null on an endpoint that was **INERT** (a median
that could not leave 1.0), so the null was uninformative. Re-pre-registering a sensitive endpoint was
an owner decision, now taken.

**Pre-registered** (`.hermes/plans/2026-11-05-p1-g3-sensitive-remeasurement-preregistration.md`,
written before the re-derivation): the endpoint is the **per-query count of chunks matching ≥ 2** of the
query's top-8 concepts, over the **whole** `matched_concepts` histogram (no LIMIT), **paired** across the
200 queries; **RESOLVED iff the 95 % CI on the mean paired delta excludes 0**.

**Result** (`logs/p1/step10/g3_sensitive_remeasure.json`, read-only over the two 2026-10-22 artifacts):

| | before | after |
|---|---|---|
| chunks matching ≥ 2 (total) | **138** | **158** |
| `share_ge_2` | 0.063419 | 0.064123 |

Mean paired delta **0.10**, SD 0.808, **95 % CI [−0.0127, +0.2127] ⇒ UNRESOLVED**; **11 W / 1 L /
188 ties** (12 of 200 queries move at all). The **138 → 158** figures reproduce §I51's V3 table
**exactly** — the harness re-derives the recorded numbers.

**⇒ THE FINDING.** Even a *sensitive* endpoint does not resolve the merge's query-side effect — it is
**UNRESOLVED, not negative**. The direction is **11 wins to 1 loss**, so the mean is swamped by the
**188 ties** (the design is underpowered on this endpoint, the §G1 defect class in a new form). ⚠️ This
does **NOT** licence *"entity resolution does not help retrieval"*: the endpoint measures
*matched-concept multiplicity*, not retrieval quality. A retrieval-quality claim still needs the
**endpoint ablation** — BLOCKED while the cluster's sparse + rerank lanes are down.

**Verification.** `logs/p1/step10/g3_sensitive_remeasure_verifier.py` **independently re-derives** the
endpoint from the inputs (a second implementation) and compares the artifact to it — **9/9 PASS**;
mutation proof **9/9 checks reddened, none inert** (an input-mutation was added so the id-match check
could be reddened at all). Independent verifier **`openai/gpt-oss-20b` (`deleg_7ed32af1`), 7/7
CONFIRMED**; the author re-ran the harness to a **byte-identical** artifact and noted the reviewer's one
arithmetic slip (0.064129 vs the correct 0.064123) — immaterial.

**Register against:** §I51 (the inert endpoint this replaces), §I29 (the query-side quantity), §G1 (the
underpowered-cut defect class), §G5 (the sibling graph item).

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

---

### I78. 2026-10-25 — S1 (nomic Stage A2 + A2b) is finished and GREEN: the document-side prefix, the span shift and the model-aware special-token layout are built, guarded and mutation-proven. ⚠️ The session's finding: the layout was resolved from a **GLOBAL flag**, not the embedder in use

**State on entry — the plan said "the next session starts S1", and S1 was already half-done,
uncommitted and RED.** Session 17's end left the Stage A2/A2b code in the working tree with **no
register entry, no HANDOFF block, and a suite at `20 failed / 661 passed`.** The documented baseline
is **4 pre-existing failures** (`test_phase1::test_hybrid_search_includes_global`,
`test_phase2::test_search_still_works_after_phase2`, `test_splade` ×2), so the tree carried **16 NEW
failures**: 9 in `test_late_chunk_embedder.py`, 5 in `test_embed_cache.py`, 1 in
`test_chunking_pipeline.py`, 1 in `test_phase1.py`.

**⚠️ Root cause of 14 of the 16 — a GLOBAL flag deciding a per-embedder contract.**
`LateChunkEmbedder.__init__` resolved the endpoint's special-token layout from `cfg.use_stub_embedder`
(True for the whole test suite) instead of from the embedder **actually in use**. Under the suite it
therefore assumed `(0, 0)` while the tests' mock endpoint returned `n_local + 1` vectors, and
`_content_tokens` **raised** on every parent. The fix keys on the instance:
`isinstance(self._embedder, StubClusterEmbedder)`. ⚠️ **Behaviour-preserving in production** — the
factory returns a `StubClusterEmbedder` exactly when `use_stub_embedder` is True — so it is a
**correctness fix to the contract** (the layout is a property of the embedder, not of the process),
**not** a test accommodation. It is also why the mistake never surfaced as a product bug: only a test
that pairs a real embedder with the global stub flag can see it.

**The other 2 — the lane rename left stale assertions.** `dense_dim_low` 128 → 64 and the lane
`dense_128` → `dense_64` (Stage A2) were not carried into `tests/test_chunking_pipeline.py:223` and
`tests/test_phase1.py:63`, which still asserted `dense_128`. Updated.

**⚠️ The build was MISSING its two load-bearing guards.** S1's definition of done requires the
span-invariance guard (trap 2) and the prefix-sent guard (trap 1); the previous session built the
mechanism but **neither guard**. Added:

* `test_a_document_prefix_does_not_shift_a_childs_pooling_window` — a child's pooled
  `dense_1024`/`dense_64` must be **unchanged** by adding a document prefix, and its `token_span`
  must move by exactly the prefix's token count. ⚠️ The test helper `_token_vector` was made
  **position-independent** first: with a position-aware vector a correct implementation and a
  mis-shifted one differ for the **wrong reason**, so the guard would have been unfalsifiable in the
  way that matters.
* `test_document_prefix_is_sent_on_both_passage_paths` — the request payload carries the prefix on
  **both** passage paths (pooled `embed_documents` and per-token `embed_documents_tokens`), and the
  query side carries only `cfg.query_instruction`.
* plus `_DECLARED_SPECIALS` model-awareness (`nomic (0,2)`, `Qwen3 (0,1)`, unknown ⇒ raise).

**✅ The alignment rule is probed, not assumed (trap 3).** `logs/p1/step10/probe_nomic_alignment.json`
puts nomic at **0 leading + 2 trailing** with a **7.87×** margin over the runner-up, and Qwen3 at
**0 + 1**; `_DECLARED_SPECIALS` declares both and `declared_specials` raises for an undeclared model.
The BERT-style `[CLS] … [SEP]` guess `(1, 1)` was **wrong** and would have pooled every child one
token off, **silently**.

**✅ Mutation-proven.** 6 of 7 mutations make their guard fail: the span shift, `ClusterDenseEmbedder._prefixed`
as a no-op, `LateChunkEmbedder` tokenizing RAW text, the wrong nomic layout, `_content_tokens`
ignoring the leading slice, and the specials keyed on the global flag again. ⚠️ The one that did
**not** (**M5**) is a **no-op mutation** — for the `(1,1)` case the guard exercises, `n_api - trailing`
equals the correct `end`, so the mutation changed nothing — and it was **replaced by M5b**, which
discriminates. Log: `logs/p1/step10/s1_a2b_mutation_log.txt`. Both source files restored
byte-identical.

**Suite after: `4 failed / 683 passed / 6 skipped`** — the 4 are the documented pre-existing set,
**proved** pre-existing by stashing the changed `src/` files and re-running (same 4).

**⚠️ Reviewers — three dispatches, and only the mechanical evidence is banked.** (a) The multi-turn
reviewer **DIED on this gateway** (`unexpected tokens remaining in message header:
Some("to=functions.read_file")`) — **no verdict, not a pass**; a second child with a mis-scoped pack
answered all-UNVERIFIED with five fabricated risks (SPLADE env flags, Memgraph threads, `CardType`
docs — none touched by this diff). (b) The compact **single-turn** reviewer (`openai/gpt-oss-20b`,
read-only) returned **8/8 CONFIRMED, no refutations** — but it was **cheap (10 calls / 25 s)** and its
risk list is generic, so it is a **weak corroboration, NOT banked**. (c) The mutation-check reviewer
returned **5 CONFIRMED / 1 REFUTED (M5)** — the refutation was **VALID**, which is why the log was
reconciled rather than defended; its *stated mechanism* for M5 ("the guard's defaults use
`leading = 0`") is **wrong** and is not recorded as the reason.

**Register against:** §I77 (the alignment defect that made a model-aware rule necessary, and the
trap-3 precedent), §I62 (the prefix trap, the same class on the query side), §I76 (the lane
inventory), §I13 (a lane named for a width it does not have), §I28 (a mechanism wired into some
callers and not others), §I25/§I47 (a silent shift presented as a normal result).

---

### I79. 2026-10-25 — ⚠️ SIGNOFF 4 (the MRL truncation convention) IS MEASURED AND IS A NULL: KEEP the project's plain slice + re-normalise

**The open question (plan §1 trap 4, plan §7 signoff 4).** `mrl_slice` / `NomicEmbedder._truncate`
do a **plain slice + re-normalise**; Nomic's model card prescribes **`layer_norm` over the full 768
dims BEFORE the slice**. Under nomic the 64d lane **is** the funnel's first stage, so the convention
decides every 64d number — and the plan recorded that **moving it means re-measuring §I59's rows.**
Signoff 4 was **OPEN and gated S3**.

**Measured** (`logs/p1/step10/mrl_convention_ab.{py,json}`, pre-registered then re-registered, **all
6 guards pass**, exit 0): arm A = plain slice, arm B = `layer_norm`-then-slice, ceiling-normalised
paired R@20/R@100/R@500/R@1000 over the 133 gold queries on the shipped pool (3,489 chunks), nomic@64.

| metric | A | B | Δ (B−A) | 95 % CI |
|---|---|---|---|---|
| cR@20 | 0.3643 | 0.3647 | **+0.000314** | [−0.0035, +0.0042] |
| cR@100 | 0.5691 | 0.5690 | −0.0000 | [−0.0002, +0.0002] |

Primary Δ **+0.000314**, CI **straddles 0**, and **below the run's own resolution floor (0.003853)**
⇒ per the pre-registered rule, **ADOPT LAYER NORM = False.** **Verdict: KEEP the project's plain
slice.** The convention does not move the 64d lane's ranking on this corpus by more than the run's
floor — a **RESULT**, not an unresolved one. **§I59's rows stand; no re-measurement.** Two anchors
reproduce §I70 exactly (nomic@64 every-chunk **0.364342**; top-1000 pool **0.364342**).

⚠️ **Recorded, not independently reviewed** — the run's own guards pass and it reproduces §I70's
rows, but no reviewer was dispatched against it in the session that produced it. Treat the
*mechanical* half as sound and the *disposition* (accept the measurement) as an **owner call that is
still open.**

**Register against:** §I70 item 4 (where the convention was first registered), §I59 (the rows that
would need re-measuring), §I78 (S1, the same session).

---

### I80. 2026-10-25 — ✅ S2: `knowledge_base_v3` is re-created with the §2 schema and VERIFIED empty; ✅ C0 PASSES under nomic — **~7.0 min** for the whole late-chunk pass, not the derived **~48 min**

**Stage B.** `knowledge_base_v3` held the **gemma shape** (`dense_128` 128d + `dense_full` 768d, **0
points**). Dropped and re-created through the project's own bootstrap
(`logs/p1/step10/s2_create_v3.py`, targeted: it touches **only** v3 — `reset_for_reingest.py` is
wrong here because it also clears SQLite and the derived collections). Resolved config for the run:
`nomic-ai/nomic-embed-text-v1.5` / 768 / 64 / `search_query: ` / `search_document: `, host
`10.0.10.65`.

**Verifier B — an INDEPENDENT live read-back (§I33: not via the code that created it).** A fresh
`QdrantClient` reads: lanes `{dense_64: 64, dense_full: 768, colbert: 128}` + `sparse`,
`points_count == 0`; **`v2` untouched at 3,869**. ⚠️ **`scripts/verify_collection_lanes.py` exits 2 on
an EMPTY collection** (*"an empty scroll is NOT a pass"*) — it is the **S3** gate (per-point lane
presence), **not** S2's; S2's assertion is the shape+count read-back, which is what was run.

**Stage C0 — the late-chunk pass, timed on 20 real PARENTS against v2's corpus** (read-only; one
cluster call per parent, per-token vectors, nomic config):

| | |
|---|---|
| sampled | **20 / 20** parents, **0 failed** |
| guards | **C0-G1, C0-G2, C0-G3, C0-G4 — all True** |
| corpus reproduced | 341 parents / 3,796 children / **11.132** per parent (exact) |
| per parent | mean **1.232 s**, p50 0.875 s, p90 4.467 s |
| **extrapolated to 341 parents** | **~7.0 min** (serial, mean×341) |

⚠️ **This replaces the derived ~48 min in the plan's cost table — the Shape B pass is ~7× cheaper
than assumed, and the biggest unknown in the re-ingest cost is now measured.** It also closes trap 3
end-to-end: **C0-G2 (alignment held, no token mismatch)** confirms the `(0, 2)` declaration against
the **live** endpoint, not just the offline probe.

**⚠️ Signoff 3 (Shape B) is at its confirmation point.** The plan made it provisional until C0; the
measured number is far under budget and Shape A is *not* cheaper, so Shape B stands. **OWNER to
re-confirm.**

**⚠️ Two records to fix, both §I44's class.** (a) The C0 probe writes to a **fixed** path, so the
nomic run **overwrote the gemma FAILED artifact**; the gemma evidence is preserved as
`c0_gemma_late_chunk_timing_FAILED.json` (and in git at `e020f0c`). **The probe should take an
`--out` argument** — a record that the next run can silently replace is not a record. (b) **A2 was
applied as ENV OVERRIDES for this run, not written to `.env`.** ⚠️ The plan designates `.env` as A2's
home so **Stage F can switch per arm in one process**; that flip is **still an owner action**, and
until it lands every stage must export `DENSE_MODEL`/`DENSE_DIM`/`DENSE_DIM_LOW`/`QUERY_INSTRUCTION`/
`DOCUMENT_PREFIX` explicitly or it will silently run Qwen3/1024.

**Register against:** §I77 (gemma's C0 failure at the same path, and why the measured number is
different), §I33 (a count-based gate is not a shape gate), §I76 (the lane inventory v3 must carry),
§I79 (the same session's other measurement), §I13 (a dimension is immutable — the reason v3 had to be
dropped rather than altered).

---

### I81. 2026-10-25 — ✅ S3: the Shape B re-embed into `knowledge_base_v3` is DONE — 3,796 points, all four lanes, ids preserved, and the late-chunk path reproduces the source at **cos 1.000000**

**What Shape B is.** Recompute the **dense** lanes with the configured embedder (**nomic,
late-chunked** — one cluster call per parent), **carry `colbert` + `sparse` over** from the source
(different models, unchanged vectors — plan §2's "carried over"), and upsert into the destination
**preserving every point id**. It is reproducible **without re-parsing**: the source payloads carry
`text` / `parent_text` / `char_start` / `char_end` / `parent_id` / `chunk_index` / `page_number`, so
the parent→child hierarchy and each child's span are reconstructed exactly — which is why the cards
and the graph (both keyed on `chunk_id`) stay valid.

**Built.** `scripts/reembed_chunks.py` gained a `--from-collection SRC` mode (the SQLite mode and its
§I13 refusal are **unchanged**; Shape B computes all lanes, so it does not refuse). ⚠️ **No child may
be dropped**: the late-chunk path returns `[]` for an empty parent and falls back to isolation when a
parent tokenizes to zero tokens, so any child not returned late-chunked is embedded in **isolation** —
that is what makes Verifier C-i passable. It checkpoints per parent and logs one line per parent with
a rolling rate (§I23/§I25 — a stalled run is distinguishable from a slow one).

**Run:** **3,796 points / 341 parents in 612.7 s (10.2 min)**, exit 0, **0 failures**. (C0's
extrapolation was ~7 min; the delta is the scroll + the upserts + the per-parent checkpoint write —
the extrapolation measured the late-chunk call alone, which is the honest reading of both numbers.)

**Verifiers (plan §3 Stage C, Verifier C) — `logs/p1/step10/reembed_v3_verify.py`, ALL PASS:**

| check | result |
|---|---|
| **V1** chunk_id set before == after | **3,796 / 3,796**, missing **0**, extra **0** (byte-identical sorted list) |
| **V2** every lane on every chunk point, per point | **3,796** checked, **0 bad** |
| **V5** point id preserved | every destination id exists in the source with the same `chunk_id` |
| **V3** A-vs-A, fresh embedders | **29 children**, `array_equal` (bit-identical) |
| **V4** known-vector spot check | Qwen3 recomputation reproduces the source's stored `dense_1024` at **cos = 1.000000** |

⚠️ **V4 is the strongest and is the one to insist on:** it proves the late-chunk path used by this
harness is the **shipped** one, not a re-implementation that happens to produce plausible vectors.

**The plan's own gate:** `scripts/verify_collection_lanes.py --collection knowledge_base_v3` →
**exit 0**, 3,796 points, **all four lanes 3,796 / 3,796** (`colbert`, `dense_64`, `dense_full`,
`sparse`).

**Negative control (the lane check discriminates):** pointed at `knowledge_base_v2` (which has no
`dense_full`) **V2 FAILS 3,796 / 3,796, exit 2** — so V2 can fail, and its PASS on v3 means something.

**⚠️ Two traps hit while writing the verifier, both worth keeping:**
1. **The embedder is a memoised SINGLETON.** `LateChunkEmbedder(old_settings)` silently reused the
   nomic instance already built for V3 and returned **768d vectors against a 1024d expectation** —
   V4 failed for the *wrong reason* until it built the old embedder **explicitly**. Any check that
   asks one process for two models must construct the second one itself.
2. The A-vs-A sample was **one child** (the first parent has one). Widened to the parent with the
   **most** children (29) — a one-span A-vs-A barely exercises the span→token mapping.

**⚠️ Scope, stated so it is not assumed:** **RAPTOR (73 nodes) is NOT in v3.** The harness logs
*"raptor is NOT re-embedded here"* and the gate reports **0 raptor**; RAPTOR re-embedding is a
separate step (`run_phase2.py --raptor-only`). And **no unit test was added for the Shape B mode** —
the verification is the live run plus V1–V5 plus the negative control. ⚠️ **`knowledge_base_v3` is
now POPULATED; `knowledge_base_v2` is still untouched at 3,869.**

**Register against:** §I13 (the dense-only refusal this mode resolves), §I33 (per-point, not counts),
§I80 (C0's measured basis), §I76 (the four lanes v3 must carry), §I44 (the checkpoint makes the run
resumable and its progress readable).

---

### I82. 2026-10-25 — ✅ S4's classifier half is DONE (768d, and it agrees with the gold labels +0.218 better than the 1024 one); ⚠️ the preflight half is NOT — 2 derived collections are still 1024d, and the gate was NOT edited to hide it

**Stage D — the retrain.** `scripts/train_intent_classifier.py --train-only` on the existing
1,158-query synthetic set, **re-embedded with nomic** (`(1158, 768)`), saved to
`data/models/intent_classifier.pkl`. The synthetic held-out accuracy is **99.6 %** — ⚠️ that is
self-consistency on synthetic queries, **not** a product measure; do not quote it as one.

**Verifier D — `logs/p1/step10/s4_intent_verify.py`, ALL PASS:**

| check | result |
|---|---|
| **V1** widths | new clf **768**, old clf **1024**, `cfg.dense_dim` **768** |
| **V2** the router's load guard is real | an `IntentRouter` with a 768 config pointed at the 1024 pickle **REFUSES it** (`_clf is None`) — the reason S4 is not optional |
| **V3** the router loads the new clf | `classify("What is Newton's second law?")` → `Intent.FACTUAL` |
| **V4** held-out comparison, 133 gold queries | agreement **new 0.5714** vs **old 0.3534**, Δ **+0.2180** |
| **V5** not degenerate | predicts all four classes on the gold set |
| **V6** a REAL query through the product funnel | **5 hits**, top chunk page 284, score **0.7367** |

⚠️ **V4's per-type detail is the interesting half:** `factual` 0.434 (old 0.264), `multihop` 0.725
(old **0.825** — the new one is *slightly worse* here), `overview` 0.600 (old **0.000** — the old
classifier was failing this class entirely). So the headline delta is real but it is **mostly the
overview class**, and the absolute agreement (**0.57**) is **moderate**: the synthetic training set
does **not** transfer perfectly to real gold queries. Reported, not buried — and note the classifier
has no `mixed` class while the router does (it falls back to prototypes for `mixed`).

**Stage E — the preflight (`logs/p1/step10/s4_preflight_v3.txt`): exit 1, and exactly TWO blockers.**

| blocker | detail |
|---|---|
| `qdrant.derivative_artifacts.dim` | **1024d** while the query side is **768d** — every query against the lane is REJECTED (73,406 points) |
| `qdrant.concept_embeddings.dim` | **1024d** vs 768d — same failure (6,065 points) |

⚠️ **This is exactly the mid-migration trap the plan predicted (§I26 / §I12 / §I47):** the derived
collections were built at the old width and have **not** been re-indexed for the 768 embedder, so a
check that compares them against `cfg.dense_dim` **cannot pass** yet. **The gate was NOT edited to get
past it** (the plan's explicit instruction). ⇒ **S4's "preflight exit 0" is NOT met, and it is not a
code fix — it needs the derived collections re-indexed at 768.**

**Everything else in the preflight PASSES:** `knowledge_base_v3` **3,796**; `intent-classifier`
**n_features_in_=768**; `visual_knowledge_base` 1,033; **`graph.matches-qdrant` 0/3,533 ids absent
(0.0 %), graph doc(s) present (3,796 points)**; Memgraph up (docs=1 chunks=3,533 concepts=6,065); and
every LLM endpoint. ⚠️ **The graph check passing is a real finding, not a coincidence:** the graph's
chunk ids match v3 because **Shape B preserved them** (§I81) — the graph did not need rebuilding.

**Register against:** §I26 (the mid-migration trap this is an instance of), §I12/§I13/§I47 (the
derived-collection width), §I81 (the id preservation that keeps the graph valid), §I79/§I70 (nomic),
§I47 (a count-based check holds a dead lane green).

---

### I83. 2026-10-25 — ✅ the preflight is CLEAN (exit 0): the two derived collections are re-indexed at 768, and the concept re-embed did NOT rebuild the graph

**The blockers, and their removal.** `derivative_artifacts` (73,406) and `concept_embeddings`
(6,065) were at the retired **1024d**. Both were dropped with
`scripts/reset_derived_collections.py --collections derivative_artifacts concept_embeddings --yes` —
⚠️ the **allowlisted** path, which refuses any other name. **`reset_for_reingest.py` is wrong here**:
it also clears `knowledge_base` and every SQLite row. `get_qdrant()` then recreated both at
`dense_dim` = **768**.

**Re-population — two different mechanisms, deliberately:**

* **`derivative_artifacts`** — `scripts/index_derivative_artifacts.py --clear --doc-id 7ba61432-…`
  (SQLite active cards; `embed_documents`, because these are passages). **73,406 points**, ~26 min
  (measured: a 32-doc embed call is **0.67 s** → 73,406/32 ≈ 2,294 calls). ⚠️ **The script
  accumulates every point in memory and upserts in 256-batches at the END**, so the collection reads
  **0 until it finishes** — that is not a stall, and reading it as one would have killed a healthy run.
* **`concept_embeddings`** — NEW `logs/p1/step10/reindex_concepts_768.py`, **6,065 points in
  1,433.7 s**. ⚠️ **It does NOT run `run_phase3.py --graph-only`**: that re-EXTRACTS concepts from
  every chunk (an LLM pass over 3,533 chunks, ~1 h 6 m) and **doubles every `RELATES_TO` weight**
  unless the graph is cleared first. **Only the vectors changed width** — the graph is valid — so
  only the **names** needed re-embedding. It reproduces `graph_builder._upsert_concepts_to_qdrant`
  exactly (`id = uuid5(NAMESPACE_DNS, "concept:<name>")`, payload `{name, type}`) and uses
  **`embed_query`** on the names, which is the graph builder's deliberate **both-sides** convention
  (§I12's note) — `embed_documents` here would put the index and the query in different spaces.

**Result: `scripts/preflight.py` against v3 exits 0 — *"All checks passed — safe to run the
baseline."*** The two dim checks now read **`768d == dense_dim`**; `knowledge_base_v3` 3,796;
`graph.matches-qdrant` **0/3,533 absent**; `intent-classifier` 768; Memgraph up. **S4 is complete.**

⚠️ **Cost:** ~50 min wall for the re-population (DA ~26, concepts ~24). The concept pass was
**4× the first estimate** (0.06 s/name suggested ~6 min): the builder's per-name `embed_query` loop
is **6,065 sequential round-trips**, and that is the cost of matching its convention rather than
batching.

**Register against:** §I12/§I13/§I47 (the dim mismatch these two collections carried), §I26 (the
trap that surfaced it), §I82 (S4's first half), §I75 (the graph is up and valid), §I81 (why the graph
survived).

---

### I84. 2026-10-25 — ✅ §I68's client-side-RRF fix is LANDED: the funnel is DETERMINISTIC, and the swap is **endpoint-identical** (ΔR@20 = **0.0** on all 133 queries). ⚠️ Blast radius was **THREE** test files, not two, and the merge silently DROPPED chunk_id-less candidates

**The fix.** `store._qdrant_search`'s multi-lane branch no longer calls
`query_points(query=FusionQuery(fusion=Fusion.RRF))`. It issues **one `query_points` per lane** (the
dense lane keeps its nested low→full prefetch; sparse/ColBERT are leaves) and fuses them in Python
with `store._rrf_merge`. The fused result is returned as `_FusedResponse`/`_FusedPoint` — the minimal
`.points[i].score/.id/.payload` shape `search()` reads — so `search()` is unchanged.

**1. ⚠️ THE MERGE CONSTANT IS MEASURED, NOT CHOSEN — Qdrant's RRF uses `k = 1`.** A scratch probe
(`~/.hermes/cache/scratch/i68_rrf_k_probe.py`, run against `knowledge_base_v2`) solved
`fused_score = Σ_lanes 1/(k + rank)` for the live server's own output: **implied k = 1.000 on every
one of the top 10 candidates** of `vec-001`. Hand-check: dense rank 119 → 1/120, sparse rank 2 → 1/3,
colbert rank 1 → 1/2, sum = **0.841667** = the server's returned score exactly. So the funnel calls
`_rrf_merge(..., rrf_k=1)`. ⚠️ **`_rrf_merge`'s own default is 60 (Cormack's classic)** — using it
would have rescaled every score ~60× and changed the ranking. The function's default is left at 60
(it is a general utility); the funnel passes `rrf_k=1` explicitly with the measurement in a comment.

**2. ✅ THE BEFORE/AFTER — `logs/p1/step10/i68_rrf_swap_ab.py` → `i68_rrf_swap_ab.json`
(sha256 `6609a64e…`), 133 queries, HyDE off, all five guards pass.** BEFORE = the retired server-side
fused call; AFTER = `store._qdrant_search` (the live product path).

| probe | BEFORE (server RRF) | AFTER (client merge) |
|---|---|---|
| determinism, 6 identical repeats | `ovw-041` **2/6**, `gold-004` **6/6**, `gold-078` **6/6**, `gold-052` **4/6** distinct | **1/6** on all four |
| top-100 id-sequence identical | — | **60 / 133** |
| top-100 mean Jaccard | — | **0.99955** (the BEFORE arm against *itself*: **0.99926**) |
| **R@20** (product convention) | **0.41049414968626663** | **0.41049414968626663** — **Δ 0.0**, CI [0, 0], **W/L/T 0/0/133** |

**The swap is score-preserving and endpoint-identical**: the page-level R@20 is bit-identical on
every one of the 133 queries, and the residual candidate-set difference (Jaccard 0.99955) is the
**same magnitude as the defect's own noise** (0.99926) — i.e. tie-breaking, not a behavioural change.
**The defect is removed and the endpoint did not move.** ⚠️ **Not production numbers** (HyDE off,
`fetch_k` 100) — the **delta** is the result.

⚠️ **The artifact is NOT byte-reproducible, and that is by construction**: one arm *is* the
nondeterministic one, so the BEFORE-derived counts move run to run — across the two runs, the
determinism counts read `gold-052` **5/6** then **4/6**, `identical_id_sequences` **65** then **60**,
`before_self_jaccard` **0.99955** then **0.99926**. **The endpoint fields did not move**: `r20_before`
and `r20_after` are **identical to the last digit in both runs** (0.41049414968626663, Δ 0.0). Quote
the endpoint; treat the wobble counts as the defect being measured, not as a statistic.

**3. ⚠️ BLAST RADIUS: THREE test files break by construction, not the two §I68 §4a recorded.**
`test_dense_prefetch_limit.py` and `test_downstream_widths.py` were named; **`test_lane_resolution.py`
was missed** — its `_inner()` reads `kwargs["prefetch"][0].prefetch[0]` and its two funnel tests read
`calls[0]["prefetch"][0]` for the full-dim lane, both of which the per-lane call shape removes. All
three are **rewritten to the new shape**, not deleted. `tests/test_backmatter_gate.py` monkeypatches
`_qdrant_search` by name only and is unaffected. **Proved, not asserted:** reverting the mechanism
(putting the server-side fusion back) fails **16** tests across the three files, **all on
`AssertionError`** (0 collection/syntax errors), including the new
`test_the_funnel_queries_each_lane_separately`; the source was restored byte-identically
(sha256 `625e2241…`).

**4. ⚠️ NEW FINDING, FOUND BY RUNNING IT — `_rrf_merge` silently DROPPED candidates with no
`chunk_id`, and Qdrant did not.** The first before/after run reported a **0.930** Jaccard and a
**+0.0040** endpoint delta. Root-caused, both were artifacts:
* **`_rrf_merge` keyed on `chunk_id` alone.** A scratch probe scrolled the whole collection: the
  **only** points with no `chunk_id` are the **73 `raptor_summary` nodes** (62/8/3 at levels 1/2/3);
  all **3,796** `base_textbook` chunks carry one. The retired server-side RRF keys on the **point
  id** and kept them; the merge dropped them. **Fixed** at the root: `cid = item.get("chunk_id") or
  item.get("qdrant_point_id")`, pinned by
  `test_rrf_merge_keeps_items_without_chunk_id_but_with_a_point_id` (mutation-proven — reverting the
  fallback fails it on its own assertion, other 15 pass). ⚠️ **The product was never at risk** —
  `search()`'s `_NOT_RAPTOR` filter excludes those nodes — but the drop was a **silent** one and the
  coupling was implicit.
* **The harness's filter was not the product's.** `i68_rrf_swap_ab.py` built a filter with page
  bounds + tenant but **omitted `_NOT_RAPTOR`** and the `is_content` exclusion, so it compared on a
  pool the product never sees. Corrected to mirror `search()` exactly; the endpoint delta went from
  +0.0040 to **0.0** and the Jaccard from 0.930 to 0.9997. ⚠️ **A harness that does not reproduce
  the product's own filter is not measuring the product.**

**5. ✅ THE HARNESS MOVED WITH THE PRODUCT (owner decision, on an independent verdict).**
`scripts/funnel_boundary_recall.py` claims to *"mirror store._qdrant_search exactly"*, so leaving it
on server-side RRF would have falsified that claim and made its B4/B5 numbers non-product numbers.
Its two RRF sites (B4 @~249, `rrf3` @~281) now call a local `fuse_lanes()` that mirrors the product
(`_rrf_merge`, `rrf_k=1`); the docstring says so. ⚠️ **`scripts/why_colbert.py` is deliberately LEFT
as-is** — a one-off diagnostic whose artifact is already written, not a product path and not a gate.
⚠️ **Pre-existing and NOT fixed (out of scope):** the harness's default `--merge colbert` uses ColBERT
as an outer query, which is *not* what the product does (the product fuses three lanes) — recorded so
it is not mistaken for a §I68 consequence.

**6. ⚠️ THE INDEPENDENT VERDICT, AND WHAT IT IS WORTH.** Reviewer `deleg_f6742a1d`
(`openai/gpt-oss-20b`, read-only, cross-family from the author's DeepSeek) returned **8/8 confirmed,
no refutations** — but it is a **cheap verdict (22 calls, 28.8 s)**, so it is **not banked**. Six of
its claims (C1–C6) are source claims it read itself and cited by identifier, and they agree with the
author's own reads; **C7/C8 were the author's own probe output handed over as data**, which a
read-only child can only check for internal consistency — those remain **author's mechanical
evidence, not a second opinion**. ⚠️ The reviewer's *own* premise for D1/D2 is what decided the
harness disposition; it did **not** catch the `_NOT_RAPTOR` filter omission or the `chunk_id` drop —
those were found by **running** the harness and root-causing its first numbers.

**7. Suite: 685 passed / 4 failed / 6 skipped.** The 4 are the documented pre-existing set
(`test_phase1` ×1, `test_phase2` ×1, `test_splade` ×2) — ⚠️ **proved, not assumed**: `store.py` was
stashed to HEAD and the same 4 fail. `_rrf_merge`'s 4 original tests still pass (an item with
*neither* id is still skipped).

**8. ⚠️ THE DIFF VERDICT, AND WHY THE COMMIT CARRIES NO `[verified]`.** Reviewer `deleg_dc2675b3`
(`openai/gpt-oss-20b`, read-only, cross-family) was given the 596-line diff by path and 7 claims, and
returned **7/7 CONFIRMED, no silent wrong answer** — ⚠️ but it is a **CHEAP verdict (19 calls,
33.6 s)** whose cited **line numbers do not resolve** (`_rrf_merge` "lines 212-213" — it sits near
780; `test_dense_prefetch_limit.py` "lines 247-266" — the file is ~110 lines; the harness mis-pathed
as `src/pdf_ingestion/scripts/…`). Its **identifiers** do resolve and are correct, so the verdict is
consistent with the code but **its citations are not evidence**, and per the standing rule it is
**not banked**. The substantive half is the author's **mechanical evidence**: the live determinism
measurement, ΔR@20 = 0.0, the two mutation proofs and the suite. **`[verified]` is deliberately OFF**
on commit `939beae`, and the commit body says exactly what was and was not established.

**9. ✅ COMMITTED `939beae`** (the fix, the three rewritten test files, the new guards,
`scripts/funnel_boundary_recall.py`, the harness + artifact, this entry). ⚠️ The only untracked files
left are the **arm-2 fragment** (`min_chunk_tokens_ab*.py`), deliberately out — the known-broken
fragment the brief says to treat as **arm 2 unstarted**.

**10. ⚠️ WHAT IS NOT DONE.** `why_colbert.py` is untouched by design. The **Stage F run itself has not
run** — its pre-registration is committed alone (`51de3f2`) and is the next step. ⚠️ **Do not run F on
top of an uncommitted product-path change** — that precondition is now satisfied (the fix is
committed), but F's own preconditions (§3's per-arm env, the HyDE cache) still apply.

**Register against:** §I68 (the defect and its measured blast radius — corrected here), §I67 (the
VOID it caused, and the A/B it blocked), §I66 (the fusion stage), §I61/§I76 (the lane shape and the
`sparse` lane the per-lane calls preserve), §I33 (a gate that reads the thing it asserts), §I44 (a
guard that passed once is not a guard that holds), §I47 (a mismatch must name its remedy).

---

### I85. 2026-10-25 — Stage F RAN: the index swap is a **NULL** at the product endpoint on the base lanes (ΔcR@20 = **−0.0012**, UNRESOLVED). The oracle screen's **+0.14** does **not** survive the funnel. ⚠️ Both derived lanes had to be turned OFF first — the whole derived layer is nomic-only

**The question.** The nomic plan's §3 Stage F: *does the nomic-768 index (`knowledge_base_v3`, arm
B) beat the incumbent qwen3-1024 index (`knowledge_base_v2`, arm A) at the **product retrieval
endpoint**, on the same 133 gold queries?* This is the product-endpoint counterpart of §I74 (the
cross-encoder on a fixed pool) and §I63/§I70 (the oracle screens). It is **the only stage whose
result can license a ship** (plan §5).

**⚠️ FIRST: the pre-registration could not be run as written, and the reason is a recurrence.**
`store.search_da` (`store.py:722`) queries `cfg.da_collection` with the **DENSE query vector**, whose
dimension **IS the arm's `dense_dim`** (1024 for A, 768 for B) — and `derivative_artifacts` is a
**single 768d collection** (§I83). So arm A's DA lane returned **HTTP 400** and `store.py:748`
**silently** logged a warning and returned `[]`, while arm B's was **live**: **not a single-variable
A/B**, and arm A could no longer reproduce Phase E (which ran when that collection was 1024d). ⚠️
**§D15/§I12 recorded the same 768-vs-1024 death in the §3d run** — the mechanism is not new; the
mismatch has merely flipped direction. The **same defect hit the GRAPH lane**: `graph_search` ranks
concepts through `concept_embeddings`, which §I83 also re-embedded at **768d**, so arm A's multihop
concept search 400s and the lane returns `[]` (`graph_builder.py:686`) — dead in A, live in B.
Measured: that handler does **not** call an LLM (the *"falling back to LLM"* text is misleading), so
it is an **asymmetry**, not a noise source.

**⇒ RE-REGISTERED (committed ALONE before the run: `e708784`, amended `a409d7d`;
`.hermes/plans/2026-10-25-p1-stageF-product-endpoint-reregistration.md`).** Three changes: **(a)** the
DA lane is **OFF in both arms**; **(b)** E8 is re-pointed from Phase E (DA ON) to **§3d** (the
registered DA-off retrieval-only v2 row, R@20 **0.452**), tolerance = the n=133 resolution floor
(±0.020), **not a fit**; **(c)** the GRAPH lane is **OFF in both arms**. ⚠️ **This NARROWS the
question and it is stated, not hidden:** the run measures the **base lanes**
(`dense(low→full) + sparse + colbert → RRF → page dedup → MMR → cross-encoder`) — the product funnel
**minus both derived lanes**, which are nomic-only in the current environment. The full-funnel
comparison is **unmeasured**.

**The run** (`logs/p1/step10/stageF_product_endpoint.py`; artifact `stageF_product_endpoint.json`,
sha256 `8ea21a83…`; per-arm `stageF_arm_{A1,A2,B1,B2}.json`; log `stageF_run_session20.txt`). Each arm
calls the **product's own** `evaluate_rag.run_retrieval` (embed → HyDE → `search_with_das` → shipped
cross-encoder) and scores with the product's own `compute_retrieval_metrics`. **HyDE ON and frozen**
(§I73 cache, 93 entries served) — a miss **raises**, never a live call. **133 queries, 0 errors, per
arm**; ~150 s/arm. Endpoints **P1** = paired Δ cR@20 (§I58), **P2** = paired Δ raw R@20, both **B − A**.

| endpoint | arm A (qwen3-1024) | arm B (nomic-768) | Δ (B−A) | 95 % CI | W/L/T | verdict |
|---|---|---|---|---|---|---|
| **P1 cR@20** (PRIMARY) | — | — | **−0.001213** | [−0.023051, **+0.020626**] | 21/26/86 | **UNRESOLVED** |
| **P2 raw R@20** (PRIMARY) | **0.4475** | **0.4463** | **−0.001185** | [−0.022523, **+0.020153**] | 21/26/86 | **UNRESOLVED** |
| S1 R@100 | 0.6469 | 0.6115 | **−0.0354** | [−0.0517, −0.0191] | — | **RESOLVED −** |
| S1 Hit@20 | 0.9173 | 0.9248 | +0.0075 | [−0.0181, +0.0331] | — | unresolved |
| S1 MRR | 0.7515 | 0.7273 | −0.0242 | [−0.0531, +0.0048] | — | unresolved |
| S1 Ctx.Prec | — | — | −0.0026 | [−0.0103, +0.0050] | — | unresolved |
| S1 NDCG@20 | 0.5018 | 0.4980 | −0.0037 | [−0.0179, +0.0105] | — | unresolved |
| S2 factual cR@20 | — | — | +0.0076 (n=53) | — | — | unresolved |
| S2 multihop cR@20 | — | — | −0.0183 (n=40) | — | — | unresolved |
| S2 overview cR@20 | — | — | +0.0042 (n=40) | — | — | unresolved |

**The decision — per the pre-registered rule (§6), NOTHING SHIPS.** P1's CI **straddles 0** and the
point estimate is **~18× below the run's own resolution floor** (`SD_d` 0.1285 → floor **0.021839**;
the required n for δ = 0.05 is **25.4**, so power was **ample** — the limit is the effect, not the
sample). Recorded **measured-and-unresolved**: **on the base lanes, at the product endpoint, the
nomic-768 index is indistinguishable from qwen3-1024.** ⚠️ **The one RESOLVED secondary is NEGATIVE
for nomic**: R@100 **−0.0354** [−0.0517, −0.0191] — nomic's fused pool covers **~3.5 pp fewer** labelled
pages. And every per-type cut is unresolved.

**⚠️ THE HEADLINE IS THE MECHANISM: the oracle gain does not survive the funnel.** §I63's oracle
screen measured **nomic − qwen3 = +0.1400** R@20 on the base lane (exact cosine, fixed corpus), and
§I74 measured **+0.068** at the cross-encoder on an oracle pool. Here, at the **product** endpoint, it
is **−0.0012 and unresolved**. The reading is structural and consistent with §I72/§I74: (i) the
**sparse and ColBERT lanes are model-independent**, so they contribute **identically** in both arms
and **dilute** the dense-lane difference; and (ii) the **cross-encoder is a strong equaliser**
(§I72: it lifted the *weaker* embedder ~44× more than the stronger). The dense-lane ranking advantage
the oracle sees is absorbed before the product's top-20.

**⚠️ A convention worth pinning, because it is scale-only here.** The §I58 divisor
(`mean(achievable_max)`) measured **0.97707 in BOTH arms** — identical by construction (v3 is v2's
chunks re-embedded, §I81), so **P1 = P2 / 0.97707** and the two primaries are the **same test up to
scale**: the divisor cannot change the sign, the CI-exclusion or the verdict. ⚠️ Note this run's
divisor (**0.97707**) differs from §I58's registered **0.9545** (a different instrument: a Qdrant
scroll with the product filter vs §I58's SQLite computation) — recorded, and **immaterial to the
verdict** for the reason above. ⚠️ Also not to be confused with §I84's `cr20` (≈4.44), a **per-query
top-k-slot** normalisation, a different convention entirely.

**✅ MECHANICAL EVIDENCE — all TEN guards pass, and the load-bearing two are the strongest.**
* **E8 (the harness IS the registered instrument):** arm A reproduces §3d's DA-off v2 row — R@20
  **0.4475** vs **0.452**, gap **−0.0045**, inside the ±0.020 floor. (The other four §3d columns:
  R@100 +0.021, Hit@20 +0.007, MRR +0.024, NDCG@20 −0.006 — all small, all consistent with §3d
  predating the §I68 swap and the §I58 label re-points.)
* **E4 (negative control):** each arm was run **twice**; **bit-exact on every metric of every query**
  in both arms (0 mismatches). This is a **legitimate** bit-exact control only because **§I68 landed**
  (the funnel is deterministic) — the reason the pre-registration could assert it.
* **E1/E2** (each arm's resolved config names its collection and a non-blank host, and matches
  `Qwen3/1024/v2` vs `nomic/768/v3`), **E3** (133 in every arm), **E5** (aggregates re-derive),
  **E6** (§I55 fallbacks named — **0 in both arms**), **E7** (min pool > 20 in both), plus
  **E_da_off_both_arms** and **E_divisor_identical_across_arms**.
* **A DA-gap cross-check on the re-registration's premise:** arm A is DA-OFF (R@20 **0.4475**),
  Phase E is DA-ON (**0.4250**) → gap **+0.0225**, close to **§I56's** independently measured
  **−0.0262** (the DA lane hurts). The premise holds.
* **An independently-written stdlib verifier** (`logs/p1/step10/stageF_verifier.py --check`,
  re-derives every aggregate from the raw per-query arrays): **V1–V8 ALL PASS**.
* ✅ **Independent cross-family reviewer `deleg_e607dda1` (`openai/gpt-oss-20b`, read-only, model
  resolved from `hermes config get delegation`) RETURNED: 7/7 CONFIRMED, no refutations — *"No claim
  remains unverified"*.** It re-derived the means, the paired delta, the CI, the W/L/T and the R@100
  row from the 34 KB compact extract **itself** (A_r20 0.4475, B_r20 0.4463, Δ −0.00118496, CI
  [−0.02252, +0.02015], 21/26/86; R@100 −0.03540 [−0.05169, −0.01912]), and confirmed 0 rows with a
  pool ≤ 20, all 133 ids present, no null metrics, 0 fallbacks. ⚠️ **NOT BANKED (4 API calls,
  71 s — a cheap verdict)**: per the standing rule the substantive half is the author's mechanical
  evidence (the ten guards, E4/E8, the stdlib verifier). It is corroboration, not a second opinion.

**⚠️ WHAT IS *NOT* DECIDED, stated plainly.** (1) **The full product funnel is unmeasured** — DA +
graph are off, so this run does **not** license a ship of the whole v3 stack; a resolved full-funnel
result would need a 1024d DA collection *and* a 1024d `concept_embeddings` (both are a write, and the
pre-registration forbade writes). (2) **The re-ingest remains a separate owner decision** (§I70/§I77):
~58.6 min ingest + 8.9 h cards + 1 h 6 m graph + every derived collection + the classifier — and
**this run gives it no support on the base lanes.** (3) **One corpus, one document, one day.** No
causal claim beyond these two indexes. (4) The **§I74 gemma-vs-nomic margin** is untouched — this run
compares nomic against the **incumbent**, not against gemma.

**Register against:** §I74 (the oracle cross-encoder contrast this is the product-endpoint
counterpart of), §I63/§I70 (the oracle screens whose +0.14 does not survive), §I72 (the cross-encoder
equaliser), §I56 (the DA-lane effect the DA-gap cross-check reproduces), §I58 (the ceiling
normalisation and its two conventions), §I83 (the 768 derived collections that forced the
re-registration), §D15/§I12 (the *same* 768-vs-1024 DA death, recurred), §I84 (the §I68 fix that
makes E4 a real control), §I73 (the HyDE cache), §I61/§I67/§I71 (the re-registration precedent).

---

### I86. 2026-10-25 — Stage G RAN: the stage decomposition on BOTH arms. ⚠️ It does **NOT** show "the fusion destroys nomic's advantage" — behind the 64d prefilter nomic's coverage is **worse at every stage**, and the only RESOLVED stage is the fusion pool

**The question.** The nomic plan §3 Stage G: *did the embedder fix the full-dimension ranking lane, or
just move the loss around?* Run on both arms after Stage F's null (§I85).

**Instrument** (`logs/p1/step10/stageG_decomposition.py` → `stageG_decomposition.json`; per-arm
`stageG_arm_{A,B}.json`; log `stageG_run_session20.txt`). Same two arms and the same DA-off /
graph-off / HyDE-frozen config as Stage F. **133 queries, 0 errors, ~145 s/arm.** Unit = **coverage of
a query's REACHABLE labelled pages** (§I66's unit), so rows compare across arms AND to §I66. Stages
**1–2 are exact brute force** (§I66's method — no ANN, no Qdrant scoring); **stages 3–4 are the real
product path**. Both collections hold the **identical corpus (3,489 in-chunk / 888 pages)** — asserted
(G5), not assumed.

**✅ THE KNOWN-ANSWER CHECK PASSES, and it is exact:** on arm A the probe reproduces §I66's exact-probe
rows — base **0.815136** vs §I66's **0.8151** (gap 3.6e-05) and cut **0.747763** vs **0.7478** (gap
−3.7e-05). So the instrument is anchored to §I66 before being trusted on v3. All five guards pass.

| stage | A = v2 / qwen3-1024 | B = v3 / nomic-768 | Δ (B−A) | 95 % CI | W/L/T | verdict |
|---|---|---|---|---|---|---|
| base (64d lane @N=1000) | 0.8151 | 0.8000 | −0.0152 | [−0.0627, +0.0324] | 34/49/50 | unresolved |
| after full-dim cut L=500 | 0.7478 | 0.6921 | **−0.0556** | [−0.1116, **+0.0004**] | 22/66/45 | unresolved (near) |
| after fusion (pool=100) | 0.6605 | 0.6247 | **−0.0358** | [−0.0521, −0.0195] | 7/51/75 | **RESOLVED −** |
| after cross-encoder (top-20) | 0.4588 | 0.4576 | −0.0012 | [−0.0226, +0.0202] | 21/26/86 | unresolved |

**⚠️ THE READING — AND A CORRECTION TO THIS SESSION'S OWN FRAMING.** The prior hypothesis (stated
before the run) was *"the oracle's +0.14 survives the base lane and the fusion destroys it."*
**The run does NOT support that, and the correction is the finding.** Every stage is **≤ 0 for nomic**,
the base stage is a **tie/negative (−0.0152, unresolved)**, and the **only resolved stage is the
fusion pool (−0.0358)**. So there is **no nomic advantage at the base stage to destroy**.

**⚠️ THE GAP ROW WAS THEN MEASURED, AND IT INVERTS §I63.** Added in the same session (the row §I86
first named as a gap): **full-dim over ALL 3,489 chunks, NO 64d prefilter** — §I63's oracle
configuration. It reproduces §I66's grid exactly on arm A (L=500 **0.828609** vs **0.8286**, gap
9e-06; L=1000 0.926563 vs 0.9266; L=2000 0.977258 vs 0.9773 — guard **G6**).

| full-dim, no prefilter | A = v2/qwen3 | B = v3/nomic | Δ (B−A) | 95 % CI | verdict |
|---|---|---|---|---|---|
| L=100 | 0.5192 | 0.4148 | −0.1044 | [−0.1559, −0.0530] | **RESOLVED −** |
| **L=500** | **0.8286** | **0.6887** | **−0.1399** | [−0.1805, −0.0994] | **RESOLVED −** |
| L=1000 | 0.9266 | 0.8257 | −0.1009 | [−0.1351, −0.0667] | **RESOLVED −** |
| L=2000 | 0.9773 | 0.9488 | −0.0284 | [−0.0459, −0.0109] | **RESOLVED −** |

**⇒ On the oracle's OWN configuration, v3's stored index is WORSE than v2 — by ≈ −0.14 at L=500, and
RESOLVED at every L.** That is the opposite sign to §I63's oracle (**nomic +0.1400**) at almost the
same magnitude.

**⚠️ AND THE CAUSE IS IDENTIFIED BY SOURCE-READ, not inferred — the two are not the same object.**
§I63's arm N built its corpus vectors with `cluster_embed([DOC_PREFIX + t for t in texts])`
(`cross_embedder_experiment.py:295`) — **POOLED whole-chunk embeddings** — while §I63's arm Q used
`scroll_pool`'s **stored** vectors (`:265`, `sims_q = m_q[:, :vq.shape[0]] @ vq`, `:329`). **So the
oracle compared POOLED nomic against v2's STORED vectors** — two different constructions, and it had
to: **v3 did not exist when it ran.** Measured live this session (12 in-window chunks per collection):
**stored-vs-pooled cosine — v2 `dense_1024` 0.9559 (min 0.881); v3 `dense_full` 0.8153 (min 0.502).**
So neither index stores pooled vectors, but **v3's late-chunked vectors sit much further from pooled
than v2's do** — and §I63's N arm was the pooled one. ⚠️ **The register already flagged this
distinction** (§I77: the §I70/§I72/§I74 gains *"embedded the text pooled, not late-chunked"*); Stage G
is the first measurement that makes it **consequential**.

**⇒ THE HONEST STATEMENT: the oracle's +0.14 was never about the index we built.** It is not that
"the oracle's gain fails to survive the funnel" — it is that the oracle **measured a different vector
construction**, and **v3 as built is worse than v2 at full-dim ranking coverage** (resolved), while the
product endpoint **ties** because the cross-encoder absorbs it (Stage F).

**⚠️ A NEW, CHEAP, UNRESOLVED QUESTION THIS OPENS.** Pooled nomic scored **well** (§I63, +0.14);
late-chunked nomic (v3) scores **worse than qwen3** (−0.14). That is **consistent with late chunking
being the cause** — but it is **NOT isolated**: no probe has yet compared pooled vs late-chunked
nomic on the same corpus and instrument. If late chunking is the cause, the lever is the
**ingestion (E3)**, not the embedder — a different fix with a different owner decision. **Named as the
next cheap test, not as a finding.**

**The mechanism that IS established:** the **cross-encoder equalises** — it shrinks the fused-pool gap
from **−0.0358 (resolved)** to **−0.0012 (unresolved)** at the top-20, reproducing §I72's equaliser
finding on the real funnel. And the fusion stage is where nomic's deficit becomes **resolved**.

**What it means for the fine-tune (S6).** The loss that is *resolved* sits at the **fused pool**, and
the cross-encoder **absorbs it before the product's cut** (R@20 is a tie). A better embedder therefore
has **very little room at the product's endpoint** — its gains are consumed either by the 64d
prefilter or by the cross-encoder. ⚠️ **This does not veto the fine-tune**, but it sets its ceiling
low and says the lever, if any, is in the **funnel**, not the embedder. ⚠️ And it is consistent with
§I66 (the 100-slot fusion output is the binding constraint) and §I67 (the width levers were nulls).

**Register against:** §I85 (the Stage F null this decomposes), §I66 (the decomposition method and its
known-answer rows — reproduced exactly here), §I63/§I70 (the full-dimension oracle whose +0.14 is NOT
reproduced behind the prefilter), §I72 (the cross-encoder equaliser, reproduced on the real funnel),
§I59 (the 64d lane as its own measurement), §I60 (the ANN loss excluded here by construction), §I58
(the reachable-page unit).

---

### I87. 2026-10-25 — ⚠️ **LATE CHUNKING IS THE CAUSE.** Pooled nomic **beats** qwen3 at full-dim coverage; the **late-chunked** index we built (v3) is the **worst of the three** — late chunking costs **+0.1547** coverage, RESOLVED

**The question §I86 opened.** §I86 measured v3 (late-chunked nomic) **worse** than v2 (qwen3) at
full-dim, no-prefilter coverage (L=500: 0.6887 vs 0.8286, RESOLVED) — the opposite sign to §I63's
oracle (**nomic +0.1400**), because §I63 embedded **POOLED** nomic while v3 stores **LATE-CHUNKED**
ones. **Is late chunking what costs the coverage?**

**Instrument** (`logs/p1/step10/pooled_vs_latechunk_nomic.py` → `pooled_vs_latechunk_nomic.json`,
sha256 `f089317f…`). **Three arms, ONE instrument** — full-dim exact cosine, **NO prefilter**,
coverage of a query's **REACHABLE** labelled pages, 133 gold queries:
`qwen3_v2_stored` (v2's `dense_1024`) · `nomic_v3_stored` (v3's `dense_full` = **late-chunked**) ·
`nomic_pooled` (nomic embedded **pooled** over each chunk's whole `text` with `search_document: ` —
§I63's own N-arm construction). Read-only, no LLM, 22 s for the 3,489 pooled chunks.

**✅ All four guards pass, and the two that anchor the instrument are exact:** `qwen3_v2_stored` L=500
**0.828609** vs §I86's **0.8286**; `nomic_v3_stored` L=500 **0.688664** vs §I86's **0.6887** — plus
one corpus and one page mapping across all three arms.

| full-dim, no prefilter | L=100 | **L=500** | L=1000 | L=2000 |
|---|---|---|---|---|
| `qwen3_v2_stored` (late-chunked) | 0.5192 | 0.8286 | 0.9266 | 0.9773 |
| `qwen3_pooled` | 0.5078 | 0.8071 | 0.9224 | 0.9766 |
| **`nomic_pooled`** | **0.5913** | **0.8433** | **0.9336** | **0.9786** |
| `nomic_v3_stored` (**late-chunked**) | 0.4148 | **0.6887** | 0.8257 | 0.9488 |

**Paired contrasts at L=500 — each arm pair scored on the SAME 133 queries:**

| contrast | Δ | 95 % CI | W/L/T | verdict |
|---|---|---|---|---|
| **`nomic_pooled` − `nomic` late-chunked** (THE isolation: same model, same corpus, only the construction differs) | **+0.154662** | [+0.112818, +0.196505] | 77/5/51 | **RESOLVED** |
| `qwen3_pooled` − `qwen3` late-chunked | −0.021517 | [−0.051683, +0.008649] | 23/36/74 | **unresolved** |
| **`nomic_pooled` − `qwen3_pooled`** (like-for-like, both pooled) | **+0.036233** | [+0.003382, +0.069084] | 38/29/66 | **RESOLVED** |
| `nomic` late-chunked − `qwen3` late-chunked (like-for-like, both late-chunked) | **−0.139946** | [−0.180467, −0.099424] | 7/73/53 | **RESOLVED** |

**⇒ THE READING — and the added `qwen3_pooled` arm is what makes it clean.** ⚠️ **The sign flip is an
INTERACTION: late chunking × nomic.** Late chunking costs nomic **+0.1547** (RESOLVED) but qwen3 only
**−0.0215** (unresolved, i.e. ≈ neutral). Like-for-like, **pooled nomic BEATS pooled qwen3 (+0.0362,
RESOLVED)** — reproducing §I63's direction properly this time — while **late-chunked nomic LOSES to
late-chunked qwen3 (−0.1399, RESOLVED)**. So **v3 as built is the worst of the four arms, and the
reason is the ingestion, not the model.**

⚠️ **AND THE INTERACTION POINTS AT H2, NOT H1.** If late chunking were simply bad, it would hurt qwen3
too. **It does not.** A cost that appears **only for one model** is the signature of a **model-specific
defect**, not of a general property of late chunking.
* **H1 — late chunking genuinely degrades nomic on this corpus.** Not formally excluded, but it now has
  to explain why the same operation is ≈neutral for qwen3.
* **H2 — the nomic late-chunk path MIS-POOLS (a defect).** ⚠️ **The magnitude is the tell:** stored-vs-
  pooled cosine is **v2 0.9559 (min 0.881)** but **v3 0.8153 (min 0.502)**. A correctly pooled child
  should sit **close** to pooled(child text) — the parent's context perturbs it, it does not halve its
  cosine. A child at **0.502** looks like the wrong token span, not like extra context.
* ⚠️ **What was verified, and what was NOT.** §I80's C0-G2 confirmed the `(0,2)` alignment **count**
  against the live endpoint, and §I81's V4 verified that a **Qwen3** recomputation reproduces v2's
  stored vectors at **cos 1.000000**. **Neither verifies that a nomic child's late-chunked vector
  equals a manual pooling of the parent's token vectors over that child's span** — a count is not a
  span. That check does not exist in the repo. **It is the cheap next test, and it discriminates H1
  from H2.**

**⇒ WHAT IT MEANS FOR THE FINE-TUNE (S6).** ⚠️ **S6 is aimed at the embedder, but the measured lever is
the INGESTION.** Fine-tuning nomic and then late-chunking it would run the fine-tune's gain through the
same loss that currently costs 0.155 — and a fine-tune on late-chunked vectors would be training on the
degraded construction. **Re-target before spending GPU hours.** ⚠️ And it is consistent with §I86's
funnel finding: the resolved product-level loss is at the **fused pool**, and the cross-encoder
absorbs it — so the ingestion loss is *masked* at the endpoint, which is why Stage F saw a null.

**Register against:** §I86 (the deficit this explains, and whose guards anchor this instrument), §I63
(the oracle whose N-arm construction is reproduced here — and whose direction survives), §I81 (Shape B
late-chunked re-embed — the construction measured here), §I80/§I78 (the alignment declaration and the
prefix/span work whose verification this shows is INCOMPLETE for nomic), §I77 (the pooled-vs-late-chunked
distinction first flagged there), §I85 (the product null this is the masked version of), §I72 (the
cross-encoder equaliser).

---

### I88. 2026-10-25 — H1 vs H2 RESOLVED: the late-chunk path is **FAITHFUL** (cos **1.000000** to an independent span-pooling). Late chunking genuinely costs nomic 0.155 — it is a METHOD choice, not a bug

**The question §I87 left open.** §I87 measured late chunking costing nomic **+0.1547** (RESOLVED) while
being ≈neutral for qwen3 (−0.0215, unresolved). **H1** = late chunking genuinely degrades nomic;
**H2** = the nomic late-chunk path **mis-pools** (a defect). The tell for H2 was the magnitude
(stored-vs-pooled cosine **v3 0.8153, min 0.502**).

**Instrument** (`logs/p1/step10/latechunk_span_audit.py` → `latechunk_span_audit.json`). An
**INDEPENDENT reimplementation** of the span math — it does **not** call `LateChunkEmbedder`: it
tokenizes the prefixed parent itself, shifts the child's char span by `len(prefix)`, takes the
endpoint's per-token vectors, drops the declared `(0,2)` specials, and mean-pools the tokens inside
the span. 83 children across 6 parents, read-only, no LLM.

**✅ RESULT — the shipped path reproduces it EXACTLY: `cos(manual, stored) = 1.000000` on all 83 rows
(mean, median and min all 1.000000; 0 rows below 0.99).** ⇒ **H1. Late chunking is faithfully
implemented.** The 0.155 coverage loss is a **genuine property of late chunking × nomic**, not a
pooling defect. ⚠️ **This does not say late chunking is a good idea — it says the loss is real.**

**⚠️ A minor defect FOUND and SIZED, and it is immaterial.** `char_end` runs **exactly one character
past** the child's text (`span = text + 1 trailing char`; only 6/83 offsets reproduce the text
byte-exactly). **Sized, not assumed:** pooling over the given offsets vs over the exact child text
gives the **same token count on 83/83 rows** and **cos 1.000000 either way** — the extra character
does not start a token. **Recorded, not fixed** (it cannot move a vector). ⚠️ It is why an
`offset_exact` byte-equality check reads 6/83 and must not be mistaken for a span bug.

**⇒ WHAT IT LICENSES (the cheap win).** Since the loss is a **method** choice, the fix is to **drop
late chunking for nomic** and re-embed v3's **dense lanes pooled** — **Shape B** (§I81's own machinery:
ids preserved, **no re-parse, no LLM, no cards, no graph**, ~10 min). ⚠️ **And pooled nomic already
BEATS qwen3 (+0.0362, §I87), so this is the single cheapest path to an index that is better than the
incumbent.** It is a **write** (v3's dense lanes) and therefore an **owner decision**.

**Register against:** §I87 (the deficit and the H1/H2 fork this resolves), §I81 (the Shape B re-embed
whose machinery the fix reuses), §I80/§I78 (the alignment work — now shown sufficient for the span
math, with one cosmetic off-by-one), §I86 (the full-dim deficit), §I63 (the pooled construction this
vindicates), §I77 (the pooled-vs-late-chunked distinction).

---

### I89. 2026-10-26 — Stage G RE-RUN on the POOLED index: the base-lane advantage is **LARGE** (+0.104, RESOLVED) and the **FUSION destroys it**. ⚠️ §I86's *"no base-lane advantage to destroy"* is **falsified**

**The write that made it necessary.** §I88 resolved H1 — the nomic late-chunk path is **faithful**
(cos 1.000000 to an independent span-pooling) — so the 0.155 coverage loss is a **METHOD** choice, and
the treatment is to **drop late chunking for nomic**. Done via a new Shape B mode
(`scripts/reembed_chunks.py --from-collection knowledge_base_v2 --pooled`, backed by
`LateChunkEmbedder.embed_isolated_batch`): **3,796 points / 341 parents / 0 failures / 91.9 s**, point
ids and the `chunk_id` set **byte-identical**, `colbert` + `sparse` + every payload key carried over
from v2 **unchanged**, `knowledge_base_v2` **untouched (3,869)**.

**Acceptance** (`logs/p1/step10/pooled_reembed_{pre,post,carryover}.py/.json`; post sha256
`3d751cf9ce5a8d4f…`), all guards pass — the check §I88 said did not exist:

| check | pre-write | post-write |
|---|---|---|
| cos(stored `dense_full`, a **fresh** pooled embedding) | **0.804564** (min 0.5949; 199/200 < 0.99) | **1.000000** (0/200 < 0.99) |
| v3 coverage, full-dim, no prefilter, L=500 | 0.688664 *(= §I86's late-chunked row)* | **0.843325** *(= §I87's `nomic_pooled` row)* |
| v3 coverage L=100 / 1000 / 2000 | 0.4148 / 0.8257 / 0.9488 | 0.591316 / 0.933638 / 0.978649 |
| lane gate | — | all four lanes on all 3,796 points, exit 0 |

⚠️ **A guard was mis-specified on the first draft and is recorded:** the collection holds **3,796** chunk
points but the content window admits only **3,489**; a guard that asserted 3,796 against the *windowed*
population read as a failure on a correct index. Split into `G1a_collection_points_total_3796` and
`G1b_chunk_points_in_window_3489` (§I71/§I72's population-naming class).

**The re-run.** Pre-registration
`.hermes/plans/2026-10-26-p1-stageG-rerun-preregistration.md`, **committed ALONE as `3d3026e`** before
the run. Same instrument and arms as §I86 — A = `knowledge_base_v2`/Qwen3-1024 (control), B =
`knowledge_base_v3`/nomic-768 (**now pooled**) — four stages, DA and graph OFF (§I85's constraint),
HyDE frozen from the §I73 cache. **All 8 guards pass**, including **two added by this re-registration**:
**G7** (arm B's gap row reproduces §I87's `nomic_pooled` at L=500 — **gap 0.000000**) and **G8** (arm A
**bit-exact** against §I86's arm-A rows — **all five gaps 0.000000000**). ⚠️ **G8 is the strongest
control in the run**: arm A shares nothing with the treatment, so if it moved, nothing would be
attributable. It did not move. Artifact `logs/p1/step10/stageG_decomposition.json`
(sha256 `8a2fd64b317f2d22…`); the §I86 artifacts are preserved as `stageG_*_session20_latechunked.json`.

**The result — coverage of a query's REACHABLE labelled pages (§I66's unit), paired Δ = B − A, n=133:**

| stage | A (v2/qwen3) | B (v3/nomic pooled) | Δ | 95 % CI | W/L/T | verdict |
|---|---|---|---|---|---|---|
| base (64d lane @ N=1000) | 0.815136 | 0.918953 | **+0.103817** | [+0.0689, +0.1387] | 67/8/58 | **RESOLVED +** |
| after full-dim cut L=500 | 0.747763 | 0.838136 | **+0.090373** | [+0.0479, +0.1329] | 60/19/54 | **RESOLVED +** |
| after fusion (pool = 100) | 0.660452 | 0.641322 | **−0.019129** | [−0.0371, −0.0011] | 17/38/78 | **RESOLVED −** |
| after cross-encoder (top-20) | 0.458824 | 0.462533 | +0.003709 | [−0.0206, +0.0280] | 24/22/87 | unresolved |

Gap row (full-dim, all 3,489 chunks, no prefilter): L=100 **+0.072112 RESOLVED**, L=500 +0.014716, L=1000
+0.007076, L=2000 +0.001391 — the last three unresolved. Raw product metrics: R@100 (pool) A 0.646897 /
B 0.627939; R@20 (top-20) A 0.447496 / B 0.451298.

**⇒ THE READING, and it inverts §I86.** On the **late-chunked** index every stage was ≤ 0 and §I86
concluded there was *"no base-lane advantage to destroy"*. On the **pooled** index the advantage is
**large and resolved** — **+0.104** at the 64d lane (67 wins to 8 losses) and **+0.090** after the
full-dim re-rank — and it is **destroyed at the fusion**: B's coverage falls **0.838 → 0.641** (−0.197)
while A's falls 0.748 → 0.660 (−0.087), and the arm difference **flips to −0.019, RESOLVED negative**.
At the product's top-20 the two indexes are **indistinguishable** (+0.004, unresolved) — which is exactly
why Stage F (§I85) saw a null at the endpoint.

⚠️ **Mechanism, stated as consistent-with and NOT proven:** the **sparse and ColBERT lanes are
model-independent** and therefore identical in both arms, so RRF gives a better dense lane no extra
weight — it dilutes it. §I85 named the same dilution; this measures it on a **fixed** index with a large
upstream gain to lose. **The split between RRF, page-dedup and MMR remains UNATTRIBUTED** (§I66's own
caveat), and **MMR is the leading suspect** — MMR penalises "redundant" candidates, and a page carrying
many relevant chunks looks exactly like redundancy while our metric is **page-level**.

⚠️ **A confound, stated not hidden:** the stage-1 comparison is **not like-for-like** — arm A is qwen3
**late-chunked**, arm B is nomic **pooled**, two differences. The like-for-like pooled-vs-pooled contrast
is §I87's (+0.0362, RESOLVED). And Stage G is **diagnostic**: it ships nothing; the ship decision is
Stage F's.

**⇒ THREE NEW FINDINGS, all of them plan-changing:**

1. **The fusion is the binding constraint** — measured on a fixed index, with a large upstream gain to
   destroy. **Not the embedder, not the ingestion.** ⇒ **S6 (the embedder fine-tune) is aimed at the
   wrong stage** — it sharpens the lane the fusion discards.
2. ⚠️ **A lane-complete v2-vs-v3 A/B is blocked by a DEFECT, not by physics.** `store.search_da` and
   `graph_builder._find_concepts_scored` both take the **arm's** dense query vector and send it to a
   768-dim collection, so a 1024-dim arm 400s, the lane's `except` swallows it and returns `[]` — the
   lane is **silently skipped** (§D15/§I12's recorded defect). **The fix is one query vector per space**
   (embed the lane's query with the model that BUILT the collection). It makes the derived layer a
   **held-constant across arms** — which is what a clean A/B wants. ⚠️ Scope: production is 768-dim, so
   **production is unaffected**; it is the v2/1024 *arm* that is broken.
3. ⚠️ **The overview (RAPTOR) lane has NEVER been on the eval path.** `evaluate_rag.py` does not call
   `search_raptor`; the only caller in the repo is `streamlit_app.py:589`. So any claim that "the funnel's
   overview path reads RAPTOR" is **false as measured**. And v3 has **0** RAPTOR nodes (v2 has 73).

⚠️ **Also stated:** the **visual (ColPali) lane cannot be measured with the current gold set** —
`visual_knowledge_base` holds 1,033 points for the **old** doc `6d55c52b` only, and the **33 visual
queries carry no `relevant_pages`** (which is why the gold set is 133, not 166).

**⇒ THE PLAN THIS PRODUCES:** `.hermes/plans/2026-10-26-p1-nomic-full-lanes-and-fusion-plan.md` — the
per-space query-vector fix, RAPTOR into v3 + wiring the overview lane, MRR/nDCG on the ladder, three
measurement tracks (T1 base-lane A/B · T2 nomic-only lane ablation · T3 full-funnel A/B), then the
fusion attribution. **Nothing in it is built or measured.**

**Register against:** §I86 (the decomposition this re-runs, and whose headline it falsifies), §I88 (the
write this measures), §I87 (the pooled row this reproduces exactly, and the like-for-like contrast),
§I85 (the product null this explains), §I66 (the binding-constraint finding this confirms), §I67 (the
width null this contextualises), §I72 (the cross-encoder equaliser), §D15/§I12 (the silent derived-lane
death, now with a fix), §I55 (the reranker's swallowed failures), §I81 (the Shape B machinery reused).

### I90. 2026-10-27 — T0 RAN: the full-funnel nomic BASELINE, and the aperture. ⚠️ The dense lane **through Qdrant is IDENTICAL to the exact computation** at L=500, and the aperture is **INERT until τ ≈ 0.7** because the K cap does the cutting

**Instrument.** `.hermes/plans/2026-10-27-p1-t0-baseline-preregistration.md`, **re-registered** the same
day (`.hermes/plans/2026-10-27-p1-t0-baseline-reregistration.md` — **boundary 5** = the product's dense
lane *through Qdrant*, and `precision@k`/`F1` added to V4's re-derivation). ⚠️ **The re-registration was
written BEFORE any number existed** — the first four attempts were blocked by the shared cluster (see
`HANDOFF.md` session 22), so **no result was ever produced under the original registration.** 133 labelled
queries, one arm (`knowledge_base_v3` / nomic-768, DA **and** graph **ON** — the product's real lane set),
HyDE **ON and frozen**, **read-only**, wall **2,707.8 s**, **0 errors**.

**ALL TEN harness guards pass** (G1–G10), and **the independent verifier passes V1–V6** on the real
artifact. ⚠️ **G3 reproduces §I89's arm-B EXACT rows to 4.4e-07 and 5.1e-08** (cov_base **0.918953**,
cov_cut **0.838136**) — the instrument IS the registered one. Artifact
`logs/p1/step10/t0_baseline.json` (sha256 `9a5037308c71c02d…`, 11.5 MB).

**The funnel** (coverage of a query's REACHABLE labelled pages, §I66's unit, n=133):

| boundary | coverage | Δ vs previous | recall@20 | MAP | nDCG@20 |
|---|---|---|---|---|---|
| 1 base — exact 64d MRL @N=1000 | **0.918953** | — | 0.3548 | 0.2315 | 0.3931 |
| 2 cut — exact full-dim @L=500 | **0.838136** | **−0.0808** | 0.4242 | 0.2925 | 0.4919 |
| **5 b5 — the SAME lane through QDRANT (ANN)** | **0.838136** | **0.000000** | 0.4242 | 0.2925 | 0.4919 |
| 3 fusion — product pool (≤100) | 0.684486 | −0.1537 | 0.4491 | 0.3421 | 0.5506 |
| 4 ce — product reranked top-20 | 0.455330 | −0.2292 | 0.4442 | 0.2789 | 0.4946 |

⚠️ **THE HEADLINE IS ROW 2 vs ROW 5: they are IDENTICAL on every metric, on every query.** G10's
ANN-vs-exact page overlap is **1.000000**, and G9's mean score gap is **2e-06**. ⇒ **at L=500 the vector
database's approximate search loses NOTHING against exhaustive arithmetic on this corpus** — the
"exact vs real-world" distinction the exact boundaries were criticised for is, **at this limit, empty**.
⚠️ **Scope: this is L=500.** The product's own dense call inside `search_with_das` uses `limit=100`
(`mmr_candidates`), and the funnel's big losses are **downstream** (fusion −0.154, cross-encoder −0.229),
not in the index.

**The aperture (recall-vs-τ, K=100 PAGES, base and cut/b5).** τ ∈ {0.0 … 0.9}:

| τ | base recall@K | base admission (uncapped) | cut/b5 recall@K | cut/b5 admission |
|---|---|---|---|---|
| 0.00–0.45 | 0.5563 | 513 | 0.6093 | 304 |
| 0.60 | 0.5563 | 509 | 0.6060 | 247 |
| 0.70 | 0.5558 | 414 | 0.3738 | 16 |
| 0.80 | 0.3522 | 32 | 0.0782 | 0 |
| 0.85 | 0.1564 | 2 | 0.0263 | 0 |
| 0.90 | 0.0365 | 0 | 0.0000 | 0 |

⚠️ **THE FINDING: the aperture is INERT until τ ≈ 0.7, because the K=100 cap — not a similarity bar —
is doing the cutting.** 513 pages clear τ=0.0 at the base and 414 still clear τ=0.70, but only 100 are
admitted, so recall@K does not move. That is **W1 §10.2.1's "blind K-NN" critique measured on our own
system**, and it is why the historical `0.45` could never have been a real aperture (§C2). The knee sits
between **0.70 and 0.80** for the base, and between **0.60 and 0.70** for the cut. ⚠️ **No τ is
committed** — the curve is the result (pre-registration §8).

**Per type, at the endpoint (cross-encoder).** coverage: factual **0.5577** · multihop **0.5812** ·
overview **0.1937**. ⚠️ **Overview is the loss**, and the overview lane (RAPTOR) is **absent from v3 and
not on the eval path** (B1/B2 unbuilt) — consistent with §I89 finding 3.

**⚠️ TWO VERIFIER DEFECTS WERE FOUND BY RUNNING IT, both over-strict checks on correct data, both
fixed and recorded** (`logs/p1/step10/t0_mutation_log.txt`): (a) **V3** asserted `da_live == n_queries`
and failed on a correct run where the DA lane was live on **132/133** — G6 requires non-empty on *at
least* the queries it should, so the bound is now `0 < live ≤ eligible` with the shortfall **reported**
(`da_shortfall 1`); (b) **V4** reported a MAP mismatch on `gold-033` (**0.05625** vs recorded **0.0563**)
— the **rounding boundary**, 1.4e-18 above a 5e-5 tolerance. ⚠️ **An over-strict check is worse than no
check: it gets switched off.** ⚠️ A third defect was found earlier — **V6's `recall_at_100` compared the
top-100 pages while the harness computes that key as the POOL recall** (gold-004: 0.0 vs 0.6667).

**Mutation proof (V1–V6, 7 mutations, `t0_mutation_log.txt`):** each mutation turns **exactly** its own
stage red; **MV5** reddens **both** V5 and V6 (the same recorded quantity exists at both swept
boundaries); **MV7** isolates the V4 extension (only `precision@20`/`F1@20` are corrupted, and only
those two checks fire); **MV6** is the case the harness's **own** guard cannot see — the record is
corrupted while G9 is computed from the live variable, so only the verifier catches it. Source restored
byte-identical (`bf313c4a…`) after every mutation.

**⚠️ What T0 does NOT measure** (unchanged from the registration): the visual lane (no ColPali data for
the new doc; the 33 `vis-*` carry no labels), RAPTOR (absent and off-path), the generator stage, and any
cross-index (v2-vs-v3) claim — that is T1/T3. ⚠️ **T0 ships nothing**; it is the reference table.

**⚠️ Independent reviewer (read-only, `openai/gpt-oss-20b`, cross-family, on the 26 KB compact extract —
never the 11.5 MB artifact): 7/7 CONFIRMED, no refutations, no additional risks. NOT BANKED** — it is a
**cheap verdict (2 API calls, 18.2 s)**. ⚠️ Its cited field paths DO resolve, spot-checked against the
extract: `aperture.base.per_tau["0.70"].recall_at_K` 0.555753, `["0.60"].admission_uncapped_mean`
509.045113, `["0.85"].recall_at_K` 0.156361, `guard_detail.G9_b5_mean_scale_gap_top20` 2e-06,
`G10_b5_mean_overlap_with_exact` 1.0, `aggregate.ce.by_type.overview.coverage_reachable` 0.193733 —
every one matches the quoted value. ⚠️ **The substantive half is the mechanical evidence, not the
verdict:** the ten harness guards, **V1–V6 ALL PASS**, and the seven-mutation proof.

**Register against:** §I89 (whose exact rows G3 reproduces, and whose fusion finding this confirms),
§I66 (the coverage unit and the funnel decomposition), §I86 (the decomposition this supersedes on v3),
§I67 (the width null — the K cap this now measures as inert), §I72 (the cross-encoder equaliser, visible
again as ce < fusion on every metric except MRR), §C2 (the score-scale/aperture finding, now measured),
§I55 (the reranker's swallowed failures — 0 fallbacks here), §I85 (the product null this explains).

### I91. 2026-10-27 — T1 RAN: the BASE-LANE ship test on the **POOLED** index — a **NULL** at the product endpoint. ⚠️ A **+0.104** base-lane advantage is worth **+0.0039** at the endpoint, and **E9 proves arm A did not move**

**Instrument.** `.hermes/plans/2026-10-27-p1-t1-base-lanes-preregistration.md`, **committed ALONE as
`3ab62f7` before the run** (D6.1). **T1 is not a new instrument**: it is Stage F's **re-registered**
instrument (`51de3f2` + `e708784`/`a409d7d`) re-run against the index that changed underneath it — the
harness (`logs/p1/step10/t1_base_lanes.py`) is a deliberate **copy** of `stageF_product_endpoint.py`, so
the only difference between the two runs is the treatment. 133 labelled queries, two arms (A =
`knowledge_base_v2` / qwen3-1024, B = `knowledge_base_v3` / nomic-768 **pooled**), HyDE **ON and frozen**,
**read-only**, wall A1 344.5 s / A2 1387.9 s / B1 359.4 s / B2 319.7 s, **0 errors**. Artifact
`logs/p1/step10/t1_base_lanes.json` (sha256 `f84e4b6599ee1f99…`).

**ALL ELEVEN GUARDS PASS**, and the two load-bearing ones are the point:

* **E8 — arm A reproduces the registered §3d row:** aggregate R@20 **0.4475** vs **0.452**, gap
  **−0.0045**, inside the ±0.020 floor. The harness **IS** the registered instrument.
* **E9 (NEW) — arm A is BIT-EXACT against Stage F's recorded arm A** (`stageF_arm_A1.json`, session 20):
  **133/133 compared, 0 mismatches** on all six endpoint metrics. ⚠️ **This is the strongest control in
  the run**: arm A shares nothing with the treatment, so a bit-exact match across two different sessions
  makes "the treatment is isolated to arm B" a **measurement**, not an assumption. ⚠️ Only those six keys
  are compared **by name** — `compute_retrieval_metrics` gained `map`/`precision_at_k`/`f1_at_k` after
  Stage F (§I90), so a whole-dict comparison would have been an over-strict check failing on correct data.
* Plus E4 (A1 vs A2 bit-exact, 0 mismatches), E1/E2/E3/E5/E7, `E_da_off_both_arms`, divisor identical.

**THE RESULT — a NULL, and the shape repeats Stage F.**

| endpoint | Δ (B − A) | 95 % CI | W/L/T | verdict |
|---|---|---|---|---|
| **P1 cR@20 ceiling-normalised** (§I58, primary) | **+0.003894** | **[−0.020984, +0.028771]** | 24/22/87 | **UNRESOLVED** |
| **P2 raw R@20** (primary) | **+0.003805** | [−0.020503, +0.028112] | 24/22/87 | **UNRESOLVED** |
| S1 **R@100** | **−0.018953** | **[−0.036938, −0.000969]** | — | **RESOLVED NEGATIVE** |
| S1 Hit@20 / MRR / Ctx.Prec / NDCG@20 | +0.0075 / +0.0289 / +0.0011 / +0.0006 | all straddle 0 | — | unresolved |
| S2 factual (n=53) | +0.010310 | [−0.048981, +0.069601] | 6/7/40 | unresolved |
| S2 multihop (n=40) | −0.003554 | [−0.029711, +0.022603] | 3/4/33 | unresolved |
| S2 overview (n=40) | +0.002840 | [−0.004851, +0.010532] | 15/11/14 | unresolved |

⚠️ **The point estimate is ~6× BELOW the run's own resolution floor (0.024878 at n=133).** Power was
ample, not the limit (SD_d 0.1464 → **n = 33** would suffice for δ = 0.05). **Per the pre-registered rule
NOTHING SHIPS**, and the honest statement is the registered one: the pooled nomic index does **not**
beat the incumbent qwen3 index at the product retrieval endpoint on the base lanes — a **RESULT**, not
merely an unresolved one.

**⚠️ THE HEADLINE IS THE MECHANISM, AND IT IS THE THIRD TIME.** The pooled index's base-lane advantage is
**large and resolved upstream** (§I89: **+0.104**; like-for-like **+0.0362**, §I87). At the endpoint it is
**+0.0039, unresolved**. The chain is now: **+0.104 (base) → +0.090 (full-dim cut) → −0.019 RESOLVED NEG
(fusion) → +0.0039 unresolved (endpoint)**. ⇒ **the funnel does not preserve the embedder's advantage; it
discards it.** §I85's product null and §I89's Stage-G decomposition are both reproduced here on the pooled
index, and the **diagnostic D1** says the same thing from the other side: **arm B pooled − arm B
late-chunked = +0.004989, CI [−0.014788, +0.024767], UNRESOLVED** — i.e. the pooled re-embed, worth
**+0.1547** at the base lane (§I87), is worth **+0.005** at the endpoint.

⚠️ **The one RESOLVED secondary is NEGATIVE and replicates:** **R@100 −0.0190 [−0.0369, −0.0010]** —
nomic's fused pool covers ~1.9 pp fewer pages at the `fetch_k` cut, against Stage F's **−0.0354
[−0.0517, −0.0191]**. **Two independent runs, same sign, same order** — a real property of this index at
this stage, and it is *not* the endpoint the student sees (top-20 is where they look).

⚠️ **The DA lane and the graph lane are OFF in both arms** — both derived collections are 768d (§I83), so a 1024d
arm 400s and the lane is **silently skipped**; leaving either on would be a non-single-variable A/B. The
run is therefore the product funnel **minus two recall lanes**; the full-funnel comparison is **T3** and
remains **unmeasured**. The **DA-gap cross-check** holds: arm A DA-off 0.4475 vs Phase E DA-on 0.4250 →
**+0.0225**, close to §I56's **−0.0262**. RAPTOR is not in v3 and this path does not read it. The intent
router is not on the eval path.

**Mutation proof (V1–V9, `logs/p1/step10/t1_mutation_log.txt`, `t1_mutation_proof.py`):** **9 mutations,
each reddens its intended check, and every check is reddened by at least one mutation — no inert check.**
⚠️ **A DEVIATION, STATED PLAINLY:** the pre-registration's §9 required the proof **before** the run; it was
performed **after**. It does not affect the run or the artifact (the verifier is a read-only checker of the
written JSON, so mutating copies proves discrimination equally well), but the deviation is recorded rather
than hidden. The verifier (`t1_verifier.py`, stdlib-only) reads only the written JSON and **ALL V1–V9 PASS**.

**⚠️ An instrument finding worth carrying:** the 90 s `socket.setdefaulttimeout(90)` **did NOT bound a
hang** — arm A rep 2 stalled **979 s** on one query before the retry raised `timed out`. The hardening
copied from T0 is therefore **not** a bound on the cluster's worst case; a run can lose ~16 min to a
single query. The retry worked (the query then succeeded), so the artifact is unaffected.

**Register against:** §I90 (T0, the reference table), §I89 (the fusion destroys the advantage — this is
its product-endpoint counterpart), §I87 (the like-for-like +0.0362 that D1 shows collapsing to +0.005),
§I85 (the original product null, now reproduced on the pooled index), §I66/§I72 (the funnel's stage
losses), §I68/§I84 (the determinism E4/E9 rest on), §D15/§I12 (the derived-lane dimension defect that
forces DA and graph OFF).

### I92. 2026-10-27 — THE FUSION LOSS IS ATTRIBUTED: it is the **100-slot CAP**, NOT MMR. ⚠️ §I89's *"leading suspect: MMR"* is **REFUTED**, and the cap is **already known to be inert at the endpoint** (§I67) — so the fusion is **not** the lever the endpoint responds to

**Instrument.** `.hermes/plans/2026-10-27-p1-fusion-attribution-preregistration.md`, **committed ALONE as
`e9c3a9f` before the run** (D6.1). One index (`knowledge_base_v3` / nomic-768), **T0's lane set** (DA ON
and the graph lane ON), HyDE ON and frozen, **read-only**, 133 queries, **0 errors**, wall **2,629.2 s**.
Artifact `logs/p1/step10/fusion_attribution.json` (sha256 `1a43f2d980183335…`). Only the product's own
config knobs moved — never a re-implementation of the funnel.

**ALL NINE GUARDS PASS, including all three anchors** — arm C reproduces T0's fusion coverage
**0.684486** *and* T0's mean pool size **86.466165**; `D500_raw` reproduces T0's boundary 5
**0.838136**; the reachable set is **identical to T0's** (888 pages, set equality, not just a count).
Plus 133/0, page-dedup in every arm, arm C bit-exact on a repeat, `pages(C) ⊆ pages(W500)` on every
query, and the two width knobs asserted to move together.

**THE RESULT — the loss is one knob.**

| arm | what it is | pool coverage | Δ vs arm C (paired) | 95 % CI | W/L/T | verdict |
|---|---|---|---|---|---|---|
| **C** | **the product as shipped** (cap 100, MMR on) | **0.684486** | — | — | — | the anchor |
| **C_nommr** | cap 100, **MMR off** | 0.687664 | **+0.003178** | [−0.002242, +0.008598] | 6/3/124 | **unresolved** |
| **W500** | **cap 500** (both knobs), MMR on | **0.868024** | **+0.183538** | **[+0.151074, +0.216001]** | **79/0/54** | **RESOLVED** |
| **W500_nommr** | cap 500, MMR off | 0.868024 | **+0.000000** | [0.000000, 0.000000] | 0/0/133 | **exactly inert** |
| D100 | dense lane alone @100, **arm C's own vector** | 0.630958 | C − D100 = **+0.053528** | [+0.020642, +0.086414] | 59/13/61 | RESOLVED |
| D100_raw | dense lane alone @100, raw vector | 0.593164 | D100 − D100_raw = **+0.037794** | [+0.011527, +0.064061] | 51/12/70 | RESOLVED |
| D500_raw | dense lane alone @500, raw vector (**= T0 b5**) | 0.838136 | D500_raw − D100_raw = **+0.244972** | [+0.205687, +0.284257] | 83/0/50 | RESOLVED |

**⚠️ FINDING 1 — THE CAP IS THE ENTIRE LOSS, AND IT IS LARGE.** Raising `mmr_candidates` **and**
`reranker_fetch_k` from 100 to 500 lifts pool coverage from **0.684486 to 0.868024**, **+0.183538
[+0.151074, +0.216001], RESOLVED, 79 wins to 0 losses**. That is **larger than T0's whole fusion loss
(−0.1537)** — because the widened **fused** pool (0.868) then also beats the **dense lane alone at the
same width** (0.838). ⚠️ **The cap costs the dense lane alone +0.244972 too** (0.593164 → 0.838136), so
this is a property of the width, not of fusing three lanes.

**⚠️ FINDING 2 — MMR IS INNOCENT, AND IT IS NOT EVEN CLOSE.** `C_nommr − C = +0.003178
[−0.002242, +0.008598]` — **unresolved**, and only **6 wins to 3 losses**. At the shipped width MMR costs
at most ~0.3 pp of coverage. And at width 500 it is **EXACTLY inert**: `W500_nommr − W500 = 0.000000,
0/0/133`. ⚠️ **This was PREDICTED from the code before the run** and is worth stating as such:
`search_with_das` only calls `_mmr_select` when `len(deduped) > reranker_fetch_k` (`store.py:911`), and
the pool after dedup is ≤ 389 at width 500, so **the branch is never taken**. ⇒ **§I89's "MMR is the
leading suspect" is REFUTED**, and the mechanism it suspected (MMR penalising a page that carries many
relevant chunks) **does not operate at this configuration at all**.

**⚠️ FINDING 3 — PAGE DEDUP IS NOT THE CULPRIT EITHER, and that is a CODE fact, not a measurement.**
Dedup keeps the highest-scoring chunk per page; it removes duplicate **chunks**, not **pages**, so under
a page-level metric it **cannot lower coverage** — it can only free slots for the cap. No dedup-off arm
was run because **the product has no such flag**; the claim rests on the code path plus the fact that the
cap explains the loss on its own. ⚠️ Stated as a code-read, not as a measured contrast.

**⚠️ FINDING 4 — HyDE is worth +0.037794 [+0.011527, +0.064061], RESOLVED (a new, clean measurement).**
`D100 − D100_raw` isolates it for the first time: the same dense lane, the same limit, **the same code** —
only the query vector differs (the HyDE hypothetical vs the raw query). It is the first **isolated** HyDE
effect in the register. ⚠️ It is a **pool-coverage** number, not an endpoint number.

**⚠️ FINDING 5 — fusing three lanes beats the dense lane alone at the same cap:** `C − D100 =
+0.053528 [+0.020642, +0.086414], RESOLVED` (0.684486 vs 0.630958). So the sparse and ColBERT lanes are
**contributing**, not merely diluting — which is the first direct measurement bearing on §I89's
"model-independent lanes dilute the dense lane" hypothesis. ⚠️ It bears on **coverage**, not on the
endpoint, and it does **not** contradict §I89 (which is about the *arm difference*, not the level).

**⚠️⚠️ THE READING THAT MATTERS, AND IT RE-TARGETS THE NEXT ACTION.** The fusion's loss is **fully
attributed to the cap**, the cap is **recoverable at the pool**, and **§I67 already measured the SAME
change (W 100→300 and 100→500, both knobs together) at the PRODUCT ENDPOINT as a NULL** (Δ R@20 c-norm
**+0.0032 / +0.0027**, both UNRESOLVED). ⇒ **A +0.1835 pool gain buys +0.003 at the endpoint.** That is
§I65's *"a pool gain is not a recall gain"* measured with a very large pool gain, and it means:

* **The fusion is NOT the binding constraint on the endpoint.** §I89 named it as such on the strength of
  the *arm difference* it destroys — which is a different claim, and both stand.
* **The endpoint loss sits in the RANKING / top-k stage.** T0's funnel: fusion **0.684486** → cross-encoder
  top-20 **0.455330**. The pool→top-20 step discards **0.2292** of reachable coverage, **and widening the
  pool does not repair it**. That stage has **never been attributed** — no run has separated *"the
  cross-encoder ranks the right page low"* from *"the 20-slot cut discards it"*.
* ⚠️ **Do NOT read this as "widen the fusion".** The width change is measured, cheap and **inert at the
  endpoint**; shipping it would be shipping a number that does not reach the student.

**Mutation proof (V1–V10, `logs/p1/step10/fusion_attribution_mutation_log.txt`,
`fusion_attribution_mutation_proof.py`): 10 mutations, each reddens its intended check, and every check is
reddened by at least one mutation — no inert check.** The verifier (`fusion_attribution_verifier.py`,
stdlib-only, reads only the written JSON) **PASSES V1–V10**. ⚠️ The paired CIs quoted above are
**derived from the registered per-query arrays** (the harness recorded means); they are a re-derivation of
the same data, not a new measurement.

**⚠️ One identity, stated so it is not mistaken for an independent confirmation.** `D500_raw − C =
+0.153650` is numerically **the same as T0's cut−fusion gap (0.838136 − 0.684486)** — because `D500_raw`
**IS** T0's boundary 5. It is an **identity**, not a second measurement.

**Register against:** §I90 (T0 — the fusion boundary this decomposes), §I89 (whose MMR suspicion this
refutes and whose *"the fusion destroys the advantage"* finding this does **not** contradict), §I67 (the
width A/B at the endpoint — the null that makes this a re-targeting rather than a fix), §I66 (the 100-slot
output as the binding *ceiling*), §I65 (a pool gain is not a recall gain), §I72 (the cross-encoder
equaliser — now the prime suspect for the endpoint loss).

#### I91a. ADDENDUM (2026-10-27, same session) — the T1 artifact RECORDED `map` / `precision@20` / `f1@20` per query but never AGGREGATED them. A real gap, now closed by re-derivation; plus a correction to the plan's precision-ceiling figure

**⚠️ THE GAP, STATED PLAINLY.** Every T1 **per-arm** file records **all ten** metrics per query —
`recall_at_20`, `recall_at_100`, `hit_at_20`, `context_precision`, `mrr`, `ndcg_at_20`, **`map`**,
**`precision_at_20`**, **`precision_ceiling_at_20`**, **`f1_at_20`** (they come from the shared
`compute_retrieval_metrics`, which §I90 extended). **nDCG@20 *is* reported** — it is in the artifact's
`S1_secondary`. But **`map`, `precision@20` and `f1@20` were never aggregated into any endpoint or
diagnostic**, so the combine artifact cannot answer a question about them. **Cause:** T1's
pre-registration §5 adopted **Stage F's endpoint list verbatim**, and Stage F predates §I90's metric
additions; `t1_base_lanes.py`'s `combine()` is a copy of Stage F's, so the new keys arrived in the
per-query rows and **nothing summed them**. ⚠️ The gap was **noticed and worked around** — E9 excludes
exactly those keys from its comparison, by name, to avoid an over-strict check — **without them being
added to the endpoint set.** That is the error: the same fact was used to make one check safe and
ignored where it would have made the artifact more complete.

**The derived numbers** (⚠️ **re-derived from the registered per-query arrays — the same data, not a new
measurement; they are NOT part of the pre-registered endpoint set and carry no ship decision**):

| metric | arm A | arm B | Δ (B − A) | 95 % CI | W/L/T | floor |
|---|---|---|---|---|---|---|
| `ndcg_at_20` *(already reported)* | 0.5018 | 0.5023 | **+0.000559** | [−0.010599, +0.011717] | 38/49/46 | 0.0112 |
| `map` | 0.2834 | 0.2828 | **−0.000686** | [−0.007906, +0.006533] | 41/47/45 | 0.0072 |
| `precision_at_20` | 0.2459 | 0.2470 | **+0.001128** | [−0.005925, +0.008181] | 24/22/87 | 0.0071 |
| `precision_ceiling_at_20` | 0.4846 | 0.4846 | **+0.000000** | [0, 0] | 0/0/133 | 0.0000 |
| `f1_at_20` | 0.1957 | 0.1957 | **+0.000015** | [−0.005536, +0.005566] | 24/22/87 | 0.0056 |

**All five unresolved, all below their own floors, all consistent with the T1 null.** ⚠️ The ceiling row
is **exactly 0.000000, 0/0/133** — the correct behaviour for a quantity that is a property of the gold
set, not of the arm, and a useful sanity check on the metric implementation.

**⚠️ A CORRECTION TO THE PLAN'S §C PRECISION-CEILING FIGURE.** The plan argues that the removed
`precision@top_k` "read as failure while sitting at its own ceiling", quoting a ceiling of **≈ 0.10** on
the grounds of a **median 2 labelled pages**. **Measured on this gold set** (arm A, n=133):
`precision_ceiling_at_20` **mean 0.4846, median 0.3000, min 0.0500, max 1.0000**; `n_relevant` **mean
27.30, median 6, max 314**; **45 queries sit at a ceiling of 1.0** (≥ 20 labelled pages) and **35 sit at
≤ 0.10** (≤ 2). ⇒ **the gold set is strongly BIMODAL, and the plan's ≈ 0.10 is not the ceiling of this
population** — it is roughly the ceiling of its small-`|rel|` mode. **The conclusion the plan draws
still holds** (a fixed-slot precision must travel with its ceiling), but **the number attached to it does
not**, and the same §C text is the reason `f1` was called "low priority at fixed k". **Register the
correction rather than the stale figure.**

#### I92a. ADDENDUM (2026-10-27, same session) — the attribution recorded NO fixed-k metric at all, and the reason given for that was IMPRECISE. ⚠️ The width effect at the top-20 **with HyDE ON** is therefore still unmeasured

**⚠️ WHAT WAS NOT RECORDED.** `fusion_attribution.json` carries, per query and per arm, only the **pool's
page list**, the **pool size** and the derived **coverage**. **No `recall@20`, `nDCG@20`, `MAP`,
`precision@20` or `f1@20`** — although every arm calls the product's own `run_retrieval`, which **does**
compute a top-20 in every arm, so all of them were **available**. They cannot be recovered from the
artifact (the reranked lists were not stored); recovering them needs a re-run.

**⚠️ THE JUSTIFICATION IN THE PRE-REGISTRATION §4 WAS IMPRECISE, and the correction matters.** It said
*"recall@k at a pool of width 500 would compare different k's across arms."* **That is wrong as stated.**
What differs across arms is **`fetch_k`** (the pool width) — which **renames** the metric key
`recall_at_{fetch_k}` and **changes `context_precision`'s denominator** (the returned count). The
**top-20** metrics are computed at the **same k = 20 in every arm** and **are comparable**. So the
pre-registered endpoint set could legitimately have included them, and the run would have answered a
second question for free.

**⚠️ WHY THAT IS MORE THAN A TIDINESS ISSUE.** §I67 measured the **same width change** at the endpoint
and found a **null** — but §I67 ran **HyDE OFF**. This run ran **HyDE ON**. So a top-20 comparison here
would have been a **NEW measurement** (the width effect at the endpoint under the product's own HyDE
setting), not a re-derivation of §I67. **It is now a named follow-up**: *does the +0.1835 pool-coverage
gain move the product's top-20 when HyDE is ON?* — cheap, one arm against T0's recorded fusion row.
⚠️ **The registered finding is unaffected** (the pool-level attribution is complete and anchored), but
**"§I67 already covers it" is a claim about a HyDE-off run**, and it should be stated that way.

#### I90a. ADDENDUM (2026-10-27) — T0's artifact OVERSTATES its page convention: boundaries 1, 2 and 5 are **top-k PAGES**, not "pages of the top-k CHUNKS". ⚠️ The funnel comparisons inside T0 are unaffected; a cross-run comparison is not

**⚠️ THE INACCURACY.** T0's `meta.units.product_metrics` says *"pages of the top-k CHUNKS (product
convention, evaluate_rag:333-341)"* — for **every** boundary. **It is true for boundaries 3 and 4 and
false for 1, 2 and 5.** `_metrics_from_pages` (`t0_baseline.py:170-174`) builds `hits` from a **PAGE
list** and passes `reranked = hits[:TOP_K]`, i.e. the **top-20 PAGES**:

| boundary | what is ranked | convention |
|---|---|---|
| 1 base, 2 cut | a **page** list derived from an exact chunk ranking (`_dedup_pages`) | **top-k PAGES** |
| 5 b5 | a **page** list derived from Qdrant's 500-chunk list (`_dedup_hits`) | **top-k PAGES** |
| 3 fusion | the product's pool, which is **already page-deduped** (one chunk per page) | **the two coincide** |
| 4 ce | `ret["reranked"][:20]` — **chunks**, then deduped to pages | **pages of the top-k CHUNKS** ✅ |

**⚠️ Why it matters, and why it does NOT break T0.** The two conventions differ by ~**0.02** and caused
**§I72's VOID run** — so they must never be mixed *within* a contrast. Inside T0 **they are not mixed**:
boundaries 1→2→3 are all top-k-pages on both sides of each comparison, and boundary 3's rows are
identical under both conventions, so **the funnel deltas, the ANN-vs-exact identity (G9/G10) and the
aperture curve all stand**. What breaks is a **cross-run** comparison: **T0's base/cut/b5 R@20 (0.3548 /
0.4242 / 0.4242) is NOT the same quantity as T1's or the product's R@20** (which is pages of the top-k
chunks). ⚠️ **T0's own `ce` row IS comparable** to T1's arm B (0.4442 vs 0.4513 — the same convention,
and the difference is the DA + graph lanes being ON in T0 and OFF in T1, consistent in sign with §I56's
DA harm).

**⇒ The rule this is an instance of (D4.1, one level down):** *a page-level metric must name its k-unit as
well as its k* — "top-20 pages" and "pages of the top-20 chunks" are different metrics that share a name.
⚠️ **Registering the metadata defect, not just the convention**, because the artifact's own `units` block
is what a later reader will trust.

### I93. 2026-10-27 — METRIC PROVENANCE against the course material: **P-ceil IS the course's §3.3**, **"coverage" is NOT a course metric** (and the course's own "coverage" means something else), and our ceiling-ratio identity is the course's **crossover**

**Why.** The gap report uses two metrics that do not look like the ones taught — `coverage` and `P-ceil`.
Before either is defended to a reviewer, both were checked against the course's own documents.

**Source, and where it lives.** ⚠️ **There is no "Beyond_RAG vault".** The only vault on this machine is
the **AI Agents Bootcamp**'s (`~/repo/Support_Vectors/AI_Agents_Bootcamp/Vault`) — a **different course**,
and `.hermes.md` forbids reading that tree unless pointed at a file. **The authoritative Beyond RAG
material is in the tree itself**: `Week_Summary/*.pdf` (12) and `Slides/*.pdf` (9), which is what §C2 of
the fusion plan already designates as the source. **All 21 documents were text-extracted and searched**
(`pymupdf`; text in the scratch dir, not committed).

**Verdict — which of our metrics are the course's, and which are ours:**

| our metric | course status | evidence |
|---|---|---|
| `recall@k` | **the course's** | W7 §3.1: *"Recall evaluates completeness by comparing the returned bucket against the entire beach … if the child only finds 3, the recall is 3/5."* |
| `precision@k` | **the course's** | W7 §3.1: *"Precision evaluates the internal purity of the returned results … If Sarah returns with 4 genuine seashells and 6 pebbles, her precision is 4/10."* |
| **`P-ceil`** | ⚠️ **the course's — §3.3, verbatim** | W7 §3.3 *"The Mathematical Ceiling of Precision"*: *"Therefore, **when n < k, Precision@k has a hard ceiling of n/k**. Systems must only be compared at identical k values, and the total population of relevant documents n must always be reported alongside the metric."* Its worked example is **n=10, k=20 → ceiling 0.50** — the same construction as ours. The deck teaches it too (slide 25, *"if n < k, perfect precision is unreachable (max n/k)"*). |
| `F1@k` | **the course's** | W7 §3.4: the harmonic mean, with the same imbalance argument. |
| `MRR` | **the course's** | W7 §4.3 "Calculating Mean Reciprocal Rank (MRR)". |
| `MAP` | **the course's** | W7 §4.6. |
| `nDCG@k` | **the course's** | W7 §5.5, "The Apex Metric". |
| **`coverage`** | ⚠️ **NOT a course metric** | **All 30 occurrences of "coverage" across the 21 documents are a different quantity.** The nearest is W8 §19.1: *"**Coverage: The proportion of total user queries the system attempts to answer.**"* — the **risk–coverage curve** of selective prediction / abstention, i.e. *how many queries you answer*, not *how many pages you returned*. The rest are subject/traffic/representation coverage. |
| `cR@k` (ceiling-normalised recall, §I58) | **ours** | no course analogue. |

**⚠️ ⇒ A NAME COLLISION, and it is worth stating in any submission.** Our `coverage` and the course's
`coverage` are **different quantities with the same name**. Ours should always be written as what it is —
*"coverage of a query's reachable labelled pages"* — never as bare "coverage", or a reader who knows the
course will read it as the abstention metric.

**⚠️ Why we need ours at all — the suspicion is CORRECT, and it is already measured.** §I58 measured it:
the content filter (`page_number ∈ [30, 936]` and `is_content is not False`, `store.py:389-402`) makes a
**non-trivial part of the gold set unreachable by any retriever**: **57 labels unreachable exactly, 26
more within ±1** of 3,631 — and **by type, overwhelmingly overview: 46 exact / 21 near, against factual
5/2 and multihop 6/3.** So a recall denominator of *all* labelled pages charges the system for pages the
pipeline was never permitted to return, and **overview is the type it penalises most** — which is exactly
the type the gap report flags. `achievable_max = |reachable| / |labelled|` (mean **0.9545** on the new
index, **0.8806** on the old) is that correction, and it is a **gold-set property, identical in every arm**
(T1 measured it at **0.97707 in both arms**).

**✅ And the course has the same IDEA, under a different name — it just never gives it a metric.**
**W10 §7.1 "The Recall Ceiling: Dictating Generation Limits"**: *"If the initial bucket scoop misses a
marble entirely, absolutely no downstream sieve can recover it"*, with the **Scoop Wide Principle** and
*"whatever recall the system captures during that initial scoop establishes an unbreakable hard ceiling."*
**Our `coverage` is that doctrine operationalised as a per-stage number** — it is what makes "the page was
never available" separable from "the page was available and ranked badly" (§I90a's distinction). ⇒ **Cite
W10 §7.1 as the concept and present `coverage` as our instrument for it, not as a course metric.**

**✅ BONUS — our ceiling-ratio identity is the course's crossover.** The deck's slide 25 states *"At the
crossover n = k: perfect precision and perfect recall coincide."* That is the general case of the identity
verified this session — **for a query with |rel| ≤ k, `P@k / P-ceil` is exactly `recall@k`** (0 violations
over 88 queries × 4 stages, §I91a's addendum). ⚠️ Note the direction: the course states the crossover for
**n = k**; ours holds for **all n ≤ k**, which is the same statement once the ceiling is divided out.

### I94. 2026-10-27 — the TOC-label question, measured: **NO label is outside the content window**, 32 label instances sit ON contents pages, and **removing them in bulk would delete CORRECT labels** for a whole query family

**The question raised.** *"Didn't we decide to remove labelled pages that are outside the content filter —
e.g. an index/TOC page, which points to the answer rather than being it?"*

**⚠️ Answer 1 — the premise is false, and it is worth correcting because it is the kind of thing that gets
repeated.** **Every one of the 3,631 label instances is inside the content window `[30, 936]`**: measured,
**0 labels below 30 and 0 above 936**, 0 on the index pages (937–968), 0 on the front matter (2–14).
`min_content_page`/`max_content_page` are not excluding any labelled page. ⇒ **Nothing needs removing for
being out of the window**, and the `achievable_max` construct (§I58) is not about TOC pages.

**⚠️ Answer 2 — what we ACTUALLY decided (§I58), verbatim:** *"**re-point `gold-003` (and optionally the two
±1 queries) and leave the set alone.** A full rebuild would cost a book-wide VLM scan (~36k judge calls)
and would destroy comparability with every historical run, for a ~1 % label-reachability gain."* Codified
as **D6.4 — the gold set is re-pointed, not rebuilt.** The re-point was applied: `gold-003` 30 → 34.

**✅ Answer 3 — but there IS a real, nameable issue, and it is a DIFFERENT one.** 32 label instances sit on
**pages 30–34**, and those pages **are contents pages** — verified by reading their chunk text in the live
DB, not inferred from a page range: `p34` holds 21 chunks of which **18 are dot-leader TOC entries**
(*"The Kinetic Theory of Gases … 39-3 Compressibility of radiation . . . 39-3"*), `p30` holds 38
(*"Chapter 38. The Relation of Wave and Particle Viewpoints … 42-2 Thermionic emission . . ."*). Affected:
**29 queries** — `gold-003`, `gold-004`, `gold-083/084/085`, and **24** `ovw-*`.
⚠️ **CORRECTED 2026-10-27:** this line first read *"21 queries … and 16 ovw-*"*. Both counts were wrong —
the true split is **5 gold + 24 ovw = 29**, re-derived from `data/eval_queries_v2.json` during the
pre-ship verification of the gap report. The claim it supports (a large majority of contents-page labels
are correct) is unaffected and gets stronger.

**⚠️⚠️ AND HERE IS WHY BULK REMOVAL IS THE WRONG REPAIR.** Two of the material cases are queries **whose
answer genuinely IS the contents page**:

| query | question | label | verdict |
|---|---|---|---|
| `gold-003` | *"Which section number is titled 'Thermionic emission'?"* | `[34]` | **the TOC page lists "42-2 Thermionic emission" — the label is CORRECT, and its R@20 of 1.0 is a TRUE positive** |
| `gold-004` | *"What is the title of section 42-4?"* | `[30, 86, 795]` | **the TOC page lists "42-4 Chemical kinetics" — CORRECT** |
| `gold-083/084/085` | *"How does X relate to Y…"* (content questions) | `[30, 490, 921]` | ⚠️ **the TOC page is a POINTER, not the answer — these three are the defensible candidates for re-pointing** |

⇒ **A blanket "drop contents pages" rule would silently delete correct labels for the entire "which section
number / what is the title of section X" query family.** ⚠️ **This is §I58's own lesson one level down: a
label is a property of the DOCUMENT, and for some questions the document's contents page is the answer.**

**⚠️ The sensitivity, measured (T0's stored page lists, endpoint, TOC labels 30–34 removed):**

| scope | R@20 as-is | R@20 with TOC labels removed | Δ |
|---|---|---|---|
| **all 133** | 0.4442 | 0.4471 | **+0.0030** — below the floor; **not a lever** |
| factual (n=53) | 0.5574 | 0.5489 | **−0.0085** |
| multihop (n=40) | 0.5500 | 0.5708 | **+0.0208** |
| overview (n=40) | 0.1882 | 0.1911 | +0.0028 — immaterial (1 TOC page among 23–155 labels) |
| ⚠️ **`gold-003`** | 1.0000 | **UNDEFINED — no labels left** | **the query becomes unscoreable** |

⚠️ **`gold-003` is why "remove" is not a general repair: its ONLY label is the contents page.** Deleting it
destroys the query; re-pointing it (what §I58 chose) preserved it, and the re-point 30 → 34 **followed the
re-chunking rather than the semantics** — which is legitimate here only because **both pages carry the same
TOC entry**, so the semantic content survived. Verified in the live DB: `p30` has chunks in the **old** doc
only (`6d55c52b`), `p34` in the **new** doc only (`7ba61432`) — consistent with §I58's *"the new ingest has
no chunk at page 30"*.

**Recommendation, and it is an OWNER decision.** ⚠️ **Do NOT bulk-remove.** Triage the **5 material queries
by hand** — `gold-083/084/085` are the defensible re-points; `gold-003`/`gold-004` are correct as they
stand. Any change must be a **NEW label artifact beside the current one** (D6.4's comparability rule, and
the same shape the plan's §C proposes for graded relevance), never a silent replacement — every historical
run used these labels. **Cost of the triage: minutes. Cost of the bulk rule: a whole query family scored
wrong, silently.**

**Register against:** §I58 (the re-point decision and the reachability measurement), §I71 (the TOC/index
page ranges, measured from the filter's rejects), D6.4 (re-point, do not rebuild), §I93 (the metric
provenance this sits beside).

#### I94a. ADDENDUM (2026-10-27) — the classification is COMPLETE for all 29 queries, and it shrinks the issue to **3 label instances**: the other **26** contents-page labels are **CORRECT**

**⚠️ The earlier note triaged only the 5 material queries. The rule's own standard requires every selected
item to be read and classified, so the remaining `ovw-*` were read too — 24 of them, not 16 (see the
correction in §I94).** The result changes the recommendation.

**What the 24 overview queries actually ask** — every one is a **whole-volume synthesis** question, and a
contents page is a legitimate part of answering it:

* `ovw-001` — *"In what ways does Feynman use the principle of conservation of energy to bridge the
  examination of mechanical systems, wave phenomena, and thermodynamic processes in Volume 1…"*
* `ovw-004` — *"How does the Feynman Lectures on Physics, Volume 1, trace the evolution of symmetry
  principles from classical mechanics to quantum mechanics…"*
* `ovw-010` — *"In what way does Feynman build the concept of entropy from its statistical roots to its role
  in thermodynamic processes throughout…"*
* `ovw-019`, `ovw-034` — the same shape (uncertainty principle; Planck's constant, *"across the entire
  volume"*).

⇒ **For a question about how the book develops a theme across the whole volume, the contents page is where
that structure is stated.** The label is **correct**, and each is 1 of 23–155 labels, so it also cannot
distort the metric.

**The completed classification:**

| item | class | why |
|---|---|---|
| `gold-003` (p34) | ✅ **correct** | *"Which section number is titled 'Thermionic emission'?"* — the TOC lists **42-2 Thermionic emission** |
| `gold-004` (p30) | ✅ **correct** | *"What is the title of section 42-4?"* — the TOC lists **42-4 Chemical kinetics** |
| **`gold-083` / `084` / `085` (p30)** | ⚠️ **pointer** | content questions (*"how does X relate to Y"*); the TOC names the sections without explaining the relation |
| **24 × `ovw-*` (p30–33)** | ✅ **correct** | whole-volume synthesis questions — the contents page is part of the answer |

**⚠️ ⇒ The issue is 3 label instances across 3 queries, not 32 instances across 29.** And **none of the
three is left unscoreable** — each keeps pages 490 and 921.

**⚠️ And the measured effect of even that change is below the floor.** Re-pointing `gold-083/084/085` off
page 30 moves **multihop R@20 from 0.5500 to 0.5708 (+0.0208)** — real in direction, but **below the n=40
resolution floor (~0.04)**, and it moves the **aggregate by +0.0030**. ⇒ **This is a hygiene item, not a
lever.** ⚠️ **Recommendation: DEFER.** If it is ever done, it must be a **new label artifact beside the
current one** (D6.4), never a silent replacement, and the re-point must be **checked against the section
body** rather than the chunking (§I58's 30 → 34 re-point is the cautionary example: it followed the
re-chunk while both pages happened to carry the same TOC entry).

**Method note.** Steps followed: enumerate the rule → **count it** (32 instances, and the "outside the
window" premise counted **zero**) → **read the source text** of every selected item (pages 30–34, not the
page numbers) → classify correct / wrong / pointer → check the empty-label case (`gold-003`) → recompute
the metrics per segment → write it as a register entry. ⚠️ **Two of the four steps that mattered here
would have been skipped by acting on the remembered decision.**

#### I95. ⚠️ TWO ARTIFACTS REPORT AN "MRR" FOR THE SAME STAGE AND THEY ARE DIFFERENT NUMBERS — the product's `mrr` is MRR@fetch_k (a POOL metric); T0's `ce` MRR is the ENDPOINT's. The gap is ~0.10

**Found by the T4 smoke test (§12 of T4's pre-registration), not by looking for it.**

`compute_retrieval_metrics` computes `mrr` from `retrieval["hits"]` — **the POOL** — and its own comment
says so: *"MRR@fetch_k (no threshold — measures rank of first relevant result)"*. That is **intentional**,
not a bug. But the same function computes `ndcg_at_{k}`, `map`, `recall_at_{k}`, `precision_at_{k}` and
`hit_at_{k}` from `retrieval["reranked"]` — **the ENDPOINT**. ⇒ **one metric in the set describes the pool
and the rest describe the endpoint, and all of them are printed under one heading.**

⚠️ **T0's artifact does the opposite, and both are self-consistent.** `t0_baseline._metrics_from_pages`
scores **each boundary's own list** (`hits = hits_above = that list`), so:

| row | `mrr` describes | value |
|---|---|---|
| T0's `fusion` row (the pool) | the **pool** | **0.7687** |
| T0's `ce` row (the 20-page endpoint) | the **ENDPOINT** | **0.6668** |
| the product's `mrr` at the endpoint | the **pool** | **0.7687** |

⇒ **The product's evaluation reports 0.7687 as the endpoint MRR; the endpoint actually achieves 0.6668.**
**Overstated by 0.10** — and MRR is exactly the metric a reader would take as "how high does the right page
rank in what the student sees".

⚠️ **Why it matters more than a naming quibble:** `mrr` is the one field in the product's metric set that is
**identical in every arm of T4** (all four share a pool), so **it silently cannot falsify a ranking
hypothesis.** The smoke proved it: the registered `P1`/`P2` MRR deltas returned **exactly `0.0` with
`ci95 [0.0, 0.0]`** — a prediction the harness could never have falsified, from a metric that never
measured the endpoint.

**Fix (do NOT do it silently):** T4's harness **adds `mrr_at_k` over the endpoint list** and anchors it on
T0's `ce` MRR. Any change to the product's `mrr` is a **product-path change** and needs its own
pre-registration, because it moves a number in the evaluation report that every historical run quoted.
**Until then: never quote the product's `mrr` as the endpoint's.**

**Method note.** This was found by an **8-query smoke test costing one minute**, and it would have been
**invisible in the full run's aggregate** — the full run would have reported "the hypothetical does not
affect MRR" from a metric that never measured the endpoint. ⚠️ **The smoke's value was not "does the code
run" but "is the instrument the one I think it is".**

#### I96. ⚠️ THE COLBERT LANE CAN DROP OUT **SILENTLY** AND CHANGE THE POOL — the store catches the failure, logs it, and fuses from a REDUCED LANE SET, and **there is no counter anywhere**

**Found by T4's first full run failing G6/G6b on exactly one query, then reading the run log** (T4
pre-registration §14).

**What happens.** `store._qdrant_search` (line ~598) wraps the ColBERT query in a `try`, and on ANY exception
it logs an **ERROR** and simply **omits the ColBERT `Prefetch`** — the RRF fusion then runs over
**dense + SPLADE only**. Its own log line says so: *"the colbert lane is inactive and results use
dense+SPLADE only"*.

**⚠️ Why it matters: the pool is a different pool.** The lane set is an input to the fusion, so a dropout
changes which chunks are shortlisted, hence which PAGES come back, hence every pool-dependent number —
T0's `fusion` row, the funnel's coverage, and the reachable-page denominators the project reports against.
**Nothing in the artifact records that it happened.**

**The evidence.** T4's full run: `gold-029` under arm N returned **86 pages** where arms C, Q, W50 **and
T0** all say **92** — with this in the log at that moment:
```
ERROR | src.pdf_ingestion.store:_qdrant_search:606 - ColBERT query FAILED (timed out);
        the colbert lane is inactive and results use dense+SPLADE only
```
A probe re-ran `gold-029` under arm N four times: **92, 92, 92, 92 — stable**, so the 86 was a transient
dropout, not a structural difference. **Rate: 1 call in 665 (~0.15 %)** on this run.

**⚠️ Contrast with the reranker, which the project already handled.** `reranker.fallbacks` exists precisely
because §I55 found that the CE *swallows its failures and returns the pool unranked while the artifact still
records `enabled=true`*. **The ColBERT lane has no equivalent counter**, so the same class of silent
degradation is invisible to every run-integrity block written so far — including T0's.

**Recommended fix (small, no re-ingest — it is query-time only):** add a counter beside
`_warned_colbert_local` (e.g. `self.colbert_dropouts`) incremented in that `except`, expose it the way
`reranker.fallbacks` is, and have run-integrity blocks **assert lane health per query** rather than
assuming the configured lane set was the executed one. **Until then, any pool-dependent number in any
artifact may have been taken from a reduced lane set, and the only way to know is to grep the run log for
that ERROR line.**

**What T4 did in the meantime:** counted the failure at the embedder (a watcher that only counts and
re-raises, changing no behaviour), **retried the call** because a lane-reduced call is not the treatment,
and recorded both — plus guards **G9/G9b/G10**. ⚠️ **A guard added at an independent reviewer's request two
hours earlier (G6b, pool CONTENT) is what caught it.**

#### I97. ✅ T4 RAN — **THE CROSS-ENCODER IS A NET HARM AT THE ENDPOINT, AND ON FACTUAL QUERIES THE CAUSE IS THE HyDE HYPOTHETICAL BEING USED AS ITS QUERY.** All 14 guards pass; all three registered predictions confirmed

**Instrument:** `logs/p1/step10/t4_endpoint.json`, sha256 `3db7c697a5bb0fec…`, 133/133 scored, 0 errors,
**14/14 guards PASS**, wall ~52 min. Independent verifier: **5,852 metric fields re-derived from the page
lists and labels**, all pass (4 deferred as a unit difference, max gap 0.0011, §15). Mutation proof: 20
checks, every one reddenable. Pre-registration
`.hermes/plans/2026-10-27-p1-endpoint-attribution-preregistration.md` (committed ALONE before the run, D6.1).

**THE ANSWER TO THE QUESTION.** Three candidate causes were separated: (a) the CE reorders badly, (b) the
20-slot cut discards pages, (c) ⚠️ the CE is fed the HyDE hypothetical instead of the user's question. **All
three are real, and (c) is the biggest actionable one.**

**P1 — REMOVING the cross-encoder (arm N vs arm C), n=133 paired:**

| metric | mean | 95 % CI | verdict |
|---|---|---|---|
| nDCG@20 | **+0.0560** | [+0.0195, +0.0925] | **RESOLVED** |
| MAP | **+0.0631** | [+0.0269, +0.0993] | **RESOLVED** |
| MRR@20 (endpoint) | **+0.1011** | [+0.0327, +0.1695] | **RESOLVED** |
| R@20 | +0.0050 | [−0.0289, +0.0389] | spans 0 |
| Hit@20 | +0.0150 | [−0.0144, +0.0445] | spans 0 |

⚠️ **The CE costs ordering and costs nothing on recall** — recall and hit are unchanged. It is not failing
to find the pages; it is **demoting the right page within the top-20**. On 52 of 133 queries the relevant
pages found are identical and only their order differs.

**P2 — the CE reranking against the RAW QUERY instead of the hypothetical (arm Q vs arm C), n=133:**

| metric | mean | 95 % CI | verdict |
|---|---|---|---|
| nDCG@20 | **+0.0430** | [+0.0080, +0.0781] | **RESOLVED** |
| MAP | **+0.0561** | [+0.0215, +0.0907] | **RESOLVED** |
| MRR@20 | **+0.0699** | [+0.0097, +0.1301] | **RESOLVED** |
| R@20 | +0.0099 | [−0.0199, +0.0398] | spans 0 |

⇒ **Changing only the CE's QUERY TEXT — one line, `evaluate_rag.py:206` — recovers 77 % of the nDCG the
cross-encoder is costing.** The CE does not have to be removed to fix most of this.

**P3 — the 20-slot cut (arm W50 vs arm C): coverage +0.1451 [+0.1125, +0.1777] RESOLVED.** The cut is a
real cost, and it is a **deliberate context budget**, not a bug — the same widening was already measured
inert at the endpoint (§I67).

**⚠️ PER TYPE — the harm is CONCENTRATED, and the fix is PER TYPE:**

| type | n | N−C nDCG | Q−C nDCG | reading |
|---|---|---|---|---|
| **factual** | 53 | **+0.1361 [+0.0684, +0.2037] R** | **+0.1397 [+0.0676, +0.2119] R** | ⚠️ **the CE badly hurts factual, and the hypothetical is essentially the whole cause** — Q ≈ N, so feeding the CE the raw query recovers it **without removing the CE**. MRR: N−C +0.2496, Q−C +0.2631, both RESOLVED |
| multihop | 40 | −0.0311, spans 0 | **+0.0000 [0,0]** | ⚠️ **Q ≡ C EXACTLY, by construction** — HyDE is not used for multihop, so `rerank_query` is *already* the raw query. **A free internal consistency check the run passed 40/40**, and it proves the instrumentation does exactly what it claims |
| overview | 40 | +0.0371, spans 0 (MAP +0.0292 R) | −0.0420, spans 0 | ⚠️ **the hypothetical is the BETTER query for overview** (Q−C is negative). **Do NOT apply the factual fix here.** Unresolved at n=40 — stated as unresolved, not as an effect |

**⇒ THE ACTION, and it is the largest measured lever in this project so far: a PER-TYPE rerank-query
policy** — the **raw query for factual**, the **HyDE hypothetical for overview**, and either for multihop
(no HyDE is used). Estimated on this corpus: **+0.14 nDCG and +0.26 MRR on factual queries**, at zero
recall cost, with **no embedder, index, or re-ingest change**.

⚠️ **NOTHING WAS CHANGED IN `src/`.** Per the pre-registration's reading rule, a confirmed P1/P2 is a
**product-path defect that licenses its own before/after, pre-registered separately** — and a one-line
change to the live pipeline off the back of an attribution run is exactly what D6.1 exists to prevent.

**⚠️ Caveats, stated because they bound the claim.** One corpus, one document, one day, one funnel. The
per-type n is 40–53, so **only the factual per-type effects are resolved** — the multihop and overview point
estimates are reported as *unresolved directions*, not effects. The overall effects are n=133 and resolved.
And the CE here is `BAAI/bge-reranker-v2-m3` as served by the cluster — a different re-ranker is a different
question.

#### I98. ✅ LANE INCLUSION RAN — **NO LANE IMPROVES THE ENDPOINT.** RAPTOR as a first-class RRF participant is a **RESOLVED HARM on overview**; DA's fusion placement is a **NULL**; and the graph lane's harm is **NOT a placement artifact** — fusing it does not recover MRR

**The registered question was NOT "does this improve things"** — it was *"does making a lane a
first-class RRF participant change its sign and ordering, versus appending it?"* (`plan §0`). Today's
wiring inserts the three lanes at three different depths: DA is appended **after** the vector fusion,
the graph lane is appended by the **caller after dedup/MMR** with a fabricated `score`, and RAPTOR was
**absent from the index and never called on the eval path**.

**Artifact** `logs/p1/step10/lane_inclusion.json` sha256 `0f5f5a05e01e9939…`, **133 queries, 0 errors,
wall 5,220.6 s**, one index (`knowledge_base_v3` + RAPTOR, nomic-768), HyDE ON and frozen, read-only.
**All 8 harness guards PASS**; the **independent stdlib verifier passes 19/19**; its mutation proof
reddens **all 14 checks with no inert check**. Pre-registration committed **ALONE** as `93146f5`
(D6.1), **including a dated pre-run amendment (§11)** — see below, it is the more useful half.

**Arms** — each REPLACES the pool's composition, so every treatment is a single-variable contrast
against **F0f** (`search_fused(lanes=())`, the vector lanes only, fused), while **F0** (today's
wiring) remains the product reference:

| arm | what it is | coverage | R@20 | nDCG@20 | MAP | MRR@20 | Hit@20 |
|---|---|---|---|---|---|---|---|
| **F0** | today's wiring | 0.4675 | 0.4563 | 0.5503 | 0.3406 | 0.7717 | 0.9323 |
| **F0f** | fused, vector lanes only | **0.4709** | **0.4596** | **0.5549** | **0.3421** | 0.7648 | 0.9474 |
| **F1** | DA **into** the fusion | 0.4628 | 0.4516 | 0.5502 | 0.3401 | **0.7816** | 0.9323 |
| **F2** | graph **into** the fusion | 0.4657 | 0.4546 | 0.5340 | 0.3287 | 0.7544 | 0.9474 |
| **F3** | RAPTOR added | 0.4678 | 0.4567 | 0.5433 | 0.3377 | 0.7648 | 0.9474 |
| **F4** | all three fused | 0.4558 | 0.4448 | 0.5269 | 0.3312 | 0.7803 | 0.9323 |

**The four results, in the order the pre-registration asked for them.**

1. ⚠️ **F3 (RAPTOR) is a RESOLVED HARM on the type it targets.** Per type, F3 − F0f: **factual
   +0.0000 and multihop +0.0000 — EXACTLY, by construction** (the lane is gated to overview, and this
   is a free internal consistency check); **overview nDCG −0.0383 RESOLVED, MAP −0.0148 RESOLVED**;
   coverage **−0.003028 RESOLVED NEGATIVE**. Endpoint pages fall 20 → 18 on overview: the two
   summary candidates **consume slots and push real pages out** (`endp_pageless_total` **58 of 133**
   queries). ⇒ **§5's prediction 1 is FALSIFIED, and §11b had already registered that it CANNOT hold
   through coverage**: a RAPTOR summary carries **no `page_number`**, so at the page-level unit the
   lane can only **DISPLACE**, never add. Reading this as "RAPTOR is a bad lane" would be reading a
   property of the **unit** as a finding about the lane.
2. **F1 (DA into the fusion) does NOT reverse the DA lane's measured harm — prediction 2 CONFIRMED.**
   vs **F0f**: nDCG −0.0047 *unresolved*, MAP −0.0020 *unresolved*, MRR +0.0168 *unresolved*, but
   **precision −0.00752 RESOLVED** and **F1 −0.00593 RESOLVED** (both negative). vs **F0** (today's
   wiring): **every metric unresolved**. ⇒ the DA lane's harm is **not** a placement artifact, and
   moving it into the fusion changes nothing measurable at the endpoint — a **null**, recorded as one.
3. ⚠️ **F2 (graph into the fusion) does NOT recover MRR — prediction 3 FALSIFIED, and that IS the
   finding.** vs **F0f**: nDCG **−0.0209 RESOLVED**, R@20 **−0.0051 RESOLVED**, precision
   **−0.0147 RESOLVED**, F1 **−0.0066 RESOLVED** — all negative; MRR −0.0103 *unresolved*. vs **F0**:
   nDCG **−0.0163 RESOLVED**, precision **−0.0087 RESOLVED**, MRR −0.0173 *unresolved*. The
   pre-registration said it: *"if F2 does not recover MRR, the placement was not the cause."* ⇒ **the
   graph lane's cost is content, not placement** — giving it a rank does not fix it. ⚠️ **Scope, as
   §11f states:** the graph lane fires for **every** query type inside `search_fused` (today's wiring
   appends it only for multihop), so F2 − F0f measures **placement on multihop** and **INCLUSION
   elsewhere** — and the largest resolved loss is on **overview** (−0.0425 nDCG), where the lane is
   pure addition.
4. **F4 does not exceed the best single-lane arm — prediction 4 CONFIRMED.** F4 is the **worst arm on
   every ranking metric** (nDCG 0.5269, overview −0.0793 RESOLVED). Lane weighting is not a free win,
   and nothing here ships.

**⚠️ A SECOND INSTRUMENT FINDING, and it would have been read as a null: `mrr_at_20` is structurally
BLIND to a page-less lane.** `F3 − F0f` on `mrr_at_20` is **exactly 0.000000 on all 133 queries, CI
[0, 0]** — the tell the independent-verification skill names (*"a delta of 0.0 with a zero-width CI is
a statement about the instrument, not the treatment"*). The mechanism is in the metric: `_endpoint_mrr`
takes the first relevant page's rank over the **page-deduped** list, and page-dedup **drops** the
page-less candidates and **compresses the positions** — so inserting a summary above the first
relevant page cannot move it. The metric that *can* see the displacement is nDCG/MAP (the page-less
candidate still occupies a slot in the gains array), and there the effect is **resolved negative**.
⇒ **Do not quote `mrr_at_20` for a page-less lane.** Same class as §I95's pool-vs-endpoint trap.

**⚠️ FOUR THINGS THE PRE-RUN AMENDMENT (§11) CAUGHT, and one of them was a live defect.**

* **§11a — a real defect, found by a LIVE probe, not by review.** `store.search_raptor` returned
  `{"score": …, **payload}`: a summary's payload has **no `chunk_id`**, and `_rrf_merge` keys on
  `chunk_id` falling back to `qdrant_point_id` (§I84) — so **every RAPTOR candidate was silently
  dropped inside `search_fused`** and **F3 as originally registered would have been a copy of its
  control**, i.e. a null by construction. Measured live: **0 of 2** candidates surviving before the
  fix, **2 of 2** after. Fixed in `store.py`; pinned by
  `tests/test_lane_inclusion_eval.py::test_the_real_search_raptor_returns_a_key_the_fusion_can_use`
  (mutation MV7). ⚠️ The first version of the tests **could not see it** — their fixture handed the
  fusion a `chunk_id`, a shape the real lane never produces. **This is G5's own case, caught before
  the run rather than by it.**
* **§11c — the arms REPLACE the composition, so G3's superset claim against F0 was false by
  construction** (measured: F0's pool 88, F3's 75 on one overview query). Re-pointed at **F0f**,
  which also made every arm single-variable.
* **§11e — the graph lane's Cypher has NO stable `ORDER BY`**: pool sizes **90 / 88 / 90** across
  three **identical** calls in one process. G3 is asserted only on the **graph-free** arms; F2/F4's
  pool relation is **reported** (F4 has 8 violations; F1/F2/F3 none; 19 queries cut-affected by the
  100-slot cut).
* **§11g — the cross-day anchor cannot be asserted on small n.** The smoke (3 overview queries)
  suggested F0 diverged from the shipped run on overview; **at n=40 the aggregate matches the shipped
  run to +0.0000 on all seven endpoint keys**. The anchor is asserted **per type on factual and
  multihop (14/14 within 1e-4)** and **reported** on overview. Per-query page lists differ on
  **1 of 133** (a multihop query — the known graph-lane transient).

**⚠️ What this does NOT license.** No lane ships. **F0f — the vector-only fusion — is the best arm on
nDCG and MAP, and today's wiring is −0.00456 nDCG against it (unresolved, but precision is −0.00602
RESOLVED negative)**: the append pattern is not *earning* anything measurable at the endpoint, but
that is an unresolved direction, **not** a licence to delete DA or the graph lane. One corpus, one
document, one day, one funnel, one CE model (`BAAI/bge-reranker-v2-m3`). n=133 overall, 40–53 per
type, so **only the per-type and the larger overall effects resolve**. ⚠️ **Not measured:** the
generator stage (retrieval only); lane weighting as a ship candidate (F4 is exploratory); the
**overview type's real problem** — its lane, as wired, makes it worse, and its R@20 (0.1947 at the
best arm, ceiling 0.3992) remains the programme's worst number.

**Read-only. No writes to any collection beyond S2's 73 carried RAPTOR nodes; no re-ingest; no
embedder change.**

---

#### I99. ✅ THE ENDPOINT'S TOP-20 LOSS, DECOMPOSED PER TYPE — **the two real levers are the POOL's coverage and the POOL's ORDER, and the CROSS-ENCODER is worth 0.005 overall.** ⚠️ It CORRECTS the report's §3 reading of overview ("a retrieval problem") and re-scopes the CE work (T4) as a fine-tune candidate.

**Read-only. No run, no new measurement** — this is a re-derivation over two existing artifacts
(`t4_endpoint.json`, `t0_baseline.json`). Harness `logs/p1/step10/order_waste_decomp.py`, artifact
`order_waste_decomp.json`; independent stdlib verifier `order_waste_decomp_verifier.py`
(**42/42 checks pass**, re-deriving every cell from the SOURCE per-query arrays, not from the
harness's own output); mutation proof `order_waste_decomp_mutation.py` (**42 mutations, 42/42 checks
reddened, NO inert check**, every mutation hits its intended check).

**The decomposition.** Per query: `R_ceil_20 = min(20, n_rel)/n_rel` (the label ceiling);
`pool_oracle_20 = min(20, pool_gold)/n_rel` (the best ANY ranker could do on the pool the product
actually built — an upper bound, not a target); `realised_N` (the pool's own order, no CE);
`realised_C` (the product). Losses: `waste_pool = R_ceil − oracle` (the pool lacks the gold),
`waste_order = oracle − N` (the pool's order buries gold it holds), `waste_ce = N − C`.

| type | n | R_ceil@20 | pool-oracle | pool order (N) | product (C) | waste_pool | **waste_order** | waste_ce | gold pages in pool |
|---|---|---|---|---|---|---|---|---|---|
| factual | 53 | 0.9557 | 0.8052 | 0.5830 | 0.5574 | 0.1505 | **0.2222** | 0.0256 | 5.3 |
| **overview** | 40 | **0.3992** | **0.3755** | 0.2103 | 0.1882 | **0.0236** | **0.1652** | 0.0221 | **31.4** |
| multihop | 40 | 1.0000 | 0.6466 | 0.5106 | **0.5500** | 0.3534 | 0.1360 | **−0.0394** | 2.7 |
| all 133 | 133 | 0.8016 | 0.6283 | 0.4491 | 0.4442 | 0.1734 | **0.1791** | **0.0050** | — |

⚠️ **`R_ceil@20` here is the LABEL ceiling — `min(k, n_rel)/n_rel`.** The final report's §3 column of
the same name is **reachability-adjusted** — `min(k, |reachable|)/|labelled|` — so the two agree
**exactly for overview (0.3992)** and differ slightly elsewhere (factual 0.9557 vs 0.9494; multihop
1.0000 vs 0.9556; all 133 0.8016 vs 0.7858). **Both are label-side, neither is a system number**,
and the overview conclusion — the one this entry turns on — is unaffected. A future session must not
read the two columns as the same quantity.

**1. ⚠️ THE CROSS-ENCODER IS A SMALL PART OF THE ENDPOINT LOSS — 0.0050 overall.** It is 0.0256 on
factual, 0.0221 on overview, and **−0.0394 on multihop, where it HELPS**. The register's focus on the
CE (T4) is correct about the *mechanism* and wrong about the *size*: the two real levers are
`waste_pool` (0.1734) and `waste_order` (0.1791), each ~35× the CE's aggregate contribution.

**2. ⇒ THE CE FINE-TUNE IS PRICED, and it is NOT the next move.** A perfect cross-encoder could
recover at most `waste_ce` — **0.026 on factual, 0.022 on overview, and nothing at all on multihop**,
where the CE is already a gain. Keep it as the last resort, with this ceiling attached.

**3. ⚠️ OVERVIEW IS AN ORDERING PROBLEM, NOT A RETRIEVAL PROBLEM — the report's §3 reading is
corrected.** §3 reasoned "overview has the lowest pool coverage (0.5221) ⇒ a retrieval problem". The
oracle shows the pool **holds 31.4 labelled pages out of 88.9 — enough to fill all 20 slots** — so
the pool supports **0.3755 of the 0.3992 ceiling (94 %)**. `waste_pool` is only **0.0236**. The
dominant loss is `waste_order` **0.1652** (the RRF order buries gold the pool holds), plus the CE's
0.0221. **The lane answer was already closed (§I98); the retrieval answer is now closed too.**
⚠️ **Caveat, stated:** overview's label sets are broad (mean 73.8 pages = 7.6 % of the corpus) and
the pool is 35 % gold, so part of `waste_order` is the metric being unable to reward a reasonable
20-slot answer to a broad question. The order loss is real recoverable space, not all of it
recoverable.

**4. ▶ THE NEW #1: THE FUSION'S ORDERING HAS NEVER BEEN TESTED.** §I92 tested the **cap** (coverage)
and **MMR** (coverage); §I67 tested the **width** (coverage); T4 tested the **CE's query text**. Every
one of those is a coverage or a CE knob. `waste_order` is the loss from the pool's own **order**, and
no run has contrasted the fused RRF order against any alternative at the endpoint. That is the
untested lever, and it is the largest one for overview.

**5. ⚠️ What this does NOT license.** The oracle is an upper bound, not an achievable target. This is
one corpus, one document, one funnel, one CE model. `n = 40` per non-factual type, so the per-type
figures are point estimates without CIs here — the ordering claim is a size argument, and the run
that would give it a CI is item 4. No lane, no cap and no width is re-opened.

**Read-only. Nothing written to any collection. No run.**

---

#### I100. ✅ THE FUSION-ORDER RUN RAN — **NO ORDER INTERVENTION MOVES THE ENDPOINT.** The pool's ORDER is **not** the lever, and removing SPLADE+ColBERT **HURTS**. ⚠️ §I99's "new #1" is CLOSED, and §I89's dilution hypothesis is contradicted.

**Artifact** `logs/p1/step10/fusion_order.json` (**133 queries, 0 errors, wall 2,470 s**, one index
`knowledge_base_v3` nomic-768, HyDE ON and frozen, read-only). Pre-registration committed **ALONE** as
`e8dda1a`; the **pre-run amendment §11** committed **ALONE** as `c65e4a6` (D6.1). Harness
`fusion_order_endpoint.py`; independent stdlib verifier `fusion_order_verifier.py`
(**393/393 checks PASS**); mutation proof `fusion_order_mutation.py` (**391 mutations, 393/393 checks
reddened, NO inert check**, every mutation reddens its intended check).

**THE RESULT — every treatment is a null or a harm.** Paired per query vs **O0** (the product), n=133:

| arm | what it changes | nDCG@20 | MAP | MRR@20 | R@20 | P@20 |
|---|---|---|---|---|---|---|
| **O1** | `mmr_enabled=False` | +0.0004 *unres* | −0.0005 *unres* | +0.0004 *unres* | +0.0015 *unres* | −0.0000 *unres* |
| **O2** | `colbert_enabled=False` | −0.0012 *unres* | −0.0034 *unres* | −0.0028 *unres* | +0.0001 *unres* | +0.0015 *unres* |
| **O3** | dense-only (SPLADE+ColBERT out) | **−0.0182** *unres* | **−0.0145** *unres* | **−0.0231** *unres* | **−0.0238** *unres* | −0.0011 *unres* |
| **O4** | level-1 RRF weights (dense 1.0, sparse .5, colbert .5) | −0.0004 *unres* | −0.0027 *unres* | +0.0038 *unres* | −0.0006 *unres* | +0.0015 *unres* |

**1. ⇒ NOTHING SHIPS, and the lever is CLOSED.** The largest effect is **O3, and it is NEGATIVE** —
**RESOLVED NEGATIVE on multihop** (nDCG **−0.0162 [−0.0310, −0.0015]**, R@20 **−0.0264
[−0.0518, −0.0011]**). Every other cell is unresolved. **The pool's order is not improvable by any of
these mechanisms**, so `waste_order` (§I99: 0.1791 overall, 0.1652 overview) is **not produced by MMR,
not by ColBERT dilution, and not by level-1 lane weighting.** §I99's "the fusion's ordering has never
been tested → the new #1" is answered, and the answer is **no**.

**2. ⚠️ §I89's DILUTION HYPOTHESIS IS CONTRADICTED.** §I89/§I99 suggested the model-independent lanes
(SPLADE, ColBERT) dilute the dense lane in RRF. **Removing them makes it worse**, not better: O3 is
−0.0182 overall and resolved-negative on multihop. The lanes are earning their place.

**3. ⚠️ PER TYPE, and overview nudges UP in every arm — none resolves.** overview nDCG@20: O1
**+0.0024**, O2 **+0.0050**, O3 **+0.0083**, O4 **+0.0050** — **all unresolved** (n=40). factual:
O1 +0.0009, O2 −0.0094, O3 **−0.0396**, O4 −0.0011. multihop: O1 −0.0024, O2 +0.0034, O3 **−0.0162
RESOLVED**, O4 −0.0049. So the direction is consistent — order tweaks help overview slightly and hurt
factual/multihop — but **the magnitude is ~20× below what would close `waste_order`**.

**4. ⚠️ MMR DOES FIRE — on 16 of 133 queries — and O1 differs from O0 on EXACTLY those 16.** The
artifact carries O0's own MMR delta; the set of queries where O0's MMR fired and the set where O1's
pool differs from O0's are **set-equal**. So O1 is a genuine single-variable contrast, and its null is
a measured null.

**5. ⚠️ O4 IS NOT A PURE ORDER INTERVENTION — §2's claim was WRONG.** §2 said O4 isolates dilution
"**without** removing candidates". Measured: O4's pool page SET differs from O0's on **133 of 133**
queries (the order on 133/133), because the level-1 fusion is **truncated** to `limit` and reordering
moves which candidates survive. **Stated, not buried:** O4's null could be an order effect cancelled by
a composition change, and it cannot be read as a clean order test.

**6. THE REGISTERED PREDICTIONS, scored.**
* **P1 (O1 is a null) — CONFIRMED as a null, but the REASON given was wrong.** §5 said MMR "fires only
  when `len(deduped) > fetch_k`, which is a minority of queries". It fires on **16 of 133** and O1
  differs on exactly those. A right answer from a wrong mechanism.
* **P2 (O3 improves overview) — DIRECTION CONFIRMED, UNRESOLVED** (+0.0083 nDCG, +0.0025 R@20), **and
  O3 is a net HARM overall and RESOLVED NEGATIVE on multihop.** The prediction was not weighted for
  the other two types.
* **P3 (O2 sits between O0 and O3) — CONFIRMED** (−0.0012 vs −0.0182).
* **P4 (O4 ≥ O0 on overview) — direction confirmed, UNRESOLVED** (+0.0050).
* **P5 (no arm closes `waste_order`) — CONFIRMED**, decisively: the best overview gain is +0.0083
  against 0.1652.

**7. ⚠️ THREE DEVIATIONS, all stated.**
* **The mutation proof ran AFTER the run**, not before it as §7 required. It **cannot** run before: the
  verifier's checks are population-specific (133 queries, 53/40/40), so it needs a full-shaped
  artifact. It ran **before any number was read** — the §I91 precedent, recorded rather than hidden.
* **The recorded `G3` flag is MIS-SPECIFIED and is SUPERSEDED.** The harness read `mmr_fired` from the
  **arm's own** call, and for O1 MMR is disabled — so it read False on all 133 and G3 asserted
  set-equality on the 16 queries where O0's MMR **did** fire. Re-derived from O0's own delta, G3
  **PASSES**. The verifier re-derives it (`V6_G3_O1_set_equality_REDERIVED`) and asserts the recorded
  flag is the mis-specified one (`V6_G3d`); the harness is fixed.
* **The recorded `G5` sub-check `O4_pool_set_identical_to_O0_everywhere` is MIS-SPECIFIED** — it is an
  INVARIANCE claim, not a mechanism check, and false by construction (item 5). Corrected to
  **reported**; the mechanism checks all pass.

**8. ⚠️ TWO INSTRUMENT FINDINGS worth carrying.**
* **`V4` is not "must be zero".** 10 multihop queries carry a **page-less endpoint candidate** from the
  graph lane (`gold-008` on all six arms — the same query §I98 flagged). The harness's metrics count the
  slot; a re-derivation from page lists cannot. The verifier now checks the **metric function** only on
  the rows where it is exact and reports the exclusion, and asserts the **mechanism** (every affected
  query is multihop).
* **`O0w` (the guard arm) is bit-identical to `O0` on 133/133 queries** — the live proof that the O4
  code change is inert by default. `G7` PASSES.

**9. ▶ WHAT THIS LEAVES.** The endpoint's loss is **not** the pool's order, **not** the lanes, **not**
the fusion width/cap/MMR, and the cross-encoder is worth 0.005 (§I99). The remaining candidates are the
**embedder/ingestion** (§A, the per-space query-vector fix, which unblocks the v2-vs-v3 comparison) and
the **generator stage** (unmeasured). ⚠️ **The overview metric itself is now a live suspect**: its label
sets are broad (73.8 pages of 968), the pool is 35 % gold, and no ranker — fused, weighted, dense-only
or cross-encoded — surfaces more than ~51 % of its slots as gold.

**Read-only. No writes to any collection. No re-ingest, no embedder change.**

---

#### I101. ✅ 5A — THE OVERVIEW-METRIC DIAGNOSIS RAN (read-only). ⚠️ **The "broken measuring stick" is REFUTED STRUCTURALLY: for overview, RECALL and PRECISION have IDENTICAL capture (0.527), so the broad-label denominator cancels — the metric is not the constraint. Every query type is RANKER-limited.** ⇒ 5B (graded labels) is **hygiene, not a fix**.

**The question** (§I100 item 9). Is overview's low score an ARTIFACT of the metric (a 73.8-page label set
making recall's denominator enormous) or a REAL ranking loss? §I100 registered it as *"a live suspect"*
but never tested it. **This is the gate for 5B.**

**Read-only. No run, no new measurement** — a re-derivation over three existing artifacts
(`t4_endpoint.json`, `t0_baseline.json`, `fusion_order.json`). Harness
`logs/p1/step10/overview_metric_diag.py` → `overview_metric_diag.json` (sha256 `a08ed9b92c1c597a…`);
independent stdlib verifier `overview_metric_diag_verifier.py` (**50/50 checks PASS**, every cell
re-derived from the SOURCE per-query arrays); mutation proof `overview_metric_diag_mutation.py`
(**50 mutations, 50/50 checks reddened, NO inert check**). Pre-registration
`.hermes/plans/2026-10-31-p1-overview-metric-diagnosis-preregistration.md`, committed **ALONE** as
`8f6af4f` (D6.1).

**The method — two ceilings, and a capture ratio.** Per query: the realised value, the **LABEL** ceiling
(what the register already reports), and the **POOL-AWARE** ceiling — the best any ranker could do on
the gold the product's pool *actually holds* (`P_ceil_pool = min(pool_gold,k)/k`;
`nDCG_ceil_pool = IDCG(min(pool_gold,k))/IDCG(min(n_rel,k))`). `capture = realised / ceiling_pool`
(per-query ratio, averaged within type). **`capture >= 0.90` ⇒ metric-limited; `< 0.90` ⇒
ranker-limited** — the threshold was fixed in the pre-registration and not moved.

| type | n | R@20 | R-ceil lab / pool | **cap_R** | P@20 | P-ceil lab / pool | **cap_P** | nDCG | nDCG-ceil pool | **cap_nDCG** | pool_gold (mean/med/min/max) | frac ≥ 20 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| factual | 53 | 0.5574 | 0.9557 / 0.8052 | 0.673 | 0.1358 | 0.3000 / 0.2472 | 0.673 | 0.4524 | 0.8829 | 0.509 | 5.3 / 2 / 0 / 29 | 0.08 |
| **overview** | 40 | 0.1882 | 0.3992 / 0.3755 | **0.527** | 0.5125 | 1.0000 / **0.9688** | **0.527** | 0.5379 | **0.9790** | **0.548** | **31.4 / 29 / 12 / 61** | **0.80** |
| multihop | 40 | 0.5500 | 1.0000 / 0.6466 | 0.843 | 0.1050 | 0.2138 / 0.1363 | 0.843 | 0.5072 | 0.7221 | 0.700 | 2.7 / 2 / 0 / 9 | 0.00 |
| all 133 | 133 | 0.4442 | — / 0.6283 | 0.676 | 0.2398 | — / 0.4308 | 0.676 | 0.4946 | 0.8634 | 0.576 | — | — |

**1. ⚠️ THE STRUCTURAL FINDING — recall and precision have the SAME capture, so the broad-label
argument is MOOT.** For overview, `cap_R == cap_P == 0.527` **exactly**. That is not a coincidence: both
ratios reduce to the same quantity,
`|gold ∩ C| / min(k, pool_gold)` — the `n_rel` denominator **cancels** between the realised recall and
the recall ceiling. ⇒ **A broad label set cannot make recall selectively unfair here, because recall's
capture is identical to precision's.** The "73.8 pages is too many" reading is **refuted for the
capture question**: the label breadth is fully absorbed by the ceiling, and against that ceiling the
ranker sits at 0.53 on both families.

**2. ⚠️ THE POOL-AWARE CEILINGS ARE NEAR THE LABEL CEILINGS, so the register's `P-ceil = 1.0` was
slightly optimistic but not misleading.** overview `P_ceil_pool = 0.9688` (vs label 1.0),
`nDCG_ceil_pool = 0.9790` (vs label 1.0), `R_ceil_pool = 0.3755` (vs label 0.3992). **80 % of overview
queries have `pool_gold >= 20`** — the pool holds enough gold to fill every slot — so the achievable
ceiling really is ≈1.0 and the system really is at ≈0.53 of it. **0.43 of nDCG@20 is recoverable
ranking**, not a metric artifact.

**3. ⇒ THE VERDICT: RANKER-LIMITED on EVERY family, for EVERY type.** overview: R 0.527 · P 0.527 ·
nDCG 0.548. factual: 0.673 · 0.673 · 0.509. multihop: 0.843 · 0.843 · 0.700. All **below the 0.90
threshold**. The registered prediction ("overview is ranker-limited on all three families; the
broken-measuring-stick reading is refuted") is **CONFIRMED**. ⇒ **5B (graded labels) is HYGIENE, not a
fix** — it would not make the overview problem go away, because the metric is not where the loss is.
The loss is the ordering loss already named (§I99 `waste_order` 0.1652).

**4. ✅ THE MMR SUBSET CHECK (the Q3 question, folded in).** MMR fires on **16 of 133** — factual 5,
overview 5, multihop 6 (⚠️ **spread across all three types, not concentrated**). On the queries where it
fires, `O1 − O0` (MMR off vs the product) is **nDCG +0.0030, R@20 +0.0127, MRR@20 +0.0037** — small, and
**mixed by type** (nDCG: factual **+0.0091**, overview **+0.0195**, multihop **−0.0159**). ⇒ **Even on
its own firing set, MMR moves the endpoint metric by ~0.003 nDCG** — the aggregate null (§I100) is not
hiding large opposite-sign per-query effects; the 16 are individually near-null. The firing set is
**set-equal to the O0/O1 pool-diff set** (§I100 item 4 reproduced, guard V8b).

**5. ⚠️ A DEVIATION, stated.** The pre-registration §3 wrote `capture = realised/ceiling` without saying
*per-query-then-averaged* vs *ratio-of-means*. It is implemented **per-query-then-averaged** (the
project's universal convention — the §I99 harness does the same), and the verifier re-derives it that
way. The two definitions differ by < 0.02 on every cell and **change no verdict**. Recorded rather than
silently chosen.

**6. ⚠️ What this does NOT license.** It does not say the ranker is "broken" — the pool-aware ceiling is
an ORACLE (an upper bound, §I99), not a target. It says the metric is not the explanation and the
headroom is real ranking headroom. One corpus, one document, one funnel, one CE model. ⚠️ **It does not
close 5B**: a graded label set is still legitimate hygiene for a broad question class, and it remains
available — but it is **demoted from "the overview fix" to "optional label hygiene"**, and it should not
be run before the retrieval levers (4A/4B, §A), which target the loss this entry shows is real.

**Read-only. Nothing written to any collection. No run, no re-ingest.**

---

#### I102. ✅ 4B — THE ENDPOINT CUT MEASURED AS nDCG@k. ⚠️ **The cut is MONOTONE and can never change the top-20 (the CE's top-20 is a PREFIX of its top-50, 133/133); it adds RECALL and nothing else. The apparent nDCG gain is a CONSTRUCTION artifact — on the 45 comparable queries it is UNRESOLVED (−0.0078).**

**The question.** §I97 P3 measured the 20-slot cut's **coverage** cost (+0.1451, RESOLVED) and the register
read it as *"a deliberate context budget."* **Coverage is not ranking** — no run had measured nDCG@k or
R@k. This closes that gap.

**Read-only. No run** — a re-derivation over ONE artifact (`t4_endpoint.json`: arm C = CE top-20, arm W50 =
CE top-50, same pool). Harness `logs/p1/step10/cut_ndcg_k.py` → `cut_ndcg_k.json` (sha256
`fe297d18981a17e9…`); independent stdlib verifier `cut_ndcg_k_verifier.py` (**33/33 checks PASS**);
mutation proof `cut_ndcg_k_mutation.py` (**31 mutations, 33/33 checks reddened, NO inert check**).
Pre-registration `.hermes/plans/2026-10-31-p1-cut-ndcg-k-preregistration.md`, committed **ALONE** as
`df92662` (D6.1).

**1. ⚠️ THE PREFIX IDENTITY — the cut CANNOT move the top-20.** On **133 of 133** queries
`W50_pages[:20] == C_pages` **and** `C_pool_sha == W50_pool_sha` (guard G2). The cut is applied *after*
reranking, so widening it appends ranks 21–50 and leaves the top-20 byte-identical. ⇒ **`nDCG@20`, `R@20`,
`P@20` are identical between the arms** (verified per query, V6). **Prediction 1 CONFIRMED.**

**2. ⚠️ THE APPARENT nDCG GAIN IS A CONSTRUCTION ARTIFACT.** Paired vs arm C, n=133:

| | arm C (top-20) | arm W50 (top-50) | paired Δ | 95 % CI | W/L/T | verdict |
|---|---|---|---|---|---|---|
| nDCG@**k** | 0.4946 | 0.5179 | **+0.0233** | [+0.0109, +0.0360] | 51/26/56 | **RESOLVED — but see below** |
| R@**k** | 0.4442 | 0.5874 | **+0.1433** | [+0.1126, +0.1780] | 77/0/56 | RESOLVED |
| P@**k** | 0.2398 | 0.1824 | **−0.0574** | [−0.0705, −0.0448] | 0/77/56 | RESOLVED (negative) |

⚠️ **`nDCG@50` vs `nDCG@20` is NOT a like-for-like comparison.** Where `n_rel <= 20` (88 of 133 queries),
`IDCG@20 == IDCG@50`, so the 50-list is a **superset with the same denominator** and the delta is
**non-negative BY CONSTRUCTION**. Split by that:

| block | n | mean ΔnDCG | 95 % CI | verdict | mean ΔR | extra gold |
|---|---|---|---|---|---|---|
| `n_rel <= 20` (same denominator) | 88 | +0.0392 | [+0.0269, +0.0528] | RESOLVED — **by construction** | +0.1191 | 0.68 |
| **`n_rel > 20` (comparable)** | **45** | **−0.0078** | [−0.0327, +0.0183] | **UNRESOLVED** | +0.1905 | **11.42** |

⇒ **On the only queries where the comparison is meaningful, the extra slots do NOT improve ranked quality
(−0.0078, unresolved).** The aggregate +0.0233 comes entirely from the 88 same-denominator queries, where
it is arithmetic, not a finding. **Prediction 2 CONFIRMED** once the construction is stripped.

**3. ✅ THE CUT ADDS RECALL, AND CANNOT REMOVE ANY.** `ΔR@k = +0.1433 [+0.1126, +0.1780] RESOLVED`,
**77 wins / 0 losses / 56 ties** — recall is **monotone** in k by construction (a superset), so "the cut
costs recall" is false and "the cut adds recall" is true. Per type the added gold is **overview 12.05
pages** vs factual 1.49 and multihop 0.33 — the broad-label type is where a wider context window pays.
**Prediction 3 CONFIRMED.** `P@k` falls (−0.0574) purely because the denominator grows.

**4. ⇒ THE VERDICT: THE CUT IS A CONTEXT-BUDGET KNOB, NOT A RANKING LEVER.** It cannot improve the
top-20 (prefix), it improves recall monotonically, and its nDCG effect is unresolved where measurable.
**Prediction 4 CONFIRMED.** ⚠️ Whether the extra context helps the *answer* is the **generator stage**,
still unmeasured — so this does not say "widen the cut"; it says the cut's cost and its only gain are both
about **context size**, not retrieval quality.

**5. ⚠️ THREE DEVIATIONS, stated.**
* **The comparability split was ADDED to the harness after the first run.** The same-denominator
  construction is a mathematical fact (same IDCG, superset list) that MUST be stated to avoid reading
  +0.0233 as a finding; it is a guard against a false positive, not a post-hoc filter. The pre-registration
  §4 prediction 2 already named this case ("unresolved or negative").
* **A verifier bug, found and fixed during verification.** `json.dumps(sort_keys=True)` reorders `by_type`
  alphabetically on reload, so the bootstrap (which resamples by INDEX) must rebuild the population in a
  FIXED `TYPES` order. The first verifier run failed 4 checks on exactly this; the fix is in both files.
* **Page-list vs chunk-list convention (§I97 §15).** The artifact stores page-deduped lists, not chunk
  slots, so `nDCG@50` re-derived from pages differs from T4's chunk-level `W50_metrics["ndcg_at_50"]` by
  **≤ 6e-4 on 2 of 133 queries** (the documented §15 gap). `R@50` re-derives **exactly** (0 mismatches).

**6. ▶ NAMED FOLLOW-UP.** **k=100 needs a run** (T4 kept ≤ 50). ⚠️ Given the prefix identity, ranks 51–100
are the same kind of question as 21–50 — a context-budget question — so k=100 is only worth a run if the
generator stage is being measured.

**Read-only. Nothing written to any collection. No run, no re-ingest.**

---

#### I103. ✅ 4A — SCORE-BASED FUSION vs RANK-BASED RRF. ⚠️ **Score fusion is NOT a lever: it is a small RESOLVED HARM on multihop (S1 −0.0112, S2 −0.0212 nDCG@20) and UNRESOLVED everywhere else. Rank RRF is earning its place. It DOES change the pool's composition on 133/133 — the composition trap, measured.**

**The question** (§I100 item 9's own "NOT measured" list). Every fusion test so far kept the **rank** mechanism and moved a knob around it (§I92 the cap and MMR, §I67 the width, §I100 the ORDER). Rank fusion **discards the score magnitude**; score fusion keeps it. **Does replacing `Σ 1/(rrf_k + rank)` with a normalised score sum change the pool's coverage, or the endpoint's nDCG@20?**

**Read-only. No collection write, no re-ingest** — one new, **additive, inert-by-default** merge (`store._score_merge`), reached through a `fusion=` kwarg on `search` / `search_with_das` / `_qdrant_search`. Harness `logs/p1/step10/score_fusion.py` → `score_fusion.json` (sha256 `83933c365f6728f0…`, 133 queries, 0 errors, wall **620.3 s**, reachable pages **888**); independent stdlib verifier `score_fusion_verifier.py` (**279 checks PASS**, every cell re-derived from the raw per-query page lists); mutation proof `score_fusion_mutation.py` (**item 7**). Pre-registration `.hermes/plans/2026-10-31-p1-score-fusion-preregistration.md`, committed **ALONE** as `32f6c5f`; its **pre-run amendment §9** committed **ALONE** as `047e292` (D6.1).

**1. THE ARMS.** The three lanes produce **incomparable** scores (dense cosine, SPLADE sparse dot, ColBERT MaxSim), so the normalisation **is** the experiment. Each lane is normalised **per query, over that lane's own candidate set**, then summed (unweighted):

| arm | merge | formula |
|---|---|---|
| **S0** | **the product** — rank RRF, `rrf_k=1` | `Σ_lanes 1/(1 + rank)` |
| **S1** | min-max score sum | `Σ_lanes (s − min)/(max − min)` |
| **S2** | z-score score sum | `Σ_lanes (s − mean)/std` |

**2. ⚠️ THE HEADLINE — score fusion is NOT a lever.** Paired vs S0, n=133, **10,000 bootstrap resamples, seed 20261031**; RESOLVED iff the paired 95 % CI excludes 0:

| arm | nDCG@20 | MAP | MRR@20 | R@20 | R@100 | P@20 | Hit@20 | pool_cov |
|---|---|---|---|---|---|---|---|---|
| **S0** | 0.5503 | 0.3406 | 0.7717 | 0.4563 | 0.6706 | 0.2372 | 0.9323 | 0.6845 |
| S1 | 0.5466 | 0.3371 | 0.7737 | 0.4437 | 0.6657 | 0.2376 | 0.9323 | 0.6797 |
| S2 | 0.5459 | 0.3350 | 0.7716 | 0.4455 | 0.6700 | 0.2391 | 0.9323 | 0.6839 |

| arm | ΔnDCG@20 | 95 % CI | ΔMAP | ΔMRR@20 | ΔR@20 | verdict |
|---|---|---|---|---|---|---|
| **S1** | **−0.0037** | [−0.0125, **+0.0040**] | −0.0035 | +0.0021 | −0.0126 | **UNRESOLVED** |
| **S2** | **−0.0044** | [−0.0138, **+0.0040**] | −0.0056 | −0.0001 | −0.0108 | **UNRESOLVED** |

**Every overall key is unresolved, and every point estimate is ≤ 0.005.** ⇒ **Prediction 2 CONFIRMED** (|ΔnDCG@20| < 0.01, unresolved). The register has found **no fusion-side lever**, and this closes §I100's last "not measured" item: the score magnitude carries nothing the rank sum does not already order.

**3. ⚠️ BUT IT IS A RESOLVED HARM ON MULTIHOP — the one place it resolves.** Per type, nDCG@20:

| arm | factual (n=53) | **multihop (n=40)** | overview (n=40) |
|---|---|---|---|
| **S1** | −0.0017 unresolved | **−0.0112 [−0.0260, −0.0004] RESOLVED NEGATIVE** | +0.0011 unresolved |
| **S2** | +0.0016 unresolved | **−0.0212 [−0.0405, −0.0049] RESOLVED NEGATIVE** | +0.0044 unresolved |

⇒ **On the one type where it resolves, score fusion LOSES.** §8's falsification clause reads *"If S1/S2 RESOLVES NEGATIVE, the rank fusion is earning its place and the question is closed."* **That is what happened.** ⚠️ Mechanism stated as **consistent-with, not proven**: the multihop pool is the one whose gold set is thin and whose appended graph lane already injects unordered candidates, so a merge that re-weights by **magnitude** (SPLADE's raw dot products are ~10², dense cosines ~10⁰) can demote a page the rank sum would have kept. The overall effect is unresolved because the other two types are exactly flat.

**4. ✅ PREDICTION 3 CONFIRMED — the composition trap, MEASURED.** S1 and S2 change the surviving pool **SET** on **133 of 133** queries (`frac 1.0`). ⇒ as §3 of the pre-registration stated, this is a **composition change as well as an order change** (exactly §I100 item 5's O4 flaw). It is stated so the near-null is **not** later read as a pure order test: the score sum **re-orders AND re-selects**, and the re-selection is not an improvement.

**5. ✅ THE ANCHOR HOLDS — S0 IS the shipped product.** G2: S0 reproduces `lane_inclusion.json`'s arm F0 (session 27, same index, same code path, post-policy) on **every key the anchor carries**, per type, within **1e-4**. The §9 amendment's cross-day check holds exactly: T0's fusion-row pool coverage **0.684486** == S0's **0.6844860103**. **Prediction 1 CONFIRMED.**

**6. ⚠️⚠️ A NEW INSTRUMENT FINDING — the store's vector-lane query is NONDETERMINISTIC in its low-ranked tail.** The first run's G3 (registered as *"the three arms' input lane lists are identical, asserted on a lane digest"*) **FAILED on 5 of 133 queries** — yet every arm's per-lane `min`/`max`/`n` was identical. A dedicated read-only probe (`score_fusion_determinism_probe.py` → `score_fusion_determinism_probe.json`) settled it: on **all 5** flagged queries, **4 identical calls (same query, same arm) return 2 distinct lane digests but 1 distinct pool SHA**, and the endpoint pages are **reproducible**. ⇒ the lane **content** flips in its tail; the lane **set** never moves and the **fused result is inert**. A random 15-query sample showed **0/15** flips — so it is **query-specific**, not a per-call coin toss.
**Guard restated, not weakened (the §I100 pattern):** **G3** now asserts the lane **SET** identity (candidate count per lane, **0 mismatches on 133/133**), and a new **G3b** asserts the digest flip is **pool-inert** — it re-queries each flagged query and requires the pool SHA **and** the endpoint pages to be reproducible (**6/6 flagged queries: pool_sha_stable and pages_stable both True**). The digest mismatches are **reported** (`n_digest_mismatch: 6`), not asserted.
⚠️ **This is a §I68-class finding and it is NOT confined to 4A.** Any run that compares two retrieval paths whose lanes are re-queried per arm (T0, T4, §I98, §I100) carries the same tail nondeterminism; the determinism guards those runs used were at the **metric** level, not the **lane** level. **Recommended follow-up: register the lane-tail nondeterminism as its own entry and add a lane-digest stability control to the shared harness.**

**7. ✅ THE VERIFIER AND MUTATION PROOF.** `score_fusion_verifier.py` — **stdlib only**, re-derives every aggregate, delta, CI (same seed) and guard from the artifact's raw per-query page lists, including re-implementing the endpoint metrics: **279 checks, 0 failed**. `score_fusion_mutation.py` — one mutation per check over every recorded cell: **307 mutations, 279/279 checks reddened, NO inert check, every mutation reddens its intended check** (log: `score_fusion_mutation_log.txt`).
⚠️ **The first mutation run failed its own bar and the two causes are recorded, not buried.** (a) **Two mutations were MIS-TARGETED**: they perturbed S0's `recall_at_100` and `coverage_reachable`, which the corrected G2 does **not** compare (the anchor lacks the first; the second is not in G2's key set) — they reddened the V2 aggregate check instead. Retargeted to the keys V8 actually compares. (b) **A duplicate check name** in the verifier (`precision_ceiling_at_20` was emitted twice, once via `ENDPOINT_KEYS` and once explicitly) made the enumerated count **291** while the unique-name count was **279** — deduplicated. Both are the **over-strict / mis-scoped-check class**; neither changed a number.

**8. ⚠️ DEVIATIONS, stated.**
* **A harness bug, found by the first run and fixed.** G2 compared **every** endpoint key against the F0 anchor, but F0 carries no `recall_at_100`; `ref.get(k) or 0` read a missing key as **0** and reddened the guard on **correct** data (gap 0.6706). Fixed to compare only the keys the anchor carries; the absent keys are **reported** (`G2_anchor_missing_keys: ["recall_at_100"]`). The first-run artifact is preserved as `score_fusion_firstrun_G2G3_failed.json`.
* **G3 restated** (item 6) — set identity asserted, digest flip reported + inertness asserted.
* **The run was executed TWICE.** The first run (artifact preserved) is the one that exposed the two guard anomalies; the second, with the corrected harness, is the registered artifact. Its aggregates reproduce the first to **4 decimal places** (S0 nDCG 0.5503, S1 0.5466, S2 0.5459; ΔS1 −0.0037, ΔS2 −0.0044) — the tail nondeterminism does **not** move the answer.
* **The "one lane pass per query" cost model was not used.** §3 of the pre-registration expected one lane pass + three merges; the harness instead runs the product entry point **once per arm** (three lane passes + three CE passes), so the run cost ~3× that estimate (620 s). The arms still differ only in the merge — G3/G3b **measure** that rather than assume it.

**9. ⚠️ What this does NOT license.** One corpus, one document, one funnel, one CE model. It says **score fusion is not a retrieval lever here**, and that on multihop it is a small resolved harm — it does not say no score fusion could ever help (a learned per-lane calibration is a different object and is unmeasured). ⚠️ It does **not** re-open the fusion as the endpoint's binding constraint: §I100's ORDER result and this one agree that the **pool → top-20 ranking step** remains the loss.

**Read-only. Nothing written to any collection. No run, no re-ingest.**

---

#### I104. ✅ §A — THE PER-SPACE QUERY-VECTOR FIX. The DA and graph lanes now embed their **own** query in the **collection's** space: a **1024-dim arm's** lanes go **0 → 5 hits**, and a **768-dim arm is a BIT-EXACT no-op** (A3). This unblocks the lane-complete v2-vs-v3 A/B (§I89's T3).

**The defect** (§I12/§D15, recorded but never fixed). Both derived lanes took the **arm's** dense vector and sent it verbatim to a collection built in a **different space**: `store.search_da` → `derivative_artifacts` and `graph_builder._find_concepts_scored` → `concept_embeddings`, both re-created at **768d** by §I83. A **1024-dim arm** therefore sent a 1024-vector to a 768-slot, **Qdrant 400'd**, the caller's `except` swallowed it, and the lane was **silently skipped** — indistinguishable from a lane that legitimately returned nothing. **Production (768) was unaffected**; the **v2/1024 *arm*** was broken, which is why Stage F had to turn both lanes **off** and narrow its question (§I89).

**The fix.** One query vector **per space**, resolved **off the COLLECTION**: if the arm's vector width already matches the collection's, it is used **unchanged** (bit-exact, A3); otherwise the lane's **TEXT** is re-embedded with the **derived** embedder (`cluster_embedder.get_derived_embedder` → `derived_dense_model`/`derived_dense_dim`, new config fields); if there is no text, or the derived embedder's width also differs, it **RAISES** naming the lane, both widths and the remedy. ⚠️ **The TEXT INPUT of each lane is preserved exactly** — the DA lane's is the **HyDE hypothetical** (`evaluate_rag` now threads `da_text`), the graph lane's the **raw query** — only the MODEL changes, so the lane's *meaning* is untouched and only its *space* moves.

**Read-only at run time. No collection write, no re-ingest.** Pre-registration `.hermes/plans/2026-11-01-p1-per-space-query-vector-preregistration.md`, committed **ALONE** as `6462145` (D6.1). Probe `logs/p1/step10/per_space_probe.py` → `per_space_probe.json` (3 queries, live cluster); independent stdlib verifier `per_space_verifier.py` (**21 checks, 0 failed**); mutation proof `per_space_mutation.py` (**21 mutations, 21/21 checks reddened, NO inert check**).

**1. ✅ A1 — the lane goes 0 → N.** A **1024-dim arm** (Qwen3) against the 768-dim collections: **before**, the raw call **400s on every query** (`da` and `graph` both, error recorded); **after**, both lanes return **5 hits on 3/3 queries**.

**2. ✅ A2 — the space actually switched.** The resolved lane vector's width (**768**) differs from the arm's (**1024**) on **3/3** for both lanes.

**3. ✅ A3 — the discriminating control holds.** For a **768-dim arm** (whose space already matches), the resolver returns the arm's **own vector object, unchanged** (`is` identity) on **3/3** for both lanes, **and** the DA lane's returned `chunk_id`s equal the raw call's **id for id** on **3/3**. ⇒ the fix is a **bit-exact no-op** where the space already matched — it changed the space, not the lane.

**4. ✅ A4 is closed by the unit tests, not the probe.** `tests/test_per_space_query_vector.py` (9 tests) pins: the mismatch with **no text RAISES**; a derived embedder of the wrong width **RAISES**; the width is read **off the collection** (a 512-wide collection resolves to 512 with `dense_dim=1024`); an unreadable schema falls back to today's behaviour; and `search_da` **sends** the resolved vector and **raises** on a mismatch with no text. ⚠️ **A4 is the point of the fix's error path**: a mismatch is never a silent `[]`.

**5. ⚠️ THREE DEVIATIONS, stated.**
* **A4 needs the lane's TEXT, so the raise is a behaviour change on the mismatched path only.** The pre-registration's *"`None` preserves today's behaviour exactly"* holds when the widths **match** (the production case, and A3 measures it). Where they **differ**, today's behaviour was a **silent `[]`** and the fix now **RAISES** — that change **is** A4, not a regression.
* **`graph_builder._find_concepts_scored` resolves OUTSIDE its query `try`.** Its `except` returns `[]` (the LLM fallback), which would have swallowed the §A raise — so the resolve was moved above it. A Qdrant **client** failure still falls back as before.
* **The signature change has a blast radius, and the full suite found it.** `search_da` gained `query_text`; `search_with_das` now falls back to `query_text` when no hypothetical is supplied; the `_derived_embedder` singleton needed a **conftest reset** (the existing fixture reset the cluster embedder but not this one, so a derived embedder built under one test's config leaked into later tests — **order-dependent failures**); and **two tests hardcoded a 768 query vector against a collection created at `dense_dim` (1024)**, which the new resolve correctly refuses — they now use the config's dim. ⚠️ **None of these changed a number**: the fix is a no-op where the spaces match (A3).

**6. ⚠️ A STALE COMMENT, recorded not silently fixed.** `config.embedding_model`/`embedding_dim` describe themselves as the derived collections' model, but **both derived writers call `get_cluster_embedder`** (`index_derivative_artifacts.py:111`, `graph_builder.py:360`) — so the derived space is the **dense lane at build time**, and §I83's 768 is that space. The new `derived_dense_model`/`derived_dense_dim` name it **explicitly**; the legacy block's comment is left for its own change (§I44's class).

**7. ▶ WHAT THIS UNBLOCKS.** **T3 — the lane-complete v2-vs-v3 A/B** (§I89 left it unmeasured because a 1024-dim arm could not query the derived lanes at all). ⚠️ **It is a DEFECT FIX, not a retrieval improvement**: nothing here says the endpoint improves — it says the derived lanes are **reachable from either arm**, so the comparison is now like-for-like.

**Read-only at run time. No collection write, no re-ingest.**




---

#### I105. ✅ THE PER-TYPE k SWEEP at the endpoint — **wider k buys RECALL and COVERAGE (most for overview), NOT ranked quality; the apparent CAPTURE gain is a CEILING artifact.** The owner's "wider k helps, and most for overview" is **half right**: the recall half is real and type-dependent; the quality half is refuted.

**The question.** §I97 P3 and §I102 measured the endpoint cut **20 → 50** on the WHOLE population. Neither reported **per query type**, and neither recomputed the **per-type ceilings**. Does widening the last layer's cut improve the metric **per type** — and is the benefit type-dependent (broad overview vs narrow factual)?

**Read-only. No run, no new measurement** — a re-derivation over TWO existing artifacts (`t4_endpoint.json`, `t0_baseline.json`). Two arms: **CE** = the cross-encoder's ranked pages (the LAST layer, `W50_pages`, k ≤ 50); **POOL** = the fused pool's own order (`fusion_ranked`, k ≤ 100). k grids CE `{1,2,5,10,20,30,40,47}`, POOL `{1,2,5,10,20,30,40,50}`; anchor **k=20**. Metrics per type: **R@k, nDCG@k, P@k, cov@k** (the `evaluate_rag.py` convention), each beside its **pool-aware ceiling**, plus **capture = realised/ceiling** (per query, averaged). Harness `logs/p1/step10/per_type_k_sweep.py` → `per_type_k_sweep.json`; independent stdlib verifier `per_type_k_sweep_verifier.py` (**18/18 checks PASS**, every cell re-derived from the raw page lists); mutation proof `per_type_k_sweep_mutation.py` (**17 mutations, 17/17 reddened their intended check, NO inert check**). Pre-registration `.hermes/plans/2026-11-01-p1-per-type-k-sweep-preregistration.md`.

**Guards (all pass).** population 133 (53/40/40); prefix identity `W50[:20]==C_pages` 133/133; pool sha 133/133; **cross-artifact anchor `t0.fusion_ranked[:20] == t4.N_pages` 133/133** (two independent runs agree on the pool order); CE arm @20 reproduces `t4.C_metrics` per query; R@k monotone.

**1. ✅ THE RECALL HALF IS REAL, MONOTONE, AND TYPE-DEPENDENT — CE arm, mean per type:**

| k | 1 | 5 | 10 | **20** | 30 | 40 | 47 |
|---|---|---|---|---|---|---|---|
| factual R@k | 0.204 | 0.344 | 0.457 | **0.557** | 0.635 | 0.689 | **0.725** |
| **overview R@k** | 0.013 | 0.058 | 0.109 | **0.188** | 0.268 | 0.327 | **0.370** |
| multihop R@k | 0.249 | 0.396 | 0.457 | **0.550** | 0.564 | 0.590 | **0.605** |

Paired vs k=20, full population: **factual ΔR@47 +0.1675 RESOLVED**, **overview +0.1817 RESOLVED**, **multihop +0.0529 RESOLVED** — and **Δcov@k tracks ΔR@k** exactly. **Overview gains most in RELATIVE terms** (0.188 → 0.370, ~2×). The owner's recall prediction is **CONFIRMED**.

**2. ⚠️ THE QUALITY HALF IS REFUTED — nDCG@k does NOT improve for overview.**

| k | 20 | 30 | 40 | 47 |
|---|---|---|---|---|
| factual nDCG@k | 0.452 | 0.474 | 0.490 | 0.500 |
| **overview nDCG@k** | **0.538** | 0.533 | 0.525 | **0.531** |
| multihop nDCG@k | 0.508 | 0.514 | 0.522 | 0.527 |

Paired vs k=20: **overview ΔnDCG@47 −0.0070 UNRESOLVED** (and −0.0050 / −0.0127 at k=30/40). On the **comparable block** (`n_rel > 20`, §I102's trap — where IDCG is not the same denominator): overview **n=40, ΔnDCG@30/40/47 = −0.0050 / −0.0127 / −0.0070, all UNRESOLVED**; factual **n=5** goes **−0.0374 RESOLVED NEGATIVE at k=30**; **multihop n=0** (no multihop query has `n_rel > 20`). ⇒ **wider k does not raise ranked quality for any type, and on the pool's own order it is a RESOLVED HARM for overview (POOL ΔnDCG@50 −0.0540).**

**3. ⚠️ THE CAPTURE RISE IS A CEILING ARTIFACT — the pre-registered falsification clause FIRED, and the mechanism refutes it.** overview `capture_nDCG` rises **0.548 (k=20) → 0.657 (k=47), +0.109** — above the +0.05 clause. **But the realised nDCG went DOWN (0.538 → 0.531) while the pool-aware CEILING fell (0.979 → 0.806).** The ceiling falls because overview's pool holds **~31 gold pages** but the label set is **~58**: past `k ≈ pool_gold`, `IDCG(min(pool_gold,k))` saturates while `IDCG(n_rel,k)` keeps growing. ⇒ **the entire capture gain is the denominator shrinking, not quality rising.** The clause is **recorded as fired and then explained away by its own mechanism** — stated, not buried.

**4. ✅ THE REGISTERED PREDICTIONS, scored.** **P1** (R/cov monotone, largest for overview) **CONFIRMED**. **P2** (nDCG flat/negative on the comparable block) **CONFIRMED**. **P3** (capture flat in k) **FALSIFIED in the letter, refuted in the mechanism** (item 3). **P4** (CE @20 a prefix) **CONFIRMED** (anchor).

**5. ⇒ THE VERDICT.** **Wider k is a CONTEXT-BUDGET knob, per type as well as overall** (§I97/§I102, now per type). It raises **recall and coverage** — real, monotone, and **most for overview** — but it **cannot raise ranked quality**, and the one number that appeared to rise (capture) rose by a **ceiling artifact**. ⚠️ Whether the extra overview pages help the *answer* is the **generator stage, still unmeasured** — this is the only reading under which "wider k for overview" pays.

**6. ⚠️ BOUNDS.** CE arm capped at **k=47** (T4 kept ≤ 50); **k > 100 is IMPOSSIBLE** without widening the pool cap (default 100) — a separate run (§I92 priced it: cap 100→500 = +0.1835 pool coverage → **+0.003** endpoint). n=40 per non-factual type. One corpus, one document, one funnel. ⚠️ **This closes the "does a wider cut help, per type?" question; it does NOT re-open the pool → top-20 ranking loss (§I99 `waste_order`), which remains the endpoint's binding loss.**

**Read-only. Nothing written to any collection. No run, no re-ingest.**

---

#### I106. ✅ THE WIDE-POOL / HIGHER-k TEST — **widening the pool cap (100 → 500) and sweeping k to 250 buys RECALL and COVERAGE, NOT ranked quality; in the comparable regime (`k < n_rel`) it is a small RESOLVED HARM for overview.** §I105's verdict SURVIVES a wider pool.

**The question** (the owner's, after §I105). §I105 swept k at the endpoint but the cross-encoder's ranking was available only to **k=50** (T4 kept ≤50), and the pool was capped at 100. Does **widening the pool cap** and sweeping k higher change the picture — per query type, on the last layer?

**Two parts.**
* **POOL arm — READ-ONLY.** `wide_pool_k_sweep.py` → `wide_pool_k_sweep.json`, from `fusion_attribution.json` (`C_pages` = pool order at cap 100; `W500_pages` = pool order at cap 500, 268–389 pages/query). Verifier **11/11**; mutation **11/11 reddened, NO inert check**.
* **CE arm — A RUN.** `wide_ce_endpoint.py` → `wide_ce_endpoint.json` (**133 queries, 0 errors, 0 reranker fallbacks, reachable 888 == T0, wall 401 s**, one arm, `mmr_candidates`/`reranker_fetch_k`/`reranker_top_k` all 100→500). It records the CE's **FULL** ordered page list (kept 268–389 of the pool). Sweep `wide_ce_k_sweep.py` → `wide_ce_k_sweep.json`. Verifier **11/11**; mutation **11/11 reddened, NO inert check**.

**Pre-registrations** `.hermes/plans/2026-11-01-p1-wide-pool-k-sweep-preregistration.md` and `...-wide-ce-endpoint-preregistration.md`. **Read-only. No collection write, no re-ingest, no `src/` change.**

**1. ✅ THE POOL ARM — widening the cap does NOT change the pool's top-50.** POOL100 and POOL500 are near-identical for k ≤ 50 (overview R@20 **0.210 vs 0.208**). The wide cap **appends** candidates; it does not reorder the top. So "wider k" only bites **beyond k=50** — the range §I105 could not reach. Recall keeps rising to k=250 (POOL500 overview **0.208 → 0.724**).

**2. ✅ THE CE ARM over the wide pool — recall rises hard, per type:**

| k | 20 | 50 | 100 | 150 | 200 | 250 |
|---|---|---|---|---|---|---|
| factual R@k | 0.583 | 0.703 | 0.799 | 0.840 | 0.870 | **0.902** |
| **overview R@k** | **0.164** | 0.315 | 0.493 | 0.620 | 0.713 | **0.768** |
| multihop R@k | 0.542 | 0.605 | 0.666 | 0.694 | 0.740 | **0.756** |

**3. ⚠️ THE RANKED QUALITY DOES NOT IMPROVE — in the comparable regime it is a RESOLVED HARM.** `nDCG@k` dips then rises (overview 0.474 @20 → 0.448 @40 → 0.637 @250), **but the rise begins at k ≈ n_rel** (`n_rel` mean: overview **73.8**, factual 9.5, multihop 4.3): past it `IDCG(n_rel,k)` **saturates** while the DCG numerator grows, so `nDCG@k` rises **BY CONSTRUCTION** — the mirror of §I102's artifact. In the comparable block (**k < n_rel**), paired vs k=20:

| type | k | n | ΔnDCG | 95 % CI | verdict |
|---|---|---|---|---|---|
| **overview** | 30 | 35 | **−0.0270** | [−0.0434, −0.0111] | **RESOLVED NEG** |
| **overview** | 40 | 27 | **−0.0285** | [−0.0509, −0.0069] | **RESOLVED NEG** |
| overview | 50 | 22 | −0.0227 | [−0.0506, +0.0049] | unresolved |
| **overview** | 100 | 9 | **−0.0413** | [−0.0827, −0.0024] | **RESOLVED NEG** |
| factual | 30 | 3 | −0.0771 | [−0.1347, −0.0058] | RESOLVED NEG |
| multihop | ≥30 | 0 | — | — | no comparable query |

⇒ **The falsification clause did NOT fire** (overview never resolves POSITIVE). **§I105's verdict survives a wider pool: wider k buys recall/coverage, not ranked quality.**

**4. ✅ PREDICTIONS, scored.** **P1** (R/cov monotone, largest for overview) **CONFIRMED**. **P2** (nDCG flat/negative in the comparable regime) **CONFIRMED** (item 3). **P3** (CE@20 ≈ §I105) **CONFIRMED** (anchor; reachable 888 == T0). ⚠️ **§I105's capture prediction was FALSIFIED** — capture rose MORE on the wider pool (overview 0.583 → 0.754), because the same denominator saturation drives it; recorded as a miss, not buried.

**5. ⇒ THE VERDICT.** **Wider k, with or without a wider pool, is a CONTEXT-BUDGET knob.** It raises recall and coverage (real, monotone, most for overview) and cannot raise ranked quality. ⚠️ **The only reading under which "wider k for overview" pays is the generator stage — still unmeasured.** ⚠️ **This does NOT re-open the pool → top-20 ranking loss (§I99 `waste_order`).**

**6. ⚠️ BOUNDS.** One corpus, one document, one funnel. n=40 per non-factual type; the comparable block thins fast (overview n=9 at k=100, n=1 at k=250). The CE list is capped at the pool size (~300), so k>~300 is not reachable without a still-wider cap. **Read-only: nothing written to any collection, no re-ingest.**

**7. ⚠️ AN ENVIRONMENT NOTE.** The run harness exits with a `libc++abi: ... recursive_mutex lock failed` **teardown-time** abort AFTER the artifact is written (a Qdrant-client shutdown race). It does not affect the artifact; check the JSON, not the exit code.

#### I107. ✅ THE VISUAL-LANE VALIDATION RAN (read-only) — ⚠️ **THE COLPALI APERTURE CANNOT SEPARATE IN-DOMAIN FROM NEAR-DOMAIN.** A near-domain image (H 2p orbital, top-1 cosine **0.5609**) **outscores the weakest in-domain concept** (oscillator, **0.4936**); the score floor is high (noise **0.4578**, a brand logo **0.4355**); **no separating threshold exists**. V1 PASSES (12/12 real page images) but **at cos 1.0000 — a self-match signature, not proof of cross-render generalisation.** The lane still has **NO labelled retrieval metric**.

**The question.** The ColPali visual lane was populated for the CURRENT doc this session (968 page vectors for `7ba61432`; 1,033 for the old doc). Does its similarity score **separate** "this image is from my book" from "this image merely looks like physics"? And is there an **aperture** (a top-1 cosine threshold τ) that accepts in-domain and rejects near/far?

**What ran — nothing written, read-only.** `logs/p1/step10/visual_lane_validation.py` → `visual_lane_validation.json`. Query images: 12 REAL page images (`data/page_images/b2d9fb56-…/page_NNNN.png`) + 8 SYNTHETIC in-domain concept figures + 4 near-domain + 5 far-domain. Each is embedded with ColPali (`embed_query_image`) and searched against `visual_knowledge_base` (top-5, τ=0.0). The in-concept "gold" is the **TEXT lane's top-5 for a description — a PROXY, not hand-verified ground truth**; the near/far labels are our judgement. Both stated in the artifact's provenance block.

**The three-way split and the aperture sweep.** Split the query images into in / near / far domains; sweep τ ∈ {0.0, 0.3 … 0.9}; a τ "separates" iff in-domain acceptance = 1.0 AND near = 0.0.

| group | n | top-1 cosine | note |
|---|---|---|---|
| **in_book_page** | 12 | **1.0000** (all) | page N image → page N, 12/12 MATCH |
| **in_concept** (synthetic) | 8 | 0.4936 – 0.5852 | mean overlap with the text proxy **0.1063** |
| **near_domain** | 4 | 0.4325 – **0.5609** | H 2p orbital is the top scorer |
| **far_domain** | 5 | 0.4019 – 0.4920 | noise 0.4578, logo 0.4355 |

Aperture sweep (acceptance rate per domain): at τ = 0.45 near is still 0.75; at τ = 0.55 in_concept drops to 0.25 while near is 0.50; **at τ = 0.60 in_concept = 0.00 and near = 0.00** — i.e. the only τ that rejects near also rejects every synthetic in-domain concept. **`separating: NONE`.**

**The checks:** ✅ **V1** in-book self-page match ≥ 80% (**12/12, PASS**). ❌ **V2** in-concept mean overlap ≥ 0.4 (**0.1063, FAIL**). ❌ **V3** in-domain top-1 min > near-domain top-1 max (**0.4936 vs 0.5609, gap −0.0673, FAIL**). Exit code 1 = the two failing checks, as registered.

**⇒ THE VERDICT.** **The aperture is NOT usable to gate the visual lane.** The score has a **high floor** (a random-noise image scores 0.4578; a brand logo 0.4355) and a **physics-looking-but-absent** image outscores a genuine in-domain one — so no similarity threshold can decide "is this from my book". A cross-modal **agreement** measure (V2) is also low (0.106). ⚠️ **The visual lane therefore has neither a labelled retrieval metric NOR a usable confidence gate** — it can be shown, but not trusted, and not scored.

**⚠️ A CAVEAT ON V1, not hidden.** V1 passes at **cos 1.0000 on all 12** page images. That is the signature of an **exact self-match**; the docstring claims a genuine **cross-render** test (old Docling renders vs new PyMuPDF@150dpi). **Whether the query images are the ones stored (a self-match) or a true cross-render match is NOT established here** — it needs one check (compare the query file to the stored page's image / vector). Until then V1 should be read as "the lane finds an image it has", not "the lane generalises across renders".

**⚠️ BOUNDS.** The concept images are **synthetic matplotlib figures**, not photographs or real diagrams — easier than real images, so the in-domain scores are an **upper** bound. The in-concept gold is a **proxy**. n is tiny (12/8/4/5). **Read-only: no collection write, no re-ingest.** **Register against:** §I89 (the visual lane declared unmeasurable), §I90/§I94 (the visual-collection state), and the demo deck's "visual lane is populated but not measurable" line.

**▶ WHAT THIS UNBLOCKS / RULES OUT.** (a) **Rules out** a similarity-gated visual lane (the aperture is a fiction on this data). (b) **The only route to a real visual measure is LABELS** — the 33 `vis-*` queries need `relevant_pages`, after which `compute_retrieval_metrics` scores the lane like any other. (c) The V1 self-match question is a **one-check** open item.

---

#### I108. ✅ THE GENERATOR EVAL RAN (`v3_judged_full`, 200 queries) — **the "generator unmeasured" gap is CLOSED.** A **cross-family** judge (generator `openai/gpt-oss-20b`, judge `Qwen/Qwen3-VL-8B-Instruct`) scored per-type **faithfulness** and **answer_relevance** for the first time.

**The question.** Every retrieval number in the register is a *retrieval* number. Nothing had ever measured whether the **generated answer** is grounded in the retrieved context (faithfulness) or answers the question (answer_relevance). This closes that gap.

**What ran.** `scripts/evaluate_rag.py --query-file data/eval_queries_v2.json --skip-visual --judge-model Qwen/Qwen3-VL-8B-Instruct --run-name v3_judged_full`. Artifacts `data/eval_results/v3_judged_full_2026-11-03_0115.{json,md}` (finished 2026-11-02 17:15 local). ⚠️ **The judge MUST be cross-family** — `config.yaml`'s default `judge_model` is `gpt-oss-20b`, the **same family as the generator**, which the code itself warns is "indistinguishable from a genuinely faithful answer". The run overrode it.

**Run integrity.** Synthesis succeeded **167/200**; faithfulness computed **166/200**; **5,057 judge calls, 0 failed**. Retrieval metrics are over the **133** labelled queries; the judged metrics over the 200.

| Scope | R@100 | R@20 | Hit@20 | Ctx.Prec | MRR | NDCG@20 | **Faithful** | **Ans.Rel** | Citation | n |
|---|---|---|---|---|---|---|---|---|---|---|
| Overall | 0.679 | 0.458 | 0.940 | 0.244 | 0.765 | 0.555 | **0.636** | **0.857** | 1.000 | 133/133 |
| factual | 0.827 | 0.590 | 0.924 | 0.131 | 0.784 | 0.593 | **0.683** | **0.855** | 1.000 | 53/53 |
| multihop | 0.647 | 0.550 | 0.900 | 0.105 | 0.665 | 0.507 | **0.702** | **0.742** | 1.000 | 40/40 |
| overview | 0.516 | 0.192 | 1.000 | 0.534 | 0.841 | 0.554 | **0.510** | **0.975** | 1.000 | 40/40 |

**Abstention** (negatives): **22/34 = 0.647** — a negative is handled correctly when the system declines.

**⇒ THE READING.** Citation accuracy is **1.000** across every type — when the generator cites, it cites a retrieved page. But **faithfulness is moderate (0.636)** and it tracks the retrieval weakness: **overview is lowest (0.510)** — the same type with the worst R@20 (0.192) — while **multihop is highest (0.702)**. **answer_relevance is high everywhere (0.857)** and *inverted* on overview (**0.975**): the system answers overview questions well but grounds them least — consistent with §I101's finding that overview is broad-label and ranker-limited. ⚠️ **This is a JUDGE score on a 200-query single run** — no independent verifier or mutation proof was run against it; treat it as a first measurement, not a certified one. **Register against:** §I97/T4 (the generator was the last unmeasured stage), §I101 (overview ranker-limited), and the demo runbook.

---

#### I109. ⚠️ T3 RAN — the lane-complete v2-vs-v3 A/B — **BUT ITS ANCHOR GUARD (G8) FAILED, so per its own pre-registration §8 "the run reports nothing".** ⚠️ **DIAGNOSED: G8's ANCHOR IS STALE, not the harness** — §I85's rows predate **two** documented changes.

**What ran.** `logs/p1/step10/t3_lane_complete.py` (six arms: `A_off`/`A_on`×2 / `B_off`/`B_on`×2), 133 queries, **0 errors**, HyDE frozen (93 served), read-only. Artifact `logs/p1/step10/t3_lane_complete.json` sha256 `f7153581657092d8…`; wall `A_off` 153.9 s · `B_off` 152.4 s · `A_on` 243.4/252.8 s · `B_on` 206.1/220.3 s.

**The result it self-reports** (⚠️ **not readable — see below**). **P1 cR@20 (B_on − A_on) = +0.01037**, CI **[+0.00077, +0.01998]**, RESOLVED, **28W/10L/95T**; P2 raw R@20 +0.01014 (same). Per type: **overview +0.0194 RESOLVED** (23W/6L), multihop +0.0242 unresolved, factual −0.0069 unresolved. **Lane deltas:** `A_on − A_off` **−0.0181 RESOLVED NEGATIVE** (adding DA+graph **hurt** arm A at the endpoint); `B_on − B_off` −0.0034 unresolved. Power: `sd_d` 0.0565 → floor 0.00961.

**Guards.** G1, G1b, G2 (reachable **888**), G3 (0 errors), G4 (0 fallbacks), **G5 (arm A's DA lane live 133/133 in BOTH arms — §A holds inside the full funnel)**, G6 (graph live 40/40), G7 (HyDE frozen), G10 (both `_on` arms bit-exact across reps), G_divisor — **all PASS**. **G8 FAILS.**

**⚠️ THE DIAGNOSIS (the substance).** G8 requires the `_off` arms to reproduce §I85's arm rows within ±0.020. Measured gaps:

| arm | R@20 | R@100 | Hit@20 | MRR | NDCG@20 |
|---|---|---|---|---|---|
| **A** off vs §I85 | +0.0163 | **0.0** | +0.0226 | **0.0** | +0.0539 |
| **B** off vs §I85 | +0.0133 | +0.0164 | +0.0226 | +0.0531 | +0.0568 |

Two **documented, post-§I85** changes explain every gap — the anchor target is a configuration that **no longer exists**:

1. **The per-type rerank-query policy (§I97/T4) shipped** in `e0f1616` (2026-11-01): `evaluate_rag.py`'s `rerank_query` changed from `hyp` to **`hyp if query_type == "overview" else query_text`**. **Evidence:** arm A's **pool is bit-identical to §I85** (`pool_size`, `recall@100`, `mrr` identical on **133/133**) yet its reranked **top-20 differs on exactly 39/53 FACTUAL queries — and 0/40 overview, 0/40 multihop**. That per-type confinement is the policy's signature (overview keeps the hypothetical; multihop never used HyDE). ⚠️ **Not** cross-encoder nondeterminism: `A_on` r1 == r2 bit-exact (G10).
2. **v3 was re-embedded POOLED** (session 21, §I89), **after** Stage F measured it late-chunked. **Evidence:** arm B's **pool differs on 133/133** (`pool_size` 65→75 etc.) while **arm A's pool is bit-identical** — same code path, so B's pool change can only come from **its index**.

⇒ ⚠️ **G9's claim ("the ONLY difference from §I85 is §A's code") was WRONG**: **three** things changed — the rerank-query policy, the v3 index, and §A. **G8 was mis-specified as a single-variable anchor.**

**⇒ THE VERDICT.** Per the pre-registration's own rule ("**If G8 fails … fix before reading anything; the run reports nothing**"), **T3's `ships=True` is NOT readable off this run as-is.** The `B_on − A_on` comparison is *internally* valid (both arms on the same current code+index), but the anchor's job — proving the instrument is §I85's — is now impossible, because the instrument legitimately evolved. **Resolution needs an owner decision:** either **re-register the anchor against the current `_off` configuration** (treat T3's off arms as the new reference, D6.1) or re-run with a corrected anchor. ⚠️ **T3 also has NO independent verifier and NO mutation proof** — prereg §7 required `t3_verifier.py` + `t3_mutation.py`; **neither exists** (the session ended mid-flight). **Register against:** §I85 (the base-lane null this completes), §I89 (the pooled re-embed + the defect §A fixed), §I97/T4 (the rerank-query policy), §I98 (DA null / graph content harm), §I104/§A.

---

#### I110. ✅ THE OVERVIEW k=50 GENERATOR RUN — **WIDER k DOES NOT IMPROVE THE OVERVIEW ANSWER.** §I105/§I106's open reading ("the only reading under which wider k pays is the generator, still unmeasured") is now **CLOSED NEGATIVE**.

**The question.** §I105/§I106 showed wider k buys overview **recall/coverage** but not ranked quality, and both end on the same sentence: the generator stage was unmeasured. It is now measured (§I108) — but at the product's **k=20**. Does raising the cut to **k=50** improve overview's **faithfulness** (the lowest of the three types, 0.5097 at k=20)?

**What ran.** `.venv/bin/python scripts/evaluate_rag.py --query-file data/eval_queries_overview.json --skip-visual --judge-model Qwen/Qwen3-VL-8B-Instruct --run-name overview_k50`, with `RERANKER_TOP_K=50` (fetch_k/mrr_candidates unchanged at 100 — the CUT is widened, not the pool). Pre-registration `.hermes/plans/2026-11-02-p1-overview-k50-generator-preregistration.md`, **committed ALONE as `d297da4`** (D6.1). Artifact `data/eval_results/overview_k50_2026-11-03_0744.{json,md}`. 40 overview queries; **synthesis 33/40**, faithfulness computed 33/40, **2,261 judge calls, 0 failed**; read-only.

**THE RESULT — paired vs k=20 (`v3_judged_full`), n=33:**

| metric | k=20 | k=50 | Δ | 95 % CI | verdict |
|---|---|---|---|---|---|
| **faithfulness** | 0.5278 | 0.4773 | **−0.0505** | [−0.1373, +0.0362] | **UNRESOLVED** (11W/15L) |
| answer_relevance | 0.9798 | 1.0000 | +0.0202 | [−0.0074, +0.0478] | unresolved |
| citation_accuracy | 1.0000 | 1.0000 | 0.0000 | — | — |
| context_precision | 0.5515 | 0.4429 | **−0.1085** | [−0.1430, −0.0741] | **RESOLVED NEGATIVE** |

**⇒ THE VERDICT.** Faithfulness is **unresolved, and the point estimate leans NEGATIVE (−0.05)** — more context did not improve grounding, and it **measurably diluted context precision**. Per the pre-registered falsification clause, **"wider k for overview" is closed: it is a context-budget knob with no answer-side benefit.** ⚠️ **Caveats, stated:** a judge score on a single run (no independent verifier on a judge score, §I108's own caveat); n=33 (1 query produced no answer, 6 had no baseline faithfulness); the judge saw a larger context at k=50, so the comparison is not context-blind. **Register against:** §I105, §I106 (the recall-only verdicts this closes), §I108 (the generator baseline), §I102 (the cut cannot move the top-20).

---

#### I111. ✅ THE POOL-ORDER ATTRIBUTION (read-only) — **THE ORDERING LOSS IS NOT THE FUSION; THE GOLD IS IN THE POOL BUT RANKED 21–100.** The RRF fusion orders the gold **no worse than its strongest single lane** (dense-only). ⇒ the remaining lever is the **lanes' own scoring**, not the fusion.

**The question.** §I99 located the endpoint loss in the pool's own ORDER (`waste_order` 0.179 overall / 0.165 overview) and priced the cross-encoder at 0.005. §I100 (§I100), §I103 and §I106 ruled out the fusion's knobs. **Is the order loss caused by the FUSION, or by the lanes it fuses?**

**What ran — read-only, nothing written.** `logs/p1/step10/pool_order_attribution.py` over `fusion_attribution.json` (133 queries; `C_pages` = the product pool order at cap 100, `D100_pages` = dense-only pool, `W500_pages` = cap 500).

| type | n | cov(pool) | oracle@20 | **FUSED@20** | dense-only@20 | W500@20 | fused−oracle |
|---|---|---|---|---|---|---|---|
| factual | 53 | 0.811 | 0.8052 | **0.5830** | 0.5291 | 0.5922 | 0.2222 |
| **overview** | 40 | 0.508 | 0.3755 | **0.2103** | 0.2128 | 0.2078 | **0.1652** |
| multihop | 40 | 0.647 | 0.6466 | **0.5106** | 0.5058 | 0.5227 | 0.1360 |
| all 133 | 133 | 0.671 | 0.6283 | **0.4491** | 0.4270 | 0.4557 | 0.1791 |

**Rank distribution of gold in the FUSED pool order (all queries):** ranks 1–20 **39.5 %** · 21–50 **29.6 %** · 51–100 **30.9 %** · 101+ 0 %.

**1. ✅ THE FUSION IS NOT THE CULPRIT.** Paired **FUSED@20 − dense-only@20**: **factual +0.0539**, **overview −0.0025**, **multihop +0.0048**, **all +0.0222** — **every one UNRESOLVED**. The fused order is at worst equal to its strongest single lane. For **overview** the two are the same to 3 dp (0.2103 vs 0.2128): **overview's order IS the dense lane's order** — the sparse and ColBERT lanes neither help nor hurt it.

**2. ✅ THE CAP APPENDS, IT DOES NOT REORDER** — W500@20 ≈ FUSED@20 on every type (all: 0.4557 vs 0.4491), reproducing §I92 at the page level.

**3. ⚠️ THE LOSS IS IN THE LANES' SCORING.** The pool **covers** 67 % of the gold overall (overview 50.8 %, factual 81.1 %) — but only **39.5 %** of the gold it holds lands in the top-20; **60.5 % sits at ranks 21–100**. Since the fusion is not worse than its lanes and the cap does not reorder, the gold is ranked low **by the lanes themselves**. ⇒ **the fix must change how the lanes SCORE these pages (query representation / embedder / reranker), not the fusion.**

**4. ⚠️ THE CEILING IS ARITHMETIC, NOT RETRIEVAL (the R-ceil question).** `R-ceil@20` for overview is **exactly `20 × mean(1/n_rel) = 20 × 0.0200 = 0.3992`** — the label sets are broad (min 22 / median 56.5 / mean 73.8 / max 314; **no** query has `n_rel < 20`). So a median overview query cannot exceed 20/56.5 ≈ 0.35 recall@20 **whatever the retriever does**. The ceiling rises only with k or with narrower labels. ⚠️ **Two ceilings exist and differ at k=50** — the **label** ceiling `min(k,n_rel)/n_rel` (0.755 at k=50) vs the **reachability-adjusted** one (0.680) — quoting one without naming it is the §I99/§I105 trap.

**⇒ NEXT LEVER (the attribution's payoff).** The levers still open, in cost order: (a) a **reranker that reorders better** — but priced at `waste_ce` 0.022 for overview; (b) a **CE score-prior/blend** so the CE cannot demote a strong-pool page (untried, cheap); (c) a **stronger/other cross-encoder** (untried); (d) the **RAPTOR lane re-placed as an append** for overview (its dedicated lane is off the eval path and displaces when fused, §I98); (e) a **better retrieval signal** for overview queries — the only class of fix the attribution leaves standing. **Register against:** §I99 (the decomposition this explains), §I100/§I103/§I106 (the fusion knobs this rules out), §I105 (the ceiling), §I108/§I110 (the generator).

#### I112. ✅ THE OVERVIEW RETRIEVAL-SIGNAL PROBE — **THE QUERY-SIDE LEVER IS CLOSED: a different query REPRESENTATION does NOT rank the overview gold higher.** §I111's reading (a "better retrieval SIGNAL" is the only class left standing) is tested on the cheap half — the QUERY side — and returns **NULL**. ⇒ the remaining signal lever is the **DOCUMENT side** (embedder / re-ingest / fine-tune).

**The question.** §I111 showed the fused order == dense-only for overview and 60.5 % of the pooled gold sits at ranks 21–100 ⇒ the gold is ranked low **by the lanes' own scoring**. **Does a different QUERY REPRESENTATION make the dense lane rank it higher?** Read-only, dense lane alone, 40 overview queries, `knowledge_base_v3` (nomic-768, pooled), index and lane config held fixed.

**Pre-registration** `.hermes/plans/2026-11-04-p1-overview-signal-probe-preregistration.md` (committed ALONE, `f93b9e6`). Artifact `logs/p1/step10/overview_signal_probe.json` (sha256 `a72d5256…`), hypotheses cache `overview_signal_hypotheses.json`, run log, verifier + mutation proof. **40 queries, 0 errors. ALL SEVEN GUARDS PASS.**

**Arms** (dense lane, top-100 recorded): **A** the shipped single HyDE hypothetical · **B** the raw query (a known-worse control) · **C** multi-hypothetical **max** over N=5 · **D** multi-hypothetical **mean** over N=5.

| arm | R@20 | nDCG@20 | mean gold rank |
|---|---|---|---|
| A single HyDE hypothetical | **0.2128** | 0.6304 | **27.92** |
| B raw query | 0.1489 | 0.4691 | 30.32 |
| C multi-hyp max (N=5) | 0.2150 | 0.6345 | 35.50 |
| D multi-hyp mean (N=5) | 0.2140 | 0.6364 | 35.85 |

**Paired vs A (95 % CI, n=40):**
* **C − A R@20: +0.0021, CI [−0.0081, +0.0123], UNRESOLVED** (12W/13L).
* **D − A R@20: +0.0012, CI [−0.0070, +0.0094], UNRESOLVED** (14W/13L).
* C − A nDCG: +0.0041, CI [−0.0200, +0.0282], UNRESOLVED · D − A nDCG: +0.0060, CI [−0.0132, +0.0252], UNRESOLVED.
* **B − A R@20: −0.0639, CI [−0.0861, −0.0417], RESOLVED NEGATIVE** (3W/34L) — the control: the HyDE hypothetical IS the better overview query (§I97/T4 confirmed at the dense lane).

**1. ✅ THE RESULT — NULL.** Neither multi-hypothetical max (C) nor mean (D) resolves on R@20 or nDCG@20. Worse, their **mean gold rank is HIGHER** than A's (35.5/35.9 vs 27.9): the 5-hypothetical union **dilutes** — it pulls marginally more gold into the top-20 (R@20 +0.002, noise) while pushing the gold it holds **deeper** on average. ⇒ **no query representation tested beats the shipped single hypothetical.**

**2. ✅ THE ANCHOR HELD.** Arm A reproduces §I111's dense-only R@20 for overview (0.2128) to the digit (G4) — the probe is the same instrument.

**3. ⚠️ THE FIRST RUN WAS VOID — G4 CAUGHT A HARNESS DEDUP DEFECT (recorded, not hidden).** The first full run reported **C/D RESOLVED POSITIVE +0.027/+0.026** and failed **G4** (arm A 0.1878 vs 0.2128). Root cause: `_dense_lane` kept the raw `store.search` chunk hits — **several chunks per page, no page dedup** — while §I111's reference arm (`fusion_attribution._pages_of`) dedups by page; the ~27 duplicate pages/query ate top-20 slots. Deduping the recorded arm A gives **0.2128** and arm B **0.1489** = `D100_raw` exactly. **⇒ the as-run "POSITIVE" was an artifact of the missing dedup.** Fixed (`_dense_lane` now dedups by page, order-preserving), pre-registration addendum §9 written, void artifacts preserved (`overview_signal_probe_VOID_run1.json`), re-run clean. **Both** the harness guard **G4** and the independent verifier's **V10** redden on the void artifact — the verification stack caught it twice.

**4. ⚠️ FALSIFICATION CLAUSE TRIGGERED (pre-reg §4).** Neither C nor D resolves positive ⇒ **the QUERY-side half of the "better retrieval signal" class is CLOSED**; the remaining lever is the **DOCUMENT side** (embedder change / re-ingest / fine-tune, §I85/§I87's caveat attached). ⚠️ Bounds: one corpus, one document, n=40, N=5 a choice not a measurement (a null at N=5 does not exclude a larger N), and the probe measures the **dense lane**, not the endpoint (a dense-lane win would not imply an endpoint win — §I85).

**Register against:** §I111 (the attribution this tests the cheap half of), §I97/T4 (the per-type query policy the control confirms), §I105 (the ceiling — overview R@20 0.2128 sits far below R-ceil 0.3992), §I110 (the generator side, also null).

#### I113. ⚠️ RAPTOR AS GENERATOR CONTEXT — **A NULL (the summaries do NOT improve overview faithfulness: −0.032, unresolved), AND FLAGGED: G6 FAILS — the harness's arm-A system prompt is not the product's, so arm A does not reproduce the §I108 baseline.** 40 overview queries, 0 errors, wall 5,976 s. Verifier **24/24**, mutation **24/24 reddened (proof passes)**.

**The question.** §I98 showed the RAPTOR lane as a *ranked participant* hurts overview (a summary has no `page_number`, so it can only displace a page). This asks the untried variant: hand the summaries to the **GENERATOR** as extra context, never entering the ranked list. Pre-registration `.hermes/plans/2026-11-04-p1-raptor-generator-context-preregistration.md` (committed ALONE, `f93b9e6`). Artifact `logs/p1/step10/raptor_context.json` (sha256 `226b3769…`), run log, verifier + mutation proof. Read-only. Arms: **A** CE top-20 pages only · **B** the same pages + the top-2 RAPTOR summaries appended as a `[Summary]` block.

**The result — NULL, point estimate negative.** Paired **B − A**, n=40:

| metric | Δ (B − A) | 95 % CI | verdict | W/L |
|---|---|---|---|---|
| **faithfulness** | **−0.0320** | [−0.1009, +0.0368] | **UNRESOLVED** | 13/17 |
| answer_relevance | 0.0000 | [0, 0] | unresolved | 0/0 |
| citation_accuracy | 0.0000 | [0, 0] | unresolved | 0/0 |

Aggregate faithfulness: **A 0.4551 · B 0.4229**. ⇒ **giving the generator chapter-level summaries does not help, and if anything costs** — the point estimate is negative, and answer_relevance / citation are bit-identical (the summaries change no answer's relevance or citations).

**⚠️ G6 FAILS — the anchor caught a harness defect (recorded, not hidden).** G6 required arm A to reproduce the §I108 overview baseline (**0.5097**, n=40); arm A came out **0.4551**, gap **−0.0546** > the ±0.030 tolerance. **Diagnosed by source-read: the harness's arm-A SYSTEM prompt differs from the product's.** The harness uses `"You are a physics tutor. Answer the student's question using ONLY the material provided. Cite the page number for each fact as [Page N]…"` while the product's `synthesize` uses `_SYNTH_SYSTEM` (the 5-rule block, incl. *"If the passages are irrelevant, say so in one sentence and stop."* — `evaluate_rag.py:472`). **⇒ arm A is NOT the product path**, so the anchor's job — prove the reuse is exact — fails, exactly as it should. ⚠️ A **second** plausible contributor: the generator **samples** (`call_llm` has no temperature knob, §I108's own caveat), so a single run need not reproduce another to ±0.03.

**⇒ VERDICT: FLAGGED, not a clean result** (the T3/§I109 precedent). The paired delta is *internally* valid (both arms share the harness prompt — only the summaries differ), so it measures the RAPTOR-context effect **for this prompt**; but because arm A is not the product's, the absolute level does not transfer. **Needs an owner decision:** (a) align the harness's system prompt to `_SYNTH_SYSTEM` and re-run (the anchor then becomes a real reuse test), or (b) record the delta as prompt-conditional and do not generalise it. ⚠️ **Do NOT quote the absolute A/B faithfulness as the product's.**

**Register against:** §I98 (the lane as a ranked participant — the harm this variant was meant to avoid), §I108 (the generator baseline the anchor references), §I110 (the k=50 generator null), §I112 (the query-side null).

#### I115. ⚠️ THE CITATION METRIC IS VACUOUS — **`citation_accuracy` reads 1.000 in every report because its regex matches ZERO citations in the entire run.** The generator emits `Page` + a **narrow no-break space (U+202F)** or a CJK bracket `【Page N】`; the metric wants a literal `[Page <ascii-space>N]`. **Read-only, over `v3_judged_full`; no cluster.**

**The mechanism.** `evaluate_rag.compute_citation_accuracy` (`:669`) matches `r"\[Page (\d+)\]"` — a **literal ASCII space** between `Page` and the number. The generator (`openai/gpt-oss-20b`) emits **`Page\u202f<N>` (545×)** or **`Page\u00a0<N>` (41×)** or a **CJK bracket `【Page N】`**. So the regex finds **no citation in any of the 166 answers**, and the function's own rule — `if not cited: return 1.0  # no citations — not penalised` — returns **1.0 for every answer**. ⇒ **the reported citation_accuracy 1.000 is 100 % artifact** (it appears in §I108, the deck, and every prior report).

**The real citation behaviour, re-derived (the fixed parser, all three forms):**

| quantity | value |
|---|---|
| answers citing **nothing** at all | **53 / 166 (32 %)** |
| answers citing in **any** form | **113 / 166 (68 %)** — `[Page N]` / `【Page N】` 94, `(page N)` 19 |
| corrected citation **validity** (cited ∩ retrieved / cited) | **0.6463** (n=113) |
| **answer-cites-gold recall** (end-to-end) | **0.2018** |

Artifact `logs/p1/step10/citation_fix.json` (harness `citation_fix_recheck.py`, verifier `citation_fix_verifier.py` **14/14**, mutation `citation_fix_mutation.py` **14/14 reddened, no inert**; **independent cross-family reviewer** `openai/gpt-oss-20b`, read-only, deleg `deleg_9aae2d81`: **C1–C7 ALL CONFIRMED**).

**⚠️ It propagates to the UI.** Both frontends' `_cited_pages` use `r'(?:\[Page\s*|\(page\s*)(\d+)'` — it handles the narrow space but **not the CJK bracket**, so for the 38 CJK-cited answers the apps find no citation and fall back to **"Sources retrieved" (all pages)** instead of the cited set (`streamlit_app.py:749`, `nicegui_app.py:134`). ⇒ **the metric AND the source panel are both blind to the same 23 % of answers.**

**⇒ VERDICT / FIX.** (a) **Standardise the citation format in the synthesis prompt** (one bracket, one space) — **still open** (a generator change, needs its own measured run); or (b) **fix the three parsers** to accept both brackets and any Unicode space. **✅ (b) APPLIED 2026-11-05:** `compute_citation_accuracy`/`compute_citation_coverage` in `evaluate_rag.py` (now returns **None**, not 1.0, when uncited, + a `Cit.Cov.` column in both report tables) and `_cited_pages` in **both** frontends — tests `test_eval_metrics.py` (6) + `test_frontend_math.py` (1). ⚠️ **Do NOT quote citation_accuracy 1.000** — the number is now None-over-uncited. **Register against:** §I108 (the report carrying the false 1.000), the demo deck (same), §I82 (the router agreement cited below).

#### I116. ⚠️ THE EVAL BYPASSES THE INTENT ROUTER — **the product routes with a classifier that agrees with the gold labels only 0.5714 of the time, but every metric is computed on the GOLD `query_type`.** ⇒ the measured retrieval is an **oracle-routing** upper bound, not the product's. **Source-read; no run.**

**The mechanism.** `evaluate_rag.evaluate_query` (`:817`) sets `query_type = query.get("query_type", "factual")` — the **gold label**. Both frontends instead call `get_intent_router(cfg).classify(q_vec)` (`streamlit_app.py:541`, `nicegui_app.py:190`) and gate **three** things on it: **HyDE** (`intent in ("factual","overview")`), **lane selection** (`also_raptor`/`also_graph`), and the **rerank query** (`hyp if intent == "overview" else query`). The router's agreement with the gold labels is **0.5714** (D6.5 / §I82) — so on ~43 % of queries the product fires the **wrong HyDE gate, the wrong lanes, and the wrong CE query**. §I97 measured the CE-query mis-set at **factual nDCG −0.136** — the largest single lever in the programme — and that harm is **invisible to every artifact** because the eval never mis-routes. ⇒ **a real, unmeasured end-to-end leak at the front of the pipeline.** **Fix/measure:** add a router-in-the-loop arm (feed `classify()` instead of the gold label) and report the delta; or improve the router. **Register against:** §I82 (the retrain), §I97 (the rerank-query policy the router gates), the guardrails plan (G1's `out_of_scope` would touch the same classifier).

#### I117. ⚠️ THE CLUSTER'S EMBEDDER MODELS MOVED — AND THE REPO'S UPGRADE FIELDS ARE **DEAD CONFIG**. The cluster's **ColBERT** list now offers **only** `lightonai/GTE-ModernColBERT-v1`; the repo's `colbert-ir/colbertv2.0` is **no longer listed** (though the **custom-model override still serves it** — POST 200). The **sparse** list offers `Qdrant/bm42-all-minilm-l6-v2-attentions`, `Qdrant/bm25`, `prithivida/Splade_PP_en_v1` (default). ⚠️ `config.py` **DECLARES** `sv_colbert_model = "lightonai/GTE-ModernColBERT-v1"` (`:126`) and `sv_sparse_model = "Qdrant/bm42-all-minilm-l6-v2-attentions"` (`:127`) — §I1's upgrades — **but NOTHING READS THEM** (`grep` finds them only in `config.py`). The embedders send `cfg.colbert_model` / `cfg.splade_model` to the cluster, so the upgrade is **declared but unwired**.

**Live probe 2026-11-05 (10.0.10.70:8123), read-only:**

| lane | model | POST | note |
|---|---|---|---|
| ColBERT | `lightonai/GTE-ModernColBERT-v1` | **200**, dim **128** | cold-load 10.5 s |
| ColBERT | `colbert-ir/colbertv2.0` (repo) | **200**, dim **128** | 0.12 s — the override works |
| sparse | `prithivida/Splade_PP_en_v1` / `Qdrant/bm25` / `Qdrant/bm42-…` | **timeout (≥30 s)** | **service DOWN** |
| rerank | `BAAI/bge-reranker-v2-m3` | **timeout (≥30 s)** | **service DOWN** |

⚠️ **Both ColBERT models are 128-dim, so the `colbert` named vector is a schema drop-in** — but a **model change invalidates the stored lane vectors**, so any switch needs the lane **re-embedded** (3,796 chunks; `reembed_chunks.py` currently *carries* colbert+sparse over, it does not recompute them). **Expected metric benefit ≈ 0**: §I100's O2 (no ColBERT) was **−0.0012 nDCG, unresolved** — the lanes contribute ~nothing at the endpoint, so a switch buys **robustness/currency, not a number**. ⚠️ **The sparse + rerank outages block every retrieval run** (#2 and the demo). **Register against:** §I1 (the embedder-upgrade table), §I96 (a silently dropped lane), §I100 (the lanes' endpoint contribution).

#### I114. ✅ THE G1 PRE-FLIGHT DIAGNOSTIC — **THE INPUT GUARDRAIL CANNOT BE BUILT FROM THE CHEAP SIGNALS THE PLAN NAMES.** The **34 negatives are THREE different problems**, and a top-1 score floor is a **weak instrument** (AUC 0.774; to catch a third of the negatives it must refuse ~9 % of answerables). ⇒ **G1's scope must split** (off-domain → an input gate; in-domain-but-absent → the G2 grounding floor). **Read-only, no cluster, no store write.**

**The question.** The guardrails plan's **G1** proposes an input gate: refuse a query when it is out-of-scope (an `out_of_scope` intent) **or** the top retrieved score is below a floor. `HANDOFF` §34's item 4 calls the score floor "the cheaper path". **Before building it, does either cheap signal separate the 34 negatives from the answerables?**

**Method.** A **read-only re-derivation** over the product-config run already on disk — `data/eval_results/v3_judged_full_2026-11-03_0115.json` (sha256 `801adffc…`; `knowledge_base_v3` / nomic-768, DA+SPLADE+ColBERT+MMR+CE on, `score_threshold` 0.0), which covers **exactly** the labelled population. Per query the signal is the **recorded top-1 cross-encoder score** (`top_chunks[0].score`). Harness `logs/p1/step10/g1_negatives_diagnostic.py` → artifact `logs/p1/step10/g1_negatives_diagnostic.json`. **No run, no re-retrieval.**

**1. ⚠️ THE 34 NEGATIVES ARE THREE DIFFERENT PROBLEMS (by id prefix), and the score distributions overlap heavily.**

| subclass | n | what it is | example | score min / median / max |
|---|---|---|---|---|
| `neg-out` | 12 | **off-domain** — the corpus cannot address it | "What is the capital of France?" | 0.05 / 0.57 / 0.85 |
| `neg-in` | 12 | **in-domain physics the book does NOT cover** | "…the book's treatment of the Higgs boson" | 0.03 / 0.31 / 1.01 |
| `neg-nea` | 10 | **in-domain, the book lacks the specific value** | "…value the book gives for the mass of the proton" | 0.10 / 0.24 / 1.08 |

The **answerable** top-1 scores span 0.03–1.50 (median 1.00). The negative scores sit **inside** that range — `neg-in`/`neg-nea` reach 1.0–1.08, above the answerable median — so **no score floor cleanly separates them.**

**2. ⚠️ THE SCORE FLOOR IS A WEAK GATE — measured, not assumed.** AUC for `refuse if top-1 < τ` is **0.774** (moderate). The operating points (rule: the lowest τ meeting a false-refusal budget, then the recall it buys):

| false-refusal budget | τ | recall of negatives | precision | false-refusal rate |
|---|---|---|---|---|
| ≤ 5 % | 0.070 | **0.147** (5/34) | 0.500 | 0.038 |
| ≤ 10 % | 0.170 | **0.324** (11/34) | 0.478 | 0.090 |
| ≤ 15 % | 0.205 | **0.382** (13/34) | 0.419 | 0.135 |

Best F1 is **0.500** (τ 0.76: recall 0.853, but a **0.398 false-refusal rate** — it refuses **40 %** of legitimate questions). ⇒ **a bare score-floor gate would either miss two-thirds of the negatives or refuse 40 % of real questions.** Neither is shippable.

**3. ⚠️ AN OFF-TOPIC / DOMAIN SIGNAL CAN ONLY REACH 12/34 = 0.353.** The `out_of_scope` class (or any domain classifier) targets the `neg-out` subclass alone — the 22 `neg-in`/`neg-nea` queries are **in-domain physics** (the eval labels all 34 negatives `query_type=factual`); no input-side signal can know whether the *book* holds the answer without retrieving and judging the evidence. ⇒ **those 22 are the OUTPUT guardrail's (G2's grounding floor) job, not the input gate's.** Even an **oracle** domain detector OR-ed with the best score floor reaches only **30/34 = 0.882** recall — and only via that 0.40-false-refusal floor.

**4. ⚠️ THE GATE IS UNDEFINED FOR THE VISUAL ROUTE.** **33 of the 200 queries** (`vis-*`, the ColPali page lane) record **no chunk-level top-1** — a text score floor is undefined for them. Any gate must be defined **per route**.

**⇒ THE FINDING.** G1 as scoped (a cheap score-floor / `out_of_scope` input gate over the 34 negatives) **cannot be built from the cheap signals** — the label set is dominated by near-domain negatives that only a *grounding* judgment separates. **Proposed reorder (owner decision):** (a) **G1 narrows** to the **off-domain input gate** (12/34), which needs the router's `out_of_scope` — a **classifier RETRAIN** (D6.5 precedent), not a score floor; (b) the **22 in-domain negatives move to G2** (the grounding floor, which the plan already specs); (c) **do NOT ship a bare score floor** (F1 0.50 / FPR 0.40 measured). ⚠️ Bounds: one corpus, one document, the **CE top-1** signal only (a normalised dense-cosine or a margin signal is untested), and the scores come from a **single recorded run** (§I103 lane-tail nondeterminism attached).

**Register against:** the guardrails plan `.hermes/plans/2026-11-04-p1-guardrails-observability-SESSIONS.md` (G1/G2 rows), `ARCHITECTURE.md` §12 (the per-check precision/recall constraint this measures), §I108/§I110 (the generator this guardrail would sit behind), D6.5 (the retrain precedent).

#### I118. ✅ THE SPARSE LANE'S SILENT DROPOUT IS NOW COUNTED — **§I96's class is closed for the FOURTH lane, and it is the one DOWN on the cluster (2026-11-05).** Also: the cluster re-probe REPRODUCED the sparse + rerank outage (dense + ColBERT answer; sparse + rerank hang). **Cluster-free change; query-time only; no re-ingest.**

**The gap.** §I96 recorded that a retrieval LANE can drop out silently — its `except` omits the lane's `Prefetch`, so the RRF fusion runs over a **reduced lane set (a different pool)** with nothing outside the log text able to see it. Counters were added for **ColBERT** (`store.colbert_dropouts`, `e0f1616`), **DA** (`store.da_dropouts`), **RAPTOR** (`store.raptor_dropouts`) and **GRAPH** (`GraphBuilder.graph_dropouts`). The **SPLADE (sparse) lane was the one left uncounted**: its `except` in `_qdrant_search` only logged `"SPLADE encode failed (…), skipping sparse lane"`. ⚠️ **It is also the lane that is DOWN on the cluster right now**, so every run since the outage has been silently fusing **dense(+ColBERT) only** with no counter to show it.

**The fix.** `src/pdf_ingestion/store.py`: `DocumentStore.__init__` now initialises `self.sparse_dropouts: int = 0` and `self.last_sparse_dropout: str | None = None`; the sparse `except` increments both and appends `[dropout #N]` to the log line — byte-for-byte the shape of the ColBERT counter. **Behaviour-neutral on the success path** (same `Prefetch`, same `lane_names`). 13 lines. **Additive/observational** — no consumer reads `sparse_dropouts` yet.

**Evidence.** `tests/test_lane_dropout_counters.py` — three sparse tests (failure increments + accumulates; success does NOT increment) + the start-at-zero test extended. **15/15 pass** (sparse + ColBERT dropout suites). **Mutation proof** `logs/p1/step10/sparse_dropout_mutation.py` → `sparse_dropout_mutation.json`: baseline all PASS; **M1** (drop `+= 1`) reddens the failure + accumulate checks **on the assertion**; **M2** (increment on success too) reddens the negative control; **M3** (init to 1) reddens start-at-zero — **no inert check**. ⚠️ The mutation harness runs the **project venv** python (`.venv/bin/python`), not the agent's — a bare `python3 -m pytest` gave a red *baseline* (missing deps), which would have made every mutation's vector meaningless.

**The cluster re-probe (2026-11-05, read-only).** `logs/p1/step10/cluster_probe.py` → `cluster_probe.json`: **dense 200 (0.19 s) · ColBERT 200 (0.12 s) · sparse timeout (35 s) · rerank timeout (35 s)** — **reproduces session 35 exactly**. `cluster_probe_alternates.py` rules out the "endpoint moved" hypothesis: `10.0.10.70:8123` answers unknown paths with a **404 in 0.08 s** (the HTTP front is ALIVE) and the same timeout recurs on `:8000` — so the sparse/rerank **handlers** hang; it is **not** a dead host, a wrong port, or a moved route. Verifier `cluster_probe_verifier.py` **7/7 PASS**, mutation proof: each check reddens its intended check, none inert. ⇒ **#2 (router-in-the-loop) and the demo's retrieval path remain BLOCKED; the owner cannot restart the services.**

**Independent reviewer (gpt-oss-20b, `deleg_1b9df948`, read-only, family ≠ the author's).** Five numbered claims (the init, the guard-gated increment, success-path neutrality, the mutation proof, and the no-other-consumer claim): **5/5 CONFIRMED**. ⚠️ The reviewer's cited *line numbers* for the test file were wrong (it named the DA-test region, lines 56–61, for `sparse_dropouts`); the **identifiers** resolve and the author re-derived C5 mechanically (`grep` finds `sparse_dropouts` only in `store.py` init:352 / increment:686, the test file, and the mutation script) — so the substance holds and the sloppy citation is recorded, not banked.

**Register against:** §I96 (the class this closes), §I117 (the outage this re-confirms), §I55 (the reranker's equivalent counter, the template), §I100 (the lanes' ~0 endpoint contribution — this is visibility, not a metric win).

#### I119. ✅ THE DERIVED LANE INHERITED THE ARM'S (QWEN) QUERY INSTRUCTION — now pinned to the derived model's own convention. **Measured; fixed; verified.** Query-time only, no re-ingest.

**The mechanism.** `get_derived_embedder` (`cluster_embedder.py`) builds the embedder for the DERIVED collections (`concept_embeddings`, `derivative_artifacts`, both **nomic-768**) by `model_copy(update={"dense_model": derived_dense_model, "dense_dim": derived_dense_dim})` — it copied the **model and the width but NOT the instruction**, so the derived embedder **inherited the ARM's `query_instruction`**. Measured (default config): the derived nomic embedder carried **Qwen's** `'Instruct: Given a physics question, retrieve textbook passages that answer it\nQuery: '`. ⚠️ `step10_env.sh` masks it (`QUERY_INSTRUCTION="search_query: "`), so it bites only when the env override is absent — which is exactly the "default config" a fresh run or a test uses.

**Why it matters.** The derived collections were **built** with `search_document:` documents, so their query side must be nomic's `search_query: `. A Qwen instruction sent to a nomic model is the wrong convention — and it fires only when the arm's width differs from the collection's (so in a nomic run it is a **no-op** and invisible).

**The fix (2 files).** `config.py`: new **`derived_query_instruction: str = "search_query: "`**. `get_derived_embedder`: also copies `"query_instruction": cfg.derived_query_instruction`. ⇒ the derived lane is **nomic end-to-end and independent of the arm**.

**⚠️ ADJACENT LATENT TRAP (recorded, not fixed).** The config **defaults** describe the retired Qwen/v2 world: `dense_model = Qwen/Qwen3-Embedding-0.6B` (1024) while the deployed collection `knowledge_base_v3` is **768** (nomic). Measured: a **1024d vector into `dense_full` (768) → HTTP 400**; 768 → OK. So a run **without** the `DENSE_MODEL` override would break the MAIN dense lane. The defaults should be aligned to the deployed collection, or a read-path width guard added (the §A guard covers the derived lanes only).

**Evidence.** `tests/test_derived_embedder_instruction.py` **5/5**; mutation `derived_embedder_mutation.py` → `.json`: baseline all PASS, **5/5 reddened, none inert**. Independent verifier **`openai/gpt-oss-20b` (`deleg_ed3b2cce`), 5/5 CONFIRMED** (⚠️ the first dispatch returned a truncated verdict — a partial verdict is no verdict; re-dispatched without the empty `output_schema` that coerced it).

**Register against:** §I12/§I47 (the derived lanes' own-space defect this is the instruction-side twin of), §I83 (the 768 rebuild), §A (the width guard), §I117.

#### I120. ⚠️ WE IMPLEMENT THE LAB'S PPR *ITERATION* BUT NOT ITS *SUBSTRATE* — and our co-occurrence graph is too dense for hop expansion (1-hop **296** pages, 2-hop **802**, of ~906).

**The lab (`Labs/Week_5/week5.2/memgraphrag_concepts`) implements MemGraphRAG** (arXiv:2606.00610; ref impl `XMUDeepLIT/MemGraphRAG`): a **three-layer global memory** (Schema / Fact / Passage) → a **heterogeneous indexing graph** (`PASSAGE, SCHEMA, TYPE, ENTITY`; typed relation edges, `instance_of`, `evidence` w=0.8, entity↔entity `similarity` at cos ≥ 0.82), with PPR as **the retrieval mechanism** over **per-layer reset vectors** `P_init(p)/P_init(e)/P_init(t)` and **applied hub suppression** `1/log(deg+1)`.

| | Lab (MemGraphRAG) | Ours |
|---|---|---|
| Extraction | LLM **typed triples** `(head_type, relation, tail_type)` | LLM **concept names** + prerequisites |
| Schema layer | yes (derived from facts; stable = ≥2 passages) | **none** |
| Relation edges | LLM-typed relations | **co-occurrence** `RELATES_TO` (weight = co-mention count) |
| PPR reset | **per-layer** (passages/entities/types) | single reset over the query's seed **concepts** |
| Hub suppression | **applied** in the reset | only **reported** |
| PPR role | **the retrieval** | a **re-ranker** over one lane's candidates (§G1) |

**We match the ALGORITHM, not the ARCHITECTURE.** Our `personalized_pagerank` is the lab's iteration verbatim (`W=D⁻¹A`, `v(k+1)=(1−λ)Wv(k)+λv(0)`, λ=½, 10 steps) with a λ sweep and a hub-suppression *report* — but no three-layer memory, no typed triples, no per-layer reset, and hub suppression not applied. **⇒ §G1's null is evidence about PPR re-ranking over a dense, untyped co-occurrence graph — NOT about the lab's method**, which propagates over a structured, typed graph.

**The density, measured** (`logs/p1/step10/g1_pool_size_probe.py` → `.json`, read-only, 40 multihop queries):

| pool | median pages | `cut_bites_at_k` (k=10 / 20) |
|---|---|---|
| shipped (seed concepts) | **15** | 26/40 · 16/40 |
| 1-hop expansion | **296** | 40/40 · 40/40 |
| 2-hop expansion | **802.5** | 40/40 · 40/40 |

⇒ **the hop expansion is a FLOOD, not a refinement** (median 15 → 802 pages of ~906 in-window; 40/40 queries gain, +682…+823). So (a) the §G5 expansion is not a usable lane treatment as wired, and (b) a **page-level PPR ablation on the expanded pool is saturated** — the pool is the book. ⚠️ Also measured: the `*0..2` **path-enumeration** Cypher (`min(size(relationships(p)))`, used by both §G5 and the first probe) is pathologically slow on high-degree seeds (did not return in minutes); the **level-by-level DISTINCT neighbour** query is 0.2–0.4 s and is the form to use.

**Register against:** §G1 (the closed null this reframes), §G5 (the expansion this bounds), §I2, the lab `memgraphrag_concepts` and the two papers in `Research Papers/`.

#### I121. ✅ C1/C4 BUILT (the response-side grounding graph + ALCE citation faithfulness) — and ⚠️ **THE LAB'S NLI MODEL DOES NOT SEPARATE UNRELATED FROM ENTAILING TEXT** (measured: an unrelated passage scores entailment **0.9948**, ABOVE a supporting passage's **0.9924**).

**What was built (C1).** `src/core/guardrails/response.py` now carries the lab's five response-grounding modules, ported from `Labs/Week_6/response_grounding/src/response_grounding/*.py`: `ClaimExtractor` (+ the lab's sentence-split fallback and its COSTAR prompt, copied to `src/core/guardrails/prompts/claim_extractor_system_prompt.md`), `ClaimDocumentMatrixBuilder` (the Cartesian product), `SemanticSimilarityFilter` (MiniLM cosine, τ 0.5, strictly-greater), `NLIEntailmentChecker` (DeBERTa cross-encoder, entailment = the softmax prob of the model's entailment head, τ 0.55) and `GroundednessEvaluator` (grounded iff ≥1 retained edge entails; score = grounded/claims; an **isolated left node** — a claim with no edge — is the graph's hallucination signature). The only deviations from the lab are (a) `call_llm` replaces `instructor`+`OpenAI` (same `ClaimExtraction` schema, same fallback) and (b) the encoder/checker are injectable so `USE_STUB_NLI` can stand in offline. Factories `get_semantic_filter` / `get_nli_checker` / `get_groundedness_evaluator` read `cfg`; `evaluate_groundedness` is the entry point. New config: `use_stub_nli`, `guard_similarity_model`, `guard_nli_model`, `guard_similarity_threshold`, `guard_nli_threshold`, `guard_max_claims`, `guard_max_evidence`.

**What was built (C4).** `compute_citation_faithfulness` implements **ALCE** (Gao et al., 2023) over the same NLI graph: **citation recall** = the fraction of ALL statements with ≥1 entailing citation; **citation precision** = the fraction of ALL citations that entail. Both are **None** when the answer cites nothing — the §I115 lesson applied (`"no citations"` and `"every citation faithful"` are different facts). Citations are stripped from the statement before the NLI read, so the entailment is about content, not the `[Page N]` marker.

**⚠️ THE FINDING — the model, not the port.** The port is faithful; the acceptance tests and the live probe's ASSERTED checks all pass. But the live probe (`logs/p1/step10/c1_live_probe.py` → `.json`) measures the lab's chosen NLI model `cross-encoder/nli-deberta-v3-base` on three passages against one claim ("Energy is conserved in a closed system."):

| passage | contradiction | entailment | neutral | verdict at τ 0.55 |
|---|---|---|---|---|
| **supporting** ("…energy can neither be created nor destroyed…") | 0.0002 | **0.9924** | 0.0074 | entailing ✓ |
| **unrelated** ("The cat sat quietly on the warm mat by the window.") | 0.0017 | **0.9948** | 0.0036 | **entailing ✗** |
| **contradicting** ("Energy is routinely created from nothing…") | 0.0730 | 0.1058 | 0.8213 | not entailing ✓ |

**The unrelated passage OUTSCORES the supporting one** (separation gap **−0.002359**): no threshold can separate them. The head reads are the model's own softmax; the entailment class index resolves to **1** (the real head order is `{0: contradiction, 1: entailment, 2: neutral}` — verified live; the offline stub mirrors that order so a test cannot pass on a class order the model does not have). ⇒ **this is a property of the base DeBERTa NLI head, and it directly undercuts §I114's plan** to hand the **22 near-domain negatives** (`neg-in` 12 + `neg-nea` 10) to the response-side grounding floor: a floor whose entailment read calls an unrelated passage entailment cannot refuse those negatives on grounding grounds. **This is a MODEL limitation, not a code defect** — the fix is a different/stronger NLI model or a two-stage read, and it needs its own measured decision.

**Evidence.** `tests/test_guardrails_response_c1.py` + `tests/test_guardrails_citation_c4.py` **33/33**; independent stdlib verifier `logs/p1/step10/guardrails_c1c4_verifier.py` **14/14** (PART 1 re-derives every probe flag from the raw probabilities; PART 2 re-derives the ALCE metrics with its own splitter/regex/arithmetic over a hand-set oracle); mutation `guardrails_c1c4_mutation.py` **13/13 reddened, no inert** (⚠️ M9 was INERT on the first run — the object-form test was rescued by the bracket-slice fallback; a stronger fixture `{"claims": [...], "extra": [1,2]}` was added and M9 now reddens — recorded, not hidden). Independent cross-family reviewer **`openai/gpt-oss-20b`** (the cluster router, vs the author's deepseek): see `logs/p1/step10/guardrails_c1c4_review.json`.

**Register against:** the plan `.hermes/plans/2026-11-05-p1-guardrails-course-aligned-SESSIONS.md` (C1/C4 rows), §I114 (the G1 split this floor was assigned), §I115 (the citation-metric lesson C4 applies), ARCHITECTURE.md §2/§4 (Gate 2, absent from `src/` until now).

#### I122. ⚠️ A PER-STEP VERIFICATION CONTRACT THAT LIVES ONLY AS PROSE GETS SILENTLY SKIPPED — now enforced by a deterministic completeness gate bound to the test suite.

**The failure, measured.** The guardrails plan's §9 states a four-part contract per step (acceptance + independent reviewer + stdlib verifier + mutation proof) and §9.4 says a step with no verdict is not done. An audit **against the files, not the prose** found the session-37 status table marked **P0, R8 and C2 `✅ DONE` with no independent reviewer** — a *consistent* omission, i.e. a forgotten ritual, not a judgment call. Nothing distinguished "no reviewer" from "reviewer recorded elsewhere", because the table is written by hand by the author.

**Why a "verifier of the verifier" is the wrong fix.** A second LLM reading the table is itself a *judgment* check, so it fails for the same reason the first one did — it only fires if someone remembers to run it, and then you need a trigger for the trigger.

**The fix (2 files).** `scripts/verify_plan_coverage.py` — deterministic, no model: for every `✅ DONE` row in a plan's status table it asserts the verifier cell is non-empty, the mutation cell is non-empty, an independent reviewer **resolves** (a `deleg_*` id, or a `…review…` artifact that exists on disk), and every backticked `path/like/this` token exists. `tests/test_plan_verification_coverage.py` binds it to the suite — so it cannot itself be skipped — and includes its own negative tests (the gate must redden on a missing reviewer and on a missing artifact). Being deterministic, the gate needs **no verifier of its own**; the one residual judgment ("was the reviewer's verdict *substantive*?") cannot be gated and stays covered by the existing rule *a partial verdict is no verdict*.

**Demonstrated.** Run against the pre-fix table it names **exactly P0, R8, C2**. The three steps were then **retro-verified**: `p0_config_guard_verifier.py` 14/14, the R7R8 mutation 7/7, the C2 mutation 4/4, and an independent cross-family reviewer (`openai/gpt-oss-20b` on the cluster router vs the author's deepseek) **13/13 CONFIRMED** (`logs/p1/step10/guardrails_p0_r8_c2_review.json`).

**Register against:** the plan §9 (the contract this enforces) and §9.5, `HANDOFF.md` session 38, §I121 (the same session's other verification work).

#### I123. ⚠️ THE VISUAL LANE'S APERTURE IS STILL AN UNJUSTIFIED RAW-COSINE THRESHOLD, AND THE CONFIG COMMENT'S JUSTIFICATION IS CONTRADICTED BY §I107's OWN MEASUREMENT.

**The state, checked 2026-11-05 (this is a correction of the record, not a new run).** `cfg.visual_score_threshold = 0.58` is applied in the product path (`store.py:1927`, and `evaluate_rag.py:358` for the eval) — a **raw mean-best-cosine** bar on the ColPali lane. The NG plan's status table shows **VL-L1, VL-L2 and VL-L3 all ⬜ (never started)**, so the calibration that was supposed to replace the raw threshold has not run.

**⚠️ THE CONTRADICTION.** `config.py:269-278` justifies 0.58 with: *"an in-domain page scores 0.94-1.00 whether the query is the native page or a downscale/upscale of it, while out-of-domain images (noise, blank, unrelated text) score 0.43-0.46. 0.58 sits in the gap."* **§I107 measured the opposite for real figures**: the weakest in-domain concept scored **0.4936**, a near-domain image (H 2p orbital) scored **0.5609** — i.e. a near-domain image OUTSCORES the weakest in-domain one — with noise at **0.4578** and a logo at **0.4355**; verdict **`separating: NONE`**. The comment's 0.94–1.00 band describes the **self-match regime** (V1 passed 12/12 at cosine **1.0000**, a self-match signature, not cross-render proof), not real in-domain figures.

**⇒ The 0.58 threshold is not a calibrated aperture.** With real figures it sits ABOVE the near-domain maximum (0.5609) — so it happens to exclude that instance — but it is also above genuine in-domain figures scoring 0.49–0.56, which it would **reject**. It excludes by luck of where the bar was placed, not by separation of the two distributions.

**What is NOT claimed:** that the threshold is harmful in the demo (no labelled visual metric exists, so its effect is unmeasured — §I107's other half). What IS claimed: the comment asserts a separation the measurement does not support, and the number is unjustified.

**The fix already scoped (never run):** **VL-L1** — calibrate a *statistic* (margin / z-score over the query's own patch scores) rather than a raw cosine, with the pre-registered outcome *"a statistic separates in/near/far where raw cosine did not; **else recorded as no-separation**"*; then **VL-L2** (a labelled set built from REAL figure crops, not synthetic plots) and **VL-L3** (rank it with `compute_retrieval_metrics`). ⚠️ **VL-L1 can legitimately conclude "no separation" — that is an allowed, reportable outcome, not a failure.**

**Register against:** §I107 (the measurement this corrects the *justification* of), the NG plan `.hermes/plans/2026-11-02-p1-nicegui-and-visual-lane-SESSIONS.md` (VL-L1/L2/L3, all ⬜), ARCHITECTURE.md §2 (the visual lane has no labelled metric).
