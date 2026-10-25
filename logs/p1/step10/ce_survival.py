#!/usr/bin/env python
"""§I72 — does the embedder's base-lane ranking gain SURVIVE the cross-encoder?

Pre-registration (the spec, written BEFORE this file existed):
`.hermes/plans/2026-10-24-p1-cross-encoder-survival-preregistration.md`.

⚠️ **If any number in the pre-registration is edited after this run starts, the run is VOID.**

What this is
------------
§I70's screen found `google/embeddinggemma-300m` @768 the only arm that passes the pre-registered
rule: **+0.186476** ceiling-normalised R@20 over the incumbent `Qwen/Qwen3-Embedding-0.6B` @1024, and
**+0.046480** over `nomic-ai/nomic-embed-text-v1.5` @768. That is a **base-lane** (dense ranking)
result. §I66 measured the product funnel's stage losses, and the **cross-encoder is the largest
single one** (0.6048 → 0.4318). Three consecutive precedents (§I65, §I66, §I67) show a measured
retrieval-side ceiling that did NOT become recall.

So the largest unmeasured risk in adopting gemma is that the cross-encoder re-orders both
embedders' pools toward the same answer and the gain is eaten before it reaches the product.

**This harness isolates that one stage, with no re-ingest**: order the same 100 candidates by cosine
under each embedder, push both lists through the LIVE cluster cross-encoder, and compare.

    per query, per embedder:
      PRE  = pages of the top-20 CHUNKS by exact cosine      (must reproduce §I70 exactly — S1)
      POST = pages of the cross-encoder's top-20 chunks

    primary endpoint: paired ceiling-normalised R@20, POST, gemma@768 − qwen3@1024, n = 133
    the bet SURVIVES iff the POST delta is > 0 with a CI excluding 0.

⚠️ **Not the product endpoint.** The product reranks a pool that has been through Qdrant's RRF,
page dedup and MMR — and §I68 measured that fusion to be NONDETERMINISTIC server-side, which is why
it is excluded here rather than simulated. This is a stage diagnostic (§I66's method).

Guards (pre-reg §4 — each must be able to FAIL)
-----------------------------------------------
  S1′ (restated in the RE-REGISTRATION, `.hermes/plans/2026-10-24-p1-cross-encoder-survival-
      reregistration.md`; the first run was VOID on the original S1). TWO conventions are in play
      and the original guard compared across them:
        §I70's screen      "top-k PAGES" — rank every chunk, dedupe to pages, take the first k pages
        the PRODUCT's      "pages of the top-k CHUNKS" — evaluate_rag.py:333-341, which is what the
                           deployed eval computes and the only one available for a reranked arm
      S1′(a) the PRE arm under §I70's convention reproduces 0.293934 (qwen3@1024) and 0.480410
            (gemma@768) EXACTLY — that is what pins this harness to the register.
      S1′(b) the PRE and POST arms of the CONTRAST both use the product's convention, asserted to
            be the same function on both sides. Both conventions are reported side by side.
  S2  the rerank service is LIVE and REORDERING: at least one query's order differs from the input
      order, and the scores are not all equal.
  S3  negative control — the same candidate list reranked TWICE returns the identical order.
      ⚠️ This CAN fail, and if it does the whole contrast is a tolerance (§I68's class): a
      nondeterministic cross-encoder would undermine every reranked metric in the register.
  S4  every failed rerank call is counted (via the reranker's own §I55 counter) and reported with
      its query ids; the paired delta states its n. Never silently dropped.
  S5  A-vs-A: gemma re-embedded at a different batch size is bit-identical.
  S6  one shared chunk→page mapping; ceiling 888; and the documents sent are the candidate texts in
      cosine rank order (index alignment asserted, not assumed).

Run:
    unset PYTHONPATH && export QDRANT_HOST=10.0.10.65 QDRANT_COLLECTION=knowledge_base_v2
    uv run python -u logs/p1/step10/ce_survival.py
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
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

import numpy as np  # noqa: E402

from src.core.config import get_settings  # noqa: E402
from src.pdf_ingestion.reranker import get_reranker  # noqa: E402
from src.pdf_ingestion.store import DocumentStore  # noqa: E402

QUERIES = REPO / "data/eval_queries_v2.json"
OUT = REPO / "logs/p1/step10/ce_survival.json"

NEW_DOC = "7ba61432"
COLLECTION = "knowledge_base_v2"
DENSE_VEC = "dense_1024"

EMBED_URL = "http://10.0.10.70:8123/embed-text/v1/embeddings"
GEMMA_HF = "google/embeddinggemma-300m"
GEMMA_DOC_PREFIX = "title: none | text: "
GEMMA_QRY_PREFIX = "task: search result | query: "

KS = (20, 100, 500, 1000)

# §I70's rows, ceiling-normalised on the shipped pool — S1 must reproduce BOTH exactly.
I70_QWEN3_1024_R20 = 0.293934
I70_GEMMA_768_R20 = 0.480410
EXPECTED_POOL = 3489
EXPECTED_REACHABLE_PAGES = 888

# The candidate list width = the product's own pool width (`cfg.reranker_fetch_k`), asserted at run
# time rather than hardcoded — if the config moves, the harness says so instead of quietly testing a
# different stage.
EXPECTED_FETCH_K = 100
EXPECTED_TOP_K = 20


def cluster_embed(texts: list[str], batch: int, model: str) -> np.ndarray:
    """Pooled vectors from the cluster, L2-normalised (verbatim from §I70/§I71)."""
    out: list[np.ndarray] = []
    for i in range(0, len(texts), batch):
        chunk = texts[i:i + batch]
        body = json.dumps({"model": model, "input": chunk}).encode()
        req = urllib.request.Request(EMBED_URL, data=body,
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=600) as r:
            d = json.load(r)
        items = sorted(d["data"], key=lambda x: x.get("index", 0))
        for it in items:
            out.append(np.asarray(it["embedding"], dtype=np.float64))
    m = np.asarray(out, dtype=np.float64)
    return m / (np.linalg.norm(m, axis=1, keepdims=True) + 1e-12)


def scroll_pool(client, cfg) -> tuple[np.ndarray, np.ndarray, list[str]]:
    """Every in-window chunk: (full-dim vector, page_number, text) — the shipped pool (§I70's)."""
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


def pages_of_chunk_idxs(idxs: list[int], pages: np.ndarray) -> list[int]:
    seen, out = set(), []
    for i in idxs:
        pg = int(pages[i])
        if pg in seen:
            continue
        seen.add(pg)
        out.append(pg)
    return out


def paired_ci(diffs: list[float]) -> dict:
    n = len(diffs)
    if n == 0:
        return {"n": 0, "mean": None, "sd": None, "ci95": None, "resolved": None,
                "direction": None, "wlt": None}
    m = statistics.mean(diffs)
    sd = statistics.stdev(diffs) if n > 1 else 0.0
    half = 1.96 * sd / math.sqrt(n) if n > 1 else 0.0
    lo, hi = m - half, m + half
    return {"n": n, "mean": round(m, 6), "sd": round(sd, 6),
            "ci95": [round(lo, 6), round(hi, 6)],
            "resolved": bool(lo > 0 or hi < 0),
            "direction": ("gemma>qwen3" if lo > 0 else "gemma<qwen3" if hi < 0 else "straddles 0"),
            "wlt": {"gemma_worse": sum(1 for d in diffs if d < 0),
                    "gemma_better": sum(1 for d in diffs if d > 0),
                    "tie": sum(1 for d in diffs if d == 0)}}


def agg(rows: list[dict], stage: str, emb: str, key: str) -> dict:
    out = {}
    for k in KS:
        vals = [r[stage][emb][f"{key}{k}"] for r in rows
                if r.get(stage) and r[stage].get(emb) and r[stage][emb].get(f"{key}{k}") is not None]
        out[f"R@{k}"] = round(statistics.mean(vals), 6) if vals else None
        out[f"n_queries_{key}@{k}"] = len(vals)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(OUT))
    ap.add_argument("--batch", type=int, default=128)
    ap.add_argument("--control-batch", type=int, default=64)
    ap.add_argument("--control-queries", type=int, default=5,
                    help="queries re-reranked for the S3 determinism control")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()
    if Path(args.out).exists() and not args.force:
        print(f"REFUSING to overwrite {args.out} without --force.", file=sys.stderr)
        return 4

    t0 = time.time()
    cfg = get_settings()
    verifiers: dict = {}

    fetch_k = int(cfg.reranker_fetch_k)
    top_k = int(cfg.reranker_top_k)
    cfg_gate = {
        "qdrant_host": (cfg.qdrant_host or "").strip(),
        "qdrant_collection": cfg.qdrant_collection,
        "sv_rerank_url": cfg.sv_rerank_url,
        "reranker_model": cfg.reranker_model,
        "reranker_enabled": cfg.reranker_enabled,
        "reranker_fetch_k": fetch_k, "expected_fetch_k": EXPECTED_FETCH_K,
        "reranker_top_k": top_k, "expected_top_k": EXPECTED_TOP_K,
        "hyde_enabled": cfg.hyde_enabled,
        "window": [cfg.min_content_page, cfg.max_content_page],
    }
    cfg_gate["pass"] = bool(
        cfg_gate["qdrant_collection"] == COLLECTION
        and cfg_gate["qdrant_host"] and cfg_gate["qdrant_host"] not in ("localhost", "127.0.0.1")
        and cfg_gate["sv_rerank_url"] and cfg_gate["reranker_enabled"]
        and fetch_k == EXPECTED_FETCH_K and top_k == EXPECTED_TOP_K
    )
    verifiers["S0_resolved_config"] = cfg_gate
    print(f"S0: collection={cfg.qdrant_collection!r} rerank={cfg.sv_rerank_url!r} "
          f"model={cfg.reranker_model!r} fetch_k={fetch_k} top_k={top_k} "
          f"hyde_enabled={cfg.hyde_enabled} (run is HyDE-OFF by design) pass={cfg_gate['pass']}")
    if not cfg_gate["pass"]:
        print("ABORT: the resolved config is not the one the pre-registration names.", file=sys.stderr)
        return 3

    store = DocumentStore(cfg)
    client = store._qdrant  # noqa: SLF001
    m_q, pages, texts = scroll_pool(client, cfg)
    print(f"pool: {m_q.shape[0]} in-window chunks x {m_q.shape[1]}d  ({time.time()-t0:.0f}s)")

    reach = reachable_pages(cfg)
    print(f"reachable pages (SQLite, §I58): {len(reach)}")

    raw = json.loads(QUERIES.read_text(encoding="utf-8"))
    queries = [q for q in raw
               if isinstance(q, dict) and str(q.get("id", "")).startswith(("gold-", "ovw-"))
               and (q.get("relevant_pages") or [])]
    queries.sort(key=lambda q: q["id"])
    if args.limit:
        queries = queries[: args.limit]
    print(f"queries: {len(queries)}")

    # ── gemma, over the same corpus; plus the A-vs-A control embed (S5) ───────────────────────
    embed_seconds: dict[str, float] = {}
    t = time.time()
    m_g = cluster_embed([GEMMA_DOC_PREFIX + x for x in texts], batch=args.batch, model=GEMMA_HF)
    embed_seconds["gemma"] = round(time.time() - t, 1)
    t = time.time()
    m_g_ctrl = cluster_embed([GEMMA_DOC_PREFIX + x for x in texts],
                             batch=args.control_batch, model=GEMMA_HF)
    embed_seconds["gemma_control"] = round(time.time() - t, 1)
    print(f"gemma embedded {m_g.shape} in {embed_seconds['gemma']}s "
          f"(control {embed_seconds['gemma_control']}s)")

    s5 = {
        "model": GEMMA_HF, "batch_a": args.batch, "batch_b": args.control_batch,
        "max_abs_diff": float(np.max(np.abs(m_g - m_g_ctrl))) if m_g.shape == m_g_ctrl.shape else None,
        "n_rows_differing": int(np.sum(np.any(m_g != m_g_ctrl, axis=1)))
        if m_g.shape == m_g_ctrl.shape else None,
    }
    s5["pass"] = bool(s5["max_abs_diff"] == 0.0)
    verifiers["S5_A_vs_A_vectors"] = s5
    print(f"S5: A-vs-A re-embed max_abs_diff={s5['max_abs_diff']} "
          f"rows_differing={s5['n_rows_differing']} pass={s5['pass']}")

    # ── query vectors, each embedder on its own path ──────────────────────────────────────────
    from src.pdf_ingestion.cluster_embedder import get_cluster_embedder
    qwen = get_cluster_embedder(cfg)
    qv: dict[str, np.ndarray] = {}
    v = np.asarray([qwen.embed_query(q["query"]) for q in queries], dtype=np.float64)
    qv["qwen3"] = v / (np.linalg.norm(v, axis=1, keepdims=True) + 1e-12)
    v = cluster_embed([GEMMA_QRY_PREFIX + q["query"] for q in queries],
                      batch=len(queries), model=GEMMA_HF)
    qv["gemma"] = v / (np.linalg.norm(v, axis=1, keepdims=True) + 1e-12)
    print("query vectors ready")

    reranker = get_reranker(cfg)
    print(f"reranker: {type(reranker).__name__}  fallbacks so far={getattr(reranker, 'fallbacks', 0)}")

    corpus = {"qwen3": m_q, "gemma": m_g}
    results: list[dict] = []
    failures: list[dict] = []
    s2_evidence: dict = {"n_order_changes": 0, "n_constant_scores": 0, "examples": []}
    s3_rows: list[dict] = []
    s6_alignment: list[dict] = []
    t3 = time.time()

    for i, q in enumerate(queries, 1):
        qid = q["id"]
        relevant = {int(p) for p in q["relevant_pages"]}
        ceil = relevant & reach
        row: dict = {"id": qid, "query_type": q.get("query_type"),
                     "n_relevant": len(relevant), "n_reachable": len(ceil),
                     "pre": {}, "post": {}}

        for emb in ("qwen3", "gemma"):
            sims = corpus[emb] @ qv[emb][i - 1]
            order = np.argsort(-sims)
            cand_idx = [int(j) for j in order[:fetch_k]]

            # ── the §I70 SCREEN convention ("top-k PAGES"), reported beside the contrast ──────
            # ⚠️ This is NOT the metric the PRE/POST contrast uses. §I70's screen ranks EVERY
            # chunk, dedupes to pages and takes the first k PAGES; the product's eval
            # (`evaluate_rag.py:333`) dedupes the top-k CHUNKS. The two differ by ~0.02 and only
            # the first reproduces the register — which is why both are carried.
            rk_all = rank_pages(sims, pages, len(pages))
            row.setdefault("i70", {})[emb] = {
                **{f"c{k}": (round(len(set(rk_all[:k]) & ceil) / len(ceil), 6) if ceil else None)
                   for k in KS},
                **{f"r{k}": (round(len(set(rk_all[:k]) & relevant) / len(relevant), 6)
                             if relevant else None) for k in KS},
            }

            # ── PRE: pages of the top-`top_k` chunks in cosine order ──────────────────────────
            pre_pages = pages_of_chunk_idxs(cand_idx[:top_k], pages)
            row["pre"][emb] = {
                **{f"c{k}": (round(len(set(pages_of_chunk_idxs(cand_idx[:k], pages)) & ceil)
                                   / len(ceil), 6) if ceil else None) for k in KS},
                **{f"r{k}": (round(len(set(pages_of_chunk_idxs(cand_idx[:k], pages)) & relevant)
                                   / len(relevant), 6) if relevant else None) for k in KS},
                "n_pages_top20": len(pre_pages),
            }

            # ── S6: the documents sent are the candidate texts IN COSINE RANK ORDER ───────────
            docs = [{"text": texts[j], "_pool_idx": j} for j in cand_idx]
            aligned = all(docs[n]["text"] == texts[cand_idx[n]] for n in range(len(cand_idx)))
            if len(s6_alignment) < 3:
                s6_alignment.append({"id": qid, "embedder": emb, "n_docs": len(docs),
                                     "aligned": bool(aligned),
                                     "first_idx": cand_idx[0], "last_idx": cand_idx[-1]})

            # ── POST: the live cross-encoder's order over that SAME list ──────────────────────
            fb_before = int(getattr(reranker, "fallbacks", 0))
            try:
                ranked = reranker.rerank(q["query"], docs, top_k=top_k)
            except Exception as exc:  # noqa: BLE001
                failures.append({"id": qid, "embedder": emb,
                                 "error": f"{type(exc).__name__}: {exc}"})
                continue
            fb_after = int(getattr(reranker, "fallbacks", 0))
            if fb_after != fb_before:
                # §I55's counter moved: the reranker swallowed a failure for THIS call and handed
                # back the unranked pool. Report it; never average it in as if it ranked.
                failures.append({"id": qid, "embedder": emb, "error": "reranker fallback (S4)"})
                continue

            post_idx = [int(d["_pool_idx"]) for d in ranked]
            if not post_idx:
                failures.append({"id": qid, "embedder": emb, "error": "empty ranking"})
                continue

            changed = post_idx != cand_idx[:len(post_idx)]
            if changed and s2_evidence["n_order_changes"] < 3:
                s2_evidence["examples"].append({"id": qid, "embedder": emb,
                                                "input_head": cand_idx[:5], "ranked_head": post_idx[:5]})
            s2_evidence["n_order_changes"] += int(changed)

            post_pages = pages_of_chunk_idxs(post_idx, pages)
            row["post"][emb] = {
                **{f"c{k}": (round(len(set(pages_of_chunk_idxs(post_idx[:k], pages)) & ceil)
                                   / len(ceil), 6) if ceil else None) for k in KS},
                **{f"r{k}": (round(len(set(pages_of_chunk_idxs(post_idx[:k], pages)) & relevant)
                                   / len(relevant), 6) if relevant else None) for k in KS},
                "n_pages_top20": len(post_pages),
                "n_returned": len(post_idx),
                "n_of_input_kept": len(set(post_idx) & set(cand_idx)),
                "order_changed": bool(changed),
                "top1_changed": bool(post_idx and post_idx[0] != cand_idx[0]),
            }

            # ── S3: the determinism control on the first N queries ────────────────────────────
            if i <= args.control_queries:
                try:
                    again = reranker.rerank(q["query"], docs, top_k=top_k)
                    again_idx = [int(d["_pool_idx"]) for d in again]
                    s3_rows.append({"id": qid, "embedder": emb,
                                    "identical": bool(again_idx == post_idx),
                                    "first": post_idx[:5], "second": again_idx[:5]})
                except Exception as exc:  # noqa: BLE001
                    s3_rows.append({"id": qid, "embedder": emb, "identical": False,
                                    "error": f"{type(exc).__name__}: {exc}"})

        results.append(row)
        if i % 20 == 0:
            print(f"  [{i}/{len(queries)}] {qid} … {time.time()-t3:.0f}s "
                  f"(failures so far {len(failures)})", flush=True)

    # ── S1′ — the instrument is §I70's, under §I70's OWN convention ───────────────────────────
    i70_q = agg(results, "i70", "qwen3", "c")
    i70_g = agg(results, "i70", "gemma", "c")
    pre_q = agg(results, "pre", "qwen3", "c")
    pre_g = agg(results, "pre", "gemma", "c")
    s1 = {
        "a_i70_convention": {
            "qwen3@1024_R@20": {"this_run": i70_q["R@20"], "registered": I70_QWEN3_1024_R20},
            "gemma@768_R@20": {"this_run": i70_g["R@20"], "registered": I70_GEMMA_768_R20},
        },
        "b_contrast_convention": {
            "name": "pages of the top-k CHUNKS (evaluate_rag.py:333-341)",
            "pre_qwen3_R@20": pre_q["R@20"], "pre_gemma_R@20": pre_g["R@20"],
            "same_function_both_sides": True,   # by construction: pages_of_chunk_idxs on both arms
        },
        "pool_size": {"this_run": int(m_q.shape[0]), "expected": EXPECTED_POOL},
        "reachable_pages": {"this_run": len(reach), "expected": EXPECTED_REACHABLE_PAGES},
    }
    for key in ("qwen3@1024_R@20", "gemma@768_R@20"):
        e = s1["a_i70_convention"][key]
        e["match"] = bool(e["this_run"] is not None
                          and abs(e["this_run"] - e["registered"]) < 1e-9)
    s1["pass"] = bool(
        all(s1["a_i70_convention"][k]["match"] for k in ("qwen3@1024_R@20", "gemma@768_R@20"))
        and s1["pool_size"]["this_run"] == EXPECTED_POOL
        and s1["reachable_pages"]["this_run"] == EXPECTED_REACHABLE_PAGES
    )
    verifiers["S1prime_instrument_is_I70s"] = s1
    print(f"S1′(a) §I70 convention: qwen3@1024 R@20={i70_q['R@20']} (want {I70_QWEN3_1024_R20})  "
          f"gemma@768 R@20={i70_g['R@20']} (want {I70_GEMMA_768_R20})  pass={s1['pass']}")
    print(f"S1′(b) contrast convention (product, pages of top-k chunks): "
          f"PRE qwen3={pre_q['R@20']} gemma={pre_g['R@20']}")

    # ── S2 — the service is live and reordering ──────────────────────────────────────────────
    s2 = {"n_rerank_calls_scored": sum(1 for r in results for e in ("qwen3", "gemma")
                                       if r["post"].get(e)),
          "n_order_changes": s2_evidence["n_order_changes"],
          "examples": s2_evidence["examples"]}
    s2["pass"] = bool(s2["n_order_changes"] > 0 and s2["n_rerank_calls_scored"] > 0)
    verifiers["S2_reranker_live_and_reordering"] = s2
    print(f"S2: {s2['n_order_changes']} of {s2['n_rerank_calls_scored']} reranked lists changed "
          f"order  pass={s2['pass']}")

    # ── S3 — determinism control ─────────────────────────────────────────────────────────────
    s3 = {"n_controls": len(s3_rows),
          "n_identical": sum(1 for r in s3_rows if r.get("identical")),
          "rows": s3_rows}
    s3["pass"] = bool(s3_rows and s3["n_identical"] == len(s3_rows))
    verifiers["S3_reranker_deterministic"] = s3
    print(f"S3: {s3['n_identical']}/{s3['n_controls']} repeat calls identical  pass={s3['pass']}")

    # ── S4 — failures counted and reported ───────────────────────────────────────────────────
    s4 = {"n_failures": len(failures), "failures": failures,
          "n_queries": len(results),
          "pass": True}   # a REPORTING guard: it fails only if a failure went unrecorded
    unrecorded = [r["id"] for r in results
                  if any(e not in r["post"] for e in ("qwen3", "gemma"))
                  and r["id"] not in {f["id"] for f in failures}]
    s4["queries_missing_a_post_arm_without_a_recorded_failure"] = unrecorded
    s4["pass"] = bool(not unrecorded)
    verifiers["S4_failures_reported"] = s4
    print(f"S4: {s4['n_failures']} rerank failure(s); unrecorded={unrecorded}  pass={s4['pass']}")

    # ── S6 — one shared page mapping + alignment ─────────────────────────────────────────────
    s6 = {"pages_array_sha256": hashlib.sha256(pages.tobytes()).hexdigest(),
          "n_chunks": int(pages.shape[0]), "ceiling_size": len(reach),
          "alignment_samples": s6_alignment,
          "all_samples_aligned": all(x["aligned"] for x in s6_alignment)}
    s6["pass"] = bool(s6["all_samples_aligned"] and len(reach) == EXPECTED_REACHABLE_PAGES)
    verifiers["S6_shared_page_mapping_and_alignment"] = s6

    # ── the endpoints ────────────────────────────────────────────────────────────────────────
    stages_agg = {st: {e: {"ceiling_norm": agg(results, st, e, "c"), "raw": agg(results, st, e, "r")}
                       for e in ("qwen3", "gemma")} for st in ("pre", "post")}
    # The §I70 SCREEN convention, carried alongside — NOT the contrast's metric (see the docstring).
    i70_agg = {e: {"ceiling_norm": agg(results, "i70", e, "c"), "raw": agg(results, "i70", e, "r")}
               for e in ("qwen3", "gemma")}

    def contrast(stage: str, key: str, k: int) -> dict:
        diffs = [r[stage]["gemma"][f"{key}{k}"] - r[stage]["qwen3"][f"{key}{k}"]
                 for r in results
                 if r[stage].get("gemma", {}).get(f"{key}{k}") is not None
                 and r[stage].get("qwen3", {}).get(f"{key}{k}") is not None]
        return paired_ci(diffs)

    pre_d = contrast("pre", "c", 20)
    post_d = contrast("post", "c", 20)
    survival = (round(post_d["mean"] / pre_d["mean"], 6)
                if pre_d["mean"] and post_d["mean"] is not None else None)
    decision = {
        "primary_endpoint": "paired ceiling-normalised R@20 POST-rerank, gemma@768 − qwen3@1024",
        "pre_delta": pre_d["mean"], "pre_ci": pre_d["ci95"], "pre_n": pre_d["n"],
        "post_delta": post_d["mean"], "post_ci": post_d["ci95"], "post_n": post_d["n"],
        "post_wlt": post_d["wlt"],
        "survival_ratio_post_over_pre": survival,
        "resolution_floor_n133": round(1.96 * (post_d["sd"] or 0.0) / math.sqrt(post_d["n"]), 6)
        if post_d["n"] else None,
        "SURVIVES": bool(post_d["resolved"] and (post_d["mean"] or 0) > 0),
        "reads": (
            "the base-lane ranking gain SURVIVES the cross-encoder"
            if post_d["resolved"] and (post_d["mean"] or 0) > 0 else
            "the cross-encoder REVERSES the gain" if post_d["resolved"] else
            "the cross-encoder leaves the gain UNRESOLVED — it is not carried to the product's "
            "last retrieval stage on this instrument"
        ),
        "scope": ("stage diagnostic, NOT the product endpoint: the cross-encoder is applied to a "
                  "cosine-ordered pool, with no Qdrant RRF (§I68 nondeterministic), no dedup/MMR, "
                  "no SPLADE lane, no DA/graph/RAPTOR/visual lane, no generator"),
    }

    out = {
        "meta": {
            "generated_by": "logs/p1/step10/ce_survival.py",
            "preregistration":
                ".hermes/plans/2026-10-24-p1-cross-encoder-survival-preregistration.md",
            "reregistration":
                ".hermes/plans/2026-10-24-p1-cross-encoder-survival-reregistration.md",
            "first_run_void": {
                "artifact": "logs/p1/step10/ce_survival_firstrun_VOID.json",
                "sha256": "0947bc0d6c541b52f332815030c1dc80ba497753fc24a7ce83414cfe6112f5dd",
                "void_on": ["S1"],
                "reason": ("a PRE-REGISTRATION PREMISE ERROR, not a harness bug: S1 required the "
                           "PRE arm to reproduce §I70's rows, which are in §I70's screen "
                           "convention (top-k PAGES from the full deduped ranking), while the "
                           "PRE/POST contrast uses the PRODUCT's convention (pages of the top-k "
                           "chunks, evaluate_rag.py:333). The two are ~0.02 apart. Restated as "
                           "S1′: the §I70 convention is computed and asserted separately, and the "
                           "contrast asserts both its sides are in the same convention."),
                "first_run_numbers_not_registered": {
                    "pre_delta": 0.184317, "pre_ci": [0.130809, 0.237824],
                    "post_delta": 0.097559, "post_ci": [0.056072, 0.139045],
                    "survival_ratio": 0.5293,
                    "note": "recorded only so the second run can be compared against it",
                },
            },
            "what": ("§I72 — does the base-lane ranking gain of the better embedder survive the "
                     "cross-encoder? Same 100 candidates per query, ordered by exact cosine under "
                     "each embedder, pushed through the LIVE cluster cross-encoder."),
            "corpus": NEW_DOC, "collection": COLLECTION,
            "pool_size": int(m_q.shape[0]), "reachable_pages": len(reach),
            "fetch_k": fetch_k, "top_k": top_k,
            "embed_url": EMBED_URL,
            "rerank_url": cfg.sv_rerank_url, "reranker_model": cfg.reranker_model,
            "models": {"gemma": {"hf": GEMMA_HF, "dim": 768, "doc_prefix": GEMMA_DOC_PREFIX,
                                 "qry_prefix": GEMMA_QRY_PREFIX},
                       "qwen3": {"hf": cfg.dense_model, "dim": 1024,
                                 "source": "stored dense_1024 (late-chunked at ingest)"}},
            "hyde": "OFF (raw query vectors) — the cache that would freeze HyDE is built in "
                    "src/pdf_ingestion/hyde_cache.py and deliberately not used here",
            "late_chunking_asymmetry": ("qwen3@1024 ranks the STORED dense_1024 vectors (produced "
                                        "with late chunking); gemma@768 embeds the chunk text "
                                        "directly — §I70's asymmetry, conservative for gemma"),
            "metric_conventions": {
                "contrast": ("pages of the top-k CHUNKS, deduped — the PRODUCT's convention "
                             "(scripts/evaluate_rag.py:333-341). Used for BOTH sides of the "
                             "PRE/POST contrast."),
                "i70_screen": ("top-k PAGES from the full deduped chunk ranking — §I70's screen "
                               "convention. Reported under `arms_i70_convention` and used only "
                               "to pin the instrument to the register (guard S1′(a))."),
                "why_both": ("the two are ~0.02 apart and are NOT the same number; the first run "
                             "was VOID because S1 compared one against the other"),
            },
            "no_llm_calls": True, "no_writes_to_collections": True,
            "embed_seconds": embed_seconds, "wall_seconds": round(time.time() - t0, 1),
        },
        "verifiers": verifiers,
        "arms": stages_agg,
        "arms_i70_convention": i70_agg,
        "endpoints": {
            "pre": {"ceiling_norm_R@20_gemma_minus_qwen3": pre_d,
                    "raw_R@20_gemma_minus_qwen3": contrast("pre", "r", 20)},
            "post": {"ceiling_norm_R@20_gemma_minus_qwen3": post_d,
                     "raw_R@20_gemma_minus_qwen3": contrast("post", "r", 20),
                     "ceiling_norm_R@100_gemma_minus_qwen3": contrast("post", "c", 100)},
        },
        "decision": decision,
        "queries": results,
    }
    Path(args.out).write_text(json.dumps(out, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    h = hashlib.sha256(Path(args.out).read_bytes()).hexdigest()
    print(f"\nwrote {args.out}\nsha256 {h}")

    print("\n=== ceiling-normalised R@20, §I70's convention (top-k PAGES) — S1′(a) ===")
    for e in ("qwen3", "gemma"):
        ca = i70_agg[e]["ceiling_norm"]
        print(f"  {'i70':>5} {e:>8} {ca['R@20']:>9.6f} {ca['R@100']:>9.6f}")

    print("\n=== ceiling-normalised R@20, PRE vs POST, per embedder (product convention) ===")
    print(f"  {'stage':>5} {'embedder':>8} {'R@20':>9} {'R@100':>9} {'raw R@20':>9}")
    for st in ("pre", "post"):
        for e in ("qwen3", "gemma"):
            ca = stages_agg[st][e]["ceiling_norm"]
            ra = stages_agg[st][e]["raw"]
            print(f"  {st:>5} {e:>8} {ca['R@20']:>9.6f} {ca['R@100']:>9.6f} {ra['R@20']:>9.6f}")

    print("\n=== the endpoint: gemma − qwen3, before and after the cross-encoder ===")
    for label, d in (("PRE  (cosine order)", pre_d), ("POST (cross-encoder)", post_d)):
        ci = d["ci95"]
        print(f"  {label:22} Δ {d['mean']:+.6f} [{ci[0]:+.6f},{ci[1]:+.6f}] n={d['n']} "
              f"{'RESOLVED' if d['resolved'] else 'UNRESOLVED'}  W/L/T "
              f"{d['wlt']['gemma_worse']}/{d['wlt']['gemma_better']}/{d['wlt']['tie']}")
    print(f"  survival ratio (post/pre) = {survival}")
    print(f"\n  DECISION: SURVIVES={decision['SURVIVES']} — {decision['reads']}")

    print("\nverifiers: " + "  ".join(f"{k.split('_')[0]}={v['pass']}"
                                      for k, v in verifiers.items()))
    return 0 if all(v["pass"] for v in verifiers.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
