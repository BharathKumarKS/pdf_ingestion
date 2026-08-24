#!/usr/bin/env python3
"""
RAG Evaluation Pipeline — Synapse Learning Worlds

Evaluates retrieval and generation quality against the labeled query set in
data/eval_queries.json. Produces a versioned JSON report with a full config
snapshot so every run is reproducible and comparable.

Implements metrics equivalent to RAGAS without the framework dependency,
allowing cross-family LLM judging (Llama 3.2 generates, Claude/GPT-4 judges).

Retrieval metrics (computed per query):
  recall@fetch_k  — with score threshold — primary: did the base retriever
                    surface the relevant pages? (no downstream can recover
                    what wasn't retrieved)
  mrr@fetch_k     — mean reciprocal rank before threshold, where did the
                    first relevant result appear?
  precision@top_k — with score threshold — of the reranked top_k, how many
                    pages are relevant?
  ndcg@top_k      — normalised discounted cumulative gain, ranking quality
                    within the reranked top_k

Generation metrics (requires --judge-backend, skipped by default):
  faithfulness         — bipartite claim entailment: extract atomic claims
                         from answer, check each against each passage
  answer_relevance     — does the answer address the question? (judge scored 0-3)
  citation_accuracy    — are cited [Page N] numbers in the retrieved set?

Usage:
  # Retrieval-only (fast — no LLM synthesis, no judge)
  uv run python scripts/evaluate_rag.py

  # Full evaluation (judge = Claude)
  uv run python scripts/evaluate_rag.py \\
      --judge-backend openai \\
      --judge-api-base https://api.anthropic.com/v1 \\
      --judge-api-key sk-ant-... \\
      --judge-model claude-3-haiku-20240307

  # Custom run name and score threshold
  uv run python scripts/evaluate_rag.py --run-name after-hyde --score-threshold 0.4

  # Skip visual queries (no ColPali available)
  uv run python scripts/evaluate_rag.py --skip-visual
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from loguru import logger
from rich.console import Console
from rich.table import Table

console = Console()


# ── Config snapshot ──────────────────────────────────────────────────────────

def build_config_snapshot(cfg, threshold: float, tenant_id: str) -> dict:
    """Capture all tunable system settings for this evaluation run."""
    classifier_exists = Path(cfg.intent_classifier_path).exists()
    return {
        "tenant_id": tenant_id,
        "score_threshold": threshold,
        "embedding": {
            "model": cfg.embedding_model,
            "dim": cfg.embedding_dim,
        },
        "retriever": {
            "type": "hybrid (SPLADE+dense RRF)" if cfg.splade_enabled else "dense",
            "splade_enabled": cfg.splade_enabled,
            "fetch_k": cfg.reranker_fetch_k,
            "collection": cfg.qdrant_collection,
        },
        "reranker": {
            "enabled": cfg.reranker_enabled,
            "model": cfg.reranker_model if cfg.reranker_enabled else None,
            "top_k": cfg.reranker_top_k,
        },
        "intent_router": {
            "enabled": cfg.intent_router_enabled,
            "mode": "trained_classifier" if classifier_exists else "prototype",
            "classifier_path": cfg.intent_classifier_path if classifier_exists else None,
        },
        "raptor": {
            "max_levels": cfg.raptor_max_levels,
            "min_cluster_size": cfg.raptor_min_cluster_size,
        },
        "llm_generator": {
            "backend": cfg.llm_backend,
            "model": cfg.ollama_model if cfg.llm_backend == "ollama" else cfg.openai_model,
        },
        "chunking": {
            "chunk_size": cfg.chunk_size,
            "chunk_overlap": cfg.chunk_overlap,
        },
        "derivative_artifacts": {
            "enabled": cfg.da_enabled,
            "collection": cfg.da_collection,
            "card_types": cfg.da_card_types,
        },
        "mmr": {
            "enabled": cfg.mmr_enabled,
            "lambda": cfg.mmr_lambda,
            "candidates": cfg.mmr_candidates,
        },
    }


# ── Retrieval ─────────────────────────────────────────────────────────────────

def run_retrieval(
    query_text: str,
    store,
    embedder,
    reranker,
    cfg,
    tenant_id: str,
    threshold: float,
) -> dict:
    """Embed + search + rerank. Returns raw hits at both stages."""
    q_vec = np.array(embedder.embed_query(query_text), dtype=np.float32)

    hits = store.search_with_das(
        q_vec,
        query_text=query_text,
        tenant_id=tenant_id,
        fetch_k=cfg.reranker_fetch_k,
    )

    hits_above = [h for h in hits if h["score"] >= threshold]

    if cfg.reranker_enabled and hits:
        reranked = reranker.rerank(query_text, hits, top_k=cfg.reranker_top_k)
    else:
        reranked = hits[: cfg.reranker_top_k]

    return {
        "q_vec": q_vec,
        "hits": hits,
        "hits_above": hits_above,
        "reranked": reranked,
    }


# ── Retrieval metrics ─────────────────────────────────────────────────────────

def compute_retrieval_metrics(retrieval: dict, relevant_pages: list[int], cfg) -> dict:
    """Compute recall, MRR, precision, NDCG from retrieval results."""
    relevant = set(relevant_pages)
    hits     = retrieval["hits"]
    reranked = retrieval["reranked"]
    threshold = None  # extracted separately

    # Recall@fetch_k (base retriever, above threshold)
    pages_above = {h["page_number"] for h in retrieval["hits_above"]}
    recall = len(relevant & pages_above) / len(relevant) if relevant else None

    # MRR@fetch_k (no threshold — measures rank of first relevant result)
    mrr = 0.0
    for rank, h in enumerate(hits, start=1):
        if h["page_number"] in relevant:
            mrr = 1.0 / rank
            break

    # Precision@top_k and NDCG@top_k (reranked, binary relevance)
    # Deduplicate by page: a relevant page counts only on its first occurrence.
    # Without this, multiple chunks from the same page inflate DCG above IDCG.
    seen_pages: set[int] = set()
    gains = []
    for h in reranked:
        p = h["page_number"]
        if p in relevant and p not in seen_pages:
            gains.append(1)
            seen_pages.add(p)
        else:
            gains.append(0)

    n_relevant_hits = sum(gains)
    precision = n_relevant_hits / cfg.reranker_top_k if cfg.reranker_top_k else None

    dcg  = sum(g / np.log2(i + 2) for i, g in enumerate(gains))
    ideal_hits = min(len(relevant), cfg.reranker_top_k)
    idcg = sum(1.0 / np.log2(i + 2) for i in range(ideal_hits))
    ndcg = dcg / idcg if idcg > 0 else 0.0

    return {
        f"recall_at_{cfg.reranker_fetch_k}": round(recall, 4) if recall is not None else None,
        "mrr":                               round(mrr, 4),
        f"precision_at_{cfg.reranker_top_k}": round(precision, 4) if precision is not None else None,
        f"ndcg_at_{cfg.reranker_top_k}":      round(ndcg, 4),
    }


# ── Synthesis ─────────────────────────────────────────────────────────────────

_SYNTH_SYSTEM = (
    "You are a physics tutor. Your only source of truth is the textbook "
    "passages provided in the prompt. Rules you must never break:\n"
    "- Never fabricate or infer facts not stated in the passages.\n"
    "- Never quote text that does not appear verbatim or near-verbatim in the passages.\n"
    "- Never reinterpret the student's question.\n"
    "- Never cite a page number unless it appears as [Page N] in the passages.\n"
    "- If the passages are irrelevant, say so in one sentence and stop."
)

def synthesize(query_text: str, chunks: list[dict], cfg) -> str:
    """Run LLM synthesis over retrieved chunks (same logic as the app)."""
    from src.core.llm import call_llm

    if not chunks:
        return "No relevant passages were retrieved."

    passages = "\n\n".join(
        f"[Page {c.get('page_number', '?')}] {c.get('text', '')}"
        for c in chunks
    )
    prompt = (
        f"Using only the passages below, answer the student's question. "
        f"Cite the page number for each fact you include.\n\n"
        f"Question: {query_text}\n\n"
        f"Passages:\n{passages}"
    )
    return call_llm(prompt=prompt, system=_SYNTH_SYSTEM, settings=cfg, timeout=60)


# ── Generation metrics ────────────────────────────────────────────────────────

_CLAIM_EXTRACT_PROMPT = """\
Extract every atomic factual claim from this answer.
Each claim must be a single verifiable statement (one sentence or phrase).
Return ONLY a JSON array of strings, no other text.

