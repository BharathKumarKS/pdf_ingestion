# P1 — SESSION BRIEF: the nomic adoption, the re-ingest, and the fine-tune

> **The plan is `.hermes/plans/2026-10-25-p1-nomic-adoption-reembed-and-finetune-plan.md`.** This file
> says **which slice each session owns**, so no session reads the whole plan.
> **⚠️ Supersedes `.hermes/plans/2026-10-24-p1-gemma-adoption-SESSIONS.md`** — the gemma plan and its
> brief are kept, not deleted: the gemma plan still holds the **Stage A work that is in force** and the
> evidence this one reverses. Read the nomic plan's **§0** before assuming anything in either is dead.
>
> ⚠️ **Read the plan's §1 "the four traps" once, first.** They are the whole risk surface: the missing
> document-side prefix, its collision with late-chunk offsets, the alignment rule, and the MRL
> convention. Three of the four bite **silently**, which is why they are traps.

---

## §0 — BEFORE S1: the signoffs that are still open

The plan's §7 lists six. **Two are taken** (nomic over gemma; `dense_dim_low = 64` / lane `dense_64`)
and **two are taken from the gemma plan's list** (§I68 before Stage F; commit in per-item style).
**Three are open and gate the work below:**

* **4 — the MRL truncation convention** (plan §1 trap 4): keep the project's plain slice + re-normalise,
  or move to Nomic's `layer_norm`-then-slice? ⚠️ **It changes every 64d number**, and the 64d lane is the
  funnel's first stage. Moving it means re-measuring §I59's rows. **This gates S3** (the re-embed).
* **6 — the fine-tune's validation split** (by document/passage, not by card). **Gates S6.**
* **3 — Shape B vs Shape A** — ⚠️ **provisional**, confirmed at S2's C0 with the measured number.

---

## §1 — THE SESSIONS, BY KIND

| # | session | kind | owns | deliverable | definition of done |
|---|---|---|---|---|---|
| **S1** | **Stage A2 + A2b** | **Build (code)** | the nomic `.env` config; the **document-side prefix**; the prefix/offset wiring in `LateChunkEmbedder`; the **model-aware** `_content_tokens` | the code + tests | resolved config prints all four values; **the span-invariance guard passes** (trap 2); the alignment rule is **probed, not assumed**; each guard proven to discriminate by mutation |
| **S2** | **Stage B + C0** | **Build + Measure** | drop the gemma-shaped v3; create it with the §2 schema; run C0 | v3 exists and is empty; **C0's measured seconds** | the LIVE read-back matches §2 (`dense_64` 64, `dense_full` 768); C0's four guards pass; the number is recorded **with its unit (parents)**; owner re-confirms signoff 3 |
| **S3** | **Stage C — the re-embed** | **Heavy run (background job)** | the late-chunk re-embed into v3 | the populated v3 + a run log | `chunk_id` set before == after (byte-identical); every enabled lane on every **required** point; A-vs-A bit-identical; the known-vector spot check reproduces the v2 value under the old model |
| **S4** | **Stage D + E** | **Model change + gate** | retrain the intent classifier; preflight | the new pickle; preflight exit 0 | `n_features_in_ == 768` and a held-out comparison reported; every lane asserted **by a real query** |
| **S5** | **Stage F + G** | **Heavy run + diagnostic** | §I68's client-side-RRF fix; the ONE pre-registered product-endpoint run; the §I66 decomposition | the pre-registration (**committed alone, first**) + the run + the register entry | the §I67 guard set incl. **one exact reproduction of a registered v2 row**; the §I66 probe reproduces the v2 decomposition before being trusted on v3 |
| **S6** | **the FINE-TUNE** | **GPU build + measurement** | the domain fine-tune of **off-the-shelf nomic** | the fine-tuned model + its §I70-instrument comparison | validated on §I63's oracle (133 gold queries); **split by document, not by card**; `MatryoshkaLoss` so the 64d lane survives; compared against **off-the-shelf nomic**, null reported as a null |

⚠️ **S3 and S5 are background jobs, not sessions.** Launch detached writing to disk, **end the
session**, start the next when the notification fires. A multi-hour run babysat in chat is a
multi-hour session paying context on every poll.

