#!/usr/bin/env python
"""Does NOMIC avoid the two defects §I77 found in gemma's late-chunk path?

§I77: gemma (a) appends TWO special tokens (`<bos>`+`<eos>`), so `_content_tokens`'s Qwen3-era
contract (`n_api == n_local + 1`) raises on every parent; and (b) the endpoint TRUNCATES at 2048
tokens, which strands 351 of 3,796 children (9.2 %) — 281 entirely beyond the window.

Both are properties of the **model + endpoint pairing**, not of the code, so they must be measured
per candidate. This probe answers, for nomic-embed-text-v1.5, on the SAME input gemma failed on:

  1. what does the endpoint return for the longest stored parent — n_local + 0 / +1 / +2?
  2. does the endpoint truncate, and at what token count?

⚠️ Read-only: no writes, no LLM calls, no re-parse. The only traffic is the per-token POST and the
tokenizer load (nomic is ungated).

⚠️ §I62 applies and is NOT what this probe tests: the cluster serves nomic but does not apply its
task prefixes. Prefixes do not change the token COUNT of the content, so they do not affect the
alignment question — but do not read anything here as a statement about prefix behaviour.

Run:
    unset PYTHONPATH && export QDRANT_HOST=10.0.10.65 QDRANT_COLLECTION=knowledge_base_v2
    uv run python -u logs/p1/step10/nomic_window_and_alignment.py
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

from src.core.config import get_settings  # noqa: E402
from src.pdf_ingestion.cluster_embedder import get_cluster_embedder  # noqa: E402

DOC_PREFIX = "7ba61432"
MODEL = "nomic-ai/nomic-embed-text-v1.5"
OUT = REPO / "logs" / "p1" / "step10" / "nomic_window_and_alignment.json"


def main() -> int:
    from qdrant_client import QdrantClient
    from transformers import AutoTokenizer

    cfg = get_settings()
    nomic_cfg = cfg.model_copy(update={"dense_model": MODEL, "dense_dim": 768})
    print(f"resolved: dense_model={nomic_cfg.dense_model!r} dim={nomic_cfg.dense_dim}")

    tok = AutoTokenizer.from_pretrained(MODEL, cache_dir=cfg.model_cache_dir)
    declared = getattr(tok, "model_max_length", None)
    print(f"tokenizer model_max_length: {declared}")

    # The longest stored parent — the same input gemma failed on.
    client = QdrantClient(host=cfg.qdrant_host, port=cfg.qdrant_port)
    rows, offset = [], None
    while True:
        pts, offset = client.scroll(collection_name=cfg.qdrant_collection, limit=512,
                                    offset=offset, with_payload=True, with_vectors=False)
        for p in pts:
            pl = p.payload or {}
            if str(pl.get("document_id", "")).startswith(DOC_PREFIX) and pl.get("parent_id") is not None:
                rows.append({"id": str(p.id), **pl})
        if offset is None:
            break

    by_parent: dict[int, list[dict]] = defaultdict(list)
    for r in rows:
        by_parent[int(r["parent_id"])].append(r)

    longest_pid, longest_text = None, ""
    for pid, group in by_parent.items():
        t = group[0].get("parent_text") or ""
        if len(t) > len(longest_text):
            longest_pid, longest_text = pid, t
    print(f"longest stored parent: id={longest_pid} chars={len(longest_text)}")

    n_local = len(tok(longest_text, add_special_tokens=False)["input_ids"])
    n_special = len(tok(longest_text, add_special_tokens=True)["input_ids"])
    print(f"\ntokens (nomic tokenizer): add_special=False -> {n_local}   add_special=True -> {n_special}")

    emb = get_cluster_embedder(nomic_cfg)
    matrix = emb.embed_documents_tokens([longest_text])[0]
    import numpy as np
    m = np.asarray(matrix)
    n_api = m.shape[0]
    print(f"endpoint returned       : {n_api} vectors of dim {m.shape[1] if m.ndim == 2 else '?'}")

    delta = n_api - n_local
    print(f"\n--- verdict for nomic ---")
    print(f"  alignment delta (n_api - n_local) : {delta}")
    if delta == 0:
        print("  => nomic's contract is n_api == n_local: `_content_tokens` accepts it AS IS")
    elif delta == 1:
        print("  => n_api == n_local + 1: the EXISTING Qwen3 rule accepts it AS IS")
    else:
        print(f"  => {delta} extra: a nomic-specific rule would be needed (like gemma's +2)")

    truncated = n_api < n_local
    print(f"  truncated? {truncated}  (n_api {n_api} vs n_local {n_local})")
    print(f"  declared window: {declared}")

    report = {
        "stage": "candidate-probe", "model": MODEL, "dim": nomic_cfg.dense_dim,
        "tokenizer_model_max_length": declared,
        "longest_parent": {"parent_id": longest_pid, "chars": len(longest_text),
                           "tokens_nomic": n_local, "tokens_with_special": n_special},
        "endpoint": {"n_vectors": n_api, "dim": int(m.shape[1]) if m.ndim == 2 else None,
                     "alignment_delta": delta, "truncated": bool(truncated)},
    }
    OUT.write_text(json.dumps(report, indent=2))
    print(f"\nwrote {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
