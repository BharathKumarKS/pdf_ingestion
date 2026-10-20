# P1 Step 9 — Phase B (cards + RAPTOR). Execution plan.

> **Written 2026-10-19, after Phase A and Step 10 §2–§3 completed.** Read `HANDOFF.md` (current
> state) first, then `IMPROVEMENTS.md` §A3 / §F2 / §I9 / §I12 / §I23, and
> `.hermes/plans/2026-10-18-p1-step9-downstream-pulled-forward-plan.md` (the parent plan — its
> "Phase B" section is the sketch this file makes executable).
>
> **Owner decisions taken 2026-10-19 (do not re-litigate):**
> 1. **Concurrency — option (b): start at 16 effective and ramp on measured throughput.**
>    `CARD_GEN_WORKERS=2` (2 chunk-workers × 8 card types = 16). **Already set in `.env`**;
>    backup at `.env.phaseb.bak`. Ramp only with sustained-load evidence (§I18).
> 2. **The one-chunk probe was run first (B1)** — it passed; see below.
> 3. **This runs in a FRESH session.** Do not continue it inside the §3 session.

---

## ⛔ SETTLED — SUPERSEDES (2026-10-20). **This block wins on conflict with anything below it.**

Phase B was **attempted on 2026-10-19 and ABORTED** at B2/B3 (74 of 3,791 chunks in 60 min, killed
by hand; the abort was clean — 0 cards, 0 RAPTOR nodes). Three findings came out of it, all now
registered in `IMPROVEMENTS.md`, and the code has changed. Read this before working any task below.

| # | Supersedes | What is true now |
|---|---|---|
| **S1** | **Owner decision 1** (concurrency): *"start at 16 effective and ramp on measured throughput"*, and `.env` `CARD_GEN_WORKERS=2` | **Measured 2026-10-20 by a controlled sweep, not by a burst probe: run at `CARD_GEN_WORKERS=4` (32 in-flight).** `.env` is **set to 4** (backup `.env.phaseb-w4.bak`). Throughput **scales** with concurrency and never collapses — **3.18 chunks/min at 1, 6.52 at 2, 9.39 at 4**, with **zero failed chunks and zero LLM failures** in all six cells. **ETA 3,791 chunks: ~19.9 h / ~9.7 h / ~6.7 h.** `workers=8` was **not** tested and the trend was still rising at 4. §I26 |
| **S2** | **B2's ramp rule and its ceiling** — *"raise one step at a time … the Session 3 ramp-probe knee was 4.21 calls/s; that is the ceiling"* | **The 4.21 calls/s ceiling does not apply to cards.** It was measured for the **VLM judge** (one page image, ~0.8 s/call) — a different model, prompt shape and response length. **A knee belongs to one model + one prompt on one server.** The card knee is unmeasured above 32 in-flight. The ramp is no longer performed on the real run (it discards the run to change the count) — it is measured by `logs/p1/step10/probe_card_throughput.py` **before** launch. §I18, §I26 |
| **S3** | **B1's latency datapoint** — *"single-chunk latency ≈ 12.3 s at 8-way concurrency … → ~6.5 h if latency holds"* | **A one-chunk probe is a burst, and it was ~8× optimistic.** Sustained p50 is **64–105 s per chunk** at every concurrency tested. **Do not plan against a one-chunk number again** (§I18's rule, applied to cards). |
| **S4** | **B4 check [1]** — *"the run log has no `Failed:` row"* | **That check was VACUOUS and has been REPLACED in `verify_phaseb_cards.py`.** The generator swallows failures **per card type**, one level deeper than the plan's fact (ii) says, so a total card loss produced **zero `Failed:` rows** (measured: 16 `LLM CALL FAILED`, 16 card-type failures, 0 `Failed:` rows). Check [1] now reads the generator's closing line — which must be **present** and read **0 failed chunks / 0 failed card-type calls / 0 LLM failures** — and fails on the "Card types that failed at least once" warning. Self-tested against the aborted log (FAIL), a synthetic clean log (clean), a synthetic failing log (FAIL) and a log with no closing line (FAIL). §I25 |
| **S5** | **Fact (ii)** — *"a per-chunk exception is swallowed"*, and the premise that the phase writes once with no resume | Both are fixed in code. Failures are now **counted** and surface in `generate_phase2_artifacts`'s result as `failed_card_types` / `failed_chunks`, and `run_phase2.py` prints a red **"Card types failed"** column. The card phase is **checkpointed and resumable** (`data/card_cache/`, §I27) and every LLM call has a **300 s total-request deadline + bounded retry** (§I24) — so an abort now costs the chunks since the last checkpoint, not the whole run. |
| **S6** | **P5's precondition row** — *`.env CARD_GEN_WORKERS=2` in force* | `.env` now reads **`CARD_GEN_WORKERS=4`**, and `run_phaseb.sh 4` must be passed to match, or the B0 gate will refuse (correctly). |

