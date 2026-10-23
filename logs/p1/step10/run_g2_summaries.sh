#!/usr/bin/env bash
# §G2 — build the Leiden community summaries for doc 7ba61432 (the §I21-filtered, §G3-merged graph).
#
#   bash logs/p1/step10/run_g2_summaries.sh            # writes the artifact + a log
#
# WHY THIS IS A SCRIPT AND NOT A ONE-LINER:
#   * `QDRANT_HOST` is BLANK in `.env`, so the default resolves to the LOCAL embedded store. Every
#     §I12/§G2/§G3 command must carry the override or it silently targets the wrong store (§I49
#     Finding 1). The override is asserted below, not assumed.
#   * The summariser is `cfg.openai_model` (`openai/gpt-oss-20b`, 131,072-token context) — NOT the
#     graph build's extractor (`Qwen/Qwen3-VL-8B-Instruct`, 15,000). Printed here so the log names
#     the model that actually produced the summaries.
#   * The seed MUST match `g2_leiden_gate.py`'s SEED (20261020) or the communities summarised are
#     not the communities the gate approved (§I50 Finding 4).
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
cd "$REPO"
unset PYTHONPATH

DOC_ID="7ba61432-c5e0-416d-aecf-25a232523481"
OUT="logs/p1/step10/g2_summaries_2026-10-22.json"
LOG="logs/p1/step10/g2_summaries_2026-10-22.log"

export QDRANT_HOST=10.0.10.65
export QDRANT_COLLECTION=knowledge_base_v2

{
  echo "# cmd: QDRANT_HOST=$QDRANT_HOST QDRANT_COLLECTION=$QDRANT_COLLECTION uv run python \\"
  echo "#        scripts/build_community_summaries.py --doc-id $DOC_ID --yes --out $OUT"
  echo "# started: $(date -u +%FT%TZ)  (local: $(date))"
  echo "# repo: $REPO"
  echo "# summariser: cfg.openai_model from .env = $(grep -E '^OPENAI_MODEL=' .env | head -1)"
  echo "# extractor (NOT used here): $(grep -A1 '^concept_extraction:' config.yaml | tail -1)"
  echo
} >> "$LOG"

[ "$QDRANT_HOST" = "10.0.10.65" ] || { echo "ABORT: wrong Qdrant host"; exit 2; }

uv run python scripts/build_community_summaries.py \
  --doc-id "$DOC_ID" --yes --out "$OUT" >> "$LOG" 2>&1
rc=$?
echo "# exit: $rc  finished: $(date -u +%FT%TZ)" >> "$LOG"
exit $rc
