"""Render the Synapse mentor-demo deck to PDF directly (no LibreOffice / Keynote needed).

Same content as `demo_deck.pptx` / `demo_deck.md`, produced with fpdf2 so it opens anywhere.
Run:  .venv/bin/python logs/p1/step10/make_demo_deck_pdf.py
Out:  logs/p1/step10/demo_deck.pdf
"""
from __future__ import annotations

from pathlib import Path

from fpdf import FPDF

OUT = Path("logs/p1/step10/demo_deck.pdf")

W, H = 338.7, 190.5  # 16:9 at 96dpi-ish (mm)
M = 14.0             # margin

# ── content (identical numbers to the PPTX; every figure sourced on its slide) ──────────────────
RETRIEVAL = [
    ("type", "n", "coverage", "R@20", "R-ceil@20", "P@20", "P-ceil@20", "nDCG@20", "MAP", "MRR@20", "Hit@20"),
    ("factual", "53", "0.588", "0.588", "0.949", "0.129", "0.300", "0.592", "0.475", "0.781", "0.906"),
    ("overview", "40", "0.194", "0.188", "0.399", "0.512", "1.000", "0.538", "0.127", "0.802", "1.000"),
    ("multihop", "40", "0.581", "0.550", "0.956", "0.105", "0.214", "0.507", "0.376", "0.729", "0.900"),
    ("ALL 133", "133", "0.468", "0.456", "0.786", "0.237", "0.485", "0.550", "0.341", "0.772", "0.932"),
]
GENERATOR = [
    ("type", "n", "Faithfulness", "Answer relevance", "Cite %", "Validity"),
    ("factual", "53", "0.683", "0.855", "0.830", "0.945"),
    ("multihop", "40", "0.702", "0.742", "0.750", "0.683"),
    ("overview", "40", "0.510", "0.975", "0.975", "0.282"),
    ("ALL 133", "133", "0.636", "0.857", "0.850", "0.646"),
]
PER_TYPE_K = [
    ("type", "R@20", "R@30", "R@40", "R@47", "nDCG@20", "nDCG@47", "ΔnDCG@47"),
    ("factual", "0.557", "0.635", "0.689", "0.725", "0.452", "0.500", "+0.048"),
    ("overview", "0.188", "0.268", "0.327", "0.370", "0.538", "0.531", "-0.007"),
    ("multihop", "0.550", "0.564", "0.590", "0.605", "0.508", "0.527", "+0.019"),
]
FUNNEL = [
    ("boundary", "coverage", "Δ"),
    ("base (exact 64d MRL)", "0.9189", "—"),
    ("full-dim cut", "0.8381", "−0.081"),
    ("fusion (product pool ≤100)", "0.6845", "−0.154"),
    ("cross-encoder top-20", "0.4553", "−0.229"),
]
ARCH = [
    ("Phase", "What it does", "Where it lands"),
    ("1", "Docling parse -> chunk -> MRL embed", "Qdrant knowledge_base_v3"),
    ("2", "LLM card generation (8 types/chunk) + RAPTOR", "same collection + summary nodes"),
    ("3", "ColPali page images + concept graph", "visual_knowledge_base + Memgraph"),
    ("4", "Intent router -> hybrid (dense+SPLADE+ColBERT -> RRF) -> cross-encoder top-20", "the product endpoint"),
]

ACCENT = (31, 78, 121)
HILITE = (176, 58, 46)
INK = (26, 26, 26)
MUTED = (90, 90, 90)


