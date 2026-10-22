# P1 graph lanes — execution index, order, and parallelization. Written 2026-10-22.

> **FOR SIGNOFF.** This is the *order* across the three phase plans; each phase's own plan carries its
> verifiers. Nothing here has been run.

---

## The lanes, and what can run together

    ┌─ Lane A ─ derivative_artifacts drop+recreate ──────────────┐  independent of everything else
    │  (2026-10-22-p1-i12-…-plan.md §3)                          │  → START NOW, in parallel
    └───────────────────────────────────────────────────────────┘
    ┌─ Lane B ─ concept_embeddings drop + Phase-3 rebuild ──────┐  independent of Lane A
    │  (2026-10-22-p1-i12-…-plan.md §4)                          │  → START NOW, in parallel with A
    └───────────────────────────────────────────────────────────┘
                          │
                          ▼  (Lane B MUST land before §G3 — §I12 plan §6)
    ┌─ §G3 ─ entity resolution + concept_embeddings sync ──────┐  single-writer on Memgraph
    │  (2026-10-22-p1-g3-entity-resolution-plan.md)             │  → serial; after Lane B
    └───────────────────────────────────────────────────────────┘
                          │
                          ▼  (G2 computes communities on the MERGED node set)
    ┌─ §G2 ─ community detection + summaries ──────────────────┐  the expensive phase; LLM-bound
    │  (2026-10-22-p1-g2-community-summaries-plan.md)           │  → serial; its gate runs first
    └───────────────────────────────────────────────────────────┘

**Read-only work that can run at any time, beside anything (LLM-free):**
- §G3-0 — re-measure the lever on the rebuilt graph (probe).
- §G2-0 — the modularity gate (probe).
- `preflight.py`, and the before-arm probes for every verifier below.

**The only real contention is the cluster LLM endpoint** (`10.0.10.70:8000`). §I23 measured that
shared-GPU contention collapsed a build's throughput ~8×, so **§G2's summarization must not run beside
another LLM-heavy phase** (a card re-run, another graph build).

---

## The critical path

    Lane A  ─┐
             ├─ (parallel, ~minutes–tens of minutes)
    Lane B  ─┘ ──▶ §G3 ──▶ §G2

Lane B is the one that gates §G3. Lane A is off the critical path entirely — it can run first, last,
or beside the others.

---

## Why Lane B gates §G3 (the "paid twice" rule)

- §G3's merge target list **is** the concept set. Lane B's rebuild **rewrites** that set.
- So a merge computed before Lane B is discarded by Lane B → paid for twice.
- And a merge after Lane B makes `concept_embeddings` stale again → §G3 must sync it (V6 in the §G3 plan).

Same reasoning as the register's D1 block: *the gate that releases §G3 is the rebuild landing.* Lane B
**is** that rebuild.

---

## Open owner decisions this index depends on

| # | Decision | Blocks | Where |
|---|---|---|---|
| A-decide | Which document does the DA lane serve? (pre-registered default: `--doc-id 7ba61432-…`) | Lane A | §I12 plan §3 |
| v (HANDOFF) | Clear `concept_embeddings` as part of the rebuild? | Lane B | **answered yes by this plan** — the move requires it |
| — | §G2 gate: build or not? | §G2 | decided by §G2-0's measurement, pre-registered in the §G2 plan |

---

## What is NOT covered here

- **§I34** (re-ingest transition reports the graph lane as SKIP — non-blocking or hard blocker?).
- **§A3** (card volume vs quality).
- **The full Phase-1 re-ingest** (E1/E2/E3 + §E5 + §D4) — gates the card/retrieval lanes and the
  reranker ablation (§D13). None of the three plans above requires it.
- **§G5** (genuine multi-hop) and **§G4** (query modes) — after §G2.

---

## ⚠️ These plan files are LOCAL-ONLY until committed

`git status` shows them untracked. A fresh clone will not have them. Commit them (or the handoff
pointer is broken) — see `project-continuity` pitfall 11.
