#!/usr/bin/env python
"""Mutation proof for lane-plan S2's verifier (`raptor_v3_verify.py`).

WHY THIS SHAPE. The S2 verifier reads the LIVE store rather than a written artifact, so it cannot be
proved by mutating a copy of a JSON file. Instead the real Qdrant client is WRAPPED and one quantity
is mutated per scenario — a dropped point, a renamed id, an edited payload, a widened vector lane, a
changed chunk count, a zeroed lane — and the verifier is run against the wrapper through its
`main(client=...)` seam. Nothing is written to either collection.

Two properties are asserted, and they are different:
  (a) each mutation reddens its INTENDED check;
  (b) every check is reddened by at least one mutation — no inert check.
A mutation that reddens a neighbour as well is expected where two checks read the same list; the
vector is reported whole rather than claiming "exactly its own check".

Run:  unset PYTHONPATH; export QDRANT_HOST=... QDRANT_COLLECTION=knowledge_base_v3 ... ;
      uv run python -u logs/p1/step10/raptor_v3_verify_mutation.py
"""
from __future__ import annotations

import contextlib
import io
import sys
import uuid
from pathlib import Path
from types import SimpleNamespace

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "logs" / "p1" / "step10"))

import raptor_v3_verify as V  # noqa: E402
from src.core.config import get_settings  # noqa: E402

V2, V3 = V.V2, V.V3


def _copy(rec, *, id=None, payload=None, vector=None):
    return SimpleNamespace(
        id=rec.id if id is None else id,
        payload=dict(rec.payload) if payload is None else payload,
        vector=dict(rec.vector) if vector is None else vector,
    )


class Wrap:
    """Delegates to the real client; applies at most one mutation per scenario."""

    def __init__(self, records=None, count=None):
        self._records = records
        self._count = count

    def scroll(self, *, collection_name, scroll_filter=None, limit=256, offset=None,
               with_payload=True, with_vectors=False):
        recs, off = real.scroll(collection_name=collection_name, scroll_filter=scroll_filter,
                                limit=limit, offset=offset, with_payload=with_payload,
                                with_vectors=with_vectors)
        if self._records is not None:
            recs = self._records(collection_name, list(recs))
        return recs, off

    def count(self, *, collection_name, count_filter=None):
        r = real.count(collection_name=collection_name, count_filter=count_filter)
        n = r.count if self._count is None else self._count(collection_name, r.count)
        return SimpleNamespace(count=n)

    def get_collection(self, name):
        return real.get_collection(name)


def _drop_one(coll, recs, only):
    return recs[:-1] if (only is None or coll == only) and len(recs) > 1 else recs


def _rename_one(coll, recs, only):
    if coll != only or not recs:
        return recs
    return recs[:-1] + [_copy(recs[-1], id=str(uuid.uuid4()))]


def _edit_payload(coll, recs, only, key, value):
    if coll != only or not recs:
        return recs
    p = dict(recs[-1].payload)
    p[key] = value
    return recs[:-1] + [_copy(recs[-1], payload=p)]


def _edit_payload_all(coll, recs, only, key, value):
    if coll != only:
        return recs
    return [_copy(r, payload={**r.payload, key: value}) for r in recs]


def _drop_lane(coll, recs, only, lane):
    if coll != only or not recs:
        return recs
    v = {k: val for k, val in recs[-1].vector.items() if k != lane}
    return recs[:-1] + [_copy(recs[-1], vector=v)]


SCENARIOS = [
    ("base (no mutation)", None, None, set()),
    ("MV1 v3 loses one raptor point", lambda c, r: _drop_one(c, r, V3), None, {"V1"}),
    ("MV2 one v3 raptor id renamed", lambda c, r: _rename_one(c, r, V3), None, {"V2"}),
    ("MV3 one v3 payload text edited",
     lambda c, r: _edit_payload(c, r, V3, "text", "MUTATED"), None, {"V3"}),
    ("MV4 v3 embedding_version reverted to Qwen3",
     lambda c, r: _edit_payload_all(c, r, V3, "embedding_version", "Qwen/Qwen3-Embedding-0.6B"),
     None, {"V3b"}),
    ("MV5 v3 chunk count +1", None,
     lambda c, n: n + 1 if c == V3 else n, {"V4"}),
    ("MV6 one v3 point loses dense_full", lambda c, r: _drop_lane(c, r, V3, "dense_full"),
     None, {"V5"}),
    ("MV7 one raptor point dropped from BOTH v2 and v3", lambda c, r: _drop_one(c, r, None),
     None, {"V6"}),
    ("MV8 search_raptor returns nothing", None, None, {"V7"}, "no_raptor"),
]

cfg = get_settings()
if cfg.qdrant_collection != V3:
    print(f"QDRANT_COLLECTION is {cfg.qdrant_collection!r}, not {V3!r} — refusing")
    sys.exit(2)

from qdrant_client import QdrantClient  # noqa: E402

real = QdrantClient(host=cfg.qdrant_host, port=cfg.qdrant_port)

names = [n for n, _, _, _, *_ in SCENARIOS]
rows: list[tuple[str, dict[str, bool], set[str]]] = []

from src.pdf_ingestion.store import DocumentStore  # noqa: E402

_orig_search_raptor = DocumentStore.search_raptor

for name, records, count, intended, *flag in SCENARIOS:
    V.checks.clear()
    if flag and flag[0] == "no_raptor":
        DocumentStore.search_raptor = lambda *a, **k: []
    try:
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            V.main(client=Wrap(records, count))
    finally:
        DocumentStore.search_raptor = _orig_search_raptor
    res = {n: ok for n, ok, _ in V.checks}
    rows.append((name, res, intended))

checks = [n for n in rows[0][1]]
print("=== S2 verifier mutation proof (live store, wrapper-injected mutations) ===")
print("checks:", ", ".join(checks))
print()
hdr = f"{'mutation':<48}" + "".join(f"{c.split()[0]:>7}" for c in checks)
print(hdr)
for name, res, _ in rows:
    print(f"{name:<48}" + "".join(f"{'PASS' if res[c] else 'RED':>7}" for c in checks))

print()
ok = True
for name, res, intended in rows[1:]:
    red = {c.split()[0] for c in checks if not res[c]}
    hit = bool(red & intended)
    ok = ok and hit
    print(f"  [{'ok' if hit else 'FAIL'}] {name}: intended {sorted(intended)} "
          f"reddened {sorted(red) or '[]'}")
    # base must be all-green: a check that can only fail is worse than a vacuous one
base_all_green = all(rows[0][1].values())
print(f"  [{'ok' if base_all_green else 'FAIL'}] base scenario is all-green "
      f"({sum(rows[0][1].values())}/{len(checks)})")
ok = ok and base_all_green

reddened = {c for _, res, _ in rows[1:] for c in checks if not res[c]}
inert = [c for c in checks if c not in reddened]
print(f"  [{'ok' if not inert else 'FAIL'}] every check reddened by at least one mutation "
      f"(inert: {inert or 'none'})")
ok = ok and not inert

print()
print("ALL MUTATIONS DISCRIMINATE" if ok else "MUTATION PROOF FAILED")
sys.exit(0 if ok else 2)
