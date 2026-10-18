#!/usr/bin/env python3
"""Step 8 pre-flight: the two LOCALLY-loaded vector lanes.

Why this probe exists: `DocumentStore.save_document` wraps both SPLADE and ColBERT
in `try/except Exception -> logger.warning(..., falling back to dense-only)`. So a
missing model or a failed download does NOT fail the ingest — it writes points with
no `sparse` / no `colbert` vector and the run still reports success. The index would
then be silently incomplete, and the hybrid-search lane quietly empty.

This probe makes that failure loud BEFORE the 968-page run: it resolves each factory,
prints which implementation was chosen, and encodes real text.

Run:  uv run python logs/p1/step8/probe_embedders.py
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from src.core.config import get_settings

TEXTS = [
    "The kinetic energy of a particle is one half its mass times the square of its velocity.",
    "Quantum mechanics describes the behaviour of matter and light on the atomic scale.",
]


def main() -> int:
    cfg = get_settings()
    out: dict = {
        "splade_enabled": cfg.splade_enabled,
        "sv_sparse_url": cfg.sv_sparse_url,
        "colbert_enabled": cfg.colbert_enabled,
        "sv_colbert_url": cfg.sv_colbert_url,
        "model_cache_dir": str(cfg.model_cache_dir),
    }

    # -- SPLADE -----------------------------------------------------------------
    t0 = time.time()
    try:
        from src.pdf_ingestion.splade_embedder import get_splade_embedder
        splade = get_splade_embedder(cfg)
        vecs = splade.encode_batch(TEXTS)
        out["splade"] = {
            "class": type(splade).__name__,
            "n_vectors": len(vecs),
            "first_indices": len(vecs[0].indices),
            "first_values_nonzero": sum(1 for v in vecs[0].values if v != 0.0),
            "max_value": max(vecs[0].values) if vecs[0].values else None,
            "seconds": round(time.time() - t0, 1),
            "ok": True,
        }
    except Exception as exc:  # noqa: BLE001 - this is the whole point
        out["splade"] = {"ok": False, "error": f"{type(exc).__name__}: {exc}",
                         "seconds": round(time.time() - t0, 1)}

    # -- ColBERT ----------------------------------------------------------------
    t0 = time.time()
    try:
        from src.pdf_ingestion.colbert_embedder import get_colbert_embedder
        colbert = get_colbert_embedder(cfg)
        mats = colbert.embed_passages(TEXTS)
        out["colbert"] = {
            "class": type(colbert).__name__,
            "n_matrices": len(mats),
            "shape": list(getattr(mats[0], "shape", [])),
            "seconds": round(time.time() - t0, 1),
            "ok": True,
        }
    except Exception as exc:  # noqa: BLE001
        out["colbert"] = {"ok": False, "error": f"{type(exc).__name__}: {exc}",
                          "seconds": round(time.time() - t0, 1)}

    out["all_ok"] = bool(out["splade"].get("ok") and out["colbert"].get("ok"))
    print(json.dumps(out, indent=2))

    dest = Path(__file__).with_name("probe_embedders.json")
    dest.write_text(json.dumps(out, indent=2) + "\n")
    print(f"\nwrote {dest}")
    return 0 if out["all_ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
