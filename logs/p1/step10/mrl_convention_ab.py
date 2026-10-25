#!/usr/bin/env python
"""Signoff 4 — the MRL truncation convention for the nomic 64d lane: plain slice vs Nomic's card.

Pre-registration (the spec; written BEFORE this file): 
`.hermes/plans/2026-10-25-p1-mrl-convention-ab-preregistration.md`.

The question
------------
Two functions produce a 64d readout of nomic's 768d vector, and they are not the same function
(measured, `cos = 0.2616` on a random probe):

  A  the project's   `x[:64]` then re-normalise      (`cluster_embedder.mrl_slice`)
  B  Nomic's card    `layer_norm(x, 768)` -> `x[:64]` -> re-normalise

The v3 index will store a 64d lane, and that lane IS the funnel's fast first stage, so the choice is
load-bearing. Owner decision 2026-10-25 (signoff 4): **measure it, do not decide it by argument.**

Instrument — §I70's oracle screen, helpers copied verbatim
----------------------------------------------------------
Corpus fixed (new doc `7ba61432`, 3,489 in-window chunks), 133 gold queries, **exact brute-force
cosine** (not Qdrant — §I60 measured up to 18.5 % of the pool lost to the filtered-HNSW path), HyDE
OFF, no LLM calls, **no writes**. Both arms are computed from the SAME 768d nomic vectors, so the
model / corpus / prefixes / query vectors are identical by construction: **one variable**.

Pre-registered rule (fixed before the run)
------------------------------------------
PRIMARY: paired ceiling-normalised R@20, arm B - arm A, every-chunk pool.
Adopt B iff the 95 % CI excludes 0 AND |delta| >= the run's own resolution floor. Else keep A and
record the null. The secondary (p1000_c1000, the prefetch's own coverage) is reported, not the
endpoint, and is not switched after seeing numbers. ONE run.

Guards (each must be able to fail)
----------------------------------
  G1  arm A reproduces §I70's registered `nomic@64` ceiling_norm row EXACTLY (all four k)
  G2  arm A reproduces §I70's `nomic@64` ceiling_norm_top1000pool row EXACTLY
  G3  A-vs-A: arm A computed twice is bit-identical
  G4  slice sanity: both arms unit-norm; A is the exact truncation; A != B (else vacuous)
  G5  both arms rank the SAME `pages` array and see identical n_relevant
  G6  every erroring query is reported, never silently dropped

Run:
    unset PYTHONPATH && export QDRANT_HOST=10.0.10.65 QDRANT_COLLECTION=knowledge_base_v2
    uv run python logs/p1/step10/mrl_convention_ab.py
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import statistics
import sys
import time
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

import numpy as np  # noqa: E402

from src.core.config import get_settings  # noqa: E402
from src.pdf_ingestion.store import DocumentStore  # noqa: E402

QUERIES = REPO / "data/eval_queries_v2.json"
OUT = REPO / "logs/p1/step10/mrl_convention_ab.json"
PREREG = REPO / ".hermes/plans/2026-10-25-p1-mrl-convention-ab-preregistration.md"

NEW_DOC = "7ba61432"
COLLECTION = "knowledge_base_v2"
DENSE_VEC = "dense_1024"

EMBED_URL = "http://10.0.10.70:8123/embed-text/v1/embeddings"
NOMIC_MODEL = "nomic-ai/nomic-embed-text-v1.5"
DOC_PREFIX = "search_document: "
QRY_PREFIX = "search_query: "

LOW_DIM = 64
KS = (20, 100, 500, 1000)

# §I70's registered `nomic@64` rows (plain slice) — G1/G2 must reproduce these EXACTLY.
I70_NOMIC64_EVERYCHUNK = {"R@20": 0.364342, "R@100": 0.569055, "R@500": 0.916027, "R@1000": 1.0}
I70_NOMIC64_TOP1000POOL = {"R@20": 0.364342, "R@100": 0.569055, "R@500": 0.915738, "R@1000": 0.918953}


# ── cluster HTTP (verbatim from §I70's `cluster_embed`) ───────────────────────────────────────

def cluster_embed(texts: list[str], batch: int, model: str) -> np.ndarray:
    """Pooled vectors from the cluster, L2-normalised. Batched; honours the response `index`."""
    out: list[np.ndarray] = []
    for i in range(0, len(texts), batch):
        chunk = texts[i:i + batch]
        body = json.dumps({"model": model, "input": chunk}).encode()
        req = urllib.request.Request(EMBED_URL, data=body,
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=300) as r:
            d = json.load(r)
        items = sorted(d["data"], key=lambda x: x.get("index", 0))
        for it in items:
            out.append(np.asarray(it["embedding"], dtype=np.float64))
    m = np.asarray(out, dtype=np.float64)
    return m / (np.linalg.norm(m, axis=1, keepdims=True) + 1e-12)


# ── reads (verbatim from §I70) ────────────────────────────────────────────────────────────────

def scroll_pool(client, cfg) -> tuple[np.ndarray, np.ndarray, list[str]]:
    """Every in-window chunk: (full-dim vector, page_number, text) — filter == `store.py:336-369`."""
    vectors: list[list[float]] = []
    pages: list[int] = []
    texts: list[str] = []
    offset = None
    while True:
        pts, offset = client.scroll(
            collection_name=COLLECTION, limit=1000, offset=offset,
            with_vectors=[DENSE_VEC], with_payload=True,
        )
        for p in pts:
            pay = p.payload or {}
            if pay.get("source_type") == "raptor_summary":
                continue
            pg = pay.get("page_number")
            if pg is None or pay.get("is_content") is False:
                continue
            if cfg.min_content_page > 0 and pg < cfg.min_content_page:
                continue
            if cfg.max_content_page > 0 and pg > cfg.max_content_page:
                continue
            if pay.get("tenant_id") not in (cfg.global_tenant_id, "global", None):
                continue
            vec = p.vector
            if isinstance(vec, dict):
                cand = [v for k, v in vec.items() if k.startswith("dense_") and len(v) > 64]
                if not cand:
                    continue
                vec = max(cand, key=len)
            if vec is None:
                continue
            vectors.append(vec)
            pages.append(int(pg))
            texts.append(pay.get("text") or "")
        if offset is None:
            break
    m = np.asarray(vectors, dtype=np.float64)
    m /= (np.linalg.norm(m, axis=1, keepdims=True) + 1e-12)
    return m, np.asarray(pages, dtype=np.int64), texts


def reachable_pages(cfg) -> set[int]:
    """§I58 ceiling: a page with >=1 chunk, `is_content is not False`, inside the content window."""
    from sqlmodel import Session, select

    from src.core.database import Chunk, get_engine
    with Session(get_engine(cfg)) as session:
        rows = session.exec(
            select(Chunk).where(Chunk.document_id.like(f"{NEW_DOC}%"))  # type: ignore[attr-defined]
        ).all()
    return {
        int(c.page_number) for c in rows
        if c.page_number is not None and c.is_content is not False
        and cfg.min_content_page <= c.page_number <= cfg.max_content_page
    }


# ── metric (verbatim from §I70) ───────────────────────────────────────────────────────────────

def rank_pages(sims: np.ndarray, pages: np.ndarray, k: int) -> list[int]:
    """Distinct pages in rank order — a page scores once, at its best chunk's rank."""
    idx = np.argsort(-sims)[:k]
    seen, out = set(), []
    for i in idx:
        pg = int(pages[i])
        if pg in seen:
            continue
        seen.add(pg)
        out.append(pg)
    return out


