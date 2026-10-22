#!/usr/bin/env python
"""§I23(c) — which model should extract the graph's concepts? A bounded, two-arm comparison.

Why this exists
---------------
`IMPROVEMENTS.md` §I23's fix list ends with: *"(c) settle the extraction model deliberately
(reasoning vs non-reasoning) with an output-quality comparison"*. The measured shape that raised it,
on ONE 2,000-char chunk: `openai/gpt-oss-20b` **12.9 s**, 1,244 completion tokens of which **4,495
chars were hidden reasoning**, 10 concepts / 10 prerequisites; `Qwen/Qwen3-VL-8B-Instruct` **3.2 s**,
166 tokens, 0 reasoning, 5 concepts / 3 prerequisites. Both returned valid JSON.

That is roughly a 4x build-time difference on a 3,796-chunk book — and it is a QUALITY decision, not
a free speedup, because the two did not return the same content. This probe is the comparison, and
it has to be settled BEFORE the rebuild: the checkpoint key includes the model
(`graph_checkpoint.prompt_digest` + `_extraction_model()`), so a mid-build swap discards every
completed extraction.

Single-variable by construction
------------------------------
Both arms run the SAME code path and differ only in the model id:

  * the prompt is **imported** from `graph_builder._CONCEPT_PROMPT`, never retyped, so it cannot
    drift from production;
  * the same `text[:2000]` truncation `_extract_concepts` applies;
  * the same payload knobs as `llm._call_openai` — `temperature 0.3`, `top_p 0.9`,
    `response_format={"type": "json_object"}`, `{base}/v1/chat/completions`;
  * the same acceptance rules as `_extract_concepts`: not-empty, parses as JSON, and is a dict.
    Anything else is `ok=False`, which is NOT the same as "this chunk has no concepts".

The chunk sample is deterministic but **effectively random**: chunks are ordered by `Chunk.id`, which
is a `uuid4`, so "every k-th row" is a reproducible random draw over the whole document rather than a
page range. Re-running compares the same texts; the printed page span is the first and last sample's
page, not a contiguous window.

What is measured, and what is NOT
---------------------------------
Structural metrics only: valid-JSON rate, concepts per chunk, whether the output obeys the prompt's
own **"3-7 concepts maximum"** rule, prerequisite edges, name shape, type validity against the
prompt's enum, latency, tokens, hidden-reasoning volume, and the **overlap of the extracted names
with the concept vocabulary already in the graph** (the proxy for how much §G3 entity-resolution
work each model creates).

⚠️ **There is no LLM judge here, on purpose.** The cluster serves exactly two text models and BOTH
of them are arms of this comparison, so a judge would be scoring its own output — the bias would be
in the direction of whichever arm judged. The artifact therefore carries a **side-by-side sample**
(`samples`: the same chunks' concept names from both arms) for a human to read, and every judgement
above is mechanical. Do not read this artifact as "model X is better"; read it as "here is what each
one produces, and here is the structural price".

⚠️ **Power.** n is small (default 24 chunks) and drawn from one book. The per-chunk counts are noisy
and the sample is not stratified by chapter. Quote the distributions (`concepts.per_chunk`), not a
single mean, and treat any difference smaller than the spread as unresolved.

⚠️ **This probe is NOT bit-reproducible.** It runs at `temperature 0.3`, exactly as production does,
so the same chunk can yield different concepts on a second run. Two consecutive `--n 24` runs of this
probe on the same sample moved gpt-oss-20b's graph-vocabulary overlap 82.11 % → 86.46 % and its p50
latency 10.92 s → 9.58 s. **Read every arm difference against that run-to-run spread**, which is why
the artifact reports distributions rather than a single verdict number.

Usage
-----
    uv run python logs/p1/step10/i23c_extraction_model_compare.py [--n 24] [--workers 4] [--force]
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import httpx
from loguru import logger
from sqlmodel import Session, select

from src.core.config import get_settings
from src.core.database import Chunk, get_engine, get_memgraph
from src.pdf_ingestion.graph_builder import _CONCEPT_PROMPT  # noqa: PLC2701 — import, never retype

OUT_DEFAULT = "logs/p1/step10/i23c_extraction_model_compare.json"
DOC_ID = "7ba61432-c5e0-416d-aecf-25a232523481"
ARMS = ["openai/gpt-oss-20b", "Qwen/Qwen3-VL-8B-Instruct"]
VALID_TYPES = {"law", "theorem", "quantity", "formula", "process",
               "phenomenon", "definition", "experiment", "person"}
CONCEPT_MIN, CONCEPT_MAX = 3, 7          # the prompt's own rule, quoted verbatim in the artifact


def sample_chunks(n: int) -> list[dict]:
    """Every k-th content chunk of the document, ordered by id — deterministic, no RNG."""
    engine = get_engine()
    with Session(engine) as s:
        rows = s.exec(
            select(Chunk.id, Chunk.text, Chunk.page_number)
            .where(Chunk.document_id == DOC_ID)
            .where(Chunk.is_content == True)          # noqa: E712 — SQLModel needs the comparison
            .order_by(Chunk.id)
        ).all()
    rows = [r for r in rows if r[1] and len(r[1].strip()) >= 200]
    if not rows:
        return []
    step = max(1, len(rows) // n)
    picked = rows[::step][:n]
    return [{"chunk_id": r[0], "page": r[2], "text": r[1]} for r in picked]


def call_arm(client: httpx.Client, base: str, key: str, model: str, text: str) -> dict:
    """One extraction call, mirroring `llm._call_openai`'s payload exactly (model aside)."""
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": _CONCEPT_PROMPT.format(text=text[:2000])}],
        "temperature": 0.3,
        "top_p": 0.9,
        "response_format": {"type": "json_object"},
    }
    headers = {"Content-Type": "application/json"}
    if key and key.lower() != "none":
        headers["Authorization"] = f"Bearer {key}"
    t0 = time.time()
    try:
        r = client.post(f"{base}/v1/chat/completions", json=payload, headers=headers)
        wall = time.time() - t0
        body = r.json()
    except Exception as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}", "wall_s": time.time() - t0}

    usage = body.get("usage") or {}
    choices = body.get("choices") or []
    if not choices:
        return {"ok": False, "error": "HTTP 200 with no choices", "wall_s": wall, "usage": usage}
    msg = choices[0].get("message") or {}
    content = msg.get("content") or ""
    # Whatever the gateway exposes about hidden reasoning, recorded verbatim rather than assumed.
    reasoning = msg.get("reasoning_content") or msg.get("reasoning") or ""
    out: dict = {
        "wall_s": round(wall, 2),
        "usage": usage,
        "finish_reason": choices[0].get("finish_reason"),
        "content_chars": len(content),
        "reasoning_chars": len(reasoning) if reasoning else 0,
    }
    # The same three acceptance rules as `_extract_concepts`.
    if not content:
        out.update(ok=False, error="empty response")
        return out
    try:
        data = json.loads(content)
    except (json.JSONDecodeError, TypeError) as exc:
        out.update(ok=False, error=f"invalid JSON: {exc}")
        return out
    if not isinstance(data, dict):
        out.update(ok=False, error=f"expected a JSON object, got {type(data).__name__}")
        return out

    concepts = data.get("concepts", []) or []
    prereqs = data.get("prerequisites", []) or []
    names, types, bad_types = [], [], 0
    for c in concepts:
        if isinstance(c, dict) and c.get("name"):
            names.append(str(c["name"]))
            t = str(c.get("type", ""))
            types.append(t)
            if t not in VALID_TYPES:
                bad_types += 1
    out.update(
        ok=True, error=None,
        n_concepts=len(names), n_prereq_edges=len(prereqs),
        names=names, types=types, n_bad_types=bad_types,
        raw_content=content,
    )
    return out


