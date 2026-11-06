"""Build the mentor-demo slide deck (PPTX) for Synapse Learning Worlds.

Every number is read out of the artifact named on its slide; nothing is invented.
Run:  .venv/bin/python logs/p1/step10/make_demo_deck.py
Out:  logs/p1/step10/demo_deck.pptx
"""
from __future__ import annotations

from pathlib import Path

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN
from pptx.util import Emu, Inches, Pt

OUT = Path("logs/p1/step10/demo_deck.pptx")

INK = RGBColor(0x1A, 0x1A, 0x1A)
MUTED = RGBColor(0x5A, 0x5A, 0x5A)
ACCENT = RGBColor(0x1F, 0x4E, 0x79)
HILITE = RGBColor(0xB0, 0x3A, 0x2E)
LIGHT = RGBColor(0xED, 0xF1, 0xF5)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)

# ── the verified numbers ────────────────────────────────────────────────────────────────────────
# Retrieval — source: lane_inclusion.json arm F0, via levers_report.md §2 (re-read 2026-10-30).
# ⚠️ ORACLE ROUTING: the eval feeds the GOLD `query_type`; the product routes with the intent
# router (agreement 0.5714, §I116), so every number here is an UPPER BOUND, not the product's.
RETRIEVAL = [
    # type,      n,   coverage, R@20,  Rceil, P@20,  Pceil, nDCG,  MAP,   MRR,   Hit
    ("factual",  53,  0.5882,  0.5879, 0.9494, 0.1292, 0.3000, 0.5921, 0.4754, 0.7809, 0.9057),
    ("overview", 40,  0.1937,  0.1882, 0.3992, 0.5125, 1.0000, 0.5379, 0.1265, 0.8021, 1.0000),
    ("multihop", 40,  0.5813,  0.5500, 0.9556, 0.1050, 0.2137, 0.5072, 0.3761, 0.7291, 0.9000),
    ("ALL 133",  133, 0.4675,  0.4563, 0.7858, 0.2372, 0.4846, 0.5503, 0.3406, 0.7717, 0.9323),
]
# Generator — source: v3_judged_full_2026-11-03_0115.md (cross-family judge, 2026-11-02).
# ⚠️ Citation is TWO numbers, not one (§I115): the shipped `citation_accuracy` was VACUOUS — its
# regex matched ZERO citations in the whole run, so its own "no citations — not penalised" rule
# returned 1.000 for every answer. `cite%` = answers citing ≥1 page; `validity` = of the cited
# pages, how many were actually retrieved. Source: logs/p1/step10/citation_fix.json.
GENERATOR = [
    # type,      n,   Faith, AnsRel, cite%, validity
    ("factual",  53,  0.683, 0.855, 0.830, 0.945),
    ("multihop", 40,  0.702, 0.742, 0.750, 0.683),
    ("overview", 40,  0.510, 0.975, 0.975, 0.282),
    ("ALL 133",  133, 0.636, 0.857, 0.850, 0.646),
]
ABSTENTION = "22 / 34 = 0.647"
FUNNEL = [
    ("base (exact 64d MRL)", 0.9189, "—"),
    ("full-dim cut", 0.8381, "−0.081"),
    ("fusion (product pool ≤100)", 0.6845, "−0.154"),
    ("cross-encoder top-20", 0.4553, "−0.229"),
]

prs = Presentation()
prs.slide_width = Inches(13.333)
prs.slide_height = Inches(7.5)
BLANK = prs.slide_layouts[6]


def _tb(slide, x, y, w, h):
    box = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = box.text_frame
    tf.word_wrap = True
    return tf


def title(slide, text, sub=None):
    tf = _tb(slide, 0.55, 0.35, 12.2, 1.0)
    p = tf.paragraphs[0]
    p.text = text
    p.font.size = Pt(30)
    p.font.bold = True
    p.font.color.rgb = ACCENT
    if sub:
        p2 = tf.add_paragraph()
        p2.text = sub
        p2.font.size = Pt(14)
        p2.font.color.rgb = MUTED