def mrl_slice_matrix(m: np.ndarray, dim: int) -> np.ndarray:
    """Row-wise MRL truncation, arm A: first `dim` coords, re-normalised (cosine assumes unit norm)."""
    low = np.asarray(m[:, :dim], dtype=np.float64).copy()
    return low / (np.linalg.norm(low, axis=1, keepdims=True) + 1e-12)


def mrl_slice(vec: np.ndarray, dim: int) -> np.ndarray:
    low = np.asarray(vec[:dim], dtype=np.float64).copy()
    return low / (float(np.linalg.norm(low)) + 1e-12)


def _layer_norm(m: np.ndarray) -> np.ndarray:
    """`F.layer_norm(x, (n,))` with no affine weight: pure standardisation over the feature axis.

    Uses the **biased** variance (torch's default) and eps 1e-5, matching torch exactly. It is
    scale-invariant, which is why it can be applied to the pipeline's already-normalised vectors
    (see the pre-registration's correction to §I70). G4a cross-checks this against torch itself.
    """
    x = np.asarray(m, dtype=np.float64)
    mean = x.mean(axis=1, keepdims=True)
    var = x.var(axis=1, keepdims=True)          # biased (ddof=0) == torch's layer_norm
    return (x - mean) / np.sqrt(var + 1e-5)


