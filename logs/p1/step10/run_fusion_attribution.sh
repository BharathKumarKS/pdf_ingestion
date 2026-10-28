#!/usr/bin/env bash
# Fusion attribution — which of RRF / page dedup / MMR drops T0's pages.
# Pre-registration: .hermes/plans/2026-10-27-p1-fusion-attribution-preregistration.md (committed ALONE e9c3a9f).
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
LOG=logs/p1/step10/fusion_attribution_run_2026-10-27.txt
: > "$LOG"
uv run python logs/p1/step10/fusion_attribution.py 2>&1 | tee -a "$LOG"
echo "===== VERIFIER =====" | tee -a "$LOG"
uv run python logs/p1/step10/fusion_attribution_verifier.py --check 2>&1 | tee -a "$LOG"
