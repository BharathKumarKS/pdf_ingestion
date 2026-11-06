"""The overview retrieval-signal probe (§I112).

Pre-registration: `.hermes/plans/2026-11-04-p1-overview-signal-probe-preregistration.md` (committed ALONE).

Question: does a different QUERY REPRESENTATION make the DENSE lane rank the overview gold higher?
§I111 showed the fused pool order == the dense-only order for overview, and 60.5% of the pooled gold
sits at ranks 21-100 — so the dense lane's scoring is where the loss is.

READ-ONLY. No collection write, no re-ingest, no `src/` change. The index and the lane config are held
fixed; only the query text fed to the dense lane varies.

Arms (dense lane, top-100 recorded):
  A  the shipped single HyDE hypothetical (the frozen §I73 cache value)
  B  the raw query (a known-worse control)
  C  max  over 5 hypotheticals' dense scores, per page
  D  mean over 5 hypotheticals' dense scores, per page

Run:  .venv/bin/python logs/p1/step10/overview_signal_probe.py
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

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from loguru import logger  # noqa: E402

from src.core.config import get_settings  # noqa: E402
from src.pdf_ingestion.cluster_embedder import get_cluster_embedder  # noqa: E402
from src.pdf_ingestion.hyde_cache import load as load_hyde, prompt_for  # noqa: E402
from src.pdf_ingestion.store import DocumentStore  # noqa: E402

QUERIES = "data/eval_queries_v2.json"
HYP_CACHE = Path("logs/p1/step10/overview_signal_hypotheses.json")
OUT = Path("logs/p1/step10/overview_signal_probe.json")
N_HYP = 5
LANE_LIMIT = 100          # record the dense lane's top-100 (the rank metric lives here)
K = 20


def _overview() -> list[dict]:
    raw = json.loads(Path(QUERIES).read_text())
    q = [x for x in raw if isinstance(x, dict) and x.get("query_type") == "overview"
         and (x.get("relevant_pages") or [])]
    q.sort(key=lambda x: x["id"])
    return q


def _build_hypotheses(queries: list[dict], cfg) -> dict:
    """FROZEN hypotheses: generate once, cache, reuse. A cache hit never calls the LLM.

    ⚠️ The cache is MERGED, not replaced: a `--limit 2` dry run must not poison the full run with a
    2-query cache (the full run would KeyError on the other 38).
    """
    cache: dict[str, list[str]] = {}
    if HYP_CACHE.exists():
        cache = json.loads(HYP_CACHE.read_text())
        logger.info("hypotheses cache loaded: {} queries", len(cache))
    missing = [q for q in queries if len(cache.get(q["id"]) or []) < N_HYP]
    if not missing:
        return cache

    from src.core.llm import call_llm
    hyde = load_hyde(Path(QUERIES), cfg=cfg)
    # ⚠️ `call_llm` has no temperature knob, so diversity comes from the PROMPT, not sampling. Each
    # variant asks for a different angle on the same question; all five are frozen to the cache.
    variants = [
        "Write a short, factual physics passage (2-3 sentences) that would answer this question, in the "
        "style of a textbook.",
        "Write the passage a lecturer would say aloud when introducing this topic, in 2-3 sentences.",
        "Write a concise technical explanation of this topic using the key terms a student would search "
        "for, in 2-3 sentences.",
        "Summarise what a textbook chapter covering this question would say, focusing on the underlying "
        "principle, in 2-3 sentences.",
    ]
    for q in missing:
        hyp0 = hyde.get(q["id"])                    # raises on a miss — never a live call for hyp0
        hyps = [hyp0]
        for i, variant in enumerate(variants, start=1):
            try:
                h = call_llm(
                    prompt=f"{variant}\n\nQuestion: {q['query']}",
                    system="You are a physics textbook author.",
                    settings=cfg, timeout=60,
                )
                hyps.append(h.strip() if h else "")
            except Exception as exc:  # noqa: BLE001
                logger.warning("[{}] hypothesis {} failed: {}", q["id"], i, exc)
                hyps.append("")
        cache[q["id"]] = hyps
        logger.info("[{}] {} hypotheses built", q["id"], len(hyps))
    HYP_CACHE.write_text(json.dumps(cache, indent=1))
    return cache


def _dense_lane(store, embedder, cfg, text: str, query_id: str) -> list[dict]:
    """The dense lane ALONE: SPLADE + ColBERT are switched off on the store, so `search` returns the
    dense funnel's own order (dense_64 prefetch -> dense_full rescore). This is the product's own code
    path, not a re-implementation.

    ⚠️ `store.search` returns RAW CHUNK hits — several chunks per page, NO page dedup (the product's
    `run_retrieval` dedups later). The rank metric is over PAGES, so we dedup by page preserving order,
    exactly as `fusion_attribution._pages_of` does. Without this the duplicate-page hits consume top-20
    slots and R@20 is depressed (this omission voided the first run — G4 caught it)."""
    qv = embedder.embed_query(text)
    hits = store.search(qv, tenant_id="global", limit=LANE_LIMIT, query_text=None)
    out, seen = [], set()
    for h in hits:
        pg = (h.get("payload") or h).get("page_number")
        if pg is None:
            continue
        pg = int(pg)
        if pg in seen:
            continue
        seen.add(pg)
        out.append({"page": pg, "score": float(h.get("score") or 0.0)})
    return out


def _ndcg_at_20(pages: list[int], gold: set[int], k: int = K) -> float:
    dcg = sum(1.0 / math.log2(i + 1) for i, p in enumerate(pages[:k], start=1) if p in gold)
    idcg = sum(1.0 / math.log2(i + 1) for i in range(1, min(k, len(gold)) + 1))
    return dcg / idcg if idcg else 0.0


def _metrics(pages: list[int], gold: set[int]) -> dict:
    r20 = len(gold & set(pages[:K])) / len(gold) if gold else 0.0
    hit = 1.0 if gold & set(pages[:K]) else 0.0
    ranks = [i for i, p in enumerate(pages, start=1) if p in gold]
    return {"R@20": r20, "nDCG@20": _ndcg_at_20(pages, gold), "Hit@20": hit,
            "mean_gold_rank": (statistics.mean(ranks) if ranks else None),
            "gold_in_top100": len(gold & set(pages))}


def _aggregate(per_hyp: list[list[dict]], mode: str) -> list[int]:
    """Union the pages across the hypotheses; score each by max or mean (0.0 when absent)."""
    pages_all: set[int] = set()
    for lst in per_hyp:
        pages_all |= {h["page"] for h in lst}
    table: dict[int, float] = {}
    for pg in pages_all:
        vals = [next((h["score"] for h in lst if h["page"] == pg), 0.0) for lst in per_hyp]
        table[pg] = max(vals) if mode == "max" else sum(vals) / len(vals)
    return [pg for pg, _ in sorted(table.items(), key=lambda kv: -kv[1])][:LANE_LIMIT]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    cfg = get_settings()
    queries = _overview()
    if args.limit:
        queries = queries[: args.limit]
    logger.info("overview queries: {}", len(queries))

    # ⚠️ The dense lane ALONE: switch the other lanes off for this process.
    cfg.splade_enabled = False
    cfg.colbert_enabled = False

    store = DocumentStore(cfg)
    embedder = get_cluster_embedder(cfg)
    hyps = _build_hypotheses(queries, cfg)

    per_query, errors = [], []
    t0 = time.time()
    for i, q in enumerate(queries, 1):
        qid, gold = q["id"], set(q["relevant_pages"])
        try:
            rep_texts = {"A": hyps[qid][0], "B": q["query"]}
            per_hyp = [_dense_lane(store, embedder, cfg, t, qid) for t in hyps[qid]]
            lane = {"A": _dense_lane(store, embedder, cfg, rep_texts["A"], qid),
                    "B": _dense_lane(store, embedder, cfg, rep_texts["B"], qid)}
            pages = {"A": [h["page"] for h in lane["A"]],
                     "B": [h["page"] for h in lane["B"]],
                     "C": _aggregate(per_hyp, "max"),
                     "D": _aggregate(per_hyp, "mean")}
            rec = {"id": qid, "n_relevant": len(gold), "gold": sorted(gold),
                   "pages": pages,
                   "metrics": {a: _metrics(pages[a], gold) for a in "ABCD"},
                   "determinism_A": [h["page"] for h in _dense_lane(store, embedder, cfg, rep_texts["A"], qid)]}
            per_query.append(rec)
        except Exception as exc:  # noqa: BLE001
            errors.append({"id": qid, "error": f"{type(exc).__name__}: {exc}"})
            logger.error("[{}] FAILED: {}", qid, exc)
        if i % 5 == 0:
            logger.info("  {}/{} queries", i, len(queries))
    wall = time.time() - t0

    arms = {}
    for a in "ABCD":
        rs = [r["metrics"][a] for r in per_query]
        arms[a] = {
            "R@20": statistics.mean(x["R@20"] for x in rs),
            "nDCG@20": statistics.mean(x["nDCG@20"] for x in rs),
            "Hit@20": statistics.mean(x["Hit@20"] for x in rs),
            "mean_gold_rank": statistics.mean([x["mean_gold_rank"] for x in rs
                                               if x["mean_gold_rank"] is not None]),
        }

    def paired(a: str, b: str, key: str) -> dict:
        d = [r["metrics"][b][key] - r["metrics"][a][key] for r in per_query]
        m = statistics.mean(d)
        half = 1.96 * statistics.stdev(d) / (len(d) ** 0.5) if len(d) > 1 else float("nan")
        return {"n": len(d), "mean": m, "ci": [m - half, m + half],
                "resolved": (m - half > 0 or m + half < 0),
                "wins": sum(1 for x in d if x > 0), "losses": sum(1 for x in d if x < 0)}

    guards = {
        "G1_population_40": len(per_query) == 40,
        "G2_zero_errors": len(errors) == 0,
        "G3_hypotheses_frozen": HYP_CACHE.exists(),
        "G4_armA_reproduces_I111_dense_only": abs(arms["A"]["R@20"] - 0.2128) <= 0.020,
        "G5_armB_differs_from_A": any(r["pages"]["B"] != r["pages"]["A"] for r in per_query),
        "G6_lane_ordered_len_ge_20": all(len(r["pages"]["A"]) >= 20 for r in per_query),
        "G7_determinism_A": all(r["pages"]["A"] == r["determinism_A"] for r in per_query),
    }

    artifact = {
        "meta": {"question": "does a different query representation rank the overview gold higher?",
                 "prereg": ".hermes/plans/2026-11-04-p1-overview-signal-probe-preregistration.md",
                 "lane": "dense only (dense_64 prefetch -> dense_full rescore), limit 100",
                 "arms": {"A": "single HyDE hypothetical", "B": "raw query",
                          "C": "multi-hypothesis max (N=5)", "D": "multi-hypothesis mean (N=5)"},
                 "collection": cfg.qdrant_collection, "dense_model": cfg.dense_model,
                 "n_hypotheses": N_HYP, "wall_seconds": round(wall, 1)},
        "aggregates": arms,
        "deltas": {"C-A": paired("A", "C", "R@20"), "D-A": paired("A", "D", "R@20"),
                   "B-A": paired("A", "B", "R@20"),
                   "C-A_ndcg": paired("A", "C", "nDCG@20"), "D-A_ndcg": paired("A", "D", "nDCG@20")},
        "guards": guards,
        "errors": errors,
        "per_query": per_query,
    }
    OUT.write_text(json.dumps(artifact, indent=1))
    sha = hashlib.sha256(OUT.read_bytes()).hexdigest()
    print(json.dumps({"aggregates": arms, "deltas": artifact["deltas"], "guards": guards}, indent=1))
    print(f"\nartifact: {OUT}\nsha256: {sha}")
    failed = [k for k, v in guards.items() if not v]
    print("ALL GUARDS PASS" if not failed else "GUARD FAILURE: " + ", ".join(failed))
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
