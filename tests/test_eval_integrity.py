"""Regression tests for the eval harness's silent-failure paths (P0 item 2).

These guard the invariant that a dead judge or generator must never look like a
clean run. Before the fix:

- ``compute_faithfulness`` returned ``1.0`` (a *perfect* score) whenever claim
  extraction failed or produced no claims — i.e. whenever the LLM was down.
- ``make_judge_fn`` returned ``""`` on failure with only a ``logger.warning``,
  and always sent ``Authorization: Bearer`` even when the key was empty, which
  the cluster gateway rejects with HTTP 500.

Net effect: every artifact in the repo's history showed
Faithfulness / Ans.Relevance / Citation as em-dashes with no error recorded.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "evaluate_rag.py"


@pytest.fixture(scope="module")
def ev():
    """Load evaluate_rag.py as a module so its functions can be tested directly."""
    spec = importlib.util.spec_from_file_location("evaluate_rag_under_test", _SCRIPT)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def openai_args():
    return argparse.Namespace(
        judge_backend="openai",
        judge_model="openai/gpt-oss-20b",
        judge_api_base="http://example.invalid/v1",
        judge_api_key="",
    )


# ── Faithfulness: must return None (not 1.0) when it cannot be computed ──────

def test_faithfulness_none_when_answer_empty(ev):
    assert ev.compute_faithfulness("", [{"text": "p"}], lambda p: "YES") is None


def test_faithfulness_none_when_claim_extraction_empty(ev, monkeypatch):
    import src.core.llm as llm

    monkeypatch.setattr(llm, "call_llm", lambda **kw: "")
    out = ev.compute_faithfulness("answer", [{"text": "p"}], lambda p: "YES")
    assert out is None  # was 1.0 before the fix


def test_faithfulness_none_when_no_claims(ev, monkeypatch):
    import src.core.llm as llm

    monkeypatch.setattr(llm, "call_llm", lambda **kw: "[]")
    out = ev.compute_faithfulness("answer", [{"text": "p"}], lambda p: "YES")
    assert out is None


def test_faithfulness_computes_score(ev, monkeypatch):
    import src.core.llm as llm

    monkeypatch.setattr(llm, "call_llm", lambda **kw: '["claim one", "claim two"]')
    assert ev.compute_faithfulness("ans", [{"text": "p1"}], lambda p: "YES") == 1.0
    assert ev.compute_faithfulness("ans", [{"text": "p1"}], lambda p: "NO") == 0.0


def test_faithfulness_caps_judge_calls(ev, monkeypatch):
    """Uncapped, the entailment matrix is O(claims x passages) — ~200-300 calls."""
    import src.core.llm as llm

    claims = json.dumps([f"claim {i}" for i in range(200)])
    monkeypatch.setattr(llm, "call_llm", lambda **kw: claims)
    passages = [{"text": f"p{i}"} for i in range(50)]

    calls = {"n": 0}

    def judge(prompt):
        calls["n"] += 1
        return "NO"

    ev.compute_faithfulness("ans", passages, judge)
    assert calls["n"] <= ev._MAX_CLAIMS * ev._MAX_PASSAGES


# ── Judge factory: auth header + failure counting ────────────────────────────

@pytest.mark.parametrize("key", ["", "none"])
def test_judge_omits_authorization_when_key_unset(ev, openai_args, key, monkeypatch):
    import httpx

    openai_args.judge_api_key = key
    captured = {}

    class FakeResp:
        def raise_for_status(self):
            pass

        def json(self):
            return {"choices": [{"message": {"content": "YES"}}]}

    def fake_post(url, **kw):
        captured.update(kw)
        return FakeResp()

    monkeypatch.setattr(httpx, "post", fake_post)
    fn = ev.make_judge_fn(openai_args)
    assert fn("test") == "YES"
    # An empty `Authorization: Bearer` returns HTTP 500 on the cluster gateway.
    assert "Authorization" not in captured["headers"]
    assert fn.stats["calls"] == 1 and fn.stats["failures"] == 0


def test_judge_counts_failure_and_returns_empty(ev, openai_args, monkeypatch):
    import httpx

    def fake_post(*a, **kw):
        raise RuntimeError("boom")

    monkeypatch.setattr(httpx, "post", fake_post)
    fn = ev.make_judge_fn(openai_args)
    assert fn("x") == ""
    assert fn.stats["failures"] == 1
    assert fn.stats["last_error"].startswith("RuntimeError")