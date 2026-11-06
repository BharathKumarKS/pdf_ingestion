#!/usr/bin/env bash
# §I105/§I106's open reading: does the generator's OVERVIEW faithfulness improve at k=50 vs k=20?
# Pre-registration: .hermes/plans/2026-11-02-p1-overview-k50-generator-preregistration.md (committed alone).
set -u
REPO=/Users/bharathkumar/repo/Support_Vectors/Beyond_RAG_Advanced_Agentic_Knowledge_Architectures/Project/Team_Project/pdf_ingestion
cd "$REPO"
unset PYTHONPATH
export QDRANT_HOST=10.0.10.65 QDRANT_COLLECTION=knowledge_base_v3
export DENSE_MODEL="nomic-ai/nomic-embed-text-v1.5" DENSE_DIM=768 DENSE_DIM_LOW=64
export DOCUMENT_PREFIX="search_document: " QUERY_INSTRUCTION="search_query: " DA_ENABLED=true
export RERANKER_TOP_K=50
.venv/bin/python scripts/evaluate_rag.py \
  --query-file data/eval_queries_overview.json --skip-visual \
  --judge-backend openai --judge-api-base http://10.0.10.70:8000/v1 \
  --judge-api-key dummy --judge-model Qwen/Qwen3-VL-8B-Instruct \
  --run-name overview_k50 --output-dir data/eval_results
