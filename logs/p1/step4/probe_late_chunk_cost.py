"""Step 4 — cost/unit measurement for the late-chunking pass (before committing to it).

Plan §Step 4: "Also measure before committing to it: per-token embedding cost on
`test_book.pdf` extrapolated to 968 pages (per-token output dwarfs pooled), and whether the
`min_chunk_tokens=32` merge (91→66 children on `test_book.pdf`, §E1) is still the right unit
now that children are what gets embedded and retrieved."

Measures, on the real fixture:

  * Docling parse time, parent count, child count (the E1/E2 shape)
  * per-token embedding wall time + response bytes for the whole book, pooled vs per-token
  * token-count accounting: parents are embedded (not children), so the per-token cost is
    driven by the parent text, not the child count
  * the child token-size distribution at the configured `min_chunk_tokens=32`
  * the 968-page extrapolation (linear in pages; the fixture's page count is the scale factor)

Run:  uv run python logs/p1/step4/probe_late_chunk_cost.py
Writes logs/p1/step4/cost.json and logs/p1/step4/fixture_children.json.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import httpx
import numpy as np

ROOT = Path(__file__).resolve().parents[3]
URL = "http://10.0.10.70:8123/embed-text/v1/embeddings"
MODEL = "Qwen/Qwen3-Embedding-0.6B"
CACHE = str(ROOT / "data" / "models")
TEST_BOOK = ROOT / "data" / "base_textbooks" / "test_book.pdf"
FEYNMAN_PAGES = 968
OUT = Path(__file__).resolve().parent / "cost.json"


def post(client, texts, tokens: bool):
    payload = {"model": MODEL, "input": texts}
    if tokens:
        payload["return_token_embeddings"] = True
    t0 = time.perf_counter()
    r = client.post(URL, json=payload, timeout=600)
    dt = time.perf_counter() - t0
    r.raise_for_status()
    return r.json(), dt, len(r.content)


def main() -> int:
    from transformers import AutoTokenizer

    from src.core.config import Settings
    from src.pdf_ingestion.chunker import SemanticChunker
    from src.pdf_ingestion.parent_chunker import ParentChunker

    cfg = Settings()
    tok = AutoTokenizer.from_pretrained(MODEL, cache_dir=CACHE)

    t0 = time.perf_counter()
    doc, parents = ParentChunker(cfg).convert(str(TEST_BOOK))
    parse_s = time.perf_counter() - t0

    children = SemanticChunker(cfg).chunk_parents("doc", "global", parents)
    n_pages = len(doc.pages)
    print(f"parse {parse_s:.1f}s | pages={n_pages} parents={len(parents)} "
          f"children={len(children)} (min_chunk_tokens={cfg.min_chunk_tokens})")

    (Path(__file__).resolve().parent / "fixture_children.json").write_text(
        json.dumps(
            [
                {
                    "parent_id": c.parent_id,
                    "text": c.text,
                    "char_start": c.char_start,
                    "char_end": c.char_end,
                    "page_number": c.page_number,
                }
                for c in children
            ],
            indent=2,
        )
    )

    parent_texts = [p.text for p in parents if p.text.strip()]
    parent_tokens = [len(tok(t, add_special_tokens=False)["input_ids"]) for t in parent_texts]
    total_parent_tokens = sum(parent_tokens)
    child_tokens = [c.token_count for c in children]

    report: dict = {
        "model": MODEL,
        "fixture": str(TEST_BOOK.name),
        "fixture_pages": n_pages,
        "parse_seconds": round(parse_s, 1),
        "parents": len(parents),
        "children": len(children),
        "parent_tokens_total": total_parent_tokens,
        "parent_tokens_max": max(parent_tokens),
        "child_token_counts": {
            "min": min(child_tokens),
            "median": sorted(child_tokens)[len(child_tokens) // 2],
            "max": max(child_tokens),
            "mean": round(sum(child_tokens) / len(child_tokens), 1),
            "under_64": sum(1 for t in child_tokens if t < 64),
            "under_128": sum(1 for t in child_tokens if t < 128),
        },
    }
    print(f"parent tokens total={total_parent_tokens} max={report['parent_tokens_max']}")
    print(f"child tokens: {report['child_token_counts']}")

    with httpx.Client() as client:
        # pooled (what the current ingest costs)
        _, pooled_s, pooled_bytes = post(client, parent_texts, tokens=False)
        # per-token (what late chunking costs)
        body, per_token_s, per_token_bytes = post(client, parent_texts, tokens=True)

    # token accounting from the response itself
    n_vecs = 0
    for item in body["data"]:
        arr = np.asarray(item["embedding"], dtype=np.float32)
        n_vecs += arr.shape[-2] if arr.ndim == 3 else 1

    scale = FEYNMAN_PAGES / n_pages
    report.update(
        {
            "pooled_seconds": round(pooled_s, 2),
            "pooled_response_mb": round(pooled_bytes / 1e6, 2),
            "per_token_seconds": round(per_token_s, 2),
            "per_token_response_mb": round(per_token_bytes / 1e6, 2),
            "per_token_vectors_returned": n_vecs,
            "per_token_vs_local_tokens": n_vecs - total_parent_tokens,
            "slowdown_x": round(per_token_s / pooled_s, 1) if pooled_s else None,
            "payload_x": round(per_token_bytes / pooled_bytes, 1) if pooled_bytes else None,
            "extrapolation_to_968_pages": {
                "scale_factor": round(scale, 2),
                "per_token_seconds": round(per_token_s * scale, 1),
                "per_token_response_mb": round(per_token_bytes * scale / 1e6, 1),
                "parse_seconds": round(parse_s * scale, 1),
            },
        }
    )
    print(f"pooled {pooled_s:.1f}s / {pooled_bytes/1e6:.1f} MB | "
          f"per-token {per_token_s:.1f}s / {per_token_bytes/1e6:.1f} MB "
          f"({report['slowdown_x']}x time, {report['payload_x']}x payload)")
    print(f"extrapolated to 968 pages: {report['extrapolation_to_968_pages']}")
    OUT.write_text(json.dumps(report, indent=2))
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