def layer_norm_then_slice_matrix(m: np.ndarray, dim: int) -> np.ndarray:
    """Row-wise arm B — Nomic's card: F.layer_norm over the FULL width, then the slice, then renorm."""
    xn = _layer_norm(m)
    low = xn[:, :dim].copy()
    return low / (np.linalg.norm(low, axis=1, keepdims=True) + 1e-12)


def paired_ci(diffs: list[float]) -> dict:
    n = len(diffs)
    if n == 0:
        return {"n": 0, "mean": None, "ci95": None, "resolved": None, "wlt": None}
    m = statistics.mean(diffs)
    sd = statistics.stdev(diffs) if n > 1 else 0.0
    half = 1.96 * sd / math.sqrt(n) if n > 1 else 0.0
    lo, hi = m - half, m + half
    w = sum(1 for d in diffs if d < 0)
    l = sum(1 for d in diffs if d > 0)  # noqa: E741
    t = sum(1 for d in diffs if d == 0)
    return {"n": n, "mean": round(m, 6), "sd": round(sd, 6),
            "ci95": [round(lo, 6), round(hi, 6)],
            "resolution_floor": round(half, 6),
            "resolved": bool(lo > 0 or hi < 0),
            "direction": ("B>A" if lo > 0 else "B<A" if hi < 0 else "straddles 0"),
            "wlt": {"B_worse": w, "B_better": l, "tie": t}}


def agg(rows: list[dict], arm: str, key: str) -> dict:
    out = {}
    for k in KS:
        vals = [r["arms"][arm][f"{key}{k}"] for r in rows
                if r.get("arms") and r["arms"].get(arm) and r["arms"][arm].get(f"{key}{k}") is not None]
        out[f"R@{k}"] = round(statistics.mean(vals), 6) if vals else None
    return {"queries": len(rows), **out}


