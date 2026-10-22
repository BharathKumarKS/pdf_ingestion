#!/usr/bin/env python
"""§G3's V6 — the `concept_embeddings` sync. Read-only. 2026-10-22.

A merge that leaves the ANN index holding a name the graph no longer has re-creates §G1's measured
confound: a top-8 seed naming a concept absent from the graph (mean 3.02 of 8 did, pre-merge). This
checks, against the live collection:

  1. the alias points are GONE (`uuid5(NAMESPACE_DNS, "concept:{alias}")`);
  2. the canonical points are PRESENT;
  3. `_find_concepts_scored` still returns top-8 concepts at all (§I47's discriminator — it returned
     0 when the collection was on the wrong lane);
  4. no point in the collection names a concept that is not a live `Concept` node.

⚠️ Needs QDRANT_HOST=10.0.10.65 QDRANT_COLLECTION=knowledge_base_v2 or it inspects the LOCAL store.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import numpy as np  # noqa: E402

from src.core.config import get_settings  # noqa: E402
from src.core.database import get_memgraph, get_qdrant  # noqa: E402
from src.pdf_ingestion.entity_resolution import concept_point_id  # noqa: E402
from src.pdf_ingestion.graph_builder import GraphBuilder  # noqa: E402


def main() -> int:
    cfg = get_settings()
    journal = Path("logs/p1/step10/g3_merge_journal_2026-10-22.jsonl")
    merges = [json.loads(ln) for ln in journal.read_text(encoding="utf-8").splitlines() if ln.strip()]
    aliases = [a for m in merges for a in m["aliases"]]
    canonicals = [m["canonical"] for m in merges]
    print(f"journal: {len(merges)} merges, {len(aliases)} aliases, {len(canonicals)} canonicals")

    qdrant = get_qdrant(cfg)
    info = qdrant.get_collection(cfg.concept_collection)
    print(f"{cfg.concept_collection} on {cfg.qdrant_host}: {info.points_count:,} points "
          f"(was 7,427 pre-merge; 1,362 aliases deleted)")

    ok = True

    # 1. alias points gone
    alias_ids = [concept_point_id(a) for a in aliases]
    found_alias = qdrant.retrieve(collection_name=cfg.concept_collection, ids=alias_ids)
    v6a = len(found_alias) == 0
    ok &= v6a
    print(f"\nV6a alias points still present: {len(found_alias)} of {len(alias_ids)}  -> "
          f"{'PASS' if v6a else 'FAIL'}")
    if found_alias:
        print(f"     e.g. {[p.payload.get('name') for p in found_alias[:5]]}")

    # 2. canonical points present
    canon_ids = [concept_point_id(c) for c in canonicals]
    found_canon = qdrant.retrieve(collection_name=cfg.concept_collection, ids=canon_ids)
    missing = len(canon_ids) - len(found_canon)
    v6b = missing == 0
    ok &= v6b
    print(f"V6b canonical points MISSING: {missing} of {len(canon_ids)}  -> "
          f"{'PASS' if v6b else 'FAIL'}")

    # 3. the ANN still answers (§I47's discriminator)
    gb = GraphBuilder(cfg)
    scored = gb._find_concepts_scored(np.zeros(cfg.dense_dim, dtype="float32"), top_k=8)
    v6c = len(scored) > 0
    ok &= v6c
    print(f"V6c _find_concepts_scored(zeros) returned {len(scored)} concepts (was 8 pre-merge, "
          f"0 when on the wrong lane)  -> {'PASS' if v6c else 'FAIL'}")

    # 4. no point names a dead concept
    driver = get_memgraph(cfg)
    with driver.session() as s:
        live = {r["name"] for r in s.run("MATCH (k:Concept) RETURN k.name AS name").data()}
    orphans, offset = [], None
    while True:
        points, offset = qdrant.scroll(
            collection_name=cfg.concept_collection, limit=1000, offset=offset, with_payload=True
        )
        orphans += [p.payload.get("name") for p in points if (p.payload or {}).get("name") not in live]
        if offset is None:
            break
    v6d = len(orphans) == 0
    ok &= v6d
    print(f"V6d ANN points naming a concept ABSENT from the graph: {len(orphans)}  -> "
          f"{'PASS' if v6d else 'FAIL'}")
    if orphans:
        print(f"     e.g. {orphans[:10]}")

    print(f"\nMECHANICAL VERDICT: {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
