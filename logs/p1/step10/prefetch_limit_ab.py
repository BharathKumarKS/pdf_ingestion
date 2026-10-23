#!/usr/bin/env python
"""§I61 — the pre-registered A/B: does RAISING THE 64d PREFETCH LIMIT improve the product endpoint?

Pre-registration (written and committed BEFORE this ran):
    .hermes/plans/2026-10-23-p1-i61-prefetch-limit-ab-preregistration.md

Why this exists
---------------
§I61 found the lever and gated it: at the production prefetch limit of 1000 the new index's
`dense_64` lane covers only **0.804127** of its reachable pool against **0.932368** for the
full-dimension lane (~30× the old index's gap), and raising the limit recovers it (2000 ->
0.971526; every in-window chunk -> 1.0000). But that was a **40-query screening subsample** and it
measured the **lane's own membership**, not the endpoint the product ships. A lane that
under-returns can still lose nothing downstream, because the full-dimension re-score of the
prefetched 1000 may already hold everything that mattered. This measures the product endpoint.

The funnel under test (`store._qdrant_search`, unchanged except for one setting):
    [dense_64(dense_prefetch_limit) -> dense_dim(rescore, 500)] -> RRF(dense, sparse, colbert)
    -> page dedup -> MMR -> cross-encoder -> top-20

Arms (pre-registered)
---------------------
    C  dense_prefetch_limit=1000   control — the shipped value
    T  dense_prefetch_limit=2000   primary treatment
    S  dense_prefetch_limit=3489   sensitivity — every in-window chunk = exact search
    N  dense_prefetch_limit=1000   NEGATIVE CONTROL — arm C re-run; MUST be bit-exact (E4)

Everything else is pinned: the collection, the query file, the 133 answerable text queries, the
query vector, `mmr_candidates`, `reranker_fetch_k`, `reranker_top_k`, the reranker, the DA lane.
The outer re-score cut (500) and the inner lane name (`dense_64`) do not move — pinned by
`tests/test_dense_prefetch_limit.py`, so the A/B is single-variable by construction.

⚠️ HyDE is OFF, deliberately, so every arm shares one query vector (see the pre-registration §4).
HyDE is arm-invariant when held fixed, so the DELTA is unaffected — but the ABSOLUTE numbers are
not production numbers and must not be quoted as such.

⚠️ The graph lane is NOT included: it fires on multihop queries only and is a second lever.
Per-`query_type` numbers are reported so its absence is visible.

Run:
    unset PYTHONPATH && export QDRANT_HOST=10.0.10.65 QDRANT_COLLECTION=knowledge_base_v2
    uv run python logs/p1/step10/prefetch_limit_ab.py            # full 133
    uv run python logs/p1/step10/prefetch_limit_ab.py --limit 3  # smoke test
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
from qdrant_client.models import FieldCondition, Filter, MatchValue, Range  # noqa: E402

import evaluate_rag as ev  # noqa: E402  (the audited metric path — same metric definitions)
from src.core.config import get_settings  # noqa: E402
from src.pdf_ingestion.cluster_embedder import get_cluster_embedder  # noqa: E402
from src.pdf_ingestion.reranker import get_reranker  # noqa: E402
from src.pdf_ingestion.store import DocumentStore  # noqa: E402

QUERIES = "data/eval_queries_v2.json"
OUT = "logs/p1/step10/prefetch_limit_ab.json"

# (tag, limit, role).  The N arm repeats C's value on purpose — that is the negative control.
ARMS = (
    ("C", 1000, "control — the shipped prefetch limit"),
    ("T", 2000, "primary treatment — where §I61 found the dimension stops mattering"),
    ("S", 3489, "sensitivity — every in-window chunk of the new index (exact search)"),
    ("N", 1000, "NEGATIVE CONTROL — a re-run of C; must be bit-exact (E4)"),
)
MECH_LIMITS = (1000, 2000, 3489)   # M1 — the §I61 mechanism metric, re-derived at full sample
NEW_DOC = "7ba61432"               # the new index's document (§I61)
TYPES = ("factual", "multihop", "overview")
HEADLINE_K = 20


# ── statistics ────────────────────────────────────────────────────────────────

def paired_ci(diffs: list[float]) -> dict:
    """mean ± 1.96·SD/√n — the repo's convention (`required_n.py` prints no CI)."""
    n = len(diffs)
    if n == 0:
        return {"n": 0, "mean": None, "sd": None, "ci95": None, "resolved": None}
    mean = statistics.mean(diffs)
    sd = statistics.stdev(diffs) if n > 1 else 0.0
    half = 1.96 * sd / math.sqrt(n) if n > 1 else 0.0
    return {"n": n, "mean": round(mean, 6), "sd": round(sd, 6),
            "ci95": [round(mean - half, 6), round(mean + half, 6)],
            "resolved": bool((mean - half) > 0 or (mean + half) < 0)}


