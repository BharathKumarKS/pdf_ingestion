# P1 — §A: THE PER-SPACE QUERY-VECTOR FIX — one query vector per collection space (pre-registration)

> **Written 2026-11-01, BEFORE any code of this fix exists.** Per **D6.1** it is **committed ALONE**,
> and nothing measured is in it.
>
> Read first: `HANDOFF.md` (session 30/31), `.hermes/plans/2026-10-26-p1-nomic-full-lanes-and-fusion-plan.md`
> **§A**, `IMPROVEMENTS.md` **§I12/§D15** (the recorded symptom), **§I89** (the finding that made it
> matter), and `src/pdf_ingestion/store.py:792-824` + `graph_builder.py:663-696` (the two defect sites).

---

## 1. The defect

Both **derived** lanes take the **arm's** dense query vector and send it verbatim to a collection that
lives in a **different space**:

```
store.search_da(query_vector, ...)                 -> query_points(da_collection,      query=query_vector)
graph_builder._find_concepts_scored(query_vector)  -> query_points(concept_collection, query=query_vector)
```

`da_collection` (`derivative_artifacts`) and `concept_collection` (`concept_embeddings`) were built at
**768d** (the retired local Nomic model — `config.embedding_model` / `embedding_dim`), while the **dense
lane's** model (`config.dense_model` / `dense_dim`) is the arm's. A **1024-dim arm** therefore sends a
1024-vector to a 768-slot: Qdrant **400s**, the lane's `except` **swallows** it, and the lane is
**silently skipped** — indistinguishable from a lane that legitimately returned nothing.

⚠️ **Production is 768-dim, so production is unaffected.** It is the **v2/1024 *arm*** that is broken,
which is why Stage F had to turn both derived lanes **off** and narrow its question (§I89). §I12/§D15
recorded the symptom; it was never fixed.

---

## 2. What this IS, and IS NOT

| | |
|---|---|
| **IS** | a **product-path** fix: the two derived lanes embed **their own** query in **their own** space, resolved **off the collection**. Small, additive, and **inert when the arm's space already matches** (the production case). |
| **IS NOT** | a re-ingest, a model change, a collection write, or a retrieval-policy change. **Read-only at run time.** |
| **IS NOT** | a change to *what* each lane is asked. ⚠️ **The TEXT INPUT of each lane is preserved exactly** — only the MODEL that embeds it changes. The DA lane's text is the **HyDE hypothetical** (it is fused with the dense lane); the graph lane's text is the **raw query**. Swapping the text would change the lane's *meaning*, not its *space* — that is the trap this design exists to avoid. |

---

## 3. The fix — one query vector per space

**Resolution rule (fixed, not config-driven):** for a derived lane, read the **collection's** dense
vector dimension, then:

| case | action |
|---|---|
| the arm's vector width **==** the collection's width | **use the arm's vector** — no re-embed. ⚠️ This is what makes **A3** hold: the arm's vector already IS the lane's space, so the fix must be a **bit-exact no-op**. |
| the arm's vector width **≠** the collection's width, and the lane's **text** is available | **re-embed the lane's text** with the **derived** embedder (`embedder.get_embedder(cfg)` → `embedding_model`/`embedding_dim`), after asserting that embedder's width equals the collection's. |
| the widths differ and **no text** is available, **or** the derived embedder's width also differs | **RAISE**, naming the lane, both widths and the remedy — **never a silent `[]`**. |

⚠️ **The dimension is read off the COLLECTION** (`get_collection` → the dense vector's size), never from
`cfg.dense_dim`. A config default is exactly how this defect appeared (§I12's class).

**Call-site threading.** `search_da` and `graph_search` gain the lane's **text** (optional). The eval
path (`evaluate_rag.run_retrieval`) supplies it — the HyDE hypothetical for the DA lane, the raw query
for the graph lane — because the store cannot recover the hypothetical from the vector it is handed.
`None` preserves today's behaviour exactly, so no existing caller changes semantics.

---

## 4. Guards (each must be able to FAIL)

| # | check |
|---|---|
| **A1** | a **1024-dim arm** queries the 768-dim DA **and** graph lanes and gets **non-empty** results (today: `[]` on both, by the swallowed 400). |
| **A2** | the lane's query vector is **NOT** the arm's dense vector (different widths) — the fix actually **switched the space**. |
| **A3** | ⚠️ **the discriminating control:** an arm whose space **already matches** (nomic/768) is **bit-exact before and after** the fix on every lane metric. A fix that moves arm B has changed something other than the space. |
| **A4** | a deliberate mismatch with **no text** available (and a derived embedder that cannot match) **raises** — it is never a silent `[]`. |
| **A5** | the resolved width comes **off the collection**: pointing the helper at a collection of a different width changes the decision (so a config-derived width cannot pass). |

---

## 5. Deliverable and read rule

**Deliverable:** the code change, its tests, and a **read-only before/after probe** showing
**arm A's lane results go 0 → N** while **arm B's metrics are unchanged** (bit-exact, A3).

**Read rule (fixed):** A1/A2/A4/A5 are **binary** and must hold on the probe's population. **A3** is
**bit-exact** — any difference on any metric of any query VOIDs the fix. **Nothing is asserted about the
endpoint's quality**: this is a **defect fix that unblocks a measurement** (the lane-complete v2-vs-v3
A/B, §I89's T3), **not a retrieval improvement**.

---

## 6. Verifier and mutation proof

* **Independent stdlib verifier** `logs/p1/step10/per_space_verifier.py` — re-derives every check from
  the probe artifact's raw per-query records, and re-checks A1–A5 without importing the fix.
* **Mutation proof** `logs/p1/step10/per_space_mutation.py` — one mutation per check; **no inert check**.

---

## 7. Registration

On completion: an `IMPROVEMENTS.md` entry, a `HANDOFF.md` session-31 block, the probe artifact
`logs/p1/step10/per_space_probe.json`, and the tests. **Read-only at run time. No collection write, no
re-ingest.**

---

## 8. What would falsify this

* If A1 does not hold (arm A's lanes still empty), the fix does not address the defect.
* If A3 fails (arm B moves), the fix changed more than the space — **VOID**.
* If A4 cannot be made to raise, the silent-skip class is not closed and the entry must say so.