def bullets(slide, items, x=0.7, y=1.55, w=12.0, h=5.2, size=16):
    tf = _tb(slide, x, y, w, h)
    first = True
    for it in items:
        p = tf.paragraphs[0] if first else tf.add_paragraph()
        first = False
        p.text = it
        p.font.size = Pt(size)
        p.font.color.rgb = INK
        p.space_after = Pt(8)
    return tf


def notes(slide, text):
    slide.notes_slide.notes_text_frame.text = text


def add_table(slide, rows, x, y, w, h, col_w=None, font=11, header_font=11, hi_rows=(), hi_cols=()):
    nrows, ncols = len(rows), len(rows[0])
    shape = slide.shapes.add_table(nrows, ncols, Inches(x), Inches(y), Inches(w), Inches(h))
    tbl = shape.table
    if col_w:
        total = sum(col_w)
        for i, cw in enumerate(col_w):
            tbl.columns[i].width = Emu(int(Inches(w) * cw / total))
    for r, row in enumerate(rows):
        for c, val in enumerate(row):
            cell = tbl.cell(r, c)
            cell.text = str(val)
            cell.margin_left = Inches(0.03)
            cell.margin_right = Inches(0.03)
            cell.margin_top = Inches(0.01)
            cell.margin_bottom = Inches(0.01)
            para = cell.text_frame.paragraphs[0]
            para.alignment = PP_ALIGN.CENTER if c > 0 else PP_ALIGN.LEFT
            for run in para.runs:
                run.font.size = Pt(header_font if r == 0 else font)
                run.font.bold = (r == 0) or (r in hi_rows)
                run.font.color.rgb = WHITE if r == 0 else (HILITE if (r in hi_rows or c in hi_cols) else INK)
            cell.fill.solid()
            if r == 0:
                cell.fill.fore_color.rgb = ACCENT
            else:
                cell.fill.fore_color.rgb = LIGHT if r % 2 else WHITE
    return tbl


# ── SLIDE 1 — title ─────────────────────────────────────────────────────────────────────────────
s = prs.slides.add_slide(BLANK)
tf = _tb(s, 0.9, 2.4, 11.5, 2.6)
p = tf.paragraphs[0]
p.text = "Synapse Learning Worlds"
p.font.size = Pt(44)
p.font.bold = True
p.font.color.rgb = ACCENT
p2 = tf.add_paragraph()
p2.text = "A hybrid RAG system for physics learning — and the measurement programme behind it"
p2.font.size = Pt(20)
p2.font.color.rgb = INK
p3 = tf.add_paragraph()
p3.text = "One textbook (Feynman Lectures Vol. 1) · 133 gold queries · a funnel measured end to end"
p3.font.size = Pt(15)
p3.font.color.rgb = MUTED
notes(s, "Half product, half evidence. 'It answers physics questions grounded in a textbook, and we "
         "measured where the answers come from and where they get lost.'")

# ── SLIDE 2 — problem + what we built ───────────────────────────────────────────────────────────
s = prs.slides.add_slide(BLANK)
title(s, "The problem, and what we built")
bullets(s, [
    "The problem: a student asks a physics question; the system must find the right PAGES and answer "
    "from them — and we need to know how well, not just that it 'works'.",
    "What we built: a 4-phase ingestion + retrieval pipeline, an eval harness over 133 labelled queries "
    "(factual 53 / overview 40 / multihop 40), and a measurement discipline.",
    "Product today: knowledge_base_v3 — nomic-embed-text-v1.5, 768d, pooled — cross-encoder top-20.",
])
notes(s, "Keep short: (a) what it does, (b) there is a labelled eval set, (c) there is a discipline. "
         "The interesting content is the metrics and the levers.")

