"""Step 4 — the child-size distribution at the configured ``min_chunk_tokens`` (E1 follow-up).

Plan §Step 4 asks whether ``min_chunk_tokens=32`` is still the right retrieval unit now that
children are what gets embedded and retrieved. This reports the distribution and, specifically,
how many children survive BELOW the threshold — which the merge can leave behind because it
never re-checks the accumulated size of the child it just grew.

No cluster, no embeddings: Docling parse + chonkie only.

Run:  uv run python logs/p1/step4/probe_child_units.py
Writes logs/p1/step4/child_units.json
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
TEST_BOOK = ROOT / "data" / "base_textbooks" / "test_book.pdf"


def main() -> int:
    from src.core.config import Settings
    from src.pdf_ingestion.chunker import SemanticChunker
    from src.pdf_ingestion.parent_chunker import ParentChunker

    cfg = Settings()
    _, parents = ParentChunker(cfg).convert(str(TEST_BOOK))
    children = SemanticChunker(cfg).chunk_parents("doc", "global", parents)

    counts = sorted(c.token_count for c in children)
    report = {
        "min_chunk_tokens": cfg.min_chunk_tokens,
        "parents": len(parents),
        "children": len(children),
        "token_counts": {
            "min": counts[0],
            "p25": counts[len(counts) // 4],
            "median": counts[len(counts) // 2],
            "max": counts[-1],
        },
        "children_below_threshold": sum(1 for t in counts if t < cfg.min_chunk_tokens),
        "children_below_half_threshold": sum(1 for t in counts if t * 2 < cfg.min_chunk_tokens),
        "smallest_children": [
            {"parent_id": c.parent_id, "token_count": c.token_count, "chars": len(c.text),
             "text_head": c.text[:70]}
            for c in sorted(children, key=lambda c: c.token_count)[:8]
        ],
        "note": (
            "The merge folds a child into the previous child of the same parent and never "
            "re-checks the grown child's size, so children below min_chunk_tokens survive: "
            "the first child of every parent is promoted unconditionally, and a merge can "
            "land under the threshold again."
        ),
    }
    (HERE / "child_units.json").write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
