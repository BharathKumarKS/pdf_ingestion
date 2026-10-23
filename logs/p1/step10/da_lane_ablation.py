#!/usr/bin/env python
"""§I12/§A2 — the DA-lane ABLATION: what does `derivative_artifacts` actually contribute?

Why this exists
---------------
§I49 (2026-10-22) made the DA lane **live** again — `derivative_artifacts` was re-indexed from
768d to 1024d, `search_da` went from **0** hits to **20** on the §I12 discriminator, and preflight
went 2 BLOCKER(S) → all checks passed. That proved the lane *answers*. It did **not** measure
whether its answers change the retrieval result.

⚠️ The lane has **never** had a number on v2. The last run with a live DA lane was §D12
(2026-10-16, on the OLD document `6d55c52b`); the §3d smoke test (2026-10-19/20) ran with the lane
**dead** (768-vs-1024, §I12). This is a first measurement, not a re-measurement.

The comparison, and what makes it a single-variable change
----------------------------------------------------------
`store.search_with_das` is the production retrieval path. It appends the DA lane's resolved parent
chunks to the dense pool **before** page-dedup and MMR (`store.py:726-740`), so the lane is
**recall-only**: it can add candidates, never displace a dense hit. Both arms here:

  * run the SAME query, the SAME query vector, the SAME dense pool (`mmr_candidates`), the SAME
    collection and the SAME cross-encoder;
  * differ **only** in `cfg.da_enabled`.

Two endpoints are reported, because the lane's own metric and the product's metric are not the same:

  * **`recall_at_{fetch_k}` on the POOL** — the lane's direct contribution, and it needs no
    reranker. This is the honest headline for a recall-only lane.
  * **`recall_at_{top_k}` on the reranked top-20** — the product's endpoint, downstream of the
    cross-encoder, so it can only be as informative as that stage is.

⚠️ §I55 — the reranker swallows its own failures, and this probe detects them
-------------------------------------------------------------------------------
`ClusterCrossEncoderReranker.rerank` catches every exception, logs `RERANKER DISABLED`, and returns
the pool **unranked** (`reranker.py:131-141`). A fallback therefore makes both arms' top-20 the
pool's own first 20 — the DA-added chunks sit *last* in the pool, so the top-20 comparison is
**inert by construction** for that query. Measured on the real v2 pools
(`rerank_payload_probe.py`): **1 of 133** queries is rejected (500), deterministically, and the
trigger is content token-density, not size (a 50,773-char pool rejected while a 78,187-char pool
passed). This probe detects the fallback by object identity, retries once, and **reports and
excludes** any query it cannot rerank from the top-20 headline.

⚠️ HyDE is deliberately OFF, and that is what keeps the arms identical
---------------------------------------------------------------------------
`run_retrieval` (`evaluate_rag.py:158-177`) generates a hypothetical passage and embeds **that** for
factual/overview queries. Calling it once per arm would issue the LLM twice per query and could hand
the two arms **different** query vectors — HyDE would stop being arm-invariant and the
single-variable property would be lost. The raw query vector is used for both arms instead. HyDE is
arm-invariant *when held fixed*, so the **delta** is unaffected; the **absolute** numbers are not
production numbers and must not be quoted as such.

⚠️ The graph lane is NOT included. It fires on multihop queries only (`evaluate_rag.py:187-212`) and
is a second lever; including it would make a multihop delta attributable to either lane. Per-type
numbers are reported so that is visible.

Run:
    unset PYTHONPATH && export QDRANT_HOST=10.0.10.65 QDRANT_COLLECTION=knowledge_base_v2
    uv run python logs/p1/step10/da_lane_ablation.py
"""
from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scripts"))

import numpy as np  # noqa: E402

import evaluate_rag as ev  # noqa: E402  (the audited metric path)
from src.core.config import get_settings  # noqa: E402
from src.pdf_ingestion.cluster_embedder import get_cluster_embedder  # noqa: E402
from src.pdf_ingestion.reranker import get_reranker  # noqa: E402
from src.pdf_ingestion.store import DocumentStore  # noqa: E402

QUERIES = "data/eval_queries_v2.json"
KS = (3, 5, 10, 20)
HEADLINE_K = 20
TYPES = ("factual", "multihop", "overview")