# ── SLIDE 3 — architecture ──────────────────────────────────────────────────────────────────────
s = prs.slides.add_slide(BLANK)
title(s, "Architecture — the 4 phases")
add_table(s, [
    ["Phase", "What it does", "Where it lands"],
    ["1", "Docling parse → chunk → MRL embed", "Qdrant knowledge_base_v3"],
    ["2", "LLM card generation (8 types/chunk) + RAPTOR summaries", "same collection + summary nodes"],
    ["3", "ColPali page images + concept graph", "visual_knowledge_base + Memgraph"],
    ["4", "Intent router → hybrid search (dense + SPLADE + ColBERT → RRF) → cross-encoder top-20",
     "the product endpoint"],
], x=0.55, y=1.7, w=12.2, h=3.6, col_w=[0.7, 7.0, 4.5], font=14, header_font=14)
notes(s, "One line per phase; go deep only in Q&A. The visual lane (Phase 3) now has data for the "
         "current doc (968 page vectors, 2026-11-02) but its 33 queries carry no labels — built, not "
         "measurable.")

# ── SLIDE 4 — the funnel ────────────────────────────────────────────────────────────────────────
s = prs.slides.add_slide(BLANK)
title(s, "The funnel — where the pages go",
      "Coverage of a query's reachable labelled pages (n=133) · source t0_baseline.json")
rows = [["boundary", "coverage", "Δ"]]
for name, cov, d in FUNNEL:
    rows.append([name, f"{cov:.4f}", d])
add_table(s, rows, x=1.6, y=1.9, w=10.0, h=3.2, col_w=[6.0, 2.0, 1.5], font=16, header_font=16,
          hi_rows=(4,))
notes(s, "The money slide. The two big losses are the fusion (−0.154) and the cross-encoder (−0.229). "
         "Everything after this is: we went after each, and here is what moved and what didn't.")

# ── SLIDE 5 — RETRIEVAL metrics (complete) ──────────────────────────────────────────────────────
s = prs.slides.add_slide(BLANK)
title(s, "Retrieval metrics — complete, per query type",
      "source lane_inclusion.json arm F0 · R-ceil / P-ceil are the course's ceilings (W7 §3.3)")
rows = [["type", "n", "coverage", "R@20", "R-ceil@20", "P@20", "P-ceil@20", "nDCG@20", "MAP", "MRR@20", "Hit@20"]]
for t, n, cov, r20, rceil, p20, pceil, ndcg, mAP, mrr, hit in RETRIEVAL:
    rows.append([t, n, f"{cov:.3f}", f"{r20:.3f}", f"{rceil:.3f}", f"{p20:.3f}", f"{pceil:.3f}",
                 f"{ndcg:.3f}", f"{mAP:.3f}", f"{mrr:.3f}", f"{hit:.3f}"])
add_table(s, rows, x=0.35, y=1.85, w=12.6, h=3.3,
          col_w=[1.5, 0.8, 1.3, 1.1, 1.3, 1.1, 1.3, 1.3, 1.1, 1.2, 1.1], font=11, header_font=11,
          hi_rows=(4,), hi_cols=(2,))
tf = _tb(s, 0.4, 5.6, 12.6, 1.5)
for txt, col, sz in [
    ("Read every recall against its ceiling: overview's raw R@20 0.188 looks ~3× worse than factual's "
     "0.588, but against its own ceiling it is 47 % vs 62 %.", INK, 13),
    ("Overview has the LOWEST recall and the HIGHEST MRR — when it finds a relevant page it ranks it "
     "first; it just finds few.", HILITE, 13),
    ("⚠️ ORACLE ROUTING: the eval feeds the GOLD query_type; the product routes with the intent router "
     "(0.5714 agreement, §I116) — so these numbers are an UPPER BOUND, not the product's.", HILITE, 13),
]:
    p = tf.paragraphs[0] if txt.startswith("Read") else tf.add_paragraph()
    p.text = txt
    p.font.size = Pt(sz)
    p.font.color.rgb = col
    p.space_after = Pt(6)
notes(s, "The full metric set: coverage, R@20 + its ceiling, P@20 + its ceiling, nDCG@20, MAP, MRR@20, "
         "Hit@20. Ceilings are the course's (W7 §3.3). Precision is ceiling-bound on every type — say "
         "so before it is asked.")

# ── SLIDE 6 — GENERATOR metrics (complete) ──────────────────────────────────────────────────────
s = prs.slides.add_slide(BLANK)
title(s, "Generator metrics — the answer side",
      "source v3_judged_full_2026-11-03_0115.md · cross-family judge (Qwen3-VL-8B vs gpt-oss-20b generator)")