class Deck(FPDF):
    _TR = str.maketrans({"Δ": "d", "−": "-", "—": "-", "–": "-", "→": "->", "×": "x",
                         "≈": "~", "≤": "<=", "≥": ">=", "•": "-", "’": "'", "“": '"', "”": '"'})

    def normalize_text(self, text):
        return super().normalize_text(str(text).translate(self._TR))

    def header(self):
        pass

    def slide(self, title: str, sub: str = ""):
        self.add_page()
        self.set_xy(M, 12)
        self.set_text_color(*ACCENT)
        self.set_font("Helvetica", "B", 24)
        self.cell(0, 12, title, new_x="LMARGIN", new_y="NEXT")
        if sub:
            self.set_text_color(*MUTED)
            self.set_font("Helvetica", "", 11)
            self.cell(0, 7, sub, new_x="LMARGIN", new_y="NEXT")
        self.ln(4)
        self.set_text_color(*INK)

    def bullets(self, items, size=13, gap=3.5):
        self.set_font("Helvetica", "", size)
        for it in items:
            self.set_x(M)
            self.multi_cell(0, size * 0.62, "-  " + it, new_x="LMARGIN", new_y="NEXT")
            self.ln(gap)

    def grid(self, rows, widths, font=10, header_font=10, hi_rows=()):
        font, header_font = int(round(font)), int(round(header_font))
        avail = W - 2 * M
        total = sum(widths)
        colw = [avail * w / total for w in widths]
        self.set_font("Helvetica", "B", header_font)
        self.set_fill_color(*ACCENT)
        self.set_text_color(255, 255, 255)
        self.set_x(M)
        for r, cw in zip(rows[0], colw):
            self.cell(cw, 8, str(r), border=0, align="C", fill=True)
        self.ln(8)
        self.set_text_color(*INK)
        for i, row in enumerate(rows[1:], start=1):
            self.set_font("Helvetica", "B" if i in hi_rows else "", font)
            self.set_x(M)
            for c, cw in enumerate(colw):
                val = str(row[c])
                self.set_text_color(*(HILITE if i in hi_rows else INK))
                self.cell(cw, 7.5, val, border="B", align="C" if c else "L")
            self.ln(7.5)
        self.set_text_color(*INK)


pdf = Deck(orientation="L", unit="mm", format=(H, W))
pdf.set_auto_page_break(False)

# 1 title
pdf.add_page()
pdf.set_xy(M, 55)
pdf.set_text_color(*ACCENT)
pdf.set_font("Helvetica", "B", 34)
pdf.cell(0, 16, "Synapse Learning Worlds", new_x="LMARGIN", new_y="NEXT")
pdf.set_text_color(*INK)
pdf.set_font("Helvetica", "", 16)
pdf.cell(0, 10, "A hybrid RAG system for physics learning - and the measurement programme behind it",
         new_x="LMARGIN", new_y="NEXT")
pdf.set_text_color(*MUTED)
pdf.set_font("Helvetica", "", 12)
pdf.cell(0, 8, "One textbook (Feynman Lectures Vol. 1) | 133 gold queries | a funnel measured end to end",
         new_x="LMARGIN", new_y="NEXT")

# 2 problem
pdf.slide("The problem, and what we built")
pdf.bullets([
    "A student asks a physics question; the system must find the right PAGES and answer from them - and "
    "we need to know how well, not just that it 'works'.",
    "Built: a 4-phase ingestion + retrieval pipeline, an eval harness over 133 labelled queries "
    "(factual 53 / overview 40 / multihop 40), and a measurement discipline.",
    "Product today: knowledge_base_v3 - nomic-embed-text-v1.5, 768d, pooled - cross-encoder top-20.",
])

# 3 architecture
pdf.slide("Architecture - the 4 phases")
pdf.grid(ARCH, widths=[0.7, 6.5, 4.0], font=12, header_font=12)

# 4 funnel
pdf.slide("The funnel - where the pages go",
          "coverage of a query's reachable labelled pages (n=133) | source t0_baseline.json")
pdf.grid(FUNNEL, widths=[6, 2, 1.5], font=13, header_font=13, hi_rows=(4,))

# 5 retrieval metrics
pdf.slide("Retrieval metrics - complete, per query type",
          "source lane_inclusion.json arm F0 | R-ceil / P-ceil are the course's ceilings (W7 3.3)")
