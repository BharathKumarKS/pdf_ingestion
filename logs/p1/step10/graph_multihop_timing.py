"""Time the REAL graph_search traversal query at h=2 and h=3 for one query's seeds. Read-only."""
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
SEEDS = [{"name": n, "score": 0.9} for n in
         ["friction", "speed of light", "electron behavior in atoms", "Newton's Laws of Mechanics",
          "Law of Friction", "Oscillating Force", "properties of matter", "Atomic nature of matter"]]


def traversal(h):
    return f"""
    UNWIND $concepts AS c
    MATCH (k:Concept {{name: c.name}})
    MATCH p = (k)-[:RELATES_TO*0..{h}]-(n:Concept)
    WITH n, c, min(size(relationships(p))) AS hop
    MATCH (ch:Chunk)-[:MENTIONS]->(n)
    WHERE ch.tenant_id IN [$tenant_id, 'global']
    WITH ch, min(hop) AS hop_distance, collect(DISTINCT n.name) AS reached,
         max(c.score) AS concept_score
    RETURN ch.id AS chunk_id, size(reached) AS matched_concepts, hop_distance
    ORDER BY hop_distance ASC, matched_concepts DESC, concept_score DESC LIMIT 20
    """


with drv.session() as s:
    for h in (1, 2, 3):
        t = time.monotonic()
        try:
            rows = s.run(traversal(h), concepts=SEEDS, tenant_id="global").data()
            print(f"h={h}: {len(rows)} chunks, hops={sorted({r['hop_distance'] for r in rows})} "
                  f"({time.monotonic()-t:.1f}s)")
        except Exception as e:
            print(f"h={h}: ERR {type(e).__name__}: {str(e)[:100]} ({time.monotonic()-t:.1f}s)")
drv.close()
