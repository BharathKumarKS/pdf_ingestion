#!/usr/bin/env bash
# P0-9 Session 3 — run the scan (three sequential steps, one background job).
#   step 1: generate gold questions  -> data/eval_queries_gold.json
#   step 2: scan-expand labels       -> data/eval_queries_gold_expanded.json
#   step 3: verified negatives       -> data/eval_negatives.json
# Judge MUST be the VLM (D9 sends the page image). --workers 8 = the ramp-probe knee.
set -uo pipefail

REPO="/Users/bharathkumar/repo/Support_Vectors/Beyond_RAG_Advanced_Agentic_Knowledge_Architectures/Project/Team_Project/pdf_ingestion"
cd "$REPO" || exit 1
LOG="$REPO/logs/p0-9/session3-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$LOG"
export PYTHONUNBUFFERED=1

JUDGE=(--judge-backend openai --judge-api-base http://10.0.10.70:8000 --judge-model Qwen/Qwen3-VL-8B-Instruct)
WORKERS=8

echo "=== P0-9 Session 3 scan started $(date) ==="
echo "logs: $LOG"

echo; echo "=== STEP 1/3: generate gold questions  $(date) ==="
uv run python scripts/generate_gold_dataset.py \
  --tenant global --n-chunks 40 --questions-per-chunk 2 --multipage-count 20 \
  --output data/eval_queries_gold.json 2>&1 | tee "$LOG/step1-generate.log"
rc1=${PIPESTATUS[0]}
n1=$(python -c "import json;print(len(json.load(open('data/eval_queries_gold.json'))))" 2>/dev/null || echo '?')
echo "step1 rc=$rc1  gold questions written: $n1"
if [ "$rc1" -ne 0 ]; then echo "STEP 1 FAILED rc=$rc1 — aborting"; exit 1; fi

echo; echo "=== STEP 2/3: scan-expand labels  $(date) ==="
uv run python scripts/expand_gold_labels.py \
  --query-file data/eval_queries_gold.json \
  --output data/eval_queries_gold_expanded.json \
  --workers $WORKERS "${JUDGE[@]}" 2>&1 | tee "$LOG/step2-expand.log"
rc2=${PIPESTATUS[0]}
echo "step2 rc=$rc2"

echo; echo "=== STEP 3/3: verified negatives  $(date) ==="
uv run python scripts/generate_negatives.py \
  --n 24 --workers $WORKERS \
  --output data/eval_negatives.json "${JUDGE[@]}" 2>&1 | tee "$LOG/step3-negatives.log"
rc3=${PIPESTATUS[0]}
echo "step3 rc=$rc3"

echo; echo "=== DONE $(date) ==="
echo "rcs: step1=$rc1 step2=$rc2 step3=$rc3"
ls -la data/eval_queries_gold.json data/eval_queries_gold_expanded.json data/eval_negatives.json 2>&1
