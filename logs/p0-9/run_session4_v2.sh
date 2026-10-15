#!/usr/bin/env bash
# P0-9 Session 4 — the v2 A/B (rerank vs no-rerank) + the judge harness.
#
# Pre-registered BEFORE any numbers exist:
#   .hermes/plans/2026-10-14-p0-9-4-preregistration.md
# Decision rule: the reranker stays iff `rerank` beats `no-rerank` on R@20 by more than
# the 95% CI on the paired difference. Abstention must beat the majority baseline.
#
# Scope: the funnel is a TEXT-lane measurement, so it excludes the 33 visual queries
# (default) and runs on the 135 text queries. The visual lane and the 34 negatives are
# measured by evaluate_rag.py.
#
# Usage:  bash logs/p0-9/run_session4_v2.sh
# Run it in the BACKGROUND; it is ~30-60 min of cluster calls.

set -uo pipefail

REPO="/Users/bharathkumar/repo/Support_Vectors/Beyond_RAG_Advanced_Agentic_Knowledge_Architectures/Project/Team_Project/pdf_ingestion"
cd "$REPO" || exit 1

# The cluster index (5,135 points). The local data/qdrant is a different, older ingest.
export QDRANT_HOST=10.0.10.65

CACHE="logs/p0-9/v2_hyde.json"          # shared: the A/B must compare lanes, not two LLM samples
OUT="logs/p0-9"
mkdir -p "$OUT"

JUDGE=(--judge-backend openai --judge-api-base http://10.0.10.70:8000 \
       --judge-model Qwen/Qwen3-VL-8B-Instruct)

banner() { echo; echo "############ $* ############"; echo "### $(date '+%Y-%m-%d %H:%M:%S')"; echo; }

banner "STEP 1/4  funnel — rerank ON"
uv run python scripts/funnel_boundary_recall.py \
    --queries data/eval_queries_v2.json \
    --hyde --hyde-cache "$CACHE" --merge rrf3 \
    --json "$OUT/v2_rerank.json"
echo "rc=$?"

banner "STEP 2/4  funnel — rerank OFF  (same HyDE cache)"
uv run python scripts/funnel_boundary_recall.py \
    --queries data/eval_queries_v2.json \
    --hyde --hyde-cache "$CACHE" --merge rrf3 --no-reranker \
    --json "$OUT/v2_norerank.json"
echo "rc=$?"

banner "STEP 3/4  required_n — the powered decision"
uv run python scripts/required_n.py \
    "$OUT/v2_rerank.json" "$OUT/v2_norerank.json" --delta 0.05
echo "rc=$?"

banner "STEP 4/4  evaluate_rag — generation metrics + abstention (judge = Qwen3-VL-8B)"
# Judge is cross-family from the generator (gpt-oss-20b). --judge-from-env would fall back
# to the generator when JUDGE_MODEL is unset — self-grading, which the plan forbids.
uv run python scripts/evaluate_rag.py \
    --query-file data/eval_queries_v2.json \
    --run-name p0-9-gold-v2 --tenant global \
    "${JUDGE[@]}"
echo "rc=$?"

banner "DONE"
ls -la "$OUT"/v2_*.json 2>/dev/null
