#!/usr/bin/env bash
# P0-9 Session 4b — step 4: evaluate_rag.py on v2.
# Measures generation metrics + the abstention block (34 negatives) + the visual lane
# (33 queries via run_visual_retrieval). Cluster-heavy: LLM generation + judge calls.
#
# CONTEXT HYGIENE: the run's stdout/stderr goes to $LOG only. This script prints a single
# marker line, so a background completion notification carries ~one line instead of the
# whole run (the funnel re-run dumped ~42k chars into the agent's context via `tee`).
#
# Usage: bash logs/p0-9/run_session4b_step4.sh   (run in the BACKGROUND)
set -uo pipefail

REPO="/Users/bharathkumar/repo/Support_Vectors/Beyond_RAG_Advanced_Agentic_Knowledge_Architectures/Project/Team_Project/pdf_ingestion"
cd "$REPO" || exit 1

export QDRANT_HOST=10.0.10.65          # the cluster index (5,135 points), NOT data/qdrant
# The visual lane is SKIPPED: ColPali's base model (vidore/colpaligemma-3b-pt-448-base) is not
# cached here and HuggingFace is unreachable, so ColPali cannot load — each visual query would
# burn ~27.7 min of HF retry-backoff for a 0 score. --skip-visual avoids loading it at all.
# HF_HUB_OFFLINE=1 is belt-and-braces: no model here should phone home.
export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1
LOG="logs/p0-9/session4b_step4.log"

# Preflight: fail fast if the cluster is unreachable. A down cluster otherwise produces an
# empty report after hours (Session 4b: 167 queries all failed, evaluate_rag exited rc=0 with
# 0/0 — see IMPROVEMENTS.md §D11).
preflight() {  # url, name
    local code
    code=$(curl -s -m 6 -o /dev/null -w "%{http_code}" "$1" 2>/dev/null || true)
    if [ "$code" != "200" ]; then
        echo "STEP4_PREFLIGHT_FAILED: $2 unreachable ($1 -> HTTP $code) — aborting before the run"
        exit 3
    fi
    echo "preflight OK: $2"
}
preflight "http://10.0.10.65:6333/collections/knowledge_base" "Qdrant 10.0.10.65"
preflight "http://10.0.10.70:8000/v1/models" "LLM router 10.0.10.70"

{
    echo "=== STEP 4 start $(date '+%F %T') ==="
    uv run python scripts/evaluate_rag.py \
        --query-file data/eval_queries_v2.json \
        --run-name p0-9-gold-v2 --tenant global \
        --skip-visual \
        --judge-backend openai --judge-api-base http://10.0.10.70:8000 \
        --judge-model Qwen/Qwen3-VL-8B-Instruct
    rc=$?
    echo "=== STEP 4 end $(date '+%F %T') rc=$rc ==="
} >> "$LOG" 2>&1

echo "STEP4_DONE rc=$rc log=$LOG"
