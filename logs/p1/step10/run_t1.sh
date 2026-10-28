#!/usr/bin/env bash
# T1 — the BASE-LANE ship test: nomic/v3 POOLED (B) vs qwen3/v2 (A), 133 gold queries, HyDE ON+frozen.
# Pre-registration: .hermes/plans/2026-10-27-p1-t1-base-lanes-preregistration.md (committed ALONE 3ab62f7).
#
# ORDER IS LOAD-BEARING (§10): arm A's two reps run FIRST, then `--gate-a` checks E4 (A1 vs A2
# bit-exact) and E9 (A1 bit-exact against Stage F's arm A). If either fails, arm B is NEVER spent.
#
# The A2 `.env` flip is NOT applied, so EVERY per-arm value is exported here and ASSERTED inside the
# harness (E1/E2). Forget one and the run silently uses Qwen3/1024 against the wrong collection.
set -euo pipefail
cd "$(dirname "$0")/../../.."          # repo root
unset PYTHONPATH                        # Hermes' python3.14 site-packages shadows the venv's pydantic

export QDRANT_HOST=10.0.10.65
export DENSE_DIM_LOW=64
# The DA lane is OFF in BOTH arms — `search_da` uses the dense query vector, whose dim is the arm's
# dense_dim, against a single 768d `derivative_artifacts`, so it can serve only one arm.
export DA_ENABLED=false
# Qwen3's instruction, verbatim from config.py (the newline is load-bearing).
QWEN_INSTR=$'Instruct: Given a physics question, retrieve textbook passages that answer it\nQuery: '

LOG=logs/p1/step10/t1_run_2026-10-27.txt
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
    uv run python logs/p1/step10/t1_base_lanes.py --arm "$arm" --rep "$rep" 2>&1 | tee -a "$LOG"
}

echo "===== GATE A PRECONDITION: arm A (control + instrument check) =====" | tee -a "$LOG"
run_arm A 1
run_arm A 2

echo "===== GATE A: E4 + E9 on arm A =====" | tee -a "$LOG"
if ! uv run python logs/p1/step10/t1_base_lanes.py --gate-a 2>&1 | tee -a "$LOG"; then
  echo "GATE A FAILED — arm B NOT run. Run is VOID (T1 pre-registration §10)." | tee -a "$LOG"
  exit 3
fi

echo "===== ARM B (treatment: the POOLED index) =====" | tee -a "$LOG"
run_arm B 1
run_arm B 2

echo "===== COMBINE =====" | tee -a "$LOG"
uv run python logs/p1/step10/t1_base_lanes.py --combine 2>&1 | tee -a "$LOG"

echo "===== VERIFIER (independent, stdlib-only) =====" | tee -a "$LOG"
uv run python logs/p1/step10/t1_verifier.py --check --extract 2>&1 | tee -a "$LOG"