def graph_vocabulary() -> set[str]:
    """The concept names already in the graph — the §G3 merge surface."""
    driver = get_memgraph(get_settings())
    if driver is None:
        return set()
    with driver.session() as s:
        return {r["name"] for r in s.run("MATCH (c:Concept) RETURN c.name AS name").data() if r["name"]}


def summarise(records: list[dict], vocab: set[str]) -> dict:
    """Per-arm aggregates. Distributions, not just means — the sample is small."""
    ok = [r for r in records if r.get("ok")]
    lat = sorted(r["wall_s"] for r in records)
    per_chunk = sorted(r["n_concepts"] for r in ok)
    names = [n for r in ok for n in r["names"]]
    comp = [r["usage"].get("completion_tokens", 0) for r in records if r.get("usage")]
    prompt_t = [r["usage"].get("prompt_tokens", 0) for r in records if r.get("usage")]
    in_band = sum(1 for c in per_chunk if CONCEPT_MIN <= c <= CONCEPT_MAX)
    uniq = {n.strip().lower() for n in names}
    vocab_l = {v.strip().lower() for v in vocab}
    matched = uniq & vocab_l
    novel = sorted(uniq - vocab_l)

    def pct(a, b):
        return round(100.0 * a / b, 2) if b else None

    return {
        "n_calls": len(records),
        "n_ok": len(ok),
        "valid_json_pct": pct(len(ok), len(records)),
        "errors": sorted({r.get("error") for r in records if not r.get("ok") and r.get("error")}),
        "concepts": {
            "per_chunk": per_chunk,
            "mean": round(statistics.mean(per_chunk), 2) if per_chunk else None,
            "median": statistics.median(per_chunk) if per_chunk else None,
            "min": min(per_chunk) if per_chunk else None,
            "max": max(per_chunk) if per_chunk else None,
            "within_prompt_band_3_7": in_band,
            "above_prompt_max": sum(1 for c in per_chunk if c > CONCEPT_MAX),
            "below_prompt_min": sum(1 for c in per_chunk if c < CONCEPT_MIN),
        },
        "prereq_edges": {
            "total": sum(r["n_prereq_edges"] for r in ok),
            "per_chunk_mean": round(statistics.mean([r["n_prereq_edges"] for r in ok]), 2) if ok else None,
        },
        "names": {
            "total": len(names),
            "distinct_lowercased": len(uniq),
            "distinct_pct": pct(len(uniq), len(names)),
            "mean_words": round(statistics.mean([len(n.split()) for n in names]), 2) if names else None,
            "in_graph_vocabulary": len(matched),
            "in_graph_vocabulary_pct": pct(len(matched), len(uniq)),
            "not_in_graph_vocabulary": len(novel),
            "not_in_graph_vocabulary_examples": novel[:30],
            # ⚠️ A CRUDE PROXY, not a verdict: the prompt asks for the canonical FULL name and
            # explicitly forbids symbols ("kinetic energy", not "KE"). A name with no word of >=4
            # alphabetic characters is symbol-like or a fragment ("delta", "sigma", "ds"). It is
            # reported so the two arms can be compared on the same rule, and it does not decide
            # which arm is right — read `not_in_graph_vocabulary_examples` for that.
            "symbol_like_count": sum(
                1 for n in uniq if not any(len(w) >= 4 and w.isalpha() for w in n.split())
            ),
        },
        "types": {
            "invalid_type_count": sum(r["n_bad_types"] for r in ok),
            "distinct_types": sorted({t for r in ok for t in r["types"]}),
        },
        "latency_s": {
            "mean": round(statistics.mean(lat), 2) if lat else None,
            "p50": lat[len(lat) // 2] if lat else None,
            "max": lat[-1] if lat else None,
            "total": round(sum(lat), 1),
        },
        "tokens": {
            "prompt_mean": round(statistics.mean(prompt_t), 1) if prompt_t else None,
            "completion_mean": round(statistics.mean(comp), 1) if comp else None,
            "completion_total": sum(comp),
            "reasoning_chars_total": sum(r.get("reasoning_chars", 0) for r in records),
        },
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=OUT_DEFAULT)
    ap.add_argument("--n", type=int, default=24, help="chunks to sample (deterministic)")
    ap.add_argument("--workers", type=int, default=4, help="in-flight calls per arm")
    ap.add_argument("--models", default=",".join(ARMS))
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    if Path(args.out).exists() and not args.force:
        print(f"REFUSING to overwrite {args.out} without --force — a registered artifact "
              f"must not be clobbered by accident.", file=sys.stderr)
        return 4

    cfg = get_settings()
    models = [m.strip() for m in args.models.split(",") if m.strip()]
    chunks = sample_chunks(args.n)
    if not chunks:
        print("ABORT: no content chunks sampled — writing nothing.", file=sys.stderr)
        return 3
    print(f"sampled {len(chunks)} content chunks from {DOC_ID[:8]} "
          f"(sampled pages {min(c['page'] for c in chunks if c['page'])}.."
          f"{max(c['page'] for c in chunks if c['page'])} — a random draw, not a window)")

    vocab = graph_vocabulary()
    print(f"graph vocabulary: {len(vocab):,} concept names")

    base = cfg.openai_api_base.rstrip("/")
    if base.endswith("/v1"):
        base = base[:-3]
    records: dict[str, list[dict]] = {m: [] for m in models}

    with httpx.Client(timeout=300.0) as client:
        for model in models:
            t0 = time.time()
            with ThreadPoolExecutor(max_workers=args.workers) as ex:
                futs = {ex.submit(call_arm, client, base, cfg.openai_api_key, model, c["text"]): c
                        for c in chunks}
                for fut in as_completed(futs):
                    c = futs[fut]
                    rec = fut.result()
                    rec.update(chunk_id=c["chunk_id"], page=c["page"], model=model)
                    records[model].append(rec)
            records[model].sort(key=lambda r: r["chunk_id"])
            ok = sum(1 for r in records[model] if r.get("ok"))
            print(f"  {model}: {ok}/{len(chunks)} ok in {time.time() - t0:.1f}s")

    if not any(r.get("ok") for rs in records.values() for r in rs):
        print("ABORT: every call failed — writing nothing (no data must not look like zero data).",
              file=sys.stderr)
        return 3

    arms = {m: summarise(rs, vocab) for m, rs in records.items()}
    # Side-by-side, same chunk, both arms — the part a human reads.
    samples = []
    for c in chunks[:5]:
        entry = {"chunk_id": c["chunk_id"], "page": c["page"], "text_head": c["text"][:300]}
        for m in models:
            r = next((x for x in records[m] if x["chunk_id"] == c["chunk_id"]), {})
            entry[m] = {"ok": r.get("ok"), "names": r.get("names", []),
                        "n_prereq_edges": r.get("n_prereq_edges"), "wall_s": r.get("wall_s")}
        samples.append(entry)

    out = {
        "meta": {
            "register_item": "§I23(c)",
            "question": "which model should extract the graph's concepts, before the rebuild",
            "document_id": DOC_ID,
            "models": models,
            "n_chunks": len(chunks),
            "workers": args.workers,
            "endpoint": cfg.openai_api_base,
            "prompt_source": "src/pdf_ingestion/graph_builder._CONCEPT_PROMPT (imported, not retyped)",
            "payload_knobs": {"temperature": 0.3, "top_p": 0.9, "response_format": "json_object",
                              "text_truncation": "text[:2000]"},
            "prompt_rule_band": [CONCEPT_MIN, CONCEPT_MAX],
            "graph_vocabulary_size": len(vocab),
            "vocabulary_overlap_caveat": (
                "CIRCULAR BY CONSTRUCTION: the graph's vocabulary was itself produced by "
                "openai/gpt-oss-20b's extraction (commit-era build of this same document), so the "
                "overlap metric favours that arm — it partly measures a model agreeing with itself. "
                "Use it to compare how much NEW vocabulary an arm introduces, not as a quality score."
            ),
            "no_llm_judge": ("the cluster serves exactly two text models and both are arms here, so a "
                             "judge would score its own output; read `samples` instead"),
            "power_caveat": ("n is small and drawn from one book, unstratified — quote the per-chunk "
                             "distributions, and treat any difference inside the spread as unresolved"),
            "ran_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        },
        "arms": arms,
        "samples": samples,
        "per_call": {m: [{k: v for k, v in r.items() if k != "raw_content"} for r in rs]
                     for m, rs in records.items()},
    }
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(
        json.dumps(out, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"\nwrote {args.out}")
    for m, a in arms.items():
        print(f"  {m}: concepts/chunk mean {a['concepts']['mean']} "
              f"(band {a['concepts']['within_prompt_band_3_7']}/{a['n_ok']}), "
              f"latency p50 {a['latency_s']['p50']}s, "
              f"vocab overlap {a['names']['in_graph_vocabulary_pct']}%")
    return 0


if __name__ == "__main__":
    logger.remove()
    logger.add(sys.stderr, level="WARNING")
    raise SystemExit(main())
