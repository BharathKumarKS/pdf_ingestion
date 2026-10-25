#!/usr/bin/env python
"""C0's follow-up: quantify the two failures C0 found, so Shape B can be re-decided on numbers.

C0 (`c0_late_chunk_timing.py`) could not complete a single parent under gemma. Two independent
problems, both structural rather than incidental:

1. **The token-alignment contract is off-by-TWO for gemma, not off-by-one.** Every parent showed
   `n_api == n_local + 2` (49->51, 269->271, 601->603, ...). `LateChunkEmbedder._content_tokens`
   accepts `n_api == n_local` or `n_api == n_local + 1` (Qwen3 appends one trailing `<|endoftext|>`)
   and RAISES otherwise — which is why all 20 parents failed loudly instead of silently shifting
   every span by one or two tokens. This probe tests the hypothesis that the two extra vectors are
   gemma's `<bos>` and `<eos>` (i.e. `matrix[1:-1]` is the content), using the LOCAL tokenizer only.

2. **The gemma endpoint truncates at 2048 tokens.** Parents 16 and 19 produced 4653 / 4221 local
   tokens against 2048 returned vectors, with the library warning *"sequence length is longer than
   the specified maximum sequence length (4653 > 2048) ... will result in indexing errors"*. A
   parent longer than the model's window has NO token vectors past 2048, so late chunking over the
   whole parent is impossible for it — a limit of the model, not of the code.

This probe answers, offline (tokenizer only, no cluster calls, no writes):
  * is the +2 exactly `<bos>` + `<eos>`?  -> is `matrix[1:-1]` the right content rule?
  * how many of the 341 parents exceed 2048 tokens, and how many CHILDREN does that expose —
    split into: fully inside the window, straddling the boundary, and entirely beyond it?

The last number is the one that sizes the decision: a child entirely beyond 2048 cannot be
late-chunked at all and must fall back to an isolated embedding (the E3 control), which changes
what Shape B's index would actually contain.

Run:
    unset PYTHONPATH && export QDRANT_HOST=10.0.10.65 QDRANT_COLLECTION=knowledge_base_v2
    uv run python -u logs/p1/step10/c0_gemma_alignment_and_truncation.py
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

from src.core.config import get_settings  # noqa: E402

DOC_PREFIX = "7ba61432"
MAX_SEQ = 2048          # the gemma endpoint's window, measured by C0
OUT = REPO / "logs" / "p1" / "step10" / "c0_gemma_alignment_and_truncation.json"


def scroll_all(client, collection: str, doc_prefix: str) -> list[dict]:
    out: list[dict] = []
    offset = None
    while True:
        points, offset = client.scroll(collection_name=collection, limit=512, offset=offset,
                                       with_payload=True, with_vectors=False)
        for p in points:
            pl = p.payload or {}
            if str(pl.get("document_id", "")).startswith(doc_prefix):
                out.append({"id": str(p.id), **pl})
        if offset is None:
            break
    return out


def main() -> int:
    cfg = get_settings()
    print(f"resolved: dense_model={cfg.dense_model!r} dim={cfg.dense_dim}")
    if "gemma" not in cfg.dense_model:
        print("ABORT: this probe is about the gemma tokenizer", file=sys.stderr)
        return 2

    from qdrant_client import QdrantClient
    from transformers import AutoTokenizer

    tok = AutoTokenizer.from_pretrained(cfg.dense_model, cache_dir=cfg.model_cache_dir)

    client = QdrantClient(host=cfg.qdrant_host, port=cfg.qdrant_port)
    rows = scroll_all(client, cfg.qdrant_collection, DOC_PREFIX)

    by_parent: dict[int, list[dict]] = defaultdict(list)
    for r in rows:
        if r.get("parent_id") is not None:
            by_parent[int(r["parent_id"])].append(r)

    # ── 1. The alignment rule ────────────────────────────────────────────────
    sample = rows[0]["parent_text"] if rows else "what is kinetic energy"
    no_special = len(tok(sample, add_special_tokens=False)["input_ids"])
    with_special = len(tok(sample, add_special_tokens=True)["input_ids"])
    print("\n--- 1. the alignment rule ---")
    print(f"  add_special_tokens=False -> {no_special} tokens")
    print(f"  add_special_tokens=True  -> {with_special} tokens  (delta {with_special - no_special})")
    rule_holds = (with_special - no_special) == 2
    print(f"  ⇒ the +2 IS <bos>+<eos>: {rule_holds}  (content matrix = matrix[1:-1])")

    # ── 2. The 2048-token exposure ───────────────────────────────────────────
    print("\n--- 2. the 2048-token window ---")
    per_parent = []
    kids_inside = kids_straddle = kids_beyond = 0
    over = []
    for pid, group in sorted(by_parent.items()):
        group.sort(key=lambda r: int(r["chunk_index"]))
        text = group[0]["parent_text"] or ""
        offsets = tok(text, add_special_tokens=False,
                      return_offsets_mapping=True)["offset_mapping"]
        n = len(offsets)
        # The first MAX_SEQ tokens are the only ones with vectors. A child's span overlaps a set
        # of token indices; classify by where those indices fall relative to MAX_SEQ.
        row = {"parent_id": pid, "tokens": n, "children": len(group),
               "inside": 0, "straddle": 0, "beyond": 0}
        if n > MAX_SEQ:
            over.append(pid)
        for r in group:
            start, end = int(r["char_start"]), int(r["char_end"])
            idx = [i for i, (ts, te) in enumerate(offsets) if te > start and ts < end]
            if not idx:
                row["beyond"] += 1            # overlaps no token at all
            elif idx[-1] < MAX_SEQ:
                row["inside"] += 1
            elif idx[0] >= MAX_SEQ:
                row["beyond"] += 1
            else:
                row["straddle"] += 1
        kids_inside += row["inside"]
        kids_straddle += row["straddle"]
        kids_beyond += row["beyond"]
        per_parent.append(row)

    total_children = sum(r["children"] for r in per_parent)
    print(f"  parents                 : {len(per_parent)}")
    print(f"  parents OVER {MAX_SEQ} tokens : {len(over)}  ({100*len(over)/max(1,len(per_parent)):.1f}%)")
    print(f"  children total          : {total_children}")
    print(f"    fully inside window   : {kids_inside}  ({100*kids_inside/max(1,total_children):.1f}%)")
    print(f"    straddling the cutoff : {kids_straddle}  ({100*kids_straddle/max(1,total_children):.1f}%)")
    print(f"    ENTIRELY beyond       : {kids_beyond}  ({100*kids_beyond/max(1,total_children):.1f}%)")

    report = {
        "stage": "C0-followup", "dense_model": cfg.dense_model, "max_seq": MAX_SEQ,
        "alignment": {"no_special": no_special, "with_special": with_special,
                      "delta": with_special - no_special, "is_bos_plus_eos": rule_holds},
        "parents": len(per_parent), "parents_over_window": len(over),
        "over_window_parent_ids": over,
        "children": {"total": total_children, "inside": kids_inside,
                     "straddle": kids_straddle, "beyond": kids_beyond},
        "per_parent": per_parent,
    }
    OUT.write_text(json.dumps(report, indent=2))
    print(f"\nwrote {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
