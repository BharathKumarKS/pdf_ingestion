#!/usr/bin/env python
"""PROBE — can the E1 chunking be reproduced from the STORED payloads, with no re-parse?

Why this probe exists
---------------------
Arm 2 of the chunking question varies `min_chunk_tokens` (pre-registration §5, committed
`aa4b55b`). That knob changes only **how a parent's text is cut into children** — see
`chunker.SemanticChunker._chunk_one_parent`: it merges a micro-chunk into the previous
child of the SAME parent and never crosses a parent boundary. The knob does not touch the
parse, the parents, or the parent→page provenance.

Every chunk payload in `knowledge_base_v2` carries `parent_id` and `parent_text`. So if
re-running `SemanticChunker` over parents **reconstructed from the payloads** reproduces the
stored children EXACTLY, then arm 2 needs **no Docling re-parse** (the 968-page PDF parse is
the expensive half of the ingest). If it does not reproduce, arm 2 needs a re-parse and its
cost is a different order.

What is compared
----------------
Per parent, the children this probe cuts vs the children actually stored:
  * count
  * each child's (char_start, char_end, token_count, text) in order
`chunk_id` is `uuid4()` at ingest and is expected to differ — it is excluded.

⚠️ Fidelity limit, recorded rather than hidden: `ParentChunk.page_map` is NOT stored. It is
reconstructed here as `{stored_child.char_start: stored_child.page_number}` for the parent's
stored children, so the reconstructed map is only as fine as the child starts. That is
sufficient for THIS probe (which compares boundaries at the current `min_chunk_tokens`), but
it is an approximation of the true element-level provenance map and is flagged as such.

⚠️ READ-ONLY: no writes to any collection, no LLM calls, no re-embed.

Run:
    unset PYTHONPATH && export QDRANT_HOST=10.0.10.65 QDRANT_COLLECTION=knowledge_base_v2
    uv run python -u logs/p1/step10/rechunk_from_payload_probe.py
"""
from __future__ import annotations

import hashlib
import json
import sys
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

from src.core.config import get_settings  # noqa: E402
from src.pdf_ingestion.chunker import SemanticChunker  # noqa: E402
from src.pdf_ingestion.models import ParentChunk  # noqa: E402

DOC_PREFIX = "7ba61432"
OUT = REPO / "logs" / "p1" / "step10" / "rechunk_from_payload_probe.json"


def scroll_all(client, collection: str, doc_prefix: str) -> list[dict]:
    """Every point whose `document_id` starts with `doc_prefix` (full payload, no vector)."""
    out: list[dict] = []
    offset = None
    while True:
        points, offset = client.scroll(
            collection_name=collection,
            limit=512,
            offset=offset,
            with_payload=True,
            with_vectors=False,
        )
        for p in points:
            pl = p.payload or {}
            did = str(pl.get("document_id", ""))
            if did.startswith(doc_prefix):
                out.append({"id": str(p.id), **pl})
        if offset is None:
            break
    return out


