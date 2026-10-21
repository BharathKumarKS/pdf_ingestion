# P1 — the non-LLM, parallel-safe work. Execution plan.

> **Written 2026-10-20 (evening). FOR SIGNOFF — nothing here has been run.** Read `IMPROVEMENTS.md`
> §I29/§I30/§I31 first (they are what this plan executes), and `HANDOFF.md`'s top block for the card
> run's state.
>
> **Why this plan exists.** A card run is in flight until ~02:07 and it owns the cluster's LLM
> endpoint (`10.0.10.70:8000`). §I23 measured what happens when a second LLM-hungry job shares that
> cluster: an 8× throughput collapse, and a 2 h estimate that became 16 h 25 m. So the work selected
> here is exactly the work that **issues no LLM call** — it can run alongside the card run without
> taking a toll on either.
>
> **⚠️ SCOPE BOUNDARY — read this before the task list.**
>
> ```
> NOW  (this plan, on approval): A1 -> A2 -> A3 -> A4   [all read-only or local code; no LLM]
> THEN: STOP. Report A1-A4's artifacts and re-plan.
> LATER (separate gate, separate approval, NOT started here): B1 = the §G3 merge.
> ```
>
> Nothing after the STOP line has started, and nothing here authorises it. A1–A4 are the *safe half*.
> B1 mutates the graph and is deliberately a **separate gate** (§4 below) — consent to the
> measurements is not consent to the merge.

---

## 0. What is in flight, and what is therefore excluded

| | |
|---|---|
| **In flight** | the Phase B card run — tmux session `phaseb`, launched 19:05:10, `logs/p1/step10/phaseb_run.log`, checkpoint `data/card_cache/7ba61432__34088ccb399ef4d5.jsonl`, ETA **~02:07** |
| **Excluded — needs the LLM at `:8000`** | anything calling `src/core/llm.py`; Phase C (DA re-index) and Phase D (ColPali), which also need the cards |
| **Excluded — needs a re-ingest** | §E5, §F1, the §D4 label fuzz, and any fix that changes the chunk set |
| **Included — the embed service** | `10.0.10.70:8123` is a **different service** from the LLM at `:8000`. Probed 2026-10-20: `/embed-text/v1/embeddings` returns 200 for `Qwen/Qwen3-Embedding-0.6B` (1024d, 0.21 s) **and** for `nomic-ai/nomic-embed-text-v1.5` (**768d**, 1.92 s). The 768d model is the one `Concept.embedding` uses, so A1 is runnable now. |

**Also due, and not part of this plan:** when the card run finishes, **B4 → B5 → B6** must run
(`verify_phaseb_cards.py`, `verify_phaseb_raptor.py`, then read ~10 sample cards). Exit code is not
the verdict; read `failed_card_types` (§I25). Before any relaunch, copy the log to a non-`.log` name
(`*.log` is gitignored, `.gitignore:68`).

---

## 1. A1 — the query-side `matched_concepts` baseline (§I29's missing number)

**What.** For a sample of the v2 gold queries: embed the query with **nomic 768d** via `:8123` (the
model `Concept.embedding` actually uses), take the top-8 concepts exactly as
`GraphBuilder._find_concepts_scored(query_vector, top_k=8)` does, then run `graph_search`'s ranking
Cypher and record the distribution of `matched_concepts` and the retrieved top-k's median.

**Why.** §I29: the §G plan's G3 verifier measures a quantity that is already at 0.9687 and cannot
discriminate. `graph_search` ranks by how many of the **query's** 8 concepts a chunk matches
(`graph_builder.py:449-459`) — that is what §I2 means by "ties at 1", and it has never been measured.
**Without this number G3 would be designed against an unmeasured baseline**, which is precisely the
mistake §I29 caught in the plan.

**Read-only.** No mutation, no LLM. Deterministic: the raw query is embedded directly, so the HyDE
non-reproducibility trap does not apply here.

