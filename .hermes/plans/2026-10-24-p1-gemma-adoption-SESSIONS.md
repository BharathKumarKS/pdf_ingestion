# P1 — SESSION BRIEF: the gemma adoption + re-embed

> **The plan is `.hermes/plans/2026-10-24-p1-gemma-adoption-and-reembed-plan.md`.** This file says
> **which slice each session owns**, so no session reads the whole plan (a 320-line plan is ~4k tokens
> nobody needs to re-read five times). Written 2026-10-24 (session 16), at the boundary.
>
> ⚠️ **Read the plan's §8 "VERIFIED AGAINST THE LIVE SYSTEM" once, first.** Four of the plan's literals
> were wrong and are corrected in place; §8 is the list, and it is the cheapest thing in this
> directory to read.

---

## §0 — BEFORE S1: five owner signoffs, and they are all upstream

The plan's §7 lists five decision points. **All five gate Stage A**, so none can be deferred into a
later session — A's code change depends on 1 and 2, B on 3, C on 4, and F on 5. Get them in one
sitting, in this order: **1** the low-lane name (`dense_low` recommended), **2** `dense_full` now or
deferred as debt, **3** build into a new `knowledge_base_v3` (recommended) keeping v2 live, **4**
**Shape B** (re-embed, ids preserved) vs **Shape A** (full re-ingest), **5** §I68 before Stage F or a
stated tolerance.

⚠️ **Decision 4 cannot be fully taken before S2's C0 measurement.** The plan recommends Shape B and
then requires C0 to time the late-chunk pass before committing — because Shape B's cost is
**derived, not measured**. So the honest sequence is: take 1, 2, 3, 5 now; take **4 provisionally**,
and confirm it at S2's gate with C0's number in hand.

---

## §1 — THE SESSIONS, BY KIND

The axis is **kind of work**, not task count: two of these invalidate everything above them, and one
is a background job that must never be a conversation.

| # | session | kind | owns | deliverable | definition of done |
|---|---|---|---|---|---|
| **S1** | **Stage A — the lane rename** | **Build (code only)** | the `dense_low` code change, the `_LOW_VECTOR_NAMES`/`_low_name_from()` pair, `dense_dim_low = 128`, the 18-file sweep | the code + tests | suite green; **each new test proven to discriminate by mutation**; committed with the plan item ticked |
| **S2** | **Stage B + C0 + the lane verifier** | **Build + Measure** | create `knowledge_base_v3`; **write `scripts/verify_collection_lanes.py`**; run C0 | v3 exists and is empty; the verifier script; **C0's measured seconds** | verifier B reads the **live** collection back; C0's number is recorded **with its unit (parents)**; owner re-confirms decision 4 |
| **S3** | **Stage C — the re-embed** | **Heavy run (background job)** | the late-chunk re-embed into v3 | the populated v3 + a run log | `chunk_id` set before == after (byte-identical); every **enabled** lane present on **every** point; A-vs-A bit-identical; the known-vector spot check reproduces the v2 value under the old model |
| **S4** | **Stage D + E** | **Model change + gate** | retrain the intent classifier; preflight | the new pickle; preflight exit 0 | `n_features_in_ == 768` and a held-out comparison reported; every lane asserted **by a real query** |
| **S5** | **Stage F + G** | **Heavy run (background job) + diagnostic** | the ONE pre-registered product-endpoint run; the §I66 decomposition | the pre-registration (**committed alone, first**) + the run + the register entry | the §I67 guard set, incl. **one exact reproduction of a registered v2 row**; the §I66 probe reproduces the v2 decomposition before being trusted on v3 |

⚠️ **S2 owns `verify_collection_lanes.py`, not S3** — the plan places it in Stage C, and that is
moved deliberately: **the heavy run must not also build its own gate.** A tool written inside the run
it is supposed to gate is a tool that gets written to pass.

⚠️ **S3 and S5 are background jobs, not sessions.** Launch detached writing to disk, **end the
session**, start the next one when the notification fires. A multi-hour run babysat in chat is a
multi-hour session paying context on every poll.

---

## §2 — THE AUDIT (two holes, both checked)

**Every task is owned by exactly one session.** ✅ Checked: the `verify_collection_lanes.py`
*script* and its *run* are both S2 (above). The Stage C harness (`reembed_chunks.py`, extended) is
**S2's to build and S3's to run** — ⚠️ that split is deliberate and must stay: S3 must not be editing
the harness it is running.

