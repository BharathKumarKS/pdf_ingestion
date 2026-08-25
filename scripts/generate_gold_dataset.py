#!/usr/bin/env python3
"""
Generate a gold evaluation dataset by creating questions FROM known pages.

This avoids circular calibration (finding pages for questions):
  - Sample chunks at regular page-range intervals across the textbook
  - For each chunk, ask the LLM to generate physics questions answerable from that page
  - Save with relevant_pages pre-populated from the source chunk

Output: data/eval_queries_gold.json

Usage:
    uv run python scripts/generate_gold_dataset.py --tenant global
    uv run python scripts/generate_gold_dataset.py --tenant global --n-chunks 40 --questions-per-chunk 2
    uv run python scripts/generate_gold_dataset.py --tenant global --dry-run
"""
from __future__ import annotations

import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import argparse
from loguru import logger
from rich.console import Console
from rich.progress import track

console = Console()

_QUESTION_TYPES = ["factual", "overview", "multihop"]

_PROMPT = """\
You are building a physics RAG evaluation dataset.

Below is a passage from a physics textbook (page {page}).

Your task: generate {n} physics questions whose COMPLETE answer is contained in this passage.
Requirements:
- Each question must be answerable using ONLY this passage.
- Mix question types: factual (specific fact/formula), conceptual (why/how), and definitional.
- Do NOT include questions that require outside knowledge.
- Make questions specific enough that only this page answers them well.
- Output ONLY a JSON array of strings, no other text.

Passage:
{text}

Output format:
["question 1", "question 2", ...]"""

_TYPE_PROMPT = """\
Classify this physics question into one of: factual, overview, multihop.
- factual: asks for a specific fact, formula, number, or definition
- overview: asks for a summary, comparison, or explanation spanning multiple ideas
- multihop: requires connecting two or more concepts to answer

Question: {question}
Answer with just the label (factual/overview/multihop):"""


def sample_chunks_stratified(chunks: list, n: int, seed: int = 42) -> list:
    """Sample n chunks spread evenly across the page range."""
    if not chunks:
        return []
    chunks_sorted = sorted(chunks, key=lambda c: c.page_number or 0)
    if len(chunks_sorted) <= n:
        return chunks_sorted
    step = len(chunks_sorted) / n
    indices = [int(i * step) for i in range(n)]
    return [chunks_sorted[i] for i in indices]


def call_llm_raw(prompt: str, cfg) -> str:
    """Call the configured LLM and return raw text."""
    import httpx
    if cfg.llm_backend == "ollama":
        resp = httpx.post(
            f"{cfg.ollama_host}/api/generate",
            json={"model": cfg.ollama_model, "prompt": prompt, "stream": False},
            timeout=cfg.ollama_timeout,
        )
        resp.raise_for_status()
        return resp.json().get("response", "").strip()
    else:
        resp = httpx.post(
            f"{cfg.openai_api_base.rstrip('/')}/chat/completions",
            headers={"Authorization": f"Bearer {cfg.openai_api_key}"},
            json={
                "model": cfg.openai_model,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 512,
                "temperature": 0.7,
            },
            timeout=60,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"].strip()


def classify_question(question: str, cfg) -> str:
    try:
        raw = call_llm_raw(_TYPE_PROMPT.format(question=question), cfg)
        label = raw.strip().lower().split()[0] if raw.strip() else "factual"
        return label if label in _QUESTION_TYPES else "factual"
    except Exception:
        return "factual"


def generate_questions_for_chunk(chunk, n: int, cfg) -> list[str]:
    """Ask LLM to generate n questions answerable from this chunk."""
    prompt = _PROMPT.format(
        page=chunk.page_number or "?",
        n=n,
        text=chunk.text[:1200],  # cap to avoid token limit
    )
    try:
        raw = call_llm_raw(prompt, cfg)
        # Extract JSON array from response
        start = raw.find("[")
        end   = raw.rfind("]") + 1
        if start == -1 or end == 0:
            return []
        questions = json.loads(raw[start:end])
        return [q.strip() for q in questions if isinstance(q, str) and q.strip()]
    except Exception as exc:
        logger.warning("Question generation failed for chunk {}: {}", chunk.id, exc)
        return []


def main():
    p = argparse.ArgumentParser(description="Generate gold evaluation dataset from known pages")
    p.add_argument("--tenant", default="global")
    p.add_argument("--n-chunks", type=int, default=30,
                   help="Number of chunks to sample (default: 30)")
    p.add_argument("--questions-per-chunk", type=int, default=2,
                   help="Questions generated per chunk (default: 2)")
    p.add_argument("--min-chunk-tokens", type=int, default=80,
                   help="Skip chunks with fewer tokens (default: 80)")
    p.add_argument("--output", default="data/eval_queries_gold.json")
    p.add_argument("--dry-run", action="store_true",
                   help="Print sampled chunks without calling LLM")
    args = p.parse_args()

    from src.core.config import get_settings
    from src.core.database import Chunk, Document, get_engine
    from sqlmodel import Session, select

    cfg = get_settings()
    engine = get_engine(cfg)

    # Load chunks for the tenant
    with Session(engine) as session:
        docs = session.exec(
            select(Document).where(Document.tenant_id == args.tenant)
        ).all()
        doc_ids = {d.id for d in docs}

        chunks = session.exec(
            select(Chunk).where(Chunk.document_id.in_(doc_ids))  # type: ignore[attr-defined]
        ).all()

    # Filter out short chunks (likely front matter, headers)
    chunks = [c for c in chunks if c.text and len(c.text.split()) >= args.min_chunk_tokens]

    console.print(f"[cyan]{len(chunks)}[/] chunks available after filtering")

    sampled = sample_chunks_stratified(chunks, args.n_chunks)
    console.print(f"Sampled [cyan]{len(sampled)}[/] chunks across page range "
                  f"[dim](pages {min(c.page_number or 0 for c in sampled)}–"
                  f"{max(c.page_number or 0 for c in sampled)})[/]")

    if args.dry_run:
        for c in sampled:
            console.print(f"  p{c.page_number}: {c.text[:80]}…")
        return

    # Generate questions
    entries = []
    qid_counter = 1

    for chunk in track(sampled, description="Generating questions…"):
        questions = generate_questions_for_chunk(chunk, args.questions_per_chunk, cfg)
        for q in questions:
            qt = classify_question(q, cfg)
            entries.append({
                "id": f"gold-{qid_counter:03d}",
                "query": q,
                "query_type": qt,
                "relevant_pages": [chunk.page_number] if chunk.page_number else [],
                "calibrated": True,
                "calibration_note": f"Generated from chunk {chunk.id} (page {chunk.page_number})",
            })
            qid_counter += 1

    console.print(f"\nGenerated [bold green]{len(entries)}[/] questions from {len(sampled)} chunks")

    # Save
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(entries, indent=2, ensure_ascii=False))
    console.print(f"Saved to [bold]{out}[/]")

    # Summary by type
    by_type: dict[str, int] = {}
    for e in entries:
        by_type[e["query_type"]] = by_type.get(e["query_type"], 0) + 1
    for qt, n in by_type.items():
        console.print(f"  {qt}: {n}")


if __name__ == "__main__":
    main()
