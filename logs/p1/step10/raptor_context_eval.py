"""RAPTOR as GENERATOR CONTEXT (overview) — the restated (c) (§I113).

Pre-registration: `.hermes/plans/2026-11-04-p1-raptor-generator-context-preregistration.md` (committed
ALONE). §I98 showed the RAPTOR lane as a RANKED participant hurts overview (a summary has no
page_number, so it only displaces a real page). This asks the untried variant: give the summaries to the
GENERATOR as extra context — never entering the ranked list.

Arms (both synthesised in THIS harness so the ranked list is verifiable):
  A  the CE top-20 pages only                       (anchored to the §I108 baseline, 0.5097)
  B  the same pages + the top-2 RAPTOR summaries appended as a [Summary] block

READ-ONLY. No collection write, no re-ingest, no `src/` change.

Run:  .venv/bin/python logs/p1/step10/raptor_context_eval.py
"""
from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import sys
import time
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from loguru import logger  # noqa: E402

from src.core.config import get_settings  # noqa: E402
from src.pdf_ingestion.cluster_embedder import get_cluster_embedder  # noqa: E402
from src.pdf_ingestion.hyde_cache import load as load_hyde, prompt_for  # noqa: E402
from src.pdf_ingestion.reranker import get_reranker  # noqa: E402
from src.pdf_ingestion.store import DocumentStore  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))
from evaluate_rag import (  # noqa: E402
    compute_answer_relevance, compute_citation_accuracy, compute_faithfulness,
    make_judge_fn, run_retrieval,
)

QUERIES = "data/eval_queries_v2.json"
OUT = Path("logs/p1/step10/raptor_context.json")
N_SUMMARIES = 2
I108_OVERVIEW_FAITHFULNESS = 0.5097   # the anchor (§I108, n=40)

_SYSTEM = (
    "You are a physics tutor. Answer the student's question using ONLY the material provided. "
    "Cite the page number for each fact as [Page N]. Never cite a page number that is not in the "
    "passages."
)


def _overview() -> list[dict]:
    raw = json.loads(Path(QUERIES).read_text())
    q = [x for x in raw if isinstance(x, dict) and x.get("query_type") == "overview"
         and (x.get("relevant_pages") or [])]
    q.sort(key=lambda x: x["id"])
    return q


def _synthesize(query: str, pages: list[dict], summaries: list[dict], cfg) -> str:
    from src.core.llm import call_llm
    passages = "\n\n".join(f"[Page {c.get('page_number', '?')}] {c.get('text', '')}" for c in pages)
    prompt = (
        f"Using only the passages below, answer the student's question. Cite the page number for each "
        f"fact you include.\n\nQuestion: {query}\n\nPassages:\n{passages}"
    )
    if summaries:
        block = "\n\n".join(f"[Summary {i + 1}] {s.get('text', '')}" for i, s in enumerate(summaries))
        prompt += (f"\n\nBackground summaries (chapter-level context — use for synthesis, but cite only "
                   f"pages from the passages above):\n{block}")
    return call_llm(prompt=prompt, system=_SYSTEM, settings=cfg, timeout=90)


