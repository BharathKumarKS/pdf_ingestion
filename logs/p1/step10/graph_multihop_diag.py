"""Diagnostic — how big are the RELATES_TO neighbourhoods, and how slow is the naive traversal?

Read-only. Times: (a) 1-hop distinct neighbours of 8 seed concepts, (b) 2-hop, (c) the naive
`*0..2` path-enumeration the first implementation used. Answers whether the timeout is path
enumeration (redesign to level-by-level BFS) or raw fan-out (cap the expansion).
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))
from src.core.config import get_settings  # noqa: E402
from src.core.database import get_memgraph  # noqa: E402

cfg = get_settings()
drv = get_memgraph(cfg)
SEEDS = ["friction", "speed of light", "electron behavior in atoms", "Newton's Laws of Mechanics",
         "Law of Friction", "Oscillating Force", "properties of matter", "Atomic nature of matter"]

with drv.session() as s:
    t = time.monotonic()
    n1 = s.run("MATCH (k:Concept)-[:RELATES_TO]-(n:Concept) WHERE k.name IN $names "
               "RETURN count(DISTINCT n) AS n", names=SEEDS).single()["n"]
    print(f"1-hop distinct neighbours: {n1}  ({time.monotonic()-t:.1f}s)")

    t = time.monotonic()
    n2 = s.run("MATCH (k:Concept)-[:RELATES_TO*2..2]-(n:Concept) WHERE k.name IN $names "
               "RETURN count(DISTINCT n) AS n", names=SEEDS).single()["n"]
    print(f"2-hop distinct neighbours: {n2}  ({time.monotonic()-t:.1f}s)")

    for h in (1, 2):
        t = time.monotonic()
        try:
            r = s.run(f"MATCH p = (k:Concept)-[:RELATES_TO*0..{h}]-(n:Concept) "
                      f"WHERE k.name IN $names RETURN count(*) AS paths", names=SEEDS).single()
            print(f"naive *0..{h} PATH ENUMERATION: {r['paths']} paths  ({time.monotonic()-t:.1f}s)")
        except Exception as e:
            print(f"naive *0..{h}: ERR {type(e).__name__}: {str(e)[:100]} ({time.monotonic()-t:.1f}s)")
drv.close()
