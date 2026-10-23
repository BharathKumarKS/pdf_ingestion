#!/usr/bin/env bash
# §I61 — the pre-registered A/B on the 64d prefetch limit, on the product retrieval path.
#
# Pre-registration: .hermes/plans/2026-10-23-p1-i61-prefetch-limit-ab-preregistration.md
# Usage: bash logs/p1/step10/run_prefetch_ab.sh
#
# Why the explicit exports: `.env` leaves QDRANT_HOST blank, so the default is the LOCAL embedded
# Qdrant — a run without the override silently targets the wrong store (§I49 Finding 1) and every
# number would be about a different corpus. The gate below asserts the RESOLVED values, not the
# exported ones (§I52: measure the store the run actually uses).
set -euo pipefail

cd "$(dirname "$0")/../../.."     # logs/p1/step10 -> repo root

export QDRANT_HOST=10.0.10.65
export QDRANT_COLLECTION=knowledge_base_v2
unset PYTHONPATH 2>/dev/null || true

echo "=== §I61 prefetch-limit A/B — settings gate ==="
echo "QDRANT_HOST       = $QDRANT_HOST"
echo "QDRANT_COLLECTION = $QDRANT_COLLECTION"

[ "$QDRANT_COLLECTION" = "knowledge_base_v2" ] || { echo "REFUSING: collection != knowledge_base_v2"; exit 2; }
[ -n "$QDRANT_HOST" ]                          || { echo "REFUSING: QDRANT_HOST blank -> local store"; exit 2; }

uv run python - <<'PY'
from src.core.config import get_settings
c = get_settings()
print("resolved collection       :", c.qdrant_collection)
print("resolved qdrant_host      :", c.qdrant_host or "(local embedded)")
print("resolved dense_prefetch_limit:", c.dense_prefetch_limit, " <- the SHIPPED value; arm C must run it")
print("resolved reranker_fetch_k :", c.reranker_fetch_k)
print("resolved reranker_top_k   :", c.reranker_top_k)
print("resolved mmr_candidates   :", c.mmr_candidates)
print("resolved dense_dim_low    :", c.dense_dim_low)
print("resolved da_enabled       :", c.da_enabled)
assert c.qdrant_collection == "knowledge_base_v2", "wrong collection resolved"
assert c.qdrant_host, "qdrant_host blank -> would target the local store"
# The control arm must BE the shipped value. If a `.env` line overrode it, arm C is not the
# production configuration and the A/B answers a different question (§I52 / §I23's trap).
assert c.dense_prefetch_limit == 1000, (
    f"dense_prefetch_limit resolved to {c.dense_prefetch_limit}, not the shipped 1000 — "
    "arm C would not be the production arm")
print("GATE PASS")
PY

OUT="logs/p1/step10/prefetch_ab_run_$(date +%Y-%m-%d_%H%M).txt"
echo "=== run -> $OUT ==="

uv run python logs/p1/step10/prefetch_limit_ab.py 2>&1 | tee "$OUT"
