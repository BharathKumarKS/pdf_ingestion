"""Tests for scripts/eval_gate.py (P0 item 6).

The gate must (a) refuse to compare artifacts measured at different K, and
(b) fail on a recall regression beyond tolerance. Both are the exact failure
modes that made the project's headline numbers untrustworthy.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "eval_gate.py"

ARTIFACT = """# run-name

**2026-10-04T04:40:45+00:00**

## Summary

| Scope | Recall@100 | Recall@20 | Hit@20 | MRR | NDCG@20 |
| --- | --- | --- | --- | --- | --- |
| Overall | 0.795 | 0.690 | 1.000 | 0.361 | 0.413 |
|   factual | 0.900 | 0.800 | 1.000 | 0.504 | 0.559 |

## Config

- **Tenant:** global
"""


@pytest.fixture(scope="module")
def gate():
    spec = importlib.util.spec_from_file_location("eval_gate_under_test", _SCRIPT)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _write(tmp_path: Path, name: str, text: str) -> Path:
    p = tmp_path / name
    p.write_text(text)
    return p


def _run(gate, monkeypatch, baseline: Path, candidate: Path) -> int:
    monkeypatch.setattr(sys, "argv", [
        "eval_gate", "--baseline", str(baseline), "--candidate", str(candidate),
    ])
    return gate.main()


def test_parses_summary_rows(gate):
    header, body = gate._summary_rows(ARTIFACT)
    assert header[1] == "Recall@100"
    assert body["Overall"][1] == "0.795"
    assert body["factual"][1] == "0.900"


def test_metric_extracts_value_and_k(gate):
    header, body = gate._summary_rows(ARTIFACT)
    val, k = gate._metric(header, body["Overall"], "recall")
    assert val == 0.795 and k == 100
    val, k = gate._metric(header, body["Overall"], "mrr")
    assert val == 0.361 and k is None


def test_gate_passes_on_identical(gate, tmp_path, monkeypatch):
    a = _write(tmp_path, "a.md", ARTIFACT)
    assert _run(gate, monkeypatch, a, a) == 0


def test_gate_refuses_mismatched_k(gate, tmp_path, monkeypatch):
    a = _write(tmp_path, "a.md", ARTIFACT)
    b = _write(tmp_path, "b.md", ARTIFACT.replace("Recall@100", "Recall@20"))
    assert _run(gate, monkeypatch, a, b) == 2


def test_gate_fails_on_regression(gate, tmp_path, monkeypatch):
    a = _write(tmp_path, "a.md", ARTIFACT)
    b = _write(tmp_path, "b.md", ARTIFACT.replace("| Overall | 0.795 |", "| Overall | 0.700 |"))
    assert _run(gate, monkeypatch, a, b) == 1


def test_gate_within_tolerance_passes(gate, tmp_path, monkeypatch):
    a = _write(tmp_path, "a.md", ARTIFACT)
    b = _write(tmp_path, "b.md", ARTIFACT.replace("| Overall | 0.795 |", "| Overall | 0.780 |"))
    assert _run(gate, monkeypatch, a, b) == 0  # -0.015, inside the 0.02 tolerance


def test_gate_refuses_missing_metric(gate, tmp_path, monkeypatch):
    a = _write(tmp_path, "a.md", ARTIFACT)
    b = _write(tmp_path, "b.md", "# empty\n\n## Summary\n\n| Scope | MRR |\n| --- | --- |\n| Overall | 0.5 |\n")
    assert _run(gate, monkeypatch, a, b) == 2


def test_gate_k_filter_disambiguates_two_recall_columns(gate, tmp_path, monkeypatch):
    """The summary carries Recall@100 (pool) and Recall@20 (final). --k picks one."""
    a = _write(tmp_path, "a.md", ARTIFACT)
    # candidate: pool recall unchanged, final top-20 recall drops 0.690 -> 0.500
    b = _write(tmp_path, "b.md",
               ARTIFACT.replace("| Overall | 0.795 | 0.690 |", "| Overall | 0.795 | 0.500 |"))

    # default = first matching recall column (@100) -> no regression
    monkeypatch.setattr(sys, "argv", ["eval_gate", "--baseline", str(a), "--candidate", str(b)])
    assert gate.main() == 0

    # --k 20 -> the final-ranking recall regressed by 0.19
    monkeypatch.setattr(sys, "argv",
                        ["eval_gate", "--baseline", str(a), "--candidate", str(b), "--k", "20"])
    assert gate.main() == 1