def _summary_text(hit: dict) -> str:
    p = hit.get("payload") or hit
    return str(p.get("summary") or p.get("text") or p.get("content") or "")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--judge-model", default="Qwen/Qwen3-VL-8B-Instruct")
    ap.add_argument("--judge-api-base", default="http://10.0.10.70:8000/v1")
    args = ap.parse_args()

    cfg = get_settings()
    queries = _overview()
    if args.limit:
        queries = queries[: args.limit]
    logger.info("overview queries: {}", len(queries))

    store = DocumentStore(cfg)
    embedder = get_cluster_embedder(cfg)
    reranker = get_reranker(cfg)

    # HyDE frozen (the product path calls call_llm for the hypothetical; pin it from the cache).
    hyde = load_hyde(Path(QUERIES), cfg=cfg)
    prompt_map = {prompt_for(q["query"]): hyde.get(q["id"]) for q in queries}
    import src.core.llm as llm_mod
    _real = llm_mod.call_llm

    def _frozen(prompt=None, system=None, settings=None, **kw):
        if prompt in prompt_map:
            return prompt_map[prompt]
        return _real(prompt=prompt, system=system, settings=settings, **kw)
    llm_mod.call_llm = _frozen

    judge_args = SimpleNamespace(judge_backend="openai", judge_api_base=args.judge_api_base,
                                 judge_api_key="dummy", judge_model=args.judge_model)
    judge_fn = make_judge_fn(judge_args)
    logger.info("judge: {} @ {}", args.judge_model, args.judge_api_base)

    per_query, errors = [], []
    t0 = time.time()
    for i, q in enumerate(queries, 1):
        qid, text, gold = q["id"], q["query"], list(q["relevant_pages"])
        try:
            r = run_retrieval(text, store, embedder, reranker, cfg, "global", 0.0, query_type="overview")
            pages = r["reranked"]
            qv = embedder.embed_query(hyde.get(qid))
            rapt = store.search_raptor(qv, tenant_id="global", limit=N_SUMMARIES)
            rapt2 = store.search_raptor(qv, tenant_id="global", limit=N_SUMMARIES)   # G7 determinism
            summaries = [{"text": _summary_text(h), "qdrant_point_id": h.get("qdrant_point_id")}
                         for h in rapt]
            page_list = [c.get("page_number") for c in pages]

            ans_a = _synthesize(text, pages, [], cfg)
            ans_b = _synthesize(text, pages, summaries, cfg)

            rec = {
                "id": qid, "n_relevant": len(gold),
                "page_list_A": page_list, "page_list_B": page_list,
                "n_summaries": len(summaries),
                "summary_ids": [s["qdrant_point_id"] for s in summaries],
                "summary_determinism_ok": [h.get("qdrant_point_id") for h in rapt]
                                          == [h.get("qdrant_point_id") for h in rapt2],
                "summaries_have_page": any(_page_of(h) is not None for h in rapt),
                "A": {"answer": ans_a,
                      "faithfulness": compute_faithfulness(ans_a, pages, judge_fn),
                      "answer_relevance": compute_answer_relevance(text, ans_a, judge_fn),
                      "citation_accuracy": compute_citation_accuracy(ans_a, pages)},
                "B": {"answer": ans_b,
                      "faithfulness": compute_faithfulness(ans_b, pages + summaries, judge_fn),
                      "answer_relevance": compute_answer_relevance(text, ans_b, judge_fn),
                      "citation_accuracy": compute_citation_accuracy(ans_b, pages)},
            }
            per_query.append(rec)
        except Exception as exc:  # noqa: BLE001
            errors.append({"id": qid, "error": f"{type(exc).__name__}: {exc}"})
            logger.error("[{}] FAILED: {}", qid, exc)
        if i % 5 == 0:
            logger.info("  {}/{} queries", i, len(queries))
    llm_mod.call_llm = _real
    wall = time.time() - t0

    def paired(metric: str) -> dict:
        d = []
        for r in per_query:
            a, b = r["A"][metric], r["B"][metric]
            if a is None or b is None:
                continue
            d.append(b - a)
        if len(d) < 2:
            return {"n": len(d), "mean": None, "ci": None, "resolved": False}
        m = statistics.mean(d)
        half = 1.96 * statistics.stdev(d) / (len(d) ** 0.5)
        return {"n": len(d), "mean": m, "ci": [m - half, m + half],
                "resolved": (m - half > 0 or m + half < 0),
                "wins": sum(1 for x in d if x > 0), "losses": sum(1 for x in d if x < 0)}

    deltas = {m: paired(m) for m in ("faithfulness", "answer_relevance", "citation_accuracy")}
    a_faith = [r["A"]["faithfulness"] for r in per_query if r["A"]["faithfulness"] is not None]

    guards = {
        "G1_population_40": len(per_query) == 40,
        "G2_zero_errors": len(errors) == 0,
        "G3_pages_identical_between_arms": all(r["page_list_A"] == r["page_list_B"] for r in per_query),
        "G4_summaries_are_pageless_and_absent": all(
            not r["summaries_have_page"] and not (set(r["summary_ids"]) & set(r["page_list_A"]))
            for r in per_query),
        "G5_judge_cross_family": args.judge_model != cfg.openai_model,
        "G6_armA_reproduces_I108_baseline": abs(statistics.mean(a_faith) - I108_OVERVIEW_FAITHFULNESS) <= 0.030
                                            if a_faith else False,
        "G7_attachment_deterministic": all(r["summary_determinism_ok"] for r in per_query),
    }

    artifact = {
        "meta": {"question": "do RAPTOR summaries as GENERATOR CONTEXT improve overview faithfulness?",
                 "prereg": ".hermes/plans/2026-11-04-p1-raptor-generator-context-preregistration.md",
                 "arms": {"A": "CE top-20 pages only", "B": "pages + top-2 RAPTOR summaries in the prompt"},
                 "generator": cfg.openai_model, "judge": args.judge_model,
                 "collection": cfg.qdrant_collection, "n_summaries": N_SUMMARIES,
                 "wall_seconds": round(wall, 1)},
        "deltas": deltas,
        "aggregates": {
            "A_faithfulness": (statistics.mean(a_faith) if a_faith else None),
            "B_faithfulness": statistics.mean([r["B"]["faithfulness"] for r in per_query
                                               if r["B"]["faithfulness"] is not None] or [0]) or None,
        },
        "guards": guards, "errors": errors, "per_query": per_query,
    }
    OUT.write_text(json.dumps(artifact, indent=1))
    sha = hashlib.sha256(OUT.read_bytes()).hexdigest()
    print(json.dumps({"deltas": deltas, "aggregates": artifact["aggregates"], "guards": guards}, indent=1))
    print(f"\nartifact: {OUT}\nsha256: {sha}")
    failed = [k for k, v in guards.items() if not v]
    print("ALL GUARDS PASS" if not failed else "GUARD FAILURE: " + ", ".join(failed))
    return 0 if not failed else 1


def _page_of(hit: dict):
    return (hit.get("payload") or hit).get("page_number")


if __name__ == "__main__":
    raise SystemExit(main())
