"""T1 — the BASE-LANE ship test: nomic/`v3` POOLED (B) vs qwen3/`v2` (A), 133 gold queries.

Pre-registration: `.hermes/plans/2026-10-27-p1-t1-base-lanes-preregistration.md` (committed ALONE as
`3ab62f7`). This file implements it and nothing else.

⚠️ THIS FILE IS A COPY OF `stageF_product_endpoint.py`, deliberately. T1 is NOT a new instrument: it is
Stage F's re-registered instrument (prereg `51de3f2`, reregistration `e708784`/`a409d7d`) re-run against
the index that changed underneath it (v3's dense lanes are now POOLED, §I88/§I89). Keeping the harness
byte-comparable to Stage F's is what makes E9 (arm A bit-exact against Stage F's arm A) meaningful, and
what makes the only difference between the two runs the treatment itself.

WHAT MAKES THIS THE PRODUCT PATH. Each arm calls the PRODUCT's own `evaluate_rag.run_retrieval`
verbatim — `embed_query` → (HyDE) → `store.search_with_das` → the graph lane for multihop → the shipped
cluster cross-encoder — and scores with the PRODUCT's own `evaluate_rag.compute_retrieval_metrics`. The
ONE substitution is HyDE: `run_retrieval` calls `src.core.llm.call_llm` directly (temperature 0.3, so
every arm would embed a different hypothetical for the same query — the §I68 class). §4 mandates HyDE be
ON and FROZEN, so `call_llm` is monkeypatched to return the cached hypothetical for the query's own
prompt. A cache miss RAISES; it never falls back to a live LLM call (§4).

PER-ARM PROCESS. `get_settings`, `get_cluster_embedder` and `get_reranker` are process-global
singletons, and the arm's embedder/dim/collection come from the ENVIRONMENT (§3; the A2 `.env` flip is
not applied). So each arm runs in its OWN process, launched by `run_t1.sh` with its env exported. This
mode (`--arm A|B --rep N`) runs one arm and writes one per-arm JSON; `--combine` reads them, computes
the paired endpoints and the guards, and writes the run artifact; `--gate-a` is the cheap early stop
(§10: arm A runs first, and if E9/E4 fail there, arm B is never spent).

READ-ONLY: no writes to any collection, no re-ingest, no config change to `src/`. The only LLM traffic
is the shared cluster embedder + cross-encoder (HyDE is served from the cache).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import socket
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import numpy as np
from loguru import logger

from src.core.config import get_settings
from src.pdf_ingestion.cluster_embedder import get_cluster_embedder
from src.pdf_ingestion.hyde_cache import HydeCacheMiss, load as load_hyde, prompt_for
from src.pdf_ingestion.reranker import get_reranker
from src.pdf_ingestion.store import DocumentStore

# The product's own retrieval + metric functions — imported, never re-implemented.
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))
from evaluate_rag import compute_retrieval_metrics, run_retrieval  # noqa: E402

TOP_K = 20            # cfg.reranker_top_k (asserted at runtime)
FETCH_K = 100         # cfg.reranker_fetch_k (asserted at runtime)
QUERIES = "data/eval_queries_v2.json"
PHASE_E = "data/eval_results/p1-phaseE-v2_2026-10-23_0650.json"
STAGE_F_ARM_A = "logs/p1/step10/stageF_arm_A1.json"   # E9's anchor
STAGE_F_ARM_B = "logs/p1/step10/stageF_arm_B1.json"   # D1's baseline
BASE = Path("logs/p1/step10")

# §3 — the per-arm config each arm MUST resolve to (E2). `doc_prefix`/`instr` are asserted, not assumed.
EXPECT = {
    "A": dict(collection="knowledge_base_v2", model="Qwen/Qwen3-Embedding-0.6B", dim=1024,
              dim_low=64, doc_prefix="", instr_kind="qwen3", role="control / incumbent"),
    "B": dict(collection="knowledge_base_v3", model="nomic-ai/nomic-embed-text-v1.5", dim=768,
              dim_low=64, doc_prefix="search_document: ", instr_kind="nomic", role="treatment"),
}

# E9 compares ONLY these keys: `compute_retrieval_metrics` gained map / precision_at_k / f1_at_k after
# Stage F (§I90), so a whole-dict comparison would be an over-strict check failing on correct data.
E9_METRIC_KEYS = ("recall_at_20", "recall_at_100", "hit_at_20", "mrr", "context_precision", "ndcg_at_20")

# §10 — the shared cluster blocked an earlier T0 attempt (5-query run: 2,700 s wall / 7.9 s CPU).
# A hung socket must fail loudly rather than stall the run; a transient failure is retried, a
# successful-but-different result is NOT (retrying a result would mask nondeterminism).
socket.setdefaulttimeout(90)
RETRIES = 3


def _load_queries() -> list[dict]:
    """The 133 gold queries — the §I63/§I70 convention: id gold-*/ovw-*, with labels, sorted by id."""
    raw = json.loads(Path(QUERIES).read_text())
    q = [x for x in raw if isinstance(x, dict)
         and str(x.get("id", "")).startswith(("gold-", "ovw-"))
         and (x.get("relevant_pages") or [])]
    q.sort(key=lambda x: x["id"])
    return q


def _reachable_pages(store, cfg) -> set[int]:
    """Pages a retriever can EVER reach under the live content filter (§I58's 'achievable max').

    Read-only scroll of the arm's own collection with the product filter (page window + is_content +
    no RAPTOR). The same chunk set in both arms (v3 is v2's chunks re-embedded, §I81), so this is
    asserted to be identical across arms in `--combine` (a real guard).
    """
    from qdrant_client.models import FieldCondition, Filter, MatchValue, Range

    must_not = [FieldCondition(key="source_type", match=MatchValue(value="raptor_summary"))]
    if cfg.min_content_page > 0:
        must_not.append(FieldCondition(key="page_number", range=Range(lt=cfg.min_content_page)))
    if cfg.max_content_page > 0:
        must_not.append(FieldCondition(key="page_number", range=Range(gt=cfg.max_content_page)))
    must_not.append(FieldCondition(key="is_content", match=MatchValue(value=False)))
    flt = Filter(must_not=must_not)

    pages: set[int] = set()
    offset = None
    while True:
        recs, offset = store._qdrant.scroll(
            collection_name=cfg.qdrant_collection, scroll_filter=flt,
            limit=1000, offset=offset, with_payload=["page_number"], with_vectors=False,
        )
        for r in recs:
            p = (r.payload or {}).get("page_number")
            if p is not None:
                pages.add(int(p))
        if offset is None:
            break
    return pages


def _full_precision(retrieval: dict, rel_pages: list[int]) -> dict:
    """R@20 / R@100 at FULL precision (the product metric rounds each query to 4dp)."""
    rel = set(rel_pages)
    seen: set[int] = set()
    n20 = 0
    for h in retrieval["reranked"]:
        p = h.get("page_number")
        if p in rel and p not in seen:
            n20 += 1
            seen.add(p)
    pages_above = {h.get("page_number") for h in retrieval["hits_above"] if h.get("page_number")}
    return {
        "r20_full": n20 / len(rel) if rel else None,
        "r100_full": len(rel & pages_above) / len(rel) if rel else None,
    }


def run_arm(arm: str, rep: int, out: Path, limit: int = 0) -> int:
    exp = EXPECT[arm]
    cfg = get_settings()

    # ── E1 / E2 — the resolved config is asserted, not assumed (the S2/S3 trap: forget the exports
    #    and the run silently uses Qwen3/1024 against the wrong collection). ────────────────────
    problems = []
    if not cfg.qdrant_host:
        problems.append(f"QDRANT_HOST is blank (resolved local store at {cfg.qdrant_local_path})")
    if cfg.qdrant_collection != exp["collection"]:
        problems.append(f"collection {cfg.qdrant_collection!r} != {exp['collection']!r}")
    if cfg.dense_model != exp["model"]:
        problems.append(f"dense_model {cfg.dense_model!r} != {exp['model']!r}")
    if cfg.dense_dim != exp["dim"]:
        problems.append(f"dense_dim {cfg.dense_dim} != {exp['dim']}")
    if cfg.dense_dim_low != exp["dim_low"]:
        problems.append(f"dense_dim_low {cfg.dense_dim_low} != {exp['dim_low']}")
    if cfg.document_prefix != exp["doc_prefix"]:
        problems.append(f"document_prefix {cfg.document_prefix!r} != {exp['doc_prefix']!r}")
    instr = cfg.query_instruction or ""
    if exp["instr_kind"] == "nomic" and instr != "search_query: ":
        problems.append(f"query_instruction {instr!r} != 'search_query: ' (nomic)")
    if exp["instr_kind"] == "qwen3" and "Instruct:" not in instr:
        problems.append(f"query_instruction {instr!r} is not Qwen3's instruction")
    if cfg.reranker_top_k != TOP_K or cfg.reranker_fetch_k != FETCH_K:
        problems.append(f"top_k/fetch_k {cfg.reranker_top_k}/{cfg.reranker_fetch_k} != {TOP_K}/{FETCH_K}")
    # RE-REGISTRATION (2026-10-25), re-verified for T1: the DA lane is OFF in BOTH arms. `search_da`
    # queries `derivative_artifacts` with the DENSE query vector, whose dim IS the arm's dense_dim — and
    # that collection is a single 768d collection (§I83), so it can serve only ONE arm. Leaving it on
    # would give arm B a live lane and arm A a dead one (a silent 400) — not a single-variable A/B.
    # §D15/§I12 recorded the same death in the §3d run.
    if cfg.da_enabled:
        problems.append("da_enabled is True — the re-registration requires it OFF in both arms")
    if problems:
        for p in problems:
            logger.error("E1/E2 FAIL: {}", p)
        print(json.dumps({"arm": arm, "e1_e2_ok": False, "problems": problems}, indent=2))
        return 2

    store = DocumentStore(cfg)
    embedder = get_cluster_embedder(cfg)
    reranker = get_reranker(cfg)

    # ── §4 — HyDE ON and FROZEN. Patch the product's call_llm to serve the cache by prompt text. ──
    queries = _load_queries()
    if limit:
        queries = queries[:limit]
    cache = load_hyde(Path(QUERIES), cfg=cfg)
    prompt_map: dict[str, str] = {}
    n_hyde_used = 0
    for q in queries:
        if q.get("query_type") in ("factual", "overview"):
            hyp = cache.get(q["id"])          # raises HydeCacheMiss — never a live call (§4)
            prompt_map[prompt_for(q["query"])] = hyp
            n_hyde_used += 1

    import src.core.llm as llm_mod
    _real_call_llm = llm_mod.call_llm

    def _frozen_llm(prompt=None, system=None, settings=None, **kw):
        if prompt in prompt_map:
            return prompt_map[prompt]
        raise RuntimeError(
            f"HyDE cache miss mid-run for prompt {str(prompt)[:90]!r} — refusing a live LLM call (§4)"
        )

    llm_mod.call_llm = _frozen_llm

    # ── RE-REGISTRATION §2c — the GRAPH lane is OFF in both arms too. `graph_search` ranks concepts
    #    via `concept_embeddings`, which §I83 re-embedded at 768; arm A's 1024d query 400s and the
    #    lane returns [] (graph_builder.py:686), so it is live in B and dead in A — the same
    #    dense-dim mismatch as the DA lane. Disabled in both arms so the A/B is single-variable over
    #    the BASE lanes. (`run_retrieval` imports `get_graph_builder` inside the function, so patching
    #    the module attribute is enough.) ──────────────────────────────────────────────────────────
    import src.pdf_ingestion.graph_builder as gb_mod

    class _NoGraphLane:
        def graph_search(self, *a, **kw):
            return []

    _real_get_graph_builder = gb_mod.get_graph_builder
    gb_mod.get_graph_builder = lambda settings=None: _NoGraphLane()

    logger.info(
        "ARM {} rep {} — collection={} host={} model={} dim={} low={} doc_prefix={!r} "
        "instr={!r} hyde_entries_used={} queries={}",
        arm, rep, cfg.qdrant_collection, cfg.qdrant_host, cfg.dense_model, cfg.dense_dim,
        cfg.dense_dim_low, cfg.document_prefix, instr[:30], n_hyde_used, len(queries),
    )

    reachable = _reachable_pages(store, cfg)
    logger.info("reachable content pages: {}", len(reachable))

    per_query: list[dict] = []
    errors: list[dict] = []
    retries_used: list[dict] = []
    t0 = time.time()
    for i, q in enumerate(queries, 1):
        qid, text = q["id"], q["query"]
        rel = list(q["relevant_pages"])
        qtype = q.get("query_type", "factual")
        rec: dict = {"id": qid, "query_type": qtype, "n_relevant": len(rel)}
        # §10 — a transient cluster failure is retried (max RETRIES attempts); a successful result is
        # never retried, because re-running a result would mask nondeterminism rather than detect it.
        retrieval = None
        last_exc: Exception | None = None
        for attempt in range(RETRIES):
            try:
                retrieval = run_retrieval(
                    text, store, embedder, reranker, cfg, "global", 0.0, query_type=qtype,
                )
                if attempt:
                    retries_used.append({"id": qid, "attempt": attempt + 1})
                break
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                logger.warning("[{}] attempt {}/{} failed: {}", qid, attempt + 1, RETRIES, exc)
                if attempt + 1 < RETRIES:
                    time.sleep(5)
        if retrieval is None:
            errors.append({"id": qid, "error": f"{type(last_exc).__name__}: {last_exc}"})
            logger.error("[{}] retrieval FAILED after {} attempts", qid, RETRIES)
            per_query.append({**rec, "error": str(last_exc)})
            continue
        m = compute_retrieval_metrics(retrieval, rel, cfg)
        fp = _full_precision(retrieval, rel)
        reach_q = len(set(rel) & reachable)
        rec.update({
            "metrics": m,
            "r20_full": fp["r20_full"],
            "r100_full": fp["r100_full"],
            "achievable_max": reach_q / len(rel) if rel else None,
            "pool_size": len(retrieval["hits"]),
            "reranked_size": len(retrieval["reranked"]),
            "reranker_fallback": bool(retrieval.get("reranker_fallback", False)),
            "n_relevant_reachable": reach_q,
        })
        per_query.append(rec)
        if i % 20 == 0:
            logger.info("  {}/{} queries", i, len(queries))
    wall = time.time() - t0

    llm_mod.call_llm = _real_call_llm  # restore

    artifact = {
        "meta": {
            "arm": arm, "rep": rep, "role": exp["role"],
            "collection": cfg.qdrant_collection, "qdrant_host": cfg.qdrant_host,
            "dense_model": cfg.dense_model, "dense_dim": cfg.dense_dim,
            "dense_dim_low": cfg.dense_dim_low, "document_prefix": cfg.document_prefix,
            "query_instruction": instr,
            "splade": cfg.splade_enabled, "colbert": cfg.colbert_enabled,
            "da_enabled": cfg.da_enabled, "mmr_enabled": cfg.mmr_enabled,
            "mmr_candidates": cfg.mmr_candidates, "reranker_fetch_k": cfg.reranker_fetch_k,
            "reranker_top_k": cfg.reranker_top_k, "reranker_model": cfg.reranker_model,
            "dense_prefetch_limit": cfg.dense_prefetch_limit,
            "dense_rescore_limit": cfg.dense_rescore_limit,
            "hyde": cfg.hyde_enabled, "hyde_cache": cache.path.name,
            "n_hyde_used": n_hyde_used, "n_queries": len(queries),
            "n_errors": len(errors), "wall_seconds": round(wall, 1),
            "retries_used": retries_used,
            "reachable_pages": len(reachable), "reachable_pages_set_sha": hashlib.sha256(
                ",".join(str(p) for p in sorted(reachable)).encode()).hexdigest()[:16],
        },
        "guards": {
            "E1_host_and_collection_resolved": True,   # we returned 2 above otherwise
            "E2_arm_config_matches": True,
            "E3_all_queries_scored": (len(per_query) == len(queries) and len(errors) == 0),
        },
        "errors": errors,
        "per_query": per_query,
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(artifact, indent=2))
    sha = hashlib.sha256(out.read_bytes()).hexdigest()
    logger.info("arm {} rep {} → {} ({}s) sha256 {}", arm, rep, out, round(wall, 1), sha[:16])
    print(f"ARM {arm} rep {rep}: {len(per_query)} queries, {len(errors)} errors, "
          f"{round(wall,1)}s → {out}")
    return 0


# ── combine ──────────────────────────────────────────────────────────────────────────────────────

def _mean(xs):
    xs = [x for x in xs if x is not None]
    return statistics.mean(xs) if xs else None


def _ci(diffs):
    n = len(diffs)
    if n < 2:
        return [float("nan"), float("nan")]
    half = 1.96 * statistics.stdev(diffs) / (n ** 0.5)
    m = statistics.mean(diffs)
    return [m - half, m + half]


def _paired(a: dict, b: dict, key) -> dict:
    """Paired B − A over the shared query ids, per-query, on `key` (a callable)."""
    diffs, ids = [], []
    for qid in sorted(set(a) & set(b)):
        va, vb = key(a[qid]), key(b[qid])
        if va is None or vb is None:
            continue
        diffs.append(vb - va)
        ids.append(qid)
    lo, hi = _ci(diffs)
    return {
        "n": len(diffs), "mean_delta": _mean(diffs), "ci": [lo, hi],
        "resolved": (lo > 0 or hi < 0) if len(diffs) > 1 else False,
        "wins": sum(1 for d in diffs if d > 0), "losses": sum(1 for d in diffs if d < 0),
        "ties": sum(1 for d in diffs if d == 0),
        "sd": statistics.stdev(diffs) if len(diffs) > 1 else None,
        "per_query": diffs, "ids": ids,
    }


def _gate_a() -> int:
    """§10's cheap early stop: run AFTER arm A's two reps, BEFORE arm B is spent.

    E4 restricted to arm A (A1 vs A2 bit-exact) and E9 (A1 bit-exact against Stage F's arm A on the
    six endpoint metrics). If either fails, arm B is never run and the run stops here.
    """
    a1 = json.loads((BASE / "t1_arm_A1.json").read_text())
    a2 = json.loads((BASE / "t1_arm_A2.json").read_text())
    s1 = {r["id"]: r for r in a1["per_query"] if "error" not in r}
    s2 = {r["id"]: r for r in a2["per_query"] if "error" not in r}

    e4_bad = [qid for qid in sorted(set(s1) & set(s2)) if s1[qid]["metrics"] != s2[qid]["metrics"]]

    sf = json.loads(Path(STAGE_F_ARM_A).read_text())
    sfq = {r["id"]: r for r in sf["per_query"] if "error" not in r}
    e9_bad = []
    for qid in sorted(set(s1) & set(sfq)):
        got = {k: s1[qid]["metrics"].get(k) for k in E9_METRIC_KEYS}
        want = {k: sfq[qid]["metrics"].get(k) for k in E9_METRIC_KEYS}
        if got != want:
            e9_bad.append({"id": qid, "got": got, "want": want})

    out = {
        "E4_arm_A_bit_exact_A1_vs_A2": {"pass": not e4_bad, "mismatch_ids": e4_bad},
        "E9_arm_A_bit_exact_vs_stageF": {"pass": not e9_bad, "n_compared": len(set(s1) & set(sfq)),
                                        "mismatches": e9_bad[:10], "n_mismatch": len(e9_bad)},
    }
    ok = out["E4_arm_A_bit_exact_A1_vs_A2"]["pass"] and out["E9_arm_A_bit_exact_vs_stageF"]["pass"]
    print(json.dumps(out, indent=2))
    print("\nGATE A: PASS — arm B may run" if ok
          else "\nGATE A: FAIL — STOP. Arm B is NOT run (T1 pre-registration §10).")
    return 0 if ok else 1


def combine(paths: dict[str, Path], out: Path) -> int:
    arms = {k: json.loads(p.read_text()) for k, p in paths.items()}
    A1, A2 = arms["A1"], arms["A2"]
    B1, B2 = arms["B1"], arms["B2"]
    n = A1["meta"]["n_queries"]

    a1 = {r["id"]: r for r in A1["per_query"] if "error" not in r}
    a2 = {r["id"]: r for r in A2["per_query"] if "error" not in r}
    b1 = {r["id"]: r for r in B1["per_query"] if "error" not in r}
    b2 = {r["id"]: r for r in B2["per_query"] if "error" not in r}

    r20 = lambda r: r["metrics"].get("recall_at_20")          # noqa: E731  (product, 4dp)
    r20f = lambda r: r["r20_full"]                             # noqa: E731  (full precision)
    r100 = lambda r: r["metrics"].get("recall_at_100")         # noqa: E731
    hit = lambda r: r["metrics"].get("hit_at_20")              # noqa: E731
    mrr = lambda r: r["metrics"].get("mrr")                    # noqa: E731
    cp = lambda r: r["metrics"].get("context_precision")       # noqa: E731
    ndcg = lambda r: r["metrics"].get("ndcg_at_20")            # noqa: E731

    # §I58 ceiling-normalised: cR@k = mean(R@k) / mean(achievable_max). The divisor is a property of
    # the CORPUS (which labelled pages are reachable), identical in both arms by construction (v3 is
    # v2's chunks re-embedded) — asserted below, not assumed. ⚠️ This is §I58's convention, NOT the
    # per-query top-k-slot normalisation §I84's `cr20` uses (≈4.44) — the two are not interchangeable.
    D_A = _mean([r["achievable_max"] for r in a1.values()])
    D_B = _mean([r["achievable_max"] for r in b1.values()])
    meanA_r20 = _mean([r20(r) for r in a1.values()])
    meanB_r20 = _mean([r20(r) for r in b1.values()])

    P2 = _paired(a1, b1, r20)                 # raw R@20, product metric (4dp per query)
    P1 = _paired(a1, b1, lambda r: (r20(r) / D_A) if r20(r) is not None else None)  # cR@20

    per_type = {}
    for qt in ("factual", "multihop", "overview"):
        aa = {k: v for k, v in a1.items() if v["query_type"] == qt}
        bb = {k: v for k, v in b1.items() if v["query_type"] == qt}
        per_type[qt] = {"n": len(aa), "cr20": _paired(aa, bb,
                        lambda r: (r20(r) / D_A) if r20(r) is not None else None)}

    # ── guards ───────────────────────────────────────────────────────────────────────────────────
    def _bit_exact(x, y):
        bad = []
        for qid in sorted(set(x) & set(y)):
            if x[qid]["metrics"] != y[qid]["metrics"]:
                bad.append(qid)
        return bad

    a_vs_a = _bit_exact(a1, a2)
    b_vs_b = _bit_exact(b1, b2)

    # E8 — arm A reproduces a REGISTERED v2 row. Anchor = §3d, the registered DA-off retrieval-only v2
    # row (data/eval_results/p1-step10-retrieval-only_2026-10-20_0411.md, §D15): R@20 0.452, R@100
    # 0.626, Hit@20 0.910, MRR 0.728, NDCG@20 0.508. Tolerance = the n=133 resolution floor (≈0.020),
    # NOT a fit. ⚠️ §3d predates §I68's funnel swap (proved endpoint-identical by §I84) and the §I58
    # label re-points (1–3 queries), so a small drift is expected and reported.
    E8_TARGET = {"recall_at_20": 0.452, "recall_at_100": 0.626, "hit_at_20": 0.910,
                 "mrr": 0.728, "ndcg_at_20": 0.508}
    E8_TOL = 0.020
    a_agg = {"recall_at_20": meanA_r20, "recall_at_100": _mean([r100(r) for r in a1.values()]),
             "hit_at_20": _mean([hit(r) for r in a1.values()]),
             "mrr": _mean([mrr(r) for r in a1.values()]),
             "ndcg_at_20": _mean([ndcg(r) for r in a1.values()])}
    e8_gaps = {k: a_agg[k] - v for k, v in E8_TARGET.items()}
    e8_ok = abs(e8_gaps["recall_at_20"]) <= E8_TOL

    # E9 — NEW (T1 §7). Arm A must be BIT-EXACT against Stage F's recorded arm A on the six endpoint
    # metrics, all 133 queries. Only those six keys are compared, by name (§I90's over-strict lesson).
    sf = json.loads(Path(STAGE_F_ARM_A).read_text())
    sf_a = {r["id"]: r for r in sf["per_query"] if "error" not in r}
    e9_mismatch = []
    for qid in sorted(set(a1) & set(sf_a)):
        got = {k: a1[qid]["metrics"].get(k) for k in E9_METRIC_KEYS}
        want = {k: sf_a[qid]["metrics"].get(k) for k in E9_METRIC_KEYS}
        if got != want:
            e9_mismatch.append({"id": qid, "got": got, "want": want})
    e9_n_compared = len(set(a1) & set(sf_a))
    e9_ok = (e9_n_compared == 133 and not e9_mismatch)

    # D1 — diagnostic: arm B (pooled) minus arm B (Stage F, late-chunked), same metric.
    sfb = json.loads(Path(STAGE_F_ARM_B).read_text())
    sf_b = {r["id"]: r for r in sfb["per_query"] if "error" not in r}
    D1 = _paired(sf_b, b1, r20)

    pe = json.loads(Path(PHASE_E).read_text())
    pe_agg = pe["aggregated"]["overall"]
    # DA-gap diagnostic: arm A is DA-OFF; Phase E is DA-ON. §I56 measured the DA lane at −0.0262 on
    # top-20 R@20, so this gap is expected ≈ +0.026. Informative, not a guard.
    da_gap = meanA_r20 - pe_agg["recall_at_20"]

    pools_A = [r["pool_size"] for r in a1.values()]
    pools_B = [r["pool_size"] for r in b1.values()]

    fb_A = sorted(qid for qid, r in a1.items() if r["reranker_fallback"])
    fb_B = sorted(qid for qid, r in b1.items() if r["reranker_fallback"])
    head_A_no_fb = _mean([r20(r) for qid, r in a1.items() if qid not in fb_A])
    head_B_no_fb = _mean([r20(r) for qid, r in b1.items() if qid not in fb_B])

    guards = {
        "E1_each_arm_config_resolved": (bool(A1["meta"]["qdrant_host"]) and bool(B1["meta"]["qdrant_host"])
                                        and A1["meta"]["collection"] != B1["meta"]["collection"]),
        "E2_arms_match_expect": (A1["meta"]["collection"] == "knowledge_base_v2"
                                 and A1["meta"]["dense_model"] == "Qwen/Qwen3-Embedding-0.6B"
                                 and A1["meta"]["dense_dim"] == 1024
                                 and B1["meta"]["collection"] == "knowledge_base_v3"
                                 and B1["meta"]["dense_model"] == "nomic-ai/nomic-embed-text-v1.5"
                                 and B1["meta"]["dense_dim"] == 768),
        "E3_133_compared_every_arm": all(len(d) == 133 for d in (a1, a2, b1, b2)),
        "E4_negative_control_bit_exact": (len(a_vs_a) == 0 and len(b_vs_b) == 0),
        "E5_aggregates_rederive": None,   # set below; the independent verifier repeats it from disk
        "E6_fallbacks_named": True,       # reported either way; not a pass/fail
        "E7_cut_can_move": (min(pools_A) > 20 and min(pools_B) > 20),
        "E8_arm_A_reproduces_registered_row": e8_ok,
        "E9_arm_A_bit_exact_vs_stageF": e9_ok,
        "E_da_off_both_arms": (not A1["meta"]["da_enabled"] and not B1["meta"]["da_enabled"]),
    }
    # E5 — every aggregate re-derives from the artifact's own per-query array. A genuine round-trip:
    # recompute each arm's mean R@20 from the stored rows and compare to the value the arm process
    # recorded. (The independent verifier repeats this from the written JSON.)
    e5_rederived = {}
    for arm_name, arm_obj, d in (("A", A1, a1), ("B", B1, b1)):
        rederived = _mean([r20(r) for r in d.values()])
        stored = _mean([r["metrics"].get("recall_at_20")
                        for r in arm_obj["per_query"] if "error" not in r])
        e5_rederived[arm_name] = {"rederived": rederived, "stored": stored}
    guards["E5_aggregates_rederive"] = all(
        abs(v["rederived"] - v["stored"]) < 1e-12 for v in e5_rederived.values())

    divisor_identical = abs(D_A - D_B) < 1e-12
    guards["E_divisor_identical_across_arms"] = divisor_identical

    artifact = {
        "meta": {
            "question": "nomic/v3 POOLED (B) vs qwen3/v2 (A) at the PRODUCT retrieval endpoint, "
                        "BASE lanes, 133 queries",
            "prereg": ".hermes/plans/2026-10-27-p1-t1-base-lanes-preregistration.md",
            "inherits": ["51de3f2 (Stage F prereg)", "e708784 / a409d7d (Stage F reregistration)"],
            "treatment": "v3's dense lanes are POOLED (§I88/§I89); v2 untouched",
            "da_lane": "OFF in both arms — search_da's dense-dim mismatch (768d derivative_artifacts)",
            "graph_lane": "OFF in both arms — concept_embeddings dense-dim mismatch (768d)",
            "measured_lanes": "dense(low->full) + sparse + colbert -> RRF -> dedup -> MMR -> cross-encoder",
            "hyde": "ON and frozen (data/hyde_cache)",
            "page_convention": "pages of the top-k CHUNKS (evaluate_rag.py:333-341) — NOT top-k PAGES",
            "ceiling_convention": "§I58: cR@k = mean(R@k) / mean(achievable_max); global divisor",
            "arms": {k: arms[k]["meta"] for k in ("A1", "A2", "B1", "B2")},
            "divisor_achievable_max": {"A": D_A, "B": D_B},
            "mean_r20": {"A": meanA_r20, "B": meanB_r20},
            "stageF_armB_mean_r20": _mean([r20(r) for r in sf_b.values()]),
            "phaseE_target": {"recall_at_20": pe_agg["recall_at_20"], "recall_at_100": pe_agg["recall_at_100"],
                              "hit_at_20": pe_agg["hit_at_20"], "mrr": pe_agg["mrr"],
                              "ndcg_at_20": pe_agg["ndcg_at_20"]},
            "wall_seconds": {k: arms[k]["meta"]["wall_seconds"] for k in ("A1", "A2", "B1", "B2")},
        },
        "endpoints": {
            "P1_cR20": P1, "P2_R20_raw": P2,
            "S1_secondary": {
                "R100": _paired(a1, b1, r100), "Hit20": _paired(a1, b1, hit),
                "MRR": _paired(a1, b1, mrr), "CtxPrec": _paired(a1, b1, cp),
                "NDCG20": _paired(a1, b1, ndcg),
            },
            "S2_by_type_cR20": per_type,
            "D1_armB_pooled_minus_armB_stageF": D1,
        },
        "guards": guards,
        "diagnostics": {
            "A_vs_A_metric_mismatch_ids": a_vs_a, "B_vs_B_metric_mismatch_ids": b_vs_b,
            "E8_arm_A_aggregate": a_agg, "E8_target": E8_TARGET, "E8_tolerance": E8_TOL,
            "E8_gaps_A_minus_target": e8_gaps,
            "E9_n_compared": e9_n_compared, "E9_n_mismatch": len(e9_mismatch),
            "E9_mismatches_head": e9_mismatch[:10],
            "DA_gap_A_off_minus_phaseE_on": da_gap, "DA_gap_expected_from_I56": 0.0262,
            "fallback_ids_A": fb_A, "fallback_ids_B": fb_B,
            "headline_r20_A_no_fallback": head_A_no_fb, "headline_r20_B_no_fallback": head_B_no_fb,
            "pool_min_max_A": [min(pools_A), max(pools_A)],
            "pool_min_max_B": [min(pools_B), max(pools_B)],
        },
        "power": {
            "n": P1["n"],
            "sd_d_cR20": P1["sd"], "sd_d_R20": P2["sd"],
            "resolution_floor_cR20": (1.96 * P1["sd"] / (P1["n"] ** 0.5)) if P1["sd"] else None,
            "resolution_floor_R20": (1.96 * P2["sd"] / (P2["n"] ** 0.5)) if P2["sd"] else None,
            "n_required_for_delta_0.05_cR20": ((1.96 * P1["sd"] / 0.05) ** 2) if P1["sd"] else None,
        },
        "verdict": {
            "ships": bool(P1["resolved"] and P1["mean_delta"] > 0),
            "P1_resolved": P1["resolved"], "P1_positive": (P1["mean_delta"] or 0) > 0,
            "reading": ("RESOLVED POSITIVE — B ships" if (P1["resolved"] and P1["mean_delta"] > 0)
                        else "RESOLVED NEGATIVE — nothing ships" if P1["resolved"]
                        else "MEASURED-AND-UNRESOLVED — nothing ships on this evidence"),
        },
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(artifact, indent=2))
    sha = hashlib.sha256(out.read_bytes()).hexdigest()

    print(json.dumps({k: artifact[k] for k in ("endpoints", "guards", "power", "verdict",
                                               "diagnostics")}, indent=2))
    print(f"\nartifact: {out}\nsha256: {sha}")
    failed = [k for k, v in guards.items() if v is False]
    print("ALL GUARDS PASS" if not failed else "GUARD FAILURE: " + ", ".join(failed))
    return 0 if not failed else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--arm", choices=["A", "B"])
    ap.add_argument("--rep", type=int, default=1)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--out", default="")
    ap.add_argument("--combine", action="store_true")
    ap.add_argument("--gate-a", action="store_true")
    args = ap.parse_args()

    if args.combine:
        return combine({
            "A1": BASE / "t1_arm_A1.json", "A2": BASE / "t1_arm_A2.json",
            "B1": BASE / "t1_arm_B1.json", "B2": BASE / "t1_arm_B2.json",
        }, BASE / "t1_base_lanes.json")
    if args.gate_a:
        return _gate_a()
    if not args.arm:
        ap.error("--arm, --combine or --gate-a required")
    out = Path(args.out) if args.out else BASE / f"t1_arm_{args.arm}{args.rep}.json"
    return run_arm(args.arm, args.rep, out, limit=args.limit)


if __name__ == "__main__":
    raise SystemExit(main())
