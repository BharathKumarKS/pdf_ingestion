"""Probe: why did gold-029's pool differ between arms in the T4 full run?

G6/G6b failed on ONE query: arm N's pool was 86 pages while arms C, Q, W50 and T0's fusion row all said
92. The arms differ ONLY in reranker config, and the reranker runs AFTER the pool is built — so a pool
difference should be impossible. This probe re-runs that single query under arm N's config, repeatedly, and
reports whether the pool is stable.

If it is stable at 92, the full run's 86 was a transient. If it varies, the pool is nondeterministic and
G6-as-an-absolute is not achievable.

Read-only.

Usage:  python logs/p1/step10/t4_probe_gold029.py [--reps 5]
"""
from __future__ import annotations

import argparse
import json
import socket
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from loguru import logger  # noqa: E402

from src.core.config import get_settings  # noqa: E402
from src.pdf_ingestion.cluster_embedder import get_cluster_embedder  # noqa: E402
from src.pdf_ingestion.hyde_cache import load as load_hyde, prompt_for  # noqa: E402
from src.pdf_ingestion.reranker import get_reranker  # noqa: E402
from src.pdf_ingestion.store import DocumentStore  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))
from evaluate_rag import run_retrieval  # noqa: E402

QID = "gold-029"
socket.setdefaulttimeout(90)
logger.remove()


def pages_of(hits):
    seen, out = set(), []
    for h in hits:
        p = h.get("page_number")
        if p is None:
            continue
        p = int(p)
        if p not in seen:
            seen.add(p)
            out.append(p)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--reps", type=int, default=5)
    args = ap.parse_args()

    cfg = get_settings()
    q = next(x for x in json.loads(Path("data/eval_queries_v2.json").read_text())
             if isinstance(x, dict) and x.get("id") == QID)
    text, qtype = q["query"], q.get("query_type", "factual")
    t0 = {r["id"]: r for r in json.loads(Path("logs/p1/step10/t0_baseline.json").read_text())["per_query"]}
    t0_pool = [p for p, _ in t0[QID]["fusion_ranked"]]
    print(f"{QID}  type={qtype}  T0 fusion pool = {len(t0_pool)} pages")

    # freeze HyDE exactly as the harness does
    cache = load_hyde(Path("data/eval_queries_v2.json"), cfg=cfg)
    prompts = {prompt_for(q["query"]): cache.get(QID)}
    import src.core.llm as llm_mod
    real = llm_mod.call_llm
    llm_mod.call_llm = lambda prompt=None, system=None, settings=None, **kw: (
        prompts[prompt] if prompt in prompts else (_ for _ in ()).throw(RuntimeError("HyDE miss")))

    embedder = get_cluster_embedder(cfg)
    reranker = get_reranker(cfg)
    try:
        for arm, upd in (("C  (CE on, top-20)", dict(reranker_enabled=True, reranker_top_k=20)),
                         ("N  (CE OFF, top-20)", dict(reranker_enabled=False, reranker_top_k=20))):
            c = cfg.model_copy(update=upd)
            store = DocumentStore(c)
            print(f"\n--- arm {arm} ---")
            sizes = []
            for i in range(args.reps):
                ret = run_retrieval(text, store, embedder, reranker, c, "global", 0.0, query_type=qtype)
                pool = pages_of(ret["hits"])
                sizes.append(len(pool))
                match = "== T0" if pool == t0_pool else f"!= T0 (first6 {pool[:6]} vs {t0_pool[:6]})"
                print(f"   rep {i+1}: pool={len(pool):3d} pages  {match}")
            print(f"   => sizes {sizes}  {'STABLE' if len(set(sizes)) == 1 else '*** NONDETERMINISTIC ***'}")
    finally:
        llm_mod.call_llm = real
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