**Verifier — the effect that must be measured, not a log line:**
1. **Non-degenerate**: the distribution must not be all-1s or all-8s. Either extreme means the
   measurement is not measuring the ranking, and must be reported as such rather than tabulated.
2. **Reproducible**: run twice; the two JSON artifacts must be **byte-identical**. (The A1 script
   must therefore sort any set-valued output — this is a requirement on the script, not a hope.)
3. **Sanity anchor**: the top-8 concept selection for a hand-checked query must be on-topic **by
   eye**, and recorded.
4. Independent reviewer (different model — see §5) on the script, with the raw artifacts.
5. **Raw output captured to a file and read back**, never quoted from the transcript.

**Artifacts:** `logs/p1/step10/g3_query_side_baseline.py`, `..._baseline.json`, `..._baseline.log`.

**Cost class:** one embed call per query on a service the card run is not using. Minutes.

---

## 2. A2 — §D14 fix (b): scope the preflight's graph↔Qdrant check

**What.** `scripts/preflight.py` requires Memgraph unconditionally and compares the graph's chunk ids
against `cfg.qdrant_collection` — the collection *under test*. Chunk ids are `uuid4()` per ingest
(`chunker.py:147`), so a graph built from the previous ingest shares no ids with a re-ingested
collection and the check reports ~100 % dangling. That is a permanent false-positive blocker: a
re-ingest transition can never pass the gate.

**Fix (b), the durable one:** scope the check to the collection the graph was built *from*, or skip it
with an explicit "graph lane not measured" note when the collection under test is not the graph's.
**Do not** run `clean_stale_graph.py` against `knowledge_base_v2` and **never** `--force` (§D14: the
graph is not stale, it is the correct graph for the deployed `knowledge_base`).

**Verifier — and it must be able to FAIL, or it is not a check:**
1. `preflight.py` exits **0** for `QDRANT_COLLECTION=knowledge_base_v2` (today: exit 1, 1 BLOCKER).
2. **The negative arm, which is the real test:** with the collection pointed at one the graph was
   genuinely *not* built from, the scoped check must still report a mismatch. A guard that passes
   both ways is vacuous — record the command and its output.
3. `memgraph` and every non-graph check must be **unchanged** in the before/after logs.
4. Independent reviewer on the diff.

**Artifacts:** `logs/p1/step10/a2_preflight_before.log`, `a2_preflight_after.log`,
`a2_preflight_negative.log`.

**Cost class:** code only, no re-ingest, no re-index. Local Memgraph + one Qdrant read.

---

## 3. A3 — §I28: stop `get_chunks_with_embeddings` over-fetching ~6×

**What.** `DocumentStore.get_chunks_with_embeddings` (defined `store.py:820`; the call is
**`store.py:836-840`**) issues
`self._qdrant.retrieve(collection_name=..., ids=[...], with_vectors=True)` — which returns **all named
vectors on all 3,796 points**, including the ColBERT token matrices the caller never uses. Measured on
the card run: a 3 min 06 s stall before the first card line, RSS 36 MB → 1,992 MB.

**Fix — smaller than §I28's write-up implies, and that was verified 2026-10-20 before relying on it.**
Line **841** already computes `dense_name = self._dense_vector_name()` and the very next lines extract
just that lane from the fully-fetched result. So the wanted vector name is **already known at the call
site**; the change is to pass it into the retrieve (an explicit vector selector) instead of fetching
everything and discarding it. `with_vectors=False` is already used elsewhere in the same file
(`store.py:974`, `store.py:1372`), so the pattern is established rather than novel. **Do not
restructure the function** — the smallest change that stops the over-fetch is the one to make.

**Verifier — measure the *call*, do not re-run the pipeline.** A full card-phase re-run is not an
acceptable verifier: it costs hours and the card run is already in flight. Instead:
1. **The call must change** — a stub/spy at the Qdrant client boundary asserting the retrieve is
   issued **without** `with_vectors=True` over all names. Print the actual kwargs.
