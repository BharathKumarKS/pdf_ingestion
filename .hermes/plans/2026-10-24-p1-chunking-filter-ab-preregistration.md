# P1 — PRE-REGISTRATION: does the §I39 content filter improve base-lane page ranking?

> **Written 2026-10-24 (session 14) at the owner's direction, and COMMITTED ALONE, BEFORE THE RUN.**
> That commit is what makes it a pre-registration (§I61's precedent). The harness, the run and the
> verifier belong to the NEXT session. **If any number in this file is edited after the run starts,
> the run is void.**
>
> Read first: `IMPROVEMENTS.md` §I39 (the filter and its measured hit rates), §I21 (the filter in the
> graph path), §I58 (the ceiling rule), §I70 (the embedder screen and its instrument), §I63 (the
> 0.0648 residual this arm is trying to move), and `HANDOFF.md` session 14.

---

## §0 — WHY THIS ARM, AND WHY IT IS FIRST

The open question is **whether the new corpus ranks worse than the deployed one because of its
chunking, or because of something else.** The owner's position is that the new corpus's chunking is
better on the merits; the register's only relevant number points the other way. Neither is measured.

The measured state, all on the same instrument (§I63 established comparability by reproducing the
Qwen3 arm exactly). Ceiling-normalised / raw R@20:

| corpus | Nomic 768 | gemma 768 | Qwen3 1024 |
|---|---|---|---|
| OLD (5,048 chunks, 756 pages) | 0.498722 / 0.442866 | not measured | — |
| NEW (3,796 chunks, 933 pages) | 0.433930 / 0.424181 | 0.480410 / 0.469155 | 0.293934 / 0.289340 |

That 0.0648 gap (Nomic, old → new) is §I63's **unattributed residual**: it mixes the chunking, the
content-filter state and the chunk count, and no experiment has isolated any of them.

**This arm isolates the content-filter state alone, because it is the one of the three that can be
varied without re-chunking, re-parsing or re-embedding.** It is also a change that is wanted
regardless of the embedder decision.

## §1 — THE MEASURED FACTS THIS ARM RESTS ON (do not re-derive)

> ⚠️ **Verification status of this section.** These are **session-14 measurements**, taken by the
> author with a throwaway probe, and they have **NOT** been independently verified — the standing
> rule ("any doc that asserts a measured number") applies to them. Two of them are covered by this
> arm's own guards (**C2** re-derives the 263, **C1** re-derives the pool); the rest (the 471, the
> character percentiles, `chunks/page`, the graph's 3,533 chunk nodes, the stale-`token_count`
> finding) are **asserted here and must be covered by the verifier dispatch in the next session** —
> hand the verifier this file and have it re-run the reads. Do not quote them elsewhere until then.

**F1. The stored `is_content` is STALE on both corpora.** `is_content` is written at ingest and the
§I39 filter extension landed after both ingests. Measured 2026-10-24 by running the CURRENT
`src/pdf_ingestion/content_filter.is_content()` over the stored chunk text:

| corpus | chunks | stored `is_content=0` | CURRENT filter would exclude |
|---|---|---|---|
| OLD (deployed) `6d55c52b` | 5,048 | **0** | 471 (9.3 %) |
| NEW `7ba61432` | 3,796 | **5** | **263 (6.9 %)** |

The 263 matches §I39's independently measured **72 TOC + 186 index + 5 front matter** exactly. So the
new corpus's retrieval index still carries its TOC/index chunks as content, and the ~5,100 junk cards
(§I39) are still active. §I21 applies the filter at **graph-build time only** — the graph holds 3,533
chunk nodes = 3,796 − 263, which confirms the count from the other direction.

**F2. The two chunkings, in characters** (⚠️ the OLD corpus's `token_count` column is a *character*
count — `token_count ≈ len(text) + 1`, p50 450 against 449 chars — so do not size anything on it):

| corpus | chars p10 / p50 / p90 / max | `parent_id` | pages with chunks | chunks/page |
|---|---|---|---|---|
| OLD | 331 / 449 / 501 / 1,700 | 0 / 5,048 | 756 | **6.68** |
| NEW | 191 / 447 / 948 / 2,949 | 3,795 / 3,796 | 933 | **4.07** |

Same median, very different shape: the old is a tight fixed window, the new a wide semantic
distribution with parents. ⚠️ **`chunks/page` is a confound, not a detail** — page-deduped recall
scores a page at its single best chunk's rank, so the old corpus gets 64 % more chances per page.
**Every arm must report it.**

**F3. No parse cache exists** (`data/parsed`, `data/docling_cache`, `data/parse_cache` all absent), so
a genuine re-chunk re-parses the PDF. **This arm does not need one** — see §2.

## §2 — THE DESIGN, AND THE SIMPLIFICATION THAT MAKES IT CHEAP

The filter changes **which chunks are in the candidate pool**. It does not change any chunk's text,
any chunk's id, or any stored vector. So the arm is measurable **over the vectors already in
`knowledge_base_v2`, with no parse, no re-chunk and no re-embed** — seconds of compute, not the
~10-minute re-chunk loop, and no writes.

Two arms, same stored vectors, same queries, same metric code. **The pool filter is the only
variable.**

| arm | pool |
|---|---|
| **C** (control) | the shipped filter: `is_content is not False` and inside the content window — §I70's pool, 3,489 chunks |
| **T** (treatment) | `C` **minus** every chunk the CURRENT `content_filter.is_content()` rejects — 263 chunks |