def page_order(hits: list[dict]) -> list[int]:
    """Distinct page numbers in rank order — a page scores once, at its best chunk's rank."""
    seen, out = set(), []
    for h in hits:
        pg = h.get("page_number")
        if pg is None or pg in seen:
            continue
        seen.add(int(pg))
        out.append(int(pg))
    return out


def chunk_ids(hits: list[dict]) -> set:
    return {h.get("chunk_id") for h in hits if h.get("chunk_id")}


def paired_ci(diffs: list[float]) -> dict:
    """mean ± 1.96·SD/√n — the repo's convention (required_n.py prints no CI)."""
    n = len(diffs)
    if n == 0:
        return {"n": 0, "mean": None, "sd": None, "ci95": None, "resolved": None}
    mean = statistics.mean(diffs)
    sd = statistics.stdev(diffs) if n > 1 else 0.0
    half = 1.96 * sd / math.sqrt(n) if n > 1 else 0.0
    return {"n": n, "mean": round(mean, 6), "sd": round(sd, 6),
            "ci95": [round(mean - half, 6), round(mean + half, 6)],
            "resolved": bool((mean - half) > 0 or (mean + half) < 0)}


def _rerank(reranker, cfg, text: str, hits: list[dict]) -> tuple[list[dict], bool]:
    """Rerank, detecting the §I55 swallowed-failure fallback and retrying once.

    The fallback returns `chunks[:top_k]` **in the pool's own order**, so it is detectable by object
    identity. A real rerank returns the same dict objects but reordered; the false-positive risk is a
    rerank that happens to preserve the input order exactly, which is reported via
    `reranker_fallback_queries` rather than hidden.
    """
    top_k = cfg.reranker_top_k
    if not (cfg.reranker_enabled and hits):
        return hits[:top_k], False
    head = hits[:top_k]
    out: list[dict] = []
    for _ in range(2):
        out = reranker.rerank(text, hits, top_k=top_k)
        if not (len(out) == len(head) and all(a is b for a, b in zip(out, head))):
            return out, False
    return out, True


def _retry(fn, attempts: int = 3, what: str = ""):
    """Retry a transient transport failure (the cluster is reached over a tunnel — §I49 Finding 1).

    ⚠️ It **logs** the retry. The first version swallowed it, and a 951 s gap between two progress
    lines had no explanation in the log — §I25's class, in the probe measuring §I25's class.
    """
    last: Exception | None = None
    for i in range(attempts):
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001
            last = exc
            print(f"    retry {i + 1}/{attempts} after {type(exc).__name__}: "
                  f"{str(exc)[:100]} [{what}]", flush=True)
            time.sleep(1.5 * (i + 1))
    raise last  # type: ignore[misc]


