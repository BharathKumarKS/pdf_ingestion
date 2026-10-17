"""Golden-file tests for formula-card rendering (B1 / I7).

B1: a formula card's ``content`` is ONE string holding both the LaTeX expression and
its prose explanation — ``"F = G \\frac{m_1 m_2}{r^2} where F is the gravitational
force..."``. ``render_math`` handed the whole string to ``st.latex()``, which typesets
its entire argument as mathematics, so the explanation rendered as maths (spaces
collapsed, letters italic).

The fix splits the card at the first top-level ``where`` and renders the two halves
with ``st.latex`` / ``st.markdown``. Cards with no credible boundary are prose-led and
fall back to markdown — where the delimiter/brace converters still typeset the maths
embedded in them.

``tests/data/formula_split_golden.json`` holds real card contents covering every
separator shape found in the corpus (``" where "``, ``" where:"``, ``" where\\n"``,
``"\\nwhere "``, multi-space, no-boundary, and ``where`` nested inside a brace group),
with the expected split. The corpus is the source of truth for these numbers; see
``IMPROVEMENTS.md`` §B1 for the measurements (1,534 cards: 1,513 split, 21 fall back).

The app file executes at import, so it is loaded via ``spec`` (as
``test_frontend_math.py`` does); conftest sets ``QDRANT_IN_MEMORY=true`` to keep that
import cheap.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

_APP = Path(__file__).resolve().parents[1] / "src" / "frontend" / "streamlit_app.py"
_GOLDEN = Path(__file__).resolve().parent / "data" / "formula_split_golden.json"


@pytest.fixture(scope="module")
def app():
    spec = importlib.util.spec_from_file_location("streamlit_app_formula_under_test", _APP)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def golden():
    return json.loads(_GOLDEN.read_text(encoding="utf-8"))


@pytest.fixture
def capture(app, monkeypatch):
    """Capture the arguments render_math passes to st.latex / st.markdown."""
    calls = {"latex": [], "markdown": []}
    monkeypatch.setattr(app.st, "latex", lambda s: calls["latex"].append(s))
    monkeypatch.setattr(app.st, "markdown", lambda s: calls["markdown"].append(s))
    return calls


def _by_shape(golden, shape):
    for case in golden:
        if case["shape"] == shape:
            return case
    raise AssertionError(f"golden file has no case {shape!r}")


# ── the splitter, against real card content ────────────────────────────────

def test_golden_split_matches_corpus(app, golden):
    """Every golden card splits exactly as recorded (the render path order: clean → split)."""
    for case in golden:
        got = app._split_formula(app._clean_text(case["content"]).strip())
        assert got == (case["expr"], case["expl"]), f"shape={case['shape']}"


def test_where_inside_braces_is_not_a_boundary(app):
    """'where' nested in a brace group must not be taken for the separator."""
    expr, expl = app._split_formula(
        r"\frac{Q_{\text{where}}}{4\pi\varepsilon_0 r^2} where Q is the enclosed charge.")
    assert expr == r"\frac{Q_{\text{where}}}{4\pi\varepsilon_0 r^2}"
    assert expl == "Q is the enclosed charge."


def test_no_boundary_when_prefix_is_prose(app):
    """A prose-led card with a later 'where' has no credible boundary."""
    expr, expl = app._split_formula(
        "The force is the cross product of a and b. Its magnitude is |a x b| where "
        "theta is the angle between them.")
    assert expl == ""
    assert expr.startswith("The force is the cross product")


# ── the render path ───────────────────────────────────────────────────────

def test_expression_goes_to_latex_and_explanation_to_markdown(app, capture, golden):
    case = _by_shape(golden, "plain")
    app.render_math(case["content"], "formula")
    assert capture["latex"] == [case["expr"]]
    assert len(capture["markdown"]) == 1


def test_latex_argument_never_contains_the_explanation(app, capture, golden):
    """B1 regression: the prose must not reach st.latex."""
    case = _by_shape(golden, "plain")
    app.render_math(case["content"], "formula")
    latex_arg = capture["latex"][0]
    assert "where" not in latex_arg
    assert "is the electric field" not in latex_arg
    assert "Valid for" not in latex_arg


def test_latex_argument_keeps_its_closing_brace(app, capture, golden):
    """Regression: the old wrapper-strip ate the final '}' of \\frac{..}{..}."""
    case = _by_shape(golden, "plain")
    assert case["expr"].endswith("}")          # guard the guard
    app.render_math(case["content"], "formula")
    assert capture["latex"][0].endswith("}")
    assert capture["latex"][0].count("{") == capture["latex"][0].count("}")


@pytest.mark.parametrize("shape", ["no_where_prose", "prose_led"])
def test_no_boundary_renders_markdown_not_latex(app, capture, golden, shape):
    """Prose-led cards render through markdown so their embedded maths still typesets."""
    case = _by_shape(golden, shape)
    app.render_math(case["content"], "formula")
    assert capture["latex"] == []
    assert len(capture["markdown"]) == 1
    assert capture["markdown"][0].strip()


def test_colon_separator_loses_the_colon(app, capture, golden):
    """' where:' + a bulleted list: the colon is not part of the explanation."""
    case = _by_shape(golden, "colon")
    app.render_math(case["content"], "formula")
    assert capture["latex"] == [case["expr"]]
    assert not capture["markdown"][0].lstrip().startswith(":")


def test_non_formula_card_still_uses_markdown_only(app, capture):
    app.render_math(r"the value {E = mc^2} holds", "definition")
    assert capture["latex"] == []
    assert capture["markdown"] == [r"the value $E = mc^2$ holds"]
