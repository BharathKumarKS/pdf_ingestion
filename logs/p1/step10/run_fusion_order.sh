#!/usr/bin/env bash
# Fusion-order run (§I99) — the registered measurement. READ-ONLY on every collection.
# Same env as run_lane_inclusion.sh / run_t4.sh so the only difference is the arms under test.
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
LOG=logs/p1/step10/fusion_order_run.txt
: > "$LOG"
uv run python -u logs/p1/step10/fusion_order_endpoint.py "$@" 2>&1 | tee -a "$LOG"
