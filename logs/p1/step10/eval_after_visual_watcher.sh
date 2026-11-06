#!/usr/bin/env bash
# Watcher: (1) ensure the phase-3 VISUAL write completes (restart it if it crashes),
#          (2) wait for the SV cluster embed+LLM endpoints to answer 200,
#          (3) start a fresh v3_judged_full eval.
# Launched by the agent on 2026-11-02 at the user's instruction.
set -u
REPO=/Users/bharathkumar/repo/Support_Vectors/Beyond_RAG_Advanced_Agentic_Knowledge_Architectures/Project/Team_Project/pdf_ingestion
cd "$REPO"
WLOG=logs/p1/step10/eval_after_visual_watcher.log
CKPT=logs/p1/step10/phase3_visual_checkpoint.json
RESULT=logs/p1/step10/phase3_visual_result.json
DOC=7ba61432-c5e0-416d-aecf-25a232523481
TARGET_BATCHES=242          # 968 pages / BATCH(4)
EVAL_LOG=logs/p1/step10/v3_judged_full_run.txt

log(){ echo "$(date '+%F %T') $*" >> "$WLOG"; }

log "=== watcher started (pid $$) ==="

# ---- Phase 1: visual write must complete (restart on crash) ----
while true; do
  if pgrep -f "phase3_visual_write.py" >/dev/null 2>&1; then
    sleep 60; continue
  fi
  if [ -f "$RESULT" ]; then log "visual write COMPLETE (result json present)"; break; fi
  nb=$(python3 -c "import json;print(len(json.load(open('$CKPT')).get('$DOC',[])))" 2>/dev/null || echo 0)
  log "visual write not running; checkpoint batches=$nb / $TARGET_BATCHES"
  if [ "$nb" -ge "$TARGET_BATCHES" ]; then log "visual write reached target batch count"; break; fi
  log "restarting visual write (resumes from checkpoint)"
  nohup bash logs/p1/step10/run_phase3_visual.sh >> "$WLOG" 2>&1 &
  sleep 30
done

# ---- Phase 2: cluster must be reachable ----
while true; do
  E=$(curl -s --max-time 8 -o /dev/null -w '%{http_code}' -X POST http://10.0.10.70:8123/embed-text/v1/embeddings -H 'Content-Type: application/json' -d '{"input":"ping","model":"nomic-ai/nomic-embed-text-v1.5"}')
  L=$(curl -s --max-time 8 -o /dev/null -w '%{http_code}' http://10.0.10.70:8000/v1/models)
  if [ "$E" = "200" ] && [ "$L" = "200" ]; then log "cluster READY (embed=$E llm=$L)"; break; fi
  log "cluster not ready (embed=$E llm=$L); waiting"
  sleep 60
done

# ---- Phase 3: start the eval ----
log "starting fresh v3_judged_full eval"
unset PYTHONPATH
export QDRANT_HOST=10.0.10.65
export QDRANT_COLLECTION=knowledge_base_v3
export DENSE_MODEL="nomic-ai/nomic-embed-text-v1.5"
export DENSE_DIM=768
export DENSE_DIM_LOW=64
export DOCUMENT_PREFIX="search_document: "
export QUERY_INSTRUCTION="search_query: "
export DA_ENABLED=true
: > "$EVAL_LOG"
.venv/bin/python scripts/evaluate_rag.py \
  --query-file data/eval_queries_v2.json --skip-visual \
  --judge-backend openai --judge-api-base http://10.0.10.70:8000/v1 \
  --judge-api-key dummy --judge-model Qwen/Qwen3-VL-8B-Instruct \
  --run-name v3_judged_full --output-dir data/eval_results >> "$EVAL_LOG" 2>&1
rc=$?
log "=== eval finished rc=$rc ==="