def required_n(sd: float, delta: float = 0.05) -> int | None:
    """n for a two-sided 95% CI to exclude 0 at the observed SD — the repo's §D/§2 convention."""
    if sd is None or sd <= 0:
        return None
    return int(math.ceil((1.96 * sd / delta) ** 2))


def win_loss_tie(diffs: list[float]) -> dict:
    return {"treat_better": sum(1 for d in diffs if d > 1e-12),
            "control_better": sum(1 for d in diffs if d < -1e-12),
            "identical": sum(1 for d in diffs if abs(d) <= 1e-12)}


# ── retrieval ─────────────────────────────────────────────────────────────────

def _rerank(reranker, cfg, text: str, hits: list[dict]) -> tuple[list[dict], bool]:
    """Rerank, detecting the §I55 swallowed-failure fallback by object identity and retrying once.

    The fallback returns `chunks[:top_k]` **in the pool's own order**, so it is detectable by
    identity: a real rerank returns the same dict objects reordered.
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
    """Retry a transient transport failure — the cluster is reached over a tunnel (§I49)."""
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


def _arm(store, reranker, cfg, vec, text, tenant, relevant, limit: int) -> dict:
    """One arm: the production path with `dense_prefetch_limit` set to this arm's value."""
    store._cfg.dense_prefetch_limit = limit            # noqa: SLF001 — the single variable
    hits = store.search_with_das(
        vec, query_text=text, tenant_id=tenant, fetch_k=cfg.reranker_fetch_k,
    )
    reranked, fallback = _rerank(reranker, cfg, text, hits)
    return {
        "n_pool": len(hits),
        "rerank_fallback": fallback,
        "metrics": ev.compute_retrieval_metrics(
            {"hits": hits, "hits_above": hits, "reranked": reranked}, relevant, cfg,
        ),
    }


# ── M1: the §I61 mechanism metric, copied from prefetch_limit_sweep.py ─────────

def content_filter(cfg) -> Filter:
    """The production filter, copied verbatim from `store.py` (the funnel's own filter)."""
    must_not = [FieldCondition(key="source_type", match=MatchValue(value="raptor_summary"))]
    if cfg.min_content_page > 0:
        must_not.append(FieldCondition(key="page_number", range=Range(lt=cfg.min_content_page)))
    if cfg.max_content_page > 0:
        must_not.append(FieldCondition(key="page_number", range=Range(gt=cfg.max_content_page)))
    must_not.append(FieldCondition(key="is_content", match=MatchValue(value=False)))
    return Filter(must_not=must_not, should=[
        Filter(must=[FieldCondition(key="tenant_id", match=MatchValue(value=cfg.global_tenant_id))]),
        Filter(must=[FieldCondition(key="tenant_id", match=MatchValue(value="global"))]),
    ])


