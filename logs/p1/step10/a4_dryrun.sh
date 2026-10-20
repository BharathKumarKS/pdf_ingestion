#!/usr/bin/env bash
# A4 (dry-run) — retire the OLD document's graph. Deletes NOTHING.
# Re-confirms the wrong-Qdrant guard against a LIVE Qdrant before the destructive apply.
set -uo pipefail
cd "/Users/bharathkumar/repo/Support_Vectors/Beyond_RAG_Advanced_Agentic_Knowledge_Architectures/Project/Team_Project/pdf_ingestion" || exit 1

# Hermes exports PYTHONPATH pointing at its own python3.14 site-packages; left in
# place it shadows the project venv's pydantic with an ABI-incompatible build
# (ModuleNotFoundError: pydantic_core._pydantic_core). Strip it for project runs.
unset PYTHONPATH
unset PYTHONHOME

export QDRANT_HOST=10.0.10.65
export QDRANT_COLLECTION=knowledge_base_v2

echo "=== cluster probe ==="
uv run python - <<'PY'
import socket
for host, port in [("10.0.10.65", 6333), ("10.0.10.70", 8000), ("10.0.10.70", 8123)]:
    s = socket.socket(); s.settimeout(5)
    try:
        s.connect((host, port)); print(f"  {host}:{port} OPEN")
    except Exception as e:
        print(f"  {host}:{port} FAIL {type(e).__name__}: {e}")
    finally:
        s.close()
PY

echo
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
echo "=== A4 DRY-RUN — deletes nothing ==="
uv run python scripts/clean_stale_graph.py --qdrant-host 10.0.10.65 --dry-run
echo "exit=$?"
