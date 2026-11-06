"""Independent verifier for the §I4 LLM-span change (O1).

Checks that `src/core/llm.py` now emits a manual `llm.call` span carrying backend / model /
json_mode / prompt_chars / latency_ms / ok / response_chars, that the failure path is marked
`ok=False`, and that the Phoenix-off no-op path is behaviour-preserving. It does NOT need a Phoenix
server: it swaps `telemetry.span` for a capturing context manager.

Run:  .venv/bin/python logs/p1/step10/llm_span_verifier.py
Exit: 0 = all checks pass.
"""
from __future__ import annotations

import sys
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from src.core import telemetry  # noqa: E402


class FakeSpan:
    def __init__(self, name, attributes=None):
        self.name = name
        self.attributes = dict(attributes or {})

    def set_attribute(self, key, value):
        self.attributes[key] = value


def fake_cfg():
    return SimpleNamespace(
        use_stub_llm=False, llm_backend="openai", openai_model="test-model",
        openai_api_base="http://cluster.invalid", openai_api_key="none",
        ollama_timeout=5, ollama_host="http://ollama.invalid", ollama_model="om",
    )


def run_checks(mod) -> dict[str, bool]:
    """Run every O1 check against `mod` (the real llm module, or a mutated copy)."""
    cfg = fake_cfg()
    checks: dict[str, bool] = {}
    captured: list[FakeSpan] = []
    orig_span = telemetry.span

    @contextmanager
    def cap(name, attributes=None):
        sp = FakeSpan(name, attributes)
        captured.append(sp)
        yield sp

    telemetry.span = cap
    try:
        # ---- success path ----
        mod._post_with_retry = lambda *a, **k: {"choices": [{"message": {"content": "world"}}]}
        captured.clear()
        out = mod.call_llm("hello", system="sys", settings=cfg)
        sp = captured[-1] if captured else None
        checks["S1 a span named llm.call is emitted"] = sp is not None and sp.name == "llm.call"
        checks["S2 attrs backend/model/json_mode/prompt_chars"] = sp is not None and (
            sp.attributes.get("backend") == "openai"
            and sp.attributes.get("model") == cfg.openai_model
            and sp.attributes.get("json_mode") is False
            and sp.attributes.get("prompt_chars") == len("hello") + len("sys"))
        lat = sp.attributes.get("latency_ms") if sp is not None else None
        checks["S3 latency_ms present and >= 0"] = isinstance(lat, (int, float)) and lat >= 0
        checks["S4 response_chars == len(response)"] = (
            sp is not None and sp.attributes.get("response_chars") == len("world"))
        checks["S5 ok True on success"] = sp is not None and sp.attributes.get("ok") is True
        checks["S6 success returns the model text"] = out == "world"

        # ---- failure path (transport returns None) ----
        mod._post_with_retry = lambda *a, **k: None
        captured.clear()
        out_fail = mod.call_llm("hello", system="sys", settings=cfg)
        spf = captured[-1] if captured else None
        checks["S7 ok False on failure"] = spf is not None and spf.attributes.get("ok") is False
        checks["S8 failure returns empty string"] = out_fail == ""
    finally:
        telemetry.span = orig_span

    # ---- Phoenix-off no-op path: the REAL span with no tracer must not change the result ----
    mod._post_with_retry = lambda *a, **k: {"choices": [{"message": {"content": "world"}}]}
    saved = telemetry._tracer
    telemetry._tracer = None
    try:
        checks["S9 no-op path (tracer None) returns text unchanged"] = \
            mod.call_llm("hello", system="sys", settings=cfg) == "world"
    finally:
        telemetry._tracer = saved
    return checks


def main() -> int:
    import src.core.llm as llm
    res = run_checks(llm)
    npass = sum(1 for ok in res.values() if ok)
    for name, ok in res.items():
        print(f"  {'PASS' if ok else 'FAIL'}  {name}")
    print(f"\n{npass}/{len(res)} checks PASS")
    return 0 if npass == len(res) else 1


if __name__ == "__main__":
    raise SystemExit(main())
