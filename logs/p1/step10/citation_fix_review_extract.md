# Independent review extract — §I115, the citation-metric fix (2026-11-05)

**Reviewer:** re-derive each claim yourself from the named sources. Do NOT take the claim text on
trust; a claim is CONFIRMED only if your own computation reproduces it. Report per claim:
CONFIRMED / REFUTED / UNVERIFIABLE, with the number or the file:line you derived it from.
Read-only — do not modify any file.

## The change (what to review)

`scripts/evaluate_rag.py` — `compute_citation_accuracy` was
`re.findall(r"\[Page (\d+)\]", answer, re.I)` with `if not cited: return 1.0`. It is now
`_CITATION_RE = re.compile(r"[\[【(]\s*[Pp]age\s*(\d+)\s*[\]】)]")`, returns **None** when uncited,
and a new `compute_citation_coverage` returns 1.0/0.0. Same regex change to `_cited_pages` in
`src/frontend/streamlit_app.py` and `src/frontend/nicegui_app.py`.

## Sources

- Artifact (the re-derivation): `logs/p1/step10/citation_fix.json` — 166 `per_answer` entries, each
  `{id, n_gold, cited_old, cited_new, valid_new, gold_hit_new}` + an `aggregates` block.
- Raw answers: `data/eval_results/v3_judged_full_2026-11-03_0115.json` (`results[*].generation.answer`).
- Code: `scripts/evaluate_rag.py` (the two functions), the two frontend files.

## Claims

- **C1.** The SHIPPED regex `r"\[Page (\d+)\]"` (a literal ASCII space) matches **zero** citations
  across all 166 answerable answers. (Re-derive: run it over the raw answers.)
- **C2.** The generator emits `Page` followed by U+202F (narrow no-break, ~545×) or U+00A0
  (no-break, ~41×), and uses the CJK bracket `【Page N】` in 38 answers — none matched by C1's regex.
- **C3.** Because of `if not cited: return 1.0`, the shipped function returned **1.0 for every
  answer**, so the reported `citation_accuracy` 1.000 is vacuous.
- **C4.** The fixed regex parses `[Page 141]`, `【Page 141】`, `(page 141)`, and any Unicode space
  between `Page` and the number; the fixed function returns **None** when the answer cites nothing.
- **C5.** Corrected aggregates: **113/166 (68 %)** cite in some form; **53 (32 %)** cite nothing;
  citation validity (|cited ∩ retrieved| / |cited|) = **0.6463**; answer-cites-gold recall =
  **0.2018**. (Re-derive from `per_answer`.)
- **C6.** Both frontends' `_cited_pages` (before the fix) matched `[Page`/`(page` but **not** the
  CJK bracket, so for CJK-cited answers the apps found no citation and fell back to
  "Sources retrieved" (all pages).
- **C7.** The fix is behaviour-preserving for citing answers: no page the old parser found is lost,
  i.e. `set(cited_old) ⊆ set(cited_new)` for all 166 entries.

## Independent stdlib verifier already run

`logs/p1/step10/citation_fix_verifier.py` → 14/14 PASS; `citation_fix_mutation.py` → 14/14 checks
reddened, no inert. Your job is the *independent* re-derivation, not to re-run those.
