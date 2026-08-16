#!/usr/bin/env python3
"""Generate a project overview PDF for Synapse Learning Worlds."""
from __future__ import annotations

import math
from datetime import date

from fpdf import FPDF
from fpdf.enums import XPos, YPos

PAGE_W = 174  # A4 210mm - 18mm margins * 2


class ReportPDF(FPDF):
    def header(self):
        self.set_font("Helvetica", "B", 9)
        self.set_text_color(120, 120, 120)
        self.cell(0, 8, "Synapse Learning Worlds - Project Report", align="L")
        self.ln(2)
        self.set_draw_color(200, 200, 200)
        self.set_line_width(0.3)
        self.line(self.l_margin, self.get_y(), self.w - self.r_margin, self.get_y())
        self.ln(4)
        self.set_text_color(0, 0, 0)

    def footer(self):
        self.set_y(-14)
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(150, 150, 150)
        self.cell(0, 8, f"Page {self.page_no()} | Confidential", align="C")

    def h1(self, text: str):
        self.set_font("Helvetica", "B", 16)
        self.set_text_color(30, 60, 120)
        self.ln(4)
        self.cell(0, 10, text, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_draw_color(30, 60, 120)
        self.set_line_width(0.5)
        self.line(self.l_margin, self.get_y(), self.w - self.r_margin, self.get_y())
        self.ln(4)
        self.set_text_color(0, 0, 0)

    def h2(self, text: str):
        self.ln(3)
        self.set_font("Helvetica", "B", 12)
        self.set_text_color(50, 90, 160)
        self.cell(0, 8, text, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_text_color(0, 0, 0)
        self.ln(1)

    def h3(self, text: str):
        self.ln(2)
        self.set_font("Helvetica", "B", 10)
        self.set_text_color(80, 80, 80)
        self.cell(0, 7, text, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_text_color(0, 0, 0)

    def body(self, text: str, indent: int = 0):
        self.set_font("Helvetica", "", 10)
        self.set_x(self.l_margin + indent)
        self.multi_cell(PAGE_W - indent, 5.5, text, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.ln(1)

    def bullet(self, text: str, indent: int = 5):
        self.set_font("Helvetica", "", 10)
        self.set_x(self.l_margin + indent)
        self.cell(5, 5.5, "-")
        self.set_x(self.l_margin + indent + 5)
        self.multi_cell(PAGE_W - indent - 5, 5.5, text, new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    def decision_box(self, decision: str, reason: str):
        """Blue decision box: write text with fill=True, then draw border outline."""
        self.set_fill_color(235, 242, 255)
        x = self.l_margin
        y = self.get_y()
        self.set_font("Helvetica", "B", 9)
        self.set_x(x + 3)
        self.multi_cell(PAGE_W - 6, 5.2, f"Decision: {decision}",
                        fill=True, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_font("Helvetica", "", 9)
        self.set_x(x + 3)
        self.multi_cell(PAGE_W - 6, 5.2, f"Reason: {reason}",
                        fill=True, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_draw_color(160, 190, 230)
        self.set_line_width(0.4)
        self.rect(x, y, PAGE_W, self.get_y() - y, style="D")
        self.ln(3)

    def warning_box(self, text: str):
        """Yellow warning box: write text with fill=True, then draw border outline."""
        self.set_fill_color(255, 248, 225)
        x = self.l_margin
        y = self.get_y()
        self.set_font("Helvetica", "B", 9)
        self.set_x(x + 3)
        self.multi_cell(PAGE_W - 6, 5.2, f"Note: {text}",
                        fill=True, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_draw_color(210, 160, 50)
        self.set_line_width(0.4)
        self.rect(x, y, PAGE_W, self.get_y() - y, style="D")
        self.ln(3)

    def table_row(self, cols: list[str], widths: list[int], bold: bool = False,
                  line_h: float = 5.5):
        """Multi-line table row: each cell wraps text without overflowing."""
        style = "B" if bold else ""
        self.set_font("Helvetica", style, 9)
        # Calculate max height needed across all cells
        max_lines = 1
        for text, w in zip(cols, widths):
            sw = self.get_string_width(text)
            lines = math.ceil(sw / max(w - 3, 1)) + 1
            max_lines = max(max_lines, lines)
        row_h = max_lines * line_h
        x_start = self.l_margin
        y_start = self.get_y()
        for text, w in zip(cols, widths):
            self.set_xy(x_start, y_start)
            self.multi_cell(w, line_h, text, border=1,
                            new_x=XPos.RIGHT, new_y=YPos.TOP)
            x_start += w
        self.set_y(y_start + row_h)

    def code(self, text: str):
        self.set_font("Courier", "", 8)
        self.set_fill_color(245, 245, 245)
        lines = text.strip().split("\n")
        for line in lines:
            self.set_x(self.l_margin)
            self.cell(PAGE_W, 5, line, border=0, fill=True,
                      new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.ln(2)

    def phase_block(self, title: str, subtitle: str, desc: str):
        self.set_font("Helvetica", "B", 10)
        self.set_fill_color(245, 248, 255)
        self.set_x(self.l_margin)
        self.cell(PAGE_W, 6, f"  {title}", fill=True, border=1,
                  new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_font("Helvetica", "I", 9)
        self.set_x(self.l_margin + 4)
        self.cell(PAGE_W - 4, 5.5, subtitle, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_font("Helvetica", "", 9)
        self.set_x(self.l_margin + 4)
        self.multi_cell(PAGE_W - 4, 5, desc, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.ln(1)


def build_pdf(output_path: str):
    pdf = ReportPDF(orientation="P", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=18)
    pdf.set_margins(18, 22, 18)
    pdf.add_page()

    # ── Title page ─────────────────────────────────────────────────────────
    pdf.ln(20)
    pdf.set_font("Helvetica", "B", 26)
    pdf.set_text_color(30, 60, 120)
    pdf.cell(0, 12, "Synapse Learning Worlds", align="C",
             new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_font("Helvetica", "", 14)
    pdf.set_text_color(80, 80, 80)
    pdf.cell(0, 8, "Hybrid RAG Platform - Project Overview & Roadmap", align="C",
             new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(6)
    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(120, 120, 120)
    pdf.cell(0, 6, f"Generated: {date.today().strftime('%B %d, %Y')}", align="C",
             new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_text_color(0, 0, 0)
    pdf.ln(12)
    pdf.set_draw_color(30, 60, 120)
    pdf.set_line_width(0.8)
    pdf.line(pdf.l_margin, pdf.get_y(), pdf.w - pdf.r_margin, pdf.get_y())
    pdf.ln(10)
    pdf.set_font("Helvetica", "", 11)
    pdf.body(
        "This document provides a comprehensive overview of the Synapse Learning Worlds "
        "platform - a Hybrid Retrieval-Augmented Generation (RAG) system built for physics "
        "education. It covers architecture decisions across four implementation phases, "
        "an honest assessment of the current intent routing system, and the roadmap for "
        "upgrading to a data-driven classifier."
    )

    # ── Section 1 ──────────────────────────────────────────────────────────
    pdf.add_page()
    pdf.h1("1. What We Built")
    pdf.body(
        "Synapse Learning Worlds is a multi-tenant, multi-modal RAG platform that goes "
        "beyond simple vector search. It combines dense embeddings, sparse lexical search, "
        "hierarchical summaries, concept graphs, visual page retrieval, and LLM synthesis "
        "to deliver high-quality, grounded answers to physics students."
    )

    pdf.h2("1.1 System Architecture - Four Phases")
    pdf.phase_block(
        "Phase 1 - Foundation", "Parse -> Chunk -> Embed -> Store",
        "Docling PDF parser, Chonkie semantic chunker, Jina v3 embedder (1024-dim), "
        "Qdrant vector store, SQLite for metadata and multi-tenancy."
    )
    pdf.phase_block(
        "Phase 2 - Pedagogical Layer", "Cards + RAPTOR Hierarchical Summaries",
        "LLM-generated learning cards (conditional on content - formula only when equation "
        "present). RAPTOR clusters chunks, summarizes each cluster via LLM, embeds summaries "
        "into Qdrant for multi-granularity retrieval."
    )
    pdf.phase_block(
        "Phase 3 - Visual + Graph Layer", "ColPali + Memgraph Concept Graph",
        "ColPali (PaliGemma backbone) rasterizes PDF pages, creates patch embeddings stored "
        "with MaxSim in Qdrant. Memgraph stores concept nodes and relationships. "
        "Qdrant concept_embeddings enables fast (~1ms) ANN concept lookup."
    )
    pdf.phase_block(
        "Phase 4 - Adaptive Retrieval", "Intent Router + SPLADE + Cross-Encoder Re-ranker",
        "Prototype-based intent routing (zero-shot, zero latency). SPLADE sparse embeddings "
        "fused with dense via RRF. Cross-encoder MiniLM re-ranks top-20 to top-6. "
        "LLM synthesizes grounded answers with page citations."
    )

    pdf.h2("1.2 Query-Time Retrieval Flow")
    pdf.code(
        "query text\n"
        "  -> Jina v3 embed (q_vec, 1024-dim)\n"
        "  -> Intent router: classify as factual / overview / multihop / visual / mixed\n"
        "  -> Qdrant hybrid search: dense (Jina) + sparse (SPLADE) -> RRF -> top-20\n"
        "  -> Cross-encoder re-rank (MiniLM-L-6) -> top-6 chunks\n"
        "  -> [overview]  RAPTOR search -> 2 cluster summaries\n"
        "  -> [multihop]  Qdrant concept ANN -> Memgraph traversal -> graph chunks\n"
        "  -> [visual]    ColPali MaxSim search -> matching page images\n"
        "  -> LLM synthesis: grounded answer with page citations\n"
        "  -> Sources collapsed below answer for verification"
    )

    # ── Section 2 ──────────────────────────────────────────────────────────
    pdf.add_page()
    pdf.h1("2. Key Architecture Decisions")

    pdf.h2("2.1 Embedding - Jina v3")
    pdf.body(
        "Jina v3 was chosen for its 1024-dimensional late-chunking capability, which "
        "preserves cross-sentence context better than naive chunking. Supports task-specific "
        "LoRA adapters for future domain fine-tuning."
    )
    pdf.decision_box(
        "Jina v3 over OpenAI text-embedding-3",
        "Late chunking preserves context at chunk boundaries. Runs locally without API "
        "costs. Same model can be fine-tuned on physics domain data later."
    )

    pdf.h2("2.2 Vector Store - Qdrant")
    pdf.decision_box(
        "Qdrant over Pinecone / Weaviate / pgvector",
        "Native sparse vector support (SPLADE), multi-vector MaxSim (ColPali), RRF fusion "
        "built-in, and local file mode for development - no Docker needed on laptops."
    )

    pdf.h2("2.3 RAPTOR Summaries - Intent-Gated")
    pdf.decision_box(
        "RAPTOR only on 'overview' intent queries",
        "Running RAPTOR on every query adds 1-2s latency with no benefit for factual "
        "queries. Intent router gates it to queries that genuinely need broad synthesis."
    )

    pdf.h2("2.4 SPLADE Hybrid Search")
    pdf.decision_box(
        "SPLADE over BM25",
        "BM25 is purely term-frequency based. SPLADE learns term expansions - 'velocity' "
        "expands to 'speed', 'acceleration', 'motion' - producing richer sparse representations."
    )
    pdf.decision_box(
        "RRF over weighted sum for fusion",
        "RRF is parameter-free - no tuning of alpha weights between dense and sparse scores. "
        "Weighted sums require calibration per domain and break when score distributions shift."
    )
    pdf.decision_box(
        "SPLADE disabled by default (SPLADE_ENABLED=false)",
        "Existing Qdrant collections use plain unnamed dense vectors. Enabling SPLADE "
        "requires re-ingestion with named vector schema. Safe default avoids breaking "
        "existing deployments. GPU VM enables it after fresh ingest."
    )

    pdf.add_page()
    pdf.h2("2.5 Cross-Encoder Re-Ranker")
    pdf.body(
        "The cross-encoder reads query and passage jointly - catching vocabulary mismatch "
        "that bi-encoders miss. Example: 'Newton's first law' query vs Feynman's 'law of "
        "inertia' text would score low in ANN but high in cross-encoder."
    )
    pdf.decision_box(
        "Retrieve top-20, re-rank to top-6",
        "More ANN candidates = higher recall. Re-ranker filters noise. Retrieving only "
        "top-6 directly risks missing relevant passages with lower embedding scores."
    )
    pdf.decision_box(
        "MiniLM-L-6 over ColBERT",
        "MiniLM is ~80MB and runs in <200ms on CPU for 20 pairs. ColBERT requires storing "
        "token-level embeddings for every chunk (large index) - overkill for our scale."
    )

    pdf.h2("2.6 Concept Graph - Memgraph + Qdrant ANN")
    pdf.decision_box(
        "Qdrant concept_embeddings for fast concept lookup",
        "Original approach fetched concept embeddings from Memgraph over Bolt (~500ms for "
        "500 concepts x 1024 floats). Qdrant ANN reduced this to ~1ms."
    )

    pdf.h2("2.7 LLM Synthesis with Epistemic Humility")
    pdf.decision_box(
        "Strict synthesis prompt over permissive",
        "Early version let LLM 'summarise what is available' when passages were irrelevant. "
        "LLM hallucinated. Now: if passages do not answer the question, say so in one "
        "sentence and stop. Never quote text not present in provided passages."
    )

    # ── Section 3 ──────────────────────────────────────────────────────────
    pdf.add_page()
    pdf.h1("3. Intent Router - Honest Assessment")

    pdf.h2("3.1 What It Actually Is")
    pdf.body(
        "The current intent router is a nearest-prototype matcher - NOT a trained classifier "
        "in any machine learning sense. It computes cosine similarity between the query "
        "embedding and hand-written prototype queries for each intent. The intent whose "
        "prototypes score highest wins. If no intent exceeds threshold 0.30, it falls "
        "back to MIXED (all retrieval paths active)."
    )

    pdf.h2("3.2 How It Works")
    pdf.h3("At startup (once per session):")
    pdf.bullet("Embed 8-10 hand-crafted prototype queries per intent using Jina v3")
    pdf.bullet("Normalize each embedding so dot product equals cosine similarity")
    pdf.bullet("Cache as a matrix of shape (N_prototypes, 1024)")
    pdf.ln(1)
    pdf.h3("At query time (zero extra cost):")
    pdf.bullet("Query vector already computed for Qdrant - reused here at zero cost")
    pdf.bullet("Dot product against each intent prototype matrix")
    pdf.bullet("Max similarity score per intent (best matching prototype wins)")
    pdf.bullet("Scores < 0.30 on all intents -> MIXED fallback (safe, retrieves more)")
    pdf.ln(2)

    pdf.h2("3.3 Prototype Queries by Intent")
    widths = [28, 146]
    pdf.table_row(["Intent", "Example Prototype Queries"], widths, bold=True)
    rows = [
        ("factual",
         "\"What is Newton's second law?\", \"Define kinetic energy\", \"What is Planck's constant?\""),
        ("overview",
         "\"Give me an overview of classical mechanics\", \"Summarize conservation laws chapter\""),
        ("multihop",
         "\"Why does a satellite stay in orbit?\", \"Prerequisites for Maxwell's equations?\""),
        ("visual",
         "\"Show me the diagram of the double-slit experiment\", \"Find the force diagram\""),
        ("mixed",
         "Fallback - no prototypes. Default when no intent scores above threshold (0.30)."),
    ]
    for intent, examples in rows:
        pdf.table_row([intent, examples], widths)
    pdf.ln(4)

    pdf.h2("3.4 Comparison with Alternatives")
    widths2 = [50, 26, 26, 72]
    pdf.table_row(["Approach", "Accuracy", "Latency", "Requirement"], widths2, bold=True)
    approaches = [
        ("Prototype similarity (current)", "Unknown*", "0 ms", "Hand-crafted prototypes only"),
        ("Logistic Regression", "~85-90%", "<1 ms", "200-500 labeled examples per class"),
        ("Fine-tuned BERT classifier", "~95%+", "20-50 ms", "Large labeled dataset + GPU fine-tuning"),
        ("LLM zero-shot classifier", "~90%", "1-5 s", "1 extra LLM call per query - too slow"),
    ]
    for row in approaches:
        pdf.table_row(list(row), widths2)
    pdf.ln(2)
    pdf.body("* No formal evaluation conducted. Accuracy is completely unmeasured.")

    pdf.h2("3.5 Honest Limitations")
    pdf.warning_box(
        "This system cannot be called a classifier in the ML sense. There is no training "
        "data, no learned decision boundary, and no measured accuracy. It is a prototype "
        "similarity lookup that works for obvious cases but has unknown performance on "
        "ambiguous or out-of-distribution queries. The confidence threshold 0.30 is "
        "intuition-based, not data-driven."
    )
    pdf.bullet("No training or test dataset - accuracy is completely unmeasured")
    pdf.bullet("Threshold 0.30 chosen by intuition, not cross-validation")
    pdf.bullet("Prototypes are physics-specific - different subjects need new prototypes")
    pdf.bullet("Multihop and overview intents overlap semantically - likely confused")
    pdf.bullet("Visual intent relies on keyword patterns more than semantic understanding")

    # ── Section 4 ──────────────────────────────────────────────────────────
    pdf.add_page()
    pdf.h1("4. Plan: Data-Driven Intent Classifier")

    pdf.body(
        "Upgrading to a real classifier requires no changes outside intent_router.py. "
        "Same public interface, different backend. The classify() method is the only "
        "thing that changes."
    )

    pdf.h2("4.1 Synthetic Data Generation Pipeline")

    pdf.h3("Step 1: Generate queries with Llama 3.2")
    pdf.bullet("200-300 diverse queries per intent (800-1200 total)")
    pdf.bullet("Cover physics subdomains: mechanics, thermodynamics, EM, quantum")
    pdf.bullet("Vary phrasing: short vs long, formal vs conversational")
    pdf.ln(1)

    pdf.h3("Step 2: Cross-family validation with Claude / GPT-4 as judge")
    pdf.body(
        "Cross-family validation is stronger than same-model validation - different model "
        "families have different biases. The generator cannot leniently validate its own "
        "outputs. This principle also applies to end-to-end answer quality evaluation."
    )
    pdf.bullet("Send each (query, intent_label) pair to Claude/GPT-4 for verification")
    pdf.bullet("Prompt: 'Does this query match the intent? YES/NO + one sentence reason'")
    pdf.bullet("Keep only queries where judge says YES (target >85% agreement rate)")
    pdf.bullet("Discard ambiguous queries - they add noise, not signal, to training")
    pdf.ln(1)

    pdf.h3("Step 3: Embed with Jina v3, split 80/20 stratified")
    pdf.bullet("Must use the same Jina v3 model used at runtime - no distribution shift")
    pdf.bullet("Stratified split ensures each intent has proportional train/test examples")
    pdf.bullet("Target: ~160-240 train, ~40-60 test examples per intent")
    pdf.ln(2)

    pdf.h2("4.2 Classifier Recommendation")
    widths3 = [45, 26, 26, 77]
    pdf.table_row(["Classifier", "Expected F1", "Complexity", "Notes"], widths3, bold=True)
    clf_rows = [
        ("Logistic Regression", "~85-90%", "Trivial",
         "Start here. Linear boundary on 1024-dim embeddings often sufficient."),
        ("SVM (RBF kernel)", "~87-92%", "Low", "Use if LR F1 < 0.85."),
        ("MLP (2-layer)", "~90-95%", "Low", "Use if SVM still insufficient."),
        ("Fine-tuned BERT", "~95%+", "High", "Overkill for 4-5 classes."),
    ]
    for row in clf_rows:
        pdf.table_row(list(row), widths3)
    pdf.ln(4)

    pdf.h2("4.3 Target Metrics")
    pdf.bullet("Per-class F1 > 0.85 for all intents")
    pdf.bullet("Overall accuracy > 88%")
    pdf.bullet("Visual: easiest (distinct vocabulary). Multihop: hardest (overlaps factual)")
    pdf.bullet("Confusion matrix to identify which intent pairs are most confused")
    pdf.ln(2)

    pdf.h2("4.4 Zero-Change Integration")
    pdf.code(
        "# Current: prototype similarity (no training data)\n"
        "def classify(self, query_vector):\n"
        "    scores = {i: (matrix @ q).max() for i, matrix in self._proto_matrices.items()}\n"
        "    return max(scores, key=scores.get)\n"
        "\n"
        "# Future: trained sklearn classifier (joblib-loaded)\n"
        "def classify(self, query_vector):\n"
        "    label = self._clf.predict([query_vector])[0]\n"
        "    return Intent(label)"
    )

    pdf.h2("4.5 Production Upgrade Path")
    pdf.bullet("Log real student query vectors and retrieval outcomes in production")
    pdf.bullet("Use click-through as weak label signal for intent")
    pdf.bullet("Retrain classifier periodically on real + synthetic data")
    pdf.bullet("A/B test router vs no-router on answer quality metrics")
    pdf.bullet("Target: 500+ real labeled queries within 3 months of launch")

    # ── Section 5 ──────────────────────────────────────────────────────────
    pdf.add_page()
    pdf.h1("5. Next Steps")

    pdf.h2("5.1 Immediate")
    items_now = [
        ("Phase 2 + 3 re-run on laptop (in progress, ~3-6 hours)",
         "Cards with quality prompts (no N/A formulas). Concept graph with canonical "
         "naming. Running overnight."),
        ("HyDE - Hypothetical Document Embeddings",
         "Generate a hypothetical answer with LLM, embed it, use for Qdrant search. "
         "Fixes vocabulary mismatch before re-ranking runs. Biggest remaining retrieval "
         "quality improvement. No re-ingest required."),
        ("Evaluation with eval_queries.json",
         "Systematic scoring: factual, overview, multihop, visual query types. "
         "Establishes quality baseline. Use different-family LLM as judge."),
    ]
    for title, desc in items_now:
        pdf.h3(f"- {title}")
        pdf.body(desc, indent=5)

    pdf.h2("5.2 Short-term (2-4 weeks)")
    items_short = [
        ("Synthetic data + trained intent classifier",
         "Generate with Llama 3.2, validate with Claude/GPT-4, train LR on Jina embeddings, "
         "evaluate on held-out split. Replace prototype router with measurable classifier."),
        ("GPU VM full deployment",
         "Re-ingest with SPLADE_ENABLED=true. Phase 2 with CARD_GEN_WORKERS=8 (~20 min). "
         "Phase 3 graph-only. Full hybrid search pipeline. Target <3s end-to-end latency."),
        ("Answer quality evaluation framework",
         "10 factual / 5 overview / 5 multihop / 5 visual queries scored 1-5 for accuracy, "
         "groundedness, citation quality. Different-family LLM as judge."),
    ]
    for title, desc in items_short:
        pdf.h3(f"- {title}")
        pdf.body(desc, indent=5)

    pdf.h2("5.3 Medium-term (1-2 months)")
    items_med = [
        ("Production data for classifier retraining",
         "Log real queries. Retrain on real + synthetic data."),
        ("Streaming LLM synthesis",
         "Stream tokens to frontend for perceived responsiveness."),
        ("Multi-subject expansion",
         "New prototype sets and concept prompts for biology, chemistry."),
        ("Latency profiling",
         "Instrument each stage. Target <3s end-to-end on GPU VM."),
    ]
    for title, desc in items_med:
        pdf.h3(f"- {title}")
        pdf.body(desc, indent=5)

    # ── Section 6 ──────────────────────────────────────────────────────────
    pdf.add_page()
    pdf.h1("6. Component Status")

    widths4 = [70, 22, 82]
    pdf.table_row(["Component", "Status", "Notes"], widths4, bold=True)
    status_rows = [
        ("Phase 1: Ingest pipeline", "Done", "Docling + Chonkie + Jina v3 + Qdrant + SQLite"),
        ("Phase 2: Learning cards", "Done*", "Improved prompt; re-run in progress on laptop"),
        ("Phase 2: RAPTOR summaries", "Done*", "Improved prompt; re-run in progress"),
        ("Phase 3: ColPali visual embeddings", "Done", "945 page vectors; GPU VM pending"),
        ("Phase 3: Memgraph concept graph", "Done*", "graph-only re-run pending"),
        ("Phase 3: Qdrant concept ANN", "Done", "Fast concept lookup (~1ms)"),
        ("Phase 4: Intent router", "MVP", "Prototype similarity, NOT a trained classifier"),
        ("Phase 4: SPLADE hybrid search", "Done", "Disabled by default; enable on GPU VM"),
        ("Phase 4: Cross-encoder re-ranker", "Done", "MiniLM-L-6, fetch-20 to top-6"),
        ("LLM synthesis with page citations", "Done", "Strict grounding, epistemic humility"),
        ("Visual search synthesis", "Done", "LLM response from matched page text"),
        ("Admin UI: delete document", "Done", "Hard delete from Qdrant + SQLite"),
        ("HyDE retrieval improvement", "Planned", "Next major retrieval quality fix"),
        ("Trained intent classifier", "Planned", "Synthetic data + LR on Jina embeddings"),
        ("Evaluation framework", "Planned", "Systematic quality scoring"),
    ]
    for row in status_rows:
        pdf.table_row(list(row), widths4)

    pdf.ln(3)
    pdf.body("* Re-run in progress to pick up improved prompts and quality fixes.")

    pdf.output(output_path)
    print(f"PDF saved to: {output_path}")


if __name__ == "__main__":
    import sys
    output = sys.argv[1] if len(sys.argv) > 1 else "synapse_project_report.pdf"
    build_pdf(output)
