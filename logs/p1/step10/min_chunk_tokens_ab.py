#!/usr/bin/env python
"""Harness to evaluate the `min_chunk_tokens` knob.

The code mirrors the pre‑registration spec and the existing probe but focuses on the three
arms described in the spec: control (min_chunk_tokens=32), T0 (0), and T16 (16).  No LLM calls,
no writes, and no PDF parsing – everything is recovered from the stored payloads.
"""

from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path

# Resolve repository root and add to sys.path
REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

# Imports from project
from src.core.config import get_settings
from src.pdf_ingestion.chunker import SemanticChunker
from src.pdf_ingestion.models import ParentChunk

DOC_PREFIX = "7ba61432"
COLLECTION = "knowledge_base_v2"


def fetch_payloads(cfg) -> list[dict]:
    """Return all payloads for the target document from Qdrant."""
    from qdrant_client import QdrantClient
    client = QdrantClient(host=cfg.qdrant_host or "localhost", port=cfg.qdrant_port)
    out: list[dict] = []
    offset = None
    while True:
        pts, offset = client.scroll(
            collection_name=COLLECTION,
            limit=512,
            offset=offset,
            with_payload=True,
            with_vectors=False,
        )
        for p in pts:
            pl = p.payload or {}
            if pl.get("document_id", "").startswith(DOC_PREFIX):
                out.append({"id": str(p.id), **pl})
        if offset is None:
            break
    return out


def build_parents(rows: list[dict]) -> list[ParentChunk]:
    by_parent: dict[int, list[dict]] = defaultdict(list)
    for r in rows:
        by_parent[int(r["parent_id"])].append(r)
    parents: list[ParentChunk] = []
    for pid, group in sorted(by_parent.items()):
        group.sort(key=lambda r: int(r["chunk_index"]))
        texts = {r["parent_text"] for r in group}
        if len(texts) > 1:
            raise ValueError(f"parent {pid} text mismatch: {texts}")
        parent_text = texts.pop()
        page_map = {
            int(r["char_start"]): int(r["page_number"]) for r in group
            if r.get("page_number") is not None and r.get("char_start") is not None
        }
        parents.append(ParentChunk(parent_id=pid, text=parent_text, page_map=page_map))
    return parents


def rechunk(parents: list[ParentChunk], min_tokens: int, cfg) -> list[ParentChunk]:
    cfg_mod = cfg.copy()
    cfg_mod.min_chunk_tokens = min_tokens
    chunker = SemanticChunker(settings=cfg_mod)
    return chunker.chunk_parents(DOC_PREFIX, "global", parents)


def main():
    cfg = get_settings()
    if cfg.qdrant_host != "10.0.10.65":
        print("ERROR: Qdrant host must be 10.0.10.65", file=sys.stderr)
        return 1
    payloads = [r for r in fetch_payloads(cfg) if r.get("parent_id") is not None]
    if not payloads:
        print("ERROR: no payloads for target document", file=sys.stderr)
        return 1
    parents = build_parents(payloads)

    EXPECTED = {"C": 3796, "T0": 5715, "T16": None}
    results = {}
    for arm, val in {"C": 32, "T0": 0, "T16": 16}.items():
        children = rechunk(parents, val, cfg)
        count = len(children)
        results[arm] = count
        print(f"arm {arm} (min_chunk_tokens={val}) produced {count} children")
    for arm, exp in EXPECTED.items():
        if exp is None:
            continue
        if results[arm] != exp:
            print(f"WARNING: arm {arm} child count differs from spec: {results[arm]} != {exp}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
