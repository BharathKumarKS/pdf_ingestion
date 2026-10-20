#!/usr/bin/env python3
"""Phase B / B5 — verify RAPTOR and the collection invariant it breaks. Exit 0 = PASS.

Phase 2 writes RAPTOR summaries into the SAME Qdrant collection as the chunks, so the invariant
Step 8 established (`knowledge_base_v2` points == SQLite chunks) is deliberately broken here. This
verifier measures the break rather than assuming it.

  1. active RAPTOR nodes exist for the document and their levels are within `raptor_max_levels`;
  2. `knowledge_base_v2` grew by the RAPTOR node count, and `source_type=raptor_summary` equals it;
  3. ⚠️ lane composition is checked PER POINT KIND, not globally. RAPTOR points are upserted with
     only `dense_64` + `dense_1024` (no colbert, no sparse — §F2). Asserting "all four lanes on
     every point" (Step 8's check) would fail spuriously here.
  4. RAPTOR vectors are NOT zero — the reason `--raptor-only` exists ("RAPTOR used zero vectors"
     happened once). A zero vector is the §I9 silent-failure signature.
  5. SQLite node count vs Qdrant point count: `save_raptor_tree` SKIPS nodes whose embedding is
     None, so the two can legitimately differ. Report the gap; a gap means embeddings were lost.

    uv run python logs/p1/step10/verify_phaseb_raptor.py
"""
from __future__ import annotations

import json
import sqlite3
import sys
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

DB = ROOT / "data/synapse.db"
BEFORE = ROOT / "logs/p1/step10/phaseb_before.json"
OUT = ROOT / "logs/p1/step10/phaseb_raptor_verify.json"
DOC_NEW = "7ba61432-c5e0-416d-aecf-25a232523481"

CHUNK_LANES = {"colbert", "dense_1024", "dense_64", "sparse"}
RAPTOR_LANES = {"dense_1024", "dense_64"}


