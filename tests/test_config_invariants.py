"""Config-invariant tests (P0 item 4).

Enforce three invariants so config / code can't silently drift from the real
model dimensions and enums. A drift here previously caused silent wrong results:

- ``embedding_dim`` must stay 768 (Nomic MRL) — ``.env.example`` still said
  Jina/1024d while the code had moved to Nomic.
- ``reranker_model`` must stay ``BAAI/bge-reranker-v2-m3`` — ``reranker.py``'s
  docstring still names ``ms-marco-MiniLM-L-6-v2``.
- ``CardType`` (8 members) is the single source for the DA card-type list — the
  ``index_derivative_artifacts.py`` constant had drifted to a 5-item subset, so
  example/misconception/objective cards were generated but never indexed.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

from src.core.config import Settings
from src.pdf_ingestion.card_generator import ALL_CARD_TYPES, CardType


def _default(field: str):
    """The literal default in config.py, independent of any .env on the machine."""
    return Settings.model_fields[field].default


def test_embedding_dim_default_matches_nomic():
    assert _default("embedding_model") == "nomic-ai/nomic-embed-text-v1.5"
    assert _default("embedding_dim") == 768
    assert _default("embedding_dim_low") == 64


def test_reranker_model_default_is_bge_not_msmarco():
    assert _default("reranker_model") == "BAAI/bge-reranker-v2-m3"


def test_cardtype_has_eight_members():
    # Docs (and CLAUDE.md) say 7; the enum actually has 8. Pin the exact set so
    # the count and membership can't regress silently.
    assert set(t.value for t in CardType) == {
        "summary", "definition", "example", "misconception",
        "question", "objective", "formula", "factoid",
    }


def test_da_card_types_matches_cardtype():
    # config.py can't import CardType (circular), so this is the only thing that
    # stops config.da_card_types from drifting away from the enum.
    assert set(_default("da_card_types")) == set(ALL_CARD_TYPES)


def test_embedder_honors_configured_dim(settings):
    from src.pdf_ingestion.embedder import get_embedder

    emb = get_embedder(settings)
    vec = emb.embed_query("kinetic energy")
    assert vec.shape == (settings.embedding_dim,)


def test_da_index_script_uses_cardtype_as_source():
    """DA_CARD_TYPES must be ALL_CARD_TYPES, not a hand-maintained subset."""
    script = Path(__file__).resolve().parents[1] / "scripts" / "index_derivative_artifacts.py"
    spec = importlib.util.spec_from_file_location("ida_under_test", script)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod.DA_CARD_TYPES == ALL_CARD_TYPES