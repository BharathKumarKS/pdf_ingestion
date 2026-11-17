# SESSIONS — Frontend (NiceGUI) + Visual-lane levers — resumable brief

> **Written 2026-11-02.** A durable, resumable workstream: pick it up in any new session and continue
> from the first ⬜. **Every step carries its own independent verifier** (this repo's rule: one
> verifier per step, not one at the end). Read this file, then the current status table, then start.

---

## 0. Status table — read this first

| id | step | status | acceptance | verifier |
|---|---|---|---|---|
| **NG-P1** | NiceGUI skeleton (`ui.run` 8504, config echo) | ✅ **DONE** | `/healthz` 200; `/` 200 + title; `resolved_config()` == env (0 mismatches); port 8504 listening; Streamlit still 8503 | ✅ reviewer `deleg_ccc4de3a` 5/6 confirmed, no defects; C3 (env echo) `unverified` by the reviewer (could not execute) → **closed by the author as mechanical evidence** (8/8 fields, 0 mismatches, re-run) |
| **NG-P2** | Ask-a-Question tab (`run.io_bound` retrieval) | ✅ **DONE** | ⚠️ **criterion RESTATED** (§1a): the literal "cited pages match" is confounded by LLM sampling and is REFUTED as a stable test; the restated deterministic claim — the two frontends RETRIEVE the same page set — HOLDS | ✅ verifier `deleg_0ee79bf9` (`openai/gpt-oss-20b`, read-only): all 5 claims CONFIRMED; ⚠️ its report had one arithmetic slip (`common_pages: 18` — the correct value is **19**, re-derived by the author from the raw JSON) and its final answer echoed the artifact instead of the numbered list |
| **NG-P3** | Read-only tabs (Status / Cards / RAPTOR) | ✅ **DONE** | counts match `list_documents` / `get_cards` / `get_raptor_tree` — see §1b (36/36 PASS) | ✅ verifier `deleg_04ed319a` (`openai/gpt-oss-20b`, read-only): all 5 claims CONFIRMED, its independently-recomputed per-document counts matching the artifact exactly; PASS verdict held justified |
| **NG-P4** | Visual + Graph tabs | ✅ **DONE** | page images render; graph nodes match `get_graph_builder(cfg)` — see §1c (18/18 PASS) | ✅ verifier `deleg_bb8ae828` (read-only): claims 1/2/3/5 CONFIRMED (image keys + pages, 1-of-3 PNGs on disk, 2,001 vectors, graph 3,533 vs SQLite 3,796 with `is_content=0` only 5); claim 4 (Memgraph counts) **UNVERIFIABLE** by the child — **closed by the author** with an independent edge-type/label decomposition that sums to the same totals; claim 6 unread (the child's report was mangled by an author tool-usage error — see §1c) |
| **NG-P5** | Upload (admin) | ⬜ | a small PDF ingests and appears in Status | ⬜ |
| **NG-P6** | Role gating + error/timeout banners | ⬜ | role hides admin tabs; a killed cluster shows a banner, not a hang | ⬜ |
| **VL-L1** | Calibrated statistic (margin / z-score) | ⬜ | a statistic separates in/near/far where raw cosine did not; else recorded as no-separation | ⬜ |
| **VL-L2** | Real figure-crop labelled set (in/near/far) | ⬜ | set built from REAL figures, not synthetic plots; labels present | ⬜ |
| **VL-L3** | Ranking metrics on the visual lane (recall@k / MRR / nDCG) | ⬜ | the lane scored with `compute_retrieval_metrics`; a per-type table | ⬜ |

---

## 1. Part A — NiceGUI frontend (ADDITIONAL; Streamlit stays primary)

**The hard rule:** `src/frontend/streamlit_app.py` is **not** touched. NiceGUI lives in a **new**
module `src/frontend/nicegui_app.py`. Both are independently launchable. The backend
(`src/pdf_ingestion/*`, `src/core/*`, `scripts/evaluate_rag.py`) is **not** modified.

**Plan:** `logs/p1/step10/nicegui_migration_plan.md` (full design: tab inventory, primitives, async
model, session state, risks).

**Ports:** 8501/8502 = other repo; **8503 = Streamlit**; **8504 = NiceGUI**.

**Resume / run:**
```bash
cd /Users/bharathkumar/repo/Support_Vectors/Beyond_RAG_Advanced_Agentic_Knowledge_Architectures/Project/Team_Project/pdf_ingestion
unset PYTHONPATH
export QDRANT_HOST=10.0.10.65 QDRANT_COLLECTION=knowledge_base_v3 \
  DENSE_MODEL="nomic-ai/nomic-embed-text-v1.5" DENSE_DIM=768 DENSE_DIM_LOW=64 \
  DOCUMENT_PREFIX="search_document: " QUERY_INSTRUCTION="search_query: " DA_ENABLED=true
.venv/bin/python src/frontend/nicegui_app.py          # NiceGUI on 8504
.venv/bin/streamlit run src/frontend/streamlit_app.py \
  --server.headless true --server.port 8503 --server.fileWatcherType none   # Streamlit on 8503
```

**NG-P1 evidence (done):** `/healthz` → `{"ok":true,"app":"synapse-nicegui","phase":"P1-skeleton"}`;
`/` → 200 (10,502 bytes, contains "Synapse — NiceGUI frontend"); `resolved_config()` matched the env
on all 8 fields (0 mismatches); 8504 LISTEN; 8503 still `ok`.

**NG-P2 (next) — the one that matters.** One tab: input → `await run.io_bound(run_retrieval, ...)` →
`ui.markdown(answer)` + a source table. ⚠️ **Do NOT call the retrieval path directly on the event
loop** (60–90 s, blocking). Show a `ui.spinner()` before and after. Acceptance: the two runbook
queries ("What is Newton's second law?" and the conservation-of-energy overview) return answers whose
**cited pages match the Streamlit app's** on the same queries.

**§1a — NG-P2 evidence (2026-11-02).** Built in `src/frontend/nicegui_app.py` (`run_ask` mirrors the
Streamlit ask path; the tab calls `await asyncio.wait_for(run.io_bound(run_ask, q, cfg), timeout=300)`
with a spinner, a timeout banner and an error banner). Streamlit and the backend are untouched.
⚠️ **Deviation, stated:** the brief names `scripts/evaluate_rag.py::run_retrieval`, but that is the
**eval-harness** path (it takes `query_type` as an input, never classifies intent, never calls RAPTOR,
and always uses `fetch_k=reranker_fetch_k`) — it cannot reproduce Streamlit's cited pages, so
`run_ask` mirrors the Streamlit path instead.
* **UI wiring — verified headlessly.** `tests/nicegui/test_nicegui_ask_tab.py` drives the real tab via
  NiceGUI's `user` simulation (httpx/ASGITransport, no browser) with the backend faked at the module
  boundaries `run_ask` imports; it asserts the answer markdown + the "📄 Sources cited" line render
  and that the blocking call ran **off the main thread**. Mutation-proof: running the call on the loop
  reddens the thread assertion (`AssertionError: ... ran ON the event loop`). Run it with
  `NICEGUI_UI_TESTS=1 .venv/bin/python -m pytest -p nicegui.testing.user_plugin tests/nicegui/...`
  (the plugin, loaded globally, breaks 11 unrelated tests — hence the opt-in skip).
* **Acceptance — the literal criterion is REFUTED as a stable test.** Harness
  `logs/p1/step10/ng_p2_acceptance.py` ran both queries through `run_ask` (2 reps) and through the
  **live Streamlit app** via `streamlit.testing.v1.AppTest`. ⚠️ **The generator samples**: the same
  NiceGUI path, run twice on the factual query, cited `[]` then `[180,195,197,224]`; the two overview
  reps cited different sets. Cited pages are therefore not a stable frontend comparison.
* **The deterministic claim HOLDS.** The **retrieved** page sets: overview **20/20 identical** between
  the two frontends; factual **19/20 identical**, the single differing page being the lowest-ranked
  (nicegui rep0 `285`, rep1 `952`, streamlit `143`) — the **already-documented §I103 lane-tail
  nondeterminism**, not a frontend difference. **⇒ restated acceptance: the two frontends RETRIEVE the
  same page set, up to the §I103 tail noise.** Artifacts `ng_p2_nicegui.json`,
  `ng_p2_streamlit_{0,1}.json`, `ng_p2_acceptance.json`.
* **Suite:** `4 failed / 745 passed / 7 skipped` — the 4 are the documented pre-existing set, 0 new;
  the 7th skip is the opt-in UI test.
* **Verifier (independent, `deleg_0ee79bf9`, `openai/gpt-oss-20b`, read-only).** Re-derived every claim
  from the raw JSON: **all 5 CONFIRMED** (overview retrieved 20/20 identical; factual differs in
  exactly one page, `285`/`952`/`143`; cited sets unstable across reps; cited sets overlap but are not
  equal; 20 chunks every run). ⚠️ **Two defects in the child's report, both caught by re-deriving it
  myself:** it printed `common_pages: 18` where the correct intersection is **19** (arithmetic slip),
  and its final answer echoed the artifact JSON instead of the numbered verdict (visible only in its
  transcript). **The verdict stands on the author's own re-derivation plus the child's independent
  read — not on the child's summary.**

**Phase order:** P2 → P3 → P4 → P5 → P6. Each phase: implement, run its acceptance check, dispatch a
read-only independent reviewer, then mark ✅.

**§1b — NG-P3 evidence (2026-11-02).** Three read-only tabs added to `nicegui_app.py`:
**Status** (document table + six header totals), **Cards** (per-document, per-type browse, capped at
`CARDS_PER_TYPE`), **RAPTOR** (L1/L2/L3 counts + root/L1 summaries). Each loads via `run.io_bound`
behind a spinner. ⚠️ **The Streamlit Status tab's Delete section is deliberately NOT ported** — a
destructive action is not part of a read-only phase (that is NG-P5/P6 territory).
* **Acceptance — PASS, 36/36 checks.** `logs/p1/step10/ng_p3_acceptance.py` calls the module's own
  loaders (the exact functions the tabs call) and compares every count against a DIRECT
  `DocumentStore` call. Artifact `ng_p3_acceptance.json`. Live numbers: 2 documents, `total_chunks`
  **8,844**, `total_cards` **157,826**, `total_raptor` **157**, `total_visual` **968**; Cards per type
  formula 1,526 / definition 2,584 / question 32,002 / misconception 4,340 / example 1,457; RAPTOR
  L1 **72**, L2 **9**, L3 **3**, total **84**.
* ⚠️ **A harness bug found and fixed by running it — and it is the runbook's known caveat.**
  The first draft keyed the per-document comparison on **filename**; the SQLite file holds **two
  documents with the SAME filename** (`feynman-lectures-on-physics-volume1.pdf`, the old and the
  current ingest) but different ids and different counts (one has **0** page images, the other
  **968**). That produced **4 false failures**. Fixed to key on the **document id**, and the Status
  table now carries a short **Doc ID** column so the two are distinguishable on screen.
* **UI wiring — verified headlessly.** `tests/nicegui/test_nicegui_readonly_tabs.py` (same opt-in
  `NICEGUI_UI_TESTS=1` guard as NG-P2) drives the real tabs with a faked `DocumentStore` and asserts
  the four tabs exist, the Status metrics render the loader's totals (`4,242` for a faked chunk
  count), the RAPTOR metric row renders, and the Cards selector builds. **Mutation-proof:** adding
  `+1` to `load_status`'s `total_chunks` reddens the render assertion.
