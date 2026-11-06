"""The pooled re-embed carries `colbert` + `sparse` over from v2 and must not disturb the payload.

The Shape B write recomputes ONLY the two dense lanes; `colbert` and `sparse` are copied verbatim
(different models, unchanged vectors — plan §2). A copy is exactly the kind of step that silently
loses a lane or a payload field, so assert it against the SOURCE collection for the same chunk ids.

READ-ONLY. Compares, for a deterministic sample of chunk ids present in both collections:
  * `colbert`  — the full (n_tokens, 128) matrix, element-wise
  * `sparse`   — indices and values
  * payload    — every key v2's chunk points carry, except the ones the write is meant to change
                 (`embedding_version`)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

import numpy as np  # noqa: E402
from loguru import logger  # noqa: E402
from qdrant_client.models import FieldCondition, Filter, MatchValue, Range  # noqa: E402

from src.core.config import get_settings  # noqa: E402
from src.core.database import get_qdrant  # noqa: E402

# The write is *meant* to change these; everything else must survive byte-for-byte.
EXPECTED_CHANGES = {"embedding_version"}
DENSE_LANES = {"dense_full", "dense_64", "dense_1024", "dense_768", "dense_128"}


def flt(cfg) -> Filter:
    must_not = [FieldCondition(key="source_type", match=MatchValue(value="raptor_summary"))]
    must_not.append(FieldCondition(key="page_number", range=Range(lt=cfg.min_content_page)))
    must_not.append(FieldCondition(key="page_number", range=Range(gt=cfg.max_content_page)))
    must_not.append(FieldCondition(key="is_content", match=MatchValue(value=False)))
    return Filter(must_not=must_not)


def scroll_by_chunk_id(client, name, cfg) -> dict:
    out: dict = {}
    offset = None
    while True:
        batch, offset = client.scroll(
            collection_name=name, scroll_filter=flt(cfg), limit=500, offset=offset,
            with_payload=True, with_vectors=True,
        )
        for p in batch:
            cid = (p.payload or {}).get("chunk_id")
            if cid:
                out[cid] = p
        if offset is None:
            break
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", type=int, default=120)
    ap.add_argument("--out", default="logs/p1/step10/pooled_reembed_carryover.json")
    args = ap.parse_args()

    cfg = get_settings()
    client = get_qdrant(cfg)
    v2 = scroll_by_chunk_id(client, "knowledge_base_v2", cfg)
    v3 = scroll_by_chunk_id(client, "knowledge_base_v3", cfg)
    logger.info("v2 chunk points: {}, v3 chunk points: {}", len(v2), len(v3))

    shared = sorted(set(v2) & set(v3))
    if len(shared) != len(v3):
        print(f"ABORT: v3 has {len(v3) - len(shared)} chunk ids absent from v2", file=sys.stderr)
        return 3
    step = max(1, len(shared) // args.sample)
    sample = shared[::step][:args.sample]

    colbert_bad, sparse_bad, payload_bad = [], [], []
    checked_lanes = {"colbert": 0, "sparse": 0}
    for cid in sample:
        a, b = v2[cid], v3[cid]
        av, bv = a.vector or {}, b.vector or {}
        if "colbert" in av:
            checked_lanes["colbert"] += 1
            if not np.array_equal(np.asarray(av["colbert"]), np.asarray(bv.get("colbert"))):
                colbert_bad.append(cid)
        if "sparse" in av:
            checked_lanes["sparse"] += 1
            sa, sb = av["sparse"], bv.get("sparse")
            if sa is None or sb is None or list(sa.indices) != list(sb.indices) \
                    or not np.allclose(list(sa.values), list(sb.values)):
                sparse_bad.append(cid)
        pa, pb = dict(a.payload or {}), dict(b.payload or {})
        keys = set(pa) - EXPECTED_CHANGES
        diff = sorted(k for k in keys if pa.get(k) != pb.get(k))
        missing = sorted(k for k in keys if k not in pb)
        if diff or missing:
            payload_bad.append({"chunk_id": cid, "differing": diff, "missing": missing})

    art = {
        "meta": {"sampled": len(sample), "v2_chunk_points": len(v2), "v3_chunk_points": len(v3),
                 "shared_chunk_ids": len(shared), "expected_changes": sorted(EXPECTED_CHANGES),
                 "no_writes": True, "no_llm": True},
        "checked_lanes": checked_lanes,
        "colbert_mismatches": colbert_bad,
        "sparse_mismatches": sparse_bad,
        "payload_mismatches": payload_bad[:20],
        "guards": {
            "G1_v3_chunk_ids_subset_of_v2": len(shared) == len(v3),
            "G2_colbert_identical_on_every_sampled_chunk":
                not colbert_bad and checked_lanes["colbert"] == len(sample),
            "G3_sparse_identical_on_every_sampled_chunk":
                not sparse_bad and checked_lanes["sparse"] == len(sample),
            "G4_payload_unchanged_except_embedding_version": not payload_bad,
        },
    }
    out = Path(args.out)
    out.write_text(json.dumps(art, indent=2))
    print(json.dumps(art, indent=2))
    print(f"\nartifact: {out}\nsha256: {hashlib.sha256(out.read_bytes()).hexdigest()}")
    failed = [k for k, v in art["guards"].items() if v is False]
    print("ALL GUARDS PASS" if not failed else "GUARD FAILURE: " + ", ".join(failed))
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
