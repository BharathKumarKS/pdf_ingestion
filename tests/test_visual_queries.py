"""P0-9 Session 3d-ii — the visual query lane.

The visual lane's *code* landed in 3d (commit 4697961): ``embed_query_text`` +
``evaluate_rag.run_visual_retrieval``. 3d-ii adds the *queries*: a text-only generation
path in ``generate_gold_dataset.py``, a D8 judge variant in
``validate_eval_calibration.py``, and the scan that fills ``relevant_pages``.

These tests pin the parts that must not silently regress:
  - the generator proposes a visual question from a page's ``<!-- image -->`` marker,
    restricted to the content region and deduped per page;
  - a visual query is judged with the *visual* criterion (SHOWS the figure), not the
    standard "does this page answer the question" one;
  - a visual query is scanned with the dense stride, not the default stride-15 pass.

No PDF and no network: the judge call is monkeypatched.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]


def _load(script: str):
    path = _ROOT / "scripts" / script
    spec = importlib.util.spec_from_file_location(f"{script[:-3]}_under_test", path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


gen = _load("generate_gold_dataset.py")
vec = _load("validate_eval_calibration.py")


# ── Generator: candidate pages and the visual question ─────────────────────────

class _Chunk:
    def __init__(self, page_number, text):
        self.page_number = page_number
        self.text = text


_MARK = "Body text on the page.\n\n<!-- image -->\n\nFigure 1-2: a diagram of steam."


def test_image_marker_pages_requires_marker_and_range():
    chunks = [
        _Chunk(10, "front matter\n\n<!-- image -->"),   # below min_page
        _Chunk(50, "no marker here, just prose."),       # no marker
        _Chunk(60, _MARK),                               # kept
        _Chunk(900, _MARK),                              # kept
        _Chunk(950, _MARK),                              # above max_page (back matter)
    ]
    pages = [c.page_number for c in gen.image_marker_pages(chunks, 30, 936)]
    assert pages == [60, 900]


def test_image_marker_pages_dedupes_and_sorts():
    chunks = [
        _Chunk(900, _MARK),
        _Chunk(60, _MARK),
        _Chunk(60, _MARK),   # second chunk on the same page — dropped
    ]
    pages = [c.page_number for c in gen.image_marker_pages(chunks, 30, 936)]
    assert pages == [60, 900]


def test_generate_visual_question_parses_first_question(monkeypatch):
    monkeypatch.setattr(gen, "call_llm_raw",
                        lambda prompt, cfg: '["Show me the diagram of a pendulum."]')
    q = gen.generate_visual_question(_Chunk(60, _MARK), cfg=None)
    assert q == "Show me the diagram of a pendulum."


def test_visual_prompt_keeps_the_image_marker_and_forbids_prose_answers():
    # The generator is text-only: the marker is its only cue that a figure is present,
    # and the question must not be answerable from prose alone.
    assert "<!-- image -->" in gen._VISUAL_PROMPT
    assert "not by reading prose" in gen._VISUAL_PROMPT


# ── Judge variant: visual questions use the visual criterion ───────────────────

def test_judge_template_routes_visual_to_the_visual_prompt():
    assert vec.judge_template("visual") is vec._VISUAL_JUDGE_PROMPT
    assert vec.judge_template("overview") is vec._OVERVIEW_JUDGE_PROMPT
    assert vec.judge_template("factual") is vec._JUDGE_PROMPT


def test_visual_judge_prompt_asks_about_the_specific_figure():
    p = vec._VISUAL_JUDGE_PROMPT
    assert "ONE SPECIFIC figure" in p and "figure" in p
    # It must force a strict subject match, not accept any figure.
    assert "Be strict" in p
    # It must NOT reuse the "answers the question" wording of the standard prompt.
    assert "genuinely useful for answering" not in p


def test_coarse_stride_is_dense_for_visual():
    class _Args:
        visual_stride = 4
        overview_stride = 4
        scan_stride = 15

    assert vec.coarse_stride(_Args(), "visual") == 4
    assert vec.coarse_stride(_Args(), "overview") == 4
    assert vec.coarse_stride(_Args(), "factual") == 15


def test_judge_page_sends_the_visual_prompt(monkeypatch):
    """A visual query must reach the judge with the visual template, not the standard."""
    seen = {}

    def _fake_call_judge(prompt, args, image_b64=None):
        seen["prompt"] = prompt
        return "YES\nthe page shows the described diagram"

    monkeypatch.setattr(vec, "call_judge", _fake_call_judge)

    class _Store:
        n_pages = 100

        def text(self, p):
            return "prose that does not mention the figure"

        def image_b64(self, p):
            return None

    class _Args:
        judge_backend = "openai"
        judge_api_base = "http://x"
        judge_api_key = ""
        judge_model = "Qwen/Qwen3-VL-8B-Instruct"
        workers = 1

    query = {"id": "vis-001", "query": "Show me the diagram of X",
             "query_type": "visual"}
    r = vec._judge_page(query, 5, _Store(), _Args(), cache=None)
    assert r["verdict"] == "YES"
    assert "ONE SPECIFIC figure" in seen["prompt"]


if __name__ == "__main__":
    pytest.main([__file__, "-q"])
