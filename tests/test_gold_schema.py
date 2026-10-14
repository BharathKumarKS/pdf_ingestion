"""The v2 gold set must be loadable by evaluate_rag.py and must carry `answerable`."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
_V2 = _ROOT / "data" / "eval_queries_v2.json"

_REQUIRED = {"id", "query", "query_type", "answerable"}


def _load():
    if not _V2.exists():
        pytest.skip("v2 gold set not generated yet")
    return json.loads(_V2.read_text())


def test_every_entry_has_required_fields():
    for e in _load():
        if e["id"].startswith("_"):
            continue
        missing = _REQUIRED - set(e)
        assert not missing, f"{e['id']} missing {missing}"


def test_answerable_is_bool():
    for e in _load():
        if e["id"].startswith("_"):
            continue
        assert isinstance(e["answerable"], bool), f"{e['id']}: {e['answerable']!r}"


def test_answerable_entries_have_pages():
    for e in _load():
        if e["id"].startswith("_") or not e["answerable"]:
            continue
        assert e.get("relevant_pages"), f"{e['id']} is answerable but has no pages"


def test_negative_entries_have_no_pages():
    for e in _load():
        if e["id"].startswith("_") or e["answerable"]:
            continue
        assert not e.get("relevant_pages"), f"{e['id']} is a negative but has pages"


def test_negatives_are_at_least_15_percent():
    qs = [e for e in _load() if not e["id"].startswith("_")]
    negs = [e for e in qs if not e["answerable"]]
    assert len(negs) / len(qs) >= 0.15, f"only {len(negs)}/{len(qs)} negatives"


def test_abstention_helper_recognises_declining_answers():
    import importlib.util
    from pathlib import Path as P

    root = P(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location("ev2", root / "scripts" / "evaluate_rag.py")
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    class Cfg:
        visual_score_threshold = 0.0

    assert mod._looks_like_abstention("This is not covered in the book.", [], Cfg())
    assert not mod._looks_like_abstention("Kinetic energy is 1/2 mv^2.", [], Cfg())
