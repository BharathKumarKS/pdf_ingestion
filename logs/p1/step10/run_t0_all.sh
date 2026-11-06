#!/usr/bin/env bash
# T0 — the mutation re-proof (against the hardened revision), THEN the full run, THEN the verifier.
# Chained in ONE process so the pre-registration's ordering (mutation-prove before the run) holds
# and a good cluster window is not lost between the two.
set -uo pipefail
cd "$(dirname "$0")/../../.."
unset PYTHONPATH

export QDRANT_HOST=10.0.10.65
export QDRANT_COLLECTION=knowledge_base_v3
export DENSE_MODEL="nomic-ai/nomic-embed-text-v1.5"
export DENSE_DIM=768
export DENSE_DIM_LOW=64
export QUERY_INSTRUCTION="search_query: "
export DOCUMENT_PREFIX="search_document: "
export DA_ENABLED=true
export SPLADE_ENABLED=true
export HYDE_ENABLED=true

PY=.venv/bin/python
DATE=$(date +%Y-%m-%d)
LOG="logs/p1/step10/t0_run_${DATE}.txt"
: > "$LOG"

echo "===== 1. MUTATION RE-PROOF (hardened revision) =====" | tee -a "$LOG"
$PY /Users/bharathkumar/.hermes/cache/scratch/mut_t0f.py 2>&1 | tee -a "$LOG"
echo "mutation re-proof exit: ${PIPESTATUS[0]}" | tee -a "$LOG"

echo "===== 2. T0 — the full-funnel nomic baseline (133 queries) =====" | tee -a "$LOG"
echo "started: $(date -u +%Y-%m-%dT%H:%M:%SZ)" | tee -a "$LOG"
$PY logs/p1/step10/t0_baseline.py --out logs/p1/step10/t0_baseline.json 2>&1 | tee -a "$LOG"
echo "harness exit: ${PIPESTATUS[0]}" | tee -a "$LOG"

echo "===== 3. VERIFIER (V1-V5) =====" | tee -a "$LOG"
$PY logs/p1/step10/t0_verifier.py --check --extract 2>&1 | tee -a "$LOG"
echo "verifier exit: ${PIPESTATUS[0]}" | tee -a "$LOG"

echo "finished: $(date -u +%Y-%m-%dT%H:%M:%SZ)" | tee -a "$LOG"
