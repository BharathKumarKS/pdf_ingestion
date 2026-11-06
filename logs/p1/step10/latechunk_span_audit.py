"""H1 vs H2 — does a nomic child's LATE-CHUNKED vector equal an INDEPENDENT span-pooling?

WHY. §I87 measured late chunking costing nomic **+0.1547** full-dim coverage (RESOLVED) while being
≈neutral for qwen3 (−0.0215, unresolved) — an **interaction**, i.e. a model-specific cost. Two
hypotheses: **H1** late chunking genuinely degrades nomic; **H2** the nomic late-chunk path mis-pools
(a defect). The tell for H2 is the magnitude: stored-vs-pooled cosine is v2 0.9559 (min 0.881) but
**v3 0.8153 (min 0.502)** — a correctly pooled child sits CLOSE to pooled(child text).

WHAT IT DOES — an INDEPENDENT reimplementation of the span math, not a call to `LateChunkEmbedder`:
  1. offsets: is `parent_text[char_start:char_end] == text`? (a pure offset bug shows up here)
  2. tokenize the PREFIXED parent locally (offsets), shift the child's char span by `len(prefix)`
  3. fetch the endpoint's per-token vectors for the prefixed parent, drop the declared (0,2) specials
  4. mean-pool the token vectors inside the child's span, L2-normalise -> the MANUAL vector
  5. cos(MANUAL, STORED) per child.

READING: cos ~ 1.0  -> the shipped path reproduces an independent span-pooling -> **H1**.
         cos << 1.0 -> the shipped path deviates from it -> **H2 (a defect)**.
Also reported: cos(STored, POOLED(child text)) — the same number §I87 measured, as a cross-check.

READ-ONLY. No writes, no LLM (endpoint embeddings only).
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

import numpy as np  # noqa: E402
from loguru import logger  # noqa: E402
from qdrant_client.models import FieldCondition, Filter, MatchValue  # noqa: E402

from src.core.config import get_settings  # noqa: E402
from src.pdf_ingestion.cluster_embedder import ClusterDenseEmbedder  # noqa: E402
from src.pdf_ingestion.late_chunk_embedder import LateChunkEmbedder, declared_specials  # noqa: E402

OUT = "logs/p1/step10/latechunk_span_audit.json"
NOMIC = "nomic-ai/nomic-embed-text-v1.5"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=OUT)
    ap.add_argument("--parents", type=int, default=6)
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()
    if Path(args.out).exists() and not args.force:
        print(f"REFUSING to overwrite {args.out} without --force.", file=sys.stderr)
        return 4

    cfg = get_settings()
    if cfg.qdrant_collection != "knowledge_base_v3":
        print("ABORT: run with QDRANT_COLLECTION=knowledge_base_v3.", file=sys.stderr)
        return 3
    if cfg.dense_model != NOMIC:
        print(f"ABORT: DENSE_MODEL must be {NOMIC}, got {cfg.dense_model!r}.", file=sys.stderr)
        return 3

    from src.core.database import get_qdrant
    client = get_qdrant(cfg)

    # base_textbook children with a parent
    flt = Filter(must=[FieldCondition(key="source_type", match=MatchValue(value="base_textbook"))])
    pts, _ = client.scroll(collection_name=cfg.qdrant_collection, scroll_filter=flt, limit=4000,
                           with_payload=True, with_vectors=["dense_full"])
    children = []
    for p in pts:
        pl = p.payload or {}
        if not pl.get("parent_text") or pl.get("char_start") is None or pl.get("char_end") is None:
            continue
        v = p.vector["dense_full"] if isinstance(p.vector, dict) else p.vector
        children.append({"parent_id": pl.get("parent_id"), "parent_text": pl["parent_text"],
                         "char_start": int(pl["char_start"]), "char_end": int(pl["char_end"]),
                         "text": pl.get("text", "") or "", "stored": np.asarray(v, dtype=np.float64)})
    logger.info("children with parent span: {}", len(children))
    by_parent: dict = {}
    for c in children:
        by_parent.setdefault(c["parent_id"], []).append(c)
    parents = [pid for pid, cs in by_parent.items() if len(cs) >= 2][: args.parents]
    logger.info("auditing {} parents", len(parents))

    embedder = ClusterDenseEmbedder(cfg)
    tok = LateChunkEmbedder(cfg)._get_tokenizer()  # noqa: SLF001  (the tokenizer is a fact; the SPAN math below is mine)
    lead, trail = declared_specials(cfg.dense_model)
    prefix = cfg.document_prefix
    logger.info("declared specials for {}: leading={} trailing={}; prefix={!r}",
                cfg.dense_model, lead, trail, prefix)

    rows = []
    for pid in parents:
        ptext = by_parent[pid][0]["parent_text"]
        prefixed = prefix + ptext
        enc = tok(prefixed, add_special_tokens=False, return_offsets_mapping=True)
        offs = enc["offset_mapping"]
        ids = enc["input_ids"]
        matrix = embedder.embed_documents_tokens([ptext])[0]   # (n_api, dim) — prefixed internally
        n_local = len(ids)
        # the declared alignment: the endpoint wraps the input; keep the n_local content vectors
        if lead:
            matrix = matrix[lead:]
        if trail:
            matrix = matrix[: len(matrix) - trail]
        align_ok = len(matrix) == n_local
        for c in by_parent[pid]:
            cs, ce = c["char_start"] + len(prefix), c["char_end"] + len(prefix)
            # tokens whose span lies inside the child's span
            sel = [i for i, (a, b) in enumerate(offs) if a >= cs and b <= ce and b > a]
            manual = None
            if sel and align_ok:
                vec = matrix[sel].mean(axis=0)
                manual = vec / (np.linalg.norm(vec) + 1e-12)
            stored = c["stored"] / (np.linalg.norm(c["stored"]) + 1e-12)
            cos = float(np.dot(manual, stored)) if manual is not None else None
            rows.append({
                "parent_id": pid, "n_children_in_parent": len(by_parent[pid]),
                "offset_exact": ptext[c["char_start"]:c["char_end"]] == c["text"],
                "n_tokens_selected": len(sel), "n_local_tokens": n_local,
                "align_ok": align_ok, "cos_manual_vs_stored": cos,
            })
        if len(rows) >= 120:
            break

    off_ok = sum(1 for r in rows if r["offset_exact"])
    align_ok = sum(1 for r in rows if r["align_ok"])
    coss = [r["cos_manual_vs_stored"] for r in rows if r["cos_manual_vs_stored"] is not None]
    art = {
        "meta": {"question": "does a nomic child's late-chunked vector equal an independent span-pooling?",
                 "collection": cfg.qdrant_collection, "model": cfg.dense_model,
                 "declared_specials": {"leading": lead, "trailing": trail}, "prefix": prefix,
                 "n_rows": len(rows), "n_parents": len(parents), "no_writes": True, "no_llm": True},
        "summary": {
            "offset_exact_all": off_ok == len(rows), "offset_exact_n": off_ok,
            "align_ok_n": align_ok,
            "cos_manual_vs_stored": {"n": len(coss),
                                     "mean": round(statistics.mean(coss), 6) if coss else None,
                                     "min": round(min(coss), 6) if coss else None,
                                     "median": round(statistics.median(coss), 6) if coss else None,
                                     "n_below_0.99": sum(1 for c in coss if c < 0.99),
                                     "n_below_0.90": sum(1 for c in coss if c < 0.90)},
            "verdict_hint": ("H1 (shipped path reproduces an independent span-pooling)"
                             if coss and statistics.mean(coss) >= 0.99 else
                             "H2 (shipped path DEVIATES from an independent span-pooling)"),
        },
        "rows": rows,
    }
    Path(args.out).write_text(json.dumps(art, indent=2))
    print(json.dumps(art["meta"], indent=2))
    print(json.dumps(art["summary"], indent=2))
    print(f"\nartifact: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
