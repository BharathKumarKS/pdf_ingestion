#!/usr/bin/env python
"""§I66 — the pre-registered A/B: do the DOWNSTREAM WIDTHS improve the product endpoint?

Pre-registration (written and committed BEFORE this ran):
    .hermes/plans/2026-10-23-p1-downstream-widths-ab-preregistration.md
RE-REGISTRATION (this file's E4' — metrics-only; see IMPROVEMENTS.md §I67):
    .hermes/plans/2026-10-24-p1-downstream-widths-ab-reregistration.md
    The first run was VOID: Qdrant's server-side RRF fusion is non-deterministic (§I67), which moved
    n_pool on a minority of queries but NO metric. E4' therefore compares METRICS (bit-exact) and
    reports n_pool/n_pages as diagnostics that do not void. Everything else is unchanged.

Why this exists
---------------
§I66 decomposed the retrieval loss and fingered the **fusion's output width** — not the 64d prefetch
(§I61/§I65, a NULL) and not the re-score cut — as the binding constraint: at exact prefetch the
fusion's own loss GROWS (0.143 -> 0.222), because feeding the fusion more candidates does not grow its
output. §I66 measured the *ceilings* by exact brute force but never the endpoint the product ships,
and the fusion-output width's own ceiling is "not yet measured". This measures the product endpoint.

The funnel under test (`store._qdrant_search` / `store.search_with_das`, unchanged except for settings):
    [dense_64(prefetch) -> dense_dim(rescore, L)] -> RRF(dense, sparse, colbert)
    -> page dedup -> MMR(top_k) -> truncate to fetch_k -> cross-encoder -> top-20

Two widths, ONE variable per contrast:
  * W — the fusion's OUTPUT width. It is TWO fields and they must move TOGETHER:
        `mmr_candidates`   = the funnel's output width (the RRF fusion's output),
        `reranker_fetch_k` = the pool truncation + the MMR top_k.
        Raising either alone does NOT widen the fusion (pinned by tests/test_downstream_widths.py).
  * L — the full-dimension re-score cut = `dense_rescore_limit` (the outer Prefetch limit).

`da_fetch_k` is pinned at 100 in EVERY arm so the DA lane (§I56) does not move with the width.

Arms (pre-registered) — each contrast differs in exactly ONE field:
    C   W=100  L=500   prefetch=2000  control (shipped W and L)
    W1  W=300  L=500   prefetch=2000  width treatment 1 — PRIMARY (vs C)
    W2  W=500  L=500   prefetch=2000  width sensitivity (vs C); ALSO the CUT CONTROL
    L1  W=500  L=1000  prefetch=2000  cut treatment 1 — PRIMARY (vs W2)
    L2  W=500  L=2000  prefetch=2000  cut sensitivity (vs W2)
    N   W=100  L=500   prefetch=2000  NEGATIVE CONTROL — arm C re-run; MUST be bit-exact (E4)

⚠️ WHY THE CUT ARMS RUN AT W=500 (not at the shipped W=100): at W=100 the fusion emits only 100
candidates, so raising L merely reshuffles candidates far below the cut and the endpoint is **inert by
construction** — the smoke test showed Δ exactly 0.0000, W/L/T 0/0/3 identical at W=100. L's extra
candidates can only reach the output if the fusion is wide enough to admit them, so the cut is tested
against W2 (the widest fusion), and W2 is therefore the cut's control. Every contrast is still
single-variable: W1/W2 move W only; L1/L2 move L only.

The prefetch is pinned at 2000 in every arm: §I66 shows N=1000 caps L's benefit at 0.8151, so at the
shipped prefetch the lane would be the cap. ⚠️ Consequence: the ABSOLUTE numbers are not the shipped
config's — quote the DELTA.

⚠️ HyDE is OFF, deliberately, so every arm shares one query vector (pre-registration §4). The DELTA is
unaffected; the ABSOLUTE numbers are not production numbers.

⚠️ The graph lane is NOT included: it fires on multihop queries only and is a second lever.
Per-`query_type` numbers are reported so its absence is visible.

⚠️ R@100 is the POOL's own width (`recall_at_{fetch_k}`), so it moves with W by construction and is
carried for the record only — NOT read as evidence (pre-registration §5).

Run:
    unset PYTHONPATH && export QDRANT_HOST=10.0.10.65 QDRANT_COLLECTION=knowledge_base_v2
    uv run python logs/p1/step10/downstream_widths_ab.py            # full 133
    uv run python logs/p1/step10/downstream_widths_ab.py --limit 3  # smoke test
    uv run python logs/p1/step10/downstream_widths_ab.py --recheck  # E5/E4 on the written artifact
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

import evaluate_rag as ev  # noqa: E402  (the audited metric path — same metric definitions)
from src.core.config import get_settings  # noqa: E402
from src.pdf_ingestion.cluster_embedder import get_cluster_embedder  # noqa: E402
from src.pdf_ingestion.reranker import get_reranker  # noqa: E402
from src.pdf_ingestion.store import DocumentStore  # noqa: E402

QUERIES = "data/eval_queries_v2.json"
OUT = "logs/p1/step10/downstream_widths_ab.json"

SHIPPED_W, SHIPPED_L, SHIPPED_PREFETCH, SHIPPED_DA = 100, 500, 1000, 100
PINNED_PREFETCH, PINNED_DA = 2000, 100      # held across every arm (see the module docstring)

# (tag, W, L, prefetch, da_fetch_k, role).  W == mmr_candidates == reranker_fetch_k.
ARMS = (
    ("C",  SHIPPED_W, SHIPPED_L, PINNED_PREFETCH, PINNED_DA, "control — shipped W and L"),
    ("W1", 300,       SHIPPED_L, PINNED_PREFETCH, PINNED_DA, "width treatment 1 — PRIMARY (vs C)"),
    ("W2", 500,       SHIPPED_L, PINNED_PREFETCH, PINNED_DA, "width sensitivity (vs C); CUT CONTROL"),
    ("L1", 500,       1000,      PINNED_PREFETCH, PINNED_DA, "cut treatment 1 — PRIMARY (vs W2)"),
    ("L2", 500,       2000,      PINNED_PREFETCH, PINNED_DA, "cut sensitivity (vs W2)"),
    ("N",  SHIPPED_W, SHIPPED_L, PINNED_PREFETCH, PINNED_DA, "NEGATIVE CONTROL — C re-run; bit-exact (E4)"),
)
# Each treatment is read against its own reference (the cut is measured on the widest fusion).
TREATMENT_REF = {"W1": "C", "W2": "C", "L1": "W2", "L2": "W2"}
TREATMENTS = tuple(TREATMENT_REF)
TYPES = ("factual", "multihop", "overview")
K_TOP = 20                                  # pinned: never varies, so the metric keys are stable


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


def _record_da(orig, seen, *a, **k):
    out = orig(*a, **k)
    seen["n"] = len(out)
    return out


def _f(x):
    """Coerce a metric to a Python float at the point of RECORD.

    `evaluate_rag.compute_retrieval_metrics` returns `ndcg` as **np.float64** (it sums
    `g / np.log2(...)`), while every other metric is a plain Python float. `np.float64` IS a subclass
    of `float`, so `json.dumps` writes it silently and the type is LOST on read — and numpy's
    `round(np.float64, 6)` differs from CPython's `round(float, 6)` at a decimal tie. Consequence
    (measured, §I69): the artifact's summary is NOT re-derivable from its own per-query array, which
    is the E5 guard and the §I57/§I44 class. Coercing here makes the artifact self-consistent.
    """
    return None if x is None else float(x)


def _arm(store, reranker, cfg, vec, text, tenant, relevant, arm: tuple) -> dict:
    """One arm: the production path with this arm's W, L, prefetch and da_fetch_k in force."""
    tag, w, l, prefetch, da, _role = arm
    # The single-variable settings. W is TWO fields and both must move together (§I66).
    store._cfg.mmr_candidates      = w            # noqa: SLF001
    store._cfg.reranker_fetch_k    = w            # noqa: SLF001
    store._cfg.dense_rescore_limit = l            # noqa: SLF001
    store._cfg.dense_prefetch_limit = prefetch    # noqa: SLF001
    store._cfg.da_fetch_k          = da           # noqa: SLF001

    da_seen = {"n": None}
    _orig_da = store.search_da
    store.search_da = lambda *a, **k: _record_da(_orig_da, da_seen, *a, **k)  # noqa: SLF001
    try:
        hits = store.search_with_das(vec, query_text=text, tenant_id=tenant, fetch_k=w)
    finally:
        store.search_da = _orig_da  # noqa: SLF001

    reranked, fallback = _rerank(reranker, cfg, text, hits)
    m = ev.compute_retrieval_metrics(
        {"hits": hits, "hits_above": hits, "reranked": reranked}, relevant, cfg,
    )
    # The metric keys are named off cfg at call time, so the POOL key is `recall_at_{w}` (it varies).
    # Re-key everything to FIXED names so the aggregation is arm-independent.
    pages = {h.get("page_number") for h in hits if h.get("page_number") is not None}
    return {
        "n_pool": len(hits),
        "n_pages": len(pages),
        "rerank_fallback": fallback,
        "da_hits": da_seen["n"],
        "metrics": {
            # _f() coerces to a Python float — ndcg comes back as np.float64 (§I69) and must not
            # leak into the artifact, or the summary is not re-derivable from the per-query array.
            "recall_at_top_k": _f(m.get(f"recall_at_{K_TOP}")),
            "hit_at_top_k":    _f(m.get(f"hit_at_{K_TOP}")),
            "ndcg_at_top_k":   _f(m.get(f"ndcg_at_{K_TOP}")),
            "mrr":             _f(m.get("mrr")),
            "context_precision": _f(m.get("context_precision")),
            "recall_at_pool":  _f(m.get(f"recall_at_{w}")),   # the POOL's own width — record only (§5)
            "pool_k":          w,
        },
    }


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
    embedder = get_cluster_embedder(cfg)
    reranker = get_reranker(cfg)
    tenant = cfg.global_tenant_id

    # E2 — the control arm must resolve to the shipped values.
    control = next(a for a in ARMS if a[0] == "C")
    assert (control[1], control[2], control[4]) == (SHIPPED_W, SHIPPED_L, SHIPPED_DA), \
        "the control arm is not the shipped configuration"

    print(f"queries: {len(queries)}   collection: {cfg.qdrant_collection}   "
          f"host: {cfg.qdrant_host or '(LOCAL — WRONG STORE)'}")
    print("arms: " + "  ".join(f"{t}(W={w},L={l},pf={p},da={d})" for t, w, l, p, d, _r in ARMS))

    results: list[dict] = []
    errors = 0
    t0 = time.time()
    for i, q in enumerate(queries, 1):
        qid, text = q["id"], q["query"]
        relevant = [int(p) for p in q["relevant_pages"]]
        try:
            vec = _retry(lambda: np.asarray(embedder.embed_query(text), dtype=np.float32),
                         what=f"{qid} embed")
            arms = {a[0]: _retry(lambda a=a: _arm(store, reranker, cfg, vec, text, tenant,
                                                  relevant, a), what=f"{qid} arm{a[0]}")
                    for a in ARMS}
        except Exception as exc:  # noqa: BLE001
            errors += 1
            results.append({"id": qid, "error": f"{type(exc).__name__}: {exc}"})
            print(f"  [{i}/{len(queries)}] {qid} ERROR {type(exc).__name__} — skipped", flush=True)
            continue

        # §I58 — the ceiling: the best a page-level recall can reach at this query's label size.
        ceiling = (min(K_TOP, len(relevant)) / len(relevant)) if relevant else None
        rec = {"id": qid, "query_type": q.get("query_type"),
               "n_relevant": len(relevant), "ceiling": ceiling, "arms": {}}
        for a in ARMS:
            tag = a[0]
            m = dict(arms[tag]["metrics"])
            m["recall_at_top_k_ceiling_norm"] = (
                round(m["recall_at_top_k"] / ceiling, 6)
                if (ceiling and m["recall_at_top_k"] is not None) else None)
            rec["arms"][tag] = {
                "n_pool": arms[tag]["n_pool"],
                "n_pages": arms[tag]["n_pages"],
                "rerank_fallback": arms[tag]["rerank_fallback"],
                "da_hits": arms[tag]["da_hits"],
                "settings": {"W": a[1], "L": a[2], "prefetch": a[3], "da_fetch_k": a[4]},
                **m,
            }
        results.append(rec)
        if i % 10 == 0:
            print(f"  [{i}/{len(queries)}] {qid} … {time.time() - t0:.0f}s", flush=True)

    ok = [r for r in results if "error" not in r]
    if not ok:
        print("\nABORT: no query produced a comparison — NOT writing the artifact.", file=sys.stderr)
        return 3

    out = {"meta": {
        "generated_by": "logs/p1/step10/downstream_widths_ab.py",
        "what": ("§I66 — the pre-registered A/B on the product retrieval path: do the downstream "
                 "widths (the fusion output W, the re-score cut L) improve the endpoint the "
                 "product ships?"),
        "preregistration": ".hermes/plans/2026-10-23-p1-downstream-widths-ab-preregistration.md",
        "queries_file": QUERIES,
        "n_queries": len(ok),
        "n_queries_selected": len(queries),
        "n_queries_errored": errors,
        "arms": {t: {"W": w, "L": l, "prefetch": p, "da_fetch_k": d, "role": r}
                 for t, w, l, p, d, r in ARMS},
        "treatment_refs": TREATMENT_REF,
        "shipped": {"W": SHIPPED_W, "L": SHIPPED_L, "prefetch": SHIPPED_PREFETCH,
                    "da_fetch_k": SHIPPED_DA},
        "qdrant_collection": cfg.qdrant_collection,
        "qdrant_host": cfg.qdrant_host or "(LOCAL EMBEDDED — WRONG STORE, §I49)",
        "pinned": {
            "reranker_top_k": K_TOP, "reranker_enabled": cfg.reranker_enabled,
            "mmr_enabled": cfg.mmr_enabled, "mmr_lambda": cfg.mmr_lambda,
            "da_enabled": cfg.da_enabled, "dense_dim_low": cfg.dense_dim_low,
            "prefetch_across_all_arms": PINNED_PREFETCH, "da_fetch_k_across_all_arms": PINNED_DA,
        },
        "hyde": "OFF — deliberately, so every arm shares one query vector (pre-registration §4). "
                "The DELTA is unaffected; the ABSOLUTE numbers are not production numbers.",
        "prefetch_note": "prefetch pinned at 2000 in EVERY arm (not the shipped 1000) so the 64d lane "
                         "is not the cap (§I66) — the absolute numbers are therefore not the shipped "
                         "config's; the delta is what is read.",
        "cut_arm_note": "the cut arms (L1/L2) run at W=500 and are read against W2, because at W=100 "
                        "the fusion emits only 100 candidates and the cut is inert by construction "
                        "(measured: Δ exactly 0.0000, W/L/T 0/0/3 identical at W=100).",
        "graph_lane": "NOT included — it fires on multihop only and is a second lever",
        "no_llm_calls": True,
        "no_writes": True,
        "reranker_swallow": {
            "why_it_matters": ("ClusterCrossEncoderReranker.rerank swallows every failure and returns "
                               "the pool UNRANKED (§I55), which makes a top-k comparison on that "
                               "query inert by construction. Named and excluded per arm, per "
                               "pre-registration §6.5."),
        },
    }, "summary": {}, "queries": sorted(results, key=lambda r: r["id"])}

    out["summary"] = summarise(out["queries"], cfg)

    e4 = out["summary"]["negative_control_E4"]
    print("\n=== E4' — negative control on the METRICS (arm N vs arm C) ===")
    print(f"  metrics compared: {e4['metrics_compared']}   metric mismatches: {e4['mismatches']}   "
          f"max_abs_diff: {e4['max_abs_diff']}   -> "
          f"{'PASS' if e4['pass'] else 'FAIL — the A/B IS VOID'}")
    print(f"  diagnostic diffs (n_pool/n_pages — reported, NOT voiding): {e4['diagnostic_diffs']}")
    for d in e4["diagnostics"][:10]:
        print(f"    diag: {d}")
    if not e4["pass"]:
        for m in e4["examples"][:10]:
            print(f"    {m}")

    Path(args.out).write_text(
        json.dumps(out, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")

    print_summary(out)
    print(f"\nwrote {args.out}")
    return 0 if e4["pass"] else 5


# ── aggregation (E5: everything re-derives from the per-query array) ───────────

_METRICS = ("recall_at_top_k_ceiling_norm", "recall_at_top_k", "recall_at_pool",
            "hit_at_top_k", "ndcg_at_top_k", "mrr", "context_precision")
_ALL = ("C",) + TREATMENTS + ("N",)


def _m(r: dict, tag: str, key: str):
    return r["arms"][tag].get(key)


def summarise(rows: list[dict], cfg) -> dict:
    ok = [r for r in rows if "error" not in r]

    def block(subset: list[dict]) -> dict:
        if not subset:
            return {}
        out: dict = {
            "queries": len(subset),
            "queries_with_reranker_fallback": {
                t: sum(1 for r in subset if r["arms"][t]["rerank_fallback"]) for t in _ALL},
            "pool_size": {t: {"min": min(r["arms"][t]["n_pool"] for r in subset),
                              "median": statistics.median(r["arms"][t]["n_pool"] for r in subset),
                              "max": max(r["arms"][t]["n_pool"] for r in subset)}
                          for t in _ALL},
            "pool_pages_median": {t: statistics.median(r["arms"][t]["n_pages"] for r in subset)
                                  for t in _ALL},
            "da_hits_median": {t: statistics.median(r["arms"][t]["da_hits"] or 0 for r in subset)
                               for t in _ALL},
        }
        for metric in _METRICS:
            for tag in _ALL:
                vals = [v for v in (_m(r, tag, metric) for r in subset) if v is not None]
                out[f"{metric}__{tag}"] = round(statistics.mean(vals), 6) if vals else None
            for tag in TREATMENTS:
                ref = TREATMENT_REF[tag]
                d = [(_m(r, tag, metric) or 0.0) - (_m(r, ref, metric) or 0.0)
                     for r in subset
                     if _m(r, tag, metric) is not None and _m(r, ref, metric) is not None]
                out[f"{metric}__delta_{tag}_minus_{ref}"] = paired_ci(d)
                if metric == "recall_at_top_k_ceiling_norm":
                    out[f"{metric}__win_loss_tie_{tag}"] = win_loss_tie(d)
        return out

    # ── E4' — the negative control on the METRICS; diagnostics reported, not voiding ───────────
    # E4' is the re-registration's disambiguation. The pre-registration's E4 said "every METRIC of
    # every query"; the metrics are bit-exact. n_pool/n_pages are DIAGNOSTICS — they can differ when
    # Qdrant's server-side RRF fusion returns a marginally different candidate set (§I67) — so they
    # are reported per query and do NOT void the run. Justified by the MEASURED floor (30 queries x 4
    # repeats of the C config -> R@20 c-norm spread max 0.000000, pool spread 0; the first run's 1,064
    # comparisons -> 0 metric mismatches, max_abs_diff 0.0).
    # Re-registration: .hermes/plans/2026-10-24-p1-downstream-widths-ab-reregistration.md §8 E4'.
    metrics_compared = 0
    mismatches: list[str] = []
    diagnostics: list[str] = []
    max_abs = 0.0
    for r in ok:
        for key, cv in r["arms"]["C"].items():
            if key == "settings":
                continue
            nv = r["arms"]["N"].get(key)
            if key in ("n_pool", "n_pages", "rerank_fallback", "da_hits"):
                if cv != nv:
                    diagnostics.append(f"{r['id']} {key}: C={cv} N={nv}")
                continue
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
          "diagnostic_diffs": len(diagnostics), "diagnostics": diagnostics[:20],
          "note": ("E4' (re-registration §8): the negative control must be bit-exact on every METRIC; "
                   "any metric mismatch VOIDS the A/B. Diagnostics (n_pool/n_pages) are reported and "
                   "do NOT void — Qdrant's server-side RRF fusion is non-deterministic (§I67) and can "
                   "move the pool by a chunk on a minority of queries without moving any metric.")}

    # ── E8/E9 — the DA lane and the 64d prefetch must be pinned in every arm ───
    e8 = {"da_fetch_k_values": sorted({r["arms"][t]["settings"]["da_fetch_k"]
                                       for r in ok for t in _ALL}),
          "pass": all(r["arms"][t]["settings"]["da_fetch_k"] == PINNED_DA
                      for r in ok for t in _ALL)}
    e9 = {"prefetch_values": sorted({r["arms"][t]["settings"]["prefetch"]
                                     for r in ok for t in _ALL}),
          "pass": all(r["arms"][t]["settings"]["prefetch"] == PINNED_PREFETCH
                      for r in ok for t in _ALL)}

    # ── E7 — the cut must be able to move, and the width arms' pools must grow ─
    e7 = {"note": ("the pool must exceed the top-20 cut or the metric is inert by construction "
                   "(§G1's defect); the width arms' pools must grow with W; and the cut arms must "
                   "show the pool's PAGE set moving, since L changes composition, not size."),
          "control_pool_median": statistics.median(r["arms"]["C"]["n_pool"] for r in ok),
          "width_pools_grow": (
              statistics.median(r["arms"]["W1"]["n_pool"] for r in ok) >
              statistics.median(r["arms"]["C"]["n_pool"] for r in ok) and
              statistics.median(r["arms"]["W2"]["n_pool"] for r in ok) >
              statistics.median(r["arms"]["W1"]["n_pool"] for r in ok)),
          "cut_moves_pages": any(r["arms"]["L1"]["n_pages"] != r["arms"]["W2"]["n_pages"]
                                 or r["arms"]["L2"]["n_pages"] != r["arms"]["W2"]["n_pages"]
                                 for r in ok),
          "control_pool_above_cut": all(r["arms"]["C"]["n_pool"] > K_TOP for r in ok)}

    no_fb = {t: [r for r in ok if not r["arms"][t]["rerank_fallback"]] for t in TREATMENTS}
    d_w1 = [(_m(r, "W1", "recall_at_top_k_ceiling_norm") or 0.0)
            - (_m(r, "C", "recall_at_top_k_ceiling_norm") or 0.0) for r in ok]
    d_l1 = [(_m(r, "L1", "recall_at_top_k_ceiling_norm") or 0.0)
            - (_m(r, "W2", "recall_at_top_k_ceiling_norm") or 0.0) for r in ok]

    return {
        "all_queries": block(ok),
        "excluding_reranker_fallbacks": {t: block(no_fb[t]) for t in TREATMENTS},
        "by_type": {t: block([r for r in ok if r["query_type"] == t]) for t in TYPES},
        "negative_control_E4": e4,
        "guards": {"E8_da_pinned": e8, "E9_prefetch_pinned": e9, "E7_cut_can_move": e7},
        "power": {
            "n": len(ok),
            "observed_sd_of_paired_delta_R20_cnorm_W1": paired_ci(d_w1)["sd"],
            "observed_sd_of_paired_delta_R20_cnorm_L1": paired_ci(d_l1)["sd"],
            "required_n_for_delta_0.05_W1": required_n(paired_ci(d_w1)["sd"]),
            "required_n_for_delta_0.05_L1": required_n(paired_ci(d_l1)["sd"]),
            "note": ("n is fixed (every answerable text query), so power is reported, not chosen. "
                     "§D9/§2 convention: n = ceil((1.96·SD/δ)²)."),
        },
    }


def print_summary(out: dict) -> None:
    a = out["summary"]["all_queries"]
    refs = out["meta"]["treatment_refs"]
    print(f"\n=== §I66 downstream-widths A/B (n={out['meta']['n_queries']}, "
          f"collection={out['meta']['qdrant_collection']}) ===")
    print(f"  pool medians: " + "  ".join(f"{t}={a['pool_size'][t]['median']:.0f}"
                                          for t in _ALL))
    print(f"  pool pages medians: " + "  ".join(f"{t}={a['pool_pages_median'][t]:.0f}"
                                                for t in _ALL))
    print(f"  reranker fallbacks (§I55): "
          + "  ".join(f"{t}={a['queries_with_reranker_fallback'][t]}" for t in _ALL))
    g = out["summary"]["guards"]
    print(f"  E7 cut-can-move: control pool median {g['E7_cut_can_move']['control_pool_median']:.0f} "
          f"(>20: {g['E7_cut_can_move']['control_pool_above_cut']}), "
          f"width pools grow: {g['E7_cut_can_move']['width_pools_grow']}, "
          f"cut moves pages: {g['E7_cut_can_move']['cut_moves_pages']}")
    print(f"  E8 da pinned {g['E8_da_pinned']['pass']} {g['E8_da_pinned']['da_fetch_k_values']}   "
          f"E9 prefetch pinned {g['E9_prefetch_pinned']['pass']} {g['E9_prefetch_pinned']['prefetch_values']}")

    blk = a
    print(f"\n  --- ALL (n={blk['queries']}) — Δ vs each treatment's own reference ---")
    for metric in ("recall_at_top_k_ceiling_norm", "recall_at_top_k", "hit_at_top_k",
                   "ndcg_at_top_k", "mrr", "context_precision"):
        if blk.get(f"{metric}__C") is None:
            continue
        print(f"    {metric}")
        for tag in TREATMENTS:
            ref = refs[tag]
            d = blk[f"{metric}__delta_{tag}_minus_{ref}"]
            if d["mean"] is None:
                continue
            extra = ""
            if metric == "recall_at_top_k_ceiling_norm":
                w = blk.get(f"{metric}__win_loss_tie_{tag}")
                if w:
                    extra = f" W/L/T {w['treat_better']}/{w['control_better']}/{w['identical']}"
            print(f"      {tag} vs {ref}: {blk[f'{metric}__{ref}']:.4f} -> "
                  f"{blk[f'{metric}__{tag}']:.4f}  Δ {d['mean']:+.4f} "
                  f"CI95 [{d['ci95'][0]:+.4f}, {d['ci95'][1]:+.4f}] "
                  f"{'RESOLVED' if d['resolved'] else 'UNRESOLVED'}{extra}")

    print("\n  (recall_at_pool = the pool's own width — record only, NOT evidence, §5)")
    p = out["summary"]["power"]
    print(f"\n  power: SD_d(W1 vs C) {p['observed_sd_of_paired_delta_R20_cnorm_W1']} "
          f"req n {p['required_n_for_delta_0.05_W1']}  |  "
          f"SD_d(L1 vs W2) {p['observed_sd_of_paired_delta_R20_cnorm_L1']} "
          f"req n {p['required_n_for_delta_0.05_L1']}  (n={p['n']})")


def recheck(path: str) -> int:
    """E5 — re-derive every aggregate from the artifact's own per-query array."""
    cfg = get_settings()
    out = json.loads(Path(path).read_text(encoding="utf-8"))
    derived = summarise(out["queries"], cfg)
    same = json.dumps(derived, sort_keys=True) == json.dumps(out["summary"], sort_keys=True)
    print(f"E5 re-derivation: {'IDENTICAL' if same else 'DIFFERS'}")
    if not same:
        for k in sorted(derived):
            if json.dumps(derived[k], sort_keys=True) != json.dumps(out["summary"].get(k),
                                                                   sort_keys=True):
                print(f"  section '{k}' differs")
                print(f"    stored    : {json.dumps(out['summary'].get(k), sort_keys=True)[:400]}")
                print(f"    re-derived: {json.dumps(derived[k], sort_keys=True)[:400]}")
        return 1
    e4 = derived["negative_control_E4"]
    print(f"E4 negative control: {'PASS' if e4['pass'] else 'FAIL — A/B IS VOID'} "
          f"({e4['metrics_compared']} metrics, {e4['mismatches']} mismatches)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
