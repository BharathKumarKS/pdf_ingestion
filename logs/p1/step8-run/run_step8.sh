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
