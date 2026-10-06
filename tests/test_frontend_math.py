"""Regression tests for the answer-path LaTeX conversion (frontend).

Two bugs made maths render as raw text in the Ask-a-Question answer:

1. The answer was passed straight to ``st.markdown`` — it never went through the
   converter the cards use. The generator emits ``\\[...\\]`` / ``\\(...\\)``, and
   Markdown treats a backslash as an escape, so display maths appeared as a literal
   ``[ \\frac{...} ]``.
2. ``_convert_braces_to_math``'s Pass 2 handled ``$...$`` but not ``$$...$$``: it
   consumed the two dollars of a display block as an *empty* inline span and then
   brace-converted the maths inside it, e.g. ``\\frac{GMm}{r^{2}}`` became
   ``\\frac{GMm}{$r^{2}$}``.

Imported via spec so the module's ``streamlit`` side effects stay out of the suite's
way; conftest sets ``QDRANT_IN_MEMORY=true``, which keeps the import cheap.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_APP = Path(__file__).resolve().parents[1] / "src" / "frontend" / "streamlit_app.py"


@pytest.fixture(scope="module")
def app():
    spec = importlib.util.spec_from_file_location("streamlit_app_under_test", _APP)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_latex_display_delimiters_become_double_dollars(app):
    out = app._latex_delims_to_dollars(r"as \[ v^{2} = \frac{GM}{r}. \] done")
    assert out == r"as $$v^{2} = \frac{GM}{r}.$$ done"


def test_latex_inline_delimiters_become_dollars(app):
    out = app._latex_delims_to_dollars(r"at distance \(r\), escaping needs \(\sqrt{2}\)")
    assert out == r"at distance $r$, escaping needs $\sqrt{2}$"


def test_brace_pass_does_not_corrupt_display_math(app):
    """The Pass-2 regression: \\frac{GMm}{r^{2}} must survive inside $$...$$ intact."""
    text = r"$$F = -\,G\,\frac{m_{1}m_{2}}{r^{3}}\,\mathbf r$$"
    assert app._convert_braces_to_math(text) == text


def test_brace_pass_still_converts_bare_braces(app):
    """Outside maths, the original {expr} -> $expr$ behaviour is unchanged."""
    assert app._convert_braces_to_math(r"the value {E = mc^2} holds") == r"the value $E = mc^2$ holds"


def test_answer_path_end_to_end(app):
    """The full pipeline the answer now goes through, on real generator output."""
    raw = (
        r"two masses \(m_1\) and \(m_2\) give" "\n\n"
        r"\[" "\n" r"F = -\,G\,m_1\,m_2\,\frac{\mathbf{r}}{r^{3}}," "\n" r"\]" "\n\n"
        r"where \(\mathbf{r}\) is the displacement and \(r=|\mathbf{r}|\) its magnitude."
    )
    out = app._convert_braces_to_math(app._latex_delims_to_dollars(raw))
    assert r"$$F = -\,G\,m_1\,m_2\,\frac{\mathbf{r}}{r^{3}},$$" in out
    assert "$m_1$" in out and "$m_2$" in out and r"$r=|\mathbf{r}|$" in out
    assert "\\[" not in out and "\\]" not in out and "\\(" not in out
    assert r"$r^{3}$" not in out  # display maths must not have been brace-split


# ── Display hygiene: parser artefacts and citation extraction ────────────────

def test_clean_text_strips_formula_comment(app):
    """Docling leaves this HTML comment; Streamlit markdown renders it visibly."""
    assert app._clean_text("Before <!-- formula-not-decoded --> after") == "Before after"


def test_clean_text_strips_literal_formula_not_decoded(app):
    out = app._clean_text("text Formula not decoded more")
    assert "ormula not decoded" not in out


def test_clean_text_collapses_blank_runs(app):
    assert app._clean_text("a\n\n\n\n\nb") == "a\n\nb"


def test_clean_text_is_safe_on_empty(app):
    assert app._clean_text("") == ""


def test_cited_pages_reads_both_citation_formats(app):
    ans = "as shown [Page 141] and again (page 274); see also p. 99"
    assert app._cited_pages(ans) == {141, 274}


def test_cited_pages_empty_when_no_citations(app):
    assert app._cited_pages("an answer with no citations at all") == set()
