#!/usr/bin/env python
"""§I74 — at the cross-encoder, is gemma@768 worth its extra adoption cost over nomic@768?

Pre-registration (the spec, written BEFORE this file existed):
`.hermes/plans/2026-10-24-p1-gemma-vs-nomic-at-the-cross-encoder-preregistration.md`.

⚠️ **If any number in the pre-registration is edited after this run starts, the run is VOID.**

Why this run
------------
§I70's oracle screen ranked `gemma@768` > `nomic@768` > `qwen3@1024`, gemma over nomic by
**+0.046480** at the **base lane**. §I72 then found the cross-encoder a strong **equaliser**: against
the incumbent the gap **halved** (+0.184317 → +0.097559), because it lifted the weaker embedder by
+0.0888 and the stronger by +0.0020. ⚠️ **§I72 measured gemma against the INCUMBENT, not against
nomic** — so the question that decides adoption is still open.

It matters because the two candidates have different costs. Both share the expensive half (re-ingest,
re-index every derived collection, retrain the intent classifier, recreate the collection). The
**difference is the low lane**: nomic has MRL 64, so the funnel's fast first stage stays 64-wide and
the name `dense_64` stays true; gemma's smallest trained slot is 128, so the lane widens **and**
needs a code change (`store.py:451` hardcodes `using="dense_64"` while the slice is
`query_vector[:cfg.dense_dim_low]`, and the schema check keys on the literal `"dense_64"` — §I13).

    three arms, only TWO of them a contrast:
      qwen3@1024  the instrument ANCHOR (stored vectors) — pins this harness to §I70 via G1
      nomic@768   candidate, cluster-embedded with search_document: / search_query:
      gemma@768   candidate, cluster-embedded with title: none | text: / task: search result | query:

    primary endpoint: paired ceiling-normalised R@20 POST-rerank, gemma@768 − nomic@768, n = 133
    rule (pre-reg §3): δ > 0.020 and resolved -> gemma is worth the cost;
                       0 < δ <= 0.020, or unresolved -> take nomic;
                       δ resolves negative -> take nomic, and record the REVERSAL.

⚠️ **Two page-level recall conventions, reported side by side** (§I72's correction — its first run
was VOID on exactly this): the CONTRAST uses the PRODUCT's convention (pages of the top-k CHUNKS,
`evaluate_rag.py:333-341`); the ANCHOR rows use §I70's (top-k PAGES from the full deduped ranking),
because that is what the register's numbers were produced under.

Guards (pre-reg §4 — each must be able to FAIL)
-----------------------------------------------
  G1  §I70 convention reproduces §I70's qwen3@1024 R@20 0.293934 EXACTLY; pool 3,489; ceiling 888.
  G2  §I70 convention reproduces §I70's nomic@768 R@20 0.433930 EXACTLY — the stronger anchor: it
      pins the CANDIDATE's own embedding path (cluster prefixes included).
  G3  the rerank service is live and reordering.
  G4  negative control: the same list reranked twice returns the identical order.
  G5  every failed rerank call counted and reported, with the contrast's n stated.
  G6  A-vs-A for BOTH candidates: re-embedded at a different batch size, bit-identical.
  G7  one shared chunk→page mapping; ceiling 888; documents sent in cosine rank order.

Run:
    unset PYTHONPATH && export QDRANT_HOST=10.0.10.65 QDRANT_COLLECTION=knowledge_base_v2
    uv run python -u logs/p1/step10/ce_gvn.py
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
from src.pdf_ingestion.reranker import get_reranker  # noqa: E402
from src.pdf_ingestion.store import DocumentStore  # noqa: E402

QUERIES = REPO / "data/eval_queries_v2.json"
OUT = REPO / "logs/p1/step10/ce_gvn.json"

NEW_DOC = "7ba61432"
COLLECTION = "knowledge_base_v2"
DENSE_VEC = "dense_1024"
EMBED_URL = "http://10.0.10.70:8123/embed-text/v1/embeddings"

KS = (20, 100, 500, 1000)

GEMMA_HF = "google/embeddinggemma-300m"
GEMMA_DOC_PREFIX = "title: none | text: "
GEMMA_QRY_PREFIX = "task: search result | query: "
NOMIC_HF = "nomic-ai/nomic-embed-text-v1.5"
NOMIC_DOC_PREFIX = "search_document: "
NOMIC_QRY_PREFIX = "search_query: "

CANDIDATES = ("gemma", "nomic")          # the contrast
ANCHOR = "qwen3"                          # instrument anchor, not a candidate
ALL_ARMS = ("qwen3", "nomic", "gemma")

# §I70's rows, ceiling-normalised under §I70's OWN convention (top-k pages) — G1/G2 must be exact.
I70_ROWS = {"qwen3": 0.293934, "nomic": 0.433930, "gemma": 0.480410}
EXPECTED_POOL = 3489
EXPECTED_REACHABLE_PAGES = 888
EXPECTED_FETCH_K = 100
EXPECTED_TOP_K = 20
RESOLUTION_FLOOR = 0.020


def cluster_embed(texts: list[str], batch: int, model: str) -> np.ndarray:
    """Pooled vectors from the cluster, L2-normalised (verbatim from §I70/§I71/§I72)."""
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
    """Distinct pages in rank order (§I70's convention: rank every chunk, dedupe, take k pages)."""
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
    """The PRODUCT's convention (evaluate_rag.py:333-341): dedupe the top-k CHUNKS to pages."""
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
            "direction": ("first>second" if lo > 0 else "first<second" if hi < 0 else "straddles 0"),
            "wlt": {"first_worse": sum(1 for d in diffs if d < 0),
                    "first_better": sum(1 for d in diffs if d > 0),
                    "tie": sum(1 for d in diffs if d == 0)}}