2. **The contract must hold** — the returned dense order still matches `chunks` order (the caller
   zips them). Assert on a fixed id list; this is the one thing the change can break.
3. **The effect must be visible** — wall time and RSS at the call site, before vs after, in the same
   process. State both numbers; a change that does not move them has not done anything. Anchor on the
   measured baseline: **3 min 06 s / RSS 36 MB → 1,992 MB** on 3,796 points (§I28).
   **Do not verify this by re-running the card phase** — it costs hours, the card run is in flight,
   and the whole point is that the fix only pays off on the *next* run.
4. Independent reviewer on the diff.

**Artifacts:** `logs/p1/step10/a3_fetch_probe.json`, `a3_fetch_probe.log`.

**Cost class:** code only. `src/pdf_ingestion/store.py` is **clean in git** (verified 2026-10-20), so
this does not collide with the other session's in-flight work. Benefits *future* Phase 2/3 runs only
— the running card run has already paid the cost.

---

## 4. A4 — the §G2 modularity gate, as the **before** arm (report-only)

**What.** Compute modularity `Q` of a Leiden partition over the `RELATES_TO` subgraph, and compare it
against a **degree-preserving random rewiring** of the same graph — the course's Lab 2 procedure.
Leiden and `modularity` are both present in the installed networkx 3.6.1 (verified in the §G plan
§2); no new dependency.

**Why now, and why report-only.** It is pure local CPU, no LLM, and it gives the **before** number
that G3's effect will be read against. **But it is one-sided on this graph**: the §G plan itself says
§I21 (TOC concepts in the graph) "is a prerequisite for good communities, since TOC concepts are
exactly the noise that fragments them". So a **PASS is trustworthy** (Q beats the null despite the
noise) and a **FAIL is confounded and proves nothing**. Recorded as a one-sided result; do not let a
FAIL kill G2.

