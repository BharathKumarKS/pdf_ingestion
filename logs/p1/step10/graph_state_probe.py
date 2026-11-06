"""Live graph probe — read-only, via the project's own Memgraph client (holds the credential).

Confirms: Memgraph Concept / RELATES_TO / MENTIONS / PREREQUISITE_OF counts, and the hop_distance
distribution (the §I2 claim: it is a constant 0). No writes.
"""
from __future__ import annotations

import sys

sys.path.insert(0, ".")
from src.core.config import get_settings  # noqa: E402
from src.core.database import get_memgraph  # noqa: E402

cfg = get_settings()
print(f"Memgraph {cfg.memgraph_host}:{cfg.memgraph_port}")
drv = get_memgraph(cfg)
if drv is None:
    print("  driver is None")
    raise SystemExit(1)

with drv.session() as s:
    for label, q in [
        ("Concept", "MATCH (c:Concept) RETURN count(c) AS n"),
        ("RELATES_TO", "MATCH ()-[r:RELATES_TO]->() RETURN count(r) AS n"),
        ("MENTIONS", "MATCH ()-[r:MENTIONS]->() RETURN count(r) AS n"),
        ("PREREQUISITE_OF", "MATCH ()-[r:PREREQUISITE_OF]->() RETURN count(r) AS n"),
        ("hop_distance", "MATCH ()-[r:RELATES_TO]->() RETURN r.hop_distance AS h, count(*) AS n"),
    ]:
        try:
            print(f"  {label}: {[dict(r) for r in s.run(q)]}")
        except Exception as e:
            print(f"  {label}: ERR {type(e).__name__}: {str(e)[:150]}")
drv.close()