⚠️ **The treatment is computed from the TEXT, not from the stored `is_content`** (F1 — reading the
stored column would silently produce a 5-chunk treatment and a near-null).

⚠️ **The ceiling moves, and that is part of the result, not a nuisance.** §I58's reachable set is
"a page with ≥1 chunk, `is_content is not False`, inside the window". Filtering 263 chunks can remove
a page from the ceiling entirely. Report **pages covered** per arm; do not silently re-normalise
against one of them.

⚠️ **A mechanism that could make this go either way, stated up front so a negative is interpretable:**
a page scores at its best chunk's rank. If a TOC/index chunk on page *p* ranks high while the body
chunk on page *p* ranks low, **removing the TOC chunk LOWERS page *p*'s score** — the filter can
improve chunk-level precision while hurting page-level recall. This arm measures the page-level
effect, which is the one the gold set labels.

**Primary embedder: gemma@768** — the corpus + embedder we would actually ship, and the §I70 winner.
**Secondary: qwen3@1024** — free (the stored vectors), and it tests whether the filter's effect is
embedder-specific. ⚠️ **Report both; the primary is not switched after seeing numbers.**

## §3 — PRE-REGISTERED ENDPOINT AND RULE

* **Endpoint: paired, ceiling-normalised R@20, arm T − arm C, n = 133**, under gemma@768.
* **Attributable iff the 95 % CI excludes 0.** Otherwise the honest statement is "applying the
  content filter does not move base-lane page ranking on this corpus" — a RESULT, not an unresolved
  one.
* **ONE run. No extension. No arm added after seeing numbers.**
* **Reported alongside, always:** raw R@20, R@100, pages covered per arm, chunks/page, and the
  qwen3@1024 secondary row.
* **The decision this feeds:** if T resolves positive, the filter is worth applying at the next
  re-ingest (which then needs its own product-endpoint run). If T is null or negative, the filter is
  **not** the 0.0648, the residual moves to the chunking proper, and the next arm is
  `min_chunk_tokens` (§5).

## §4 — VERIFIERS (each must be able to FAIL)

| # | check |
|---|---|
| C1 | **arm C reproduces §I70's qwen3@1024 row EXACTLY** — R@20 0.293934 · R@100 0.569074 · R@500 0.922982 · R@1000 1.0. The control pool is unchanged, so the instrument must be the same one that produced the register. |
| C2 | the treatment pool is **exactly** `C` minus the flagged chunks; the flagged set is **263**; the split by band (TOC / index / front matter) is reported and matches §I39's 72 / 186 / 5. |
| C3 | **A-vs-A negative control**: arm C run twice is byte-identical. |
| C4 | the treatment was built from the **text**, not the stored `is_content` — assert the flagged count is 263 and **not** 5. |
| C5 | every query whose reachable set is empty in an arm is reported, never silently dropped. |
| C6 | identical chunk→page mapping across arms (one shared `pages` array; a sha256 of it). |

## §5 — WHAT THIS ARM DOES NOT DO, AND WHAT COMES AFTER

* **It does not test the chunking.** It isolates the content-filter state, one of the three things in
  §I63's residual. If it is null, the next single-variable arms are, in order: **`min_chunk_tokens`**
  (32; §E1 measured it merging 27 % of the new children and never re-checking the grown child's
  size), then **`semantic_threshold`** (0.8), then **late chunking** (the expensive one — 36 min per
  arm, and it changes the embedding, not the chunking, so it is its own contrast).
* **It does not touch the product path.** The base lane is a **ceiling**, not the endpoint: §I66
  measured the loss as the 100-slot fusion and the cross-encoder (0.7478 → 0.6048 → 0.4318), and §I65
  is the case where a measured ceiling did not become recall. A win here licenses a re-ingest; it
  does not ship.
* **It does not measure the ingest-time side effects** of the filter (new chunk ids, card
  regeneration, graph rebuild). Those are a build, not an arm.
* ⚠️ **§0's power rule still applies:** n = 133, resolution floor ≈ **0.020**. An effect below that is
  out of scope — record it, do not chase it.

## §6 — COST

Harness + run + verifier: **one session, well under an hour of wall time.** No LLM calls, no writes
to any collection, no parse, no re-embed. The only cluster work is the gemma embed of the 3,489
in-window chunks (~1 min idle; measured at 66 s / 1,073 s / 73 s across three runs under varying
cluster load — `meta.embed_seconds` must record which).

## §7 — ARTEFACTS TO PRODUCE

* `logs/p1/step10/chunk_filter_ab.py` — the harness (extend `embedder_screen.py`; its `scroll_pool`
  already reads `is_content`, and `content_filter.is_content()` is the flagger).
* `logs/p1/step10/chunk_filter_ab.json` — the artefact: meta, verifiers, arms, endpoints, per-query rows.
* `logs/p1/step10/chunk_filter_ab_verifier.py` — an **independently written** stdlib aggregation over
  the raw per-query array, with `--check` diffing against the artefact (the §I70 pattern). The
  reviewer gets the extract, never the summary block.
* The register entry in `IMPROVEMENTS.md` (§I71) and the `HANDOFF.md` block.

**Verifier dispatch: with the run, not after.** `openai/gpt-oss-20b` (different family from the author
*and* from the subject). ⚠️ This session's shell returns **empty stdout with exit 0** — smoke-test one
`echo` before dispatching a tool-using child, and if it is still empty, dispatch a **read-only**
reviewer (`read_file` / `search_files` only, `terminal` named and forbidden) with the evidence
embedded as DATA, and record the arithmetic as mechanical evidence rather than a second opinion.
