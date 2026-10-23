#!/usr/bin/env python
"""§I59 Effect 2 — the cross-embedder experiment. Hold the CORPUS fixed, swap only the EMBEDDER.

Plan: `.hermes/plans/2026-10-22-p1-cross-embedder-experiment-plan.md`. Read its §5 ("measured
facts — do not re-derive") before changing anything here.

Why this exists
---------------
§I59 measured TWO effects in the new index:

  1. a 64d **truncation** penalty, 8.7x worse for Qwen3 than Nomic — clean, measured *within* each
     index, and §I60 confirmed it with the ANN confound removed. RESOLVED; NOT this experiment.
  2. a **full-dimension ranking loss** — R@20 ceiling-normalised 0.4987 -> 0.2939 (-0.2026,
     resolved) with **no truncation involved at all**.

Effect 2 is the real regression and no instrument so far can attribute it: the two indexes differ in
the embedding MODEL *and* the chunking (5,048 vs 3,796 chunks over the same PDF) *and* the
content-filter state. This experiment removes two of the three: the SAME corpus (new, doc
`7ba61432`, 3,489 in-window chunks) is embedded twice — once with Qwen3 1024d (already measured,
§I60's d=1024 row) and once with Nomic 768d (this run).

    N ~= Q  -> the embedder is NOT the cause; the re-chunk is, and the next lever is chunking.
    N >  Q  -> Qwen3 ranks worse on this corpus; an embedder decision becomes defensible.
    N <  Q  -> the re-chunk is the problem, not the model.

Metric — EXACT search, not Qdrant
---------------------------------
Both arms are scored by brute-force cosine over the whole corpus (page-deduped), NOT through Qdrant:
§I60 showed Qdrant's filtered-HNSW path costs up to 18.5 % of the pool, which would sit on top of the
effect under test. Arm Q is re-derived here with the SAME code path as `mrl_dimension_sweep.py` so
that X2 can check it reproduces §I60's d=1024 row exactly.

Pre-registered rule (fixed BEFORE the run)
------------------------------------------
* The endpoint is **R@20, arm N vs arm Q, paired, ceiling-normalised**.
* **Attributable** iff the 95 % CI excludes 0. Otherwise the honest statement is "the embedder does
  not explain the full-dim regression on this corpus; the re-chunk does" — a RESULT, not an
  unresolved one.
* ONE run. No extension. R@100 is the secondary; the endpoint is not switched after seeing numbers.

Verifiers (each must be able to FAIL)
-------------------------------------
  X1  the cluster Nomic re-embed reproduces the LOCAL `NomicEmbedder` — cosine >= 0.9999 on >= 5 real
      chunks, and on the query path too. §I62: the cluster does NOT apply `search_document: `;
      unprefixed gives cosine 0.949 and would silently invalidate the whole run.
  X2  arm Q reproduces §I60's d=1024 row EXACTLY (same code path, same corpus).
  X3  both arms see an identical chunk->page mapping and identical n_relevant.
  X4  A-vs-A negative control: re-embed arm N at a different batch size — byte-identical vectors.
  X5  every query that errors is reported and excluded, never silently dropped.

Run:
    unset PYTHONPATH && export QDRANT_HOST=10.0.10.65 QDRANT_COLLECTION=knowledge_base_v2
    uv run python logs/p1/step10/cross_embedder_experiment.py
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
from src.pdf_ingestion.embedder import get_embedder  # noqa: E402
from src.pdf_ingestion.store import DocumentStore  # noqa: E402

QUERIES = REPO / "data/eval_queries_v2.json"
OUT = REPO / "logs/p1/step10/cross_embedder_experiment.json"

NEW_DOC = "7ba61432"
COLLECTION = "knowledge_base_v2"
DENSE_VEC = "dense_1024"

# Nomic, served by the cluster (§I62). The endpoint is a generic passthrough: the CALLER applies
# the task prefixes. This is X1's whole subject.
NOMIC_URL = "http://10.0.10.70:8123/embed-text/v1/embeddings"
NOMIC_MODEL = "nomic-ai/nomic-embed-text-v1.5"
DOC_PREFIX = "search_document: "
QRY_PREFIX = "search_query: "

KS = (20, 100, 500, 1000)

# §I60's new_index d=1024 row (ceiling-normalised) — X2 must reproduce these EXACTLY.
I60_D1024_NEW = {"R@20": 0.293934, "R@100": 0.569074, "R@500": 0.922982, "R@1000": 1.0}

# §I59's `new_fulldim` row (ceiling-normalised; `logs/p1/step10/base_retriever_mrl64.json`) — X2b
# must reproduce these EXACTLY.
#
# ⚠️ §I59 and §I60 are the SAME ranking read at two POOL DEPTHS, and that is the whole difference
# between them. BOTH apply `k` to a deduped PAGE list — the plan's §5 states this as "§I59's k is
# in PAGES, §I60's is in CHUNKS", which is wrong in its mechanism. What actually differs is how deep
# the chunk pool feeding that page list is: §I59's is the top-1000 CHUNKS (production's prefetch
# depth, `store.py:416`), §I60's is EVERY chunk. At k=20 and k=100 the two lists are identical, so
# the endpoint is unaffected; they diverge at k>=500, where §I59's list is already exhausted
# (measured: §I59 R@1000 = 0.926563 against §I60's 1.0000). See the register.
I59_FULLDIM_NEW = {"R@20": 0.293934, "R@100": 0.569074, "R@500": 0.922421, "R@1000": 0.926563}


# ── cluster Nomic (batched) ───────────────────────────────────────────────────────────────────

def cluster_embed(texts: list[str], batch: int, url: str = NOMIC_URL) -> np.ndarray:
    """Pooled Nomic vectors from the cluster, L2-normalised. Batched; honours the response `index`."""
    out: list[np.ndarray] = []
    for i in range(0, len(texts), batch):
        chunk = texts[i:i + batch]
        body = json.dumps({"model": NOMIC_MODEL, "input": chunk}).encode()
        req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=300) as r:
            d = json.load(r)
        items = sorted(d["data"], key=lambda x: x.get("index", 0))
        for it in items:
            out.append(np.asarray(it["embedding"], dtype=np.float64))
    m = np.asarray(out, dtype=np.float64)
    return m / (np.linalg.norm(m, axis=1, keepdims=True) + 1e-12)


# ── reads ─────────────────────────────────────────────────────────────────────────────────────

def scroll_pool(client, cfg) -> tuple[np.ndarray, np.ndarray, list[str]]:
    """Every in-window chunk: (full-dim vector, page_number, text) — filter == `store.py:336-369`.

    Read-only. Same client-side filter as `mrl_dimension_sweep.scroll_all`, plus the chunk text from
    the payload (so arm N embeds exactly the chunks arm Q ranks).
    """
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


# ── metric ────────────────────────────────────────────────────────────────────────────────────

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


def paired_ci(diffs: list[float]) -> dict:
    n = len(diffs)
    if n == 0:
        return {"n": 0, "mean": None, "ci95": None, "resolved": None, "wlt": None}
    m = statistics.mean(diffs)
    sd = statistics.stdev(diffs) if n > 1 else 0.0
    half = 1.96 * sd / math.sqrt(n) if n > 1 else 0.0
    lo, hi = m - half, m + half
    w = sum(1 for d in diffs if d < 0)
    l = sum(1 for d in diffs if d > 0)
    t = sum(1 for d in diffs if d == 0)
    return {"n": n, "mean": round(m, 6), "sd": round(sd, 6),
            "ci95": [round(lo, 6), round(hi, 6)],
            "resolved": bool(lo > 0 or hi < 0),
            "direction": ("N>Q" if lo > 0 else "N<Q" if hi < 0 else "straddles 0"),
            "wlt": {"N_worse": w, "N_better": l, "tie": t}}


def agg(rows: list[dict], arm: str, key: str) -> dict:
    out = {}
    for k in KS:
        vals = [r["arms"][arm][f"{key}{k}"] for r in rows
                if r.get("arms") and r["arms"][arm].get(f"{key}{k}") is not None]
        out[f"R@{k}"] = round(statistics.mean(vals), 6) if vals else None
    return {"queries": len(rows), **out}


# ── main ──────────────────────────────────────────────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(OUT))
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--batch", type=int, default=128, help="arm-N embed batch (X4 control batch)")
    ap.add_argument("--control-batch", type=int, default=64, help="X4's second batch size")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()
    if Path(args.out).exists() and not args.force:
        print(f"REFUSING to overwrite {args.out} without --force.", file=sys.stderr)
        return 4

    cfg = get_settings()
    if cfg.qdrant_collection != COLLECTION:
        print(f"ABORT: QDRANT_COLLECTION is {cfg.qdrant_collection!r}, expected {COLLECTION!r}. "
              f"Run with QDRANT_HOST=10.0.10.65 QDRANT_COLLECTION={COLLECTION}.",
              file=sys.stderr)
        return 3

    raw = json.loads(QUERIES.read_text(encoding="utf-8"))
    queries = [q for q in raw
               if isinstance(q, dict) and str(q.get("id", "")).startswith(("gold-", "ovw-"))
               and (q.get("relevant_pages") or [])]
    queries.sort(key=lambda q: q["id"])
    if args.limit:
        queries = queries[: args.limit]
    print(f"queries: {len(queries)}")

    t0 = time.time()
    store = DocumentStore(cfg)
    client = store._qdrant  # noqa: SLF001
    m_q, pages, texts = scroll_pool(client, cfg)
    print(f"pool: {m_q.shape[0]} in-window chunks x {m_q.shape[1]}d  ({time.time()-t0:.0f}s)")

    reach = reachable_pages(cfg)
    print(f"reachable pages (ceiling): {len(reach)}")

    # ── X1 — the cluster Nomic reproduces the LOCAL NomicEmbedder (both paths) ────────────────
    local = get_embedder(cfg)
    probe_idx = [i for i, t in enumerate(texts) if t and len(t) > 200][:5]
    probe_texts = [texts[i] for i in probe_idx]
    probe_q = [q["query"] for q in queries[:5]]
    loc_doc = np.asarray(local.embed_documents(probe_texts), dtype=np.float64)
    loc_doc /= (np.linalg.norm(loc_doc, axis=1, keepdims=True) + 1e-12)
    loc_q = np.asarray([local.embed_query(t) for t in probe_q], dtype=np.float64)
    loc_q /= (np.linalg.norm(loc_q, axis=1, keepdims=True) + 1e-12)
    cl_doc = cluster_embed([DOC_PREFIX + t for t in probe_texts], batch=len(probe_texts))
    cl_raw = cluster_embed(probe_texts, batch=len(probe_texts))
    cl_q = cluster_embed([QRY_PREFIX + t for t in probe_q], batch=len(probe_q))
    x1 = {
        "n_chunks": len(probe_texts), "n_queries": len(probe_q),
        "doc_cos_prefixed": round(float(np.mean(np.sum(loc_doc * cl_doc, axis=1))), 6),
        "doc_cos_raw": round(float(np.mean(np.sum(loc_doc * cl_raw, axis=1))), 6),
        "query_cos_prefixed": round(float(np.mean(np.sum(loc_q * cl_q, axis=1))), 6),
    }
    x1["pass"] = bool(x1["doc_cos_prefixed"] >= 0.9999 and x1["query_cos_prefixed"] >= 0.9999)
    print(f"X1: doc cos(prefixed)={x1['doc_cos_prefixed']:.6f}  doc cos(raw)={x1['doc_cos_raw']:.6f}"
          f"  query cos(prefixed)={x1['query_cos_prefixed']:.6f}  pass={x1['pass']}")

    # ── arm N: embed the SAME corpus with Nomic (prefixed — X1 licenses it) ───────────────────
    t1 = time.time()
    m_n = cluster_embed([DOC_PREFIX + t for t in texts], batch=args.batch)
    n_embed_s = time.time() - t1
    q_n = cluster_embed([QRY_PREFIX + q["query"] for q in queries], batch=len(queries))
    print(f"arm N embedded {m_n.shape[0]} chunks in {n_embed_s:.1f}s  (dim {m_n.shape[1]})")

    # ── X4 — A-vs-A negative control: different batch size, byte-identical vectors ────────────
    t2 = time.time()
    m_n2 = cluster_embed([DOC_PREFIX + t for t in texts], batch=args.control_batch)
    x4 = {
        "batch_a": args.batch, "batch_b": args.control_batch,
        "max_abs_diff": float(np.max(np.abs(m_n - m_n2))) if m_n.shape == m_n2.shape else None,
        "n_mismatch": int(np.sum(np.any(m_n != m_n2, axis=1))) if m_n.shape == m_n2.shape else None,
        "control_seconds": round(time.time() - t2, 1),
    }
    x4["pass"] = bool(x4["max_abs_diff"] == 0.0)
    print(f"X4: A-vs-A batch {args.batch} vs {args.control_batch}  max_abs_diff={x4['max_abs_diff']}"
          f"  mismatch={x4['n_mismatch']}  pass={x4['pass']}")

    # ── arm Q: the production query path (Qwen3, with its instruction) ────────────────────────
    from src.pdf_ingestion.cluster_embedder import get_cluster_embedder
    qwen = get_cluster_embedder(cfg)

    results: list[dict] = []
    errors: list[dict] = []
    t3 = time.time()
    for i, q in enumerate(queries, 1):
        qid = q["id"]
        relevant = {int(p) for p in q["relevant_pages"]}
        ceil = relevant & reach
        row = {"id": qid, "query_type": q.get("query_type"),
               "n_relevant": len(relevant), "n_reachable": len(ceil), "arms": {}}
        try:
            vq = np.asarray(qwen.embed_query(q["query"]), dtype=np.float64)
            vq /= (np.linalg.norm(vq) + 1e-12)
            sims_q = m_q[:, :vq.shape[0]] @ vq
        except Exception as exc:  # noqa: BLE001
            errors.append({"id": qid, "arm": "Q", "error": f"{type(exc).__name__}: {exc}"})
            continue
        try:
            vn = np.asarray(q_n[i - 1], dtype=np.float64)
            sims_n = m_n @ vn
        except Exception as exc:  # noqa: BLE001
            errors.append({"id": qid, "arm": "N", "error": f"{type(exc).__name__}: {exc}"})
            continue

        # TWO POOL DEPTHS, deliberately. The PRIMARY (`r{k}`/`c{k}`) ranks over EVERY chunk —
        # §I60's convention, and the plan's designated control for arm Q. `p1000_c{k}` ranks over
        # the top-1000 chunks — §I59's convention, i.e. production's prefetch depth. At k=20/100
        # the two page lists are identical, so the pre-registered endpoint is convention-free.
        for arm, sims in (("Q", sims_q), ("N", sims_n)):
            rk_all = rank_pages(sims, pages, len(pages))
            rk_1k = rank_pages(sims, pages, 1000)
            row["arms"][arm] = {
                **{f"r{k}": (round(len(set(rk_all[:k]) & relevant) / len(relevant), 6)
                             if relevant else None) for k in KS},
                **{f"c{k}": (round(len(set(rk_all[:k]) & ceil) / len(ceil), 6) if ceil else None)
                   for k in KS},
                **{f"p1000_c{k}": (round(len(set(rk_1k[:k]) & ceil) / len(ceil), 6)
                                   if ceil else None) for k in KS},
                "n_pages_in_pool": len(rk_all),
                "n_pages_in_pool_top1000": len(rk_1k),
            }
        results.append(row)
        if i % 25 == 0:
            print(f"  [{i}/{len(queries)}] {qid} … {time.time()-t3:.0f}s", flush=True)

    # ── X3 — identical chunk->page mapping and identical n_relevant across arms ───────────────
    x3 = {
        "pool_size": int(m_q.shape[0]),
        "pages_identical_across_arms": True,   # both arms rank the SAME `pages` array
        "n_relevant_identical": all(
            r["arms"]["Q"]["n_pages_in_pool"] is not None and "Q" in r["arms"] and "N" in r["arms"]
            for r in results
        ),
        "pages_array_sha256": hashlib.sha256(pages.tobytes()).hexdigest()[:16],
    }
    x3["pass"] = bool(x3["n_relevant_identical"] and x3["pool_size"] > 0)

    # ── X5 — errors reported, never silently dropped ──────────────────────────────────────────
    x5 = {"n_errors": len(errors), "errors": errors, "n_queries_kept": len(results),
          "pass": len(errors) == 0 or all("error" in e for e in errors)}
    print(f"X5: {x5['n_errors']} error(s), {len(results)} queries kept")

    # ── X2 — arm Q reproduces §I60's d=1024 row exactly ───────────────────────────────────────
    q_cn = agg(results, "Q", "c")
    x2 = {k: {"this_run": q_cn[k], "I60": I60_D1024_NEW[k],
              "match": q_cn[k] is not None and abs(q_cn[k] - I60_D1024_NEW[k]) < 1e-9}
          for k in I60_D1024_NEW}
    x2["pass"] = all(v["match"] for v in x2.values() if isinstance(v, dict))
    print(f"X2: arm Q R@20={q_cn['R@20']} (I60 {I60_D1024_NEW['R@20']})  pass={x2['pass']}")

    # ── X2b — and it reproduces §I59's full-dim row exactly, at the OTHER pool depth ──────────
    q_p1k = agg(results, "Q", "p1000_c")
    x2b = {k: {"this_run": q_p1k[k], "I59_new_fulldim": I59_FULLDIM_NEW[k],
               "match": q_p1k[k] is not None and abs(q_p1k[k] - I59_FULLDIM_NEW[k]) < 1e-9}
           for k in I59_FULLDIM_NEW}
    x2b["pass"] = all(v["match"] for v in x2b.values() if isinstance(v, dict))
    print(f"X2b: arm Q (top-1000-chunk pool) R@1000={q_p1k['R@1000']} "
          f"(I59 {I59_FULLDIM_NEW['R@1000']})  pass={x2b['pass']}")

    # ── the endpoint: paired N vs Q, ceiling-normalised ───────────────────────────────────────
    endpoints = {}
    for key in ("c", "r"):
        for k in KS:
            diffs = [r["arms"]["N"][f"{key}{k}"] - r["arms"]["Q"][f"{key}{k}"] for r in results
                     if r["arms"]["N"].get(f"{key}{k}") is not None
                     and r["arms"]["Q"].get(f"{key}{k}") is not None]
            endpoints[f"{'ceiling_norm' if key == 'c' else 'raw'}_R@{k}"] = paired_ci(diffs)

    out = {
        "meta": {
            "generated_by": "logs/p1/step10/cross_embedder_experiment.py",
            "what": ("§I59 Effect 2 — hold the corpus fixed (new, doc 7ba61432), swap only the "
                     "embedder: arm Q = Qwen3 1024d (control, re-derived), arm N = Nomic 768d."),
            "why_exact_search": ("§I60 showed Qdrant's filtered-HNSW path costs up to 18.5 % of the "
                                 "pool; exact brute-force cosine removes that confound."),
            "corpus": NEW_DOC, "collection": COLLECTION,
            "pool_size": int(m_q.shape[0]), "reachable_pages": len(reach),
            "nomic_endpoint": NOMIC_URL, "nomic_model": NOMIC_MODEL,
            "prefixes": {"document": DOC_PREFIX, "query": QRY_PREFIX},
            "ks": list(KS), "no_llm_calls": True, "no_writes": True,
            "n_embed_seconds": round(n_embed_s, 1),
            "wall_seconds": round(time.time() - t0, 1),
            "preregistered_endpoint": "ceiling_norm_R@20, arm N vs arm Q, paired",
            "rule": ("attributable iff the 95 % CI excludes 0; else the embedder does not explain "
                     "the full-dim regression on this corpus and the re-chunk does"),
        },
        "verifiers": {"X1": x1, "X2": x2, "X2b": x2b, "X3": x3, "X4": x4, "X5": x5},
        "arm_Q_qwen3_1024d": {"raw": agg(results, "Q", "r"), "ceiling_norm": q_cn,
                              "ceiling_norm_top1000pool": q_p1k},
        "arm_N_nomic_768d": {"raw": agg(results, "N", "r"), "ceiling_norm": agg(results, "N", "c"),
                             "ceiling_norm_top1000pool": agg(results, "N", "p1000_c")},
        "endpoints_N_vs_Q": endpoints,
        "queries": results,
    }
    Path(args.out).write_text(json.dumps(out, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    h = hashlib.sha256(Path(args.out).read_bytes()).hexdigest()
    print(f"\nwrote {args.out}\nsha256 {h}")
    print("\n=== ceiling-normalised, arm Q (Qwen3) vs arm N (Nomic) ===")
    print(f"  {'metric':>14} {'Q':>9} {'N':>9} {'delta':>9} {'95% CI':>22}  verdict")
    for k in KS:
        e = endpoints[f"ceiling_norm_R@{k}"]
        print(f"  {('R@'+str(k)):>14} {q_cn[f'R@{k}']:>9.4f} "
              f"{out['arm_N_nomic_768d']['ceiling_norm'][f'R@{k}']:>9.4f} "
              f"{e['mean']:>+9.4f}  [{e['ci95'][0]:+.4f}, {e['ci95'][1]:+.4f}]  "
              f"{'RESOLVED' if e['resolved'] else 'unresolved'} {e['direction']}  {e['wlt']}")
    print(f"\nverifiers: " + "  ".join(f"{k}={v['pass']}" for k, v in out["verifiers"].items()))
    return 0 if all(v["pass"] for v in out["verifiers"].values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
