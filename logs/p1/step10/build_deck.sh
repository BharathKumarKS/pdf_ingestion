#!/usr/bin/env bash
# Rebuild every deck artifact from one command, so the PDF never drifts from the PPTX/MD.
#   1. deck PDF   (13 slides)                     -> logs/p1/step10/demo_deck.pdf
#   2. merge the 2 architecture pages into it      -> demo_deck.pdf (15 pages)
#   3. deck PPTX  (13 slides + 2 architecture)     -> logs/p1/step10/demo_deck.pptx
# The architecture itself: Docs/synapse_architecture_v2.html (+ .pdf, rendered by headless Chrome).
set -eu
REPO=/Users/bharathkumar/repo/Support_Vectors/Beyond_RAG_Advanced_Agentic_Knowledge_Architectures/Project/Team_Project/pdf_ingestion
cd "$REPO"
unset PYTHONPATH

echo "== 1/3 deck PDF =="
.venv/bin/python logs/p1/step10/make_demo_deck_pdf.py

echo "== 2/3 merge architecture into the PDF =="
uv run --quiet --with pypdf python logs/p1/step10/merge_arch_into_deck.py

echo "== 3/3 deck PPTX =="
.venv/bin/python logs/p1/step10/make_demo_deck.py

echo "== done =="
ls -la logs/p1/step10/demo_deck.pdf logs/p1/step10/demo_deck.pptx logs/p1/step10/demo_deck.md
