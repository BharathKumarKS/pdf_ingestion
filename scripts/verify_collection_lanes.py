#!/usr/bin/env python3
"""verify_collection_lanes — a READ-ONLY gate: every ENABLED lane is present on every point
that requires it, scoped by point kind. Reports per-lane coverage; exits non-zero on a gap.

**Why this exists** (§I13 / §I33 / §I76). A re-embed or a lane migration can leave a named
vector ABSENT on every point. Qdrant accepts that silently, the collection still reports a
healthy point count, and the missing lane returns nothing until someone issues a real query.
A point-count gate holds a dead lane green; a per-point check does not.

**Why the assertion is SCOPED, not "every lane on every point"** — measured 2026-10-24 on the
live ``knowledge_base_v2`` (3,869 points): ``dense_64``/``dense_1024`` are on all 3,869 while
``colbert``/``sparse`` are on 3,796. The 73 without them are ``raptor_level`` summary nodes,
which legitimately carry the dense lanes only. A naive "every lane on every point" assertion
FAILS on a collection that is known-good — which is how a gate gets edited until it passes
(§I26). Scope it; do not delete it.

⚠️ **The lane inventory is read from BOTH ``params.vectors`` AND ``params.sparse_vectors``.**
The sparse lane lives in the second key, so a named-vector check that reads only the first
misses it entirely — the mistake registered as ``IMPROVEMENTS.md`` §I76.

⚠️ **This builds its OWN client and deliberately does NOT use ``database.get_qdrant``**, because
that factory calls ``_ensure_collection``: it CREATES the collection it cannot find. A gate that
creates its subject can never report it missing. §I49 Finding 1 is the same class — only the
store that is actually resolved counts, so this prints it.

⚠️ **Zero points inspected is a FAILURE, not a pass.** "Scrolled nothing, found nothing wrong"
is the silent all-clear this tool exists to prevent (§I25).

Usage::

    unset PYTHONPATH && export QDRANT_HOST=10.0.10.65 QDRANT_COLLECTION=knowledge_base_v3
    uv run python scripts/verify_collection_lanes.py --collection knowledge_base_v3
"""
from __future__ import annotations

import argparse
import sys

# Exit codes: 0 = every required lane present; 1 = a lane gap; 2 = cannot inspect the collection.
EXIT_OK, EXIT_GAP, EXIT_UNINSPECTABLE = 0, 1, 2


def _build_client(cfg):
    """A read-only Qdrant client, mirroring ``database.get_qdrant``'s resolution WITHOUT the
    ``_ensure_*`` calls. Tests monkeypatch this module attribute."""
    from qdrant_client import QdrantClient

    if cfg.qdrant_in_memory:
        return QdrantClient(":memory:")
    if cfg.qdrant_url:
        kwargs = {"url": cfg.qdrant_url}
        if cfg.qdrant_api_key:
            kwargs["api_key"] = cfg.qdrant_api_key
        return QdrantClient(**kwargs)
    if cfg.qdrant_host:
        return QdrantClient(host=cfg.qdrant_host, port=cfg.qdrant_port)
    from pathlib import Path
    Path(cfg.qdrant_local_path).mkdir(parents=True, exist_ok=True)
    return QdrantClient(path=cfg.qdrant_local_path)


def describe_store(cfg) -> str:
    """The store that will ACTUALLY be inspected — never an assumed one."""
    if cfg.qdrant_in_memory:
        return "in-memory (tests)"
    if cfg.qdrant_url:
        return f"url {cfg.qdrant_url}"
    if cfg.qdrant_host:
        return f"host {cfg.qdrant_host}:{cfg.qdrant_port}"
    return f"LOCAL embedded path {cfg.qdrant_local_path!r} (QDRANT_HOST is unset)"


def _lane_names(mapping) -> list[str]:
    """Lane names in a Qdrant vectors/sparse_vectors config mapping ([] when not a mapping)."""
    if mapping is None or not hasattr(mapping, "keys"):
        return []
    return sorted(mapping.keys())


def enabled_lanes(client, collection: str) -> tuple[list[str], list[str]]:
    """``(dense_lane_names, all_lane_names)`` — read from BOTH config keys.

    ⚠️ ``dense_lane_names`` is the **``dense_*`` subset** of ``params.vectors``, not all of it:
    ``colbert`` lives in that same key but a RAPTOR summary node does **not** carry it. Measured
    on the live ``knowledge_base_v2`` — the 73 summary nodes have ``dense_64`` + ``dense_1024``
    and nothing else, so a "raptor nodes need everything in ``params.vectors``" rule reports 73
    false gaps on a known-good collection. ``colbert`` belongs in ``all_lane_names`` only.
    """
    params = client.get_collection(collection).config.params
    named = _lane_names(getattr(params, "vectors", None))
    sparse = _lane_names(getattr(params, "sparse_vectors", None))
    dense = [n for n in named if n.startswith("dense_")]
    return dense, named + sparse


