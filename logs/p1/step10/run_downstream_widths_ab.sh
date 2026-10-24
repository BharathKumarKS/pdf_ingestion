#!/usr/bin/env bash
# §I66 — the pre-registered A/B on the downstream widths (the fusion output W, the re-score cut L),
# on the product retrieval path.
#
# Pre-registration: .hermes/plans/2026-10-23-p1-downstream-widths-ab-preregistration.md
# Usage: bash logs/p1/step10/run_downstream_widths_ab.sh
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

echo "=== §I66 downstream-widths A/B — settings gate ==="
echo "QDRANT_HOST       = $QDRANT_HOST"
echo "QDRANT_COLLECTION = $QDRANT_COLLECTION"

[ "$QDRANT_COLLECTION" = "knowledge_base_v2" ] || { echo "REFUSING: collection != knowledge_base_v2"; exit 2; }
[ -n "$QDRANT_HOST" ]                          || { echo "REFUSING: QDRANT_HOST blank -> local store"; exit 2; }

uv run python - <<'PY'
from src.core.config import get_settings
c = get_settings()
print("resolved collection          :", c.qdrant_collection)
print("resolved qdrant_host         :", c.qdrant_host or "(local embedded)")
print("resolved mmr_candidates      :", c.mmr_candidates, " <- W's feed; control arm must run 100")
print("resolved reranker_fetch_k    :", c.reranker_fetch_k, " <- W's clip; control arm must run 100")
print("resolved dense_rescore_limit :", c.dense_rescore_limit, " <- L; control arm must run 500")
print("resolved da_fetch_k          :", c.da_fetch_k, " <- DA lane; pinned at 100 in every arm")
print("resolved dense_prefetch_limit:", c.dense_prefetch_limit, " <- shipped 1000; arms pin 2000")
print("resolved reranker_top_k      :", c.reranker_top_k)
assert c.qdrant_collection == "knowledge_base_v2", "wrong collection resolved"
assert c.qdrant_host, "qdrant_host blank -> would target the local store"
# The control arm must BE the shipped configuration. If a `.env` line overrode any of these, arm C is
# not the production configuration and the A/B answers a different question (§I52 / §I23's trap).
assert (c.mmr_candidates, c.reranker_fetch_k, c.dense_rescore_limit, c.da_fetch_k) == (100, 100, 500, 100), (
    f"the control width/cut resolved to "
    f"{(c.mmr_candidates, c.reranker_fetch_k, c.dense_rescore_limit, c.da_fetch_k)}, "
    "not the shipped (100, 100, 500, 100) — arm C would not be the production arm")
print("GATE PASS")
PY

OUT="logs/p1/step10/downstream_widths_run_$(date +%Y-%m-%d_%H%M).txt"
echo "=== run -> $OUT ==="

uv run python logs/p1/step10/downstream_widths_ab.py 2>&1 | tee "$OUT"
