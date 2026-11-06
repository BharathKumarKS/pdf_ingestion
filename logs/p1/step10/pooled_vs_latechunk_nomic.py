"""Is LATE CHUNKING the cause of v3's full-dim deficit? — POOLED vs LATE-CHUNKED nomic, same corpus,
same instrument.

WHY. §I86 measured v3 (the index we built) **worse** than v2 at full-dim, no-prefilter coverage
(L=500: 0.6887 vs 0.8286, RESOLVED). §I63's oracle measured nomic **better** (+0.1400) — but §I63
embedded **POOLED** whole-chunk vectors (`cross_embedder_experiment.py:295`) while v3 stores
**LATE-CHUNKED** ones (§I81 Shape B). So the two disagree because they are different objects, and the
open question is whether **late chunking (E3) is what costs the coverage**. That decides whether the
fine-tune (S6) is aimed at the embedder or at the ingestion.

WHAT IT MEASURES — three arms, ONE instrument (full-dim exact cosine, NO prefilter, coverage of a
query's REACHABLE labelled pages, 133 gold queries):
  * `qwen3_v2_stored`     — v2's stored `dense_1024` (the reference; §I86 L500 = 0.8286)
  * `nomic_v3_stored`     — v3's stored `dense_full` = LATE-CHUNKED nomic (§I86 L500 = 0.6887)
  * `nomic_pooled`        — nomic embedded **pooled** over each chunk's whole `text`, with the
                            `search_document: ` prefix (this is §I63's N-arm construction)

GUARDS (each must be able to fail):
  G1  `qwen3_v2_stored` reproduces §I86's L=500 (0.8286 ± 0.002)
  G2  `nomic_v3_stored` reproduces §I86's L=500 (0.6887 ± 0.002)
  G3  133 queries in every arm, 0 errors
  G4  the three arms share ONE chunk set and ONE page mapping (same corpus)

READ-ONLY. No writes, no LLM. Queries and pooled chunks go to the cluster embed endpoint only.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import statistics
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

import numpy as np  # noqa: E402
import httpx  # noqa: E402
from loguru import logger  # noqa: E402
from qdrant_client.models import FieldCondition, Filter, MatchValue, Range  # noqa: E402

from src.core.config import get_settings  # noqa: E402
from src.pdf_ingestion.cluster_embedder import get_cluster_embedder  # noqa: E402

QUERIES = "data/eval_queries_v2.json"
OUT = "logs/p1/step10/pooled_vs_latechunk_nomic.json"
URL = "http://10.0.10.70:8123/embed-text/v1/embeddings"
NOMIC = "nomic-ai/nomic-embed-text-v1.5"
QWEN = "Qwen/Qwen3-Embedding-0.6B"
DOC_PREFIX = "search_document: "
QRY_PREFIX = "search_query: "
LS = (100, 500, 1000, 2000)
I86 = {"qwen3_v2_stored": 0.8286, "nomic_v3_stored": 0.6887}
I86_TOL = 0.002


def flt(cfg) -> Filter:
    must_not = [FieldCondition(key="source_type", match=MatchValue(value="raptor_summary"))]
    must_not.append(FieldCondition(key="page_number", range=Range(lt=cfg.min_content_page)))
    must_not.append(FieldCondition(key="page_number", range=Range(gt=cfg.max_content_page)))
    must_not.append(FieldCondition(key="is_content", match=MatchValue(value=False)))
    return Filter(must_not=must_not)


def pooled(texts: list[str], model: str = NOMIC, prefix: str = DOC_PREFIX,
           batch: int = 64) -> np.ndarray:
    """The endpoint's POOLED output for (prefixed) texts — §I63's N-arm construction.

    ⚠️ `model`/`prefix` are explicit because the SAME probe needs a pooled arm for EACH embedder:
    comparing `nomic_pooled` against `qwen3_stored` would repeat §I63's own construction asymmetry
    in the opposite direction (nomic pooled vs qwen3 late-chunked).
    """
    out: list[list[float]] = []
    for i in range(0, len(texts), batch):
        chunk = [prefix + t for t in texts[i:i + batch]]
        for attempt in range(3):
            try:
                r = httpx.post(URL, json={"input": chunk, "model": model}, timeout=180)
                r.raise_for_status()
                data = r.json()
                data = data.get("data", data)
                out.extend(d["embedding"] if isinstance(d, dict) else d for d in data)
                break
            except Exception as exc:  # noqa: BLE001
                logger.warning("pooled batch {} attempt {} failed: {}", i, attempt, exc)
                if attempt == 2:
                    raise
        if (i // batch) % 10 == 0:
            logger.info("  pooled {}/{}", min(i + batch, len(texts)), len(texts))
    v = np.asarray(out, dtype=np.float64)
    return v / (np.linalg.norm(v, axis=1, keepdims=True) + 1e-12)


def scroll(client, name, dense, cfg):
    vs, pages, texts = [], [], []
    offset = None
    while True:
        pts, offset = client.scroll(collection_name=name, scroll_filter=flt(cfg), limit=1000,
                                    offset=offset, with_payload=["page_number", "text"],
                                    with_vectors=[dense])
        for p in pts:
            v = p.vector[dense] if isinstance(p.vector, dict) else p.vector
            pg = (p.payload or {}).get("page_number")
            if v is None or pg is None:
                continue
            vs.append(v)
            pages.append(int(pg))
            texts.append((p.payload or {}).get("text", "") or "")
        if offset is None:
            break
    m = np.asarray(vs, dtype=np.float64)
    m /= (np.linalg.norm(m, axis=1, keepdims=True) + 1e-12)
    return m, np.asarray(pages, dtype=np.int64), texts


def ci(d):
    n = len(d)
    if n < 2:
        return [float("nan"), float("nan")]
    m = statistics.mean(d)
    h = 1.96 * statistics.stdev(d) / math.sqrt(n)
    return [m - h, m + h]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=OUT)
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()
    if Path(args.out).exists() and not args.force:
        print(f"REFUSING to overwrite {args.out} without --force.", file=sys.stderr)
        return 4

    cfg = get_settings()
    if cfg.qdrant_collection != "knowledge_base_v2":
        print("ABORT: run with QDRANT_COLLECTION=knowledge_base_v2.", file=sys.stderr)
        return 3
    from src.core.database import get_qdrant
    client = get_qdrant(cfg)

    raw = json.loads(Path(QUERIES).read_text())
    queries = [q for q in raw if isinstance(q, dict)
               and str(q.get("id", "")).startswith(("gold-", "ovw-"))
               and (q.get("relevant_pages") or [])]
    queries.sort(key=lambda q: q["id"])
    logger.info("queries: {}", len(queries))

    t0 = time.time()
    m_q, pages, texts = scroll(client, "knowledge_base_v2", "dense_1024", cfg)
    m_n, pages_n, texts_n = scroll(client, "knowledge_base_v3", "dense_full", cfg)
    logger.info("corpus: v2 {} chunks / v3 {} chunks  ({}s)", len(pages), len(pages_n),
                round(time.time() - t0, 1))
    if len(pages) != len(pages_n) or not np.array_equal(pages, pages_n):
        print("ABORT: v2 and v3 do not share a chunk->page mapping.", file=sys.stderr)
        return 3

    # pooled arms over the same texts — ONE per embedder, so no construction asymmetry survives
    t1 = time.time()
    m_p = pooled(texts, model=NOMIC, prefix=DOC_PREFIX)
    logger.info("pooled nomic: {} x {}d ({}s)", *m_p.shape, round(time.time() - t1, 1))
    t1b = time.time()
    m_qp = pooled(texts, model=QWEN, prefix="")   # Qwen3 needs NO document prefix
    logger.info("pooled qwen3: {} x {}d ({}s)", *m_qp.shape, round(time.time() - t1b, 1))

    # query vectors — nomic query path for the nomic arms, qwen3 for the reference arm
    qwen = get_cluster_embedder(cfg)
    Qq = np.asarray([qwen.embed_query(q["query"]) for q in queries], dtype=np.float64)
    Qq /= (np.linalg.norm(Qq, axis=1, keepdims=True) + 1e-12)
    r = httpx.post(URL, json={"input": [QRY_PREFIX + q["query"] for q in queries], "model": NOMIC},
                   timeout=180).json()
    r = r.get("data", r)
    Qn = np.asarray([d["embedding"] if isinstance(d, dict) else d for d in r], dtype=np.float64)
    Qn /= (np.linalg.norm(Qn, axis=1, keepdims=True) + 1e-12)

    coll_pages = {int(p) for p in pages.tolist()}
    arms = {"qwen3_v2_stored": (m_q, Qq), "qwen3_pooled": (m_qp, Qq),
            "nomic_v3_stored": (m_n, Qn), "nomic_pooled": (m_p, Qn)}

    per_query, cov = [], {a: {L: [] for L in LS} for a in arms}
    for i, q in enumerate(queries):
        rel = {int(p) for p in q["relevant_pages"]}
        reach = rel & coll_pages
        rec = {"id": q["id"], "query_type": q.get("query_type"), "n_reachable": len(reach)}
        for a, (M, Q) in arms.items():
            order = np.argsort(-(M @ Q[i]), kind="stable")
            for L in LS:
                got = {int(pages[j]) for j in order[:L]}
                c = (len(got & reach) / len(reach)) if reach else None
                if c is not None:
                    cov[a][L].append(c)
                rec[f"{a}_L{L}"] = c
        per_query.append(rec)

    agg = {a: {str(L): round(statistics.mean(cov[a][L]), 6) if cov[a][L] else None for L in LS}
           for a in arms}
    # paired contrasts at L=500 — each arm pair is scored on the SAME 133 queries, so the per-query
    # differences are paired (the standard convention here).
    def paired_contrast(a_key: str, b_key: str) -> dict:
        d = [r_[f"{a_key}_L500"] - r_[f"{b_key}_L500"] for r_ in per_query
             if r_.get(f"{a_key}_L500") is not None and r_.get(f"{b_key}_L500") is not None]
        lo, hi = ci(d)
        return {"n": len(d), "mean": round(statistics.mean(d), 6),
                "ci95": [round(lo, 6), round(hi, 6)], "resolved": bool(lo > 0 or hi < 0),
                "wins": sum(1 for x in d if x > 0), "losses": sum(1 for x in d if x < 0),
                "ties": sum(1 for x in d if x == 0)}

    contrasts = {
        # THE isolation: same model, same corpus, same queries — only the construction differs
        "nomic_pooled_minus_nomic_latechunked": paired_contrast("nomic_pooled", "nomic_v3_stored"),
        "qwen3_pooled_minus_qwen3_latechunked": paired_contrast("qwen3_pooled", "qwen3_v2_stored"),
        # the EMBEDDER comparison, now like-for-like (both pooled, both late-chunked)
        "nomic_pooled_minus_qwen3_pooled": paired_contrast("nomic_pooled", "qwen3_pooled"),
        "nomic_latechunked_minus_qwen3_latechunked": paired_contrast("nomic_v3_stored", "qwen3_v2_stored"),
    }

    guards = {
        "G1_qwen3_reproduces_I86_L500": abs(agg["qwen3_v2_stored"]["500"] - I86["qwen3_v2_stored"]) <= I86_TOL,
        "G2_nomic_v3_reproduces_I86_L500": abs(agg["nomic_v3_stored"]["500"] - I86["nomic_v3_stored"]) <= I86_TOL,
        "G3_133_all_arms": len(per_query) == 133,
        "G4_same_corpus_and_pages": len(pages) == len(pages_n) and np.array_equal(pages, pages_n),
    }
    art = {
        "meta": {
            "question": "is LATE CHUNKING the cause of v3's full-dim deficit? (pooled vs late-chunked nomic)",
            "unit": "coverage of a query's REACHABLE labelled pages, full-dim exact cosine, NO prefilter",
            "n_chunks": len(pages), "n_pages": len(coll_pages), "n_queries": len(per_query),
            "ls": list(LS), "nomic_model": NOMIC, "doc_prefix": DOC_PREFIX, "query_prefix": QRY_PREFIX,
            "no_writes": True, "no_llm": True,
            "note": ("`nomic_v3_stored` IS the late-chunked index (§I81 Shape B). `nomic_pooled` is "
                     "§I63's N-arm construction. `qwen3_v2_stored` is the reference."),
        },
        "guards": guards,
        "coverage": agg,
        "contrasts_L500": contrasts,
        "per_query": per_query,
    }
    Path(args.out).write_text(json.dumps(art, indent=2))
    sha = hashlib.sha256(Path(args.out).read_bytes()).hexdigest()
    print(json.dumps({k: art[k] for k in ("guards", "coverage", "contrasts_L500")}, indent=2))
    print(f"\nartifact: {args.out}\nsha256: {sha}")
    failed = [k for k, v in guards.items() if v is False]
    print("ALL GUARDS PASS" if not failed else "GUARD FAILURE: " + ", ".join(failed))
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
