#!/usr/bin/env python3
"""
Generate a gold evaluation dataset by creating questions FROM known pages.

This avoids circular calibration (finding pages for questions):
  - Sample chunks at regular page-range intervals across the textbook
  - For each chunk, ask the LLM to generate physics questions answerable from that page
  - Save with relevant_pages pre-populated from the source chunk

Two generation strategies:
  - single-page (default): a question answerable from one sampled chunk.
  - multi-page (--multipage-count N): an overview/multihop question that requires
    connecting THREE distant passages and cannot be answered from any one of them
    (D5). The single-passage prompt structurally cannot produce these.
  - overview (--overview-count N): a book-spanning summary/comparison question, one
    per TOPIC, where the topics are derived from the book's own section headings
    (3c, the plan's §D method). Labels are NOT taken from the source — an overview
    question is not answered by any one page — so they are filled by an exhaustive
    book-wide scan (scripts/expand_gold_labels.py). Written to a separate file so
    the already-scanned single/multi-page set is never regenerated.

Output: data/eval_queries_gold.json

Usage:
    uv run python scripts/generate_gold_dataset.py --tenant global
    uv run python scripts/generate_gold_dataset.py --tenant global --n-chunks 40 --questions-per-chunk 2
    uv run python scripts/generate_gold_dataset.py --tenant global --multipage-count 20
    uv run python scripts/generate_gold_dataset.py --tenant global --overview-count 40 \
        --overview-output data/eval_queries_gold_overview.json
    uv run python scripts/generate_gold_dataset.py --tenant global --dry-run
"""
from __future__ import annotations

import json
import random
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import argparse
from loguru import logger
from rich.console import Console
from rich.progress import track

console = Console()

_QUESTION_TYPES = ["factual", "overview", "multihop"]

# D10: 512 truncated multi-question batches (the model was cut off mid-array and the
# parser then saw an unterminated JSON array and returned []). 2048 gives a full
# {n}-question array plus headroom.
#
# Session 3 (2026-10-13): 2048 was STILL too small for `openai/gpt-oss-20b` — it is a
# reasoning model, so the reasoning trace is billed against max_tokens. On page 403 the
# content came back null twice (finish_reason=length, everything spent on reasoning) and
# truncated to a 26-char partial array once. Raised to 8192 so the trace plus the answer
# array both fit.
_MAX_TOKENS = 8192

# D10: bounded retry for a generation call that fails or returns an unusable batch.
_GEN_RETRIES = 3

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

_MULTI_PROMPT = """\
You are building a physics RAG evaluation dataset.

Below are passages from THREE DIFFERENT, DISTANT parts of a physics textbook.

Your task: write {n} questions that CANNOT be answered from any single passage alone --
each must require connecting ideas from at least two of them.

Requirements:
- The question must name or imply both concepts, but must not say "passage" or "excerpt".
- It must be answerable from these passages COMBINED, and only from them.
- Prefer questions a student would actually ask, e.g. "How does X relate to Y?"
- Output ONLY a JSON array of strings.

Passage A (page {pa}):
{ta}

Passage B (page {pb}):
{tb}

Passage C (page {pc}):
{tc}

Output format:
["question 1", "question 2", ...]"""

# 3c: the overview path. One LLM call picks book-spanning TOPICS from the book's own
# section headings; one call per topic writes the question. The question must not be
# answerable from a single page — that is the whole point of the lane.
_OVERVIEW_TOPIC_PROMPT = """\
You are designing overview questions for a physics RAG evaluation set built on \
The Feynman Lectures on Physics, Volume 1.

Below are the book's section titles (markdown "##" headings), one per line.

Propose {n} book-spanning TOPICS for overview questions: concepts that recur across \
several chapters, or that the book develops over its whole length (for example \
conservation of energy, the atomic theory of matter, symmetry and invariance). \
Avoid narrow topics confined to a single section — a topic is only useful here if the \
book discusses it on many pages spread across different chapters.
{used}
Output ONLY a JSON array of {n} short topic strings, no other text.

Section titles:
{titles}

Output format:
["topic 1", "topic 2", ...]"""

