#!/usr/bin/env bash
# P1 Step 10 — prerequisite: rebuild the Memgraph concept graph for the
# re-ingested document, so preflight's graph.matches-qdrant check can pass
# (IMPROVEMENTS.md §D14, cause 2).
#
# This is the graph half of Step 9, pulled forward by owner decision
# (2026-10-18) because Step 10 §1's gate cannot pass without it.
#
#   doc 7ba61432-c5e0-416d-aecf-25a232523481 = the Step 8 re-ingest
#   (knowledge_base_v2, 3,796 chunks). The graph currently holds only
#   6d55c52b (the previous ingest, 5,048 chunks) -> 100% dangling.
#
# --graph-only  => skip ColPali entirely; force_graph=True rebuilds the graph.
#                  GraphBuilder.build_graph MERGEs by id, so re-running is
#                  idempotent for this document.
#
# NOT DONE HERE: removing the OLD document's graph nodes. That is
# clean_stale_graph.py and it is destructive to the currently-deployed
# knowledge_base's graph — an owner decision, deliberately not automated.
#
# Usage:  bash logs/p1/step10/run_graph.sh

set -euo pipefail

REPO="/Users/bharathkumar/repo/Support_Vectors/Beyond_RAG_Advanced_Agentic_Knowledge_Architectures/Project/Team_Project/pdf_ingestion"
cd "$REPO" || exit 1

export QDRANT_HOST=10.0.10.65
export QDRANT_COLLECTION=knowledge_base_v2

DOC_ID="7ba61432-c5e0-416d-aecf-25a232523481"
OUT="logs/p1/step10"
LOG="$OUT/graph_build.log"
mkdir -p "$OUT"

banner() { echo; echo "############ $* ############"; echo "### $(date '+%Y-%m-%d %H:%M:%S')"; echo; }

STEP="(startup)"
fail() {
    echo
    echo "############################################################"
    echo "!!! ABORTED — step failed: ${STEP}"
    echo "############################################################"
    echo
}
trap 'fail' ERR

banner "RESOLVED SETTINGS (assert what is actually in force)"
uv run python - <<'PY'
from src.core.config import get_settings
c = get_settings()
print(f"  qdrant            : {c.qdrant_host or c.qdrant_url or c.qdrant_local_path}")
print(f"  qdrant_collection : {c.qdrant_collection}")
print(f"  memgraph          : {c.memgraph_host}:{c.memgraph_port}")
print(f"  llm_backend       : {c.llm_backend}")
print(f"  openai_model      : {c.openai_model} @ {c.openai_api_base}")
print(f"  concept_gen_workers: {c.concept_gen_workers}")
print(f"  legacy embedder   : {c.embedding_model} ({c.embedding_dim}d)  <- concept names")
print(f"  stubs             : embedder={c.use_stub_embedder} graph={c.use_stub_graph} llm={c.use_stub_llm}")
assert c.memgraph_host and c.memgraph_port, "memgraph not configured"
assert not c.use_stub_graph, "use_stub_graph is ON — the graph would be a stub"
assert not c.use_stub_llm, "use_stub_llm is ON — concept extraction would be a stub"
assert not c.use_stub_embedder, "use_stub_embedder is ON — concept vectors would be random"
print("  ASSERTIONS OK")
PY

STEP="graph build — doc $DOC_ID"
banner "$STEP"
uv run python scripts/run_phase3.py --doc-id "$DOC_ID" --graph-only

STEP="(done)"
banner "DONE"
