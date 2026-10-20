#!/usr/bin/env bash
# P1 Step 10 §2 — the ablation: funnel rerank ON vs OFF on the rebuilt index.
#
# Adapted from logs/p0-9/run_session4_v2.sh (plan §2: "adapt the existing harness, do not
# write a new one"). Changes:
#   * QDRANT_COLLECTION=knowledge_base_v2  (both scripts resolve the collection from
#     cfg.qdrant_collection, so this is the whole switch)
#   * artifacts go to logs/p1/step10/ so the p0-9 JSONs stay as the recorded baseline
#   * the SAME HyDE cache is reused (logs/p0-9/v2_hyde.json) — HyDE is per-query, not
#     per-index, so reusing it keeps the two arms paired; regenerating it would add an
#     LLM sample to the difference
#   * step 4 (evaluate_rag) is NOT here — deferred by decision (2026-10-18). It reads the
#     DA, graph and visual lanes, which are still the OLD document's; running it now would
#     produce numbers that are not about knowledge_base_v2. It resumes after Phase B/C/D.
#
# Pre-registered BEFORE any number exists:
#   .hermes/plans/2026-10-18-p1-step10-preregistration.md
# Decision rule: the reranker stays iff `rerank` beats `no-rerank` on R@20 by more than
# the 95% CI on the paired difference.
#
# Usage:  bash logs/p1/step10/run_step10_v2.sh
# ~3 min/arm with a warm HyDE cache.

set -euo pipefail

REPO="/Users/bharathkumar/repo/Support_Vectors/Beyond_RAG_Advanced_Agentic_Knowledge_Architectures/Project/Team_Project/pdf_ingestion"
cd "$REPO" || exit 1

# Hermes exports PYTHONPATH pointing at its own python3.14 site-packages; left in
# place it shadows the project venv's pydantic with an ABI-incompatible build
# (ModuleNotFoundError: pydantic_core._pydantic_core). Strip it for project runs.
unset PYTHONPATH
unset PYTHONHOME

export QDRANT_HOST=10.0.10.65
export QDRANT_COLLECTION=knowledge_base_v2

CACHE="logs/p0-9/v2_hyde.json"
OUT="logs/p1/step10"
QUERIES="data/eval_queries_v2.json"
mkdir -p "$OUT"

STEP="(startup)"
fail() {
    echo
    echo "############################################################"
    echo "!!! ABORTED — step failed: ${STEP}"
    echo "!!! (set -e is on; the next step was NOT run)"
    echo "############################################################"
    echo
}
trap 'fail' ERR

banner() { echo; echo "############ $* ############"; echo "### $(date '+%Y-%m-%d %H:%M:%S')"; echo; }

banner "RESOLVED SETTINGS (assert what is actually in force)"
uv run python - <<'PY'
from src.core.config import get_settings
c = get_settings()
print(f"  qdrant_collection : {c.qdrant_collection}")
print(f"  qdrant            : {c.qdrant_host or c.qdrant_url or c.qdrant_local_path}")
print(f"  dense lane        : {c.dense_model} ({c.dense_dim}d + {c.dense_dim_low}d)")
print(f"  reranker          : {c.reranker_model}  enabled={c.reranker_enabled}")
print(f"  splade/colbert    : {c.splade_enabled} / {c.colbert_enabled}")
print(f"  page bounds       : [{c.min_content_page}, {c.max_content_page}]")
assert c.qdrant_collection == "knowledge_base_v2", f"collection is {c.qdrant_collection}"
assert c.reranker_enabled, "reranker_enabled is False — the ON arm would not rerank"
assert c.splade_enabled and c.colbert_enabled, "a lane the funnel needs is disabled"
print("  ASSERTIONS OK")
PY

STEP="STEP 1/3  funnel — rerank ON"
banner "$STEP"
uv run python scripts/funnel_boundary_recall.py \
    --queries "$QUERIES" \
    --hyde --hyde-cache "$CACHE" --merge rrf3 \
    --json "$OUT/v2_rerank.json"

STEP="STEP 2/3  funnel — rerank OFF  (same HyDE cache)"
banner "$STEP"
uv run python scripts/funnel_boundary_recall.py \
    --queries "$QUERIES" \
    --hyde --hyde-cache "$CACHE" --merge rrf3 --no-reranker \
    --json "$OUT/v2_norerank.json"

STEP="STEP 3/3  required_n — the powered decision"
banner "$STEP"
uv run python scripts/required_n.py \
    "$OUT/v2_rerank.json" "$OUT/v2_norerank.json" \
    --queries "$QUERIES" --delta 0.05

STEP="(done)"
banner "DONE — now run the arm verifier"
echo "  uv run python logs/p1/step10/check_ab_arms.py"
ls -la "$OUT"/v2_*.json 2>/dev/null || true