pdf.grid(RETRIEVAL, widths=[1.5, 0.8, 1.3, 1.1, 1.3, 1.1, 1.3, 1.3, 1.1, 1.2, 1.1],
         font=9.5, header_font=9.5, hi_rows=(4,))
pdf.ln(3)
pdf.set_text_color(*HILITE)
pdf.set_font("Helvetica", "", 11)
pdf.multi_cell(0, 6, "Read recall against its ceiling: overview's raw R@20 0.188 looks ~3x worse than "
                     "factual's 0.588, but against its own ceiling it is 47% vs 62%. Overview has the "
                     "LOWEST recall and the HIGHEST MRR - when it finds a relevant page it ranks it "
                     "first; it just finds few.", new_x="LMARGIN", new_y="NEXT")

# 5b generator metrics
pdf.slide("Generator metrics - the answer side",
          "source v3_judged_full_2026-11-03_0115.md | cross-family judge (Qwen3-VL-8B vs gpt-oss-20b)")
pdf.grid(GENERATOR, widths=[1.7, 0.9, 2.1, 2.2, 1.5, 1.5], font=13, header_font=12, hi_rows=(4,))
pdf.ln(3)
pdf.set_text_color(*INK)
pdf.set_font("Helvetica", "", 11)
pdf.multi_cell(0, 6, "Abstention (negatives): 22/34 = 0.647. Citation is TWO numbers (I115): the shipped "
                     "'citation 1.000' was a regex artefact - its pattern matched no citation in the "
                     "whole run - so read the real pair: 85% of answers cite a page, and of the pages "
                     "cited, 65% were retrieved. Faithfulness is moderate (0.636) "
                     "and tracks retrieval weakness - overview lowest (0.510); answer-relevance is high "
                     "everywhere and inverted on overview (0.975).",
               new_x="LMARGIN", new_y="NEXT")

# 5c per-type k  (the newly added slide)
pdf.slide("Per-type k - does a wider cut help?",
          "source per_type_k_sweep.json (§I105) | CE arm, mean per type, paired vs k=20")
pdf.grid(PER_TYPE_K, widths=[1.6, 1.1, 1.1, 1.1, 1.1, 1.3, 1.3, 1.3], font=12, header_font=12, hi_rows=(2,))
pdf.ln(3)
pdf.set_text_color(*HILITE)
pdf.set_font("Helvetica", "", 11)
pdf.multi_cell(0, 6, "RECALL/COVERAGE rises, most for overview (R@20 0.188 -> R@47 0.370, ~2x). But "
                     "RANKED QUALITY does not: overview nDCG@k is FLAT (0.538 -> 0.531), and in the "
                     "comparable regime (k < n_rel) it is a small RESOLVED HARM. The apparent capture "
                     "gain was a CEILING artifact. Wider k is a context-budget knob, not a ranking "
                     "lever. Open: does the extra overview context help the ANSWER? (now measurable - "
                     "the generator eval ran at k=20).", new_x="LMARGIN", new_y="NEXT")

# 5d the loss decomposition (R@20 per type)
pdf.slide("Where the endpoint loss lives - R@20 decomposed, per type",
          "source order_waste_decomp.json (§I99) | oracle = the best any ranker could do on the pool we built")