rows = [["type", "n", "Faithfulness", "Answer relevance", "Cite %", "Validity"]]
for t, n, f_, a_, cp, cv in GENERATOR:
    rows.append([t, n, f"{f_:.3f}", f"{a_:.3f}", f"{cp:.3f}", f"{cv:.3f}"])
add_table(s, rows, x=1.3, y=1.95, w=10.7, h=2.5, col_w=[1.7, 0.9, 2.1, 2.2, 1.5, 1.5], font=14, header_font=13,
          hi_rows=(4,))
tf = _tb(s, 1.3, 4.7, 10.7, 2.2)
for txt, col in [
    (f"Abstention (negatives): {ABSTENTION} — a negative is handled correctly when the system declines.", INK),
    ("Citation: 85 % of answers cite a page; of the pages cited, 65 % were retrieved. The shipped "
     "'citation 1.000' was a regex artefact — its pattern matched no citation in the whole run (§I115).", HILITE),
    ("Faithfulness is moderate (0.636) and tracks retrieval weakness — overview lowest (0.510); "
     "answer-relevance is high everywhere and inverted on overview (0.975).", INK),
]:
    p = tf.paragraphs[0] if txt.startswith("Abstention") else tf.add_paragraph()
    p.text = txt
    p.font.size = Pt(13)
    p.font.color.rgb = col
    p.space_after = Pt(6)
notes(s, "Synthesis 167/200, 5,057 judge calls 0 failed. This closes the 'generator unmeasured' gap. "
         "Caveat: a judge score on a single run — no independent verifier yet.")

# ── SLIDE 6b — per-type k ───────────────────────────────────────────────────────────────────────
s = prs.slides.add_slide(BLANK)
title(s, "Per-type k — does a wider cut help?",
      "source per_type_k_sweep.json (§I105) · CE arm, mean per type, paired vs k=20")
add_table(s, [
    ["type", "R@20", "R@30", "R@40", "R@47", "nDCG@20", "nDCG@47", "ΔnDCG@47"],
    ["factual", "0.557", "0.635", "0.689", "0.725", "0.452", "0.500", "+0.048"],
    ["overview", "0.188", "0.268", "0.327", "0.370", "0.538", "0.531", "-0.007"],
    ["multihop", "0.550", "0.564", "0.590", "0.605", "0.508", "0.527", "+0.019"],
], x=2.4, y=1.9, w=8.5, h=2.2, col_w=[1.6, 1.1, 1.1, 1.1, 1.1, 1.3, 1.3, 1.3], font=13, header_font=12,
   hi_rows=(2,))
tf = _tb(s, 1.4, 4.4, 10.6, 2.6)
for txt, col in [
    ("RECALL/COVERAGE rises, most for overview (R@20 0.188 → R@47 0.370, ~2×).", INK),
    ("But RANKED QUALITY does not: overview nDCG@k is FLAT (0.538 → 0.531), and in the comparable "
     "regime (k < n_rel) it is a small RESOLVED HARM. The apparent capture gain was a CEILING artifact.",
     HILITE),
    ("Wider k is a context-budget knob, not a ranking lever. Open: does the extra overview context help "
     "the ANSWER? (now measurable — the generator eval ran at k=20.)", INK),
]:
    p = tf.paragraphs[0] if txt.startswith("RECALL") else tf.add_paragraph()
    p.text = txt
    p.font.size = Pt(13)
    p.font.color.rgb = col
    p.space_after = Pt(7)
notes(s, "§I105/§I106, both pre-registered and verified. The owner's 'wider k helps overview most' is "
         "half right — the recall half is real and type-dependent; the quality half is refuted.")

# ── SLIDE 7a — the loss decomposition (R@20 per type) ───────────────────────────────────────────
s = prs.slides.add_slide(BLANK)
title(s, "Where the endpoint loss lives — R@20 decomposed, per type",
      "source order_waste_decomp.json (§I99) · oracle = the best any ranker could do on the pool we built")