def main() -> int:
    cfg = get_settings()
    from qdrant_client import QdrantClient

    host = cfg.qdrant_host or "localhost"
    client = QdrantClient(host=host, port=cfg.qdrant_port)
    collection = cfg.qdrant_collection
    print(f"store: {host}:{cfg.qdrant_port} collection={collection}")
    assert host == "10.0.10.65", f"resolved store is not the remote one: {host}"

    all_rows = scroll_all(client, collection, DOC_PREFIX)
    if not all_rows:
        print("FATAL: no chunks found for the document prefix")
        return 2
    # The collection is chunks + RAPTOR summary nodes (§I43: 3,796 + 73 = 3,869). Only the
    # chunks carry `parent_id`; the RAPTOR nodes have neither `parent_id` nor `is_content`.
    rows = [r for r in all_rows if r.get("parent_id") is not None]
    raptor = [r for r in all_rows if r.get("parent_id") is None]
    doc_ids = {str(r["document_id"]) for r in rows}
    print(f"points for the document: {len(all_rows)}  chunks (parent_id present): {len(rows)}  "
          f"non-chunk (RAPTOR summary nodes): {len(raptor)}")
    print(f"chunks: {len(rows)}  document_id(s): {sorted(doc_ids)}")
    print(f"stored is_content values: {dict(_count(r.get('is_content') for r in rows))}")
    if raptor:
        print(f"  non-chunk keys: {sorted(raptor[0].keys())[:14]}")

    by_parent: dict[int, list[dict]] = defaultdict(list)
    for r in rows:
        by_parent[int(r["parent_id"])].append(r)

    # -- reconstruct parents from the payloads ---------------------------------
    parents: list[ParentChunk] = []
    parent_texts: dict[int, str] = {}
    inconsistent: list[int] = []
    for pid, group in sorted(by_parent.items()):
        group.sort(key=lambda r: int(r["chunk_index"]))
        texts = {str(r["parent_text"]) for r in group}
        if len(texts) != 1:
            inconsistent.append(pid)
        text = str(group[0]["parent_text"])
        parent_texts[pid] = text
        page_map = {int(r["char_start"]): int(r["page_number"]) for r in group
                    if r.get("page_number") is not None and r.get("char_start") is not None}
        parents.append(ParentChunk(parent_id=pid, text=text, page_map=page_map))

    print(f"parents reconstructed: {len(parents)}  "
          f"parents with >1 distinct parent_text: {len(inconsistent)}")

    # -- re-cut with the SHIPPED settings --------------------------------------
    chunker = SemanticChunker(settings=cfg)
    print(f"shipped settings: min_chunk_tokens={cfg.min_chunk_tokens} "
          f"semantic_threshold={cfg.semantic_threshold} chunk_size={cfg.chunk_size}")
    new_chunks = chunker.chunk_parents(sorted(doc_ids)[0], "global", parents)

    new_by_parent: dict[int, list] = defaultdict(list)
    for c in new_chunks:
        new_by_parent[int(c.parent_id)].append(c)

    # -- compare, per parent ---------------------------------------------------
    n_match = n_diff = 0
    first_diffs: list[dict] = []
    total_stored = total_new = 0
    for pid, group in sorted(by_parent.items()):
        stored = [(int(r["char_start"]), int(r["char_end"]), str(r["text"])) for r in group]
        made = [(int(c.char_start), int(c.char_end), c.text) for c in new_by_parent.get(pid, [])]
        total_stored += len(stored)
        total_new += len(made)
        if stored == made:
            n_match += 1
            continue
        n_diff += 1
        if len(first_diffs) < 5:
            first_diffs.append({
                "parent_id": pid,
                "stored_n": len(stored), "new_n": len(made),
                "stored_head": [s[:2] for s in stored[:4]],
                "new_head": [m[:2] for m in made[:4]],
                "first_text_mismatch": _first_text_mismatch(stored, made),
            })

    print(f"\nparents identical: {n_match}   differing: {n_diff}")
    print(f"children stored {total_stored} -> re-cut {total_new}")
    for d in first_diffs:
        print(f"  parent {d['parent_id']}: stored {d['stored_n']} vs new {d['new_n']} | "
              f"first text mismatch at {d['first_text_mismatch']}")

    verdict = (n_diff == 0 and total_stored == total_new)
    print("\nVERDICT:",
          "REPRODUCED — arm 2 needs NO re-parse (parents recoverable from payloads)"
          if verdict else
          "NOT REPRODUCED — arm 2 needs a Docling re-parse (or the difference explained)")

    # -- what the knob actually does: raw chonkie count vs merged ---------------
    from chonkie import SemanticChunker as ChonkieSemanticChunker
    raw = ChonkieSemanticChunker(threshold=cfg.semantic_threshold, chunk_size=cfg.chunk_size)
    raw_counts = {pid: len(raw.chunk(p.text)) for pid, p in
                  ((p.parent_id, p) for p in parents)}
    print(f"\nraw chonkie children (no merge): {sum(raw_counts.values())}  "
          f"vs stored {total_stored}  "
          f"(merge removes {sum(raw_counts.values()) - total_stored})")

    artifact = {
        "probe": "rechunk_from_payload_probe",
        "store": {"host": host, "port": cfg.qdrant_port, "collection": collection},
        "document_id": sorted(doc_ids),
        "chunks_stored": len(rows),
        "stored_is_content": dict(_count(r.get("is_content") for r in rows)),
        "settings": {
            "min_chunk_tokens": cfg.min_chunk_tokens,
            "semantic_threshold": cfg.semantic_threshold,
            "chunk_size": cfg.chunk_size,
        },
        "parents_reconstructed": len(parents),
        "parents_with_inconsistent_parent_text": len(inconsistent),
        "parents_identical": n_match,
        "parents_differing": n_diff,
        "children_stored": total_stored,
        "children_recut": total_new,
        "children_raw_chonkie_no_merge": sum(raw_counts.values()),
        "reproduced": bool(verdict),
        "first_diffs": first_diffs,
        "page_map_caveat": ("ParentChunk.page_map is not stored; reconstructed from the "
                            "stored children's (char_start, page_number) pairs, so it is only "
                            "as fine as the child starts — an approximation of the true "
                            "element-level provenance map."),
    }
    OUT.write_text(json.dumps(artifact, indent=2) + "\n", encoding="utf-8")
    print(f"\nartifact: {OUT}  sha256 {hashlib.sha256(OUT.read_bytes()).hexdigest()[:16]}…")
    return 0 if verdict else 1


def _count(iterable):
    from collections import Counter
    return Counter(iterable)


def _first_text_mismatch(stored, made):
    for i, (s, m) in enumerate(zip(stored, made)):
        if s[2] != m[2]:
            return {"index": i, "stored_len": len(s[2]), "new_len": len(m[2])}
    return None if len(stored) == len(made) else "length differs"


if __name__ == "__main__":
    raise SystemExit(main())
