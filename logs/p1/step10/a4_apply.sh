#!/usr/bin/env bash
# A4 (apply) — retire the OLD document's graph. DESTRUCTIVE.
# Removes the graph belonging to the currently-DEPLOYED `knowledge_base` (doc 6d55c52b).
# Owner approved 2026-10-19. Never pass --force: the no-overlap guard refusing IS the safety.
set -uo pipefail
cd "/Users/bharathkumar/repo/Support_Vectors/Beyond_RAG_Advanced_Agentic_Knowledge_Architectures/Project/Team_Project/pdf_ingestion" || exit 1

unset PYTHONPATH
unset PYTHONHOME

export QDRANT_HOST=10.0.10.65
export QDRANT_COLLECTION=knowledge_base_v2

echo "=== resolved settings (assert what is actually in force) ==="
uv run python - <<'PY'
from src.core.config import get_settings
c = get_settings()
print(f"  qdrant_collection : {c.qdrant_collection}")
print(f"  qdrant            : {c.qdrant_host or c.qdrant_url or c.qdrant_local_path}")
print(f"  memgraph          : {c.memgraph_host}:{c.memgraph_port}")
assert c.qdrant_collection == "knowledge_base_v2", f"collection is {c.qdrant_collection!r}"
assert c.qdrant_host == "10.0.10.65", f"qdrant_host is {c.qdrant_host!r}"
print("  ASSERTIONS OK")
PY

echo
echo "=== A4 APPLY — destructive ==="
uv run python scripts/clean_stale_graph.py --qdrant-host 10.0.10.65 --yes
echo "exit=$?"
