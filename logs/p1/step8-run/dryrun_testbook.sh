#!/usr/bin/env bash
# Step 8 dry run (R-b): the EXACT Step 8 entry point on the 19-page fixture.
#
# Proves the whole write path against the real cluster before the 968-page run, and
# times the small book so the full run can be estimated.
#
# Safety: writes to a THROWAWAY collection (knowledge_base_probe) and a scratch SQLite
# (data/step8_probe.db) — the deployed `knowledge_base` and data/synapse.db are untouched.
# R-d: the real run goes to a fresh collection so a failure leaves the old index intact.
#
# Run:  bash logs/p1/step8-run/dryrun_testbook.sh
set -euo pipefail
cd "$(dirname "$0")/../../.."

export QDRANT_HOST=10.0.10.65
export SV_EMBED_URL=http://10.0.10.70:8123/embed-text/v1/embeddings
export SQLITE_URL="sqlite:///./data/step8_probe.db"

rm -f data/step8_probe.db
curl -s -X DELETE http://10.0.10.65:6333/collections/knowledge_base_probe > /dev/null || true

echo "=== env ==="
echo "QDRANT_HOST=$QDRANT_HOST  SV_EMBED_URL=$SV_EMBED_URL  SQLITE_URL=$SQLITE_URL"

echo "=== ingest (timed) ==="
/usr/bin/time -l uv run python scripts/ingest_base_textbook.py \
    --pdf data/base_textbooks/test_book.pdf \
    --collection-name knowledge_base_probe \
    --title "Test Book (Step 8 dry run)" \
    --subject Physics \
    --grade Undergraduate

echo "=== done ==="