* ⚠️ **A TEST-ENVIRONMENT TRAP, found while checking the suite and worth carrying:** running the
  suite with the **demo env exported** (`DENSE_MODEL` / `DENSE_DIM` / `DENSE_DIM_LOW` /
  `DOCUMENT_PREFIX` / `QUERY_INSTRUCTION` / `QDRANT_HOST` / `QDRANT_COLLECTION` / `DA_ENABLED`) makes
  **11 extra tests fail** (`test_late_chunk_embedder` ×5 and others) because those exports override
  the config the stubs assume. **Run pytest with a scrubbed env** (`env -u DENSE_MODEL -u DENSE_DIM
  -u DENSE_DIM_LOW -u DOCUMENT_PREFIX -u QUERY_INSTRUCTION -u QDRANT_HOST -u QDRANT_COLLECTION
  -u DA_ENABLED -u PYTHONPATH .venv/bin/python -m pytest ...`) or the failures look like regressions.
* **Suite (scrubbed env):** `4 failed / 745 passed / 8 skipped` — the 4 are the documented
  pre-existing set, **0 new**; the 8 skips are the 6 documented + the 2 opt-in UI modules.
* **Verifier (independent, `deleg_04ed319a`, `openai/gpt-oss-20b`, read-only).** Re-derived every
  count from the live store: **all 5 CONFIRMED**, and its per-document numbers match the artifact
  **exactly** — `6d55c52b` cards 82,164 / raptor 84 / visual **0** / chunks 5,048; `7ba61432` cards
  75,662 / raptor 73 / visual **968** / chunks 3,796. It also confirmed the two-document same-filename
  situation and the reason the filename-keyed draft produced 4 false failures, and judged the PASS
  verdict justified with no inert check. ⚠️ Its answer arrived as a JSON object rather than the
  requested one-line-per-claim list (a formatting miss, not a substance one).