add_table(s, [
    ["type", "R-ceil@20", "pool-oracle", "pool order", "product", "waste_pool", "waste_order", "waste_ce"],
    ["factual", "0.9557", "0.8052", "0.5830", "0.5574", "0.1505", "0.2222", "0.0256"],
    ["overview", "0.3992", "0.3755", "0.2103", "0.1882", "0.0236", "0.1652", "0.0221"],
    ["multihop", "1.0000", "0.6466", "0.5106", "0.5500", "0.3534", "0.1360", "-0.0394"],
    ["ALL 133", "0.8016", "0.6283", "0.4491", "0.4442", "0.1734", "0.1791", "0.0050"],
], x=0.6, y=1.85, w=12.1, h=2.6, col_w=[1.3, 1.3, 1.4, 1.3, 1.2, 1.3, 1.5, 1.2], font=12, header_font=11,
   hi_rows=(4,))
tf = _tb(s, 0.7, 4.7, 12.0, 2.4)
for txt, col in [
    ("waste_order — the POOL's own ordering — is the biggest loss (0.179 overall; 0.165 overview; "
     "0.222 factual).", HILITE),
    ("The cross-encoder (waste_ce) is worth only 0.005 overall — and it HURTS factual (+0.026) and "
     "overview (+0.022); it helps only multihop (−0.039).", INK),
    ("⇒ The levers to chase are the pool's COVERAGE and its ORDER, not the reranker.", INK),
]:
    p = tf.paragraphs[0] if txt.startswith("waste_order") else tf.add_paragraph()
    p.text = txt
    p.font.size = Pt(13)
    p.font.color.rgb = col
    p.space_after = Pt(7)
notes(s, "This is the 'where can we improve, or is this the max?' slide. It separates three losses: the "
         "pool missing gold (waste_pool), the pool ordering gold badly (waste_order), and the reranker "
         "(waste_ce). §I99, verified 42/42 with a mutation proof.")

# ── SLIDE 7b — where the gold actually sits (the attribution) ───────────────────────────────────
s = prs.slides.add_slide(BLANK)
title(s, "The ordering loss: the gold is IN the pool, ranked 21–100",
      "source fusion_attribution.json (§I92) · new read-only attribution, §I111")
add_table(s, [
    ["type", "cov(pool)", "oracle@20", "FUSED@20", "dense-only@20", "cap-500@20"],
    ["factual", "0.811", "0.8052", "0.5830", "0.5291", "0.5922"],
    ["overview", "0.508", "0.3755", "0.2103", "0.2128", "0.2078"],
    ["multihop", "0.647", "0.6466", "0.5106", "0.5058", "0.5227"],
    ["ALL 133", "0.671", "0.6283", "0.4491", "0.4270", "0.4557"],
], x=1.4, y=1.8, w=10.5, h=2.4, col_w=[1.4, 1.4, 1.4, 1.4, 1.6, 1.4], font=13, header_font=12, hi_rows=(4,))
tf = _tb(s, 0.7, 4.35, 12.0, 2.8)
for txt, col in [
    ("39.5 % of the gold the pool holds lands in the top-20 — 60.5 % sits at ranks 21–100.", INK),
    ("The fusion is NOT the culprit: fused ≈ dense-only (Δ +0.0222 overall, unresolved), and the "
     "cap does not reorder (cap-500 ≈ fused).", INK),
    ("⇒ the gold is ranked low by the LANES themselves — the fix is the retrieval signal, not the fusion.",
     HILITE),
    ("⚠️ And the ceiling is arithmetic: R-ceil@20 = 20 × mean(1/n_rel) = 0.3992 for overview — a broad "
     "label set (median 56.5 pages), so no retriever can beat ~0.35 there.", MUTED),
    ("§I112 (the query-side lever): a different query REPRESENTATION does NOT help — multi-hypothetical "
     "max/mean (N=5) leave overview R@20 UNRESOLVED vs the shipped single HyDE hypothetical "
     "(C−A +0.0021, D−A +0.0012). ⇒ the signal lever left is the DOCUMENT side (embedder / re-ingest).",
     HILITE),
]:
    p = tf.paragraphs[0] if txt.startswith("39.5") else tf.add_paragraph()
    p.text = txt
    p.font.size = Pt(13 if not txt.startswith("⚠️") else 11)
    p.font.color.rgb = col
    p.space_after = Pt(6)
