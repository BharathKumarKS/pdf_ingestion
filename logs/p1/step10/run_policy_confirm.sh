#!/usr/bin/env bash
# The LIVE confirmation of the per-type rerank-query policy (pre-registration §8).
# Read-only. T0's lane set: DA ON and the graph lane ON. HyDE ON and frozen.
# Same env as run_t4.sh so the only difference is the src change under test.
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
LOG=logs/p1/step10/policy_confirm_run.txt
: > "$LOG"
uv run python logs/p1/step10/policy_confirm.py "$@" 2>&1 | tee -a "$LOG"
