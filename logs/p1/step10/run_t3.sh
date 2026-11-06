#!/usr/bin/env bash
# T3 — the LANE-COMPLETE v2-vs-v3 A/B: the full-funnel ship test.
# Pre-registration: .hermes/plans/2026-11-02-p1-t3-lane-complete-preregistration.md (committed ALONE, D6.1).
#
# SIX arm-runs: A_off/B_off once each (the §I85 reproduction = the instrument anchor, G8); A_on/B_on
# TWICE each (the treatment + the determinism guard, G10). The A2 `.env` flip is NOT applied, so every
# per-arm value is exported here and ASSERTED inside the harness (E1/E2).
set -euo pipefail
cd "$(dirname "$0")/../../.."          # repo root
unset PYTHONPATH                        # Hermes' python3.14 site-packages shadows the venv's pydantic

export QDRANT_HOST=10.0.10.65
export DENSE_DIM_LOW=64
# Qwen3's instruction, verbatim from config.py:111-113 (the newline is load-bearing).
QWEN_INSTR=$'Instruct: Given a physics question, retrieve textbook passages that answer it\nQuery: '

LOG=logs/p1/step10/t3_run.txt
: > "$LOG"

run_arm() {
  local arm="$1" lanes="$2" rep="$3" coll model dim instr prefix da
  if [ "$arm" = "A" ]; then
    coll=knowledge_base_v2; model="Qwen/Qwen3-Embedding-0.6B"; dim=1024
    instr="$QWEN_INSTR"; prefix=""
  else
    coll=knowledge_base_v3; model="nomic-ai/nomic-embed-text-v1.5"; dim=768
    instr="search_query: "; prefix="search_document: "
  fi
  if [ "$lanes" = "on" ]; then da=true; else da=false; fi
  echo "===== ARM $arm lanes=$lanes rep $rep ($coll / $model / ${dim}d / DA=$da) =====" | tee -a "$LOG"
  QDRANT_COLLECTION="$coll" DENSE_MODEL="$model" DENSE_DIM="$dim" \
  QUERY_INSTRUCTION="$instr" DOCUMENT_PREFIX="$prefix" DA_ENABLED="$da" \
    .venv/bin/python logs/p1/step10/t3_lane_complete.py \
      --arm "$arm" --lanes "$lanes" --rep "$rep" 2>&1 | tee -a "$LOG"
}

# The instrument anchor (§I85's configuration).
run_arm A off 1
run_arm B off 1
# The lane-complete treatment (+ determinism).
run_arm A on 1
run_arm A on 2
run_arm B on 1
run_arm B on 2

echo "===== COMBINE =====" | tee -a "$LOG"
.venv/bin/python logs/p1/step10/t3_lane_complete.py --combine 2>&1 | tee -a "$LOG"
