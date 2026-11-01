#!/usr/bin/env bash
# 4A score-fusion run (§I103) — the registered measurement. READ-ONLY on every collection.
# Same env as run_fusion_order.sh / run_lane_inclusion.sh so the only difference is the arms.
set -euo pipefail
cd "$(dirname "$0")/../../.."
unset PYTHONPATH
export QDRANT_HOST=10.0.10.65
export QDRANT_COLLECTION=knowledge_base_v3
export DENSE_MODEL="nomic-ai/nomic-embed-text-v1.5"
export DENSE_DIM=768
export DENSE_DIM_LOW=64
export DOCUMENT_PREFIX="search_document: "
export QUERY_INSTRUCTION="search_query: "
export DA_ENABLED=true
LOG=logs/p1/step10/score_fusion_run.txt
: > "$LOG"
uv run python -u logs/p1/step10/score_fusion.py "$@" 2>&1 | tee -a "$LOG"
