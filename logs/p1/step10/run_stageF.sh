#!/usr/bin/env bash
# Stage F — the ONE product-endpoint run: nomic/v3 (B) vs qwen3/v2 (A), 133 gold queries, HyDE ON+frozen.
# Pre-registration: .hermes/plans/2026-07-25-p1-stageF-product-endpoint-preregistration.md (committed alone).
#
# The A2 `.env` flip is NOT applied, so EVERY per-arm value is exported here and ASSERTED inside the
# harness (E1/E2). Forget one and the run silently uses Qwen3/1024 against the wrong collection — the
# S2/S3 trap (§I80).
set -euo pipefail
cd "$(dirname "$0")/../../.."          # repo root
unset PYTHONPATH                        # Hermes' python3.14 site-packages shadows the venv's pydantic

export QDRANT_HOST=10.0.10.65
export DENSE_DIM_LOW=64
# RE-REGISTRATION (2026-10-25): the DA lane is OFF in BOTH arms — `search_da` uses the dense query
# vector, whose dim is the arm's dense_dim, against a single 768d `derivative_artifacts` (§I83), so it
# can serve only one arm. Leaving it on is not a single-variable A/B (arm B live, arm A silently 400).
export DA_ENABLED=false
# Qwen3's instruction, verbatim from config.py:100-102 (the newline is load-bearing).
QWEN_INSTR=$'Instruct: Given a physics question, retrieve textbook passages that answer it\nQuery: '

LOG=logs/p1/step10/stageF_run_session20.txt
: > "$LOG"

run_arm() {
  local arm="$1" rep="$2" coll model dim instr prefix
  if [ "$arm" = "A" ]; then
    coll=knowledge_base_v2; model="Qwen/Qwen3-Embedding-0.6B"; dim=1024
    instr="$QWEN_INSTR"; prefix=""
  else
    coll=knowledge_base_v3; model="nomic-ai/nomic-embed-text-v1.5"; dim=768
    instr="search_query: "; prefix="search_document: "
  fi
  echo "===== ARM $arm rep $rep ($coll / $model / ${dim}d) =====" | tee -a "$LOG"
  QDRANT_COLLECTION="$coll" DENSE_MODEL="$model" DENSE_DIM="$dim" \
  QUERY_INSTRUCTION="$instr" DOCUMENT_PREFIX="$prefix" \
    uv run python logs/p1/step10/stageF_product_endpoint.py --arm "$arm" --rep "$rep" 2>&1 | tee -a "$LOG"
}

run_arm A 1
run_arm A 2
run_arm B 1
run_arm B 2

echo "===== COMBINE =====" | tee -a "$LOG"
uv run python logs/p1/step10/stageF_product_endpoint.py --combine 2>&1 | tee -a "$LOG"