_OVERVIEW_QUESTION_PROMPT = """\
You are building a physics RAG evaluation dataset from The Feynman Lectures on \
Physics, Volume 1.

Topic: {topic}

Write ONE overview question about this topic whose answer is a synthesis spanning \
the whole book — a summary, a comparison, or a "how does the book develop X" \
question. It must NOT be answerable from any single page.

Output ONLY a JSON array containing the one question string, no other text.

Output format:
["question"]"""

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


def sample_distant_triples(chunks: list, n: int, min_gap: int = 60) -> list[list]:
    """n triples of chunks from widely separated pages.

    `min_gap` forces the pages apart so the questions genuinely span the book rather than
    three neighbouring paragraphs (which would be answerable from one page).
    """
    rng = random.Random(1234)
    pool = [c for c in chunks if c.page_number]
    pool.sort(key=lambda c: c.page_number)
    triples, tries = [], 0
    while len(triples) < n and tries < n * 200:
        tries += 1
        a, b, c = rng.sample(pool, 3)
        pages = sorted([a.page_number, b.page_number, c.page_number])
        if pages[1] - pages[0] < min_gap or pages[2] - pages[1] < min_gap:
            continue
        triples.append([a, b, c])
    return triples


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
        # Mirror src/core/llm.py: strip a trailing /v1 (so a base that already
        # carries it is not doubled) and post to /v1/chat/completions. The cluster
        # gateway only serves the /v1 path — posting to /chat/completions 404s.
        base = cfg.openai_api_base.rstrip("/")
        if base.endswith("/v1"):
            base = base[:-3]
        headers = {"Content-Type": "application/json"}
        key = (cfg.openai_api_key or "").strip()
        if key and key.lower() != "none":
            headers["Authorization"] = f"Bearer {key}"
        resp = httpx.post(
            f"{base}/v1/chat/completions",
            headers=headers,
            json={
                "model": cfg.openai_model,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": _MAX_TOKENS,
                "temperature": 0.7,
            },
            timeout=120,
        )
        resp.raise_for_status()
        choice = resp.json()["choices"][0]
        content = choice.get("message", {}).get("content")
        if not content:
            # Reasoning models (gpt-oss, R1, Qwen3-thinking) return content=null when the
            # token budget went entirely to the reasoning trace. Say so, rather than dying
            # on `None.strip()` — the bounded retry in _generate_batch then applies.
            raise RuntimeError(
                f"empty content from {cfg.openai_model} "
                f"(finish_reason={choice.get('finish_reason')!r}) — the reasoning trace "
                f"likely consumed max_tokens={_MAX_TOKENS}"
            )
        return content.strip()


def _sanitize_json_backslashes(s: str) -> str:
    """Escape backslashes that are not the ``\\"`` or ``\\\\`` the model needs.

    Physics questions come back carrying LaTeX, and several LaTeX commands collide with
    *legal* JSON escapes — ``\\f`` in ``\\frac``, ``\\t`` in ``\\theta``, ``\\n`` in
    ``\\nu``, ``\\b`` in ``\\beta``, ``\\r`` in ``\\rangle``, ``\\u`` in ``\\underline``.
    A strict ``json.loads`` therefore either rejects the array (``\\(m v\\)``) or silently
    decodes the command into a control character (``\\frac`` → formfeed + ``rac``). Both
    corrupt the gold set, so we escape every backslash except ``\\"`` (the in-string quote)
    and ``\\\\`` (a literal backslash), then parse.
    """
    out: list[str] = []
    i = 0
    n = len(s)
    while i < n:
        c = s[i]
        if c == "\\":
            nxt = s[i + 1] if i + 1 < n else ""
            if nxt in ("\\", '"'):
                # The two escapes the model actually needs — keep them intact.
                out.append(c)
                out.append(nxt)
                i += 2
                continue
            # A lone backslash (LaTeX) or a trailing one — escape it.
            out.append("\\\\")
            i += 1
            continue
        out.append(c)
        i += 1
    return "".join(out)