notes(s, "The attribution that says WHERE to aim: not the fusion (it is no worse than its best single "
         "lane), not the cut — the lanes' own scoring. The last line is the honest ceiling: for overview "
         "the ceiling is set by the label set, not by the system.")

# ── SLIDE 7 — levers ledger ─────────────────────────────────────────────────────────────────────
s = prs.slides.add_slide(BLANK)
title(s, "The levers ledger — what moved, what didn't",
      "each row a pre-registered run · source IMPROVEMENTS.md §I67–§I109")
tf = _tb(s, 0.7, 1.55, 12.0, 5.4)
rows = [
    ("MOVED", ACCENT, True),
    ("Per-type rerank-query policy (raw question for factual, hypothetical for overview): endpoint "
     "nDCG@20 0.4946 → 0.5503 — the largest measured lever, zero recall cost.", INK, False),
    ("MEASURED AND DID NOT MOVE", ACCENT, True),
    ("fusion width (§I67), cap (§I92), MMR (§I92) — inert at the endpoint", INK, False),
    ("fusion ORDER — MMR off / no ColBERT / dense-only / reweighted (§I100) — null or harm", INK, False),
    ("score-based fusion vs rank RRF (§I103) — null overall; harm on multihop", INK, False),
    ("RAPTOR / DA / graph lanes into the pool (§I98) — RAPTOR a resolved harm on overview", INK, False),
    ("wider k, cap 100 → 500, k → 250 (§I105/§I106) — recall/coverage only; ranked quality negative for overview", INK, False),
    ("NEWLY CLOSED / FLAGGED (2026-11-02 → 11-05)", ACCENT, True),
    ("generator stage (§I108) — MEASURED: faithfulness 0.636, answer relevance 0.857", INK, False),
    ("citation metric (§I115) — the shipped '1.000' was VACUOUS (its regex matched no citation in the "
     "whole run); real: 85 % of answers cite, 65 % of cited pages retrieved", HILITE, False),
    ("overview query-signal probe (§I112) — the QUERY side is CLOSED (null)", INK, False),
    ("RAPTOR as generator context (§I113) — null, and FLAGGED (harness prompt ≠ the product's)", HILITE, False),
    ("the eval bypasses the intent router (§I116) — the product routes at 0.5714 agreement, unmeasured", HILITE, False),
    ("visual / ColPali lane (§I107) — the raw cosine cannot separate in-domain from near-domain", INK, False),
    ("T3 lane-complete A/B (§I109) — ran but FLAGGED: anchor guard G8 failed (stale anchor)", HILITE, False),
]
first = True
for txt, col, bold in rows:
    p = tf.paragraphs[0] if first else tf.add_paragraph()
    first = False
    p.text = txt
    p.font.size = Pt(12 if bold else 12)
    p.font.bold = bold
    p.font.color.rgb = col
    p.space_after = Pt(5)
notes(s, "Where the project separates itself from 'I built a RAG app.' Most rows came back negative — "
         "the negative results are the contribution; they stop us chasing dead ends.")

# ── SLIDE 8 — the method ────────────────────────────────────────────────────────────────────────
s = prs.slides.add_slide(BLANK)
title(s, "Why this is a capstone: the method")
bullets(s, [
    "Every run is PRE-REGISTERED (arms, metrics, predictions, a falsification clause), and the "
    "pre-registration is committed alone, before the run.",
    "Every result has an INDEPENDENT VERIFIER (stdlib, re-derives every cell from the raw data) and a "
    "MUTATION PROOF (mutate the artifact; every check must go red; no inert checks).",
    "A DECISION LOG (DECISIONS.md) records every fork, why, and why not the alternatives.",
    "Test suite: 745 passed / 4 failed / 8 skipped — the 4 are a documented pre-existing set.",
])
notes(s, "The punchline: 'when I say a lever is a dead end, I can show you the pre-registration, the "
         "artifact, the verifier and the mutation proof.' Offer to walk through one.")

