"""The concept extractor's model is chosen per stage, and the choice must actually take effect.

§I23(c) settled the extraction model on measured evidence (`IMPROVEMENTS.md` §I23,
`logs/p1/step10/i23c_extraction_model_compare.json`): `Qwen/Qwen3-VL-8B-Instruct` at 3.2-3.6x the
speed of `openai/gpt-oss-20b` for the same concept volume. It lives in `config.yaml` under
`concept_extraction`, so it can differ from the card/RAPTOR model.

What has to be true, and is pinned here rather than assumed:

1. **The section wins** when it names a model.
2. **The fallback is unchanged** when the section is absent — a checkout without `config.yaml`
   behaves exactly as it did before, using `.env`'s model.
3. **The call actually uses it.** `_extract_concepts` must hand the resolved settings to `call_llm`;
   a resolution nothing reads is the §I23(d) failure mode, one line away from being invisible.
4. **The checkpoint key agrees with the call.** `_extraction_model()` is part of the checkpoint's
   identity, so if it resolved differently from the model the call used, a checkpoint would be
   labelled with a model that did not produce it — and a later resume would trust the wrong one.
5. **Query-time extraction uses the same model as index-time.** Different models name concepts
   differently, so a mismatch manufactures the §G3 defect: the query misses nodes the graph holds.

Offline: `call_llm` is replaced, and no Memgraph connection is made (the driver is lazy).
"""
from __future__ import annotations

import pytest

from src.core.config import Settings
from src.pdf_ingestion.graph_builder import GraphBuilder


@pytest.fixture
def builder(monkeypatch):
    """A real GraphBuilder with a controlled `concept_extraction` section."""
    def _make(section: dict | None, backend: str = "openai"):
        import src.core.pipeline_config as pc
        monkeypatch.setattr(pc, "get_section", lambda name: (section or {}) if name == "concept_extraction" else {})
        cfg = Settings(llm_backend=backend, openai_model="openai/gpt-oss-20b",
                       ollama_model="llama3.2")
        return GraphBuilder(settings=cfg)
    return _make


class TestResolution:
    def test_section_model_wins(self, builder):
        b = builder({"model": "Qwen/Qwen3-VL-8B-Instruct"})
        assert b._extraction_model() == "Qwen/Qwen3-VL-8B-Instruct"
        assert b._extraction_settings().openai_model == "Qwen/Qwen3-VL-8B-Instruct"

    def test_absent_section_falls_back_to_env(self, builder):
        b = builder({})
        assert b._extraction_model() == "openai/gpt-oss-20b"
        assert b._extraction_settings().openai_model == "openai/gpt-oss-20b"

    def test_blank_model_falls_back(self, builder):
        """A section that exists but names nothing must not blank the model out."""
        b = builder({"model": "   "})
        assert b._extraction_model() == "openai/gpt-oss-20b"

    def test_ollama_backend_gets_the_ollama_field(self, builder):
        """The section is backend-agnostic; it must land on the field that backend reads."""
        b = builder({"model": "some/local-model"}, backend="ollama")
        assert b._extraction_model() == "some/local-model"
        assert b._extraction_settings().openai_model == "openai/gpt-oss-20b"  # untouched

    def test_section_base_url_is_honoured(self, builder):
        b = builder({"model": "m", "base_url": "http://example.invalid:9999/v1"})
        assert b._extraction_settings().openai_api_base == "http://example.invalid:9999/v1"


class TestTheCallUsesIt:
    def _capture(self, monkeypatch) -> dict:
        """Replace `call_llm` and record the settings object it was handed."""
        import src.core.llm as llm
        seen: dict = {}

        def _fake(prompt, system="", settings=None, timeout=None, json_mode=False):
            seen["settings"] = settings
            seen["prompt_head"] = prompt[:60]
            return '{"concepts": [{"name": "kinetic energy", "type": "quantity"}], "prerequisites": []}'

        monkeypatch.setattr(llm, "call_llm", _fake)
        return seen

    def test_index_time_call_uses_the_resolved_model(self, builder, monkeypatch):
        b = builder({"model": "Qwen/Qwen3-VL-8B-Instruct"})
        seen = self._capture(monkeypatch)
        out = b._extract_concepts("some physics text " * 20)
        assert out["ok"] is True
        assert seen["settings"].openai_model == "Qwen/Qwen3-VL-8B-Instruct"

    def test_checkpoint_key_agrees_with_the_call(self, builder, monkeypatch):
        """The invariant: the model in the key is the model that made the record."""
        b = builder({"model": "Qwen/Qwen3-VL-8B-Instruct"})
        seen = self._capture(monkeypatch)
        b._extract_concepts("text " * 100)
        key_model = b._extraction_model()
        called_with = (seen["settings"].openai_model
                       if seen["settings"].llm_backend == "openai"
                       else seen["settings"].ollama_model)
        assert key_model == called_with == "Qwen/Qwen3-VL-8B-Instruct"

    def test_query_time_call_uses_the_same_model(self, builder, monkeypatch):
        """Index-time and query-time must not diverge (§G3 manufactured on purpose)."""
        b = builder({"model": "Qwen/Qwen3-VL-8B-Instruct"})
        seen = self._capture(monkeypatch)
        b._extract_query_concepts("what is kinetic energy?")
        assert seen["settings"].openai_model == "Qwen/Qwen3-VL-8B-Instruct"

    def test_a_failed_call_still_reports_not_ok(self, builder, monkeypatch):
        """The §I23 contract survives the settings change."""
        import src.core.llm as llm
        b = builder({"model": "Qwen/Qwen3-VL-8B-Instruct"})

        def _boom(*a, **k):
            raise RuntimeError("endpoint down")

        monkeypatch.setattr(llm, "call_llm", _boom)
        out = b._extract_concepts("text " * 100)
        assert out["ok"] is False and out["concepts"] == []
