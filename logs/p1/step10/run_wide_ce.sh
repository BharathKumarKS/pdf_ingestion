#!/usr/bin/env bash
# Wide-CE endpoint run — the cross-encoder's FULL ranking over a WIDE pool (cap 500).
# Pre-registration: .hermes/plans/2026-11-01-p1-wide-ce-endpoint-preregistration.md (D6.1).
# Read-only. T0's lane set: DA ON and the graph lane ON. HyDE ON and frozen.
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
LOG=logs/p1/step10/wide_ce_endpoint_run_2026-11-01.txt
: > "$LOG"
uv run python logs/p1/step10/wide_ce_endpoint.py "$@" 2>&1 | tee -a "$LOG"