Answer: {answer}"""

_ENTAILMENT_PROMPT = """\
Does the passage below clearly support or state the claim?
Answer YES if the passage entails the claim. Answer NO otherwise.
Only YES or NO on the first line.

Passage: {passage}

Claim: {claim}"""

_RELEVANCE_PROMPT = """\
Does this answer adequately address the student's question?
Rate 0-3:
0 = completely irrelevant, wrong, or refuses to answer
1 = partially addresses the question
2 = mostly addresses the question
3 = fully and accurately addresses the question
Return only the single digit, nothing else.

Question: {question}
Answer: {answer}"""


def compute_faithfulness(answer: str, chunks: list[dict], judge_fn) -> float:
    """Bipartite claim-entailment faithfulness. Cross-family judge required."""
    from src.core.llm import call_llm

    if not answer or not chunks:
        return 1.0

    # Extract atomic claims from the answer (generator LLM)
    raw = call_llm(
        prompt=_CLAIM_EXTRACT_PROMPT.format(answer=answer),
        system="You are a precise fact extractor.",
    )
    try:
        start = raw.find("[")
        end   = raw.rfind("]") + 1
        claims = json.loads(raw[start:end]) if start != -1 else []
    except Exception:
        claims = []

    if not claims:
        return 1.0

    passages = [c.get("text", "") for c in chunks if c.get("text")]
    faithful = 0

    for claim in claims:
        for passage in passages:
            verdict = judge_fn(
                _ENTAILMENT_PROMPT.format(passage=passage[:800], claim=claim)
            )
            if verdict.strip().upper().startswith("YES"):
                faithful += 1
                break

    return round(faithful / len(claims), 4)


def compute_answer_relevance(question: str, answer: str, judge_fn) -> float:
    """Judge-scored answer relevance, normalised to 0-1."""
    if not answer:
        return 0.0
    verdict = judge_fn(_RELEVANCE_PROMPT.format(question=question, answer=answer))
    digits = re.findall(r"\d", verdict)
    score  = int(digits[0]) if digits else 0
    return round(score / 3, 4)


def compute_citation_accuracy(answer: str, chunks: list[dict]) -> float:
    """Fraction of [Page N] citations in the answer that appear in retrieved chunks."""
    cited = {int(m) for m in re.findall(r"\[Page (\d+)\]", answer, re.IGNORECASE)}
    if not cited:
        return 1.0  # no citations — not penalised (no false claims)
    retrieved_pages = {c.get("page_number") for c in chunks}
    return round(len(cited & retrieved_pages) / len(cited), 4)


# ── Judge LLM factory ─────────────────────────────────────────────────────────

def make_judge_fn(args):
    """Returns a callable(prompt) -> str using the specified judge LLM backend."""
    if args.judge_backend == "skip":
        return None

    import httpx

    def _call_judge(prompt: str) -> str:
        if args.judge_backend == "ollama":
            payload = {
                "model": args.judge_model,
                "prompt": prompt,
                "stream": False,
            }
            try:
                resp = httpx.post(
                    f"{args.judge_api_base.rstrip('/')}/api/generate",
                    json=payload,
                    timeout=60,
                )
                resp.raise_for_status()
                return resp.json().get("response", "")
            except Exception as exc:
                logger.warning("Judge call failed: {}", exc)
                return ""
        else:
            headers = {
                "Authorization": f"Bearer {args.judge_api_key}",
                "Content-Type": "application/json",
            }
            payload = {
                "model": args.judge_model,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 200,
                "temperature": 0,
            }
            try:
                resp = httpx.post(
                    f"{args.judge_api_base.rstrip('/')}/chat/completions",
                    headers=headers,
                    json=payload,
                    timeout=30,
                )
                resp.raise_for_status()
                return resp.json()["choices"][0]["message"]["content"].strip()
            except Exception as exc:
                logger.warning("Judge call failed: {}", exc)
                return ""

    return _call_judge


# ── Per-query evaluation ──────────────────────────────────────────────────────

def evaluate_query(query: dict, store, embedder, reranker, cfg, judge_fn, args) -> dict:
    """Run full evaluation for one query. Returns per-query result dict."""
    qid         = query["id"]
    query_text  = query["query"]
    query_type  = query.get("query_type", "factual")
    rel_pages   = query.get("relevant_pages")  # None for visual / uncalibrated

    result = {
        "id":          qid,
        "query":       query_text,
        "query_type":  query_type,
        "calibrated":  query.get("calibrated", False),
        "relevant_pages": rel_pages,
        "metrics":     {},
        "generation":  {},
        "top_chunks":  [],
    }

    # Visual queries skip text retrieval metrics
    if query_type == "visual":
        if args.skip_visual:
            result["skipped"] = "visual query, --skip-visual set"
            return result
        result["skipped"] = "visual query — text retrieval metrics not applicable"
        return result

    # Queries without page labels skip retrieval metrics (but still run retrieval)
    try:
        retrieval = run_retrieval(
            query_text, store, embedder, reranker, cfg, args.tenant, args.score_threshold
        )
    except Exception as exc:
        result["error"] = str(exc)
        return result

    # Top chunks for inspection
    result["top_chunks"] = [
        {
            "page":  h.get("page_number"),
            "score": round(h.get("score", 0), 4),
            "text":  h.get("text", "")[:150],
        }
        for h in retrieval["reranked"][:3]
    ]

    # Retrieval metrics (only if relevant_pages labelled)
    if rel_pages is not None:
        result["metrics"] = compute_retrieval_metrics(
            retrieval, rel_pages, cfg
        )
    else:
        result["metrics"] = {"note": "relevant_pages not labelled — calibrate and set calibrated=true"}

    # Generation metrics (only if full eval mode)
    if not args.retrieval_only and judge_fn is not None:
        answer = synthesize(query_text, retrieval["reranked"], cfg)
        result["generation"]["answer"] = answer
        if answer:
            result["generation"]["faithfulness"]      = compute_faithfulness(
                answer, retrieval["reranked"], judge_fn
            )
            result["generation"]["answer_relevance"]  = compute_answer_relevance(
                query_text, answer, judge_fn
            )
            result["generation"]["citation_accuracy"] = compute_citation_accuracy(
                answer, retrieval["reranked"]
            )

    return result


# ── Aggregate metrics ─────────────────────────────────────────────────────────

def aggregate_metrics(results: list[dict], cfg) -> dict:
    """Average per-query metrics, broken down by query type."""
    recall_k  = f"recall_at_{cfg.reranker_fetch_k}"
    prec_k    = f"precision_at_{cfg.reranker_top_k}"
    ndcg_k    = f"ndcg_at_{cfg.reranker_top_k}"

    def _avg(vals):
        clean = [v for v in vals if v is not None]
        return round(sum(clean) / len(clean), 4) if clean else None

    by_type: dict[str, list] = {}
    for r in results:
        if r.get("skipped") or r.get("error"):
            continue
        qt = r["query_type"]
        if qt not in by_type:
            by_type[qt] = []
        by_type[qt].append(r)

    def _type_agg(items):
        return {
            recall_k:  _avg([i["metrics"].get(recall_k)  for i in items]),
            "mrr":     _avg([i["metrics"].get("mrr")      for i in items]),
            prec_k:    _avg([i["metrics"].get(prec_k)     for i in items]),
            ndcg_k:    _avg([i["metrics"].get(ndcg_k)     for i in items]),
            "faithfulness":      _avg([i["generation"].get("faithfulness")      for i in items]),
            "answer_relevance":  _avg([i["generation"].get("answer_relevance")  for i in items]),
            "citation_accuracy": _avg([i["generation"].get("citation_accuracy") for i in items]),
            "n_queries": len(items),
            "n_calibrated": sum(1 for i in items if i.get("calibrated")),
        }

    all_scored = [r for r in results if not r.get("skipped") and not r.get("error")]
    return {
        "overall":    _type_agg(all_scored),
        "by_type":    {qt: _type_agg(items) for qt, items in by_type.items()},
    }


# ── Report rendering ──────────────────────────────────────────────────────────

def _md_table(headers: list[str], rows: list[list[str]]) -> str:
    sep = "| " + " | ".join("---" for _ in headers) + " |"
    lines = ["| " + " | ".join(headers) + " |", sep]
    for row in rows:
        lines.append("| " + " | ".join(str(c) for c in row) + " |")
    return "\n".join(lines)


def build_summary_table(aggregated: dict, cfg) -> str:
    recall_k = f"recall_at_{cfg.reranker_fetch_k}"
    prec_k   = f"precision_at_{cfg.reranker_top_k}"
    ndcg_k   = f"ndcg_at_{cfg.reranker_top_k}"

    def _fmt(v):
        return f"{v:.3f}" if v is not None else "—"

    headers = [
        "Scope",
        f"Recall@{cfg.reranker_fetch_k}", "MRR",
        f"Precision@{cfg.reranker_top_k}", f"NDCG@{cfg.reranker_top_k}",
        "Faithfulness", "Ans.Relevance", "Citation Acc.", "n / cal",
    ]

    def _row(label, m):
        n = m.get("n_queries", 0)
        nc = m.get("n_calibrated", 0)
        return [
            label,
            _fmt(m.get(recall_k)), _fmt(m.get("mrr")),
            _fmt(m.get(prec_k)), _fmt(m.get(ndcg_k)),
            _fmt(m.get("faithfulness")), _fmt(m.get("answer_relevance")),
            _fmt(m.get("citation_accuracy")), f"{n}/{nc}",
        ]

    rows = [_row("Overall", aggregated["overall"])]
    for qt, m in aggregated["by_type"].items():
        rows.append(_row(f"  {qt}", m))

    return _md_table(headers, rows)


def build_per_query_table(results: list[dict], cfg) -> str:
    recall_k = f"recall_at_{cfg.reranker_fetch_k}"
    prec_k   = f"precision_at_{cfg.reranker_top_k}"
    ndcg_k   = f"ndcg_at_{cfg.reranker_top_k}"

    def _fmt(v):
        return f"{v:.3f}" if v is not None else "—"

    headers = [
        "ID", "Query", "Type",
        f"Recall@{cfg.reranker_fetch_k}", "MRR",
        f"P@{cfg.reranker_top_k}", f"NDCG@{cfg.reranker_top_k}",
        "Retrieved pages", "Labeled pages",
    ]

    rows = []
    for r in results:
        if r.get("skipped") or r.get("error"):
            continue
        m = r.get("metrics", {})
        top_pages = ", ".join(
            str(c["page"]) for c in r.get("top_chunks", [])[:cfg.reranker_top_k]
            if c.get("page") is not None
        )
        labeled = ", ".join(str(p) for p in (r.get("relevant_pages") or [])[:8])
        if len(r.get("relevant_pages") or []) > 8:
            labeled += ", …"
        rows.append([
            r["id"],
            r["query"][:55] + ("…" if len(r["query"]) > 55 else ""),
            r.get("query_type", ""),
            _fmt(m.get(recall_k)), _fmt(m.get("mrr")),
            _fmt(m.get(prec_k)), _fmt(m.get(ndcg_k)),
            top_pages or "—",
            labeled or "—",
        ])

    return _md_table(headers, rows)


def print_report(aggregated: dict, cfg):
    recall_k = f"recall_at_{cfg.reranker_fetch_k}"
    prec_k   = f"precision_at_{cfg.reranker_top_k}"
    ndcg_k   = f"ndcg_at_{cfg.reranker_top_k}"

    def _fmt(v):
        return f"{v:.3f}" if v is not None else "  —  "

    table = Table(title="RAG Evaluation Results", show_header=True, header_style="bold cyan")
    table.add_column("Scope",        style="bold")
    table.add_column(f"Recall@{cfg.reranker_fetch_k}", justify="right")
    table.add_column("MRR",          justify="right")
    table.add_column(f"Precision@{cfg.reranker_top_k}", justify="right")
    table.add_column(f"NDCG@{cfg.reranker_top_k}", justify="right")
    table.add_column("Faithfulness",     justify="right")
    table.add_column("Ans.Relevance",    justify="right")
    table.add_column("Citation Acc.",    justify="right")
    table.add_column("n / calibrated",   justify="right")

    def _row(label, m):
        n = m.get("n_queries", 0)
        nc = m.get("n_calibrated", 0)
        table.add_row(
            label,
            _fmt(m.get(recall_k)),
            _fmt(m.get("mrr")),
            _fmt(m.get(prec_k)),
            _fmt(m.get(ndcg_k)),
            _fmt(m.get("faithfulness")),
            _fmt(m.get("answer_relevance")),
            _fmt(m.get("citation_accuracy")),
            f"{n} / {nc}",
        )

    _row("Overall", aggregated["overall"])
    for qt, m in aggregated["by_type"].items():
        _row(f"  {qt}", m)

    console.print(table)

    # Warning if recall is low
    overall_recall = aggregated["overall"].get(recall_k)
    if overall_recall is not None and overall_recall < 0.6:
        console.print(
            f"\n[bold yellow]Warning:[/] Recall@{cfg.reranker_fetch_k} = {overall_recall:.3f} "
            f"(< 0.60). The base retriever is missing relevant pages. "
            f"Consider: HyDE, lower score threshold, or query expansion."
        )


# ── CLI ────────────────────────────────────────────────────────────────────────

def parse_args():
    p = argparse.ArgumentParser(
        description="Evaluate Synapse RAG pipeline against labeled query set"
    )
    p.add_argument("--query-file", default="data/eval_queries.json",
                   help="Path to labeled query file (default: data/eval_queries.json)")
    p.add_argument("--tenant", default="global",
                   help="Tenant ID to query against (default: global)")
    p.add_argument("--score-threshold", type=float, default=0.45,
                   help="Similarity score threshold for recall/precision (default: 0.45)")
    p.add_argument("--retrieval-only", action="store_true",
                   help="Skip LLM synthesis and generation metrics (fast mode)")
    p.add_argument("--skip-visual", action="store_true",
                   help="Skip visual (ColPali) queries")
    p.add_argument("--run-name", default="baseline",
                   help="Name prefix for the output file (default: baseline)")
    p.add_argument("--output-dir", default="data/eval_results",
                   help="Directory to write results (default: data/eval_results)")

    # Judge LLM (cross-family — should be different from generator)
    p.add_argument("--judge-backend", choices=["openai", "ollama", "skip"], default="skip",
                   help="Judge LLM backend for generation metrics (default: skip)")
    p.add_argument("--judge-api-base", default="https://api.openai.com/v1")
    p.add_argument("--judge-api-key",  default="")
    p.add_argument("--judge-model",    default="gpt-4o-mini",
                   help="Judge model (e.g. claude-3-haiku-20240307, gpt-4o-mini)")

    return p.parse_args()


def main():
    args = parse_args()

    from src.core.config import get_settings
    from src.pdf_ingestion.embedder  import get_embedder
    from src.pdf_ingestion.reranker  import get_reranker
    from src.pdf_ingestion.store     import DocumentStore

    cfg = get_settings()

    console.print("\n[bold blue]Synapse RAG Evaluation Pipeline[/]")
    console.print(f"  Query file:       {args.query_file}")
    console.print(f"  Tenant:           {args.tenant}")
    console.print(f"  Score threshold:  {args.score_threshold}")
    console.print(f"  Mode:             {'retrieval-only' if args.retrieval_only else 'full (retrieval + generation)'}")
    console.print(f"  Judge LLM:        {args.judge_backend}" +
                  (f" / {args.judge_model}" if args.judge_backend != "skip" else " (disabled)"))
    console.print()

    # Load queries
    queries = json.loads(Path(args.query_file).read_text())
    queries = [q for q in queries if not q.get("id", "").startswith("_")]  # skip _note entries

    console.print(f"Loaded [cyan]{len(queries)}[/] queries from {args.query_file}")

    # Initialise components
    store    = DocumentStore(cfg)
    embedder = get_embedder(cfg)
    reranker = get_reranker(cfg)
    judge_fn = make_judge_fn(args)

    # Build config snapshot
    config_snapshot = build_config_snapshot(cfg, args.score_threshold, args.tenant)

    # Evaluate each query
    results: list[dict] = []
    t_start = time.monotonic()

    for i, query in enumerate(queries, start=1):
        qid = query.get("id", f"q{i}")
        console.print(f"  [{i:2d}/{len(queries)}] {qid}: {query['query'][:60]}...")

        result = evaluate_query(query, store, embedder, reranker, cfg, judge_fn, args)
        results.append(result)

        if "error" in result:
            console.print(f"        [red]Error: {result['error']}[/]")
        elif result.get("skipped"):
            console.print(f"        [dim]Skipped: {result['skipped']}[/]")
        else:
            m = result["metrics"]
            recall_k = f"recall_at_{cfg.reranker_fetch_k}"
            if m.get(recall_k) is not None:
                color = "green" if m[recall_k] >= 0.6 else "red"
                console.print(
                    f"        recall@{cfg.reranker_fetch_k}=[{color}]{m[recall_k]:.3f}[/] "
                    f"mrr={m.get('mrr', 0):.3f} "
                    f"precision@{cfg.reranker_top_k}={m.get(f'precision_at_{cfg.reranker_top_k}', 0):.3f} "
                    f"ndcg@{cfg.reranker_top_k}={m.get(f'ndcg_at_{cfg.reranker_top_k}', 0):.3f}"
                )

    elapsed = time.monotonic() - t_start
    console.print(f"\nEvaluation complete in {elapsed:.1f}s")

    # Aggregate and display
    aggregated = aggregate_metrics(results, cfg)
    print_report(aggregated, cfg)

    # Save results — single .md file (summary + per-query tables + config)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    ts       = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H%M")
    out_path = output_dir / f"{args.run_name}_{ts}.md"

    timestamp   = datetime.now(timezone.utc).isoformat(timespec="seconds")
    summary_tbl = build_summary_table(aggregated, cfg)
    per_qry_tbl = build_per_query_table(results, cfg)

    cfg_lines = "\n".join([
        f"- **Tenant:** {args.tenant}",
        f"- **Collection:** {cfg.qdrant_collection}",
        f"- **Embedder:** {cfg.embedding_model}",
        f"- **SPLADE:** {cfg.splade_enabled}",
        f"- **Reranker:** {cfg.reranker_enabled}" + (f" ({cfg.reranker_model})" if cfg.reranker_enabled else ""),
        f"- **Min content page:** {cfg.min_content_page}",
        f"- **Score threshold:** {args.score_threshold}",
        f"- **Judge:** {args.judge_model if args.judge_backend != 'skip' else 'none'}",
        f"- **Elapsed:** {round(elapsed, 1)}s",
    ])

    out_path.write_text(
        f"# {args.run_name}\n\n"
        f"**{timestamp}**\n\n"
        f"## Summary\n\n"
        f"{summary_tbl}\n\n"
        f"## Per-Query Results\n\n"
        f"{per_qry_tbl}\n\n"
        f"## Config\n\n"
        f"{cfg_lines}\n"
    )

    console.print(f"\n[green]Results saved to:[/] {out_path}")
    console.print(
        "\n[dim]Tip: Run again with --run-name <name> after each system change "
        "to track lift.[/]"
    )


if __name__ == "__main__":
    main()