pdf.grid([
    ("type", "R-ceil@20", "pool-oracle", "pool order", "product", "waste_pool", "waste_order", "waste_ce"),
    ("factual", "0.9557", "0.8052", "0.5830", "0.5574", "0.1505", "0.2222", "0.0256"),
    ("overview", "0.3992", "0.3755", "0.2103", "0.1882", "0.0236", "0.1652", "0.0221"),
    ("multihop", "1.0000", "0.6466", "0.5106", "0.5500", "0.3534", "0.1360", "-0.0394"),
    ("ALL 133", "0.8016", "0.6283", "0.4491", "0.4442", "0.1734", "0.1791", "0.0050"),
], widths=[1.3, 1.3, 1.4, 1.3, 1.2, 1.3, 1.5, 1.2], font=11, header_font=10, hi_rows=(4,))
pdf.ln(3)
pdf.set_text_color(*HILITE)
pdf.set_font("Helvetica", "", 11)
pdf.multi_cell(0, 6, "waste_order - the POOL's own ordering - is the biggest loss (0.179 overall; "
                     "0.165 overview; 0.222 factual). The cross-encoder (waste_ce) is worth only 0.005 "
                     "overall, and it HURTS factual (+0.026) and overview (+0.022); it helps only "
                     "multihop (-0.039). => the levers to chase are the pool's COVERAGE and its ORDER, "
                     "not the reranker.", new_x="LMARGIN", new_y="NEXT")

# 5e where the gold actually sits (the attribution)
pdf.slide("The ordering loss: the gold is IN the pool, ranked 21-100",
          "source fusion_attribution.json (§I92) | new read-only attribution, §I111")
pdf.grid([
    ("type", "cov(pool)", "oracle@20", "FUSED@20", "dense-only@20", "cap-500@20"),
    ("factual", "0.811", "0.8052", "0.5830", "0.5291", "0.5922"),
    ("overview", "0.508", "0.3755", "0.2103", "0.2128", "0.2078"),
    ("multihop", "0.647", "0.6466", "0.5106", "0.5058", "0.5227"),
    ("ALL 133", "0.671", "0.6283", "0.4491", "0.4270", "0.4557"),
], widths=[1.4, 1.4, 1.4, 1.4, 1.6, 1.4], font=12, header_font=11, hi_rows=(4,))
pdf.ln(3)
pdf.set_text_color(*INK)
pdf.set_font("Helvetica", "", 11)
pdf.multi_cell(0, 6, "39.5% of the gold the pool holds lands in the top-20 - 60.5% sits at ranks "
                     "21-100. The fusion is NOT the culprit: fused ~ dense-only (delta +0.0222 overall, "
                     "unresolved), and the cap does not reorder (cap-500 ~ fused). => the gold is ranked "
                     "low by the LANES themselves - the fix is the retrieval signal, not the fusion.",
               new_x="LMARGIN", new_y="NEXT")
pdf.set_text_color(*MUTED)
pdf.set_font("Helvetica", "", 10)
pdf.multi_cell(0, 5.5, "And the ceiling is arithmetic: R-ceil@20 = 20 x mean(1/n_rel) = 0.3992 for "
                       "overview - a broad label set (median 56.5 pages), so no retriever can beat ~0.35 "
                       "there.", new_x="LMARGIN", new_y="NEXT")
pdf.ln(1)
pdf.set_text_color(*HILITE)
pdf.set_font("Helvetica", "", 10)
pdf.multi_cell(0, 5.5, "§I112 (the query-side lever): a different query REPRESENTATION does NOT help - "
                       "multi-hypothetical max/mean (N=5) leave overview R@20 UNRESOLVED vs the shipped "
                       "single HyDE hypothetical (C-A +0.0021, D-A +0.0012). => the signal lever left is "
                       "the DOCUMENT side (embedder / re-ingest).", new_x="LMARGIN", new_y="NEXT")

# 6 levers
pdf.slide("The levers ledger - what moved, what didn't",
          "each row a pre-registered run | source IMPROVEMENTS.md §I67-§I109")
pdf.set_font("Helvetica", "B", 12)
pdf.set_text_color(*ACCENT)
pdf.cell(0, 7, "MOVED", new_x="LMARGIN", new_y="NEXT")
pdf.set_text_color(*INK)
pdf.set_font("Helvetica", "", 11.5)
pdf.multi_cell(0, 6, "•  Per-type rerank-query policy (raw question for factual, hypothetical for "
                     "overview): endpoint nDCG@20 0.4946 -> 0.5503 - the largest measured lever, zero "
                     "recall cost.", new_x="LMARGIN", new_y="NEXT")
