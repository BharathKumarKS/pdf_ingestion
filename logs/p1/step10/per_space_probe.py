"""§A probe — the per-space query-vector fix, before/after, READ-ONLY.

Pre-registration: `.hermes/plans/2026-11-01-p1-per-space-query-vector-preregistration.md` (§1-§8,
committed ALONE as `6462145`).

Shows, on the LIVE cluster and with no writes:
  * **A1** — a **1024-dim arm** queries the 768-dim DA and graph collections: **before** the fix the
    raw call 400s (the lane's `except` then silently returned `[]`); **after** it returns N > 0.
  * **A2** — the lane's query vector is **not** the arm's dense vector (the width switched).
  * **A3** — ⚠️ the discriminating control: a **768-dim arm** (whose space already matches) is
    **bit-exact** — the store's lane result is identical to the raw call, id for id.

    python logs/p1/step10/per_space_probe.py [--ids gold-003,gold-008,gold-014]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import numpy as np  # noqa: E402

from src.core.config import get_settings  # noqa: E402
from src.core.database import get_qdrant  # noqa: E402
from src.pdf_ingestion.cluster_embedder import (  # noqa: E402
    ClusterDenseEmbedder, get_cluster_embedder, get_derived_embedder,
)
from src.pdf_ingestion.store import DocumentStore, resolve_space_query_vector  # noqa: E402

BASE = Path("logs/p1/step10")
QUERIES = "data/eval_queries_v2.json"
ARM_A_MODEL = "Qwen/Qwen3-Embedding-0.6B"      # 1024d — the arm whose space does NOT match
ARM_A_DIM = 1024


def _load(ids=None, n=3):
    raw = json.loads(Path(QUERIES).read_text())
    q = [x for x in raw if isinstance(x, dict) and str(x.get("id", "")).startswith("gold-")]
    q.sort(key=lambda x: x["id"])
    if ids:
        want = {s.strip() for s in ids.split(",") if s.strip()}
        return [x for x in q if x["id"] in want]
    return q[:n]


def _raw_ids(qdrant, collection, vec, limit=5):
    """The BEFORE path: the arm's vector handed STRAIGHT to the collection (the defect).

    ⚠️ Keyed on the payload's `chunk_id` (falling back to the point id), the SAME key the store's
    DA lane returns — comparing raw point ids against `chunk_id`s would differ by construction.
    """
    try:
        r = qdrant.query_points(collection_name=collection, query=np.asarray(vec).tolist(),
                                limit=limit, with_payload=True)
        return [str((p.payload or {}).get("chunk_id") or p.id) for p in r.points], None
    except Exception as exc:  # noqa: BLE001
        return [], f"{type(exc).__name__}: {str(exc)[:200]}"


def _lane_ids(hits):
    return [str(h.get("chunk_id") or h.get("qdrant_point_id") or h.get("id")) for h in hits]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ids", default="")
    ap.add_argument("--out", default=str(BASE / "per_space_probe.json"))
    args = ap.parse_args()

    cfg = get_settings()
    qdrant = get_qdrant(cfg)
    store = DocumentStore(cfg)
    arm_a = ClusterDenseEmbedder(settings=cfg.model_copy(
        update={"dense_model": ARM_A_MODEL, "dense_dim": ARM_A_DIM}))
    derived = get_derived_embedder(cfg)          # the 768d space the collections were built in
    arm_b = get_cluster_embedder(cfg)            # the registered arm (nomic/768 under the run env)

    rows = []
    for q in _load(args.ids):
        text = q["query"]
        v_a = np.asarray(arm_a.embed_query(text), dtype=np.float32)
        v_b = np.asarray(arm_b.embed_query(text), dtype=np.float32)
        rec = {"id": q["id"], "arm_a_dim": int(v_a.shape[0]), "arm_b_dim": int(v_b.shape[0]),
               "derived_dim": int(derived.embed_query(text).shape[0])}

        for lane, coll in (("da", cfg.da_collection), ("graph", cfg.concept_collection)):
            # BEFORE — the arm's 1024d vector straight at the 768d collection
            before_ids, before_err = _raw_ids(qdrant, coll, v_a)
            # the resolved vector (A2) and the lane's own result AFTER the fix (A1)
            resolved = resolve_space_query_vector(cfg, qdrant, v_a, text, coll, lane)
            if lane == "da":
                after_ids = _lane_ids(store.search_da(v_a, tenant_id="global", limit=5,
                                                      query_text=text))
            else:
                from src.pdf_ingestion.graph_builder import get_graph_builder
                gh = get_graph_builder(cfg).graph_search(query_text=text, tenant_id="global",
                                                         query_vector=v_a, limit=5)
                after_ids = _lane_ids(gh)
            # A3 — arm B (space already matches) must be a BIT-EXACT no-op. Two things:
            #   (a) the resolver returns the arm's OWN vector, unchanged (identity);
            #   (b) the DA lane's returned ids equal the raw call's, key for key.
            resolved_b = resolve_space_query_vector(cfg, qdrant, v_b, text, coll, lane)
            b_raw, _ = _raw_ids(qdrant, coll, v_b)
            b_store = _lane_ids(store.search_da(v_b, tenant_id="global", limit=5, query_text=text)) \
                if lane == "da" else None
            rec[lane] = {
                "before_n": len(before_ids), "before_error": before_err,
                "after_n": len(after_ids),
                "a2_width_switched": int(np.asarray(resolved).shape[0]) != int(v_a.shape[0]),
                "a3_arm_b_pass_through": resolved_b is v_b,
                "a3_da_result_identical": (b_store == b_raw) if lane == "da" else None,
                "arm_b_n": len(b_raw),
            }
        rows.append(rec)
        print(f"  {q['id']:10s} DA before={rec['da']['before_n']} after={rec['da']['after_n']} "
              f"A2={rec['da']['a2_width_switched']} A3pass={rec['da']['a3_arm_b_pass_through']} "
              f"A3ids={rec['da']['a3_da_result_identical']} | "
              f"graph before={rec['graph']['before_n']} after={rec['graph']['after_n']} "
              f"A2={rec['graph']['a2_width_switched']} A3pass={rec['graph']['a3_arm_b_pass_through']}")

    res = {
        "meta": {
            "what": "§A — the per-space query-vector fix, before/after (read-only)",
            "prereg": ".hermes/plans/2026-11-01-p1-per-space-query-vector-preregistration.md "
                      "(committed ALONE as 6462145)",
            "collection": cfg.qdrant_collection, "qdrant_host": cfg.qdrant_host,
            "da_collection": cfg.da_collection, "concept_collection": cfg.concept_collection,
            "arm_a": {"model": ARM_A_MODEL, "dim": ARM_A_DIM},
            "arm_b": {"model": cfg.dense_model, "dim": cfg.dense_dim},
            "derived": {"model": cfg.derived_dense_model, "dim": cfg.derived_dense_dim},
            "read_only": True, "n_queries": len(rows),
        },
        "summary": {
            "A1_da_nonempty_after": sum(1 for r in rows if r["da"]["after_n"] > 0),
            "A1_graph_nonempty_after": sum(1 for r in rows if r["graph"]["after_n"] > 0),
            "A1_da_empty_before": sum(1 for r in rows if r["da"]["before_n"] == 0),
            "A1_graph_empty_before": sum(1 for r in rows if r["graph"]["before_n"] == 0),
            "A2_both_lanes_switched": sum(1 for r in rows
                                          if r["da"]["a2_width_switched"]
                                          and r["graph"]["a2_width_switched"]),
            "A3_da_bit_exact": sum(1 for r in rows
                                   if r["da"]["a3_arm_b_pass_through"]
                                   and r["da"]["a3_da_result_identical"]),
            "A3_graph_pass_through": sum(1 for r in rows
                                         if r["graph"]["a3_arm_b_pass_through"]),
        },
        "per_query": rows,
    }
    Path(args.out).write_text(json.dumps(res, indent=1, sort_keys=True))
    print(f"\nwrote {args.out}")
    print(json.dumps(res["summary"], indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
