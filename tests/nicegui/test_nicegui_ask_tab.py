"""NG-P2 — headless UI test for the NiceGUI Ask-a-Question tab.

Drives the REAL tab through NiceGUI's user simulation (httpx/ASGITransport — no browser), so it
proves the wiring the function-level acceptance harness cannot: input → Search → ``run.io_bound``
→ answer markdown + sources + source table.

The backend is faked at the module boundary `run_ask` imports *inside* the function, so the fakes
take effect without touching the retrieval code. One fake records the THREAD it ran on — the whole
point of ``run.io_bound`` is that the blocking call leaves the event loop, so the test asserts it
ran off the main thread.

⚠️ This test needs NiceGUI's user-simulation plugin, which — loaded globally — breaks 11 unrelated
tests in this suite, so it is NOT loaded by default. It is skipped unless explicitly enabled:

    NICEGUI_UI_TESTS=1 .venv/bin/python -m pytest \
        -p nicegui.testing.user_plugin tests/nicegui/test_nicegui_ask_tab.py -q
"""
from __future__ import annotations

import os

import pytest

if os.environ.get("NICEGUI_UI_TESTS") != "1":
    pytest.skip(
        "NiceGUI UI test — run with NICEGUI_UI_TESTS=1 and -p nicegui.testing.user_plugin",
        allow_module_level=True,
    )

import threading  # noqa: E402

import numpy as np  # noqa: E402
from nicegui import ui  # noqa: E402

pytestmark = pytest.mark.nicegui_main_file("src/frontend/nicegui_app.py")

ANSWER = "The net force on a body equals its mass times its acceleration (page 42)."


def _install_fakes(monkeypatch: pytest.MonkeyPatch, seen: dict) -> None:
    import src.core.intent_router as ir_mod
    import src.core.llm as llm_mod
    import src.pdf_ingestion.cluster_embedder as ce_mod
    import src.pdf_ingestion.reranker as rr_mod
    import src.pdf_ingestion.store as store_mod

    class _Emb:
        def embed_query(self, _text: str) -> np.ndarray:
            return np.zeros(768, dtype=np.float32)

    monkeypatch.setattr(ce_mod, "get_cluster_embedder", lambda cfg: _Emb())

    class _Store:
        def __init__(self, _cfg) -> None:
            pass

        def search_with_das(self, **_kw) -> list[dict]:
            seen["thread"] = threading.current_thread().name
            seen["on_main_thread"] = threading.current_thread() is threading.main_thread()
            return [
                {"chunk_id": "c1", "page_number": 42, "text": "F = m a.", "score": 0.7,
                 "source_type": "base_textbook"},
                {"chunk_id": "c2", "page_number": 43, "text": "Momentum is conserved.",
                 "score": 0.5, "source_type": "base_textbook"},
            ]

        def search_raptor(self, **_kw) -> list[dict]:
            return []

    monkeypatch.setattr(store_mod, "DocumentStore", _Store)

    class _RR:
        def rerank(self, query, chunks, top_k):
            return chunks[:top_k]

    monkeypatch.setattr(rr_mod, "get_reranker", lambda cfg: _RR())

    class _Router:
        def classify(self, _q) -> str:
            return "factual"  # ROUTE_MAP["factual"] -> no raptor, no graph lane

    monkeypatch.setattr(ir_mod, "get_intent_router", lambda cfg=None: _Router())
    monkeypatch.setattr(llm_mod, "call_llm", lambda **kw: ANSWER)


async def test_ask_tab_renders_answer_off_the_event_loop(user, monkeypatch):
    seen: dict = {}
    _install_fakes(monkeypatch, seen)

    await user.open("/")
    user.find(marker="ask-input").type("What is Newton's second law?")
    user.find(marker="ask-button").click()

    await user.should_see(ANSWER, retries=50)                      # the answer markdown rendered
    await user.should_see("📄 Sources cited: p. 42", retries=50)   # the citation line rendered
    user.find(ui.expansion)                                        # source-passage section exists

    assert seen, "run_ask never reached the fake store — the Search handler did not run"
    assert seen["on_main_thread"] is False, (
        "the blocking retrieval ran ON the event loop — run.io_bound is not offloading "
        f"(thread={seen['thread']!r})"
    )
