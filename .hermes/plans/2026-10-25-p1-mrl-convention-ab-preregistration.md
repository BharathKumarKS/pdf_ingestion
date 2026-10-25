# P1 — PRE-REGISTRATION: the MRL truncation convention for the nomic 64d lane (signoff 4)

> **Written 2026-10-25 (session 18), BEFORE the run.** Nothing here has been executed. This is the
> spec; the harness is `logs/p1/step10/mrl_convention_ab.py` and must not exist before this file.
> Per §I61's precedent the pre-registration is committed **alone, before the run** — its sha256 is
> recorded in the run artifact's `meta` so "written first" is evidenced without relying on git.

---

## §0 — WHY THIS RUN EXISTS

Plan §1 **trap 4** and the plan's **§7 signoff 4**. The adopted embedder is
`nomic-ai/nomic-embed-text-v1.5` at 768d full / **64d** low. Two different functions produce a 64d
readout, and the project currently uses the first:

| | function | where |
|---|---|---|
| **A — the project's** | `x[:64]` then re-normalise | `cluster_embedder.mrl_slice`, `embedder.NomicEmbedder._truncate` |
| **B — Nomic's card** | `F.layer_norm(x, (768,))` → `x[:64]` → re-normalise | `nomic-ai/nomic-embed-text-v1.5` model card (verified live 2026-10-25) |

They are **not** the same function: measured on a random 768d probe, `cos(A, B) = 0.2616`. So the
choice matters for what the 64d lane contains.

**Owner decision 2026-10-25: measure it, do not decide it by argument** (signoff 4, answered
"measure both conventions on §I63's oracle first"). This document is that measurement.

**⚠️ What is already measured and must not be re-derived.** §I59 measured nomic's *plain-slice*
64d truncation penalty — full-dim vs 64d at R@1000 coverage — at **0.0128** (0.9352 → 0.9224), i.e.
nearly lossless, and **below the 0.020 resolution floor at n=133**. §I70's screen registered the
plain-slice 64d oracle row (this run's guard G1 anchors to it).

**⚠️ A correction to the register, recorded here because this run depends on it.** §I70's note says
the layer-norm variant "would need the **un-normalised** pooled vectors, which the cluster does
return but this probe discards". **That is not a blocker.** `F.layer_norm` with no affine weight is
pure standardisation, which is scale-invariant; measured, `layer_norm(raw)` and
`layer_norm(unit_normed)` agree at **cosine 1.000000000000000** (1e-15). The pipeline's normalised
vectors therefore suffice, and this run needs no new endpoint capability.

---

## §1 — INSTRUMENT

§I70's oracle screen (`logs/p1/step10/embedder_screen.py`), reused with its metric helpers **copied
verbatim** so the anchor guard can be an *exact* reproduction of a registered row:

* **Corpus fixed**: new doc `7ba61432`, **3,489** in-window chunks, filter == `store.py:336-369`.
* **Queries**: the 133 gold queries (`data/eval_queries_v2.json`, ids `gold-*`/`ovw-*`).
* **Scoring**: **exact brute-force cosine** over the whole corpus (page-deduped) — not Qdrant;
  §I60 measured up to 18.5 % of the pool lost to the filtered-HNSW path.
* **HyDE OFF**, no LLM calls, **no writes to any collection**.
* **One variable**: the 64d readout function. Both arms are computed from the **same** 768d nomic
  vectors (one cluster embed pass), so the model, the corpus, the prefixes and the query vectors are
  identical by construction.

## §2 — ARMS

| arm | readout |
|---|---|
| **A `nomic64_plain`** | `mrl_slice` — `x[:64]`, re-normalised (the project's convention, §I70's registered `nomic@64`) |
| **B `nomic64_layernorm`** | `layer_norm(x, 768)` → `x[:64]` → re-normalised (Nomic's card) |

## §3 — PRE-REGISTERED ENDPOINTS AND RULE

* **PRIMARY**: paired **ceiling-normalised R@20**, **arm B − arm A**, every-chunk pool (§I70's
  convention). This is the project's standing embedder endpoint (§I58/§I63/§I70/§I74), so the number
  is comparable to the register.
* **SECONDARY (the mechanism)**: the prefetch's own operating point — **ceiling-normalised R@1000
  over the top-1000-chunk pool** (`p1000_c1000`), i.e. the coverage the production funnel's
  `dense_64(prefetch=1000)` actually consumes. §I59's truncation penalty is stated on this quantity.
* **RULE — adopt Nomic's layer-norm readout iff BOTH hold**: the primary's 95 % CI **excludes 0**
  **AND** |Δ_primary| ≥ the run's own resolution floor (`1.96·SD/√133`, reported from the run).
  * If the primary is **unresolved**, or resolved but **sub-floor**, the honest statement is: *the
    convention does not move the 64d lane's ranking on this corpus*, the project keeps **plain
    slice**, and **§I59's rows are NOT re-measured** — a RESULT, not an unresolved one.
  * The secondary is reported and is **not** the endpoint; it is not switched after seeing numbers.
* **ONE run. No extension.**

## §4 — GUARDS (each must be able to fail)

| id | assertion |
|---|---|
| **G1** | arm **A** reproduces §I70's registered `nomic@64` **ceiling_norm** row EXACTLY (all four k: 0.364342 / 0.569055 / 0.916027 / 1.0) — pins the instrument to the register |
| **G2** | arm **A** reproduces §I70's `nomic@64` **ceiling_norm_top1000pool** row EXACTLY (R@500 0.915738, R@1000 0.918953) |
| **G3** | A-vs-A negative control: arm A computed twice is **bit-identical** (max_abs_diff 0.0) |
| **G4** | slice sanity: both arms are unit-norm; A is the **exact** truncation of the full vector; **A ≠ B** (else the contrast is vacuous) |
| **G5** | both arms rank the **same** `pages` array and see identical `n_relevant` |
| **G6** | every query that errors is **reported**, never silently dropped |

## §5 — WHAT THIS RUN DOES *NOT* LICENSE

* It is an **oracle screen**, not the product. It does not license a ship on its own.
* It does **not** re-open the embedder choice (§0) — nomic is adopted on cost (§I77), not on this.
* It does **not** touch the full-dimension lane; only the 64d readout is under test.

## §6 — THE DECISION'S BLAST RADIUS, EITHER WAY

* **Keep plain slice (A)**: zero change, §I59's rows stand, the deployed nomic `knowledge_base`
  (also plain slice) stays on the same convention. Cost: nothing.
* **Adopt layer-norm (B)**: `mrl_slice` and `NomicEmbedder._truncate` change together (index **and**
  query, so the lane stays self-consistent), and **§I59's nomic-64 rows must be re-measured** before
  any of them is quoted again.