def main() -> int:
    from src.core.config import get_settings

    cfg = get_settings()
    before = json.loads(BEFORE.read_text()) if BEFORE.exists() else {}
    points_before = before.get("qdrant_points")

    failures: list[str] = []
    print("=" * 92)
    print("Phase B / B5 — RAPTOR + collection invariant verifier")
    print("=" * 92)
    print(f"  collection: {cfg.qdrant_collection} @ "
          f"{cfg.qdrant_host or cfg.qdrant_url or cfg.qdrant_local_path}")

    # ── 1. SQLite nodes ───────────────────────────────────────────────────
    con = sqlite3.connect(DB)
    nodes = con.execute(
        "SELECT count(*) FROM raptor_nodes WHERE document_id = ? AND is_active = 1", (DOC_NEW,)
    ).fetchone()[0]
    levels = Counter(r[0] for r in con.execute(
        "SELECT level FROM raptor_nodes WHERE document_id = ? AND is_active = 1", (DOC_NEW,)))
    con.close()

    print(f"\n[1] RAPTOR nodes (SQLite, active)")
    print(f"      nodes  : {nodes}")
    print(f"      levels : {dict(sorted(levels.items()))}   "
          f"(raptor_max_levels={cfg.raptor_max_levels})")
    if nodes == 0:
        failures.append("ZERO active RAPTOR nodes")
    over = [lv for lv in levels if lv > cfg.raptor_max_levels]
    if over:
        failures.append(f"levels {sorted(over)} exceed raptor_max_levels={cfg.raptor_max_levels}")

    # ── 2..4. Qdrant ──────────────────────────────────────────────────────
    try:
        from qdrant_client import QdrantClient
        from qdrant_client.models import FieldCondition, Filter, MatchValue

        kwargs: dict = {"timeout": 120}
        if cfg.qdrant_url:
            kwargs.update(url=cfg.qdrant_url, api_key=cfg.qdrant_api_key or None)
        elif cfg.qdrant_host:
            kwargs.update(host=cfg.qdrant_host, port=cfg.qdrant_port)
        else:
            kwargs.update(path=cfg.qdrant_local_path)
        qc = QdrantClient(**kwargs)

        info = qc.get_collection(cfg.qdrant_collection)
        total = int(info.points_count or 0)
        n_raptor = int(qc.count(cfg.qdrant_collection, count_filter=Filter(must=[
            FieldCondition(key="source_type", match=MatchValue(value="raptor_summary"))]
        )).count or 0)
        print(f"\n[2] the invariant Phase B breaks")
        print(f"      points now            : {total}"
              f"{f'   (before: {points_before})' if points_before else ''}")
        print(f"      source_type=raptor_summary : {n_raptor}")
        print(f"      chunk points          : {total - n_raptor}")
        if points_before is not None:
            grew = total - points_before
            print(f"      grew by               : {grew}   (SQLite nodes: {nodes})")
            if grew != nodes:
                failures.append(
                    f"collection grew by {grew} but SQLite has {nodes} nodes — a gap means nodes "
                    "were skipped at upsert (embedding was None) or something else wrote points")
        if n_raptor == 0:
            failures.append("no raptor_summary points in the collection — RAPTOR was not persisted")

        # ── 3/4. per-point-kind lanes and zero vectors ────────────────────
        print(f"\n[3] lane composition per point kind")
        zero_raptor = 0
        bad_chunk_lanes = 0
        seen_raptor = 0
        checked = 0
        offset = None
        while True:
            pts, offset = qc.scroll(cfg.qdrant_collection, limit=256, offset=offset,
                                    with_payload=["source_type"], with_vectors=True)
            for p in pts:
                vec = p.vector if isinstance(p.vector, dict) else {}
                names = set(vec.keys())
                is_raptor = (p.payload or {}).get("source_type") == "raptor_summary"
                if is_raptor:
                    seen_raptor += 1
                    if not RAPTOR_LANES.issubset(names):
                        failures.append(f"RAPTOR point {p.id} missing lanes: "
                                        f"{sorted(RAPTOR_LANES - names)}")
                    raw: Any = vec.get("dense_1024")
                    if isinstance(raw, list):
                        norm_sq = sum(float(x) * float(x) for x in raw)
                        if norm_sq == 0.0:
                            zero_raptor += 1
                else:
                    if not CHUNK_LANES.issubset(names):
                        bad_chunk_lanes += 1
                checked += 1
            if offset is None:
                break
        print(f"      points scanned        : {checked}  (raptor: {seen_raptor})")
        print(f"      chunk points missing a lane : {bad_chunk_lanes}")
        print(f"      RAPTOR points with a ZERO dense_1024 vector : {zero_raptor}")
        if zero_raptor:
            failures.append(f"{zero_raptor} RAPTOR points have zero vectors (§I9 signature) — "
                            "rebuild with --raptor-only")
        if bad_chunk_lanes:
            failures.append(f"{bad_chunk_lanes} CHUNK points are missing a lane")

        qc.close()
    except Exception as exc:
        print(f"\n!! could not read Qdrant: {type(exc).__name__}: {exc}")
        failures.append(f"Qdrant unreadable: {exc}")

    print(f"\n[5] SQLite nodes vs Qdrant points: {nodes} vs "
          f"{'n/a' if not points_before else '(see above)'}")

    OUT.write_text(json.dumps({
        "document_id": DOC_NEW, "sqlite_nodes": nodes, "levels": dict(levels),
        "failures": failures, "verdict": "FAIL" if failures else "PASS",
    }, indent=2))
    print(f"  wrote {OUT.relative_to(ROOT)}")

    print()
    print("=" * 92)
    if failures:
        print("B5 VERDICT: FAIL")
        for f in failures:
            print(f"  !! {f}")
        print("=" * 92)
        return 1
    print("B5 VERDICT: PASS — RAPTOR persisted, vectors non-zero, chunk lanes intact")
    print("=" * 92)
    return 0


if __name__ == "__main__":
    sys.exit(main())
