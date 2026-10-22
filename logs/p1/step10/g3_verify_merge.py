#!/usr/bin/env python
"""§G3's verifiers, from Bolt. Read-only. 2026-10-22.

Usage:
    uv run python logs/p1/step10/g3_verify_merge.py --before  --out <state.json>
    uv run python logs/p1/step10/g3_verify_merge.py --after   --before-state <state.json>

Captures the graph's concept/edge state, then — in `--after` mode — checks §G3's verifiers against
the captured before-state:

  V1  no name is lost: every merged-away name survives as an `aliases` entry on a survivor.
  V2  MENTIONS / RELATES_TO / PREREQUISITE_OF counts are CONSERVED MODULO THE MERGES: the delta must
      equal the number of edges collapsed by the merge, which is computed from the before-state.
      A bare "> 0" would pass a merge that destroyed 90 % of the graph, so the arithmetic is the check.
  V4  the measured lever reproduces: each surviving group's chunk count equals the UNION of its
      members' chunk sets in the before-state (that union is the whole point of merging).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

DOC = "7ba61432-c5e0-416d-aecf-25a232523481"


def _counts(s):
    def one(cypher, **kw):
        row = s.run(cypher, **kw).single()
        return int(row["n"]) if row else 0
    return {
        "Concept": one("MATCH (k:Concept) RETURN count(k) AS n"),
        "MENTIONS": one("MATCH (:Chunk)-[r:MENTIONS]->(:Concept) RETURN count(r) AS n"),
        "RELATES_TO": one("MATCH (:Concept)-[r:RELATES_TO]-(:Concept) RETURN count(r) AS n") // 2,
        "PREREQUISITE_OF": one("MATCH (:Concept)-[r:PREREQUISITE_OF]->(:Concept) RETURN count(r) AS n"),
    }


def _state(s):
    mentions = {
        (r["chunk"], r["concept"])
        for r in s.run(
            "MATCH (c:Chunk)-[:MENTIONS]->(k:Concept) WHERE c.document_id = $doc "
            "RETURN c.id AS chunk, k.name AS concept", doc=DOC).data()
    }
    relates = set()
    for r in s.run(
        "MATCH (a:Concept)-[r:RELATES_TO]-(b:Concept) RETURN a.name AS a, b.name AS b").data():
        relates.add(tuple(sorted((r["a"], r["b"]))))
    prereq = {
        (r["a"], r["b"])
        for r in s.run(
            "MATCH (a:Concept)-[:PREREQUISITE_OF]->(b:Concept) "
            "RETURN a.name AS a, b.name AS b").data()
    }
    aliases = {
        r["name"]: sorted(r["aliases"] or [])
        for r in s.run(
            "MATCH (k:Concept) WHERE k.aliases IS NOT NULL "
            "RETURN k.name AS name, k.aliases AS aliases").data()
    }
    chunks_of = {}
    for r in s.run(
        "MATCH (c:Chunk)-[:MENTIONS]->(k:Concept) WHERE c.document_id = $doc "
        "RETURN k.name AS name, collect(DISTINCT c.id) AS chunks", doc=DOC).data():
        chunks_of[r["name"]] = sorted(r["chunks"])
    return {
        "counts": _counts(s),
        "mentions": sorted(f"{c}|{k}" for c, k in mentions),
        "relates": sorted(f"{a}|{b}" for a, b in relates),
        "prereq": sorted(f"{a}|{b}" for a, b in prereq),
        "aliases": aliases,
        "chunks_of": chunks_of,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--before", action="store_true")
    ap.add_argument("--after", action="store_true")
    ap.add_argument("--out", default=None)
    ap.add_argument("--before-state", default=None)
    args = ap.parse_args()

    from src.core.config import get_settings
    from src.core.database import get_memgraph

    driver = get_memgraph(get_settings())
    if driver is None:
        print("Memgraph unavailable", file=sys.stderr)
        return 2
    with driver.session() as s:
        st = _state(s)

    if args.before:
        out = args.out or "logs/p1/step10/g3_state_before.json"
        Path(out).write_text(json.dumps(st, indent=1, sort_keys=True), encoding="utf-8")
        print(f"BEFORE counts: {st['counts']}")
        print(f"wrote {out}")
        return 0

    if not args.after:
        print("pass --before or --after", file=sys.stderr)
        return 2

    before = json.loads(Path(args.before_state).read_text(encoding="utf-8"))
    print(f"BEFORE counts: {before['counts']}")
    print(f"AFTER  counts: {st['counts']}")

    ok = True

    # ---- V1: every merged-away name survives as an alias ----
    merged_away = set(before["chunks_of"]) - set(st["chunks_of"])
    aliased = {a for v in st["aliases"].values() for a in v}
    v1 = merged_away <= aliased
    ok &= v1
    print(f"\nV1  names merged away: {len(merged_away)};  surviving as aliases: "
          f"{len(merged_away & aliased)};  LOST: {len(merged_away - aliased)}  -> "
          f"{'PASS' if v1 else 'FAIL'}")
    if merged_away - aliased:
        print(f"    LOST NAMES: {sorted(merged_away - aliased)[:10]}")

    # ---- V2: edges conserved modulo the merges ----
    # The plan's requirement is that the delta EQUALS the number of edges the merge collapsed, not
    # merely that it is non-negative. That is computable exactly: remap every before-state edge
    # through the alias map, drop the self-loops a merge creates, and the result must equal the
    # after-state edge set — not just its size.
    survivor_of: dict[str, str] = {}
    for surv, als in st["aliases"].items():
        survivor_of[surv] = surv
        for al in als:
            survivor_of[al] = surv

    def remap(name: str) -> str:
        return survivor_of.get(name, name)

    print("\nV2  edge conservation — the after-state must EQUAL the remapped before-state:")
    expected = {
        "MENTIONS": {
            (c, remap(k)) for c, k in (e.split("|", 1) for e in before["mentions"])
        },
        "RELATES_TO": {
            tuple(sorted((remap(a), remap(b))))
            for a, b in (e.split("|", 1) for e in before["relates"])
            if remap(a) != remap(b)
        },
        "PREREQUISITE_OF": {
            (remap(a), remap(b))
            for a, b in (e.split("|", 1) for e in before["prereq"])
            if remap(a) != remap(b)
        },
    }
    actual = {
        "MENTIONS": {tuple(e.split("|", 1)) for e in st["mentions"]},
        "RELATES_TO": {tuple(e.split("|", 1)) for e in st["relates"]},
        "PREREQUISITE_OF": {tuple(e.split("|", 1)) for e in st["prereq"]},
    }
    for label in ("MENTIONS", "RELATES_TO", "PREREQUISITE_OF"):
        before_key = {"MENTIONS": "mentions", "RELATES_TO": "relates",
                      "PREREQUISITE_OF": "prereq"}[label]
        b, exp, act = len(before[before_key]), len(expected[label]), len(actual[label])
        collapsed = b - exp
        same = expected[label] == actual[label]
        ok &= same
        print(f"    {label:16} before {b:>7,}  expected {exp:>7,}  after {act:>7,}  "
              f"collapsed {collapsed:>6,}  exact-match {same}  -> {'PASS' if same else 'FAIL'}")
        if not same:
            missing = expected[label] - actual[label]
            extra = actual[label] - expected[label]
            print(f"      MISSING {len(missing)} (e.g. {list(missing)[:3]})")
            print(f"      EXTRA   {len(extra)} (e.g. {list(extra)[:3]})")
    if st["counts"]["Concept"] > before["counts"]["Concept"]:
        ok = False
        print("    FAIL: the Concept count rose — a merge must only remove nodes")

    # ---- V4: each survivor's chunk count equals the UNION of its members' chunks ----
    print("\nV4  the lever reproduces (survivor chunks == union of merged members):")
    checked = 0
    for survivor, aliases in sorted(st["aliases"].items()):
        if survivor not in st["chunks_of"]:
            continue
        union = set(st["chunks_of"][survivor])
        for al in aliases:
            union |= set(before["chunks_of"].get(al, []))
        got = set(st["chunks_of"][survivor])
        checked += 1
        if checked <= 5:
            print(f"    {survivor!r:32} chunks {len(got):>4}  union(expected) {len(union):>4}  "
                  f"{'ok' if got == union else 'MISMATCH'}")
        if got != union:
            ok = False
    print(f"    checked {checked} survivors -> {'PASS' if ok else 'FAIL'}")

    print(f"\nMECHANICAL VERDICT: {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
