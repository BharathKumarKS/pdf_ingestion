#!/usr/bin/env bash
# Phase E — the authoritative FULL evaluate_rag.py run (retrieval + synthesis + judge) against
# the rebuilt index, knowledge_base_v2.
#
# Pre-registration: .hermes/plans/2026-10-22-p1-phaseE-preregistration.md
# Usage: bash logs/p1/step10/run_phaseE.sh
#
# Why the explicit exports: `.env` leaves QDRANT_HOST blank, so the default is the LOCAL embedded
# Qdrant — a run without the override silently targets the wrong store (§I49 Finding 1). And
# JUDGE_MODEL is unset in `.env`, so `--judge-from-env` would fall back to the GENERATOR, i.e. the
# generator grading itself. Both are asserted below before anything is spent.
set -euo pipefail

cd "$(dirname "$0")/../../.."     # logs/p1/step10 -> repo root

export QDRANT_HOST=10.0.10.65
export QDRANT_COLLECTION=knowledge_base_v2
export JUDGE_MODEL=Qwen/Qwen3-VL-8B-Instruct
unset PYTHONPATH 2>/dev/null || true

echo "=== Phase E settings gate ==="
echo "QDRANT_HOST       = $QDRANT_HOST"
echo "QDRANT_COLLECTION = $QDRANT_COLLECTION"
echo "JUDGE_MODEL       = $JUDGE_MODEL"

[ "$QDRANT_COLLECTION" = "knowledge_base_v2" ] || { echo "REFUSING: collection != knowledge_base_v2"; exit 2; }
[ -n "$QDRANT_HOST" ]                          || { echo "REFUSING: QDRANT_HOST blank -> local store"; exit 2; }

# Assert the RESOLVED settings, not the exported ones — a `.env` line can override an export and
# the log must name what actually runs (§I52: measure the model the phase runs).
uv run python - <<'PY'
from src.core.config import get_settings
c = get_settings()
print("resolved collection :", c.qdrant_collection)
print("resolved qdrant_host:", c.qdrant_host or "(local embedded)")
print("generator model     :", c.openai_model)
print("judge model         :", c.judge_model or "(UNSET -> judge would be the generator)")
assert c.qdrant_collection == "knowledge_base_v2", "wrong collection resolved"
assert c.qdrant_host, "qdrant_host blank -> would target the local store"
assert c.judge_model, "judge_model unset -> the generator would grade itself"
assert c.judge_model != c.openai_model, "judge must be cross-family from the generator"
print("GATE PASS")
PY

OUT="logs/p1/step10/phaseE_run_$(date +%Y-%m-%d_%H%M).txt"
echo "=== Phase E run -> $OUT ==="

uv run python scripts/evaluate_rag.py \
  --query-file data/eval_queries_v2.json \
  --run-name p1-phaseE-v2 \
  --judge-from-env \
  --skip-visual \
  --tenant global \
  2>&1 | tee "$OUT"
