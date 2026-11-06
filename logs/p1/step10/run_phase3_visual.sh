#!/usr/bin/env bash
# Phase 3 VISUAL write for the current doc — ColPali only, no Docling re-parse, no graph rebuild.
# Checkpointed per batch; verifier at each stage. Read the result: logs/p1/step10/phase3_visual_result.json
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
LOG=logs/p1/step10/phase3_visual_write_run_2026-11-02.txt
: > "$LOG"
.venv/bin/python logs/p1/step10/phase3_visual_write.py "$@" 2>&1 | tee -a "$LOG"