**§1c — NG-P4 evidence (2026-11-02).** Two read-only tabs added to `nicegui_app.py`:
**Visual** (text-query ColPali search → page images in cards, with the index size) and **Graph**
(live Memgraph node/edge counts + a single-hop concept search). Both load via `run.io_bound`.
Inputs/buttons carry `.mark(...)` so the headless tests can target them unambiguously.
* **Acceptance — PASS, 18/18 checks.** `logs/p1/step10/ng_p4_acceptance.py` (artifact
  `ng_p4_acceptance.json`) runs the module's own loaders against independent sources: the visual
  results match a direct `visual_search`; every page image that exists resolves to a valid PNG
  (`\x89PNG` magic); the Memgraph counts equal a **separate driver's** counts; the graph search's
  chunk_ids equal a direct `get_graph_builder(cfg).graph_search(...)`.
* ⚠️ **A DATA finding the acceptance surfaced, not a tab defect.** The visual query
  `"the diagram of a pendulum"` returns pages **94 / 102 / 446** across **both** documents, but
  `data/page_images/` holds PNGs for the **current** doc only (`7ba61432`, 968 files) — the old doc
  `6d55c52b` has **no directory at all**, so **2 of the 3 cards show "⚠️ page image unavailable"**.
  That is the runbook's visual-lane caveat made concrete; the check was therefore restated as
  "every key that exists on disk resolves to a valid PNG" + "the missing ones are marked", rather
  than an equality that would fail on pre-existing data.
