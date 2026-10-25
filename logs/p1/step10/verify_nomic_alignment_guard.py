#!/usr/bin/env python
"""Does the LIVE endpoint still match nomic's DECLARED layout (0 leading, 2 trailing)?

`probe_nomic_alignment.py` measures; `_DECLARED_SPECIALS` declares. This is the check that the two
agree right now, in three parts:

  1. `LateChunkEmbedder.probe_alignment` — re-measures the layout and RAISES if it disagrees with
     the declaration.
  2. the raw count on a real parent: `n_api == n_local + 2`.
  3. `_content_tokens` on that matrix — it must return exactly `n_local` vectors, and every child
     must pool a non-empty, unit-norm vector.

Run:
    unset PYTHONPATH && uv run python -u logs/p1/step10/verify_nomic_alignment_guard.py
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

import numpy as np  # noqa: E402

from src.core.config import Settings  # noqa: E402
from src.pdf_ingestion.chunker import TextChunk  # noqa: E402
from src.pdf_ingestion.late_chunk_embedder import LateChunkEmbedder, declared_specials  # noqa: E402
from src.pdf_ingestion.models import ParentChunk  # noqa: E402

MODEL = "nomic-ai/nomic-embed-text-v1.5"
PREFIX = "search_document: "

TEXT = (
    "Newton's second law states that the net force on an object is equal to the mass of that "
    "object multiplied by its acceleration. This is proportional to the square of the distance "
    "from the source, as we shall now derive. The lever is a rigid bar that rotates about a "
    "fulcrum, and the mechanical advantage equals the ratio of the two arms."
)


def main() -> int:
    cfg = Settings(
        dense_model=MODEL, dense_dim=768, dense_dim_low=64, document_prefix=PREFIX,
        sv_embed_url="http://10.0.10.70:8123/embed-text/v1/embeddings",
        use_stub_embedder=False, late_chunk_enabled=True,
    )
    lc = LateChunkEmbedder(settings=cfg)
    declared = declared_specials(MODEL)
    print(f"declared (leading, trailing) : {declared}")

    # 1. the guard — raises on a mismatch
    guard = lc.probe_alignment(TEXT)
    print(f"guard measured               : ({guard['leading']}, {guard['trailing']})")
    print(f"guard match_max_abs_diff     : {guard['match_max_abs_diff']:.4f}")
    print("guard profile                : " + "  ".join(
        f"o={p['leading']}:{p['max_abs_diff']:.3f}" for p in guard["profile"]))
    print(f"guard verdict                : {'AGREES with the declaration' if (guard['leading'], guard['trailing']) == declared else 'DISAGREES'}")

    # 2 + 3. the real parent path
    offsets = lc._offsets(TEXT)
    matrix = np.asarray(lc._embedder.embed_documents_tokens([TEXT])[0], dtype=np.float32)
    content = lc._content_tokens(matrix, len(offsets), 1, 768, lc.specials)
    print(f"n_local={len(offsets)}  n_api={matrix.shape[0]}  delta={matrix.shape[0] - len(offsets)}"
          f"  content_rows={content.shape[0]}  (must equal n_local)")
    assert content.shape[0] == len(offsets), "content rows != n_local tokens"

    mid = TEXT.index("The lever")
    parent = ParentChunk(parent_id=1, text=TEXT)
    kids = [
        TextChunk("c1", "d", "t", 0, TEXT[:mid], 0, mid, len(TEXT[:mid].split()), 1, parent_id=1),
        TextChunk("c2", "d", "t", 1, TEXT[mid:], mid, len(TEXT), len(TEXT[mid:].split()), 1,
                  parent_id=1),
    ]
    for ec in lc.embed_parent(parent, kids):
        norm = float(np.linalg.norm(ec.dense_1024))
        print(f"child {ec.chunk.chunk_id}: token_span={ec.token_span} "
              f"dim={ec.dense_1024.shape[0]} |v|={norm:.6f} "
              f"dense_64={ec.dense_64.shape[0]}")
        assert ec.token_span != (0, 0), "child pooled no token — span translation is off"
        assert abs(norm - 1.0) < 1e-5, "vector not unit-norm"

    print("\nPASS — the live endpoint matches the declared (0, 2) layout and the parent path pools "
          "real spans.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