**What is NOT changed:** the scope (cards + RAPTOR for doc `7ba61432` only), B0's settings gate, B0b's
live preconditions, B1's one-chunk probe as a *liveness* check (its latency is no longer used for
planning), B3's single-write-point property, and B5/B6's RAPTOR and card-reading verifiers.

## 0. What is already measured (do not re-derive)

From `logs/p1/step10/probe_phaseb_scope.py` → `phaseb_before.json`:

| quantity | value |
|---|---|
| chunks in doc `7ba61432` | 3,796 |
| **content chunks (the card denominator)** | **3,791** (5 skipped: pages 2,3,9,13,14) |
| **LLM calls ≈** | **3,791 × 8 = 30,328** |
| cards per chunk, old doc | **16.3** (82,164 active / 5,048) — `question` + `factoid` are multi-card |
| → expected card count | **~60–76k** (B1 measured 20 cards from one chunk) |
| chunks > 512 tokens (reranker window) | **6 of 3,796 (0.16%)**, max 1,347 — §H's old figure was 57/5,048 (1.13%), max 1,701 |
| `knowledge_base_v2` | **3,796 points**, vectors `[colbert, dense_1024, dense_64]`, `raptor_summary` 0 |
| active cards / RAPTOR nodes for this doc | 0 / 0 (clean start) |
| old doc's active cards | 82,164 (must be untouched) |

From `logs/p1/step10/probe_phaseb_card_one_chunk.py` → `phaseb_card_probe.json` (**B1 PASS**):

- chunk index 449, page 109, 103 tokens → **20 cards in 12.3 s**
- **7/8 types** (formula 0 — nullable, and this chunk has no formula)
- `question` 7 cards, `factoid` 8 cards → the multi-card parsers are alive
- single-chunk latency ≈ **12.3 s at 8-way concurrency**, which is the ramp's first datapoint:
  ~0.16 chunks/s at 16 effective concurrency → **~6.5 h** if latency holds (it will not; that is
  why the ramp exists).

---

## 1. The two facts that shape this phase

**(i) The real concurrency is `card_gen_workers × |CardType|`, not `card_gen_workers`.**
`generate_cards_for_chunks` runs `card_gen_workers` chunk-threads; each chunk runs its 8 card types
in a nested `ThreadPoolExecutor(max_workers=8)`. At the old `.env` value of 8 that was **64**
concurrent calls against an endpoint that has degraded under load twice (§I18, §I23 — the graph
build collapsed 8× under shared-GPU contention). At 2 it is 16.

**(ii) `generate_cards_for_chunks` swallows per-chunk exceptions.**
It counts them into a local `failed` variable and logs it — **the process still exits 0**. So a
broken LLM yields zero cards reported as a completed run: the same shape as §I23's graph build,
which swallowed 44 real timeouts and printed "0 failed". Exit 0 is never evidence; B4 and B1 are.

---

## 2. Steps — each with its verifier

Every step stops the chain on a failed verifier. All artifacts go to `logs/p1/step10/`.

### B0 — Settings gate

```bash
bash logs/p1/step10/run_phaseb.sh 2      # arg = expected card_gen_workers
```

Prints the resolved settings and **asserts**: `collection == knowledge_base_v2`,
`qdrant_host == 10.0.10.65`, `card_gen_workers == <arg>`, no stub enabled.

**Verifier:** prints `ASSERTIONS OK`. Any assertion failure → stop.
*Why it is not ceremony:* `.env` silently overrode `config.py`'s default of 4 with 8 once already
and made Step 8 attempt 3 run at the wrong worker count while everyone believed 4.

### B1 — One-chunk card probe — ✅ **DONE, PASS**

`logs/p1/step10/probe_phaseb_card_one_chunk.py`. 8 LLM calls, seconds.

**Verifier (met):** ≥6 of 8 types produced a card; `question` and `factoid` each ≥1; no empty
content; 0 cards → STOP. Result: 20 cards, 7/8 types, both multi-card parsers alive.
**Re-run it if anything about the card pipeline changes** — it is the cheapest way to catch a
broken generator before committing hours.

### B2 — Concurrency — ✅ **DECIDED (option b)**

`CARD_GEN_WORKERS=2` in `.env` → 16 effective. **Ramp rule:** raise one step at a time
(2 → 4 → 8) only after ≥5 minutes of sustained running at the current step with **0 errors**,
and record the observed chunks/s at each step. The Session 3 ramp-probe knee was **4.21 calls/s**;
that is the ceiling to compare against, not a target to assume.
**Verifier per ramp step:** sustained chunks/s over ≥5 min, 0 errors, and no fall in the rate over
the window (a falling rate is the endpoint degrading — revert the step).

### B3 — The run

