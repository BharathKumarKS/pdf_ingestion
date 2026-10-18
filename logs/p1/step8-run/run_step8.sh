#!/usr/bin/env bash
# ============================================================================
# P1 Step 8 — THE RUN.  Re-ingest the Feynman Volume I textbook into a NEW
# Qdrant collection (`knowledge_base_v2`) using the E1/E2/E3 pipeline.
#
# Plan:  .hermes/plans/2026-10-16-p1-reingest-plan.md  §5 Step 8
# Register: IMPROVEMENTS.md §E6
#
# WHY A NEW COLLECTION (plan R1 / R-d):
#   The deployed `knowledge_base` (5,135 points, dense_768) is left completely
#   intact, so a failed run costs nothing and the old index stays queryable.
#   Rollback = point QDRANT_COLLECTION back at `knowledge_base`.
#
# WHY THE EXPLICIT ENV (not from .env):
#   * QDRANT_HOST is blank in .env (local file-mode default); the cluster Qdrant
#     is at 10.0.10.65.  The hostname `ansatz` in the cluster's own URLs does not
#     resolve from this Mac — always use the IP.
#   * SV_EMBED_URL is MISSING from .env even though the whole query path now
#     depends on the cluster dense lane.  Without it ClusterDenseEmbedder raises.
#
# WHY --reindex:
#   ingest_base_textbook.py skips a PDF whose filename is already in `documents`.
#   The old Feynman doc (6d55c52b) is there, so without --reindex the script
#   prints "already ingested" and exits 0 having done nothing.
#
# RESUMABILITY (R-d): at document granularity only.  If this dies mid-run:
#     curl -X DELETE http://10.0.10.65:6333/collections/knowledge_base_v2
#     # and delete the partial doc's rows from SQLite, then re-run this script.
# ============================================================================
set -euo pipefail
cd "$(dirname "$0")/../../.."

export QDRANT_HOST=10.0.10.65
export SV_EMBED_URL=http://10.0.10.70:8123/embed-text/v1/embeddings
export PYTHONUNBUFFERED=1
# `.env` pins LATE_CHUNK_WORKERS=8 (added when 8 was still the default). An exported environment
# variable takes precedence over the .env file, so this is what actually sets the run's worker
# count — and attempt 3 is the reason it is stated here explicitly: it was launched believing it
# ran at 4 when .env silently made it 8. Never infer a setting; print it (see the gate below).
export LATE_CHUNK_WORKERS="${LATE_CHUNK_WORKERS:-4}"

PDF="data/base_textbooks/feynman-lectures-on-physics-volume1.pdf"
COLLECTION="knowledge_base_v2"
LOG="logs/p1/step8-run/run_feynman.log"

mkdir -p logs/p1/step8-run

{
  echo "=================== P1 Step 8 — THE RUN ==================="
  date "+started  %Y-%m-%d %H:%M:%S"
  echo "pdf        : $PDF"
  echo "collection : $COLLECTION"
  echo "qdrant     : $QDRANT_HOST:6333"
  echo "dense lane : $SV_EMBED_URL"
  echo "sqlite     : ${SQLITE_URL:-<from .env: data/synapse.db>}"
  echo "==========================================================="
} | tee "$LOG"

# Resolved-settings gate. This exists because attempt 3 ran at 8 workers while everyone believed
# it ran at 4 — the config default had been changed but `.env` overrode it, and nothing printed
# the value that was actually in force. A launch that cannot state its own settings is a launch
# that cannot be reasoned about afterwards.
uv run python - <<'GATE' | tee -a "$LOG"
from src.core.config import get_settings
c = get_settings()
print("RESOLVED SETTINGS (what this run will actually use)")
print(f"  late_chunk_workers = {c.late_chunk_workers}")
print(f"  embed_cache        = {c.embed_cache_enabled} -> {c.embed_cache_dir}")
print(f"  dense_model        = {c.dense_model} ({c.dense_dim}d)")
print(f"  splade/colbert     = {c.splade_enabled}/{c.colbert_enabled}")
# NB the collection is NOT printed here: it is overridden by --collection-name at run time, so
# `c.qdrant_collection` would show the .env default and read as a contradiction. The header above
# prints the collection actually used.
assert c.late_chunk_workers == int(__import__("os").environ.get("LATE_CHUNK_WORKERS", 4)), \
    "LATE_CHUNK_WORKERS did not take effect — .env is overriding the export"
GATE

/usr/bin/time -l uv run python scripts/ingest_base_textbook.py \
    --pdf "$PDF" \
    --collection-name "$COLLECTION" \
    --title "The Feynman Lectures on Physics, Volume I" \
    --subject Physics \
    --grade Undergraduate \
    --reindex \
    >> "$LOG" 2>&1

echo "=================== RUN COMPLETE ===================" | tee -a "$LOG"
date "+finished %Y-%m-%d %H:%M:%S" | tee -a "$LOG"