# ── SLIDE 9 — measured / NOT ────────────────────────────────────────────────────────────────────
s = prs.slides.add_slide(BLANK)
title(s, "What is measured, and what is NOT",
      "say this before you are asked")
bullets(s, [
    "MEASURED: retrieval quality per type at every funnel boundary; every major lever; determinism; "
    "and — new this week — the generator (faithfulness, answer relevance, citation coverage + validity, "
    "abstention).",
    "NOT measured: the visual / ColPali lane has data for the current document (968 vectors) but its 33 "
    "queries carry no labels, so it is built and populated but not measurable.",
    "NOT measured: multi-tenant behaviour — deliberately deferred (single-user scope).",
    "Open: T3 (the lane-complete v2-vs-v3 A/B) ran but its anchor guard failed and was diagnosed as a "
    "stale anchor — it needs an owner decision before its verdict is read.",
])
notes(s, "Lead with the honesty. A mentor will find the gaps anyway. Naming them first is the strong move.")

# ── SLIDE 10 — plan to the finish line ──────────────────────────────────────────────────────────
s = prs.slides.add_slide(BLANK)
title(s, "The plan to the finish line")
bullets(s, [
    "T3 — resolve the flagged lane-complete v2-vs-v3 A/B (re-register the anchor, or re-run).",
    "The pool → top-20 ranking attribution — the last unmeasured retrieval lever.",
    "The write-up — the Medium/Substack piece + the portfolio framing.",
    "Stretch (finish line B): visual-lane labels; UI polish; multi-tenant.",
])
notes(s, "'For a defensible capstone I am weeks away, not months.' The retrieval research is "
         "essentially complete; what remains is one controlled comparison, one attribution, the write-up.")

# ── SLIDE 11 — live demo ────────────────────────────────────────────────────────────────────────
s = prs.slides.add_slide(BLANK)
title(s, "Live demo (2 queries)")
bullets(s, [
    "Factual: \"What is Newton's second law?\" → answer + cited pages (~66 s).",
    "Overview (the hard type): \"How does Feynman develop conservation of energy across mechanics, waves "
    "and thermodynamics?\" → a synthesised answer citing pages 251 / 94 / 316 / 921 (~96 s).",
    "App runs on http://localhost:8503 (do not start it live).",
])
notes(s, "The overview answer is the surprise: the retrieval metric for overview is our weakest, yet "
         "the answer reads well — exactly the tension the generator metrics now quantify.")

# ── SLIDE 12 — close / asks ─────────────────────────────────────────────────────────────────────
s = prs.slides.add_slide(BLANK)
title(s, "Close / asks")
bullets(s, [
    "A read on finish line A vs B: is the capstone defensible as retrieval + generator measurement + "
    "demo, or does it need more?",
    "Any steer on the write-up angle for industry re-entry.",
])
notes(s, "End with a specific ask. The mentor's value is judgment on scope, not code review.")

# ── SLIDE 14/15 — architecture diagrams (appendix) ───────────────────────────────────────────────
from PIL import Image  # noqa: E402

for fname, ttl in (("arch_ingestion.png", "Architecture — Ingestion (Phases 1·2·3)"),
                   ("arch_retrieval.png", "Architecture — Query-Time Retrieval")):
    s = prs.slides.add_slide(BLANK)
    title(s, ttl, "verified against code · Docs/synapse_architecture_v2.html")
    img = Path("logs/p1/step10") / fname
    iw, ih = Image.open(img).size
    max_w, max_h = 12.2, 5.5
    scale = min(max_w / iw, max_h / ih)
    tw, th = iw * scale, ih * scale
    s.shapes.add_picture(str(img), Inches((13.333 - tw) / 2), Inches(1.55),
                         width=Inches(tw), height=Inches(th))
    notes(s, "The full pipeline, verified against the code (48/48 mechanical checks; independent "
             "cross-family reviewer 11/12 confirmed, the 12th dismissed on evidence).")

OUT.parent.mkdir(parents=True, exist_ok=True)
prs.save(str(OUT))
print(f"wrote {OUT} ({OUT.stat().st_size} bytes, {len(prs.slides._sldIdLst)} slides)")