⚠️ **S2 owns the C0 run and S3 owns the harness** — deliberate and must stay: **a tool written inside
the run it gates is a tool written to pass.** Same reason `verify_collection_lanes.py` was pulled
forward out of Stage C (✅ already built and verified live).

---

## §2 — THE AUDIT (checked against the live system 2026-10-25)

**Every session's inputs exist.** ✅ Checked:

* **S1** — `cluster_embedder.py:169,300` (query instruction only — the missing document prefix is real);
  `late_chunk_embedder.py:117-143` (`_content_tokens` accepts only `n_local`/`n_local+1`);
  `embedder.py:161,180,186` (the LOCAL nomic prefixes both sides, as the reference implementation).
* **S2** — the cluster answers at `10.0.10.65:6333`; `v3` exists with the **gemma shape** and **0
  points** ⇒ **drop it**; `knowledge_base_v2` = 3,869 points, untouched.
* **S3** — ⚠️ **`data/embed_cache/` (874 dirs) CANNOT be reused** — the model and `dense_dim_low` are in
  `_FINGERPRINT_FIELDS`. Correct, but it belongs in the cost, not in a mid-run discovery.
* **S4** — `scripts/train_intent_classifier.py`, `scripts/preflight.py` present.
* **S5** — ⚠️ **the HyDE cache IS complete** (127 entries = exactly the 93 HyDE-eligible queries). The 40
  apparently missing are all `multihop`, which `evaluate_rag.py:190` never Hyde-ifies. **Nothing to
  generate; do not extend it.**
* **S6** — the training set is on disk: **75,645 cards, 29,321 of them `question`**, each paired with its
  source chunk. The fine-tune is not blocked on data.

---

## §3 — RUN ORDER (concrete)

**S1**
```
unset PYTHONPATH
# the .env config + the prefix/alignment build, then:
uv run pytest tests/ -q -m "not slow"
```
⚠️ **A2b changes the embedding, so nothing that depends on vectors may be built before it is green.**

**S2**
```
unset PYTHONPATH && export QDRANT_HOST=10.0.10.65
# drop the gemma-shaped v3 (empty), re-create with dense_64(64) + dense_full(768) + colbert + sparse
uv run python scripts/verify_collection_lanes.py --collection knowledge_base_v3   # read the LIVE shape
uv run python -u logs/p1/step10/c0_late_chunk_timing.py --parents 20             # then STOP and report
```

**S3** — detached, logging to disk; **end the session after launching**:
```
uv run python -u scripts/reembed_chunks.py --collection knowledge_base_v3 … > logs/p1/step10/reembed_v3_$(date +%F_%H%M).txt 2>&1
uv run python scripts/verify_collection_lanes.py --collection knowledge_base_v3   # the gate
```

**S4** — `train_intent_classifier.py` … then `preflight.py`.
**S5** — §I68's fix first, then pre-register, **commit it alone**, then run retrieval-only.
**S6** — the fine-tune on GPU; validate on §I63's oracle.

---

## §4 — WHAT IS *NOT* IN THIS CHAIN, AND IS STILL RUNNING

⚠️ **Independent lanes. Do not fold them in, and do not let them be forgotten:**

* **Arm 2 — `min_chunk_tokens`**: pre-registered (`.hermes/plans/2026-10-24-p1-min-chunk-tokens-ab-preregistration.md`)
  and **independent of Shape A/B** — it needs no re-parse and no re-chunk of the corpus (~3 s from stored
  payloads). ⚠️ **Its harness is NOT built**: `logs/p1/step10/min_chunk_tokens_ab.py` is an untracked
  **fragment** (re-chunks and prints child counts; **no endpoint, no artifact**, and its "verifier" reads a
  JSON nothing writes). Two delegated children misreported it. **Treat arm 2 as unstarted.**
* **§I68** — the client-side-RRF fix. Blast radius measured: one source file, **two test files that break
  by construction**, one harness. **S5's first job.**
* **§I56's DA lane**, **§G5/§I2** (`hop_distance` = constant 0), **§G2's V5 build** — all untouched.
* **Housekeeping:** §I55's exclude-from-metrics follow-on, §I58's `gold-003` caveat, §I53 item 6.
