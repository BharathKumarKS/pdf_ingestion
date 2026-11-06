#!/usr/bin/env bash
# T0 — the FULL-FUNNEL nomic baseline + the aperture sweep. Read-only, no writes, no LLM (HyDE frozen).
# Pre-registration: .hermes/plans/2026-10-27-p1-t0-baseline-preregistration.md (committed ALONE first).
#
# ⚠️ ONE arm, and it is the PRODUCT's own lane set: DA **ON** and the graph lane **ON** — unlike
# Stage F/G, which forced both OFF because a 1024-dim arm cannot query the 768-dim derived
# collections. T0 is nomic/768, so both derived lanes are live against their own space.
#
# The A2 `.env` flip is NOT applied, so every per-arm value is exported here and ASSERTED inside the
# harness (G1). Forget one and the run silently uses Qwen3/1024 against the wrong collection (§I80).
set -euo pipefail
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

DATE=$(date +%Y-%m-%d)
LOG="logs/p1/step10/t0_run_${DATE}.txt"
: > "$LOG"

echo "===== T0 — the full-funnel nomic baseline =====" | tee -a "$LOG"
echo "started: $(date -u +%Y-%m-%dT%H:%M:%SZ)" | tee -a "$LOG"

# ⚠️ `.venv/bin/python`, NOT `uv run`: `uv run` takes a lock on the project environment, and other
# sessions' uv processes holding it turned a ~1-minute harness run into a multi-minute wait.
PY=.venv/bin/python

$PY logs/p1/step10/t0_baseline.py --out logs/p1/step10/t0_baseline.json 2>&1 | tee -a "$LOG"

echo "===== VERIFIER (V1-V5) =====" | tee -a "$LOG"
$PY logs/p1/step10/t0_verifier.py --check --extract 2>&1 | tee -a "$LOG"

echo "finished: $(date -u +%Y-%m-%dT%H:%M:%SZ)" | tee -a "$LOG"