**Verifier:**
1. Both numbers reported — `Q(observed)` and `Q(rewired null)` — never the former alone.
2. The null is **reproducible**: fixed seed, run twice, identical. A null that moves is not a null.
3. Every community asserted **connected** (Leiden's point vs Louvain).
4. The one-sided caveat is written into the output artifact itself, not only into the register.
5. Independent reviewer on the script.

**Artifacts:** `logs/p1/step10/g2_modularity_gate.py`, `g2_modularity_gate.json`, `.log`.

**Cost class:** local CPU, minutes. No LLM, no dependency.

---

## 5. The verifier at every stage — how, and its limits

Every stage above carries an independent reviewer, and the reviewer must be a **different model from
the author's**. Resolve it, do not infer it:

```bash
hermes config get delegation            # expect: openai/gpt-oss-20b, provider custom, fallback []
cat ~/.hermes/cache/delegation/live/<deleg_id>/manifest.json   # what a child ACTUALLY ran on
```

Both children on 2026-10-20 ran `openai/gpt-oss-20b` against a parent of
`deepseek/deepseek-v4.1-flash` — genuinely independent. **⚠️ HANDOFF's "Verifier model" row said the
opposite and was wrong** (corrected 2026-10-20; it read a commented *template* line as the live
value). Re-check the pin before trusting any `passed: true`.

**Two limits, measured 2026-10-20, that a green verifier does not cover** (§I31 trap 5):
- **A verifier buys consistency-checking, not metric critique.** An independent pass verified 8/8
  claims including a number that was **wrong** (6,328 vs the true 6,327), because the artifact was
  internally consistent. It also misattributed fields to the wrong artifact and wrote arithmetic that
  does not compute while reaching the right answer.
- **A number registered from a probe dies when the probe changes.** 6,328 was registered from a
  *pre-guard* run. Rule (§I31 trap 4): on any probe change, re-run and re-check **every** number
  already registered from it; prefer registering only once the script is frozen.

So for A1–A4: the reviewer is a check, and **re-running the script and re-deriving the metric is the
evidence**. Capture raw output to the named artifact path and read it back.

**Reviewer transport limit:** the cluster reviewer has been observed to reject a request after ~25
tool calls in one session (its own control tokens leak into the replayed history). Keep child briefs
to ~8 tool calls; a mid-run protocol failure is **no verdict**, never a pass. Budget `max_tokens` for
the hidden reasoning — a reasoning reviewer can return `finish_reason: length` with empty content.

---

## 6. STOP POINT, and the decisions this plan needs from the owner

**STOP after A4.** Report the four artifacts, then re-plan. **B1 (the §G3 merge) is not authorised by
this document.**

### B1 — the §G3 merge (LATER, separate gate, destructive)

Not started, and it needs **all** of the following first:

1. **A1's baseline exists** — otherwise there is no "before" to read the merge against.
2. **The §I21 decision (owner).** The Phase 3 graph build does not apply the E5 content filter, so the
   graph carries TOC concepts. §I21 is "a prerequisite for good communities". Fixing it means a
   **graph rebuild** — 3,796 concept-extraction LLM calls, which §I23 measured at **16 h 25 m** on
   this shared cluster, and budgeted in **days**. So: fix §I21 first (and redo the merges on the
   rebuilt graph), or accept G3 on the current graph and accept that its merges are redone later?
   **This is the fork, and it changes whether B1 is worth doing at all.**
3. **A dry-run that names every merge and marks the survivors** (§I31 trap 1: normalisation groups
   are *not* synonym sets — `['velocity', 'Velocity', 'Velocity = √(g h)']`; and trap 2: substring
   matching must not be used — 809 substring pairs are mostly distinct concepts). 1,186 groups is too
   many to eyeball; the top ~50 carry most of the measured gain (§I30), so review is budgeted there.
   If the dry-run cannot produce the exact merge list, it is not ready to run.
4. **Two separate gates**: the merge is additive-and-reversible (aliases preserved, every merge
   logged) but it *retires* nodes, so the destructive half gets its own approval. Never `--force`.

### Decisions needed now

| # | Question | Why it is blocking |
|---|---|---|
| **D1** | §I21: rebuild the graph with the content filter before G3, or run G3 on the current graph? | It decides whether B1 is worth doing, and whether the merges are throwaway |
| **D2** | Approve A1–A4 as scoped, or drop any of them? | A2/A3 are not on G3's critical path — A2 unblocks the preflight gate, A3 only helps future runs |
| **D3** | The untracked `.hermes/plans/2026-10-18-p1-graph-analytics-plan.md` carries the G3-verifier rewrite; commit it, or let it ride with the other session's work? | An untracked plan is invisible to a fresh clone |

### Parallel track — needs only the owner, no machine

**Session 5 / Task 7 (human verification).** `data/gold_v2_review.md` exists (30 queries, 6 per
stratum, written 2026-10-17); fill it in, then `uv run python scripts/score_review_sheet.py`. Protocol
in `.hermes/plans/2026-10-16-p0-9-5-verification-protocol.md`. This is the only P0-9 task that needs
nothing but a human, and it has been open since 2026-10-17.

---

## 7. Working-tree state at the time of writing

**Committed:** `758630e` `[verified]` — the §G3 probes, §I29/§I30/§I31, the §I2/§G corrections,
HANDOFF's verifier-model correction.

**Untracked / modified, NOT mine — another session's in-flight work, leave alone:**
`ARCHITECTURE.md`, `data/eval_queries_v2.json`, `scripts/build_gold_v2.py`,
`src/pdf_ingestion/embed_cache.py`, `src/pdf_ingestion/late_chunk_embedder.py`,
`tests/test_embed_cache.py`, `data/eval_results/p1-step10-retrieval-only_2026-10-20_0411.md`,
`logs/p1/step8-run/probe_cache_hit*`, and the `.hermes/plans/2026-10-18-*` plans (D3).

**Clean and therefore safe to edit:** `src/pdf_ingestion/store.py` (A3), `scripts/preflight.py` (A2).
