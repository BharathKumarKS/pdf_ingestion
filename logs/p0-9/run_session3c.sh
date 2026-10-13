#!/usr/bin/env bash
# P0-9 Session 3c — the overview lane (three sequential steps, one background job).
#   step 1: generate overview questions  -> data/eval_queries_gold_overview.json
#   step 2: book-wide scan labels        -> data/eval_queries_gold_overview_expanded.json
#   step 3: grown negatives              -> data/eval_negatives.json
# Judge MUST be the VLM (D9 sends the page image). --workers 8 = the ramp-probe knee
# (4.21 calls/s). Step 1 takes no judge flags — it generates from .env's LLM settings.
set -uo pipefail

REPO="/Users/bharathkumar/repo/Support_Vectors/Beyond_RAG_Advanced_Agentic_Knowledge_Architectures/Project/Team_Project/pdf_ingestion"
cd "$REPO" || exit 1
LOG="$REPO/logs/p0-9/session3c-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$LOG"
export PYTHONUNBUFFERED=1

JUDGE=(--judge-backend openai --judge-api-base http://10.0.10.70:8000 --judge-model Qwen/Qwen3-VL-8B-Instruct)
WORKERS=8
PDF=data/base_textbooks/feynman-lectures-on-physics-volume1.pdf

echo "=== P0-9 Session 3c (overview) started $(date) ==="
echo "logs: $LOG"

echo; echo "=== STEP 1/3: generate overview questions  $(date) ==="
uv run python scripts/generate_gold_dataset.py \
  --tenant global --n-chunks 0 --overview-count 40 \
  --overview-output data/eval_queries_gold_overview.json 2>&1 | tee "$LOG/step1-generate.log"
rc1=${PIPESTATUS[0]}
n1=$(python -c "import json;print(len(json.load(open('data/eval_queries_gold_overview.json'))))" 2>/dev/null || echo '?')
echo "step1 rc=$rc1  overview questions written: $n1"
if [ "$rc1" -ne 0 ]; then echo "STEP 1 FAILED rc=$rc1 — aborting"; exit 1; fi

echo; echo "=== STEP 2/3: book-wide scan labels  $(date) ==="
uv run python scripts/expand_gold_labels.py \
  --query-file data/eval_queries_gold_overview.json \
  --pdf "$PDF" \
  --output data/eval_queries_gold_overview_expanded.json \
  --workers $WORKERS "${JUDGE[@]}" 2>&1 | tee "$LOG/step2-expand.log"
rc2=${PIPESTATUS[0]}
echo "step2 rc=$rc2"

echo; echo "=== STEP 3/3: grown negatives  $(date) ==="
uv run python scripts/generate_negatives.py \
  --n 36 --pdf "$PDF" --workers $WORKERS \
  --output data/eval_negatives.json "${JUDGE[@]}" 2>&1 | tee "$LOG/step3-negatives.log"
rc3=${PIPESTATUS[0]}
echo "step3 rc=$rc3"

echo; echo "=== DONE $(date) ==="
echo "rcs: step1=$rc1 step2=$rc2 step3=$rc3"
ls -la data/eval_queries_gold_overview.json data/eval_queries_gold_overview_expanded.json data/eval_negatives.json 2>&1