def dense64_pages(client, cfg, filt, vec, limit: int) -> list[int]:
    """Distinct pages the `dense_64` lane returns at `limit` — §I61's unit."""
    v64 = vec[: cfg.dense_dim_low].copy()
    v64 /= np.linalg.norm(v64) + 1e-12
    pts = client.query_points(collection_name=cfg.qdrant_collection, query=v64.tolist(),
                              using="dense_64", query_filter=filt, limit=limit,
                              with_payload=True).points
    seen, out = set(), []
    for p in pts:
        pg = (p.payload or {}).get("page_number")
        if pg is None or pg in seen:
            continue
        seen.add(int(pg))
        out.append(int(pg))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=OUT)
    ap.add_argument("--limit", type=int, default=0, help="0 = every selected query (smoke test only)")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--recheck", action="store_true",
                    help="do NOT run: re-read --out and re-derive every aggregate from its "
                         "per-query array (the E5 check, runnable on its own)")
    args = ap.parse_args()

    if args.recheck:
        return recheck(args.out)

    if Path(args.out).exists() and not args.force:
        print(f"REFUSING to overwrite {args.out} without --force — a registered artifact "
              f"must not be clobbered by accident.", file=sys.stderr)
        return 4

    cfg = get_settings()
    raw = json.loads(Path(QUERIES).read_text(encoding="utf-8"))
    queries = [q for q in raw
               if isinstance(q, dict)
               and str(q.get("id", "")).startswith(("gold-", "ovw-"))
               and q.get("answerable", True)
               and q.get("query_type") in TYPES
               and (q.get("relevant_pages") or [])]
    queries.sort(key=lambda q: q["id"])
    if args.limit:
        queries = queries[: args.limit]
    if not queries:
        print("ABORT: no queries selected — writing nothing.", file=sys.stderr)
        return 3

    store = DocumentStore(cfg)
    client = store._qdrant  # noqa: SLF001
    embedder = get_cluster_embedder(cfg)
    reranker = get_reranker(cfg)
    tenant = cfg.global_tenant_id
    filt = content_filter(cfg)

    # The reachable pool per query: the new document's in-window content pages (§I61's ceiling).
    from sqlmodel import Session, select

    from src.core.database import Chunk, get_engine
    with Session(get_engine(cfg)) as session:
        rows = session.exec(select(Chunk).where(
            Chunk.document_id.like(f"{NEW_DOC}%"))).all()  # type: ignore[attr-defined]
    in_window = {int(c.page_number) for c in rows
                 if c.page_number is not None and c.is_content is not False
                 and cfg.min_content_page <= c.page_number <= cfg.max_content_page}

    print(f"queries: {len(queries)}   collection: {cfg.qdrant_collection}   "
          f"in-window content pages of {NEW_DOC}: {len(in_window)}")
    print(f"arms: " + "  ".join(f"{t}={l}" for t, l, _r in ARMS))

    results: list[dict] = []
    errors = 0
    t0 = time.time()
    for i, q in enumerate(queries, 1):
        qid, text = q["id"], q["query"]
        relevant = [int(p) for p in q["relevant_pages"]]
        ceil = sorted(set(relevant) & in_window)
        try:
            vec = _retry(lambda: np.asarray(embedder.embed_query(text), dtype=np.float32),
                         what=f"{qid} embed")
            arms = {}
            for tag, limit, _role in ARMS:
                arms[tag] = _retry(
                    lambda t=tag, l=limit: _arm(store, reranker, cfg, vec, text, tenant,
                                                relevant, l),
                    what=f"{qid} arm{tag}")
            mech = {}
            for lim in MECH_LIMITS:
                pages = _retry(lambda l=lim: dense64_pages(client, cfg, filt, vec, l),
                               what=f"{qid} mech{lim}")
                mech[str(lim)] = {
                    "n_pages": len(pages),
                    "pool_ceiling_norm": (round(len(set(pages) & set(ceil)) / len(ceil), 6)
                                          if ceil else None),
                }
        except Exception as exc:  # noqa: BLE001
            errors += 1
            results.append({"id": qid, "error": f"{type(exc).__name__}: {exc}"})
            print(f"  [{i}/{len(queries)}] {qid} ERROR {type(exc).__name__} — skipped", flush=True)
            continue

        k_top = cfg.reranker_top_k
        rec = {"id": qid, "query_type": q.get("query_type"),
               "n_relevant": len(relevant), "n_reachable": len(ceil),
               "ceiling": (min(k_top, len(relevant)) / len(relevant)) if relevant else None,
               "mechanism": mech, "arms": {}}
        for tag, _l, _r in ARMS:
            m = dict(arms[tag]["metrics"])
            rec["arms"][tag] = {
                "n_pool": arms[tag]["n_pool"],
                "rerank_fallback": arms[tag]["rerank_fallback"],
                **m,
                # §I58 — raw R@20 compares different denominators when |relevant| varies.
                f"recall_at_{k_top}_ceiling_norm": (
                    round(m[f"recall_at_{k_top}"] / rec["ceiling"], 6)
                    if rec["ceiling"] else None),
            }
        results.append(rec)
        if i % 10 == 0:
            print(f"  [{i}/{len(queries)}] {qid} … {time.time() - t0:.0f}s", flush=True)

    ok = [r for r in results if "error" not in r]
    if not ok:
        print("\nABORT: no query produced a comparison — NOT writing the artifact.", file=sys.stderr)
        return 3

    out = {"meta": {
        "generated_by": "logs/p1/step10/prefetch_limit_ab.py",
        "what": ("§I61 — the pre-registered A/B on the product retrieval path: does raising the "
                 "64d prefetch limit (1000 -> 2000) improve the endpoint the product ships?"),
        "preregistration": ".hermes/plans/2026-10-23-p1-i61-prefetch-limit-ab-preregistration.md",
        "queries_file": QUERIES,
        "n_queries": len(ok),
        "n_queries_selected": len(queries),
        "n_queries_errored": errors,
        "arms": {t: {"dense_prefetch_limit": l, "role": r} for t, l, r in ARMS},
        "qdrant_collection": cfg.qdrant_collection,
        "qdrant_host": cfg.qdrant_host or "(LOCAL EMBEDDED — WRONG STORE, §I49)",
        "document_id": NEW_DOC,
        "in_window_content_pages": len(in_window),
        "pinned": {
            "reranker_fetch_k": cfg.reranker_fetch_k,
            "reranker_top_k": cfg.reranker_top_k,
            "reranker_enabled": cfg.reranker_enabled,
            "mmr_candidates": cfg.mmr_candidates,
            "mmr_enabled": cfg.mmr_enabled,
            "mmr_lambda": cfg.mmr_lambda,
            "da_enabled": cfg.da_enabled,
            "dense_dim_low": cfg.dense_dim_low,
            "outer_rescore_limit": 500,
        },
        "hyde": "OFF — deliberately, so every arm shares one query vector (pre-registration §4). "
                "The DELTA is unaffected; the ABSOLUTE numbers are not production numbers.",
        "graph_lane": "NOT included — it fires on multihop only and is a second lever",
        "no_llm_calls": True,
        "no_writes": True,
        "reranker_swallow": {
            "why_it_matters": ("ClusterCrossEncoderReranker.rerank swallows every failure and "
                               "returns the pool UNRANKED (§I55), which makes a top-k comparison "
                               "on that query inert by construction. Named and excluded from the "
                               "headline, per pre-registration §6.5."),
        },
    }, "summary": {}, "queries": sorted(results, key=lambda r: r["id"])}

    out["summary"] = summarise(out["queries"], cfg, out["meta"])

    # ── E4: the negative control must be bit-exact, or the A/B is VOID ──────────
    e4 = out["summary"]["negative_control_E4"]
    print("\n=== E4 — negative control (arm N must equal arm C exactly) ===")
    print(f"  metrics compared: {e4['metrics_compared']}   mismatches: {e4['mismatches']}   "
          f"max_abs_diff: {e4['max_abs_diff']}   -> "
          f"{'PASS' if e4['pass'] else 'FAIL — the A/B IS VOID'}")
    if not e4["pass"]:
        for m in e4["examples"][:10]:
            print(f"    {m}")

    Path(args.out).write_text(
        json.dumps(out, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")

    print_summary(out)
    print(f"\nwrote {args.out}")
    return 0 if e4["pass"] else 5


# ── aggregation (E5: everything re-derives from the per-query array) ───────────

def _arm_metric(r: dict, tag: str, key: str):
    return r["arms"][tag].get(key)


def summarise(rows: list[dict], cfg, meta: dict) -> dict:
    ok = [r for r in rows if "error" not in r]
    k_top, k_fetch = cfg.reranker_top_k, cfg.reranker_fetch_k
    rec_key, pool_key = f"recall_at_{k_top}", f"recall_at_{k_fetch}"
    hit_key, ndcg_key = f"hit_at_{k_top}", f"ndcg_at_{k_top}"
    cnorm_key = f"recall_at_{k_top}_ceiling_norm"

    def block(subset: list[dict]) -> dict:
        if not subset:
            return {}
        out: dict = {"queries": len(subset),
                     "queries_with_reranker_fallback":
                         sum(1 for r in subset if r["arms"]["C"]["rerank_fallback"]
                             or r["arms"]["T"]["rerank_fallback"])}
        for metric, key in (("recall_at_top_k", rec_key),
                            ("recall_at_top_k_ceiling_norm", cnorm_key),
                            ("recall_at_fetch_k", pool_key),
                            ("hit_at_top_k", hit_key),
                            ("ndcg_at_top_k", ndcg_key),
                            ("mrr", "mrr"),
                            ("context_precision", "context_precision")):
            for tag in ("C", "T", "S"):
                vals = [_arm_metric(r, tag, key) for r in subset]
                vals = [v for v in vals if v is not None]
                out[f"{metric}__{tag}"] = round(statistics.mean(vals), 6) if vals else None
            d = [(_arm_metric(r, "T", key) or 0.0) - (_arm_metric(r, "C", key) or 0.0)
                 for r in subset if _arm_metric(r, "T", key) is not None
                 and _arm_metric(r, "C", key) is not None]
            out[f"{metric}__delta_T_minus_C"] = paired_ci(d)
            if key == rec_key:
                out[f"{metric}__win_loss_tie"] = win_loss_tie(d)
            dS = [(_arm_metric(r, "S", key) or 0.0) - (_arm_metric(r, "C", key) or 0.0)
                  for r in subset if _arm_metric(r, "S", key) is not None
                  and _arm_metric(r, "C", key) is not None]
            out[f"{metric}__delta_S_minus_C"] = paired_ci(dS)
        out["pool_size"] = {
            "min": min(r["arms"]["C"]["n_pool"] for r in subset),
            "median": statistics.median(r["arms"]["C"]["n_pool"] for r in subset),
            "max": max(r["arms"]["C"]["n_pool"] for r in subset),
        }
        return out

    # ── E4 — the negative control, checked per metric per query ────────────────
    metrics_compared = 0
    mismatches: list[str] = []
    max_abs = 0.0
    for r in ok:
        for key, cv in r["arms"]["C"].items():
            if key in ("n_pool", "rerank_fallback"):
                if cv != r["arms"]["N"][key]:
                    mismatches.append(f"{r['id']} {key}: C={cv} N={r['arms']['N'][key]}")
                continue
            nv = r["arms"]["N"].get(key)
            metrics_compared += 1
            if cv is None and nv is None:
                continue
            if cv is None or nv is None or abs(cv - nv) > 1e-12:
                mismatches.append(f"{r['id']} {key}: C={cv} N={nv}")
            else:
                max_abs = max(max_abs, abs(cv - nv))
    e4 = {"pass": not mismatches, "metrics_compared": metrics_compared,
          "mismatches": len(mismatches), "max_abs_diff": round(max_abs, 12),
          "examples": mismatches[:20],
          "note": ("arm N re-runs arm C with HyDE off, so the only legitimate source of a "
                   "difference is instrument noise. Any mismatch voids the A/B (pre-registration "
                   "§7 E4).")}

    # ── M1 — the §I61 mechanism metric at full sample ──────────────────────────
    mech = {}
    for lim in MECH_LIMITS:
        vals = [r["mechanism"][str(lim)]["pool_ceiling_norm"] for r in ok
                if r["mechanism"][str(lim)]["pool_ceiling_norm"] is not None]
        npg = [r["mechanism"][str(lim)]["n_pages"] for r in ok]
        mech[str(lim)] = {
            "pool_recall_ceiling_norm_mean": round(statistics.mean(vals), 6) if vals else None,
            "median_pages_in_pool": statistics.median(npg) if npg else None,
            "queries": len(vals),
        }

    no_fb = [r for r in ok if not (r["arms"]["C"]["rerank_fallback"]
                                   or r["arms"]["T"]["rerank_fallback"])]
    d_r20 = [(_arm_metric(r, "T", rec_key) or 0.0) - (_arm_metric(r, "C", rec_key) or 0.0)
             for r in ok]
    sd = paired_ci(d_r20)["sd"]

    return {
        "all_queries": block(ok),
        "excluding_reranker_fallbacks": block(no_fb),
        "by_type": {t: block([r for r in ok if r["query_type"] == t]) for t in TYPES},
        "mechanism_M1": {
            "unit": ("`dense_64` lane, `limit` in CHUNKS, recall over the deduped PAGE pool "
                     "intersected with the query's REACHABLE labelled pages (§I61's convention)"),
            "why": ("the causal chain: §I61 measured this on a 40-query screening subsample; this "
                    "re-derives it at n=133. It must move in the §I61 direction, or the A/B's "
                    "premise is wrong (pre-registration §6.6)."),
            "by_limit": mech,
        },
        "negative_control_E4": e4,
        "power": {
            "n": len(ok),
            "observed_sd_of_paired_delta_R20": sd,
            "required_n_for_delta_0.05": required_n(sd),
            "note": ("n is fixed (every answerable text query), so power is reported, not chosen. "
                     "§D9/§2 convention: n = ceil((1.96·SD/δ)²)."),
        },
    }


def print_summary(out: dict) -> None:
    cfg = get_settings()
    k_top, k_fetch = cfg.reranker_top_k, cfg.reranker_fetch_k
    a = out["summary"]["all_queries"]
    nf = out["summary"]["excluding_reranker_fallbacks"]
    print(f"\n=== §I61 prefetch-limit A/B (n={out['meta']['n_queries']}, "
          f"collection={out['meta']['qdrant_collection']}) ===")
    print(f"  pool (arm C): min {a['pool_size']['min']} median {a['pool_size']['median']} "
          f"max {a['pool_size']['max']}   (top_k cut = {k_top})")
    print(f"  reranker fallbacks (§I55): {a['queries_with_reranker_fallback']}/{a['queries']} "
          f"excluded from the headline (n={nf.get('queries')})")

    print(f"\n  --- M1 mechanism: dense_64 pool coverage (ceiling-normalised) ---")
    for lim, b in out["summary"]["mechanism_M1"]["by_limit"].items():
        print(f"    limit {lim:>5}: {b['pool_recall_ceiling_norm_mean']}   "
              f"median pages {b['median_pages_in_pool']}")

    for label, blk in (("ALL", a), ("excl. fallbacks", nf)):
        if not blk:
            continue
        print(f"\n  --- {label} (n={blk['queries']}) ---")
        for metric in ("recall_at_top_k", "recall_at_top_k_ceiling_norm", "recall_at_fetch_k",
                       "hit_at_top_k", "ndcg_at_top_k", "mrr", "context_precision"):
            d = blk[f"{metric}__delta_T_minus_C"]
            ds = blk[f"{metric}__delta_S_minus_C"]
            if d["mean"] is None:
                continue
            extra = ""
            if metric == "recall_at_top_k":
                w = blk[f"{metric}__win_loss_tie"]
                extra = (f"  W/L/T {w['treat_better']}/{w['control_better']}/{w['identical']}")
            print(f"    {metric:<32} C {blk[f'{metric}__C']:.4f}  T {blk[f'{metric}__T']:.4f}  "
                  f"S {blk[f'{metric}__S']:.4f}   Δ(T-C) {d['mean']:+.4f} "
                  f"CI95 [{d['ci95'][0]:+.4f}, {d['ci95'][1]:+.4f}] "
                  f"{'RESOLVED' if d['resolved'] else 'UNRESOLVED'}   "
                  f"Δ(S-C) {ds['mean']:+.4f}{extra}")
    p = out["summary"]["power"]
    print(f"\n  power: SD_d(R@20) {p['observed_sd_of_paired_delta_R20']}  "
          f"required n for δ=0.05: {p['required_n_for_delta_0.05']}  (n={p['n']})")


def recheck(path: str) -> int:
    """E5 — re-derive every aggregate from the artifact's own per-query array."""
    cfg = get_settings()
    out = json.loads(Path(path).read_text(encoding="utf-8"))
    derived = summarise(out["queries"], cfg, out["meta"])
    same = json.dumps(derived, sort_keys=True) == json.dumps(out["summary"], sort_keys=True)
    print(f"E5 re-derivation: {'IDENTICAL' if same else 'DIFFERS'}")
    if not same:
        for k in sorted(derived):
            if json.dumps(derived[k], sort_keys=True) != json.dumps(out["summary"].get(k),
                                                                   sort_keys=True):
                print(f"  section '{k}' differs")
                print(f"    stored   : {json.dumps(out['summary'].get(k), sort_keys=True)[:400]}")
                print(f"    re-derived: {json.dumps(derived[k], sort_keys=True)[:400]}")
        return 1
    e4 = derived["negative_control_E4"]
    print(f"E4 negative control: {'PASS' if e4['pass'] else 'FAIL — A/B IS VOID'} "
          f"({e4['metrics_compared']} metrics, {e4['mismatches']} mismatches)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