def _extract_questions(raw: str) -> list[str]:
    """Pull a JSON array of non-empty strings out of a raw LLM response."""
    start = raw.find("[")
    end = raw.rfind("]") + 1
    if start == -1 or end == 0:
        return []
    body = raw[start:end]
    try:
        parsed = json.loads(_sanitize_json_backslashes(body))
    except json.JSONDecodeError:
        return []
    if not isinstance(parsed, list):
        return []
    return [q.strip() for q in parsed if isinstance(q, str) and q.strip()]


def _generate_batch(prompt: str, cfg, context: str) -> list[str]:
    """Call the LLM and parse a JSON array of questions. Bounded retry.

    D10: an empty/unparseable batch is **loud and asserted**, never a silent ``[]``.
    The old code returned ``[]`` on any failure, so a truncated or refused generation
    was indistinguishable from "the model chose to write no questions" — the run
    reported success with a quietly short dataset. Now every empty batch logs the raw
    response, retries a bounded number of times, and then raises, so a bad run fails
    visibly instead of under-populating the gold set.
    """
    last_raw = ""
    for attempt in range(1, _GEN_RETRIES + 1):
        try:
            last_raw = call_llm_raw(prompt, cfg)
            questions = _extract_questions(last_raw)
        except Exception as exc:
            questions = []
            logger.error(
                "Generation call failed ({}) — attempt {}/{}: {}",
                context, attempt, _GEN_RETRIES, exc,
            )
        if questions:
            return questions
        logger.error(
            "Empty generation batch ({}) — attempt {}/{}, raw response {} chars: {!r}",
            context, attempt, _GEN_RETRIES, len(last_raw), last_raw[:500],
        )
        if attempt < _GEN_RETRIES:
            time.sleep(min(2 ** attempt, 10))
    raise RuntimeError(
        f"Generation produced no questions for {context} after {_GEN_RETRIES} "
        f"attempts. Raw response: {last_raw[:500]!r}"
    )


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
    return _generate_batch(prompt, cfg, context=f"chunk {chunk.id} (page {chunk.page_number})")


def generate_multipage_questions(triple: list, n: int, cfg) -> list[str]:
    """Ask the LLM for overview/multihop questions spanning three distant passages."""
    a, b, c = triple
    prompt = _MULTI_PROMPT.format(
        n=n,
        pa=a.page_number, pb=b.page_number, pc=c.page_number,
        ta=a.text[:700], tb=b.text[:700], tc=c.text[:700],
    )
    pages = sorted({a.page_number, b.page_number, c.page_number})
    return _generate_batch(prompt, cfg, context=f"triple pages {pages}")


# ── 3c: overview lane — topics from the book's own headings, labels from the scan ──

_HEADING_RE = re.compile(r"^\s*#{1,3}\s+(.+?)\s*$")
# Front/back matter and table headings are not physics topics.
_SKIP_TITLE_PREFIXES = ("table ", "preface", "foreword", "acknowledg", "index",
                        "contents", "the feynman", "chapter ")


def extract_section_titles(chunks: list, max_titles: int = 250) -> list[str]:
    """Distinct section titles from the chunks' markdown headings, in page order.

    Grounded topic source: the chunker emits the book's own headings
    ("## 4-1 What is energy?", "## Conservation of Energy"). Section numbering is
    stripped, front/back matter and table headings are dropped, and titles are
    deduped case-insensitively with order preserved.
    """
    titles: list[str] = []
    seen: set[str] = set()
    for c in sorted(chunks, key=lambda c: c.page_number or 0):
        for line in (c.text or "").splitlines():
            m = _HEADING_RE.match(line)
            if not m:
                continue
            title = re.sub(r"^\d+-\d+\s+", "", m.group(1)).strip()
            if not (4 <= len(title) <= 70):
                continue
            low = title.lower()
            if any(low.startswith(p) for p in _SKIP_TITLE_PREFIXES):
                continue
            if low in seen:
                continue
            seen.add(low)
            titles.append(title)
            if len(titles) >= max_titles:
                return titles
    return titles


