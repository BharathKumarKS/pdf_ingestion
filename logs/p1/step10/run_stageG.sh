#!/usr/bin/env bash
# Stage G — the §I66 stage decomposition on both arms. Read-only, no writes, no LLM (HyDE frozen).
# Mirrors Stage F's per-arm env and its DA-off / graph-off config, so the two runs are comparable.
set -euo pipefail
cd "$(dirname "$0")/../../.."
unset PYTHONPATH

export QDRANT_HOST=10.0.10.65
export DENSE_DIM_LOW=64
export DA_ENABLED=false
QWEN_INSTR=$'Instruct: Given a physics question, retrieve textbook passages that answer it\nQuery: '

LOG=logs/p1/step10/stageG_run_session20.txt
: > "$LOG"

run_arm() {
  local arm="$1" coll model dim instr prefix
  if [ "$arm" = "A" ]; then
    coll=knowledge_base_v2; model="Qwen/Qwen3-Embedding-0.6B"; dim=1024
    instr="$QWEN_INSTR"; prefix=""
  else
    coll=knowledge_base_v3; model="nomic-ai/nomic-embed-text-v1.5"; dim=768
    instr="search_query: "; prefix="search_document: "
  fi
  echo "===== ARM $arm ($coll / $model / ${dim}d) =====" | tee -a "$LOG"
  QDRANT_COLLECTION="$coll" DENSE_MODEL="$model" DENSE_DIM="$dim" \
  QUERY_INSTRUCTION="$instr" DOCUMENT_PREFIX="$prefix" \
    uv run python logs/p1/step10/stageG_decomposition.py --arm "$arm" 2>&1 | tee -a "$LOG"
}

run_arm A
run_arm B

echo "===== COMBINE =====" | tee -a "$LOG"
uv run python logs/p1/step10/stageG_decomposition.py --combine 2>&1 | tee -a "$LOG"