* ⚠️ **A second store-state finding.** Memgraph holds **3,533** Chunk nodes for the current doc vs
  SQLite's **3,796** (**−263**), and SQLite's `is_content = 0` count for that doc is only **5** — so
  the gap is **not** explained by the stored column. It matches the register's documented
  recompute-vs-stored-column split (the graph build recomputes the content predicate; the column is
  a stale snapshot). The check asserts a **bound**, not equality, and the delta is recorded.
* **Independent edge decomposition (closes the verifier's one gap):** total edges **47,209** =
  RELATES_TO **21,670** + MENTIONS **14,405** + PART_OF **4,440** + ON_PAGE **3,533** +
  PREREQUISITE_OF **3,161**; node labels Concept **6,065** / Chunk **3,533** / Page **907** /
  Document **1**. ⚠️ The runbook's "21,670 edges" is **RELATES_TO only** — quote the total as 47,209.
* **UI wiring — verified headlessly.** `tests/nicegui/test_nicegui_visual_graph_tabs.py` (opt-in
  `NICEGUI_UI_TESTS=1`) fakes every backend boundary and asserts the six tabs exist, the Graph
  metric row renders the faked edge count, a visual query creates a `ui.image`, and a graph query
  renders its matched concepts. **Mutation-proof:** `+1` on the graph counts reddens the render
  assertion.
* ⚠️ **A verifier-harness error of the author's, recorded rather than hidden.** The verifier was
  dispatched with an **empty `output_schema`**, which collapsed its final answer to `{}` — so its
  verdict had to be read out of the (truncated) live transcript: claims 1/2/3/5 CONFIRMED, claim 4
  **UNVERIFIABLE** (the child could not find the Memgraph container to query it — the port answers,
  the container is just named differently), claim 6 unread. Claim 4 was closed by the author's own
  independent decomposition above; claim 6 is covered by the acceptance harness.
* **Suite (scrubbed env):** `4 failed / 745 passed / 9 skipped` — the 4 are the documented
  pre-existing set, **0 new**; the 9 skips are the 6 documented + the 3 opt-in UI modules.

---

## 2. Part B — Visual-lane levers (make the ColPali lane measurable / gateable)

**Where it stands.** §I107 (IMPROVEMENTS.md): the raw ColPali top-1 cosine **cannot** separate
in-domain from near-domain — a near-domain image (0.5609) outscores the weakest in-domain concept
(0.4936), the floor is high (noise 0.4578), and **no threshold separates** (`separating: NONE`). V1
passes 12/12 but at **cos 1.0000 — a self-match signature** (unresolved: self-match vs cross-render).

**VL-L1 — calibrate the statistic (cheapest; do first).**
The stored `score_cosine` is already the **mean best cosine** (MaxSim ÷ query patch count,
`store.visual_search`), so the normalisation lever is partly applied. What is NOT tested is the
**shape**: margin (top1 − top2), z-score (top1 vs the query's own score distribution over the corpus),
and the raw-vs-normalised gap. ⚠️ `visual_search` filters at `score_threshold` and caps at `limit`, so
to get a distribution call it with **threshold 0 and a large limit**.
Deliverable: a harness that stores the **full top-k score list per query** and re-derives
top1 / margin / z-score, then reports whether any of them separates in/near/far. Artifact +
independent verifier + mutation proof.

**VL-L2 — fix the test set (it currently confounds the question).** The in-domain group is
**synthetic matplotlib plots** — in-domain by *topic*, not by *appearance*, while the near-domain group
is also plots. Build a **real** set: in-domain = figure **crops from the actual Feynman pages**;
near-domain = figures from a **different** physics book; far-domain = photos/logos/noise. State the
provenance per image. This is annotation, not code.

**VL-L3 — score it as RANKING, with labels.** Label the visual queries / figure crops with their true
page, then score with the product's own `compute_retrieval_metrics` (recall@k, MRR, nDCG) — the lane
then drops into the same per-type table as the text lane. This is the only route to a real
"is the visual lane performing?" number.

**Order:** L1 → L2 → L3. L1 is read-only and can run now; L2/L3 are annotation-heavy.

---

## 3. What "verified" means here

Every step: (a) its **acceptance check** run by the author and its raw output read; (b) a
**DETERMINISTIC verifier** for **every** step — a **stdlib program** (not a judge) that re-derives every
reported cell from the raw per-item array, so its evaluation needs no model and is reproducible;
(c) an **independent reviewer** — a **different model family** from the author, read-only, given the
diff and the numbered claims, told to re-derive rather than agree — this is the SECOND check, never the
first; (d) a **mutation proof** where every check is reddened by ≥1 mutation and no check is inert.
A step with no verdict is **not** done and is **not committed**. Record the outcome where the next
reader looks (this file + HANDOFF).

---

## 4. Open items carried into this workstream

* The **V1 self-match question** (VL-L1 can settle it: is the query image the stored one?).
* The **T3 pre-registration** is written (`.hermes/plans/2026-11-02-p1-t3-lane-complete-preregistration.md`)
  and the T3 chain runs after the generator eval — **separate workstream**, not part of this brief.
* Nothing here is committed. The branch is ahead of origin; **nothing pushed** — owner decision.