def required_lanes(point, dense: list[str], all_lanes: list[str]) -> list[str]:
    """A RAPTOR summary node carries the dense lanes only; a chunk point carries every lane."""
    payload = getattr(point, "payload", None) or {}
    if payload.get("raptor_level") is not None:
        return dense
    return all_lanes


def point_lanes(point) -> set[str]:
    """The lane names actually present on a point.

    ⚠️ The attribute is ``point.vector`` (singular). ``getattr(p, "vectors", {})`` returns ``{}``
    for every real Qdrant record, which makes every point look vector-less — a silent all-clear
    with zero coverage. That defect was in this script's first draft, and its test passed anyway
    because the stub declared the same wrong attribute.
    """
    vec = getattr(point, "vector", None)
    return set(vec.keys()) if hasattr(vec, "keys") else set()


def verify(client, collection: str, *, page_size: int = 1000) -> tuple[int, dict]:
    """Inspect every point. Returns ``(exit_code, report)``."""
    try:
        dense, all_lanes = enabled_lanes(client, collection)
    except Exception as exc:                                   # absent, or the store is down
        return EXIT_UNINSPECTABLE, {"error": f"cannot read collection '{collection}': {exc}"}

    if not all_lanes:
        return EXIT_UNINSPECTABLE, {
            "error": f"collection '{collection}' declares no named lanes "
                     f"(a legacy single-vector schema) — nothing to verify"}

    coverage = {lane: 0 for lane in all_lanes}
    seen: set[str] = set()
    by_kind = {"chunk": 0, "raptor": 0}
    gaps: list[tuple[str, list[str]]] = []

    offset = None
    while True:
        points, offset = client.scroll(
            collection_name=collection, limit=page_size, offset=offset,
            with_vectors=True, with_payload=True,
        )
        if not points:
            break
        for p in points:
            seen.add(str(p.id))
            payload = getattr(p, "payload", None) or {}
            kind = "raptor" if payload.get("raptor_level") is not None else "chunk"
            by_kind[kind] += 1
            present = point_lanes(p)
            for lane in present:
                if lane in coverage:
                    coverage[lane] += 1
            missing = sorted(set(required_lanes(p, dense, all_lanes)) - present)
            if missing:
                gaps.append((str(p.id), missing))
        if offset is None:                                     # the cursor is exhausted
            break

    report = {
        "collection": collection, "dense_lanes": dense, "all_lanes": all_lanes,
        "points_inspected": len(seen), "points_by_kind": by_kind,
        "coverage": coverage, "gaps": gaps,
    }
    if not seen:
        # ⚠️ A silent all-clear: an empty scroll is not a pass.
        report["error"] = (f"inspected 0 points in '{collection}' — an empty scroll is NOT a "
                           f"pass; check the resolved store and the collection name")
        return EXIT_UNINSPECTABLE, report
    return (EXIT_GAP if gaps else EXIT_OK), report


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Verify collection lane coverage")
    parser.add_argument("--collection", default=None,
                        help="Qdrant collection to inspect (default: cfg.qdrant_collection)")
    parser.add_argument("--page-size", type=int, default=1000)
    args = parser.parse_args(argv)

    from src.core.config import get_settings
    cfg = get_settings()
    collection = args.collection or cfg.qdrant_collection

    # The resolved store first — an assumed one is how a run inspects the wrong place (§I49).
    print(f"resolved store      : {describe_store(cfg)}")
    print(f"resolved collection : {collection}")

    client = _build_client(cfg)
    rc, report = verify(client, collection, page_size=args.page_size)

    if "error" in report:
        print(f"FAIL: {report['error']}", file=sys.stderr)
        return rc

    print(f"points inspected    : {report['points_inspected']} "
          f"({report['points_by_kind']['chunk']} chunk / {report['points_by_kind']['raptor']} raptor)")
    print(f"enabled lanes       : {', '.join(report['all_lanes'])}")
    print("per-lane coverage   :")
    for lane in report["all_lanes"]:
        print(f"    {lane:12} {report['coverage'][lane]:6d} / {report['points_inspected']}")

    if report["gaps"]:
        print(f"\nFAIL: {len(report['gaps'])} point(s) missing a required lane "
              f"(showing up to 10):", file=sys.stderr)
        for pid, missing in report["gaps"][:10]:
            print(f"    point {pid}: missing {missing}", file=sys.stderr)
        return rc

    print("\nOK: every required lane is present on every point it is required on.")
    return rc


if __name__ == "__main__":
    sys.exit(main())
