#!/usr/bin/env bash
# Phase B (Step 9) — generate cards + RAPTOR for the re-ingested document.
#
#   bash logs/p1/step10/run_phaseb.sh [expected_workers]
#
# expected_workers defaults to 2 (= 2 x 8 card types = 16 effective LLM concurrency, the
# owner-approved option (b), 2026-10-19). Pass a higher number ONLY after measuring sustained
# throughput at the current one — §I18's rule: concurrency is not raised without sustained-load
# evidence, and this endpoint has degraded under load twice (§I18, §I23).
#
# The gate asserts what is ACTUALLY in force. `.env` overrode config.py's default of 4 with 8
# once already and made Step 8 attempt 3 run at the wrong worker count while everyone believed 4.
set -uo pipefail

REPO="/Users/bharathkumar/repo/Support_Vectors/Beyond_RAG_Advanced_Agentic_Knowledge_Architectures/Project/Team_Project/pdf_ingestion"
cd "$REPO" || exit 1

# Hermes exports PYTHONPATH pointing at its own python3.14 site-packages; left in place it shadows
# the project venv's pydantic with an ABI-incompatible build.
unset PYTHONPATH
unset PYTHONHOME

export QDRANT_HOST=10.0.10.65
export QDRANT_COLLECTION=knowledge_base_v2

DOC_ID="7ba61432-c5e0-416d-aecf-25a232523481"
EXPECTED_WORKERS="${1:-2}"
OUT="logs/p1/step10"
mkdir -p "$OUT"

STEP="(startup)"
fail() {
    echo
    echo "############################################################"
    echo "!!! ABORTED — step failed: ${STEP}"
    echo "############################################################"
    echo
}
trap 'fail' ERR

banner() { echo; echo "############ $* ############"; echo "### $(date '+%Y-%m-%d %H:%M:%S')"; echo; }

banner "B0 — RESOLVED SETTINGS GATE (assert what is actually in force)"
EXPECTED_WORKERS="$EXPECTED_WORKERS" uv run python - <<'PY'
import os
from src.core.config import get_settings
from src.pdf_ingestion.card_generator import CardType

c = get_settings()
expected = int(os.environ["EXPECTED_WORKERS"])
n_types = len(CardType)
print(f"  qdrant_collection   : {c.qdrant_collection}")
print(f"  qdrant              : {c.qdrant_host or c.qdrant_url or c.qdrant_local_path}")
print(f"  card_gen_workers    : {c.card_gen_workers}  (expected {expected})")
print(f"  card types          : {n_types}")
print(f"  effective concurrency: {c.card_gen_workers * n_types}")
print(f"  llm                 : {c.llm_backend} {c.openai_api_base} {c.openai_model}")
print(f"  dense lane          : {c.dense_model} ({c.dense_dim}d)")
print(f"  stubs e/l/g         : {c.use_stub_embedder} / {c.use_stub_llm} / {c.use_stub_graph}")

assert c.qdrant_collection == "knowledge_base_v2", f"collection is {c.qdrant_collection!r}"
assert c.qdrant_host == "10.0.10.65", f"qdrant_host is {c.qdrant_host!r}"
assert c.card_gen_workers == expected, (
    f"card_gen_workers is {c.card_gen_workers}, expected {expected} — check .env "
    "(CARD_GEN_WORKERS) before spending hours of cluster time")
assert not (c.use_stub_embedder or c.use_stub_llm or c.use_stub_graph), "a stub is enabled"
print("  ASSERTIONS OK")
PY

banner "B3 — the run (cards + RAPTOR) for $DOC_ID"
echo "  started : $(date '+%Y-%m-%d %H:%M:%S')"
echo "  log     : $OUT/phaseb_run.log"
START=$(date +%s)
uv run python scripts/run_phase2.py --doc-id "$DOC_ID"
END=$(date +%s)
echo "  finished: $(date '+%Y-%m-%d %H:%M:%S')"
echo "  wall    : $(( (END - START) / 60 )) min $(( (END - START) % 60 )) s"

STEP="(done)"
banner "DONE — now run the verifiers"
echo "  uv run python logs/p1/step10/verify_phaseb_cards.py"
echo "  uv run python logs/p1/step10/verify_phaseb_raptor.py"