pdf.ln(2)
pdf.set_font("Helvetica", "B", 12)
pdf.set_text_color(*ACCENT)
pdf.cell(0, 7, "MEASURED AND DID NOT MOVE (each a pre-registered run)", new_x="LMARGIN", new_y="NEXT")
pdf.set_text_color(*INK)
pdf.set_font("Helvetica", "", 11.5)
for line in [
    "-  fusion width (§I67), cap (§I92), MMR (§I92) - inert at the endpoint",
    "-  fusion ORDER - MMR off / no ColBERT / dense-only / reweighted (§I100) - null or harm",
    "-  score-based fusion vs rank RRF (§I103) - null overall; harm on multihop",
    "-  RAPTOR / DA / graph lanes into the pool (§I98) - RAPTOR a resolved harm on overview",
    "-  wider k, cap 100->500, k->250 (§I105/§I106) - recall/coverage only; ranked quality negative for overview",
]:
    pdf.multi_cell(0, 6, line, new_x="LMARGIN", new_y="NEXT")

# 7 method
pdf.slide("Why this is a capstone: the method")
pdf.bullets([
    "Every run is PRE-REGISTERED (arms, metrics, predictions, a falsification clause), committed alone "
    "before the run.",
    "Every result has an INDEPENDENT VERIFIER (stdlib, re-derives every cell from the raw data) and a "
    "MUTATION PROOF (every check must go red; no inert checks).",
    "A DECISION LOG (DECISIONS.md) records every fork, why, and why not the alternatives.",
    "Test suite: 745 passed / 4 failed / 8 skipped - the 4 are a documented pre-existing set.",
])

# 8 measured / not
pdf.slide("What is measured, and what is NOT", "say this before you are asked")
pdf.bullets([
    "MEASURED: retrieval quality per type at every funnel boundary; every major lever; determinism; and "
    "(2026-11-02) the generator - faithfulness, answer relevance, citation coverage + validity, abstention.",
    "NOT measured: the visual / ColPali lane has data for the current document (968 vectors) but its 33 "
    "queries carry no labels - built and populated, not measurable; and the raw cosine cannot separate "
    "in-domain from near-domain (§I107), so it is not gateable either.",
    "NOT measured: multi-tenant behaviour - deliberately deferred (single-user scope).",
    "OPEN: T3 (lane-complete v2-vs-v3 A/B) ran but is FLAGGED - anchor guard G8 failed (diagnosed as a "
    "stale anchor, §I109); needs an owner decision. OPEN: does a wider k for overview help the ANSWER?",
])

# 9 plan
pdf.slide("The plan to the finish line")
pdf.bullets([
    "T3 - resolve the flagged lane-complete v2-vs-v3 A/B (re-register the anchor, or re-run).",
    "The pool -> top-20 ranking attribution - the last unmeasured retrieval lever.",
    "Generator-at-wider-k for overview - close the §I105/§I106 open reading now that the generator is measured.",
    "The write-up (Medium/Substack) + this demo. Stretch: visual-lane labels; UI polish; multi-tenant.",
])

# 9b live demo
pdf.slide("Live demo (2 queries)")
pdf.bullets([
    "Factual: \"What is Newton's second law?\" -> answer + cited pages (~66 s).",
    "Overview (the hard type): \"How does Feynman develop conservation of energy across mechanics, waves "
    "and thermodynamics?\" -> a synthesised answer citing pages 251 / 94 / 316 / 921 (~96 s).",
    "App runs on http://localhost:8503 (do not start it live).",
])

# 10 close
pdf.slide("Close / asks")
pdf.bullets([
    "A read on finish line A vs B: is the capstone defensible as retrieval + generator measurement + demo?",
    "Any steer on the write-up angle for industry re-entry.",
])

pdf.output(str(OUT))
print(f"wrote {OUT} ({OUT.stat().st_size} bytes, {pdf.pages_count} pages)")