```bash
bash logs/p1/step10/run_phaseb.sh 2       # background, notify on exit
  → uv run python scripts/run_phase2.py --doc-id 7ba61432-c5e0-416d-aecf-25a232523481
```

Output → `logs/p1/step10/phaseb_run.log`. Records the wall clock.
⚠️ **No checkpoint, no resume.** A crash loses the whole card run. `--raptor-only` exists for
RAPTOR; there is no cards-only equivalent.
⚠️ **Irreversible from here:** Phase B adds RAPTOR points to `knowledge_base_v2`, so Step 10 §2's
ablation numbers can no longer be reproduced from that collection. That is the accepted Order A
tradeoff, and it takes effect at B3.

### B4 — Verify the cards (SQLite)

```bash
uv run python logs/p1/step10/verify_phaseb_cards.py
```

**Verifier, exit 0 = PASS:** (1) no `Failed:` row in `phaseb_run.log`; (2) active cards exist and
every card's `chunk_id` resolves to a chunk of *this* document; (3) the distinct `card_type` set ==
the 8 in `CardType`; (4) cards/content-chunk ratio recorded (expected family ~16–20); (5) the
per-type distribution printed — `question`/`factoid` empty means a multi-card parser degraded;
(6) the old doc's 82,164 active cards unchanged.

### B5 — Verify RAPTOR + the invariant it breaks

```bash
uv run python logs/p1/step10/verify_phaseb_raptor.py
```

**Verifier, exit 0 = PASS:** (1) active RAPTOR nodes > 0, levels within `raptor_max_levels`;
(2) `knowledge_base_v2` grew by exactly the node count and `source_type=raptor_summary` equals it;
(3) ⚠️ **lane composition per point kind** — RAPTOR points carry only `dense_64` + `dense_1024`
(no colbert, no sparse, §F2), so Step 8's "all four lanes on every point" check **would fail
spuriously**; assert chunk points keep 4 lanes and RAPTOR points have 2; (4) no RAPTOR point has a
zero `dense_1024` vector (§I9 — the reason `--raptor-only` exists); (5) report the SQLite-node vs
Qdrant-point gap (`save_raptor_tree` skips nodes whose embedding is `None`).

### B6 — Read the artifacts (the course's own requirement)

`Week_Plan/week-4-…`: *"Run both over a fifty-chunk sample. Then do the thing engineers skip and
should not: read the artifacts."*

Sample ~10 cards across types and inspect for **self-containment** (no dangling "it"/"this"),
**atomicity** (one fact per card), **faithfulness** (supported by its chunk).

**Verifier:** a written record of what was read and what was found. A pass on counts alone is not
acceptable; a card unsupported by its chunk is a defect even though it counts.
*Note:* the project has **no card faithfulness gate** (§A3), so this manual read is currently the
only faithfulness check that exists.

### B7 — Register

- **§A3** — the measured cards-per-chunk ratio (the card-volume-vs-quality question).
- **§F2** — confirm/correct the RAPTOR lane note (2 of 4 lanes).
- **§H** — correct the chunk-size row to the re-measured **6 / 3,796 (0.16%), max 1,347**.
- **§I12** — Phase B does **not** fix the 768d `derivative_artifacts` (that is Phase C); say so.
- **Step 9** — record the **cards + RAPTOR half** as done (the graph half landed in Phase A).
- **HANDOFF.md** — move "Current focus". Every number greps back to `logs/p1/step10/`.

---

## 3. Explicitly NOT in this phase

- **Phase C** (DA re-index, `scripts/index_derivative_artifacts.py --clear`) — this is what makes the
  DA lane live again (§I12). Its own plan.
- **Phase D** (ColPali visual re-index) — needs the PDF on disk; its own plan.
- **Phase E** — the authoritative `evaluate_rag.py` run, once DA / visual / graph are all about v2.
- **§F2** (RAPTOR hybrid retrieval), **§A1** (regenerate the `question` card type),
  **§I20** (`save_document` atomicity) — each its own item.
- **Any `src/` code change.** If a verifier fails, that becomes a register entry and a stop.

---

## 4. Preconditions — re-verify, do not assume

| # | Claim | Verified 2026-10-19 |
|---|---|---|
| P1 | Memgraph reachable, Bolt `localhost:7687` | ✅ (needed only by Phase E) |
| P2 | Qdrant `10.0.10.65:6333` reachable | ✅ 3,796 points in `knowledge_base_v2` |
| P3 | Cluster LLM `10.0.10.70:8000` answers | ✅ B1 produced 20 real cards |
| P4 | Embed endpoint `10.0.10.70:8123` reachable | ✅ (RAPTOR embeds summaries) |
| P5 | `.env` `CARD_GEN_WORKERS=2` in force | ✅ resolved settings show 2 (16 effective) |
| P6 | doc `7ba61432` has 0 cards / 0 RAPTOR nodes | ✅ clean start |