def agg(rows: list[dict], stage: str, arm: str, key: str) -> dict:
    out = {}
    for k in KS:
        vals = [r[stage][arm][f"{key}{k}"] for r in rows
                if r.get(stage, {}).get(arm, {}).get(f"{key}{k}") is not None]
        out[f"R@{k}"] = round(statistics.mean(vals), 6) if vals else None
        out[f"n_queries_{key}@{k}"] = len(vals)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(OUT))
    ap.add_argument("--batch", type=int, default=128)
    ap.add_argument("--control-batch", type=int, default=64)
    ap.add_argument("--control-queries", type=int, default=5)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()
    if Path(args.out).exists() and not args.force:
        print(f"REFUSING to overwrite {args.out} without --force.", file=sys.stderr)
        return 4

    t0 = time.time()
    cfg = get_settings()
    verifiers: dict = {}

    fetch_k, top_k = int(cfg.reranker_fetch_k), int(cfg.reranker_top_k)
    g0 = {
        "qdrant_host": (cfg.qdrant_host or "").strip(), "qdrant_collection": cfg.qdrant_collection,
        "sv_rerank_url": cfg.sv_rerank_url, "reranker_model": cfg.reranker_model,
        "reranker_enabled": cfg.reranker_enabled,
        "reranker_fetch_k": fetch_k, "expected_fetch_k": EXPECTED_FETCH_K,
        "reranker_top_k": top_k, "expected_top_k": EXPECTED_TOP_K,
        "hyde_enabled": cfg.hyde_enabled, "window": [cfg.min_content_page, cfg.max_content_page],
    }
    g0["pass"] = bool(
        g0["qdrant_collection"] == COLLECTION
        and g0["qdrant_host"] and g0["qdrant_host"] not in ("localhost", "127.0.0.1")
        and g0["sv_rerank_url"] and g0["reranker_enabled"]
        and fetch_k == EXPECTED_FETCH_K and top_k == EXPECTED_TOP_K
    )
    verifiers["G0_resolved_config"] = g0
    print(f"G0: collection={cfg.qdrant_collection!r} rerank={cfg.sv_rerank_url!r} "
          f"model={cfg.reranker_model!r} fetch_k={fetch_k} top_k={top_k} pass={g0['pass']}")
    if not g0["pass"]:
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

    # ── embed both candidates over the same corpus, plus each one's A-vs-A control (G6) ───────
    corpus: dict[str, np.ndarray] = {ANCHOR: m_q}
    ctrl: dict[str, np.ndarray] = {}
    embed_seconds: dict[str, float] = {}
    for key, hf, pref in ((NOMIC_KEY := "nomic", NOMIC_HF, NOMIC_DOC_PREFIX),
                          ("gemma", GEMMA_HF, GEMMA_DOC_PREFIX)):
        t = time.time()
        corpus[key] = cluster_embed([pref + x for x in texts], batch=args.batch, model=hf)
        embed_seconds[key] = round(time.time() - t, 1)
        t = time.time()
        ctrl[key] = cluster_embed([pref + x for x in texts], batch=args.control_batch, model=hf)
        embed_seconds[f"{key}_control"] = round(time.time() - t, 1)
        print(f"  embedded {key}: {corpus[key].shape} in {embed_seconds[key]}s "
              f"(control {embed_seconds[f'{key}_control']}s)")

    g6: dict = {"pass": True}
    for key in CANDIDATES:
        a, b = corpus[key], ctrl[key]
        entry = {"batch_a": args.batch, "batch_b": args.control_batch,
                 "max_abs_diff": float(np.max(np.abs(a - b))) if a.shape == b.shape else None,
                 "n_rows_differing": int(np.sum(np.any(a != b, axis=1))) if a.shape == b.shape else None}
        entry["pass"] = bool(entry["max_abs_diff"] == 0.0)
        g6[key] = entry
        g6["pass"] = g6["pass"] and entry["pass"]
    verifiers["G6_A_vs_A_both_candidates"] = g6
    print("G6: " + "  ".join(f"{k}(max_abs_diff={v['max_abs_diff']})"
                             for k, v in g6.items() if k != "pass") + f"  pass={g6['pass']}")

    # ── query vectors, each arm on its own path ──────────────────────────────────────────────
    from src.pdf_ingestion.cluster_embedder import get_cluster_embedder
    qwen = get_cluster_embedder(cfg)
    qv: dict[str, np.ndarray] = {}
    v = np.asarray([qwen.embed_query(q["query"]) for q in queries], dtype=np.float64)
    qv[ANCHOR] = v / (np.linalg.norm(v, axis=1, keepdims=True) + 1e-12)
    for key, hf, pref in (("nomic", NOMIC_HF, NOMIC_QRY_PREFIX),
                          ("gemma", GEMMA_HF, GEMMA_QRY_PREFIX)):
        v = cluster_embed([pref + q["query"] for q in queries], batch=len(queries), model=hf)
        qv[key] = v / (np.linalg.norm(v, axis=1, keepdims=True) + 1e-12)
    print("query vectors ready")

    reranker = get_reranker(cfg)
    print(f"reranker: {type(reranker).__name__}  fallbacks so far={getattr(reranker, 'fallbacks', 0)}")

    results: list[dict] = []
    failures: list[dict] = []
    n_order_changes = 0
    s3_rows: list[dict] = []
    align_samples: list[dict] = []
    t3 = time.time()

    for i, q in enumerate(queries, 1):
        qid = q["id"]
        relevant = {int(p) for p in q["relevant_pages"]}
        ceil = relevant & reach
        row: dict = {"id": qid, "query_type": q.get("query_type"),
                     "n_relevant": len(relevant), "n_reachable": len(ceil),
                     "pre": {}, "post": {}, "i70": {}}

        for arm in ALL_ARMS:
            sims = corpus[arm] @ qv[arm][i - 1]
            order = np.argsort(-sims)
            cand_idx = [int(j) for j in order[:fetch_k]]

            # the §I70 SCREEN convention — the ANCHOR rows (G1/G2), not the contrast
            rk_all = rank_pages(sims, pages, len(pages))
            row["i70"][arm] = {
                **{f"c{k}": (round(len(set(rk_all[:k]) & ceil) / len(ceil), 6) if ceil else None)
                   for k in KS},
                **{f"r{k}": (round(len(set(rk_all[:k]) & relevant) / len(relevant), 6)
                             if relevant else None) for k in KS},
            }

            # the PRODUCT convention — both sides of the contrast
            row["pre"][arm] = {
                **{f"c{k}": (round(len(set(pages_of_chunk_idxs(cand_idx[:k], pages)) & ceil)
                                   / len(ceil), 6) if ceil else None) for k in KS},
                **{f"r{k}": (round(len(set(pages_of_chunk_idxs(cand_idx[:k], pages)) & relevant)
                                   / len(relevant), 6) if relevant else None) for k in KS},
            }

            docs = [{"text": texts[j], "_pool_idx": j} for j in cand_idx]
            if len(align_samples) < 3:
                align_samples.append({"id": qid, "arm": arm, "n_docs": len(docs),
                                      "aligned": all(docs[n]["text"] == texts[cand_idx[n]]
                                                     for n in range(len(cand_idx)))})

            fb_before = int(getattr(reranker, "fallbacks", 0))
            try:
                ranked = reranker.rerank(q["query"], docs, top_k=top_k)
            except Exception as exc:  # noqa: BLE001
                failures.append({"id": qid, "arm": arm, "error": f"{type(exc).__name__}: {exc}"})
                continue
            if int(getattr(reranker, "fallbacks", 0)) != fb_before:
                failures.append({"id": qid, "arm": arm, "error": "reranker fallback (G5)"})
                continue
            post_idx = [int(d["_pool_idx"]) for d in ranked]
            if not post_idx:
                failures.append({"id": qid, "arm": arm, "error": "empty ranking"})
                continue

            n_order_changes += int(post_idx != cand_idx[:len(post_idx)])
            row["post"][arm] = {
                **{f"c{k}": (round(len(set(pages_of_chunk_idxs(post_idx[:k], pages)) & ceil)
                                   / len(ceil), 6) if ceil else None) for k in KS},
                **{f"r{k}": (round(len(set(pages_of_chunk_idxs(post_idx[:k], pages)) & relevant)
                                   / len(relevant), 6) if relevant else None) for k in KS},
                "order_changed": bool(post_idx != cand_idx[:len(post_idx)]),
                "n_returned": len(post_idx),
            }

            if i <= args.control_queries:
                try:
                    again = reranker.rerank(q["query"], docs, top_k=top_k)
                    s3_rows.append({"id": qid, "arm": arm,
                                    "identical": bool([int(d["_pool_idx"]) for d in again] == post_idx)})
                except Exception as exc:  # noqa: BLE001
                    s3_rows.append({"id": qid, "arm": arm, "identical": False,
                                    "error": f"{type(exc).__name__}: {exc}"})

        results.append(row)
        if i % 20 == 0:
            print(f"  [{i}/{len(queries)}] {qid} … {time.time()-t3:.0f}s "
                  f"(failures {len(failures)})", flush=True)

    # ── G1/G2 — the two anchors, §I70's convention, EXACT ────────────────────────────────────
    i70_agg = {a: {"ceiling_norm": agg(results, "i70", a, "c"), "raw": agg(results, "i70", a, "r")}
               for a in ALL_ARMS}
    g1 = {"qwen3@1024_R@20": {"this_run": i70_agg["qwen3"]["ceiling_norm"]["R@20"],
                              "registered": I70_ROWS["qwen3"]},
          "pool_size": {"this_run": int(m_q.shape[0]), "expected": EXPECTED_POOL},
          "reachable_pages": {"this_run": len(reach), "expected": EXPECTED_REACHABLE_PAGES}}
    g1["qwen3@1024_R@20"]["match"] = bool(
        g1["qwen3@1024_R@20"]["this_run"] is not None
        and abs(g1["qwen3@1024_R@20"]["this_run"] - I70_ROWS["qwen3"]) < 1e-9)
    g1["pass"] = bool(g1["qwen3@1024_R@20"]["match"]
                      and g1["pool_size"]["this_run"] == EXPECTED_POOL
                      and g1["reachable_pages"]["this_run"] == EXPECTED_REACHABLE_PAGES)
    verifiers["G1_anchor_qwen3_is_I70s"] = g1

    g2 = {"nomic@768_R@20": {"this_run": i70_agg["nomic"]["ceiling_norm"]["R@20"],
                             "registered": I70_ROWS["nomic"]}}
    g2["nomic@768_R@20"]["match"] = bool(
        g2["nomic@768_R@20"]["this_run"] is not None
        and abs(g2["nomic@768_R@20"]["this_run"] - I70_ROWS["nomic"]) < 1e-9)
    g2["pass"] = bool(g2["nomic@768_R@20"]["match"])
    verifiers["G2_anchor_nomic_is_I70s"] = g2
    print(f"G1: §I70 convention qwen3@1024 R@20={g1['qwen3@1024_R@20']['this_run']} "
          f"(want {I70_ROWS['qwen3']})  pass={g1['pass']}")
    print(f"G2: §I70 convention nomic@768  R@20={g2['nomic@768_R@20']['this_run']} "
          f"(want {I70_ROWS['nomic']})  pass={g2['pass']}")
    print(f"    (gemma@768 anchor for reference: {i70_agg['gemma']['ceiling_norm']['R@20']}, "
          f"§I70 {I70_ROWS['gemma']})")

    # ── G3/G4/G5/G7 ──────────────────────────────────────────────────────────────────────────
    scored = sum(1 for r in results for a in ALL_ARMS if r["post"].get(a))
    g3 = {"n_rerank_calls_scored": scored, "n_order_changes": n_order_changes}
    g3["pass"] = bool(n_order_changes > 0 and scored > 0)
    verifiers["G3_reranker_live_and_reordering"] = g3

    g4 = {"n_controls": len(s3_rows), "n_identical": sum(1 for r in s3_rows if r.get("identical")),
          "rows": s3_rows}
    g4["pass"] = bool(s3_rows and g4["n_identical"] == len(s3_rows))
    verifiers["G4_reranker_deterministic"] = g4

    g5 = {"n_failures": len(failures), "failures": failures, "n_queries": len(results),
          "pass": True}
    missing = [r["id"] for r in results if any(a not in r["post"] for a in ALL_ARMS)]
    failed_ids = {f["id"] for f in failures}
    g5["queries_missing_an_arm_without_a_recorded_failure"] = sorted(set(missing) - failed_ids)
    g5["pass"] = bool(not g5["queries_missing_an_arm_without_a_recorded_failure"])
    verifiers["G5_failures_reported"] = g5

    g7 = {"pages_array_sha256": hashlib.sha256(pages.tobytes()).hexdigest(),
          "n_chunks": int(pages.shape[0]), "ceiling_size": len(reach),
          "alignment_samples": align_samples,
          "all_samples_aligned": all(x["aligned"] for x in align_samples)}
    g7["pass"] = bool(g7["all_samples_aligned"] and len(reach) == EXPECTED_REACHABLE_PAGES)
    verifiers["G7_shared_page_mapping_and_alignment"] = g7

    print(f"G3: {n_order_changes} of {scored} reranked lists changed order  pass={g3['pass']}")
    print(f"G4: {g4['n_identical']}/{g4['n_controls']} repeat calls identical  pass={g4['pass']}")
    print(f"G5: {g5['n_failures']} failure(s); unrecorded={g5['queries_missing_an_arm_without_a_recorded_failure']}  pass={g5['pass']}")

    # ── the contrast: gemma − nomic, PRE and POST ────────────────────────────────────────────
    stages_agg = {st: {a: {"ceiling_norm": agg(results, st, a, "c"), "raw": agg(results, st, a, "r")}
                       for a in ALL_ARMS} for st in ("pre", "post")}

    def contrast(stage: str, first: str, second: str, key: str, k: int) -> dict:
        diffs = [r[stage][first][f"{key}{k}"] - r[stage][second][f"{key}{k}"]
                 for r in results
                 if r[stage].get(first, {}).get(f"{key}{k}") is not None
                 and r[stage].get(second, {}).get(f"{key}{k}") is not None]
        return paired_ci(diffs)

    pre_d = contrast("pre", "gemma", "nomic", "c", 20)
    post_d = contrast("post", "gemma", "nomic", "c", 20)
    survival = (round(post_d["mean"] / pre_d["mean"], 6)
                if pre_d["mean"] and post_d["mean"] is not None else None)
    floor = (round(1.96 * (post_d["sd"] or 0.0) / math.sqrt(post_d["n"]), 6) if post_d["n"] else None)

    if post_d["resolved"] and (post_d["mean"] or 0) > RESOLUTION_FLOOR:
        verdict, disposition = "gemma is worth its extra cost", "GEMMA"
    elif post_d["resolved"] and (post_d["mean"] or 0) <= RESOLUTION_FLOOR:
        verdict, disposition = ("what survives is at or below the resolution floor", "NOMIC")
    elif post_d["resolved"]:
        verdict, disposition = ("the cross-encoder REVERSES the base-lane ordering", "NOMIC")
    else:
        verdict, disposition = ("the contrast is UNRESOLVED at this n", "NOMIC")

    decision = {
        "primary_endpoint": "paired ceiling-normalised R@20 POST-rerank, gemma@768 − nomic@768",
        "pre_delta": pre_d["mean"], "pre_ci": pre_d["ci95"], "pre_n": pre_d["n"],
        "pre_wlt": pre_d["wlt"],
        "post_delta": post_d["mean"], "post_ci": post_d["ci95"], "post_n": post_d["n"],
        "post_wlt": post_d["wlt"],
        "survival_ratio_post_over_pre": survival,
        "resolution_floor_this_run": floor,
        "resolution_floor_preregistered": RESOLUTION_FLOOR,
        "verdict": verdict,
        "DISPOSITION": disposition,
        "reversal": bool(post_d["resolved"] and (post_d["mean"] or 0) < 0),
        "scope": ("stage diagnostic, NOT the product endpoint: the cross-encoder is applied to a "
                  "cosine-ordered pool, with no Qdrant RRF (§I68 nondeterministic), no dedup/MMR, "
                  "no SPLADE lane, no DA/graph/RAPTOR/visual lane, no generator"),
    }

    out = {
        "meta": {
            "generated_by": "logs/p1/step10/ce_gvn.py",
            "preregistration":
                ".hermes/plans/2026-10-24-p1-gemma-vs-nomic-at-the-cross-encoder-preregistration.md",
            "what": ("§I74 — the last cheap measurement before the adoption call: at the "
                     "cross-encoder, is gemma@768 worth its extra cost over nomic@768? The extra "
                     "cost is the LOW LANE: nomic has MRL 64 so `dense_64` stays true and "
                     "64-wide; gemma's smallest slot is 128, so the lane widens AND the hardcoded "
                     "name at store.py:451 needs a rename plus a schema-detection repoint."),
            "corpus": NEW_DOC, "collection": COLLECTION,
            "pool_size": int(m_q.shape[0]), "reachable_pages": len(reach),
            "fetch_k": fetch_k, "top_k": top_k,
            "embed_url": EMBED_URL, "rerank_url": cfg.sv_rerank_url,
            "reranker_model": cfg.reranker_model,
            "arms": {"qwen3": "ANCHOR (stored dense_1024) — not a candidate",
                     "nomic": {"hf": NOMIC_HF, "dim": 768, "doc_prefix": NOMIC_DOC_PREFIX,
                               "qry_prefix": NOMIC_QRY_PREFIX, "low_slot": 64},
                     "gemma": {"hf": GEMMA_HF, "dim": 768, "doc_prefix": GEMMA_DOC_PREFIX,
                               "qry_prefix": GEMMA_QRY_PREFIX, "low_slot": 128}},
            "i70_rows_for_the_anchors": I70_ROWS,
            "hyde": "OFF (raw query vectors)",
            "metric_conventions": {
                "contrast": ("pages of the top-k CHUNKS, deduped — the PRODUCT's convention "
                             "(scripts/evaluate_rag.py:333-341). Both sides of the contrast."),
                "anchor": ("top-k PAGES from the full deduped chunk ranking — §I70's screen "
                           "convention, used ONLY for G1/G2 because that is what the register's "
                           "rows were produced under."),
            },
            "no_llm_calls": True, "no_writes_to_collections": True,
            "embed_seconds": embed_seconds, "wall_seconds": round(time.time() - t0, 1),
        },
        "verifiers": verifiers,
        "arms": stages_agg,
        "arms_i70_convention": i70_agg,
        "endpoints": {
            "primary_gemma_minus_nomic": {
                "pre_ceiling_norm_R@20": pre_d, "post_ceiling_norm_R@20": post_d,
                "post_raw_R@20": contrast("post", "gemma", "nomic", "r", 20),
                "post_ceiling_norm_R@100": contrast("post", "gemma", "nomic", "c", 100),
            },
            "context_gemma_minus_qwen3": {"post_ceiling_norm_R@20":
                                          contrast("post", "gemma", "qwen3", "c", 20)},
            "context_nomic_minus_qwen3": {"post_ceiling_norm_R@20":
                                          contrast("post", "nomic", "qwen3", "c", 20)},
        },
        "decision": decision,
        "queries": results,
    }
    Path(args.out).write_text(json.dumps(out, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    h = hashlib.sha256(Path(args.out).read_bytes()).hexdigest()
    print(f"\nwrote {args.out}\nsha256 {h}")

    print("\n=== §I70 convention (top-k PAGES) — the anchors G1/G2 ===")
    for a in ALL_ARMS:
        c = i70_agg[a]["ceiling_norm"]
        print(f"  {a:>6} R@20 {c['R@20']:.6f}   R@100 {c['R@100']:.6f}   "
              f"(§I70 {I70_ROWS[a]})")

    print("\n=== product convention — PRE vs POST, per arm ===")
    print(f"  {'stage':>5} {'arm':>6} {'R@20':>9} {'R@100':>9}")
    for st in ("pre", "post"):
        for a in ALL_ARMS:
            c = stages_agg[st][a]["ceiling_norm"]
            print(f"  {st:>5} {a:>6} {c['R@20']:>9.6f} {c['R@100']:>9.6f}")

    print("\n=== the primary contrast: gemma − nomic ===")
    for label, d in (("PRE  (cosine order)", pre_d), ("POST (cross-encoder)", post_d)):
        ci = d["ci95"]
        print(f"  {label:22} Δ {d['mean']:+.6f} [{ci[0]:+.6f},{ci[1]:+.6f}] n={d['n']} "
              f"{'RESOLVED' if d['resolved'] else 'UNRESOLVED'}  W/L/T "
              f"{d['wlt']['first_worse']}/{d['wlt']['first_better']}/{d['wlt']['tie']}")
    print(f"  survival ratio (post/pre) = {survival}   resolution floor = {floor}")
    print(f"\n  DECISION: {decision['DISPOSITION']} — {decision['verdict']}")

    print("\nverifiers: " + "  ".join(f"{k.split('_')[0]}={v['pass']}"
                                      for k, v in verifiers.items()))
    return 0 if all(v["pass"] for v in verifiers.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
