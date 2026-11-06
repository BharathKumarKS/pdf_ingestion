# P1 — THE VISUAL-LANE APERTURE — V1 / V2 pre-registration

> **Written 2026-11-06, BEFORE the run.** Per **D6.1** it is **committed ALONE**, and nothing measured
> is in it. Read first: `IMPROVEMENTS.md` **§I107** (the measurement), **§I123** (the correction of the
> record), and the plan `.hermes/plans/2026-11-06-p1-visual-lane-aperture-SESSIONS.md` §2 (steps) and
> §4 (decisions).

---

## 1. The question

§I107 measured that the visual lane's aperture — a raw **mean-best-cosine** bar
(`cfg.visual_score_threshold = 0.58`) — **cannot separate** in-domain from near-domain: a near-domain
image (H 2p orbital, top-1 **0.5609**) outscores the weakest in-domain concept (**0.4936**); verdict
**`separating: NONE`**. That measurement kept only the **top-1** cosine per query.

> **Does any of {top1, margin, z-score} separate in-domain from near/far-domain — and does the answer
> differ by MODALITY (image vs text)?**

This run is the **capture (V1)** plus the **statistic re-derivation (V2)** that answers it. It is
**read-only** and runs entirely on the **local** ColPali embedder + Qdrant — **no cluster**.

---

## 2. What this IS, and IS NOT

| | |
|---|---|
| **IS** | a **read-only** capture of the full per-query score distribution for BOTH modalities, then a read-only re-derivation of three statistics and their separation verdicts, **per modality**. |
| **IS** | local `get_colpali_embedder(cfg)` + `store.visual_search` only. |
| **IS NOT** | a store write, a re-ingest, a `src/` change, a threshold change, or a cluster call. |
| **IS NOT** | the aperture itself (that is V4, on a calibration set) — V1/V2 measure; they do not tune. |

⚠️ **The two modalities are captured SEPARATELY and must not be pooled.** `store.visual_search`
divides the MaxSim sum by the **query's own patch count** (§B4e): an image is a fixed ~1031-patch grid;
a short text query yields far fewer patches, so the mean-best-cosine sits on a **different scale**. A
pooled test would average the two populations and could miss a working statistic in both.

---

## 3. The probe set

**Image modality** (the §I107 set — the reproduction anchor):
* **in-domain** — 12 page images of the OLD doc `b2d9fb56…` (`data/page_images/b2d9fb56…/page_NNNN.png`,
  pages 50,100,200,300,400,500,600,700,800,900,940,960): a real cross-render test (old images are
  Docling-rendered; the current doc's are PyMuPDF@150dpi).
* **in-concept** — the 8 `logs/p1/step10/concept_images/in_*.png` (SYNTHETIC matplotlib figures —
  in-domain by *topic*, not by *appearance*; ⚠️ recorded as a limitation, §I107).
* **near-domain** — the 4 `near_*.png` (physics-looking, topic NOT in Vol 1).
* **far-domain** — the 2 `far_*.png` + the 3 `sv_ray_cluster_access/**` files (logos / photos).

**Text modality** (this is NEW — §I107 had no text capture):
* the 8 concept descriptions (the §I107 `CONCEPTS` text strings), and
* the 33 `vis-*` query texts from `data/eval_queries_v2_visual.json`.

⚠️ The text groups are **in-domain only** (concept descriptions + real figure-seeking queries). A text
**near/far** group is deliberately NOT invented here — that is V3's job (a labelled set with provenance).
⇒ **V2's text-modality separation test is bounded**: it reports the text score *distribution* and its
statistics, and any separation claim for text is **provisional until V3 supplies near/far text inputs**.

---

## 4. The capture (V1)

Per probe item, at **`score_threshold = 0.0`** and **`limit = 2001`** (the full visual index; no
truncation at the 0.58 default):

```
image: q = colpali.embed_query_image(pil)          -> (N_patches, 128)
text:  q = colpali.embed_query_text(description)   -> (N_patches, 128)
hits = store.visual_search(query_patches=q, tenant_id=cfg.global_tenant_id,
                           limit=2001, score_threshold=0.0)          # ordered, descending
record: modality, group, label, n_query_patches, ordered [(page_number, score_cosine), ...]
```

Artifact: `logs/p1/step10/visual_aperture_v1.json` — one row per probe item, the **full ordered score
list**, so every V2 statistic is re-derivable from the raw array and never recomputed ad hoc.

---

## 5. The statistics (V2) and their falsification clauses (FIXED BEFORE the run)

For a query's ordered score list `s` (descending), and `μ/σ` its own mean/SD over the corpus:

| statistic | definition |
|---|---|
| **top1** | `s[0]` |
| **margin** | `s[0] − s[1]` |
| **z** | `(s[0] − μ) / σ` |

**Separation rule (per statistic S, per modality M).** Let `IN` = the in-domain groups of modality M,
`OUT` = the near ∪ far groups of modality M. **S separates iff `min_S(IN) > max_S(OUT)`.** If no
threshold lies between them, S **does not separate** for (S, M) — reported as **`no-separation`**.

⚠️ **`no-separation` is a REDIRECT, not a closure** (plan §4). It moves the search to the next
statistic; if the statistic space is exhausted it escalates to a **feature** change (a wider patch dim →
a re-embed) as a product decision. The plan may not close by declaring no-separation, and may not ship a
threshold the evidence does not support.

**The self-match question (settled here).** For each in-domain **book page** query, record whether its
top-1 is **its own page at cosine exactly 1.0000** — the self-match signature §I123 flagged (the query
image IS the stored vector, so `in_book_page` is a **self-match test**, not cross-render proof). Record
it; do not silently read it as cross-render evidence.

---

## 6. Guards (each must be able to FAIL)

| # | check |
|---|---|
| **G1** | population: the image probe set is non-empty and matches the files present; the text probe set is **41** (8 concepts + 33 `vis-*`). |
| **G2** | **zero errors** across all probes. |
| **G3** | **threshold 0 honoured**: every recorded score list is non-empty AND contains at least one score **below 0.58** (proving the default was not applied). |
| **G4** | **read-only**: the `visual_knowledge_base` point count is **identical** before and after the run. |
| **G5** | `n_query_patches` is recorded per query and the **image vs text patch counts differ** (the §B4e scale fact, measured not assumed). |
| **G6** | the two modalities are captured **separately** (two labelled subsets; no pooled row). |

---

## 7. Verifier and mutation proof

* **Independent stdlib verifier** `logs/p1/step10/visual_aperture_v1_verifier.py` — re-derives every
  statistic (top1/margin/z) and each separation verdict **from the artifact's raw score arrays**, and
  re-checks G1–G6. No model.
* **Mutation proof** `logs/p1/step10/visual_aperture_v1_mutation.py` — one mutation per check; **no inert
  check** (every check reddened by ≥ 1 mutation).
* An **independent cross-family reviewer** (`openai/gpt-oss-20b`, read-only) on a compact extract.

---

## 8. Registration

On completion: an `IMPROVEMENTS.md` entry, the artifact, the run log, the verifier and the mutation
proof. **Read-only at run time.** ⚠️ **If a statistic separates, that is a candidate aperture — V4 must
still derive its threshold on a calibration set and validate on held-out images before anything ships.**