**Every session's inputs exist.** ✅ Checked against the live system 2026-10-24:

* **S1** — `store.py:451`/`:432` verified exact; the sweep surface is **33 literals across 18 files**
  (plan §8 lists them). `scripts/reembed_chunks.py`, `train_intent_classifier.py`, `preflight.py`,
  `reset_for_reingest.py` all **present**; `scripts/verify_collection_lanes.py` confirmed **absent**
  (S2 writes it).
* **S2** — the cluster is up (`10.0.10.70:8000` LLM, `:8123` embed) and Qdrant `10.0.10.65:6333`
  answers. `knowledge_base_v2` = 3,869 points, lanes `['colbert','dense_1024','dense_64']`
  ⚠️ **AND a fourth, `sparse`, which that listing misses because it lives in
  `params.sparse_vectors`, not `params.vectors` — 3,796/3,869 points carry real SPLADE vectors.
  `IMPROVEMENTS.md` §I76. Stage B declares FOUR lanes and carries `sparse` over by id.**
* **S3** — ⚠️ **the existing `data/embed_cache/` (874 dirs) CANNOT be reused**: `dense_dim_low` is in
  `_FINGERPRINT_FIELDS`, so the rename invalidates every entry. That is correct (the vectors change),
  but it must be in the cost, not discovered mid-run.
* **S5** — ⚠️ **the HyDE cache IS complete** — 127 entries covering exactly the **93 HyDE-eligible
  queries** (53 factual + 40 overview) of the 133. The 40 apparently-missing are all `multihop`, and
  `evaluate_rag.py:190` applies HyDE only to `factual`/`overview`. **Nothing to generate; do not
  extend it** (plan §8).

---

## §3 — RUN ORDER (concrete)

**S1**
```
unset PYTHONPATH
grep -rn '"dense_64"' --include=*.py . | grep -v '\.venv'     # the 33-literal sweep surface
# … the code change + tests …
uv run pytest tests/ -q -m "not slow"
```

**S2**
```
unset PYTHONPATH && export QDRANT_HOST=10.0.10.65 QDRANT_COLLECTION=knowledge_base_v3
# create v3 (drop-and-create; a vector dimension is immutable)
curl -s http://10.0.10.65:6333/collections/knowledge_base_v3 | python3 -m json.tool   # read the LIVE config back
uv run python scripts/verify_collection_lanes.py --collection knowledge_base_v3      # S2 writes this
# C0 — time the late-chunk pass on ~20 PARENTS (not chunks), then stop and report
```

**S3** — detached, logging to disk; **end the session after launching**:
```
uv run python -u scripts/reembed_chunks.py --collection knowledge_base_v3 … > logs/p1/step10/reembed_v3_$(date +%F_%H%M).txt 2>&1
uv run python scripts/verify_collection_lanes.py --collection knowledge_base_v3      # the gate
```

**S4**
```
uv run python scripts/train_intent_classifier.py …
uv run python scripts/preflight.py
```

**S5** — pre-register first, **commit it alone**, then run retrieval-only:
```
# commit the pre-registration ALONE, before the run
uv run python scripts/evaluate_rag.py …        # HyDE ON and frozen via data/hyde_cache/
```

---

## §4 — WHAT IS *NOT* IN THIS CHAIN, AND IS STILL RUNNING

⚠️ **These are independent lanes. Do not fold them in, and do not let them be forgotten:**

* **Arm 2 — `min_chunk_tokens`** is **pre-registered and ready**
  (`.hermes/plans/2026-10-24-p1-min-chunk-tokens-ab-preregistration.md`) and is **independent of the
  Shape A/B decision** — measured this session, it needs no re-parse and no re-chunk of the corpus
  (~3 s from stored payloads). It can run before, after or beside S1–S5. Its harness is not built.
* **§I68 — the client-side-RRF fix.** Its blast radius is now measured (`IMPROVEMENTS.md` §I68 §4a):
  one source file, **two test files that break by construction**, one harness
  (`scripts/funnel_boundary_recall.py`, which shares the defect). It is decision point 5 and also a
  precondition for a *clean* S5.
* **§I75 — the graph lane is up**, and §I56's DA lane and §G5/§I2 are untouched by it.
* **Housekeeping:** §I55's exclude-from-metrics follow-on, §I58's `gold-003` caveat, §I53 item 6, and
  **committing sessions 13–16** (still uncommitted).