def _arm(store, reranker, cfg, vec, text, tenant, relevant, enabled: bool, da_stats: dict) -> dict:
    """One retrieval arm: the production path with the DA lane toggled."""
    store._cfg.da_enabled = enabled                    # noqa: SLF001 — the single variable
    hits = store.search_with_das(
        vec, query_text=text, tenant_id=tenant, fetch_k=cfg.reranker_fetch_k,
    )
    reranked, fallback = _rerank(reranker, cfg, text, hits)
    return {
        "n_pool": len(hits),
        "pool_ids": chunk_ids(hits),
        "top20_ids": chunk_ids(reranked),
        "top20_pages": page_order(reranked),
        "da_hits": da_stats["hits"] if enabled else 0,
        "rerank_fallback": fallback,
        "metrics": ev.compute_retrieval_metrics(
            {"hits": hits, "hits_above": hits, "reranked": reranked}, relevant, cfg,
        ),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="logs/p1/step10/da_lane_ablation.json")
    ap.add_argument("--limit", type=int, default=0, help="0 = every selected query")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    if Path(args.out).exists() and not args.force:
        print(f"REFUSING to overwrite {args.out} without --force — a registered artifact "
              f"must not be clobbered by accident.", file=sys.stderr)
        return 4

    cfg = get_settings()
    raw = json.loads(Path(QUERIES).read_text(encoding="utf-8"))
    queries = [q for q in raw if not str(q.get("id", "")).startswith("_")]
    queries = [q for q in queries
               if q.get("answerable", True)
               and q.get("query_type") in TYPES
               and (q.get("relevant_pages") or [])]
    queries.sort(key=lambda q: q["id"])
    if args.limit:
        queries = queries[: args.limit]
    if not queries:
        print("ABORT: no queries selected — writing nothing.", file=sys.stderr)
        return 3

    store = DocumentStore(cfg)
    embedder = get_cluster_embedder(cfg)
    reranker = get_reranker(cfg)
    tenant = cfg.global_tenant_id

    # The lane's raw answer rate, per query, independent of whether it survives downstream.
    da_stats = {"hits": 0}
    _orig_search_da = store.search_da

    def _counting_search_da(query_vector, tenant_id, limit=20):
        got = _orig_search_da(query_vector, tenant_id=tenant_id, limit=limit)
        da_stats["hits"] = len(got)
        return got

    store.search_da = _counting_search_da

    results: list[dict] = []
    errors = 0
    t0 = time.time()
    for i, q in enumerate(queries, 1):
        qid, text = q["id"], q["query"]
        relevant = [int(p) for p in q["relevant_pages"]]
        try:
            vec = _retry(lambda: np.asarray(embedder.embed_query(text), dtype=np.float32),
                         what=f"{qid} embed")
            da_stats["hits"] = 0
            on = _retry(lambda: _arm(store, reranker, cfg, vec, text, tenant, relevant,
                                     True, da_stats), what=f"{qid} da_on")
            off = _retry(lambda: _arm(store, reranker, cfg, vec, text, tenant, relevant,
                                      False, da_stats), what=f"{qid} da_off")
        except Exception as exc:  # noqa: BLE001
            # The cluster is reached over a tunnel and drops connections; one query must not cost
            # the whole run. Recorded as an error and excluded from the summary, never guessed at.
            errors += 1
            results.append({"id": qid, "error": f"{type(exc).__name__}: {exc}"})
            print(f"  [{i}/{len(queries)}] {qid} ERROR {type(exc).__name__} — skipped", flush=True)
            continue

        results.append({
            "id": qid,
            "query_type": q.get("query_type"),
            "n_relevant": len(relevant),
            "da_hits_returned": on["da_hits"],
            "n_pool": {"da_on": on["n_pool"], "da_off": off["n_pool"]},
            "rerank_fallback": on["rerank_fallback"] or off["rerank_fallback"],
            # the lane's direct contribution: chunks/pages present with DA that are absent without it
            "da_added_chunks": len(on["pool_ids"] - off["pool_ids"]),
            "da_added_chunks_in_top20": len(on["top20_ids"] - off["top20_ids"]),
            "da_added_pages_in_top20": len(set(on["top20_pages"][:HEADLINE_K])
                                           - set(off["top20_pages"][:HEADLINE_K])),
            "arms": {"da_on": on["metrics"], "da_off": off["metrics"]},
        })
        if i % 10 == 0:
            print(f"  [{i}/{len(queries)}] {qid} … {time.time() - t0:.0f}s", flush=True)

    ok = [r for r in results if "error" not in r]
    if not ok:
        print("\nABORT: no query produced a comparison — NOT writing the artifact.", file=sys.stderr)
        return 3

    k_top = cfg.reranker_top_k
    k_fetch = cfg.reranker_fetch_k
    rec_key = f"recall_at_{k_top}"
    pool_key = f"recall_at_{k_fetch}"
    hit_key = f"hit_at_{k_top}"
    ndcg_key = f"ndcg_at_{k_top}"

    def summarise(subset: list[dict]) -> dict:
        if not subset:
            return {}
        d_r = [r["arms"]["da_on"][rec_key] - r["arms"]["da_off"][rec_key] for r in subset]
        d_p = [r["arms"]["da_on"][pool_key] - r["arms"]["da_off"][pool_key] for r in subset]
        d_h = [r["arms"]["da_on"][hit_key] - r["arms"]["da_off"][hit_key] for r in subset]
        d_n = [r["arms"]["da_on"][ndcg_key] - r["arms"]["da_off"][ndcg_key] for r in subset]
        d_m = [r["arms"]["da_on"]["mrr"] - r["arms"]["da_off"]["mrr"] for r in subset]
        return {
            "queries": len(subset),
            "queries_with_reranker_fallback": sum(1 for r in subset if r["rerank_fallback"]),
            "POOL_recall_at_fetch_k": {
                "da_on": round(statistics.mean(r["arms"]["da_on"][pool_key] for r in subset), 6),
                "da_off": round(statistics.mean(r["arms"]["da_off"][pool_key] for r in subset), 6),
            },
            f"POOL_recall_at_{k_fetch}_paired_delta_da_on_minus_da_off": paired_ci(d_p),
            "POOL_recall_win_loss_tie": {
                "da_on_better": sum(1 for d in d_p if d > 1e-12),
                "da_off_better": sum(1 for d in d_p if d < -1e-12),
                "identical": sum(1 for d in d_p if abs(d) <= 1e-12),
            },
            "TOPK_recall_at_top_k": {
                "da_on": round(statistics.mean(r["arms"]["da_on"][rec_key] for r in subset), 6),
                "da_off": round(statistics.mean(r["arms"]["da_off"][rec_key] for r in subset), 6),
            },
            f"TOPK_recall_at_{k_top}_paired_delta_da_on_minus_da_off": paired_ci(d_r),
            "TOPK_hit_at_top_k": {
                "da_on": round(statistics.mean(r["arms"]["da_on"][hit_key] for r in subset), 6),
                "da_off": round(statistics.mean(r["arms"]["da_off"][hit_key] for r in subset), 6),
            },
            f"TOPK_hit_at_{k_top}_paired_delta": paired_ci(d_h),
            f"TOPK_ndcg_at_{k_top}_paired_delta": paired_ci(d_n),
            "TOPK_mrr_paired_delta": paired_ci(d_m),
            "TOPK_recall_win_loss_tie": {
                "da_on_better": sum(1 for d in d_r if d > 1e-12),
                "da_off_better": sum(1 for d in d_r if d < -1e-12),
                "identical": sum(1 for d in d_r if abs(d) <= 1e-12),
            },
            "contribution": {
                "da_hits_returned_mean": round(statistics.mean(r["da_hits_returned"] for r in subset), 4),
                "da_added_chunks_mean": round(statistics.mean(r["da_added_chunks"] for r in subset), 4),
                "pool_growth_mean_pct": round(statistics.mean(
                    100.0 * r["da_added_chunks"] / max(1, r["n_pool"]["da_off"]) for r in subset), 4),
                "queries_with_any_da_added_chunk": sum(1 for r in subset if r["da_added_chunks"] > 0),
                "queries_with_a_da_chunk_in_top20": sum(
                    1 for r in subset if r["da_added_chunks_in_top20"] > 0),
                "queries_with_a_da_page_in_top20": sum(
                    1 for r in subset if r["da_added_pages_in_top20"] > 0),
                "da_pages_in_top20_total": sum(r["da_added_pages_in_top20"] for r in subset),
            },
        }

    no_fallback = [r for r in ok if not r["rerank_fallback"]]
    by_type = {t: summarise([r for r in ok if r["query_type"] == t]) for t in TYPES}
    pools = [r["n_pool"]["da_off"] for r in ok]

    out = {
        "meta": {
            "generated_by": "logs/p1/step10/da_lane_ablation.py",
            "what": ("§I12/§A2 — the DA lane's contribution to retrieval: the production path "
                     "with cfg.da_enabled toggled, everything else pinned"),
            "queries_file": QUERIES,
            "query_types": list(TYPES),
            "n_queries": len(ok),
            "n_queries_selected": len(queries),
            "n_queries_errored": errors,
            "ks": list(KS),
            "headline_k": HEADLINE_K,
            "reranker_fetch_k": k_fetch,
            "reranker_top_k": k_top,
            "mmr_candidates": cfg.mmr_candidates,
            "mmr_enabled": cfg.mmr_enabled,
            "reranker_enabled": cfg.reranker_enabled,
            "hyde": "OFF — deliberately, so the two arms share one query vector (see the docstring)",
            "graph_lane": "NOT included — it fires on multihop only and is a second lever",
            "qdrant_collection": cfg.qdrant_collection,
            "da_collection": cfg.da_collection,
            "embed_model": cfg.embedding_model,
            "no_llm_calls": True,
            "reranker_swallow": {
                "why_it_matters": ("ClusterCrossEncoderReranker.rerank swallows every failure and "
                                   "returns the pool UNRANKED (reranker.py:131-141), which makes "
                                   "the top-k comparison inert by construction for that query — the "
                                   "DA-added chunks sit last in the pool, so an unranked top-20 is "
                                   "always dense. §I55; rate measured by reranker_payload_probe.py."),
                "queries_excluded_from_topk_headline": len(ok) - len(no_fallback),
            },
            "power": {
                "why_it_matters": (
                    "the pool is the production mmr_candidates pool and is far larger than the "
                    "top-k cut, so unlike §G1's ablation the cut bites and the metric CAN move. "
                    "The lane is RECALL-ONLY, so the POOL endpoint is the one it can actually "
                    "move; read `contribution` for whether any DA chunk survives at all."),
                "n_pool_da_off": {"min": min(pools), "median": statistics.median(pools),
                                  "max": max(pools)},
            },
        },
        "summary": {
            "all": summarise(ok),
            "reranked_headline_excluding_fallbacks": summarise(no_fallback),
            "by_type": by_type,
        },
        "queries": sorted(results, key=lambda r: r["id"]),
    }
    Path(args.out).write_text(
        json.dumps(out, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")

    a = out["summary"]["all"]
    nf = out["summary"]["reranked_headline_excluding_fallbacks"]
    print(f"\n=== DA-lane ablation (n={len(ok)}, reranker_top_k={k_top}) ===")
    print(f"  pool (DA off): min {min(pools)} median {statistics.median(pools)} max {max(pools)}")
    print(f"  lane answers: mean {a['contribution']['da_hits_returned_mean']:.1f} DA hit(s)/query; "
          f"mean {a['contribution']['da_added_chunks_mean']:.1f} new chunk(s) added "
          f"(+{a['contribution']['pool_growth_mean_pct']:.1f}% pool)")
    print(f"  SURVIVAL: {a['contribution']['queries_with_a_da_chunk_in_top20']}/{len(ok)} queries "
          f"have a DA-added CHUNK in the top-{k_top}; "
          f"{a['contribution']['queries_with_a_da_page_in_top20']}/{len(ok)} have a DA-added PAGE")
    print(f"  reranker fallbacks (§I55): {a['queries_with_reranker_fallback']}/{len(ok)} "
          f"excluded from the top-k headline (n={nf['queries']})")
    dp = a[f"POOL_recall_at_{k_fetch}_paired_delta_da_on_minus_da_off"]
    print(f"  POOL R@{k_fetch}  off {a['POOL_recall_at_fetch_k']['da_off']:.4f} -> on "
          f"{a['POOL_recall_at_fetch_k']['da_on']:.4f}   delta {dp['mean']:+.4f}  "
          f"CI95 [{dp['ci95'][0]:+.4f}, {dp['ci95'][1]:+.4f}]  "
          f"{'RESOLVED' if dp['resolved'] else 'UNRESOLVED'}  "
          f"W/L/T {a['POOL_recall_win_loss_tie']['da_on_better']}/"
          f"{a['POOL_recall_win_loss_tie']['da_off_better']}/"
          f"{a['POOL_recall_win_loss_tie']['identical']}")
    if nf:
        dt = nf[f"TOPK_recall_at_{k_top}_paired_delta_da_on_minus_da_off"]
        print(f"  TOP{k_top} R@{k_top}  off {nf['TOPK_recall_at_top_k']['da_off']:.4f} -> on "
              f"{nf['TOPK_recall_at_top_k']['da_on']:.4f}   delta {dt['mean']:+.4f}  "
              f"CI95 [{dt['ci95'][0]:+.4f}, {dt['ci95'][1]:+.4f}]  "
              f"{'RESOLVED' if dt['resolved'] else 'UNRESOLVED'}  "
              f"W/L/T {nf['TOPK_recall_win_loss_tie']['da_on_better']}/"
              f"{nf['TOPK_recall_win_loss_tie']['da_off_better']}/"
              f"{nf['TOPK_recall_win_loss_tie']['identical']}  (n={nf['queries']})")
    for t in TYPES:
        s = by_type[t]
        if not s:
            continue
        dt = s[f"POOL_recall_at_{k_fetch}_paired_delta_da_on_minus_da_off"]
        print(f"    {t:<9} n={s['queries']:<4} POOL R@{k_fetch} "
              f"{s['POOL_recall_at_fetch_k']['da_off']:.4f} -> "
              f"{s['POOL_recall_at_fetch_k']['da_on']:.4f}  delta {dt['mean']:+.4f} "
              f"CI95 [{dt['ci95'][0]:+.4f}, {dt['ci95'][1]:+.4f}] "
              f"{'RESOLVED' if dt['resolved'] else 'UNRESOLVED'}")
    print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