def generate_overview_questions(chunks: list, n: int, cfg,
                                exclude: list[str] | None = None,
                                candidates: int = 0) -> list[tuple[str, str]]:
    """(topic, question) pairs for the overview lane.

    One LLM call proposes ``candidates`` (default ``n``) book-spanning topics from the
    section titles; one call per topic writes the question. The question is pre-labelled
    ``overview`` — it is NOT run through ``classify_question``, which is exactly what
    mislabelled the multipage questions as ``multihop``.

    ``exclude`` suppresses topics already in the set: their titles are dropped from the
    candidate list AND named in the prompt, so the model cannot re-propose one via a
    different heading.
    """
    titles = extract_section_titles(chunks)
    if exclude:
        used_low = {t.strip().lower() for t in exclude}
        titles = [t for t in titles if t.strip().lower() not in used_low]
    if not titles:
        raise RuntimeError("no section titles left after exclusion — cannot derive topics")
    used_block = ""
    if exclude:
        used_block = ("\nDo NOT propose any of these topics (already in the set): "
                      + "; ".join(exclude) + ".\n")
    topics = _generate_batch(
        _OVERVIEW_TOPIC_PROMPT.format(n=candidates or n, titles="\n".join(titles),
                                      used=used_block),
        cfg, context="overview topics",
    )
    pairs: list[tuple[str, str]] = []
    for topic in topics[:n]:
        qs = _generate_batch(
            _OVERVIEW_QUESTION_PROMPT.format(topic=topic),
            cfg, context=f"overview topic {topic!r}",
        )
        if qs:
            pairs.append((topic, qs[0]))
    return pairs