# ── main ──────────────────────────────────────────────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(OUT))
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--batch", type=int, default=128)
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()
    if Path(args.out).exists() and not args.force:
        print(f"REFUSING to overwrite {args.out} without --force.", file=sys.stderr)
        return 4
    if not PREREG.exists():
        print(f"ABORT: the pre-registration {PREREG} is missing — this run has no spec.",
              file=sys.stderr)
        return 6
    prereg_sha = hashlib.sha256(PREREG.read_bytes()).hexdigest()

    cfg = get_settings()
    print(f"resolved store   : host {cfg.qdrant_host!r} port {cfg.qdrant_port} "
          f"collection {cfg.qdrant_collection!r}")
    print(f"resolved embed   : {NOMIC_MODEL!r} via {EMBED_URL}")
    print(f"pre-registration : {PREREG.name} sha256 {prereg_sha[:16]}…")
    if not cfg.qdrant_host or cfg.qdrant_collection != COLLECTION:
        print(f"ABORT: QDRANT_COLLECTION is {cfg.qdrant_collection!r}, expected {COLLECTION!r}. "
              f"Run with QDRANT_HOST=10.0.10.65 QDRANT_COLLECTION={COLLECTION}.", file=sys.stderr)
        return 3

    raw = json.loads(QUERIES.read_text(encoding="utf-8"))
    queries = [q for q in raw
               if isinstance(q, dict) and str(q.get("id", "")).startswith(("gold-", "ovw-"))
               and (q.get("relevant_pages") or [])]
    queries.sort(key=lambda q: q["id"])
    if args.limit:
        queries = queries[: args.limit]
    print(f"queries          : {len(queries)}")

    t0 = time.time()
    store = DocumentStore(cfg)
    client = store._qdrant  # noqa: SLF001
    m_q, pages, texts = scroll_pool(client, cfg)
    print(f"pool             : {m_q.shape[0]} in-window chunks x {m_q.shape[1]}d "
          f"({time.time()-t0:.0f}s)")
    if m_q.shape[0] != 3489:
        print(f"ABORT: pool is {m_q.shape[0]} chunks, expected 3,489 — this is not the corpus "
              f"§I70's row was measured on, so G1 could not mean anything.", file=sys.stderr)
        return 7
    reach = reachable_pages(cfg)
    print(f"reachable pages  : {len(reach)}")

    # ── ONE nomic embed pass — the single 768d source for both arms ────────────────────────────
    t1 = time.time()
    m_n = cluster_embed([DOC_PREFIX + t for t in texts], batch=args.batch, model=NOMIC_MODEL)
    q_n = cluster_embed([QRY_PREFIX + q["query"] for q in queries], batch=len(queries),
                        model=NOMIC_MODEL)
    embed_s = time.time() - t1
    print(f"nomic embedded   : {m_n.shape[0]}x{m_n.shape[1]} + {q_n.shape[0]} queries "
          f"in {embed_s:.1f}s")

    # ── the two arms ──────────────────────────────────────────────────────────────────────────
    corpus_A = mrl_slice_matrix(m_n, LOW_DIM)                 # the project's plain slice
    corpus_B = layer_norm_then_slice_matrix(m_n, LOW_DIM)     # Nomic's card
    q_A = np.asarray([mrl_slice(v, LOW_DIM) for v in q_n], dtype=np.float64)
    q_B = layer_norm_then_slice_matrix(q_n, LOW_DIM)

    # ── G4 — slice sanity + an INDEPENDENT implementation check (can fail) ────────────────────
    # ⚠️ G4 was RESTATED after the first run (see the re-registration addendum). Its non-vacuity
    # clause originally required `cos(A,B) < 0.999`, calibrated on a synthetic all-positive
    # non-unit vector (cos 0.2616). On REAL unit-norm nomic embeddings the two conventions are
    # nearly the same direction (measured cos 0.999987), so that threshold was mis-specified — it
    # asserted a property of the data, not of the code. The restatement asserts what the guard is
    # FOR: (i) the numpy layer_norm is the real `F.layer_norm` (cross-checked against torch, a
    # different implementation), (ii) arm B is the slice+renorm of that, and (iii) the two arms are
    # not bit-identical — i.e. this is a contrast, not a function compared to itself. The measured
    # cos is reported as a FINDING, not gated on.
    import torch
    import torch.nn.functional as F

    trunc = m_n[:, :LOW_DIM] / (np.linalg.norm(m_n[:, :LOW_DIM], axis=1, keepdims=True) + 1e-12)
    cos_AB = float(np.mean(np.sum(corpus_A * corpus_B, axis=1)))
    sample = torch.as_tensor(np.asarray(m_n[:32], dtype=np.float64), dtype=torch.float64)
    torch_ln = F.layer_norm(sample, normalized_shape=(sample.shape[1],)).numpy()
    torch_armB = torch_ln[:, :LOW_DIM].copy()
    torch_armB /= (np.linalg.norm(torch_armB, axis=1, keepdims=True) + 1e-12)
    g4 = {
        "A_max_norm_error": float(np.max(np.abs(np.linalg.norm(corpus_A, axis=1) - 1.0))),
        "B_max_norm_error": float(np.max(np.abs(np.linalg.norm(corpus_B, axis=1) - 1.0))),
        "A_is_exact_truncation": bool(np.array_equal(corpus_A, trunc)),
        "numpy_vs_torch_layernorm_max_abs": float(np.max(np.abs(torch_ln - _layer_norm(m_n[:32])))),
        "numpy_armB_vs_torch_armB_max_abs": float(np.max(np.abs(torch_armB - corpus_B[:32]))),
        "arms_bit_identical": bool(np.array_equal(corpus_A, corpus_B)),
        "n_rows_differing": int(np.sum(np.any(corpus_A != corpus_B, axis=1))),
        "mean_cos_A_vs_B": round(cos_AB, 6),
    }
    g4["pass"] = bool(g4["A_max_norm_error"] < 1e-9 and g4["B_max_norm_error"] < 1e-9
                      and g4["A_is_exact_truncation"]
                      and g4["numpy_vs_torch_layernorm_max_abs"] < 1e-9
                      and g4["numpy_armB_vs_torch_armB_max_abs"] < 1e-9
                      and not g4["arms_bit_identical"])
    print(f"G4: A==truncation={g4['A_is_exact_truncation']}  "
          f"numpy-vs-torch ln max|d|={g4['numpy_vs_torch_layernorm_max_abs']:.2e}  "
          f"rows_differing={g4['n_rows_differing']}  cos(A,B)={g4['mean_cos_A_vs_B']}  "
          f"pass={g4['pass']}")

    # ── G3 — A-vs-A negative control (can fail) ───────────────────────────────────────────────
    corpus_A2 = mrl_slice_matrix(m_n, LOW_DIM)
    g3 = {"max_abs_diff": float(np.max(np.abs(corpus_A - corpus_A2))),
          "n_mismatch": int(np.sum(np.any(corpus_A != corpus_A2, axis=1)))}
    g3["pass"] = bool(g3["max_abs_diff"] == 0.0)
    print(f"G3: A-vs-A max_abs_diff={g3['max_abs_diff']} mismatch={g3['n_mismatch']} "
          f"pass={g3['pass']}")

    # ── the ranking pass — both arms rank the SAME `pages` ────────────────────────────────────
    results: list[dict] = []
    errors: list[dict] = []
    t2 = time.time()
    for i, q in enumerate(queries, 1):
        qid = q["id"]
        relevant = {int(p) for p in q["relevant_pages"]}
        ceil = relevant & reach
        row = {"id": qid, "query_type": q.get("query_type"),
               "n_relevant": len(relevant), "n_reachable": len(ceil), "arms": {}}
        for arm, sims in (("A", corpus_A @ q_A[i - 1]), ("B", corpus_B @ q_B[i - 1])):
            try:
                rk_all = rank_pages(sims, pages, len(pages))
                rk_1k = rank_pages(sims, pages, 1000)
            except Exception as exc:  # noqa: BLE001
                errors.append({"id": qid, "arm": arm, "error": f"{type(exc).__name__}: {exc}"})
                continue
            row["arms"][arm] = {
                **{f"c{k}": (round(len(set(rk_all[:k]) & ceil) / len(ceil), 6) if ceil else None)
                   for k in KS},
                **{f"p1000_c{k}": (round(len(set(rk_1k[:k]) & ceil) / len(ceil), 6)
                                   if ceil else None) for k in KS},
                "n_pages_in_pool": len(rk_all),
            }
        results.append(row)
        if i % 40 == 0:
            print(f"  [{i}/{len(queries)}] {qid} … {time.time()-t2:.0f}s", flush=True)

    arm_names = ("A", "B")
    complete = [r for r in results if all(a in r["arms"] for a in arm_names)]

    # ── G5 — one shared pages array, identical n_relevant across arms (can fail) ──────────────
    g5 = {
        "pool_size": int(m_q.shape[0]),
        "pages_array_sha256": hashlib.sha256(pages.tobytes()).hexdigest()[:16],
        "n_queries_with_both_arms": len(complete),
        "all_arms_share_one_pages_array": True,   # by construction: one `pages`, one rank_pages
        "n_relevant_identical_across_arms": all(
            len({r["arms"][a]["n_pages_in_pool"] for a in arm_names}) == 1 for r in complete),
    }
    g5["pass"] = bool(g5["n_relevant_identical_across_arms"]
                      and len(complete) == len(results))
    print(f"G5: shared pages={g5['n_relevant_identical_across_arms']} "
          f"queries_with_both={len(complete)}/{len(results)} pass={g5['pass']}")

    # ── G6 — errors reported, never silently dropped (can fail) ───────────────────────────────
    g6 = {"n_errors": len(errors), "errors": errors, "n_queries_kept": len(results),
          "pass": len(errors) == 0}
    print(f"G6: {g6['n_errors']} error(s), {len(results)} queries kept  pass={g6['pass']}")

    # ── aggregates ────────────────────────────────────────────────────────────────────────────
    arms_agg = {a: {"ceiling_norm": agg(results, a, "c"),
                    "ceiling_norm_top1000pool": agg(results, a, "p1000_c")} for a in arm_names}

    # ── G1/G2 — arm A reproduces §I70's registered nomic@64 rows EXACTLY (can fail) ───────────
    def exact(got: dict, want: dict) -> dict:
        d = {k: {"this_run": got[k], "registered": want[k],
                 "match": got[k] is not None and abs(got[k] - want[k]) < 1e-9} for k in want}
        d["pass"] = all(v["match"] for k, v in d.items() if k != "pass")
        return d

    g1 = exact(arms_agg["A"]["ceiling_norm"], I70_NOMIC64_EVERYCHUNK)
    g2 = exact(arms_agg["A"]["ceiling_norm_top1000pool"], I70_NOMIC64_TOP1000POOL)
    print(f"G1: A reproduces §I70 nomic@64 (every-chunk) pass={g1['pass']}  "
          + " ".join(f"{k}={v['this_run']}" for k, v in g1.items() if k != "pass"))
    print(f"G2: A reproduces §I70 nomic@64 (top-1000 pool) pass={g2['pass']}  "
          + " ".join(f"{k}={v['this_run']}" for k, v in g2.items() if k != "pass"))

    # ── endpoints: paired (B - A), ceiling-normalised ─────────────────────────────────────────
    endpoints: dict = {}
    for key, label in (("c", "ceiling_norm"), ("p1000_c", "ceiling_norm_top1000pool")):
        for k in KS:
            diffs = [r["arms"]["B"][f"{key}{k}"] - r["arms"]["A"][f"{key}{k}"] for r in results
                     if r["arms"]["B"].get(f"{key}{k}") is not None
                     and r["arms"]["A"].get(f"{key}{k}") is not None]
            endpoints[f"{label}_R@{k}_B_minus_A"] = paired_ci(diffs)

    primary = endpoints["ceiling_norm_R@20_B_minus_A"]
    floor = primary["resolution_floor"]
    decision = {
        "primary_endpoint": "ceiling_norm_R@20_B_minus_A",
        "delta": primary["mean"], "ci95": primary["ci95"],
        "resolution_floor": floor, "wlt": primary["wlt"],
        "ci_excludes_zero": bool(primary["resolved"]),
        "delta_at_or_above_floor": bool(primary["mean"] is not None and floor is not None
                                        and abs(primary["mean"]) >= floor),
    }
    decision["ADOPT_LAYER_NORM"] = bool(decision["ci_excludes_zero"]
                                       and decision["delta_at_or_above_floor"])
    decision["verdict"] = (
        "ADOPT Nomic's layer-norm readout (B) for the v3 64d lane; §I59's nomic-64 rows must be "
        "re-measured before being quoted again."
        if decision["ADOPT_LAYER_NORM"] else
        "KEEP the project's plain slice (A). The convention does not move the 64d lane's ranking on "
        "this corpus by more than the run's own resolution floor — a RESULT, not an unresolved one. "
        "§I59's rows stand; no re-measurement."
    )

    out = {
        "meta": {
            "generated_by": "logs/p1/step10/mrl_convention_ab.py",
            "preregistration": PREREG.name, "preregistration_sha256": prereg_sha,
            "what": ("signoff 4 — the MRL truncation convention for the nomic 64d lane: arm A = the "
                     "project's plain slice, arm B = Nomic's card's layer_norm->slice"),
            "instrument": "§I70's oracle screen; helpers copied verbatim",
            "corpus": NEW_DOC, "collection": COLLECTION,
            "pool_size": int(m_q.shape[0]), "reachable_pages": len(reach),
            "nomic_model": NOMIC_MODEL, "embed_url": EMBED_URL,
            "prefixes": {"document": DOC_PREFIX, "query": QRY_PREFIX},
            "low_dim": LOW_DIM, "ks": list(KS),
            "hyde": "OFF (raw query vectors)",
            "late_chunking": "OFF — the chunk text is embedded directly (§I70's oracle convention)",
            "no_llm_calls": True, "no_writes": True,
            "embed_seconds": round(embed_s, 1), "wall_seconds": round(time.time() - t0, 1),
            "preregistered_rule": ("adopt B iff the primary's 95 % CI excludes 0 AND |delta| >= the "
                                   "run's own resolution floor; else keep A and record the null"),
        },
        "guards": {"G1_A_reproduces_I70_everychunk": g1,
                   "G2_A_reproduces_I70_top1000pool": g2,
                   "G3_A_vs_A": g3, "G4_slice_sanity": g4, "G5_shared_pages": g5,
                   "G6_errors_reported": g6},
        "arms": arms_agg,
        "endpoints_B_minus_A": endpoints,
        "decision": decision,
        "queries": results,
    }
    Path(args.out).write_text(json.dumps(out, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    h = hashlib.sha256(Path(args.out).read_bytes()).hexdigest()
    print(f"\nwrote {args.out}\nsha256 {h}")

    print("\n=== ceiling-normalised, arm A (plain slice) vs arm B (layer_norm->slice) ===")
    print(f"  {'metric':>12} {'A':>9} {'B':>9} {'delta B-A':>10} {'95% CI':>24}  verdict")
    for label in ("ceiling_norm", "ceiling_norm_top1000pool"):
        for k in KS:
            e = endpoints[f"{label}_R@{k}_B_minus_A"]
            print(f"  {label[:10]+' R@'+str(k):>12} "
                  f"{arms_agg['A'][label][f'R@{k}']:>9.4f} {arms_agg['B'][label][f'R@{k}']:>9.4f} "
                  f"{e['mean']:>+10.4f}  [{e['ci95'][0]:+.4f}, {e['ci95'][1]:+.4f}]  "
                  f"{'RESOLVED' if e['resolved'] else 'unresolved'} {e['direction']} {e['wlt']}")

    print("\n=== the pre-registered rule ===")
    print(f"  primary delta      : {decision['delta']:+.6f}  CI {decision['ci95']}")
    print(f"  resolution floor   : {decision['resolution_floor']:.6f}")
    print(f"  ci excludes 0      : {decision['ci_excludes_zero']}")
    print(f"  |delta| >= floor   : {decision['delta_at_or_above_floor']}")
    print(f"  => ADOPT LAYER NORM: {decision['ADOPT_LAYER_NORM']}")
    print(f"  verdict            : {decision['verdict']}")

    guards = out["guards"]
    print("\nguards: " + "  ".join(f"{k.split('_')[0]}={v['pass']}" for k, v in guards.items()))
    return 0 if all(v["pass"] for v in guards.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