def main():
    p = argparse.ArgumentParser(description="Generate gold evaluation dataset from known pages")
    p.add_argument("--tenant", default="global")
    p.add_argument("--n-chunks", type=int, default=30,
                   help="Number of chunks to sample (default: 30). 0 = skip single-page "
                        "generation entirely (an overview-only run).")
    p.add_argument("--questions-per-chunk", type=int, default=2,
                   help="Questions generated per chunk (default: 2)")
    p.add_argument("--multipage-count", type=int, default=0,
                   help="How many overview/multihop questions to generate from distant "
                        "page triples. 0 = skip (the old behaviour).")
    p.add_argument("--overview-count", type=int, default=0,
                   help="How many book-spanning overview questions to generate from topics "
                        "derived from the book's section headings. 0 = skip.")
    p.add_argument("--overview-output", default="data/eval_queries_gold_overview.json",
                   help="Where overview entries are written (kept separate from --output so "
                        "the already-scanned set is not regenerated)")
    p.add_argument("--overview-exclude-file", default="",
                   help="JSON file of existing entries; their `topic` values are excluded from "
                        "the new candidates (use when adding topics to an existing set)")
    p.add_argument("--overview-id-start", type=int, default=1,
                   help="First numeric id for the overview entries (default 1)")
    p.add_argument("--overview-candidates", type=int, default=0,
                   help="How many topics to request before trimming to --overview-count "
                        "(default: the same number). Request extras to allow filtering.")
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

    sampled = sample_chunks_stratified(chunks, args.n_chunks) if args.n_chunks > 0 else []
    if sampled:
        console.print(f"Sampled [cyan]{len(sampled)}[/] chunks across page range "
                      f"[dim](pages {min(c.page_number or 0 for c in sampled)}–"
                      f"{max(c.page_number or 0 for c in sampled)})[/]")
    else:
        console.print("[dim]No single-page sampling requested (--n-chunks 0).[/]")

    if args.dry_run:
        for c in sampled:
            console.print(f"  p{c.page_number}: {c.text[:80]}…")
        if args.overview_count > 0:
            titles = extract_section_titles(chunks)
            console.print(f"\n[cyan]{len(titles)}[/] section titles extracted; first 10:")
            for t in titles[:10]:
                console.print(f"  · {t}")
            console.print(f"would pick [cyan]{args.overview_count}[/] topics, "
                          f"then 1 question per topic")
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
                "expected_route": "vector",
                "relevant_pages": [chunk.page_number] if chunk.page_number else [],
                "calibrated": True,
                "answerable": True,
                "calibration_note": f"Generated from chunk {chunk.id} (page {chunk.page_number})",
            })
            qid_counter += 1

    if args.multipage_count > 0:
        triples = sample_distant_triples(chunks, args.multipage_count)
        console.print(f"Sampling [cyan]{len(triples)}[/] distant page triples…")
        for triple in track(triples, description="Generating multi-page questions…"):
            for q in generate_multipage_questions(triple, 1, cfg):
                pages = sorted({c.page_number for c in triple})
                entries.append({
                    "id": f"gold-{qid_counter:03d}",
                    "query": q,
                    "query_type": "multihop",
                    "expected_route": "vector",
                    "relevant_pages": pages,
                    "calibrated": True,
                    "answerable": True,
                    "calibration_note": f"Multi-page, generated from pages {pages}",
                })
                qid_counter += 1

    console.print(f"\nGenerated [bold green]{len(entries)}[/] questions from {len(sampled)} chunks")

    # Save — but never clobber an existing gold file when this run asked for no
    # single/multi-page entries. An overview-only run (--n-chunks 0 --overview-count N)
    # must not overwrite the already-scanned data/eval_queries_gold.json.
    if entries:
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(entries, indent=2, ensure_ascii=False))
        console.print(f"Saved to [bold]{out}[/]")
    else:
        console.print("[dim]No single/multi-page entries generated — --output left untouched.[/]")

    # Summary by type
    by_type: dict[str, int] = {}
    for e in entries:
        by_type[e["query_type"]] = by_type.get(e["query_type"], 0) + 1
    for qt, n in by_type.items():
        console.print(f"  {qt}: {n}")

    # 3c: overview lane — written to its own file, labels filled by the book-wide scan.
    if args.overview_count > 0:
        exclude: list[str] = []
        if args.overview_exclude_file:
            prev = json.loads(Path(args.overview_exclude_file).read_text())
            exclude = [e["topic"] for e in prev if e.get("topic")]
            console.print(f"Excluding [cyan]{len(exclude)}[/] topics already in the set")
        console.print("\nDeriving overview topics from the book's section headings…")
        pairs = generate_overview_questions(
            chunks, args.overview_count, cfg,
            exclude=exclude,
            candidates=args.overview_candidates or args.overview_count,
        )
        overview_entries = [
            {
                "id": f"ovw-{args.overview_id_start + i - 1:03d}",
                "query": q,
                "query_type": "overview",
                "expected_route": "raptor",
                "topic": topic,
                "relevant_pages": [],
                "calibrated": False,
                "answerable": True,
                "calibration_note": (
                    f"Overview, topic {topic!r} (topics derived from the book's section "
                    "headings); labels pending exhaustive book-wide scan"
                ),
            }
            for i, (topic, q) in enumerate(pairs, 1)
        ]
        oout = Path(args.overview_output)
        oout.parent.mkdir(parents=True, exist_ok=True)
        oout.write_text(json.dumps(overview_entries, indent=2, ensure_ascii=False))
        console.print(f"Saved [bold green]{len(overview_entries)}[/] overview entries "
                      f"to [bold]{oout}[/]")


if __name__ == "__main__":
    main()
